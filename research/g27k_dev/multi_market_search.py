#!/usr/bin/env python3
"""One pattern for many markets (ledger id multi_market_pooled_search).

The free search of h4d1_pattern_search on H1, H4 and D1 over 16 markets with
real broker costs and swap, ranked on discovery data before 2018 (BTC before
2021). ALL16 = the top pattern pooled over all 16; POOL3 = the top pattern
pooled over gold, silver and BTC only, on the same data. Both are then
traded on the test period: on all 16 markets, and on the three target
markets as one account at 1% per trade. Drift-placebo runs of the whole
search give the selection-aware null.

Usage: python3 research/g27k_dev/multi_market_search.py --root <data-snapshot checkout> [--placebos N]
"""
import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import per_market_search as PMS
import walkforward_controller as W

MARKETS = ("XAUUSD", "XAGUSD", "XCUUSD", "USOIL", "US500", "USTEC", "DE30", "JP225", "EURUSD", "USDJPY",
           "AUDUSD", "USDCHF", "USDCNH", "USDMXN", "USDZAR", "BTCUSD")
TARGET = ("XAUUSD", "XAGUSD", "BTCUSD")
SPLITS = {m: ("2021-01-01" if m == "BTCUSD" else "2018-01-01") for m in MARKETS}
SCOPES = ("pooled", "POOL3")
CACHE = HERE.parent / ".cache_duka"


def load(m, G):
    if m in ("XAUUSD", "XAGUSD"):
        return W.hybrid_h1(m, G)
    d = pd.read_parquet(CACHE / f"{m}_H1BID.parquet")
    d = d[(d.h > d.l) & (d.index >= pd.Timestamp("2009-01-01", tz="UTC")) & (d.index < pd.Timestamp(PMS.END, tz="UTC"))]
    t = ((d.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    return dict(t=t, o=d.o.to_numpy(float), h=d.h.to_numpy(float), l=d.l.to_numpy(float), c=d.c.to_numpy(float),
                v=d.v.to_numpy(float), step=3600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--placebos", type=int, default=0)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G = P._M["G"]
    PMS.MKTS, PMS.SPLITS, PMS.SCOPES = MARKETS, SPLITS, SCOPES
    P._M.update(scopes=SCOPES, scope_sets={"POOL3": TARGET})
    P._M["h1"] = {m: load(m, G) for m in MARKETS}
    for m, b in P._M["h1"].items():
        print(f"  {m:7s} {len(b['t']):7,} H1 bars from {pd.Timestamp(int(b['t'][0]), unit='s').date()}", flush=True)
    best, total = PMS.run_search(P._M["h1"], "real", ("H1", "H4", "D1"))
    res = dict(total=total, best=best, placebos=[])
    path = PMS.CACHE / "mms.pkl"
    path.write_bytes(pickle.dumps(res))
    out = dict(patterns=total, pick={}, accounts={}, per_market_test={}, top={s: [PMS.slim(c) for c in best[s]] for s in SCOPES})
    for s in SCOPES:
        c = best[s][0]
        T = c["trades"]
        out["pick"][s] = PMS.slim(c)
        out["per_market_test"][s] = {m: dict(n=int((T.mkt == m).sum()), totR=float(T.R[T.mkt == m].sum()),
                                             R=float(T.R[T.mkt == m].mean()) if (T.mkt == m).any() else None)
                                     for m in MARKETS}
        PMS.MKTS = TARGET
        out["accounts"][s] = PMS.account(T[T.mkt.isin(TARGET)])
        PMS.MKTS = MARKETS
        print(f"  {s:6s} {c['tf']} {c['exit']:5s} {' & '.join(c['names'])}")
        print(f"         discovery n {c['n_disc']} R {c['R_disc']:+.3f} t {c['t_disc']:.2f} | test (scope) n {c['n_val']} "
              f"R {c['R_val']:+.3f} t {c['t_val']:.2f}")
        pos = sum(1 for v in out["per_market_test"][s].values() if v["totR"] > 0)
        print(f"         markets positive in test: {pos}/{len(MARKETS)}  target: " +
              " ".join(f"{m} {out['per_market_test'][s][m]['totR']:+.0f}R" for m in TARGET))
        ac = out["accounts"][s]
        if ac.get("n"):
            print(f"         target account CAGR {ac['cagr']:+.1%} DD {ac['dd']:.1%} MAR {ac['mar']:.2f} PF {ac['pf']:.2f}", flush=True)
    jpath = HERE / "multi_market_search.json"
    jpath.write_text(json.dumps(out, indent=1, default=str))
    for p in range(a.placebos):
        pb, _ = PMS.run_search(P.drift_placebo(p), f"drift{p}", ("H1", "H4", "D1"))
        res["placebos"].append({s: [dict(tf=c["tf"], t_disc=c["t_disc"], R_val=c["R_val"], t_val=c["t_val"], n_val=c["n_val"])
                                    for c in pb[s]] for s in SCOPES})
        path.write_bytes(pickle.dumps(res))
        out["placebo_top1"] = [{s: x[s][0] for s in SCOPES} for x in res["placebos"]]
        jpath.write_text(json.dumps(out, indent=1, default=str))
        print(f"  drift{p}: " + "  ".join(f"{s} test R {pb[s][0]['R_val']:+.3f} t {pb[s][0]['t_val']:.2f}" for s in SCOPES), flush=True)
    print(f"  elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
