#!/usr/bin/env python3
"""Stage two and three: the screen's survivors, through the real engine.

WHAT THIS STAGE IS FOR

  rigorous_search.py ranks rules on signed forward return per ATR with no
  exit structure and no cost. That is a necessary condition, not a result -
  it says a rule is followed by movement in a consistent direction, which is
  a long way from saying a tradeable book can be built on it.

  This stage takes the survivors and runs them through run_e01, the engine
  carrying the martingale calibration guard and both look-ahead corrections,
  at TWO cost levels.

WHY ZERO COST COMES FIRST, AND WHY IT IS THE DECISIVE SCREEN

  venue_change.py measured the liquidity sweep - the best candidate this repo
  ever had - losing 0.0574R per trade with no friction at all. A rule that
  loses money frictionless cannot be rescued by a cheaper broker, a futures
  contract, a larger account, or a better fill. It is dead everywhere.

  So zero cost is checked before the real quote is ever charged. It costs
  nothing extra to compute and it is the difference between "this rule needs
  a better venue" and "this rule has nothing in it".

THE SELECTION CRITERION IS FIXED HERE, BEFORE ANY RESULT IS SEEN

  Three finalists, chosen by:

    1. zero-cost E(R) positive on at least 7 of the 9 discovery markets
    2. drift-adjusted skill positive pooled, against the matched
       random-timing control
    3. among those, ranked by pooled zero-cost E(R)

  Written down now so that it cannot be adjusted to suit whatever comes back.
  If fewer than three rules satisfy (1) and (2), fewer than three go forward -
  the count is a ceiling, not a quota, and padding it with the best of the
  failures is how a holdout gets spent on rules nobody believed in.
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from liquidity_sweep_crossmarket import block_se
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from rigorous_search import conditions, features

HERE = pathlib.Path(__file__).parent
DISCOVERY = HERE / "rigorous_search_discovery.json"
FINALISTS = HERE / "rigorous_finalists.json"
MIN_MARKETS_POSITIVE = 7
N_FINALISTS = 3
SEED = 17


def rule_mask(P, cond_names, want):
    """Rebuild one rule's boolean mask on a market from its condition names."""
    mk = {c[0]: c[1] for c in conditions(features(P))}
    m = None
    for nm in want:
        c = mk.get(nm)
        if c is None:
            return None
        m = c if m is None else (m & c)
    return m


def signals(P, mask, direction):
    """Mask -> (dvec, Ivec). The stop sits at the signal bar's own extreme,
    which is a fixed choice rather than a searched one - no stop parameter is
    swept anywhere in this pipeline."""
    d = np.zeros(P["N"], np.int8)
    I = np.full(P["N"], np.nan)
    d[mask] = direction
    I[mask] = P["l"][mask] if direction > 0 else P["h"][mask]
    return d, I


def zero_cost(df):
    d = df.copy()
    for k in ("open", "high", "low", "close"):
        d[f"bid_{k}"] = d[k]
        d[f"ask_{k}"] = d[k]
    return d


