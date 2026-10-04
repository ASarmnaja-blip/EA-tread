#!/usr/bin/env python3
"""Walk-forward round 2 as one continuous ten-year account, 2016-10..2026-09:
patterns and capital carry over, nothing restarts at 2021. Same rules as
walkforward_round2.py; compared with round-1 rules, the no-decision stream of
round 2's own patterns, and G27K #1 run on the same ten years and data.

Usage: python3 walkforward_10y.py --root <data-snapshot checkout>
"""
import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import h4d1_pattern_search as P
import walkforward_controller as W
import walkforward_round2 as W2

START, END = pd.Timestamp("2016-10-01", tz="UTC"), pd.Timestamp("2026-10-01", tz="UTC")


def g27k_10y(RP, G, K):
    """G27K #1 (C8/D3/E1/F1/G2/H2/I1/J1, 1%) with the report's own fills, on
    the same hybrid data the walk-forward uses."""
    ext = K.externals()
    K.START = int(START.timestamp())
    sub, Xs = [], {}
    for m in K.MKTS:
        h1 = P._M["h1"][m]
        M = K.prepare(m, h1, ext)
        X = G.features(G.frames(h1), m, "H4")
        X["sec"] = 14400
        Xs[m] = X
        d = K.directions(M, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        sub += [dict(tr, X=X) for tr in RP.sim_paths(X, m, idx, d[idx], "I1")]
    T = RP.timeline(sub, Xs)
    RP.prep_marks(sub, T)
    with np.errstate(all="ignore"):
        return RP.metrics(RP.account(sub, 0.01), T, 0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in W.TFS}
    cache = HERE / ".cache_wf" / "refits.pkl"
    allref = pickle.loads(cache.read_bytes())
    dates = [W.ts(d) for d in pd.date_range(START, END - pd.Timedelta(days=1), freq="QS")]
    for D in dates:
        if D not in allref:
            allref[D] = W.refit_candidates(D, B)
            cache.write_bytes(pickle.dumps(allref))
    refits = {D: allref[D] for D in dates}
    news = W.news_times(a.root)
    G.START = int(START.timestamp())
    W.START, W.END = START, END
    res = {}
    rows, pats, log, st = W2.run2(B, refits, news, int(END.timestamp()))
    res["controller"] = W2.pack(rows, pats, log, st, RP, G, B)
    W.BASE_RISK = 0.0075
    r1, p1, l1, s1 = W.run(B, refits, news, decide=True)
    res["round1_rules"] = W2.pack(r1, p1, l1, s1, RP, G, B)
    rn, pn, ln, sn = W.run(B, refits, news, decide=False, fixed=list(pats.values()))
    res["no_decisions"] = W2.pack(rn, pn, ln, sn, RP, G, B)
    res["g27k_1"] = dict(metrics=W.slim(g27k_10y(RP, G, K)))
    for k in ("controller", "round1_rules", "no_decisions", "g27k_1"):
        m = res[k]["metrics"]
        print(f"  {k:13s} trades {m['trades']:5d} net {m['net']:+12,.0f} CAGR {m['cagr']:+6.1%} "
              f"eqDD {m['equity_dd']:5.1%} MAR {m['mar']:5.2f} PF {m['pf']:.2f}", flush=True)
    res["config"] = dict(start=str(START.date()), end="2026-09-30", base_risk=W2.BASE, refits=len(dates),
                         candidates=[dict(date=str(pd.Timestamp(D, unit='s').date()), n=len(refits[D]),
                                          eligible=int(sum(W.eligible(c) for c in refits[D]))) for D in dates])
    (HERE / "walkforward_10y.json").write_text(json.dumps(res, ensure_ascii=False, default=str))
    print(f"  saved walkforward_10y.json  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
