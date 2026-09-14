#!/usr/bin/env python3
"""Does changing the VENUE rescue any rule this project has already killed?

THE QUESTION, STATED FROM WHAT IS ALREADY MEASURED

  Every rule tested here that showed positive drift-adjusted skill showed it
  in a narrow band: +0.028R (liquidity sweep, 9 markets, 43,198 trades),
  +0.042R (compression), +0.051R (the sweep at zero cost on 27 futures). None
  of them made money, because the spread at H1 costs more than that.

  That is not 823 coincidences. It is one fact with 823 observations: the
  edges available in this asset are SMALLER THAN THE COST OF TRADING THEM ON
  THIS ACCOUNT. Which raises a question no strategy test can answer, because
  it is not about strategies - what if the account is the variable?

WHAT THE RESEARCH ESTABLISHES, AND WHAT IT COSTS

  Round-turn cost against gold's own median H1 ATR, from this repo's cache:

      XAUUSD CFD, measured here          $0.4240     18.3% of ATR
      XAUUSD CFD, OANDA measured         $0.7525     32.6%
      XAUUSD CFD, terminal quote         $0.2600     11.2%
      COMEX gold futures, 1 tick + fees  $0.1310      5.7%

  The futures number is $0.10 of spread on a 100oz contract plus about $3.10
  of exchange, clearing and NFA fees, which is $0.131 per ounce round turn.
  It is 3.2x cheaper than the CFD this project has been modelling, and it
  puts gold in the same cost bracket as EURUSD - the cheapest instrument the
  repo ever tested, at 5.0%.

  It also removes the other cost entirely. tsmom_d1.py derived h* = S/w, the
  holding period that minimises cost per unit of move, and got 0.85 nights
  for a gold CFD long because swap is charged every night. A futures contract
  has no overnight debit; the financing is in the basis, paid once. So h*
  does not exist there and the holding-period ceiling this project has been
  trading under is an artefact of the account, not of gold.

WHAT THIS FILE ACTUALLY DOES

  Re-prices the trades the liquidity sweep already made - same signals, same
  bars, same entries and exits, nothing re-fitted - at three cost levels, to
  separate "the rule has no edge" from "the venue ate it".
"""
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from liquidity_sweep_crossmarket import block_se, sweep_signals
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

# Round-turn cost per ounce / per unit, researched, applied as a FLAT quote.
GOLD_FUTURES_COST = 0.131
SEED = 17


def reprice(df, cost):
    """The same frame with the two-sided quote rebuilt at a chosen cost.

    cost is the full round-turn spread in price units. Setting it to 0 gives
    a frictionless book; setting it to the futures figure gives what the same
    trades would have paid on an exchange."""
    d = df.copy()
    half = cost / 2.0
    for k in ("open", "high", "low", "close"):
        d[f"bid_{k}"] = d[k] - half
        d[f"ask_{k}"] = d[k] + half
    return d


def run(df, tick):
    P = X.prep(df, 60)
    d, I = sweep_signals(P)
    out = X.run_e01(P, d, I, 0, P["N"], tick)
    if out is None:
        return None
    R, I_, HD, RATIO = out
    rng = np.random.default_rng(SEED)
    C = X.run_e01_control(P, d, 0, P["N"], risk_ratios=np.asarray(RATIO),
                          rng=rng)
    if C is None:
        return None
    Cr, Cent, Chd = C
    Ra = np.asarray(R, float)
    skill = float(Ra.mean() - np.asarray(Cr, float).mean())
    se = math.sqrt(block_se(Ra, I_, HD) ** 2
                   + block_se(np.asarray(Cr, float), Cent, Chd) ** 2)
    return dict(n=len(Ra), E=float(Ra.mean()),
                t_E=float(M.block_bootstrap_t(Ra, I_, HD, 1)),
                skill=skill, t_skill=skill / se if se else np.nan,
                win=float((Ra > 0).mean()) * 100)


