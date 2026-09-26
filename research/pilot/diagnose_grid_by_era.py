"""Does the FIXED, pre-registered 8,250-cell grid (Amendment 14, test-covered)
itself contain money-making information in 2022-2025, independent of any
particular weekly-selection algorithm's quality?

Uses the freshly-built demo90-cost universe cache (the project's real Demo cost
model: spread 0.090, commission 0.140 - not Codex's cent260 exploration
profile). Read-only against Codex's cache file; no selection logic from
weekly_evolution_grid.py or compound_bar_replay.py is used or trusted here.

For each cell with enough trades in an era, compute its own net R mean. Then
report, across the whole grid: the share of cells net-positive, the median and
mean cell performance, and the long/short trade-count split. If the fixed rule
set itself is flat-to-negative across most cells in 2022-2025 despite the market
genuinely trending in that window (already shown in diagnose_2022_2025_loss.py),
that points at the mechanical rules lacking information, not at the market being
unreadable in some special sense - which would match every prior closure in this
project (Amendments 07, 09, 10, 11, 13).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
import evolution_portfolio_audit as audit

DAY = 86400
MIN_TRADES = 15

ERAS = [
    ("2022", "2022-01-01", "2023-01-01"),
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2025 Jan-Sep", "2025-01-01", "2025-09-21"),
    ("LOSING WINDOW 2022-01..2025-09-21", "2022-01-01", "2025-09-21"),
    ("CURRENT trailing 12mo", "2025-09-21", "2026-09-21"),
]


def epoch(s: str) -> int:
    import datetime as dt
    y, m, d = (int(x) for x in s.split("-"))
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp())


def main() -> int:
    print("=" * 100)
    print("กริดที่ประกาศไว้ล่วงหน้าทั้ง 8,250 ช่อง (Amendment 14) มีข้อมูลทำเงินจริงไหมในแต่ละปี")
    print("ใช้ต้นทุนจริงของโปรเจกต์ (spread 0.090 + คอมมิชชั่น 0.140) ไม่ใช่ค่าที่กำหนดเอง")
    print("=" * 100)

    bars = ch.load(Path("data/canonical_XAUUSD_M5.npz"))
    uni, meta = audit.load_universe(bars)
    print(f"ช่อง (cells) ทั้งหมด: {len(uni):,}\n")

    print(f"{'ช่วง':38s}{'ช่องที่ประเมินได้':>16s}{'บวก%':>8s}{'ค่ากลาง':>10s}"
          f"{'เฉลี่ย':>10s}{'ไม้รวม':>10s}{'%Long':>8s}")
    print("-" * 100)

    for name, s0, s1 in ERAS:
        lo, hi = epoch(s0), epoch(s1)
        means = []
        n_long = n_short = 0
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
            print(f"{name:38s}  ไม่มีช่องที่ประเมินได้")
            continue
        means = np.array(means)
        tot = n_long + n_short
        print(f"{name:38s}{len(means):16,d}{100*np.mean(means>0):7.1f}%"
              f"{np.median(means):10.4f}{np.mean(means):10.4f}{tot:10,d}"
              f"{100*n_long/max(tot,1):7.1f}%")

    print("\nคำอธิบาย:")
    print("  ช่องที่ประเมินได้ = จำนวนช่อง (จาก 8,250) ที่มีไม้ครบ 15 ไม้ขึ้นไปในช่วงนั้น")
    print("  บวก% = % ของช่องเหล่านั้นที่ net R เฉลี่ยเป็นบวก (ถ้าเป็นเครื่องมือสุ่มไร้ข้อมูล ควรอยู่ราว 50%)")
    print("  ค่ากลาง/เฉลี่ย = net R เฉลี่ยของช่องทั้งหมดที่ประเมินได้ (หน่วย R ต่อไม้)")
    print("  %Long = สัดส่วนไม้ที่เป็นฝั่ง Long ของทั้งกริดในช่วงนั้น")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
