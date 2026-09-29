"""Regime map (Part 1) and regime-change traces (Part 2).
See docs/REGIME_MAP_PREREG.md.  Read-only.
Usage: python research/pilot/regime_map.py [--smoke]   (--smoke prints COUNTS ONLY)"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research" / "history"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
sys.path.insert(0, str(HERE))
from build_all_tf import load_kind  # noqa: E402
import vol as V  # noqa: E402
from plan_b_daily import daily_from_h1  # noqa: E402

SMOKE = "--smoke" in sys.argv
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
N_SHIFT = 200 if SMOKE else 5000
WARM = 60
STAGE2_WARM = 260
RNG = np.random.default_rng(20260929)
OUT = ROOT / "data" / ("regime_map_smoke.xlsx" if SMOKE else "regime_map.xlsx")
PNG = ROOT / "data" / "regime_map.png"
ERAS = {"2003-2008": ("2003-01-01", "2009-01-01"), "2009-2014": ("2009-01-01", "2015-01-01"),
        "2015-2020": ("2015-01-01", "2021-01-01"), "2021-2026": ("2021-01-01", "2027-01-01")}
TARGETS = ("V-on", "V-off", "D-rev", "D-up")
CATEGORICAL = ("month", "week_of_month")


# ------------------------------------------------------------------ weekly series
def weekly():
    h = load_kind("hour")
    t = h.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    gaps = np.diff(t)
    big = int((gaps > 8 * 86400).sum())
    last_cut = int(t[-1] + 3600 - (int(t[-1] + 3600 - FIRST_CUT) % WEEK)) - WEEK
    cuts = np.arange(FIRST_CUT, last_cut, WEEK, dtype=np.int64)
    rv_raw, rng, ret, nbar = V.weekly_rv(t, h.c.to_numpy(float), h.h.to_numpy(float), h.l.to_numpy(float), cuts)
    rv = V.mask_invalid(rv_raw, nbar)
    ok = np.isfinite(rv)
    return h, t, cuts, rv, rng, np.where(ok, ret, np.nan), nbar, big


# ---------------------------------------------------------------------- Part 1
def regime_map(cuts, rv, ret):
    sig = np.sqrt(rv)
    lr = np.log1p(ret / 1e4)
    r13 = pd.Series(lr).rolling(13, min_periods=13).sum().to_numpy()
    valid = np.isfinite(sig)
    q1, q2 = np.nanquantile(sig, [1 / 3, 2 / 3])
    lvl = np.where(sig <= q1, 0, np.where(sig <= q2, 1, 2)).astype(float)
    lvl[~valid] = np.nan
    t1, t2 = np.nanquantile(r13, [1 / 3, 2 / 3])
    trend = np.where(r13 <= t1, 0, np.where(r13 <= t2, 1, 2)).astype(float)
    trend[~np.isfinite(r13)] = np.nan
    date = pd.to_datetime(cuts, unit="s")
    df = pd.DataFrame({"date": date, "sigma": sig, "ret": ret, "lvl": lvl, "trend": trend, "r13": r13})
    flip = (np.sign(df.ret) != np.sign(df.ret.shift(1))).astype(float)
    flip[df.ret.isna() | df.ret.shift(1).isna()] = np.nan
    df["flip"] = flip
    run = np.zeros(len(df)); run_id = []
    for k in range(len(df)):
        run[k] = run[k - 1] + 1 if k and df.lvl.iloc[k] == df.lvl.iloc[k - 1] and np.isfinite(df.lvl.iloc[k]) else 1
    df["run"] = run
    ends = (df.lvl != df.lvl.shift(-1)) & df.lvl.notna()
    names_l, names_t = ("ต่ำ", "กลาง", "สูง"), ("ลง", "ข้าง", "ขึ้น")
    rows = []
    for L in range(3):
        for T in range(3):
            s = df[(df.lvl == L) & (df.trend == T)]
            if len(s) == 0:
                continue
            rows.append({"ระดับผันผวน": names_l[L], "เทรนด์ 13 สัปดาห์": names_t[T], "สัปดาห์": len(s),
                         "สัดส่วน": len(s) / df.lvl.notna().sum(), "σ เฉลี่ย (bp)": s.sigma.mean(),
                         "|ผลตอบแทน| เฉลี่ย (bp)": s.ret.abs().mean(), "กลับทิศจากสัปดาห์ก่อน": s.flip.mean(),
                         "สัปดาห์ถัดไปเป็นระดับเดิม": np.nanmean((df.lvl.shift(-1)[s.index] == L).astype(float))})
    reg = pd.DataFrame(rows)
    lv = []
    for L in range(3):
        s = df[df.lvl == L]
        lv.append({"ระดับ": names_l[L], "σ ต่ำสุด (bp)": s.sigma.min(), "σ สูงสุด (bp)": s.sigma.max(),
                   "สัปดาห์": len(s), "อายุเฉลี่ยของช่วง (สัปดาห์)": df[ends & (df.lvl == L)].run.mean()})
    levels = pd.DataFrame(lv)
    trans = pd.crosstab(df.lvl, df.lvl.shift(-1), normalize="index").rename(
        index=dict(enumerate(names_l)), columns=dict(enumerate(names_l)))
    era_rows = []
    for e, (a, b) in ERAS.items():
        s = df[(df.date >= a) & (df.date < b) & df.lvl.notna()]
        if len(s):
            era_rows.append({"ยุค": e, "สัปดาห์": len(s), "ต่ำ": (s.lvl == 0).mean(), "กลาง": (s.lvl == 1).mean(),
                             "สูง": (s.lvl == 2).mean(), "σ กลาง (bp)": s.sigma.median()})
    return df, reg, levels, trans, pd.DataFrame(era_rows), (q1, q2)


# ---------------------------------------------------------------------- Part 2
def causal_high(sig):
    """HIGH_k: sigma_k >= 67th percentile of the previous 52 weekly sigmas."""
    n = len(sig)
    high = np.full(n, np.nan)
    for k in range(52, n):
        w = sig[k - 52:k]
        if np.isfinite(sig[k]) and np.isfinite(w).sum() >= 40:
            high[k] = float(sig[k] >= np.nanquantile(w, 2 / 3))
    return high


def traces(h, t, cuts, rv, rng, ret, sig, nbar):
    n = len(cuts)
    lr = np.log1p(ret / 1e4)
    close_t = t + 3600
    c_h = h.c.to_numpy(float); hi_h = h.h.to_numpy(float); lo_h = h.l.to_numpy(float)
    r1 = np.r_[np.nan, np.diff(np.log(c_h))]
    f = V.ewma_forecast(rv)
    day = daily_from_h1()
    dclose = day.c.to_numpy(float)
    dend = (day.index + pd.Timedelta(days=1, hours=22)).astype("datetime64[s]").astype(np.int64).to_numpy()
    g = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
    gs = g.set_index("d").GVZ.astype(float)
    gd = gs.index.astype("datetime64[s]").astype(np.int64).to_numpy(); gv = gs.to_numpy()
    T = {k: np.full(n, np.nan) for k in (
        "sig_ratio", "sig4_26", "ewma_ratio", "range_exp", "accel", "gvz_lvl", "gvz_chg", "gvz_prem",
        "r4z", "r13z", "r26z", "dist_ma50", "dist_ma200", "dist_hi52", "dist_lo52", "streak", "up_share8",
        "month", "week_of_month", "qend_flag", "short_week")}
    s = np.sign(ret)
    for k in range(WARM, n):
        cut = int(cuts[k]); p = k - 1
        if not np.isfinite(sig[p]):
            continue
        w52 = sig[k - 52:k]
        med52 = np.nanmedian(w52)
        T["sig_ratio"][k] = sig[p] / med52
        T["sig4_26"][k] = np.nanmean(sig[k - 4:k]) / np.nanmean(sig[k - 26:k])
        if np.isfinite(f[k]):
            T["ewma_ratio"][k] = math.sqrt(f[k]) / med52
        T["range_exp"][k] = rng[p] / sig[p]
        use = (close_t > cut - WEEK) & (close_t <= cut)
        late = use & (close_t > cut - 2 * 86400 - 3600)
        v_all = np.nansum(r1[use] ** 2)
        if v_all > 0:
            T["accel"][k] = (np.nansum(r1[late] ** 2) / v_all) / 0.4
        thu = cut - 86400
        j = np.searchsorted(gd, thu, side="right") - 1
        if j > 260 and gd[j] > cut - 6 * 86400:
            T["gvz_lvl"][k] = gv[j] / np.median(gv[j - 260:j + 1])
            j0 = np.searchsorted(gd, gd[j] - 6 * 86400, side="right") - 1
            T["gvz_chg"][k] = gv[j] / gv[j0] - 1
            T["gvz_prem"][k] = (gv[j] / 100) ** 2 / 52 * 1e8 / rv[p]
        for L, name in ((4, "r4z"), (13, "r13z"), (26, "r26z")):
            w = lr[k - L:k]
            if np.isfinite(w).sum() == L:
                T[name][k] = w.sum() / (np.nanmean(sig[k - L:k]) / 1e4 * math.sqrt(L))
        pos = np.searchsorted(close_t, cut, side="right") - 1
        c_now = c_h[pos]
        m13 = np.nanmean(sig[k - 13:k]) / 1e4
        dok = dend <= cut
        dc = dclose[dok]
        for L, name in ((50, "dist_ma50"), (200, "dist_ma200")):
            if len(dc) >= L:
                T[name][k] = math.log(c_now / dc[-L:].mean()) / m13
        lo_i = np.searchsorted(close_t, cut - 52 * WEEK, side="right")
        if pos - lo_i > 1000:
            T["dist_hi52"][k] = math.log(c_now / hi_h[lo_i:pos + 1].max()) / m13
            T["dist_lo52"][k] = math.log(c_now / lo_h[lo_i:pos + 1].min()) / m13
        st, sg = 0, s[p]
        for q in range(p, max(p - 30, -1), -1):
            if s[q] == sg and sg != 0:
                st += 1
            else:
                break
        T["streak"][k] = st * sg if sg else 0
        T["up_share8"][k] = np.nanmean(s[k - 8:k] > 0)
        d = pd.Timestamp(cut, unit="s")
        T["month"][k] = d.month
        T["week_of_month"][k] = (d.day - 1) // 7 + 1
        T["qend_flag"][k] = float(d.month in (3, 6, 9, 12) and d.day >= 22)
        T["short_week"][k] = float(nbar[k] < 100) if k < n else np.nan
    return T


def targets(sig, ret, high):
    n = len(sig)
    lr = np.log1p(ret / 1e4)
    out = {k: np.full(n, np.nan) for k in TARGETS}
    for k in range(WARM, n):
        if np.isfinite(high[k]) and np.isfinite(high[k - 1]):
            if high[k - 1] == 0:
                out["V-on"][k] = high[k]
            else:
                out["V-off"][k] = 1.0 - high[k]
        w = lr[k - 4:k]
        if np.isfinite(ret[k]) and np.isfinite(w).sum() == 4 and w.sum() != 0 and ret[k] != 0:
            out["D-rev"][k] = float(np.sign(ret[k]) != np.sign(w.sum()))
        if np.isfinite(ret[k]) and ret[k] != 0:
            out["D-up"][k] = float(ret[k] > 0)
    return out


def auc(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok].astype(bool)
    npos, nneg = y.sum(), (~y).sum()
    if npos < 10 or nneg < 10:
        return np.nan, int(npos), int(nneg)
    r = rankdata(x)
    return float((r[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)), int(npos), int(nneg)


def gstat(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok].astype(int), y[ok].astype(int)
    if y.sum() < 10 or (1 - y).sum() < 10:
        return np.nan
    cats = np.unique(x)
    tot = 0.0
    p1 = y.mean()
    for c in cats:
        m = x == c
        n = m.sum(); o1 = y[m].sum(); o0 = n - o1
        for o, e in ((o1, n * p1), (o0, n * (1 - p1))):
            if o > 0 and e > 0:
                tot += 2 * o * math.log(o / e)
    return tot


def stage1(T, Y):
    n = len(next(iter(T.values())))
    rows = []
    for tn, y in Y.items():
        for name, x in T.items():
            cat = name in CATEGORICAL
            if cat:
                obs = gstat(x, y); a, npos, nneg = np.nan, int(np.nansum(y)), int(np.sum(np.isfinite(y)) - np.nansum(y))
            else:
                a, npos, nneg = auc(x, y)
                obs = abs(a - 0.5) if np.isfinite(a) else np.nan
            if not np.isfinite(obs):
                continue
            null = np.empty(N_SHIFT)
            for i in range(N_SHIFT):
                sft = int(RNG.integers(52, n - 52))
                xs = np.roll(x, sft)
                null[i] = gstat(xs, y) if cat else abs(auc(xs, y)[0] - 0.5)
            null = null[np.isfinite(null)]
            p = (1 + np.sum(null >= obs)) / (1 + len(null))
            rows.append(dict(target=tn, trace=name, AUC=a, stat=obs, p=p, events=npos, non_events=nneg))
    R = pd.DataFrame(rows)
    return R


def walk_forward(x, y, k_start=STAGE2_WARM, bins=5):
    n = len(x)
    ok = np.isfinite(x) & np.isfinite(y)
    pred = np.full(n, np.nan)
    for k in range(k_start, n):
        past = np.flatnonzero(ok[:k]);
        if not ok[k] or len(past) < 100:
            continue
        xs, ys = x[past], y[past]
        edges = np.unique(np.quantile(xs, np.linspace(0, 1, bins + 1)[1:-1]))
        b = np.searchsorted(edges, xs)
        bk = np.searchsorted(edges, x[k])
        base = ys.mean()
        sel = b == bk
        pred[k] = (ys[sel].sum() + 5 * base) / (sel.sum() + 5)
    return pred


def stage2(x, y, pred, dates, low_mid_high):
    rows = []
    ok = np.isfinite(pred) & np.isfinite(y)
    # top-20% alarm threshold from the past predictions only
    alarm = np.zeros(len(x), bool)
    hist = []
    for k in range(len(x)):
        if ok[k]:
            if len(hist) >= 50 and pred[k] >= np.quantile(hist, 0.8):
                alarm[k] = True
            hist.append(pred[k])
    sets = {"all": ok}
    for e, (a, b) in ERAS.items():
        sets[e] = ok & (dates >= np.datetime64(a)) & (dates < np.datetime64(b))
    for nm, lab in (("LOW", 0), ("MID", 1), ("HIGH", 2)):
        sets["regime " + nm] = ok & (low_mid_high == lab)
    for nm, m in sets.items():
        if m.sum() < 30:
            continue
        yy, pp, aa = y[m], pred[m], alarm[m]
        a_ = auc(pp, yy)[0]
        base = yy.mean()
        prec = yy[aa].mean() if aa.sum() else np.nan
        rows.append(dict(subset=nm, weeks=int(m.sum()), base_rate=base, AUC=a_, alarms=int(aa.sum()),
                         precision=prec, lift=prec / base if np.isfinite(prec) and base > 0 else np.nan,
                         false_alarm_rate=float(aa[yy == 0].mean()) if (yy == 0).any() else np.nan,
                         coverage=float(aa[yy == 1].mean()) if (yy == 1).any() else np.nan))
    return pd.DataFrame(rows)


def main() -> int:
    os.chdir(ROOT)
    h, t, cuts, rv, rng, ret, nbar, big = weekly()
    sig = np.sqrt(rv)
    valid = np.isfinite(sig)
    print(f"{'SMOKE ' if SMOKE else ''}H1 bars {len(t):,} {pd.to_datetime(t[0], unit='s'):%Y-%m-%d}..{pd.to_datetime(t[-1], unit='s'):%Y-%m-%d}; "
          f"weeks {len(cuts)}; valid {int(valid.sum())}; gaps > 8 days in the bars: {big}")
    if not SMOKE:
        assert big == 0 and t[-1] > np.datetime64("2026-09-01").astype("datetime64[s]").astype(np.int64), \
            "the Dukascopy cache is not yet complete to 2026-09: run later"
    df, reg, levels, trans, eras, (q1, q2) = regime_map(cuts, rv, ret)
    if "--part1" in sys.argv:            # descriptive preview only; no Part 2 statistic is computed
        pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
        print()
        print("PART 1 PREVIEW (partial data) - LEVEL CUT-OFFS (weekly sigma, bp): "
              f"LOW <= {q1:.0f} < MID <= {q2:.0f} < HIGH")
        print(levels.round(1).to_string(index=False))
        print()
        print("9 regimes")
        print(reg.round(3).to_string(index=False))
        print()
        print("week-to-week transition of the vol level")
        print(trans.round(3).to_string())
        print()
        print("share of weeks by era")
        print(eras.round(3).to_string(index=False))
        _plot(df, q1, q2)
        print(f"saved {PNG}")
        return 0
    high = causal_high(sig)
    T = traces(h, t, cuts, rv, rng, ret, sig, nbar)
    Y = targets(sig, ret, high)
    counts = {k: (int(np.nansum(v)), int(np.isfinite(v).sum())) for k, v in Y.items()}
    print("target counts (events, defined weeks):", counts)
    if SMOKE:
        print("smoke: pipeline ran end to end on counts; no association statistic is printed by design")
        R = stage1({k: T[k] for k in ("sig_ratio", "month")}, {"V-on": Y["V-on"]})
        print(f"smoke stage1 ran {len(R)} tests; nothing shown")
        return 0
    print(f"\nPART 1 — LEVEL CUT-OFFS (weekly sigma, bp): LOW <= {q1:.0f} < MID <= {q2:.0f} < HIGH")
    pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
    print(levels.round(1).to_string(index=False))
    print("\n9 regimes"); print(reg.round(3).to_string(index=False))
    print("\nweek-to-week transition of the vol level"); print(trans.round(3).to_string())
    print("\nshare of weeks by era"); print(eras.round(3).to_string(index=False))
    R = stage1(T, Y)
    n_tests = len(R)
    alpha = 0.05 / 84
    R["survivor"] = R.p < alpha
    print(f"\nPART 2 stage 1: {n_tests} tests run, alpha = {alpha:.6f}, survivors {int(R.survivor.sum())}")
    top = R.reindex(R.p.sort_values().index).head(15)
    print(top.round(5).to_string(index=False))
    dates = np.array(cuts, dtype="datetime64[s]")
    lmh = np.full(len(cuts), np.nan)
    hi_prev = causal_high(sig)
    q_lo = np.array([np.nanquantile(sig[k - 52:k], 1 / 3) if k >= 52 else np.nan for k in range(len(sig))])
    q_hi = np.array([np.nanquantile(sig[k - 52:k], 2 / 3) if k >= 52 else np.nan for k in range(len(sig))])
    for k in range(1, len(sig)):
        if np.isfinite(sig[k - 1]) and np.isfinite(q_lo[k - 1]):
            lmh[k] = 0 if sig[k - 1] <= q_lo[k - 1] else (2 if sig[k - 1] >= q_hi[k - 1] else 1)
    s2 = []
    for _, r in R[R.survivor].iterrows():
        pred = walk_forward(T[r.trace], Y[r.target])
        tab = stage2(T[r.trace], Y[r.target], pred, dates, lmh)
        tab.insert(0, "trace", r.trace); tab.insert(0, "target", r.target)
        s2.append(tab)
    S2 = pd.concat(s2) if s2 else pd.DataFrame()
    with pd.ExcelWriter(OUT) as xw:
        levels.to_excel(xw, sheet_name="levels", index=False)
        reg.to_excel(xw, sheet_name="9 regimes", index=False)
        trans.to_excel(xw, sheet_name="transitions")
        eras.to_excel(xw, sheet_name="by era", index=False)
        df.to_excel(xw, sheet_name="weekly", index=False)
        R.to_excel(xw, sheet_name="stage1", index=False)
        if len(S2):
            S2.to_excel(xw, sheet_name="stage2", index=False)
    if len(S2):
        print("\nPART 2 stage 2 — walk-forward accuracy of survivors (all / by era / by regime)")
        print(S2.round(3).to_string(index=False))
    else:
        print("\nno survivor: stage 2 and 3 have nothing to evaluate")
    _plot(df, q1, q2)
    print(f"\nsaved {OUT} and {PNG}")
    return 0


def _plot(df, q1, q2):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("Leelawadee UI", "Tahoma", "Segoe UI"):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f
            break
    fig, ax = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw=dict(height_ratios=[2, 1]))
    col = {0: "#9ad0a0", 1: "#f2df8a", 2: "#f0a09a"}
    for L in range(3):
        m = df.lvl == L
        ax[0].scatter(df.date[m], df.sigma[m], s=6, color=col[L], label=("ต่ำ", "กลาง", "สูง")[L])
    ax[0].axhline(q1, color="k", lw=0.6, ls=":"); ax[0].axhline(q2, color="k", lw=0.6, ls=":")
    ax[0].set_yscale("log"); ax[0].set_ylabel("ความผันผวนรายสัปดาห์ (bp, สเกลลอการิทึม)")
    ax[0].set_title("แผนที่สภาพตลาดทอง 2003-2026 — ต่ำ / กลาง / สูง (แบ่งเป็น 3 ส่วนเท่ากันตามความผันผวนรายสัปดาห์ตลอดประวัติ)")
    ax[0].legend(loc="upper right")
    yr = df[df.lvl.notna()].groupby([df.date.dt.year, "lvl"]).size().unstack(fill_value=0)
    yr = yr.div(yr.sum(axis=1), axis=0)
    yr.plot(kind="bar", stacked=True, ax=ax[1], color=[col[0], col[1], col[2]], legend=False, width=0.9)
    ax[1].set_ylabel("สัดส่วนสัปดาห์"); ax[1].set_xlabel("ปี")
    fig.tight_layout(); fig.savefig(PNG, dpi=110)


if __name__ == "__main__":
    sys.exit(main())
