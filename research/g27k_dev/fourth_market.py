#!/usr/bin/env python3
"""Fourth market chosen blind, every 1 January from past trades only
(ledger g27k_fourth_market_walkforward).

Usage: python3 research/g27k_dev/fourth_market.py --root <data-snapshot checkout>
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
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

START, END = "2015-01-01", "2026-10-01"
TARGET = SU.TARGET
CANDS = [m for m in MMS.MARKETS if m not in TARGET]


def choose(g, year):
    cut = W.ts(f"{year}-01-01")
    past = g[(g.tx < cut) & g.mkt.isin(CANDS)].groupby("mkt").R.agg(["count", "mean"])
    past = past[(past["count"] >= 30) & (past["mean"] > 0)]
    return (past["mean"].idxmax(), past.loc[past["mean"].idxmax()].to_dict(), past["mean"].sort_values(ascending=False).round(3).to_dict()) if len(past) else (None, None, {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    H1 = {m: MMS.load(m, G) for m in MMS.MARKETS}
    g = SU.g27k_trades(MMS.MARKETS, H1, RP, G, K, K.externals())
    news = W.news_times(a.root)
    B3 = g[g.mkt.isin(TARGET)]
    picks, parts = {}, [B3]
    for y in range(2015, 2027):
        m, st, ranking = choose(g, y)
        picks[y] = dict(market=m, stats=st, ranking=ranking)
        if m:
            parts.append(g[(g.mkt == m) & (g.t >= W.ts(f"{y}-01-01")) & (g.t < W.ts(f"{y + 1}-01-01"))])
        print(f"  {y}: {m}  (past mean R {st['mean']:+.3f}, n {int(st['count'])})" if m else f"  {y}: none", flush=True)
    B4wf = pd.concat(parts, ignore_index=True)
    res = dict(picks=picks, systems={})
    systems = {"B3": B3, "B4wf": B4wf, "B4_JP225_hindsight": g[g.mkt.isin(TARGET + ("JP225",))]}
    for c in CANDS:
        systems[f"B3+{c}"] = g[g.mkt.isin(TARGET + (c,))]
    for name, T in systems.items():
        res["systems"][name] = {}
        for v in ("brake", "normal"):
            st, eq, _ = SU.simulate(T, v, START, END, news=news)
            st["mar_bal"] = st["cagr"] / st["dd"] if st["dd"] else None
            if v == "brake":
                st["mc"] = SU.monte_carlo(eq)
            res["systems"][name][v] = st
    rnd = [res["systems"][f"B3+{c}"]["brake"] for c in CANDS]
    res["random_pick_avg_brake"] = dict(cagr=float(np.mean([r["cagr"] for r in rnd])), dd=float(np.mean([r["dd"] for r in rnd])))
    for name in ("B3", "B4wf", "B4_JP225_hindsight"):
        for v in ("brake", "normal"):
            s = res["systems"][name][v]
            print(f"  {name:20s} {v:6s} CAGR {s['cagr']:+.1%} DD {s['dd']:.1%} MAR {s['mar_bal']:.2f} n {s['n']}"
                  + (f"  MC P(DD>50%) {s['mc']['p_dd50']:.1%}" if 'mc' in s else ""))
    print(f"  random 4th market (avg of 13, brake): CAGR {res['random_pick_avg_brake']['cagr']:+.1%} DD {res['random_pick_avg_brake']['dd']:.1%}")
    for c in CANDS:
        s = res["systems"][f"B3+{c}"]["brake"]
        print(f"    B3+{c:7s} CAGR {s['cagr']:+.1%} DD {s['dd']:.1%}")
    (HERE / "fourth_market.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
