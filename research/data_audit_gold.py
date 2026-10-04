#!/usr/bin/env python3
"""Is the downloaded gold data sound, and is the data the H4 tests used complete?

1. Dukascopy M1 (hourly closes) against two independent sources: Candle Lab
   H1 and the user's broker MT5 H1, per year.
2. H1 bars per year in the spliced history (stress_top3.spliced_h1) that every
   "2009-2026" H4 result was computed on.
3. Gold volatility per year, to show how far today's regime sits from the past.

Usage: python3 data_audit_gold.py --root <data-snapshot checkout>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
CACHE = HERE / ".cache_duka"


def hourly_from_m1(yr):
    p = CACHE / f"XAUUSD_M1_{yr}.parquet"
    if not p.exists():
        return None
    m = pd.read_parquet(p)
    m = m[m.bid_high > m.bid_low]
    return ((m.bid_close + m.ask_close) / 2).resample("1h").last().dropna(), m


def compare(hc, src):
    j = hc.index.intersection(src.index)
    if len(j) < 50:
        return dict(matched=int(len(j)))
    d = np.abs(hc.reindex(j).values - src.reindex(j).values)
    return dict(matched=int(len(j)), median_usd=float(np.median(d)),
                p99_bp=float(np.quantile(d / hc.reindex(j).values, 0.99) * 1e4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    sys.path[:0] = [str(root / "research" / "grid27k"), str(root / "research" / "grid768")]
    import stress_top3 as S

    def series(z):
        return pd.Series(z["c"].astype(float),
                         index=pd.to_datetime(z["t"].astype(np.int64), unit="s", utc=True))

    cl = series(np.load(root / "data" / "bundle" / "bars_XAUUSD_H1.npz"))
    mt = series(np.load(root / "data" / "mt5" / "XAUUSD_H1.npz"))
    out = dict(duka_vs=[], spliced_bars={}, volatility={})
    print("Dukascopy vs independent sources (hourly closes)")
    for yr in range(2009, 2027):
        r = hourly_from_m1(yr)
        if r is None:
            continue
        hc, m = r
        sp = (m.ask_close - m.bid_close)
        row = dict(year=yr, hours=len(hc), spread_median=float(sp.median()),
                   candlelab=compare(hc, cl), mt5=compare(hc, mt))
        out["duka_vs"].append(row)
        print(f"  {yr}: Candle Lab {row['candlelab']}  MT5 {row['mt5']}  "
              f"spread median ${row['spread_median']:.2f}")
    print("\nH1 bars per year in the spliced history the H4 tests used")
    for mk in ("XAUUSD", "XAGUSD", "BTCUSD"):
        b = S.spliced_h1(mk)
        y = pd.Series(pd.to_datetime(b["t"], unit="s").year).value_counts().sort_index()
        out["spliced_bars"][mk] = {int(k): int(v) for k, v in y.items()}
        print(f"  {mk}: " + ", ".join(f"{k}:{v}" for k, v in y.items() if k >= 2015))
    h = pd.read_parquet(CACHE / "XAUUSD_H1_2003_2026.parquet")
    mid = (h.bid_close + h.ask_close) / 2
    rng = (h.bid_high + h.ask_high) / 2 - (h.bid_low + h.ask_low) / 2
    dr = np.log(mid.resample("1D").last().dropna()).diff()
    print("\nGold volatility by year")
    for yr in range(2009, 2027):
        s = rng[(rng.index.year == yr) & (rng > 0)]
        v = float(dr[dr.index.year == yr].std() * np.sqrt(252) * 100)
        out["volatility"][yr] = dict(h1_range_usd=float(s.mean()),
                                     h1_range_pct=float((s / mid.reindex(s.index)).mean() * 100),
                                     annual_vol_pct=v)
        print(f"  {yr}: H1 range ${s.mean():6.2f}  annual vol {v:5.1f}%")
    (HERE / "data_audit_gold.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
