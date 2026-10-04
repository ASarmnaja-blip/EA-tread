#!/usr/bin/env python3
"""The variance ratio, as measured here, is mostly a liquidity reading.

WHAT PROMPTED THIS

  profile_setups.py put momentum entries into the hours the instrument
  measured as EXTENDING their moves (variance ratio above 1.10) and reversion
  entries into the hours measured as REVERTING (below 0.90). Matching came
  back slightly WORSE than the swapped control on the first three markets -
  -0.0088, -0.0513, -0.0093 - and consistently so rather than scattered
  around zero, which is the shape of a small systematic effect rather than
  noise.

  A systematic sign asks for a mechanical explanation, not a bigger sample.

WHAT THE MAP ALREADY CONTAINED

  Correlation between an hour's variance ratio and its cost per unit of
  movement, on gold:

      M1   +0.42     M5   +0.41     M15  +0.41     H1   +0.53

  The hours that extend their moves are systematically the EXPENSIVE ones,
  at every timeframe. And the relationship with movement runs the other way:
  at H1, hour 14 has VR 0.74 and moves 1.93 ATR, while hour 21 has VR 2.78
  and moves 0.33 ATR. The highest-VR hours are the deadest hours.

WHAT THAT MEANS THE MEASUREMENT IS ACTUALLY PICKING UP

  In an illiquid hour, price does not stand still - it drifts, because there
  is nobody on the other side to push it back. A sequence of small moves in
  one direction makes the k-bar variance exceed k times the one-bar variance,
  which is exactly what a high variance ratio is. So the statistic fires on
  thin-book drift and on genuine trend alike, and cannot tell them apart.

  High VR here does not mean "a trend worth trading". It substantially means
  "nobody is trading". Putting a breakout entry into the high-VR hours was
  therefore putting it into the dead, expensive end of the day, and the small
  negative in the matched-versus-swapped comparison is that cost, not a
  failure of the matching idea.

WHY THIS IS A DIAGNOSIS AND NOT A RATIONALISATION

  The finding rests on the correlation table above and on the VR-versus-
  movement column, both of which are properties of the measurements alone.
  Nothing in it depends on whether a strategy made money. Had the matched
  arm won, this correlation would still be here and would still mean the
  variance ratio is contaminated - the setup test is what drew attention to
  it, not what established it.

THE CONSEQUENCE FOR THE INSTRUMENT

  A regime classifier built on raw VR is not fit for choosing entries. It
  needs to be conditioned on there being something to capture - VR measured
  only across hours of comparable movement, or a joint classification on
  (VR, move/ATR) so that "extends its moves" and "actually moves" are
  separate requirements rather than one column silently standing for both.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
SRC = HERE / "market_profile_xtf.json"


def main():
    if not SRC.exists():
        print(f"  {SRC.name} missing - run the cross-timeframe profile first")
        return 1
    d = pd.DataFrame(json.load(SRC.open())["cells"])
    print("VARIANCE RATIO vs COST, and vs MOVEMENT - gold")
    print("=" * 84)
    print(f"  {'TF':<5}{'corr(VR, cost)':>16}{'corr(VR, move/ATR)':>21}"
          f"{'VR range':>16}")
    for tf in ("M1", "M5", "M15", "H1", "H4"):
        g = d[d.tf == tf].dropna(subset=["vr", "cost_range", "move_atr"])
        if len(g) < 8:
            continue
        rc = float(np.corrcoef(g.vr, g.cost_range)[0, 1])
        rm = float(np.corrcoef(g.vr, g.move_atr)[0, 1])
        print(f"  {tf:<5}{rc:>+16.2f}{rm:>+21.2f}"
              f"{g.vr.min():>9.2f}-{g.vr.max():<6.2f}")

    print("\n" + "=" * 84)
    print("  H1 hours, sorted by variance ratio")
    print("=" * 84)
    g = d[d.tf == "H1"].dropna(subset=["vr"]).sort_values("vr")
    print(f"  {'hr':>3}{'VR':>7}{'cost/rng':>10}{'move/ATR':>10}  session")
    for _, r in g.iterrows():
        print(f"  {int(r.hour):>3}{r.vr:>7.2f}{r.cost_range*100:>9.1f}%"
              f"{r.move_atr:>10.2f}  {r.session}")

    lo = g.head(6)
    hi = g.tail(6)
    print(f"\n  six lowest-VR hours:  cost {lo.cost_range.mean()*100:5.1f}%   "
          f"movement {lo.move_atr.mean():.2f} ATR")
    print(f"  six highest-VR hours: cost {hi.cost_range.mean()*100:5.1f}%   "
          f"movement {hi.move_atr.mean():.2f} ATR")
    print(f"\n  The hours that 'extend their moves' cost "
          f"{hi.cost_range.mean()/lo.cost_range.mean():.1f}x more and move "
          f"{lo.move_atr.mean()/hi.move_atr.mean():.1f}x less.")
    print(f"  That is not a description of trend. It is a description of an")
    print(f"  empty book, and the variance ratio cannot separate the two.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
