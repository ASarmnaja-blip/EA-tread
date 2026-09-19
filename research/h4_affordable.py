#!/usr/bin/env python3
"""The only configuration in 828 hypotheses where the arithmetic is not
already lost before an entry rule is chosen.

THE THREE NUMBERS

  largest drift-adjusted skill ever measured in this repo   +0.073R  (zero cost)
  H1 median cost per unit of an hour's own range             12.5%   (~0.125R)
  H4 cheapest hours                                           3.1%   (~0.03R)

  At H1 nothing measured here survives its own cost. At H4's cheap end a
  +0.073R gross skill would net around +0.04R. That gap is the whole reason
  this file exists, and it comes from the instrument rather than from another
  search.

WHAT IS AND IS NOT BEING CLAIMED

  Refusing the expensive hours is a COST decision and free - "this hour
  charges 3x the median" is a measurement, not a prediction, and nothing is
  selected for having worked. The hypothesis, the only one paid for here, is
  whether the resulting book comes out NON-NEGATIVE.

  The control is the identical entries on the identical H4 bars with no hour
  restriction, so the comparison isolates the cost constraint rather than the
  move from H1 to H4. Two things changed at once would attribute to whichever
  is mentioned first.

WHAT A NEGATIVE RESULT WOULD SETTLE

  If the cost-restricted book is still negative, then the cost map is right
  about which hours are dear and the edge is too small to survive even the
  cheapest of them. That closes the timeframe question instead of leaving it
  open for a seventh attempt, which is worth more than another inconclusive
  reading.
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
import market_profile as MP
import mega_search as M
import xauusd_1000_setups as X
from liquidity_sweep_crossmarket import block_se
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import COST_MULT, momentum_signal, reversion_signal, run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("H4, AFFORDABLE HOURS ONLY - ordinary entries, nothing re-tuned")
    print("=" * 100)
    print(__doc__.split("THE THREE NUMBERS")[1].split("WHAT A NEGATIVE")[0])

    rows = []
    for sym in syms:
        r = MP.profile(sym, "H4")
        if r is None:
            continue
        H = r["hours"]
        med = float(H.cost_range.median())
        cheap = {int(x.hour) for _, x in H.iterrows()
                 if np.isfinite(x.cost_range) and x.cost_range <= med * COST_MULT}
        if len(cheap) < 2:
            continue
        bars = MP.load_tf(sym, "H4")
        if bars is None or len(bars) < 10000:
            continue
        P = X.prep(bars, 240)
        tick = TICKS.get(sym, 0.00001)
        dm, Im = momentum_signal(P)
        dr, Ir = reversion_signal(P)

        res = {}
        for lab, hrs in (("restricted", cheap), ("unrestricted", None)):
            arms = [run(P, d, I, tick, hrs) for d, I in ((dm, Im), (dr, Ir))]
            arms = [x for x in arms if x]
            if not arms:
                continue
            R = np.concatenate([x["R"] for x in arms])
            se = math.sqrt(sum(x["se"] ** 2 for x in arms))
            res[lab] = dict(n=len(R), E=float(R.mean()), se=se)
        if len(res) < 2:
            continue
        diff = res["restricted"]["E"] - res["unrestricted"]["E"]
        se = math.sqrt(res["restricted"]["se"] ** 2 +
                       res["unrestricted"]["se"] ** 2)
        rows.append(dict(symbol=sym, cheap_hours=len(cheap),
                         n_res=res["restricted"]["n"],
                         e_res=res["restricted"]["E"],
                         n_all=res["unrestricted"]["n"],
                         e_all=res["unrestricted"]["E"],
                         diff=diff, t=diff / se if se > 0 else np.nan,
                         cheapest_cost=float(H.cost_range.min())))
        print(f"  {sym:<9} cheap hrs {len(cheap):>2}   restricted "
              f"{res['restricted']['E']:+.4f} (n {res['restricted']['n']:,})   "
              f"all-hours {res['unrestricted']['E']:+.4f} "
              f"(n {res['unrestricted']['n']:,})   diff {diff:+.4f}",
              flush=True)

    if not rows:
        print("\n  nothing produced a comparison")
        return
    D = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("THE TEST")
    print("=" * 100)
    er = float(D.e_res.mean())
    ea = float(D.e_all.mean())
    md = float(D["diff"].mean())
    se = float(D["diff"].std(ddof=1) / math.sqrt(len(D)))
    t = md / se if se > 0 else np.nan
    print(f"  markets                    {len(D)}")
    print(f"  restricted book E(R)       {er:+.4f}   "
          f"{'NON-NEGATIVE' if er >= 0 else 'still negative'}")
    print(f"  unrestricted book E(R)     {ea:+.4f}")
    print(f"  cost constraint is worth   {md:+.4f}R   t {t:+.2f}")
    print(f"  restricted positive on     {int((D.e_res > 0).sum())} of {len(D)}")
    print(f"  signals per year           "
          f"{D.n_res.sum() / (len(D) * 22):.0f} per market restricted, "
          f"{D.n_all.sum() / (len(D) * 22):.0f} unrestricted")
    print(f"\n  For scale: the largest skill this project has ever measured is")
    print(f"  +0.073R at zero cost, and H4's cheapest hours charge about")
    print(f"  {D.cheapest_cost.mean()*100:.1f}% of range.")
    if er < 0:
        print(f"\n  A restricted book still at {er:+.4f} says the cost map is")
        print(f"  right about which hours are dear and the edge is too small")
        print(f"  to survive even the cheapest of them. That closes the")
        print(f"  timeframe question rather than leaving it open.")
    out = HERE / "h4_affordable.csv"
    D.to_csv(out, index=False)
    print(f"\n  -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
