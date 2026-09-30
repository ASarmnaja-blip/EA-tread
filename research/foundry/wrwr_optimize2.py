"""WRWR system optimiser v2 (operator 2026-09-30 "ดีไม่พอ"): H1 + H4 + D1 candidates pooled, more selector knobs,
three objectives (total R with every era positive; share of positive years; return / max drawdown).
v1 docstring follows. WRWR (formerly WPWB) system optimiser - operator 2026-09-30: "เมื่อย้อนหลังมาแล้วระบบต้องทำให้ได้กำไร".
Base: the walk-forward champion backtest (wpwb_walkforward.py, cached shadow trades of 2,232 H1 candidates).
Searches selector configurations (window, score, top-m, NO TRADE margin, min trades, candidate pool, WRWR sizing,
equity-curve filter, skipped WRWR vol classes) and reports
  (1) WALK-FORWARD: each calendar year uses the configuration that did best over the previous 4 years (no future);
  (2) IN-SAMPLE: the configuration with the highest 2004-26 total among those positive in every era (chosen WITH
      hindsight - a curve fit, not evidence).
No Grid / Martingale / averaging: sizes only ever shrink (vol_scale 0.5-1.0) and one weekly champion set trades.
Writes data/foundry/wrwr_system.xlsx and .png. Research only; no orders."""
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
for tf, f in (("H1", "wpwb_walkforward_cache.npz"), ("H4", "wpwb_walkforward_cache_H4.npz"), ("D1", "wpwb_walkforward_cache_D1.npz")):
    z = np.load(E.ROOT / "data" / "foundry" / f, allow_pickle=True)
    parts.append((pd.DataFrame(z["cands"].tolist()).assign(tf=tf), *(z[x] for x in ("S1", "S2", "NN", "E1", "EN"))))
C = pd.concat([p[0] for p in parts], ignore_index=True)
S1, S2, NN, E1, EN = (np.vstack([p[i] for p in parts]) for i in range(1, 6))
print(f"{len(C)} candidates:", C.tf.value_counts().to_dict(), flush=True)
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
year = wkdate[weeks].year.to_numpy()
vcls = np.array([c.split("/")[0] if c else "" for c in cell[weeks]])
ERAS = {"2004-08": (2004, 2008), "2009-14": (2009, 2014), "2015-20": (2015, 2020), "2021-26": (2021, 2026)}
cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]
cS1, cS2, cN = cum(S1), cum(S2), cum(NN)
tfv, k2, longh = C.tf.to_numpy(), (C.k_atr == 2).to_numpy(), C.groupby("tf").hold.transform("max").eq(C.hold).to_numpy()
POOLS = {"ALL": np.ones(len(C), bool), "H1": tfv == "H1", "H4": tfv == "H4", "D1": tfv == "D1", "H4+D1": tfv != "H1",
         "SL2ATR": k2, "LONG_HOLD": longh, "H4+D1_SL2": (tfv != "H1") & k2}
WINDOWS, ZS, MINNS, TOPM, THETA = (26, 52, 78, 104), (0.5, 1.0, 1.5, 2.0), (10, 20), (1, 2, 3, 5, 8), (0.0, 0.05, 0.1)
EQF = (0, 13, 26, 52)
TOPK = max(TOPM)

# top-5 candidates per week for every (window, z, min trades, pool)
tops = {}
for L, zz, mn in itertools.product(WINDOWS, ZS, MINNS):
    a = np.maximum(weeks - L, 0)
    s1, s2, n = cS1[:, weeks] - cS1[:, a], cS2[:, weeks] - cS2[:, a], cN[:, weeks] - cN[:, a]
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s1 / np.maximum(n, 1)
        var = (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1)
        sc = mu - zz * np.sqrt(np.maximum(var, 0) / np.maximum(n, 1))
    sc = np.where(n >= mn, sc, -np.inf)
    for pn, pm in POOLS.items():
        s_ = np.where(pm[:, None], sc, -np.inf)
        idx = np.argpartition(-s_, TOPK, axis=0)[:TOPK]
        v = np.take_along_axis(s_, idx, 0); o = np.argsort(-v, axis=0)
        tops[(L, zz, mn, pn)] = (np.take_along_axis(idx, o, 0), np.take_along_axis(v, o, 0))
print(f"{len(tops)} score tables ready", flush=True)
cols = np.arange(len(weeks))
e1w, enw = E1[:, weeks], EN[:, weeks]


