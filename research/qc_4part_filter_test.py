# ============================================================================
# DOBBY  -  4-PART FILTER TEST   (QuantConnect *Research*, Python project)
#
# A 2x2 factorial over two filter families, measured only on trades that could
# actually have been taken.
#
#     PART 1   no volume profile, no CHoCH+OB      <- baseline
#     PART 2   volume profile,    no CHoCH+OB
#     PART 3   no volume profile, CHoCH+OB
#     PART 4   volume profile,    CHoCH+OB
#
# WHY A 2x2 AND NOT FOUR SEPARATE RUNS
#   Running "baseline" and "everything on" tells you the pair works, not which
#   half did the work, or whether one is cancelling the other. The factorial
#   separates the volume effect, the structure effect, and the interaction.
#
# ONE THING THAT IS EASY TO GET WRONG AND MATTERS A LOT
#   The non-overlapping selection is RECOMPUTED INSIDE EACH PART. A filter that
#   rejects a signal frees the account to take the next one, which a filter
#   applied after sequencing would never see. Sequencing the unfiltered census
#   once and filtering the survivors would understate every filter here.
#
# THE FILTERS
#   VOLUME PROFILE (VP_MODE="breakout", the trend-following reading)
#     Long  taken only above the value area high, short only below the value
#     area low: price has left value in the signal's direction. Set
#     VP_MODE="reversion" for the opposite reading, which is a separate
#     hypothesis and should be counted as another test if you look at it.
#
#   CHoCH + ORDER BLOCK
#     CHoCH follows the EA's Structure.mqh: a CLOSE beyond the last confirmed
#     opposing swing by at least MIN_BREAK_ATR x ATR, and only when it flips
#     the prevailing structure. A same-direction break is a BOS and does not
#     re-arm anything.
#     The ORDER BLOCK is the last opposite-close candle before that impulse.
#     NOTE: no order block exists anywhere in the EA - this is a new
#     definition written here, not a port, so it has never been validated.
#     The signal must arrive with price back inside the block, within
#     OB_TOL x ATR of its edge.
#
# COST AND SIZING ARE UNCHANGED
#   Spread 0.7525 charged per leg round trip, R is scale-free (every leg risks
#   exactly 1R), exits resolve on minute bars, stop wins a tie with a target.
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
# STRUCTURE:  CHoCH  and the ORDER BLOCK it leaves behind
# ---------------------------------------------------------------------------
MIN_BREAK_ATR = 0.10     # a close must clear the swing by this much to count
OB_LOOKBACK   = 30       # bars searched back for the last opposite candle
OB_TOL        = 0.50     # entry may sit this far outside the block, in ATR
CHOCH_MAX_AGE = 60       # a CHoCH older than this no longer arms the setup

o5 = m5["open"].to_numpy(np.float64)

choch_dir = np.zeros(N5, np.int8)
choch_bar = np.full(N5, -1, np.int64)
ob_lo     = np.full(N5, np.nan)
ob_hi     = np.full(N5, np.nan)

_state = 0
_cd, _cb, _olo, _ohi = 0, -1, np.nan, np.nan
for i in range(N5):
    a = atr5[i]
    if np.isfinite(a) and a > 0:
        brk = MIN_BREAK_ATR * a
        sh, sl = piv_hi[i], piv_lo[i]
        ev = 0
        if np.isfinite(sh) and c5[i] > sh + brk:
            ev = 1
        elif np.isfinite(sl) and c5[i] < sl - brk:
            ev = -1
        # Only a break that FLIPS the prevailing structure is a CHoCH. A break
        # the same way as the current state is a BOS: continuation, not change.
        if ev != 0 and ev != _state:
            _state, _cd, _cb = ev, ev, i
            _olo = _ohi = np.nan
            for k in range(i, max(-1, i - OB_LOOKBACK), -1):
                if (ev > 0 and c5[k] < o5[k]) or (ev < 0 and c5[k] > o5[k]):
                    _olo, _ohi = l5[k], h5[k]
                    break
    choch_dir[i], choch_bar[i] = _cd, _cb
    ob_lo[i], ob_hi[i] = _olo, _ohi

def structure_ok(i, d, a):
    """Signal direction agrees with a recent CHoCH, and price is back at the
    order block that CHoCH left behind."""
    if choch_dir[i] != d or choch_bar[i] < 0:
        return False
    if i - choch_bar[i] > CHOCH_MAX_AGE:
        return False
    lo, hi = ob_lo[i], ob_hi[i]
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return False
    px = c5[i]
    if lo - OB_TOL * a <= px <= hi + OB_TOL * a:
        return True
    return False

VP_MODE = "breakout"

def volume_ok(i, d, a, poc, val, vah):
    if not (np.isfinite(val) and np.isfinite(vah) and vah > val):
        return False
    px = c5[i]
    if VP_MODE == "breakout":
        return (px > vah) if d > 0 else (px < val)
    return val <= px <= vah

