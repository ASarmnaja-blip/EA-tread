#!/usr/bin/env python3
"""How the three H1 finalists of ledger h1_d1_search combine with G27K #1
(H4) at different risk per setup: drawdown, return, Monte Carlo and the peak
risk open at once. Scaling a stream's R by k is the same as trading it at k%
(profit = risk x balance x R). Brake 25% on the whole account, 2011-09..2026-09.

Usage: python3 research/g27k_dev/tf_combos.py --root <snap>
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
import per_market_search as PMS
import suite as SU
import tf_finalize as TF
import tf_search as TS
import walkforward_controller as W

S5 = TF.S5
PSTART, PMID, END = TF.PSTART, TF.PMID, TF.END


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    fin = json.loads((HERE / "tf_finalize_H1.json").read_text())["finalists"]
    h = TS.setup(a.root, END)
    TS.l3_setup({m: TS.cut(x, TS.D0, TS.CUT) for m, x in h.items()}, "H1")
    ev = FV.Events(h)
    streams = {}
    for i, k in enumerate(fin, 1):
        c = TF.parse_name(k["name"])
        E, feats, cats = ev.get("H1")
        R = E[f"R_{c['exit']}"]
        m = W.pmask(feats, cats, [W.parse(n) for n in c["names"]]) & np.isfinite(R) & (E["t"] >= TS.LO) & (E["t"] < TS.FIN)
        kk = P.no_overlap(E, m, c["exit"])
        streams[i] = pd.DataFrame(dict(mkt=E["mkt"][kk], t=E["t"][kk] + 3600, tx=E[f"tx_{c['exit']}"][kk], R=R[kk]))
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    PMS.END = END
    news = W.news_times(a.root)
    H1 = {m: MMS.load(m, G) for m in S5}
    g = SU.g27k_trades(S5, H1, RP, G, K, K.externals())[["mkt", "t", "tx", "R", "vp", "sc"]]
    cols = list(g.columns)

    def add(i, risk):
        x = streams[i][streams[i].mkt.isin(S5)]
        return x.assign(mkt=x.mkt + f"#H1{i}", R=x.R * (risk / 0.01), vp=0.0, sc=x.t)[cols]
    plans = {
        "G27K เท่านั้น": [],
        "+#1 1%": [(1, 0.01)], "+#2 1%": [(2, 0.01)], "+#3 1%": [(3, 0.01)],
        "+#1 0.5%": [(1, 0.005)],
        "+ทั้ง 3 ตัว 1% ต่อตัว": [(1, 0.01), (2, 0.01), (3, 0.01)],
        "+ทั้ง 3 ตัว 0.5% ต่อตัว": [(1, 0.005), (2, 0.005), (3, 0.005)],
        "+ทั้ง 3 ตัว 0.33% ต่อตัว": [(1, 0.0033), (2, 0.0033), (3, 0.0033)],
        "+#1 0.5% +#2 0.5%": [(1, 0.005), (2, 0.005)],
        "+#1 0.5% +#2 1%": [(1, 0.005), (2, 0.01)],
    }
    res = {}
    for name, parts in plans.items():
        TT = pd.concat([g] + [add(i, r) for i, r in parts], ignore_index=True)
        st, eq, risk = SU.simulate(TT, "brake", PSTART, END, news=news)
        a1, _, _ = SU.simulate(TT, "brake", PSTART, PMID, news=news)
        a2, _, _ = SU.simulate(TT, "brake", PMID, END, news=news)
        mc = SU.monte_carlo(eq)
        # peak open risk in % of balance (risk fraction x the stream's scale)
        scale = np.where(TT.mkt.str.contains("#H1"), 0.0, 1.0)
        for i, r in parts:
            scale = np.where(TT.mkt.str.endswith(f"#H1{i}"), r / 0.01, scale)
        TT2 = TT.loc[risk.index].assign(rf=risk.values * scale[risk.index])
        ev_ = sorted([(t, 1, i) for i, t in zip(TT2.index, TT2.t)] + [(tx, 0, i) for i, tx in zip(TT2.index, TT2.tx)])
        cur = peak = 0.0
        for _, kind, i in ev_:
            cur += TT2.rf[i] if kind else -TT2.rf[i]
            peak = max(peak, cur)
        res[name] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], worst=st["worst_year"],
                         p_dd50=mc["p_dd50"], dd_median=mc["dd_median"], peak_open_risk=peak)
        r_ = res[name]
        print(f"  {name:26s} CAGR {r_['cagr']:+6.1%}  DD {r_['dd']:5.1%}  MAR {r_['mar']:.2f}  halves {r_['mar_h1']:+.2f}/{r_['mar_h2']:+.2f}  "
              f"worst yr {r_['worst']:+.0%}  MC P(DD>50%) {r_['p_dd50']:.1%}  open risk peak {r_['peak_open_risk']:.1%}", flush=True)
    (HERE / "tf_combos.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
