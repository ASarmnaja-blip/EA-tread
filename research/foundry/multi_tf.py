"""Indicator zoo + random entries on many timeframes (operator 2026-09-30: "ทำหลาย tf").
M5 / M15 / M30 from the live Exness feed (mid = bid + half the recorded spread, 2021-01..2026-09);
H1 / H4 / D1 from Dukascopy mid (2003-05..2026-08). 31 indicators x FOLLOW/FADE x stop 1/2 ATR(14 of that
TF) x RR {1, 2, 3, 5, 10} x max hold {24, 240} bars (D1: {10, 60}); one position at a time, at most
6,000 trades per setup (seeded subsample when more); 2 bp cost and swap. All rows kept.
Writes data/foundry/multi_tf.xlsx and data/foundry/multi_tf.png. Descriptive only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402
from families import nonoverlap  # noqa: E402

src = (HERE / "indicator_zoo.py").read_text(encoding="utf-8")
NS = {"__file__": str(HERE / "indicator_zoo.py"), "__name__": "zoo_defs"}
exec(compile(src[: src.index("rng = np.random.default_rng(7)")], "zoo_defs", "exec"), NS)
RRS, KS, CAP = (1, 2, 3, 5, 10), (1, 2), 6000


def mk(t, o, h, l, c, v, sp_bp, step):
    t = np.asarray(t, np.int64)
    idx = pd.to_datetime(t, unit="s")
    B = E.Bars(t, o, h, l, c, E._atr(h, l, c, 14), np.zeros(len(t), int), sp_bp, idx.hour.to_numpy(), idx.dayofweek.to_numpy(),
               idx.year.to_numpy(), step)
    B.v = v
    return B


def resample(B, step):
    k = B.t // step
    df = pd.DataFrame(dict(k=k, t=B.t, o=B.o, h=B.h, l=B.l, c=B.c, v=B.v, sp=B.spread_bp))
    g = df.groupby("k").agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"),
                            sp=("sp", "median"), n=("t", "size"))
    need = max(1, int(0.5 * step / B.step))
    g = g[g.n >= need]
    return mk(g.t.to_numpy(), *(g[x].to_numpy(float) for x in ("o", "h", "l", "c", "v", "sp")), step)


def load_all():
    import bars as BR
    b5 = BR.load_bars(frozen=False)
    half = np.asarray(b5.sp, float) / 2
    o, h, l, c = (np.asarray(getattr(b5, x), float) + half for x in ("o", "h", "l", "c"))
    M5 = mk(b5.t, o, h, l, c, np.asarray(b5.v, float), np.asarray(b5.sp, float) / c * 1e4, 300)
    Hd, Dd, _, _ = E.load()
    Hd.v = E._CACHE["vol"]
    Dv = pd.Series(Hd.v).groupby(((Hd.t - 22 * 3600) // 86400)).sum()
    Dd.v = Dv.reindex((Dd.t - 22 * 3600) // 86400).fillna(0).to_numpy()
    H4 = resample(Hd, 4 * 3600)
    return {"M5": (M5, "Exness"), "M15": (resample(M5, 900), "Exness"), "M30": (resample(M5, 1800), "Exness"),
            "H1": (Hd, "Dukascopy"), "H4": (H4, "Dukascopy"), "D1": (Dd, "Dukascopy")}


def eras_for(src):
    if src == "Exness":
        return {"2021-23": ("2021", "2024"), "2024-26": ("2024", "2027")}
    return {"2003-08": ("2003", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"), "2021-26": ("2021", "2027")}


def run_setup(B, ent, d, k, rr, hold):
    last = np.minimum(ent + hold - 1, len(B.t) - 1)
    a = B.atr[ent]
    g, ex = E.simulate(B, ent, d, k * a, rr * k * a, last)
    sw = E.swap_bp(B, ent, ex, d)
    sb = k * a / B.o[ent] * 1e4
    return g / sb, (g - sw - E.COST_BP) / sb, E.COST_BP / sb


rows = []
rng = np.random.default_rng(20260930)
for tf, (B, srcname) in load_all().items():
    holds = (10, 60) if tf == "D1" else (24, 240)
    ERAS = eras_for(srcname)
    ok_bar = np.isfinite(B.atr) & (np.arange(len(B.t)) < len(B.t) - max(holds) - 2)
    for nm, x in (("H", B), ("o", pd.Series(B.o)), ("h", pd.Series(B.h)), ("l", pd.Series(B.l)), ("c", pd.Series(B.c)), ("v", pd.Series(B.v))):
        NS[nm] = x
    sigs = NS["signals"]()
    sigs["RANDOM (coin flip)"] = None
    print(f"{tf}: {len(B.t):,} bars {pd.to_datetime(B.t[0], unit='s'):%Y-%m} .. {pd.to_datetime(B.t[-1], unit='s'):%Y-%m}", flush=True)
    for name, sg in sigs.items():
        if sg is None:
            pool = np.flatnonzero(ok_bar)
            ent0 = np.sort(rng.choice(pool, min(40000, len(pool)), replace=False))
            d0 = np.where(rng.random(len(ent0)) < .5, 1.0, -1.0)
            modes = (("RANDOM", 1),)
        else:
            sl, ss = sg
            il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
            ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
            o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
            okm = ok_bar[np.minimum(ent0, len(ok_bar) - 1)]; ent0, d0 = ent0[okm], d0[okm]
            modes = (("FOLLOW", 1), ("FADE", -1))
        for hold in holds:
            keep = nonoverlap(ent0, ent0 + hold - 1)
            ent, dd = ent0[keep], d0[keep]
            n_signals = len(ent)
            if len(ent) > CAP:
                pick = np.sort(rng.choice(len(ent), CAP, replace=False)); ent, dd = ent[pick], dd[pick]
            if len(ent) < 30:
                continue
            dt = pd.to_datetime(B.t[ent], unit="s")
            yrs = (B.t[-1] - B.t[0]) / (365.25 * 86400)
            for mode, sgn in modes:
                d = dd * sgn
                for k in KS:
                    for rr in RRS:
                        gross, net, cost = run_setup(B, ent, d, k, rr, hold)
                        r = dict(tf=tf, data=srcname, setup=name, mode=mode, k_atr=k, RR=f"1:{rr}", rr=rr, hold_bars=hold,
                                 n=len(ent), n_signals=n_signals, win_rate=float((gross > 0).mean()), gross_R=float(gross.mean()),
                                 cost_R=float(cost.mean()), net_R=float(net.mean()),
                                 R_per_year=float(net.mean() * n_signals / yrs))
                        for e, (a0, a1) in ERAS.items():
                            m = (dt >= a0) & (dt < a1)
                            r[f"net_{e}"] = float(net[m].mean()) if m.sum() >= 20 else np.nan
                        rows.append(r)
X = pd.DataFrame(rows)
base = X[X["mode"] == "RANDOM"].set_index(["tf", "k_atr", "rr", "hold_bars"]).net_R
X["random_net_R"] = [base.get((r.tf, r.k_atr, r.rr, r.hold_bars), np.nan) for r in X.itertuples()]
X["minus_random"] = X.net_R - X.random_net_R
I = X[X["mode"] != "RANDOM"]
order = ["M5", "M15", "M30", "H1", "H4", "D1"]
S = I.groupby("tf").agg(setups=("n", "size"), best_net_R=("net_R", "max"), worst_net_R=("net_R", "min"), mean_net_R=("net_R", "mean"),
                        share_positive=("net_R", lambda s: float((s > 0).mean())), mean_cost_R=("cost_R", "mean"),
                        mean_gross_R=("gross_R", "mean")).reindex(order)
S["random_mean_net_R"] = X[X["mode"] == "RANDOM"].groupby("tf").net_R.mean().reindex(order)
SR = I.pivot_table(index="tf", columns="RR", values="net_R", aggfunc="max").reindex(order)[[f"1:{r}" for r in RRS]]
SM = I.pivot_table(index="tf", columns="RR", values="net_R", aggfunc="mean").reindex(order)[[f"1:{r}" for r in RRS]]
best_rows = I.loc[I.groupby("tf").net_R.idxmax()].set_index("tf").reindex(order)
worst_rows = I.loc[I.groupby("tf").net_R.idxmin()].set_index("tf").reindex(order)
out = E.ROOT / "data" / "foundry" / "multi_tf.xlsx"
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "ทุกแบบอยู่ครบ ทั้งบวกและลบ · M5/M15/M30 จาก Exness (2021-2026) · H1/H4/D1 จาก Dukascopy (2003-2026)",
        "stop 1 หรือ 2 ATR ของกรอบเวลานั้น · RR 1:1 ถึง 1:10 · ถือสูงสุด 24 หรือ 240 แท่ง (D1: 10 หรือ 60 แท่ง) · ถือได้ทีละไม้",
        "หักต้นทุน 2 bp และ swap แล้ว · หน่วย R เทียบกับระยะ stop · R_per_year = R ต่อไม้ × จำนวนสัญญาณต่อปี (ถือได้ทีละไม้)",
        "ข้อมูลที่เห็นแล้วทั้งหมด ลองหลายพันแบบ ตัวที่ดูดีมีส่วนหนึ่งเป็นความบังเอิญ ไม่ใช่สัญญาณเทรด"]}).to_excel(xw, sheet_name="README", index=False)
    S.to_excel(xw, sheet_name="สรุปตาม TF")
    SR.to_excel(xw, sheet_name="บวกสุด TF x RR")
    SM.to_excel(xw, sheet_name="เฉลี่ย TF x RR")
    best_rows.to_excel(xw, sheet_name="ตัวบวกสุดแต่ละ TF")
    worst_rows.to_excel(xw, sheet_name="ตัวลบสุดแต่ละ TF")
    X.to_excel(xw, sheet_name="ทุกแบบ", index=False)
pd.set_option("display.width", 240)
print(f"\n{len(I)} indicator setups + {len(X) - len(I)} random rows -> {out.name}")
print(S.round(3).to_string())
print("\nbest net R per trade, TF x RR:"); print(SR.round(3).to_string())
print("\naverage net R per trade, TF x RR:"); print(SM.round(3).to_string())
print("\nbest per TF:"); print(best_rows[["setup", "mode", "k_atr", "RR", "hold_bars", "n", "win_rate", "gross_R", "cost_R", "net_R", "R_per_year"]].round(3).to_string())
print("\nworst per TF:"); print(worst_rows[["setup", "mode", "k_atr", "RR", "hold_bars", "n", "win_rate", "gross_R", "cost_R", "net_R"]].round(3).to_string())
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(15, 5))
for tf in order:
    ax[0].plot(range(len(RRS)), SM.loc[tf].values, marker="o", label=tf)
ax[0].axhline(0, color="k", lw=.7); ax[0].set_xticks(range(len(RRS))); ax[0].set_xticklabels(SM.columns)
ax[0].set_title("Average indicator setup: net R per trade by RR and timeframe"); ax[0].legend()
xs = np.arange(len(order))
ax[1].bar(xs - 0.2, S.mean_gross_R.values, 0.4, label="gross R (before cost)")
ax[1].bar(xs + 0.2, -S.mean_cost_R.values, 0.4, label="cost (2 bp) in R", color="tab:red")
ax[1].plot(xs, S.mean_net_R.values, "ko-", label="net R")
ax[1].axhline(0, color="k", lw=.7); ax[1].set_xticks(xs); ax[1].set_xticklabels(order); ax[1].set_title("Cost drag by timeframe"); ax[1].legend()
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "multi_tf.png", dpi=110)
print("chart -> multi_tf.png")
