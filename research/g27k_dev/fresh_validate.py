#!/usr/bin/env python3
"""Stage 2 gates 2-5 for layers L2 and L3 (ledger fresh_markets_search_v2).
Nothing here reads data from 2024-01-01 on (sealed).

  gate 2  per layer: the real top-100 median discovery t must beat the top-100
          median of every drift-placebo run, else the layer is empty
  gate 3  per candidate (the real top 100): t > 2 on group A 2020-2023 AND on
          group B 2012-2023, positive on >= 60% of markets in each, still
          positive at cost x2 and swap x2, and without its best market
  gate 4  >= 70% of parameter neighbours positive in discovery
          (L2: the 26 setups differing in one component; L3: each threshold
          moved one discovery decile either way)
  gate 5  cluster survivors by entry-day overlap, best per cluster, <= 3

Usage: python3 research/g27k_dev/fresh_validate.py --root <snap> l3|l2
"""
import argparse
import glob
import json
import pickle
import sys

import numpy as np
import pandas as pd

import pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import per_market_search as PMS
import walkforward_controller as W

LO, SP, HI = W.ts(L3.D0), W.ts(L3.SPLIT), W.ts(L3.SEAL)
MIN_N_L2 = 300


def tst(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else np.nan


def summarize(mk, R):
    R = np.asarray(R, float)
    if not len(R):
        return dict(n=0, R=np.nan, t=np.nan, pos_share=np.nan, R_wo_best=np.nan)
    s = pd.Series(R).groupby(np.asarray(mk)).sum()
    keep = np.asarray(mk) != s.idxmax()
    return dict(n=len(R), R=float(R.mean()), t=tst(R), pos_share=float((s > 0).mean()),
                R_wo_best=float(R[keep].mean()) if keep.any() else np.nan)


def gate2(real_top_t, placebo_top_ts):
    rm = float(np.median(real_top_t[:100]))
    pms = [float(np.median(x[:100])) for x in placebo_top_ts]
    return dict(real_median=rm, placebo_medians=pms, pass_=bool(len(pms) >= 10 and all(rm > p for p in pms)))


def gate3_ok(a, b, a2, b2):
    return bool(a["t"] > 2 and b["t"] > 2 and a["pos_share"] >= 0.6 and b["pos_share"] >= 0.6 and a2 > 0 and b2 > 0
                and a["R_wo_best"] > 0 and b["R_wo_best"] > 0)


# ------------------------------------------------------------------ L3 (free search)
class Events:
    """Built events for one market set and timeframe, at a cost multiplier."""
    def __init__(self, h1s, mult=1.0):
        self.h1s, self.mult, self.cache = h1s, mult, {}

    def get(self, tf):
        if tf not in self.cache:
            C = P._M["C"]
            base = {m: dict(C.SPECS[m]) for m in self.h1s}
            C.SPECS.update({m: dict(s, cost_rt_bp=s["cost_rt_bp"] * self.mult, swap_long_bp=s["swap_long_bp"] * self.mult,
                                    swap_short_bp=s["swap_short_bp"] * self.mult) for m, s in base.items()})
            P._M["h1"] = self.h1s
            self.cache[tf] = P.build(self.h1s, tf)
            C.SPECS.update(base)
        return self.cache[tf]


def l3_trades(ev, c, conds=None, lo=LO, hi=HI):
    E, feats, cats = ev.get(c["tf"])
    conds = conds or [W.parse(n) for n in c["names"]]
    ex = c["exit"]
    R = E[f"R_{ex}"]
    m = W.pmask(feats, cats, conds) & np.isfinite(R) & (E["t"] >= lo) & (E["t"] < hi)
    k = P.no_overlap(E, m, ex)
    return E["mkt"][k], R[k], E["t"][k]


def neighbours_l3(evA, c):
    E, feats, cats = evA.get(c["tf"])
    disc = (E["t"] >= LO) & (E["t"] < SP)
    conds = [W.parse(n) for n in c["names"]]
    out = []
    for i, (f, op, q) in enumerate(conds):
        if op == "cat":
            continue
        qs = np.unique(np.nanquantile(feats[f][disc], np.linspace(0.1, 0.9, 9)))
        j = int(np.argmin(np.abs(qs - q)))
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(qs):
                cc = list(conds)
                cc[i] = (f, op, float(qs[jj]))
                _, R, _ = l3_trades(evA, c, cc, LO, SP)
                out.append(float(R.mean()) if len(R) else np.nan)
    return out


def run_l3():
    real = pickle.loads((PMS.CACHE / "fresh_l3_real.pkl").read_bytes())
    top = real["top"]
    pls = [pickle.loads(open(p, "rb").read()) for p in sorted(glob.glob(str(PMS.CACHE / "fresh_l3_drift*.pkl")))]
    g2 = gate2([c["t_disc"] for c in top], [[c["t_disc"] for c in pl["top"]] for pl in pls])
    print(f"  L3 gate 2: real top-100 median t {g2['real_median']:.2f} vs placebo medians "
          f"{', '.join(f'{x:.2f}' for x in g2['placebo_medians'])} -> {'PASS' if g2['pass_'] else 'FAIL'} ({len(pls)} placebos)")
    res = dict(gate2=g2, candidates=[])
    hA = {m: L3.load(m) for m in L3.GROUP_A}
    hB = {m: L3.load(m) for m in L3.GROUP_B}
    evA, evB, evA2, evB2 = Events(hA), Events(hB), Events(hA, 2.0), Events(hB, 2.0)
    for i, c in enumerate(top):
        mkA, RA, tA = l3_trades(evA, c, None, SP, HI)
        mkB, RB, _ = l3_trades(evB, c, None, LO, HI)
        a, b = summarize(mkA, RA), summarize(mkB, RB)
        row = dict(rank=i + 1, tf=c["tf"], exit=c["exit"], names=c["names"], t_disc=c["t_disc"], A_val=a, B=b)
        if a["t"] > 2 and b["t"] > 2:
            _, RA2, _ = l3_trades(evA2, c, None, SP, HI)
            _, RB2, _ = l3_trades(evB2, c, None, LO, HI)
            row["A_val_cost2"], row["B_cost2"] = float(RA2.mean()), float(RB2.mean())
            row["gate3"] = gate3_ok(a, b, row["A_val_cost2"], row["B_cost2"])
            if row["gate3"]:
                nb = neighbours_l3(evA, c)
                row["neighbours"] = nb
                row["gate4"] = bool(np.mean(np.array(nb) > 0) >= 0.7) if nb else False
        else:
            row["gate3"] = False
        res["candidates"].append(row)
        print(f"  #{i + 1:3d} {c['tf']} {c['exit']:5s} {' & '.join(c['names'])[:60]:60s} disc t {c['t_disc']:5.2f} | "
              f"A20-23 n {a['n']:4d} R {a['R']:+.3f} t {a['t']:+.2f} | B n {b['n']:4d} R {b['R']:+.3f} t {b['t']:+.2f}"
              + ("  GATE3" if row.get("gate3") else "") + ("  GATE4" if row.get("gate4") else ""), flush=True)
    res["survivors"] = [r for r in res["candidates"] if r.get("gate4")]
    print(f"  L3: gate 3 passed {sum(r.get('gate3', False) for r in res['candidates'])}, gate 4 passed {len(res['survivors'])}")
    (HERE / "fresh_validate_l3.json").write_text(json.dumps(res, indent=1, default=float))


# ------------------------------------------------------------------ L2 (G27K grid)
def run_l2(root):
    import g27k_fast as GF
    real = pd.read_parquet(PMS.CACHE / "fresh_l2_real.parquet")
    pls = [pd.read_parquet(p) for p in sorted(glob.glob(str(PMS.CACHE / "fresh_l2_drift*.parquet")))]
    rank = lambda D: D[D.n_disc >= MIN_N_L2].sort_values("t_disc", ascending=False)
    R0 = rank(real)
    g2 = gate2(R0.t_disc.to_numpy(), [rank(D).t_disc.to_numpy() for D in pls])
    print(f"  L2 gate 2: real top-100 median t {g2['real_median']:.2f} vs placebo medians "
          f"{', '.join(f'{x:.2f}' for x in g2['placebo_medians'])} -> {'PASS' if g2['pass_'] else 'FAIL'} ({len(pls)} placebos)")
    res = dict(gate2=g2, candidates=[])
    K, C = P._M["K"], P._M["C"]
    K.START, K.SPLIT = LO, SP
    ext = K.externals()

    def prep(markets, mult):
        base = FM.specs(C)
        C.SPECS.update({m: dict(s, cost_rt_bp=s["cost_rt_bp"] * mult, swap_long_bp=s["swap_long_bp"] * mult,
                                swap_short_bp=s["swap_short_bp"] * mult) for m, s in base.items()})
        Ms = {m: K.prepare(m, L3.load(m), ext, "H4") for m in markets}
        C.SPECS.update(base)
        return Ms
    MA, MB, MA2, MB2 = prep(L3.GROUP_A, 1.0), prep(L3.GROUP_B, 1.0), prep(L3.GROUP_A, 2.0), prep(L3.GROUP_B, 2.0)

    def trades(Ms, combo, lo, hi):
        Cc, D, E, F, G, H, I, J = combo.split("/")
        mk, R = [], []
        for m, M in Ms.items():
            d = K.directions(M, Cc, D, E, J)
            s = np.flatnonzero(d)
            for x in GF.simulate(M, s, d[s], F, G, H, I, C.nights):
                if lo <= x[0] < hi:
                    mk.append(m); R.append(x[2])
        return np.array(mk), np.array(R, float)
    disc = real.set_index("combo")
    for i, (_, c) in enumerate(R0.head(100).iterrows()):
        a, b = summarize(*trades(MA, c.combo, SP, HI)), summarize(*trades(MB, c.combo, LO, HI))
        row = dict(rank=i + 1, combo=c.combo, t_disc=float(c.t_disc), R_disc=float(c.R_disc), A_val=a, B=b)
        if a["t"] > 2 and b["t"] > 2:
            row["A_val_cost2"] = float(trades(MA2, c.combo, SP, HI)[1].mean())
            row["B_cost2"] = float(trades(MB2, c.combo, LO, HI)[1].mean())
            row["gate3"] = gate3_ok(a, b, row["A_val_cost2"], row["B_cost2"])
            if row["gate3"]:
                parts = c.combo.split("/")
                opts = [K.CS, K.DS, K.ES, K.FS, K.GS, K.HS, K.IS, K.JS]
                nb = []
                for k, op in enumerate(opts):
                    for alt in op:
                        if alt != parts[k]:
                            nc = "/".join(parts[:k] + [alt] + parts[k + 1:])
                            if nc in disc.index:
                                nb.append(float(disc.loc[nc, "R_disc"]))
                row["neighbours"] = nb
                row["gate4"] = bool(np.mean(np.array(nb) > 0) >= 0.7)
        else:
            row["gate3"] = False
        res["candidates"].append(row)
        print(f"  #{i + 1:3d} {c.combo:28s} disc t {c.t_disc:5.2f} | A20-23 n {a['n']:4d} R {a['R']:+.3f} t {a['t']:+.2f} | "
              f"B n {b['n']:4d} R {b['R']:+.3f} t {b['t']:+.2f}" + ("  GATE3" if row.get("gate3") else "") + ("  GATE4" if row.get("gate4") else ""),
              flush=True)
    res["survivors"] = [r for r in res["candidates"] if r.get("gate4")]
    print(f"  L2: gate 3 passed {sum(r.get('gate3', False) for r in res['candidates'])}, gate 4 passed {len(res['survivors'])}")
    (HERE / "fresh_validate_l2.json").write_text(json.dumps(res, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("layer", choices=("l3", "l2"))
    a = ap.parse_args()
    P.setup(a.root)
    C = P._M["C"]
    C.SPECS.update(FM.specs(C))
    PMS.MKTS, PMS.SCOPES = L3.GROUP_A, ("pooled",)
    P._M.update(scopes=("pooled",), scope_sets={})
    run_l3() if a.layer == "l3" else run_l2(a.root)


if __name__ == "__main__":
    main()
