"""Random 1:1 setups - the no-edge baseline (operator request 2026-09-30). Entries are drawn at random
from H1 bars; stop distance = target distance = k ATR; exit at stop, target, or the time limit.
Grid: direction {LONG, SHORT, COIN} x k {0.5, 1, 1.5, 2, 3} x max hold {4, 12, 24, 72} h x session
{ALL, ASIA 00-07, LONDON 07-12, NY 12-17 UTC}. ~20,000 random entries per session (seed fixed), reused
across the grid. After 2 bp cost and swap. Results by era and by WPWB regime; writes
data/foundry/random_1to1.csv and a chart data/foundry/random_1to1.png. Descriptive only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402

H, D, cuts, cell = E.load()
cb = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
rng = np.random.default_rng(20260930)
SESS = {"ALL": range(24), "ASIA": range(0, 7), "LONDON": range(7, 12), "NY": range(12, 17)}
ERAS = {"2003-08": ("2003", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"), "2021-26": ("2021", "2027")}
ok_bar = np.isfinite(H.atr) & (np.arange(len(H.t)) < len(H.t) - 80) & (cb != "")
rows, per_trade = [], []
for sname, hrs in SESS.items():
    pool = np.flatnonzero(ok_bar & np.isin(H.hour, list(hrs)))
    ent = np.sort(rng.choice(pool, 20000, replace=False))
    coin = np.where(rng.random(len(ent)) < 0.5, 1.0, -1.0)
    a = H.atr[ent]
    date = pd.to_datetime(H.t[ent], unit="s")
    era = np.select([(date >= a0) & (date < a1) for a0, a1 in ERAS.values()], list(ERAS), "")
    vol = np.array([c.split("/")[0] for c in cb[ent]]); trd = np.array([c.split("/")[1] for c in cb[ent]])
    for dname in ("LONG", "SHORT", "COIN"):
        d = np.ones(len(ent)) if dname == "LONG" else (-np.ones(len(ent)) if dname == "SHORT" else coin)
        for k in (0.5, 1.0, 1.5, 2.0, 3.0):
            for hold in (4, 12, 24, 72):
                last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
                g, ex = E.simulate(H, ent, d, k * a, k * a, last)
                sw = E.swap_bp(H, ent, ex, d)
                sb = k * a / H.o[ent] * 1e4
                R = (g - sw - E.COST_BP) / sb
                gross_R = g / sb
                win = g > 0
                base = dict(session=sname, direction=dname, k_atr=k, hold_h=hold)
                for e in list(ERAS) + ["ALL"]:
                    m = (era == e) if e != "ALL" else np.ones(len(ent), bool)
                    rows.append(dict(base, split="era", group=e, n=int(m.sum()), win_rate=float(win[m].mean()),
                                     gross_R=float(gross_R[m].mean()), net_R=float(R[m].mean()),
                                     cost_R=float((E.COST_BP / sb[m]).mean()), swap_R=float((sw[m] / sb[m]).mean()),
                                     t=E.cluster_t(R[m], H.t[ent][m] // E.WEEK)))
                for v in ("CALM", "NORMAL", "HIGH"):
                    for tr in ("DOWN", "FLAT", "UP"):
                        m = (vol == v) & (trd == tr)
                        if m.sum() >= 100:
                            rows.append(dict(base, split="regime", group=f"{v}/{tr}", n=int(m.sum()), win_rate=float(win[m].mean()),
                                             gross_R=float(gross_R[m].mean()), net_R=float(R[m].mean()),
                                             cost_R=float((E.COST_BP / sb[m]).mean()), swap_R=float((sw[m] / sb[m]).mean()),
                                             t=E.cluster_t(R[m], H.t[ent][m] // E.WEEK)))
X = pd.DataFrame(rows)
out = E.ROOT / "data" / "foundry" / "random_1to1.csv"
X.to_csv(out, index=False)
A = X[(X.split == "era") & (X.group == "ALL")]
pd.set_option("display.width", 220)
print(f"{len(A)} random 1:1 setups (x 5 era rows, + regime rows) -> {out.name}")
print("\nall eras pooled, by direction and stop size (averaged over sessions and holds):")
print(A.groupby(["direction", "k_atr"])[["win_rate", "gross_R", "cost_R", "swap_R", "net_R"]].mean().round(3).to_string())
E_ = X[(X.split == "era") & (X.group != "ALL")]
print("\nby era and direction (all sessions/stops/holds averaged):")
print(E_.groupby(["group", "direction"])[["win_rate", "gross_R", "net_R"]].mean().round(3).unstack("direction").to_string())
print(f"\nshare of the {len(A)} setups with net R > 0 over 2003-2026: {(A.net_R > 0).mean():.0%}; "
      f"COIN direction only: {(A[A.direction == 'COIN'].net_R > 0).mean():.0%}")
R_ = X[(X.split == "regime") & (X.direction == "COIN")]
print("\nCOIN direction by WPWB regime (averaged over the grid):")
print(R_.groupby("group")[["n", "win_rate", "gross_R", "net_R"]].mean().round(3).to_string())

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 3, figsize=(16, 5))
for dname, col in (("LONG", "tab:green"), ("SHORT", "tab:red"), ("COIN", "tab:gray")):
    g = E_[E_.direction == dname].groupby(["group"]).net_R.mean().reindex(list(ERAS))
    ax[0].plot(list(ERAS), g.values, marker="o", color=col, label=dname)
ax[0].axhline(0, color="k", lw=.6); ax[0].set_title("Random 1:1: mean net R by era"); ax[0].legend(); ax[0].set_ylabel("net R per trade")
g = A[A.direction == "COIN"].groupby("k_atr")[["gross_R", "net_R"]].mean()
ax[1].plot(g.index, g.gross_R, marker="o", label="gross (before cost/swap)")
ax[1].plot(g.index, g.net_R, marker="o", label="net")
ax[1].axhline(0, color="k", lw=.6); ax[1].set_xlabel("stop = target (ATR)"); ax[1].set_title("COIN direction: cost drag by stop size"); ax[1].legend()
ax[2].hist(A.net_R, bins=40, color="tab:blue", alpha=.7)
ax[2].axvline(0, color="k", lw=.8); ax[2].set_title(f"all {len(A)} random 1:1 setups, net R 2003-26"); ax[2].set_xlabel("net R per trade")
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "random_1to1.png", dpi=110)
print("chart -> random_1to1.png")
