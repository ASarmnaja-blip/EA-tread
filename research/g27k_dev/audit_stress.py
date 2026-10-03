#!/usr/bin/env python3
"""Audit part 2: how the final system (G27K #1 on gold, silver, BTC, JP225,
1% with the 25% brake) holds up when the assumptions are made worse.

  costs x2 and x3; stop exits filled 0.1R and 0.25R worse; JP225 charged a
  long swap like US500's; entry one H1 bar late; no news filter; the 80-rule
  neighbourhood (N 8-20, M 15-30, k 1.5-3); without the best trades and the
  best year; peak leverage and open risk; yearly contribution per market.

Usage: python3 research/g27k_dev/audit_stress.py --root <data-snapshot checkout>
"""
import argparse
import itertools
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
import phase1 as PH
import suite as SU
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225")
START, END = "2011-09-01", "2026-10-01"


def run(T, news, v="brake", start=START):
    st, eq, risk = SU.simulate(T, v, start, END, news=news)
    return st, eq, risk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    H1 = {m: MMS.load(m, G) for m in MKTS}
    ext = K.externals()
    news = W.news_times(a.root)
    K.START = W.ts("2009-09-01")
    rows, Xs = [], {}
    for m in MKTS:
        Mk = K.prepare(m, H1[m], ext)
        X = G.features(G.frames(H1[m]), m, "H4")
        Xs[m] = (X, Mk)
        vp = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        for r in RP.sim_paths(X, m, idx, d[idx], "I1"):
            b = X["b"]
            q = X["k0"][r["e"]]
            ep2 = b["o"][q + 1] if q + 1 < X["k1"][r["e"]] else r["ep"]
            nts = C.nights(np.array([r["units"][0][2]], np.int64), np.array([r["t_exit"]], np.int64), C.SPECS[m]["rollover3"])[0]
            rows.append(dict(mkt=m, t=r["t"], tx=r["t_exit"], R=r["R"], R_spread=r["R_spread"], ep=r["ep"], px=r["px"], risk=r["risk"],
                             stop_exit=bool(r["px"] <= r["ep"] - r["risk"] + 1e-9), ep2=ep2, nights=nts,
                             vp=float(vp[max(r["e"] - 1, 0)]), sc=int(r["t"])))
    T = pd.DataFrame(rows)
    res = {}

    def rec(name, TT, start=START):
        st, _, _ = run(TT, news, "brake", start)
        res[name] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], n=st["n"])
        print(f"  {name:38s} CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  n {st['n']}", flush=True)

    rec("base (brake 25%)", T)
    rec("costs x2", T.assign(R=T.R - T.R_spread))
    rec("costs x3", T.assign(R=T.R - 2 * T.R_spread))
    rec("stop exits 0.10R worse", T.assign(R=T.R - 0.10 * T.stop_exit))
    rec("stop exits 0.25R worse", T.assign(R=T.R - 0.25 * T.stop_exit))
    jp_swap = C.SPECS["US500"]["swap_long_bp"] / 1e4
    rec("JP225 long swap like US500", T.assign(R=np.where(T.mkt == "JP225", T.R - T.ep * jp_swap * T.nights / T.risk, T.R)))
    stop = T.ep - T.risk
    late = (T.px - T.ep2) / (T.ep2 - stop).where(T.ep2 > stop, np.nan) - T.R_spread
    rec("entry one H1 bar late", T.assign(R=late.fillna(-1.0)))
    rec("all of the above together", T.assign(R=late.fillna(-1.0) - 2 * T.R_spread - 0.25 * T.stop_exit
                                              - np.where(T.mkt == "JP225", T.ep * jp_swap * T.nights / T.risk, 0)))
    # no news filter (C1 instead of C8)
    nn = []
    for m in MKTS:
        X, Mk = Xs[m]
        d = K.directions(Mk, "C1", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        vp = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        nn += [dict(mkt=m, t=r["t"], tx=r["t_exit"], R=r["R"], vp=float(vp[max(r["e"] - 1, 0)]), sc=int(r["t"]))
               for r in RP.sim_paths(X, m, idx, d[idx], "I1")]
    rec("no news filter", pd.DataFrame(nn))
    # without the best trades / best year
    best = T.sort_values("R", ascending=False)
    rec("without best 1% of trades", T.drop(best.index[: max(1, len(T) // 100)]))
    rec("without best 5% of trades", T.drop(best.index[: max(1, len(T) // 20)]))
    yr = pd.to_datetime(T.t, unit="s").dt.year
    by = T.groupby(yr).R.sum()
    res["R_by_year"] = by.round(1).to_dict()
    rec(f"without best year ({by.idxmax()})", T[yr != by.idxmax()])
    rec("from 2015 (fourth market chosen blind)", T, "2015-01-01")
    # neighbourhood with the phase-1 engine
    Ds = {m: PH.prep_market(m, H1[m], ext) for m in MKTS}
    nb = []
    for N, M, k in itertools.product(PH.NS, PH.MS, PH.KS):
        TT = pd.concat([PH.trades(Ds[m], N, M, k) for m in MKTS], ignore_index=True)
        TT["vp"], TT["sc"] = 0.0, TT.t
        st, _, _ = run(TT, news)
        nb.append(dict(N=N, M=M, k=k, cagr=st["cagr"], dd=st["dd"], mar=st["mar"]))
    nb = pd.DataFrame(nb)
    base_mar = nb[(nb.N == 10) & (nb.M == 20) & (nb.k == 2.0)].mar.iloc[0]
    res["neighbourhood"] = dict(n=len(nb), positive=int((nb.cagr > 0).sum()), mar_median=float(nb.mar.median()),
                                mar_min=float(nb.mar.min()), mar_max=float(nb.mar.max()), base_mar=float(base_mar),
                                base_rank=int((nb.mar > base_mar).sum()) + 1, dd_max=float(nb.dd.max()),
                                best=nb.sort_values("mar", ascending=False).head(3).round(3).to_dict("records"))
    print("  neighbourhood", json.dumps(res["neighbourhood"], default=float), flush=True)
    # leverage and open risk through time (normal sizing, balance at entry)
    _, _, risk = run(T, news, "brake")
    T2 = T.loc[risk.index].assign(rf=risk.values)
    T2["lev"] = T2.rf / (T2.risk / T2.ep)
    ev = sorted([(t, 1, i) for i, t in zip(T2.index, T2.t)] + [(tx, 0, i) for i, tx in zip(T2.index, T2.tx)])
    lev = rk = mlev = mrk = 0.0
    maxpos = pos = 0
    for t, kind, i in ev:
        sgn = 1 if kind == 1 else -1
        lev += sgn * T2.lev[i]
        rk += sgn * T2.rf[i]
        pos += sgn
        mlev, mrk, maxpos = max(mlev, lev), max(mrk, rk), max(maxpos, pos)
    res["peak_notional_x_equity"] = float(mlev)
    res["peak_open_risk"] = float(mrk)
    res["max_open_positions"] = int(maxpos)
    res["median_stop_pct"] = {m: float((T[T.mkt == m].risk / T[T.mkt == m].ep).median()) for m in MKTS}
    res["R_by_market"] = T.groupby("mkt").R.agg(["count", "sum", "mean"]).round(3).to_dict("index")
    res["win_rate"] = float((T.R > 0).mean())
    res["longest_losing_streak"] = int(max((len(list(g)) for k, g in itertools.groupby(T.sort_values("t").R > 0) if not k), default=0))
    print("  leverage/risk", res["peak_notional_x_equity"], res["peak_open_risk"], res["max_open_positions"], res["median_stop_pct"])
    print("  by market", res["R_by_market"], "win", round(res["win_rate"], 3), "losing streak", res["longest_losing_streak"])
    print("  R by year", res["R_by_year"])
    (HERE / "audit_stress.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
