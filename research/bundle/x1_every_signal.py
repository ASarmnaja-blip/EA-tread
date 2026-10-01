"""X1 of docs/BUNDLE_2026-10-01_PREREG.md: every-signal autopsy and stacking. Every channel-breakout bar of Turtle S1 / S2 / Chandelier is
its own uncapped trade (overlaps allowed) on gold and silver M5..W1 and on 16 MT5 markets (D1, H1); TAKEN / SKIPPED flags against the
one-position system; per-trade path and candle anatomy at the signal bar; AUC of every feature for winners vs losers (gold DEV, gold
CHECK, silver); stacking portfolios P0 / P1 / P2 at 0.25 / 0.5 / 1 % risk. Usage: python research/bundle/x1_every_signal.py"""
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
HTF = {"M5": ("H1", "D1"), "M15": ("H1", "D1"), "H1": ("H4", "D1", "W1"), "H4": ("D1", "W1"), "D1": ("W1",), "W1": ()}
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def features(B, sym):
    F = L.anatomy(B)
    for y in HTF[B.tf]:
        F = pd.concat([F, L.htf_context(B, C.bars(sym, y), y.lower())], axis=1)
    win = {"M5": 12 * 24 * 250, "M15": 4 * 24 * 250, "H1": 24 * 250, "H4": 6 * 250, "D1": 250, "W1": 52}[B.tf]
    F["atr_pct_1y"] = pd.Series(B.atr).rolling(win, min_periods=min(win, 100)).rank(pct=True).to_numpy()
    F["ret20_atr"] = (B.c - np.r_[np.full(20, np.nan), B.c[:-20]]) / B.atr
    return F.astype(np.float32)


def period_masks(sym, t):
    if sym == "XAUUSD":
        return {"DEV": (t >= C.ts(C.GOLD_DEV[0])) & (t < C.ts(C.GOLD_DEV[1])), "CHECK": (t >= C.ts(C.GOLD_CHECK[0])) & (t < C.ts(C.GOLD_CHECK[1]))}
    return {"ALL": np.ones(len(t), bool)}


def summarise(T, sym, tf, rows):
    for (system, side), g in T.groupby(["system", "d"]):
        for p, m in period_masks(sym, g.t.to_numpy()).items():
            x = g[m]
            if not len(x):
                continue
            tk = x.taken.to_numpy()
            big = x[tk & (x.R >= 3)].R.sum(); tot = x[tk].R.sum()
            rows.append(dict(sym=sym, tf=tf, system=system, side="long" if side > 0 else "short", period=p, n_all=len(x), R_all=x.R.mean(),
                             gR_all=x.gR.mean(), win_all=(x.R > 0).mean(), n_taken=int(tk.sum()), R_taken=x.R[tk].mean() if tk.any() else np.nan,
                             n_skip=int((~tk).sum()), R_skip=x.R[~tk].mean() if (~tk).any() else np.nan,
                             R_taken_LS=x.R[x.taken_ls.to_numpy()].mean() if x.taken_ls.any() else np.nan,
                             share_R_from_3R=big / tot if tot != 0 else np.nan, bars=x.bars.mean(), mfe=x.mfe_R.mean(),
                             losers_never_half_R=(x[x.R <= 0].mfe_R < 0.5).mean(), plus1_first=x.plus1_first.mean(),
                             winners_mae_before_best=x[x.R > 0].mae_before_best_R.mean(), open_end=int(x.open_end.sum())))


def auc_fast(score, y):
    m = np.isfinite(score)
    s, yy = score[m], y[m]
    npos = int(yy.sum()); nneg = len(yy) - npos
    if npos < 20 or nneg < 20:
        return np.nan
    r = pd.Series(s).rank().to_numpy()
    return (r[yy == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def main():
    rows, aucs, stack = [], [], []
    for sym in C.METALS:
        for tf in C.TFS:
            B = C.bars(sym, tf)
            F = features(B, sym)
            parts = []
            for system in C.SYSTEMS:
                for side in (1, -1):
                    T = C.trend_trades(B, sym, system, side)
                    T["taken"] = C.one_position(T)
                    parts.append(T)
                both = pd.concat(parts[-2:], ignore_index=True)
                both["taken_ls"] = C.one_position(both)
                parts[-2] = both[both.d > 0].copy(); parts[-1] = both[both.d < 0].copy()
            T = pd.concat(parts, ignore_index=True)
            T = pd.concat([T.reset_index(drop=True), F.iloc[T.s.to_numpy()].reset_index(drop=True)], axis=1)
            C.save(T, f"x1_trades_{sym}_{tf}.pkl")
            summarise(T, sym, tf, rows)
            y = (T.R.to_numpy() > 0).astype(int)
            for (system, side), g in T.groupby(["system", "d"]):
                for p, m in period_masks(sym, g.t.to_numpy()).items():
                    gg = g[m]; yy = (gg.R.to_numpy() > 0).astype(int)
                    for f in F.columns:
                        aucs.append(dict(sym=sym, tf=tf, system=system, side=int(side), period=p, feature=f, auc=auc_fast(gg[f].to_numpy(float), yy), n=len(gg)))
            if tf in ("H1", "H4", "D1"):
                for system in C.SYSTEMS:
                    for sideset in ("long", "both"):
                        g = T[(T.system == system) & ((T.d > 0) if sideset == "long" else True)]
                        flag = g.taken if sideset == "long" else g.taken_ls
                        pers = {"ALL": (None, None)} if sym == "XAGUSD" else {"ALL": ("2009-01-01", "2026-10-01"), "CHECK": C.GOLD_CHECK}
                        for p, (a, b) in pers.items():
                            for risk in (0.0025, 0.005, 0.01):
                                for mode, sub, how in (("P0 one", g[flag.to_numpy()], "all"), ("P1 stack all", g, "all"), ("P2 stack winners", g, "winners")):
                                    r = C.equity(sub, risk, a, b, how, B.c)
                                    stack.append(dict(sym=sym, tf=tf, system=system, sides=sideset, period=p, risk=risk, mode=mode, **r))
            log(f"{sym} {tf}: {len(T)} trades")
            del T, F, parts
        pd.DataFrame(rows).to_csv(C.OUT / "x1_summary.csv", index=False)
    for sym in C.ORIG8 + C.NEW8:
        for tf in ("D1", "H1"):
            B = C.bars(sym, tf)
            parts = []
            for system in C.SYSTEMS:
                for side in (1, -1):
                    T = C.trend_trades(B, sym, system, side); T["taken"] = C.one_position(T); parts.append(T)
                both = pd.concat(parts[-2:], ignore_index=True); both["taken_ls"] = C.one_position(both)
                parts[-2] = both[both.d > 0].copy(); parts[-1] = both[both.d < 0].copy()
            T = pd.concat(parts, ignore_index=True)
            C.save(T, f"x1_trades_{sym}_{tf}.pkl")
            summarise(T, sym, tf, rows)
        log(f"{sym} done")
    pd.DataFrame(rows).to_csv(C.OUT / "x1_summary.csv", index=False)
    pd.DataFrame(aucs).to_csv(C.OUT / "x1_auc.csv", index=False)
    pd.DataFrame(stack).to_csv(C.OUT / "x1_stacking.csv", index=False)
    log("X1 done")


if __name__ == "__main__":
    main()
