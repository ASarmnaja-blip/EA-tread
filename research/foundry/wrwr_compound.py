"""Which timeframe compounds best under WRWR weekly champion selection? (operator 2026-09-30:
"Tf ไหนทำผลทาง finance ทบต้นได้ดีที่สุด"). For each TF pool (M5, M15, H1, H4, D1, ALL) and a small grid of selector
settings, the weekly net R series is compounded at a fixed fraction f of equity risked per trade:
equity *= 1 + f x (week's R). Reports CAGR, max drawdown % and final multiple over the full span, the last 5 years and the
last 3 years, for (a) the pre-registered rule (52w LCB z1 top2, WRWR sizing) and (b) the best in-sample setting per TF.
f in {0.25, 0.5, 1, 2, 3}% per trade; "best" = highest CAGR with max drawdown <= 30%. Paper only; no orders.
Writes data/foundry/wrwr_compound.xlsx and .png."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import vol as V  # noqa: E402

parts = []
for tf in ("H1", "H4", "D1", "M15", "M5"):
    f = E.ROOT / "data" / "foundry" / ("wpwb_walkforward_cache.npz" if tf == "H1" else f"wpwb_walkforward_cache_{tf}.npz")
    z = np.load(f, allow_pickle=True)
    parts.append((pd.DataFrame(z["cands"].tolist()).assign(tf=tf), *(z[x] for x in ("S1", "S2", "NN", "E1", "EN"))))
C = pd.concat([p[0] for p in parts], ignore_index=True)
S1, S2, NN, E1, EN = (np.vstack([p[i] for p in parts]) for i in range(1, 6))
H, _, cuts, cell = E.load()
NW = len(cuts)
rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
rv = V.mask_invalid(rv_raw, nb); F = V.ewma_forecast(rv)
scale = np.full(NW, V.SCALE_MIN)
for k in range(1, NW):
    scale[k] = V.effective_scale(V.vol_scale(F[k]), V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
wkdate = pd.to_datetime(cuts, unit="s")
weeks = np.arange(60, NW - 1)
weeks = weeks[(cell[weeks] != "") & (EN[:, weeks].sum(0) > 0)]
vcls = np.array([c.split("/")[0] for c in cell[weeks]])
cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]
cS1, cS2, cN = cum(S1), cum(S2), cum(NN)
cols = np.arange(len(weeks)); e1w, enw = E1[:, weeks], EN[:, weeks]
POOLS = {tf: (C.tf == tf).to_numpy() for tf in ("M5", "M15", "H1", "H4", "D1")}
POOLS["ALL 5 TF"] = np.ones(len(C), bool)
FS = (0.0025, 0.005, 0.01, 0.02, 0.03)
WIN = {"เต็ม 2004-26": slice(0, len(weeks)), "5 ปีล่าสุด": slice(len(weeks) - 260, len(weeks)), "3 ปีล่าสุด": slice(len(weeks) - 156, len(weeks))}


_TOP = {}


def series(pm, L, zz, m, sized, eqf, skip_calm, minn=20):
    key = (pm.tobytes().__hash__(), L, zz)
    if key not in _TOP:
        a = np.maximum(weeks - L, 0)
        s1, s2, n = cS1[:, weeks] - cS1[:, a], cS2[:, weeks] - cS2[:, a], cN[:, weeks] - cN[:, a]
        mu = s1 / np.maximum(n, 1); var = (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1)
        s_ = np.where((n >= minn) & pm[:, None], mu - zz * np.sqrt(np.maximum(var, 0) / np.maximum(n, 1)), -np.inf)
        ix = np.argpartition(-s_, 5, axis=0)[:5]; v = np.take_along_axis(s_, ix, 0); o = np.argsort(-v, axis=0)
        _TOP[key] = (np.take_along_axis(ix, o, 0), np.take_along_axis(v, o, 0))
    idx, vv = _TOP[key]
    sc = None
    R = np.zeros(len(weeks)); T = np.zeros(len(weeks))
    for j in range(m):
        ok = vv[j] > 0
        R += np.where(ok, e1w[idx[j], cols], 0.0); T += np.where(ok, enw[idx[j], cols], 0.0)
    live = np.ones(len(weeks), bool)
    if skip_calm:
        live &= vcls != "CALM"
    if eqf:
        c_ = np.r_[0.0, np.cumsum(R)]; live &= (c_[cols] - c_[np.maximum(cols - eqf, 0)]) > 0
    return np.where(live, R, 0.0) * (scale[weeks] if sized else 1.0), np.where(live, T, 0.0)


def compound(R, f):
    g = np.maximum(1 + f * R, 1e-9)                      # a week can't lose more than all equity
    eq = np.cumprod(g); yrs = len(R) / 52.18
    dd = float((1 - eq / np.maximum.accumulate(eq)).max())
    return dict(CAGR=float(eq[-1] ** (1 / yrs) - 1), max_dd=dd, multiple=float(eq[-1]))


rows = []
GRID = list(itertools.product((26, 52, 78), (0.5, 1.0, 2.0), (1, 2, 3, 5), (True, False), (0, 26), (False, True)))
for pn, pm in POOLS.items():
    for (L, zz, m, sized, eqf, skc) in GRID:
        R, T = series(pm, L, zz, m, sized, eqf, skc)
        base = (L, zz, m, sized, eqf, skc) == (52, 1.0, 2, True, 0, False)
        for wn, sl in WIN.items():
            r_ = R[sl]
            for f in FS:
                rows.append(dict(pool=pn, window=L, lcb_z=zz, top_m=m, wrwr_sizing=sized, equity_filter=eqf, skip_calm=skc,
                                 preregistered=base, period=wn, risk_per_trade=f, total_R=float(r_.sum()), trades=float(T[sl].sum()),
                                 **compound(r_, f)))
    print(f"{pn} done", flush=True)
X = pd.DataFrame(rows)
ok = X.max_dd <= 0.30
best = X[ok].sort_values("CAGR", ascending=False).groupby(["period", "pool"], sort=False).head(1)
pre = X[X.preregistered & (X.risk_per_trade == 0.01)]
order = ["M5", "M15", "H1", "H4", "D1", "ALL 5 TF"]
pd.set_option("display.width", 250)
for wn in WIN:
    print(f"\n=== {wn} ===")
    b = best[best.period == wn].set_index("pool").reindex(order)
    p = pre[pre.period == wn].set_index("pool").reindex(order)
    t = pd.DataFrame({"pre_CAGR_1%": p.CAGR, "pre_maxDD_1%": p.max_dd, "pre_R": p.total_R,
                      "best_CAGR": b.CAGR, "best_maxDD": b.max_dd, "best_multiple": b.multiple, "best_risk": b.risk_per_trade,
                      "best_R": b.total_R, "best_setting": b.apply(lambda r: f"{r.window}w z{r.lcb_z} top{r.top_m} size{int(r.wrwr_sizing)} "
                                                                        f"eq{r.equity_filter} skipCALM{int(r.skip_calm)}", axis=1)})
    print(t.round(3).to_string())
out = E.ROOT / "data" / "foundry" / "wrwr_compound.xlsx"
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "ทบต้นทุกสัปดาห์: พอร์ต × (1 + ความเสี่ยงต่อไม้ × R ของสัปดาห์) · หักต้นทุนและ swap แล้ว · ไม่มี Grid/Martingale",
        "M5/M15 มีข้อมูลตั้งแต่ 2021 เท่านั้น ในช่วง 'เต็ม' สัปดาห์ก่อนหน้านั้นจึงไม่มีไม้ (นับเป็น 0) เทียบ TF อย่างยุติธรรมให้ดูช่วง 5 ปีและ 3 ปี",
        "pre = กฎที่ประกาศไว้ก่อนดูผล (52 สัปดาห์ LCB 2 ตัว) ที่ความเสี่ยง 1% ต่อไม้ · best = ชุดที่ CAGR สูงสุดโดยขาดทุนสะสมไม่เกิน 30% (จูนย้อนหลัง)",
        "ผลจูนย้อนหลังไม่ใช่หลักฐานว่าจะได้ต่อในอนาคต · กระดาษเท่านั้น"]}).to_excel(xw, sheet_name="README", index=False)
    for wn in WIN:
        best[best.period == wn].set_index("pool").reindex(order).reset_index().to_excel(xw, sheet_name=f"ดีสุด {wn}"[:31], index=False)
        pre[pre.period == wn].to_excel(xw, sheet_name=f"กฎเดิม {wn}"[:31], index=False)
    X.to_excel(xw, sheet_name="ทุกแบบ", index=False)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 3, figsize=(17, 5), sharey=False)
for i, wn in enumerate(WIN):
    b = best[best.period == wn].set_index("pool").reindex(order)
    for pn in order:
        if pn not in b.index or pd.isna(b.loc[pn, "window"]):
            continue
        r = b.loc[pn]
        R, _ = series(POOLS[pn], int(r.window), float(r.lcb_z), int(r.top_m), bool(r.wrwr_sizing), int(r.equity_filter), bool(r.skip_calm))
        eq = np.cumprod(np.maximum(1 + r.risk_per_trade * R[WIN[wn]], 1e-9))
        ax[i].plot(wkdate[weeks][WIN[wn]], eq, label=f"{pn}: CAGR {r.CAGR:.0%}, DD {r.max_dd:.0%}")
    ax[i].set_yscale("log"); ax[i].set_title(f"{wn} - best setting per TF (in-sample)"); ax[i].legend(fontsize=7)
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "wrwr_compound.png", dpi=110)
print("-> wrwr_compound.xlsx / .png")
