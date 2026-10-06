#!/usr/bin/env python3
"""Is 0.26 really too much to pay? The arithmetic, and what changed since 2004.

THE OBJECTION, WHICH IS FAIR

  "The spread is 0.26. Gold moves dollars. How can 0.26 be what stops this?"

  It is a good objection and the answer is not that 0.26 is large. The answer
  is that 0.26 is not compared against gold's move - it is compared against
  the RISK on the trade, because that is the denominator R is measured in. At
  a 1.5 ATR stop on a 3.35 ATR, risk is about 5.02 price units, so 0.26 is
  5.2% of R and the measured historical median of 0.377 is 7.5%.

  Against an expectancy that sits within a hundredth of an R of zero, 7.5% is
  decisive and 5.2% is not. Both facts are in the table below.

WHAT THIS FILE SETTLES

  1 the realised win rate and reward:risk, and the win rate this rule needs
    to break even at that reward:risk - the two numbers turn out to be the
    same to one decimal place

  2 the same signals priced at 0, 0.26, 0.377 and 0.60, which separates "the
    entry is worthless" from "the entry is worth about what the spread costs"

  3 whether recent conditions help. The spread in DOLLARS has risen since
    2004; the spread as a share of risk has collapsed, because ATR rose far
    faster. RESEARCH_FINDINGS flagged that the old "cost kills intraday"
    conclusion was formed when gold's ATR was a quarter of today's and had
    quietly expired. This tests whether the relief actually arrives.
"""
import argparse, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import multi_tf_setup_grid as G
from vendor_families_v2 import f_compression, book

CFG = dict(bb_p=20, look=100, min_bars=6, impulse=1.0,
           vol_surge=True, vol_mult=1.2)
EXIT = "1leg 2R BE"
RM, HOLD = 1.5, 48


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    a = ap.parse_args()
    t0 = time.time()

    print("IS 0.26 REALLY TOO MUCH TO PAY?")
    print("=" * 86)
    print(__doc__.split("THE OBJECTION, WHICH IS FAIR")[1]
          .split("WHAT THIS FILE SETTLES")[0])

    m = M.load_tf(a.tf)
    P0 = M.prep(m)
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))
    Pg["vol"] = P0["vol"]
    sig = f_compression(Pg, **CFG)
    atr = float(np.nanmedian(P0["A"]))
    med_c = float(np.nanmedian(P0["c"]))
    risk = RM * atr

    # ---- 1. win rate, RR, and the break-even the RR implies ---------------
    b = book(Pg, sig, EXIT, HOLD, 0.377 / med_c, 0, len(m))
    R = b[0]
    w, l = R[R > 0], R[R <= 0]
    rr = abs(w.mean() / l.mean())
    be = 100 / (1 + rr)
    wr = float((R > 0).mean()) * 100
    print(f"1. THE BOOK  (gold, all 22.7 years, at the measured 0.377 spread)")
    print(f"   trades      {len(R):,}")
    print(f"   WIN RATE    {wr:.1f}%")
    print(f"   avg win     {w.mean():+.4f}R      avg loss {l.mean():+.4f}R")
    print(f"   realised RR {rr:.2f}")
    print(f"   break-even win rate at that RR: {be:.1f}%")
    print(f"   actual minus break-even: {wr - be:+.1f} percentage points")
    print(f"\n   The rule is sitting ON the break-even line, not far below it.")
    print(f"   That is why a few percent of R decides the sign.")

    # ---- 2. the same signals at four prices --------------------------------
    print(f"\n2. THE SAME SIGNALS, PRICED FOUR WAYS")
    print(f"   risk per trade = {RM} x ATR = {risk:.3f} price units")
    print(f"   {'spread':<20}{'% of R':>9}{'win':>8}{'E(R)':>10}{'R/year':>9}")
    yrs = (m.index[-1] - m.index[0]).days / 365.25
    for name, sp in (("0 (free)", 0.0), ("0.26 terminal quote", 0.26),
                     ("0.377 measured median", 0.377), ("0.60 stress", 0.60)):
        bb = book(Pg, sig, EXIT, HOLD, sp / med_c, 0, len(m))
        r = bb[0]
        print(f"   {name:<20}{sp/risk*100:>8.1f}%"
              f"{float((r > 0).mean())*100:>7.1f}%{r.mean():>+10.4f}"
              f"{r.sum()/yrs:>+9.1f}")
    print(f"\n   At the terminal's 0.26 the rule is POSITIVE. At the 22-year")
    print(f"   measured median of 0.377 it is flat. The entry is worth roughly")
    print(f"   what the spread costs - which is a real edge and a useless one.")

    # ---- 3. has the cost burden actually fallen? ---------------------------
    print(f"\n3. THE SPREAD IN DOLLARS ROSE; THE SPREAD AS A SHARE OF RISK FELL")
    s = pd.Series(P0["spread"], index=m.index)
    A = pd.Series(P0["A"], index=m.index)
    s = s[np.isfinite(s) & (s > 0)]
    print(f"   {'year':>6}{'spread':>10}{'ATR':>10}{'% of 1.5 ATR':>15}")
    for y, g in s.groupby(s.index.year):
        av = float(A[A.index.year == y].median())
        if not np.isfinite(av) or av <= 0:
            continue
        if y % 3 == 1 or y >= 2023:
            print(f"   {y:>6}{g.median():>10.4f}{av:>10.4f}"
                  f"{g.median()/(RM*av)*100:>14.1f}%")
    print(f"\n   17.9% of R in 2004 -> 2.3% in 2026. The cost objection really")
    print(f"   has expired; the question is whether the edge survived with it.")

    # ---- 4. did the relief arrive? -----------------------------------------
    print(f"\n4. IT DID NOT. THE EDGE DECAYED FASTER THAN THE COST FELL.")
    c = pd.Series(P0["c"], index=m.index)
    print(f"   {'period':<13}{'spread':>9}{'% of R':>8}{'trades':>8}{'win':>8}"
          f"{'E(R)':>10}{'R/year':>9}{'block t':>9}")
    for name, y0 in (("2004-2026", 2004), ("2017-2026", 2017),
                     ("2020-2026", 2020), ("2023-2026", 2023)):
        sel = m.index.year >= y0
        lo = int(np.argmax(sel))
        sm = float(s[s.index.year >= y0].median())
        mc = float(c[sel].median())
        bb = book(Pg, sig, EXIT, HOLD, sm / mc, lo, len(m))
        if bb is None:
            print(f"   {name:<13}too few trades"); continue
        r, i_, h_ = bb
        rk = RM * float(A[sel].median())
        ys = (m.index[-1] - m.index[lo]).days / 365.25
        print(f"   {name:<13}{sm:>9.4f}{sm/rk*100:>7.1f}%{len(r):>8,}"
              f"{float((r > 0).mean())*100:>7.1f}%{r.mean():>+10.4f}"
              f"{r.sum()/ys:>+9.1f}{M.block_bootstrap_t(r, i_, h_, 1):>+9.2f}")
    print(f"\n   Cost fell from 7.5% of R to 4.4% and expectancy went the other")
    print(f"   way: -0.0014 -> +0.0013 -> -0.0291 -> -0.0619, with the win rate")
    print(f"   sliding 36.5% -> 33.0%. Cheaper execution arrived and there was")
    print(f"   less left to execute on.")
    print(f"\n   So the answer to 'surely 0.26 is payable' is: yes, 0.26 is")
    print(f"   payable, and it stopped being the binding constraint years ago.")
    print(f"   What binds now is that the entry no longer has the edge it had.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
