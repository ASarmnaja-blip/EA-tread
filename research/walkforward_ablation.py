#!/usr/bin/env python3
"""Post-hoc diagnosis of round 1: switch each monitor off in turn, using the
cached quarterly searches, and see what each one added or cost. Diagnosis
only - it cannot change the round-1 verdict, it can only inform a round 2.

Usage: python3 walkforward_ablation.py --root <data-snapshot checkout>
"""
import argparse
import json
import pathlib
import pickle
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import h4d1_pattern_search as P
import walkforward_controller as W

ALL = ("cap_market", "cap_risk", "brake", "live_retire", "refit_retire", "news", "vol", "probation")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in W.TFS}
    refits = pickle.loads((HERE / ".cache_wf" / "refits.pkl").read_bytes())
    news = W.news_times(a.root)
    variants = [("full controller", ())] + [(f"without {k}", (k,)) for k in ALL] + [("adoption only, every monitor off", ALL)]
    out = []
    for name, off in variants:
        rows, patterns, log, skipped = W.run(B, refits, news, decide=True, off=off)
        M = W.slim(W.metrics_for(W.to_report_rows(rows, B), RP, G))
        rec = dict(variant=name, off=list(off), trades=M["trades"], net=M["net"], cagr=M["cagr"],
                   eq_dd=M["equity_dd"], mar=M["mar"], pf=M["pf"], skipped=skipped,
                   patterns=len(patterns), retired=sum(1 for p in patterns.values() if p.t_off))
        out.append(rec)
        print(f"  {name:36s} trades {rec['trades']:5d} net {rec['net']:+12,.0f} CAGR {rec['cagr']:+6.1%} "
              f"eqDD {rec['eq_dd']:5.1%} MAR {rec['mar']:5.2f} PF {rec['pf']:.2f} | patterns {rec['patterns']} "
              f"retired {rec['retired']} | skipped {skipped}", flush=True)
    (HERE / "walkforward_ablation.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
