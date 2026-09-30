"""Every indicator setup and every random 1:1 setup, KEPT IN FULL (positive and negative alike), broken
down by the WPWB regime of the week (volatility class x 13-week trend, known at the Friday cut) and by era,
each cell next to the random-entry baseline for the same stop, hold and regime.
Operator 2026-09-30: "ติดลบหรือเป็นบวกผมเอาหมด ไม่ต้องตัดทิ้ง ใช้ wpwb".
Writes data/foundry/zoo_all_wpwb.xlsx and data/foundry/zoo_wpwb_heatmap.png. Descriptive only."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
from families import nonoverlap  # noqa: E402

# reuse the zoo's indicator definitions without running its report
src = (HERE / "indicator_zoo.py").read_text(encoding="utf-8")
src = src[: src.index("rng = np.random.default_rng(7)")]
ns = {"__file__": str(HERE / "indicator_zoo.py"), "__name__": "zoo_defs"}
exec(compile(src, "indicator_zoo_defs", "exec"), ns)
H, signals, ERAS = ns["H"], ns["signals"], ns["ERAS"]
_, _, cuts, cell = E.load()
cb = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
VOL_TH = {"CALM": "สงบ", "NORMAL": "ปกติ", "HIGH": "ผันผวนสูง"}
TR_TH = {"DOWN": "ขาลง", "FLAT": "ไซด์เวย์", "UP": "ขาขึ้น"}
CELLS = [f"{v}/{t}" for v in VOL_TH for t in TR_TH]


def run(ent, d, k, hold):
    ok = np.isfinite(H.atr[ent]) & (ent < len(H.t) - 80) & (cb[np.minimum(ent, len(cb) - 1)] != "")
    ent, d = ent[ok], d[ok]
    last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
    a = H.atr[ent]
    g, ex = E.simulate(H, ent, d, k * a, k * a, last)
    g = g - E.swap_bp(H, ent, ex, d)
    R = (g - E.COST_BP) / (k * a / H.o[ent] * 1e4)
    return ent, d, R


def summarise(label, mode, k, hold, ent, d, R, extra=None):
    dt = pd.to_datetime(H.t[ent], unit="s")
    era = np.select([(dt >= a0) & (dt < a1) for a0, a1 in ERAS.values()], list(ERAS), "")
    rows = []
    for split, keys, arr in (("ALL", ["ALL"], np.array(["ALL"] * len(ent))), ("era", list(ERAS), era), ("WPWB", CELLS, cb[ent])):
        for key in keys:
            m = arr == key
            n = int(m.sum())
            rows.append(dict(setup=label, mode=mode, k_atr=k, hold_h=hold, split=split, group=key, n=n,
                             win_rate=float((R[m] > 0).mean()) if n else np.nan, net_R=float(R[m].mean()) if n else np.nan,
                             total_R=float(R[m].sum()) if n else 0.0, long_share=float((d[m] > 0).mean()) if n else np.nan,
                             t=E.cluster_t(R[m], H.t[ent][m] // E.WEEK) if n > 2 else np.nan, **(extra or {})))
    return rows


rows = []
rng = np.random.default_rng(20260930)
pool = np.flatnonzero(np.isfinite(H.atr) & (np.arange(len(H.t)) < len(H.t) - 80) & (cb != ""))
for k in (1, 2):
    for hold in (24, 72):
        ent = np.sort(rng.choice(pool, 40000, replace=False)); d = np.where(rng.random(len(ent)) < .5, 1.0, -1.0)
        e2, d2, R = run(ent, d, k, hold)
        rows += summarise("RANDOM (coin flip)", "RANDOM", k, hold, e2, d2, R)
for name, (sl, ss) in signals().items():
    for fade in (False, True):
        for k in (1, 2):
            for hold in (24, 72):
                il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
                ent = np.r_[il, is_] + 1
                d = np.r_[np.ones(len(il)), -np.ones(len(is_))] * (-1 if fade else 1)
                o_ = np.argsort(ent, kind="stable"); ent, d = ent[o_], d[o_]
                last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
                keep = nonoverlap(ent, last); ent, d = ent[keep], d[keep]
                e2, d2, R = run(ent, d, k, hold)
                if len(e2):
                    rows += summarise(name, "FADE" if fade else "FOLLOW", k, hold, e2, d2, R)
X = pd.DataFrame(rows)
base = X[X["mode"] == "RANDOM"].set_index(["k_atr", "hold_h", "split", "group"]).net_R
X["random_net_R"] = [base.get((r.k_atr, r.hold_h, r.split, r.group), np.nan) for r in X.itertuples()]
X["minus_random"] = X.net_R - X.random_net_R

# the random 1:1 grid from random_1to1.py, kept in full as well
rnd = E.ROOT / "data" / "foundry" / "random_1to1.csv"
R11 = pd.read_csv(rnd) if rnd.exists() else pd.DataFrame()

ALLr = X[X.split == "ALL"].copy()
wide_era = X[X.split == "era"].pivot_table(index=["setup", "mode", "k_atr", "hold_h"], columns="group", values="net_R")
wide_wpwb = X[X.split == "WPWB"].pivot_table(index=["setup", "mode", "k_atr", "hold_h"], columns="group", values="net_R")[CELLS]
wide_wpwb_n = X[X.split == "WPWB"].pivot_table(index=["setup", "mode", "k_atr", "hold_h"], columns="group", values="n")[CELLS]
wide_wpwb_ex = X[X.split == "WPWB"].pivot_table(index=["setup", "mode", "k_atr", "hold_h"], columns="group", values="minus_random")[CELLS]
th = {c_: f"{VOL_TH[c_.split('/')[0]]}/{TR_TH[c_.split('/')[1]]}" for c_ in CELLS}
best_cell = X[(X.split == "WPWB") & (X["mode"] != "RANDOM") & (X.n >= 30)].sort_values("minus_random", ascending=False)
per_cell = (best_cell.groupby("group").head(5)[["group", "setup", "mode", "k_atr", "hold_h", "n", "net_R", "random_net_R", "minus_random", "t"]]
            .assign(group=lambda d: d.group.map(th)))
out = E.ROOT / "data" / "foundry" / "zoo_all_wpwb.xlsx"
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "ทุก setup อยู่ในไฟล์นี้ครบ ทั้งบวกและลบ ไม่ได้ตัดทิ้ง (ผู้ใช้ขอ 2026-09-30)",
        "ทองคำ H1 (Dukascopy) 2003-2026 · ออกแบบ 1:1 (stop = target = k × ATR) · ถือสูงสุด 24 หรือ 72 ชม. · ถือได้ทีละไม้",
        "หักต้นทุน 2 bp ต่อรอบ และ swap ฝั่ง Buy แล้ว · หน่วย R = กำไรหรือขาดทุนเทียบกับระยะ stop",
        "FOLLOW = เล่นตามที่ตำราอ่านสัญญาณ · FADE = เล่นฝั่งตรงข้าม · RANDOM = เข้าไม้สุ่ม (เส้นฐานที่ไม่มี edge)",
        "สภาพตลาด WPWB = ความผันผวนที่คาดไว้ (สงบ/ปกติ/ผันผวนสูง) × เทรนด์ 13 สัปดาห์ (ขาลง/ไซด์เวย์/ขาขึ้น) รู้ได้ตั้งแต่เย็นวันศุกร์",
        "minus_random = R สุทธิ ลบ R ของไม้สุ่มที่ใช้ขนาด stop เวลาถือ และสภาพตลาดเดียวกัน (> 0 แปลว่าดีกว่าสุ่ม)",
        "ตัวเครื่องจำลองระวังไว้ก่อน: ถ้าแท่งเดียวแตะทั้ง stop และ target นับเป็นแพ้ ไม้สุ่มก็โดนกฎเดียวกัน การเทียบกับไม้สุ่มจึงยุติธรรม",
        "เป็นข้อมูลที่เห็นแล้วทั้งหมด ลองหลายร้อยแบบ ตัวที่ดูดีมีส่วนหนึ่งมาจากความบังเอิญ ไม่ใช่สัญญาณเทรด"]}).to_excel(xw, sheet_name="README", index=False)
    ALLr.drop(columns=["split", "group"]).sort_values("minus_random", ascending=False).to_excel(xw, sheet_name="ทุก setup 2003-26", index=False)
    wide_era.to_excel(xw, sheet_name="R ตามยุค")
    wide_wpwb.rename(columns=th).to_excel(xw, sheet_name="R ตามสภาพ WPWB")
    wide_wpwb_ex.rename(columns=th).to_excel(xw, sheet_name="ดีกว่าสุ่ม ตาม WPWB")
    wide_wpwb_n.rename(columns=th).to_excel(xw, sheet_name="จำนวนไม้ ตาม WPWB")
    per_cell.to_excel(xw, sheet_name="5 อันดับต่อสภาพ", index=False)
    X.to_excel(xw, sheet_name="ข้อมูลดิบทั้งหมด", index=False)
    if len(R11):
        R11.to_excel(xw, sheet_name="ไม้สุ่ม 1-1 ทุกแบบ", index=False)
print(f"{ALLr[ALLr['mode'] != 'RANDOM'].shape[0]} indicator setups + {ALLr[ALLr['mode'] == 'RANDOM'].shape[0]} random baselines, "
      f"{int(ALLr[ALLr['mode'] != 'RANDOM'].n.sum()):,} trades; all kept -> {out.name}")
cellsum = X[(X.split == "WPWB") & (X["mode"] != "RANDOM")].groupby("group").agg(
    setups=("n", "size"), trades=("n", "sum"), mean_net_R=("net_R", "mean"), share_beat_random=("minus_random", lambda s: float((s > 0).mean())),
    share_net_pos=("net_R", lambda s: float((s > 0).mean())))
cellsum["random_net_R"] = X[(X.split == "WPWB") & (X["mode"] == "RANDOM")].groupby("group").net_R.mean()
cellsum.index = [th[i] for i in cellsum.index]
pd.set_option("display.width", 200)
print(cellsum.round(3).to_string())
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
M = wide_wpwb_ex.groupby(level=["setup", "mode"]).mean()
M = M.loc[M.mean(axis=1).sort_values().index]
fig, ax = plt.subplots(figsize=(11, 18))
im = ax.imshow(M.values, aspect="auto", cmap="RdYlGn", vmin=-0.3, vmax=0.3)
ax.set_xticks(range(len(CELLS))); ax.set_xticklabels([c_.replace("/", "\n") for c_ in CELLS], fontsize=8)
ax.set_yticks(range(len(M))); ax.set_yticklabels([f"{a} ({b})" for a, b in M.index], fontsize=6)
ax.set_title("Indicator setups (1:1, after cost/swap) minus random entries, by WPWB regime\n(green = better than random, red = worse; averaged over stop and hold)")
fig.colorbar(im, ax=ax, fraction=0.03)
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "zoo_wpwb_heatmap.png", dpi=110)
print("heatmap -> zoo_wpwb_heatmap.png")
