# ============================================================================
# DOBBY  -  EXIT STRUCTURE SWEEP   (QuantConnect *Research*, Python project)
#
# WHAT THIS IS FOR
#   The signal is held fixed (M5 EMA 9/21 + the volume-profile filter, the one
#   combination that showed gross edge). Only the EXIT changes. The question is
#   whether the 3-leg 1/2/3R ladder is the right way to harvest that edge, or
#   whether it is throwing part of it away.
#
# THE THING TO GET STRAIGHT FIRST
#   MOVING A STOP DOES NOT REDUCE SPREAD COST. The spread is paid on the way in
#   and on the way out, once per leg, wherever the exit ends up. Break-even
#   stops, trailing stops and wider targets all change WHERE you exit. None of
#   them change WHETHER you pay.
#
#   Cost in R is spread / stop distance, and all three legs share one stop, so
#   every leg pays the same fraction. Measured on M5 that is 0.0948R per leg.
#   Against a gross edge of 0.1016R per leg, the ratio is 1.07 - the edge
#   barely clears the toll, which is the entire problem.
#
#   There are exactly three ways to move that ratio:
#     1. WIDEN THE STOP  - cost is spread/stop, so a wider stop is directly
#        cheaper in R. This is what the timeframe sweep tests.
#     2. NARROW THE SPREAD - trade only when the spread is actually tight.
#        Requires measuring your broker's spread by hour. Assumed here, and
#        flagged as an assumption wherever it appears.
#     3. RAISE GROSS - the only exit change that can do this is one that lets
#        winners run further than a fixed target would. That is what the
#        trailing variants below are for.
#
#   Everything else is redistribution: it moves R between legs and between
#   winners and losers without changing the total the signal is capable of.
#
# WHY LEG 1 IS THE WEAKEST LEG, AND WHY IT STAYS ANYWAY
#   A fixed cost hurts a near target far more than a far one:
#
#       leg   target   effective RR after cost   break-even hit rate
#       L1      1R            0.83 : 1                  54.7%
#       L2      2R            1.74 : 1                  36.5%
#       L3      3R            2.65 : 1                  27.4%
#
#   Leg 1 needs 54.7% accuracy and appears to run at about 50%, so it loses
#   almost exactly the cost. But it is also what arms the break-even move, and
#   that move looks worth roughly 0.5R per signal against leg 1's 0.095R -
#   about five times its cost. Hence the variants that keep the trigger but
#   change what triggers it, rather than deleting the leg.
# ============================================================================

import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from statistics import NormalDist

START, IS_END, END = datetime(2025,1,1), datetime(2026,1,1), datetime(2026,9,10)
SPREAD     = 0.7525
SIGNAL_TF  = "5min"
TF_MIN     = int(pd.Timedelta(SIGNAL_TF).total_seconds() // 60)
HOLD_MIN   = 10 * 60
VP_HOURS, VP_BINS, VALUE_AREA = 24.0, 48, 0.70
VP_LB      = max(20, int(VP_HOURS * 60 / TF_MIN))

qb  = QuantBook()
SYM = qb.add_cfd("XAUUSD", Resolution.MINUTE, Market.OANDA).symbol

def load_minute(sym, start, end):
    frames, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=90), end)
        h = qb.history(sym, cur, nxt, Resolution.MINUTE)
        if h is not None and len(h):
            if isinstance(h.index, pd.MultiIndex):
                h = h.droplevel(0)
            cols = {}
            for f in ("open","high","low","close"):
                if f in h.columns:
                    cols[f] = h[f].astype("float32")
                elif f"bid{f}" in h.columns and f"ask{f}" in h.columns:
                    cols[f] = ((h[f"bid{f}"]+h[f"ask{f}"])/2.0).astype("float32")
            if "volume" in h.columns:
                cols["volume"] = h["volume"].astype("float32")
            if len({"open","high","low","close"} & set(cols)) == 4:
                frames.append(pd.DataFrame(cols, index=h.index))
        del h
        cur = nxt
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated(keep="first")]

