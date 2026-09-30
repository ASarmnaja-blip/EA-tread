"""Operator 2026-09-30: "ติดลบขนาดนี้แล้วอีกฝั่งจะเป็นยังไง" - what does the other side of the corrected BASE earn?
(1) exact counterparty of every BASE live trade: opposite direction, stop and target swapped, same lots (so before
    costs it is the mirror P&L), paying its own cost and swap (shorts pay no swap, longs do), stop-first on ties;
(2) FADE/FOLLOW twin: each champion replaced by the same indicator/exit with the opposite mode, run through the C2
    portfolio. All in R of the ORIGINAL trade's stop. Descriptive; writes nothing but the printout."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402
import signals as SG  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

H, _, cuts, cell = E.load()
P = PF.load_pool("XAUUSD", ["H1"], cuts)
B, _, _ = SG.load_xau("H1")
active = np.array([c != "" for c in cell][: len(cuts)] + [False] * max(0, len(cuts) - len(cell)))
vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts)
S1, S2, NN = PF.shadow_stats(P)
sc, _ = PF.window_scores(S1, S2, NN, 52, 1.0, 10)
ch = PF.champions(sc, np.ones(len(P.cands), bool), 2, P.rank_key, active)
log = []
wr, eq, cnt = PF.simulate(P, ch, vs, f=0.01, log=log)
print(f"BASE corrected: {wr[active].sum():+.1f} R (weekly, sized), {cnt['entries']} live trades")

mult = dict(SG.EXITS)
L = pd.DataFrame(log, columns=["k", "c", "entry_t", "exit_t", "lots", "R", "pnl"])
ent = np.searchsorted(B.t, L.entry_t.to_numpy())
assert (B.t[ent] == L.entry_t.to_numpy()).all()
c_arr = L.c.to_numpy()
row = np.array([np.searchsorted(P.entry_t[c], t) for c, t in zip(c_arr, L.entry_t)])
dirs = np.array([1.0 if P.cands[c]["mode"] == "FOLLOW" else -1.0 for c in c_arr])
# direction of the trade = signal direction x mode sign; recover it from the stored R sign convention via re-simulation
stop = np.array([P.stop_px[c][i] for c, i in zip(c_arr, row)])
tgt = np.array([mult[P.cands[c]["exit"]] for c in c_arr]) * stop
hold = np.array([P.cands[c]["hold"] for c in c_arr])
last = ent + hold - 1
stop_bp = stop / B.o[ent] * 1e4
cost = K.cost_bp("XAUUSD", B.spread_bp[ent])
# the table does not store the direction per row of the pool; try both and keep the one that reproduces the table R
best_dir = np.zeros(len(L))
for dsign in (1.0, -1.0):
    g, ex = E.simulate(B, ent, np.full(len(L), dsign), stop, tgt, last)
    sw = K.swap_bp("XAUUSD", B.t[ent], B.t[ex] + 3600, np.full(len(L), dsign))
    r = (g - cost - sw) / stop_bp
    match = np.abs(r - L.R.to_numpy()) < 1e-3
    best_dir = np.where(match & (best_dir == 0), dsign, best_dir)
assert (best_dir != 0).all(), f"{int((best_dir == 0).sum())} trades not reproduced"
d = best_dir
g, ex = E.simulate(B, ent, d, stop, tgt, last); sw = K.swap_bp("XAUUSD", B.t[ent], B.t[ex] + 3600, d)
g2, ex2 = E.simulate(B, ent, -d, tgt, stop, last); sw2 = K.swap_bp("XAUUSD", B.t[ent], B.t[ex2] + 3600, -d)
u = lambda x: x / stop_bp
orig_gross, orig_cost, orig_swap = u(g), u(cost), u(sw)
rev_gross, rev_swap = u(g2), u(sw2)
orig_net = orig_gross - orig_cost - orig_swap
rev_net = rev_gross - orig_cost - rev_swap
tie_both_lose = (orig_gross < 0) & (rev_gross < 0)
wk = pd.to_datetime(L.entry_t, unit="s")
print("\n(1) exact counterparty, per-trade R of the original stop (unit size, no compounding):")
T = pd.DataFrame(dict(side=["BASE", "counterparty"],
                      gross_R=[orig_gross.sum(), rev_gross.sum()], cost_R=[-orig_cost.sum(), -orig_cost.sum()],
                      swap_R=[-orig_swap.sum(), -rev_swap.sum()], net_R=[orig_net.sum(), rev_net.sum()]))
print(T.round(1).to_string(index=False))
print(f"   trades {len(L)}, both sides lose before cost (stop-first ties / timeouts near 0): {int(tie_both_lose.sum())}")
for a0, a1 in (("2004", "2009"), ("2009", "2015"), ("2015", "2021"), ("2021", "2027")):
    m = (wk >= a0) & (wk < a1)
    print(f"   {a0}-{int(a1) - 1}: BASE net {orig_net[m].sum():+7.1f} R | counterparty net {rev_net[m].sum():+7.1f} R | "
          f"cost {orig_cost[m].sum():6.1f} R over {int(m.sum())} trades")

twin = {}
keys = {(c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"]): i for i, c in enumerate(P.cands)}
for i, c in enumerate(P.cands):
    twin[i] = keys[(c["setup"], "FADE" if c["mode"] == "FOLLOW" else "FOLLOW", c["k_atr"], c["exit"], c["hold"])]
ch_twin = [[twin[c] for c in w] for w in ch]
wr2, eq2, cnt2 = PF.simulate(P, ch_twin, vs, f=0.01)
print(f"\n(2) FADE/FOLLOW twins of the same champions, C2 portfolio: {wr2[active].sum():+.1f} R "
      f"(BASE {wr[active].sum():+.1f} R), final equity {eq2[-1]:,.0f} vs {eq[-1]:,.0f}")
