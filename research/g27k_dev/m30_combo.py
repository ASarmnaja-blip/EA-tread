#!/usr/bin/env python3
"""M30 trend-continuation sleeve together with G27K-F (ledger
m30_sleeve_with_g27kf; criterion fixed there).

Usage: python3 research/g27k_dev/m30_combo.py --root <snap>
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
import intraday_pattern_search as IP
import news_shock as NS
import per_market_search as PMS

START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
EX = "tp2"


def sleeve_trades():
    h1 = {m: PMS.load_m1(m) for m in PMS.MKTS}
    P._M["h1"] = h1
    P._M["frames_for"] = IP.frames_minute
    E, feats, cats = P.build(h1, "M30")
    m = np.isfinite(E[f"R_{EX}"]) & (feats["brk55"] >= -1.0) & (feats["atr_ratio"] >= 1.5) & cats["htf1_with"]
    k = P.no_overlap(E, m, EX)
    sec = P.TF_SEC["M30"]
    T = pd.DataFrame(dict(mkt=E["mkt"][k], t=(E["t"][k] + sec).astype(np.int64), tx=E[f"tx_{EX}"][k].astype(np.int64), R=E[f"R_{EX}"][k],
                          d=E["d"][k]))
    P._M.pop("frames_for", None)
    return T.sort_values("t").reset_index(drop=True)


def frame(rows_g, S, kg, ks, extra=0.0):
    g = pd.DataFrame(dict(mkt=[r["mkt"] for r in rows_g], t=[r["t"] for r in rows_g], tx=[r["t_exit"] for r in rows_g],
                          R=[(r["R"] - extra) * kg for r in rows_g]))
    parts = [g]
    if S is not None and ks > 0:
        parts.append(pd.DataFrame(dict(mkt=S.mkt + "_M30", t=S.t, tx=S.tx, R=(S.R - extra) * ks)))
    F = pd.concat(parts, ignore_index=True)
    return F.assign(vp=0.0, sc=F.t)


def acct(F, ver, news, start=START, end=END, mc=False):
    st, eq, _ = NS.SU.simulate(F, ver, start, end, news=news)
    out = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"])
    if mc:
        out["p50"] = NS.SU.monte_carlo(eq)["p_dd50"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    S = sleeve_trades()
    S = S[(S.t >= NS.W.ts(START)) & (S.t < NS.W.ts(END))]
    print(f"  sleeve: {len(S)} trades 2011-09..2026-09, R {S.R.mean():+.3f}  " + "  ".join(f"{m} {int((S.mkt == m).sum())}" for m in PMS.MKTS), flush=True)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(NS.FM.specs(C))
    H1 = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    news = NS.W.news_times(a.root)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, H1, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), H1, True)
    # overlap and correlation with G27K-F
    gd = pd.DataFrame(dict(mkt=[r["mkt"] for r in gf], t=[r["t"] for r in gf], tx=[r["t_exit"] for r in gf], R=[r["R"] for r in gf]))
    ov = 0
    for m in PMS.MKTS:
        s = S[S.mkt == m]
        g = gd[gd.mkt == m]
        for t, d in zip(s.t, s.d):
            ov += int(d > 0 and ((g.t <= t) & (g.tx > t)).any())      # G27K #1 is long only
    mon = lambda x: pd.Series(x.R.to_numpy(), index=pd.to_datetime(x.tx, unit="s")).resample("ME").sum()
    a_, b_ = mon(S), mon(gd)
    i = a_.index.union(b_.index)
    corr = float(np.corrcoef(a_.reindex(i, fill_value=0), b_.reindex(i, fill_value=0))[0, 1])
    print(f"  overlap: {ov / len(S):.0%} of sleeve trades open while a same-direction G27K-F trade is open | monthly R correlation {corr:+.2f}", flush=True)
    out = dict(sleeve=dict(n=len(S), R=float(S.R.mean()), overlap=ov / len(S), corr=corr), runs={})
    for acct_nm, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
        rows = [r for r in gf if r["mkt"] in ms]
        for gname, kg, ver in (("1% + brake", 1.0, "brake"), ("0.75%", 0.75, "normal")):
            res = {}
            for ks in (0.0, 0.25, 0.5, 1.0):
                F, Fs = frame(rows, S, kg, ks), frame(rows, S, kg, ks, 0.10)
                res[ks] = dict(full=acct(F, ver, news, mc=True), h1=acct(F, ver, news, end=MID), h2=acct(F, ver, news, start=MID), stress=acct(Fs, ver, news))
                r = res[ks]
                print(f"  {acct_nm:8s} G27K-F {gname:10s} + sleeve {ks:.2f}%: CAGR {r['full']['cagr']:+6.1%} DD {r['full']['dd']:5.1%} MAR {r['full']['mar']:.2f} | "
                      f"halves MAR {r['h1']['mar']:+.2f}/{r['h2']['mar']:+.2f} | -0.10R MAR {r['stress']['mar']:.2f} | P(DD>50%) {r['full']['p50']:.1%} | trades {r['full']['n']}",
                      flush=True)
            b, s5 = res[0.0], res[0.5]
            ok = bool(s5["full"]["mar"] > b["full"]["mar"] and s5["h1"]["mar"] > b["h1"]["mar"] and s5["h2"]["mar"] > b["h2"]["mar"]
                      and s5["stress"]["mar"] > b["stress"]["mar"] and s5["full"]["p50"] <= b["full"]["p50"] + 0.01)
            out["runs"][f"{acct_nm} {gname}"] = dict(res={str(k): v for k, v in res.items()}, pass_=ok)
            print(f"    -> sleeve 0.5% {'PASSES' if ok else 'fails'} for {acct_nm} {gname}", flush=True)
    main_ok = out["runs"]["Cent 1% + brake"]["pass_"] and out["runs"]["Standard 1% + brake"]["pass_"]
    print(f"  VERDICT (Cent and Standard, 1% + brake): {'ADOPT sleeve 0.5%' if main_ok else 'do not adopt'}")
    out["verdict"] = main_ok
    (HERE / "m30_combo.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
