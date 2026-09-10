# ============================================================================
# DOBBY  -  SIGNAL CENSUS   (QuantConnect *Research* notebook, Python project)
#
# WHAT CHANGED AND WHY
#   The previous cell applied the [0.30, 3.00] x ATR risk band BEFORE measuring
#   anything, and threw away 1,033 of 2,184 signals. We therefore never learned
#   what those signals would have done, and could not tell whether the band was
#   removing losers or removing winners.
#
#   This cell filters NOTHING. Every EMA cross is simulated and recorded with
#   the features attached, so a filter can be judged on measured evidence
#   afterwards instead of being assumed in advance.
#
# THE FEATURES RECORDED PER SIGNAL
#   risk_atr    stop distance / ATR      <- what the old band was cutting
#   trend_ok    on the right side of the 15m EMA  (a feature, not a gate)
#   zone        (close - SMA200) / ATR   <- the one finding that survived
#   poc_dist    (close - POC) / ATR
#   va_pos      position across the value area, 0 = VAL, 1 = VAH
#   liq_up      distance to nearest UNTESTED swing high / ATR
#   liq_dn      distance to nearest UNTESTED swing low  / ATR
#   swept       a level was wicked through and reclaimed, within N bars
#   atr_pct     ATR percentile - volatility regime
#   hour        UTC hour - session
#   spread_r    SPREAD / stop distance   <- cost in R, per leg
#
# ---------------------------------------------------------------------------
# VOLUME: READ THIS BEFORE TRUSTING THE PROFILE COLUMNS
#
#   XAU/USD spot is OTC. There is no consolidated volume, and QuantConnect's
#   OANDA CFD feed carries none - the EA's own VolumeProfile.mqh says the same
#   thing about MT5, where the default source is one broker's tick count.
#
#   So the profile here is a TIME profile (TPO / Market Profile), built from
#   how long price spent in each bin, not how much traded there. That is a real
#   and standard construction, and it is honest about what the data supports.
#
#   USE_GC_VOLUME=True additionally weights the profile by REAL traded volume
#   from a correlated instrument (COMEX gold futures, else the GLD ETF). No
#   basis adjustment is needed or done: the bins are built from XAUUSD's own
#   highs and lows, and the other instrument contributes only a per-bar volume
#   WEIGHT. Its price scale is therefore irrelevant, only its time alignment
#   matters. If neither source loads, the cell says so and uses time alone.
# ---------------------------------------------------------------------------
#
# DATA DREDGING - THE THING THAT WILL RUIN THIS IF UNMANAGED
#   Slicing 11 features into buckets is dozens of new tests, and dozens of
#   tests on a signal with no edge WILL produce something that looks great.
#   Three guards, all printed:
#     1. Every bucket is shown in-sample AND out-of-sample. A bucket that only
#        works in one is noise.
#     2. The Bonferroni bar is recomputed for the real number of tests run.
#     3. MONOTONICITY is flagged. A real effect gradients across buckets. A
#        single spiky bucket beside flat neighbours is almost always luck.
# ============================================================================

import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from statistics import NormalDist

START   = datetime(2025, 1,  1)
IS_END  = datetime(2026, 1,  1)
END     = datetime(2026, 9, 10)
SPREAD  = 0.7525          # OANDA measured 2023-2026 gold mean

USE_GC_VOLUME = True      # also build a real-volume profile from COMEX futures
VP_LOOKBACK   = 288       # 5-min bars in the profile window (288 = 24h)
VP_BINS       = 48
VALUE_AREA    = 0.70
LIQ_LOOKBACK  = 200       # bars scanned for untested swing levels
SWEEP_BARS    = 12        # a sweep counts if it happened this recently
SWEEP_MIN_ATR = 0.05      # wick must clear the level by at least this
SWEEP_MAX_ATR = 1.00      # but not by more than this, or it is a breakout
SWEEP_RECLAIM = 3         # bars allowed for the close to come back

qb  = QuantBook()
SYM = qb.add_cfd("XAUUSD", Resolution.MINUTE, Market.OANDA).symbol

# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------
def load_minute(sym, start, end, res=Resolution.MINUTE):
    frames, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=90), end)
        h = qb.history(sym, cur, nxt, res)
        if h is not None and len(h):
            if isinstance(h.index, pd.MultiIndex):
                h = h.droplevel(0)
            cols = {}
            for f in ("open", "high", "low", "close"):
                if f in h.columns:
                    cols[f] = h[f].astype("float32")
                elif f"bid{f}" in h.columns and f"ask{f}" in h.columns:
                    cols[f] = ((h[f"bid{f}"] + h[f"ask{f}"]) / 2.0).astype("float32")
            if "volume" in h.columns:
                cols["volume"] = h["volume"].astype("float32")
            if len({"open", "high", "low", "close"} & set(cols)) == 4:
                frames.append(pd.DataFrame(cols, index=h.index))
        del h
        cur = nxt
    if not frames:
        raise RuntimeError("no history returned")
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated(keep="first")]

minute = load_minute(SYM, START, END)
print(f"minute bars {len(minute):,}   {minute.index[0]} -> {minute.index[-1]}")

has_vol = "volume" in minute.columns and float(minute["volume"].abs().sum()) > 0
print(f"XAUUSD CFD volume usable: {has_vol}"
      f"{'' if has_vol else '   -> time (TPO) profile will be used'}")

OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}
m5  = minute.resample("5min").agg(OHLC).dropna()
m15 = minute.resample("15min").agg(OHLC).dropna()
print(f"5-minute bars {len(m5):,}   15-minute bars {len(m15):,}")

mi   = minute.index.values
mlow = minute["low"].to_numpy(np.float64)
mhig = minute["high"].to_numpy(np.float64)
mclo = minute["close"].to_numpy(np.float64)
N_MIN = len(mi)

J0 = np.searchsorted(mi, (m5.index + pd.Timedelta("5min")).values, side="left")
c5 = m5["close"].to_numpy(np.float64)
h5 = m5["high"].to_numpy(np.float64)
l5 = m5["low"].to_numpy(np.float64)
idx5 = m5.index
N5 = len(m5)

# ---------------------------------------------------------------------------
# OPTIONAL: real volume from COMEX gold futures, basis-adjusted onto spot
# ---------------------------------------------------------------------------
gc5 = None
vol_source = "time (TPO) only"
if USE_GC_VOLUME:
    tried = []
    cand = None
    # COMEX gold futures first: real, 23h, the same underlying.
    try:
        cand = ("COMEX GC futures", qb.add_future(Futures.Metals.GOLD,
                                                  Resolution.MINUTE).symbol)
    except Exception as e:
        tried.append(f"GC futures {type(e).__name__}")
    # GLD is the fallback: real exchange volume, but US cash hours only, so it
    # weights the US session and leaves Asia and early London at zero.
    if cand is None:
        try:
            cand = ("GLD ETF (US hours only)",
                    qb.add_equity("GLD", Resolution.MINUTE).symbol)
        except Exception as e:
            tried.append(f"GLD {type(e).__name__}")
    if cand is None:
        print(f"no real-volume source loaded ({'; '.join(tried)}) - time profile only")
    else:
        name, vsym = cand
        try:
            vmin = load_minute(vsym, START, END)
            if "volume" in vmin.columns and float(vmin["volume"].abs().sum()) > 0:
                agg = dict(OHLC); agg["volume"] = "sum"
                gc5 = vmin.resample("5min").agg(agg).reindex(idx5)
                gc5["volume"] = gc5["volume"].fillna(0.0)
                vol_source = name
                covered = float((gc5["volume"] > 0).mean()) * 100
                print(f"real volume from {name}: total {gc5['volume'].sum():,.0f}"
                      f"   covers {covered:.0f}% of 5-minute bars")
            else:
                print(f"{name} returned no usable volume - time profile only")
            del vmin
        except Exception as e:
            print(f"{name} history failed ({type(e).__name__}) - time profile only")

# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------
def wilder_atr(df, n):
    h, l, c = (df["high"].astype("float64"), df["low"].astype("float64"),
               df["close"].astype("float64"))
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()

def pivot_available(series, left, right, is_low):
    """Most recent CONFIRMED pivot as known at each bar: a pivot with `right`
    bars to its right is only knowable `right` bars later."""
    s = series.astype("float64").reset_index(drop=True)
    if is_low:
        ok = (s < s.rolling(left).min().shift(1)) & (s < s.rolling(right).min().shift(-right))
    else:
        ok = (s > s.rolling(left).max().shift(1)) & (s > s.rolling(right).max().shift(-right))
    raw = pd.Series(np.where(ok.fillna(False), s, np.nan))
    return raw.shift(right).to_numpy(), raw.shift(right).ffill().to_numpy()

