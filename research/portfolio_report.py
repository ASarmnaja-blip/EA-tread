#!/usr/bin/env python3
"""Take one configuration all the way to an account statement.

WHAT THIS IS FOR
  Everything upstream reports expectancy in R. R cannot tell you whether an
  account survives, because it has no account in it: no equity to compound, no
  margin to run out of, no minimum lot to round against, and no floating loss
  while three positions sit open at once. This runs a single named
  configuration through portfolio.py and prints what the account did, at three
  cost assumptions, and writes the trade log so any number can be traced back
  to individual fills.

  It does NOT search. It takes a configuration you already have and prices it.
  Running it over many configurations and keeping the best would be the same
  overfitting the rest of this repo spends its effort avoiding.

Run:
  python3 research/portfolio_report.py --look 20 --buf 0.1 --stop atr2 \\
      --tp 2.0 --hold 48 --filters atr_contracting,long_side --risk 0.01
"""
import argparse, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import portfolio as PF
from split_guard import Split

def build(args):
    m = M.load_tf(args.tf)
    P = M.prep(m)
    split = Split(P["idx"], args.boundary or M.DISCOVERY_END)
    th = M.fit_thresholds(P, split)
    cost = P["spread"] + M.COMMISSION
    W = M.walk_rule(P, args.look, args.buf, args.stop, cost, max(M.HOLDS))
    if W is None:
        raise SystemExit("that rule produced no signals at all")
    tps = [t for t in M.TPS if t is not None]
    tp_j = None if args.tp is None else tps.index(args.tp)
    hk = list(M.HOLDS).index(args.hold)
    R, held, keep, rep = M.resolve(W, tp_j, hk, split, args.side)
    F = M.build_filters(P, W, th)
    msk = keep.copy()
    names = [f.strip() for f in args.filters.split(",") if f.strip()]
    for nm in names:
        if nm not in F:
            raise SystemExit(f"unknown filter {nm!r}; have {sorted(F)}")
        msk &= F[nm]
    return m, P, split, th, W, R, held, msk, rep, names

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--look", type=int, default=20)
    ap.add_argument("--buf", type=float, default=0.1)
    ap.add_argument("--stop", default="atr2")
    ap.add_argument("--tp", type=float, default=2.0)
    ap.add_argument("--hold", type=int, default=48)
    ap.add_argument("--filters", default="")
    ap.add_argument("--side", default="discovery",
                    choices=["discovery", "holdout"])
    ap.add_argument("--boundary", default=None)
    ap.add_argument("--risk", type=float, default=0.01)
    ap.add_argument("--equity", type=float, default=10_000.0)
    ap.add_argument("--csv", default=None, help="write the trade log here")
    a = ap.parse_args()
    if a.tp is not None and a.tp <= 0: a.tp = None

    m, P, split, th, W, R, held, msk, rep, names = build(a)
    r_units = R[msk]
    cfg = (f"look{a.look} buf{a.buf} {a.stop} "
           f"tp{'none' if a.tp is None else str(a.tp)+'R'} hold{a.hold}"
           + (f" | {'+'.join(names)}" if names else ""))

    print("PORTFOLIO REPORT")
    print("=" * 74)
    print(f"  data        {a.tf}  {m.index[0].date()} -> {m.index[-1].date()} "
          f"({len(m):,} bars)")
    print(f"  split       {split!r}, thresholds fitted on discovery only")
    print(f"  side        {a.side.upper()}")
    print(f"  config      {cfg}")
    print(f"  trades      {int(msk.sum()):,} after filters "
          f"({rep['straddling']:,} purged for straddling the boundary, "
          f"{rep['gap_skipped']:,} entry-gap skips)")
    if len(r_units) == 0:
        raise SystemExit("  no trades survive - nothing to price")

    print(f"\n  PER-TRADE, in R (what every earlier report stopped at)")
    print(f"    E(R) {r_units.mean():+.4f}   median {np.median(r_units):+.4f}   "
          f"win rate {float((r_units > 0).mean())*100:.1f}%   "
          f"sum {r_units.sum():+.1f}R")
    ci = M.block_bootstrap_ci(r_units, W["i"][msk], held[msk])
    if ci is not None:
        print(f"    block bootstrap 95% CI [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    ctrl, cst = M.matched_control(P, M.subset(W, msk),
                                  None if a.tp is None else
                                  [t for t in M.TPS if t is not None].index(a.tp),
                                  list(M.HOLDS).index(a.hold), split, a.side)
    if len(ctrl) >= 30:
        print(f"    matched control E(R) {ctrl.mean():+.4f} over {cst['n']:,} "
              f"trades ({cst['long_frac']*100:.0f}% long vs "
              f"{float((W['d'][msk] > 0).mean())*100:.0f}% for the strategy, "
              f"mean hold {cst['mean_held']:.0f} vs {held[msk].mean():.0f})")
        print(f"    SKILL over the control: {r_units.mean()-ctrl.mean():+.4f}R")

    print(f"\n  AS AN ACCOUNT, risking {a.risk*100:.1f}% per position, "
          f"starting at {a.equity:,.0f}")
    print("  (overlapping positions are held simultaneously; costs are charged")
    print("   here and NOT taken from the R figures above, which already net "
          "their own)")
    mid = P["c"]
    res = {}
    for lvl in ("base", "elevated", "adverse"):
        br = PF.stressed(PF.Broker(), lvl)
        res[lvl] = PF.from_trades(W, msk, held, mid, P["idx"], P["spread"],
                                  broker=br, risk_frac=a.risk,
                                  start_equity=a.equity)
        print()
        print(PF.summarise(res[lvl], f"  [{lvl.upper()}] "
                           f"spread x{br.spread_mult}, slippage "
                           f"{br.slippage_points} pts, commission "
                           f"{br.commission_per_lot_side}/lot/side"))

    print("\n  WHAT IS ASSUMPTION HERE, NOT MEASUREMENT")
    print("    contract size, leverage, lot step, commission, swap rates and")
    print("    the slippage figures are broker policy chosen as plausible")
    print("    defaults - this repo has measured none of them. The spread")
    print("    series is real Dukascopy bid/ask. The three stress levels are a")
    print("    sensitivity analysis, not a forecast.")

    if a.csv:
        df = PF.log_frame(res["base"])
        df.to_csv(a.csv, index=False)
        print(f"\n  trade log ({len(df):,} rows, base costs) -> {a.csv}")
        if len(df):
            print("\n  first 5 rows:")
            cols = ["entry_time", "exit_time", "d", "lots", "entry_fill",
                    "exit_fill", "stop_px", "risk_money", "commission",
                    "swap", "spread_cost", "pl", "balance_after"]
            print(df[cols].head(5).to_string(index=False))

if __name__ == "__main__":
    main()
