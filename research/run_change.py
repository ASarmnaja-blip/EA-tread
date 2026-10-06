#!/usr/bin/env python3
"""Run one registered change: baseline against variant, on the declared period.

WHAT THIS DOES AND WHY IT IS SEPARATE FROM THE LEDGER

  The ledger records. This runs. They are separate files because the ledger
  must be readable and auditable without understanding any backtest machinery,
  and because a result produced here is meant to be pasted into
  `change_ledger.py record` deliberately, as an act, rather than written
  automatically by the thing that produced it.

THE COMPARISON IS PAIRED, AND THAT IS NOT A DETAIL

  Baseline and variant fire on the SAME signals - only the exit changes. So
  the right test is on the per-signal DIFFERENCE, not on two independent
  means. An unpaired test here throws away most of the power and would call
  a real improvement inconclusive; a paired test on overlapping trades
  without a block bootstrap does the opposite and calls noise a result. Both
  are handled below.

  Signals present in only one arm are DROPPED, not compared. Widening the
  stop raises the risk per trade, which lets more signals clear the
  3x-cost rule, so the variant naturally sees signals the baseline never
  took. Counting those as improvement would credit the change for trades it
  did not improve - it merely admitted them. They are reported separately.

THE PERIOD

  The change is tested on data that did not suggest it. For a diagnosis run
  on discovery, that means holdout, and this is the one place in the project
  where holdout is spent deliberately. Every run here consumes some of it,
  which is why the ledger counts them.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB


def book(P, deadline, look, buf, stop, hold, cost_px, lo, hi):
    """The trade book for one configuration over bars [lo, hi).

    Returns a dict keyed by SIGNAL BAR so the two arms can be paired. The
    signal bar is the identity of a trade; the entry, stop and exit are what
    the configuration does with it."""
    W = EB.walk_for(P, look, buf, stop, cost_px, hold)
    R, held, keep, rep, xpx = EB.resolve_window(W, P, None, hold, lo, hi,
                                                deadline)
    i = W["i"][keep]
    return dict(zip(i.tolist(), zip(R[keep].tolist(), held[keep].tolist(),
                                    W["d"][keep].tolist()))), rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--look", type=int, default=20)
    ap.add_argument("--buf", type=float, default=0.0)
    ap.add_argument("--hold", type=int, default=12)
    ap.add_argument("--baseline-stop", default="atr1")
    ap.add_argument("--variant-stop", default="atr2")
    ap.add_argument("--baseline-hold", type=int, default=None)
    ap.add_argument("--variant-hold", type=int, default=None)
    ap.add_argument("--period", default="holdout",
                    choices=("holdout", "discovery"))
    ap.add_argument("--spread", type=float, default=260.0)
    ap.add_argument("--slip", type=float, default=0.0)
    a = ap.parse_args()
    t0 = time.time()

    print("RUN CHANGE - baseline vs variant on the declared period")
    print("=" * 84)
    print(__doc__.split("THE COMPARISON IS PAIRED")[1].split("THE PERIOD")[0])

    m = M.load_tf(a.tf)
    P = M.prep(m)
    tf_min = S.bar_minutes(m.index)
    deadline, _, _ = S.intraday_deadlines(m.index, tf_min)
    disc_end = EB.DISCOVERY_END if tf_min >= 60 else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    lo, hi = ((n_disc, len(m)) if a.period == "holdout" else (0, n_disc))
    cost_px = EB.scenario_cost_px(a.spread, a.slip)

    bh = a.baseline_hold if a.baseline_hold is not None else a.hold
    vh = a.variant_hold if a.variant_hold is not None else a.hold
    yrs = (m.index[hi - 1] - m.index[lo]).days / 365.25

    print(f"data      {a.tf}  {a.period.upper()} bars {lo:,}..{hi:,}  "
          f"{m.index[lo].date()} -> {m.index[hi-1].date()}  ({yrs:.1f} years)")
    print(f"cost      spread {a.spread:.0f} pts, slippage {a.slip:g}x -> "
          f"{cost_px:.3f} price units round trip")
    print(f"baseline  look{a.look} buf{a.buf} {a.baseline_stop} hold{bh}")
    print(f"variant   look{a.look} buf{a.buf} {a.variant_stop} hold{vh}")

    B, repB = book(P, deadline, a.look, a.buf, a.baseline_stop, bh, cost_px,
                   lo, hi)
    V, repV = book(P, deadline, a.look, a.buf, a.variant_stop, vh, cost_px,
                   lo, hi)

    shared = sorted(set(B) & set(V))
    only_b = sorted(set(B) - set(V))
    only_v = sorted(set(V) - set(B))
    print(f"\nSIGNALS   baseline {len(B):,}   variant {len(V):,}   "
          f"shared {len(shared):,}")
    print(f"          baseline-only {len(only_b):,}   variant-only "
          f"{len(only_v):,}")
    if len(shared) < 100:
        print("\n  too few shared signals to compare - the two arms are not "
              "the same\n  experiment, so a difference between them is not "
              "attributable to the change.")
        return

    rb = np.array([B[k][0] for k in shared], float)
    rv = np.array([V[k][0] for k in shared], float)
    hb = np.array([B[k][1] for k in shared], float)
    hv = np.array([V[k][1] for k in shared], float)
    where = np.asarray(shared, float)
    diff = rv - rb
    # Held for overlap purposes is the LONGER of the two arms: the paired
    # difference is not independent of the next one until both trades have
    # closed.
    held = np.maximum(hb, hv)

    t_paired = M.block_bootstrap_t(diff, where, held, 1)
    ci = M.block_bootstrap_ci(diff, where, held)

    print(f"\nPAIRED ON SHARED SIGNALS  (n={len(shared):,})")
    print(f"  baseline E(R)  {rb.mean():+.4f}   win "
          f"{float((rb > 0).mean())*100:.1f}%   sum {rb.sum():+.1f}R")
    print(f"  variant  E(R)  {rv.mean():+.4f}   win "
          f"{float((rv > 0).mean())*100:.1f}%   sum {rv.sum():+.1f}R")
    print(f"  difference     {diff.mean():+.4f}R per signal")
    if ci is not None:
        print(f"  block-bootstrap 95% CI on the difference  "
              f"[{ci[0]:+.4f}, {ci[1]:+.4f}]")
    print(f"  block-bootstrap t on the difference       {t_paired:+.2f}")
    print(f"  signals improved {int((diff > 0).sum()):,}  "
          f"unchanged {int((diff == 0).sum()):,}  "
          f"worsened {int((diff < 0).sum()):,}")

    # Per year, which is what an account actually experiences. E(R) can rise
    # while total R falls if the change also thins the book.
    print(f"\nPER YEAR  (E(R) can rise while the account earns less)")
    print(f"  baseline {len(B)/yrs:>7,.0f} trades/yr   "
          f"{sum(v[0] for v in B.values())/yrs:>+8.1f} R/yr")
    print(f"  variant  {len(V)/yrs:>7,.0f} trades/yr   "
          f"{sum(v[0] for v in V.values())/yrs:>+8.1f} R/yr")

    if only_v:
        rov = np.array([V[k][0] for k in only_v], float)
        print(f"\nVARIANT-ONLY SIGNALS  (excluded from the paired test above)")
        print(f"  n {len(only_v):,}   E(R) {rov.mean():+.4f}   these are "
              f"signals the change\n  ADMITTED, not signals it improved. They "
              f"are reported so a change that\n  merely loosens a filter "
              f"cannot be read as a change that works.")

    print("\n" + "=" * 84)
    print("PASTE INTO THE LEDGER (after registering, never before):")
    print(f"  python3 research/change_ledger.py record --id <id> \\")
    print(f"    --baseline-er {rb.mean():.4f} --variant-er {rv.mean():.4f} \\")
    print(f"    --t-stat {t_paired:.2f} --n-baseline {len(B)} "
          f"--n-variant {len(V)}")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