# ---------------------------------------------------------------------------
# ONE PASS: every cross, simulated, with both filter verdicts attached
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

    poc, val, vah = profile_at(i, weights=gc_vol)
    rows.append(dict(bar=i, time=idx5[i], dir=d, r=r, dur=dur,
                     vp_ok=bool(volume_ok(i, d, a, poc, val, vah)),
                     st_ok=bool(structure_ok(i, d, a))))

S = pd.DataFrame(rows)
print(f"\ncrosses simulated: {len(S):,}   volume weighting: {vol_source}")
print(f"  pass volume filter ({VP_MODE}): {int(S.vp_ok.sum()):,}"
      f"   pass CHoCH+OB: {int(S.st_ok.sum()):,}"
      f"   pass both: {int((S.vp_ok & S.st_ok).sum()):,}")

# ---------------------------------------------------------------------------
# SEQUENCING  -  recomputed per part, which is the whole point
# ---------------------------------------------------------------------------
def sequence(df):
    """Walk forward taking only trades that do not overlap one already open.
    Must run AFTER the filter: rejecting a signal frees the account for the
    next one, and a filter applied after sequencing would never see that."""
    take, busy = [], -1
    for bar, dur in zip(df.bar.to_numpy(), df.dur.to_numpy()):
        if bar > busy:
            take.append(True)
            busy = bar + int(np.ceil(dur / 5.0))
        else:
            take.append(False)
    return df[np.array(take)]

def stat(r):
    r = np.asarray(r, float)
    n = len(r)
    if n < 2:
        return n, float("nan"), float("nan"), 0.0, float("nan")
    e, sd = r.mean(), r.std(ddof=1)
    t = e / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    return n, e, t, r.sum(), 100.0 * (r > 0).mean()

PARTS = [
    ("1  baseline, no filters",  lambda x: np.ones(len(x), bool)),
    ("2  + volume profile",      lambda x: x.vp_ok.to_numpy()),
    ("3  + CHoCH and OB",        lambda x: x.st_ok.to_numpy()),
    ("4  + both",                lambda x: (x.vp_ok & x.st_ok).to_numpy()),
]

res = {}
print("\n" + "=" * 92)
print("TRADEABLE TRADES ONLY - one position at a time, resequenced inside each part")
print("=" * 92)
print(f"{'part':<26}{'IS n':>6}{'IS E':>9}{'IS t':>7}{'IS R':>9}"
      f"{'OOS n':>7}{'OOS E':>9}{'OOS t':>7}{'OOS R':>9}{'win%':>7}")
for name, f in PARTS:
    seq = sequence(S[f(S)].reset_index(drop=True))
    i_, o_ = seq[seq.time < IS_END], seq[seq.time >= IS_END]
    ni, ei, ti, Ri, _  = stat(i_["r"])
    no, eo, to, Ro, wo = stat(o_["r"])
    res[name] = seq
    print(f"{name:<26}{ni:>6}{ei:>+9.4f}{ti:>+7.2f}{Ri:>+9.1f}"
          f"{no:>7}{eo:>+9.4f}{to:>+7.2f}{Ro:>+9.1f}{wo:>7.1f}")

# ---------------------------------------------------------------------------
# ATTRIBUTION  -  what each half actually contributed
# ---------------------------------------------------------------------------
def E(name, oos):
    d = res[name]
    d = d[d.time >= IS_END] if oos else d[d.time < IS_END]
    return d.r.mean() if len(d) > 1 else float("nan")

print("\n" + "-" * 92)
print("ATTRIBUTION (change in expectancy, R per trade)")
print(f"{'effect':<40}{'in-sample':>14}{'out-of-sample':>16}")
n1, n2, n3, n4 = [p[0] for p in PARTS]
for lab, a_, b_ in (
        ("volume profile alone  (2 - 1)", n2, n1),
        ("CHoCH+OB alone        (3 - 1)", n3, n1),
        ("both                  (4 - 1)", n4, n1),
        ("interaction   (4-3) - (2-1)", None, None)):
    if a_ is None:
        vi = (E(n4, False) - E(n3, False)) - (E(n2, False) - E(n1, False))
        vo = (E(n4, True)  - E(n3, True))  - (E(n2, True)  - E(n1, True))
    else:
        vi, vo = E(a_, False) - E(b_, False), E(a_, True) - E(b_, True)
    print(f"{lab:<40}{vi:>+14.4f}{vo:>+16.4f}")

K = len(PARTS) * 2
BAR = NormalDist().inv_cdf(1 - 0.025 / K)
print("\n" + "=" * 92)
print(f"{K} hypotheses here (4 parts x 2 samples). Bonferroni 5%: t > {BAR:.2f}")
print("A part counts only if E > 0 with t over that bar, on the SAME part, in")
print("BOTH columns. A filter that merely makes a losing system lose more")
print("slowly has not found an edge - it has found fewer trades.")
print("Watch the trade count too: a part with very few trades will show a wide")
print("expectancy for reasons that have nothing to do with skill.")
print("=" * 92)
for name in res:
    res[name].to_csv(f"part_{name[0]}_trades.csv", index=False)
print("saved part_1..4_trades.csv")
