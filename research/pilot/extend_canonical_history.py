"""Extend the canonical XAUUSD M5 history as far back as the broker will serve.

Codex's canonical_history.py assumed the broker's continuous history started in
early 2021 (`START_YEAR = 2021` in historical_regime_walkforward.py) - that was
never actually probed. A direct probe found real M5 bars back to 2016-08-09.
This fetches 2016-08-09 through the existing canonical file's start, checks
continuity honestly, and builds a NEW, separate canonical file - the original
`canonical_XAUUSD_M5.npz` is never overwritten (canonical_history.save() refuses
to anyway), so every result already built on it stays reproducible.

Read-only against MT5 (history queries only, no order API touched).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
import data as D

SYMBOL = "XAUUSD"
NEW_START = datetime(2016, 8, 9, tzinfo=timezone.utc)
OUT = Path("data/canonical_XAUUSD_M5_from2016.npz")


def fetch_range(mt5, start: datetime, end: datetime):
    """Yearly MT5 requests, same chunking Codex's own fetcher used - MT5 can
    truncate very large multi-year requests at the terminal's max-bars limit."""
    chunks = []
    y0, y1 = start.year, end.year
    for year in range(y0, y1 + 1):
        a = max(start, datetime(year, 1, 1, tzinfo=timezone.utc))
        b = min(end, datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        if a >= b:
            continue
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, a, b)
        n = 0 if rates is None else len(rates)
        print(f"  {year}: ขอ {a:%Y-%m-%d} .. {b:%Y-%m-%d}  ได้ {n:,} แท่ง")
        if rates is not None and len(rates):
            chunks.append(rates)
    if not chunks:
        return None
    r = np.concatenate(chunks)
    order = np.argsort(r["time"])
    r = r[order]
    uniq = np.r_[True, r["time"][1:] != r["time"][:-1]]
    return r[uniq]


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("ต่อ MT5 ไม่ได้:", mt5.last_error())
        return 1

    existing = ch.load(Path("data/canonical_XAUUSD_M5.npz"))
    existing_start = int(existing.t[0])
    print(f"ไฟล์เดิมเริ่มที่ {datetime.fromtimestamp(existing_start, timezone.utc)}")
    print(f"จะขอเพิ่มตั้งแต่ {NEW_START} ถึงตรงนั้น\n")

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        print("ไม่พบสัญลักษณ์"); mt5.shutdown(); return 1

    end = datetime.fromtimestamp(existing_start, timezone.utc)
    r = fetch_range(mt5, NEW_START, end)
    mt5.shutdown()
    if r is None:
        print("ไม่ได้ข้อมูลเพิ่มเลย"); return 1

    keep = r["time"] < existing_start
    r = r[keep]
    print(f"\nรวมได้ {len(r):,} แท่งใหม่ก่อนถึงจุดเริ่มเดิม")

    # continuity check, reported honestly rather than hidden
    step = 300
    gaps = np.diff(r["time"].astype(np.int64))
    normal = int(np.sum(gaps == step))
    weekend_or_break = int(np.sum((gaps > step) & (gaps <= 3 * 86400)))
    big_gap = int(np.sum(gaps > 3 * 86400))
    print(f"ช่วงเวลาระหว่างแท่ง: ต่อเนื่องปกติ {normal:,}  "
          f"ช่วงพักตลาด/วันหยุด {weekend_or_break:,}  "
          f"รูโหว่ผิดปกติ (>3 วัน) {big_gap:,}")
    if big_gap:
        idx = np.flatnonzero(gaps > 3 * 86400)
        for i in idx[:10]:
            a = datetime.fromtimestamp(int(r["time"][i]), timezone.utc)
            b = datetime.fromtimestamp(int(r["time"][i + 1]), timezone.utc)
            print(f"    รูโหว่: {a} -> {b}  ({(b-a).days} วัน)")

    old = D.Bars(r["time"], r["open"], r["high"], r["low"], r["close"],
                r["tick_volume"], 300, SYMBOL, r["spread"] * info.point)

    t = np.r_[old.t, existing.t]
    o = np.r_[old.o, existing.o]
    h = np.r_[old.h, existing.h]
    l = np.r_[old.l, existing.l]
    c = np.r_[old.c, existing.c]
    v = np.r_[old.v, existing.v]
    sp = np.r_[old.sp, existing.sp]
    combined = D.Bars(t, o, h, l, c, v, 300, SYMBOL, sp)

    meta = ch.save(OUT, combined,
                   source=(f"MT5 annual M5 {NEW_START:%Y-%m-%d}..existing-start "
                          f"combined with the existing verified canonical file "
                          f"(sha256={ch.bars_digest(existing)})"))
    print(f"\nบันทึกไฟล์ใหม่ {OUT}")
    print(f"  แท่งทั้งหมด {meta['bars']:,}")
    print(f"  จาก {datetime.fromtimestamp(meta['first_epoch'], timezone.utc)}")
    print(f"  ถึง {datetime.fromtimestamp(meta['last_epoch'], timezone.utc)}")
    print(f"  sha256 {meta['sha256'][:16]}...")
    print("\nไฟล์เดิม canonical_XAUUSD_M5.npz ไม่ถูกแก้หรือทับ ยังใช้ตรวจผลเก่าได้เหมือนเดิม")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