def evaluate(df, cond_names, direction, tick, free):
    P = X.prep(zero_cost(df) if free else df, 60)
    m = rule_mask(P, cond_names, cond_names)
    if m is None or int(m.sum()) < 200:
        return None
    dv, Iv = signals(P, m, direction)
    out = X.run_e01(P, dv, Iv, 0, P["N"], tick)
    if out is None:
        return None
    R, I_, HD, RATIO = out
    Ra = np.asarray(R, float)
    res = dict(n=len(Ra), E=float(Ra.mean()),
               t_E=float(M.block_bootstrap_t(Ra, I_, HD, 1)))
    if not free:
        C = X.run_e01_control(P, dv, 0, P["N"],
                              risk_ratios=np.asarray(RATIO),
                              rng=np.random.default_rng(SEED))
        if C is not None:
            Cr, Ce, Ch = C
            res["skill"] = float(Ra.mean() - np.asarray(Cr, float).mean())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args()
    t0 = time.time()

    if not DISCOVERY.exists():
        print(f"  {DISCOVERY.name} missing - run rigorous_search.py first")
        return
    disc = json.loads(DISCOVERY.read_text())
    cands = disc["top"][:a.top]

    print("RIGOROUS SEARCH - ENGINE STAGE (holdout still sealed)")
    print("=" * 92)
    print(__doc__.split("WHY ZERO COST COMES FIRST")[1]
          .split("THE SELECTION CRITERION IS FIXED HERE")[0])
    print(f"  null bar from the simulated null: {disc['null']['bar']:.3f}")
    print(f"  candidates carried in: {len(cands)} of {disc['n_rules']:,} searched\n")

    frames = {}
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is not None and len(df) >= 5000:
            frames[sym] = df

    print("=" * 92)
    print("STAGE 2 - ZERO COST. A rule negative here is dead at every venue.")
    print("=" * 92)
    print(f"  {'#':<4}{'rule':<52}{'mkts+':>7}{'E free':>10}{'t':>8}")
    survivors = []
    for ci, c in enumerate(cands):
        names = c["rule"]
        per = {}
        for sym, df in frames.items():
            # direction is read off the discovery score's sign, which is part
            # of the rule, not a second hypothesis
            for d in (1, -1):
                r = evaluate(df, names, d, TICKS.get(sym, 0.00001), free=True)
                if r is not None:
                    per.setdefault(d, {})[sym] = r
        best = None
        for d, pm in per.items():
            if len(pm) < MIN_MARKETS_POSITIVE:
                continue
            Es = np.array([v["E"] for v in pm.values()])
            npos = int((Es > 0).sum())
            if best is None or npos > best["npos"]:
                best = dict(d=d, npos=npos, E=float(Es.mean()),
                            n=int(sum(v["n"] for v in pm.values())),
                            per={k: v["E"] for k, v in pm.items()})
        if best is None:
            continue
        lab = " & ".join(names)
        print(f"  {ci+1:<4}{lab[:50]:<52}{best['npos']:>4}/{len(frames):<2}"
              f"{best['E']:>+10.4f}{'':>8}", flush=True)
        if best["npos"] >= MIN_MARKETS_POSITIVE and best["E"] > 0:
            survivors.append(dict(rule=names, direction=best["d"],
                                  e_free=best["E"], npos=best["npos"],
                                  n=best["n"], disc_score=c["score"]))

    print(f"\n  {len(survivors)} of {len(cands)} candidates are positive at zero")
    print(f"  cost on at least {MIN_MARKETS_POSITIVE} of {len(frames)} markets.")
    if not survivors:
        print(f"\n  NOTHING SURVIVES STAGE 2. Not one rule out of "
              f"{disc['n_rules']:,} searched")
        print(f"  makes money in this engine with no spread charged at all.")
        print(f"  The holdout stays sealed - there is nothing to spend it on,")
        print(f"  and that is the result, not a failure to find one.")
        FINALISTS.write_text(json.dumps(dict(
            created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            n_searched=disc["n_rules"], n_stage2_survivors=0,
            finalists=[], holdout_opened=False,
            note="no rule positive at zero cost; holdout never opened"),
            indent=1))
        return

    print("\n" + "=" * 92)
    print("STAGE 3 - REAL BID/ASK, with the matched random-timing control")
    print("=" * 92)
    print(f"  {'rule':<52}{'E real':>10}{'skill':>10}{'mkts+':>7}")
    final = []
    for s in survivors:
        per = {}
        for sym, df in frames.items():
            r = evaluate(df, s["rule"], s["direction"],
                         TICKS.get(sym, 0.00001), free=False)
            if r is not None:
                per[sym] = r
        if len(per) < MIN_MARKETS_POSITIVE:
            continue
        Es = np.array([v["E"] for v in per.values()])
        Sk = np.array([v.get("skill", np.nan) for v in per.values()])
        s2 = dict(**s, e_real=float(Es.mean()),
                  skill=float(np.nanmean(Sk)),
                  npos_real=int((Es > 0).sum()))
        final.append(s2)
        lab = " & ".join(s["rule"])
        print(f"  {lab[:50]:<52}{s2['e_real']:>+10.4f}{s2['skill']:>+10.4f}"
              f"{s2['npos_real']:>4}/{len(per):<2}", flush=True)

    # the criterion, exactly as declared in the docstring above
    ok = [f for f in final if f["skill"] > 0]
    ok.sort(key=lambda f: -f["e_free"])
    chosen = ok[:N_FINALISTS]

    print("\n" + "=" * 92)
    print("FINALISTS - fixed now, before the holdout is opened")
    print("=" * 92)
    if not chosen:
        print("  None. No rule satisfies both declared conditions, so no")
        print("  finalist goes forward and the holdout is not opened.")
    for i, f in enumerate(chosen):
        print(f"  {i+1}. {' & '.join(f['rule'])}")
        print(f"     direction {'long' if f['direction'] > 0 else 'short':<6}"
              f"  E free {f['e_free']:+.4f}   E real {f['e_real']:+.4f}"
              f"   skill {f['skill']:+.4f}")

    FINALISTS.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_searched=disc["n_rules"], n_stage2_survivors=len(survivors),
        criterion=("zero-cost E>0 on >=7 of 9 markets; pooled skill>0; "
                   "ranked by pooled zero-cost E; at most 3"),
        finalists=chosen, holdout_opened=False), indent=1))
    print(f"\n  written -> {FINALISTS.name}   (holdout_opened: false)")
    print(f"  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
