#!/usr/bin/env python3
"""Ledger m30_sleeve_new_markets, part 2: G27K-F with the extended M30 sleeve
(the original three markets plus the new markets part 1 added) against
G27K-F alone and against the three-market sleeve, Cent and Standard, G27K-F
at 0.75% / 1% / 1% + brake 25%, sleeve 0.5% per trade. Same four conditions
as m30_sleeve_with_g27kf, judged at 1% + brake 25%.

Needs .cache_wf/m30_sleeve6.pkl and m30_new_markets.json from m30_new_markets.py.

Usage: python3 research/g27k_dev/m30_combo6.py --root <snap> [--all-new]
  --all-new   descriptive run with all three new markets whatever part 1 said
"""
import argparse
import json
import pathlib
import pickle
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import m30_combo as MC
import m30_new_markets as NM
import news_shock as NS
import per_market_search as PMS

START, MID, END = MC.START, MC.MID, MC.END
VCONF = {"0.75%": (0.75, "normal"), "1%": (1.0, "normal"), "1% + brake": (1.0, "brake")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--all-new", action="store_true")
    ap.add_argument("--cent", default="", help="markets tradable on the Cent account")
    a = ap.parse_args()
    if a.cent:
        NS.RF.CENT = tuple(a.cent.split(","))
    P.setup(a.root)
    S = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    p1 = json.loads((HERE / "m30_new_markets.json").read_text())
    new = list(NM.NEW) if a.all_new else p1["added"]
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(NS.FM.specs(C))
    H1 = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    news = NS.W.news_times(a.root)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, H1, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), H1, True)
    out = dict(new_markets=new, runs={})
    for acct_nm, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
        rows = [r for r in gf if r["mkt"] in ms]
        s3 = S[S.mkt.isin(NM.OLD)]
        s6 = S[S.mkt.isin(list(NM.OLD) + [m for m in new if m in ms])]
        for vn, (kg, ver) in VCONF.items():
            res = {}
            for nm, sl, ks in (("F", None, 0.0), ("F+M30x3", s3, 0.5), ("F+M30ext", s6, 0.5)):
                F, Fs = MC.frame(rows, sl, kg, ks), MC.frame(rows, sl, kg, ks, 0.10)
                res[nm] = dict(full=MC.acct(F, ver, news, mc=True), h1=MC.acct(F, ver, news, end=MID), h2=MC.acct(F, ver, news, start=MID),
                               stress=MC.acct(Fs, ver, news))
                r = res[nm]
                print(f"  {acct_nm:8s} {vn:10s} {nm:9s} CAGR {r['full']['cagr']:+6.1%} DD {r['full']['dd']:5.1%} MAR {r['full']['mar']:.2f} | halves {r['h1']['mar']:+.2f}/{r['h2']['mar']:+.2f} "
                      f"| -0.10R MAR {r['stress']['mar']:.2f} | P(DD>50%) {r['full']['p50']:.1%} | trades {r['full']['n']}", flush=True)
            b, x = res["F"], res["F+M30ext"]
            ok = bool(x["full"]["mar"] > b["full"]["mar"] and x["h1"]["mar"] > b["h1"]["mar"] and x["h2"]["mar"] > b["h2"]["mar"]
                      and x["stress"]["mar"] > b["stress"]["mar"] and x["full"]["p50"] <= b["full"]["p50"] + 0.01)
            out["runs"][f"{acct_nm} {vn}"] = dict(res=res, pass_=ok)
            print(f"    -> extended sleeve {'PASSES' if ok else 'fails'} for {acct_nm} {vn}", flush=True)
    v = bool(new) and out["runs"]["Cent 1% + brake"]["pass_"] and out["runs"]["Standard 1% + brake"]["pass_"]
    out["verdict"] = v
    print(f"  PART 2 VERDICT (Cent and Standard, 1% + brake): {'ADOPT extended sleeve' if v else 'do not adopt'}")
    (HERE / (("m30_combo6_allnew" if a.all_new else "m30_combo6") + ("_cent" + str(len(NS.RF.CENT)) if a.cent else "") + ".json")).write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
