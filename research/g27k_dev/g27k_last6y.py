#!/usr/bin/env python3
"""G27K #1 over the last six years of data (2020-10-01..2026-09-30), a fresh
account at the start, brake version, Cent 5 / Standard 6 markets, crypto at 1%
or 0.5%. Same trades as report_final6.

Usage: python3 research/g27k_dev/g27k_last6y.py --root <snap>
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
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_final6 as RF
import report_suite_detail as RSD
import suite as SU
import walkforward_controller as W

START, END = "2020-10-01", "2026-10-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in RF.STD}
    RSD.START = "2011-09-01"
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    out = {}
    for s, (label, ms, w) in RF.SYS.items():
        rr = [r for r in rows if r["mkt"] in ms]
        scale = {m: w.get(m, 1.0) for m in ms}
        T = RF.frame(rr, scale)
        st, eq, _ = SU.simulate(T, "brake", START, END, news=news)
        y = eq.resample("YE").last()
        yr = (y / y.shift(1).fillna(1.0) - 1)
        R = np.array([r["R"] for r in rr])
        out[label] = dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"], win=float((R > 0).mean()),
                          R=float(R.mean()), years={int(k.year): float(v) for k, v in yr.items()},
                          per_mkt={m: dict(n=int(sum(r["mkt"] == m for r in rr)), R=float(np.mean([r["R"] for r in rr if r["mkt"] == m])),
                                           sumR=float(np.sum([r["R"] * scale[m] for r in rr if r["mkt"] == m]))) for m in ms})
        o = out[label]
        print(f"  {label:22s} x{o['final']:.2f} (${100_000 * o['final']:,.0f})  CAGR {o['cagr']:+.1%}  DD {o['dd']:.1%}  MAR {o['mar']:.2f}  "
              f"trades {o['n']}  win {o['win']:.0%}  R {o['R']:+.3f}")
        print("     years: " + "  ".join(f"{k} {v:+.0%}" for k, v in o["years"].items()))
        print("     markets: " + "  ".join(f"{m} n{v['n']} R{v['R']:+.2f} sumR{v['sumR']:+.0f}" for m, v in o["per_mkt"].items()))
    (HERE / "g27k_last6y.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