OHLC = {"open":"first","high":"max","low":"min","close":"last"}
minute = load_minute(SYM, START, END)
mi, mlow = minute.index.values, minute["low"].to_numpy(np.float64)
mhig, mclo = minute["high"].to_numpy(np.float64), minute["close"].to_numpy(np.float64)
N_MIN = len(mi)
DAYS  = N_MIN / (23*60)
print(f"minute bars {N_MIN:,}   ~{DAYS:.0f} trading days")

vol_minute, vol_source = None, "time (TPO) only"
for name, make in (("COMEX GC futures",
                    lambda: qb.add_future(Futures.Metals.GOLD, Resolution.MINUTE).symbol),
                   ("GLD ETF (US hours only)",
                    lambda: qb.add_equity("GLD", Resolution.MINUTE).symbol)):
    try:
        v = load_minute(make(), START, END)
        if "volume" in v.columns and float(v["volume"].abs().sum()) > 0:
            vol_minute, vol_source = v[["volume"]], name
            print(f"real volume from {name}")
            break
    except Exception as e:
        print(f"  {name}: {type(e).__name__}")

bars = minute.resample(SIGNAL_TF).agg(OHLC).dropna()
idx  = bars.index
c = bars["close"].to_numpy(np.float64); h = bars["high"].to_numpy(np.float64)
l = bars["low"].to_numpy(np.float64);   N = len(bars)
J0 = np.searchsorted(mi, (idx + pd.Timedelta(SIGNAL_TF)).values, side="left")

