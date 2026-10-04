#!/usr/bin/env python3
"""Last six years (2020-10-01..2026-09-30) of G27K #1 on the 6 kept and the 38
dropped markets: per market (trades, R, t, total R, positive years, per year)
and per group as an account (fresh $100,000, brake, 1% per trade).

Usage: python3 research/g27k_dev/dropped_last6y.py --root <snap>
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
import suite as SU
import walkforward_controller as W

START, END = "2020-10-01", "2026-10-01"
HALF = {"BTCUSD": 0.5, "ETHUSD": 0.5}


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
    news = W.news_times(a.root)
    allT = []
    for m in list(MMS.MARKETS) + list(FM.NEW):
        b = MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)
        T = FM.trades(m, b, RP, G, K, ext)
        allT.append(T[(T.t >= W.ts(START)) & (T.t < W.ts(END))].assign(mkt=m))
    T = pd.concat(allT, ignore_index=True)
    T["kept"] = T.mkt.isin(DM.KEPT)
    T["year"] = pd.to_datetime(T.t, unit="s").dt.year
    per = []
    for m, x in T.groupby("mkt"):
        yr = x.groupby("year").R.sum()
        per.append(dict(mkt=m, kept=bool(m in DM.KEPT), n=len(x), R=float(x.R.mean()), t=DM.tstat(x.R), sumR=float(x.R.sum()), win=float((x.R > 0).mean()),
                        pos_years=int((yr > 0).sum()), years={int(k): float(v) for k, v in yr.items()}))
    per.sort(key=lambda p: (not p["kept"], -p["sumR"]))
    for p in per:
        print(f"  {'KEEP' if p['kept'] else 'drop'} {p['mkt']:8s} n {p['n']:3d} R {p['R']:+.3f} t {p['t']:+.1f} sum {p['sumR']:+6.1f}R  + years {p['pos_years']}/{len(p['years'])}  "
              + " ".join(f"{y % 100:02d}:{v:+.0f}" for y, v in p["years"].items()))
    groups = {}
    for nm, k in (("kept", True), ("dropped", False)):
        x = T[T.kept == k]
        groups[nm] = dict(markets=int(x.mkt.nunique()), n=len(x), R=float(x.R.mean()), t=DM.tstat(x.R), pos_markets=int(sum(p["sumR"] > 0 for p in per if p["kept"] == k)),
                          years={int(y): float(v) for y, v in x.groupby("year").R.mean().items()})
    accts = {}
    for nm, sel, scale in (("6 ตลาดที่ใช้ · 1%", T.kept, {}), ("6 ตลาดที่ใช้ · คริปโต 0.5%", T.kept, HALF), ("38 ตลาดที่ตัด · 1%", ~T.kept, {}),
                           ("38 ตลาดที่ตัด · 0.25%", ~T.kept, "q"), ("5 ตลาดที่ตัดที่บวกสุด 6 ปี · 1%", T.mkt.isin([p["mkt"] for p in per if not p["kept"]][:5]), {})):
        x = T[sel]
        f = (lambda m: 0.25) if scale == "q" else (lambda m: scale.get(m, 1.0))
        F = pd.DataFrame(dict(mkt=x.mkt, t=x.t, tx=x.tx, R=x.R * x.mkt.map(f), vp=0.0, sc=x.t))
        st, eq, _ = SU.simulate(F, "brake", START, END, news=news)
        y = eq.resample("YE").last()
        yr = y / y.shift(1).fillna(1.0) - 1
        accts[nm] = dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"], years={int(k.year): float(v) for k, v in yr.items()})
        print(f"  {nm:34s} x{st['final']:.2f}  CAGR {st['cagr']:+.1%}  DD {st['dd']:.1%}  MAR {st['mar']:.2f}  trades {st['n']}  "
              + " ".join(f"{k.year % 100:02d}:{v:+.0%}" for k, v in yr.items()))
    for nm, g in groups.items():
        print(f"  {nm}: {g['markets']} markets, {g['n']} trades, R {g['R']:+.3f} t {g['t']:+.1f}, markets positive {g['pos_markets']}")
    (HERE / "dropped_last6y.json").write_text(json.dumps(dict(markets=per, groups=groups, accounts=accts), indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