fast = pd.Series(c5).ewm(span=9,  adjust=False).mean().to_numpy()
slow = pd.Series(c5).ewm(span=21, adjust=False).mean().to_numpy()
atr5 = wilder_atr(m5, 14).to_numpy()

piv_lo_pt, piv_lo = pivot_available(m5["low"],  5, 5, True)
piv_hi_pt, piv_hi = pivot_available(m5["high"], 5, 5, False)
fb_lo = m5["low"].rolling(10).min().to_numpy()
fb_hi = m5["high"].rolling(10).max().to_numpy()

# 15-minute trend EMA, available only after its bar closed
_t = m15["close"].astype("float64").ewm(span=50, adjust=False).mean().shift(1)
_t.index = _t.index + pd.Timedelta("15min")
trend15 = _t.reindex(idx5, method="ffill").to_numpy()

# Trend zone on the EA's own M15 basis: (close - SMA200) / ATR
_s = m15["close"].astype("float64").rolling(200).mean().shift(1)
_a = wilder_atr(m15, 14).shift(1)
_s.index = _s.index + pd.Timedelta("15min")
_a.index = _a.index + pd.Timedelta("15min")
sma200_15 = _s.reindex(idx5, method="ffill").to_numpy()
atr15     = _a.reindex(idx5, method="ffill").to_numpy()

atr_pct = pd.Series(atr5).rolling(2000, min_periods=200).rank(pct=True).to_numpy()
hour5   = idx5.hour.to_numpy()

# ---------------------------------------------------------------------------
# PROFILE  (time, and optionally real volume) over a trailing window
# ---------------------------------------------------------------------------
def profile_at(i, weights=None):
    """POC / VAL / VAH from the trailing VP_LOOKBACK bars ending at bar i-1.
    Each bar spreads its weight evenly over the bins its range covers, which
    is the same construction the EA's VolumeProfile.mqh uses."""
    a = max(0, i - VP_LOOKBACK)
    if i - a < 20:
        return np.nan, np.nan, np.nan
    lo, hi = l5[a:i].min(), h5[a:i].max()
    if not (hi > lo):
        return np.nan, np.nan, np.nan
    binsz = (hi - lo) / VP_BINS
    ilo = np.floor((l5[a:i] - lo) / binsz).astype(np.int64).clip(0, VP_BINS - 1)
    ihi = np.floor((h5[a:i] - lo) / binsz).astype(np.int64).clip(0, VP_BINS - 1)
    span = (ihi - ilo + 1).astype(np.float64)
    w = np.ones(i - a) if weights is None else weights[a:i].astype(np.float64)
    w = np.divide(w, span, out=np.zeros_like(w), where=span > 0)
    diff = np.zeros(VP_BINS + 1)
    np.add.at(diff, ilo, w)
    np.add.at(diff, ihi + 1, -w)
    prof = np.cumsum(diff)[:VP_BINS]
    tot = prof.sum()
    if tot <= 0:
        return np.nan, np.nan, np.nan
    poc = int(prof.argmax())
    lo_i = hi_i = poc
    acc = prof[poc]
    while acc < VALUE_AREA * tot and (lo_i > 0 or hi_i < VP_BINS - 1):
        dn = prof[lo_i - 1] if lo_i > 0 else -1.0
        up = prof[hi_i + 1] if hi_i < VP_BINS - 1 else -1.0
        if up >= dn:
            hi_i += 1; acc += up
        else:
            lo_i -= 1; acc += dn
    c = lambda b: lo + (b + 0.5) * binsz
    return c(poc), c(lo_i), c(hi_i)

gc_vol = gc5["volume"].to_numpy(np.float64) if gc5 is not None else None

