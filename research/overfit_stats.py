#!/usr/bin/env python3
"""The three overfitting statistics this project's discipline layer lacks.

WHAT IS ALREADY HERE, AND WHERE IT STOPS

  change_ledger.py judges a candidate against

      floor = sqrt(2 * ln k)

  which is the asymptotic expected maximum of k draws from a STANDARD normal.
  That is the right shape of correction and it is the reason this project has
  killed almost everything. But it carries two assumptions that this repo's
  own data contradicts:

    1. It assumes the trial statistics have unit variance. search_751.py
       measured the discovery t across 324 configurations and got
       sd = 1.475, with the holdout t at 1.398. Both are far from 1. When
       trials are over-dispersed - whether from real effects or from
       correlated trades inflating each t - the expected maximum scales
       with that dispersion, and a floor built for sd = 1 is too low.

    2. sqrt(2 ln k) is the asymptotic limit, not the expectation. The exact
       first-order expression (Bailey and Lopez de Prado) is

           E[max] = sigma * [ (1-g) * Z(1 - 1/N) + g * Z(1 - 1/(N*e)) ]

       with g the Euler-Mascheroni constant. At N = 823 the asymptote gives
       3.664 while the exact value at sigma = 1 gives 3.199 - so the repo is
       CONSERVATIVE on this axis and LENIENT on the first one, and the two do
       not cancel.

  Neither assumption is visible from inside the ledger, which is why they
  have gone unexamined for 823 hypotheses.

WHAT THIS ADDS

  deflated_sharpe   The Deflated Sharpe Ratio. Corrects an observed Sharpe
                    for the number of trials, the dispersion of trial
                    Sharpes, AND the skew and kurtosis of the return stream -
                    the last of which matters here because this project's
                    best-looking rules are long-right-tail books where a
                    normal-theory t is not the right null.

  pbo_cscv          Probability of Backtest Overfitting by Combinatorially
                    Symmetric Cross-Validation. Asks a question no test in
                    this repo asks: across every symmetric split of the
                    sample, how often does the configuration that looked best
                    in-sample land BELOW the median out-of-sample? Above 0.5
                    means the selection procedure itself is overfit,
                    independent of whether any individual rule is.

  min_backtest_length  How many years of data are required before a search
                    over N configurations can produce a given Sharpe without
                    it being the expected outcome of noise.

CALIBRATION IS NOT OPTIONAL

  Every function here is checked against synthetic data in
  test_overfit_stats.py, where the answer is known by construction: on pure
  noise PBO must come out near 0.5 and DSR near 0.5, and the expected-maximum
  formula must match a Monte Carlo of the same size. A statistic that has not
  been shown to return the right answer on data with no edge is exactly the
  kind of instrument that produced the look-ahead result this project had to
  retract.
"""
import math
from itertools import combinations

import numpy as np

EULER_GAMMA = 0.5772156649015329


