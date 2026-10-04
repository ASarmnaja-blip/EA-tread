#!/usr/bin/env python3
"""G27K-F over the last three years (2023-10-01..2026-09-30), fresh account,
locked risk (0.75%, 1%, 1% + brake 25%, all markets equal), Cent and Standard;
also without the Fed rule.

Usage: python3 research/g27k_dev/g27kf_last3y.py --root <snap>
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
import news_shock as NS

START, END = "2023-10-01", "2026-10-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P, RF, RSD, W, MMS, L3, FM, SU = NS.P, NS.RF, NS.RSD, NS.W, NS.MMS, NS.L3, NS.FM, NS.SU
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in RF.STD}
    RSD.START = "2011-09-01"
    news = W.news_times(a.root)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    sh = NS.fed_shocks(a.root)
    fed = NS.apply(raw, sh, H1, True)
    print(f"  Fed shocks in window: {int(((sh >= W.ts(START)) & (sh < W.ts(END))).sum())}  trades {len(raw)} -> {len(fed)}")
    out = {}
    for acct, ms in (("Cent", RF.CENT), ("Standard", RF.STD)):
        for nm, k, ver in (("0.75%", 0.75, "normal"), ("1%", 1.0, "normal"), ("1% + เบรก 25%", 1.0, "brake")):
            res = {}
            for tag, rows in (("F", fed), ("no Fed", raw)):
                rr = [r for r in rows if r["mkt"] in ms]
                F = pd.DataFrame(dict(mkt=[r["mkt"] for r in rr], t=[r["t"] for r in rr], tx=[r["t_exit"] for r in rr],
                                      R=[r["R"] * k for r in rr], vp=0.0, sc=[r["t"] for r in rr]))
                st, eq, _ = SU.simulate(F, ver, START, END, news=news)
                y = eq.resample("YE").last()
                yr = y / y.shift(1).fillna(1.0) - 1
                res[tag] = dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"], years={int(d.year): float(v) for d, v in yr.items()})
            out[f"{acct} {nm}"] = res
            f, n0 = res["F"], res["no Fed"]
            print(f"  {acct:8s} {nm:14s} G27K-F: x{f['final']:.2f} CAGR {f['cagr']:+.1%} DD {f['dd']:.1%} MAR {f['mar']:.2f} trades {f['n']} | "
                  + " ".join(f"{yy}:{v:+.0%}" for yy, v in f["years"].items()) + f" || no Fed: CAGR {n0['cagr']:+.1%} DD {n0['dd']:.1%}")
    (HERE / "g27kf_last3y.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
