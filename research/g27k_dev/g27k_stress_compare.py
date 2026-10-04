#!/usr/bin/env python3
"""The execution stress of h1_stress.py applied to G27K #1 (H4) on the same six
markets and years, for a like-for-like comparison. Costs scale through each
trade's own spread and swap components; one bar late = entry at the next H1
open (one hour later, the same delay as the H1 test); also one H4 bar late.

Usage: python3 research/g27k_dev/g27k_stress_compare.py --root <snap>
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
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY", "ETHUSD")
LO, END = "2011-09-01", "2026-10-01"


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS["ETHUSD"] = dict(C.SPECS["BTCUSD"])
    K.START = W.ts("2009-09-01")
    ext = K.externals()
    rows = []
    for m in MKTS:
        h1 = MMS.load(m, G)
        Mk = K.prepare(m, h1, ext)
        X = G.features(G.frames(h1), m, "H4")
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        b = X["b"]
        for r in RP.sim_paths(X, m, idx, d[idx], "I1"):
            if not (W.ts(LO) <= r["t"] < W.ts(END)):
                continue
            q = X["k0"][r["e"]]
            stop = r["ep"] - r["risk"]
            ep_h1 = b["o"][q + 1] if q + 1 < X["k1"][r["e"]] else r["ep"]
            e4 = r["e"] + 1
            ep_h4 = X["o"][e4] if e4 < len(X["o"]) and X["t"][e4] < r["t_exit"] else np.nan
            rows.append(dict(mkt=m, t=r["t"], tx=r["t_exit"], R=r["R"], cost=r["R_spread"] + r["R_swap"], R_spread=r["R_spread"],
                             stop_exit=bool(r["px"] <= stop + 1e-9), ep=r["ep"], px=r["px"], stop=stop, ep_h1=ep_h1, ep_h4=ep_h4))
    T = pd.DataFrame(rows)

    def late(col):
        e = T[col]
        ok = e > T.stop
        R = (T.px - e) / (e - T.stop).where(ok) - T.cost
        return R.fillna(-1.0)          # already through the stop before the late entry: count a full loss
    lateH1, lateH4 = late("ep_h1"), late("ep_h4").where(T.ep_h4.notna(), T.R)
    cases = {
        "base": T.R,
        "(a) costs x2": T.R - T.cost,
        "(b) costs x3": T.R - 2 * T.cost,
        "(c) +0.05R": T.R - 0.05,
        "(d) +0.10R": T.R - 0.10,
        "(e) stop 0.10R worse": T.R - 0.10 * T.stop_exit,
        "(f) stop 0.25R worse": T.R - 0.25 * T.stop_exit,
        "(g) one H1 bar late": lateH1,
        "(g4) one H4 bar late": lateH4,
        "(i) without best 5%": T.R.sort_values().iloc[: int(len(T) * 0.95)],
        "(j) x2 + 0.05R + 1h late": lateH1 - T.cost - 0.05,
    }
    res = {nm: dict(n=len(R), mean=float(np.mean(R)), t=tstat(R)) for nm, R in cases.items()}
    print(f"  G27K #1 on {len(MKTS)} markets, {len(T)} trades, stop exits {T.stop_exit.mean():.0%}, cost per trade {T.cost.mean():.3f}R")
    for nm, r in res.items():
        print(f"    {nm:26s} n {r['n']:5d}  R {r['mean']:+.3f}  t {r['t']:+.2f}")
    # account level: G27K alone (five markets, brake 25%) with every trade at the (j) stress
    news = W.news_times(a.root)
    S5 = T[T.mkt != "ETHUSD"].assign(vp=0.0, sc=lambda x: x.t)
    acc = {}
    for nm, R in (("base", S5.R), ("(j)", (lateH1 - T.cost - 0.05)[S5.index])):
        st, eq, _ = SU.simulate(S5.assign(R=R)[["mkt", "t", "tx", "R", "vp", "sc"]], "brake", LO, END, news=news)
        mc = SU.monte_carlo(eq)
        acc[nm] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], p_dd50=mc["p_dd50"])
        print(f"  account S5 G27K alone {nm:5s} CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  MC P(DD>50%) {mc['p_dd50']:.1%}")
    (HERE / "g27k_stress_compare.json").write_text(json.dumps(dict(cases=res, account=acc), indent=1, default=float))


if __name__ == "__main__":
    main()
