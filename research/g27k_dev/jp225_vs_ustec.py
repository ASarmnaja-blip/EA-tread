#!/usr/bin/env python3
"""JP225 vs USTEC under G27K #1, 2012-01..2026-09: trade profile, costs, how
each index moves, and correlation with the other kept markets.

Usage: python3 research/g27k_dev/jp225_vs_ustec.py --root <snap>
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
import dropped_markets as DM
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import walkforward_controller as W

PAIR = ("JP225", "USTEC")
OTHERS = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    ext = K.externals()
    T, H = {}, {}
    for m in PAIR + OTHERS:
        b = MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", DM.HI)
        x = FM.trades(m, b, RP, G, K, ext)
        T[m] = x[(x.t >= W.ts(DM.LO)) & (x.t < W.ts(DM.HI))].copy()
        H[m] = b
    mon = lambda x: pd.Series(x.R.to_numpy(), index=pd.to_datetime(x.tx, unit="s")).resample("ME").sum()
    oth = pd.concat([mon(T[m]) for m in OTHERS], axis=1).fillna(0).sum(axis=1)
    out = {}
    for m in PAIR:
        x = T[m]
        w, l = x.R[x.R > 0], x.R[x.R <= 0]
        hold = (x.tx - x.t) / 86400
        b = H[m]
        d = pd.Series(b["c"], index=pd.to_datetime(b["t"], unit="s")).resample("D").last().dropna()
        d = d[(d.index >= DM.LO) & (d.index < DM.HI)]
        r = np.log(d).diff().dropna()
        dd = 1 - d / d.cummax()
        # how often a 5%+ pullback happens inside a rising year, and how deep moves run after a new 10-bar high
        mm = mon(x)
        i = mm.index.union(oth.index)
        corr = float(np.corrcoef(mm.reindex(i, fill_value=0), oth.reindex(i, fill_value=0))[0, 1])
        out[m] = dict(n=len(x), R=float(x.R.mean()), win=float((x.R > 0).mean()), avg_win=float(w.mean()), avg_loss=float(l.mean()),
                      payoff=float(w.mean() / -l.mean()), big=float((x.R >= 3).mean()), top10_share=float(x.R.nlargest(max(1, len(x) // 10)).sum() / x.R.sum()) if x.R.sum() > 0 else np.nan,
                      hold_days=float(hold.median()), swap_R=float(x.R_swap.mean()), R_before_swap=float((x.R + x.R_swap).mean()),
                      drift=float(r.mean() * 252), vol=float(r.std() * np.sqrt(252)), up_days=float((r > 0).mean()),
                      dd_max=float(dd.max()), dd_days_10=float((dd > 0.10).mean()), corr_others=corr,
                      half1=float(x.R[x.t < W.ts("2019-01-01")].mean()), half2=float(x.R[x.t >= W.ts("2019-01-01")].mean()))
    print(json.dumps(out, indent=1))
    (HERE / "jp225_vs_ustec.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
