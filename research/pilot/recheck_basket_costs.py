"""Claude's independent recheck of the Amendment 23 result (review role).

Re-derives the admitted basket orders with Codex's own functions, then
recomputes each window's figures directly from the order list rather than from
Codex's report path:

  - net R at base cost and at 1.5x cost, to confirm the headline figures
  - mean member weight, mean cost as a fraction of R, and gross edge per
    trade before cost, so the reason the 44-month window fails under stress
    can be stated from numbers rather than inferred
  - median stop distance in price units, since cost is fixed in dollars and
    R scales with ATR

Trades are assigned to a window by exit time (clarification A). Read-only; no
order path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_dd as B
import mtf_engine as E


def main() -> int:
    b5 = B.hist.load_history()
    uni, meta = B.audit.load_universe(b5)
    wd = B.WeeklyData.build(b5, uni)
    sel = B.Selector(wd, uni, meta)
    first_policy = int(wd.boundaries[B.MIN_HISTORY_WEEKS])
    last = int(b5.t[-1] + b5.step)
    decisions = B.decisions_through(sel, first_policy, last)
    rows = B.admit_orders(B.orders_from_decisions(b5, uni, decisions)).admitted

    windows = (("44_MONTH", B.REPORT_START, B.REPORT_SPLIT),
               ("TRAILING_12M", B.REPORT_SPLIT, last),
               ("FULL", B.REPORT_START, last))
    print(f"{'window':14s}{'trades':>8s}{'net R':>10s}{'1.5x R':>10s}"
          f"{'mean w':>8s}{'cost/R':>8s}{'net/tr':>9s}{'gross/tr':>10s}"
          f"{'cost share':>11s}{'med stop $':>11s}")
    for name, lo, hi in windows:
        rs = [r for r in rows if lo <= r.exit_t < hi]
        w = np.array([r.weight for r in rs])
        net = np.array([r.net_r for r in rs])
        st = np.array([r.stress_r for r in rs])
        risk = np.array([r.risk for r in rs])
        # full execution cost in R per trade; stress_r = net - 0.5*cost/risk
        cost_r = 2.0 * (net - st)
        gross = net + cost_r
        print(f"{name:14s}{len(rs):8d}{np.sum(net*w):10.3f}{np.sum(st*w):10.3f}"
              f"{w.mean():8.3f}{cost_r.mean():8.4f}{net.mean():9.4f}"
              f"{gross.mean():10.4f}{cost_r.mean()/gross.mean():11.1%}"
              f"{np.median(risk):11.3f}")
    print("\nnet/tr, gross/tr, cost/R are unweighted per-trade means in R.")
    print("cost share = execution cost as a share of the gross edge before cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
