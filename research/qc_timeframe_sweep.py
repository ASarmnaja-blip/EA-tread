# ============================================================================
# DOBBY  -  TIMEFRAME SWEEP   (QuantConnect *Research*, Python project)
#
# M1, M5 and M15, with the logic re-anchored for each so the comparison is
# fair. Exits always resolve on 1-minute bars whatever the signal timeframe.
#
# THE PREDICTION, WRITTEN DOWN BEFORE THE RUN
#   Part 2 (the volume-profile filter) showed gross expectancy of +0.3048R at
#   t = +2.81 on M5 against a baseline with none, but net of only +0.03R
#   because the spread ate it. ATR scales with the square root of time, so a
#   higher timeframe means a wider stop and a fixed spread that is a smaller
#   share of R. If that reading is right:
#
#       tf     spread/R   cost (3 legs)   predicted NET
#       M1       0.212        0.636          -0.331
#       M5       0.095        0.284          +0.020
#       M15      0.055        0.164          +0.141
#
#   THE TEST IS MONOTONICITY, NOT WHICH TIMEFRAME WINS.
#     1. spread/R must FALL as the timeframe rises. If it does not, the cost
#        mechanism is wrong and nothing else here matters.
#     2. NET must RISE with it, in order: M1 < M5 < M15.
#     3. GROSS should stay roughly FLAT. Gross rising with the timeframe would
#        mean a different signal rather than a cheaper one, and would kill the
#        cost story rather than confirm it.
#
#   One timeframe landing positive while the order is scrambled is the outcome
#   to distrust: three draws and one winner is what noise looks like.
#
# HOW THE LOGIC IS RE-ANCHORED, AND WHY THE SPLIT IS WHERE IT IS
#   SIGNAL SHAPE STAYS IN BARS. "EMA 9/21" means the same thing on any chart,
#   and so do a 14-bar ATR and a 5-bar pivot. Rescaling those would test a
#   different indicator on each timeframe rather than the same one.
#
#   MARKET CONTEXT STAYS IN CLOCK TIME. How long a value area is relevant, how
#   long a structure break stays live, how long a trade should be given to
#   work - none of that changes because you changed your chart. Leaving them
#   in bars would silently give M15 a 30-hour hold against M1's 2 hours, and
#   the sweep would be measuring the hold, not the timeframe.
#
# RUNTIME: M1 produces several times more crosses than M5 and each is
# simulated twice, at the real spread and at zero. Expect a few minutes.
# ============================================================================

import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from statistics import NormalDist

START   = datetime(2025, 1,  1)
IS_END  = datetime(2026, 1,  1)
END     = datetime(2026, 9, 10)
SPREAD  = 0.7525

TIMEFRAMES = ["1min", "5min", "15min"]

# --- signal shape: bars, identical on every timeframe ----------------------
EMA_FAST, EMA_SLOW = 9, 21
ATR_LEN            = 14
PIVOT_L = PIVOT_R  = 5
FALLBACK           = 10

# --- market context: clock time, identical on every timeframe --------------
VP_HOURS        = 24.0
HOLD_HOURS      = 10.0
CHOCH_MAX_HOURS = 5.0
OB_LOOKBACK_HRS = 2.5

VP_BINS       = 48
VALUE_AREA    = 0.70
MIN_BREAK_ATR = 0.10
OB_TOL        = 0.50
VP_MODE       = "breakout"
USE_REAL_VOLUME = True

qb  = QuantBook()
SYM = qb.add_cfd("XAUUSD", Resolution.MINUTE, Market.OANDA).symbol

# ---------------------------------------------------------------------------
# LOAD  (once; every timeframe is resampled from this)
# ---------------------------------------------------------------------------
def load_minute(sym, start, end):
    frames, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=90), end)
        h = qb.history(sym, cur, nxt, Resolution.MINUTE)
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

OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}
minute = load_minute(SYM, START, END)
mi   = minute.index.values
mlow = minute["low"].to_numpy(np.float64)
mhig = minute["high"].to_numpy(np.float64)
mclo = minute["close"].to_numpy(np.float64)
N_MIN = len(mi)
SESSION_MIN = 23 * 60
DAYS = N_MIN / SESSION_MIN
print(f"minute bars {N_MIN:,}   {minute.index[0]} -> {minute.index[-1]}"
      f"   ~{DAYS:.0f} trading days")

