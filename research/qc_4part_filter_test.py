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
# Recent-window analysis. Each is reported WHOLE - a window this short cannot
# carry an in-sample / out-of-sample split that means anything, so these
# describe a period rather than test a hypothesis. The 2025-onward IS/OOS table
# above them is still the test.
RECENT_MONTHS = 3         # the short period, measured back from END

# SIGNAL TIMEFRAME. Exits always resolve on 1-minute bars whatever this is.
# Raising it is the one lead the cost diagnostic keeps pointing at: a fixed
# spread against a wider ATR-based stop is a smaller share of R, so "15min",
# "30min" or "1h" is the experiment worth running if GROSS comes back positive
# while NET does not.
SIGNAL_TF   = "5min"
TF_MIN      = int(pd.Timedelta(SIGNAL_TF).total_seconds() // 60)
HOLD_BARS   = 120                        # signal bars a trade may stay open
VP_HOURS    = 24                         # profile window, in hours

VP_LOOKBACK   = max(20, int(VP_HOURS * 60 / TF_MIN))
VP_BINS       = 48
VALUE_AREA    = 0.70

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
tf = minute.resample(SIGNAL_TF).agg(OHLC).dropna()
print(f"{SIGNAL_TF} signal bars {len(tf):,}   profile window {VP_LOOKBACK} bars"
      f" ({VP_HOURS}h)   max hold {HOLD_BARS} bars ({HOLD_BARS * TF_MIN / 60:.0f}h)")

mi   = minute.index.values
mlow = minute["low"].to_numpy(np.float64)
mhig = minute["high"].to_numpy(np.float64)
mclo = minute["close"].to_numpy(np.float64)
N_MIN = len(mi)

# First minute of the NEXT signal bar. Exits may only be scanned from there;
# anything earlier is inside the bar that produced the signal.
J0 = np.searchsorted(mi, (tf.index + pd.Timedelta(SIGNAL_TF)).values, side="left")
tfc = tf["close"].to_numpy(np.float64)
tfh = tf["high"].to_numpy(np.float64)
tfl = tf["low"].to_numpy(np.float64)
tfidx = tf.index
N_TF = len(tf)

# ---------------------------------------------------------------------------
# OPTIONAL: real traded volume as a per-bar WEIGHT (no basis adjustment
# needed - the bins come from XAUUSD's own highs and lows)
# ---------------------------------------------------------------------------
gc5 = None
vol_source = "time (TPO) only"
if USE_GC_VOLUME:
    # Each candidate is tried END TO END - subscribe AND fetch - before moving
    # on. Subscribing to a future succeeds even when its history call does not,
    # so testing only the subscription silently skips the fallback.
    def _gc():
        return qb.add_future(Futures.Metals.GOLD, Resolution.MINUTE).symbol
    def _gld():
        return qb.add_equity("GLD", Resolution.MINUTE).symbol

    tried = []
    for name, make in (("COMEX GC futures", _gc),
                       ("GLD ETF (US hours only)", _gld)):
        try:
            vmin = load_minute(make(), START, END)
            if "volume" not in vmin.columns or float(vmin["volume"].abs().sum()) <= 0:
                tried.append(f"{name}: no volume column")
                del vmin
                continue
            agg = dict(OHLC); agg["volume"] = "sum"
            gc5 = vmin.resample("5min").agg(agg).reindex(tfidx)
            gc5["volume"] = gc5["volume"].fillna(0.0)
            vol_source = name
            covered = float((gc5["volume"] > 0).mean()) * 100
            print(f"real volume from {name}: total {gc5['volume'].sum():,.0f}"
                  f"   covers {covered:.0f}% of 5-minute bars")
            del vmin
            break
        except Exception as e:
            tried.append(f"{name}: {type(e).__name__}")
    if gc5 is None:
        print(f"no real-volume source ({'; '.join(tried)}) - time profile only")

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
    return raw.shift(right).ffill().to_numpy()

fast = pd.Series(tfc).ewm(span=9,  adjust=False).mean().to_numpy()
slow = pd.Series(tfc).ewm(span=21, adjust=False).mean().to_numpy()
tfatr = wilder_atr(tf, 14).to_numpy()

piv_lo = pivot_available(tf["low"],  5, 5, True)
piv_hi = pivot_available(tf["high"], 5, 5, False)
fb_lo = tf["low"].rolling(10).min().to_numpy()
fb_hi = tf["high"].rolling(10).max().to_numpy()

# This cell deliberately has NO higher-timeframe trend filter. Part 1 is the
# raw cross, so the factorial measures the two filters under test against a
# clean baseline rather than against another filter's leftovers.

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
    lo, hi = tfl[a:i].min(), tfh[a:i].max()
    if not (hi > lo):
        return np.nan, np.nan, np.nan
    binsz = (hi - lo) / VP_BINS
    ilo = np.floor((tfl[a:i] - lo) / binsz).astype(np.int64).clip(0, VP_BINS - 1)
    ihi = np.floor((tfh[a:i] - lo) / binsz).astype(np.int64).clip(0, VP_BINS - 1)
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
# STRUCTURE:  CHoCH  and the ORDER BLOCK it leaves behind
# ---------------------------------------------------------------------------
MIN_BREAK_ATR = 0.10     # a close must clear the swing by this much to count
OB_LOOKBACK   = 30       # SIGNAL BARS back for the last opposite candle
OB_TOL        = 0.50     # entry may sit this far outside the block, in ATR
CHOCH_MAX_AGE = 60       # SIGNAL BARS; a CHoCH older than this stops arming

tfo = tf["open"].to_numpy(np.float64)

choch_dir = np.zeros(N_TF, np.int8)
choch_bar = np.full(N_TF, -1, np.int64)
ob_lo     = np.full(N_TF, np.nan)
ob_hi     = np.full(N_TF, np.nan)

_state = 0
_cd, _cb, _olo, _ohi = 0, -1, np.nan, np.nan
for i in range(N_TF):
    a = tfatr[i]
    if np.isfinite(a) and a > 0:
        brk = MIN_BREAK_ATR * a
        sh, sl = piv_hi[i], piv_lo[i]
        ev = 0
        if np.isfinite(sh) and tfc[i] > sh + brk:
            ev = 1
        elif np.isfinite(sl) and tfc[i] < sl - brk:
            ev = -1
        # Only a break that FLIPS the prevailing structure is a CHoCH. A break
        # the same way as the current state is a BOS: continuation, not change.
        if ev != 0 and ev != _state:
            _state, _cd, _cb = ev, ev, i
            _olo = _ohi = np.nan
            for k in range(i, max(-1, i - OB_LOOKBACK), -1):
                if (ev > 0 and tfc[k] < tfo[k]) or (ev < 0 and tfc[k] > tfo[k]):
                    _olo, _ohi = tfl[k], tfh[k]
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
    px = tfc[i]
    if lo - OB_TOL * a <= px <= hi + OB_TOL * a:
        return True
    return False

VP_MODE = "breakout"

def volume_ok(i, d, a, poc, val, vah):
    if not (np.isfinite(val) and np.isfinite(vah) and vah > val):
        return False
    px = tfc[i]
    if VP_MODE == "breakout":
        return (px > vah) if d > 0 else (px < val)
    return val <= px <= vah

# ---------------------------------------------------------------------------
# ONE PASS: every cross, simulated, with both filter verdicts attached
# ---------------------------------------------------------------------------
def simulate(i, d, entry, risk, spread=None):
    sp = SPREAD if spread is None else spread
    stop0 = entry - d * risk
    be    = entry + d * sp
    tgt   = [entry + d * risk * m for m in (1.0, 2.0, 3.0)]
    j0 = J0[i]
    if j0 >= N_MIN:
        return None
    j1 = min(j0 + HOLD_BARS * TF_MIN, N_MIN)
    alive, tp1, r, k = [True] * 3, False, 0.0, j0
    while k < j1:
        cur = be if tp1 else stop0
        if (d > 0 and mlow[k] <= cur) or (d < 0 and mhig[k] >= cur):
            for x in range(3):
                if alive[x]:
                    r += ((cur - entry) * d - sp) / risk
                    alive[x] = False
            break
        for x in range(3):
            if alive[x] and ((d > 0 and mhig[k] >= tgt[x]) or (d < 0 and mlow[k] <= tgt[x])):
                r += ((tgt[x] - entry) * d - sp) / risk
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
                r += ((px - entry) * d - sp) / risk
    return r, kx - j0 + 1

bull = np.concatenate([[False], (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])])
bear = np.concatenate([[False], (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])])