# ---------------------------------------------------------------------------
# LIQUIDITY: nearest UNTESTED swing level, and recent sweeps
# ---------------------------------------------------------------------------
def liquidity_at(i, price):
    """Nearest swing high above / swing low below that price has NOT traded
    through since it formed. Those are the resting-order pools.

    Suffix max/min over the window make the 'untested' test O(1) per pivot
    instead of a fresh slice scan, which is the difference between this cell
    finishing in seconds and finishing in an hour."""
    a = max(0, i - LIQ_LOOKBACK)
    if i - a < 2:
        return np.nan, np.nan
    hh, ll = h5[a:i], l5[a:i]
    sufmax = np.maximum.accumulate(hh[::-1])[::-1]
    sufmin = np.minimum.accumulate(ll[::-1])[::-1]
    n = i - a
    up = dn = np.nan
    hs = piv_hi_pt[a:i]
    for p_ in np.where(np.isfinite(hs))[0][::-1]:
        lvl = hs[p_]
        if lvl > price and (p_ + 1 >= n or sufmax[p_ + 1] < lvl):
            up = lvl; break
    ls = piv_lo_pt[a:i]
    for p_ in np.where(np.isfinite(ls))[0][::-1]:
        lvl = ls[p_]
        if lvl < price and (p_ + 1 >= n or sufmin[p_ + 1] > lvl):
            dn = lvl; break
    return up, dn

# Sweeps, precomputed once over the whole series instead of per signal.
#
# This DIFFERS from the EA's Sweep.mqh, which sweeps named levels (PDH/PDL,
# Asian high/low). Here the level is the prior 20-bar extreme, which is
# vectorisable and captures the same event: an extreme is taken out and price
# closes back through it.
#
# The reclaim test reads bars AFTER the sweep bar, so a sweep is not confirmed
# until SWEEP_RECLAIM bars later. The lookup window below is shifted by that
# much, or the feature would be reading the future.
_W = 20
prior_hi = pd.Series(h5).rolling(_W).max().shift(1).to_numpy()
prior_lo = pd.Series(l5).rolling(_W).min().shift(1).to_numpy()
with np.errstate(invalid="ignore"):
    pen_hi = h5 - prior_hi
    pen_lo = prior_lo - l5
    took_hi = (pen_hi >= SWEEP_MIN_ATR * atr5) & (pen_hi <= SWEEP_MAX_ATR * atr5)
    took_lo = (pen_lo >= SWEEP_MIN_ATR * atr5) & (pen_lo <= SWEEP_MAX_ATR * atr5)
recl_hi = np.zeros(N5, bool)
recl_lo = np.zeros(N5, bool)
for _s in range(SWEEP_RECLAIM + 1):
    cs = np.concatenate([c5[_s:], np.full(_s, np.nan)])
    with np.errstate(invalid="ignore"):
        recl_hi |= cs < prior_hi
        recl_lo |= cs > prior_lo
sweep_hi = np.nan_to_num(took_hi, nan=0).astype(bool) & recl_hi
sweep_lo = np.nan_to_num(took_lo, nan=0).astype(bool) & recl_lo

_lag = SWEEP_RECLAIM + 1
_any_hi = pd.Series(sweep_hi.astype(float)).rolling(SWEEP_BARS).max().shift(_lag).to_numpy()
_any_lo = pd.Series(sweep_lo.astype(float)).rolling(SWEEP_BARS).max().shift(_lag).to_numpy()

def swept_at(i):
    hi = _any_hi[i] == 1.0
    lo = _any_lo[i] == 1.0
    return 1 if (hi and not lo) else (-1 if (lo and not hi) else 0)

# ---------------------------------------------------------------------------
# THE CENSUS  -  every cross, nothing filtered
# ---------------------------------------------------------------------------
def simulate(i, d, entry, risk):
    stop0 = entry - d * risk
    be    = entry + d * SPREAD
    tgt   = [entry + d * risk * m for m in (1.0, 2.0, 3.0)]
    j0 = J0[i]
    if j0 >= N_MIN:
        return None
    j1 = min(j0 + 120 * 5, N_MIN)
    alive, tp1, r, k = [True] * 3, False, 0.0, j0
    while k < j1:
        cur = be if tp1 else stop0
        if (d > 0 and mlow[k] <= cur) or (d < 0 and mhig[k] >= cur):
            for x in range(3):
                if alive[x]:
                    r += ((cur - entry) * d - SPREAD) / risk
                    alive[x] = False
            break
        for x in range(3):
            if alive[x] and ((d > 0 and mhig[k] >= tgt[x]) or (d < 0 and mlow[k] <= tgt[x])):
                r += ((tgt[x] - entry) * d - SPREAD) / risk
                alive[x] = False
                if x == 0:
                    tp1 = True
        if not any(alive):
            break
        k += 1
    kx = min(k, j1 - 1, N_MIN - 1)
    if any(alive):
        px = mclo[kx]
        for x in range(3):
            if alive[x]:
                r += ((px - entry) * d - SPREAD) / risk
    return r, kx - j0 + 1

