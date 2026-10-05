#!/usr/bin/env python3
"""Experiment only, never for live use: gold on M15 with every profit
withdrawn at once (account of gold_sweep.py), scored per week: net
withdrawn minus new deposits in % of the capital, for risk 5%..100%.

Rules on XAUUSD M15 (Dukascopy M1, 2011-09..2026-09, one trade at a time):
  A  pos250>=0.9 & atr_ratio>=1.5 & htf1_with, both, ch20 exit
  B  pos250>=0.9 & atr_ratio>=1.25 & htf1_with, both, ch20 exit
     (the two M15 candidates of minute_reverse_and_constrained, found pooled
     on gold, silver and BTC)
  C  the M30 sleeve rule run on M15 (not validated on M15)

Usage: python3 research/g27k_dev/gold_week.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h1_sleeve as HS
import h4d1_pattern_search as P
import m30_new_markets as NM
from gold_sweep import FLOOR
from gold_sweep_cap import WIN

RISKS = tuple(round(0.05 * k, 2) for k in range(1, 21))
RULES = {"A": dict(near="pos250", thr=0.9, vol=1.5, ctx="htf1_with", dir="both", exit="ch20"),
         "B": dict(near="pos250", thr=0.9, vol=1.25, ctx="htf1_with", dir="both", exit="ch20"),
         "C": dict(near="brk55", thr=-1.0, vol=1.5, ctx="htf1_with", dir="both", exit="tp2")}


def run(T, r):
    bal, blows, flows = 1.0, [], []
    for R, tx in zip(T.R.to_numpy(), T.tx.to_numpy()):
        bal += r * bal * R
        if bal > 1.0:
            flows.append((tx, bal - 1.0))
            bal = 1.0
        if bal < FLOOR:
            blows.append(tx)
            flows.append((tx, -1.0))
            bal = 1.0
    b = np.array(blows)
    worst3 = int(max((np.searchsorted(b, x + WIN, "left") - i for i, x in enumerate(b)), default=0))
    f = pd.Series([v for _, v in flows], index=pd.to_datetime([t for t, _ in flows], unit="s"))
    w = f.resample("W-SUN").sum().reindex(pd.date_range("2011-09-04", "2026-09-27", freq="W-SUN"), fill_value=0.0)
    return dict(blowups=len(b), per_year=len(b) / 15.08, worst_3m=worst3, week_mean=float(w.mean()), week_median=float(w.median()),
                weeks_ge5=float((w >= 0.05).mean()), weeks_neg=float((w < 0).mean()), best_week=float(w.max()), net_total=float(w.sum() - 1.0 + bal))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    NM.prepare(a.root, ("XAUUSD",))
    E, feats, cats = P.build(P._M["h1"], "M15")
    out = {}
    for k, rule in RULES.items():
        s = dict(rule, tf="M15", scope="XAUUSD")
        T = HS.trades(E, P.no_overlap(E, HS.mask(E, feats, cats, s), s["exit"]), s)
        R = T.R.to_numpy()
        print(f"  rule {k} {rule}: {len(T)} trades ({len(T) / 15.08 / 52:.1f} a week), win {(R > 0).mean():.0%}, mean {R.mean():+.3f}R, "
              f"t {NM.tstat(R):+.2f}, best {R.max():+.1f}R, worst {R.min():+.1f}R", flush=True)
        res = {}
        for r in RISKS:
            x = run(T, r)
            res[f"{r:.2f}"] = x
            print(f"    risk {r:4.0%}: per week mean {x['week_mean']:+6.1%} median {x['week_median']:+.1%} | weeks >= +5% {x['weeks_ge5']:4.0%}, "
                  f"weeks < 0 {x['weeks_neg']:4.0%} | best week {x['best_week']:+.0%} | blow-ups {x['blowups']} ({x['per_year']:.1f}/yr, most in 3 months {x['worst_3m']}) | "
                  f"15y net x{x['net_total']:+.1f}", flush=True)
        out[k] = dict(rule=rule, n=int(len(T)), mean_R=float(R.mean()), t=NM.tstat(R), risks=res)
    (HERE / "gold_week.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