def main():
    t0 = time.time()
    print("DOES THE VENUE RESCUE ANYTHING? - re-pricing trades already made")
    print("=" * 92)
    print(__doc__.split("THE QUESTION, STATED FROM WHAT IS ALREADY MEASURED")[1]
          .split("WHAT THIS FILE ACTUALLY DOES")[0])

    gold = load_bidask_h1("XAUUSD")
    spr = float((gold["ask_close"] - gold["bid_close"]).median())

    print("=" * 92)
    print("1. GOLD - the same liquidity sweep, three cost levels")
    print("=" * 92)
    print(f"  {'cost basis':<38}{'round turn':>12}{'n':>7}{'E(R)':>10}"
          f"{'t_E':>8}{'skill':>10}")
    rows = []
    for lab, c in ((f"CFD, as measured in this repo", spr),
                   ("COMEX gold futures + fees", GOLD_FUTURES_COST),
                   ("zero cost (the upper bound)", 0.0)):
        r = run(reprice(gold, c), 0.001)
        if r is None:
            continue
        rows.append(dict(label=lab, cost=c, **r))
        print(f"  {lab:<38}${c:>11.4f}{r['n']:>7,}{r['E']:>+10.4f}"
              f"{r['t_E']:>+8.2f}{r['skill']:>+10.4f}")

    if len(rows) >= 2:
        cfd, fut = rows[0], rows[1]
        gain = fut["E"] - cfd["E"]
        print(f"\n  moving venue is worth {gain:+.4f}R per trade on this rule.")
        if fut["E"] < 0:
            short = -fut["E"]
            print(f"  It is not enough. The rule still loses {short:.4f}R per")
            print(f"  trade on an exchange, so the venue was never the whole")
            print(f"  problem - it was {gain/(gain+short)*100:.0f}% of it.")
        else:
            print(f"  It IS enough on this rule: the same trades that lose")
            print(f"  {cfd['E']:+.4f}R on the CFD make {fut['E']:+.4f}R on the exchange.")

    # ---- 2. every market, the same two cost levels ------------------------
    print("\n" + "=" * 92)
    print("2. EVERY MARKET - CFD cost against an exchange-grade cost")
    print("=" * 92)
    print("  Applying the SAME proportional reduction gold gets from moving to")
    print("  futures (3.2x) to every market, which is optimistic for the FX")
    print("  pairs - their CFD spreads are already close to interbank - and so")
    print("  is a best case rather than a forecast.")
    print(f"\n  {'market':<9}{'n':>8}{'E CFD':>10}{'E exch':>10}"
          f"{'skill':>10}{'exch > 0?':>11}")
    tot = []
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            continue
        s = float((df["ask_close"] - df["bid_close"]).median())
        a = run(df, TICKS.get(sym, 0.00001))
        b = run(reprice(df, s / 3.2), TICKS.get(sym, 0.00001))
        if a is None or b is None:
            continue
        tot.append(dict(symbol=sym, n=a["n"], e_cfd=a["E"], e_ex=b["E"],
                        skill=b["skill"]))
        print(f"  {sym:<9}{a['n']:>8,}{a['E']:>+10.4f}{b['E']:>+10.4f}"
              f"{b['skill']:>+10.4f}{'YES' if b['E'] > 0 else 'no':>11}")
    T = pd.DataFrame(tot)
    if len(T):
        pos = int((T.e_ex > 0).sum())
        print(f"\n  positive at exchange-grade cost: {pos} of {len(T)} markets")
        print(f"  mean E: CFD {T.e_cfd.mean():+.4f}  ->  exchange "
              f"{T.e_ex.mean():+.4f}")

    print("\n" + "=" * 92)
    print("VERDICT")
    print("=" * 92)
    if len(T) and int((T.e_ex > 0).sum()) >= 5:
        print("  The venue was a large part of the problem. A majority of")
        print("  markets flip positive on cost alone, with no change to the")
        print("  rule - which means the thing to change next is where the")
        print("  trades are sent, not what triggers them.")
    else:
        print("  The venue is worth real money and it is not enough. The")
        print("  measured edges here - +0.028R to +0.051R of drift-adjusted")
        print("  skill - are smaller than even an exchange-grade cost on")
        print("  this timeframe. That is the finding, and it does not move")
        print("  by testing more rules.")

    out = pathlib.Path(__file__).parent / "venue_change.csv"
    if len(T):
        T.to_csv(out, index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
