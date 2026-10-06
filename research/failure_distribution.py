#!/usr/bin/env python3
"""Why 127 hypotheses died, counted - which decides what to rebuild next.

WHAT THIS IS FOR

  A search that returns "nothing worked" has produced one bit. The same search
  that returns a distribution over named failure modes has produced a research
  plan: the layer that decides a hundred outcomes is worth rebuilding and the
  one that decides three is not.

  The spec this run follows is explicit that the aggregate failure
  distribution, not the top PnL, chooses what to upgrade. That rule matters
  most exactly here, because one family did produce the best numbers and it
  would be easy to let it choose the next step on that basis alone.

WHAT IS MEASURED FOR EACH HYPOTHESIS

  Four control levels rather than all eight - C1, C3, C4 and C7 - because
  those are the four the taxonomy's selection codes actually read: C1 is the
  reference, C3 separates activity, C4 separates session, and C7 is the
  decision. Running all eight on 127 hypotheses across nine markets would
  cost four times as much to change no classification.
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
import controls as C
import discovery as DIS
import failure_codes as FC
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, load_bidask_h1

SEED = 17
H = 3
COST = DIS.COST_SPREADS
FLOOR = 4.84
LEVELS = ("C1", "C3", "C4", "C7")


def cross_t(v):
    v = np.asarray([x for x in v if np.isfinite(x)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("FAILURE DISTRIBUTION - why 127 hypotheses died")
    print("=" * 100)

    ref_df = load_bidask_h1("EURUSD")
    ref_s = None
    if ref_df is not None:
        Pr = X.prep(ref_df, 60)
        ref_s = pd.Series(DIS.state_vars(Pr)["ret_atr"],
                          index=pd.DatetimeIndex(Pr["idx"]))

    # name -> {market -> (edge, n, per-level control edges)}
    book = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        V = DIS.state_vars(P)
        cands = []
        ref = None
        if ref_s is not None and sym != "EURUSD":
            ref = ref_s.reindex(pd.DatetimeIndex(P["idx"])).to_numpy(float)
        if ref is not None:
            cands.extend(DIS.fam_cross(P, V, ref))
        for _, fn in DIS.FAMILIES:
            cands.extend(fn(P, V))
        if a.limit:
            cands = cands[:a.limit]
        A = np.asarray(P["A"], float)
        c = np.asarray(P["c"], float)
        for name, t, d in cands:
            s = DIS.score(P, t, d, H)
            if s is None:
                continue
            dv = np.zeros(P["N"], np.int8)
            dv[t] = d.astype(np.int8)
            Iv = np.full(P["N"], np.nan)
            Iv[t] = c[t] - d * 1.2 * A[t]
            rec = dict(edge=s["edge"], n=s["n"], sign=s["sign_rate"],
                       spread_atr=s["median_spread_atr"])
            for lv in LEVELS:
                dc, Ic, meta = C.build(P, dv, Iv, lv,
                                       np.random.default_rng(SEED))
                tc = np.where(dc != 0)[0]
                sc = DIS.score(P, tc, dc[tc].astype(float), H)
                rec[lv] = sc["edge"] if sc else np.nan
            book.setdefault(name, {})[sym] = rec
        print(f"  {sym:<9}{len(cands):>5} hypotheses   "
              f"{time.time()-t0:>6.0f}s", flush=True)

    rows = []
    for name, per in book.items():
        if len(per) < 3:
            continue
        e = [r["edge"] for r in per.values()]
        sk = {lv: [r["edge"] - r[lv] for r in per.values()
                   if np.isfinite(r[lv])] for lv in LEVELS}
        t7, pos7, n7 = cross_t(sk["C7"])
        t1, _, _ = cross_t(sk["C1"])
        m = dict(
            skill_c1=float(np.mean(sk["C1"])) if sk["C1"] else None,
            t_c1=t1,
            skill_c3=float(np.mean(sk["C3"])) if sk["C3"] else None,
            skill_c4=float(np.mean(sk["C4"])) if sk["C4"] else None,
            skill_c7=float(np.mean(sk["C7"])) if sk["C7"] else None,
            t_c7=t7, t_best=t7, floor=FLOOR,
            markets_positive=pos7, markets_total=n7,
            n_trades=int(np.mean([r["n"] for r in per.values()])),
            spread_over_range=float(np.mean(
                [r["spread_atr"] for r in per.values()])),
            zero_cost_skill=float(np.mean(e)),
            net_expectancy=float(np.mean(e)) - COST,
            cost_per_trade=COST,
        )
        cls = FC.classify(m)
        rows.append(dict(hypothesis=name, family=name.split("/")[0],
                         edge=float(np.mean(e)), t_c7=t7,
                         skill_c7=m["skill_c7"], codes=cls["codes"],
                         missing=cls["missing_inputs"]))

    dist = FC.aggregate([{"codes": r["codes"]} for r in rows])
    print("\n" + "=" * 100)
    print(f"FAILURE DISTRIBUTION OVER {len(rows)} HYPOTHESES")
    print("=" * 100)
    print(f"  {'code':<30}{'n':>6}{'share':>9}  what it means")
    for r in dist:
        what = FC.CODES.get(r["code"], ("", ""))[0].split(".")[0]
        print(f"  {r['code']:<30}{r['n']:>6}{r['share']*100:>8.1f}%  "
              f"{what[:56]}")

    print("\n" + "=" * 100)
    print("BY FAMILY - which mechanisms die of what")
    print("=" * 100)
    fams = sorted({r["family"] for r in rows})
    print(f"  {'family':<14}{'hyps':>6}  dominant failure modes")
    for f in fams:
        g = [r for r in rows if r["family"] == f]
        d = FC.aggregate([{"codes": r["codes"]} for r in g])[:3]
        print(f"  {f:<14}{len(g):>6}  "
              + ", ".join(f"{x['code']} {x['share']*100:.0f}%" for x in d))

    print("\n" + "=" * 100)
    print("WHAT THE DISTRIBUTION SAYS TO UPGRADE")
    print("=" * 100)
    for r in FC.upgrade_target(dist):
        print(f"  {r['code']:<30}{r['n']:>5} ({r['share']*100:.0f}%)  ->  "
              f"{r['upgrade']}")
    print("\n  The rule this follows is that the aggregate distribution "
          "chooses,")
    print("  not the best PnL. One family produced every large number in the")
    print("  pilot and it would be easy to let that choose the next step.")

    surv = [r for r in rows if "BELOW_MULTIPLICITY_FLOOR" in r["codes"]]
    if surv:
        print(f"\n  {len(surv)} hypotheses fail nothing named and are held "
              f"back only by the floor:")
        for r in sorted(surv, key=lambda r: -(r["skill_c7"] or 0))[:8]:
            print(f"    {r['hypothesis']:<44}skill vs C7 "
                  f"{r['skill_c7']:+.3f}  t {r['t_c7']:+.2f}")

    out = HERE / "failure_distribution.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        horizon=H, cost=COST, floor=FLOOR, levels=list(LEVELS),
        hypotheses=len(rows), per_hypothesis=rows, distribution=dist,
        upgrade_targets=FC.upgrade_target(dist),
        manifest=PR.manifest(dict(horizon=H, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase2-failure-distribution",
           "Which measurement layer does the aggregate failure distribution "
           "say to rebuild?",
           hypothesis="pilot_conditional_amplitude",
           tools=["failure_codes", "controls", "failure_distribution"],
           result=dict(distribution=dist,
                       upgrade=FC.upgrade_target(dist)),
           status="MEASURED",
           finding="; ".join(f"{r['code']} {r['share']*100:.0f}%"
                             for r in dist[:4]),
           next_action="upgrade the layer the distribution names",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
