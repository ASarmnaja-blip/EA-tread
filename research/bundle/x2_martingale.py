"""X2 of docs/BUNDLE_2026-10-01_PREREG.md: martingale, RESEARCH ONLY (CLAUDE.md section 8 and data/DEMO_ORDER_PERMISSION.md keep martingale,
grid and averaging forbidden for every demo or real order). Measures what the sizing does to risk; it cannot create expectancy.
  M-SEQ  : dollar risk x m after a loss, reset to 1 % of equity after a win (m = 1.5, 2); all-in when the required risk exceeds equity.
  M-ANTI : x 2 after a win, reset after a loss.
  FLAT   : 1 % of equity per trade (reference).
  Applied to the one-position trend trades of X1 (gold, silver; H4, D1; S1 / S2 / CH; long-only and long+short) and to random-entry
  trades with the same exits (200 seeds, trade count matched).
  M-GRID : averaging grid on gold and silver H1 (first order 20 % of equity notional, add x m every S against, close all at the
  weighted average + 0.5 S, no stop, leverage 1:200, ruin = equity <= 0, then a fresh $10,000 account).
Usage: python research/bundle/x2_martingale.py"""
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
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
RUIN_EQ = 100.0                                   # an account below $100 (1 % of the start) is ruined


def run_sizing(R, t_exit, scheme, m=2.0, base=0.01):
    """Sizing scheme over a sequence of trade results R (in R units, time order). Returns ruins, years to first ruin, end equity of the
    last account, CAGR of the whole history counting every ruin as a loss of $10,000 (fresh capital injected), max drawdown."""
    eq = 10_000.0; peak = eq; dd = 0.0; ruins = 0; first_ruin = None; streak = 0; unit = base * eq; injected = 10_000.0
    t_first = t_exit[0] if len(t_exit) else 0
    for i in range(len(R)):
        if scheme == "FLAT":
            risk = base * eq
        else:
            risk = unit * (m ** streak)
        risk = min(risk, eq)
        eq += risk * R[i]
        win = R[i] > 0
        if scheme == "M-SEQ":
            streak = 0 if win else streak + 1
        elif scheme == "M-ANTI":
            streak = streak + 1 if win else 0
        if streak == 0:
            unit = base * max(eq, 0)
        peak = max(peak, eq); dd = max(dd, 1 - eq / peak if peak > 0 else 1)
        if eq <= RUIN_EQ:
            ruins += 1
            if first_ruin is None:
                first_ruin = (t_exit[i] - t_first) / (365.25 * 86400)
            eq = 10_000.0; peak = eq; streak = 0; unit = base * eq; injected += 10_000.0
    yrs = max((t_exit[-1] - t_first) / (365.25 * 86400), 0.1) if len(R) else 1
    return dict(ruins=ruins, first_ruin_yrs=first_ruin, end_eq=eq, injected=injected, net_multiple=eq / injected,
                cagr_net=(max(eq, 1) / injected) ** (1 / yrs) - 1, dd_last_life=dd)


def random_sequences(B, sym, system, n_trades, mean_hold, sides, seeds, a, b):
    """Random-entry trades with the system's exit: every bar's trade in both directions is simulated once; a sequence walks forward with
    geometric waiting times matched to the system's trade count, direction by coin flip (long only if sides == 'long')."""
    entry_n, ex = C.SYSTEMS[system]
    N = L.atr(B.h, B.l, B.c, 20)
    idx = np.flatnonzero((B.t >= C.ts(a)) & (B.t < C.ts(b)) & np.isfinite(N))
    TL = C.simulate(B, idx, np.ones(len(idx), int), 2 * N[idx], ex, sym).set_index("s")
    TS = C.simulate(B, idx, -np.ones(len(idx), int), 2 * N[idx], ex, sym).set_index("s") if sides == "both" else None
    span = len(idx)
    gap = max(1.0, (span - n_trades * mean_hold) / max(n_trades, 1))
    out = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        k = idx[0] + int(rng.geometric(1 / gap)); R, tx = [], []
        while k < idx[-1]:
            T = TL if (sides == "long" or rng.random() < 0.5) else TS
            if k not in T.index:
                k += 1; continue
            r = T.loc[k]
            R.append(r.R); tx.append(r.t_exit)
            k = int(r.xf) + int(rng.geometric(1 / gap))
        out.append((np.array(R), np.array(tx)))
    return out


