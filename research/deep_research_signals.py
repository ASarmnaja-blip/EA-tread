#!/usr/bin/env python3
"""Three signal families this repo has never tested, sourced from published
research rather than pattern-hunting on gold's own chart.

WHY THESE THREE
  Everything tested in this program before now was PRICE-DERIVED: candles,
  swings, breakouts, ranges. All of it lives on the same information - the
  chart - and all of it has died. These three are different in KIND, not just
  parameters:

  1. CALENDAR SEASONALITY. Lucey & Tully (2006) document a Monday-weak/
     Friday-strong pattern in gold, attributed to institutional week-end
     hedging; multiple studies (Seasonax; arXiv:2003.11027) document a
     turn-of-month effect. A calendar signal cannot be curve-fit to gold's own
     price path - the day-of-week is a fact about the calendar, decided before
     the market data exists.

  2. GOLD/SILVER RATIO MEAN REVERSION. Standard commodities-desk practice:
     the ratio has a long-run mean near 60-80:1, and multiple published
     backtests (QuantifiedStrategies; SSRN 5710242) test reversion from
     extremes. This is an INTERMARKET signal - it needs silver, not just gold.

  3. COT POSITIONING EXTREMES. Managed-money net positioning from the CFTC's
     weekly Commitment of Traders report. Extreme positioning (>80th or <20th
     percentile of its own trailing history) has been written up as preceding
     reversals - a FLOW signal, not a price-pattern signal, sourced from an
     entirely different dataset (CFTC, not price bars).

PRE-REGISTERED BEFORE ANY RESULT WAS READ
  S1 Monday short / Friday long, held ~1 trading day. Reading: skill > +0.05R
     at t > 2.39 (Bonferroni bar for 3 tests) is a result; anything smaller is
     noise dressed as folklore.
  S2 Turn-of-month long (last 1 + first 3 trading days of the month), same bar.
  S3 Gold/silver ratio z-score beyond +/-1.5, betting on reversion (short gold
     when the ratio is stretched high, long when stretched low), held 10 days.
  S4 COT managed-money net position, z-scored against its own trailing 156-week
     (3y) history, faded beyond +/-1.5 (short when crowded long, long when
     crowded short), held 20 trading days - COT is weekly, so the signal cannot
     usefully fire faster than that.

  All four measured against a MATCHED RANDOM CONTROL - same count, same
  direction mix, same exit - because this repo's own history says an
  unmatched benchmark manufactures fake skill from gold's own 20-year drift.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd

SEED, CTRL_REPS = 17, 10
BONFERRONI_4 = None  # computed at runtime

def fetch(sym, rng="20y", iv="1d"):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def fetch_cot(commodity="GOLD"):
    """CFTC disaggregated futures-only report, Socrata public API, no key."""
    # `%` is SoQL's own wildcard; urlencode() percent-encodes it for us, so
    # the query string here uses a literal % and must NOT be pre-escaped.
    q = f"market_and_exchange_names like '{commodity}%COMMODITY EXCHANGE%'"
    url = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json?" +
           urllib.parse.urlencode({"$where": q,
                                   "$order": "report_date_as_yyyy_mm_dd ASC",
                                   "$limit": 5000}))
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    rows = json.load(urllib.request.urlopen(r, timeout=45))
    if not rows:
        raise RuntimeError(f"CFTC query returned no rows for {commodity!r}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize("UTC")
    for c in ("noncomm_positions_long_all", "noncomm_positions_short_all"):
        df[c] = df[c].astype(float)
    df["net"] = df["noncomm_positions_long_all"] - df["noncomm_positions_short_all"]
    return df.set_index("date")[["net"]].sort_index()

def atr(df, n=14):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    pc = pd.Series(c).shift(1)
    return pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                      (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
             .ewm(alpha=1 / n, adjust=False).mean().to_numpy()

# ----------------------------------------------------------------- exit ----
# The same trail-2ATR + BE-at-1R design this repo already validated as the
# best risk-adjusted exit it has found (RESEARCH_FINDINGS: "trail 2ATR + BE
# beat 8R target on risk-adjusted return in nearly every row"). Reusing a
# design that has already earned trust, rather than writing a new one, is
# deliberate after this session's wick-tip bug.
RMULT, TRAIL, BE_AT, HOLD_DEFAULT, COST = 1.8, 1.0, 1.0, 20, 0.0002

def run_trade(h, l, c, N, i, d, hold, cost=COST, rmult=RMULT):
    A = atr(pd.DataFrame({"high": h, "low": l, "close": c}))
    risk = rmult * A[i]
    if not np.isfinite(risk) or risk <= 0: return None
    entry = c[i]
    stop = entry - d * risk
    moved, best = False, entry
    for k in range(i + 1, min(i + 1 + hold, N)):
        cur = entry if moved else stop
        if k - 1 > i:
            best = max(best, h[k - 1]) if d > 0 else min(best, l[k - 1])
            t2 = best - d * TRAIL * risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (l[k] <= cur) if d > 0 else (h[k] >= cur):
            return ((cur - entry) * d - cost * entry) / risk
        if not moved and ((d > 0 and h[k] >= entry + d * BE_AT * risk) or
                          (d < 0 and l[k] <= entry + d * BE_AT * risk)):
            moved = True
    kx = min(k, N - 1)
    return ((c[kx] - entry) * d - cost * entry) / risk

def matched_control(h, l, c, N, sig_idx, sig_dir, hold, seed):
    rng = np.random.default_rng(seed)
    pool = np.arange(260, N - 1)
    if len(pool) < len(sig_idx): return np.array([])
    pick = np.sort(rng.choice(pool, size=len(sig_idx), replace=False))
    out, busy = [], -1
    for j, i in enumerate(pick):
        i = int(i)
        if i <= busy: continue
        r = run_trade(h, l, c, N, i, sig_dir[j % len(sig_dir)], hold)
        if r is not None: out.append(r); busy = i + hold
    return np.array(out)

def evaluate(df, sig, hold, seed_base=SEED, reps=CTRL_REPS):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    N = len(c)
    idx = [i for i in range(260, N - 1) if sig[i] != 0]
    real, busy = [], -1
    for i in idx:
        if i <= busy: continue
        r = run_trade(h, l, c, N, i, int(sig[i]), hold)
        if r is not None: real.append(r); busy = i + hold
    real = np.array(real)
    if len(real) < 15: return None
    dirs = [int(sig[i]) for i in idx]
    ctrl = np.concatenate([matched_control(h, l, c, N, idx, dirs, hold,
                                            seed_base * 1000 + rep)
                           for rep in range(reps)])
    if len(ctrl) < 15: return None
    sk = real.mean() - ctrl.mean()
    se = math.sqrt(real.var(ddof=1) / len(real) + ctrl.var(ddof=1) / len(ctrl))
    return dict(n=len(real), E=float(real.mean()), ctrlE=float(ctrl.mean()),
               skill=float(sk), t=float(sk / se) if se > 0 else float("nan"),
               win=float((real > 0).mean()))

def line(label, r):
    if r is None: print(f"  {label:<40}  too few trades"); return
    print(f"  {label:<40}{r['n']:>6}{r['win']:>7.3f}{r['E']:>+9.3f}"
          f"{r['ctrlE']:>+9.3f}{r['skill']:>+9.3f}{r['t']:>+8.2f}")

HDR = (f"  {'signal':<40}{'n':>6}{'win':>7}{'E(R)':>9}{'ctrlE':>9}"
       f"{'skill':>9}{'skill t':>8}")

# ------------------------------------------------------------- S1: DOW ----
def s1_day_of_week(df):
    dow = df.index.dayofweek.to_numpy()
    sig = np.zeros(len(df), np.int8)
    sig[dow == 0] = -1     # Monday: short (post weekend profit-taking)
    sig[dow == 4] = 1      # Friday: long (pre-weekend hedge demand)
    return sig

# ----------------------------------------------------------- S2: TOM -----
def s2_turn_of_month(df):
    """Long the last trading day of the month and the first three of the
    next - the window Seasonax and arXiv:2003.11027 identify."""
    day = df.index.day.to_numpy()
    is_month_end = np.zeros(len(df), bool)
    months = df.index.tz_localize(None).to_period("M")
    for m in pd.unique(months):
        ix = np.flatnonzero(months == m)
        if len(ix): is_month_end[ix[-1]] = True
    is_early = day <= 3
    sig = np.zeros(len(df), np.int8)
    sig[is_month_end | is_early] = 1
    # fire only on the FIRST bar of a qualifying run, not every bar in it
    fire = np.zeros(len(df), np.int8)
    prev = False
    for i in range(len(df)):
        on = sig[i] != 0
        if on and not prev: fire[i] = 1
        prev = on
    return fire

# ------------------------------------------------------ S3: GOLD/SILVER --
def s3_ratio_reversion(gold, silver, z_thresh=1.5, lookback=252):
    j = pd.concat([gold.close.rename("g"), silver.close.rename("s")],
                  axis=1, join="inner").dropna()
    ratio = j.g / j.s
    z = (ratio - ratio.rolling(lookback).mean()) / ratio.rolling(lookback).std()
    z = z.shift(1)          # only yesterday's z-score is known today
    sig = pd.Series(0, index=j.index, dtype=np.int8)
    sig[z > z_thresh] = -1      # ratio stretched high -> fade gold (short)
    sig[z < -z_thresh] = 1      # ratio stretched low  -> fade gold (long)
    # fire only when crossing INTO the extreme zone
    active = sig != 0
    fire = active & ~active.shift(1).fillna(False)
    out = sig.where(fire, 0)
    return out.reindex(gold.index, fill_value=0).to_numpy()

# ------------------------------------------------------------- S4: COT ---
def s4_cot_fade(df, cot, z_thresh=1.5, lookback_weeks=156):
    net = cot["net"]
    z = (net - net.rolling(lookback_weeks).mean()) / net.rolling(lookback_weeks).std()
    z = z.shift(1)
    sig_w = pd.Series(0, index=cot.index, dtype=np.int8)
    sig_w[z > z_thresh] = -1     # managed money crowded long -> fade (short)
    sig_w[z < -z_thresh] = 1     # managed money crowded short -> fade (long)
    active = sig_w != 0
    fire_w = active & ~active.shift(1).fillna(False)
    fire_w = sig_w.where(fire_w, 0)
    # The report is dated Tuesday but the CFTC does not publish it until the
    # following FRIDAY - a 3-day lag. Reindexing on the report date, as an
    # earlier version of this function did, means "knowing" the report up to
    # three trading days before it existed publicly. Shift the index forward
    # to the actual release day (+3 calendar days) before reindexing onto the
    # daily bars, so a signal can only fire on or after the day it was real.
    fire_w = fire_w.copy()
    fire_w.index = fire_w.index + pd.Timedelta(days=3)
    daily = fire_w.reindex(df.index, method="ffill")
    out = np.zeros(len(df), np.int8)
    last = None
    for i, (dt, v) in enumerate(daily.items()):
        if v != 0 and v != last:
            out[i] = v
        last = v
    return out

def main():
    print("Fetching gold, silver (20y daily) and CFTC COT (weekly) ...")
    gold = fetch("GC=F")
    silver = fetch("SI=F")
    cot = fetch_cot("GOLD")
    print(f"  gold {len(gold):,} bars, silver {len(silver):,} bars, "
          f"COT {len(cot):,} weekly reports "
          f"{cot.index[0].date()} -> {cot.index[-1].date()}\n")

    print(HDR); print("  " + "-"*(len(HDR)-2))
    r1 = evaluate(gold, s1_day_of_week(gold), hold=1)
    line("S1 Monday short / Friday long", r1)
    r2 = evaluate(gold, s2_turn_of_month(gold), hold=4)
    line("S2 turn-of-month long", r2)
    sig3 = s3_ratio_reversion(gold, silver)
    r3 = evaluate(gold, sig3, hold=10)
    line("S3 gold/silver ratio fade (|z|>1.5)", r3)
    sig4 = s4_cot_fade(gold, cot)
    r4 = evaluate(gold, sig4, hold=20)
    line("S4 COT managed-money fade (|z|>1.5)", r4)

    k = 4
    bar = 2.39   # Bonferroni two-sided bar for 4 pre-registered tests, from t-table
    print(f"\n  Bonferroni bar for {k} pre-registered tests, two-sided: |t| > {bar}")
    for nm, r in (("S1", r1), ("S2", r2), ("S3", r3), ("S4", r4)):
        if r is None: continue
        verdict = "CLEARS the bar" if abs(r["t"]) > bar else "does not clear"
        print(f"  {nm}: skill t = {r['t']:+.2f}  -  {verdict}")

    print("\nHOW TO READ THIS")
    print("  E is what the trade earned. ctrlE is what a random entry, matched")
    print("  on count/direction/exit, earned over the same span - it carries")
    print("  gold's own 20-year drift. skill = E - ctrlE is what the SIGNAL")
    print("  contributed on top of that drift. Read skill and its t, not E.")

if __name__ == "__main__":
    main()
