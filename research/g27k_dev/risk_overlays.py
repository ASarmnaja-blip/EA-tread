#!/usr/bin/env python3
"""Risk overlays on G27K #1 (ledger g27k_risk_overlays; criterion fixed there).

Each overlay is compared with plain fixed risk scaled down to the same
full-period max balance drawdown: an overlay only adds value if it earns more
than simply trading smaller.

Usage: python3 research/g27k_dev/risk_overlays.py --root <snap>
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
HALF = {"BTCUSD": 0.5, "ETHUSD": 0.5}
RULES = {"A plain": dict(), "B brake 25% (now)": dict(brake=True), "C steps": dict(steps=True), "D brake + cap 3%": dict(brake=True, cap=0.03),
         "E brake + equity filter": dict(brake=True, eqf=True), "F brake + high-vol half": dict(brake=True, vol=True), "G steps + cap 3%": dict(steps=True, cap=0.03)}


def run(T, rule, scale=1.0, start=START, end=END, extra=0.0):
    T = T[(T.t >= W.ts(start)) & (T.t < W.ts(end))]
    bal, peak, dd, braked = 1.0, 1.0, 0.0, False
    heap, open_r, hist, yrs = [], {}, [], {}
    t_, tx_, R_, m_, vp_ = T.t.to_numpy(), T.tx.to_numpy(), T.R.to_numpy() - extra, T.mkt.to_numpy(), T.vp.to_numpy()
    for i in range(len(T)):
        while heap and heap[0][0] <= t_[i]:
            _, j, pnl = heapq.heappop(heap)
            bal += pnl
            open_r.pop(j, None)
            peak = max(peak, bal)
            now = 1 - bal / peak
            dd = max(dd, now)
            braked = now >= 0.25 or (braked and now > 0.125)
            hist.append(bal)
        now = 1 - bal / peak
        base = 0.01 * HALF.get(m_[i], 1.0)
        mult = 1.0
        if rule.get("brake") and braked:
            mult *= 0.5
        if rule.get("steps"):
            mult *= 1.0 if now < 0.10 else 0.75 if now < 0.20 else 0.5 if now < 0.30 else 0.25
        if rule.get("eqf") and len(hist) >= 30 and bal < np.mean(hist[-30:]):
            mult *= 0.5
        if rule.get("vol") and vp_[i] > 0.9:
            mult *= 0.5
        r = base * mult
        if rule.get("cap") and sum(open_r.values()) + r > rule["cap"] + 1e-12:
            continue
        open_r[i] = r
        heapq.heappush(heap, (tx_[i], i, r * scale * bal * R_[i]))
    while heap:
        bal += heapq.heappop(heap)[2]
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    yrs_n = (W.ts(end) - W.ts(start)) / (365.25 * 86400)
    cagr = bal ** (1 / yrs_n) - 1 if bal > 0 else -1.0
    return dict(cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.nan)


def same_dd_scale(T, dd, **kw):
    lo, hi = 0.05, 2.0
    for _ in range(40):
        k = (lo + hi) / 2
        if run(T, {}, k, **kw)["dd"] > dd:
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
                           R=[r["R"] for r in rows], vp=[r.get("vp", 0.0) for r in rows])).sort_values(["t", "mkt"], kind="mergesort").reset_index(drop=True)
    out = {}
    for acct, ms in (("Cent", RF.CENT), ("Standard", RF.STD)):
        T = TT[TT.mkt.isin(ms)]
        out[acct] = {}
        print(f"\n  {acct}")
        for nm, rule in RULES.items():
            full = run(T, rule)
            h1, h2 = run(T, rule, end=MID), run(T, rule, start=MID)
            st = run(T, rule, extra=0.10)
            k = same_dd_scale(T, full["dd"])
            p_full, p1, p2 = run(T, {}, k), run(T, {}, k, end=MID), run(T, {}, k, start=MID)
            ks = same_dd_scale(T, st["dd"], extra=0.10)
            p_st = run(T, {}, ks, extra=0.10)
            adds = bool(full["cagr"] > p_full["cagr"] and h1["cagr"] > p1["cagr"] and h2["cagr"] > p2["cagr"] and st["mar"] > p_st["mar"])
            out[acct][nm] = dict(full=full, h1=h1, h2=h2, stress=st, plain_scale=k, plain_full=p_full, plain_h1=p1, plain_h2=p2, plain_stress=p_st,
                                 adds_value=adds if nm != "A plain" else None)
            print(f"    {nm:24s} CAGR {full['cagr']:+6.1%} DD {full['dd']:5.1%} MAR {full['mar']:.2f} | 2011-18 {h1['cagr']:+.1%} 2019-26 {h2['cagr']:+.1%} | "
                  f"-0.10R MAR {st['mar']:.2f} || plain x{k:.2f} same DD: CAGR {p_full['cagr']:+.1%} ({p1['cagr']:+.1%}/{p2['cagr']:+.1%}) -0.10R MAR {p_st['mar']:.2f}"
                  + ("" if nm == "A plain" else f"  -> {'ADDS VALUE' if adds else 'no'}"), flush=True)
    (HERE / "risk_overlays.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
