#!/usr/bin/env python3
"""What is actually left, after 824 hypotheses - the arithmetic, not advice.

This file makes no new claim about any strategy. It puts four numbers this
project has already measured next to three it had to look up, and reads what
they say together.

THE FOUR MEASURED HERE

  1. Every rule that showed positive drift-adjusted skill showed it in one
     narrow band: +0.028R (liquidity sweep, 9 markets, 43,198 trades at real
     bid/ask), +0.042R (compression), +0.051R (the sweep at zero cost on 27
     futures), +0.073R (the sweep at zero cost here). Nothing has ever been
     bigger. That band is the size of the edge available.

  2. Cost at H1 on the account modelled throughout is 18.3% of gold's median
     ATR, 5.0% on EURUSD, 32.6% at OANDA's measured gold spread. In R terms
     with this engine's stop sizing, that is 0.05R to 0.18R per trade. The
     cost is two to six times the edge.

  3. venue_change.py re-priced the same trades on an exchange-grade quote.
     Moving gold from CFD to COMEX futures is worth +0.0464R per trade - real
     money, a third of the gap - and the rule still loses 0.0904R. At ZERO
     cost it loses 0.0574R. The venue was never the whole problem.

  4. discipline_audit.py: after 824 hypotheses the smallest annual Sharpe that
     22 years of this data can still establish is 0.68.

THE THREE LOOKED UP

  5. COMEX gold futures cost about $0.131 per ounce round turn - one tick of
     spread on a 100oz contract plus roughly $3.10 of exchange, clearing and
     NFA fees. That is 3.2x cheaper than the CFD spread measured here, and it
     carries no overnight debit, which removes the h* = S/w holding ceiling
     that tsmom_d1.py derived. Micro gold (MGC) is the same cost per ounce at
     a tenth the size, but initial margin is about $1,870 and a workable
     account is $1,500-$5,000 - between thirty and a thousand times the
     capital this project has been sizing for.

  6. On a retail FX/CFD account a limit order CANNOT earn the spread. CME
     Group's own write-up of it: once the quote reaches your price the limit
     becomes a market order against the broker's stream, so the trader always
     crosses the spread and never gets a passive fill. There is no queue to
     join, because there is no book - the broker is the counterparty. Passive
     execution, the one lever that turns a cost into a credit, is structurally
     unavailable here. It exists on an exchange, and on crypto perpetuals,
     where maker fees run 0.020% and go to zero or negative at volume tiers.

  7. The SG CTA Index has returned a Sharpe of 0.61 since 2000; the SG Trend
     Index about 0.43. Those are the professional trend-followers - billions
     under management, institutional execution, decades of research, net of
     fees.

WHAT (4) AND (7) SAY TOGETHER, WHICH IS THE POINT OF THIS FILE

  The verification standard now exceeds the industry it is verifying. A
  strategy performing exactly as well as the entire professional CTA sector
  has performed since 2000 would be UNVERIFIABLE on this project's data at
  this hypothesis count. That is not a statement about gold, or about any
  rule tested here. It is a statement about the search: 824 hypotheses have
  consumed the sample.

  So "test more carefully" is not available, and neither is "test more". The
  floor rises with every hypothesis and the 22 years do not grow.

THE ONE THING THAT DOES MOVE IT

  The floor is set by how many hypotheses were spent BEFORE the evidence was
  seen. Evidence gathered AFTER committing to a single rule is judged at
  k = 1. That is not a loophole; it is the entire reason pre-registration
  exists, and this project already built the machinery for it in
  change_ledger.py.
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from change_ledger import floor_for
from overfit_stats import min_backtest_length

K_NOW = 824
SG_CTA = 0.61
SG_TREND = 0.43
HAVE_YEARS = 22.0


def main():
    print("WHAT IS LEFT AFTER 824 HYPOTHESES")
    print("=" * 88)
    print(__doc__.split("WHAT (4) AND (7) SAY TOGETHER, WHICH IS THE POINT OF THIS FILE")[1]
          .split("THE ONE THING THAT DOES MOVE IT")[0])

    print("=" * 88)
    print("1. THE STANDARD AGAINST THE INDUSTRY IT IS JUDGING")
    print("=" * 88)
    smallest = 0.05
    lo, hi = 0.05, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if min_backtest_length(K_NOW, mid) > HAVE_YEARS:
            lo = mid
        else:
            hi = mid
    smallest = (lo + hi) / 2
    print(f"  smallest Sharpe {HAVE_YEARS:.0f} years can establish at k={K_NOW}"
          f"      {smallest:.2f}")
    print(f"  SG CTA Index, realised Sharpe since 2000            {SG_CTA:.2f}"
          f"   {'BELOW the bar' if SG_CTA < smallest else 'clears'}")
    print(f"  SG Trend Index, realised Sharpe                     {SG_TREND:.2f}"
          f"   {'BELOW the bar' if SG_TREND < smallest else 'clears'}")
    print(f"\n  The professional trend-following industry, measured over a")
    print(f"  quarter century, could not be verified on this data at this")
    print(f"  hypothesis count. The search has consumed the sample.")

    print("\n" + "=" * 88)
    print("2. WHAT PRE-COMMITMENT IS WORTH, IN YEARS OF DATA")
    print("=" * 88)
    print(f"  Years of evidence needed to establish a given Sharpe, as a")
    print(f"  function of how many hypotheses were spent before seeing it:\n")
    print(f"  {'hypotheses spent':<22}{'@ Sharpe 0.50':>16}{'@ 0.61 (SG CTA)':>18}")
    for k in (1, 5, 10, 50, 824):
        print(f"  {('k = ' + str(k)):<22}{min_backtest_length(k, 0.50):>15.1f}y"
              f"{min_backtest_length(k, 0.61):>17.1f}y")
    ratio = min_backtest_length(824, 0.50) / min_backtest_length(1, 0.50)
    print(f"\n  Committing to ONE rule before the evidence exists is worth")
    print(f"  {ratio:.0f}x the data. 1.1 years of forward evidence on a rule fixed")
    print(f"  in advance carries what 41 years of backtest carries after 824")
    print(f"  hypotheses. That factor is the largest number in this project.")

    print("\n" + "=" * 88)
    print("3. THE THREE ROUTES, AND WHAT EACH COSTS")
    print("=" * 88)
    print("""
  A  FORWARD EVIDENCE ON ONE PRE-COMMITTED RULE
     Cost: about 1.1 years of wall-clock time, and the discipline not to
     change the rule while it runs. Buys: evidence judged at k=1 instead of
     k=824, the only source of hypothesis-free data left. This is the only
     route that repairs the statistical problem rather than working around
     it, and the ledger already enforces the commitment.
     What it does NOT fix: nothing tested here is positive at zero cost, so
     there is currently no rule worth committing to. That has to come first.

  B  MORE INSTRUMENTS, SAME RULES
     Cost: data and engineering, no new hypotheses if nothing is re-tuned -
     liquidity_sweep_crossmarket.py spent exactly one k for nine markets.
     Buys: n grows, t grows like sqrt(n), the floor does not move.
     What it does NOT fix: the edges measured are negative at zero cost, and
     more markets of a negative-expectancy rule is more of a negative
     expectancy. This raises resolution, not returns.

  C  CHANGE THE VENUE
     Cost: 30x to 1000x the capital for futures; or a different asset class
     entirely for exchange-grade execution at small size. Buys: measured at
     +0.0464R per trade on gold, about a third of the gap, plus the removal
     of the swap ceiling. Passive execution - the lever that turns cost into
     credit - does not exist on a retail CFD account at all and does exist on
     an exchange.
     What it does NOT fix: on its own, nothing. Every rule here is still
     negative at zero cost. Venue is a multiplier on an edge, not a source
     of one.
""")

    print("=" * 88)
    print("THE HONEST ORDER")
    print("=" * 88)
    print("""
  C does not help without an edge. B does not help without an edge. A cannot
  start without an edge. All three routes are downstream of the same missing
  thing, and 824 hypotheses of searching this sample is precisely how the
  ability to recognise one was spent.

  Which leaves the one move that is not on the list: STOP SEARCHING THIS
  SAMPLE. Every additional hypothesis tested against 2004-2026 gold and FX
  raises the floor and shortens the runway, and the floor is already above
  the professional industry's own realised Sharpe. The sample cannot answer
  the question any more, and no amount of care changes that - it is
  arithmetic, not technique.

  The project's own machinery already says this. It just had not been asked.
""")
    print(f"  current floor, for reference: |t| > {floor_for(K_NOW):.2f} at k = {K_NOW}")
    print(f"  after 100 more hypotheses:    |t| > {floor_for(K_NOW + 100):.2f}")
    print(f"  after 1000 more:              |t| > {floor_for(K_NOW + 1000):.2f}")


if __name__ == "__main__":
    main()
