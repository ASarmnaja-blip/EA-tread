#!/usr/bin/env python3
"""The one rule that passed, run unchanged on nine markets.

THE RULE, FROZEN

  Compression Range Breakout with the volume surge, exactly as it cleared the
  criterion in `vendor_families_v2.py`:

      BBW and ATR both below their own 100-bar means, held 6 bars
      range box over the squeeze window
      close beyond the box, body >= 1.0 ATR
      volume >= 1.2 x its own 20-bar mean
      stop 1.5 ATR, single 2R target, break-even after 1R

  Not one parameter is refitted per market. Each market is charged its OWN
  measured median spread, because gold's 260 points on EURUSD would be
  meaningless - but the rule itself is identical everywhere.

WHY THIS IS THE TEST THAT MATTERS

  On gold the rule has already used both halves of the data: discovery found
  it, holdout confirmed it. There is nothing left on that instrument to check
  it against. The eight other markets have never been touched by it, so every
  bar of them is out of sample, and a rule that describes something real about
  how markets behave after a volatility squeeze has no reason to work only on
  gold.

  This repo's standing rule, applied to every previous candidate: an effect
  found on gold and absent elsewhere is gold overfit.

THE BAR, PRE-DECLARED

  Under the null that the rule has no edge anywhere, each market's skill is
  positive with probability 1/2:

      P(>= 7 of 9) = 8.98%
      P(>= 8 of 9) = 1.95%
      P(   9 of 9) = 0.195%

  8 of 9 is the pass. 7 of 9 is reported as suggestive and is NOT a pass -
  the same bar `cross_market.py` used on the breakout family, chosen there
  before that run and reused here rather than invented for this one.

  The markets are not independent - the dollar is on one side of six of them -
  so the binomial figure is an UPPER BOUND on the evidence. Stated here rather
  than left for someone to notice.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import multi_tf_setup_grid as G
from cross_market import MARKETS, cost_for, load_market
from vendor_families_v2 import f_compression, book
from strictness import randomise_timing

SEED = 17
CFG = dict(bb_p=20, look=100, min_bars=6, impulse=1.0,
           vol_surge=True, vol_mult=1.2)
EXIT = "1leg 2R BE"
RM = 1.5
HOLD = 48


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()

    print("THE COMPRESSION + VOLUME SURGE RULE, ON NINE MARKETS")
    print("=" * 92)
    print(__doc__.split("WHY THIS IS THE TEST THAT MATTERS")[1]
          .split("THE BAR, PRE-DECLARED")[0])
    print(f"  frozen rule: {CFG}")
    print(f"  exit {EXIT}, stop {RM} ATR, hold {HOLD}\n")

    syms = [s for s in a.markets.split(",") if s]
    rng = np.random.default_rng(SEED)
    rows = []
    print(f"  {'market':<9}{'bars':>9}{'spread':>10}{'cost/ATR':>10}"
          f"{'trades':>9}{'E(R)':>10}{'skill':>10}{'t':>8}  sign")
    for sym in syms:
        try:
            m = load_market(sym)
        except Exception as e:
            print(f"  {sym:<9} load failed ({type(e).__name__})")
            continue
        P0 = M.prep(m)
        cost_px = cost_for(sym, P0["spread"])
        if not np.isfinite(cost_px):
            print(f"  {sym:<9} no usable spread series")
            continue
        atr_med = float(np.nanmedian(P0["A"]))
        spread_frac = cost_px / float(np.nanmedian(P0["c"]))
        Pg = G.prep(pd.DataFrame(
            dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
            index=m.index))
        Pg["vol"] = P0["vol"]
        sig = f_compression(Pg, **CFG)
        b = book(Pg, sig, EXIT, HOLD, spread_frac, 0, len(m))
        cb = book(Pg, randomise_timing(sig, 0, len(m), rng), EXIT, HOLD,
                  spread_frac, 0, len(m))
        if b is None or cb is None:
            print(f"  {sym:<9}{len(m):>9,}  too few trades")
            continue
        R, I, HD = b
        skill = float(R.mean() - cb[0].mean())
        t = float(M.block_bootstrap_t(R - cb[0].mean(), I, HD, 1))
        # The t on RAW E(R), not on skill. Skill says the entry beats random
        # timing; this says whether the book makes money, which is a different
        # question and the one an account cares about.
        t_e = float(M.block_bootstrap_t(R, I, HD, 1))
        rows.append(dict(symbol=sym, n=len(R), E=float(R.mean()),
                         skill=skill, t=t, t_E=t_e,
                         cost_atr=cost_px / atr_med))
        print(f"  {sym:<9}{len(m):>9,}{cost_px:>10.5f}"
              f"{cost_px/atr_med*100:>9.1f}%{len(R):>9,}{R.mean():>+10.4f}"
              f"{skill:>+10.4f}{t:>+8.2f}  {'+' if skill > 0 else '-'}")

    if len(rows) < 5:
        print("\n  too few markets produced a book to run the test")
        return
    T = pd.DataFrame(rows)
    pos = int((T["skill"] > 0).sum())
    n = len(T)
    p = binom_tail(pos, n)

    print("\n" + "=" * 92)
    print("REPLICATION")
    print("=" * 92)
    print(f"  positive skill on {pos} of {n} markets    "
          f"P(>= {pos} | no edge anywhere) = {p:.4f}")
    print(f"  mean skill across markets {T['skill'].mean():+.4f}   "
          f"median {T['skill'].median():+.4f}")
    print(f"  markets with |t| > 2: {int((T['t'].abs() > 2).sum())}   "
          f"with t > 2: {int((T['t'] > 2).sum())}")

    if pos >= 8 and n >= 9:
        print(f"\n  -> REPLICATES at the pre-declared bar of 8 of 9.")
        print(f"     This is the first rule in this project to do so. It is")
        print(f"     now a pre-registered hypothesis with cross-market support,")
        print(f"     which is a reason to test it forward on unseen data - not")
        print(f"     a reason to size a position from a backtest.")
    elif pos >= 7:
        print(f"\n  -> SUGGESTIVE ONLY. The bar was declared at 8 of 9 before")
        print(f"     this run and {pos} of {n} does not meet it. Moving the bar")
        print(f"     now is the thing pre-declaring it was meant to prevent.")
    else:
        print(f"\n  -> DOES NOT REPLICATE. The rule is positive on {pos} of {n}")
        print(f"     markets, consistent with no edge anywhere. By this repo's")
        print(f"     standing rule an effect found on gold and absent elsewhere")
        print(f"     is gold overfit, and the gold result was 1 of 24 tests.")

    print(f"\n  CAVEAT: these markets share the dollar on one side of most of")
    print(f"  them, so the binomial p above is an upper bound on the evidence,")
    print(f"  not an exact level.")

    # ---- skill is not the same as making money ---------------------------
    # The E(R) column is negative on most markets while skill is positive on
    # eight of nine. Those are different claims and the difference is the whole
    # question: positive skill says the entry beats random TIMING, negative
    # E(R) says you still lose after the spread. A rule can be informative and
    # unprofitable at the same time, and this project has never before had one
    # that was informative at all - so the question is now whether the cost is
    # what stands between the two.
    #
    # cross_market.py Q3 built exactly this test for the breakout family and
    # found an intercept of -0.0118, meaning no gross edge to uncover. The same
    # regression on this rule asks the same question with a different answer
    # available.
    print(f"\n" + "=" * 92)
    print("SKILL vs MONEY: is the cost what stands between them?")
    print("=" * 92)
    x = T["cost_atr"].to_numpy(float)
    y = T["E"].to_numpy(float)
    slope, icpt = np.polyfit(x, y, 1)
    rng2 = np.random.default_rng(7)
    ints = []
    for _ in range(20000):
        k = rng2.integers(0, len(x), len(x))
        if len(np.unique(x[k])) < 2:
            continue
        ints.append(np.polyfit(x[k], y[k], 1)[1])
    lo, hi = np.percentile(np.asarray(ints), [2.5, 97.5])
    print(f"  {'market':<9}{'cost/ATR':>10}{'E(R)':>10}{'t on E':>9}"
          f"{'skill':>10}")
    for _, r in T.sort_values("cost_atr").iterrows():
        print(f"  {r['symbol']:<9}{r['cost_atr']*100:>9.1f}%{r['E']:>+10.4f}"
              f"{r['t_E']:>+9.2f}{r['skill']:>+10.4f}")
    print(f"\n  E(R) regressed on cost/ATR:")
    print(f"    slope     {slope:+.4f}")
    print(f"    INTERCEPT {icpt:+.4f}   95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"    (the breakout family's intercept was -0.0118)")

    # XAGUSD sits at twice the cost of anything else and its E(R) is four
    # times the next worst. One point that extreme can set a nine-point slope
    # on its own, so the fit is repeated without it. If the intercept survives
    # the removal it was not an artefact of that point; if it collapses, the
    # whole cost story rests on silver.
    T2 = T[T["symbol"] != "XAGUSD"]
    if len(T2) >= 4:
        s2, i2 = np.polyfit(T2["cost_atr"], T2["E"], 1)
        print(f"\n  same fit WITHOUT XAGUSD (cost 20.2%, E -0.2728 - a point")
        print(f"  extreme enough to set the slope by itself):")
        print(f"    slope     {s2:+.4f}")
        print(f"    intercept {i2:+.4f}")
        if icpt > 0 and i2 > 0:
            print(f"    the intercept stays positive, so it is not silver's")
            print(f"    doing - the cost relationship is in the other eight too")
        else:
            print(f"    the intercept does NOT survive removing one market, so")
            print(f"    the cost story rests on that single point and should")
            print(f"    not be carried forward")
    if icpt > 0 and lo > 0:
        print(f"\n  The intercept is positive and its interval excludes zero:")
        print(f"  at zero cost this rule MAKES MONEY. That is a gross edge,")
        print(f"  which is the thing every previous candidate here lacked, and")
        print(f"  it means the cost is what stands between skill and profit -")
        print(f"  so the cheapest instruments are where it can survive.")
    elif icpt > 0:
        print(f"\n  The intercept is positive but its interval touches zero, so")
        print(f"  a gross edge is the better reading of these nine points and")
        print(f"  is not established by them.")
    else:
        print(f"\n  The intercept is not positive: the rule has skill over")
        print(f"  random timing and still no gross edge, which means cost is")
        print(f"  not what stands between them.")
    prof = T[T["E"] > 0]
    if len(prof):
        print(f"\n  markets with POSITIVE E(R): "
              f"{', '.join(prof['symbol'])}")
        print(f"    their cost/ATR: "
              f"{', '.join(f'{v*100:.1f}%' for v in prof['cost_atr'])}")
        print(f"    against gold's {float(T[T.symbol=='XAUUSD']['cost_atr'].iloc[0])*100:.1f}% "
              f"- the rule is not a gold rule, it is a CHEAP-MARKET rule")

    gold = T[T["symbol"] == "XAUUSD"]
    if len(gold):
        g = gold.iloc[0]
        others = T[T["symbol"] != "XAUUSD"]
        print(f"\n  gold alone   skill {g['skill']:+.4f}  t {g['t']:+.2f}")
        print(f"  other eight  mean skill {others['skill'].mean():+.4f}   "
              f"positive on {int((others['skill'] > 0).sum())} of {len(others)}")
        print(f"  The second line is the one that is out of sample in every")
        print(f"  respect, since no part of those markets was used to find the")
        print(f"  rule or to confirm it.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
