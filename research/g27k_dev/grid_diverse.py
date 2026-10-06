#!/usr/bin/env python3
"""Grid setups that win and behave differently from G27K #1 (ledger grid_diverse_from_g27k1).

Pool (selection reads nothing from 2024 on): six main markets H4, t > 2 in
2011-09..2019-12 and in 2020-01..2023-12 (tf_l2_H4_real), positive on gold,
silver and BTC in 2017-01..2021-09 (g27k_early). Different from #1 on
2011-09..2023-12: <= 30% of its trades open while a same-direction #1 trade is
open in the same market, and monthly R correlation <= 0.30. Ranked by
2020-2023 t; a new pick must overlap <= 50% with each earlier pick; max 3.
Then 2024-01..2026-09 once, the execution stress (costs x2 + 0.05R + one H1
bar late), and the account check with G27K #1 on S5 and S4U.

Usage: python3 research/g27k_dev/grid_diverse.py --root <snap>
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
import g27k_fast as GF
import h4d1_pattern_search as P
import per_market_search as PMS
import suite as SU
import tf_search as TS
import walkforward_controller as W

ONE = "C8/D3/E1/F1/G2/H2/I1/J1"
S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
S4U = ("XAUUSD", "XAGUSD", "BTCUSD", "USDJPY")
LO, CUT, FIN = W.ts("2011-09-01"), W.ts("2024-01-01"), W.ts("2026-10-01")
PSTART, PMID, END = "2011-09-01", "2018-01-01", "2026-10-01"


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def trades(Ms, K, combo, nights, late=False):
    Cc, D, E, F, G_, H, I, J = combo.split("/")
    out = []
    for m, M in Ms.items():
        d = K.directions(M, Cc, D, E, J)
        s = np.flatnonzero(d)
        out += [(m, *x) for x in GF.simulate(M, s, d[s], F, G_, H, I, nights, late)]
    return pd.DataFrame(out, columns=["mkt", "t", "tx", "R", "d"])


def overlap_share(A, B):
    """Share of A's trades open while a same-direction B trade is open in the same market."""
    hit = 0
    for (m, d), a in A.groupby(["mkt", "d"]):
        b = B[(B.mkt == m) & (B.d == d)].sort_values("t")
        if not len(b):
            continue
        t1, x1 = b.t.to_numpy(), np.maximum.accumulate(b.tx.to_numpy())
        j = np.searchsorted(t1, a.tx.to_numpy(), side="left") - 1
        hit += int(((j >= 0) & (x1[np.maximum(j, 0)] > a.t.to_numpy())).sum())
    return hit / max(1, len(A))


def monthly(T):
    return pd.Series(T.R.to_numpy(), index=pd.to_datetime(T.tx, unit="s")).resample("ME").sum()


