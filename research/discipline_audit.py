#!/usr/bin/env python3
"""Turn the harsher statistics on this project's own discipline layer.

THE CLAIM BEING AUDITED

  change_ledger.py has judged 823 hypotheses against

      floor = sqrt(2 * ln k)

  and that floor is the reason almost everything here is dead. It is a
  serious correction and most projects have nothing like it. This asks
  whether it is the RIGHT number, using the repo's own measurements rather
  than an assumption.

  Two things are wrong with it, and they pull in opposite directions.

  ONE - sqrt(2 ln N) is the asymptote, not the expectation. The exact
  first-order value (Bailey and Lopez de Prado) at N = 823 is 3.199 against
  the asymptote's 3.664, verified against Monte Carlo in
  test_overfit_stats.py. On this axis the ledger has been too HARSH.

  TWO - the floor assumes trial statistics have unit variance. This repo
  measured its own: search_751_results.csv holds 324 configurations whose
  discovery t has sd 1.475 and holdout t sd 1.398. The expected maximum
  scales linearly with that dispersion. On this axis the ledger has been far
  too LENIENT, and this axis is the larger of the two.

  Whether the over-dispersion is real effects or correlated trades inflating
  each t does not change the arithmetic. If it is real effects, the maximum
  of the trials is genuinely larger. If it is correlation, the null itself is
  wider than assumed. Either way the bar a winner must clear is set by the
  measured dispersion, not by a nominal 1.0.

AND ONE THING THE LEDGER CANNOT SEE AT ALL

  Every test here judges a rule against a null. None judges the SEARCH. PBO
  by combinatorially symmetric cross-validation asks: across every symmetric
  split of the sample, how often is the in-sample winner below median out of
  sample? That is a property of the selection procedure, and a procedure can
  be broken while every individual rule in it is innocent.
"""
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import xauusd_1000_setups as X
from overfit_stats import (asymptotic_max_t, deflated_sharpe_from_returns,
                           expected_max_t, min_backtest_length, pbo_cscv)
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

HERE = pathlib.Path(__file__).parent
N_BLOCKS = 16


def measured_dispersion():
    f = HERE / "search_751_results.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    td, th = d["t_d"].dropna(), d["t_h"].dropna()
    return dict(n=len(d), sd_d=float(td.std(ddof=1)), sd_h=float(th.std(ddof=1)),
                max_d=float(td.max()), max_h=float(th.max()),
                mean_d=float(td.mean()))


def build_matrix():
    """A real configuration space: every implemented template x every market.

    The rows are contiguous time blocks and the cells are mean R per trade in
    that block, so the matrix is exactly what a search over this repo's own
    rule space would have had in front of it."""
    cols, names = [], []
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            continue
        P = X.prep(df, 60)
        tmpl = X.make_templates(P)
        # Blocks are cut on BAR INDEX, not on timestamps. run_e01 already
        # returns the entry bar, so this needs no timezone handling at all -
        # and a bar-index cut is what "contiguous slice of the sample" means
        # for an engine that iterates bars.
        bounds = np.linspace(0, P["N"], N_BLOCKS + 1)[1:-1]
        for name in X.TEMPLATES_IMPLEMENTED:
            if name not in tmpl:
                continue
            dvec, Ivec = tmpl[name]()
            R, I_, _, _ = X.run_e01(P, dvec, Ivec, 0, P["N"],
                                    TICKS.get(sym, 0.00001))
            if len(R) < N_BLOCKS * 4:
                continue
            b = np.searchsorted(bounds, np.asarray(I_, float))
            col = np.full(N_BLOCKS, np.nan)
            Ra = np.asarray(R, float)
            for kb in range(N_BLOCKS):
                m = b == kb
                if m.sum() >= 3:
                    col[kb] = float(Ra[m].mean())
            cols.append(col)
            names.append(f"{sym}:{name}")
    if not cols:
        return None, None
    M = np.column_stack(cols)
    # Drop CONFIGURATIONS with a gap, never time blocks: CSCV compares
    # configurations against each other within each split, so a column with a
    # hole would be ranked against columns that have none. Dropping rows
    # instead would throw away the very periods that distinguish them.
    ok = np.isfinite(M).all(axis=0)
    return M[:, ok], [n for n, f in zip(names, ok) if f]


