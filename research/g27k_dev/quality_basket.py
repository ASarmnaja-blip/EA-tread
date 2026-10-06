#!/usr/bin/env python3
"""Quality markets chosen blind (ledger g27k_blind_quality_basket).

Every 1 January 2012..2026 the markets to trade that year are chosen from
G27K #1 trades closed before that date only (expanding history, n >= 30):
  Q1  mean R > 0
  Q2  t of mean R > 1.0              (primary)
  Q3  the 5 best by t, with t > 0
pure = all 16 markets are candidates; anchored = gold, silver, BTC always
traded plus blind picks from the other 13. Compared on 2012-01..2026-10 with
all 16 and with the sets chosen in hindsight (S3, S4J, S4U, S5).

Usage: python3 research/g27k_dev/quality_basket.py --root <data-snapshot checkout>
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

START, MID, END = "2012-01-01", "2019-01-01", "2026-10-01"
M3 = ("XAUUSD", "XAGUSD", "BTCUSD")
HINDSIGHT = {"S3": M3, "S4J": M3 + ("JP225",), "S4U": M3 + ("USDJPY",), "S5": M3 + ("JP225", "USDJPY")}


def past_stats(g, year, cands):
    cut = W.ts(f"{year}-01-01")
    p = g[(g.tx < cut) & g.mkt.isin(cands)].groupby("mkt").R.agg(["count", "mean", "std"])
    p = p[p["count"] >= 30]
    p["t"] = p["mean"] / p["std"] * np.sqrt(p["count"])
    return p


RULES = {
    "Q1": lambda p: list(p.index[p["mean"] > 0]),
    "Q2": lambda p: list(p.index[p["t"] > 1.0]),
    "Q3": lambda p: list(p[p["t"] > 0].sort_values("t", ascending=False).index[:5]),
}


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
    res = {"picks": {}, "systems": {}, "per_market": {}}
    w = g[(g.t >= W.ts(START)) & (g.t < W.ts(END))]
    for m, x in w.groupby("mkt").R:
        res["per_market"][m] = dict(n=int(len(x)), mean=float(x.mean()), t=float(x.mean() / x.std() * np.sqrt(len(x))))
    print("  G27K #1 per market 2012-2026 (mean R, t):")
    for m, s in sorted(res["per_market"].items(), key=lambda kv: -kv[1]["mean"]):
        print(f"    {m:7s} n {s['n']:4d}  {s['mean']:+.3f}R  t {s['t']:+.2f}")

    systems = {"ALL16": g, **{k: g[g.mkt.isin(v)] for k, v in HINDSIGHT.items()}}
    others = [m for m in MMS.MARKETS if m not in M3]
    for rule, f in RULES.items():
        for variant, cands in (("pure", list(MMS.MARKETS)), ("anchored", others)):
            name = f"{rule}-{variant}"
            parts, picks = [], {}
            if variant == "anchored":
                parts.append(g[g.mkt.isin(M3)])
            for y in range(2012, 2027):
                chosen = f(past_stats(g, y, cands))
                picks[y] = chosen
                parts.append(g[g.mkt.isin(chosen) & (g.t >= W.ts(f"{y}-01-01")) & (g.t < W.ts(f"{y + 1}-01-01"))])
            res["picks"][name] = picks
            systems[name] = pd.concat(parts, ignore_index=True)
    print("  Q2-pure picks:")
    for y, ms in res["picks"]["Q2-pure"].items():
        print(f"    {y}: {', '.join(ms) if ms else '-'}")

    for name, T in systems.items():
        res["systems"][name] = {}
        for v in ("brake", "normal"):
            st, eq, risk = SU.simulate(T, v, START, END, news=news)
            a1, _, _ = SU.simulate(T, v, START, MID, news=news)
            a2, _, _ = SU.simulate(T, v, MID, END, news=news)
            st.update(mar_h1=a1["mar"], mar_h2=a2["mar"])
            tk = T.loc[risk.index[risk.values > 0]]
            ev = sorted([(t, 1) for t in tk.t] + [(t, -1) for t in tk.tx])
            cur = mx = 0
            for _, k in ev:
                cur += k
                mx = max(mx, cur)
            st["max_open"] = mx
            if v == "brake":
                st["mc"] = SU.monte_carlo(eq)
            res["systems"][name][v] = st
        s = res["systems"][name]["brake"]
        print(f"  {name:12s} brake CAGR {s['cagr']:+6.1%}  DD {s['dd']:5.1%}  MAR {s['mar']:.2f}  halves {s['mar_h1']:+.2f}/{s['mar_h2']:+.2f}  "
              f"worst yr {s['worst_year']:+.0%}  n {s['n']}  max open {s['max_open']}  MC P(DD>50%) {s['mc']['p_dd50']:.1%}", flush=True)
    p, b = res["systems"]["Q2-pure"]["brake"], res["systems"]["ALL16"]["brake"]
    res["verdict"] = dict(full=p["mar"] > b["mar"], h1=p["mar_h1"] > b["mar_h1"], h2=p["mar_h2"] > b["mar_h2"], mc=p["mc"]["p_dd50"] <= 0.05)
    res["verdict"]["pass"] = all(res["verdict"].values())
    print("  primary verdict", res["verdict"])
    (HERE / "quality_basket.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
