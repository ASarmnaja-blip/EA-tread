"""EXPLORATION, weird batch (operator 2026-10-01: "ทำอะไรแปลกๆไปก่อน ค่อยมาหาเหตุผลเอาทีหลัง"). Twenty quick rules (macro, COT, lunar,
seasonal, calendar, intraday patterns). For each: both directions are run on gold DEV (2004-15 or the series start); the better DEV direction is
kept (flip if worse); then gold CHECK (2016-26) and silver (2010-26) are read, with the same-direction random-timing control.
Exploratory only: survivors need a confirmation. Usage: python research/hyp/explore_weird.py -> data/hyp/explore_weird.csv"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import batch2 as B2  # noqa: E402
import batch3 as B3  # noqa: E402
import batch5 as B5  # noqa: E402
import macro_data as MD  # noqa: E402


def daily_from(series_avail, mask, dirs, M, hold, k):
    return B2.daily_rule(M, series_avail[mask], dirs, hold, k)


def macro_rules():
    R = {}
    ry = MD.fred("DFII10"); d1 = ry.value.diff().to_numpy()
    q05 = B2.causal_q(d1, 0.05); q95 = B2.causal_q(d1, 0.95)
    m = np.isfinite(q05) & (d1 <= q05); R["REAL_YIELD_DROP"] = (ry.avail.to_numpy()[m], np.ones(int(m.sum())), 5, 2)
    m = np.isfinite(q95) & (d1 >= q95); R["REAL_YIELD_RISE"] = (ry.avail.to_numpy()[m], np.ones(int(m.sum())), 5, 2)
    be = MD.fred("T10YIE"); c20 = be.value.diff(20).to_numpy(); m = np.isfinite(c20) & (c20 != 0)
    R["BREAKEVEN_TREND"] = (be.avail.to_numpy()[m][::20], np.sign(c20[m])[::20], 20, 3)
    rt = ry.value.diff(20).to_numpy(); m = np.isfinite(rt) & (rt != 0)
    R["REAL_YIELD_TREND"] = (ry.avail.to_numpy()[m][::20], -np.sign(rt[m])[::20], 20, 3)
    vx = MD.fred("VIXCLS"); lv = np.log(vx.value).diff().to_numpy(); q = B2.causal_q(lv, 0.975); m = np.isfinite(q) & (lv >= q)
    R["VIX_SPIKE"] = (vx.avail.to_numpy()[m], np.ones(int(m.sum())), 5, 2)
    m = (vx.value.to_numpy() > 30) & (vx.value.shift(1).to_numpy() <= 30)
    R["VIX_ABOVE_30"] = (vx.avail.to_numpy()[m], np.ones(int(m.sum())), 10, 3)
    y2 = MD.fred("DGS2"); dy = y2.value.diff().to_numpy(); q = B2.causal_q(dy, 0.975); m = np.isfinite(q) & (dy >= q)
    R["Y2_HAWKISH_SHOCK"] = (y2.avail.to_numpy()[m], np.ones(int(m.sum())), 5, 2)
    dx = MD.fred("DTWEXBGS"); c60 = np.log(dx.value).diff(60).to_numpy(); m = np.isfinite(c60) & (c60 != 0)
    R["BROAD_DOLLAR_TREND"] = (dx.avail.to_numpy()[m][::20], -np.sign(c60[m])[::20], 20, 3)
    ct = MD.cftc_gold(); sh = ct.nc_share.to_numpy()
    hi = B2.causal_q(sh, 0.90, n=156, minn=104); lo = B2.causal_q(sh, 0.10, n=156, minn=104)
    m = np.isfinite(hi) & (sh >= hi); R["COT_CROWDED_LONG"] = (ct.avail.to_numpy()[m], np.ones(int(m.sum())), 20, 3)
    m = np.isfinite(lo) & (sh <= lo); R["COT_WASHOUT"] = (ct.avail.to_numpy()[m], np.ones(int(m.sum())), 20, 3)
    cz = (ct.c_net - ct.c_net.rolling(156, min_periods=104).mean().shift(1)) / ct.c_net.rolling(156, min_periods=104).std().shift(1)
    m = (cz >= 2).to_numpy(); R["COT_HEDGERS_LESS_SHORT"] = (ct.avail.to_numpy()[m], np.ones(int(m.sum())), 20, 3)
    return R


def d1_rules(M):
    """Rules built on the market's own D1 bars: returns {name: (B, events dict, hold, k)} with direction +1 placeholders."""
    D = M["D1"]; lab = B3.day_label(D); n = len(D.t); out = {}
    ref = pd.Timestamp("2000-01-06 18:14").value / 1e9; syn = 29.530588 * 86400
    phase = ((D.t - ref) / syn) % 1.0
    newm = np.flatnonzero((phase < 0.1) & (np.r_[1.0, phase[:-1]] >= 0.9))            # first bar of each new-moon window
    out["LUNAR_NEW_MOON"] = (newm, 5, 2)
    ym = (lab.year * 100 + lab.month).to_numpy()
    first = np.flatnonzero(np.r_[True, ym[1:] != ym[:-1]])
    out["DAY_OF_MONTH_1_5"] = (first, 5, 2)
    ret = np.r_[np.nan, np.diff(np.log(D.c))]
    mo = pd.Series(ret).groupby([lab.year.to_numpy(), lab.month.to_numpy()]).sum()
    seas_e, seas_d = [], []
    for i in first:
        y, mth = lab.year[i], lab.month[i]
        past = [mo.get((y - j, mth), np.nan) for j in range(1, 11)]
        past = [x for x in past if np.isfinite(x)]
        if len(past) >= 5 and np.mean(past) != 0:
            seas_e.append(i); seas_d.append(np.sign(np.mean(past)))
    out["SEASONAL_MOMENTUM"] = (np.array(seas_e, int), 20, 3, np.array(seas_d))
    mtd_e, mtd_d = [], []
    for j, i in enumerate(first):
        k = i + 10
        nxt = first[j + 1] if j + 1 < len(first) else n
        if k < nxt and k < n - 1:
            r = np.log(D.c[k - 1] / D.o[i])
            if r != 0:
                mtd_e.append(k); mtd_d.append(np.sign(r))
    out["MTD_MOMENTUM"] = (np.array(mtd_e, int), 8, 3, np.array(mtd_d))
    rng = D.h - D.l
    shock = np.flatnonzero(np.abs(D.c - D.o) >= 3 * D.atr) + 1
    out["SHOCK_FOLLOW"] = (shock[shock < n], 5, 2, np.sign((D.c - D.o)[shock[shock < n] - 1]))
    v = getattr(D, "v", None)
    hh20 = pd.Series(D.h).rolling(20).max().shift(1).to_numpy(); ll20 = pd.Series(D.l).rolling(20).min().shift(1).to_numpy()
    fib = ll20 + 0.382 * (hh20 - ll20)                                               # 61.8 % retracement of the 20-day range
    up = (D.c > pd.Series(D.c).shift(20).to_numpy())
    with np.errstate(invalid="ignore"):
        fx = np.flatnonzero(up & (D.l <= fib) & (np.r_[np.inf, D.l[:-1]] > np.r_[np.inf, fib[:-1]])) + 1
    out["FIB_618_IN_UPTREND"] = (fx[fx < n], 5, 2)
    return out


