# ============================================================================
# DOBBY 3-LEG  -  TUNING CELL   (QuantConnect *Research* notebook)
#
# Self-contained. Paste into a fresh cell and run. 2025 onward only.
#
# WHY A CELL AND NOT A BACKTEST
#   Tuning means running the same system dozens of times. A LEAN backtest per
#   configuration takes minutes; here the minute data is loaded once and every
#   configuration is replayed over it in seconds.
#
# THE HONEST STRUCTURE, BUILT IN
#   Sweeping parameters over one sample and keeping the winner is how noise
#   gets fitted. So the sample is split before anything is measured:
#
#       IN SAMPLE   2025-01-01 .. 2025-12-31   <- tune here, look freely
#       OUT SAMPLE  2026-01-01 .. 2026-09-10   <- verify ONCE, do not tune
#
#   Both are printed side by side. A configuration that is strong in-sample and
#   dead out-of-sample was fitted, not found. Read the OOS column only after
#   you have committed to a configuration from the IS column.
#
#   The multiple-testing threshold is printed too: testing K configurations
#   raises the t needed for the best one to mean anything.
#
# THREE IMPLEMENTATION DETAILS THAT HAVE CHANGED RESULTS BEFORE
#   1. Exits resolve on MINUTE bars. Resolving on the 5-minute signal bar
#      inflated earlier work by +0.06R at 1.5R and +0.20R at 3R.
#   2. The 5-minute -> minute mapping starts at the FIRST minute of the NEXT
#      5-minute bar. pandas labels a resampled bin by its left edge; searching
#      that label into the minute index lands inside the signal bar itself,
#      which is a look-ahead. That bug once lifted a win rate to 79.8%.
#   3. When a minute bar could have hit both the stop and a target, the stop is
#      taken. Pessimistic, and the safe direction to be wrong in.
#
# R IS SCALE-FREE HERE
#   Quantity is not modelled at all. Every leg risks exactly 1R by definition,
#   which is what constant-money sizing achieves in the live build. So no
#   account size, lot size or cent conversion can distort these numbers.
# ============================================================================

import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from statistics import NormalDist

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
START   = datetime(2025, 1,  1)
IS_END  = datetime(2026, 1,  1)     # in-sample / out-of-sample boundary
END     = datetime(2026, 9, 10)

# Cost assumption, in price units, charged once per leg round trip.
# 0.7525 = OANDA's measured 2023-2026 mean for gold.
# 0.26   = what the TradingView build assumed. 2.9x optimistic.
SPREAD  = 0.7525

qb  = QuantBook()
SYM = qb.add_cfd("XAUUSD", Resolution.MINUTE, Market.OANDA).symbol

# ---------------------------------------------------------------------------
# LOAD  (quarterly chunks, float32, to stay inside free-tier memory)
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
            if len(cols) == 4:
                frames.append(pd.DataFrame(cols, index=h.index))
        del h
        cur = nxt
    if not frames:
        raise RuntimeError("no history returned - check the symbol and date range")
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated(keep="first")]

minute = load_minute(SYM, START, END)
print(f"minute bars {len(minute):,}   {minute.index[0]}  ->  {minute.index[-1]}")

OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}
m5  = minute.resample("5min").agg(OHLC).dropna()
m15 = minute.resample("15min").agg(OHLC).dropna()
print(f"5-minute bars {len(m5):,}    15-minute bars {len(m15):,}")

# Numpy views for the inner loop.
mi   = minute.index.values
mlow = minute["low"].to_numpy(np.float64)
mhig = minute["high"].to_numpy(np.float64)
mclo = minute["close"].to_numpy(np.float64)
N_MIN = len(mi)

# For each 5-minute bar, the first minute of the NEXT 5-minute bar. Exits may
# only be scanned from there: anything earlier is inside the signal bar.
next_bar_start = (m5.index + pd.Timedelta("5min")).values
J0 = np.searchsorted(mi, next_bar_start, side="left")

m5_close = m5["close"].to_numpy(np.float64)
m5_low   = m5["low"].to_numpy(np.float64)
m5_high  = m5["high"].to_numpy(np.float64)
m5_index = m5.index

# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------
def wilder_atr(df, n):
    h, l, c = df["high"].astype("float64"), df["low"].astype("float64"), df["close"].astype("float64")
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()

def pivot_available(series, left, right, is_low):
    """The most recent confirmed pivot, as known at each bar. A pivot with
    `right` bars to its right is only confirmed `right` bars later, so the
    value is placed at the confirmation bar and forward-filled."""
    s = series.astype("float64").reset_index(drop=True)
    if is_low:
        ok = (s < s.rolling(left).min().shift(1)) & (s < s.rolling(right).min().shift(-right))
    else:
        ok = (s > s.rolling(left).max().shift(1)) & (s > s.rolling(right).max().shift(-right))
    return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(right).ffill().to_numpy()

# The 15-minute trend EMA, made available without look-ahead: shift(1) is
# Pine's [1], and the label shift reflects that a bar's value is not known
# until the bar has closed.
def trend_on_m5(length):
    e = m15["close"].astype("float64").ewm(span=length, adjust=False).mean().shift(1)
    e.index = e.index + pd.Timedelta("15min")
    return e.reindex(m5_index, method="ffill").to_numpy()

