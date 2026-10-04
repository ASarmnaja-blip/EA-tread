#!/usr/bin/env python3
"""The sealed holdout is a deterministic function of the panel it was meant
to be independent of.

HOW THIS WAS FOUND, WHICH MATTERS

  Not by auditing the holdout. The relative-value run selected on synthetic
  crosses built from pairs of panel markets, and its best performers were
  EURUSD/USDJPY, AUDUSD/USDCAD, AUDUSD/NZDUSD and EURUSD/USDCHF. Those
  residuals ARE EURJPY, AUDCAD, AUDNZD and EURCHF - four sealed symbols,
  selected on directly, without anyone opening anything.

  Checking the rest found the same for all of them. Fourteen of fourteen.

THE REASONING THAT BUILT IT, AND WHY IT IS BACKWARDS

  The holdout was chosen as fourteen FX crosses with NO USD LEG, on the
  reasoning that a panel dominated by the dollar could not have touched them.

  That is exactly inverted. A cross with no USD leg is PRECISELY the one that
  triangular arbitrage pins to two USD pairs:

      EURJPY  =  EURUSD  x  USDJPY

  and the panel holds both. The criterion that was supposed to guarantee
  independence guarantees dependence instead.

WHAT IS STILL INDEPENDENT, AND IT IS NOT NOTHING

  The mid price is pinned. The QUOTE is not. Each cross has its own book, its
  own spread, its own hours of thin liquidity and its own no-arbitrage band
  width, and none of those follows from the legs. So the sealed set can still
  adjudicate anything that turns on cost or tradability, and cannot adjudicate
  anything that turns on where the price goes.

  That distinction matters here because every economic verdict in this project
  divides by a spread.

WHAT THIS DOES AND DOES NOT RETRACT

  It retracts the PROTECTION claimed for the holdout, not any result. Nothing
  was ever tested on it; it has never been opened; and this finding did not
  require opening it, because the synthesis follows from the currency names
  alone. No series was read to write this file.

  A genuinely independent holdout would have to differ in something other than
  which currencies appear in the ticker - a different asset class, a different
  venue, or a different era. The last of those this project already has and
  has been using: 2004-2016 against 2017-2026.
"""
import itertools
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import provenance as PR
from p01_cross_market import MARKETS

PANEL = list(MARKETS) + ["USDSEK"]


def legs(sym):
    return sym[:3], sym[3:]


def synthesis_map(holdout, panel):
    """Which panel pair reproduces each holdout symbol, from names alone.

    No price series is read. Two pairs sharing a common currency define the
    cross between their other two legs by no-arbitrage, so the mapping is a
    fact about tickers."""
    out = {}
    for a, b in itertools.combinations(panel, 2):
        (a1, a2), (b1, b2) = legs(a), legs(b)
        shared = {a1, a2} & {b1, b2}
        if not shared:
            continue
        rest = ({a1, a2} | {b1, b2}) - shared
        if len(rest) != 2:
            continue
        x, y = sorted(rest)
        for cand in (x + y, y + x):
            if cand in holdout:
                out.setdefault(cand, []).append(f"{a} x {b}")
    return out


def main():
    t0 = time.time()
    print("HOLDOUT INDEPENDENCE - is the seal protecting anything?")
    print("=" * 96)
    print(__doc__.split("THE REASONING THAT BUILT IT")[1]
          .split("WHAT IS STILL INDEPENDENT")[0])

    p = HERE / "sealed_holdout.json"
    d = json.loads(p.read_text())
    hold = list(d.get("symbols", []))
    print(f"  sealed set: {len(hold)} symbols, examined: {d.get('examined')}")
    print(f"  panel:      {len(PANEL)} markets\n")

    m = synthesis_map(set(hold), PANEL)
    print(f"  {'sealed symbol':<16}{'synthesised by':<30}{'status'}")
    for s in sorted(hold):
        if s in m:
            print(f"  {s:<16}{m[s][0]:<30}PINNED by no-arbitrage")
        else:
            print(f"  {s:<16}{'-':<30}independent of the panel")

    pinned = sorted(m)
    free = sorted(set(hold) - set(m))
    print(f"\n  {len(pinned)} of {len(hold)} sealed symbols are exactly "
          f"synthesisable from the panel")
    print(f"  {len(free)} remain independent"
          + (f": {free}" if free else ""))

    print("\n" + "=" * 96)
    print("WHAT THE SEAL CAN AND CANNOT STILL ADJUDICATE")
    print("=" * 96)
    print("  CANNOT   any finding about where the price goes. The mid is")
    print("           pinned to within the no-arbitrage band, so a directional")
    print("           rule selected on the panel is largely pre-determined on")
    print("           the holdout. That covers every directional hypothesis in")
    print("           this repository.")
    print()
    print("  CAN      anything that turns on the QUOTE. Each cross has its own")
    print("           book, its own spread, its own thin hours and its own")
    print("           band width, and none of those follows from the legs.")
    print("           Since every economic verdict here divides by a spread,")
    print("           that is not a small residue - but it is a different")
    print("           question from the one the holdout was built to answer.")

    print("\n" + "=" * 96)
    print("WHAT A GENUINELY INDEPENDENT HOLDOUT WOULD NEED")
    print("=" * 96)
    print("  To differ in something other than which currencies appear in the")
    print("  ticker: a different asset class, a different venue, or a")
    print("  different era. The last of those this project already has and has")
    print("  been using - 2004-2016 against 2017-2026 - and it has killed two")
    print("  candidates on its own.")

    d["independence_defect"] = dict(
        found=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        finding="all %d sealed symbols are exactly synthesisable from the "
                "nine-market panel by triangular arbitrage; the criterion "
                "used to build the set - no USD leg - guarantees dependence "
                "on a USD panel rather than independence from it" % len(pinned),
        synthesis={k: v[0] for k, v in m.items()},
        pinned=pinned, independent=free,
        can_adjudicate="cost and tradability, which depend on each cross's "
                       "own book",
        cannot_adjudicate="anything directional, since the mid is pinned to "
                          "within the no-arbitrage band",
        seal_intact=True,
        note="no holdout series was read to establish this; the synthesis "
             "follows from the currency names alone",
    )
    p.write_text(json.dumps(d, indent=1))
    print(f"\n  sealed_holdout.json marked with the defect; "
          f"examined remains {d.get('examined')}")

    out = HERE / "holdout_independence.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        holdout=hold, panel=PANEL, synthesis={k: v for k, v in m.items()},
        pinned=len(pinned), independent=len(free),
        seal_intact=True), indent=1))
    PR.log("phase7-holdout-independence",
           "Is the sealed holdout independent of the panel it was meant to "
           "test against?",
           hypothesis="holdout_independence_defect",
           tools=["holdout_independence"],
           result=dict(pinned=len(pinned), independent=len(free)),
           status="DEFECT_FOUND",
           finding=f"{len(pinned)} of {len(hold)} sealed symbols are exactly "
                   f"synthesisable from the panel; the seal is intact but "
                   f"protects far less than was believed",
           next_action="record; the seal stays closed either way",
           started=t0)
    print(f"  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
