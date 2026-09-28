"""WPWB_LIVE_PREREG.md amendment 3: single out-of-era test of the FOMC rule
and VOLMAN on broker XAUUSD H1, 2016-08-09 .. 2021-12-31 (never examined)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
import common as C  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402

ET = ZoneInfo("America/New_York")
# FOMC statement dates (14:00 ET unless noted), entered by hand and verified
# against price below before use. 2020-03-15 was a Sunday emergency move
# announced with the market closed: unverifiable, therefore excluded.
FOMC = [
    "2016-09-21", "2016-11-02", "2016-12-14",
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14", "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-03-03@10:00", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05",
    "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
]
END = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())


def fetch_h1():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        info = mt5.symbol_info("XAUUSD")
        chunks = []
        for y in range(2016, 2022):
            r = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, datetime(y, 1, 1, tzinfo=timezone.utc),
                                     datetime(y + 1, 1, 8, tzinfo=timezone.utc))
            if r is not None and len(r):
                chunks.append(r)
        r = np.concatenate(chunks)
        r = r[np.argsort(r["time"])]
        r = r[np.r_[True, r["time"][1:] != r["time"][:-1]]]
        return (r["time"].astype(np.int64), r["open"], r["high"], r["low"], r["close"],
                np.maximum(r["spread"] * info.point, C.SPREAD_FLOOR))
    finally:
        mt5.shutdown()


def statement_utc(s):
    day, _, hm = s.partition("@")
    hh, mm = (int(x) for x in (hm or "14:00").split(":"))
    y, m, d = (int(x) for x in day.split("-"))
    return int(datetime(y, m, d, hh, mm, tzinfo=ET).timestamp())


def main() -> int:
    t, o, h, l, c, sp = fetch_h1()
    np.savez("data/fresh/XAUUSD_H1_2016_2021.npz", t=t, o=o, h=h, l=l, c=c, sp=sp)
    keep = t < END + 7 * 86400
    t, o, h, l, c, sp = t[keep], o[keep], h[keep], l[keep], c[keep], sp[keep]
    print(f"H1 bars {len(t):,}: {pd.to_datetime(t[0], unit='s')} .. {pd.to_datetime(t[-1], unit='s')}")
    rng_ = h - l
    hour = (t % 86400) // 3600
    wday = ((t // 86400) + 3) % 7
    year = pd.to_datetime(t, unit="s").year.to_numpy()

    # ---- verify each hand-entered FOMC date against the data
    ann = [statement_utc(s) for s in FOMC]
    ann_bar = {}
    print("\nFOMC date verification (statement-hour H1 range vs median same hour, non-FOMC Wednesdays, same year):")
    ok_n = 0
    fomc_days = {a // 86400 for a in ann}
    for s, a in zip(FOMC, ann):
        k = int(np.searchsorted(t, a - (a % 3600), side="left"))
        if k >= len(t) or t[k] != a - (a % 3600):
            print(f"  {s:18s} no bar at the statement hour -> EXCLUDED")
            continue
        hh = hour[k]; yy = year[k]
        ref = rng_[(hour == hh) & (wday == 2) & (year == yy)
                   & ~np.isin(t // 86400, list(fomc_days))]
        ratio = rng_[k] / np.median(ref)
        ok = ratio > 1.0
        ok_n += ok
        if ok:
            ann_bar[s] = a
        print(f"  {s:18s} {pd.to_datetime(t[k], unit='s'):%a %H:%M} UTC range ${rng_[k]:5.2f} = "
              f"{ratio:4.1f}x median {'OK' if ok else 'FAILED -> EXCLUDED'}")
    print(f"  verified {ok_n} of {len(FOMC)} (2020-03-15 Sunday emergency move not listed: market closed)")

    # ---- weekly long, Sunday open -> Friday close
    cut = _week_boundary(int(t[0]))
    rows = []
    while cut + C.WEEK <= END + 86400 * 2:
        lo = int(np.searchsorted(t, cut)); hi = int(np.searchsorted(t, cut + C.WEEK - C.HOUR, side="right"))
        if hi - lo >= 50:
            entry = o[lo] + sp[lo]
            n = int(C.rollover_nights_vec([t[lo]], [t[hi - 1] + C.HOUR - 1])[0])
            pnl = c[hi - 1] - entry - C.FEES - C.SWAP_LONG * n
            fomc_wk = any(cut <= a < cut + C.WEEK for a in ann_bar.values())
            rows.append(dict(cut=cut, bp=pnl / o[lo] * 1e4, fomc=fomc_wk))
        cut += C.WEEK
    wk = pd.DataFrame(rows)

    # daily sigma (hl 13 weeks over trailing 26 weeks) and VOLMAN size, causal
    day = t // 86400
    ud, first = np.unique(day, return_index=True)
    last = np.r_[first[1:] - 1, len(t) - 1]
    dret = c[last] / o[first] - 1; dts = t[first]

    def sig_at(ct):
        mk = (dts < ct) & (dts >= ct - 26 * C.WEEK)
        if mk.sum() < 40:
            return np.nan
        w = 0.5 ** (((ct - dts[mk]) / C.WEEK) / 13)
        r = dret[mk]; mu = (w * r).sum() / w.sum()
        return float(np.sqrt((w * (r - mu) ** 2).sum() / w.sum()))

    sig = {int(ct): sig_at(int(ct)) for ct in wk.cut}
    sizes = []
    for ct in wk.cut:
        ref = [sig.get(int(ct) - j * C.WEEK) for j in range(1, 53)]
        ref = [x for x in ref if x is not None and np.isfinite(x)]
        s_now = sig[int(ct)]
        sizes.append(min(2.0, np.median(ref) / s_now) if (len(ref) >= 8 and np.isfinite(s_now)) else np.nan)
    wk["size"] = sizes
    print(f"\nweeks {len(wk)} ({pd.to_datetime(wk.cut.iloc[0], unit='s').date()} .. "
          f"{pd.to_datetime(wk.cut.iloc[-1], unit='s').date()}), FOMC weeks {int(wk.fomc.sum())}; "
          f"plain long total {wk.bp.sum():+.0f} bp")

    rng = np.random.default_rng(2016)
    # ---- Test F
    f = wk.fomc.to_numpy(); x = wk.bp.to_numpy()
    obs = x[f].mean() - x[~f].mean()
    perm = np.array([x[p].mean() - x[~p].mean() for p in
                     (np.isin(np.arange(len(x)), rng.choice(len(x), f.sum(), replace=False))
                      for _ in range(20000))])
    p_f = float((perm <= obs).mean())
    lose_f, lose_o = (x[f] < 0).mean(), (x[~f] < 0).mean()
    pass_f = p_f < 0.05 and lose_f > lose_o
    print("\n== TEST F (FOMC weeks worse for longs?)")
    print(f"   FOMC weeks mean {x[f].mean():+.1f} bp (median {np.median(x[f]):+.1f}), losing {lose_f:.0%}")
    print(f"   other weeks mean {x[~f].mean():+.1f} bp (median {np.median(x[~f]):+.1f}), losing {lose_o:.0%}")
    print(f"   difference {obs:+.1f} bp/week, one-sided permutation p = {p_f:.3f} -> "
          f"{'PASS' if pass_f else 'FAIL'}")

    # ---- Test V
    v = wk.dropna(subset=["size"])
    s, L = v["size"].to_numpy(), v.bp.to_numpy()
    ex = s * L - s.mean() * L
    perm_v = np.array([(rng.permutation(s) * L).sum() for _ in range(20000)])
    p_v = float((perm_v >= (s * L).sum()).mean())
    ex_wo3 = np.sort(ex)[:-3].sum()
    pass_v = ex.sum() > 0 and p_v < 0.05 and ex_wo3 > 0
    print("\n== TEST V (VOLMAN beats exposure-matched long?)")
    print(f"   weeks {len(v)}, mean size {s.mean():.2f}; excess total {ex.sum():+.0f} bp "
          f"({ex.mean():+.2f} bp/week); size-permutation p = {p_v:.3f}; "
          f"excess without its best 3 weeks {ex_wo3:+.0f} bp -> {'PASS' if pass_v else 'FAIL'}")

    # context only
    r2 = np.where(v.fomc.to_numpy(), 0.0, s * L)
    print(f"\ncontext: plain long {L.sum():+.0f} bp | VOLMAN {(s * L).sum():+.0f} bp | "
          f"VOLMAN + skip FOMC {r2.sum():+.0f} bp over the same {len(v)} weeks")
    wk.to_csv("data/wpwb_oos_2016_weekly.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