def grid(B, D1, sym, S_mult, m, rule, seed=0, lev=200.0, first_frac=0.20):
    """Averaging grid on H1 bars. Returns ruins, first ruin (years), cycles, cycles won share, max adds, max floating drawdown, the end
    equity and CAGR of the whole history counting each ruin as a lost $10,000."""
    t, o, h, l, c = B.t, B.o, B.h, B.l, B.c
    half = C.cost_rt_bp(sym) / 2 / 1e4
    swl = C.K.swap_bp(sym, t, t + 3600, np.ones(len(t))) / 1e4               # long swap per H1 bar (non-zero on rollover bars)
    d1c = D1.t + 86400
    j = np.searchsorted(d1c, t, side="right") - 1                                # last completed D1 bar at each H1 open
    A22 = L.atr(D1.h, D1.l, D1.c, 22)
    mid = (pd.Series(D1.h).rolling(55).max() + pd.Series(D1.l).rolling(55).min()).to_numpy() / 2
    atr_at = np.where(j >= 0, A22[np.maximum(j, 0)], np.nan); trend_at = np.nan_to_num(np.where(j >= 0, np.sign(D1.c[np.maximum(j, 0)] - mid[np.maximum(j, 0)]), 0), nan=0.0)
    rng = np.random.default_rng(seed)
    eq_bal = 10_000.0; injected = 10_000.0; ruins = 0; first_ruin = None
    orders = []; D = 0; S = 0.0; cycles = 0; won = 0; max_adds = 0; maxdd = 0.0; peak = eq_bal
    i = 0; n = len(t)
    while i < n:
        if not orders:
            if not np.isfinite(atr_at[i]) or atr_at[i] <= 0:
                i += 1; continue
            D = {"LONG": 1, "SHORT": -1, "TREND": int(trend_at[i]) or 1}.get(rule) or (1 if rng.random() < 0.5 else -1)
            S = S_mult * atr_at[i]
            notion = first_frac * eq_bal
            orders = [(o[i], notion)]; eq_bal -= notion * half; cycles += 1
        # adverse extreme first: adds, then the stop-out test at the extreme
        adv = l[i] if D > 0 else h[i]
        while True:
            last_px = orders[-1][0]
            lvl = last_px - D * S
            if (D > 0 and adv <= lvl) or (D < 0 and adv >= lvl):
                notion = orders[-1][1] * m
                used = sum(q for _, q in orders) / lev
                flo = sum(q * D * (lvl / p - 1) for p, q in orders)
                if (eq_bal + flo - used) >= notion / lev:
                    orders.append((lvl, notion)); eq_bal -= notion * half
                    max_adds = max(max_adds, len(orders) - 1)
                    continue
            break
        flo_adv = sum(q * D * (adv / p - 1) for p, q in orders)
        if eq_bal + flo_adv <= 0:
            ruins += 1
            if first_ruin is None:
                first_ruin = (t[i] - t[0]) / (365.25 * 86400)
            eq_bal = 10_000.0; injected += 10_000.0; orders = []; peak = eq_bal; i += 1; continue
        maxdd = max(maxdd, 1 - (eq_bal + flo_adv) / peak)
        tot = sum(q for _, q in orders); avg = tot / sum(q / p for p, q in orders)
        tp = avg + D * 0.5 * S
        fav = h[i] if D > 0 else l[i]
        if (D > 0 and fav >= tp) or (D < 0 and fav <= tp):
            eq_bal += sum(q * D * (tp / p - 1) for p, q in orders) - tot * half
            orders = []; won += 1; peak = max(peak, eq_bal)
            i += 1; continue
        if D > 0:
            eq_bal -= tot * swl[i]
        i += 1
    if orders:
        eq_bal += sum(q * D * (c[-1] / p - 1) for p, q in orders) - sum(q for _, q in orders) * half
    yrs = (t[-1] - t[0]) / (365.25 * 86400)
    return dict(ruins=ruins, first_ruin_yrs=first_ruin, cycles=cycles, won_share=won / max(cycles, 1), max_adds=max_adds, max_float_dd=maxdd,
                end_eq=eq_bal, injected=injected, cagr_net=(max(eq_bal, 1) / injected) ** (1 / yrs) - 1)


