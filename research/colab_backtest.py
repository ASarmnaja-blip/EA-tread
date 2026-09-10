# ============================================================================
# DOBBY  -  COLAB BACKTEST      (Google Colab, or any plain Python)
#
# No QuantConnect. Reads M1 bars exported from YOUR OWN MetaTrader 5 terminal
# and runs the same M1 / M5 / M15 comparison against them.
#
# WHY THIS IS BETTER THAN THE QUANTCONNECT VERSION
#   Every result so far charged ONE FLAT SPREAD of 0.7525 - an average lifted
#   from OANDA, not a measurement of your broker. That single assumption has
#   been the largest unpinned number in the whole investigation: the volume-
#   filtered signal showed gross +0.3048R against a cost of 0.2844R, so the
#   verdict turns on a number nobody had measured.
#
#   MetaTrader records the spread it actually charged on every bar. Exported
#   with tools/export_mt5_data.py, that column comes with the data, and this
#   notebook charges it PER TRADE - the real spread at the entry minute and the
#   real spread at the exit minute - instead of one flat guess.
#
#   A flat average is not conservative, it is just wrong in both directions at
#   once: it overcharges the liquid hours and undercharges the rollover.
#
# GETTING THE DATA
#   On the Windows box running MetaTrader 5, with the terminal open:
#
#       pip install MetaTrader5 pandas
#       python tools/export_mt5_data.py --list          # find the real symbol
#       python tools/export_mt5_data.py --symbol XAUUSD --timeframe M1 --years 2
#
#   That writes data/XAUUSD_M1.csv plus a .meta.json holding the point size,
#   which is what converts the spread column from points into price. Put both
#   in Google Drive, then point CSV_PATH below at the CSV.
#
# WITHOUT MT5
#   Set FLAT_SPREAD and leave the file without a spread column. The run still
#   works and simply reproduces the QuantConnect assumption, which is worth
#   doing once as a cross-check that the two harnesses agree.
# ============================================================================

import numpy as np
import pandas as pd
import math, json, os
from statistics import NormalDist

# ---------------------------------------------------------------------------
CSV_PATH    = "/content/drive/MyDrive/XAUUSD_M1.csv"
META_PATH   = ""            # blank = look for CSV_PATH with .meta.json
FLAT_SPREAD = 0.7525        # fallback only, when the file has no spread column
POINT       = None          # None = read from meta, else e.g. 0.01 for 2-digit gold

TIMEFRAMES  = ["1min", "5min", "15min"]
IS_FRACTION = 0.60          # first 60% of the file is in-sample

EMA_FAST, EMA_SLOW, ATR_LEN = 9, 21, 14
PIVOT_L, PIVOT_R, FALLBACK = 5, 5, 10
VP_HOURS, HOLD_HOURS = 24.0, 10.0
VP_BINS, VALUE_AREA  = 48, 0.70
TARGETS = (1.0, 2.0, 3.0)

# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------
if not os.path.exists(CSV_PATH):
    try:
        from google.colab import drive
        drive.mount("/content/drive")
    except Exception:
        pass
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(
        f"{CSV_PATH} not found. Mount Drive and put the export there, or use\n"
        "  from google.colab import files; files.upload()\n"
        "and set CSV_PATH to the uploaded filename.")

raw = pd.read_csv(CSV_PATH)
tcol = "time" if "time" in raw.columns else raw.columns[0]
raw[tcol] = pd.to_datetime(raw[tcol])
raw = raw.set_index(tcol).sort_index()
raw = raw[~raw.index.duplicated(keep="first")]

point = POINT
if point is None:
    mp = META_PATH or (os.path.splitext(CSV_PATH)[0] + ".meta.json")
    if os.path.exists(mp):
        point = float(json.load(open(mp))["point"])
        print(f"point size {point} from {os.path.basename(mp)}")
if point is None:
    # 2-digit gold is 0.01. Inferred, and stated, rather than silently assumed.
    point = 0.01
    print(f"no meta file - assuming point = {point}. Wrong for a 3-digit feed;"
          " set POINT if your broker quotes gold to 3 decimals.")

minute = raw[["open", "high", "low", "close"]].astype("float64")
if "spread" in raw.columns and raw["spread"].abs().sum() > 0:
    msp = (raw["spread"].astype("float64") * point).to_numpy()
    SPREAD_SOURCE = "REAL, per bar, from your broker"
else:
    msp = np.full(len(minute), FLAT_SPREAD)
    SPREAD_SOURCE = f"flat {FLAT_SPREAD} (no spread column in the file)"

