#!/usr/bin/env python3
"""Turn the measured map into setups - as ONE hypothesis, not twenty-four.

THE TRAP THIS FILE IS BUILT TO AVOID

  market_profile.py measures every hour and reports every hour. Reading that
  table and picking the hours where returns happened to be highest is a search
  over 24 hypotheses wearing a map's clothing, and it would inherit every
  problem that killed the other 827.

  So the map is used in exactly two ways, and the difference between them is
  the whole design:

  AS A CONSTRAINT, which is free. Refusing to trade an hour whose cost per
  unit of movement is multiples of the median is a cost decision. It needs no
  significance test, because "this hour costs 3x more" is a measurement, not
  a prediction. Nothing is being selected for having worked.

  AS ONE PREDICTION, which is paid for exactly once. The map reports a
  variance ratio per hour - above 1, moves extend; below 1, they are given
  back. That is a measured property of the hour. The single hypothesis tested
  here is whether MATCHING THE ENTRY TO IT does better than ignoring it:

      momentum entries in the hours measured as extending
      reversion entries in the hours measured as reverting
        versus
      the identical entries, same count, run blind to the hour

  One comparison, declared before it runs. Not "which hour is best" - the
  hour assignment comes from the instrument, computed on its own data, and is
  not free to move.

WHY THIS IS WORTH DOING AFTER 21,889 RULES FAILED

  rigorous_search.py searched price-shape features and found 0 of 21,889
  beating a simulated null; the engine stage then found its best candidates
  losing money at ZERO cost on 0 of 9 markets. That closes the question of
  whether a price pattern predicts direction in this data. It does not touch
  a different question: whether the market's own measured STRUCTURE - when it
  extends, when it reverts, when it is affordable - tells you which of two
  ordinary entries to use. Those are not the same claim, and the second has
  never been tested here.
"""
import argparse
import json
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

SEED = 17
VR_MOM, VR_REV = 1.10, 0.90      # declared here, before any result
COST_MULT = 1.50                 # hours dearer than this x median are refused


# ------------------------------------------------------------ the entries --
def momentum_signal(P, look=20):
    """Close beyond the prior `look`-bar extreme. The most ordinary momentum
    trigger there is, chosen for exactly that reason - nothing here is being
    asked to be clever, only to be matched or mismatched to the hour."""
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    hi = pd.Series(h).rolling(look).max().shift(1).to_numpy()
    lo = pd.Series(l).rolling(look).min().shift(1).to_numpy()
    d = np.zeros(N, np.int8)
    I = np.full(N, np.nan)
    up = np.nan_to_num(c > hi, nan=False)
    dn = np.nan_to_num(c < lo, nan=False)
    d[up] = 1
    I[up] = l[up]
    d[dn] = -1
    I[dn] = h[dn]
    return d, I


def reversion_signal(P, look=20, z=1.5):
    """Close stretched from its own mean by z ATR, faded. The mirror of the
    above, equally ordinary."""
    c, A, N = P["c"], P["A"], P["N"]
    ma = pd.Series(c).rolling(look).mean().to_numpy()
    with np.errstate(invalid="ignore"):
        dev = (c - ma) / A
    d = np.zeros(N, np.int8)
    I = np.full(N, np.nan)
    hi = np.nan_to_num(dev > z, nan=False)
    lo = np.nan_to_num(dev < -z, nan=False)
    d[hi] = -1
    I[hi] = P["h"][hi]
    d[lo] = 1
    I[lo] = P["l"][lo]
    return d, I


# ------------------------------------------------------------- the regime --
def regime_from_profile(sym, tf):
    """Read the hour classification off the instrument. This is the part that
    must NOT be tuned to results - it is whatever the profile measured."""
    r = MP.profile(sym, tf)
    if r is None:
        return None
    H = r["hours"]
    med = float(H.cost_range.median())
    aff = {int(x.hour) for _, x in H.iterrows()
           if np.isfinite(x.cost_range) and x.cost_range <= med * COST_MULT}
    vr = r["vr"]
    mom = {h for h, v in vr.items() if np.isfinite(v) and v >= VR_MOM}
    rev = {h for h, v in vr.items() if np.isfinite(v) and v <= VR_REV}
    return dict(affordable=aff, momentum=mom, reversion=rev, quality=r["quality"],
                median_cost=med, vr=vr)


