"""Complement search (docs/plans/COMPLEMENT_PREREG.md): B wins in the months setup 1 (A) loses, C wins in the months A and B both lose.
Pools: B = 108 short-only trend setups (G27K short entries), C = 72 two-way reversion setups for trendless markets. Choose on
2009-09..2017-12 (gold and silver), test on 2018-01..2026-09 (gold, silver, BTC). Single unit, stops and exits walked on H1 bars;
trades returned in the report768 format so equity is marked at every H4 close."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
FIRST, TEST0 = C.ts("2009-09-01"), C.ts("2018-01-01")
B_POOL = list(itertools.product(("C1", "C2", "C3"), ("D1", "D2", "D3", "D4", "D6", "D8"), ("G2", "G3"), ("H1", "H2", "H3")))
C_POOL = list(itertools.product(("R0", "R1", "R2"), ("M1", "M2", "M3", "M4"), ("X1", "X2", "X3"), ("S1", "S2")))


def er(c, n=20):
    with np.errstate(invalid="ignore", divide="ignore"):
        net = np.abs(c - np.r_[np.full(n, np.nan), c[:-n]])
        path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(n).sum().to_numpy()
        return net / path


def extras(m, h1, X, M):
    """Indicators the B and C pools need, aligned to the H4 bars of X."""
    c = X["c"]; S_ = pd.Series(c)
    X["lo10"] = pd.Series(X["l"]).rolling(10).min().shift(1).to_numpy(); X["hi10"] = pd.Series(X["h"]).rolling(10).max().shift(1).to_numpy()
    X["sma20"] = S_.rolling(20).mean().to_numpy(); sd = S_.rolling(20).std(ddof=0).to_numpy()
    X["bb_up"], X["bb_dn"] = X["sma20"] + 2 * sd, X["sma20"] - 2 * sd
    X["rsi2"] = K.rsi(c, 2); X["er_h4"] = er(c)
    D = G.frames(h1)["D1"]; erd = er(D["c"])
    dc = np.minimum(np.r_[D["t"][1:], K.BIG], D["t"] + 86400); xc = np.minimum(np.r_[X["t"][1:], K.BIG], X["t"] + 14400)
    j = np.searchsorted(dc, xc, side="right") - 1
    X["er_d1"] = np.where(j >= 0, erd[np.maximum(j, 0)], np.nan)
    X["ok"] = M["ok"]


def sim(X, m, s_idx, d_arr, stop_k, exit_mode, tp_r=None):
    """Single unit, market entry at the next open, stop stop_k x ATR20, exits: ch20 / ch10 / chand / sma20 / time6 / tp."""
    o, h, l, c, a20, a22, t = X["o"], X["h"], X["l"], X["c"], X["a20"], X["a22"], X["t"]
    B = X["b"]; bo, bh, bl, bt = B["o"], B["h"], B["l"], B["t"]; k0, k1 = X["k0"], X["k1"]; n = len(c)
    spec = C.SPECS[m]; cost = spec["cost_rt_bp"] / 1e4
    lo20, hi20, lo10, hi10, sma = X["dlo"], X["dhi"], X["lo10"], X["hi10"], X["sma20"]
    out = []; busy = -1
    for s, d in zip(s_idx, d_arr):
        if s <= busy or s + 1 >= n or not np.isfinite(a20[s]):
            continue
        e = s + 1; ep = o[e]; N = a20[s]; risk = stop_k * N; stop = ep - d * risk
        tp = ep + d * tp_r * risk if tp_r else None
        j = e; px = None; best = ep; tx = None
        while j < n:
            for q in range(k0[j], k1[j]):
                oq = ep if q == k0[e] else bo[q]
                if (d > 0 and bl[q] <= stop) or (d < 0 and bh[q] >= stop):
                    px = stop if d * (oq - stop) > 0 else oq; tx = int(bt[q]); break
                if tp is not None and ((d > 0 and bh[q] >= tp) or (d < 0 and bl[q] <= tp)):
                    px = tp if d * (tp - oq) > 0 else oq; tx = int(bt[q]); break
            if px is not None:
                break
            best = max(best, h[j]) if d > 0 else min(best, l[j])
            if exit_mode == "ch20":
                hit = (c[j] < lo20[j]) if d > 0 else (c[j] > hi20[j])
            elif exit_mode == "ch10":
                hit = (c[j] < lo10[j]) if d > 0 else (c[j] > hi10[j])
            elif exit_mode == "chand":
                hit = (c[j] < best - 3 * a22[j]) if d > 0 else (c[j] > best + 3 * a22[j])
            elif exit_mode == "sma20":
                hit = (c[j] >= sma[j]) if d > 0 else (c[j] <= sma[j])
            elif exit_mode == "time6":
                hit = j >= e + 5
            else:
                hit = False
            if hit and j + 1 < n:
                j += 1; px = o[j]; tx = int(t[j]); break
            j += 1
        if px is None:
            j = n - 1; px = c[j]; tx = int(t[j])
        swr = (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
        nts = int(C.nights(np.array([t[e]]), np.array([tx]), spec["rollover3"])[0])
        gross = d * (px - ep); swap = ep * swr * nts; spread = ep * cost
        out.append(dict(mkt=m, e=e, x=j, d=int(d), ep=ep, px=px, risk=risk, units=[(ep, e, int(t[e]))], R=(gross - swap - spread) / risk,
                        R_gross=gross / risk, R_swap=swap / risk, R_spread=spread / risk, t=int(t[e]), t_exit=tx, mfe=0.0, mae=0.0, gaps=0, same=0,
                        stop_pct=risk / ep, cost=cost, swr=swr, triple=spec["rollover3"], X=X))
        busy = j
    return out


def signals_A(M):
    d = K.directions(M, "C8", "D3", "E1", "J1"); return np.flatnonzero(d), d[np.flatnonzero(d)]


def signals_B(M, Cc, D):
    sh = M["Ds"][D] & M["Cs"][Cc] & M["ok"]; s = np.flatnonzero(sh); return s, -np.ones(len(s), int)


def signals_C(X, Rf, Mf):
    c, h, l = X["c"], X["h"], X["l"]; p = lambda a: np.r_[np.nan, a[:-1]]
    with np.errstate(invalid="ignore"):
        if Mf == "M1":
            lo, sh = X["rsi2"] < 10, X["rsi2"] > 90
        elif Mf == "M2":
            lo, sh = c < X["bb_dn"], c > X["bb_up"]
        elif Mf == "M3":
            lo = (p(c) < p(X["dlo"])) & (c > p(X["dlo"])); sh = (p(c) > p(X["dhi"])) & (c < p(X["dhi"]))
        else:
            lo = (l <= X["dlo"]) & (c > X["dlo"]); sh = (h >= X["dhi"]) & (c < X["dhi"])
        f = np.ones(len(c), bool) if Rf == "R0" else ((X["er_d1"] < 0.25) if Rf == "R1" else (X["er_h4"] < 0.25))
    d = np.zeros(len(c), int); d[lo & f & X["ok"]] = 1; d[sh & f & X["ok"] & ~(lo & f)] = -1
    s = np.flatnonzero(d); return s, d[s]


def monthly(trades, t0=None, t1=None):
    r = [(pd.Timestamp(x["t_exit"], unit="s").to_period("M"), x["R"]) for x in trades if (t0 is None or x["t"] >= t0) and (t1 is None or x["t"] < t1)]
    return pd.Series([v for _, v in r], index=[k for k, _ in r], dtype=float).groupby(level=0).sum() if r else pd.Series(dtype=float)


def stats(trades, t0, t1):
    sub = [x for x in trades if x["t"] >= t0 and (t1 is None or x["t"] < t1)]
    R = np.array([x["R"] for x in sub]) if sub else np.array([])
    return dict(n=len(R), totR=float(R.sum()) if len(R) else 0.0, avgR=float(R.mean()) if len(R) else np.nan, win=float((R > 0).mean()) if len(R) else np.nan)


def pick(pool_trades, target_months, t0, t1):
    best = None
    for key, tr in pool_trades.items():
        st = stats(tr, t0, t1)
        if st["n"] < 30 or st["totR"] <= 0:
            continue
        mo = monthly(tr, t0, t1); inm = float(mo.reindex(target_months).fillna(0).sum())
        if best is None or inm > best[1]:
            best = (key, inm, st)
    return best


def main():
    K.START = FIRST
    ext = K.externals(); Ms, Xs = {}, {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); Ms[m] = K.prepare(m, h1, ext); X = G.features(G.frames(h1), m, "H4"); X["sec"] = 14400
        extras(m, h1, X, Ms[m]); Xs[m] = X
    stop_k = {"G2": 2.0, "G3": 3.0, "S1": 1.5, "S2": 2.5}
    exit_of = {"H1": ("chand", None), "H2": ("ch20", None), "H3": ("ch10", None), "X1": ("sma20", None), "X2": ("tp", 1.5), "X3": ("time6", None)}
    A = [x for m in K.MKTS for x in sim(Xs[m], m, *signals_A(Ms[m]), 2.0, "ch20")]
    Bp = {}
    for Cc, D, Gs, H in B_POOL:
        Bp["/".join((Cc, D, Gs, H))] = [x for m in K.MKTS for x in sim(Xs[m], m, *signals_B(Ms[m], Cc, D), stop_k[Gs], *exit_of[H])]
    Cp = {}
    for Rf, Mf, Xe, Sk in C_POOL:
        Cp["/".join((Rf, Mf, Xe, Sk))] = [x for m in K.MKTS for x in sim(Xs[m], m, *signals_C(Xs[m], Rf, Mf), stop_k[Sk], *exit_of[Xe])]
    a_mo = monthly(A, FIRST, TEST0); a_lose = a_mo.index[a_mo < 0]
    bk, b_in, b_st = pick(Bp, a_lose, FIRST, TEST0)
    b_mo = monthly(Bp[bk], FIRST, TEST0).reindex(a_mo.index.union(monthly(Bp[bk], FIRST, TEST0).index)).fillna(0)
    a_full = a_mo.reindex(b_mo.index).fillna(0)
    ab_lose = b_mo.index[(a_full < 0) & (b_mo < 0)]
    ck, c_in, c_st = pick(Cp, ab_lose, FIRST, TEST0)
    print(f"selection 2009-09..2017-12: A losing months {len(a_lose)} of {len(a_mo)}; A totR {stats(A, FIRST, TEST0)['totR']:.1f}")
    print(f"  B = {bk}: R in A-losing months {b_in:+.1f}, selection {b_st}")
    print(f"  months A and B both lose: {len(ab_lose)}; C = {ck}: R in those months {c_in:+.1f}, selection {c_st}")
    res = dict(B=bk, C=ck, selection=dict(A=stats(A, FIRST, TEST0), B=b_st, C=c_st, b_in=b_in, c_in=c_in, a_lose=len(a_lose), ab_lose=len(ab_lose)))
    B, Cc_ = Bp[bk], Cp[ck]
    test = {}
    for nm, tr in (("A", A), ("B", B), ("C", Cc_)):
        test[nm] = stats(tr, TEST0, None)
    ma, mb, mc = (monthly(tr, TEST0, None) for tr in (A, B, Cc_))
    idx = ma.index.union(mb.index).union(mc.index); ma, mb, mc = (x.reindex(idx).fillna(0) for x in (ma, mb, mc))
    la = ma < 0; lab = la & (mb < 0)
    test["months"] = dict(total=len(idx), a_lose=int(la.sum()), b_wins_when_a_loses=float((mb[la] > 0).mean()), ab_lose=int(lab.sum()),
                          c_wins_when_ab_lose=float((mc[lab] > 0).mean()) if lab.any() else np.nan,
                          corr_ab=float(np.corrcoef(ma, mb)[0, 1]), corr_ac=float(np.corrcoef(ma, mc)[0, 1]), corr_bc=float(np.corrcoef(mb, mc)[0, 1]),
                          b_R_in_a_lose=float(mb[la].sum()), c_R_in_ab_lose=float(mc[lab].sum()) if lab.any() else 0.0)
    print("test 2018-01..2026-09:", json.dumps({k: test[k] for k in ("A", "B", "C")}), "\n  months:", json.dumps(test["months"]))
    port = {}
    for vname, items, risk in (("A alone 1%", [A], 0.01), ("A+B+C 0.33% each", [A, B, Cc_], 0.01 / 3), ("A+B+C 1% each", [A, B, Cc_], 0.01),
                               ("B alone 1%", [B], 0.01), ("C alone 1%", [Cc_], 0.01)):
        for wname, a, b in (("test 2018-01..2026-09", "2018-01-01", None), ("2018", "2018-01-01", "2019-01-01"), ("2022", "2022-01-01", "2023-01-01"),
                            ("metals bear 2011-09..2015-12 (selection period)", "2011-09-01", "2016-01-01"), ("all 2009-09..2026-09 (part selection)", "2009-09-01", None)):
            R = S.account_window([x for tr in items for x in tr], risk, C.ts(a), C.ts(b) if b else None, Xs)
            if R is None:
                continue
            port[f"{vname} | {wname}"] = {k: v for k, v in R.items() if k not in ("by_mkt",)}
            print(f"  {vname:20s} | {wname:46s} | total {R['ret']:+7.0%} CAGR {R['cagr']:+6.1%} equity DD {R['eq_dd']:5.1%} balance DD {R['bal_dd']:5.1%}"
                  f" low {R['low']:4.0%} | trades {R['n']} PF {R['pf']:.2f}")
    res.update(test=test, portfolio=port)
    (K.OUT / "complement.json").write_text(json.dumps(res, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
