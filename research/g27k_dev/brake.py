#!/usr/bin/env python3
"""System B at 1% risk with a drawdown brake (ledger id g27k_b_1pct_brake).

Risk per trade is 1% x mult. At each entry, after closed trades settle,
dd = 1 - balance / peak balance; mult drops to 0.5 when dd >= X and returns
to 1 when dd <= X/2. Compared with a constant risk equal to the brake's
trade-weighted average risk (matched constant), constant 1% and 0.5%, over
the full period and both halves, with a paired block-bootstrap Monte Carlo
and a monthly top-up (DCA) run from 2009 and 2016.

Usage: python3 research/g27k_dev/brake.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import dca as DC
import h4d1_pattern_search as P
import phase1 as PH
import walkforward_controller as W

XS = (0.25, 0.20, 0.30)


def account(T, base, X, start, end):
    """Balance compounding with overlapping trades and an optional brake (X None = constant)."""
    T = T.sort_values("t")
    bal, peak, dd, heap, pts = 1.0, 1.0, 0.0, [], []
    mult, risks, braked = 1.0, [], 0
    for r in T.itertuples():
        while heap and heap[0][0] <= r.t:
            tx, p = heapq.heappop(heap)
            bal += p
            peak = max(peak, bal)
            dd = max(dd, 1 - bal / peak)
            pts.append((tx, bal))
        if X is not None:
            now = 1 - bal / peak
            if mult == 1.0 and now >= X:
                mult = 0.5
            elif mult < 1.0 and now <= X / 2:
                mult = 1.0
        risks.append(base * mult)
        braked += mult < 1.0
        heapq.heappush(heap, (r.tx, base * mult * bal * r.R))
    while heap:
        tx, p = heapq.heappop(heap)
        bal += p
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        pts.append((tx, bal))
    yrs = (W.ts(end) - W.ts(start)) / (365.25 * 86400)
    cagr = bal ** (1 / yrs) - 1 if bal > 0 else -1.0
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([x for x, _ in pts], unit="s"))
    return dict(n=len(T), cagr=float(cagr), dd=float(dd), mar=float(cagr / dd) if dd > 0 else np.nan,
                final=float(bal), avg_risk=float(np.mean(risks)) if risks else base,
                share_braked=float(braked / max(len(T), 1))), eq


def mc(mret, rules, runs=10000, years=10, block=6, seed=7):
    """Paired block bootstrap of monthly returns at 1%; each rule is (scale, X) applied on the path."""
    rng = np.random.default_rng(seed)
    nb = math.ceil(years * 12 / block)
    paths = [np.concatenate([mret[s:s + block] for s in rng.integers(0, len(mret) - block, nb)])[: years * 12]
             for _ in range(runs)]
    out = {}
    for name, (scale, X) in rules.items():
        dds, fin = np.empty(runs), np.empty(runs)
        for i, p in enumerate(paths):
            v, pk, mdd, mult = 1.0, 1.0, 0.0, 1.0
            for x in p:
                if X is not None:
                    now = 1 - v / pk
                    mult = 0.5 if (mult == 1.0 and now >= X) else 1.0 if (mult < 1.0 and now <= X / 2) else mult
                v *= 1 + x * scale * mult
                pk = max(pk, v)
                mdd = max(mdd, 1 - v / pk)
            dds[i], fin[i] = mdd, v
        out[name] = dict(dd_median=float(np.median(dds)), dd_p95=float(np.quantile(dds, 0.95)),
                         p_dd30=float((dds > 0.30).mean()), p_dd50=float((dds > 0.50).mean()),
                         cagr_median=float(np.median(fin) ** (1 / years) - 1))
    return out


def dca_brake(T, X, start, end):
    """dca.run_dca with the brake applied on the unit-value drawdown (deposits do not reset it)."""
    s0, s1 = W.ts(start), W.ts(end)
    T = T[(T.t >= s0) & (T.t < s1)].sort_values("t")
    months = [W.ts(d) for d in pd.date_range(start, end, freq="MS", inclusive="left")]
    ev = sorted([(m, 0, None) for m in months] + [(r.t, 2, r) for r in T.itertuples()], key=lambda e: (e[0], e[1]))
    bal, nav, pk_nav, dd_nav, mult = 0.0, 1.0, 1.0, 0.0, 1.0
    heap, flows, ftimes = [], [], []
    for i, (t, _, r) in enumerate(ev):
        while heap and heap[0][0] <= t:
            _, _, pnl = heapq.heappop(heap)
            nav *= (bal + pnl) / bal if bal > 0 else 1
            bal += pnl
            pk_nav = max(pk_nav, nav)
            dd_nav = max(dd_nav, 1 - nav / pk_nav)
        if r is None:
            amt = DC.INITIAL + DC.MONTHLY if not flows else DC.MONTHLY
            bal += amt
            flows.append(amt)
            ftimes.append(t)
            continue
        if X is not None:
            now = 1 - nav / pk_nav
            mult = 0.5 if (mult == 1.0 and now >= X) else 1.0 if (mult < 1.0 and now <= X / 2) else mult
        heapq.heappush(heap, (r.tx, i, 0.01 * mult * bal * r.R))
    while heap:
        _, _, pnl = heapq.heappop(heap)
        nav *= (bal + pnl) / bal
        bal += pnl
        pk_nav = max(pk_nav, nav)
        dd_nav = max(dd_nav, 1 - nav / pk_nav)
    return dict(deposited=float(sum(flows)), final=float(bal), irr=float(DC.irr(flows, ftimes, bal, s1)),
                dd_unit=float(dd_nav))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    ext = K.externals()
    H1 = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    Ds = {m: PH.prep_market(m, H1[m], ext) for m in K.MKTS}
    T = PH.system_trades("B", Ds, *PH.BASE)
    halves = (("full", PH.START, PH.END), ("2009-16", PH.START, PH.HALF), ("2017-26", PH.HALF, PH.END))

    def run(base, X):
        out = {}
        for name, lo, hi in halves:
            k = (T.t >= W.ts(lo)) & (T.t < W.ts(hi))
            out[name], eq = account(T[k], base, X, lo, hi)
            if name == "full":
                out["eq"] = eq
        return out

    res = {"const 1%": run(0.01, None), "const 0.5%": run(0.005, None)}
    for X in XS:
        b = run(0.01, X)
        res[f"brake {X:.0%}"] = b
        r = round(b["full"]["avg_risk"], 5)
        res[f"matched {X:.0%} ({r:.3%})"] = run(r, None)
    eq1 = res["const 1%"]["eq"]
    mret = eq1.resample("ME").last().ffill().pct_change().dropna().to_numpy()
    rules = {"const 1%": (1.0, None), "const 0.5%": (0.5, None)}
    for X in XS:
        rules[f"brake {X:.0%}"] = (1.0, X)
        rules[f"matched {X:.0%}"] = (res[f"brake {X:.0%}"]["full"]["avg_risk"] / 0.01, None)
    M = mc(mret, rules)
    out = {}
    print(f"{'':24s} {'full CAGR':>9s} {'DD':>5s} {'MAR':>5s} | {'09-16 MAR':>9s} | {'17-26 MAR':>9s} | "
          f"{'avg risk':>8s} {'braked':>6s}")
    for name, r in res.items():
        f = r["full"]
        print(f"{name:24s} {f['cagr']:+9.1%} {f['dd']:5.0%} {f['mar']:5.2f} | {r['2009-16']['mar']:9.2f} | "
              f"{r['2017-26']['mar']:9.2f} | {f['avg_risk']:8.3%} {f['share_braked']:6.0%}")
        out[name] = {h: r[h] for h, _, _ in halves}
    print("Monte Carlo (10 years, 10,000 paths)")
    for name, m in M.items():
        print(f"  {name:14s} DD median {m['dd_median']:.0%} p95 {m['dd_p95']:.0%}  P(DD>30%) {m['p_dd30']:.1%}  "
              f"P(DD>50%) {m['p_dd50']:.1%}  median CAGR {m['cagr_median']:+.1%}")
    print("Monthly top-up ($100 + $100/month)")
    D = {}
    for start in ("2009-10-01", "2016-10-01"):
        Ts = PH.system_trades("B", Ds, *PH.BASE, start=start)
        for name, X in (("const 1%", None), ("brake 25%", 0.25)):
            d = dca_brake(Ts, X, start, DC.END)
            D[f"{start} {name}"] = d
            print(f"  {start} {name:10s} in ${d['deposited']:,.0f} final ${d['final']:,.0f} IRR {d['irr']:+.1%} "
                  f"DD(unit) {d['dd_unit']:.0%}")
    (HERE / "brake.json").write_text(json.dumps(dict(accounts=out, monte_carlo=M, dca=D), indent=1))


if __name__ == "__main__":
    main()
