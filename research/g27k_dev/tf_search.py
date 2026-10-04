#!/usr/bin/env python3
"""H1 and D1 searches on the six main markets (ledger h1_d1_search,
docs/PLAN_H1_D1_SEARCH.md). Each timeframe is its own search.

  l2 <tf> real | placebo <first> <count>   G27K grid (27,648) on <tf>
  l3 <tf> real | placebo <first> <count>   free search on <tf> only
  grade <tf>                               gates 1-5 and grades A/B; the final
                                           2024-2026 window only for survivors

Search and validation read data before 2024-01-01 only.

Usage: python3 research/g27k_dev/tf_search.py --root <snap> l2 H1 real
"""
import argparse
import glob
import itertools
import json
import pickle
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_validate as FV
import g27k_fast as GF
import h4d1_pattern_search as P
import multi_market_search as MMS
import per_market_search as PMS
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY", "ETHUSD")
D0, SPLIT, CUT, END = "2011-09-01", "2020-01-01", "2024-01-01", "2026-10-01"
LO, SP, HI, FIN = W.ts(D0), W.ts(SPLIT), W.ts(CUT), W.ts(END)
MIN_N_L2 = {"H1": 300, "D1": 100}
OUT = PMS.CACHE


def cut(b, lo=D0, hi=CUT):
    t = np.asarray(b["t"], np.int64)
    k = (t >= W.ts(lo)) & (t < W.ts(hi))
    return {x: (v[k] if isinstance(v, np.ndarray) and len(v) == len(t) else v) for x, v in b.items()}


def setup(root, hi=CUT):
    P.setup(root)
    C = P._M["C"]
    C.SPECS.update(FM.specs(C))
    G = P._M["G"]
    return {m: cut(MMS.load(m, G), D0, hi) for m in MKTS}


# ------------------------------------------------------------------ L2
_W = {}


def _init(root, h1s, tf, mult=1.0):
    P.setup(root)
    K, C = P._M["K"], P._M["C"]
    base = FM.specs(C)
    C.SPECS.update(base)
    if mult != 1.0:
        C.SPECS.update({m: dict(C.SPECS[m], cost_rt_bp=C.SPECS[m]["cost_rt_bp"] * mult, swap_long_bp=C.SPECS[m]["swap_long_bp"] * mult,
                                swap_short_bp=C.SPECS[m]["swap_short_bp"] * mult) for m in h1s})
    K.START, K.SPLIT = LO, SP
    ext = K.externals()
    _W.update(K=K, nights=C.nights, M={m: K.prepare(m, b, ext, tf) for m, b in h1s.items()})


def _stats(R):
    n = len(R)
    if n < 3 or R.std(ddof=1) == 0:
        return n, (float(R.mean()) if n else np.nan), np.nan
    return n, float(R.mean()), float(R.mean() / R.std(ddof=1) * np.sqrt(n))


def _task(sig):
    K, Ms = _W["K"], _W["M"]
    Cc, D, E, J = sig
    dirs = {m: (lambda d: (np.flatnonzero(d), d[np.flatnonzero(d)]))(K.directions(M, Cc, D, E, J)) for m, M in Ms.items()}
    out = []
    for Fm, Gm, Hm, Im in K.SIM:
        te, R, mk = [], [], []
        for m in Ms:
            for x in GF.simulate(Ms[m], *dirs[m], Fm, Gm, Hm, Im, _W["nights"]):
                te.append(x[0]); R.append(x[2]); mk.append(m)
        te, R, mk = np.array(te, np.int64), np.array(R, float), np.array(mk)
        row = dict(combo="/".join((Cc, D, E, Fm, Gm, Hm, Im, J)))
        for nm, sel in (("disc", (te >= LO) & (te < SP)), ("val", (te >= SP) & (te < HI))):
            n, mu, t = _stats(R[sel])
            row.update({f"n_{nm}": n, f"R_{nm}": mu, f"t_{nm}": t})
        out.append(row)
    return out


def l2_run(root, h1s, tf, label, workers):
    t0 = time.time()
    sigs = list(itertools.product(("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"), tuple(f"D{i}" for i in range(1, 9)),
                                  ("E1", "E2", "E3"), ("J1", "J2")))
    rows = []
    with Pool(workers, initializer=_init, initargs=(root, h1s, tf)) as pool:
        for r in pool.imap_unordered(_task, sigs, chunksize=1):
            rows += r
    D = pd.DataFrame(rows)
    D.to_parquet(OUT / f"tf_l2_{tf}_{label}.parquet")
    ok = D[D.n_disc >= MIN_N_L2[tf]].sort_values("t_disc", ascending=False)
    print(f"  [L2 {tf} {label}] {len(ok):,} setups with n_disc >= {MIN_N_L2[tf]}; top-1 t {ok.t_disc.iloc[0]:.2f}; "
          f"top-100 median {ok.t_disc.head(100).median():.2f}  {time.time() - t0:.0f}s", flush=True)


