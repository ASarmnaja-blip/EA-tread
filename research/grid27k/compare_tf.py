"""G27K on H1, H4 and D1 (same 27,648 setups, gold + silver + BTC): best setups per timeframe with their 2017-21 results, dimension
effects, and how the H4 winners do on the other timeframes. Five-year window 2021-10..2026-09; early window 2017-01..2021-09."""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[2] / "data" / "grid27k"
MIN_N = {"H1": 150, "H4": 100, "D1": 30}


def load(tf):
    sfx = "" if tf == "H4" else f"_{tf}"
    R = pd.read_csv(OUT / f"g27k_real{sfx}.csv").set_index("combo"); E = pd.read_csv(OUT / f"g27k_early{sfx}.csv").set_index("combo")
    return R.join(E[["n", "pf", "cagr", "dd", "totR"]], rsuffix="_e")


def main():
    T = {tf: load(tf) for tf in ("H1", "H4", "D1")}
    for tf, J in T.items():
        ok = J[J.n >= MIN_N[tf]]
        print(f"\n=== {tf}: setups {len(J)}, with n >= {MIN_N[tf]}: {len(ok)}; positive 5y {(ok.totR > 0).mean():.0%}; median CAGR {ok.cagr.median():.1%};"
              f" median early CAGR {ok.cagr_e.median():.1%}; rank corr 5y vs early CAGR {ok[['cagr', 'cagr_e']].corr(method='spearman').iloc[0, 1]:.2f}")
        top = ok.nlargest(8, "cagr")
        print(top[["n", "win", "pf", "cagr", "dd", "n_e", "pf_e", "cagr_e", "dd_e"]].round(3).to_string())
        ok = ok.assign(mar=ok.cagr / ok.dd, mar_e=ok.cagr_e / ok.dd_e)
        both = ok[(ok.cagr_e > 0)].nlargest(5, "mar")
        print(" best 5y MAR among setups positive in 2017-21:"); print(both[["n", "pf", "cagr", "dd", "pf_e", "cagr_e", "dd_e"]].round(3).to_string())
        for dim in ("C", "D", "H", "I", "J"):
            print(f"  median CAGR by {dim}:", ok.groupby(dim).cagr.median().round(3).to_dict())
    h4top = T["H4"][T["H4"].n >= 100].nlargest(10, "cagr").index
    print("\nH4 top 10 by CAGR on the other timeframes (5y CAGR / DD | early CAGR):")
    for c in h4top:
        print("  " + c + ": " + " | ".join(f"{tf} {T[tf].loc[c, 'cagr']:+.1%}/{T[tf].loc[c, 'dd']:.0%} early {T[tf].loc[c, 'cagr_e']:+.1%}" for tf in ("H1", "H4", "D1")))


if __name__ == "__main__":
    main()
