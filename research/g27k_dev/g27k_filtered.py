#!/usr/bin/env python3
"""G27K #1 against four filtered one-slot variants at account level
(ledger g27k_filtered_variants; criterion fixed there before this ran).

Usage: python3 research/g27k_dev/g27k_filtered.py --root <snap>
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
import grid_diverse as GD
import h4d1_pattern_search as P
import suite as SU
import tf_search as TS
import walkforward_controller as W

ONE = "C8/D3/E1/F1/G2/H2/I1/J1"
VARS = {"#1": ONE, "V1 C2": "C2/D3/E1/F1/G2/H2/I1/J1", "V2 D2": "C8/D2/E1/F1/G2/H2/I1/J1",
        "V3 D4": "C8/D4/E1/F1/G2/H2/I1/J1", "V4 D6": "C8/D6/E1/F1/G2/H2/I1/J1"}
CENT = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")
ACCTS = {"Cent": CENT, "Standard": CENT + ("JP225",)}
HALF = {"BTCUSD": 0.5, "ETHUSD": 0.5}
START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
GATE = "2024-01-01"


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def account(T, mk, news):
    T = T[T.mkt.isin(mk)]
    T = T.assign(R=T.R * T.mkt.map(HALF).fillna(1.0), vp=0.0, sc=T.t)[["mkt", "t", "tx", "R", "vp", "sc"]]
    st, eq, _ = SU.simulate(T, "brake", START, END, news=news)
    a1, _, _ = SU.simulate(T, "brake", START, MID, news=news)
    a2, _, _ = SU.simulate(T, "brake", MID, END, news=news)
    g, _, _ = SU.simulate(T, "brake", GATE, END, news=news)
    return dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], cagr_h1=a1["cagr"], cagr_h2=a2["cagr"],
                ret_gate=g["final"] - 1, p_dd50=SU.monte_carlo(eq)["p_dd50"], n=st["n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    h = TS.setup(a.root, TS.END)
    K, C = P._M["K"], P._M["C"]
    K.START = W.ts(START)
    ext = K.externals()
    Ms = {m: K.prepare(m, b, ext, "H4") for m, b in h.items()}
    base = {m: dict(C.SPECS[m]) for m in Ms}
    C.SPECS.update({m: dict(s, cost_rt_bp=s["cost_rt_bp"] * 2, swap_long_bp=s["swap_long_bp"] * 2, swap_short_bp=s["swap_short_bp"] * 2)
                    for m, s in base.items()})
    Ms2 = {m: K.prepare(m, b, ext, "H4") for m, b in h.items()}
    C.SPECS.update(base)
    news = W.news_times(a.root)
    lo, hi = W.ts(START), W.ts(END)
    res = {}
    for nm, combo in VARS.items():
        T = GD.trades(Ms, K, combo, C.nights)
        T = T[(T.t >= lo) & (T.t < hi)]
        J = GD.trades(Ms2, K, combo, C.nights, late=True)
        J = J[(J.t >= lo) & (J.t < hi)].assign(R=lambda d: d.R - 0.05)
        r = dict(combo=combo, n=len(T), R=float(T.R.mean()), t=tstat(T.R), R_h1=float(T.R[T.t < W.ts(MID)].mean()),
                 R_h2=float(T.R[T.t >= W.ts(MID)].mean()), R_j=float(J.R.mean()), t_j=tstat(J.R), acct={}, stress={})
        for an, mk in ACCTS.items():
            r["acct"][an] = account(T, mk, news)
            r["stress"][an] = account(J, mk, news)
        res[nm] = r
        print(f"  {nm:6s} {combo}  n {r['n']}  R {r['R']:+.3f} t {r['t']:.2f}  halves {r['R_h1']:+.3f}/{r['R_h2']:+.3f}  (j) {r['R_j']:+.3f} t {r['t_j']:.2f}")
        for an in ACCTS:
            x, s = r["acct"][an], r["stress"][an]
            print(f"     {an:8s} CAGR {x['cagr']:+6.1%} DD {x['dd']:5.1%} MAR {x['mar']:.2f} | 2011-18 CAGR {x['cagr_h1']:+.1%} MAR {x['mar_h1']:+.2f} | "
                  f"2019-26 MAR {x['mar_h2']:+.2f} | 2024-26 {x['ret_gate']:+.0%} | P(DD>50%) {x['p_dd50']:.1%} | (j) CAGR {s['cagr']:+.1%} MAR {s['mar']:.2f}", flush=True)
    b = res["#1"]
    passed = []
    for nm, r in res.items():
        if nm == "#1":
            continue
        chk = {}
        for an in ACCTS:
            x, y = r["acct"][an], b["acct"][an]
            chk[an] = dict(h1=x["mar_h1"] > y["mar_h1"], h2=x["mar_h2"] > y["mar_h2"], stress=r["stress"][an]["mar"] > b["stress"][an]["mar"],
                           mc=x["p_dd50"] <= y["p_dd50"] + 0.005)
        r["checks"] = chk
        r["pass"] = all(all(v.values()) for v in chk.values())
        print(f"  {nm}: " + " | ".join(f"{an} " + " ".join(f"{k}{'✓' if v else '✗'}" for k, v in c.items()) for an, c in chk.items())
              + f"  -> {'PASS' if r['pass'] else 'FAIL'}")
        if r["pass"]:
            passed.append(nm)
    pick = max(passed, key=lambda n: res[n]["acct"]["Standard"]["mar_h1"]) if passed else None
    gate = None
    if pick:
        gate = res[pick]["acct"]["Standard"]["ret_gate"] >= 0.9 * b["acct"]["Standard"]["ret_gate"]
        print(f"  pick {pick}: 2024-26 Standard {res[pick]['acct']['Standard']['ret_gate']:+.0%} vs #1 {b['acct']['Standard']['ret_gate']:+.0%} -> "
              f"{'PASS' if gate else 'FAIL'}")
    print(f"  VERDICT: {'adopt ' + pick + ' as forward-test candidate' if pick and gate else 'keep #1'}")
    (HERE / "g27k_filtered.json").write_text(json.dumps(dict(results=res, passed=passed, pick=pick, gate=gate), indent=1, default=float))


if __name__ == "__main__":
    main()