# Mean price drift per minute across the whole sample, for the drift-adjusted
# column. Gold rose hard over this window and a long-only rule inherits that.
DRIFT_PER_MIN = (mclo[-1] - mclo[0]) / N_MIN

# ---------------------------------------------------------------------------
# THE SYSTEM
# ---------------------------------------------------------------------------
DEFAULTS = dict(
    fast=9, slow=21, trend=50, atr=14,
    pivot_left=5, pivot_right=5, fallback=10,
    min_risk_atr=0.30, max_risk_atr=3.00,
    tp=(1.0, 2.0, 3.0),
    hold_bars=120,
    trend_filter=True,
    longs=True, shorts=True,
    be_after_tp1=True,
)

def run(**over):
    cfg = dict(DEFAULTS); cfg.update(over)
    n5 = len(m5)

    c5 = pd.Series(m5_close)
    fast = c5.ewm(span=cfg["fast"], adjust=False).mean().to_numpy()
    slow = c5.ewm(span=cfg["slow"], adjust=False).mean().to_numpy()
    atr  = wilder_atr(m5, cfg["atr"]).to_numpy()
    tema = trend_on_m5(cfg["trend"])

    piv_lo = pivot_available(m5["low"],  cfg["pivot_left"], cfg["pivot_right"], True)
    piv_hi = pivot_available(m5["high"], cfg["pivot_left"], cfg["pivot_right"], False)
    fb_lo  = m5["low"].rolling(cfg["fallback"]).min().to_numpy()
    fb_hi  = m5["high"].rolling(cfg["fallback"]).max().to_numpy()

    bull = (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])
    bear = (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])
    bull = np.concatenate([[False], bull])
    bear = np.concatenate([[False], bear])

    tp = cfg["tp"]
    hold_min = cfg["hold_bars"] * 5
    warm = max(cfg["slow"], cfg["atr"], cfg["fallback"], cfg["pivot_left"] + cfg["pivot_right"]) + 5

    rows, skipped_band = [], 0
    busy_until = -1

    for i in range(warm, n5):
        if i <= busy_until:
            continue
        d = 1 if bull[i] else (-1 if bear[i] else 0)
        if d == 0:
            continue
        if d > 0 and not cfg["longs"]:
            continue
        if d < 0 and not cfg["shorts"]:
            continue

        entry = m5_close[i]
        if cfg["trend_filter"]:
            t = tema[i]
            if not np.isfinite(t):
                continue
            if (d > 0 and entry <= t) or (d < 0 and entry >= t):
                continue

        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        raw = piv_lo[i] if d > 0 else piv_hi[i]
        if not np.isfinite(raw):
            raw = fb_lo[i] if d > 0 else fb_hi[i]
        if not np.isfinite(raw):
            continue
        risk = abs(entry - raw)
        if risk < cfg["min_risk_atr"] * a or risk > cfg["max_risk_atr"] * a:
            skipped_band += 1
            continue

        stop0 = entry - d * risk
        be    = entry + d * SPREAD
        tgt   = [entry + d * risk * m for m in tp]

        j0 = J0[i]
        if j0 >= N_MIN:
            break
        j1 = min(j0 + hold_min, N_MIN)

        alive = [True, True, True]
        tp1 = False
        r = 0.0
        k = j0
        while k < j1:
            cur_stop = be if (tp1 and cfg["be_after_tp1"]) else stop0
            # Stop is tested first: when a minute bar could have hit both, the
            # stop is assumed. Pessimistic by design.
            if (d > 0 and mlow[k] <= cur_stop) or (d < 0 and mhig[k] >= cur_stop):
                for x in range(3):
                    if alive[x]:
                        r += ((cur_stop - entry) * d - SPREAD) / risk
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

        k_exit = min(k, j1 - 1, N_MIN - 1)
        if any(alive):                      # time stop, at the last bar in window
            px = mclo[k_exit]
            for x in range(3):
                if alive[x]:
                    r += ((px - entry) * d - SPREAD) / risk

        dur = max(1, k_exit - j0 + 1)
        drift_r = d * DRIFT_PER_MIN * dur / risk
        rows.append((m5_index[i], d, r, r - drift_r))
        busy_until = i + int(np.ceil(dur / 5.0))

    out = pd.DataFrame(rows, columns=["time", "dir", "r", "r_nodrift"])
    out.attrs["skipped_band"] = skipped_band
    return out

# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------
def stats(r):
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 2:
        return dict(n=n, e=float("nan"), sd=float("nan"), t=float("nan"),
                    win=float("nan"), need=float("inf"), total=float(r.sum()) if n else 0.0)
    e  = r.mean()
    sd = r.std(ddof=1)
    t  = e / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    need = (2.0 * sd / e) ** 2 if e != 0 else float("inf")
    return dict(n=n, e=e, sd=sd, t=t, win=100.0 * (r > 0).mean(), need=need,
                total=r.sum())

