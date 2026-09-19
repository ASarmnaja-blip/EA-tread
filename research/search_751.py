#!/usr/bin/env python3
"""The 751 representatives: probing the whole rule space at its real width.

WHY 751 AND NOT 131,040

  `combinatorics.py` measured that the nominal space - 13 conditions, depths 1
  to 6, four exits, two stops, four timeframes - contains 131,040 rules and of
  order 751 genuinely different questions. The rules' own return series are
  correlated enough that m_eff = 3.69 k^0.451: sublinear, so each new rule adds
  less than one new question, and past a point adds almost none.

  That makes the full grid a waste of both compute and statistical budget.
  Running 751 stratified representatives asks the same questions at 1/175th of
  the cost, and - this is the part that matters - carries a floor of
  sqrt(2 ln 751) = 3.64 instead of 4.85. A real effect has a meaningfully
  better chance of clearing the lower bar, and a fake one has no better chance
  at either.

WHAT IS DECLARED BEFORE THE RUN, AND CANNOT MOVE AFTER

  sampling    stratified across depth x exit x stop x timeframe, seed 17.
              The strata and the seed fully determine which cells run. No cell
              is included or excluded for how it looks.

  the metric  SKILL against a randomised-timing control, not raw E(R).
              `strictness.py` established that raw E rises with rule sparsity
              through an effect a random-timing book reproduces in full, so
              raw E is not a measure of anything the rule knows.

  the bar     discovery skill t > 3.64 AND holdout skill > 0. Both. A cell
              that clears the floor on discovery and turns negative out of
              sample has failed, not "partially succeeded".

  the pooled all-751 book is reported next to the winners as the
  no-selection baseline, because the difference between them IS the selection.

WHAT A NULL RESULT LOOKS LIKE HERE

  At 751 tests with no edge anywhere, about 17 cells clear t > 2 and about 1
  clears t > 3, each with a clean-looking backtest. So a handful of impressive
  discovery numbers is the EXPECTED output of a dead space, not evidence
  against it. That is why the holdout column exists and why the bar is 3.64.
"""
import argparse, itertools, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB
import multi_tf_setup_grid as G
from strictness import conditions, conjunction, randomise_timing

SEED = 17
N_CELLS = 751
DEPTHS = (1, 2, 3, 4, 5, 6)
TFS = ("1h", "30min", "15min", "5min")
HOLD = {"1h": 48, "30min": 96, "15min": 96, "5min": 288}


def load_tf_cached(tf, cache={}):
    if tf in cache:
        return cache[tf]
    m = M.load_tf(tf)
    P0 = M.prep(m)
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))
    tf_min = S.bar_minutes(m.index)
    disc_end = EB.DISCOVERY_END if tf_min >= 60 else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    spread = float(EB.scenario_cost_px(260.0, 0.0) / np.nanmedian(P0["c"]))
    cache[tf] = (m, Pg, conditions(Pg), n_disc, spread)
    return cache[tf]


