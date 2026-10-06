#!/usr/bin/env python3
"""M15/M30: reverse search and a constrained family (ledger
minute_reverse_and_constrained; criterion fixed there).

  --part reverse          the full forward search space with discovery after
                          the split and validation before it
  --part family [--placebo p]
                          the 1,296-pattern constrained family on the real
                          M1 history (p = -1) or on drift placebo p

Usage: python3 research/g27k_dev/minute_reverse.py --root <snap> --part family
"""
import argparse
import itertools
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
import intraday_pattern_search as IP
import per_market_search as PMS

NEAR = {"brk55>=-1": ("brk55", -1.0), "brk100>=-1.25": ("brk100", -1.25), "pos250>=0.9": ("pos250", 0.9)}
VOL = {"-": None, "atr_ratio>=1.25": 1.25, "atr_ratio>=1.5": 1.5}
CTX = ("-", "htf1_with", "ema20_50>=0")
DIRS = ("long", "both")
EXITS = ("tp2", "t6", "ch20")
SCOPES = ("XAUUSD", "XAGUSD", "BTCUSD", "pooled")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else float("nan")


def stats(E, k, ex):
    R = E[f"R_{ex}"][k]
    g = E["d"][k] * (E[f"px_{ex}"][k] - E[f"ep_{ex}"][k]) / E[f"rk_{ex}"][k]
    return dict(n=int(len(k)), net=float(R.mean()) if len(k) else np.nan, t=tstat(R), gross=float(g.mean()) if len(k) else np.nan,
                cost=float((g - R).mean()) if len(k) else np.nan)


def family(h1, label, tfs=("M15", "M30")):
    out = []
    for tf in tfs:
        t0 = time.time()
        E, feats, cats = P.build(h1, tf)
        split = PMS.split_for(E)
        A = E["t"] < split
        for (nn, (fk, thr)), (vn, vthr), ctx, dr, ex, sc in itertools.product(NEAR.items(), VOL.items(), CTX, DIRS, EXITS, SCOPES):
            m = np.isfinite(E[f"R_{ex}"]) & P.scope_mask(E, sc) & (feats[fk] >= thr)
            if vthr is not None:
                m &= feats["atr_ratio"] >= vthr
            if ctx == "htf1_with":
                m &= cats["htf1_with"]
            elif ctx == "ema20_50>=0":
                m &= feats["ema20_50"] >= 0
            if dr == "long":
                m &= E["d"] > 0
            row = dict(tf=tf, near=nn, vol=vn, ctx=ctx, dir=dr, exit=ex, scope=sc)
            for per, sel in (("A", A), ("B", ~A), ("all", np.ones(len(A), bool))):
                row[per] = stats(E, P.no_overlap(E, m & sel, ex), ex)
            row["cand"] = bool(all(row[p]["n"] >= 100 and row[p]["net"] > 0 and row[p]["t"] >= 2 for p in ("A", "B")))
            out.append(row)
        print(f"  [{label}] {tf}: {sum(r['cand'] for r in out if r['tf'] == tf)} candidates of {sum(1 for r in out if r['tf'] == tf)}  {time.time() - t0:.0f}s", flush=True)
        del E, feats, cats
    return out


def reverse(h1):
    res = {s: [] for s in PMS.SCOPES}
    total = 0
    for tf in ("M15", "M30"):
        t0 = time.time()
        E, feats, cats = P.build(h1, tf)
        split = PMS.split_for(E)
        disc = E["t"] >= split
        P._M["SPLIT"] = np.full(len(E["t"]), 2 ** 62)          # search() keeps tx < SPLIT: make it keep everything in the mask
        names, Bm = P.conditions(feats, cats, disc)
        cands, tot = P.search(tf, E, names, Bm, disc)
        total += tot
        for s in PMS.SCOPES:
            top = sorted([c for c in cands if c["scope"] == s], key=lambda c: -c["t_disc"])[:10]
            for c in top:
                ex = c["exit"]
                m = np.isfinite(E[f"R_{ex}"]) & P.scope_mask(E, s)
                for q in c["conds"]:
                    m &= Bm[:, q]
                c["names"] = [names[q] for q in c["conds"]]
                c["disc"] = stats(E, P.no_overlap(E, m & disc, ex), ex)
                c["val"] = stats(E, P.no_overlap(E, m & ~disc, ex), ex)
                res[s].append({k: v for k, v in c.items() if k != "conds"})
        print(f"  reverse {tf}: {tot:,} patterns  {time.time() - t0:.0f}s", flush=True)
        del E, feats, cats, Bm
    for s in PMS.SCOPES:
        res[s] = sorted(res[s], key=lambda c: -c["t_disc"])[:10]
    return res, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--part", choices=("reverse", "family"), required=True)
    ap.add_argument("--placebo", type=int, default=-1)
    a = ap.parse_args()
    P.setup(a.root)
    P._M["scopes"] = PMS.SCOPES
    P._M["h1"] = {m: PMS.load_m1(m) for m in PMS.MKTS}
    P._M["frames_for"] = IP.frames_minute
    if a.part == "reverse":
        res, total = reverse(P._M["h1"])
        (HERE / "minute_reverse.json").write_text(json.dumps(dict(total=total, best=res), indent=1, default=float))
        for s, lst in res.items():
            for c in lst:
                print(f"  {s:7s} {c['tf']} {c['exit']:5s} disc(2018+) n {c['disc']['n']} net {c['disc']['net']:+.3f} | val(early) n {c['val']['n']} "
                      f"net {c['val']['net']:+.3f} t {c['val']['t']:+.2f} gross {c['val']['gross']:+.3f} | {' & '.join(c['names'])}")
        return
    h1 = P._M["h1"] if a.placebo < 0 else P.drift_placebo(a.placebo)
    rows = family(h1, "real" if a.placebo < 0 else f"drift{a.placebo}")
    name = "minute_family_real.json" if a.placebo < 0 else f"minute_family_drift{a.placebo}.json"
    (HERE / name).write_text(json.dumps(rows, indent=1, default=float))
    c = [r for r in rows if r["cand"]]
    print(f"  candidates: {len(c)} of {len(rows)}")
    for r in sorted(c, key=lambda r: -r["all"]["t"])[:20]:
        print(f"    {r['tf']} {r['scope']:7s} {r['near']:14s} {r['vol']:16s} {r['ctx']:12s} {r['dir']:5s} {r['exit']:4s} | A n {r['A']['n']} {r['A']['net']:+.3f} t {r['A']['t']:.1f} | "
              f"B n {r['B']['n']} {r['B']['net']:+.3f} t {r['B']['t']:.1f} | all {r['all']['net']:+.3f} t {r['all']['t']:.1f} gross {r['all']['gross']:+.3f} cost {r['all']['cost']:.3f}")


if __name__ == "__main__":
    main()
