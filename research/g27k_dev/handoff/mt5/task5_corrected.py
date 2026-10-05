"""Task 5 table recomputed after fixing the Fed-exit formula (2026-10-05): five Cent markets, G27K-F 1 % + brake 25 %, sleeves 0.5 %,
$100,000 from Sep 2011, as in TASK5_SWAP_BUG.md. Columns: as published; Cent spreads + 1 bp (swap as published); Cent spreads + 1 bp
with swap as today's points (case B, the correction TASK5 proposed); and the same with the research's case D for reference.

Usage: python task5_corrected.py
"""
import numpy as np
import pandas as pd

import cent4_capital as K
import cent4_costs as CC

CENT5 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY"]


def main():
    T = CC.load()
    now, y = CC.now_prices(T), CC.us2y()
    parts = []
    for b, x in T.items():
        x = x[x.market.isin(CENT5)].copy()
        fs = x.market.map(lambda m: (CC.CENT_BP[m] + 1.0) / CC.MODEL_BP[m]).to_numpy()
        x["R_pub"] = x.R
        x["R_cent"] = x.R - x.R_spread * (fs - 1)
        x["R_centB"] = x.R_cent - x.R_swap * (CC.swap_factor(x, now, y, "B") - 1)
        x["R_centD"] = x.R_cent - x.R_swap * (CC.swap_factor(x, now, y, "D") - 1)
        parts.append(x)
    D = pd.concat(parts, ignore_index=True).sort_values(["t", "market", "book"], kind="mergesort").reset_index(drop=True)
    cols = ["R_pub", "R_cent", "R_centB", "R_centD"]
    print("R per trade, five Cent markets:")
    for b, g in D.groupby("book"):
        print(f"  {b:4s} " + "  ".join(f"{c[2:]:6s} {g[c].mean():+.3f}" for c in cols))
    print("\naccounts, 1 % + brake 25 %, sleeves 0.5 %:")
    for name, books in (("F", ["F"]), ("F+M30", ["F", "M30"]), ("F+M30+H1", ["F", "M30", "H1"])):
        X = D[D.book.isin(books)]
        line = []
        for c in cols:
            a, _, _ = K.account(X, c, brake=True)
            line.append(f"{c[2:]:6s} {a['cagr']:.1%} DD {a['dd']:.1%} MAR {a['mar']:.2f}")
        print(f"  {name:9s} " + " | ".join(line))


if __name__ == "__main__":
    main()