def h1_rules(M):
    H = M["H1"]; u = pd.to_datetime(H.t, unit="s"); hr = u.hour.to_numpy(); day = (H.t // 86400)
    out_e, out_d = [], []
    df = pd.DataFrame(dict(day=day, hr=hr, h=H.h, l=H.l, c=H.c, i=np.arange(len(H.t))))
    for dd, g in df.groupby("day"):
        a = g[g.hr < 7]
        if len(a) < 5:
            continue
        hi, lo = a.h.max(), a.l.min()
        b = g[(g.hr >= 7) & (g.hr < 12)]
        for _, r in b.iterrows():
            if r.c > hi:
                out_e.append(int(r.i) + 1); out_d.append(1.0); break
            if r.c < lo:
                out_e.append(int(r.i) + 1); out_d.append(-1.0); break
    return {"ASIAN_RANGE_BREAKOUT": (np.array(out_e, int), 6, 1.0, np.array(out_d))}


def run_rule(Gd, Sv, build_g, build_s, hold, k):
    best = None
    for s in (1, -1):
        r = B3.evaluate(Gd, Sv, lambda M, s=s: build_g(M, s) if M["sym"] == "XAUUSD" else build_s(M, s), hold, k)
        if best is None or r["DEV"]["mean_R"] > best[1]["DEV"]["mean_R"]:
            best = (s, r)
    return best


def main():
    t0 = time.time()
    Gd = B5.light_gold(); Sv = B5.light_silver()
    rows = []
    for name, (av, dirs, hold, k) in macro_rules().items():
        b = lambda M, s, av=av, dirs=dirs, hold=hold, k=k: B2.daily_rule(M, av, s * dirs, hold, k)
        s, r = run_rule(Gd, Sv, b, b, hold, k)
        rows.append((name, s, r))
        print(f"{name} done ({time.time() - t0:.0f}s)", flush=True)
    dg, ds = d1_rules(Gd), d1_rules(Sv)
    for name in dg:
        spec_g, spec_s = dg[name], ds[name]
        hold, k = spec_g[1], spec_g[2]

        def mk(M, s, spec):
            e = spec[0]; D = M["D1"]; e = e[e < len(D.t) - spec[1] - 1]
            dirs = spec[3][:len(spec[0])][spec[0] < len(D.t) - spec[1] - 1] if len(spec) > 3 else np.ones(len(e))
            return D, dict(e=e, d=s * dirs, stop=spec[2] * D.atr[e], tgt=np.full(len(e), np.nan), last=e + spec[1] - 1)
        s, r = run_rule(Gd, Sv, lambda M, s: mk(M, s, spec_g), lambda M, s: mk(M, s, spec_s), hold, k)
        rows.append((name, s, r))
        print(f"{name} done ({time.time() - t0:.0f}s)", flush=True)
    hg, hs = h1_rules(Gd), h1_rules(Sv)
    for name in hg:
        spec_g, spec_s = hg[name], hs[name]

        def mkh(M, s, spec):
            e, hold, k, dirs = spec; H = M["H1"]; ok = e < len(H.t) - hold - 1
            e = e[ok]; dirs = dirs[ok]
            return H, dict(e=e, d=s * dirs, stop=k * H.atr[e], tgt=np.full(len(e), np.nan), last=e + hold - 1)
        s, r = run_rule(Gd, Sv, lambda M, s: mkh(M, s, spec_g), lambda M, s: mkh(M, s, spec_s), spec_g[1], spec_g[2])
        rows.append((name, s, r))
        print(f"{name} done ({time.time() - t0:.0f}s)", flush=True)
    out = []
    for name, s, r in rows:
        out.append(dict(rule=name, sign=s, dev_n=r["DEV"]["n"], dev_R=r["DEV"]["mean_R"], dev_p=min(1, 2 * r["DEV"]["p"]), check_n=r["CHECK"]["n"],
                        check_R=r["CHECK"]["mean_R"], check_p=r["CHECK"]["p"], check_excess=r["CHECK"]["excess"], silver_n=r["SILVER"]["n"],
                        silver_R=r["SILVER"]["mean_R"], silver_p=r["SILVER"]["p"], silver_excess=r["SILVER"]["excess"]))
    T = pd.DataFrame(out)
    T["consistent"] = (T.dev_R > 0) & (T.check_R > 0) & (T.silver_R > 0) & (T.check_excess > 0) & (T.silver_excess > 0)
    T.to_csv(B1.OUT / "explore_weird.csv", index=False)
    pd.set_option("display.width", 250)
    print(T.round(3).sort_values(["consistent", "check_R"], ascending=False).to_string(index=False))
    print(f"consistent (positive and above random timing in DEV, CHECK and SILVER): {int(T.consistent.sum())} of {len(T)} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
