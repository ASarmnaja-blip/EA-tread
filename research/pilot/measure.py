"""
Measurement engine — built FROM the chart, not applied TO setups.

The pilot answers "did this fixed rule survive the gate". That is a statement
about eighteen rules written months ago. It is not a statement about what the
market is currently paying for, which is what CLAUDE.md section 9 actually
asks for.

This module inverts the direction. It describes the chart in layers, and the
only outcome it measures is what price DOES after each state - never what a
strategy earned there. No PnL, no Sharpe, no win rate appears anywhere in the
measurement or its quality report, because a measurement scored by the
profitability of the thing it measures cannot be used to judge that thing.

Layers, in the order they depend on each other:

    1 tradability        what it costs to be here at all
    2 activity           how much the market is moving
    3 structure          what shape the last moves made
    4 context            session, news proximity, positioning, cross-asset
    5 regime             the combination, as a label and a continuous score
    6 execution          how reliably an exit can be resolved here
    7 behaviour          what price then does - the dependent variable
    8 quality            whether any of the above is measured well enough to use

Knobs are labelled where they appear:
    [CAL] calibration/precision - changes the estimate's sharpness
    [DEF] quantity definition   - changes WHAT is being measured, so a change
                                  here makes a different quantity and the
                                  estimate history does not carry over
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

# ------------------------------------------------------------------ knobs
ATR_N = 14                 # [DEF] the volatility unit everything is scaled by
PCT_WINDOW = 288 * 5       # [CAL] ~5 trading days of M5 for percentile ranks
SWING_K = 3                # [DEF] fractal half-width for a swing point
HORIZONS = (12, 36, 72)    # [DEF] 1h, 3h, 6h on M5 - the outcome windows
DISPLACE_ATR = 1.5         # [DEF] a bar is a displacement above this many ATR
SWEEP_LOOKBACK = 48        # [DEF] bars whose extreme a sweep must exceed
NEWS_NEAR_MIN = 30         # [DEF] minutes either side counted as "at news"
ROLLOVER_HOUR_UTC = 21     # measured from the data, see rollover_hour()

COST_SPREAD = 0.260        # measured on the account that will be traded
COST_SLIPPAGE = 0.10       # ASSUMED per fill - the largest unmeasured term
SWAP_LONG_PER_OZ = 0.5493  # measured, longs only
STOP_ATR = 1.5             # [DEF] the R unit: risk = STOP_ATR * ATR


# ---------------------------------------------------------------- helpers
def _roll_pct(x: np.ndarray, window: int) -> np.ndarray:
    """Percentile rank of x[i] within the PRIOR window values. Excludes i, so
    nothing here can see its own bar."""
    return core.rolling_pct_rank(x, window)


def _fwd_max(h: np.ndarray, k: int) -> np.ndarray:
    """max of the NEXT k values (exclusive of the current bar)."""
    n = len(h)
    out = np.full(n, np.nan)
    if k < 1:
        return out
    s = pd.Series(h)
    out[:n - k] = s.shift(-1).rolling(k).max().shift(-(k - 1)).values[:n - k]
    return out


def _fwd_min(l: np.ndarray, k: int) -> np.ndarray:
    n = len(l)
    out = np.full(n, np.nan)
    if k < 1:
        return out
    s = pd.Series(l)
    out[:n - k] = s.shift(-1).rolling(k).min().shift(-(k - 1)).values[:n - k]
    return out


def rollover_hour(b: D.Bars) -> int:
    """The hour with the fewest bars is the maintenance break; the swap is
    charged across it. Measured rather than assumed, because a wrong rollover
    hour silently misprices every overnight position."""
    h = pd.to_datetime(b.t, unit="s", utc=True).hour
    counts = pd.Series(h).value_counts()
    return int(counts.idxmin())


# ------------------------------------------------------- 1..6 state layers
def build_states(b5: D.Bars, cal: pd.DataFrame | None = None,
                 dxy: D.Bars | None = None) -> pd.DataFrame:
    """Everything knowable at the close of each M5 bar, and nothing later."""
    n = len(b5)
    t = pd.to_datetime(b5.t, unit="s", utc=True)
    df = pd.DataFrame({"t": t, "o": b5.o, "h": b5.h, "l": b5.l, "c": b5.c,
                       "v": b5.v})
    if b5.sp is not None:
        df["spread_file"] = b5.sp

    atr = core.atr(b5, ATR_N)
    df["atr"] = atr
    rng = b5.h - b5.l
    df["range"] = rng

    # ---------------- 1 tradability
    risk = STOP_ATR * atr                       # price distance of one R
    cost = COST_SPREAD + 2 * COST_SLIPPAGE      # round turn, price units
    with np.errstate(divide="ignore", invalid="ignore"):
        df["friction_R"] = cost / risk          # what one round turn costs in R
        df["spread_over_atr"] = COST_SPREAD / atr
        df["spread_over_range"] = np.where(rng > 0, COST_SPREAD / rng, np.nan)
    hour = t.hour
    df["hour"] = hour
    df["session"] = np.select(
        [hour == ROLLOVER_HOUR_UTC,
         (hour >= 22) | (hour < 7),
         (hour >= 7) & (hour < 13),
         (hour >= 13) & (hour < 16),
         (hour >= 16) & (hour < 21)],
        ["BREAK", "ASIA", "LONDON", "OVERLAP", "NY"], default="OTHER")
    # swap only bites a position carried across the break
    bars_to_roll = ((ROLLOVER_HOUR_UTC - hour) % 24) * 12 - (t.minute // 5)
    df["bars_to_rollover"] = bars_to_roll
    with np.errstate(divide="ignore", invalid="ignore"):
        df["swap_R_if_held_long"] = SWAP_LONG_PER_OZ / risk

    gap = np.concatenate(([0.0], np.diff(b5.t))) / 60.0
    df["gap_min_before"] = gap
    df["after_gap"] = gap > 20                  # [DEF] 4 missing M5 bars

    # ---------------- 2 activity
    df["tr_over_atr"] = np.where(atr > 0, rng / atr, np.nan)
    df["atr_pct"] = _roll_pct(atr, PCT_WINDOW)
    df["vol_pct"] = _roll_pct(np.asarray(b5.v, dtype=float), PCT_WINDOW)
    logc = np.log(np.maximum(b5.c, 1e-9))
    r1 = np.concatenate(([0.0], np.diff(logc)))
    df["rv_12"] = pd.Series(r1).rolling(12).std().values * np.sqrt(12)
    df["rv_72"] = pd.Series(r1).rolling(72).std().values * np.sqrt(72)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["expansion"] = atr / pd.Series(atr).shift(72).values
        df["vol_of_vol"] = (pd.Series(df["rv_12"]).rolling(72).std().values
                            / np.maximum(pd.Series(df["rv_12"]).rolling(72).mean().values, 1e-12))

    # ---------------- 3 structure
    hh = core.rolling_max(b5.h, SWEEP_LOOKBACK)
    ll = core.rolling_min(b5.l, SWEEP_LOOKBACK)
    df["swept_high"] = (b5.h > hh) & (b5.c < hh)      # took it and closed back
    df["swept_low"] = (b5.l < ll) & (b5.c > ll)
    df["broke_high"] = b5.c > hh
    df["broke_low"] = b5.c < ll
    with np.errstate(invalid="ignore"):
        pos = np.where(rng > 0, (b5.c - b5.l) / rng, 0.5)
    df["close_pos"] = pos
    df["displacement"] = (rng > DISPLACE_ATR * atr) & ((pos > 0.7) | (pos < 0.3))
    # directional efficiency: net move over path length, 36 bars [DEF]
    net = np.abs(b5.c - pd.Series(b5.c).shift(36).values)
    path = pd.Series(np.abs(r1) * np.maximum(b5.c, 1e-9)).rolling(36).sum().values
    with np.errstate(divide="ignore", invalid="ignore"):
        df["dir_eff_36"] = np.where(path > 0, net / path, np.nan)
    # variance ratio: 12-bar variance against 12x the 1-bar variance
    v1 = pd.Series(r1).rolling(144).var().values
    r12 = pd.Series(logc).diff(12).values
    v12 = pd.Series(r12).rolling(144).var().values
    with np.errstate(divide="ignore", invalid="ignore"):
        df["vr_12"] = np.where(v1 > 0, v12 / (12.0 * v1), np.nan)
    df["ac_1"] = pd.Series(r1).rolling(288).apply(
        lambda s: pd.Series(s).autocorr(1), raw=False).values

    # ---------------- 4 context
    if cal is not None and len(cal):
        ev = cal["epoch"].to_numpy()
        bt = b5.t.astype(np.int64)
        nxt = np.searchsorted(ev, bt, side="left")
        prv = nxt - 1
        to_next = np.where(nxt < len(ev), (ev[np.minimum(nxt, len(ev) - 1)] - bt) / 60.0, np.inf)
        since_prev = np.where(prv >= 0, (bt - ev[np.maximum(prv, 0)]) / 60.0, np.inf)
        df["min_to_next_news"] = to_next
        df["min_since_news"] = since_prev
        df["at_news"] = (to_next <= NEWS_NEAR_MIN) | (since_prev <= NEWS_NEAR_MIN)
    else:
        df["min_to_next_news"] = np.inf
        df["min_since_news"] = np.inf
        df["at_news"] = False

    if dxy is not None:
        dx = pd.Series(dxy.c, index=pd.to_datetime(dxy.t, unit="s", utc=True))
        dx = dx[~dx.index.duplicated()].reindex(t, method="ffill")
        dr = np.log(np.maximum(dx.values, 1e-9))
        dr1 = np.concatenate(([0.0], np.diff(dr)))
        df["dxy_ret_1"] = dr1
        df["corr_dxy_288"] = (pd.Series(r1).rolling(288)
                              .corr(pd.Series(dr1)).values)
    else:
        df["corr_dxy_288"] = np.nan

    # ---------------- 5 regime, as a label and a score
    trend_like = ((df["dir_eff_36"] > df["dir_eff_36"].median()) &
                  (df["vr_12"] > 1.0))
    df["regime"] = np.select(
        [df["atr_pct"] >= 90, trend_like & (df["atr_pct"] >= 40),
         (~trend_like) & (df["atr_pct"] < 40)],
        ["EXTREME_VOL", "TREND", "QUIET_RANGE"], default="MIXED")
    z = lambda s: (s - s.rolling(PCT_WINDOW).mean()) / s.rolling(PCT_WINDOW).std()
    df["mrs"] = (z(df["dir_eff_36"]).fillna(0) + z(df["vr_12"]).fillna(0)
                 - z(df["vol_of_vol"]).fillna(0)) / 3.0

    return df


# ------------------------------------------------ 6 execution reliability
def execution_reliability(b5: D.Bars, b1: D.Bars, df: pd.DataFrame,
                          sample: int = 20000, seed: int = 20260921) -> dict:
    """How often a five-minute bar hides the answer.

    For a hypothetical long with a STOP_ATR stop and a 2R target placed at each
    sampled bar, an M5 bar that contains BOTH levels is ambiguous: the coarse
    series cannot say which came first. The M1 series can. The ambiguity rate
    and the disagreement rate are properties of the DATA, not of a strategy -
    no profit is computed here, only which bar resolved first.
    """
    rng = np.random.default_rng(seed)
    t1 = b1.t
    lo_i = int(np.searchsorted(b5.t, t1[0]))
    hi_i = int(np.searchsorted(b5.t, t1[-1])) - 80
    if hi_i <= lo_i + 10:
        return dict(n=0, note="no M1 overlap")
    idx = rng.choice(np.arange(lo_i, hi_i), size=min(sample, hi_i - lo_i),
                     replace=False)
    atr = df["atr"].to_numpy()
    amb = dis = res5 = 0
    n = 0
    for i in idx:
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = b5.c[i]
        stop = entry - STOP_ATR * a
        target = entry + 2.0 * STOP_ATR * a
        k5 = np.arange(i + 1, min(i + 1 + 72, len(b5)))
        if len(k5) == 0:
            continue
        hit_s5 = np.flatnonzero(b5.l[k5] <= stop)
        hit_t5 = np.flatnonzero(b5.h[k5] >= target)
        if len(hit_s5) == 0 and len(hit_t5) == 0:
            continue
        n += 1
        first5 = ("stop" if (len(hit_s5) and (not len(hit_t5) or hit_s5[0] <= hit_t5[0]))
                  else "target")
        # was the deciding M5 bar ambiguous?
        j = k5[hit_s5[0] if first5 == "stop" else hit_t5[0]]
        if b5.l[j] <= stop and b5.h[j] >= target:
            amb += 1
        # resolve the same window on M1
        m0 = int(np.searchsorted(t1, b5.t[i] + 300))
        m1_end = int(np.searchsorted(t1, b5.t[i] + 300 + 72 * 300))
        if m1_end <= m0:
            continue
        s1 = np.flatnonzero(b1.l[m0:m1_end] <= stop)
        t1h = np.flatnonzero(b1.h[m0:m1_end] >= target)
        if len(s1) == 0 and len(t1h) == 0:
            continue
        first1 = ("stop" if (len(s1) and (not len(t1h) or s1[0] <= t1h[0]))
                  else "target")
        res5 += 1
        dis += int(first1 != first5)
    return dict(n=n, resolved_both=res5,
                ambiguity_rate=(amb / n if n else np.nan),
                disagreement_rate=(dis / res5 if res5 else np.nan))


# ------------------------------------------------------- 7 what price does
def behaviour(df: pd.DataFrame, b5: D.Bars) -> pd.DataFrame:
    """The dependent variable: excursion after each bar, in R units.

    MFE and MAE are properties of the PATH, not of a rule - no entry logic, no
    exit logic, no side chosen. `net_up` and `net_dn` are what a perfectly
    timed exit in each direction could have reached, minus the measured cost,
    so a state where nothing is reachable after cost shows as negative for
    both sides rather than as a bad strategy.
    """
    atr = df["atr"].to_numpy()
    risk = STOP_ATR * atr
    cost = COST_SPREAD + 2 * COST_SLIPPAGE
    out = {}
    for k in HORIZONS:
        fmax = _fwd_max(b5.h, k)
        fmin = _fwd_min(b5.l, k)
        with np.errstate(divide="ignore", invalid="ignore"):
            up = (fmax - b5.c) / risk
            dn = (b5.c - fmin) / risk
            out[f"mfe_up_{k}"] = up
            out[f"mfe_dn_{k}"] = dn
            out[f"net_up_{k}"] = up - cost / risk
            out[f"net_dn_{k}"] = dn - cost / risk
            fwd = (pd.Series(b5.c).shift(-k).values - b5.c) / risk
            out[f"fwd_{k}"] = fwd
    return pd.DataFrame(out, index=df.index)


# --------------------------------------------------------- 8 quality + report
def bucket_report(df: pd.DataFrame, bh: pd.DataFrame, by: str,
                  k: int = 72, min_n: int = 200) -> pd.DataFrame:
    """One row per state. Sample size and CI width are reported beside every
    estimate; a bucket below `min_n` is kept and flagged, never dropped
    silently."""
    j = pd.concat([df[[by, "friction_R", "atr"]], bh], axis=1).dropna(
        subset=[by, f"fwd_{k}", f"mfe_up_{k}", f"mfe_dn_{k}"])
    rows = []
    for name, g in j.groupby(by, observed=True):
        n = len(g)
        fwd = g[f"fwd_{k}"]
        up, dn = g[f"mfe_up_{k}"], g[f"mfe_dn_{k}"]
        se = fwd.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
        rows.append(dict(
            state=name, n=n,
            friction_R=g["friction_R"].median(),
            mfe_up=up.mean(), mfe_dn=dn.mean(),
            best_side_net=max(up.mean(), dn.mean()) - g["friction_R"].median(),
            drift=fwd.mean(), drift_se=se,
            drift_ci=2.8 * se if np.isfinite(se) else np.nan,
            abs_move=fwd.abs().mean(),
            enough=("yes" if n >= min_n else "NO - too few"),
        ))
    r = pd.DataFrame(rows).sort_values("n", ascending=False)
    return r


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b1 = D.load_csv("data/XAUUSD_M1.csv")
    try:
        dxy = D.load_csv("data/DXY_M5.csv")
    except Exception:
        dxy = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        cal = cal[(cal.currency == "USD") & (cal.importance == "HIGH")]
    except Exception as e:
        print("calendar unavailable:", e)
        cal = None

    print("=" * 96)
    print("MEASUREMENT ENGINE - descriptive, built from the chart")
    print("=" * 96)
    print(f"M5 {len(b5):,} bars | M1 {len(b1):,} | "
          f"DXY {'yes' if dxy is not None else 'no'} | "
          f"calendar {0 if cal is None else len(cal)} USD HIGH")
    rh = rollover_hour(b5)
    print(f"rollover/maintenance hour measured from the data: {rh:02d}:00 UTC "
          f"(constant used: {ROLLOVER_HOUR_UTC:02d}:00)")

    df = build_states(b5, cal, dxy)
    bh = behaviour(df, b5)
    print(f"\ncost model: spread ${COST_SPREAD:.3f} measured + "
          f"2 x ${COST_SLIPPAGE:.2f} slippage ASSUMED -> "
          f"median friction {df['friction_R'].median():.4f} R per round turn")
    print(f"swap if a long is carried over the break: "
          f"{df['swap_R_if_held_long'].median():.4f} R")

    for by in ("session", "regime"):
        print(f"\n--- what price does next 6h, by {by} ---")
        r = bucket_report(df, bh, by, k=72)
        print(r.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

    if cal is not None:
        df["news_state"] = np.where(df["at_news"], "AT_NEWS", "AWAY")
        print("\n--- by news proximity (+/- 30 min of a USD HIGH release) ---")
        print(bucket_report(df, bh, "news_state", k=72)
              .to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

    df["vol_bucket"] = pd.cut(df["atr_pct"], [0, 20, 40, 60, 80, 100],
                              labels=["p0-20", "p20-40", "p40-60", "p60-80", "p80-100"])
    print("\n--- by volatility percentile ---")
    print(bucket_report(df, bh, "vol_bucket", k=72)
          .to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

    print("\n--- execution reliability (M5 vs M1 on the overlap) ---")
    er = execution_reliability(b5, b1, df)
    for k, v in er.items():
        print(f"    {k:20s} {v}")

    print("\n--- feed health ---")
    print(f"    M5 duplicate timestamps : {int(pd.Series(b5.t).duplicated().sum())}")
    print(f"    M5 gaps > 20 min        : {int(df['after_gap'].sum())}")
    print(f"    bars with atr <= 0      : {int((df['atr'] <= 0).sum())}")
    print(f"    coverage of atr_pct     : {df['atr_pct'].notna().mean():.3f}")
    print(f"    coverage of vr_12       : {df['vr_12'].notna().mean():.3f}")
    print(f"    coverage of corr_dxy    : {df['corr_dxy_288'].notna().mean():.3f}")

    out = Path("research/pilot/results"); out.mkdir(parents=True, exist_ok=True)
    keep = ["t", "session", "regime", "atr", "atr_pct", "vol_pct", "friction_R",
            "dir_eff_36", "vr_12", "mrs", "at_news", "min_since_news",
            "corr_dxy_288", "swept_high", "swept_low", "displacement"]
    pd.concat([df[keep], bh], axis=1).to_parquet(out / "states.parquet") \
        if _has_parquet() else pd.concat([df[keep], bh], axis=1).to_csv(
            out / "states.csv", index=False)
    print(f"\nstate table written to {out}")
    print("No PnL, Sharpe or win rate appears in any measurement above.")
    return 0


def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