bull = np.concatenate([[False], (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])])
bear = np.concatenate([[False], (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])])

rows = []
busy_until = -1
warm = max(VP_LOOKBACK, LIQ_LOOKBACK, 250) + 10
for i in range(warm, N5):
    d = 1 if bull[i] else (-1 if bear[i] else 0)
    if d == 0:
        continue
    a = atr5[i]
    if not np.isfinite(a) or a <= 0:
        continue
    entry = c5[i]
    raw = piv_lo[i] if d > 0 else piv_hi[i]
    if not np.isfinite(raw):
        raw = fb_lo[i] if d > 0 else fb_hi[i]
    if not np.isfinite(raw):
        continue
    risk = abs(entry - raw)
    if risk <= 0:
        continue

    sim = simulate(i, d, entry, risk)
    if sim is None:
        break
    r, dur = sim

    poc, val, vah = profile_at(i)
    vpoc = vval = vvah = np.nan
    if gc_vol is not None:
        vpoc, vval, vvah = profile_at(i, weights=gc_vol)
    up, dn = liquidity_at(i, entry)

    rows.append(dict(
        time=idx5[i], dir=d, r=r, dur=dur,
        risk_atr=risk / a,
        trend_ok=int((d > 0 and entry > trend15[i]) or (d < 0 and entry < trend15[i]))
                 if np.isfinite(trend15[i]) else -1,
        zone=(entry - sma200_15[i]) / atr15[i]
             if np.isfinite(sma200_15[i]) and np.isfinite(atr15[i]) and atr15[i] > 0 else np.nan,
        poc_dist=(entry - poc) / a if np.isfinite(poc) else np.nan,
        va_pos=(entry - val) / (vah - val) if np.isfinite(val) and vah > val else np.nan,
        vpoc_dist=(entry - vpoc) / a if np.isfinite(vpoc) else np.nan,
        liq_up=(up - entry) / a if np.isfinite(up) else np.nan,
        liq_dn=(entry - dn) / a if np.isfinite(dn) else np.nan,
        swept=swept_at(i),
        atr_pct=atr_pct[i],
        hour=int(hour5[i]),
        spread_r=SPREAD / risk,
        sequential=int(i > busy_until),
    ))
    if i > busy_until:
        busy_until = i + int(np.ceil(dur / 5.0))

S = pd.DataFrame(rows)
print(f"\nCENSUS COMPLETE: {len(S):,} signals recorded, NONE filtered out")
print(f"  of which the old risk band [0.30,3.00] would have kept "
      f"{int(((S.risk_atr>=0.30)&(S.risk_atr<=3.00)).sum()):,}")
print(f"  of which a one-position-at-a-time rule would have taken "
      f"{int(S.sequential.sum()):,}")

# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------
TESTS = [0]

def stat(r):
    r = np.asarray(r, float)
    n = len(r)
    if n < 2:
        return n, float("nan"), float("nan")
    e, sd = r.mean(), r.std(ddof=1)
    return n, e, (e / (sd / math.sqrt(n)) if sd > 0 else float("nan"))

def buckets(df, col, edges=None, q=5, label=None):
    sub = df[np.isfinite(df[col])] if df[col].dtype.kind == "f" else df
    if len(sub) < 50:
        print(f"{col}: too few signals"); return
    if edges is None:
        try:
            cats, bins = pd.qcut(sub[col], q, retbins=True, duplicates="drop", labels=False)
        except ValueError:
            print(f"{col}: not enough distinct values"); return
    else:
        bins = np.array(edges, float)
        cats = pd.cut(sub[col], bins, labels=False, include_lowest=True)
    print(f"\n--- {label or col} " + "-" * (58 - len(label or col)))
    print(f"{'bucket':<22}{'IS n':>6}{'IS E':>9}{'IS t':>7}{'OOS n':>7}{'OOS E':>9}{'OOS t':>7}")
    es = []
    for b in sorted(pd.unique(cats.dropna())):
        m = sub[cats == b]
        i_, o_ = m[m.time < IS_END], m[m.time >= IS_END]
        ni, ei, ti = stat(i_["r"]); no, eo, to = stat(o_["r"])
        lo, hi = bins[int(b)], bins[int(b) + 1]
        print(f"{f'[{lo:.2f}, {hi:.2f})':<22}{ni:>6}{ei:>+9.4f}{ti:>+7.2f}"
              f"{no:>7}{eo:>+9.4f}{to:>+7.2f}")
        es.append(ei); TESTS[0] += 1
    if len(es) >= 3:
        d = np.diff(es)
        mono = (d > 0).all() or (d < 0).all()
        print(f"  monotonic across buckets in-sample: "
              f"{'YES' if mono else 'NO  <- a lone good bucket is usually luck'}")

