# =====================================================================
# CROSS-INSTRUMENT VALIDATION OF THE TREND ZONE
# Paste as ONE cell in a QuantConnect Research notebook. Self-contained:
# it does not use any helper from earlier cells.
#
# PRE-REGISTERED, written before the output is seen:
#   The rule is  z = (Close - SMA200) / ATR  on 15-minute bars,
#   long entries when z ENTERS [+1.08, +7.21], stop 1.8*ATR, target 8R,
#   time stop 1800 minutes. Fixed on gold; nothing is refitted here.
#
#   PASS  = net E > 0 AND t > 2.0 on BOTH XAGUSD and EURUSD,
#           on the long side, at the 8R target.
#   FAIL  = anything else. A fail means the zone was fitted to gold.
#
#   The drift-adjusted column is the honest one: gold rose for the whole
#   sample, so a long-only rule inherits that. If the effect only exists
#   before drift is removed, it is beta, not timing.
#
# Exits are resolved on MINUTE bars, not 15-minute bars. Resolving on the
# signal timeframe misses stops that were actually hit and inflates
# results (+0.06R at 1.5R, +0.20R at 3R in the earlier work).
# =====================================================================
from AlgorithmImports import *
from datetime import datetime
import pandas as pd, numpy as np, gc

# ---- fixed on gold, not refitted per instrument ----------------------
ZLO, ZHI      = 1.08, 7.21     # zone edges in ATR from the 200-bar SMA
SL_ATR        = 1.8            # stop distance
TARGET_R      = 8.0            # take profit in R
MAX_HOLD_MIN  = 1800           # 30 hours
SMA_N, ATR_N  = 200, 14
BAR           = "15min"
YEAR_FROM, YEAR_TO = 2012, 2026
LONG_ONLY     = True           # the side the equity curves were built on

# spread per instrument in PRICE units. Measure yours; these are the
# quoted means from the gold work plus conservative FX defaults.
SPREAD = {"XAUUSD": 0.7525, "XAGUSD": 0.030, "EURUSD": 0.00012}

qb = QuantBook()


def load_minutes(ticker):
    """Minute OHLC, loaded a quarter at a time so the free tier survives."""
    try:
        sym = qb.add_cfd(ticker, Resolution.MINUTE).symbol
    except Exception as e:
        print(f"  cannot add {ticker}: {e}")
        return None
    parts = []
    for y in range(YEAR_FROM, YEAR_TO + 1):
        for q in range(4):
            a = datetime(y, 1 + 3 * q, 1)
            b = datetime(y + 1, 1, 1) if q == 3 else datetime(y, 4 + 3 * q, 1)
            try:
                df = qb.history(sym, a, b, Resolution.MINUTE)
            except Exception:
                continue
            if df is None or len(df) == 0:
                continue
            if isinstance(df.index, pd.MultiIndex):
                df = df.droplevel(0)
            keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
            if len(keep) < 4:
                continue
            parts.append(df[keep].astype(np.float32))
            del df
        gc.collect()
    if not parts:
        return None
    m = pd.concat(parts).sort_index()
    del parts; gc.collect()
    m = m[~m.index.duplicated(keep="first")]
    return m[(m.high >= m.low) & (m.high > 0)]


def build_signals(m):
    """15-minute bars, z score, and the index of each bar's LAST minute.

    pandas labels a resampled bin by its LEFT edge. Mapping that label
    straight into the minute index lands on the FIRST minute of the bar -
    a 15-minute look-ahead. Bin the minutes the same way and take the
    last minute of each bin instead.
    """
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    b = m.resample(BAR).agg(agg).dropna()

    mbin = m.index.floor(BAR)
    last_min = np.searchsorted(mbin.values, b.index.values, side="right") - 1
    ok = (last_min >= 0) & (mbin.values[np.clip(last_min, 0, len(mbin) - 1)] == b.index.values)
    b, last_min = b[ok], last_min[ok]

    c = b["close"].to_numpy(float)
    h = b["high"].to_numpy(float)
    l = b["low"].to_numpy(float)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False).mean().to_numpy()
    sma = pd.Series(c).rolling(SMA_N).mean().to_numpy()

    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - sma) / atr
    return b, z, atr, last_min


