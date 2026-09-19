#!/usr/bin/env python3
"""Before building the sweep chain on M15/M5: could the result be MEASURED?

WHY THIS RUNS BEFORE ANY BACKTEST

  `dobby_setup01_sweep_chain.py` tested the four-stage chain - sweep, CHoCH,
  displacement, FVG limit entry - and did not fail for the usual reason. It
  failed for a rarer one: at the full depth the measured skill was +0.296 and
  the smallest effect the sample could DETECT was 0.64. The number was not
  disappointing, it was unmeasurable. 26,185 sweeps across 27 markets and two
  years left 217 positions, because each stage keeps only a fraction:

      sweep -> CHoCH        keeps  8-13%
      + displacement        keeps 79-85%
      + leaves an FVG       keeps 28-40%
      + stop inside 4 ATR   keeps 86-93%
      + limit gets filled   keeps 34-50%
                            ----------------
      end to end            keeps about 0.8%

  RESEARCH_FINDINGS recorded the consequence honestly: "the blocker is
  frequency, not a measured absence of edge - at 4 trades a year on H1 the
  question cannot be asked at all", and named minute data as the one thing
  that would change it.

  That data now exists in this repo. So the question is no longer "does the
  chain work" but "is there now enough of it to find out", and that question
  is answered by arithmetic BEFORE any backtest is run. Running the backtest
  first and discovering the sample was never adequate is how a noisy number
  gets mistaken for a finding.

THE ARITHMETIC

  The minimum detectable effect at 80% power, 5% two-sided, is

      MDE = (1.96 + 0.84) * sigma / sqrt(n) = 2.8 * sigma / sqrt(n)

  sigma is calibrated from the measured chain itself rather than assumed: that
  run reported MDE 0.64 at n = 217 and MDE 0.07 at n = 18,187, and both imply
  the same sigma, which is the consistency check printed below.

  Inverting it gives the sample a target MDE needs, and the observed trade
  RATE per timeframe turns that into YEARS. If the years required exceed the
  years available, the setup cannot be evaluated on this instrument no matter
  how good it is - and that is a reason not to build it, not a reason to build
  it and hope.

WHAT THIS DOES NOT DO

  It does not say the chain has an edge, and a sample large enough to measure
  one is not evidence that one exists. It only says whether an answer is
  reachable. Sample adequacy is a precondition for a test, never a result.
"""
import argparse, math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))

Z = 1.96 + 0.84                      # 80% power, 5% two-sided

# Measured on 27 futures, H1, 730 days by dobby_setup01_sweep_chain.py.
MEASURED = ((217, 0.64), (18_187, 0.07))

# End-to-end survival of the four-stage chain, from that run's own funnel.
KEEP_FULL = 0.008                    # sweep -> filled position
KEEP_NO_FVG = 0.008 / 0.34           # ablation: dropping stage 4 took 217->883


def sigma_from(n, mde):
    return mde * math.sqrt(n) / Z


