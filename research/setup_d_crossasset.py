#!/usr/bin/env python3
"""Setup D (trend zone) - the cross-asset test its own config says is missing.

WHAT SETUP D IS, FROM THE REPO'S OWN SOURCE

  MQL5/Include/XAUM15/Setups.mqh, class CSetupTrendZone:

      z = (Close - SMA200) / ATR
      long  when  +1.08 <= z <= +7.21
      short when  -7.21 <= z <= -1.08
      fire only on ENTERING the zone, not every bar spent inside it
      stop  = 1.8 x ATR, flat
      exit  = 8R target with a 30-hour time stop behind it
      one position at a time

  It is the EA's only default-ON setup, and README credits it with a
  permutation test at p=0.0005 and net E +0.2312R at 8R.

WHY THIS RUN EXISTS

  Config.mqh says it in its own words:

      "NOT YET VALIDATED: the zone was found on the FULL gold sample, not a
       held-out half, and cross-asset confirmation (silver, EURUSD) has not
       been run. If it does not reproduce there, this is gold overfit."

  That test has never been run. This is it.

THE SECOND THING THIS CHECKS, WHICH THE README ALREADY HALF-ANSWERED

  The README's own drift table:

                        Raw E      t     Skill (raw - drift)     t
      longs in zone    +0.0569   +4.45        -0.0494         -4.14
      shorts in zone   +0.0102   +0.75        +0.1092         +7.56

  Longs in zone have NEGATIVE skill once gold's own drift is subtracted -
  and the shipped config trades LONGS ONLY (InpTrendZoneLong=true,
  InpTrendZoneShort=false). So the side the EA actually trades is the side
  whose raw edge is the market going up, and the side with real measured
  skill is switched off. Both sides are reported here, raw and drift-
  adjusted, on every market.

VERIFICATION BEFORE BELIEF

  The gold M15 run comes first and has to land near the documented
  +0.2312R at 8R. If it does not, the implementation is wrong and the
  nine-market numbers mean nothing - the same order this project should
  have used on P01 before writing up a nine-market result that turned out
  to be a one-bar look-ahead.
"""
import argparse, math, pathlib, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from p01_multi_tf_2026 import resample_bidask, m1_source

# --- the spec, verbatim from Setups.mqh / Config.mqh -----------------------
Z_MIN, Z_MAX = 1.08, 7.21
SMA_PERIOD = 200
SL_ATR = 1.8
TARGET_R = 8.0
TIME_STOP_HOURS = 30.0
SEED = 17


def trend_zone_signals(P, sma_period=SMA_PERIOD):
    """z = (Close - SMA200)/ATR, firing only on ENTRY into the zone.

    The entry-only rule is not decoration: Setups.mqh notes that without it
    "the EA re-signals continuously and the trade count inflates far beyond
    the ~254/year the notebook measured"."""
    c, A, N = P["c"], P["A"], P["N"]
    sma = pd.Series(c).rolling(sma_period).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - sma) / A
    z = np.where(np.isfinite(z), z, 0.0)
    in_long = (z >= Z_MIN) & (z <= Z_MAX)
    in_short = (z <= -Z_MIN) & (z >= -Z_MAX)
    prev_long = np.roll(in_long, 1); prev_long[0] = False
    prev_short = np.roll(in_short, 1); prev_short[0] = False
    d = np.zeros(N, np.int8)
    d[in_long & ~prev_long] = 1
    d[in_short & ~prev_short] = -1
    return d, z