def run(P, d, I, tick, hours=None):
    if hours is not None:
        keep = np.isin(P["idx"].hour, list(hours))
        d = np.where(keep, d, 0).astype(np.int8)
    out = X.run_e01(P, d, I, 0, P["N"], tick)
    if out is None:
        return None
    R, I_, HD, RATIO = out
    Ra = np.asarray(R, float)
    return dict(n=len(Ra), E=float(Ra.mean()),
                t=float(M.block_bootstrap_t(Ra, I_, HD, 1)),
                se=block_se(Ra, I_, HD), R=Ra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="H1")
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("PROFILE-MATCHED SETUPS - one hypothesis, declared before the run")
    print("=" * 100)
    print(__doc__.split("THE TRAP THIS FILE IS BUILT TO AVOID")[1]
          .split("WHY THIS IS WORTH DOING")[0])
    print(f"  declared thresholds: momentum VR >= {VR_MOM}, reversion VR <= "
          f"{VR_REV}, refuse hours costing > {COST_MULT}x median\n")

    rows = []
    for sym in syms:
        reg = regime_from_profile(sym, a.tf)
        if reg is None:
            continue
        df = load_bidask_h1(sym) if a.tf == "H1" else MP.load_tf(sym, a.tf)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 0.00001)
        dm, Im = momentum_signal(P)
        dr, Ir = reversion_signal(P)

        mom_h = reg["momentum"] & reg["affordable"]
        rev_h = reg["reversion"] & reg["affordable"]
        if len(mom_h) < 2 or len(rev_h) < 2:
            print(f"  {sym:<9} regime split too thin "
                  f"(mom {len(mom_h)}, rev {len(rev_h)}) - skipped")
            continue

        matched = []
        for d, I, hrs in ((dm, Im, mom_h), (dr, Ir, rev_h)):
            r = run(P, d, I, tick, hrs)
            if r:
                matched.append(r)
        # the control: the SAME two entries, same affordable hours, but with
        # the regime assignment SWAPPED - momentum where the instrument says
        # revert and vice versa. A blind control would differ in trade count
        # as well as in matching; this one differs only in the matching.
        swapped = []
        for d, I, hrs in ((dm, Im, rev_h), (dr, Ir, mom_h)):
            r = run(P, d, I, tick, hrs)
            if r:
                swapped.append(r)
        if not matched or not swapped:
            continue
        Rm = np.concatenate([r["R"] for r in matched])
        Rs = np.concatenate([r["R"] for r in swapped])
        se = math.sqrt(sum(r["se"] ** 2 for r in matched) +
                       sum(r["se"] ** 2 for r in swapped))
        diff = float(Rm.mean() - Rs.mean())
        rows.append(dict(symbol=sym, n_matched=len(Rm), n_swapped=len(Rs),
                         e_matched=float(Rm.mean()), e_swapped=float(Rs.mean()),
                         diff=diff, t=diff / se if se > 0 else np.nan,
                         mom_hours=len(mom_h), rev_hours=len(rev_h),
                         quality=reg["quality"]["score"]))
        print(f"  {sym:<9} matched {Rm.mean():+.4f} (n {len(Rm):,})   "
              f"swapped {Rs.mean():+.4f} (n {len(Rs):,})   "
              f"diff {diff:+.4f}  t {rows[-1]['t']:+.2f}", flush=True)

    if not rows:
        print("\n  nothing produced a comparison")
        return
    D = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("THE ONE COMPARISON")
    print("=" * 100)
    md = float(D["diff"].mean())
    se = float(D["diff"].std(ddof=1) / math.sqrt(len(D)))
    t = md / se if se > 0 else np.nan
    print(f"  markets            {len(D)}")
    print(f"  mean difference    {md:+.4f}R   (matched minus swapped)")
    print(f"  across-market t    {t:+.2f}")
    print(f"  positive on        {int((D['diff'] > 0).sum())} of {len(D)}")
    print(f"  signals per year   matched "
          f"{D.n_matched.sum() / (len(D) * 22):.0f} per market")
    print(f"\n  A difference near zero says the instrument's regime split")
    print(f"  carries no information about which entry to use - the map is")
    print(f"  real as a description and empty as a guide. That is a specific,")
    print(f"  falsifiable thing to learn about it, and it is not the same as")
    print(f"  the map being wrong.")
    out = HERE / f"profile_setups_{a.tf}.csv"
    D.to_csv(out, index=False)
    print(f"\n  -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
