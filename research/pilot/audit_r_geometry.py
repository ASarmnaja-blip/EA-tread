"""The audit Part 11 flagged and nobody ran: do the six declared setup
families fire preferentially at particular ATR levels?

Why it decides everything downstream. The project's edge unit is
R = price move / stop distance, and the stop is k x ATR. If a family fires
when ATR is unusually LOW, its denominator is small, so the same dollar move
scores a larger R than an unmatched control drawn from all bars — an edge that
is geometry, not skill. The sibling program's +0.0171 R fell to +0.0026 R once
its control was ATR-matched, and one family turned negative.

This script only MEASURES the skew and its size. It does not re-run any
strategy and claims no edge. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core  # noqa: E402
import historical_regime_walkforward as hist  # noqa: E402
import mtf_engine as E  # noqa: E402

OUT = HERE.parents[1] / "data" / "r_geometry_audit.xlsx"
ERAS = {"2021-07..2023-12": ("2021-07-01", "2024-01-01"),
        "2024-01..2026-09": ("2024-01-01", "2026-10-01"),
        "all 2021-07..2026-09": ("2021-07-01", "2026-10-01")}


def main() -> int:
    import os
    os.chdir(HERE.parents[1])
    b5 = hist.load_history()
    b15, nxt5 = E.resample(b5, 3)
    c = core.Ctx(b15, nxt5)
    t = pd.to_datetime(b15.t, unit="s")
    atr_pct = c.atr_pct
    atr = c.atr

    rows = []
    for fam in E.SETUPS:
        sig = E.setup_signals(fam, c)
        idx = np.array([s[0] for s in sig], dtype=int)
        idx = idx[(idx >= c.warm) & (idx < len(b15))]
        for era, (a, b) in ERAS.items():
            m_all = (t >= a) & (t < b) & np.isfinite(atr_pct) & (np.arange(len(b15)) >= c.warm)
            sel = idx[(t[idx] >= a) & (t[idx] < b) & np.isfinite(atr_pct[idx])]
            if len(sel) < 50:
                continue
            base = atr_pct[m_all]
            fam_pct = atr_pct[sel]
            # how much smaller/larger is the stop denominator at signal bars?
            ratio = np.median(atr[sel]) / np.median(atr[m_all])
            rows.append({
                "family": fam, "era": era, "signals": len(sel),
                "median ATR pct-rank at signal": round(float(np.median(fam_pct)), 1),
                "median ATR pct-rank all bars": round(float(np.median(base)), 1),
                "ATR ratio signal/all": round(float(ratio), 3),
                "R inflation from geometry (x)": round(float(1 / ratio), 3),
                "share of signals in bottom ATR third": round(float((fam_pct < 33.3).mean()), 3),
                "share in top ATR third": round(float((fam_pct > 66.7).mean()), 3)})
    df = pd.DataFrame(rows)
    df.to_excel(OUT, index=False)
    pd.set_option("display.width", 240)
    for era in ERAS:
        sub = df[df.era == era]
        if len(sub):
            print(f"\n=== {era} ===")
            print(sub.drop(columns="era").to_string(index=False))
    print(f"\nsaved {OUT}")
    print("\nReading: 'R inflation from geometry' > 1 means the family fires where ATR is")
    print("smaller than average, so its stop is tighter and the SAME dollar move is")
    print("recorded as a bigger R than an unmatched control would score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