vol_minute, vol_source = None, "time (TPO) only"
if USE_REAL_VOLUME:
    tried = []
    for name, make in (("COMEX GC futures",
                        lambda: qb.add_future(Futures.Metals.GOLD, Resolution.MINUTE).symbol),
                       ("GLD ETF (US hours only)",
                        lambda: qb.add_equity("GLD", Resolution.MINUTE).symbol)):
        try:
            v = load_minute(make(), START, END)
            if "volume" in v.columns and float(v["volume"].abs().sum()) > 0:
                vol_minute, vol_source = v[["volume"]], name
                print(f"real volume from {name}: total {v['volume'].sum():,.0f}")
                break
            tried.append(f"{name}: no volume")
        except Exception as e:
            tried.append(f"{name}: {type(e).__name__}")
    if vol_minute is None:
        print(f"no real-volume source ({'; '.join(tried)}) - time profile only")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def wilder_atr(df, n):
    h, l, c = (df["high"].astype("float64"), df["low"].astype("float64"),
               df["close"].astype("float64"))
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()

def pivot_available(series, left, right, is_low):
    s = series.astype("float64").reset_index(drop=True)
    if is_low:
        ok = (s < s.rolling(left).min().shift(1)) & (s < s.rolling(right).min().shift(-right))
    else:
        ok = (s > s.rolling(left).max().shift(1)) & (s > s.rolling(right).max().shift(-right))
    return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(right).ffill().to_numpy()

def stat(r):
    r = np.asarray(r, float)
    n = len(r)
    if n < 2:
        return n, float("nan"), float("nan"), 0.0
    e, sd = r.mean(), r.std(ddof=1)
    return n, e, (e / (sd / math.sqrt(n)) if sd > 0 else float("nan")), r.sum()