def corr(A, B):
    a, b = monthly(A), monthly(B)
    i = a.index.union(b.index)
    return float(np.corrcoef(a.reindex(i, fill_value=0), b.reindex(i, fill_value=0))[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    h = TS.setup(a.root, TS.END)
    K, C = P._M["K"], P._M["C"]
    K.START = LO
    ext = K.externals()
    Ms = {m: K.prepare(m, b, ext, "H4") for m, b in h.items()}
    base = {m: dict(C.SPECS[m]) for m in Ms}
    C.SPECS.update({m: dict(s, cost_rt_bp=s["cost_rt_bp"] * 2, swap_long_bp=s["swap_long_bp"] * 2, swap_short_bp=s["swap_short_bp"] * 2)
                    for m, s in base.items()})
    Ms2 = {m: K.prepare(m, b, ext, "H4") for m, b in h.items()}
    C.SPECS.update(base)
    grid = pd.read_parquet(PMS.CACHE / "tf_l2_H4_real.parquet").set_index("combo")
    early = pd.read_csv(pathlib.Path(a.root) / "data" / "grid27k" / "g27k_early.csv").set_index("combo")
    pool = grid[(grid.t_disc > 2) & (grid.t_val > 2)].join(early[["totR", "n"]].rename(columns={"totR": "totR_e", "n": "n_e"}))
    pool = pool[(pool.totR_e > 0) & (pool.index != ONE)].sort_values("t_val", ascending=False)
    one = trades(Ms, K, ONE, C.nights)
    one_sel = one[(one.t >= LO) & (one.t < CUT)]
    print(f"  pool: {len(pool)} setups (t>2 in 2011-19 and 2020-23, positive 2017-21 on gold/silver/BTC); #1 has {len(one_sel)} trades 2011-2023")
    rows, picks = [], []
    for combo, r in pool.iterrows():
        T = trades(Ms, K, combo, C.nights)
        Ts = T[(T.t >= LO) & (T.t < CUT)]
        if len(Ts) < 30:
            continue
        ov, cr = overlap_share(Ts, one_sel), corr(Ts, one_sel)
        rows.append(dict(combo=combo, t_disc=float(r.t_disc), t_val=float(r.t_val), R_val=float(r.R_val), overlap_1=ov, corr_1=cr,
                         short_share=float((Ts.d < 0).mean())))
        if ov <= 0.30 and cr <= 0.30 and len(picks) < 3:
            if all(max(overlap_share(Ts, p["sel"]), overlap_share(p["sel"], Ts)) <= 0.50 for p in picks):
                picks.append(dict(combo=combo, T=T, sel=Ts, t_val=float(r.t_val), R_val=float(r.R_val), overlap_1=ov, corr_1=cr))
                print(f"  pick {len(picks)}: {combo}  2020-23 R {r.R_val:+.3f} t {r.t_val:.2f} | overlap with #1 {ov:.0%} corr {cr:+.2f} "
                      f"| shorts {(Ts.d < 0).mean():.0%}", flush=True)
    D = pd.DataFrame(rows)
    ok = D[(D.overlap_1 <= 0.30) & (D.corr_1 <= 0.30)]
    print(f"  checked {len(D)}; different from #1 (overlap <= 30% and corr <= 0.30): {len(ok)}")
    if len(ok):
        print("  their entry types:", ok.combo.str.split("/").str[1].value_counts().to_dict(), " directions:", ok.combo.str.split("/").str[7].value_counts().to_dict())
    res = dict(pool=len(pool), checked=len(D), different=len(ok), picks=[])
    # final window, stress, account
    P.setup(a.root)
    G = P._M["G"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    import multi_market_search as MMS
    PMS.END = END
    news = W.news_times(a.root)
    H1 = {m: MMS.load(m, G) for m in S5}
    g = SU.g27k_trades(S5, H1, RP, G, P._M["K"], P._M["K"].externals())[["mkt", "t", "tx", "R", "vp", "sc"]]
    for p in picks:
        T = p["T"]
        fin = T[(T.t >= CUT) & (T.t < FIN)]
        J = trades(Ms2, K, p["combo"], C.nights, late=True)
        J = J[(J.t >= LO) & (J.t < FIN)]
        J = J.assign(R=J.R - 0.05)
        full = T[(T.t >= LO) & (T.t < FIN)]
        pr = dict(combo=p["combo"], R_val=p["R_val"], t_val=p["t_val"], overlap_1=p["overlap_1"], corr_1=p["corr_1"],
                  final_n=len(fin), final_R=float(fin.R.mean()) if len(fin) else np.nan, final_t=tstat(fin.R),
                  stress_R=float(J.R.mean()), stress_t=tstat(J.R), corr_1_full=corr(full, one[(one.t >= LO) & (one.t < FIN)]))
        pr["pass_final"] = bool(pr["final_n"] > 0 and pr["final_R"] > 0)
        pr["pass_stress"] = bool(pr["stress_R"] > 0 and pr["stress_t"] > 2)
        pr["account"] = {}
        for bname, bset in (("S5", S5), ("S4U", S4U)):
            B = g[g.mkt.isin(bset)]
            x = full[full.mkt.isin(bset)].assign(mkt=lambda d: d.mkt + "#2", vp=0.0, sc=lambda d: d.t)[B.columns]
            for vn, TT in ((bname, B), (bname + "+pick", pd.concat([B, x], ignore_index=True))):
                st, eq, _ = SU.simulate(TT, "brake", PSTART, END, news=news)
                a1, _, _ = SU.simulate(TT, "brake", PSTART, PMID, news=news)
                a2, _, _ = SU.simulate(TT, "brake", PMID, END, news=news)
                mc = SU.monte_carlo(eq)
                pr["account"][vn] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], worst=st["worst_year"],
                                         p_dd50=mc["p_dd50"])
            b0, b1 = pr["account"][bname], pr["account"][bname + "+pick"]
            okh = lambda new, old: new >= old - 0.1 * abs(old)
            pr["account"][bname + "_adopt"] = bool(pr["pass_final"] and pr["pass_stress"] and b1["mar"] > b0["mar"] and okh(b1["mar_h1"], b0["mar_h1"])
                                                   and okh(b1["mar_h2"], b0["mar_h2"]) and b1["p_dd50"] <= 0.05 and pr["corr_1_full"] <= 0.30)
        res["picks"].append(pr)
        print(f"\n  {p['combo']}: 2024-26 n {pr['final_n']} R {pr['final_R']:+.3f} t {pr['final_t']:+.2f} -> {'PASS' if pr['pass_final'] else 'FAIL'} | "
              f"stress R {pr['stress_R']:+.3f} t {pr['stress_t']:+.2f} -> {'PASS' if pr['pass_stress'] else 'FAIL'} | corr with #1 full {pr['corr_1_full']:+.2f}")
        for vn in ("S5", "S5+pick", "S4U", "S4U+pick"):
            r_ = pr["account"][vn]
            print(f"    {vn:9s} CAGR {r_['cagr']:+6.1%}  DD {r_['dd']:5.1%}  MAR {r_['mar']:.2f}  halves {r_['mar_h1']:+.2f}/{r_['mar_h2']:+.2f}  "
                  f"worst {r_['worst']:+.0%}  MC P(DD>50%) {r_['p_dd50']:.1%}")
        print(f"    adopt S5 {pr['account']['S5_adopt']}  S4U {pr['account']['S4U_adopt']}", flush=True)
    (HERE / "grid_diverse.json").write_text(json.dumps(res, indent=1, default=float))
    D.to_csv(HERE / "grid_diverse_candidates.csv", index=False)


if __name__ == "__main__":
    main()