def split(df):
    return df[df["time"] < IS_END], df[df["time"] >= IS_END]

HDR = (f"{'configuration':<34}{'IS n':>6}{'IS E':>9}{'IS t':>7}"
       f"{'OOS n':>7}{'OOS E':>9}{'OOS t':>7}{'ND t':>7}")

def line(label, df):
    i, o = split(df)
    si, so = stats(i["r"]), stats(o["r"])
    snd = stats(o["r_nodrift"])
    return (f"{label:<34}{si['n']:>6}{si['e']:>+9.4f}{si['t']:>+7.2f}"
            f"{so['n']:>7}{so['e']:>+9.4f}{so['t']:>+7.2f}{snd['t']:>+7.2f}")

# ---------------------------------------------------------------------------
# 1. BASELINE  -  exactly what the TradingView build runs
# ---------------------------------------------------------------------------
print("\n" + "=" * 86)
print(f"BASELINE   spread {SPREAD}   IS {START:%Y-%m-%d}..{IS_END:%Y-%m-%d}   "
      f"OOS {IS_END:%Y-%m-%d}..{END:%Y-%m-%d}")
print("ND t = out-of-sample t after removing gold's drift over each hold")
print("=" * 86)
print(HDR)
base = run()
print(line("EMA 9/21 + trend filter (both)", base))
print(line("  long only",  base[base["dir"] > 0]))
print(line("  short only", base[base["dir"] < 0]))
b_is, b_oos = split(base)
print(f"\nsignals {len(base)}   skipped by risk band {base.attrs['skipped_band']}   "
      f"total {b_is['r'].sum():+.1f}R in-sample, {b_oos['r'].sum():+.1f}R out")

# ---------------------------------------------------------------------------
# 2. SWEEP  -  one axis at a time, so a result can be attributed
# ---------------------------------------------------------------------------
GRID = []
for f, s in ((5, 13), (9, 21), (13, 34), (21, 55)):
    GRID.append((f"EMA {f}/{s}", dict(fast=f, slow=s)))
GRID += [
    ("no trend filter",        dict(trend_filter=False)),
    ("trend EMA 100",          dict(trend=100)),
    ("trend EMA 200",          dict(trend=200)),
    ("risk band 0.5-2.0 ATR",  dict(min_risk_atr=0.5, max_risk_atr=2.0)),
    ("risk band 0.8-1.5 ATR",  dict(min_risk_atr=0.8, max_risk_atr=1.5)),
    ("ladder 1/2/4",           dict(tp=(1.0, 2.0, 4.0))),
    ("ladder 1/3/6",           dict(tp=(1.0, 3.0, 6.0))),
    ("ladder 1.5/3/6",         dict(tp=(1.5, 3.0, 6.0))),
    ("hold 48 bars",           dict(hold_bars=48)),
    ("hold 240 bars",          dict(hold_bars=240)),
    ("no break-even move",     dict(be_after_tp1=False)),
]

print("\n" + "=" * 86)
print(f"SWEEP   {len(GRID)} configurations, one axis changed at a time")
print("=" * 86)
print(HDR)
results = {}
for label, over in GRID:
    df = run(**over)
    results[label] = df
    print(line(label, df))

K = len(GRID) + 1
BAR = NormalDist().inv_cdf(1.0 - 0.025 / K)     # two-sided, family-wise 5%
print(f"\nMULTIPLE TESTING: {K} configurations were tested, so the best of them")
print(f"is the maximum of {K} draws and clears a higher bar than a lone test.")
print(f"Family-wise 5% over {K} tests (Bonferroni, two-sided): t > {BAR:.2f}")
print("A configuration that only clears the plain 2.0 has not cleared anything.")
print("The out-of-sample column is exempt only if you fixed the configuration")
print("from the in-sample column BEFORE reading it. Otherwise it is a test too.")

# ---------------------------------------------------------------------------
# 3. SPREAD SENSITIVITY  -  on the baseline, out-of-sample
# ---------------------------------------------------------------------------
print("\n" + "=" * 86)
print("SPREAD SENSITIVITY (baseline, out-of-sample)")
print("=" * 86)
print(f"{'spread':<12}{'n':>6}{'E':>10}{'t':>8}{'total R':>10}")
for sp in (0.26, 0.40, 0.50, 0.7525, 1.00, 1.50):
    SPREAD_SAVE = SPREAD
    SPREAD = sp
    _, o = split(run())
    st = stats(o["r"])
    print(f"{sp:<12}{st['n']:>6}{st['e']:>+10.4f}{st['t']:>+8.2f}{st['total']:>+10.1f}")
    SPREAD = SPREAD_SAVE

# ---------------------------------------------------------------------------
# 4. VERDICT
# ---------------------------------------------------------------------------
bh = 100.0 * (mclo[-1] / mclo[0] - 1.0)
print("\n" + "=" * 86)
print(f"buy and hold over the whole window: {bh:+.1f}%")
print("An edge means: positive E, t over the multiple-testing bar, on the SAME")
print("configuration in both columns, and surviving the drift-adjusted column")
print("on whichever side you intend to trade. Anything less is a fitted curve.")
print("=" * 86)
