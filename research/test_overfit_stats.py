#!/usr/bin/env python3
"""Calibration for overfit_stats.py, on data whose answer is known.

WHY THIS FILE IS NOT OPTIONAL

  A statistic used to reject strategies is itself a measuring instrument, and
  this project has already been burned once by an instrument nobody checked -
  the one-bar look-ahead in run_e01 that produced the best result this repo
  ever recorded and had to be retracted. It was caught by a calibration test
  on data with no edge, not by inspection.

  So every function in overfit_stats.py is run here against a case where the
  answer is known by construction:

    - pure noise: PBO must come out near 0.5, because on a matrix with no
      real differences the in-sample winner is a coin flip out of sample
    - a planted edge: PBO must come out well below 0.5
    - the expected-maximum formula must match a Monte Carlo of the same N
    - DSR with one trial and no skew must reproduce the ordinary one-sided
      normal p-value
    - the inverse normal must invert the normal
"""
import math
import sys

import numpy as np

from overfit_stats import (asymptotic_max_t, deflated_sharpe,
                           deflated_sharpe_from_returns, expected_max_t,
                           min_backtest_length, norm_cdf, norm_ppf, pbo_cscv)

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('   ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


def test_normal():
    print("\n1. the inverse normal actually inverts the normal")
    worst = max(abs(norm_cdf(norm_ppf(p)) - p)
                for p in (1e-5, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999, 1 - 1e-6))
    check("norm_ppf round-trips to <1e-9", worst < 1e-9, f"max err {worst:.2e}")
    check("norm_ppf(0.975) ~ 1.959964",
          abs(norm_ppf(0.975) - 1.959963985) < 1e-6)


def test_expected_max():
    print("\n2. expected maximum matches a Monte Carlo of the same size")
    rng = np.random.default_rng(7)
    for n in (100, 823, 5000):
        sim = float(rng.standard_normal((4000, n)).max(axis=1).mean())
        got = expected_max_t(n)
        check(f"N={n}: formula {got:.3f} vs simulated {sim:.3f}",
              abs(got - sim) < 0.06, f"diff {got-sim:+.3f}")
    print("\n   and the repo's asymptote is NOT the same number:")
    for n in (100, 823):
        print(f"     N={n:<5} exact {expected_max_t(n):.3f}   "
              f"sqrt(2lnN) {asymptotic_max_t(n):.3f}   "
              f"asymptote is {asymptotic_max_t(n)-expected_max_t(n):+.3f} high")
    check("asymptote overstates E[max] at N=823",
          asymptotic_max_t(823) > expected_max_t(823))


def test_dispersion_scaling():
    print("\n3. over-dispersed trials raise the bar proportionally")
    rng = np.random.default_rng(11)
    n, sg = 500, 1.475
    sim = float((rng.standard_normal((4000, n)) * sg).max(axis=1).mean())
    got = expected_max_t(n, sg)
    check(f"sigma={sg}: formula {got:.3f} vs simulated {sim:.3f}",
          abs(got - sim) < 0.09, f"diff {got-sim:+.3f}")
    check("scaling is linear in sigma",
          abs(expected_max_t(n, 2.0) - 2 * expected_max_t(n, 1.0)) < 1e-9)


def test_dsr_reduces_to_pvalue():
    print("\n4. DSR with one trial and normal returns = the ordinary p-value")
    n = 500
    for sr in (0.02, 0.05, 0.10):
        t = sr * math.sqrt(n)
        classic = norm_cdf(t)
        got = deflated_sharpe(sr, n, 0.0, 3.0, n_trials=1)
        check(f"sr={sr}: DSR {got:.4f} vs normal p {classic:.4f}",
              abs(got - classic) < 0.02, f"diff {got-classic:+.4f}")


def test_dsr_penalises_trials_and_tails():
    print("\n5. DSR falls when trials rise, and when the tail is long-right")
    n, sr = 500, 0.10
    a = deflated_sharpe(sr, n, 0.0, 3.0, n_trials=1)
    b = deflated_sharpe(sr, n, 0.0, 3.0, n_trials=823)
    c = deflated_sharpe(sr, n, 0.0, 3.0, n_trials=823, sigma_trials=1.475)
    check(f"more trials lowers DSR ({a:.3f} -> {b:.3f})", b < a)
    check(f"over-dispersion lowers it further ({b:.3f} -> {c:.3f})", c < b)
    neg = deflated_sharpe(sr, n, -2.5, 12.0, n_trials=1)
    pos = deflated_sharpe(sr, n, +2.5, 12.0, n_trials=1)
    check(f"NEGATIVE skew lowers DSR ({a:.3f} -> {neg:.3f})", neg < a)
    check(f"POSITIVE skew raises it ({a:.3f} -> {pos:.3f})", pos > a)
    print("     The direction here corrects an assumption worth stating: a")
    print("     long-RIGHT-tail book, which is what an 8R target produces, is")
    print("     skew > 0, and that makes its Sharpe MORE reliable, not less -")
    print("     the fat right tail inflates the denominator, so the naive")
    print("     Sharpe understates. The penalty in this formula is for")
    print("     NEGATIVE skew: many small gains and rare large losses, the")
    print("     shape of a martingale or an option-selling book. Setup D's")
    print("     tail was therefore never the statistical problem with it.")


def test_pbo_noise():
    print("\n6. PBO on pure noise must average 0.5 - ACROSS MATRICES")
    print("     A single PBO is one number computed from one dataset, and all")
    print("     its splits share that dataset, so it is far noisier than the")
    print("     thousands of combinations suggest. That is measured here")
    print("     rather than assumed, because it sets how a PBO may be read.")
    vals = []
    for s in range(25):
        rng = np.random.default_rng(100 + s)
        vals.append(pbo_cscv(rng.standard_normal((320, 40)),
                             n_splits=16, max_combos=2000, seed=5))
    v = np.array(vals)
    se = v.std(ddof=1) / math.sqrt(len(v))
    check(f"mean PBO {v.mean():.3f} within 3 SE of 0.5",
          abs(v.mean() - 0.5) < 3 * se, f"SE {se:.3f}")
    check(f"per-matrix sd is large ({v.std(ddof=1):.3f}) - PBO needs error bars",
          v.std(ddof=1) > 0.05)
    print(f"     single-matrix range was [{v.min():.3f}, {v.max():.3f}] on data")
    print(f"     with NO edge at all. Any PBO reported below must carry this")
    print(f"     +/-{v.std(ddof=1):.2f} with it or it will be over-read.")


def test_pbo_real_edge():
    print("\n7. PBO with one genuinely better config must fall well below 0.5")
    rng = np.random.default_rng(4)
    T, N = 320, 40
    M = rng.standard_normal((T, N))
    M[:, 7] += 0.45                      # a real, persistent edge
    p = pbo_cscv(M, n_splits=16, max_combos=4000, seed=5)
    check(f"planted edge: PBO {p:.3f} < 0.2", p < 0.2)


def test_pbo_fitted_noise():
    print("\n8. PBO must CONDEMN a config that only wins in the first half")
    vals = []
    for s in range(15):
        rng = np.random.default_rng(200 + s)
        T, N = 320, 40
        M = rng.standard_normal((T, N))
        # net ZERO over the full sample - superb early, equally bad late.
        # An earlier draft of this test added +1.2 early and only -0.3 late,
        # which left the config genuinely the best overall; PBO correctly
        # said so, and the test was wrong rather than the statistic.
        M[:T // 2, 3] += 1.2
        M[T // 2:, 3] -= 1.2
        vals.append(pbo_cscv(M, n_splits=16, max_combos=2000, seed=5))
    v = np.array(vals)
    check(f"regime-fitted config: mean PBO {v.mean():.3f} > 0.55", v.mean() > 0.55)
    print("     (a rule that works only in the period it was found in is the")
    print("      exact failure this repo's holdout split can miss when the")
    print("      split point is chosen once)")


def test_minbtl():
    print("\n9. minimum backtest length behaves")
    a = min_backtest_length(100, 1.0)
    b = min_backtest_length(1000, 1.0)
    c = min_backtest_length(100, 2.0)
    check(f"more trials needs more data ({a:.1f}y -> {b:.1f}y)", b > a)
    check(f"a bigger claimed Sharpe needs less ({a:.1f}y -> {c:.1f}y)", c < a)
    print(f"     at 823 trials, a claimed Sharpe of 1.0 needs "
          f"{min_backtest_length(823, 1.0):.1f} years to mean anything")


def test_returns_wrapper():
    print("\n10. the return-stream wrapper agrees with the scalar form")
    rng = np.random.default_rng(21)
    r = rng.standard_normal(600) * 0.8 + 0.05
    sr, dsr = deflated_sharpe_from_returns(r, n_trials=1)
    z = (r - r.mean()) / r.std(ddof=1)
    manual = deflated_sharpe(sr, len(r), float((z**3).mean()),
                             float((z**4).mean()), n_trials=1)
    check(f"wrapper matches manual ({dsr:.6f} vs {manual:.6f})",
          abs(dsr - manual) < 1e-9)


def main():
    print("CALIBRATION - overfit_stats.py against data with known answers")
    print("=" * 78)
    for f in (test_normal, test_expected_max, test_dispersion_scaling,
              test_dsr_reduces_to_pvalue, test_dsr_penalises_trials_and_tails,
              test_pbo_noise, test_pbo_real_edge, test_pbo_fitted_noise,
              test_minbtl, test_returns_wrapper):
        f()
    print("\n" + "=" * 78)
    if FAILS:
        print(f"{len(FAILS)} CHECK(S) FAILED: " + ", ".join(FAILS))
        print("These statistics must not be used until this passes.")
        sys.exit(1)
    print("all checks passed - the statistics return the right answer on data")
    print("where the right answer is known, so they may be used on data where")
    print("it is not.")


if __name__ == "__main__":
    main()