def main():
    rows = []
    for sym in C.METALS:
        a, b = ("2009-01-01", "2026-10-01") if sym == "XAUUSD" else ("2010-01-01", "2026-10-01")
        for tf in ("H4", "D1"):
            B = C.bars(sym, tf)
            T = C.load(f"x1_trades_{sym}_{tf}.pkl")
            T = T[(T.t >= C.ts(a)) & (T.t < C.ts(b))]
            for system in C.SYSTEMS:
                for sides in ("long", "both"):
                    g = T[(T.system == system) & (T.d > 0)] if sides == "long" else T[T.system == system]
                    g = g[g.taken.to_numpy()] if sides == "long" else g[g.taken_ls.to_numpy()]
                    g = g.sort_values("t")
                    R, tx = g.R.to_numpy(), g.t_exit.to_numpy()
                    for scheme, mm in (("FLAT", 1.0), ("M-SEQ", 1.5), ("M-SEQ", 2.0), ("M-ANTI", 2.0)):
                        r = run_sizing(R, tx, scheme, mm)
                        rows.append(dict(part="trend", sym=sym, tf=tf, system=system, sides=sides, scheme=scheme, m=mm, entries="system", n=len(R),
                                         R_mean=R.mean() if len(R) else np.nan, **r))
                    seqs = random_sequences(B, sym, system, len(R), g.bars.mean() if len(g) else 1, sides, range(200), a, b)
                    for scheme, mm in (("FLAT", 1.0), ("M-SEQ", 1.5), ("M-SEQ", 2.0), ("M-ANTI", 2.0)):
                        rs = pd.DataFrame([run_sizing(Rr, txr, scheme, mm) for Rr, txr in seqs if len(Rr)])
                        rows.append(dict(part="trend", sym=sym, tf=tf, system=system, sides=sides, scheme=scheme, m=mm, entries="random x200",
                                         n=float(np.mean([len(x[0]) for x in seqs])), R_mean=float(np.mean([x[0].mean() for x in seqs if len(x[0])])),
                                         ruins=rs.ruins.mean(), first_ruin_yrs=rs.first_ruin_yrs.median(), end_eq=rs.end_eq.median(),
                                         injected=rs.injected.mean(), net_multiple=rs.net_multiple.median(), cagr_net=rs.cagr_net.median(),
                                         dd_last_life=rs.dd_last_life.median(), share_seeds_ruined=(rs.ruins > 0).mean()))
                    log(f"{sym} {tf} {system} {sides}")
        pd.DataFrame(rows).to_csv(C.OUT / "x2_martingale.csv", index=False)
        H1 = C.bars(sym, "H1"); D1 = C.bars(sym, "D1")
        msk = (H1.t >= C.ts(a)) & (H1.t < C.ts(b))
        H1s = L.Bars(tf="H1", t=H1.t[msk], o=H1.o[msk], h=H1.h[msk], l=H1.l[msk], c=H1.c[msk])
        for S_mult in (0.5, 1.0, 2.0):
            for m in (1.0, 1.5, 2.0):
                for rule in ("LONG", "SHORT", "TREND"):
                    r = grid(H1s, D1, sym, S_mult, m, rule)
                    rows.append(dict(part="grid", sym=sym, tf="H1", scheme="M-GRID", m=m, S_atr=S_mult, entries=rule, **r))
                rs = pd.DataFrame([grid(H1s, D1, sym, S_mult, m, "RANDOM", seed) for seed in range(100)])
                rows.append(dict(part="grid", sym=sym, tf="H1", scheme="M-GRID", m=m, S_atr=S_mult, entries="RANDOM x100", ruins=rs.ruins.mean(),
                                 first_ruin_yrs=rs.first_ruin_yrs.median(), cycles=rs.cycles.mean(), won_share=rs.won_share.mean(),
                                 max_adds=rs.max_adds.max(), max_float_dd=rs.max_float_dd.median(), end_eq=rs.end_eq.median(),
                                 injected=rs.injected.mean(), cagr_net=rs.cagr_net.median(), share_seeds_ruined=(rs.ruins > 0).mean()))
                log(f"grid {sym} S {S_mult} m {m}")
                pd.DataFrame(rows).to_csv(C.OUT / "x2_martingale.csv", index=False)
    log("X2 done")


if __name__ == "__main__":
    main()