def resolve(m, entries, spread):
    """Walk each trade forward minute by minute. Stop, target, or time."""
    mh = m["high"].to_numpy(float)
    ml = m["low"].to_numpy(float)
    mo = m["open"].to_numpy(float)
    n = len(mo)
    out, holds = [], []

    for i0, side, risk in entries:
        if i0 >= n:
            continue
        entry = mo[i0] + (spread if side > 0 else -spread)   # pay the spread on entry
        stop = entry - side * risk
        targ = entry + side * risk * TARGET_R
        j1 = min(i0 + MAX_HOLD_MIN, n)
        hi, lo = mh[i0:j1], ml[i0:j1]

        if side > 0:
            hit_s = np.flatnonzero(lo <= stop)
            hit_t = np.flatnonzero(hi >= targ)
        else:
            hit_s = np.flatnonzero(hi >= stop)
            hit_t = np.flatnonzero(lo <= targ)

        ks = hit_s[0] if hit_s.size else 10**9
        kt = hit_t[0] if hit_t.size else 10**9

        if ks == kt == 10**9:                     # time stop
            k = j1 - i0 - 1
            exit_px = (mh[j1 - 1] + ml[j1 - 1]) / 2
            r = side * (exit_px - entry) / risk
        elif ks <= kt:                            # stop first (same bar = stop)
            k, r = ks, -1.0
        else:
            k, r = kt, TARGET_R
        out.append(r)
        holds.append(k + 1)
    return np.array(out), np.array(holds, float)


def tstat(x):
    if len(x) < 30:
        return np.nan
    s = x.std(ddof=1)
    return x.mean() / (s / np.sqrt(len(x))) if s > 0 else np.nan


def run(ticker):
    print(f"\n### {ticker}")
    m = load_minutes(ticker)
    if m is None or len(m) < 50000:
        print("  no usable data")
        return None
    b, z, atr, last_min = build_signals(m)

    # drift charged per minute, in price units, over the same sample
    c = m["close"].to_numpy(float)
    drift = float(np.diff(c).mean())

    sides = (1,) if LONG_ONLY else (1, -1)
    res = {}
    for side in sides:
        lo, hi = (ZLO, ZHI) if side > 0 else (-ZHI, -ZLO)
        inz = (z >= lo) & (z <= hi)
        # fire only on ENTERING the zone, and only where ATR is defined
        trig = np.flatnonzero(inz[1:] & ~inz[:-1] & np.isfinite(atr[1:])) + 1
        ent = [(int(last_min[i] + 1), side, SL_ATR * atr[i]) for i in trig
               if last_min[i] + 1 < len(m) and atr[i] > 0]
        if len(ent) < 100:
            print(f"  side {side:+d}: only {len(ent)} signals, skipped")
            continue

        r, hold = resolve(m, ent, SPREAD.get(ticker, 0.0))
        risks = np.array([e[2] for e in ent[:len(r)]], float)
        rd = r - side * drift * hold / risks          # remove the market's own move

        res[side] = dict(n=len(r), hit=float((r > 0).mean() * 100),
                         E=float(r.mean()), t=float(tstat(r)),
                         Ed=float(rd.mean()), td=float(tstat(rd)))
        d = res[side]
        print(f"  side {side:+d}  n={d['n']:>6,}  hit {d['hit']:5.1f}%   "
              f"E {d['E']:+.4f}R (t {d['t']:+.2f})   "
              f"drift-adj {d['Ed']:+.4f}R (t {d['td']:+.2f})")
    del m, b, z, atr; gc.collect()
    return res


print("=" * 66)
print("CROSS-INSTRUMENT TEST - zone fixed on gold, nothing refitted")
print(f"zone [{ZLO}, {ZHI}] ATR | stop {SL_ATR}xATR | target {TARGET_R}R | "
      f"hold {MAX_HOLD_MIN}min")
print("=" * 66)

all_res = {}
for tk in ("XAUUSD", "XAGUSD", "EURUSD"):
    all_res[tk] = run(tk)

print("\n" + "=" * 66)
print("VERDICT")
print("=" * 66)
verdict = []
for tk in ("XAGUSD", "EURUSD"):
    d = (all_res.get(tk) or {}).get(1)
    if d is None:
        print(f"  {tk:<8} no result")
        verdict.append(False)
        continue
    ok = d["E"] > 0 and d["t"] > 2.0
    okd = d["Ed"] > 0 and d["td"] > 2.0
    print(f"  {tk:<8} E {d['E']:+.4f} t {d['t']:+.2f} -> {'PASS' if ok else 'FAIL'}"
          f"   | drift-adj {d['Ed']:+.4f} t {d['td']:+.2f} -> {'PASS' if okd else 'FAIL'}")
    verdict.append(ok)

print()
if all(verdict):
    print("  *** THE ZONE CARRIED ACROSS INSTRUMENTS ***")
    print("  It is more likely a real effect. Next: walk-forward, then size it.")
else:
    print("  *** IT DID NOT CARRY ***")
    print("  The zone was fitted to gold. Do not trade it. Do not retune the")
    print("  edges per instrument - that turns one overfit into three.")
print("=" * 66)
