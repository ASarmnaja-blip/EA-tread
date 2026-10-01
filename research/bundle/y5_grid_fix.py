"""Y5 of docs/BUNDLE2_2026-10-01_PREREG.md, RESEARCH ONLY (grids and martingale stay forbidden for any order): can the averaging grid be
fixed? Gold and silver H1, S = 1 x ATR22(D1), m = 1.5 / 2.0, first order 20 % of equity notional, take-profit at the weighted average
+ 0.5 S. Fixes: basket stop after k adds (k = 3 / 5 / 8), equity stop (floating loss 10 % / 20 % of the cycle-start equity), regime
direction (D1 and W1 55-bar Donchian midpoints agree). Reference: ONE order of the same first size with the same take-profit and a stop at
the k = 5 basket-stop distance. Directions LONG, SHORT, REGIME, RANDOM (50 seeds). Usage: python research/bundle/y5_grid_fix.py"""
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


def grid2(B, D1, W1, sym, S_mult, m, rule, basket_k=None, eq_stop=None, single_k=None, seed=0, lev=200.0, first_frac=0.20):
    t, o, h, l, c = B.t, B.o, B.h, B.l, B.c
    half = C.cost_rt_bp(sym) / 2 / 1e4
    swl = C.K.swap_bp(sym, t, t + 3600, np.ones(len(t))) / 1e4
    j = np.searchsorted(D1.t + 86400, t, side="right") - 1
    A22 = L.atr(D1.h, D1.l, D1.c, 22)
    atr_at = np.where(j >= 0, A22[np.maximum(j, 0)], np.nan)
    def regime_dir(X, closes_t):
        mid = (pd.Series(X.h).rolling(55).max() + pd.Series(X.l).rolling(55).min()).to_numpy() / 2
        k = np.searchsorted(closes_t, t, side="right") - 1
        return np.nan_to_num(np.where(k >= 0, np.sign(X.c[np.maximum(k, 0)] - mid[np.maximum(k, 0)]), 0))
    rd = regime_dir(D1, D1.t + 86400); rw = regime_dir(W1, np.r_[W1.t[1:], W1.t[-1] + 7 * 86400])
    regime = np.where(rd == rw, rd, 0)
    rng = np.random.default_rng(seed)
    eq = 10_000.0; injected = 10_000.0; ruins = 0; first_ruin = None; peak = eq; maxdd = 0.0
    orders = []; D = 0; S = 0.0; cyc = 0; won = 0; stops = 0; eq0 = eq; cyc_pnl = []
    i = 0; n = len(t)
    while i < n:
        if not orders:
            if not np.isfinite(atr_at[i]) or atr_at[i] <= 0:
                i += 1; continue
            if rule == "REGIME":
                D = int(regime[i])
                if D == 0:
                    i += 1; continue
            else:
                D = {"LONG": 1, "SHORT": -1}.get(rule) or (1 if rng.random() < 0.5 else -1)
            S = S_mult * atr_at[i]; eq0 = eq
            orders = [(o[i], first_frac * eq)]; eq -= first_frac * eq * half; cyc += 1
        adv = l[i] if D > 0 else h[i]
        closed = False
        # adds (grid only) and the basket stop at the level after the k-th add
        if single_k is None:
            while True:
                lvl = orders[-1][0] - D * S
                if not ((D > 0 and adv <= lvl) or (D < 0 and adv >= lvl)):
                    break
                if basket_k is not None and len(orders) - 1 >= basket_k:
                    px = lvl if D * (o[i] - lvl) > 0 else o[i]
                    eq += sum(q * D * (px / p - 1) for p, q in orders) - sum(q for _, q in orders) * half
                    cyc_pnl.append(eq / eq0 - 1); orders = []; stops += 1; closed = True
                    break
                notion = orders[-1][1] * m
                used = sum(q for _, q in orders) / lev
                flo = sum(q * D * (lvl / p - 1) for p, q in orders)
                if (eq + flo - used) >= notion / lev:
                    orders.append((lvl, notion)); eq -= notion * half
                    continue
                break
        else:
            lvl = orders[0][0] - D * (single_k + 1) * S
            if (D > 0 and adv <= lvl) or (D < 0 and adv >= lvl):
                px = lvl if D * (o[i] - lvl) > 0 else o[i]
                eq += sum(q * D * (px / p - 1) for p, q in orders) - sum(q for _, q in orders) * half
                cyc_pnl.append(eq / eq0 - 1); orders = []; stops += 1; closed = True
        if not closed and eq_stop is not None and orders:
            Q0 = sum(q for _, q in orders); Q1 = sum(q / p for p, q in orders)
            lim = eq_stop * eq0
            x = (Q0 - D * lim) / Q1
            if (D > 0 and adv <= x) or (D < 0 and adv >= x):
                px = x if D * (o[i] - x) > 0 else o[i]
                eq += D * (px * Q1 - Q0) - Q0 * half
                cyc_pnl.append(eq / eq0 - 1); orders = []; stops += 1; closed = True
        if not closed and orders:
            flo_adv = sum(q * D * (adv / p - 1) for p, q in orders)
            if eq + flo_adv <= 0:
                ruins += 1; first_ruin = first_ruin if first_ruin is not None else (t[i] - t[0]) / (365.25 * 86400)
                cyc_pnl.append(-1.0)
                eq = 10_000.0; injected += 10_000.0; orders = []; peak = eq; i += 1; continue
            maxdd = max(maxdd, 1 - (eq + flo_adv) / peak)
            tot = sum(q for _, q in orders); avg = tot / sum(q / p for p, q in orders)
            tp = avg + D * 0.5 * S
            fav = h[i] if D > 0 else l[i]
            if (D > 0 and fav >= tp) or (D < 0 and fav <= tp):
                eq += sum(q * D * (tp / p - 1) for p, q in orders) - tot * half
                cyc_pnl.append(eq / eq0 - 1); orders = []; won += 1; peak = max(peak, eq)
                i += 1; continue
            if D > 0:
                eq -= tot * swl[i]
        else:
            peak = max(peak, eq); maxdd = max(maxdd, 1 - eq / peak)
        i += 1
    if orders:
        eq += sum(q * D * (c[-1] / p - 1) for p, q in orders)
    yrs = (t[-1] - t[0]) / (365.25 * 86400)
    cp = np.asarray(cyc_pnl) if cyc_pnl else np.zeros(1)
    return dict(ruins=ruins, first_ruin_yrs=first_ruin, cycles=cyc, won_share=won / max(cyc, 1), stops=stops, max_dd=maxdd, end_eq=eq,
                injected=injected, cagr_net=(max(eq, 1) / injected) ** (1 / yrs) - 1, exp_cycle_pct=float(cp.mean() * 100),
                worst_cycle_pct=float(cp.min() * 100))


