"""Y1 / Y3 / Y4 / Y7 / Y8 of docs/BUNDLE2_2026-10-01_PREREG.md: the higher-TF-aligned trend system (anchor direction + side switch + no
chasing), the exclusion of the conditions that lose most often, small timeframes anchored to big ones, the invalidation exit and the
volatility router. Clean evidence: 16 MT5 markets and gold 2003-05..2008-12 (Dukascopy); gold 2009-26 / silver are in-sample.
Usage: python research/bundle/y1_htf_system.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

L = C.L
OUT = C.ROOT / "data" / "bundle2"; OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
ENTRY_TFS = ("M5", "M15", "M30", "H1", "H4", "D1")
NEAR = {"M5": ("H1", "H4"), "M15": ("H4", "D1"), "M30": ("H4", "D1"), "H1": ("D1", "W1"), "H4": ("D1", "W1"), "D1": ("W1", "W1")}
FAR = {tf: ("D1", "W1") for tf in ENTRY_TFS[:-1]} | {"D1": ("W1", "W1")}
CLEAN = tuple(m for m in C.ORIG8 + C.NEW8)
CUTS = L.cut_grid(C.ts("2026-10-02"))


# ------------------------------------------------------------------ gold 2003-08 (Dukascopy)
_EARLY = {}


def early_bars(tf):
    if tf in _EARLY:
        return _EARLY[tf]
    sys.path[:0] = [str(C.ROOT / "research" / "wrwr"), str(C.ROOT / "research" / "foundry")]
    import signals as SG
    if tf == "W1":
        D = early_bars("D1")
        X = C._agg(D, np.searchsorted(CUTS, D.t, side="right") - 1, "W1")
    else:
        B, _, _ = SG.load_xau(tf)
        X = L.Bars(tf=tf, t=np.asarray(B.t, np.int64), o=np.asarray(B.o, float), h=np.asarray(B.h, float), l=np.asarray(B.l, float),
                   c=np.asarray(B.c, float), v=np.asarray(B.v, float), n=np.full(len(B.t), 12), hi_pos=np.full(len(B.t), np.nan),
                   lo_pos=np.full(len(B.t), np.nan))
        X.atr = L.atr(X.h, X.l, X.c, 14)
    _EARLY[tf] = X
    return X


def get_bars(mkt, tf):
    if mkt == "GOLD_EARLY":
        return early_bars(tf)
    return C.bars(mkt, tf)


def cost_sym(mkt):
    return "XAUUSD" if mkt == "GOLD_EARLY" else mkt


# ------------------------------------------------------------------ anchors
def anchor_dir(B, A):
    """Sign of (close of the last completed anchor bar - midpoint of its 55-bar Donchian), at each B bar's close."""
    ac = A.t + L.TF_SECONDS[A.tf] if A.tf != "W1" else np.r_[A.t[1:], A.t[-1] + 7 * 86400]
    j = np.searchsorted(ac, B.t + L.TF_SECONDS[B.tf], side="right") - 1
    mid = (pd.Series(A.h).rolling(55).max() + pd.Series(A.l).rolling(55).min()).to_numpy() / 2
    v = np.where(j >= 0, np.sign(A.c[np.maximum(j, 0)] - mid[np.maximum(j, 0)]), 0)
    return np.nan_to_num(v).astype(int)


