#!/usr/bin/env python3
"""What if the rule had been chosen with earlier data only? Rank all 27,648
grid setups by t on the six markets in 2011-09..2019-12 (tf_l2_H4_real, at
least 300 trades), take the top 10, and trade each from 2020-01-01 to
2026-09-30 on a fresh account (brake, BTC/ETH 0.5%), Cent and Standard. G27K #1
(chosen while seeing 2021-2026) over the same window for comparison.

Usage: python3 research/g27k_dev/g27k_select_early.py --root <snap>
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
import g27k_filtered as GFV
import grid_diverse as GD
import h4d1_pattern_search as P
import per_market_search as PMS
import suite as SU
import tf_search as TS
import walkforward_controller as W

TEST0, END = "2020-01-01", "2026-10-01"
TOP = 10


def acct(T, mk, news):
    T = T[T.mkt.isin(mk)]
    T = T.assign(R=T.R * T.mkt.map(GFV.HALF).fillna(1.0), vp=0.0, sc=T.t)[["mkt", "t", "tx", "R", "vp", "sc"]]
    st, eq, _ = SU.simulate(T, "brake", TEST0, END, news=news)
    return dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    h = TS.setup(a.root, TS.END)
    K, C = P._M["K"], P._M["C"]
    K.START = W.ts("2011-09-01")
    ext = K.externals()
    Ms = {m: K.prepare(m, b, ext, "H4") for m, b in h.items()}
    news = W.news_times(a.root)
    g = pd.read_parquet(PMS.CACHE / "tf_l2_H4_real.parquet").set_index("combo")
    r = g[g.n_disc >= 300].sort_values("t_disc", ascending=False)
    rank1 = list(r.index).index(GFV.ONE) + 1
    print(f"  #1 ranks {rank1} of {len(r)} by 2011-2019 t")
    picks = list(r.index[:TOP])
    lo, hi = W.ts(TEST0), W.ts(END)
    res = []
    for i, combo in enumerate(picks + [GFV.ONE]):
        T = GD.trades(Ms, K, combo, C.nights)
        T = T[(T.t >= lo) & (T.t < hi)]
        row = dict(rank=i + 1 if combo != GFV.ONE else rank1, combo=combo, t_disc=float(r.loc[combo, "t_disc"]), R_disc=float(r.loc[combo, "R_disc"]),
                   n=len(T), R=float(T.R.mean()), cent=acct(T, GFV.ACCTS["Cent"], news), std=acct(T, GFV.ACCTS["Standard"], news))
        res.append(row)
        print(f"  {'#1 ' if combo == GFV.ONE else f'{i + 1:2d}.'} {combo}  2011-19 R {row['R_disc']:+.3f} t {row['t_disc']:.2f} | 2020-26 n {row['n']} R {row['R']:+.3f} | "
              f"Cent CAGR {row['cent']['cagr']:+.1%} DD {row['cent']['dd']:.1%} MAR {row['cent']['mar']:.2f} | "
              f"Std CAGR {row['std']['cagr']:+.1%} DD {row['std']['dd']:.1%} MAR {row['std']['mar']:.2f} x{row['std']['final']:.1f}", flush=True)
    top = res[:TOP]
    for k in ("cent", "std"):
        c = [x[k]["cagr"] for x in top]
        d = [x[k]["dd"] for x in top]
        print(f"  top {TOP} {k}: CAGR median {np.median(c):+.1%} (min {min(c):+.1%} max {max(c):+.1%})  DD median {np.median(d):.1%}  "
              f"positive {sum(v > 0 for v in c)}/{TOP}")
    (HERE / "g27k_select_early.json").write_text(json.dumps(dict(rank_of_1=rank1, pool=len(r), rows=res), indent=1, default=float))


if __name__ == "__main__":
    main()
