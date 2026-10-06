#!/usr/bin/env python3
"""An instrument for reading the market, not a rule for trading it.

WHY THIS IS A DIFFERENT KIND OF WORK, STATISTICALLY

  Everything else in this repo SELECTS: it searches a space of rules and
  reports the winner, which is why the ledger's floor sits at |t| > 4.72 after
  827 hypotheses and why rigorous_search.py found 0 of 21,889 rules beating a
  simulated null.

  This ESTIMATES. "Gold's spread at 21:00 UTC is 3.0x the cost, per unit of
  movement, that it is at 14:00" is a measurement of the instrument being
  traded, not a hypothesis selected from alternatives. There is no
  maximum-of-N inflation to correct for because nothing is being maximised -
  every hour is reported, the boring ones included, and each number carries an
  error bar rather than a claim that it beat its rivals.

THE LINE THAT MUST NOT BE CROSSED

  The moment this table is scanned for "the best hour to trade", it becomes a
  search over 24 hypotheses and every problem returns. Refusing an hour whose
  cost ratio is three times the median is a COST decision and needs no
  significance test. Choosing an hour because returns were positive there is a
  RULE, and would.

THE INSTRUMENT SCORES ITSELF

  Every run returns a quality report alongside the measurements:

    coverage    the share of cells that came back usable at all
    precision   how tight the bootstrap intervals are, relative to the
                quantity being measured
    resolution  how much of the spread ACROSS hours is real structure rather
                than sampling noise - an intraclass ratio, so an instrument
                that reports 24 different-looking numbers which are all the
                same number plus noise scores near zero

  That triple is what makes "tune the instrument and measure again" mean
  something other than moving numbers around until they look nicer.
"""
import argparse
import json
import math
import pathlib
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from p01_cross_market import MARKETS, load_bidask_h1

NY = ZoneInfo("America/New_York")
LDN = ZoneInfo("Europe/London")
SEED = 17
VERSION = 2

# The instrument's tunable knobs. These control how WELL it measures, not
# what it concludes - raising BOOT narrows a confidence interval, it does not
# move an estimate toward a preferred answer. profile_iterate.py does
# coordinate ascent on these against the quality score, which is calibration
# rather than selection.
PARAMS = dict(
    boot=800,          # bootstrap resamples
    atr_hours=480,     # volatility scale, in wall-clock hours
    bucket=1,          # hours per bucket; <1 splits the hour
    min_cell=200,      # bars required before a cell is reported
    tail_q=0.99,       # quantile that defines a tail
    vap_bins=40,       # price buckets in the volume profile
    vap_window="1D",   # volume-profile window
    vr_k=4,            # variance-ratio horizon, in bars
)
BOOT = PARAMS["boot"]

# bars per hour, and the ATR window each timeframe should use so that the
# volatility scale covers a comparable stretch of wall-clock time rather than
# a comparable number of bars
TF = {"M1": dict(rule="1min", per_h=60), "M5": dict(rule="5min", per_h=12),
      "M15": dict(rule="15min", per_h=4), "H1": dict(rule="1h", per_h=1),
      "H4": dict(rule="4h", per_h=0.25)}


# ----------------------------------------------------------------- data ----
def resample(src, rule):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last",
           "volume": "sum",
           "bid_open": "first", "bid_high": "max", "bid_low": "min",
           "bid_close": "last", "ask_open": "first", "ask_high": "max",
           "ask_low": "min", "ask_close": "last"}
    use = {k: v for k, v in agg.items() if k in src.columns}
    return src.resample(rule).agg(use).dropna(subset=["close"])