def main():
    rows = []
    for sym, a in (("XAUUSD", "2009-01-01"), ("XAGUSD", "2010-01-01")):
        H1 = C.bars(sym, "H1"); D1 = C.bars(sym, "D1"); W1 = C.bars(sym, "W1")
        mk = H1.t >= C.ts(a)
        H = L.Bars(tf="H1", t=H1.t[mk], o=H1.o[mk], h=H1.h[mk], l=H1.l[mk], c=H1.c[mk])
        for m in (1.5, 2.0):
            fixes = {"none": {}, "basket k3": dict(basket_k=3), "basket k5": dict(basket_k=5), "basket k8": dict(basket_k=8),
                     "equity stop 10%": dict(eq_stop=0.10), "equity stop 20%": dict(eq_stop=0.20), "single order (k5 distance)": dict(single_k=5)}
            for fx, kw in fixes.items():
                for rule in ("LONG", "SHORT", "REGIME"):
                    rows.append(dict(sym=sym, m=m, fix=fx, entries=rule, **grid2(H, D1, W1, sym, 1.0, m, rule, **kw)))
                rs = pd.DataFrame([grid2(H, D1, W1, sym, 1.0, m, "RANDOM", seed=s_, **kw) for s_ in range(50)])
                rows.append(dict(sym=sym, m=m, fix=fx, entries="RANDOM x50", **rs.mean(numeric_only=True).to_dict(), share_seeds_ruined=(rs.ruins > 0).mean()))
                log(f"{sym} m {m} {fx}")
                pd.DataFrame(rows).to_csv(OUT / "y5_grid_fix.csv", index=False)
    log("Y5 done")


if __name__ == "__main__":
    main()
