"""X8 (descriptive, after the bundle): which entry conditions win or lose in EVERY sample. On the X1 every-signal trend trades of gold and silver
(S1 / S2 / Chandelier pooled per timeframe and side), each candle / higher-TF feature is cut into deciles (gold DEV thresholds; flags and
categories by value; entry hour in 4-hour blocks; weekday). For every cell: net R per trade in gold DEV 2009-15, gold CHECK 2016-26, silver,
and gold 2012-10..2015-12 (the bear phase). Chance benchmark: with no information, the excess over the sample's own mean has the same sign in
all three main samples for 25 % of cells. Usage: python research/bundle/x8_consistency_scan.py"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

CAT = {"color", "run", "high_first"}
FLAGS = ("inside", "outside", "engulf", "pin_", "doji", "marubozu", "sweep_", "break_", "nr7", "wr7", "three_")


def cells(T, f, edges):
    x = T[f].to_numpy(float)
    if f in ("hour",):
        return (x // 4).astype(int), [f"{int(k) * 4:02d}-{int(k) * 4 + 4:02d}h" for k in range(6)]
    if f in ("weekday",) or f in CAT or f.startswith(FLAGS):
        v = np.clip(x, -4, 4) if f == "run" else x
        return np.where(np.isfinite(v), v, -99).astype(int), None
    b = np.searchsorted(edges, x, side="right") - 1
    return np.where(np.isfinite(x), np.clip(b, 0, len(edges) - 2), -99), None


def main():
    rows = []
    for tf in C.TFS:
        G = C.load(f"x1_trades_XAUUSD_{tf}.pkl"); S = C.load(f"x1_trades_XAGUSD_{tf}.pkl")
        for X in (G, S):
            X["hour"] = (X.t // 3600) % 24
            X["weekday"] = ((X.t // 86400) + 3) % 7
        feats = [c for c in G.columns if G[c].dtype == np.float32] + ["hour", "weekday"]
        samples = {"gold_DEV": (G, (G.t >= C.ts("2009-01-01")) & (G.t < C.ts("2016-01-01"))),
                   "gold_CHECK": (G, G.t >= C.ts("2016-01-01")),
                   "silver": (S, np.ones(len(S), bool)),
                   "gold_BEAR": (G, (G.t >= C.ts("2012-10-01")) & (G.t < C.ts("2016-01-01")))}
        for side in (1, -1):
            base = {k: X[m & (X.d == side)].R.mean() for k, (X, m) in samples.items()}
            dev = G[samples["gold_DEV"][1] & (G.d == side)]
            for f in feats:
                v = dev[f].to_numpy(float); v = v[np.isfinite(v)]
                edges = np.unique(np.quantile(v, np.linspace(0, 1, 11))) if len(v) > 200 else np.array([-np.inf, np.inf])
                edges[0], edges[-1] = -np.inf, np.inf
                stats = {}
                for k, (X, m) in samples.items():
                    x = X[m & (X.d == side)]
                    b, _ = cells(x, f, edges)
                    g = pd.DataFrame(dict(b=b, R=x.R.to_numpy())).groupby("b").R.agg(["mean", "size"])
                    stats[k] = g
                keys = sorted(set().union(*[set(s.index) for s in stats.values()]) - {-99})
                for kk in keys:
                    r = dict(tf=tf, side="long" if side > 0 else "short", feature=f, cell=int(kk),
                             lo=float(edges[kk]) if f not in CAT and f not in ("hour", "weekday") and not f.startswith(FLAGS) and kk < len(edges) - 1 else np.nan,
                             hi=float(edges[kk + 1]) if f not in CAT and f not in ("hour", "weekday") and not f.startswith(FLAGS) and kk + 1 < len(edges) else np.nan)
                    for k, s in stats.items():
                        r[f"R_{k}"] = float(s["mean"].get(kk, np.nan)); r[f"n_{k}"] = int(s["size"].get(kk, 0)); r[f"base_{k}"] = base[k]
                    rows.append(r)
        print(tf, "done", flush=True)
    D = pd.DataFrame(rows)
    D.to_csv(C.OUT / "x8_consistency.csv", index=False)
    main3 = ["gold_DEV", "gold_CHECK", "silver"]
    ok = np.all([D[f"n_{k}"] >= 100 for k in main3], axis=0)
    E = D[ok].copy()
    for k in main3:
        E[f"ex_{k}"] = E[f"R_{k}"] - E[f"base_{k}"]
    sg = np.sign(E[[f"ex_{k}" for k in main3]].to_numpy())
    E["same_sign"] = (sg == sg[:, [0]]).all(1)
    big = (E[[f"ex_{k}" for k in main3]].abs() >= 0.05).all(1)
    print(f"\ncells with >= 100 trades in each sample: {len(E)}; excess same sign in all three: {E.same_sign.mean():.1%} (chance 25 %); "
          f"same sign and |excess| >= 0.05 R everywhere: {(E.same_sign & big).mean():.1%}")
    print("by tf:", E.groupby("tf").same_sign.mean().round(3).to_dict())
    E.to_csv(C.OUT / "x8_consistency_cells.csv", index=False)


if __name__ == "__main__":
    main()