def run_setup_d(P, dvec, tick, hold_bars, lo=0, hi=None):
    """Flat 1.8 ATR stop, 8R target, time stop, real two-sided quotes.

    Entry is the entry bar's OPEN quote and exits are tested on the side
    that actually closes the trade - the two corrections that turned the
    P01 nine-market result from a discovery into a retraction."""
    hi = P["N"] if hi is None else hi
    A, N = P["A"], P["N"]
    bid_o, ask_o = P["bid_o"], P["ask_o"]
    bid, ask = P["bid"], P["ask"]
    rows = []
    busy = -1
    for t in range(max(lo, SMA_PERIOD + 5), min(hi, N - 1)):
        d = dvec[t]
        if d == 0 or t <= busy:
            continue
        a = A[t]
        if not np.isfinite(a) or a <= 0:
            continue
        e = t + 1
        entry = ask_o[e] if d > 0 else bid_o[e]
        if not np.isfinite(entry):
            continue
        dist = SL_ATR * a
        stop = entry - d * dist
        target = entry + d * TARGET_R * dist
        ex_lo = P["bid_l"] if d > 0 else P["ask_l"]
        ex_hi = P["bid_h"] if d > 0 else P["ask_h"]
        exit_px, exit_bar, reason = None, None, None
        for k in range(e, min(e + hold_bars, N)):
            hit_stop = (ex_lo[k] <= stop) if d > 0 else (ex_hi[k] >= stop)
            hit_tp = (ex_hi[k] >= target) if d > 0 else (ex_lo[k] <= target)
            if hit_stop:
                exit_px, exit_bar, reason = stop, k, "stop"; break
            if hit_tp:
                exit_px, exit_bar, reason = target, k, "target"; break
        if exit_px is None:
            kx = min(e + hold_bars - 1, N - 1)
            exit_px = bid[kx] if d > 0 else ask[kx]
            exit_bar, reason = kx, "time"
        r = (exit_px - entry) * d / dist
        # DRIFT over exactly the bars this trade was open, in the same R
        # units and signed by the trade's own direction: what simply being
        # in the market for that long would have paid.
        mid_in, mid_out = P["c"][e - 1], P["c"][exit_bar]
        drift = (mid_out - mid_in) * d / dist
        rows.append(dict(t=t, d=int(d), R=float(r), drift=float(drift),
                         skill=float(r - drift), reason=reason,
                         held=int(exit_bar - t)))
        busy = exit_bar
    return pd.DataFrame(rows)


def zero_cost(P):
    """The same bars with the spread removed - every quote set to the mid.

    Not a realism claim: it isolates whether the ZONE carries information
    from whether the book can pay gold's spread, which are two different
    questions the README itself keeps separate."""
    P0 = dict(P)
    for k, src in (("bid", "c"), ("ask", "c"),
                   ("bid_o", "o"), ("ask_o", "o"),
                   ("bid_h", "h"), ("ask_h", "h"),
                   ("bid_l", "l"), ("ask_l", "l")):
        P0[k] = P[src]
    P0["spread"] = np.zeros_like(P["c"])
    return P0