def l2_trades(Ms, K, combo, lo, hi, nights):
    Cc, D, E, F, G_, H, I, J = combo.split("/")
    mk, R = [], []
    for m, M in Ms.items():
        d = K.directions(M, Cc, D, E, J)
        s = np.flatnonzero(d)
        for x in GF.simulate(M, s, d[s], F, G_, H, I, nights):
            if lo <= x[0] < hi:
                mk.append(m); R.append(x[2])
    return np.array(mk), np.array(R, float)


# ------------------------------------------------------------------ L3
def l3_setup(h1s, tf):
    PMS.MKTS, PMS.SCOPES, PMS.KEEP = MKTS, ("pooled",), 100
    PMS.SPLITS = {m: SPLIT for m in MKTS}
    PMS.TEST0, PMS.END = SPLIT, CUT
    P._M.update(scopes=("pooled",), scope_sets={})
    P._M["h1"] = h1s


def l3_run(h1s, tf, label):
    t0 = time.time()
    best, total = PMS.run_search(h1s, label, (tf,))
    top = best["pooled"]
    if label == "real":
        out = dict(total=total, top=[PMS.slim(c) for c in top])
    else:
        out = dict(total=total, top=[dict(t_disc=c["t_disc"]) for c in top])
    (OUT / f"tf_l3_{tf}_{label}.pkl").write_bytes(pickle.dumps(out))
    print(f"  [L3 {tf} {label}] {total:,} patterns; top-1 t {top[0]['t_disc']:.2f}; top-100 median {np.median([c['t_disc'] for c in top]):.2f}  "
          f"{time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------ grading
def grade_row(r, layer_wins, cand_wins):
    a = (layer_wins >= 10 and cand_wins >= 10 and r["val"]["t"] >= 2.5 and r["val"]["pos_n"] >= 5 and r["cost2"] > 0
         and r["val"]["R_wo_best"] > 0 and r["nb_share"] >= 0.7)
    b = (layer_wins >= 8 and cand_wins >= 8 and r["val"]["t"] >= 1.5 and r["val"]["pos_n"] >= 4 and r["cost2"] > 0
         and r["val"]["R_wo_best"] > 0 and r["nb_share"] >= 0.6)
    return "A" if a else "B" if b else None


def summarize(mk, R):
    s = FV.summarize(mk, R)
    if s["n"]:
        pm = pd.Series(R).groupby(np.asarray(mk)).sum()
        s["pos_n"] = int((pm > 0).sum())
    else:
        s["pos_n"] = 0
    return s


def grade(root, tf):
    res = {"tf": tf, "layers": {}}
    h1s = setup(root)
    K, C = P._M["K"], P._M["C"]
    K.START, K.SPLIT = LO, SP
    ext = K.externals()
    for layer in ("L2", "L3"):
        if layer == "L2":
            real = pd.read_parquet(OUT / f"tf_l2_{tf}_real.parquet")
            pls = [pd.read_parquet(p) for p in sorted(glob.glob(str(OUT / f"tf_l2_{tf}_drift*.parquet")))]
            rank = lambda D: D[D.n_disc >= MIN_N_L2[tf]].sort_values("t_disc", ascending=False)
            R0 = rank(real)
            top = [dict(combo=c.combo, t_disc=float(c.t_disc), R_disc=float(c.R_disc)) for _, c in R0.head(100).iterrows()]
            pl_top = [rank(D).t_disc.to_numpy() for D in pls]
        else:
            real = pickle.loads((OUT / f"tf_l3_{tf}_real.pkl").read_bytes())
            top = real["top"]
            pls = [pickle.loads(open(p, "rb").read()) for p in sorted(glob.glob(str(OUT / f"tf_l3_{tf}_drift*.pkl")))]
            pl_top = [np.array([c["t_disc"] for c in x["top"]]) for x in pls]
        rmed = float(np.median([c["t_disc"] for c in top]))
        pmeds = [float(np.median(x[:100])) for x in pl_top]
        layer_wins = int(sum(rmed > p for p in pmeds))
        pl_top1 = [float(x[0]) for x in pl_top]
        L = dict(real_median=rmed, placebo_medians=pmeds, layer_wins=layer_wins, n_placebos=len(pls), candidates=[])
        print(f"  {tf} {layer}: real top-100 median t {rmed:.2f} vs placebo medians {', '.join(f'{p:.2f}' for p in pmeds)} -> wins {layer_wins}/{len(pls)}")
        if layer_wins < 8:
            res["layers"][layer] = L
            continue
        if layer == "L2":
            Ms = {m: K.prepare(m, b, ext, tf) for m, b in h1s.items()}
            base = FM.specs(C)
            C.SPECS.update({m: dict(base[m], cost_rt_bp=base[m]["cost_rt_bp"] * 2, swap_long_bp=base[m]["swap_long_bp"] * 2,
                                    swap_short_bp=base[m]["swap_short_bp"] * 2) for m in MKTS})
            Ms2 = {m: K.prepare(m, b, ext, tf) for m, b in h1s.items()}
            C.SPECS.update(base)
            disc = real.set_index("combo")
        else:
            l3_setup(h1s, tf)
            ev, ev2 = FV.Events(h1s), FV.Events(h1s, 2.0)
        for i, c in enumerate(top):
            cand_wins = int(sum(c["t_disc"] > p for p in pl_top1))
            if layer == "L2":
                v = summarize(*l2_trades(Ms, K, c["combo"], SP, HI, C.nights))
            else:
                mk, R, _ = FV.l3_trades(ev, c, None, SP, HI)
                v = summarize(mk, R)
            row = dict(rank=i + 1, name=c.get("combo") or f"{c['tf']} {c['exit']} " + " & ".join(c["names"]), t_disc=c["t_disc"],
                       cand_wins=cand_wins, val=v, cost2=np.nan, nb_share=np.nan, grade=None)
            if cand_wins >= 8 and v["t"] >= 1.5 and v["pos_n"] >= 4 and v["R_wo_best"] > 0:
                if layer == "L2":
                    row["cost2"] = float(l2_trades(Ms2, K, c["combo"], SP, HI, C.nights)[1].mean())
                    parts = c["combo"].split("/")
                    nb = []
                    for k, op in enumerate([K.CS, K.DS, K.ES, K.FS, K.GS, K.HS, K.IS, K.JS]):
                        for alt in op:
                            if alt != parts[k]:
                                nc = "/".join(parts[:k] + [alt] + parts[k + 1:])
                                if nc in disc.index and np.isfinite(disc.loc[nc, "R_disc"]):
                                    nb.append(float(disc.loc[nc, "R_disc"]))
                else:
                    row["cost2"] = float(FV.l3_trades(ev2, c, None, SP, HI)[1].mean())
                    nb = FV.neighbours_l3(ev, c)
                row["nb_share"] = float(np.mean(np.array(nb) > 0)) if nb else 0.0
                row["grade"] = grade_row(row, layer_wins, cand_wins)
            L["candidates"].append(row)
            if row["grade"] or i < 5:
                print(f"    #{i + 1:3d} {row['name'][:70]:70s} disc t {c['t_disc']:5.2f} beats {cand_wins}/10 | val n {v['n']:4d} R {v['R']:+.3f} "
                      f"t {v['t']:+.2f} mk+ {v['pos_n']}/6 | cost2 {row['cost2']:+.3f} nb {row['nb_share']:.2f} -> {row['grade']}", flush=True)
        res["layers"][layer] = L
    surv = [dict(c, layer=l) for l, L in res["layers"].items() for c in L["candidates"] if c["grade"]]
    print(f"  {tf}: graded A/B before the final window: {len(surv)}")
    res["graded"] = surv
    (HERE / f"tf_search_{tf}.json").write_text(json.dumps(res, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("cmd", choices=("l2", "l3", "grade"))
    ap.add_argument("tf", choices=("H1", "D1"))
    ap.add_argument("mode", nargs="?", default="real")
    ap.add_argument("first", nargs="?", type=int, default=0)
    ap.add_argument("count", nargs="?", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "grade":
        return grade(a.root, a.tf)
    h1s = setup(a.root)
    if a.cmd == "l2":
        if a.mode == "real":
            l2_run(a.root, h1s, a.tf, "real", a.workers)
        else:
            P._M["h1"] = h1s
            for p in range(a.first, a.first + a.count):
                l2_run(a.root, P.drift_placebo(p), a.tf, f"drift{p}", a.workers)
    else:
        l3_setup(h1s, a.tf)
        if a.mode == "real":
            l3_run(h1s, a.tf, "real")
        else:
            for p in range(a.first, a.first + a.count):
                pl = P.drift_placebo(p)
                P._M["h1"] = pl
                l3_run(pl, a.tf, f"drift{p}")
                P._M["h1"] = h1s


if __name__ == "__main__":
    main()