# ---------------------------------------------------------------------------
# ONE TIMEFRAME
# ---------------------------------------------------------------------------
def run_tf(tf_str):
    TF = int(pd.Timedelta(tf_str).total_seconds() // 60)
    bars = minute.resample(tf_str).agg(OHLC).dropna()
    idx  = bars.index
    c = bars["close"].to_numpy(np.float64)
    h = bars["high"].to_numpy(np.float64)
    l = bars["low"].to_numpy(np.float64)
    o = bars["open"].to_numpy(np.float64)
    N = len(bars)

    VP_LB     = max(20, int(VP_HOURS * 60 / TF))
    HOLD_MIN  = int(HOLD_HOURS * 60)
    CHOCH_AGE = max(1, int(CHOCH_MAX_HOURS * 60 / TF))
    OB_LB     = max(2, int(OB_LOOKBACK_HRS * 60 / TF))

    J0 = np.searchsorted(mi, (idx + pd.Timedelta(tf_str)).values, side="left")
    fast = pd.Series(c).ewm(span=EMA_FAST, adjust=False).mean().to_numpy()
    slow = pd.Series(c).ewm(span=EMA_SLOW, adjust=False).mean().to_numpy()
    atr  = wilder_atr(bars, ATR_LEN).to_numpy()
    piv_lo = pivot_available(bars["low"],  PIVOT_L, PIVOT_R, True)
    piv_hi = pivot_available(bars["high"], PIVOT_L, PIVOT_R, False)
    fb_lo  = bars["low"].rolling(FALLBACK).min().to_numpy()
    fb_hi  = bars["high"].rolling(FALLBACK).max().to_numpy()

    vw = None
    if vol_minute is not None:
        vw = (vol_minute["volume"].resample(tf_str).sum()
              .reindex(idx).fillna(0.0).to_numpy(np.float64))

    def profile(i):
        a = max(0, i - VP_LB)
        if i - a < 20:
            return np.nan, np.nan
        lo, hi = l[a:i].min(), h[a:i].max()
        if not (hi > lo):
            return np.nan, np.nan
        bs = (hi - lo) / VP_BINS
        il = np.floor((l[a:i] - lo) / bs).astype(np.int64).clip(0, VP_BINS - 1)
        ih = np.floor((h[a:i] - lo) / bs).astype(np.int64).clip(0, VP_BINS - 1)
        span = (ih - il + 1).astype(np.float64)
        w = np.ones(i - a) if vw is None else vw[a:i]
        w = np.divide(w, span, out=np.zeros_like(w, dtype=np.float64), where=span > 0)
        d = np.zeros(VP_BINS + 1)
        np.add.at(d, il, w)
        np.add.at(d, ih + 1, -w)
        prof = np.cumsum(d)[:VP_BINS]
        tot = prof.sum()
        if tot <= 0:
            return np.nan, np.nan
        poc = int(prof.argmax())
        a_, b_ = poc, poc
        acc = prof[poc]
        while acc < VALUE_AREA * tot and (a_ > 0 or b_ < VP_BINS - 1):
            dn = prof[a_ - 1] if a_ > 0 else -1.0
            up = prof[b_ + 1] if b_ < VP_BINS - 1 else -1.0
            if up >= dn:
                b_ += 1; acc += up
            else:
                a_ -= 1; acc += dn
        return lo + (a_ + 0.5) * bs, lo + (b_ + 0.5) * bs

    # CHoCH: a close beyond the last confirmed opposing swing that FLIPS the
    # prevailing structure. A same-direction break is a BOS and re-arms nothing.
    cd = np.zeros(N, np.int8); cb = np.full(N, -1, np.int64)
    olo = np.full(N, np.nan); ohi = np.full(N, np.nan)
    st, _d, _b, _lo, _hi = 0, 0, -1, np.nan, np.nan
    for i in range(N):
        a = atr[i]
        if np.isfinite(a) and a > 0:
            brk = MIN_BREAK_ATR * a
            ev = 0
            if np.isfinite(piv_hi[i]) and c[i] > piv_hi[i] + brk:
                ev = 1
            elif np.isfinite(piv_lo[i]) and c[i] < piv_lo[i] - brk:
                ev = -1
            if ev != 0 and ev != st:
                st, _d, _b = ev, ev, i
                _lo = _hi = np.nan
                for k in range(i, max(-1, i - OB_LB), -1):
                    if (ev > 0 and c[k] < o[k]) or (ev < 0 and c[k] > o[k]):
                        _lo, _hi = l[k], h[k]
                        break
        cd[i], cb[i], olo[i], ohi[i] = _d, _b, _lo, _hi

    def simulate(i, d, entry, risk, sp):
        stop0 = entry - d * risk
        be    = entry + d * sp
        tgt   = [entry + d * risk * m for m in (1.0, 2.0, 3.0)]
        j0 = J0[i]
        if j0 >= N_MIN:
            return None
        j1 = min(j0 + HOLD_MIN, N_MIN)
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
    warm = max(VP_LB, 250) + 10
    for i in range(warm, N):
        d = 1 if bull[i] else (-1 if bear[i] else 0)
        if d == 0:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = c[i]
        raw = piv_lo[i] if d > 0 else piv_hi[i]
        if not np.isfinite(raw):
            raw = fb_lo[i] if d > 0 else fb_hi[i]
        if not np.isfinite(raw):
            continue
        risk = abs(entry - raw)
        if risk <= 0:
            continue
        s1 = simulate(i, d, entry, risk, SPREAD)
        if s1 is None:
            break
        r, dur = s1
        r0, _ = simulate(i, d, entry, risk, 0.0)

        val, vah = profile(i)
        vp_ok = bool(np.isfinite(val) and vah > val and
                     ((c[i] > vah) if d > 0 else (c[i] < val))) if VP_MODE == "breakout" \
                else bool(np.isfinite(val) and val <= c[i] <= vah)
        st_ok = False
        if cd[i] == d and cb[i] >= 0 and (i - cb[i]) <= CHOCH_AGE \
           and np.isfinite(olo[i]) and np.isfinite(ohi[i]):
            st_ok = bool(olo[i] - OB_TOL * a <= c[i] <= ohi[i] + OB_TOL * a)

        rows.append(dict(bar=i, time=idx[i], r=r, r0=r0, dur=dur,
                         spread_r=SPREAD / risk, risk_atr=risk / a,
                         vp_ok=vp_ok, st_ok=st_ok))

    S = pd.DataFrame(rows)
    out = {}
    for name, f in (("1 baseline", lambda x: np.ones(len(x), bool)),
                    ("2 +volume",  lambda x: x.vp_ok.to_numpy()),
                    ("3 +CHoCH/OB", lambda x: x.st_ok.to_numpy()),
                    ("4 +both",    lambda x: (x.vp_ok & x.st_ok).to_numpy())):
        sub = S[f(S)].reset_index(drop=True)
        take, busy = [], -1
        for b_, du in zip(sub.bar.to_numpy(), sub.dur.to_numpy()):
            if b_ > busy:
                take.append(True); busy = b_ + int(np.ceil(du / TF))
            else:
                take.append(False)
        out[name] = sub[np.array(take)] if len(sub) else sub
    return TF, len(S), out

# ---------------------------------------------------------------------------
# SWEEP
# ---------------------------------------------------------------------------
RES = {}
for tfs in TIMEFRAMES:
    TF, ncross, parts = run_tf(tfs)
    RES[tfs] = parts
    print(f"\n{tfs}: {ncross:,} crosses ({ncross/DAYS:.1f}/day)   "
          f"VP window {int(VP_HOURS*60/TF)} bars   hold {int(HOLD_HOURS*60/TF)} bars"
          f"   CHoCH age {max(1,int(CHOCH_MAX_HOURS*60/TF))} bars")

print("\n" + "=" * 96)
print("TIMEFRAME SWEEP   volume:", vol_source)
print("=" * 96)
print(f"{'tf':<8}{'part':<13}{'n':>6}{'n/day':>7}{'spread/R':>10}"
      f"{'NET E':>9}{'t':>7}{'GROSS E':>9}{'G t':>7}{'NET IS':>9}{'NET OOS':>9}")
for tfs in TIMEFRAMES:
    lab = tfs
    for name in ("1 baseline", "2 +volume", "3 +CHoCH/OB", "4 +both"):
        d = RES[tfs][name]
        n, e, t, _ = stat(d["r"]) if len(d) else (0, 0, 0, 0)
        if n < 2:
            print(f"{lab:<8}{name:<13}{n:>6}{'-':>7}{'-':>10}{'-':>9}{'-':>7}"
                  f"{'-':>9}{'-':>7}{'-':>9}{'-':>9}")
            lab = ""
            continue
        _, e0, t0, _ = stat(d["r0"])
        _, ei, _, _ = stat(d[d.time < IS_END]["r"])
        _, eo, _, _ = stat(d[d.time >= IS_END]["r"])
        print(f"{lab:<8}{name:<13}{n:>6}{n/DAYS:>7.2f}{d.spread_r.mean():>10.4f}"
              f"{e:>+9.4f}{t:>+7.2f}{e0:>+9.4f}{t0:>+7.2f}{ei:>+9.4f}{eo:>+9.4f}")
        lab = ""
    print()

print("=" * 96)
print("MONOTONICITY - the actual test.  Part 2 across timeframes:")
print(f"{'tf':<8}{'spread/R':>10}{'cost 3x':>10}{'NET E':>10}{'GROSS E':>10}"
      f"{'SE':>10}{'n':>7}")
chain = []
for tfs in TIMEFRAMES:
    d = RES[tfs]["2 +volume"]
    if len(d) < 2:
        continue
    _, e, _, _ = stat(d["r"]); _, e0, _, _ = stat(d["r0"])
    sp = d.spread_r.mean()
    se0 = d["r0"].std(ddof=1) / math.sqrt(len(d))
    chain.append((tfs, sp, e, e0, se0, len(d)))
    print(f"{tfs:<8}{sp:>10.4f}{3*sp:>10.4f}{e:>+10.4f}{e0:>+10.4f}"
          f"{se0:>10.4f}{len(d):>7}")
if len(chain) >= 2:
    sp_falls  = all(chain[i][1] > chain[i+1][1] for i in range(len(chain)-1))
    net_rises = all(chain[i][2] < chain[i+1][2] for i in range(len(chain)-1))
    # "Flat" has to be judged against how precisely each gross is measured.
    # The three timeframes carry very different trade counts, so an absolute
    # threshold would call a well-measured wobble flat and a barely-measured
    # one a trend. Compare the extremes against their own combined error.
    hi = max(chain, key=lambda x: x[3])
    lo = min(chain, key=lambda x: x[3])
    gap = hi[3] - lo[3]
    comb = math.sqrt(hi[4] ** 2 + lo[4] ** 2)
    z = gap / comb if comb > 0 else float("inf")
    gr_flat = z < 2.0
    print(f"\n  spread/R falls with timeframe : {'YES' if sp_falls else 'NO'}"
          f"   {'' if sp_falls else '<- cost mechanism is wrong, stop here'}")
    print(f"  NET rises with timeframe      : {'YES' if net_rises else 'NO'}"
          f"   {'' if net_rises else '<- not a cost story'}")
    print(f"  GROSS stays flat              : {'YES' if gr_flat else 'NO'}"
          f"   (widest gap {gap:+.4f} = {z:.1f} combined SE, {lo[0]} vs {hi[0]})")
    if not gr_flat:
        print("      gross moves by more than measurement error, so this is a")
        print("      different signal per timeframe, not the same one made cheaper")
    # Necessary is not sufficient. On a driftless random walk all three checks
    # above pass - spread falls, net rises, gross is flat at zero - and net
    # stays deeply negative at every timeframe, because there was never
    # anything to make cheaper. Gross has to be POSITIVE for the rest to matter.
    best = max(chain, key=lambda x: x[3])
    gz = best[3] / best[4] if best[4] > 0 else 0.0
    print(f"  GROSS is positive             : "
          f"{'YES' if best[3] > 0 and gz > 2.0 else 'NO'}"
          f"   (best {best[0]}: {best[3]:+.4f} at {gz:+.1f} SE)")
    print("\n  The first three say the cost mechanism is real. Only the fourth")
    print("  says there is an edge for it to uncover: a driftless random walk")
    print("  passes the first three and still loses at every timeframe.")
    print("  One timeframe positive with the order scrambled is three draws")
    print("  and one winner, which is what noise looks like.")
print("=" * 96)
