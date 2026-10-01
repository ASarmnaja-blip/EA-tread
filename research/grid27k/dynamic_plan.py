"""Dynamic plan search (docs/plans/DYNAMIC_PLAN_PREREG.md): setup 1 as the core, 100 plans = regime signal (5) x action in a bad regime (5)
x volatility scaling (2) x drawdown brake (2). Choose on 2009-09..2017-12 by MAR (CAGR / equity DD, >= 100 trades), test on
2018-01..2026-09. Gold and silver from 2009, BTC from 2018; 1 % base risk; equity marked at every H4 close."""
from __future__ import annotations

import heapq
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
FIRST, SEL_END = CP.FIRST, C.ts("2018-01-01")
PLANS = list(itertools.product(("R1", "R2", "R3", "R4", "R5"), ("B0", "B1", "B2", "B3", "B4"), ("V0", "V1"), ("Q0", "Q1")))
WINDOWS = [("test 2018-01..2026-09", "2018-01-01", None), ("all 2009-09..2026-09", "2009-09-01", None),
           ("metals bear 2011-09..2015-12", "2011-09-01", "2016-01-01"), ("2013", "2013-01-01", "2014-01-01"), ("2018", "2018-01-01", "2019-01-01"),
           ("2022", "2022-01-01", "2023-01-01"), ("last five years 2021-10..2026-09", "2021-10-01", None)]


def align(X, A, sig, a_sec):
    ac = np.minimum(np.r_[A["t"][1:], K.BIG], A["t"] + a_sec); xc = np.minimum(np.r_[X["t"][1:], K.BIG], X["t"] + 14400)
    j = np.searchsorted(ac, xc, side="right") - 1
    return np.where(j >= 0, sig[np.maximum(j, 0)], 0)


def regimes(X, F):
    W, D = F["W1"], F["D1"]
    mid = lambda A, n: (pd.Series(A["h"]).rolling(n).max() + pd.Series(A["l"]).rolling(n).min()).to_numpy() / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        sig = {"R1": (W, np.sign(W["c"] - mid(W, 55)), 7 * 86400),
               "R2": (W, np.sign(W["c"] - pd.Series(W["c"]).rolling(40).mean().to_numpy()), 7 * 86400),
               "R3": (D, np.sign(D["c"] - pd.Series(D["c"]).rolling(200).mean().to_numpy()), 86400),
               "R4": (W, np.sign(W["c"] / pd.Series(W["c"]).shift(52).to_numpy() - 1), 7 * 86400),
               "R5": (W, np.sign(W["c"] - mid(W, 26)), 7 * 86400)}
    return {k: align(X, A, np.nan_to_num(s), sec) > 0 for k, (A, s, sec) in sig.items()}


def tag(trades, good, vm):
    for r in trades:
        sb = r["e"] - 1; r["good"] = {k: bool(v[sb]) for k, v in good.items()}; r["vm"] = float(vm[sb])
    return trades


def account(items, base, brake):
    order = sorted(range(len(items)), key=lambda i: (items[i][0]["t"], items[i][0]["mkt"]))
    bal = peak = RP.DEPOSIT; heap = []; live = {}; rows = []
    for i in order:
        tr, mult = items[i]
        while heap and heap[0][0] <= tr["t"]:
            _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; peak = max(peak, bal); rows.append(r)
        risk = base * mult * (0.5 if brake == "Q1" and bal < 0.8 * peak else 1.0)
        if risk <= 0:
            continue
        live[i] = dict(tr, unit_usd=risk * bal, pnl=risk * bal * tr["R"], bal_before=bal); heapq.heappush(heap, (tr["t_exit"], i))
    while heap:
        _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; rows.append(r)
    rows.sort(key=lambda r: (r["t_exit"], r["t"]))
    bal = RP.DEPOSIT
    for r in rows:
        bal += r["pnl"]; r["bal_after"] = bal
    return rows


def items_for(plan, L_all, L_good, S_bad):
    R, B, V, Q = plan
    vmul = (lambda r: r["vm"]) if V == "V1" else (lambda r: 1.0)
    if B == "B0":
        it = [(r, vmul(r)) for r in L_good[R]]
    elif B in ("B1", "B2"):
        low = 0.5 if B == "B1" else 0.25
        it = [(r, (1.0 if r["good"][R] else low) * vmul(r)) for r in L_all]
    else:
        it = [(r, vmul(r)) for r in L_good[R]] + [(r, (1.0 if B == "B3" else 0.5) * vmul(r)) for r in S_bad[R]]
    return it, Q