def load_tf(sym, tf):
    """H1 and coarser come from the H1 cache; M1/M5/M15 need the minute cache,
    which exists for gold only."""
    spec = TF[tf]
    if spec["per_h"] <= 1:
        df = load_bidask_h1(sym)
        if df is None:
            return None
        for k in ("open", "high", "low", "close"):
            if k not in df:
                df[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
        return df if tf == "H1" else resample(df, spec["rule"])
    if sym != "XAUUSD":
        return None
    import fetch_dukascopy as D
    m = D.load("2019-01-01", None, verbose=False)
    if m is None or len(m) == 0:
        return None
    for k in ("open", "high", "low", "close"):
        m[k] = (m[f"bid_{k}"] + m[f"ask_{k}"]) / 2
    return m if tf == "M1" else resample(m, spec["rule"])


def prep(df, tf):
    """Shared columns. The ATR window is set in HOURS, not bars, so the
    volatility scale means the same thing on M1 as on H4 - a fixed bar count
    would make the M1 scale cover eight hours and the H4 scale eighty days."""
    d = df.copy()
    d = d[(d["ask_close"] - d["bid_close"]) > 0]
    d = d[(d.high >= d.low) & (d.close > 0)]
    d = d[(d.index.dayofweek < 5) |
          ((d.index.dayofweek == 5) & (d.index.hour == 0))]
    d["spread"] = d["ask_close"] - d["bid_close"]
    tr = np.maximum(d.high - d.low,
                    np.maximum((d.high - d.close.shift()).abs(),
                               (d.low - d.close.shift()).abs()))
    d["tr"] = tr
    win = max(int(TF[tf]["per_h"] * PARAMS["atr_hours"]), 20)
    d["atr"] = tr.rolling(win, min_periods=win // 4).median().shift()
    d["ret"] = np.log(d.close / d.close.shift())
    d["gap"] = (d.open - d.close.shift()).abs()
    d["hour"] = d.index.hour
    d["dow"] = d.index.dayofweek
    d["day"] = d.index.normalize()
    return d.dropna(subset=["atr"])


def volume_usable(d):
    """Whether this feed's volume column can carry any weight.

    Dukascopy reports gold volume in lots (median 0.55) and EURUSD in ticks
    (median 5,038), and about 30% of bars are zero in both. A column that is
    zero a third of the time, on a scale that means something different per
    symbol, cannot be compared across markets and must not be silently
    averaged into a liquidity claim."""
    v = d["volume"] if "volume" in d else None
    if v is None or len(v) == 0:
        return dict(usable=False, why="absent")
    zero = float((v == 0).mean())
    if zero > 0.5:
        return dict(usable=False, why=f"{zero*100:.0f}% zero", zero=zero)
    if float(v.median()) <= 0:
        return dict(usable=False, why="median zero", zero=zero)
    return dict(usable=True, zero=zero, median=float(v.median()),
                unit="lots" if v.median() < 100 else "ticks")


# ------------------------------------------------------------ estimation ---
def boot(x, groups, stat=np.median, reps=None, seed=SEED):
    """Bootstrap resampling whole DAYS - hours inside a day are not
    independent draws, since a quiet Tuesday makes all of its hours quiet."""
    x = np.asarray(x, float)
    g = np.asarray(groups)
    ok = np.isfinite(x)
    x, g = x[ok], g[ok]
    if len(x) < 50:
        return np.nan, np.nan, np.nan
    keys = np.unique(g)
    if len(keys) < 20:
        return np.nan, np.nan, np.nan
    reps = int(reps or PARAMS["boot"])
    buckets = [x[g == k] for k in keys]
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    for i in range(reps):
        pick = rng.integers(0, len(buckets), len(buckets))
        out[i] = stat(np.concatenate([buckets[p] for p in pick]))
    return float(stat(x)), float(np.percentile(out, 2.5)), \
        float(np.percentile(out, 97.5))


def session_of(idx):
    ny = idx.tz_convert(NY).hour
    ldn = idx.tz_convert(LDN).hour
    lab = np.full(len(idx), "asia", dtype="<U7")
    lab[(ldn >= 8) & (ldn < 17)] = "london"
    lab[(ny >= 8) & (ny < 17)] = "ny"
    lab[((ldn >= 8) & (ldn < 17)) & ((ny >= 8) & (ny < 17))] = "overlap"
    return lab


def hour_map(d, sym, tf, vol_ok):
    rows = []
    tail_q = float(np.nanquantile((d.tr / d.atr), PARAMS["tail_q"]))
    bk = PARAMS["bucket"]
    slots = np.arange(0, 24, bk)
    frac = (d.index.hour + d.index.minute / 60.0).to_numpy()
    for h in slots:
        m = (frac >= h) & (frac < h + bk)
        if m.sum() < PARAMS["min_cell"]:
            continue
        cv = (d.spread[m] / d.tr[m]).replace([np.inf, -np.inf], np.nan)
        med, lo, hi = boot(cv, d.day[m])
        rr = (d.tr[m] / d.atr[m])
        rows.append(dict(
            symbol=sym, tf=tf, hour=h, n=int(m.sum()),
            session=pd.Series(session_of(d.index[m])).mode()[0],
            spread=float(d.spread[m].median()),
            move_atr=float(rr.median()),
            cost_range=med, cr_lo=lo, cr_hi=hi,
            volume=float(d.volume[m].median()) if vol_ok else np.nan,
            tail_pct=float((rr > tail_q).mean()) * 100,
            gap_atr=float((d.gap[m] / d.atr[m]).median())))
    return pd.DataFrame(rows), tail_q


def variance_ratio(d, h, k=4):
    r = d.ret.to_numpy()
    idx = np.where(d.hour.to_numpy() == h)[0]
    idx = idx[(idx + k) < len(r)]
    if len(idx) < 200:
        return np.nan
    one = r[idx]
    many = np.array([r[i:i + k].sum() for i in idx])
    v1 = one.var(ddof=1)
    return float(many.var(ddof=1) / (k * v1)) if v1 > 0 else np.nan


def volume_at_price(d, window="1D", bins=40, vol_ok=True):
    """Where price spends its time, and whether it returns there.

    When the volume column is unusable the histogram is weighted by TIME
    instead - one unit per bar - which measures the same thing a tick-volume
    profile approximates anyway, and says so rather than weighting by a column
    that is zero a third of the time."""
    rows, touch = [], []
    gm = d.groupby(pd.Grouper(freq=window))
    groups = [(t, g) for t, g in gm if len(g) >= 6]
    for i, (ts, g) in enumerate(groups):
        lo, hi = float(g.low.min()), float(g.high.max())
        if not np.isfinite([lo, hi]).all() or hi <= lo:
            continue
        edges = np.linspace(lo, hi, bins + 1)
        mid = ((g.high + g.low) / 2).to_numpy()
        w = (g.volume.to_numpy() if vol_ok else np.ones(len(g)))
        hist, _ = np.histogram(mid, bins=edges, weights=w)
        if hist.sum() <= 0:
            continue
        centers = (edges[:-1] + edges[1:]) / 2
        order = np.argsort(-hist)
        cum = np.cumsum(hist[order]) / hist.sum()
        keep = centers[order[:int(np.searchsorted(cum, 0.70)) + 1]]
        rows.append(dict(t=ts, poc=float(centers[int(np.argmax(hist))]),
                         va_lo=float(keep.min()), va_hi=float(keep.max()),
                         rng=hi - lo, close=float(g.close.iloc[-1])))
        if i + 1 < len(groups):
            g2 = groups[i + 1][1]
            touch.append(bool(g2.low.min() <= keep.max()
                              and g2.high.max() >= keep.min()))
    V = pd.DataFrame(rows)
    if len(V) < 20:
        return V, {}
    return V, dict(
        n_windows=len(V), weighted_by="volume" if vol_ok else "time",
        va_width_pct=float(((V.va_hi - V.va_lo) / V.rng).median()) * 100,
        next_touches_va=float(np.mean(touch)) * 100 if touch else np.nan,
        close_in_va=float(((V.close >= V.va_lo) &
                           (V.close <= V.va_hi)).mean()) * 100)


# -------------------------------------------------------------- quality ----
def quality(H):
    """How good is the instrument, as a number, so tuning can be judged.

    coverage    share of hour-cells with a finite estimate AND a finite CI
    precision   1 / (1 + median relative CI half-width) - tight intervals
                score near 1, intervals as wide as the estimate score near 0.5
    resolution  the share of variance ACROSS hours that survives the sampling
                noise inside each hour. An instrument reporting 24 numbers
                that are one number plus noise scores near 0 here however
                pretty the table looks."""
    if H is None or len(H) == 0:
        return dict(coverage=0.0, precision=0.0, resolution=0.0, score=0.0)
    fin = H.cost_range.notna() & H.cr_lo.notna() & H.cr_hi.notna()
    coverage = float(fin.mean())
    g = H[fin]
    if len(g) < 4:
        return dict(coverage=coverage, precision=0.0, resolution=0.0, score=0.0)
    half = (g.cr_hi - g.cr_lo) / 2.0
    rel = float(np.median(half / g.cost_range.abs().clip(lower=1e-12)))
    precision = 1.0 / (1.0 + rel)
    between = float(np.var(g.cost_range, ddof=1))
    within = float(np.mean((half / 1.96) ** 2))
    resolution = between / (between + within) if (between + within) > 0 else 0.0
    return dict(coverage=coverage, precision=precision,
                resolution=float(resolution),
                score=float(coverage * precision * resolution))


def profile(sym, tf):
    bars = load_tf(sym, tf)
    if bars is None or len(bars) < 5000:
        return None
    d = prep(bars, tf)
    if len(d) < 5000:
        return None
    vu = volume_usable(d)
    H, tail_q = hour_map(d, sym, tf, vu["usable"])
    V, vstats = volume_at_price(d, window=PARAMS["vap_window"],
                                bins=PARAMS["vap_bins"], vol_ok=vu["usable"])
    vr = {h: variance_ratio(d, h, k=PARAMS["vr_k"]) for h in range(24)}
    return dict(symbol=sym, tf=tf, version=VERSION, bars=len(d),
                params=dict(PARAMS),
                hours=H, vol=vu, vap=vstats, vr=vr, tail_q=tail_q,
                quality=quality(H))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="H1")
    ap.add_argument("--symbols", default="XAUUSD,EURUSD")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print(f"MARKET PROFILE v{VERSION} - {a.tf}")
    print("=" * 100)
    allH, q = [], {}
    for s in syms:
        r = profile(s, a.tf)
        if r is None:
            print(f"  {s:<9} no usable data at {a.tf}")
            continue
        allH.append(r["hours"])
        q[s] = r["quality"]
        print(f"\n  {s}  {r['bars']:,} bars   volume: "
              f"{'usable (' + r['vol'].get('unit', '?') + ')' if r['vol']['usable'] else 'UNUSABLE - ' + r['vol']['why']}")
        print(f"  quality  coverage {r['quality']['coverage']:.2f}  "
              f"precision {r['quality']['precision']:.3f}  "
              f"resolution {r['quality']['resolution']:.3f}  "
              f"=> {r['quality']['score']:.3f}")
        if r["vap"]:
            v = r["vap"]
            print(f"  value area ({v['weighted_by']}-weighted): "
                  f"{v['va_width_pct']:.1f}% of range, next window touches "
                  f"{v['next_touches_va']:.1f}%, close inside "
                  f"{v['close_in_va']:.1f}%")
        if a.quiet:
            continue
        H = r["hours"]
        med = H.cost_range.median()
        print(f"  {'hr':>3} {'session':<8}{'spread':>10}{'mv/ATR':>8}"
              f"{'cost/rng':>10}{'95% CI':>17}{'tail%':>7}{'VR4':>7}{'vs med':>8}")
        for _, x in H.iterrows():
            ci = (f"[{x.cr_lo*100:5.2f},{x.cr_hi*100:5.2f}]"
                  if np.isfinite(x.cr_lo) else f"{'-':^17}")
            v = r["vr"].get(int(x.hour), np.nan)
            flag = ""
            if np.isfinite(x.cr_lo) and x.cr_lo > med * 1.5:
                flag = "  EXPENSIVE"
            elif np.isfinite(x.cr_hi) and x.cr_hi < med * 0.75:
                flag = "  cheap"
            vr = f"{v:>7.2f}" if np.isfinite(v) else f"{'-':>7}"
            print(f"  {int(x.hour):>3} {x.session:<8}{x.spread:>10.5f}"
                  f"{x.move_atr:>8.2f}{x.cost_range*100:>9.2f}%{ci:>17}"
                  f"{x['tail_pct']:>6.1f}%{vr}{x.cost_range/med:>7.2f}x{flag}")
    if allH:
        out = HERE / f"market_profile_{a.tf}.csv"
        pd.concat(allH, ignore_index=True).to_csv(out, index=False)
        print(f"\n  -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
