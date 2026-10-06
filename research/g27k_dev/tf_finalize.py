#!/usr/bin/env python3
"""Final steps of ledger h1_d1_search for one timeframe: gate 5 (cluster the
A/B candidates by entry-day overlap, keep the best per cluster, at most 3),
gate 6 (the 2024-01..2026-09 window, opened once here), and the combination
with G27K #1 (H4) on S5 and S4U at 1% each with the account brake 25%.

Usage: python3 research/g27k_dev/tf_finalize.py --root <snap> H1
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
import fresh_validate as FV
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import tf_search as TS
import walkforward_controller as W

S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
S4U = ("XAUUSD", "XAGUSD", "BTCUSD", "USDJPY")
PSTART, PMID, END = "2011-09-01", "2018-01-01", "2026-10-01"


def parse_name(name):
    tf, ex, rest = name.split(" ", 2)
    return dict(tf=tf, exit=ex, names=rest.split(" & "))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("tf", choices=("H1", "D1"))
    a = ap.parse_args()
    res = json.loads((HERE / f"tf_search_{a.tf}.json").read_text())
    graded = sorted(res["graded"], key=lambda c: (c["grade"], -c["val"]["t"]))
    assert all(c["layer"] == "L3" for c in graded), "L2 finalisation not implemented (no L2 candidate graded)"
    h_full = TS.setup(a.root, END)
    TS.l3_setup({m: TS.cut(h, TS.D0, TS.CUT) for m, h in h_full.items()}, a.tf)
    ev_full = FV.Events(h_full)

    def trades(c, lo, hi):
        mk, R, t = FV.l3_trades(ev_full, parse_name(c["name"]), None, lo, hi)
        return mk, R, t
    # gate 5: cluster by (market, entry day) overlap on 2011-09..2023-12
    kept = []
    for c in graded:
        mk, _, t = trades(c, TS.LO, TS.HI)
        key = set(zip(mk, (t // 86400).tolist()))
        dup = next((k for k in kept if len(key & k["key"]) / max(1, len(key | k["key"])) >= 0.5), None)
        if dup is None:
            kept.append(dict(c, key=key))
        else:
            dup.setdefault("cluster", []).append(c["name"])
        if len(kept) >= 3 and all(k["grade"] == "A" for k in kept):
            pass
    kept = kept[:3]
    print(f"  gate 5: {len(graded)} graded -> {len(kept)} finalists (clusters: " + ", ".join(str(1 + len(k.get('cluster', []))) for k in kept) + ")")
    # gate 6: the final window, once
    fin = []
    for k in kept:
        mk, R, t = trades(k, TS.HI, TS.FIN)
        s = TS.summarize(mk, R)
        k["final"] = s
        k["pass_final"] = bool(s["n"] > 0 and s["R"] > 0)
        print(f"  {k['grade']} {k['name'][:70]:70s} val R {k['val']['R']:+.3f} t {k['val']['t']:+.2f} | 2024-26 n {s['n']} R {s['R']:+.3f} "
              f"t {s['t']:+.2f} mk+ {s['pos_n']}/6 -> {'PASS' if k['pass_final'] else 'FAIL'}", flush=True)
        if k["pass_final"]:
            fin.append(k)
    out = dict(tf=a.tf, finalists=[{x: v for x, v in k.items() if x != "key"} for k in kept], combination={})
    # combination with G27K H4
    if fin:
        P.setup(a.root)
        G, K = P._M["G"], P._M["K"]
        sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
        import report768 as RP
        news = W.news_times(a.root)
        import per_market_search as PMS
        PMS.END = END          # l3_setup cut it to 2024 for the search; G27K needs the whole history here
        H1 = {m: MMS.load(m, G) for m in S5}
        assert max(int(h["t"][-1]) for h in H1.values()) > W.ts("2026-09-01"), "G27K data truncated"
        g = SU.g27k_trades(S5, H1, RP, G, K, K.externals())[["mkt", "t", "tx", "R", "vp", "sc"]]
        streams = {}
        for i, k in enumerate(fin):
            E, feats, cats = ev_full.get(a.tf)
            c = parse_name(k["name"])
            conds = [W.parse(n) for n in c["names"]]
            Rv = E[f"R_{c['exit']}"]
            msk = W.pmask(feats, cats, conds) & np.isfinite(Rv) & (E["t"] >= TS.LO) & (E["t"] < TS.FIN)
            kk = P.no_overlap(E, msk, c["exit"])
            sec = P.TF_SEC[c["tf"]]
            streams[f"{a.tf}#{i + 1}"] = pd.DataFrame(dict(mkt=E["mkt"][kk], t=E["t"][kk] + sec, tx=E[f"tx_{c['exit']}"][kk], R=Rv[kk]))
        for bname, bset in (("S5", S5), ("S4U", S4U)):
            B = g[g.mkt.isin(bset)]
            variants = {bname: B}
            allx = [B]
            for sname, T in streams.items():
                x = T[T.mkt.isin(bset)].assign(mkt=lambda d: d.mkt + "#" + sname, vp=0.0, sc=lambda d: d.t)[B.columns]
                variants[f"{bname}+{sname}"] = pd.concat([B, x], ignore_index=True)
                allx.append(x)
            if len(streams) > 1:
                variants[f"{bname}+all"] = pd.concat(allx, ignore_index=True)
            base = None
            for vn, TT in variants.items():
                st, eq, _ = SU.simulate(TT, "brake", PSTART, END, news=news)
                a1, _, _ = SU.simulate(TT, "brake", PSTART, PMID, news=news)
                a2, _, _ = SU.simulate(TT, "brake", PMID, END, news=news)
                mc = SU.monte_carlo(eq)
                row = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], worst=st["worst_year"],
                           n=st["n"], p_dd50=mc["p_dd50"])
                if base is None:
                    base = row
                    row["adopt"] = None
                else:
                    ok_half = lambda new, old: new >= old - 0.1 * abs(old)
                    row["adopt"] = bool(row["mar"] > base["mar"] and ok_half(row["mar_h1"], base["mar_h1"]) and ok_half(row["mar_h2"], base["mar_h2"])
                                        and row["p_dd50"] <= 0.05)
                out["combination"][vn] = row
                print(f"  {vn:12s} CAGR {row['cagr']:+6.1%}  DD {row['dd']:5.1%}  MAR {row['mar']:.2f}  halves {row['mar_h1']:+.2f}/{row['mar_h2']:+.2f}  "
                      f"worst yr {row['worst']:+.0%}  MC P(DD>50%) {row['p_dd50']:.1%}" + ("" if row["adopt"] is None else f"  adopt {row['adopt']}"), flush=True)
        # correlation of each stream with G27K (monthly R)
        mon = lambda d: pd.Series(d.R.to_numpy(), index=pd.to_datetime(d.tx, unit="s")).resample("ME").sum()
        gm = mon(g[g.t >= W.ts(PSTART)])
        for sname, T in streams.items():
            sm = mon(T)
            i = gm.index.union(sm.index)
            out.setdefault("corr_with_g27k", {})[sname] = float(np.corrcoef(gm.reindex(i, fill_value=0), sm.reindex(i, fill_value=0))[0, 1])
        print("  monthly R correlation with G27K H4:", {k: round(v, 2) for k, v in out["corr_with_g27k"].items()})
    (HERE / f"tf_finalize_{a.tf}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