mi   = minute.index.values
mlow = minute["low"].to_numpy(); mhig = minute["high"].to_numpy()
mclo = minute["close"].to_numpy(); N_MIN = len(mi)
DAYS = N_MIN / (23 * 60)
CUT  = minute.index[int(len(minute) * IS_FRACTION)]
print(f"\n{N_MIN:,} M1 bars   {minute.index[0]} -> {minute.index[-1]}"
      f"   ~{DAYS:.0f} trading days")
print(f"spread source: {SPREAD_SOURCE}")
print(f"in-sample up to {CUT}, out-of-sample after")

# ---------------------------------------------------------------------------
# WHAT THE SPREAD ACTUALLY DOES BY HOUR
# ---------------------------------------------------------------------------
sph = pd.DataFrame({"sp": msp, "h": minute.index.hour}).groupby("h")["sp"]
tab = sph.agg(["median", "mean", "max", "count"])
print("\n" + "=" * 68)
print("SPREAD BY HOUR (broker clock)   this is the number every earlier")
print("backtest replaced with a single average")
print("=" * 68)
print(f"{'hour':>5}{'median':>10}{'mean':>10}{'max':>10}{'bars':>10}{'':>4}")
for hh, r in tab.iterrows():
    bar = "#" * int(round(r["median"] / max(tab["median"].max(), 1e-9) * 20))
    print(f"{hh:>5}{r['median']:>10.4f}{r['mean']:>10.4f}{r['max']:>10.4f}"
          f"{int(r['count']):>10}  {bar}")
# Thresholds, not nsmallest: when many hours share a median, picking "the
# lowest 8" returns an arbitrary subset and can list the same hour as both
# cheapest and dearest.
med = float(np.median(msp))
cheap = tab.index[tab["median"] <= med].tolist()
dear  = tab.index[tab["median"] >= 1.5 * med].tolist()
print(f"\nat or below the overall median: {cheap}")
print(f"at least 1.5x the overall median: {dear}")
print(f"overall median {np.median(msp):.4f}   mean {msp.mean():.4f}"
      f"   ratio dearest/cheapest hour "
      f"{tab['median'].max()/max(tab['median'].min(),1e-9):.1f}x")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}

def wilder_atr(df, n):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()

def pivots(series, left, right, is_low):
    s = series.reset_index(drop=True)
    if is_low:
        ok = (s < s.rolling(left).min().shift(1)) & (s < s.rolling(right).min().shift(-right))
    else:
        ok = (s > s.rolling(left).max().shift(1)) & (s > s.rolling(right).max().shift(-right))
    return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(right).ffill().to_numpy()

def stat(r):
    r = np.asarray(r, float); n = len(r)
    if n < 2: return n, float("nan"), float("nan"), 0.0
    e, sd = r.mean(), r.std(ddof=1)
    return n, e, (e / (sd / math.sqrt(n)) if sd > 0 else float("nan")), r.sum()

