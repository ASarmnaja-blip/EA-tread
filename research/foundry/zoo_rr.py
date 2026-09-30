"""Everything from the random 1:1 and indicator-zoo runs, re-run with reward:risk from 1:1 to 1:10
(operator 2026-09-30). Stop = k ATR (k 1, 2), target = RR x stop, RR {1, 1.5, 2, 3, 5, 7, 10}, max hold
{24, 72, 240} h; 31 indicators x FOLLOW/FADE plus random coin-flip entries; 2 bp cost and swap; all rows
kept. Writes data/foundry/zoo_rr.xlsx and data/foundry/zoo_rr.png. Descriptive only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
from families import nonoverlap  # noqa: E402

src = (HERE / "indicator_zoo.py").read_text(encoding="utf-8")
ns = {"__file__": str(HERE / "indicator_zoo.py"), "__name__": "zoo_defs"}
exec(compile(src[: src.index("rng = np.random.default_rng(7)")], "zoo_defs", "exec"), ns)
H, signals, ERAS = ns["H"], ns["signals"], ns["ERAS"]
RRS, KS, HOLDS = (1, 1.5, 2, 3, 5, 7, 10), (1, 2), (24, 72, 240)
MAXB = 260
ok_bar = np.isfinite(H.atr) & (np.arange(len(H.t)) < len(H.t) - MAXB)


def sim(ent, d, k, rr, hold):
    last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
    a = H.atr[ent]
    g, ex = E.simulate(H, ent, d, k * a, rr * k * a, last)
    sw = E.swap_bp(H, ent, ex, d)
    sb = k * a / H.o[ent] * 1e4
    return g / sb, (g - sw - E.COST_BP) / sb, E.COST_BP / sb, sw / sb


def row(label, mode, k, rr, hold, ent, gross, net, cost, swap):
    dt = pd.to_datetime(H.t[ent], unit="s")
    r = dict(setup=label, mode=mode, k_atr=k, RR=f"1:{rr:g}", rr=rr, hold_h=hold, n=len(ent),
             win_rate=float((gross > 0).mean()), gross_R=float(gross.mean()), cost_R=float(cost.mean()),
             swap_R=float(swap.mean()), net_R=float(net.mean()), total_R=float(net.sum()),
             years=float((H.t[ent].max() - H.t[ent].min()) / (365.25 * 86400)) if len(ent) else np.nan)
    r["R_per_year"] = r["total_R"] / r["years"] if r["years"] else np.nan
    for e, (a0, a1) in ERAS.items():
        m = (dt >= a0) & (dt < a1)
        r[f"net_{e}"] = float(net[m].mean()) if m.sum() >= 20 else np.nan
    return r


rows = []
rng = np.random.default_rng(20260930)
pool = np.flatnonzero(ok_bar)
for hold in HOLDS:
    ent = np.sort(rng.choice(pool, 20000, replace=False)); d = np.where(rng.random(len(ent)) < .5, 1.0, -1.0)
    last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
    keep = nonoverlap(ent, last)            # one position at a time, like the indicators
    e2, d2 = ent[keep], d[keep]
    for k in KS:
        for rr in RRS:
            rows.append(row("RANDOM (coin flip)", "RANDOM", k, rr, hold, e2, *sim(e2, d2, k, rr, hold)))
for name, (sl, ss) in signals().items():
    il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
    ent0 = np.r_[il, is_] + 1
    d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
    o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
    ok = ok_bar[np.minimum(ent0, len(ok_bar) - 1)]; ent0, d0 = ent0[ok], d0[ok]
    for hold in HOLDS:
        last = np.searchsorted(H.t, H.t[ent0] + (hold - 1) * 3600, side="right") - 1
        keep = nonoverlap(ent0, last); ent, dd = ent0[keep], d0[keep]
        for fade in (False, True):
            d = -dd if fade else dd
            for k in KS:
                for rr in RRS:
                    rows.append(row(name, "FADE" if fade else "FOLLOW", k, rr, hold, ent, *sim(ent, d, k, rr, hold)))
X = pd.DataFrame(rows)
base = X[X["mode"] == "RANDOM"].set_index(["k_atr", "rr", "hold_h"]).net_R
X["random_net_R"] = [base[(r.k_atr, r.rr, r.hold_h)] for r in X.itertuples()]
X["minus_random"] = X.net_R - X.random_net_R
I = X[X["mode"] != "RANDOM"]
byrr = I.groupby("RR", sort=False).agg(setups=("n", "size"), best_net_R=("net_R", "max"), worst_net_R=("net_R", "min"),
                                       mean_net_R=("net_R", "mean"), share_positive=("net_R", lambda s: float((s > 0).mean())),
                                       mean_win_rate=("win_rate", "mean"), mean_gross_R=("gross_R", "mean"), mean_cost_R=("cost_R", "mean"))
rnd = X[X["mode"] == "RANDOM"].groupby("RR", sort=False).agg(random_mean_net_R=("net_R", "mean"), random_win_rate=("win_rate", "mean"))
byrr = byrr.join(rnd)
top = I.sort_values("net_R", ascending=False)
out = E.ROOT / "data" / "foundry" / "zoo_rr.xlsx"
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "ทุกแบบอยู่ครบ ทั้งบวกและลบ · RR 1:1 ถึง 1:10 (target = RR × stop) · stop 1 หรือ 2 ATR · ถือสูงสุด 24 / 72 / 240 ชม.",
        "หักต้นทุน 2 bp และ swap แล้ว · หน่วย R = เทียบกับระยะ stop · win_rate = สัดส่วนไม้ที่ได้กำไรก่อนหักต้นทุน",
        "RANDOM = เข้าไม้สุ่ม ใช้ RR stop และเวลาถือเดียวกัน · minus_random = ดีกว่าไม้สุ่มเท่าไร",
        "ข้อมูลที่เห็นแล้วทั้งหมด ลองหลายพันแบบ ตัวที่ดูดีมีส่วนหนึ่งเป็นความบังเอิญ ไม่ใช่สัญญาณเทรด"]}).to_excel(xw, sheet_name="README", index=False)
    byrr.to_excel(xw, sheet_name="สรุปตาม RR")
    top.head(50).to_excel(xw, sheet_name="บวกมากสุด 50", index=False)
    top.tail(50).iloc[::-1].to_excel(xw, sheet_name="ลบมากสุด 50", index=False)
    X.to_excel(xw, sheet_name="ทุกแบบ", index=False)
pd.set_option("display.width", 230)
print(f"{len(I)} indicator setups + {len(X) - len(I)} random -> {out.name}")
print(byrr.round(3).to_string())
print("\nbest 5:"); print(top.head(5)[["setup", "mode", "k_atr", "RR", "hold_h", "n", "win_rate", "gross_R", "cost_R", "net_R", "R_per_year"]].round(3).to_string(index=False))
print("\nworst 5:"); print(top.tail(5)[["setup", "mode", "k_atr", "RR", "hold_h", "n", "win_rate", "gross_R", "cost_R", "net_R", "R_per_year"]].round(3).to_string(index=False))
print(f"\nnet R > 0 in all four eras: {int((I[[f'net_{e}' for e in ERAS]] > 0).all(axis=1).sum())} of {len(I)}")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(14, 5))
xs = range(len(RRS))
ax[0].plot(xs, byrr.best_net_R.values, marker="o", color="tab:green", label="best indicator setup")
ax[0].plot(xs, byrr.mean_net_R.values, marker="o", color="tab:blue", label="average indicator setup")
ax[0].plot(xs, byrr.random_mean_net_R.values, marker="o", color="tab:gray", label="random entries")
ax[0].plot(xs, byrr.worst_net_R.values, marker="o", color="tab:red", label="worst indicator setup")
ax[0].axhline(0, color="k", lw=.7); ax[0].set_xticks(list(xs)); ax[0].set_xticklabels(list(byrr.index)); ax[0].set_ylabel("net R per trade")
ax[0].set_title("Net R per trade by reward:risk (after cost and swap)"); ax[0].legend(fontsize=8)
ax[1].plot(xs, byrr.mean_win_rate.values, marker="o", label="indicators"); ax[1].plot(xs, byrr.random_win_rate.values, marker="o", color="tab:gray", label="random")
ax[1].plot(xs, [1 / (1 + r) for r in RRS], ls="--", color="k", label="break-even win rate (no cost)")
ax[1].set_xticks(list(xs)); ax[1].set_xticklabels(list(byrr.index)); ax[1].set_title("Win rate by reward:risk"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "zoo_rr.png", dpi=110)
print("chart -> zoo_rr.png")
