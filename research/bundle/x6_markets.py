"""X6 of docs/BUNDLE_2026-10-01_PREREG.md: the ten-market trend portfolio (gold, silver + the original 8 MT5 markets) re-run WITH each
market's broker swap (MT5 symbol_info, current specification applied to the whole history: an assumption) next to the no-swap figures;
the 8 untouched cached markets reported separately. One position per market and system (TAKEN trades of X1), every market at 1 % risk
per trade on one shared $10,000 account, D1, 2016-08-01 .. 2026-10-01. Usage: python research/bundle/x6_markets.py"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

A, B = "2016-08-01", "2026-10-01"


def trades(sym, system, sides):
    T = C.load(f"x1_trades_{sym}_D1.pkl")
    g = T[T.system == system]
    g = g[(g.d > 0) & g.taken] if sides == "long" else g[g.taken_ls]
    g = g[(g.t >= C.ts(A)) & (g.t < C.ts(B))].copy()
    risk_bp = g.risk / g.ep * 1e4
    g["R_noswap"] = g.gR - g.cost_bp / risk_bp
    g["mkt"] = sym
    return g


def main():
    rows = []
    groups = {"10 markets": C.METALS + C.ORIG8, "10 markets without BTC": C.METALS + tuple(m for m in C.ORIG8 if m != "BTCUSD"),
              "8 untouched markets": C.NEW8, "8 untouched without USDINR": tuple(m for m in C.NEW8 if m != "USDINR"),
              "all 18": C.METALS + C.ORIG8 + C.NEW8}
    for system in C.SYSTEMS:
        for sides in ("long", "both"):
            per = {m: trades(m, system, sides) for m in C.METALS + C.ORIG8 + C.NEW8}
            for m, g in per.items():
                for col, lab in (("R", "with swap"), ("R_noswap", "no swap")):
                    r = C.equity(g.assign(R=g[col]), 0.01, A, B)
                    rows.append(dict(level="market", name=m, system=system, sides=sides, swap=lab, avg_R=g[col].mean(), swap_R=(g.R_noswap - g.R).mean(), **r))
            for nm, mk in groups.items():
                G = pd.concat([per[m] for m in mk])
                for col, lab in (("R", "with swap"), ("R_noswap", "no swap")):
                    r = C.equity(G.assign(R=G[col]), 0.01, A, B)
                    rows.append(dict(level="portfolio", name=nm, system=system, sides=sides, swap=lab, avg_R=G[col].mean(), swap_R=(G.R_noswap - G.R).mean(), **r))
    D = pd.DataFrame(rows)
    D.to_csv(C.OUT / "x6_markets.csv", index=False)
    pd.set_option("display.width", 250)
    P = D[(D.level == "portfolio") & (D.system == "CH") & (D.sides == "long")]
    print(P[["name", "swap", "n", "avg_R", "swap_R", "cagr", "dd", "max_open", "pos_years"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
