"""Quarterly-resolution version of diagnose_grid_by_era.py.

The annual buckets (2022, 2023, 2024, 2025-partial, current-12mo) gave five data
points for "is the fixed grid's improving hit rate a real trend or noise."
Quarters give roughly 19 data points over the same real, verified history
(2021-01-03 to now - MT5 does not serve genuine continuous M5 further back;
see extend_canonical_history.py's finding that pre-2021 bars are one-per-day
placeholders with zero spread, not real M5). More points, same trustworthy
data, no new data source.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
import evolution_portfolio_audit as audit

MIN_TRADES = 15


def quarters(t0: int, t1: int):
    import datetime as dt
    d = dt.datetime.fromtimestamp(t0, dt.timezone.utc)
    y, q = d.year, (d.month - 1) // 3
    out = []
    while True:
        m0 = q * 3 + 1
        lo = dt.datetime(y, m0, 1, tzinfo=dt.timezone.utc)
        y2, m2 = (y, m0 + 3) if m0 + 3 <= 12 else (y + 1, m0 + 3 - 12)
        hi = dt.datetime(y2, m2, 1, tzinfo=dt.timezone.utc)
        lo_e, hi_e = int(lo.timestamp()), int(hi.timestamp())
        if lo_e >= t1:
            break
        out.append((f"{y}Q{q+1}", lo_e, min(hi_e, t1)))
        q += 1
        if q > 3:
            q = 0
            y += 1
    return out


def main() -> int:
    print("=" * 100)
    print("กริดคงที่ 8,250 ช่อง แยกรายไตรมาส (ต้นทุนจริงของโปรเจกต์)")
    print("=" * 100)

    bars = ch.load(Path("data/canonical_XAUUSD_M5.npz"))
    uni, meta = audit.load_universe(bars)
    print(f"ช่องทั้งหมด {len(uni):,}\n")

    print(f"{'ไตรมาส':10s}{'ช่องที่ประเมินได้':>16s}{'บวก%':>8s}{'ค่ากลาง':>10s}"
          f"{'เฉลี่ย':>10s}{'ไม้รวม':>10s}{'%Long':>8s}")
    print("-" * 80)
    rows = []
    for name, lo, hi in quarters(int(bars.t[0]), int(bars.t[-1]) + bars.step):
        means, n_long, n_short = [], 0, 0
        for tag, a in uni.items():
            m = (a["t_in"] >= lo) & (a["t_in"] < hi)
            n = int(m.sum())
            if n < MIN_TRADES:
                continue
            means.append(float(a["net"][m].mean()))
            d = a["direction"][m]
            n_long += int((d > 0).sum())
            n_short += int((d < 0).sum())
        if not means:
            print(f"{name:10s}  ไม้ไม่พอ")
            continue
        means = np.array(means)
        tot = n_long + n_short
        pos_pct = 100 * float(np.mean(means > 0))
        rows.append((name, len(means), pos_pct, float(np.median(means)),
                    float(np.mean(means)), tot,
                    100 * n_long / max(tot, 1)))
        print(f"{name:10s}{len(means):16,d}{pos_pct:7.1f}%{np.median(means):10.4f}"
              f"{np.mean(means):10.4f}{tot:10,d}{100*n_long/max(tot,1):7.1f}%")

    print("\nแนวโน้ม % ช่องที่เป็นบวก ตามลำดับเวลา:")
    print("  " + " -> ".join(f"{r[0]}={r[2]:.0f}%" for r in rows))

    xs = np.arange(len(rows))
    ys = np.array([r[2] for r in rows])
    if len(xs) > 3:
        slope, intercept = np.polyfit(xs, ys, 1)
        pred = slope * xs + intercept
        ss_res = float(np.sum((ys - pred) ** 2))
        ss_tot = float(np.sum((ys - ys.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        print(f"\nเส้นตรงที่ลากผ่านค่าเฉลี่ย (linear trend): "
              f"ชัน {slope:+.2f} จุด%/ไตรมาส   R^2 {r2:.3f}")
        print("  R^2 สูง = จุดข้อมูลเรียงตัวเป็นเส้นตรงชัด (แนวโน้มจริงมีโอกาสสูง)")
        print("  R^2 ต่ำ = จุดข้อมูลกระจัดกระจาย ไม่ใช่เส้นตรง (โน้มเอียงไปทางสุ่ม/รอบ)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
