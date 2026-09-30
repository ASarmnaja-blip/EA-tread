"""WPWB walk-forward champion backtest (docs/WPWB_WALKFORWARD_PREREG.md; operator 2026-09-30:
"จับ backtest เดินผ่านกราฟทีละแท่งด้วยเทคนิค wpwb"). Every one of 2,232 indicator candidates runs bar by bar as a
shadow (one position each); at every Friday 22:15 UTC cut the champion(s) are picked from trades that already
exited, the week is traded with the champion's shadow trades, sized by the WPWB vol_scale. Descriptive only.
Writes data/foundry/wpwb_walkforward.xlsx and .png."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import vol as V  # noqa: E402

src = (HERE / "indicator_zoo.py").read_text(encoding="utf-8")
NS = {"__file__": str(HERE / "indicator_zoo.py"), "__name__": "zoo_defs"}
exec(compile(src[: src.index("rng = np.random.default_rng(7)")], "zoo_defs", "exec"), NS)
H, cuts, cell = NS["H"], NS["cuts"], NS["cell"]
SPLICED = __import__("os").environ.get("SPLICED") == "1"
if SPLICED:     # Dukascopy H1 to its end, then the live Exness feed (engine.load_spliced) - to name the current champion
    _v = np.asarray(H.v, float)
    H, _, cuts, cell = E.load_spliced()
    H.v = np.r_[_v, np.full(len(H.t) - len(_v), np.median(_v[-6000:]))]     # Exness tick volume is on another scale
TF = __import__("os").environ.get("TF", "H1")
TF_SUFFIX = ""
if True:                        # resampler (H4 / D1 from Dukascopy H1, M15 from Exness M5)
    def _rs(B, step):
        k = (B.t - (22 * 3600 if step == 86400 else 0)) // step
        df = pd.DataFrame(dict(k=k, t=B.t, o=B.o, h=B.h, l=B.l, c=B.c, v=B.v, sp=B.spread_bp))
        g = df.groupby("k").agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                                v=("v", "sum"), sp=("sp", "median"), n=("t", "size"))
        g = g[g.n >= (18 if step == 86400 else (2 if step >= 3600 else 1))]
        tt = g.t.to_numpy(np.int64); idx = pd.to_datetime(tt, unit="s")
        R = E.Bars(tt, g.o.to_numpy(float), g.h.to_numpy(float), g.l.to_numpy(float), g.c.to_numpy(float),
                   E._atr(g.h.to_numpy(float), g.l.to_numpy(float), g.c.to_numpy(float), 14),
                   np.searchsorted(cuts, tt, side="left") - 1, g.sp.to_numpy(float), idx.hour.to_numpy(),
                   idx.dayofweek.to_numpy(), idx.year.to_numpy(), step)
        R.v = g.v.to_numpy(float)
        return R
    if TF in ("H4", "D1"):
        H = _rs(H, 4 * 3600 if TF == "H4" else 86400)
if TF in ("M5", "M15"):         # operator 2026-09-30 "เอา tf เล็ก m5/m15": live Exness M5 mid (2021-01 ..), same cuts
    import bars as _BR
    if __import__("os").environ.get("HIST") == "1":     # HistData 2009-2020 + Exness 2021- (research/history/build_histdata.py)
        _z = np.load(E.ROOT / "data" / "history" / "XAUUSD_M5_2009_2026_spliced.npz")
        _t, _o, _h, _l, _c = _z["t"].astype(np.int64), _z["o"], _z["h"], _z["l"], _z["c"]
        _sp = np.where(np.isfinite(_z["sp_bp"]), _z["sp_bp"], np.nanmedian(_z["sp_bp"])); _v = _z["v"]
    else:
        _b5 = _BR.load_bars(frozen=False)
        _half = np.asarray(_b5.sp, float) / 2
        _o, _h, _l, _c = (np.asarray(getattr(_b5, x), float) + _half for x in ("o", "h", "l", "c"))
        _t = np.asarray(_b5.t, np.int64); _sp = np.asarray(_b5.sp, float) / _c * 1e4; _v = np.asarray(_b5.v, float)
    _i = pd.to_datetime(_t, unit="s")
    H = E.Bars(_t, _o, _h, _l, _c, E._atr(_h, _l, _c, 14), np.searchsorted(cuts, _t, side="left") - 1,
               _sp, _i.hour.to_numpy(), _i.dayofweek.to_numpy(), _i.year.to_numpy(), 300)
    H.v = _v
    if __import__("os").environ.get("HIST") == "1":
        TF_SUFFIX = "L"
    if TF == "M15":
        H = _rs(H, 900)
N = len(H.t)
EXITS = [("1:1", 1.0), ("1:2", 2.0), ("1:3", 3.0), ("1:5", 5.0), ("1:10", 10.0),
         ("2:1", 1 / 2), ("3:1", 1 / 3), ("5:1", 1 / 5), ("10:1", 1 / 10)]      # target = mult x stop
KS = (1, 2)
HOLDS = {"H1": (24, 72), "H4": (6, 30), "D1": (5, 20), "M5": (48, 144), "M15": (32, 96)}[__import__("os").environ.get("TF", "H1")]
ERAS = {"2003-08": ("2003", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"), "2021-26": ("2021", "2027")}


# ---------------------------------------------------------------- leak check (pre-registered)
def _signals_with(Hx):
    for nm, x in (("H", Hx), ("o", pd.Series(Hx.o)), ("h", pd.Series(Hx.h)), ("l", pd.Series(Hx.l)),
                  ("c", pd.Series(Hx.c)), ("v", pd.Series(Hx.v))):
        NS[nm] = x
    return NS["signals"]()


base = _signals_with(H)
rng_l = np.random.default_rng(1)
for j in (N // 10, N // 2, N - 300):
    G = copy.copy(H)
    for f in ("o", "h", "l", "c", "v"):
        a = np.asarray(getattr(H, f), float).copy()
        a[j + 1:] = a[j + 1:] * rng_l.uniform(0.5, 1.5, N - j - 1)
        setattr(G, f, a)
    G.h = np.maximum.reduce([G.o, G.h, G.l, G.c]); G.l = np.minimum.reduce([G.o, G.h, G.l, G.c])
    G.h[: j + 1], G.l[: j + 1] = H.h[: j + 1], H.l[: j + 1]
    S2 = _signals_with(G)
    bad = [k for k in base if not (np.array_equal(base[k][0][: j + 1], S2[k][0][: j + 1])
                                   and np.array_equal(base[k][1][: j + 1], S2[k][1][: j + 1]))]
    assert not bad, f"LEAK at j={j}: {bad}"
print("leak check PASS (3 cut points, 31 signals)", flush=True)
_signals_with(H)

# ---------------------------------------------------------------- shadow trades of every candidate
close_t = H.t + H.step
NW = len(cuts)
wk_exit_of_bar = np.searchsorted(cuts, close_t, side="left") - 1     # close in (cuts[w], cuts[w+1]]
wk_ent_of_bar = H.week
atr_ok = np.isfinite(H.atr)


def sequential(ent, ex):
    keep, busy = [], -1
    for i, (e, x) in enumerate(zip(ent.tolist(), ex.tolist())):
        if e > busy:
            keep.append(i); busy = x
    return np.asarray(keep, int)


CACHE = E.ROOT / "data" / "foundry" / (("wpwb_walkforward_cache_spliced" if SPLICED else "wpwb_walkforward_cache") + ("" if TF == "H1" else f"_{TF}{TF_SUFFIX}") + ".npz")
cands, S1, S2_, NN, E1, EN = [], [], [], [], [], []
for name, (sl, ss) in ({} if CACHE.exists() else base).items():
    il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
    ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
    o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
    ok = atr_ok[ent0] & (ent0 < N - max(HOLDS) - 2) & (wk_ent_of_bar[ent0] >= 0) & (wk_ent_of_bar[ent0] < NW - 2)
    ent0, d0 = ent0[ok], d0[ok]
    for mode, sgn in (("FOLLOW", 1.0), ("FADE", -1.0)):
        d = d0 * sgn
        for k in KS:
            stop = k * H.atr[ent0]
            sb = stop / H.o[ent0] * 1e4
            for hold in HOLDS:
                last = ent0 + hold - 1
                for lab, mult in EXITS:
                    g, ex = E.simulate(H, ent0, d, stop, mult * stop, last)
                    keep = sequential(ent0, ex)
                    e_, x_ = ent0[keep], ex[keep]
                    R = (g[keep] - E.swap_bp(H, e_, x_, d[keep]) - E.COST_BP) / sb[keep]
                    we, wx = wk_ent_of_bar[e_], wk_exit_of_bar[x_]
                    inw = wx < NW                                    # exits after the last cut are dropped
                    we, wx, R = we[inw], wx[inw], R[inw]
                    cands.append(dict(setup=name, mode=mode, k_atr=k, exit=lab, hold=hold, n_trades=len(e_)))
                    S1.append(np.bincount(wx, R, NW)); S2_.append(np.bincount(wx, R * R, NW)); NN.append(np.bincount(wx, None, NW))
                    E1.append(np.bincount(we, R, NW)); EN.append(np.bincount(we, None, NW))
    print(f"  {name}: done ({len(cands)} candidates)", flush=True)
if CACHE.exists():
    z = np.load(CACHE, allow_pickle=True)
    C = pd.DataFrame(z["cands"].tolist()); S1, S2_, NN, E1, EN = (z[x] for x in ("S1", "S2", "NN", "E1", "EN"))
    print(f"loaded shadow trades of {len(C)} candidates from cache", flush=True)
else:
    C = pd.DataFrame(cands)
    S1, S2_, NN, E1, EN = (np.vstack(a) for a in (S1, S2_, NN, E1, EN))       # candidates x weeks
    np.savez_compressed(CACHE, cands=np.array(cands, dtype=object), S1=S1, S2=S2_, NN=NN, E1=E1, EN=EN)
C["label"] = C.setup + " " + C["mode"] + " SL" + C.k_atr.astype(str) + "ATR " + C.exit + " ถือ" + C.hold.astype(str) + "ชม."

# ---------------------------------------------------------------- WPWB vol_scale per week
rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
rv = V.mask_invalid(rv_raw, nb)
F = V.ewma_forecast(rv)
scale = np.full(NW, V.SCALE_MIN)
for k in range(1, NW):
    cal = V.calibration(rv[:k], F[:k])[0]
    scale[k] = V.effective_scale(V.vol_scale(F[k]), cal, bool(nb[k - 1] >= V.MIN_BARS))

# ---------------------------------------------------------------- selection rules
cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]     # cum[:, k] = sum of weeks < k
cS1, cS2, cN = cum(S1), cum(S2_), cum(NN)
first_k = 60
wkdate = pd.to_datetime(cuts, unit="s")
weeks = np.arange(first_k, NW - 1)
weeks = weeks[(cell[weeks] != "") & (EN[:, weeks].sum(0) > 0)]


def window_stats(win, k):
    if win == "SAME-CELL":
        j = np.arange(max(0, k - 104), k)
        j = j[cell[j] == cell[k]]
        return S1[:, j].sum(1), S2_[:, j].sum(1), NN[:, j].sum(1)
    a = max(0, k - win)
    return cS1[:, k] - cS1[:, a], cS2[:, k] - cS2[:, a], cN[:, k] - cN[:, a]


cfg = pd.factorize(C.k_atr.astype(str) + C.exit + C.hold.astype(str))[0]
RULES = [(w, s, m) for w in (4, 13, 26, 52, "SAME-CELL") for s in ("MEAN", "LCB") for m in (1, 2)]
rng = np.random.default_rng(20260930)
REPS = 1000
summary, weekly_logs, nulls, pick_count = [], {}, {}, {}
for win, sc, m in RULES:
    minn = 5 if win == 4 else 10
    log, null_tot = [], np.zeros(REPS)
    null_n, cfg_tot, cfg_n = np.zeros(REPS), np.zeros(REPS), np.zeros(REPS)    # Amendment 1 (post hoc)
    for k in weeks:
        s1, s2, n = window_stats(win, k)
        elig = n >= minn
        if not elig.any():
            continue
        mu = np.where(elig, s1 / np.maximum(n, 1), -np.inf)
        if sc == "LCB":
            var = np.where(n > 1, (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1), np.inf)
            mu = np.where(elig, mu - np.sqrt(np.maximum(var, 0) / np.maximum(n, 1)), -np.inf)
        top = np.argsort(-mu)[:m]
        top = top[mu[top] > 0]
        if len(top) == 0:
            log.append(dict(week=wkdate[k], cell=cell[k], scale=scale[k], champion="NO TRADE", score=float(mu.max()),
                            trades=0, R=0.0, R_sized=0.0, all_R=float(E1[elig, k].sum() / elig.sum())))
            continue
        R = float(E1[top, k].sum()); nt = int(EN[top, k].sum())
        pool = np.flatnonzero(elig)
        pk = rng.integers(0, len(pool), (REPS, len(top)))
        null_tot += E1[pool[pk], k].sum(1) * scale[k]
        null_n += EN[pool[pk], k].sum(1)
        for c_ in top:
            same = pool[cfg[pool] == cfg[c_]]
            q_ = same[rng.integers(0, len(same), REPS)]
            cfg_tot += E1[q_, k] * scale[k]; cfg_n += EN[q_, k]
        for c_ in top:
            pick_count.setdefault((win, sc, m), {}).setdefault(int(c_), 0)
            pick_count[(win, sc, m)][int(c_)] += 1
        log.append(dict(week=wkdate[k], cell=cell[k], scale=scale[k], champion=" + ".join(C.label[top]),
                        score=float(mu[top[0]]), trades=nt, R=R, R_sized=R * scale[k],
                        all_R=float(E1[elig, k].sum() / elig.sum()) * len(top)))
    L = pd.DataFrame(log)
    tr = L[L.champion != "NO TRADE"]
    yrs = (L.week.max() - L.week.min()).days / 365.25
    r = dict(window=str(win), score=sc, champions=m, weeks=len(L), weeks_traded=len(tr), trades=int(tr.trades.sum()),
             R_per_trade=tr.R.sum() / max(tr.trades.sum(), 1), total_R=tr.R.sum(), total_R_sized=tr.R_sized.sum(),
             R_per_year_sized=tr.R_sized.sum() / yrs, share_weeks_pos=float((tr.R > 0).sum() / max((tr.trades > 0).sum(), 1)),
             t_weeks=float(tr.R.mean() / tr.R.std(ddof=1) * np.sqrt(len(tr))) if len(tr) > 2 else np.nan,
             random_pick_median_sized=float(np.median(null_tot)), p_vs_random=float((null_tot >= tr.R_sized.sum()).mean()),
             all_candidates_R_sized=float((tr.all_R * tr.scale).sum()),
             random_pick_R_per_trade=float(np.median(null_tot / np.maximum(null_n, 1))),
             samecfg_median_sized=float(np.median(cfg_tot)), samecfg_R_per_trade=float(np.median(cfg_tot / np.maximum(cfg_n, 1))),
             p_vs_samecfg=float((cfg_tot >= tr.R_sized.sum()).mean()))
    for e, (a0, a1) in ERAS.items():
        q = tr[(tr.week >= a0) & (tr.week < a1)]
        r[f"R_sized_{e}"] = q.R_sized.sum(); r[f"R_per_trade_{e}"] = q.R.sum() / max(q.trades.sum(), 1)
    summary.append(r); weekly_logs[(win, sc, m)] = L; nulls[(win, sc, m)] = null_tot
    print(f"{str(win):>9} {sc:4} top{m}: traded {len(tr)} wk, {int(tr.trades.sum())} trades, "
          f"{r['R_per_trade']:+.3f} R/trade, sized total {r['total_R_sized']:+.1f} R, random-pick median "
          f"{r['random_pick_median_sized']:+.1f}, p {r['p_vs_random']:.3f} | same-exit-config pick median {r['samecfg_median_sized']:+.1f} "
          f"({r['samecfg_R_per_trade']:+.3f} R/trade), p {r['p_vs_samecfg']:.3f}", flush=True)
Sm = pd.DataFrame(summary)
best = Sm.sort_values(["p_vs_samecfg", "total_R_sized"], ascending=[True, False]).iloc[0]
bk = (int(best.window) if best.window.isdigit() else best.window, best.score, int(best.champions))
picks = pd.DataFrame([(C.label[c_], n) for c_, n in pick_count.get(bk, {}).items()], columns=["candidate", "weeks_as_champion"])
picks = picks.sort_values("weeks_as_champion", ascending=False)
out = E.ROOT / "data" / "foundry" / (("wpwb_walkforward_spliced" if SPLICED else "wpwb_walkforward") + ("" if TF == "H1" else f"_{TF}{TF_SUFFIX}") + ".xlsx")
with pd.ExcelWriter(out) as xw:
    pd.DataFrame({"อ่านก่อน": [
        "เดินทีละแท่งบน H1 ทองคำ 2003-2026 · 2,232 ตัวเลือก (31 อินดิเคเตอร์ × ตาม/สวน × SL 1-2 ATR × TP 9 แบบ × ถือ 24/72 ชม.) รันเงาทุกตัวตลอด",
        "ทุกเย็นศุกร์ 22:15 UTC (สไตล์ WPWB) เลือกตัวเต็ง 1-2 ตัวจากไม้ที่ปิดไปแล้วเท่านั้น แล้วใช้ตัวนั้นเทรดสัปดาห์ถัดไป · ถ้าคะแนนตัวดีสุด ≤ 0 = NO TRADE",
        "หน้าต่างเลือก: 4 / 13 / 26 / 52 สัปดาห์ล่าสุด หรือ SAME-CELL = สัปดาห์ในรอบ 104 สัปดาห์ที่สภาพตลาด WPWB เหมือนสัปดาห์นี้",
        "คะแนน MEAN = R เฉลี่ย · LCB = R เฉลี่ยลบ 1 ส่วนเบี่ยงเบนมาตรฐาน (ลงโทษตัวที่ผลแกว่ง)",
        "R_sized = R × vol_scale ของ WPWB (ลดขนาดไม้อย่างเดียว 0.5-1.0) · net หลังต้นทุน 2 bp และ swap",
        "p_vs_random = โอกาสที่การเลือกแบบสุ่มจากตัวเลือกเดียวกันในสัปดาห์เดียวกันได้ผลเท่าหรือดีกว่า · ลอง 20 กฎ ต้อง p < 0.0025 ถึงจะเกินกว่าความบังเอิญ",
        "p_vs_samecfg (เพิ่มภายหลัง) = สุ่มเลือกตัวที่ใช้ SL/TP/เวลาถือ แบบเดียวกับตัวเต็ง แต่อินดิเคเตอร์/ทิศสุ่ม → ทดสอบว่าการเลือกอินดิเคเตอร์ช่วยจริงไหม ไม่ใช่แค่ได้ต้นทุนถูก",
        "ข้อมูลที่เห็นแล้ว ไม่ใช่สัญญาณเทรด (docs/WPWB_WALKFORWARD_PREREG.md)"]}).to_excel(xw, sheet_name="README", index=False)
    Sm.to_excel(xw, sheet_name="สรุปทุกกฎ", index=False)
    weekly_logs[bk].to_excel(xw, sheet_name="รายสัปดาห์ กฎดีสุด", index=False)
    picks.to_excel(xw, sheet_name="ตัวที่ถูกเลือกบ่อย", index=False)
    C.drop(columns="label").to_excel(xw, sheet_name="ตัวเลือกทั้งหมด", index=False)
pd.set_option("display.width", 250)
print(Sm[["window", "score", "champions", "weeks_traded", "trades", "R_per_trade", "total_R_sized", "R_per_year_sized",
          "random_pick_median_sized", "p_vs_random", "samecfg_median_sized", "samecfg_R_per_trade", "p_vs_samecfg"] + [f"R_sized_{e}" for e in ERAS]].round(3).to_string(index=False))
print("\nmost-picked champions of the lowest-p rule", bk); print(picks.head(10).to_string(index=False))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(13, 6))
for key, L in weekly_logs.items():
    ax.plot(L.week, L.R_sized.cumsum(), lw=1.4 if key == bk else .6, alpha=1 if key == bk else .45,
            label=f"best-p rule: window {key[0]}, {key[1]}, top{key[2]}" if key == bk else None)
ax.axhline(0, color="k", lw=.7)
ax.set_title("WPWB walk-forward: cumulative sized net R of all 20 selection rules (H1 gold, 2004-2026)")
ax.set_ylabel("cumulative R (x vol_scale)"); ax.legend()
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / (("wpwb_walkforward_spliced" if SPLICED else "wpwb_walkforward") + ("" if TF == "H1" else f"_{TF}{TF_SUFFIX}") + ".png"), dpi=110)
print("-> wpwb_walkforward.xlsx / .png")
