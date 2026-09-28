"""WPWB_LIVE_PREREG.md amendment 4: Tests F and V on broker XAUUSD D1,
2016-08-09 .. 2020-11-27 (disjoint from the H1 run). Runs once."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import common as C  # noqa: E402
from oos_2016 import FOMC, statement_utc  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402

START = int(datetime(2016, 8, 9, tzinfo=timezone.utc).timestamp())
END = int(datetime(2020, 12, 4, tzinfo=timezone.utc).timestamp())   # H1 run starts at this cut


def fetch_d1():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        info = mt5.symbol_info("XAUUSD")
        r = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_D1, datetime(2016, 1, 1, tzinfo=timezone.utc),
                                 datetime(2021, 1, 1, tzinfo=timezone.utc))
        r = r[np.argsort(r["time"])]
        return (r["time"].astype(np.int64), r["open"], r["high"], r["low"], r["close"],
                np.maximum(r["spread"] * info.point, C.SPREAD_FLOOR))
    finally:
        mt5.shutdown()


def main() -> int:
    t, o, h, l, c, sp = fetch_d1()
    np.savez("data/fresh/XAUUSD_D1_2016_2020.npz", t=t, o=o, h=h, l=l, c=c, sp=sp)
    wd = ((t // 86400) + 3) % 7
    yr = pd.to_datetime(t, unit="s").year.to_numpy()
    print(f"D1 bars {len(t):,}: {pd.to_datetime(t[0], unit='s').date()} .. {pd.to_datetime(t[-1], unit='s').date()}; "
          f"weekday counts Mon..Sun {[int((wd == k).sum()) for k in range(7)]}")
    rngd = h - l

    # FOMC verification on D1
    fomc_days = {statement_utc(s) // 86400 for s in FOMC}
    verified = []
    print("\nFOMC verification on D1 (statement-day range vs median of non-FOMC Wednesdays, same year):")
    for s in FOMC:
        a = statement_utc(s)
        if not (START <= a < END):
            continue
        k = np.flatnonzero(t // 86400 == a // 86400)
        if len(k) == 0:
            print(f"  {s:18s} no D1 bar -> EXCLUDED"); continue
        k = int(k[0])
        ref = rngd[(wd == 2) & (yr == yr[k]) & ~np.isin(t // 86400, list(fomc_days))]
        ratio = rngd[k] / np.median(ref)
        ok = ratio > 1.0
        if ok:
            verified.append(a)
        print(f"  {s:18s} range ${rngd[k]:6.2f} = {ratio:4.2f}x {'OK' if ok else 'FAILED -> EXCLUDED'}")
    print(f"  verified {len(verified)} dates in the window")

    cut = _week_boundary(START)
    rows = []
    while cut + C.WEEK <= END:
        k = np.flatnonzero((t >= cut) & (t < cut + C.WEEK))
        if len(k) >= 4:
            lo, hi = int(k[0]), int(k[-1])
            nights = int(np.isin(wd[k], (0, 1, 2, 3)).sum())
            pnl = c[hi] - (o[lo] + sp[lo]) - C.FEES - C.SWAP_LONG * nights
            rows.append(dict(cut=cut, bp=pnl / o[lo] * 1e4,
                             fomc=any(cut <= a < cut + C.WEEK for a in verified)))
        cut += C.WEEK
    wk = pd.DataFrame(rows)

    dret = c / o - 1

    def sig_at(ct):
        mk = (t < ct) & (t >= ct - 26 * C.WEEK)
        if mk.sum() < 40:
            return np.nan
        w = 0.5 ** (((ct - t[mk]) / C.WEEK) / 13)
        r = dret[mk]; mu = (w * r).sum() / w.sum()
        return float(np.sqrt((w * (r - mu) ** 2).sum() / w.sum()))

    allcuts = [_week_boundary(START) + j * C.WEEK for j in range(-60, 300)]
    sig = {ct: sig_at(ct) for ct in allcuts}
    sz = []
    for ct in wk.cut:
        ref = [sig.get(int(ct) - j * C.WEEK, np.nan) for j in range(1, 53)]
        ref = [x for x in ref if np.isfinite(x)]
        s_now = sig.get(int(ct), np.nan)
        sz.append(min(2.0, np.median(ref) / s_now) if (len(ref) >= 8 and np.isfinite(s_now)) else np.nan)
    wk["size"] = sz
    print(f"\nweeks {len(wk)} ({pd.to_datetime(wk.cut.iloc[0], unit='s').date()} .. "
          f"{pd.to_datetime(wk.cut.iloc[-1], unit='s').date()}), FOMC weeks {int(wk.fomc.sum())}; "
          f"plain long {wk.bp.sum():+.0f} bp")

    rng = np.random.default_rng(2017)
    x = wk.bp.to_numpy(); f = wk.fomc.to_numpy()
    obs = x[f].mean() - x[~f].mean()
    perm = []
    for _ in range(20000):
        p = np.zeros(len(x), bool); p[rng.choice(len(x), f.sum(), replace=False)] = True
        perm.append(x[p].mean() - x[~p].mean())
    p_f = float((np.array(perm) <= obs).mean())
    lf, lo_ = (x[f] < 0).mean(), (x[~f] < 0).mean()
    print("\n== TEST F on D1 2016-08..2020-11")
    print(f"   FOMC weeks mean {x[f].mean():+.1f} bp (median {np.median(x[f]):+.1f}), losing {lf:.0%}")
    print(f"   other weeks mean {x[~f].mean():+.1f} bp (median {np.median(x[~f]):+.1f}), losing {lo_:.0%}")
    print(f"   difference {obs:+.1f} bp/week, one-sided p = {p_f:.3f} -> "
          f"{'PASS' if (p_f < 0.05 and lf > lo_) else 'FAIL'}")

    v = wk.dropna(subset=["size"])
    s, L = v["size"].to_numpy(), v.bp.to_numpy()
    ex = s * L - s.mean() * L
    pv = float((np.array([(rng.permutation(s) * L).sum() for _ in range(20000)]) >= (s * L).sum()).mean())
    wo3 = np.sort(ex)[:-3].sum()
    print("\n== TEST V on D1 2016-08..2020-11")
    print(f"   weeks {len(v)}, mean size {s.mean():.2f}; excess {ex.sum():+.0f} bp ({ex.mean():+.2f}/week); "
          f"size-permutation p = {pv:.3f}; without best 3 weeks {wo3:+.0f} bp -> "
          f"{'PASS' if (ex.sum() > 0 and pv < 0.05 and wo3 > 0) else 'FAIL'}")
    r2 = np.where(v.fomc.to_numpy(), 0.0, s * L)
    print(f"\ncontext: plain long {L.sum():+.0f} bp | VOLMAN {(s * L).sum():+.0f} | VOLMAN+skip FOMC {r2.sum():+.0f}")
    wk.to_csv("data/wpwb_oos_2016_d1_weekly.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