def series(key, m, th, sized, eqf, skip):
    idx, v = tops[key]
    R = np.zeros(len(weeks)); T = np.zeros(len(weeks))
    for j in range(m):
        ok = v[j] > th
        R += np.where(ok, e1w[idx[j], cols], 0.0); T += np.where(ok, enw[idx[j], cols], 0.0)
    live = np.ones(len(weeks), bool)
    if skip:
        live &= ~np.isin(vcls, skip)
    if eqf:                                      # trade only while the rule's own last-eqf-week shadow result is > 0
        c_ = np.r_[0.0, np.cumsum(R)]
        live &= (c_[cols] - c_[np.maximum(cols - eqf, 0)]) > 0
    R = np.where(live, R, 0.0) * (scale[weeks] if sized else 1.0); T = np.where(live, T, 0.0)
    return R, T


SKIPS = {"none": (), "skip_CALM": ("CALM",), "skip_HIGH": ("HIGH",), "NORMAL_only": ("CALM", "HIGH")}
configs = list(itertools.product(tops.keys(), TOPM, THETA, (True, False), EQF, SKIPS))
print(f"{len(configs):,} configurations", flush=True)
yrs_u = np.unique(year)
Yr = np.zeros((len(configs), len(yrs_u))); stats = []
for i, (key, m, th, sized, eqf, sk) in enumerate(configs):
    R, T = series(key, m, th, sized, eqf, SKIPS[sk])
    Yr[i] = np.bincount(np.searchsorted(yrs_u, year), R, len(yrs_u))
    c_ = np.cumsum(R); dd = float((np.maximum.accumulate(c_) - c_).max())
    stats.append((R.sum(), T.sum(), dd))
    if i % 20000 == 0:
        print(f"  {i:,}", flush=True)
cfg = pd.DataFrame([dict(window=k[0], lcb_z=k[1], min_trades=k[2], pool=k[3], top_m=m, no_trade_margin=th, wrwr_sizing=s,
                         equity_filter=e, skip=sk) for (k, m, th, s, e, sk) in configs])
cfg["total_R"], cfg["trades"], cfg["max_dd_R"] = zip(*stats)
cfg["R_per_year"] = cfg.total_R / (len(weeks) / 52.18)
cfg["R_per_trade"] = cfg.total_R / cfg.trades.clip(lower=1)
cfg["pos_years"] = (Yr > 0).mean(1); cfg["worst_year_R"] = Yr.min(1)
for e, (a, b) in ERAS.items():
    cfg[f"R_{e}"] = Yr[:, (yrs_u >= a) & (yrs_u <= b)].sum(1)
eras_pos = (cfg[[f"R_{e}" for e in ERAS]] > 0).all(axis=1)
cfg["all_eras_positive"] = eras_pos
cfg["ret_dd"] = cfg.total_R / cfg.max_dd_R.clip(lower=1)
best_is = cfg[eras_pos].sort_values("total_R", ascending=False)
best_years = cfg[eras_pos & (cfg.trades >= 1000)].sort_values(["pos_years", "total_R"], ascending=False)
best_rdd = cfg[eras_pos & (cfg.trades >= 1000)].sort_values("ret_dd", ascending=False)

# (1) walk-forward over configurations: year Y uses the config with the best total over years Y-4..Y-1
wf_rows, wf_R = [], []
for yi, Y in enumerate(yrs_u):
    past = (yrs_u >= Y - 4) & (yrs_u < Y)
    if past.sum() < 4:
        continue
    j = int(np.argmax(Yr[:, past].sum(1)))
    wf_rows.append(dict(year=int(Y), chosen=str(cfg.iloc[j][["window", "lcb_z", "min_trades", "pool", "top_m", "no_trade_margin",
                                                            "wrwr_sizing", "equity_filter", "skip"]].to_dict()), R=float(Yr[j, yi])))
WF = pd.DataFrame(wf_rows)
base_mask = ((cfg.window == 52) & (cfg.lcb_z == 1.0) & (cfg.min_trades == 10) & (cfg.pool == "H1") & (cfg.top_m == 2)
             & (cfg.no_trade_margin == 0.0) & cfg.wrwr_sizing & (cfg.equity_filter == 0) & (cfg.skip == "none"))
base = cfg[base_mask].iloc[0]
pd.set_option("display.width", 250)
show = ["window", "lcb_z", "min_trades", "pool", "top_m", "no_trade_margin", "wrwr_sizing", "equity_filter", "skip", "total_R",
        "R_per_year", "R_per_trade", "trades", "max_dd_R", "ret_dd", "pos_years", "worst_year_R"] + [f"R_{e}" for e in ERAS]
print("\nbaseline (pre-registered 52w LCB top2):"); print(base[show].to_string())
print(f"\n(1) WALK-FORWARD over configs (year uses best of the prior 4 years): total {WF.R.sum():+.1f} R over {len(WF)} years "
      f"({WF.R.sum() / len(WF):+.1f} R/yr), positive years {(WF.R > 0).mean():.0%}")
print(WF.assign(R=WF.R.round(1))[["year", "R"]].T.to_string(header=False))
for e, (a, b) in ERAS.items():
    print(f"   {e}: {WF[(WF.year >= a) & (WF.year <= b)].R.sum():+.1f} R")
