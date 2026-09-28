"""Is XAUUSD history from 2009-03 enough? Arithmetic from data already held.

Uses Exness D1 (2016-08..) for weekly returns before true intraday data exists
and the WPWB weekly H1 series (2021-07..) for the current era. Nothing here is
a test of an edge; it sizes what a longer history can and cannot deliver.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402

Z = 1.96 + 0.84          # two-sided 5%, 80% power


def main() -> int:
    z = np.load(ROOT / "data" / "history" / "XAUUSD_D1.npz")
    d1 = pd.DataFrame({"c": z["c"], "sp": z["sp"]}, index=pd.to_datetime(z["t"], unit="s"))
    wk = d1.c.resample("W-FRI").last().dropna()
    r = np.log(wk).diff().dropna() * 1e4                     # weekly return, bp
    by_era = r.groupby(np.where(r.index < "2021-07-01", "2016-08..2021-06", "2021-07..2026-09"))
    print("weekly return SD (bp) from D1 closes:")
    for k, g in by_era:
        print(f"  {k}: SD {g.std():.0f} bp, n={len(g)}, mean {g.mean():+.1f}")
    sd_now = float(r[r.index >= "2021-07-01"].std())
    sd_old = float(r[r.index < "2021-07-01"].std())

    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    med = V.past_median52(rv)
    lab = np.array([V.label(rv[k] / med[k])[1] if np.isfinite(med[k]) else "U" for k in range(len(rv))])
    valid = lab != "U"
    hi = np.isin(lab, ["HIGH", "EXTREME"])[valid]
    onsets = int((hi & ~np.r_[False, hi[:-1]]).sum())
    rate = onsets / valid.sum()
    print(f"\ncurrent era: {valid.sum()} labelled weeks, {hi.sum()} volatile, {onsets} episodes "
          f"-> {rate:.3f} episode starts per week")

    spans = {"Exness intraday 2021-07..": 273, "HistData M1 2009-03..": 914, "Dukascopy H1 2003-05..": 1221}
    print("\nweeks, expected volatile episodes, and smallest weekly edge detectable "
          "(5% two-sided, 80% power; weekly SD of a full-week gold position):")
    for name, n in spans.items():
        mde_now = Z * sd_now / math.sqrt(n)
        mde_mix = Z * (sd_old if n > 273 else sd_now) / math.sqrt(n)
        print(f"  {name:28s} weeks {n:5d}  episodes ~{rate * (n - 52):4.0f}  "
              f"MDE {mde_now:5.1f} bp/week at today's SD, {mde_mix:5.1f} at era SD")
    print("\nfor the edge sizes this project cares about (10-20 bp/week), weeks needed at today's SD:")
    for e in (10, 15, 20):
        print(f"  {e} bp/week: {math.ceil((Z * sd_now / e) ** 2):,} weeks "
              f"(~{(Z * sd_now / e) ** 2 / 52:.0f} years)")
    sp = d1.sp.groupby(d1.index.year).median()
    px = d1.c.groupby(d1.index.year).median()
    print("\nmedian D1 spread by year (Exness, $ and bp of price):")
    for y in sp.index:
        print(f"  {y}: ${sp[y]:.3f} at ~${px[y]:,.0f} = {sp[y] / px[y] * 1e4:.1f} bp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