def market_frame(mkt, tf):
    """Every-signal trades of the three systems (both sides) with every flag the variants need."""
    B = get_bars(mkt, tf)
    a1n, a2n = NEAR[tf]; a1f, a2f = FAR[tf]
    A = {x: get_bars(mkt, x) for x in {a1n, a2n, a1f, a2f, "D1", "W1"}}
    dn1, dn2 = anchor_dir(B, A[a1n]), anchor_dir(B, A[a2n])
    reg_near = np.where(dn1 == dn2, dn1, 0)
    df1, df2 = anchor_dir(B, A[a1f]), anchor_dir(B, A[a2f])
    reg_far = np.where(df1 == df2, df1, 0)
    ctx = L.htf_context(B, A[a1n], "a1")
    a1_run = ctx["a1_last_run"].to_numpy(); a1_rng = ctx["a1_form_range_atr"].to_numpy()
    w1 = L.htf_context(B, A["W1"], "w1")
    w1_body = w1["w1_last_body_atr"].to_numpy(); w1_run = w1["w1_last_run"].to_numpy()
    if tf == "D1":
        d1_run = L.anatomy(B)["run"].to_numpy()
    else:
        d1_run = L.htf_context(B, A["D1"], "d1")["d1_last_run"].to_numpy()
    win = {"M5": 12 * 24 * 250, "M15": 4 * 24 * 250, "M30": 2 * 24 * 250, "H1": 24 * 250, "H4": 6 * 250, "D1": 250}[tf]
    atr_pct = pd.Series(B.atr).rolling(win, min_periods=min(win, 500)).rank(pct=True).to_numpy()
    d1 = A["D1"]
    d1_pct_d = pd.Series(d1.atr).rolling(250, min_periods=100).rank(pct=True).to_numpy()
    jd = np.searchsorted(d1.t + 86400, B.t + L.TF_SECONDS[B.tf], side="right") - 1
    d1_pct = np.where(jd >= 0, d1_pct_d[np.maximum(jd, 0)], np.nan)
    parts = []
    for system in C.SYSTEMS:
        for side in (1, -1):
            T = C.trend_trades(B, cost_sym(mkt), system, side)
            parts.append(T)
    T = pd.concat(parts, ignore_index=True)
    s = T.s.to_numpy(); d = T.d.to_numpy()
    T["reg_near"] = reg_near[s]; T["reg_far"] = reg_far[s]
    chase = np.where(d > 0, (a1_run[s] >= 3) | (a1_rng[s] >= 1.3), (a1_run[s] <= -3) | (a1_rng[s] >= 1.3))
    T["chase"] = np.nan_to_num(chase).astype(bool)
    hour = (T.t.to_numpy() // 3600) % 24
    T["E1"] = (hour >= 20) & (L.TF_SECONDS[tf] <= 3600)
    T["E2"] = (atr_pct[s] < 0.10) & (L.TF_SECONDS[tf] <= 1800)
    counter_long = (w1_body[s] <= -0.75) | (w1_run[s] <= -3) | (d1_run[s] <= -3)
    counter_short = (w1_body[s] >= 0.75) | (w1_run[s] >= 3) | (d1_run[s] >= 3)
    T["E3"] = np.nan_to_num(np.where(d > 0, counter_long, counter_short)).astype(bool)
    T["E4"] = T.chase
    T["d1_pct"] = d1_pct[s]
    T["mkt"] = mkt; T["tf"] = tf
    T["inv_R"] = invalidation_R(B, T, cost_sym(mkt))
    return B, T


def invalidation_R(B, T, sym):
    """Y7: exit at the next open when a close within the first 5 bars after entry falls back beyond the breakout level (the entry channel
    extreme at the signal); otherwise the system's own exit. Net R with cost and swap."""
    out = T.R.to_numpy().copy()
    hiE = {}
    for system, (entry_n, _) in C.SYSTEMS.items():
        hiE[system] = (pd.Series(B.h).rolling(entry_n).max().shift(1).to_numpy(), pd.Series(B.l).rolling(entry_n).min().shift(1).to_numpy())
    n = len(B.c)
    s_, e_, xf_, d_, ep_, rk_ = T.s.to_numpy(), T.e.to_numpy(), T.xf.to_numpy(), T.d.to_numpy(), T.ep.to_numpy(), T.risk.to_numpy()
    sysn = T.system.to_numpy(); cost = C.cost_rt_bp(sym)
    for i in range(len(T)):
        lvl = hiE[sysn[i]][0][s_[i]] if d_[i] > 0 else hiE[sysn[i]][1][s_[i]]
        if not np.isfinite(lvl):
            continue
        j1 = min(e_[i] + 5, xf_[i] - 1, n - 2)
        if j1 < e_[i]:
            continue
        seg = B.c[e_[i]:j1 + 1]
        hit = (seg < lvl) if d_[i] > 0 else (seg > lvl)
        if hit.any():
            j = e_[i] + int(np.argmax(hit)); px = B.o[j + 1]
            g = d_[i] * (px - ep_[i]) / rk_[i]
            sw = float(C.swap_bp(sym, B.t[[e_[i]]], B.t[[j + 1]], d_[i:i + 1])[0])
            out[i] = g - (cost + sw) / (rk_[i] / ep_[i] * 1e4)
    return out


VARIANTS = {
    "BASE": lambda T: np.ones(len(T), bool),
    "LONG": lambda T: T.d.to_numpy() > 0,
    "REGIME": lambda T: T.reg_near.to_numpy() == T.d.to_numpy(),
    "FULL": lambda T: (T.reg_near.to_numpy() == T.d.to_numpy()) & ~T.chase.to_numpy(),
    "FULL_FAR": lambda T: (T.reg_far.to_numpy() == T.d.to_numpy()) & ~T.chase.to_numpy(),
    "Y3_KEPT": lambda T: ~(T.E1 | T.E2 | T.E3 | T.E4).to_numpy(),
    "Y3_noE1": lambda T: ~T.E1.to_numpy(), "Y3_noE2": lambda T: ~T.E2.to_numpy(), "Y3_noE3": lambda T: ~T.E3.to_numpy(),
    "Y3_noE4": lambda T: ~T.E4.to_numpy(),
}


def evaluate(T, mkt, tf, period):
    rows, taken = [], {}
    for v, f in VARIANTS.items():
        m = f(T)
        for system in C.SYSTEMS:
            g = T[m & (T.system.to_numpy() == system)]
            if not len(g):
                continue
            tk = g[C.one_position(g)]
            taken[(v, system)] = tk
            rows.append(dict(mkt=mkt, tf=tf, period=period, variant=v, system=system, n_all=len(g), R_all=g.R.mean(), n_taken=len(tk),
                             R_taken=tk.R.mean() if len(tk) else np.nan, R_inv_all=g.inv_R.mean(), R_inv_taken=tk.inv_R.mean() if len(tk) else np.nan))
    return rows, taken


def boot_pooled(D, K=1000, seed=3):
    """One-sided p for pooled mean R > 0, clusters = market-week."""
    key = D.mkt.astype(str) + "|" + pd.Series(np.searchsorted(CUTS, D.t.to_numpy(), side="right") - 1, index=D.index).astype(str)
    g = D.groupby(key).R.agg(["sum", "size"])
    S, N = g["sum"].to_numpy(), g["size"].to_numpy(); mu = S.sum() / N.sum()
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(S), (K, len(S)))
    bm = (S - mu * N)[idx].sum(1) / N[idx].sum(1)
    return mu, float((bm >= mu).mean())