def wilder_atr(df, n):
    hh, ll, cc = (df["high"].astype("float64"), df["low"].astype("float64"),
                  df["close"].astype("float64"))
    pc = cc.shift(1)
    tr = pd.concat([hh-ll, (hh-pc).abs(), (ll-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/n, adjust=False).mean()

def pivot_available(series, left, right, is_low):
    s = series.astype("float64").reset_index(drop=True)
    if is_low:
        ok = (s < s.rolling(left).min().shift(1)) & (s < s.rolling(right).min().shift(-right))
    else:
        ok = (s > s.rolling(left).max().shift(1)) & (s > s.rolling(right).max().shift(-right))
    return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(right).ffill().to_numpy()

fast = pd.Series(c).ewm(span=9,  adjust=False).mean().to_numpy()
slow = pd.Series(c).ewm(span=21, adjust=False).mean().to_numpy()
atr  = wilder_atr(bars, 14).to_numpy()
piv_lo = pivot_available(bars["low"], 5, 5, True)
piv_hi = pivot_available(bars["high"], 5, 5, False)
fb_lo = bars["low"].rolling(10).min().to_numpy()
fb_hi = bars["high"].rolling(10).max().to_numpy()
vw = None
if vol_minute is not None:
    vw = (vol_minute["volume"].resample(SIGNAL_TF).sum()
          .reindex(idx).fillna(0.0).to_numpy(np.float64))

def value_area(i):
    a = max(0, i - VP_LB)
    if i - a < 20: return np.nan, np.nan
    lo, hi = l[a:i].min(), h[a:i].max()
    if not (hi > lo): return np.nan, np.nan
    bs = (hi - lo) / VP_BINS
    il = np.floor((l[a:i]-lo)/bs).astype(np.int64).clip(0, VP_BINS-1)
    ih = np.floor((h[a:i]-lo)/bs).astype(np.int64).clip(0, VP_BINS-1)
    span = (ih-il+1).astype(np.float64)
    w = np.ones(i-a) if vw is None else vw[a:i]
    w = np.divide(w, span, out=np.zeros_like(w, dtype=np.float64), where=span>0)
    d = np.zeros(VP_BINS+1); np.add.at(d, il, w); np.add.at(d, ih+1, -w)
    prof = np.cumsum(d)[:VP_BINS]; tot = prof.sum()
    if tot <= 0: return np.nan, np.nan
    poc = int(prof.argmax()); a_ = b_ = poc; acc = prof[poc]
    while acc < VALUE_AREA*tot and (a_ > 0 or b_ < VP_BINS-1):
        dn = prof[a_-1] if a_ > 0 else -1.0
        up = prof[b_+1] if b_ < VP_BINS-1 else -1.0
        if up >= dn: b_ += 1; acc += up
        else:        a_ -= 1; acc += dn
    return lo + (a_+0.5)*bs, lo + (b_+0.5)*bs

# ---------------------------------------------------------------------------
# A GENERAL EXIT ENGINE
#
# legs      list of target multiples; None in a slot means that leg trails
# be_at     None, or an R multiple whose TOUCH arms break-even on the
#           remaining legs. "fill" means the old behaviour: leg 1 filling.
# trail_atr None, or a multiple of the entry ATR to trail behind the extreme
#
# The stop always wins a tie with a target inside the same minute, and the
# trail only ratchets on bars already completed, so neither can see forward.
# ---------------------------------------------------------------------------
def simulate(i, d, entry, risk, a, legs, be_at, trail_atr, sp):
    n = len(legs)
    stop0 = entry - d*risk
    be    = entry + d*sp
    tgt   = [None if t is None else entry + d*risk*t for t in legs]
    j0 = J0[i]
    if j0 >= N_MIN: return None
    j1 = min(j0 + HOLD_MIN, N_MIN)
    alive = [True]*n
    armed = False
    ext   = entry                      # best price reached, for the trail
    r, k  = 0.0, j0
    while k < j1:
        cur = be if armed else stop0
        if trail_atr is not None and armed:
            cur = max(cur, ext - d*trail_atr*a) if d > 0 else min(cur, ext + trail_atr*a)
        if (d > 0 and mlow[k] <= cur) or (d < 0 and mhig[k] >= cur):
            for x in range(n):
                if alive[x]:
                    r += ((cur-entry)*d - sp)/risk
                    alive[x] = False
            break
        for x in range(n):
            if alive[x] and tgt[x] is not None and \
               ((d > 0 and mhig[k] >= tgt[x]) or (d < 0 and mlow[k] <= tgt[x])):
                r += ((tgt[x]-entry)*d - sp)/risk
                alive[x] = False
                if be_at == "fill" and x == 0:
                    armed = True
        if be_at not in (None, "fill") and not armed:
            lvl = entry + d*risk*be_at
            if (d > 0 and mhig[k] >= lvl) or (d < 0 and mlow[k] <= lvl):
                armed = True
        ext = max(ext, mhig[k]) if d > 0 else min(ext, mlow[k])
        if not any(alive): break
        k += 1
    kx = min(k, j1-1, N_MIN-1)
    if any(alive):
        px = mclo[kx]
        for x in range(n):
            if alive[x]:
                r += ((px-entry)*d - sp)/risk
    return r, kx-j0+1

# ---------------------------------------------------------------------------
# SIGNALS  (fixed: EMA cross + volume-profile breakout)
# ---------------------------------------------------------------------------
bull = np.concatenate([[False], (fast[1:]>slow[1:]) & (fast[:-1]<=slow[:-1])])
bear = np.concatenate([[False], (fast[1:]<slow[1:]) & (fast[:-1]>=slow[:-1])])

sigs = []
for i in range(max(VP_LB,250)+10, N):
    d = 1 if bull[i] else (-1 if bear[i] else 0)
    if d == 0: continue
    a = atr[i]
    if not np.isfinite(a) or a <= 0: continue
    entry = c[i]
    raw = piv_lo[i] if d > 0 else piv_hi[i]
    if not np.isfinite(raw): raw = fb_lo[i] if d > 0 else fb_hi[i]
    if not np.isfinite(raw): continue
    risk = abs(entry-raw)
    if risk <= 0: continue
    val, vah = value_area(i)
    if not (np.isfinite(val) and vah > val): continue
    if not ((c[i] > vah) if d > 0 else (c[i] < val)): continue
    sigs.append((i, d, entry, risk, a, idx[i]))
print(f"\nsignals after the volume filter: {len(sigs):,} ({len(sigs)/DAYS:.2f}/day)"
      f"   volume: {vol_source}")

VARIANTS = [
    ("3 legs 1/2/3, BE on TP1 fill", [1.,2.,3.], "fill", None),
    ("3 legs 1/2/3, BE on 0.5R touch", [1.,2.,3.], 0.5, None),
    ("3 legs 1/2/3, no BE at all",   [1.,2.,3.], None, None),
    ("3 legs 1.5/3/6, BE on TP1",    [1.5,3.,6.], "fill", None),
    ("3 legs 2/4/6, BE on TP1",      [2.,4.,6.], "fill", None),
    ("3 legs 1/2/run, trail 2 ATR",  [1.,2.,None], "fill", 2.0),
    ("3 legs 1/2/run, trail 3 ATR",  [1.,2.,None], "fill", 3.0),
    ("1 leg 2R",                     [2.], 0.5, None),
    ("1 leg, pure 2 ATR trail",      [None], 0.5, 2.0),
]

def stat(r):
    r = np.asarray(r, float); n = len(r)
    if n < 2: return n, float("nan"), float("nan"), 0.0
    e, sd = r.mean(), r.std(ddof=1)
    return n, e, (e/(sd/math.sqrt(n)) if sd > 0 else float("nan")), r.sum()

print("\n" + "="*100)
print("EXIT STRUCTURE   signal fixed, only the exit changes")
print("NET per SIGNAL. Variants risk different totals, so 'per R risked' is the")
print("column that compares them fairly.")
print("="*100)
print(f"{'variant':<32}{'legs':>5}{'n':>6}{'NET':>9}{'t':>7}{'GROSS':>9}"
      f"{'G t':>7}{'per R risked':>14}{'IS':>9}{'OOS':>9}")
for label, legs, be_at, tr in VARIANTS:
    rows = []
    busy = -1
    for (i, d, entry, risk, a, ts) in sigs:
        if i <= busy: continue
        s1 = simulate(i, d, entry, risk, a, legs, be_at, tr, SPREAD)
        if s1 is None: break
        r, dur = s1
        r0, _ = simulate(i, d, entry, risk, a, legs, be_at, tr, 0.0)
        rows.append((ts, r, r0))
        busy = i + int(np.ceil(dur/TF_MIN))
    D = pd.DataFrame(rows, columns=["time","r","r0"])
    if len(D) < 2:
        print(f"{label:<32}{len(legs):>5}{len(D):>6}   too few"); continue
    n, e, t, _ = stat(D["r"]); _, e0, t0, _ = stat(D["r0"])
    _, ei, _, _ = stat(D[D.time <  IS_END]["r"])
    _, eo, _, _ = stat(D[D.time >= IS_END]["r"])
    print(f"{label:<32}{len(legs):>5}{n:>6}{e:>+9.4f}{t:>+7.2f}{e0:>+9.4f}"
          f"{t0:>+7.2f}{e/len(legs):>+14.4f}{ei:>+9.4f}{eo:>+9.4f}")

print("\n" + "-"*100)
print("READ IT THIS WAY")
print("  GROSS rising across variants = the exit is releasing edge the old one")
print("     threw away. That is a real gain and trailing is the usual source.")
print("  GROSS flat while NET moves = redistribution only. The ladder shape is")
print("     shuffling R between legs and changing nothing that matters.")
print("  Fewer legs is NOT cheaper per R risked: spread scales with volume, not")
print("     with ticket count. One leg risking 1R pays the same 0.0948R that")
print("     each of three legs pays. Compare on 'per R risked', never on NET.")
print("-"*100)
