"""P05b (docs/plans/P05b_THREE_BAR_INVERTED.md): the three-bar setup traded in the opposite direction with the mirrored stop distance, next to the
original direction without the early-cut rule. Usage: python research/setups/p05b_inverted.py"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine_s as E  # noqa: E402
import plans_gen as G  # noqa: E402
import run_plans as RP  # noqa: E402


def gen(B, mkt, tf):
    O = G.gen_P05(B, mkt, tf)["main"].reset_index(drop=True)
    c = B.c[O.s.to_numpy()]; dist = np.abs(c - O.sl.to_numpy()); d = O.d.to_numpy()
    orig = E.orders(O.s, d, c - d * dist, c + d * dist)
    inv = E.orders(O.s, -d, c + d * dist, c - d * dist)
    return {"original 1:1 no cut": orig, "inverted 1:1": inv}


def main():
    tfs = {tf: RP.ALL for tf in ("M5", "M15", "M30", "H1", "H4", "D1")}
    D = RP.run_one("P05b", gen, tfs, modes=("tp", "unc"))
    D.to_csv(E.OUT / "P05b_rows.csv", index=False)
    V = E.verdict(D); V.to_csv(E.OUT / "P05b_verdict.csv", index=False)
    pd.set_option("display.width", 250)
    print(V[["tf", "variant", "exit", "n_check", "win_check", "R_check", "excess", "p_holm", "R_dev", "R_silver", "share_markets_pos", "median_market_R", "PASS"]]
          .round(3).to_string(index=False))
    g = D[(D.mkt == "XAUUSD") & (D["sample"] == "CHECK")]
    print("\ngold CHECK gross vs net R:"); print(g.pivot_table(index=["tf", "exit"], columns="variant", values=["gR", "R"]).round(3).to_string())


if __name__ == "__main__":
    main()