def boot_diff(A_, B_, K=1000, seed=5):
    """One-sided p for mean(A) - mean(B) > 0 with joint market-week clusters (A is a subset of B's universe)."""
    def keyed(D):
        return D.mkt.astype(str) + "|" + pd.Series(np.searchsorted(CUTS, D.t.to_numpy(), side="right") - 1, index=D.index).astype(str)
    ga = A_.groupby(keyed(A_)).R.agg(["sum", "size"]); gb = B_.groupby(keyed(B_)).R.agg(["sum", "size"])
    keys = gb.index
    ga = ga.reindex(keys).fillna(0)
    a, b = ga.to_numpy(), gb.to_numpy()
    obs = a[:, 0].sum() / max(a[:, 1].sum(), 1) - b[:, 0].sum() / b[:, 1].sum()
    rng = np.random.default_rng(seed); out = []
    for _ in range(K):
        i = rng.integers(0, len(keys), len(keys))
        out.append(a[i, 0].sum() / max(a[i, 1].sum(), 1) - b[i, 0].sum() / b[i, 1].sum())
    return obs, float((np.asarray(out) - obs >= obs).mean())


def main():
    rows, verdict, fin = [], [], []
    for tf in ENTRY_TFS:
        pool = {v: [] for v in VARIANTS}
        taken_all = {v: [] for v in VARIANTS}
        router_src = []
        for mkt in CLEAN + ("GOLD_EARLY", "XAUUSD", "XAGUSD"):
            if mkt == "GOLD_EARLY" and tf not in ("H1", "H4", "D1"):
                continue
            try:
                B, T = market_frame(mkt, tf)
            except (FileNotFoundError, KeyError, ValueError) as ex:
                log(f"skip {mkt} {tf}: {ex}"); continue
            if mkt == "GOLD_EARLY":
                T = T[(T.t >= C.ts("2003-08-01")) & (T.t < C.ts("2009-01-01"))]
            periods = {"ALL": T} if mkt not in ("XAUUSD",) else {"DEV": T[T.t < C.ts("2016-01-01")], "CHECK": T[T.t >= C.ts("2016-01-01")],
                                                                 "BEAR": T[(T.t >= C.ts("2012-10-01")) & (T.t < C.ts("2016-01-01"))]}
            for p, TT in periods.items():
                r, tk = evaluate(TT, mkt, tf, p)
                rows += r
                if mkt in CLEAN and mkt != "USDINR":
                    for v, f in VARIANTS.items():
                        pool[v].append(TT[f(TT)])
                        for system in C.SYSTEMS:
                            if (v, system) in tk:
                                taken_all[v].append(tk[(v, system)].assign(system=system))
            if mkt in CLEAN and mkt != "USDINR" and tf in ("H1", "H4", "D1"):
                router_src.append(T)
            del T
        log(f"{tf}: markets done")
        R = pd.DataFrame(rows)
        for v in VARIANTS:
            P = pd.concat(pool[v]) if pool[v] else pd.DataFrame()
            if not len(P):
                continue
            for system in C.SYSTEMS:
                Pv = P[P.system == system]
                Pb = pd.concat(pool["BASE"]); Pb = Pb[Pb.system == system]
                mu, p = boot_pooled(Pv)
                dlt, pd_ = boot_diff(Pv, Pb) if v != "BASE" else (0.0, np.nan)
                x = R[(R.tf == tf) & (R.variant == v) & (R.system == system) & R.mkt.isin([m for m in CLEAN if m != "USDINR"])]
                share = float((x.R_taken > 0).mean()) if len(x) else np.nan
                ge = R[(R.tf == tf) & (R.variant == v) & (R.system == system) & (R.mkt == "GOLD_EARLY")]
                ge_R = float(ge.R_taken.iloc[0]) if len(ge) else np.nan
                ok = (share >= 0.6) and mu > 0 and p < 0.05 and dlt > 0 and pd_ < 0.05 and (tf not in ("H1", "H4", "D1") or ge_R > 0)
                verdict.append(dict(tf=tf, variant=v, system=system, markets=len(x), share_taken_pos=share, pooled_R_all=mu, p=p, vs_BASE=dlt,
                                    p_vs_BASE=pd_, gold_2003_08_R_taken=ge_R, PASS=bool(ok) if v not in ("BASE", "LONG") else None))
            Tk = pd.concat(taken_all[v]) if taken_all[v] else pd.DataFrame()
            for system in C.SYSTEMS:
                g = Tk[Tk.system == system] if len(Tk) else Tk
                if len(g):
                    fin.append(dict(tf=tf, variant=v, system=system, **C.equity(g, 0.01)))
        if router_src:
            S = pd.concat(router_src)
            for v in ("BASE", "FULL"):
                m = VARIANTS[v](S)
                g = S[m]
                allow = np.where(g.d1_pct < 0.33, "D1", np.where(g.d1_pct <= 0.67, "H4", "H1"))
                fin.append(dict(tf=tf, variant=f"Y8 router part ({v})", system="all", **C.equity(g[allow == tf], 0.01)))
        pd.DataFrame(rows).to_csv(OUT / "y1_rows.csv", index=False)
        pd.DataFrame(verdict).to_csv(OUT / "y1_verdict.csv", index=False)
        pd.DataFrame(fin).to_csv(OUT / "y1_finance.csv", index=False)
    log("Y1 done")


if __name__ == "__main__":
    main()
