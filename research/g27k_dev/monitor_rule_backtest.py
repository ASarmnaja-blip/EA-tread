#!/usr/bin/env python3
"""Backtest of the weekly monitor's risk rule (ledger g27k_monitor_rule).

Base 0.75% (BTC/ETH 0.375%) with the EA's 25% brake. Every Monday the
account drawdown sets the next week's state: >= 25% DEFENCE x0.5, >= 20%
REDUCE x0.667, NORMAL again once DD < 10%. Compared with the same account
without the rule, and with plain fixed risk (brake on) scaled to the same max
drawdown.

Usage: python3 research/g27k_dev/monitor_rule_backtest.py --root <snap>
"""
import argparse
import heapq
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
import walkforward_controller as W

START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
WEEK = 7 * 86400
MONDAY0 = W.ts("2011-08-29")


def run(T, scale=1.0, rule=True, start=START, end=END, extra=0.0):
    T = T[(T.t >= W.ts(start)) & (T.t < W.ts(end))]
    bal, peak, dd, braked, state, wk = 1.0, 1.0, 0.0, False, 1.0, None
    heap, days_reduced = [], 0
    t_, tx_, R_, m_ = T.t.to_numpy(), T.tx.to_numpy(), T.R.to_numpy() - extra, T.mkt.to_numpy()
    reduced_trades = 0
    for i in range(len(T)):
        while heap and heap[0][0] <= t_[i]:
            _, pnl = heapq.heappop(heap)
            bal += pnl
            peak = max(peak, bal)
            now = 1 - bal / peak
            dd = max(dd, now)
            braked = now >= 0.25 or (braked and now > 0.125)
        w = (t_[i] - MONDAY0) // WEEK
        if rule and w != wk:                    # weekly decision on the drawdown known at that Monday
            wk = w
            now = 1 - bal / peak
            state = 0.5 if now >= 0.25 else (2 / 3) if now >= 0.20 else (1.0 if now < 0.10 else state)
        base = 0.0075 * (0.5 if m_[i] in ("BTCUSD", "ETHUSD") else 1.0)
        mult = (0.5 if braked else 1.0)
        if rule:
            mult = min(mult, state)             # the rule's level already includes the brake's halving
            reduced_trades += state < 1.0
        heapq.heappush(heap, (tx_[i], base * mult * scale * bal * R_[i]))
    while heap:
        bal += heapq.heappop(heap)[1]
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    yrs = (W.ts(end) - W.ts(start)) / (365.25 * 86400)
    cagr = bal ** (1 / yrs) - 1 if bal > 0 else -1.0
    return dict(cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.nan, reduced=reduced_trades / max(1, len(T)))


def same_dd(T, dd, **kw):
    lo, hi = 0.05, 2.0
    for _ in range(40):
        k = (lo + hi) / 2
        if run(T, k, rule=False, **kw)["dd"] > dd:
            hi = k
        else:
            lo = k
    return lo


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
    RSD.START = START
    rows = [r for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    TT = pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[int(r["t"]) for r in rows], tx=[int(r["t_exit"]) for r in rows],
                           R=[r["R"] for r in rows])).sort_values(["t", "mkt"], kind="mergesort").reset_index(drop=True)
    out = {}
    for acct, ms in (("Cent", RF.CENT), ("Standard", RF.STD)):
        T = TT[TT.mkt.isin(ms)]
        base, rule = run(T, rule=False), run(T)
        k = same_dd(T, rule["dd"])
        res = dict(base=base, rule=rule, plain_scale=k, plain=run(T, k, rule=False))
        for nm, kw in (("h1", dict(end=MID)), ("h2", dict(start=MID))):
            res["base_" + nm], res["rule_" + nm], res["plain_" + nm] = run(T, rule=False, **kw), run(T, **kw), run(T, k, rule=False, **kw)
        res["base_st"], res["rule_st"] = run(T, rule=False, extra=0.10), run(T, extra=0.10)
        ks = same_dd(T, res["rule_st"]["dd"], extra=0.10)
        res["plain_st"] = run(T, ks, rule=False, extra=0.10)
        res["pass"] = bool(res["base"]["dd"] - res["rule"]["dd"] >= 0.02 and all(res["rule" + s]["cagr"] >= res["plain" + s]["cagr"] for s in ("", "_h1", "_h2"))
                           and res["rule_st"]["cagr"] >= res["plain_st"]["cagr"])
        out[acct] = res
        f = lambda r: f"CAGR {r['cagr']:+6.1%} DD {r['dd']:5.1%} MAR {r['mar']:.2f}"
        print(f"\n  {acct}")
        print(f"    0.75% + brake          {f(res['base'])} | 2011-18 {res['base_h1']['cagr']:+.1%} 2019-26 {res['base_h2']['cagr']:+.1%} | -0.10R {f(res['base_st'])}")
        print(f"    + monitor rule         {f(res['rule'])} | 2011-18 {res['rule_h1']['cagr']:+.1%} 2019-26 {res['rule_h2']['cagr']:+.1%} | -0.10R {f(res['rule_st'])} | "
              f"trades at reduced risk {res['rule']['reduced']:.0%}")
        print(f"    plain x{k:.2f} same DD     {f(res['plain'])} | 2011-18 {res['plain_h1']['cagr']:+.1%} 2019-26 {res['plain_h2']['cagr']:+.1%} | -0.10R same DD {f(res['plain_st'])}")
        print(f"    -> {'PASS' if res['pass'] else 'FAIL'}")
    (HERE / "monitor_rule_backtest.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
