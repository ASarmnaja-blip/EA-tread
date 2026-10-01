"""Candle Lab figures from data/candlelab/curves.json: decile curves of the next-bar return (ret1), the 5-bar return (ret5) and the next bar's
range, per feature (rows) and timeframe (columns), gold DEV 2009-15 / gold CHECK 2016-26 / silver, with the round-trip cost band (a long in a
bucket pays only if its curve is above +cost, a short only if below -cost). Usage: python research/candlelab/plot_curves.py"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "candlelab"
COST_ATR = {"M15": 0.13, "H1": 0.07, "H4": 0.035, "D1": 0.017, "W1": 0.008}     # round trip, in ATR of the timeframe (gold, C4 + swap)
TFS = ("M15", "H1", "H4", "D1", "W1")
FEATS = ["body_atr", "upwick_frac", "lowick_frac", "clv", "range_atr", "gap_atr", "run", "wickpress5", "path_tilt", "uld"]
LBL = {"body_atr": "body / ATR (signed)", "upwick_frac": "upper wick / range", "lowick_frac": "lower wick / range", "clv": "close location in range",
       "range_atr": "range / ATR", "gap_atr": "open gap / ATR", "run": "same-colour run", "wickpress5": "wick pressure, 5 bars",
       "path_tilt": "high-first vs low-first", "uld": "upper minus lower wick"}


def fig(J, out, title, cost):
    fig_, ax = plt.subplots(len(FEATS), len(TFS), figsize=(3.0 * len(TFS), 2.0 * len(FEATS)), squeeze=False)
    for i, f in enumerate(FEATS):
        for j, tf in enumerate(TFS):
            a = ax[i, j]
            for src, per, col, lab in (("gold", "DEV", "#b8860b", "gold 2009-15"), ("gold", "CHECK", "#d62728", "gold 2016-26"),
                                       ("silver", "DEV", "#7f7f7f", "silver")):
                key = f"{tf}|{f}|{out}|{per}"
                pts = J[src].get(key)
                if src == "silver":                                         # silver has no DEV split: merge both periods
                    p2 = {k: (v, n) for k, v, n in (J[src].get(f"{tf}|{f}|{out}|DEV") or [])}
                    for k, v, n in (J[src].get(f"{tf}|{f}|{out}|CHECK") or []):
                        v0, n0 = p2.get(k, (0.0, 0))
                        p2[k] = ((v0 * n0 + v * n) / (n0 + n), n0 + n)
                    pts = [(k, v, n) for k, (v, n) in sorted(p2.items())]
                if not pts:
                    continue
                a.plot([p[0] for p in pts], [p[1] for p in pts], "-o", ms=2.5, lw=1.2, color=col, label=lab)
            if cost:
                c = COST_ATR[tf]
                a.axhspan(-c, c, color="#1f77b4", alpha=0.10, lw=0)
            a.axhline(0, color="k", lw=0.5)
            a.tick_params(labelsize=6)
            if i == 0:
                a.set_title(tf, fontsize=9)
            if j == 0:
                a.set_ylabel(LBL[f], fontsize=7)
            if i == len(FEATS) - 1:
                a.set_xlabel("bucket (low -> high)", fontsize=6)
    ax[0, 0].legend(fontsize=6, loc="best")
    fig_.suptitle(title, fontsize=11)
    fig_.tight_layout(rect=(0, 0, 1, 0.98))
    p = D / f"fig_{out}.png"
    fig_.savefig(p, dpi=110)
    plt.close(fig_)
    return p


def main():
    J = json.loads((D / "curves.json").read_text())
    for out, title, cost in (("ret1", "Next-bar return (open to close of bar t+1, in ATR) by bucket of the candle feature at bar t; blue band = round-trip cost", True),
                             ("ret5", "5-bar return after the candle (in ATR); blue band = round-trip cost", True),
                             ("next_up", "Probability that the next bar closes up", False),
                             ("next_range_atr", "Size of the next bar (range / ATR): volatility, not direction", False)):
        print(fig(J, out, title, cost))


if __name__ == "__main__":
    main()
