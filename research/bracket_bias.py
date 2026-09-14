#!/usr/bin/env python3
"""How much does the EXIT cost, before any entry is chosen?

THE FINDING THAT PROMPTED THIS

  Random entry timing, run through this project's standard bracket at ZERO
  cost, loses 0.10R to 0.17R on real data. The same bracket on a random walk
  loses exactly the spread and nothing more, which is what the martingale
  guard has correctly reported for 828 hypotheses. A constant-volatility
  fixture cannot detect a volatility-clustering effect, so the guard was
  never going to catch this.

  That makes the exit the largest single term in every result this repo has
  produced, and the one term never examined.

THE PRINCIPLE THAT MAKES IT MEASURABLE

  A PURE TIME EXIT is unbiased by construction. Enter, wait N bars, leave -
  the expectancy is the mean forward return over N bars, which is the market's
  drift and nothing else. It cannot manufacture a loss.

  So the bias of any bracketed exit is simply

      E(bracket, random timing) - E(time exit, random timing)

  measured at zero cost, on the same bars, with the same random entries. No
  theory about stops is needed; the difference IS the penalty.

THE RULE THIS FILE MUST NOT BREAK

  The exit is chosen by the CONTROL's fairness alone - the design whose
  random-timing expectancy sits nearest zero. What the real entries do with
  each exit is computed only AFTER that choice is fixed, and is never an
  input to it. Choosing the exit that flatters the real entries would be a
  five-hypothesis search wearing a calibration's clothing, and would be the
  same error this project has made 828 times.
"""
import argparse
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal

SEED = 17
HOLD = X.HOLD_BARS


def zero_cost(df):
    d = df.copy()
    for k in ("open", "high", "low", "close"):
        d[f"bid_{k}"] = d[k]
        d[f"ask_{k}"] = d[k]
    return d


def engine(P, dvec, Ivec, tick, tp_R=1.0, hold=HOLD, stop_mult=1.0,
           use_stop=True, use_target=True):
    """run_e01's mechanics with the exit opened up.

    Defaults reproduce run_e01 exactly: stop from the signal bar's own
    invalidation level with the same buffer, target at 1R, same G09 gate,
    same one-position-at-a-time rule, entry at the entry bar's OPEN. The
    reproduction is asserted in main() before anything else is read, because
    a comparison against a different engine would measure the rewrite rather
    than the exit."""
    o, h, l, c, N = P["o"], P["h"], P["l"], P["c"], P["N"]
    bid, ask, A, spread = P["bid"], P["ask"], P["A"], P["spread"]
    R, I_, HD = [], [], []
    busy = -1
    for t in range(300, N - 1):
        d = dvec[t]
        if d == 0 or t <= busy:
            continue
        a = A[t]
        if not np.isfinite(a) or a <= 0:
            continue
        e = t + 1
        entry = P["ask_o"][e] if d > 0 else P["bid_o"][e]
        inval = Ivec[t]
        if not np.isfinite(entry) or not np.isfinite(inval):
            continue
        b = max(0.10 * a, spread[t] if np.isfinite(spread[t]) else 0, 2 * tick)
        raw = (X.tick_round(inval - b, False, tick) if d > 0
               else X.tick_round(inval + b, True, tick))
        dist = abs(entry - raw) * stop_mult
        if dist <= 0:
            continue
        stop = entry - d * dist
        sp = spread[e] if np.isfinite(spread[e]) else spread[t]
        if not np.isfinite(sp) or sp > 0.10 * a:
            continue
        if not (max(0.30 * a, 5 * sp) <= abs(entry - raw) <= 3 * a):
            continue
        # Gapped through the stop before the order could exist. This must be
        # tested on the RAW invalidation level, not on the reconstructed stop:
        # `stop = entry - d*dist` is forced to the correct side by
        # construction, so testing it can never fire. run_e01 tests the real
        # rounded level, which can land on the wrong side of the entry. The
        # reproduction check caught this as 12 extra gold trades.
        if (entry <= raw) if d > 0 else (entry >= raw):
            continue
        target = entry + d * tp_R * dist
        ex_lo = P["bid_l"] if d > 0 else P["ask_l"]
        ex_hi = P["bid_h"] if d > 0 else P["ask_h"]
        px = None
        for k in range(e, min(e + hold, N)):
            hit_s = use_stop and ((ex_lo[k] <= stop) if d > 0
                                  else (ex_hi[k] >= stop))
            hit_t = use_target and ((ex_hi[k] >= target) if d > 0
                                    else (ex_lo[k] <= target))
            # G12: both in one bar with no intrabar order known - assume the
            # stop filled first, the conservative read
            if hit_s:
                px, bar = stop, k
                break
            if hit_t:
                px, bar = target, k
                break
        if px is None:
            bar = min(e + hold - 1, N - 1)
            px = bid[bar] if d > 0 else ask[bar]
        R.append((px - entry) * d / dist)
        I_.append(float(t))
        HD.append(float(max(bar - t, 1)))
        # one position at a time - omitting this let trades overlap and
        # produced 13,000 where run_e01 produces 7,500, which is what the
        # reproduction check above caught
        busy = bar
    if len(R) < 20:
        return None
    return np.asarray(R), np.asarray(I_), np.asarray(HD)


def random_like(dvec, rng, lo=300):
    """Same number of signals, same direction mix, placed at random bars."""
    out = np.zeros_like(dvec)
    live = np.where(dvec != 0)[0]
    live = live[live >= lo]
    pool = np.arange(lo, len(dvec) - HOLD - 2)
    if len(pool) < len(live) or len(live) == 0:
        return out
    pick = rng.choice(pool, size=len(live), replace=False)
    out[pick] = dvec[live]
    return out