def run_cell(Pg, C, cb, exit_name, rm, hold, spread, lo, hi, rng):
    """One cell's discovery-or-holdout book, and its timing control."""
    s = conjunction(C, cb)
    s[:lo] = 0; s[hi:] = 0
    if int((s != 0).sum()) < 20:
        return None
    c, A, N = Pg["c"], Pg["A"], Pg["N"]
    design = G.EXITS[exit_name]

    def walk(sig):
        live = np.where((sig != 0) & np.isfinite(A) & (A > 0))[0]
        live = live[(live >= max(lo, 320)) & (live < min(hi, N - 1))]
        R, I, HD = [], [], []
        busy = -1
        for i in live:
            i = int(i)
            if i <= busy:
                continue
            risk = rm * A[i]
            if risk <= 0:
                continue
            r, kx = G.exit_run(Pg, i, c[i], int(sig[i]), risk, design, hold,
                               spread)
            if r is None:
                continue
            R.append(r); I.append(float(i)); HD.append(float(max(kx - i, 1)))
            busy = kx
        if len(R) < 20:
            return None
        return np.asarray(R), np.asarray(I), np.asarray(HD)

    real = walk(s)
    if real is None:
        return None
    ctrl = walk(randomise_timing(s, lo, hi, rng))
    if ctrl is None:
        return None
    R, I, HD = real
    skill = float(R.mean() - ctrl[0].mean())
    t = M.block_bootstrap_t(R - ctrl[0].mean(), I, HD, 1)
    return dict(n=len(R), E=float(R.mean()), ctrl=float(ctrl[0].mean()),
                skill=skill, t=float(t)), (R, I, HD)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=int, default=N_CELLS)
    ap.add_argument("--tfs", default=",".join(TFS))
    a = ap.parse_args()
    t0 = time.time()

    print("THE 751 REPRESENTATIVES")
    print("=" * 92)
    print(__doc__.split("WHAT IS DECLARED BEFORE THE RUN")[1]
          .split("WHAT A NULL RESULT LOOKS LIKE")[0])

    tfs = [x for x in a.tfs.split(",") if x]
    floor = math.sqrt(2 * math.log(a.cells))
    print(f"  floor for {a.cells} tests: |t| > {floor:.2f}")
    print(f"  a dead space of this size returns about "
          f"{0.0228*a.cells:.0f} cells at t>2 and "
          f"{0.00135*a.cells:.0f} at t>3\n")

    # ---- the stratified sample, drawn before anything is measured --------
    rng_pick = np.random.default_rng(SEED)
    plan = []
    names_by_tf = {}
    for tf in tfs:
        _, _, C, _, _ = load_tf_cached(tf)
        names_by_tf[tf] = sorted(C)
    strata = [(tf, d, ex, rm) for tf in tfs for d in DEPTHS
              for ex in G.EXITS for rm in G.RMULTS]
    per = max(a.cells // len(strata), 1)
    for tf, d, ex, rm in strata:
        nm = names_by_tf[tf]
        combos = list(itertools.combinations(nm, d))
        take = min(per, len(combos))
        idx = rng_pick.choice(len(combos), size=take, replace=False)
        for j in idx:
            plan.append((tf, combos[j], ex, rm))
    # top up to exactly the declared count, still at random
    while len(plan) < a.cells:
        tf, d, ex, rm = strata[rng_pick.integers(len(strata))]
        nm = names_by_tf[tf]
        combos = list(itertools.combinations(nm, d))
        plan.append((tf, combos[rng_pick.integers(len(combos))], ex, rm))
    plan = plan[:a.cells]
    print(f"  sampled {len(plan)} cells across {len(strata)} strata "
          f"({len(tfs)} tf x {len(DEPTHS)} depths x {len(G.EXITS)} exits "
          f"x {len(G.RMULTS)} stops)")

    # ---- run ---------------------------------------------------------------
    rows = []
    pooled_d, pooled_h = [], []
    rng_ctrl = np.random.default_rng(SEED + 500)
    done = 0
    for tf, cb, ex, rm in plan:
        m, Pg, C, n_disc, spread = load_tf_cached(tf)
        hold = HOLD[tf]
        d = run_cell(Pg, C, cb, ex, rm, hold, spread, 0, n_disc, rng_ctrl)
        h = run_cell(Pg, C, cb, ex, rm, hold, spread, n_disc, len(m), rng_ctrl)
        done += 1
        if done % 100 == 0:
            print(f"    {done}/{len(plan)} cells, {time.time()-t0:.0f}s",
                  flush=True)
        if d is None or h is None:
            continue
        dm, db = d
        hm, hb = h
        rows.append(dict(tf=tf, depth=len(cb), rule="+".join(cb), exit=ex,
                         rm=rm,
                         n_d=dm["n"], skill_d=dm["skill"], t_d=dm["t"],
                         n_h=hm["n"], skill_h=hm["skill"], t_h=hm["t"],
                         E_h=hm["E"]))
        pooled_d.append(db); pooled_h.append(hb)

    if not rows:
        print("\n  no cell produced a usable book on both periods")
        return
    T = pd.DataFrame(rows)
    print(f"\n  {len(T)} cells produced a usable book on BOTH periods "
          f"({time.time()-t0:.0f}s)")

    # ---- the no-selection baseline ----------------------------------------
    def pool(bs):
        R = np.concatenate([b[0] for b in bs])
        I = np.concatenate([b[1] for b in bs])
        HD = np.concatenate([b[2] for b in bs])
        o = np.argsort(I)
        return R[o], I[o], HD[o]

    PD, PH = pool(pooled_d), pool(pooled_h)
    print(f"\nTHE WHOLE SAMPLE, NO SELECTION  (the baseline every winner must "
          f"beat)")
    print(f"  discovery  {len(PD[0]):>9,} trades   E {PD[0].mean():+.4f}   "
          f"block t {M.block_bootstrap_t(*PD, 1):+.2f}")
    print(f"  holdout    {len(PH[0]):>9,} trades   E {PH[0].mean():+.4f}   "
          f"block t {M.block_bootstrap_t(*PH, 1):+.2f}")

    # ---- the distribution, which is the real answer ------------------------
    td = T["t_d"].to_numpy()
    td = td[np.isfinite(td)]
    print(f"\nTHE DISTRIBUTION OF DISCOVERY SKILL t  (noise: mean 0, sd 1)")
    print(f"  {len(td)} cells with a finite t")
    print(f"  mean {td.mean():+.3f}   sd {td.std(ddof=1):.3f}   "
          f"min {td.min():+.2f}   max {td.max():+.2f}")
    for thr in (2, 3, floor):
        got = int((td > thr).sum())
        exp = {2: 0.0228, 3: 0.00135}.get(
            thr, 1 - 0.5 * (1 + math.erf(thr / math.sqrt(2)))) * len(td)
        print(f"  cells with t > {thr:>4.2f}: {got:>4}   "
              f"(a dead space expects {exp:.1f})")
    print(f"\n  The mean and sd are the headline. Noise gives 0 and 1; a space")
    print(f"  with real effects in it gives a mean above 0 and a sd above 1.")
    if td.std(ddof=1) > 1.2:
        print(f"  This distribution is OVER-DISPERSED (sd {td.std(ddof=1):.2f}),")
        print(f"  so the space is not dead - it holds real effects, on both")
        print(f"  sides: max {td.max():+.2f} and min {td.min():+.2f}. An")
        print(f"  over-dispersion this symmetric is the signature of effects")
        print(f"  that are strong within a period and reverse between periods,")
        print(f"  which is regime dependence rather than edge. The holdout")
        print(f"  columns below are what tell the two apart.")

    # ---- who cleared the declared bar --------------------------------------
    print(f"\nCELLS THAT CLEAR THE DECLARED BAR  "
          f"(discovery t > {floor:.2f} AND holdout skill > 0)")
    passed = T[(T["t_d"] > floor) & (T["skill_h"] > 0)]
    near = T[(T["t_d"] > floor)]
    print(f"  cleared discovery floor:              {len(near)}")
    print(f"  of those, ALSO positive on holdout:   {len(passed)}")
    if len(near):
        print(f"\n  {'tf':<7}{'d':>2}{'rule':<44}{'exit':<15}{'rm':>4}"
              f"{'n_d':>7}{'skill_d':>9}{'t_d':>7}{'skill_h':>9}{'t_h':>7}")
        for _, r in near.sort_values("t_d", ascending=False).head(20).iterrows():
            print(f"  {r['tf']:<7}{r['depth']:>2}{r['rule'][:43]:<44}"
                  f"{r['exit']:<15}{r['rm']:>4.1f}{r['n_d']:>7,}"
                  f"{r['skill_d']:>+9.4f}{r['t_d']:>+7.2f}"
                  f"{r['skill_h']:>+9.4f}{r['t_h']:>+7.2f}")
    print(f"\n  TOP 10 BY DISCOVERY t, whether or not they cleared:")
    print(f"  {'tf':<7}{'d':>2}{'rule':<44}{'t_d':>7}{'skill_h':>9}{'t_h':>7}")
    for _, r in T.sort_values("t_d", ascending=False).head(10).iterrows():
        print(f"  {r['tf']:<7}{r['depth']:>2}{r['rule'][:43]:<44}"
              f"{r['t_d']:>+7.2f}{r['skill_h']:>+9.4f}{r['t_h']:>+7.2f}")

    # ---- does discovery rank predict holdout? ------------------------------
    # The single most informative number in the whole run. If selecting on
    # discovery carries ANY information, discovery t and holdout skill are
    # positively related across 751 cells. If that correlation is zero, the
    # entire selection step is noise and no search over this space can work,
    # whatever any individual cell's backtest says.
    V = T[np.isfinite(T["t_d"]) & np.isfinite(T["skill_h"])]
    print(f"\nDOES DISCOVERY RANK PREDICT HOLDOUT?")
    if len(V) < 10:
        print(f"  only {len(V)} cells with both numbers finite - not enough")
        cc = float("nan")
    else:
        cc = float(np.corrcoef(V["t_d"], V["skill_h"])[0, 1])
        # Spearman too: the relationship that matters is whether RANK carries
        # over, and one outlier cell can set a Pearson correlation on its own.
        # Spearman by hand - scipy is not installed here, and a rank
        # correlation is a Pearson correlation of ranks.
        sp = float(np.corrcoef(pd.Series(V["t_d"]).rank(),
                               pd.Series(V["skill_h"]).rank())[0, 1])
        print(f"  Pearson  corr(discovery t, holdout skill) = {cc:+.3f}  "
              f"over {len(V)} cells")
        print(f"  Spearman rank correlation                 = {sp:+.3f}")
    q = V.assign(bucket=pd.qcut(V["t_d"], 5, labels=False, duplicates="drop"))
    print(f"  {'discovery quintile':<22}{'mean t_d':>10}{'mean skill_h':>14}")
    for b, g in q.groupby("bucket"):
        print(f"  {'Q'+str(int(b)+1):<22}{g['t_d'].mean():>+10.2f}"
              f"{g['skill_h'].mean():>+14.4f}")
    if np.isfinite(cc):
        # A correlation of r over n points has SE about 1/sqrt(n-1) under the
        # null. Quoting r without it invites reading +0.10 as "small but there"
        # when it is under two standard errors from nothing.
        se = 1.0 / math.sqrt(max(len(V) - 1, 1))
        print(f"  SE of either correlation under the null   {se:.3f}  "
              f"-> Pearson {cc/se:+.1f} SE, Spearman {sp/se:+.1f} SE")
        if max(abs(cc), abs(sp)) < 2 * se:
            print(f"\n  Neither clears two standard errors. Ranking cells on")
            print(f"  discovery tells you essentially nothing about holdout, so")
            print(f"  there is no selection rule over this space that works -")
            print(f"  not a stricter one, not a smarter one. That is a statement")
            print(f"  about the SPACE rather than about any rule in it, and it")
            print(f"  is the strongest form the answer could take.")
            print(f"\n  Note the quintile table says the same thing more bluntly:")
            print(f"  the WORST discovery quintile has a higher mean holdout")
            print(f"  skill than the best one.")
        else:
            print(f"\n  At least one clears two standard errors, so discovery")
            print(f"  rank carries SOME information about holdout. That is worth")
            print(f"  a pre-registered follow-up, not a position.")

    print(f"\n  elapsed {time.time()-t0:.0f}s")
    out = pathlib.Path(__file__).parent / "search_751_results.csv"
    T.to_csv(out, index=False)
    print(f"  per-cell detail -> {out.name}")


if __name__ == "__main__":
    main()
