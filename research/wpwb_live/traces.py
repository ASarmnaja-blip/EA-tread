"""WPWB trace metrics: what did the market 'reward' each week, and does that
carry over to the next week? (the premise WPWB rests on)

Weekly (Friday 22:15 UTC boundary) metrics from XAUUSD M5 log returns:
  ac1_m5/m15/h1  lag-1 autocorrelation within the week (+ = continuation,
                 - = reversal) at each horizon
  vr_m15/vr_h1   variance ratio vs M5 (>1 trending intraday, <1 reverting)
  rv             realised M5 volatility
  drift_asia/lon/ny   summed log return per UTC session
  week_ret       whole-week return
  dxy_corr       H1 return correlation XAU vs DXY (from 2023-09, fresh data)
Persistence = Spearman rank correlation of metric(week w) with metric(w+1),
and with a 4-week decay-weighted mean of weeks <= w. Reported per era.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "pilot"))
import historical_regime_walkforward as hist  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402

WEEK = 7 * 86400


def load_xau():
    b5 = hist.load_history()
    f = np.load("data/fresh/XAUUSD_M5.npz")
    keep = f["t"] > b5.t[-1]
    t = np.r_[b5.t, f["t"][keep]]
    c = np.r_[b5.c, f["c"][keep]]
    sp = np.r_[np.maximum(b5.sp, 0.09), np.maximum(f["sp"][keep], 0.09)]
    return t.astype(np.int64), c, sp


def contiguous_returns(t, c, step):
    r = np.diff(np.log(c))
    ok = np.diff(t) == step
    return r, ok


def block_returns(t, c, k):
    """Non-overlapping k-bar returns from contiguous runs of M5 bars."""
    n = len(t)
    starts = np.arange(0, n - k, k)
    ends = starts + k
    ok = (t[ends] - t[starts]) == k * 300
    r = np.log(c[ends] / c[starts])
    return r[ok]


def ac1(x):
    if len(x) < 20 or x.std() == 0:
        return np.nan
    return float(np.corrcoef(x[1:], x[:-1])[0, 1])


def week_metrics(t, c, lo, hi, dxy=None):
    tt, cc = t[lo:hi], c[lo:hi]
    if len(tt) < 500:
        return None
    r5, ok = contiguous_returns(tt, cc, 300)
    r5 = r5[ok]
    r15 = block_returns(tt, cc, 3)
    r60 = block_returns(tt, cc, 12)
    v5 = r5.var()
    hrs = (tt[:-1] % 86400) // 3600
    hrs = hrs[ok]
    asia = np.isin(hrs, (22, 23, 0, 1, 2, 3, 4, 5, 6))
    lon = (hrs >= 7) & (hrs <= 12)
    ny = (hrs >= 13) & (hrs <= 20)
    out = dict(ac1_m5=ac1(r5), ac1_m15=ac1(r15), ac1_h1=ac1(r60),
               vr_m15=float(r15.var() / (3 * v5)) if v5 > 0 else np.nan,
               vr_h1=float(r60.var() / (12 * v5)) if v5 > 0 else np.nan,
               rv=float(np.sqrt(v5)),
               drift_asia=float(r5[asia].sum()), drift_lon=float(r5[lon].sum()),
               drift_ny=float(r5[ny].sum()), week_ret=float(np.log(cc[-1] / cc[0])))
    if dxy is not None:
        dt, dc = dxy
        a = np.searchsorted(dt, tt[0]); b = np.searchsorted(dt, tt[-1])
        if b - a > 500:
            hx = tt[::12]; hd = dt[a:b:12]
            common, ia, ib = np.intersect1d(hx, hd, return_indices=True)
            if len(common) > 30:
                xc = cc[::12][ia]; yc = dc[a:b:12][ib]
                rx = np.diff(np.log(xc)); ry = np.diff(np.log(yc))
                out["dxy_corr"] = float(np.corrcoef(rx, ry)[0, 1])
    return out


def main() -> int:
    t, c, _ = load_xau()
    d = np.load("data/fresh/DXY_M5.npz")
    dxy = (d["t"], d["c"])
    cut = _week_boundary(int(t[0]))
    rows = []
    while cut < t[-1]:
        lo = int(np.searchsorted(t, cut)); hi = int(np.searchsorted(t, cut + WEEK))
        m = week_metrics(t, c, lo, hi, dxy if cut >= d["t"][0] else None)
        if m:
            m["cut"] = cut
            rows.append(m)
        cut += WEEK
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df.cut, unit="s").dt.date
    df.to_csv("data/wpwb_traces.csv", index=False)
    print(f"weeks with metrics: {len(df)} ({df.date.iloc[0]} .. {df.date.iloc[-1]})\n")

    metrics = ["ac1_m5", "ac1_m15", "ac1_h1", "vr_m15", "vr_h1", "rv",
               "drift_asia", "drift_lon", "drift_ny", "week_ret", "dxy_corr"]
    eras = {"2021-07..2023-12": df.cut < 1704067200,
            "2024-01..2026-09": df.cut >= 1704067200,
            "all": np.ones(len(df), bool)}
    print(f"{'metric':12s}" + "".join(f"{e:>22s}" for e in eras))
    print(f"{'':12s}" + "".join(f"{'next-wk rho (p)':>22s}" for _ in eras))
    for mname in metrics:
        line = f"{mname:12s}"
        for e, mask in eras.items():
            x = df.loc[mask, mname].to_numpy()
            a, b = x[:-1], x[1:]
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() < 20:
                line += f"{'n/a':>22s}"
                continue
            rho, p = stats.spearmanr(a[ok], b[ok])
            line += f"{rho:+13.3f} ({p:.3f})"
        print(line)
    print("\nlevel of each metric (mean, and share of weeks > 0 / > 1 for vr):")
    for mname in metrics:
        x = df[mname].dropna()
        extra = f" share>1={float((x > 1).mean()):.2f}" if mname.startswith("vr") else \
                f" share>0={float((x > 0).mean()):.2f}"
        rec = df.loc[eras["2024-01..2026-09"], mname].dropna()
        print(f"  {mname:12s} mean_all={x.mean():+.5f} mean_recent={rec.mean():+.5f}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