def n_for(mde, sigma):
    return (Z * sigma / mde) ** 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="0.30,0.20,0.15,0.10")
    a = ap.parse_args()

    print("CAN THE SWEEP CHAIN BE MEASURED ON M15/M5?")
    print("=" * 78)
    print(__doc__.split("THE ARITHMETIC")[1].split("WHAT THIS DOES NOT DO")[0])

    sigmas = [sigma_from(n, m) for n, m in MEASURED]
    print(f"CALIBRATION of sigma from the measured run")
    for (n, m), s in zip(MEASURED, sigmas):
        print(f"  n={n:>7,}  MDE {m:.2f}  ->  sigma {s:.3f}")
    if abs(sigmas[0] - sigmas[1]) > 0.05 * max(sigmas):
        print("  the two disagree - the reported MDEs are not on one "
              "definition, so\n  everything below is unreliable")
        return
    sigma = float(np.mean(sigmas))
    print(f"  consistent -> sigma = {sigma:.3f} R per trade")
    print(f"  (wide because the exit is a 1R/2R/3R ladder, not a single "
          f"target)")

    # ---- how often the chain fires, per timeframe -------------------------
    # Sweeps scale with the number of bars. The H1 rate is measured; the rest
    # are that rate scaled by bars per year, which ASSUMES a sweep is equally
    # likely per bar at any timeframe. That assumption is optimistic - shorter
    # bars produce more marginal sweeps, not proportionally more real ones -
    # so every "years needed" figure below is a LOWER BOUND.
    print(f"\nTRADE RATE, gold alone")
    print(f"  measured: 27 markets x 2 years -> 217 trades = "
          f"{217/27/2:.2f} trades/market/year on H1")
    h1_rate = 217 / 27 / 2
    tfs = (("H1", 1), ("M15", 4), ("M5", 12), ("M1", 60))
    print(f"  {'tf':<5}{'bars x H1':>11}{'full chain':>13}{'no-FVG':>11}"
          f"   trades/year")
    rates = {}
    for nm, mult in tfs:
        full = h1_rate * mult
        nofvg = full * (KEEP_NO_FVG / KEEP_FULL)
        rates[nm] = (full, nofvg)
        print(f"  {nm:<5}{mult:>10}x{full:>13.1f}{nofvg:>11.1f}")

    # ---- years needed ------------------------------------------------------
    targets = [float(x) for x in a.targets.split(",")]
    print(f"\nYEARS OF GOLD NEEDED, and what is actually on disk")
    print(f"  H1 cache 2003-2026 = 23.7 years;  M1 cache 2019-2026 = 7.7 years")
    print(f"\n  {'MDE':>6}{'n needed':>11}", end="")
    for nm, _ in tfs[:3]:
        print(f"{nm + ' full':>11}{nm + ' noFVG':>12}", end="")
    print()
    for mde in targets:
        n = n_for(mde, sigma)
        print(f"  {mde:>6.2f}{n:>11,.0f}", end="")
        for nm, _ in tfs[:3]:
            full, nofvg = rates[nm]
            print(f"{n/full:>11,.0f}{n/nofvg:>12,.0f}", end="")
        print()
    print(f"  (columns are YEARS; M1 cache offers 7.7, H1 cache offers 23.7)")

    # ---- the verdict -------------------------------------------------------
    print(f"\nWHAT THIS SETTLES")
    best_mde = min(targets)
    n_need = n_for(best_mde, sigma)
    m5_full, m5_nofvg = rates["M5"]
    m15_full, m15_nofvg = rates["M15"]
    print(f"  To resolve a skill of {best_mde:.2f}R needs {n_need:,.0f} trades.")
    print(f"    M5, full chain     {n_need/m5_full:>8,.0f} years vs 7.7 "
          f"available  -> {'reachable' if n_need/m5_full <= 7.7 else 'NOT reachable'}")
    print(f"    M5, stage 4 dropped{n_need/m5_nofvg:>8,.0f} years vs 7.7 "
          f"available  -> {'reachable' if n_need/m5_nofvg <= 7.7 else 'NOT reachable'}")
    print(f"    M15, full chain    {n_need/m15_full:>8,.0f} years vs 7.7 "
          f"available  -> {'reachable' if n_need/m15_full <= 7.7 else 'NOT reachable'}")
    print(f"\n  A skill of {best_mde:.2f}R is itself a demanding target: the "
          f"largest\n  honestly-measured skill anywhere in this repo is "
          f"+0.051 at t=+1.89\n  (the liquidity sweep alone, n=18,187). A "
          f"chain that needed skill an\n  order of magnitude larger than its "
          f"own strongest component to be\n  visible is not a chain worth "
          f"sizing a test around.")
    # ---- what the data actually on disk can resolve ------------------------
    # The measured run reached 27 markets through Yahoo. This repo's own
    # Dukascopy cache holds 9 markets with real bid/ask at H1 over 23.7 years,
    # which is a different and in most ways better sample - real spreads
    # rather than mid, and ten times the history. So the honest question is
    # what THAT resolves, not what 27 Yahoo futures would.
    print(f"\nWHAT THE CACHE ON DISK ACTUALLY RESOLVES")
    for label, n_mkt, years, rate in (
            ("9 markets, H1, full chain", 9, 23.7, rates["H1"][0]),
            ("9 markets, H1, no FVG", 9, 23.7, rates["H1"][1]),
            ("gold only, M5, no FVG", 1, 7.7, rates["M5"][1]),
            ("gold only, M15, no FVG", 1, 7.7, rates["M15"][1])):
        n = n_mkt * years * rate
        mde = Z * sigma / math.sqrt(n)
        print(f"  {label:<28}n {n:>8,.0f}   MDE {mde:>5.2f}R")
    print(f"\n  Compare every MDE above against +0.051R, the largest skill this")
    print(f"  repo has ever measured honestly. The best available sample "
          f"resolves\n  about 0.19R - roughly FOUR TIMES COARSER than the "
          f"effect it would be\n  looking for. A test at that resolution "
          f"returns a number either way,\n  and the number means nothing.")

    print(f"\n  POOLING MARKETS is the lever that actually works, and it is the")
    print(f"  one the measured run already used: 27 markets multiply the rate "
          f"by 27,\n  which turns centuries into years. It also changes the "
          f"claim being\n  tested, from 'this works on gold' to 'this works', "
          f"and only the second\n  one was ever going to be checkable.")


if __name__ == "__main__":
    main()
