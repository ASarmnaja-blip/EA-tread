"""Operator 2026-10-01: what drawdown do the top three G27K setups by CAGR give when run together in one account?
The three (C8/D3, C1/D6, C8/D6, all E1/F1/G2/H2/I1/J1) on gold, silver and BTC, entries 2021-10..2026-09, each trade sized from the
realised balance; positions of different setups in the same market are allowed to overlap. Compares: each setup alone at 1 % per trade,
the three together at 1 % each, the three at 1/3 % each (same total risk as one), and setup 1 alone at 3 %. Equity marked at every
H4 close (report768.metrics)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

TOP3 = ["C8/D3/E1/F1/G2/H2/I1/J1", "C1/D6/E1/F1/G2/H2/I1/J1", "C8/D6/E1/F1/G2/H2/I1/J1"]


def trades_of(combo, Ms, Xs):
    Cc, D, E, F, Gs, H, I, J = combo.split("/"); out = []
    for m in K.MKTS:
        d = K.directions(Ms[m], Cc, D, E, J); idx = np.flatnonzero(d)
        out += [dict(tr, X=Xs[m], setup=combo) for tr in RP.sim_paths(Xs[m], m, idx, d[idx], "I1")]
    return out


def show(name, trades, risk, Xs):
    T = RP.timeline(trades, Xs); RP.prep_marks(trades, T)
    M = RP.metrics(RP.account(trades, risk), T, risk)
    print(f"{name:34s} trades {M['trades']:4d}  total {M['net'] / RP.DEPOSIT:+6.0%}  CAGR {M['cagr']:5.1%}  balance DD {M['balance_dd']['relative_pct']:5.1%}"
          f"  equity DD {M['equity_dd']['relative_pct']:5.1%}  max open {M['max_positions']:2d}  max leverage {M['max_leverage']:4.1f}x"
          f"  worst month {M['worst_month']:+.1%}  losing run {M['streaks']['max_losses']} ({M['streaks']['max_losses_usd']:,.0f})")
    return M


def main():
    ext = K.externals(); Ms, Xs = {}, {}
    for m in K.MKTS:
        h1 = G.load_h1(m); Ms[m] = K.prepare(m, h1, ext); Xs[m] = G.features(G.frames(h1), m, "H4"); Xs[m]["sec"] = 14400
    T3 = {c: trades_of(c, Ms, Xs) for c in TOP3}
    keys = {c: {(r["mkt"], r["t"]) for r in T3[c]} for c in TOP3}
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = keys[TOP3[i]], keys[TOP3[j]]
            print(f"same entries setup {i + 1} & {j + 1}: {len(a & b)} of {len(a)} / {len(b)}")
    for i, c in enumerate(TOP3):
        show(f"setup {i + 1} alone, 1 %", [dict(r) for r in T3[c]], 0.01, Xs)
    allt = [dict(r) for c in TOP3 for r in T3[c]]
    show("three together, 1 % each", allt, 0.01, Xs)
    show("three together, 0.33 % each", [dict(r) for r in allt], 0.01 / 3, Xs)
    show("setup 1 alone, 3 %", [dict(r) for r in T3[TOP3[0]]], 0.03, Xs)


if __name__ == "__main__":
    main()
