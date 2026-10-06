#!/usr/bin/env python3
"""Stage 2, layer L3 (ledger fresh_markets_search_v2): the free pattern search
on group A, discovery 2012-01..2019-12, validation 2020-01..2023-12. Data from
2024-01-01 on is cut at load (sealed holdout). Drift-placebo runs of the
identical search give the null for gate 2.

Usage: python3 research/g27k_dev/fresh_search_l3.py --root <snap> real
       python3 research/g27k_dev/fresh_search_l3.py --root <snap> placebo <first> <count>
"""
import argparse
import pickle
import sys
import time

import numpy as np
import pandas as pd

import pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import h4d1_pattern_search as P
import per_market_search as PMS

GROUP_A = ("GBPUSD", "NZDUSD", "EURJPY", "AUDJPY", "CHFJPY", "EURGBP", "EURCAD", "GBPAUD", "AUDCAD",
           "UK100", "HK50", "STOXX50", "UKOIL", "XPDUSD")
GROUP_B = ("USDCAD", "USDSEK", "GBPJPY", "CADJPY", "NZDJPY", "EURAUD", "EURCHF", "GBPCHF", "AUDNZD",
           "FRA40", "AUS200", "XPTUSD", "XNGUSD", "ETHUSD")
D0, SPLIT, SEAL = "2012-01-01", "2020-01-01", "2024-01-01"
TFS = ("H1", "H4", "D1")


def load(m, d0=D0, d1=SEAL):
    d = pd.read_parquet(PMS.CACHE.parent / ".cache_duka" / f"{m}_H1BID.parquet")
    d = d[(d.h > d.l) & (d.index >= pd.Timestamp(d0, tz="UTC")) & (d.index < pd.Timestamp(d1, tz="UTC"))]
    d = d[~d.index.duplicated()].sort_index()
    t = ((d.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    return dict(t=t, o=d.o.to_numpy(float), h=d.h.to_numpy(float), l=d.l.to_numpy(float), c=d.c.to_numpy(float),
                v=d.v.to_numpy(float), step=3600)


def setup(root, markets):
    P.setup(root)
    C = P._M["C"]
    C.SPECS.update(FM.specs(C))
    PMS.MKTS, PMS.SCOPES, PMS.KEEP = markets, ("pooled",), 100
    PMS.SPLITS = {m: SPLIT for m in markets}
    PMS.TEST0, PMS.END = SPLIT, SEAL
    P._M.update(scopes=("pooled",), scope_sets={})
    P._M["h1"] = {m: load(m) for m in markets}
    return P._M["h1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("mode", choices=("real", "placebo"))
    ap.add_argument("first", nargs="?", type=int, default=0)
    ap.add_argument("count", nargs="?", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    h1 = setup(a.root, GROUP_A)
    for m, b in h1.items():
        assert b["t"].max() < pd.Timestamp(SEAL).value // 10 ** 9, "sealed data leaked"
    if a.mode == "real":
        best, total = PMS.run_search(h1, "real", TFS)
        out = dict(total=total, top=[dict(PMS.slim(c), trades_all=c["trades_all"]) for c in best["pooled"]])
        (PMS.CACHE / "fresh_l3_real.pkl").write_bytes(pickle.dumps(out))
        for c in best["pooled"][:10]:
            print(f"  {c['tf']} {c['exit']:5s} {' & '.join(c['names'])}  disc n {c['n_disc']} R {c['R_disc']:+.3f} t {c['t_disc']:.2f} | "
                  f"val n {c['n_val']} R {c['R_val']:+.3f} t {c['t_val']:.2f}", flush=True)
        print(f"  real: {total:,} patterns  top-100 median disc t {np.median([c['t_disc'] for c in best['pooled']]):.2f}  {time.time() - t0:.0f}s")
    else:
        for p in range(a.first, a.first + a.count):
            pb, total = PMS.run_search(P.drift_placebo(p), f"drift{p}", TFS)
            out = dict(total=total, top=[dict(tf=c["tf"], t_disc=c["t_disc"], R_disc=c["R_disc"], R_val=c["R_val"], t_val=c["t_val"],
                                              n_val=c["n_val"]) for c in pb["pooled"]])
            (PMS.CACHE / f"fresh_l3_drift{p}.pkl").write_bytes(pickle.dumps(out))
            print(f"  drift{p}: top-1 disc t {out['top'][0]['t_disc']:.2f}  top-100 median {np.median([c['t_disc'] for c in out['top']]):.2f}  "
                  f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