def main():
    t0 = time.time()
    print("DISCIPLINE AUDIT - the harsher statistics, on this repo's own work")
    print("=" * 92)
    print(__doc__.split("THE CLAIM BEING AUDITED")[1]
          .split("AND ONE THING THE LEDGER")[0])

    led = json.loads((HERE / "change_ledger.json").read_text())
    entries = led if isinstance(led, list) else led.get("entries", [])
    # k lives inside each entry's `result`, written at the moment the result
    # was recorded - not at the top level of the entry.
    ks = [(e.get("result") or {}).get("k_at_test") for e in entries
          if isinstance(e, dict)]
    k = max([x for x in ks if isinstance(x, int)] or [len(entries)])

    print("=" * 92)
    print("1. IS THE FLOOR THE RIGHT NUMBER?")
    print("=" * 92)
    D = measured_dispersion()
    if D is None:
        print("  search_751_results.csv missing - cannot measure dispersion")
        return
    print(f"  measured on {D['n']} configurations in search_751_results.csv:")
    print(f"    discovery t   mean {D['mean_d']:+.3f}   sd {D['sd_d']:.3f}   "
          f"max {D['max_d']:+.3f}")
    print(f"    holdout   t                sd {D['sd_h']:.3f}   "
          f"max {D['max_h']:+.3f}")
    print(f"\n  Under the null both sd would be 1.0. Neither is.\n")

    repo = asymptotic_max_t(k)
    exact = expected_max_t(k)
    corrected = expected_max_t(k, D["sd_d"])
    print(f"  at the ledger's current k = {k}:")
    print(f"    sqrt(2 ln k), what the ledger uses today    {repo:.3f}")
    print(f"    exact E[max] at the assumed sigma = 1       {exact:.3f}")
    print(f"    exact E[max] at the MEASURED sigma {D['sd_d']:.3f}    "
          f"{corrected:.3f}   <- the honest floor")
    print(f"\n  The ledger's floor is {(repo/corrected-1)*100:+.0f}% relative to"
          f" the corrected one.")
    print(f"  It has been too lenient by {corrected - repo:.2f} of a t all along.")

    print(f"\n  What that changes, concretely: the best discovery t in the")
    print(f"  751-representative search was {D['max_d']:+.3f}, which CLEARS the")
    print(f"  ledger's {repo:.2f} floor and would have been reported as surviving")
    print(f"  the multiple-testing correction. Against the corrected floor of")
    print(f"  {corrected:.2f} it does not. The holdout best, {D['max_h']:+.3f}, fails too.")

    print("\n" + "=" * 92)
    print("2. RE-JUDGING EVERY RECORDED RESULT AT THE CORRECTED FLOOR")
    print("=" * 92)
    rows = []
    for e in entries:
        r = (e.get("result") or {}) if isinstance(e, dict) else {}
        t = r.get("t_stat")
        if t is None:
            continue
        kk = r.get("k_at_test") or k
        if t is None or not np.isfinite(t):
            continue
        old = asymptotic_max_t(kk)
        new = expected_max_t(kk, D["sd_d"])
        rows.append(dict(id=e.get("id", "?"), t=t, k=kk, old=old, new=new,
                         was=r.get("verdict", "?"),
                         old_ok=abs(t) > old, new_ok=abs(t) > new))
    if rows:
        A = pd.DataFrame(rows)
        flipped = A[A.old_ok & ~A.new_ok]
        print(f"  {len(A)} recorded results carry a t-statistic.")
        print(f"  cleared the old floor: {int(A.old_ok.sum())}      "
              f"clear the corrected floor: {int(A.new_ok.sum())}")
        if len(flipped):
            print(f"\n  Results that PASSED the old floor and FAIL the new one:")
            for _, r in flipped.iterrows():
                print(f"    {r['id']:<44} t {r['t']:+.2f}  "
                      f"old {r['old']:.2f}  new {r['new']:.2f}  ({r['was']})")
        gained = A[~A.old_ok & A.new_ok]
        if len(gained):
            print(f"\n  And one artefact worth naming rather than hiding: "
                  f"{len(gained)} entry")
            print(f"  now 'clears' a floor it previously failed, because at very")
            print(f"  small k the exact E[max] is far BELOW the asymptote "
                  f"(at k=2, 0.77 vs 1.18).")
            for _, r in gained.iterrows():
                print(f"    {r['id']:<44} t {r['t']:+.2f}  k {r['k']}  "
                      f"old {r['old']:.2f} -> new {r['new']:.2f}")
            print(f"  That is not a rehabilitation. The t is negative, so it")
            print(f"  'clears' only on absolute value - the ledger's own")
            print(f"  convention - and it failed the improvement margin anyway.")
            print(f"  The correction is meant for large k; at k of 1 or 2 there")
            print(f"  is no multiple-testing problem to correct for.")
        if not len(flipped):
            print(f"\n  No recorded verdict changes. Every result this project")
            print(f"  accepted or rejected lands the same way at the corrected")
            print(f"  floor - not because the floor was right, but because")
            print(f"  nothing came close enough to it for the difference to")
            print(f"  matter. The correction bites on the SEARCHES, where the")
            print(f"  best-of-many t was within the gap, not on the registered")
            print(f"  single hypotheses.")

    print("\n" + "=" * 92)
    print("3. PBO - AUDITING THE SEARCH ITSELF, WHICH NOTHING HERE HAS DONE")
    print("=" * 92)
    print("  Building the real configuration matrix: every implemented")
    print("  template on every market, scored in contiguous time blocks.")
    M, names = build_matrix()
    if M is None or M.shape[1] < 8:
        print("  could not build a usable matrix")
        return
    print(f"  matrix: {M.shape[0]} time blocks x {M.shape[1]} configurations")
    pbo, lam = pbo_cscv(M, n_splits=min(N_BLOCKS, M.shape[0]),
                        max_combos=20000, return_detail=True)
    print(f"\n  PBO = {pbo:.3f}")
    print(f"  (calibration in test_overfit_stats.py put the per-matrix sd of")
    print(f"   this statistic at 0.175 on data with NO edge, so read this as")
    print(f"   {pbo:.2f} +/- 0.17 and not as three decimal places)")
    print(f"  median logit  {np.median(lam):+.3f}")
    if pbo > 0.5:
        print(f"\n  Above 0.5: picking the in-sample best from this rule space")
        print(f"  is worse than picking at random. The SELECTION PROCEDURE is")
        print(f"  overfit regardless of any individual rule's merits, and that")
        print(f"  is a verdict no test in this repo was able to reach.")
    else:
        print(f"\n  At or below 0.5, so the selection procedure is not itself")
        print(f"  pathological - the in-sample winner does carry SOME rank")
        print(f"  information out of sample. That is a weaker statement than")
        print(f"  'the winner makes money', which the holdout runs already")
        print(f"  answered no to.")

    print("\n" + "=" * 92)
    print("4. HOW MUCH DATA WOULD A SEARCH THIS SIZE EVEN NEED?")
    print("=" * 92)
    print(f"  {'claimed annual Sharpe':<26}{'years required':>16}")
    for sr in (0.5, 1.0, 1.5, 2.0):
        print(f"  {sr:<26.1f}{min_backtest_length(k, sr):>16.1f}")
    have = 22.0
    lo, hi = 0.05, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if min_backtest_length(k, mid) > have:
            lo = mid
        else:
            hi = mid
    min_sr = (lo + hi) / 2
    print(f"\n  This project has about {have:.0f} years of gold H1, and after")
    print(f"  {k} hypotheses the SMALLEST annual Sharpe it can still")
    print(f"  establish on that sample is {min_sr:.2f}.")
    print(f"\n  That is the number to sit with. A realistic retail edge in")
    print(f"  gold or FX, after the costs this project has spent a year")
    print(f"  measuring, is a Sharpe somewhere around 0.3 to 0.8. Most of")
    print(f"  that range is now BELOW what {have:.0f} years can demonstrate at this")
    print(f"  trial count - a Sharpe of 0.5 would need "
          f"{min_backtest_length(k, 0.5):.0f} years, which is")
    print(f"  {min_backtest_length(k, 0.5) - have:.0f} more than exist.")
    print(f"\n  So the search has already outrun its data for the effect sizes")
    print(f"  actually on offer. This is not an argument for testing more")
    print(f"  carefully; it is an argument that additional hypotheses on this")
    print(f"  sample cost more than they can return. Every new k raises the")
    print(f"  bar and the sample does not grow.")

    print("\n" + "=" * 92)
    print("5. DEFLATED SHARPE ON THE BEST CONFIGURATION IN THE MATRIX")
    print("=" * 92)
    mu = np.nanmean(M, axis=0)
    bi = int(np.nanargmax(mu))
    series = M[:, bi]
    sr, dsr = deflated_sharpe_from_returns(series, n_trials=M.shape[1],
                                           sigma_trials=D["sd_d"])
    sr_naive, dsr_naive = deflated_sharpe_from_returns(series, n_trials=1)
    print(f"  best of {M.shape[1]} configurations: {names[bi]}")
    print(f"    block-level Sharpe        {sr:+.4f}  over {len(series)} blocks")
    print(f"    naive P(true SR > 0)      {dsr_naive:.4f}   "
          f"(one trial, what a single backtest reports)")
    print(f"    DEFLATED P(true SR > 0)   {dsr:.4f}   "
          f"(deflated for {M.shape[1]} trials at sigma {D['sd_d']:.2f})")
    print(f"\n  The gap between those two numbers is the entire content of")
    print(f"  this file. The same book, the same trades, the same sixteen")
    print(f"  blocks - read once as a standalone result and once as the")
    print(f"  winner of a search that was actually run.")

    out = HERE / "discipline_audit.csv"
    pd.DataFrame({"config": names,
                  **{f"block{i}": M[i] for i in range(M.shape[0])}}
                 ).to_csv(out, index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s   matrix -> {out.name}")


if __name__ == "__main__":
    main()
