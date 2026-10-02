#!/usr/bin/env python3
"""Free pattern search per market, combined into one portfolio (ledger id
per_market_free_search).

The h4d1_pattern_search engine (every H1, H4 and D1 bar a long and short
candidate, 1-3 conditions, five exits, one open trade per market) run with
four scopes: gold, silver and BTC each alone, and pooled. Discovery is
metals 2009-09..2017-12 and BTC 2021-01..2023-12; everything after is test.
PER-MARKET = each market's top-1 own pattern; SHARED = the top-1 pooled
pattern. Both are traded on the test period as one account at 1% per trade,
next to G27K #1 (system B). The same search on drift-placebo histories gives
the selection-aware null for each market's top-1.

Usage: python3 research/g27k_dev/per_market_search.py --root <data-snapshot checkout> [--placebos N]
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import brake as BR
import h4d1_pattern_search as P
import phase1 as PH
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD")
SCOPES = ("XAUUSD", "XAGUSD", "BTCUSD", "pooled")
SPLITS = {"XAUUSD": "2018-01-01", "XAGUSD": "2018-01-01", "BTCUSD": "2024-01-01"}
TEST0, END = "2018-01-01", "2026-10-01"
KEEP = 10


def split_for(E):
    return np.select([E["mkt"] == m for m in MKTS], [W.ts(SPLITS[m]) for m in MKTS], W.ts(TEST0)).astype(np.int64)


def trades_of(E, Bm, c):
    """Non-overlapping test-period trades of one pattern: market, entry, exit, R."""
    ex = c["exit"]
    R = E[f"R_{ex}"]
    mask = np.isfinite(R) & (E["t"] >= _split(E))
    for q in c["conds"]:
        mask &= Bm[:, q]
    if c["scope"] != "pooled":
        mask &= E["mkt"] == c["scope"]
    k = P.no_overlap(E, mask, ex)
    sec = P.TF_SEC[c["tf"]]
    return pd.DataFrame(dict(mkt=E["mkt"][k], t=E["t"][k] + sec, tx=E[f"tx_{ex}"][k], R=R[k]))


def _split(E):
    return P._M["SPLIT"]


def run_search(h1s, label):
    t0 = time.time()
    best = {s: [] for s in SCOPES}
    store = {}
    total = 0
    for tf in ("H1", "H4", "D1"):
        E, feats, cats = P.build(h1s, tf)
        P._M["SPLIT"] = split_for(E)
        disc = E["t"] < P._M["SPLIT"]
        names, Bm = P.conditions(feats, cats, disc)
        cands, tot = P.search(tf, E, names, Bm, disc)
        total += tot
        for s in SCOPES:
            top = sorted([c for c in cands if c["scope"] == s], key=lambda c: -c["t_disc"])[:KEEP]
            for c in top:
                c.update(P.validate(E, Bm, names, c))
                c["trades"] = trades_of(E, Bm, c)
            best[s] += top
        store[tf] = None
        print(f"  [{label}] {tf}: {len(E['t']):,} events, {len(names)} conditions, {tot:,} patterns  "
              f"{time.time() - t0:.0f}s", flush=True)
        del E, feats, cats, Bm
    for s in SCOPES:
        best[s] = sorted(best[s], key=lambda c: -c["t_disc"])[:KEEP]
    return best, total


def account(T, start=TEST0, end=END):
    if len(T) == 0:
        return dict(n=0)
    st, eq = BR.account(T[["t", "tx", "R"]].assign(R=T.R.astype(float)), 0.01, None, start, end)
    R = T.R.to_numpy()
    st["pf"] = float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else float("inf")
    st["totR"] = float(R.sum())
    st["per_mkt"] = {m: dict(n=int((T.mkt == m).sum()), totR=float(T.R[T.mkt == m].sum())) for m in MKTS}
    yr = eq.resample("YE").last()
    st["yearly"] = {int(d.year): float(v) for d, v in (yr / yr.shift(1).fillna(1.0) - 1).items()}
    return st


def slim(c):
    return {k: v for k, v in c.items() if k != "trades"} | dict(n_test=len(c["trades"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--placebos", type=int, default=0)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    P._M["scopes"] = SCOPES
    P._M["tfs"] = ("H1", "H4", "D1")
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in MKTS}
    best, total = run_search(P._M["h1"], "real")
    pick = {s: best[s][0] for s in SCOPES}
    per_market = pd.concat([pick[m]["trades"] for m in MKTS], ignore_index=True)
    shared = pick["pooled"]["trades"]
    ext = K.externals()
    Ds = {m: PH.prep_market(m, P._M["h1"][m], ext) for m in MKTS}
    g27k = PH.system_trades("B", Ds, *PH.BASE, start=TEST0)
    acc = {"per_market": account(per_market), "shared": account(shared), "g27k_B": account(g27k)}
    out = dict(patterns=total, pick={s: slim(pick[s]) for s in SCOPES},
               top={s: [slim(c) for c in best[s]] for s in SCOPES}, accounts=acc, placebos=[])
    path = HERE / "per_market_search.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print(f"\n  {total:,} patterns searched  {time.time() - t0:.0f}s")
    for s in SCOPES:
        c = pick[s]
        print(f"  {s:7s} {c['tf']} {c['exit']:5s} {' & '.join(c['names'])}")
        print(f"          discovery n {c['n_disc']} R {c['R_disc']:+.3f} t {c['t_disc']:.2f} | "
              f"test n {c['n_val']} R {c['R_val']:+.3f} t {c['t_val']:.2f} totR {c['totR_val']:+.1f}")
    for k, s in acc.items():
        print(f"  {k:10s} n {s['n']:4d} CAGR {s['cagr']:+.1%} DD {s['dd']:.1%} MAR {s['mar']:.2f} PF {s['pf']:.2f} "
              + " ".join(f"{m} {v['n']}/{v['totR']:+.0f}R" for m, v in s["per_mkt"].items()))
    for p in range(a.placebos):
        pb, _ = run_search(P.drift_placebo(p), f"drift{p}")
        out["placebos"].append({s: dict(t_disc=pb[s][0]["t_disc"], R_val=pb[s][0]["R_val"], t_val=pb[s][0]["t_val"],
                                        R_disc=pb[s][0]["R_disc"]) for s in SCOPES})
        path.write_text(json.dumps(out, indent=1, default=str))
        print(f"  drift{p}: " + "  ".join(f"{s} disc t {out['placebos'][-1][s]['t_disc']:.2f} test R "
                                          f"{out['placebos'][-1][s]['R_val']:+.3f}" for s in SCOPES), flush=True)
    print(f"  elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