# ---------------------------------------------------------------------------
# ONE TIMEFRAME
# ---------------------------------------------------------------------------
def run_tf(tf_str, spread_arr):
    TF = int(pd.Timedelta(tf_str).total_seconds() // 60)
    bars = minute.resample(tf_str).agg(OHLC).dropna()
    idx = bars.index
    c = bars["close"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();   N = len(bars)
    VP_LB    = max(20, int(VP_HOURS * 60 / TF))
    HOLD_MIN = int(HOLD_HOURS * 60)
    J0 = np.searchsorted(mi, (idx + pd.Timedelta(tf_str)).values, side="left")

    fast = pd.Series(c).ewm(span=EMA_FAST, adjust=False).mean().to_numpy()
    slow = pd.Series(c).ewm(span=EMA_SLOW, adjust=False).mean().to_numpy()
    atr  = wilder_atr(bars, ATR_LEN).to_numpy()
    p_lo = pivots(bars["low"], PIVOT_L, PIVOT_R, True)
    p_hi = pivots(bars["high"], PIVOT_L, PIVOT_R, False)
    f_lo = bars["low"].rolling(FALLBACK).min().to_numpy()
    f_hi = bars["high"].rolling(FALLBACK).max().to_numpy()

    def value_area(i):
        a = max(0, i - VP_LB)
        if i - a < 20: return np.nan, np.nan
        lo, hi = l[a:i].min(), h[a:i].max()
        if not (hi > lo): return np.nan, np.nan
        bs = (hi - lo) / VP_BINS
        il = np.floor((l[a:i] - lo) / bs).astype(np.int64).clip(0, VP_BINS - 1)
        ih = np.floor((h[a:i] - lo) / bs).astype(np.int64).clip(0, VP_BINS - 1)
        span = (ih - il + 1).astype(float)
        w = np.divide(np.ones(i - a), span, out=np.zeros(i - a), where=span > 0)
        d = np.zeros(VP_BINS + 1); np.add.at(d, il, w); np.add.at(d, ih + 1, -w)
        prof = np.cumsum(d)[:VP_BINS]; tot = prof.sum()
        if tot <= 0: return np.nan, np.nan
        poc = int(prof.argmax()); a_ = b_ = poc; acc = prof[poc]
        while acc < VALUE_AREA * tot and (a_ > 0 or b_ < VP_BINS - 1):
            dn = prof[a_ - 1] if a_ > 0 else -1.0
            up = prof[b_ + 1] if b_ < VP_BINS - 1 else -1.0
            if up >= dn: b_ += 1; acc += up
            else:        a_ -= 1; acc += dn
        return lo + (a_ + .5) * bs, lo + (b_ + .5) * bs

    def simulate(i, d, entry, risk, free=False):
        """Charges half the spread entering and half leaving, at the spread
        that actually applied on each of those minutes. free=True replays the
        identical path at zero cost, which is the GROSS column."""
        j0 = J0[i]
        if j0 >= N_MIN: return None
        sp_in = 0.0 if free else spread_arr[j0]
        stop0 = entry - d * risk
        be    = entry + d * sp_in
        tgt   = [entry + d * risk * m for m in TARGETS]
        j1 = min(j0 + HOLD_MIN, N_MIN)
        alive, tp1, r, k = [True] * 3, False, 0.0, j0
        while k < j1:
            sp_out = 0.0 if free else spread_arr[k]
            cost = 0.5 * sp_in + 0.5 * sp_out
            cur = be if tp1 else stop0
            if (d > 0 and mlow[k] <= cur) or (d < 0 and mhig[k] >= cur):
                for x in range(3):
                    if alive[x]:
                        r += ((cur - entry) * d - cost) / risk; alive[x] = False
                break
            for x in range(3):
                if alive[x] and ((d > 0 and mhig[k] >= tgt[x]) or (d < 0 and mlow[k] <= tgt[x])):
                    r += ((tgt[x] - entry) * d - cost) / risk
                    alive[x] = False
                    if x == 0: tp1 = True
            if not any(alive): break
            k += 1
        kx = min(k, j1 - 1, N_MIN - 1)
        if any(alive):
            cost = 0.5 * sp_in + 0.5 * (0.0 if free else spread_arr[kx])
            for x in range(3):
                if alive[x]:
                    r += ((mclo[kx] - entry) * d - cost) / risk
        return r, kx - j0 + 1, 0.5 * sp_in + 0.5 * (0.0 if free else spread_arr[kx])

    bull = np.concatenate([[False], (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])])
    bear = np.concatenate([[False], (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])])
    rows = []
    for i in range(max(VP_LB, 250) + 10, N):
        d = 1 if bull[i] else (-1 if bear[i] else 0)
        if d == 0: continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0: continue
        entry = c[i]
        raw_s = p_lo[i] if d > 0 else p_hi[i]
        if not np.isfinite(raw_s): raw_s = f_lo[i] if d > 0 else f_hi[i]
        if not np.isfinite(raw_s): continue
        risk = abs(entry - raw_s)
        if risk <= 0: continue
        s1 = simulate(i, d, entry, risk)
        if s1 is None: break
        r, dur, cost = s1
        s0 = simulate(i, d, entry, risk, free=True)
        val, vah = value_area(i)
        vp = bool(np.isfinite(val) and vah > val and
                  ((c[i] > vah) if d > 0 else (c[i] < val)))
        rows.append(dict(bar=i, time=idx[i], r=r, r0=s0[0], dur=dur,
                         spread_r=cost / risk, risk_atr=risk / a, vp_ok=vp,
                         hour=idx[i].hour))
    S = pd.DataFrame(rows)
    out = {}
    for name, f in (("1 baseline", lambda x: np.ones(len(x), bool)),
                    ("2 +volume", lambda x: x.vp_ok.to_numpy())):
        sub = S[f(S)].reset_index(drop=True)
        take, busy = [], -1
        for b_, du in zip(sub.bar.to_numpy(), sub.dur.to_numpy()):
            if b_ > busy: take.append(True); busy = b_ + int(np.ceil(du / TF))
            else:         take.append(False)
        out[name] = sub[np.array(take)] if len(sub) else sub
    return len(S), out