def evaluate(items, brake, w0, w1, Xs, base=0.01):
    sub = [(dict(r), m) for r, m in items if r["t"] >= w0 and (w1 is None or r["t"] < w1) and m > 0]
    if len(sub) < 2:
        return None
    trades = [r for r, _ in sub]; last = max(r["t_exit"] for r in trades)
    T = np.unique(np.concatenate([X["t"] + 14400 for X in Xs.values()] + [np.array([r["t_exit"] for r in trades])])); T = T[(T >= w0) & (T <= last)]
    RP.prep_marks(trades, T)
    rows = account(sub, base, brake)
    M = RP.metrics(rows, T, base, start=w0)
    eq = np.array(M["curve"]["eq"])
    return dict(n=M["trades"], ret=M["net"] / RP.DEPOSIT, cagr=M["cagr"], eq_dd=M["equity_dd"]["relative_pct"], bal_dd=M["balance_dd"]["relative_pct"],
                mar=M["cagr"] / M["equity_dd"]["relative_pct"] if M["equity_dd"]["relative_pct"] > 0 else np.nan, low=float(eq.min() / RP.DEPOSIT),
                pf=M["pf"], under=M["longest_underwater_days"])


def main():
    K.START = FIRST
    ext = K.externals(); Xs, L_all, L_good, S_bad, now = {}, [], {r: [] for r in ("R1", "R2", "R3", "R4", "R5")}, {r: [] for r in ("R1", "R2", "R3", "R4", "R5")}, {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); M = K.prepare(m, h1, ext); F = G.frames(h1); X = G.features(F, m, "H4"); X["sec"] = 14400; CP.extras(m, h1, X, M); Xs[m] = X
        good = regimes(X, F)
        with np.errstate(invalid="ignore", divide="ignore"):
            vm = np.nan_to_num(np.clip(pd.Series(X["a20"]).rolling(1500, min_periods=300).median().shift(1).to_numpy() / X["a20"], 0, 1), nan=1.0)
        dL = K.directions(M, "C8", "D3", "E1", "J1")
        dS = np.where(M["Ds"]["D3"] & M["Cs"]["C8"] & M["ok"], -1, 0)
        s = np.flatnonzero(dL); L_all += tag(CP.sim(X, m, s, dL[s], 2.0, "ch20"), good, vm)
        for R, g in good.items():
            d = np.where(g, dL, 0); s = np.flatnonzero(d); L_good[R] += tag(CP.sim(X, m, s, d[s], 2.0, "ch20"), good, vm)
            d = np.where(~g, dS, 0); s = np.flatnonzero(d); S_bad[R] += tag(CP.sim(X, m, s, d[s], 2.0, "ch20"), good, vm)
        now[m] = {R: ("good" if g[-1] else "bad") for R, g in good.items()}
    sel = []
    for plan in PLANS:
        it, Q = items_for(plan, L_all, L_good, S_bad)
        r = evaluate(it, Q, FIRST, SEL_END, Xs)
        if r:
            sel.append(dict(plan="/".join(plan), **r))
    SD = pd.DataFrame(sel); ok = SD[SD.n >= 100].sort_values("mar", ascending=False)
    base = evaluate([(r, 1.0) for r in L_all], "Q0", FIRST, SEL_END, Xs)
    print(f"selection 2009-09..2017-12: P alone MAR {base['mar']:.2f} (CAGR {base['cagr']:.1%}, DD {base['eq_dd']:.1%}); plans with >=100 trades {len(ok)} of {len(SD)}")
    print(ok.head(10)[["plan", "n", "cagr", "eq_dd", "mar", "pf"]].round(3).to_string(index=False))
    for dim, pos in (("R", 0), ("B", 1), ("V", 2), ("Q", 3)):
        print(f"  median MAR by {dim}:", ok.assign(k=ok.plan.str.split("/").str[pos]).groupby("k").mar.median().round(2).to_dict())
    chosen = ok.plan.iloc[0]; show = ["P", "R1/B0/V0/Q0"] + ok.plan.head(5).tolist()
    out = dict(selection=sel, chosen=chosen, now=now, windows={})
    for p in dict.fromkeys(show):
        it, Q = ([(r, 1.0) for r in L_all], "Q0") if p == "P" else items_for(tuple(p.split("/")), L_all, L_good, S_bad)
        for wname, a, b in WINDOWS:
            r = evaluate(it, Q, C.ts(a), C.ts(b) if b else None, Xs)
            if r is None:
                continue
            out["windows"][f"{p} | {wname}"] = r
            tagp = " (chosen)" if p == chosen else (" (K1)" if p == "R1/B0/V0/Q0" else "")
            print(f"{p + tagp:24s} | {wname:34s} | trades {r['n']:4d} total {r['ret']:+7.0%} CAGR {r['cagr']:+6.1%} equity DD {r['eq_dd']:5.1%} MAR {r['mar']:5.2f}"
                  f" low {r['low']:4.0%} PF {r['pf']:.2f}")
    print("regime now (last bar):", json.dumps(now))
    (K.OUT / "dynamic_plan.json").write_text(json.dumps(out, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