print(f"\n(2) IN-SAMPLE (hindsight) - {int(eras_pos.sum()):,} of {len(cfg):,} configs positive in every era; top 5:")
print(best_is[show].head(5).round(3).to_string(index=False))
print("\n(2b) IN-SAMPLE, most positive years (>= 1,000 trades):"); print(best_years[show].head(5).round(3).to_string(index=False))
print("\n(2c) IN-SAMPLE, best return / max drawdown (>= 1,000 trades):"); print(best_rdd[show].head(5).round(3).to_string(index=False))
out = E.ROOT / "data" / "foundry" / "wrwr_system_v2.xlsx"
top = best_is.iloc[0]
key = (int(top.window), float(top.lcb_z), int(top.min_trades), top.pool)
Rb, Tb = series(key, int(top.top_m), float(top.no_trade_margin), bool(top.wrwr_sizing), int(top.equity_filter), SKIPS[top.skip])
kb = (52, 1.0, 10, "H1"); R0, _ = series(kb, 2, 0.0, True, 0, ())
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "ระบบ WRWR (ชื่อใหม่ของ WPWB) ทองคำ H1+H4+D1 2004-2026 · ทุกสัปดาห์เลือกตัวเต็งจากตัวเลือก 3 กรอบเวลา ที่รันเงาทีละแท่ง · net หลังต้นทุน 2 bp และ swap",
        "ไม่มี Grid / Martingale / ถัวเฉลี่ย: ขนาดไม้ลดได้อย่างเดียว (vol_scale 0.5-1.0) · R = หน่วยความเสี่ยงต่อไม้",
        "(1) WALK-FORWARD = ทุกปีใช้ชุดตั้งค่าที่ดีที่สุดของ 4 ปีก่อนหน้า (ไม่รู้อนาคต) = ตัวเลขที่ใกล้ความจริงกว่า",
        "(2) IN-SAMPLE = ชุดตั้งค่าที่ดีที่สุดเมื่อรู้ผลทั้ง 23 ปีแล้ว (จูนย้อนหลัง) · ได้กำไรย้อนหลังแน่นอน แต่ไม่ใช่หลักฐานว่าจะได้ต่อในอนาคต",
        "ห้ามใช้เงินจริงจากไฟล์นี้ ต้องผ่านบันทึกกระดาษและผู้ใช้ยืนยันก่อน (CLAUDE.md ข้อ 1, 8)"]}).to_excel(xw, sheet_name="README", index=False)
    pd.DataFrame([base[show]]).to_excel(xw, sheet_name="กฎเดิม 52w", index=False)
    WF.to_excel(xw, sheet_name="(1) walk-forward รายปี", index=False)
    best_is[show].head(200).to_excel(xw, sheet_name="(2) in-sample 200 อันดับ", index=False)
    best_years[show].head(100).to_excel(xw, sheet_name="(2b) ปีบวกมากสุด", index=False)
    best_rdd[show].head(100).to_excel(xw, sheet_name="(2c) กำไรต่อDD", index=False)
    pd.DataFrame(dict(week=wkdate[weeks], cell=cell[weeks], scale=scale[weeks], R=Rb, trades=Tb, cum_R=np.cumsum(Rb))).to_excel(
        xw, sheet_name="(2) ระบบดีสุด รายสัปดาห์", index=False)
    pd.DataFrame(Yr[best_is.index[:20]], columns=yrs_u, index=[f"#{i + 1}" for i in range(min(20, len(best_is)))]).to_excel(
        xw, sheet_name="(2) 20 อันดับ รายปี")
    cfg[show + ["all_eras_positive"]].to_excel(xw, sheet_name="ทุกชุดตั้งค่า", index=False)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(13, 6))
ax.plot(wkdate[weeks], np.cumsum(Rb), label=f"(2) IN-SAMPLE best: {top.total_R:+.0f} R (hindsight)", color="tab:green")
wfy = pd.Series(WF.R.to_numpy(), index=pd.to_datetime(WF.year.astype(str) + "-12-31"))
ax.plot(wfy.index, wfy.cumsum() + 0, marker="o", label=f"(1) WALK-FORWARD over configs: {WF.R.sum():+.0f} R", color="tab:blue")
ax.plot(wkdate[weeks], np.cumsum(R0), label=f"pre-registered 52w LCB top2: {R0.sum():+.0f} R", color="tab:gray")
ax.axhline(0, color="k", lw=.7); ax.set_ylabel("cumulative net R (x WRWR vol_scale)"); ax.legend()
ax.set_title("WRWR weekly champion system, gold H1 2004-2026, after cost and swap")
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "wrwr_system_v2.png", dpi=110)
print("-> wrwr_system.xlsx / .png")