rows = []
warm = max(VP_LOOKBACK, 250) + 10
for i in range(warm, N_TF):
    d = 1 if bull[i] else (-1 if bear[i] else 0)
    if d == 0:
        continue
    a = tfatr[i]
    if not np.isfinite(a) or a <= 0:
        continue
    entry = tfc[i]
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
    # The same setup replayed at zero spread. Not the same as adding the cost
    # back: at zero spread the break-even stop sits at the entry rather than
    # one spread inside profit, so a BE-stopped leg returns 0 either way and
    # adding the cost back would credit it with a spread it never earned.
    r0, _ = simulate(i, d, entry, risk, spread=0.0)

    poc, val, vah = profile_at(i, weights=gc_vol)
    rows.append(dict(bar=i, time=tfidx[i], dir=d, r=r, r0=r0, dur=dur,
                     risk_atr=risk / a, spread_r=SPREAD / risk,
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
            busy = bar + int(np.ceil(dur / TF_MIN))
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
# COST DIAGNOSTIC  -  is the filter predicting direction, or dodging cost?
#
# GROSS is the same setups replayed at zero spread - a second simulation, not
# the cost added back, because at zero spread the break-even stop sits at the
# entry instead of one spread inside profit. If GROSS sits near zero in every
# part while NET improves as the filters tighten, then
# the filters are not forecasting anything - they are selecting trades with
# wider stops, on which the same fixed spread is a smaller fraction of R. The
# fix for that is a larger stop, not a better filter.
# ---------------------------------------------------------------------------
print("\n" + "-" * 92)
print("COST DIAGNOSTIC   (GROSS = the same setups replayed at zero spread)")
print(f"{'part':<26}{'spread/R':>10}{'risk/ATR':>10}{'NET':>9}{'GROSS':>9}"
      f"{'G t':>7}{'G IS':>9}{'G t IS':>8}{'G OOS':>9}{'G t OOS':>9}")
for name, _f in PARTS:
    d = res[name]
    if len(d) < 2:
        continue
    _, e0, t0, _, _ = stat(d["r0"])
    _, ei, ti, _, _ = stat(d[d.time < IS_END]["r0"])
    _, eo, to, _, _ = stat(d[d.time >= IS_END]["r0"])
    print(f"{name:<26}{d.spread_r.mean():>10.4f}{d.risk_atr.mean():>10.2f}"
          f"{d.r.mean():>+9.4f}{e0:>+9.4f}{t0:>+7.2f}"
          f"{ei:>+9.4f}{ti:>+8.2f}{eo:>+9.4f}{to:>+9.2f}")
print("A gross edge that holds its sign and size in BOTH G IS and G OOS is the")
print("only version of this worth acting on. GROSS over the whole sample mixes")
print("the period the filters were chosen against with the one they were not.")

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

# ---------------------------------------------------------------------------
# MONTHLY REGIME  -  does the volatility break exist, and when?
#
# Checked rather than assumed. ATR/price is the volatility level; spread/R is
# what that volatility does to cost, since a fixed spread is a smaller share of
# a wider stop. If volatility rose and spread/R fell, a later period can show a
# better NET expectancy for a purely mechanical reason, with no change in the
# signal's ability to predict anything. GROSS is what separates the two.
# ---------------------------------------------------------------------------
mon = pd.DataFrame({"atr": tfatr, "px": tfc}, index=tfidx).resample("MS").mean()
mon["atr_pct"] = 100.0 * mon["atr"] / mon["px"]
_g = S.set_index("time").resample("MS")
mon["signals"] = _g.size()
mon["spread_r"] = _g["spread_r"].mean()
mon["E_net"] = _g["r"].mean()
mon["E_gross"] = _g["r0"].mean()
mon = mon[mon["signals"].fillna(0) > 0]

print("\n" + "=" * 92)
print("MONTHLY REGIME  (all crosses, before sequencing or filtering)")
print("=" * 92)
print(f"{'month':<10}{'ATR(5m)':>10}{'ATR/px %':>10}{'signals':>9}"
      f"{'spread/R':>10}{'NET E':>10}{'GROSS E':>10}")
for ts, r in mon.iterrows():
    print(f"{ts:%Y-%m}   {r['atr']:>10.2f}{r['atr_pct']:>10.3f}"
          f"{int(r['signals']):>9}{r['spread_r']:>10.4f}"
          f"{r['E_net']:>+10.4f}{r['E_gross']:>+10.4f}")

# ---------------------------------------------------------------------------
# TWO PERIODS  -  the full sample against the recent one
#
# MDE is the minimum detectable effect: the expectancy this many trades could
# resolve at 5% significance and 80% power. It is the ceiling on what a period
# can say. A result inside +/- MDE is consistent with no edge whatever its
# sign, and one outside it on a handful of trades is an outlier, not a finding.
# ---------------------------------------------------------------------------
Z = NormalDist().inv_cdf(0.975) + NormalDist().inv_cdf(0.80)   # 1.96 + 0.84
CUT = END - pd.DateOffset(months=RECENT_MONTHS)

print("\n" + "=" * 92)
print(f"TWO PERIODS   full = {START:%Y-%m-%d}..{END:%Y-%m-%d}   "
      f"recent = {CUT:%Y-%m-%d}..{END:%Y-%m-%d}")
print("=" * 92)
print(f"{'period':<12}{'part':<24}{'n':>6}{'NET E':>10}{'t':>7}"
      f"{'GROSS E':>10}{'G t':>7}{'spread/R':>10}{'MDE':>8}{'verdict':>15}")
for plabel, lo in (("full", START), (f"last {RECENT_MONTHS}m", CUT)):
    lab = plabel
    for name, f in PARTS:
        d = res[name]
        d = d[d.time >= lo]
        n, e, t, R, _ = stat(d["r"])
        if n < 2:
            print(f"{lab:<12}{name:<24}{n:>6}{'-':>10}{'-':>7}{'-':>10}"
                  f"{'-':>7}{'-':>10}{'-':>8}{'too few':>15}")
            lab = ""
            continue
        _, e0, t0, _, _ = stat(d["r0"])
        mde = Z * d["r"].std(ddof=1) / math.sqrt(n)
        verdict = ("inside noise" if abs(e) < mde
                   else ("positive" if e > 0 else "negative"))
        print(f"{lab:<12}{name:<24}{n:>6}{e:>+10.4f}{t:>+7.2f}"
              f"{e0:>+10.4f}{t0:>+7.2f}{d['spread_r'].mean():>10.4f}"
              f"{mde:>8.3f}{verdict:>15}")
        lab = ""
    print()

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
