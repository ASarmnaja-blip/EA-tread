#!/usr/bin/env python3
"""H1 search done exactly as the M30 one (ledger h1_search_mirror_m30;
criteria fixed there). Same data (Dukascopy M1 mid for gold and silver from
2009, Binance BTC 1m from 2021; H1 bars built from M1 and stops walked on
M1, higher timeframes D1 and W1 as for M30), same engine, conditions, five
exits, scopes (XAUUSD, XAGUSD, BTCUSD, pooled), splits (metals 2018-01-01,
BTC 2024-01-01), costs and non-overlapping trades.

  --part main         A forward: discover before the split, test after
                      B reverse: discover after the split, test before
                      (both: full search space, top-10 per scope with net,
                      gross and cost R in both periods)
                      C the constrained family (the M30 family's blocks on
                      H1: 3 x 3 x 3 x 2 x 3 x 4 = 648 patterns) on the real
                      history, candidates = net > 0, t >= 2, n >= 100 in
                      both periods; pick = candidate with the best
                      all-period t
  --part placebo -p k the family on drift placebo k (k = 0..4)

Usage: python3 research/g27k_dev/h1_mirror.py --root <snap> --part main
"""
import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import m30_new_markets as NM
import minute_reverse as MR
import per_market_search as PMS

TF = "H1"
KEEP = 10


def top_rows(E, names, Bm, cands, disc, tag):
    """Top-10 per scope by discovery t, with net / gross / cost in both periods."""
    out = {}
    for s in PMS.SCOPES:
        top = sorted([c for c in cands if c["scope"] == s], key=lambda c: -c["t_disc"])[:KEEP]
        rows = []
        for c in top:
            ex = c["exit"]
            m = np.isfinite(E[f"R_{ex}"]) & P.scope_mask(E, s)
            for q in c["conds"]:
                m &= Bm[:, q]
            r = dict(tf=TF, exit=ex, scope=s, names=[names[q] for q in c["conds"]], t_disc_engine=float(c["t_disc"]),
                     disc=MR.stats(E, P.no_overlap(E, m & disc, ex), ex), val=MR.stats(E, P.no_overlap(E, m & ~disc, ex), ex))
            rows.append(r)
            print(f"  [{tag}] {s:7s} {ex:5s} disc n {r['disc']['n']:4d} net {r['disc']['net']:+.3f} gross {r['disc']['gross']:+.3f} | "
                  f"val n {r['val']['n']:4d} net {r['val']['net']:+.3f} t {r['val']['t']:+.2f} gross {r['val']['gross']:+.3f} cost {r['val']['cost']:.3f} | "
                  f"{' & '.join(r['names'])}", flush=True)
        out[s] = rows
    return out


def summary(res, tag):
    allr = [r for s in res for r in res[s]]
    d = {f"{p}_{k}": float(np.nanmean([r[p][k] for r in allr])) for p in ("disc", "val") for k in ("net", "gross", "cost")}
    print(f"  [{tag}] mean of {len(allr)} top patterns: disc net {d['disc_net']:+.3f} gross {d['disc_gross']:+.3f} | "
          f"val net {d['val_net']:+.3f} gross {d['val_gross']:+.3f} cost {d['val_cost']:.3f}", flush=True)
    return d


def main_part(h1):
    t0 = time.time()
    out = {}
    E, feats, cats = P.build(h1, TF)
    split = PMS.split_for(E)
    before = E["t"] < split
    # A forward
    P._M["SPLIT"] = split
    names, Bm = P.conditions(feats, cats, before)
    cands, tot = P.search(TF, E, names, Bm, before)
    out["A"] = dict(total=tot, top=top_rows(E, names, Bm, cands, before, "A forward"))
    out["A"]["mean"] = summary(out["A"]["top"], "A forward")
    print(f"  A forward: {tot:,} patterns  {time.time() - t0:.0f}s", flush=True)
    del Bm, cands
    # B reverse (search() keeps tx < SPLIT: keep everything in the discovery mask)
    after = ~before
    P._M["SPLIT"] = np.full(len(E["t"]), 2 ** 62)
    names, Bm = P.conditions(feats, cats, after)
    cands, tot = P.search(TF, E, names, Bm, after)
    out["B"] = dict(total=tot, top=top_rows(E, names, Bm, cands, after, "B reverse"))
    out["B"]["mean"] = summary(out["B"]["top"], "B reverse")
    print(f"  B reverse: {tot:,} patterns  {time.time() - t0:.0f}s", flush=True)
    del E, feats, cats, Bm, cands
    # C constrained family, both periods
    rows = MR.family(h1, "real", (TF,))
    out["C"] = rows
    c = [r for r in rows if r["cand"]]
    print(f"  C family: {len(c)} candidates of {len(rows)}", flush=True)
    for r in sorted(c, key=lambda r: -r["all"]["t"])[:15]:
        print(f"    {r['scope']:7s} {r['near']:14s} {r['vol']:16s} {r['ctx']:12s} {r['dir']:5s} {r['exit']:4s} | A n {r['A']['n']} {r['A']['net']:+.3f} t {r['A']['t']:.1f} | "
              f"B n {r['B']['n']} {r['B']['net']:+.3f} t {r['B']['t']:.1f} | all {r['all']['net']:+.3f} t {r['all']['t']:.1f} gross {r['all']['gross']:+.3f} cost {r['all']['cost']:.3f}",
              flush=True)
    (HERE / "h1_mirror_real.json").write_text(json.dumps(out, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--part", choices=("main", "placebo"), required=True)
    ap.add_argument("-p", type=int, default=0)
    a = ap.parse_args()
    h1 = NM.prepare(a.root, NM.OLD)
    P._M["scopes"] = PMS.SCOPES
    if a.part == "main":
        main_part(h1)
        return
    rows = MR.family(P.drift_placebo(a.p), f"drift{a.p}", (TF,))
    (HERE / f"h1_mirror_drift{a.p}.json").write_text(json.dumps(rows, indent=1, default=float))
    print(f"  drift{a.p}: {sum(r['cand'] for r in rows)} candidates of {len(rows)}")


if __name__ == "__main__":
    main()