DESIGNS = [
    ("current: stop 1.0x, TP 1R", dict(stop_mult=1.0, tp_R=1.0)),
    ("stop 2.0x, TP 1R", dict(stop_mult=2.0, tp_R=1.0)),
    ("stop 3.0x, TP 1R", dict(stop_mult=3.0, tp_R=1.0)),
    ("stop 1.0x, TP 2R", dict(stop_mult=1.0, tp_R=2.0)),
    ("stop 2.0x, TP 2R", dict(stop_mult=2.0, tp_R=2.0)),
    ("stop only, no target", dict(stop_mult=1.0, use_target=False)),
    ("TIME EXIT ONLY", dict(use_stop=False, use_target=False)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="XAUUSD,EURUSD,GBPUSD")
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("BRACKET BIAS - what the exit costs before any entry is chosen")
    print("=" * 96)
    print(__doc__.split("THE PRINCIPLE THAT MAKES IT MEASURABLE")[1]
          .split("THE RULE THIS FILE MUST NOT BREAK")[0])

    frames = {}
    for s in syms:
        df = load_bidask_h1(s)
        if df is not None and len(df) > 20000:
            frames[s] = X.prep(zero_cost(df), 60)

    # --- reproduction check, before anything is read ----------------------
    print("=" * 96)
    print("0. DOES THE REWRITTEN ENGINE REPRODUCE run_e01 AT ITS DEFAULTS?")
    print("=" * 96)
    ok = True
    for s, P in frames.items():
        d, I = momentum_signal(P)
        mine = engine(P, d, I, TICKS.get(s, 0.00001))
        theirs = X.run_e01(P, d, I, 0, P["N"], TICKS.get(s, 0.00001))
        if mine is None or theirs is None:
            continue
        dm, dt = float(mine[0].mean()), float(theirs[0].mean())
        same = abs(dm - dt) < 1e-9 and len(mine[0]) == len(theirs[0])
        ok &= same
        print(f"  {s:<9} mine {dm:+.6f} (n {len(mine[0]):,})   "
              f"run_e01 {dt:+.6f} (n {len(theirs[0]):,})   "
              f"{'MATCH' if same else 'DIFFER'}")
    if not ok:
        print("\n  The rewrite does not reproduce the engine it is meant to")
        print("  vary. Any difference below would measure the rewrite rather")
        print("  than the exit. Stopping.")
        return
    print("  -> identical, so differences below are the exit and nothing else")

    # --- the measurement: random timing only ------------------------------
    print("\n" + "=" * 96)
    print("1. RANDOM TIMING, ZERO COST - the exit's own expectancy")
    print("=" * 96)
    print("  The real entries are NOT consulted here. The exit is chosen on")
    print("  this table alone.\n")
    print(f"  {'exit design':<28}" + "".join(f"{s:>12}" for s in frames)
          + f"{'mean':>10}")
    rows = []
    for label, kw in DESIGNS:
        vals = []
        for s, P in frames.items():
            d, I = momentum_signal(P)
            rng = np.random.default_rng(SEED)
            rd = random_like(d, rng)
            r = engine(P, rd, I, TICKS.get(s, 0.00001), **kw)
            vals.append(float(r[0].mean()) if r is not None else np.nan)
        m = float(np.nanmean(vals))
        rows.append(dict(label=label, mean=m, **kw))
        print(f"  {label:<28}" + "".join(f"{v:>+12.4f}" for v in vals)
              + f"{m:>+10.4f}")

    fair = min(rows, key=lambda r: abs(r["mean"]))
    print(f"\n  nearest to zero: {fair['label']}  at {fair['mean']:+.4f}")
    print(f"  current design:  {rows[0]['label']}  at {rows[0]['mean']:+.4f}")
    print(f"  the exit this project has always used costs "
          f"{rows[0]['mean'] - fair['mean']:+.4f}R per trade before any")
    print(f"  entry is chosen and before any spread is charged")

    # --- only now, the real entries ---------------------------------------
    print("\n" + "=" * 96)
    print("2. WHAT THE REAL ENTRIES DO - computed AFTER the exit was fixed")
    print("=" * 96)
    kw = {k: v for k, v in fair.items() if k not in ("label", "mean")}
    print(f"  exit: {fair['label']}\n")
    print(f"  {'market':<9}{'entry':<7}{'real E':>10}{'random E':>11}"
          f"{'skill':>10}")
    for s, P in frames.items():
        for lab, fn in (("mom", momentum_signal), ("rev", reversion_signal)):
            d, I = fn(P)
            r = engine(P, d, I, TICKS.get(s, 0.00001), **kw)
            rd = random_like(d, np.random.default_rng(SEED))
            rc = engine(P, rd, I, TICKS.get(s, 0.00001), **kw)
            if r is None or rc is None:
                continue
            re, ce = float(r[0].mean()), float(rc[0].mean())
            print(f"  {s:<9}{lab:<7}{re:>+10.4f}{ce:>+11.4f}{re-ce:>+10.4f}")
    print(f"\n  These are ZERO-COST numbers. Real spread at H1 runs 0.011R to")
    print(f"  0.073R depending on market and hour, and has to come off the")
    print(f"  skill column before any of it means anything.")
    pd.DataFrame(rows).to_csv(HERE / "bracket_bias.csv", index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
