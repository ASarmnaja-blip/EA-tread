"""Candle Lab analysis: what every candle feature is followed by, on every timeframe, for gold (DEV 2009-15, CHECK 2016-26) and silver (2010-26),
with a placebo (mirrored base series) to count how many "consistent" effects pure chance produces.
Effect of a feature on an outcome: top bucket mean minus bottom bucket mean (continuous: deciles with gold-DEV thresholds per TF; flags: 1 vs 0;
colour: up vs down; run: >= +3 vs <= -3), t with weekly clusters. Consistent = same sign in DEV, CHECK and SILVER with |t| >= 3 / 2 / 2.
Usage: python research/candlelab/analyze.py [placebo_paths]   -> data/candlelab/effects.csv, effects_placebo.csv, summary.txt"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L  # noqa: E402

OUT = L.ROOT / "data" / "candlelab"
TFS = ("M5", "M15", "H1", "H4", "D1", "W1")
HTF = {"M5": ("H1", "D1"), "M15": ("H1", "D1"), "H1": ("H4", "D1", "W1"), "H4": ("D1", "W1"), "D1": ("W1",), "W1": ()}
OUTS = ("ret1", "ret3", "ret5", "ret20", "next_up", "fp_up1", "mfe5", "mae5", "next_range_atr", "next_upwick_atr", "next_lowick_atr")
GOLD_PER = {"DEV": ("2009-01-01", "2016-01-01"), "CHECK": ("2016-01-01", "2026-10-01")}
FLAG_PREFIX = ("inside", "outside", "engulf", "pin_", "doji", "marubozu", "sweep_", "break_", "nr7", "wr7", "three_", "high_first")


def frame(base, cuts):
    bars = {tf: L.resample(base, tf, cuts) for tf in TFS}
    out = {}
    for tf in TFS:
        X = bars[tf]
        F = L.anatomy(X)
        for y in HTF[tf]:
            F = pd.concat([F, L.htf_context(X, bars[y], y.lower())], axis=1)
        O = L.outcomes(X)
        wk = np.searchsorted(cuts, X.t, side="left") - 1
        out[tf] = (X, F, O, wk)
    return out


def buckets(name, x, thr):
    """Returns (top_mask, bottom_mask) using thresholds fixed on gold DEV (thr = (q10, q90) or None for flags / categories)."""
    if name == "color":
        return x > 0, x < 0
    if name == "run":
        return x >= 3, x <= -3
    if name.startswith(FLAG_PREFIX):
        return x == 1, x == 0
    lo, hi = thr
    return x >= hi, x <= lo


def effect(y, top, bot, wk, mask):
    m = mask & np.isfinite(y)
    t_, b_ = m & top, m & bot
    nt, nb = int(t_.sum()), int(b_.sum())
    if nt < 30 or nb < 30:
        return np.nan, np.nan, nt, nb
    mt, mb = y[t_].mean(), y[b_].mean()
    w = wk[m]; wt = wk[t_]; wb = wk[b_]
    W = int(max(w.max(), 0)) + 1
    st = np.bincount(np.maximum(wt, 0), y[t_] - mt, W) / nt
    sb = np.bincount(np.maximum(wb, 0), y[b_] - mb, W) / nb
    se = np.sqrt(((st - sb) ** 2).sum())
    return float(mt - mb), float((mt - mb) / se) if se > 0 else np.nan, nt, nb


def effects_table(fr_gold, fr_silver, thresholds=None):
    rows = []
    thr_out = {}
    for tf in TFS:
        Xg, Fg, Og, wkg = fr_gold[tf]
        tg = pd.to_datetime(Xg.t, unit="s")
        masks = {p: np.asarray((tg >= a) & (tg < b)) for p, (a, b) in GOLD_PER.items()}
        sv = fr_silver.get(tf) if fr_silver else None
        for f in Fg.columns:
            x = Fg[f].to_numpy(float)
            if thresholds is None:
                v = x[masks["DEV"] & np.isfinite(x)]
                thr = tuple(np.quantile(v, [0.1, 0.9])) if len(v) > 100 else (np.nan, np.nan)
            else:
                thr = thresholds.get((tf, f), (np.nan, np.nan))
            thr_out[(tf, f)] = thr
            top, bot = buckets(f, x, thr)
            if sv is not None and f in sv[1].columns:
                xs = sv[1][f].to_numpy(float); top_s, bot_s = buckets(f, xs, thr)
            for o in OUTS:
                y = Og[o].to_numpy(float)
                r = dict(tf=tf, feature=f, outcome=o)
                for p, m in masks.items():
                    e, t, nt, nb = effect(y, top, bot, wkg, m)
                    r[f"{p}_eff"] = e; r[f"{p}_t"] = t; r[f"{p}_n"] = min(nt, nb)
                if sv is not None and f in sv[1].columns:
                    ys = sv[2][o].to_numpy(float)
                    e, t, nt, nb = effect(ys, top_s, bot_s, sv[3], np.ones(len(ys), bool))
                    r["SILVER_eff"] = e; r["SILVER_t"] = t; r["SILVER_n"] = min(nt, nb)
                rows.append(r)
    T = pd.DataFrame(rows)
    s = np.sign(T.DEV_eff)
    T["consistent_gold"] = (T.DEV_t.abs() >= 3) & (T.CHECK_t.abs() >= 2) & (np.sign(T.CHECK_eff) == s)
    if "SILVER_eff" in T:
        T["consistent_all"] = T.consistent_gold & (T.SILVER_t.abs() >= 2) & (np.sign(T.SILVER_eff) == s)
    return T, thr_out


def main():
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    bg = L.base_gold(); cuts = L.cut_grid(bg["t"][-1])
    fg = frame(bg, cuts); print(f"gold frames ({time.time() - t0:.0f}s)", flush=True)
    bs = L.base_silver(); fs = frame(bs, cuts); print(f"silver frames ({time.time() - t0:.0f}s)", flush=True)
    T, thr = effects_table(fg, fs)
    T.to_csv(OUT / "effects.csv", index=False)
    print(f"real: {len(T)} tests; consistent on gold DEV+CHECK: {int(T.consistent_gold.sum())}; also on silver: {int(T.consistent_all.sum())} ({time.time() - t0:.0f}s)", flush=True)
    del fs
    P = []
    for k in range(K):
        pb = L.mirror_base(bg, 1000 + k)
        fp = frame(pb, cuts)
        Tp, _ = effects_table(fp, None, thresholds=thr)
        Tp["path"] = k; P.append(Tp)
        print(f"placebo {k}: consistent on gold DEV+CHECK: {int(Tp.consistent_gold.sum())} ({time.time() - t0:.0f}s)", flush=True)
        del fp
    TP = pd.concat(P); TP.to_csv(OUT / "effects_placebo.csv", index=False)
    lines = [f"tests per run: {len(T)}", f"real consistent (gold DEV+CHECK): {int(T.consistent_gold.sum())}",
             f"real consistent (gold DEV+CHECK + silver): {int(T.consistent_all.sum())}",
             f"placebo consistent (gold DEV+CHECK), per path: {TP.groupby('path').consistent_gold.sum().tolist()}"]
    for tf in TFS:
        a = T[T.tf == tf]; b = TP[TP.tf == tf]
        lines.append(f"  {tf}: real {int(a.consistent_gold.sum())} (with silver {int(a.consistent_all.sum())}), placebo mean {b.groupby('path').consistent_gold.sum().mean():.1f}")
    (OUT / "summary.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