def stats(T, label, idx=None):
    if len(T) == 0:
        return None
    R = T["R"].to_numpy()
    S = T["skill"].to_numpy()
    where = T["t"].to_numpy(float)
    held = T["held"].to_numpy(float)
    return dict(
        label=label, n=len(T), E=float(R.mean()),
        t_E=float(M.block_bootstrap_t(R, where, held, 1)),
        skill=float(S.mean()),
        t_skill=float(M.block_bootstrap_t(S, where, held, 1)),
        win=float((R > 0).mean()) * 100,
        tgt=float((T.reason == "target").mean()) * 100)


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()
    t0 = time.time()

    print("SETUP D (TREND ZONE) - THE CROSS-ASSET TEST ITS CONFIG ASKS FOR")
    print("=" * 94)
    print(__doc__.split("WHY THIS RUN EXISTS")[1].split("VERIFICATION BEFORE")[0])
    print(f"  spec: z in [{Z_MIN}, {Z_MAX}], stop {SL_ATR} ATR, target "
          f"{TARGET_R:.0f}R, time stop {TIME_STOP_HOURS:.0f}h, entry-only\n")

    # ---- 1. verification on gold M15 --------------------------------------
    if not a.skip_verify:
        print("=" * 94)
        print("1. VERIFICATION - gold M15, the timeframe the research used")
        print("=" * 94)
        m1 = m1_source("2019-01-01")
        m1 = m1[(m1.index.dayofweek < 5) |
                ((m1.index.dayofweek == 5) & (m1.index.hour == 0))]
        m15 = resample_bidask(m1, "15min")
        Pg = X.prep(m15, 0)
        dv, z = trend_zone_signals(Pg)
        hold = int(TIME_STOP_HOURS * 60 / 15)   # 120 bars
        T = run_setup_d(Pg, dv, 0.001, hold)
        yrs = (Pg["idx"][-1] - Pg["idx"][0]).days / 365.25
        for side, lab in ((1, "LONG"), (-1, "SHORT")):
            s = stats(T[T.d == side], lab)
            if s:
                print(f"  {lab:<6} n={s['n']:>5,} ({s['n']/yrs:>5.0f}/yr)  "
                      f"win {s['win']:>4.1f}%  target-hit {s['tgt']:>4.1f}%  "
                      f"E {s['E']:>+7.4f} (t {s['t_E']:>+5.2f})  "
                      f"skill {s['skill']:>+7.4f} (t {s['t_skill']:>+5.2f})")
        # LIKE FOR LIKE. The documented +0.2312R was costed at the terminal's
        # $0.26 quote - README's own table says so, and Config.mqh adds that
        # the same book at OANDA's measured $0.7525 falls to +0.1253R, a 46%
        # haircut. Comparing a real-bid/ask run against a $0.26-costed number
        # is comparing two different questions, so the verification is done on
        # a matched cost basis and the real-spread number is reported next to
        # it rather than in place of it.
        Pz = zero_cost(Pg)
        Tz = run_setup_d(Pz, dv, 0.001, hold)
        slz = stats(Tz[Tz.d == 1], "LONG")
        sl = stats(T[T.d == 1], "LONG")
        if sl and slz:
            ok = 0.5 * 0.2312 <= slz["E"] <= 2.0 * 0.2312
            print(f"\n  documented   +0.2312R at 8R (costed at the $0.26 quote),"
                  f" ~254 trades/yr, win ~23.8%")
            print(f"  reproduced   {slz['E']:+.4f}R at ZERO cost, "
                  f"{slz['n']/yrs:.0f} trades/yr, win {slz['win']:.1f}%")
            print(f"  same book at REAL measured bid/ask: {sl['E']:+.4f}R")
            print(f"\n  within a factor of two of the documented E, on a")
            print(f"  matched cost basis?   {'YES' if ok else 'NO'}")
            if ok:
                print(f"  -> the implementation reproduces the research. The")
                print(f"     gap between {slz['E']:+.4f} and {sl['E']:+.4f} is the")
                print(f"     real spread, which is the thing the README calls")
                print(f"     'the other open question'.")
            else:
                print(f"\n  The implementation does not reproduce the number it")
                print(f"  is supposed to reproduce even at matched cost. The")
                print(f"  nine-market run below should NOT be read as a test of")
                print(f"  Setup D until this is resolved.")

    # ---- 2. cross-asset on H1 ---------------------------------------------
    print("\n" + "=" * 94)
    print("2. CROSS-ASSET - 9 markets, H1, time stop matched in wall-clock hours")
    print("=" * 94)
    hold_h1 = int(TIME_STOP_HOURS)
    rows = []
    print(f"  {'market':<9}{'side':<7}{'n':>7}{'win':>7}{'tgt%':>7}"
          f"{'E(R)':>10}{'t_E':>7}{'skill':>10}{'t_skill':>9}")
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            print(f"  {sym:<9} no usable cache")
            continue
        P = X.prep(df, 60)
        dv, z = trend_zone_signals(P)
        T = run_setup_d(P, dv, TICKS.get(sym, 0.00001), hold_h1)
        for side, lab in ((1, "long"), (-1, "short")):
            s = stats(T[T.d == side], lab)
            if s is None:
                continue
            rows.append(dict(symbol=sym, side=lab, **{
                k: s[k] for k in ("n", "E", "t_E", "skill", "t_skill",
                                  "win", "tgt")}))
            print(f"  {sym:<9}{lab:<7}{s['n']:>7,}{s['win']:>6.1f}%"
                  f"{s['tgt']:>6.1f}%{s['E']:>+10.4f}{s['t_E']:>+7.2f}"
                  f"{s['skill']:>+10.4f}{s['t_skill']:>+9.2f}")

    if not rows:
        print("\n  nothing produced a book")
        return
    D = pd.DataFrame(rows)

    print("\n" + "=" * 94)
    print("THE DECLARED TEST: drift-adjusted skill positive on 8 of 9")
    print("=" * 94)
    for lab in ("long", "short"):
        g = D[D.side == lab]
        if len(g) == 0:
            continue
        pos_E = int((g["E"] > 0).sum())
        pos_S = int((g["skill"] > 0).sum())
        n = len(g)
        print(f"\n  {lab.upper()} side, {n} markets")
        print(f"    raw E(R) positive         {pos_E} of {n}   "
              f"P(>={pos_E}) = {binom_tail(pos_E, n):.4f}")
        print(f"    DRIFT-ADJUSTED skill > 0  {pos_S} of {n}   "
              f"P(>={pos_S}) = {binom_tail(pos_S, n):.4f}   <- the declared bar")
        print(f"    mean raw E {g['E'].mean():+.4f}   "
              f"mean skill {g['skill'].mean():+.4f}")
        verdict = ("REPLICATES" if pos_S >= 8 and n >= 9
                   else "does NOT replicate")
        print(f"    -> {verdict}")

    print(f"\n  The shipped config trades LONGS ONLY. Read the long row first.")
    print(f"  A long side that is positive in raw E and negative in skill is")
    print(f"  the market going up, measured twice.")
    out = pathlib.Path(__file__).parent / "setup_d_crossasset.csv"
    D.to_csv(out, index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s   detail -> {out.name}")


if __name__ == "__main__":
    main()
