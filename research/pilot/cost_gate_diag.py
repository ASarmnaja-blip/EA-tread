"""Why does the 8 percent cost-over-ATR gate disqualify most of the universe?

The cross-asset run found XAGUSD 83 percent TOO_EXPENSIVE, USDJPY 91 percent
and EURUSD 99 percent, which left only four of six assets testable and failed
Amendment 06's "positive on at least 4 of 6" criterion by construction rather
than by evidence. Before that can be called a finding about those markets, the
gate's own arithmetic has to be printed: price, ATR, the measured spread, and
the ratio the gate actually compares against 0.08.

This prints numbers and draws no conclusion. It changes no rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

UNIVERSE = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "US500")
SLIP_PER_ATR = 0.0165 / 4.705


def main() -> int:
    print("ส่วนประกอบของด่านต้นทุน (เกณฑ์คือ cost/ATR ต้องไม่เกิน 0.08)")
    print("bp = basis point = 0.01% ของราคา ใช้เทียบ ATR ข้ามสินค้าที่ราคาต่างกันมาก\n")
    for sym in UNIVERSE:
        try:
            b5 = D.load_csv(f"data/{sym}_M5.csv")
        except Exception as e:
            print(f"{sym:8s} โหลดไม่ได้: {e}")
            continue
        b15, _ = D.to_15m(b5)
        atr = core.atr(b15, 14)
        a = float(np.nanmedian(atr))
        px = float(np.nanmedian(b15.c))
        if b5.sp is not None and np.isfinite(b5.sp).any():
            good = b5.sp[np.isfinite(b5.sp) & (b5.sp > 0)]
            sp = float(np.nanmedian(good)) if len(good) else float("nan")
            frac_zero = float(np.mean(b5.sp <= 0))
            q = (np.nanpercentile(good, [10, 50, 90]) if len(good)
                 else [float("nan")] * 3)
        else:
            sp, frac_zero, q = float("nan"), float("nan"), [float("nan")] * 3
        slip = SLIP_PER_ATR * a
        ratio = (sp + 2 * slip) / a
        print(f"{sym:8s} ราคา {px:11.5f}  ATR15 {a:10.5f} ({1e4*a/px:6.2f} bp)")
        print(f"         spread {sp:10.5f} ({1e4*sp/px:6.2f} bp)  "
              f"spread/ATR {sp/a:7.4f}   slip/ATR {slip/a:6.4f}")
        print(f"         cost/ATR {ratio:7.4f}  -> "
              f"{'ผ่านด่าน' if ratio <= 0.08 else 'TOO_EXPENSIVE'}"
              f"   แท่งที่ spread=0 {100*frac_zero:5.1f}%"
              f"   p10/p50/p90 {q[0]:.5f}/{q[1]:.5f}/{q[2]:.5f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
