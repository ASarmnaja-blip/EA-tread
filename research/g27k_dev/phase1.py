#!/usr/bin/env python3
"""G27K development, phase 0 + 1 (ledger id g27k_two_systems_phase1).

Two systems with the same G27K #1 rules: A = gold only, B = gold + silver +
BTC. Reproduces the baseline, then tests robustness without changing the
rules: 2009-2026 history, an 80-rule neighbourhood, doubled costs plus stop
slippage, 100 drift placebos and a block-bootstrap Monte Carlo.

Usage: python3 research/g27k_dev/phase1.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import itertools
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd
from numba import njit

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import walkforward_controller as W

SYSTEMS = {"A": ["XAUUSD"], "B": ["XAUUSD", "XAGUSD", "BTCUSD"]}
START, END = "2009-09-01", "2026-10-01"
HALF = "2017-01-01"
NS, MS, KS = (8, 10, 12, 15, 20), (15, 20, 25, 30), (1.5, 2.0, 2.5, 3.0)
BASE = (10, 20, 2.0)
N_PLACEBO = 100
_X = {}


@njit(cache=True)
def sim(o, c, a20, a14, hiN, loM, okbar, bo, bh, bl, bt, k0, k1, t, kstop, slip):
    n = len(c)
    E = np.zeros(n, np.int64)
    J = np.zeros(n, np.int64)
    EP = np.zeros(n)
    PX = np.zeros(n)
    TX = np.zeros(n, np.int64)
    RK = np.zeros(n)
    cnt = 0
    busy = -1
    for s in range(n - 1):
        if s <= busy or not okbar[s] or not (c[s] > hiN[s]):
            continue
        if not (np.isfinite(a20[s]) and np.isfinite(a14[s])):
            continue
        e = s + 1
        ep = o[e]
        risk = kstop * a20[s]
        stop = ep - risk
        j = e
        px = np.nan
        tx = 0
        done = False
        while j < n:
            for q in range(k0[j], k1[j]):
                if bl[q] <= stop:
                    px = (stop if bo[q] > stop else bo[q]) - slip * a20[s]
                    tx = bt[q]
                    done = True
                    break
            if done:
                break
            if c[j] < loM[j] and j + 1 < n:
                j += 1
                px = o[j]
                tx = t[j]
                done = True
                break
            j += 1
        if not done:
            j = n - 1
            px = c[j]
            tx = t[j]
        E[cnt] = e
        J[cnt] = j
        EP[cnt] = ep
        PX[cnt] = px
        TX[cnt] = tx
        RK[cnt] = risk
        cnt += 1
        busy = j
    return E[:cnt], J[:cnt], EP[:cnt], PX[:cnt], TX[:cnt], RK[:cnt]


def prep_market(m, h1, ext):
    G, K = P._M["G"], P._M["K"]
    F = G.frames(h1)
    X = F["H4"]
    t = X["t"].astype(np.int64)
    tc = t + 14400
    j = np.searchsorted(ext["ev"], tc, side="left")
    nxt = np.where(j < len(ext["ev"]), ext["ev"][np.minimum(j, len(ext["ev"]) - 1)], np.iinfo(np.int64).max)
    news = (nxt <= tc + 8 * 3600) & (tc >= ext["ev0"])
    S = pd.Series
    hi = {N: S(X["h"]).rolling(N).max().shift(1).to_numpy() for N in NS}
    lo = {M: S(X["l"]).rolling(M).min().shift(1).to_numpy() for M in MS}
    ok = (t >= W.ts(START)) & (t < W.ts(END)) & ~news
    b = X["b"]
    return dict(m=m, X=X, t=t, hi=hi, lo=lo, ok=ok, bo=np.asarray(b["o"], float), bh=np.asarray(b["h"], float),
                bl=np.asarray(b["l"], float), bt=np.asarray(b["t"], np.int64))


def trades(D, N, M, k, cost_mult=1.0, slip=0.0, start=None):
    C = P._M["C"]
    X = D["X"]
    E, J, EP, PX, TX, RK = sim(np.asarray(X["o"], float), np.asarray(X["c"], float), np.asarray(X["a20"], float),
                               np.asarray(X["a14"], float), D["hi"][N], D["lo"][M],
                               D["ok"] & (D["t"] >= W.ts(start or START)), D["bo"], D["bh"], D["bl"],
                               D["bt"], X["k0"].astype(np.int64), X["k1"].astype(np.int64), D["t"], k, slip)
    if len(E) == 0:
        return pd.DataFrame(columns=["mkt", "t", "tx", "R"])
    E, EP, PX, TX, RK = (np.asarray(v) for v in (E, EP, PX, TX, RK))
    spec = C.SPECS[D["m"]]
    t_in = D["bt"][X["k0"][E]]
    nts = C.nights(t_in, TX, spec["rollover3"])
    cost = spec["cost_rt_bp"] / 1e4 * cost_mult
    R = ((PX - EP) - EP * cost - EP * spec["swap_long_bp"] / 1e4 * nts) / RK
    return pd.DataFrame(dict(mkt=D["m"], t=D["t"][E], tx=TX, R=R))


def account(T, risk=0.01, start=None, end=None):
    """Balance compounding with overlapping trades: CAGR, balance DD, monthly returns."""
    T = T.sort_values("t")
    bal, peak, dd, heap, pts = 1.0, 1.0, 0.0, [], []
    for r in T.itertuples():
        while heap and heap[0][0] <= r.t:
            tx, p = heapq.heappop(heap)
            bal += p
            peak = max(peak, bal)
            dd = max(dd, 1 - bal / peak)
            pts.append((tx, bal))
        heapq.heappush(heap, (r.tx, risk * bal * r.R))
    while heap:
        tx, p = heapq.heappop(heap)
        bal += p
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        pts.append((tx, bal))
    s0 = W.ts(start or START)
    s1 = W.ts(end or END)
    yrs = (s1 - s0) / (365.25 * 86400)
    cagr = bal ** (1 / yrs) - 1 if bal > 0 else -1.0
    Rr = T.R.to_numpy()
    pf = Rr[Rr > 0].sum() / -Rr[Rr <= 0].sum() if (Rr <= 0).any() else np.inf
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([x for x, _ in pts], unit="s")) if pts else pd.Series(dtype=float)
    return dict(n=len(T), totR=float(Rr.sum()), pf=float(pf), cagr=float(cagr), dd=float(dd),
                mar=float(cagr / dd) if dd > 0 else np.nan), eq


def system_trades(sysname, Ds, N, M, k, **kw):
    return pd.concat([trades(Ds[m], N, M, k, **kw) for m in SYSTEMS[sysname]], ignore_index=True)


def monte_carlo(eq, risks=(0.005, 0.01, 0.02), runs=10000, years=10, block=6, seed=7):
    me = eq.resample("ME").last().ffill()
    mret = me.pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    nb = math.ceil(years * 12 / block)
    out = {}
    for r in risks:
        x = mret * (r / 0.01)
        dds, fin = [], []
        for _ in range(runs):
            st = rng.integers(0, len(x) - block, nb)
            path = np.concatenate([x[s:s + block] for s in st])[: years * 12]
            v = np.cumprod(1 + path)
            pk = np.maximum.accumulate(np.r_[1.0, v])[1:]
            dds.append(float(np.max(1 - v / pk)))
            fin.append(float(v[-1]))
        dds, fin = np.array(dds), np.array(fin)
        out[r] = dict(dd_median=float(np.median(dds)), dd_p95=float(np.quantile(dds, 0.95)),
                      p_dd30=float((dds > 0.30).mean()), p_dd50=float((dds > 0.50).mean()),
                      cagr_median=float(np.median(fin) ** (1 / years) - 1), p_loss=float((fin < 1).mean()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--placebos", type=int, default=N_PLACEBO)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    ext = K.externals()
    H1 = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    Ds = {m: prep_market(m, H1[m], ext) for m in K.MKTS}
    res = {"systems": {}}
    log = lambda s: print(f"  [{time.time() - t0:5.0f}s] {s}", flush=True)

    # phase 0: reproduce the baseline on the windows already reported
    for sname in SYSTEMS:
        win = {}
        for lab, s, e in (("5y", "2021-10-01", "2026-10-01"), ("10y", "2016-10-01", "2026-10-01"),
                          ("full", START, END), ("first_half", START, HALF), ("second_half", HALF, END)):
            T = system_trades(sname, Ds, *BASE, start=s)
            sub = T[(T.t >= W.ts(s)) & (T.t < W.ts(e))]
            st, eq = account(sub, 0.01, s, e)
            yearly = {}
            for y, g in sub.groupby(pd.to_datetime(sub.t, unit="s").dt.year):
                yearly[int(y)] = float(g.R.sum())
            win[lab] = dict(st, yearly_R=yearly)
        res["systems"][sname] = dict(markets=SYSTEMS[sname], windows=win)
        w = win["full"]
        log(f"{sname} 5y check: trades {win['5y']['n']} totR {win['5y']['totR']:+.1f}")
        log(f"{sname} full 2009-2026: trades {w['n']} totR {w['totR']:+.0f} PF {w['pf']:.2f} CAGR {w['cagr']:+.1%} "
            f"balDD {w['dd']:.1%} | 5y CAGR {win['5y']['cagr']:+.1%} | 10y CAGR {win['10y']['cagr']:+.1%} DD {win['10y']['dd']:.1%}")
        for lab in ("first_half", "second_half"):
            log(f"   {lab}: CAGR {win[lab]['cagr']:+.1%} DD {win[lab]['dd']:.1%} PF {win[lab]['pf']:.2f}")

    # (2) neighbourhood
    for sname in SYSTEMS:
        grid = []
        for N, M, k in itertools.product(NS, MS, KS):
            st, _ = account(system_trades(sname, Ds, N, M, k), 0.01)
            grid.append(dict(N=N, M=M, k=k, **st))
        G_ = pd.DataFrame(grid)
        base = G_[(G_.N == BASE[0]) & (G_.M == BASE[1]) & (G_.k == BASE[2])].iloc[0]
        others = G_.drop(base.name)
        res["systems"][sname]["neighbourhood"] = dict(
            grid=grid, share_pf_gt1=float((G_.pf > 1).mean()), median_mar=float(others.mar.median()),
            base_mar=float(base.mar), base_rank_mar=int((G_.mar > base.mar).sum()) + 1)
        log(f"{sname} neighbourhood: PF>1 in {(G_.pf > 1).mean():.0%} of 80, median MAR {others.mar.median():.2f} vs base "
            f"{base.mar:.2f} (rank {int((G_.mar > base.mar).sum()) + 1}/80)")

    # (3) cost stress
    for sname in SYSTEMS:
        st, _ = account(system_trades(sname, Ds, *BASE, cost_mult=2.0, slip=0.1), 0.01)
        res["systems"][sname]["cost_stress"] = st
        log(f"{sname} costs x2 + 0.1 ATR stop slippage: PF {st['pf']:.2f} CAGR {st['cagr']:+.1%} DD {st['dd']:.1%}")

    # (5) Monte Carlo from the base account's monthly balance
    for sname in SYSTEMS:
        _, eq = account(system_trades(sname, Ds, *BASE), 0.01)
        mc = monte_carlo(eq)
        res["systems"][sname]["monte_carlo"] = {str(k): v for k, v in mc.items()}
        log(f"{sname} Monte Carlo 10y: " + " | ".join(
            f"{r:.1%} risk: DD median {v['dd_median']:.0%} p95 {v['dd_p95']:.0%} P(DD>50%) {v['p_dd50']:.1%} P(loss) {v['p_loss']:.1%}"
            for r, v in mc.items()))

    # (4) drift placebos
    P._M["h1"] = H1
    real = {s: float(system_trades(s, Ds, *BASE).R.sum()) for s in SYSTEMS}
    plac = {s: [] for s in SYSTEMS}
    for p in range(a.placebos):
        ph = P.drift_placebo(p)
        Dp = {m: prep_market(m, ph[m], ext) for m in K.MKTS}
        for s in SYSTEMS:
            plac[s].append(float(system_trades(s, Dp, *BASE).R.sum()))
        if (p + 1) % 10 == 0:
            log(f"placebos {p + 1}/{a.placebos}")
    for s in SYSTEMS:
        v = np.array(plac[s])
        res["systems"][s]["placebo"] = dict(real_totR=real[s], median=float(np.median(v)), p95=float(np.quantile(v, 0.95)),
                                            max=float(v.max()), p_value=float((1 + (v >= real[s]).sum()) / (1 + len(v))))
        log(f"{s} placebo: real {real[s]:+.0f}R vs drift median {np.median(v):+.0f}R p95 {np.quantile(v, 0.95):+.0f}R "
            f"max {v.max():+.0f}R  p={(1 + (v >= real[s]).sum()) / (1 + len(v)):.3f}")

    # verdicts
    for s, r in res["systems"].items():
        w = r["windows"]
        nb = r["neighbourhood"]
        checks = dict(
            a_history=w["full"]["cagr"] > 0 and w["full"]["pf"] > 1.2 and w["first_half"]["cagr"] > 0 and w["second_half"]["cagr"] > 0,
            b_plateau=nb["share_pf_gt1"] >= 0.70 and nb["median_mar"] >= 0.5 * nb["base_mar"],
            c_costs=r["cost_stress"]["pf"] > 1.1,
            d_placebo=r["placebo"]["real_totR"] > r["placebo"]["p95"],
            e_montecarlo=r["monte_carlo"]["0.01"]["p_dd50"] < 0.05)
        r["checks"] = checks
        r["passed"] = all(checks.values())
        log(f"{s} checks: {checks} -> {'PASS' if r['passed'] else 'FAIL'}")
    (HERE / "phase1.json").write_text(json.dumps(res, indent=1, default=str))
    log("saved phase1.json")


if __name__ == "__main__":
    main()
