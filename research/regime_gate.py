#!/usr/bin/env python3
"""Can a simple causal sizing/gating rule keep the profit and cut the drawdown,
on a window it was not chosen on? (ledger id regime_gate_crossval)

Trade streams are the forward-adopted patterns of walk-forward round 2,
traded without decisions, in both windows. Each of 18 rules re-sizes that
stream; the best rule on one window is applied unchanged to the other.

Usage: python3 regime_gate.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import itertools
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import h4d1_pattern_search as P
import walkforward_controller as W
import walkforward_round2 as W2

BASE = 0.005
CAPS = (0.03, 0.06, None)
EQF = (0, 30, 60)
TREND = (False, True)


def er_gate_series(m):
    X = P.FRAMES[(m, "D1")]
    c = pd.Series(np.asarray(X["c"], float))
    net = (c - c.shift(60)).abs()
    path = c.diff().abs().rolling(60).sum()
    er = net / path
    ok = er >= er.rolling(250, min_periods=120).median()
    close_t = np.asarray(X["t"], np.int64) + 86400
    return close_t, ok.to_numpy()


def simulate(rows, cap, n_eq, trend, gates):
    ex_sorted = sorted(rows, key=lambda r: r["t_exit"])
    ex_t = np.array([r["t_exit"] for r in ex_sorted], np.int64)
    cum = np.r_[0.0, np.cumsum([r["R"] for r in ex_sorted])]
    bal = W.DEPOSIT
    heap, open_risk, out = [], 0.0, []
    for r in sorted(rows, key=lambda r: (r["t"], r["mkt"])):
        while heap and heap[0][0] <= r["t"]:
            _, _, o = heapq.heappop(heap)
            bal += o["pnl"]
            open_risk -= o["risk_frac"]
        risk = BASE
        if trend:
            ct, ok = gates[r["mkt"]]
            j = np.searchsorted(ct, r["t"], side="right") - 1
            if j < 0 or not ok[j]:
                continue
        if n_eq:
            k = int(np.searchsorted(ex_t, r["t"], side="right"))
            if k >= n_eq and cum[k] - cum[k - n_eq] < 0:
                risk *= 0.25
        if cap is not None:
            risk = min(risk, cap - open_risk)
            if risk < 0.0005:
                continue
        o = dict(r, risk_frac=risk, bal_before=bal, unit_usd=risk * bal, pnl=risk * bal * r["R"])
        open_risk += risk
        heapq.heappush(heap, (o["t_exit"], id(o), o))
        out.append(o)
    out.sort(key=lambda r: (r["t_exit"], r["t"]))
    b = W.DEPOSIT
    for o in out:
        b += o["pnl"]
        o["bal_after"] = b
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in W.TFS}
    allref = pickle.loads((HERE / ".cache_wf" / "refits.pkl").read_bytes())
    news = W.news_times(a.root)
    gates = {m: er_gate_series(m) for m in K.MKTS}
    rules = list(itertools.product(CAPS, EQF, TREND))
    res = {}
    for wname, (s, e) in W2.WINDOWS.items():
        start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
        dates = [W.ts(d) for d in pd.date_range(start, end - pd.Timedelta(days=1), freq="QS")]
        refits = {D: allref[D] for D in dates}
        G.START = int(start.timestamp())
        W.START, W.END = start, end
        _, pats, _, _ = W2.run2(B, refits, news, int(end.timestamp()))
        rows, _, _, _ = W.run(B, refits, news, decide=False, fixed=list(pats.values()))
        print(f"  [{wname}] {len(rows)} trades in the stream  {time.time() - t0:.0f}s", flush=True)
        res[wname] = []
        for cap, n_eq, trend in rules:
            sim = simulate(rows, cap, n_eq, trend, gates)
            M = W.slim(W.metrics_for(W.to_report_rows(sim, B), RP, G))
            rec = dict(cap=cap, eq=n_eq, trend=trend, trades=M["trades"], net=M["net"], cagr=M["cagr"],
                       eq_dd=M["equity_dd"], mar=M["mar"], pf=M["pf"], yearly=M["yearly"], curve=M["curve"])
            res[wname].append(rec)
            print(f"  [{wname}] cap {str(cap):5s} eq {n_eq:2d} trend {str(trend):5s} trades {rec['trades']:5d} "
                  f"CAGR {rec['cagr']:+6.1%} eqDD {rec['eq_dd']:5.1%} MAR {rec['mar']:5.2f}", flush=True)
    base = lambda w: next(r for r in res[w] if r["cap"] is None and r["eq"] == 0 and not r["trend"])
    cross = []
    for fit, test in (("main", "independent"), ("independent", "main")):
        best = max(res[fit], key=lambda r: r["mar"])
        same = next(r for r in res[test] if (r["cap"], r["eq"], r["trend"]) == (best["cap"], best["eq"], best["trend"]))
        b = base(test)
        ok = same["mar"] > b["mar"] and same["eq_dd"] <= 0.6 * b["eq_dd"]
        cross.append(dict(fit=fit, test=test, rule=dict(cap=best["cap"], eq=best["eq"], trend=best["trend"]),
                          fit_mar=best["mar"], test_mar=same["mar"], test_dd=same["eq_dd"], test_cagr=same["cagr"],
                          base_mar=b["mar"], base_dd=b["eq_dd"], base_cagr=b["cagr"], passed=bool(ok)))
        print(f"  fit {fit} -> rule {cross[-1]['rule']} | test {test}: MAR {same['mar']:.2f} DD {same['eq_dd']:.1%} "
              f"CAGR {same['cagr']:+.1%} vs base MAR {b['mar']:.2f} DD {b['eq_dd']:.1%} CAGR {b['cagr']:+.1%} -> "
              f"{'PASS' if ok else 'FAIL'}", flush=True)
    G.START = W.ts("2021-10-01")
    (HERE / "regime_gate.json").write_text(json.dumps(dict(rules=res, cross=cross,
                                                             passed=all(c["passed"] for c in cross)), default=str))
    print(f"  saved regime_gate.json  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