n, e, t = stat(S["r"]); TESTS[0] += 1
print("\n" + "=" * 86)
print(f"ALL SIGNALS, NOTHING FILTERED: n={n:,}  E={e:+.4f}R  t={t:+.2f}")
i_, o_ = S[S.time < IS_END], S[S.time >= IS_END]
print(f"  in-sample  n={len(i_):,}  E={i_.r.mean():+.4f}  total {i_.r.sum():+.1f}R")
print(f"  out-sample n={len(o_):,}  E={o_.r.mean():+.4f}  total {o_.r.sum():+.1f}R")
print("=" * 86)

# 5,326 includes signals that fired while an earlier one was still open. Only
# the sequential subset could actually have been traded, so it gets its own row.
seq = S[S.sequential == 1]
si, so = seq[seq.time < IS_END], seq[seq.time >= IS_END]
ns, es, ts = stat(seq["r"])
print(f"TRADEABLE SUBSET (one position at a time): n={ns:,}  E={es:+.4f}R  t={ts:+.2f}")
print(f"  in-sample  n={len(si):,}  E={si.r.mean():+.4f}  total {si.r.sum():+.1f}R")
print(f"  out-sample n={len(so):,}  E={so.r.mean():+.4f}  total {so.r.sum():+.1f}R")
print("=" * 86)
TESTS[0] += 1

print("\n### THE RISK BAND AUTOPSY - what the old cell threw away")
kept = S[(S.risk_atr >= 0.30) & (S.risk_atr <= 3.00)]
cut  = S[(S.risk_atr < 0.30) | (S.risk_atr > 3.00)]
for lab, g in (("kept by band", kept), ("CUT by band", cut)):
    gi, go = g[g.time < IS_END], g[g.time >= IS_END]
    print(f"  {lab:<14} n={len(g):>5}  IS E={gi.r.mean():+.4f}  OOS E={go.r.mean():+.4f}")
TESTS[0] += 2

buckets(S, "risk_atr", q=6, label="risk_atr  (stop distance / ATR)")
buckets(S, "spread_r", q=5, label="spread_r  (cost in R per leg)")
buckets(S, "zone",     q=6, label="zone  (close - SMA200)/ATR on M15")
buckets(S, "poc_dist", q=6, label="poc_dist  TIME profile")
buckets(S, "va_pos",   edges=[-9, 0, 0.25, 0.5, 0.75, 1.0, 9], label="va_pos  value area position")
if gc_vol is not None:
    buckets(S, "vpoc_dist", q=6, label="vpoc_dist  REAL COMEX VOLUME profile")
buckets(S, "liq_up",   q=5, label="liq_up  distance to untested high / ATR")
buckets(S, "liq_dn",   q=5, label="liq_dn  distance to untested low / ATR")
buckets(S, "atr_pct",  q=5, label="atr_pct  volatility regime")
buckets(S, "swept",    edges=[-1.5, -0.5, 0.5, 1.5], label="swept  (-1 low, 0 none, +1 high)")
buckets(S, "trend_ok", edges=[-1.5, -0.5, 0.5, 1.5], label="trend_ok  (-1 n/a, 0 against, 1 with)")
buckets(S, "hour",     edges=[-0.5, 5.5, 11.5, 16.5, 23.5], label="hour  UTC session")

K = TESTS[0]
BAR = NormalDist().inv_cdf(1 - 0.025 / K)
print("\n" + "=" * 86)
print(f"{K} hypotheses were tested in this cell.")
print(f"Bonferroni family-wise 5%:  t > {BAR:.2f}   (a lone test would be 2.00)")
print("A bucket counts ONLY if it clears that in-sample, holds its sign and")
print("size out-of-sample, and sits on a monotonic gradient rather than alone.")
print("=" * 86)
S.to_csv("signal_census.csv", index=False)
print("saved signal_census.csv - reload it to slice further without re-running")