# ---------------------------------------------------------------------------
# SWEEP
# ---------------------------------------------------------------------------
RES = {}
for tfs in TIMEFRAMES:
    n, parts = run_tf(tfs, msp)
    RES[tfs] = parts
    print(f"{tfs}: {n:,} crosses ({n/DAYS:.1f}/day)")

print("\n" + "=" * 96)
print(f"TIMEFRAME SWEEP    spread: {SPREAD_SOURCE}")
print("=" * 96)
print(f"{'tf':<8}{'part':<13}{'n':>6}{'n/day':>7}{'spread/R':>10}{'NET E':>9}"
      f"{'t':>7}{'GROSS E':>9}{'G t':>7}{'NET IS':>9}{'NET OOS':>9}")
for tfs in TIMEFRAMES:
    lab = tfs
    for name in ("1 baseline", "2 +volume"):
        d = RES[tfs][name]
        n, e, t, _ = stat(d["r"]) if len(d) else (0, 0, 0, 0)
        if n < 2:
            print(f"{lab:<8}{name:<13}{n:>6}   too few"); lab = ""; continue
        _, e0, t0, _ = stat(d["r0"])
        _, ei, _, _ = stat(d[d.time < CUT]["r"])
        _, eo, _, _ = stat(d[d.time >= CUT]["r"])
        print(f"{lab:<8}{name:<13}{n:>6}{n/DAYS:>7.2f}{d.spread_r.mean():>10.4f}"
              f"{e:>+9.4f}{t:>+7.2f}{e0:>+9.4f}{t0:>+7.2f}{ei:>+9.4f}{eo:>+9.4f}")
        lab = ""
    print()

print("=" * 96)
print("MONOTONICITY   part 2 across timeframes")
print(f"{'tf':<8}{'spread/R':>10}{'NET E':>10}{'GROSS E':>10}{'SE':>10}{'n':>7}")
ch = []
for tfs in TIMEFRAMES:
    d = RES[tfs]["2 +volume"]
    if len(d) < 2: continue
    _, e, _, _ = stat(d["r"]); _, e0, _, _ = stat(d["r0"])
    se = d["r0"].std(ddof=1) / math.sqrt(len(d))
    ch.append((tfs, d.spread_r.mean(), e, e0, se, len(d)))
    print(f"{tfs:<8}{ch[-1][1]:>10.4f}{e:>+10.4f}{e0:>+10.4f}{se:>10.4f}{len(d):>7}")
if len(ch) >= 2:
    sp_f = all(ch[i][1] > ch[i+1][1] for i in range(len(ch)-1))
    nt_r = all(ch[i][2] < ch[i+1][2] for i in range(len(ch)-1))
    hi, lo = max(ch, key=lambda x: x[3]), min(ch, key=lambda x: x[3])
    z = (hi[3]-lo[3]) / math.sqrt(hi[4]**2 + lo[4]**2)
    best = hi
    gz = best[3]/best[4] if best[4] > 0 else 0
    print(f"\n  spread/R falls with timeframe : {'YES' if sp_f else 'NO'}")
    print(f"  NET rises with timeframe      : {'YES' if nt_r else 'NO'}")
    print(f"  GROSS stays flat              : {'YES' if z < 2 else 'NO'}"
          f"   ({z:.1f} combined SE)")
    print(f"  GROSS is positive             : "
          f"{'YES' if best[3] > 0 and gz > 2 else 'NO'}   "
          f"(best {best[0]}: {best[3]:+.4f} at {gz:+.1f} SE)")
    print("\n  The first three only say the cost mechanism works. A driftless")
    print("  random walk passes all three and still loses everywhere, because")
    print("  there was nothing to make cheaper. The fourth is the one that")
    print("  says an edge exists at all.")
print("=" * 96)

# ---------------------------------------------------------------------------
# WHAT THE FLAT ASSUMPTION COST US
# ---------------------------------------------------------------------------
if SPREAD_SOURCE.startswith("REAL"):
    print("\nRe-running M5 on the flat 0.7525 every earlier backtest assumed,")
    print("to see how much that one number was moving the answer.")
    _, flat = run_tf("5min", np.full(N_MIN, FLAT_SPREAD))
    for name in ("1 baseline", "2 +volume"):
        a, b = RES["5min"][name], flat[name]
        if len(a) < 2 or len(b) < 2: continue
        _, ea, _, _ = stat(a["r"]); _, eb, _, _ = stat(b["r"])
        print(f"  {name:<13} real {ea:+.4f}   flat {eb:+.4f}   "
              f"difference {ea-eb:+.4f} R per signal")