# ------------------------------------------------------------------ normal --
def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """Inverse standard normal CDF, Acklam's rational approximation.

    Written out rather than imported because scipy is not a dependency of
    this project and a bad inverse-normal would silently mis-set every floor
    computed from it."""
    if not (0.0 < p < 1.0):
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > 1 - pl:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
             ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / \
            (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    # one Halley refinement - the raw approximation is good to ~1e-9 but the
    # refinement makes it exact enough that the floor is never the weak link
    e = norm_cdf(x) - p
    u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - u / (1 + x * u / 2)


# ------------------------------------------------- expected maximum of N ----
def expected_max_t(n_trials, sigma_trials=1.0):
    """Exact first-order E[max] of n_trials draws, Bailey / Lopez de Prado.

    sigma_trials is the CROSS-SECTIONAL standard deviation of the trial
    statistics, which is 1 only if the trials are independent draws from the
    null. Measure it; do not assume it."""
    n = max(int(n_trials), 2)
    return sigma_trials * ((1 - EULER_GAMMA) * norm_ppf(1 - 1.0 / n)
                           + EULER_GAMMA * norm_ppf(1 - 1.0 / (n * math.e)))


def asymptotic_max_t(n_trials):
    """sqrt(2 ln N) - what change_ledger.py uses today, kept for comparison."""
    return math.sqrt(2 * math.log(max(int(n_trials), 2)))


# --------------------------------------------------- Deflated Sharpe ratio --
def deflated_sharpe(sr, n_obs, skew=0.0, kurtosis=3.0,
                    n_trials=1, sigma_trials=1.0):
    """P(true Sharpe > 0) after deflating for selection and non-normality.

    sr is the Sharpe PER OBSERVATION (not annualised); n_obs the number of
    observations behind it. kurtosis is the raw fourth moment, so 3 is normal.
    Returns a probability: below 0.95 means the observed Sharpe is not
    distinguishable from the best of n_trials noise draws."""
    if n_obs < 3 or not np.isfinite(sr):
        return float("nan")
    sr_star = expected_max_t(n_trials, sigma_trials) / math.sqrt(n_obs) \
        if n_trials > 1 else 0.0
    var = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if var <= 0:
        return float("nan")
    z = (sr - sr_star) * math.sqrt(n_obs - 1) / math.sqrt(var)
    return norm_cdf(z)


def deflated_sharpe_from_returns(r, n_trials=1, sigma_trials=1.0):
    """Same, computing sr / skew / kurtosis from a return stream directly."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return float("nan"), float("nan")
    sd = r.std(ddof=1)
    if sd <= 0:
        return float("nan"), float("nan")
    sr = r.mean() / sd
    z = (r - r.mean()) / sd
    sk = float((z ** 3).mean())
    ku = float((z ** 4).mean())
    return sr, deflated_sharpe(sr, len(r), sk, ku, n_trials, sigma_trials)


# ------------------------------- Probability of Backtest Overfitting (PBO) --
def pbo_cscv(perf, n_splits=16, max_combos=20000, seed=17, return_detail=False):
    """PBO by Combinatorially Symmetric Cross-Validation.

    perf is a (T x N) matrix: T time slices down, N configurations across,
    each cell a performance number for that configuration in that slice.

    The sample is cut into n_splits contiguous blocks. For every way of
    choosing half the blocks as in-sample, the configuration with the best
    in-sample performance is found, and its RANK among all configurations
    out-of-sample is recorded. PBO is the fraction of splits where that rank
    falls below the median - that is, where picking the in-sample winner was
    worse than picking at random.

    PBO > 0.5 condemns the SELECTION PROCEDURE, not any one configuration:
    it says the thing that looked best did so for reasons that did not
    survive to the other half of the data."""
    M = np.asarray(perf, float)
    if M.ndim != 2 or M.shape[1] < 2:
        return float("nan")
    T, N = M.shape
    S = int(n_splits) - (int(n_splits) % 2)
    if S < 4 or T < S:
        return float("nan")
    edges = np.array_split(np.arange(T), S)
    combos = list(combinations(range(S), S // 2))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:
        pick = rng.choice(len(combos), max_combos, replace=False)
        combos = [combos[i] for i in pick]
    lam = []
    for cb in combos:
        ins = np.concatenate([edges[i] for i in cb])
        oos = np.concatenate([edges[i] for i in range(S) if i not in cb])
        mu_i = np.nanmean(M[ins], axis=0)
        mu_o = np.nanmean(M[oos], axis=0)
        if not np.isfinite(mu_i).any() or not np.isfinite(mu_o).any():
            continue
        best = int(np.nanargmax(mu_i))
        # rank of the in-sample winner among all configs, out of sample
        order = np.argsort(np.argsort(mu_o))          # 0 = worst
        w = (order[best] + 1) / (N + 1)
        w = min(max(w, 1e-6), 1 - 1e-6)
        lam.append(math.log(w / (1 - w)))
    if not lam:
        return float("nan")
    lam = np.array(lam)
    pbo = float((lam <= 0).mean())
    if return_detail:
        return pbo, lam
    return pbo


# ---------------------------------------------------- minimum backtest len --
def min_backtest_length(n_trials, target_sr_annual, obs_per_year=252):
    """Years of data needed before a search over n_trials can show this Sharpe
    without it being the expected result of noise.

    Inverts E[max SR] = expected_max_t(N) / sqrt(T). Below this length, a
    backtest reporting target_sr_annual is uninformative no matter how clean
    it looks."""
    if target_sr_annual <= 0:
        return float("inf")
    e = expected_max_t(n_trials)
    sr_obs = target_sr_annual / math.sqrt(obs_per_year)
    return (e / sr_obs) ** 2 / obs_per_year
