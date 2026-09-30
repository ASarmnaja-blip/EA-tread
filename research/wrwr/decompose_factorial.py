"""Codex R19-8: clean decomposition of BASE (52w LCB z1, H1 pool, m 2, causal vol_scale, f = 1%) under the corrected
simulator: full factorial {flat 2 bp, C4 costs} x {weekly -3U entry stop off, on}, with champions both FIXED to the
flat-cost selection and RE-SELECTED under the cost model in use. Reports direct and interaction effects.
Descriptive diagnostics; writes data/wrwr/decompose_factorial.csv."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

H, _, cuts, cell = E.load()
P = PF.load_pool("XAUUSD", ["H1", "H4", "D1"], cuts, verify=True)
h1 = P.tf == "H1"
vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, mode="historical", bar_seconds=3600)
active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
wk = pd.to_datetime(cuts, unit="s")


def flat_pool(P):
    R, cost = [], []
    for c in range(len(P.cands)):
        R.append(((P.gross_bp[c].astype(np.float64) - 2.0 - P.swap_bp[c]) / P.stop_bp[c]).astype(np.float32))
        cost.append(np.full(len(P.gross_bp[c]), 2.0, np.float32))
    return dataclasses.replace(P, R=R, cost_bp=cost)


PF2 = flat_pool(P)


def select(Pp):
    S1, S2, NN = PF.shadow_stats(Pp)
    sc, _ = PF.window_scores(S1, S2, NN, 52, 1.0, 10)
    return PF.champions(sc, h1, 2, Pp.rank_key, active)


ch_flat = select(PF2)
ch_c4 = select(P)
rows = []
for cost_name, Pp in (("FLAT2", PF2), ("C4", P)):
    for champ_name, ch in (("fixed to flat-cost champions", ch_flat), ("re-selected under the cost model", select(Pp) if Pp is not P else ch_c4)):
        for stop in (False, True):
            wr, eq, cnt = PF.simulate(Pp, ch, vs, f=0.01, weekstop=stop)
            r = wr[active]
            rows.append(dict(costs=cost_name, champions=champ_name, weekly_stop="on" if stop else "off", total_R=r.sum(),
                             final_equity=eq[-1], entries=cnt["entries"], weekstop_skips=cnt["skip_weekstop"],
                             minlot_skips=cnt["skip_minlot"], busy_skips=cnt["skip_busy"], riskcap_skips=cnt["skip_riskcap"],
                             **{e: wr[active & (wk >= a0) & (wk < a1)].sum() for e, (a0, a1) in
                                {"2004-08": ("2004", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"),
                                 "2021-26": ("2021", "2027")}.items()}))
X = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(X.round(1).to_string(index=False))
X.to_csv(K.ROOT / "data" / "wrwr" / "decompose_factorial.csv", index=False)
print()
for champ in X.champions.unique():
    g = X[X.champions == champ].set_index(["costs", "weekly_stop"]).total_R
    a, b, c, d = g[("FLAT2", "off")], g[("FLAT2", "on")], g[("C4", "off")], g[("C4", "on")]
    print(f"{champ}: stop effect at flat cost {b - a:+.1f} R, at C4 cost {d - c:+.1f} R; cost effect with stop off {c - a:+.1f} R, "
          f"with stop on {d - b:+.1f} R; interaction {(d - c) - (b - a):+.1f} R")
