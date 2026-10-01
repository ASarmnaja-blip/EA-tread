"""Candle Lab decile curves for the report: for the most readable candle features, the mean next-bar return, the probability that the next bar is
up, and the mean 5-bar return by decile of the feature (thresholds from gold DEV per TF), for gold DEV 2009-15, gold CHECK 2016-26 and silver.
Writes data/candlelab/curves.json. Usage: python research/candlelab/curves.py"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L  # noqa: E402

FEATS = ["body_atr", "upwick_frac", "lowick_frac", "uld", "clv", "range_atr", "gap_atr", "run", "wickpress5", "path_tilt"]
TFS = ("M15", "H1", "H4", "D1", "W1")
OUTS = ("ret1", "next_up", "ret5", "next_range_atr")


def curves_for(bars, thr=None):
    out = {}
    for tf in TFS:
        X = bars[tf]; F = L.anatomy(X); O = L.outcomes(X)
        tg = pd.to_datetime(X.t, unit="s")
        per = {"DEV": (tg < "2016-01-01"), "CHECK": (tg >= "2016-01-01")}
        for f in FEATS:
            x = F[f].to_numpy(float)
            if f == "run":
                edges = np.array([-np.inf, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5, np.inf])
            else:
                if thr is None:
                    v = x[np.asarray(per["DEV"]) & np.isfinite(x)]
                    edges = np.unique(np.r_[-np.inf, np.quantile(v, np.linspace(0.1, 0.9, 9)), np.inf])
                else:
                    edges = thr[(tf, f)]
            out[(tf, f, "edges")] = edges
            b = np.digitize(x, edges[1:-1])
            for o in OUTS:
                y = O[o].to_numpy(float)
                for p, m in per.items():
                    m = np.asarray(m) & np.isfinite(x) & np.isfinite(y)
                    s = pd.Series(y[m]).groupby(b[m]).agg(["mean", "count"])
                    out[(tf, f, o, p)] = [(int(k), float(v), int(n)) for k, (v, n) in s.iterrows()]
    return out


def main():
    t0 = time.time()
    bg = L.base_gold(); cuts = L.cut_grid(bg["t"][-1])
    G = {tf: L.resample(bg, tf, cuts) for tf in TFS}
    cg = curves_for(G)
    thr = {(k[0], k[1]): v for k, v in cg.items() if k[2] == "edges"}
    bs = L.base_silver()
    S = {tf: L.resample(bs, tf, cuts) for tf in TFS}
    cs = curves_for(S, thr)
    res = {"gold": {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in cg.items() if k[2] != "edges"},
           "silver": {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in cs.items() if k[2] != "edges"},
           "edges": {f"{k[0]}|{k[1]}": [float(e) for e in v] for k, v in thr.items()}}
    (L.ROOT / "data" / "candlelab" / "curves.json").write_text(json.dumps(res))
    print(f"curves written ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
