"""Measure each symbol's spread from the broker instead of from the export.

WHY THIS EXISTS. The per-bar `spread` column in the M5 exports is an integer
count of points, and for four of the six symbols it is zero on most bars -
EURUSD 94.1 percent, USDJPY 92.2 percent, GBPUSD 59.6 percent, US500 52.1
percent. Zero is not a plausible spread, so it is either a genuine sub-point
figure rounded down or a field the feed does not populate. Either way the
cross-asset code dropped those bars and took the median of what was left,
which is the median of the WIDEST few percent of bars. That is how EURUSD came
out at 1.35 bp and was classified TOO_EXPENSIVE on 99 percent of its bars,
producing zero signals - a bug that looked like a fact about the euro.

Guessing a replacement is forbidden, so the number is measured: the live
tick and the symbol's own declared spread, sampled over time and reduced to a
median. Read-only. No order is sent and nothing is modified.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 package not installed")
    raise SystemExit(1)

SYMBOLS = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "US500")
OUT = Path("data/measured_spreads.json")


def main() -> int:
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    if not mt5.initialize():
        print(f"initialize failed: {mt5.last_error()}")
        return 1
    ai = mt5.account_info()
    if ai is None:
        print("no account info")
        mt5.shutdown()
        return 1
    print(f"account {ai.login} on {ai.server}  trade_mode={ai.trade_mode} "
          f"(0=DEMO)  read-only measurement, no orders")

    acc: dict[str, list[float]] = {s: [] for s in SYMBOLS}
    digits: dict[str, int] = {}
    points: dict[str, float] = {}
    missing = []
    for s in SYMBOLS:
        si = mt5.symbol_info(s)
        if si is None:
            missing.append(s)
            continue
        if not si.visible:
            mt5.symbol_select(s, True)
        si = mt5.symbol_info(s)
        digits[s] = si.digits
        points[s] = si.point
    if missing:
        print(f"ไม่พบสัญลักษณ์: {missing}")

    print(f"\nเก็บ {samples} ตัวอย่าง ห่างกัน {gap}s ...")
    for _ in range(samples):
        for s in SYMBOLS:
            if s in missing:
                continue
            t = mt5.symbol_info_tick(s)
            if t and t.ask > 0 and t.bid > 0:
                acc[s].append(t.ask - t.bid)
        time.sleep(gap)

    import statistics as st
    out = {}
    print(f"\n{'symbol':9s}{'n':>5s}{'p10':>11s}{'median':>11s}{'p90':>11s}"
          f"{'median pts':>12s}")
    for s in SYMBOLS:
        v = sorted(acc[s])
        if len(v) < 3:
            print(f"{s:9s}{len(v):5d}   วัดไม่ได้ (ตลาดอาจปิด)")
            continue
        p10 = v[int(0.10 * (len(v) - 1))]
        med = st.median(v)
        p90 = v[int(0.90 * (len(v) - 1))]
        pts = med / points[s] if points.get(s) else float("nan")
        out[s] = dict(n=len(v), p10=p10, median=med, p90=p90,
                      digits=digits.get(s), point=points.get(s),
                      median_points=pts)
        print(f"{s:9s}{len(v):5d}{p10:11.5f}{med:11.5f}{p90:11.5f}{pts:12.1f}")

    mt5.shutdown()
    if out:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nบันทึกที่ {OUT}")
        print("นี่คือ spread ของบัญชี DEMO ยังไม่ใช่ของบัญชีจริง")
        print("บน XAUUSD อัตราจริง/เดโม่ที่วัดได้คือ 0.260/0.037 ~ 7 เท่า")
    else:
        print("\nไม่ได้ค่าใด ๆ ตลาดอาจปิดอยู่ ยังต้องรายงานว่า NOT MEASURED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
