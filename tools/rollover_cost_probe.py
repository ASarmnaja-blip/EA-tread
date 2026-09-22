"""Measure what execution actually costs in the 21:00-23:00 UTC rollover window.

WHY THIS IS THE DECISIVE MEASUREMENT. W1 passed its cost test, but 66 percent of
its historical entries are at 22:00 UTC and 33 percent at 23:00 - it is a
rollover-gap trade. The slippage floor the whole project uses, 0.0165 per fill,
was measured during liquid hours. W1's net expectancy dies at a 7x cost
multiplier, and a rollover fill is plausibly in that range. So the single number
that decides whether W1 is real is a number nobody has taken.

TWO PHASES.

  Phase 1, read-only: sample the quoted spread every few seconds across the
  window. This alone may settle it - if the quoted spread at 22:00 is ten times
  the median, no fill measurement is needed to know the answer.

  Phase 2, the demo probe: a small number of immediate round trips to measure
  the gap between the quote and the fill, which no amount of quote-watching can
  reveal. Obeys data/DEMO_ORDER_PERMISSION.md, verified at runtime rather than
  trusted: demo account only, the symbol's minimum volume, a stop loss attached
  to the order itself, one position at a time, opened and closed within seconds,
  never held overnight, and labelled EXECUTION TEST ONLY so its P&L can never be
  counted as strategy performance.

Phase 2 is skipped entirely unless `--orders` is passed, so the read-only half
can be run freely.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SYMBOL = "XAUUSD"
VOLUME = 0.01
DEVIATION = 100
MAGIC = 20260922
HOLD_SECONDS = 1
OUT = Path("data/rollover_cost.json")


def now_utc():
    return datetime.now(timezone.utc)


def watch(mt5, seconds: int, every: float) -> list[dict]:
    """Phase 1. Quotes only. Sends nothing."""
    rows = []
    t_end = time.time() + seconds
    while time.time() < t_end:
        t = mt5.symbol_info_tick(SYMBOL)
        if t and t.ask > 0 and t.bid > 0:
            rows.append(dict(utc=now_utc().isoformat(timespec="seconds"),
                             bid=t.bid, ask=t.ask, spread=t.ask - t.bid))
        time.sleep(every)
    return rows


def probe(mt5, info, label: str) -> dict | None:
    """Phase 2. One immediate round trip, stop loss attached to the order."""
    q0 = mt5.symbol_info_tick(SYMBOL)
    if q0 is None or not q0.time:
        print(f"  {label}: ไม่มีราคา ข้าม")
        return None
    r = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 200)
    rng = (float(sum(x["high"] - x["low"] for x in r) / len(r))
           if r is not None and len(r) > 20 else 1.0)
    sl_dist = max(10.0 * rng, (info.trade_stops_level or 0) * info.point * 2.0)
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=VOLUME,
               type=mt5.ORDER_TYPE_BUY, price=q0.ask, sl=q0.bid - sl_dist,
               deviation=DEVIATION, magic=MAGIC, comment="EXEC_TEST_ONLY",
               type_time=mt5.ORDER_TIME_GTC,
               type_filling=mt5.ORDER_FILLING_IOC)
    t0 = time.time()
    res = mt5.order_send(req)
    t1 = time.time()
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  {label}: เปิดไม่สำเร็จ {res.retcode if res else None}")
        return None
    entry, slip_in = res.price, res.price - q0.ask
    time.sleep(HOLD_SECONDS)
    q1 = mt5.symbol_info_tick(SYMBOL)
    pos = mt5.positions_get(symbol=SYMBOL)
    if not pos:
        print(f"  {label}: หาสถานะไม่เจอ")
        return None
    p = pos[0]
    creq = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=p.volume,
                type=mt5.ORDER_TYPE_SELL, position=p.ticket, price=q1.bid,
                deviation=DEVIATION, magic=MAGIC,
                comment="EXEC_TEST_ONLY_CLOSE", type_time=mt5.ORDER_TIME_GTC,
                type_filling=mt5.ORDER_FILLING_IOC)
    t2 = time.time()
    cres = mt5.order_send(creq)
    t3 = time.time()
    if cres is None or cres.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  {label}: !! ปิดไม่สำเร็จ มีสถานะค้าง ต้องปิดด้วยมือทันที")
        return None
    slip_out = q1.bid - cres.price
    print(f"  {label}: spread {q0.ask-q0.bid:.4f}  ขาเข้า {slip_in:+.4f}  "
          f"ขาออก {slip_out:+.4f}  ({1000*(t1-t0):.0f}/{1000*(t3-t2):.0f} ms)")
    return dict(utc=now_utc().isoformat(timespec="seconds"),
                label="EXECUTION TEST ONLY - not strategy performance",
                spread=q0.ask - q0.bid, slip_in=slip_in, slip_out=slip_out,
                both_sides=slip_in + slip_out,
                ms_in=round(1000 * (t1 - t0)), ms_out=round(1000 * (t3 - t2)))


def main() -> int:
    import MetaTrader5 as mt5
    do_orders = "--orders" in sys.argv
    secs = 900
    if "--seconds" in sys.argv:
        secs = int(sys.argv[sys.argv.index("--seconds") + 1])
    n_probes = 3
    if "--probes" in sys.argv:
        n_probes = int(sys.argv[sys.argv.index("--probes") + 1])

    if not mt5.initialize():
        print("ต่อ MT5 ไม่ได้:", mt5.last_error())
        return 1
    acc = mt5.account_info()
    if acc is None:
        print("อ่านบัญชีไม่ได้")
        mt5.shutdown()
        return 1
    is_demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO

    print("=" * 92)
    print("ROLLOVER COST PROBE — วัดต้นทุนจริงในช่วง 21:00-23:00 UTC")
    print("=" * 92)
    print(f"เวลา {now_utc():%Y-%m-%d %H:%M} UTC   ชั่วโมง UTC = {now_utc().hour}")
    print(f"บัญชี {acc.login} @ {acc.server}  "
          f"{'DEMO' if is_demo else 'LIVE'}  ยอด {acc.balance:,.2f}")
    print("W1 เทรด 66% ที่ 22:00 UTC และ 33% ที่ 23:00 UTC")
    print("ค่า slippage 0.0165 ที่ใช้อยู่วัดมาจากช่วงตลาดคึกคัก ไม่ใช่ช่วงนี้\n")

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        print("ไม่พบสัญลักษณ์")
        mt5.shutdown()
        return 1
    if not info.visible:
        mt5.symbol_select(SYMBOL, True)
        info = mt5.symbol_info(SYMBOL)
    if info.volume_min > VOLUME:
        globals()["VOLUME"] = float(info.volume_min)

    print(f"--- ระยะที่ 1: เฝ้าดูราคาเสนอ {secs}s (ไม่ส่งคำสั่งใด ๆ) ---")
    quotes = watch(mt5, secs, 3.0)
    rec = dict(started_utc=now_utc().isoformat(timespec="seconds"),
               symbol=SYMBOL, quotes=quotes, probes=[])
    if quotes:
        import statistics as st
        sp = [q["spread"] for q in quotes]
        print(f"ตัวอย่าง {len(sp)} จุด   ค่ากลาง {st.median(sp):.4f}   "
              f"ต่ำสุด {min(sp):.4f}   สูงสุด {max(sp):.4f}")
        print(f"เทียบกับค่ากลางทั่วกราฟ 0.0520 และค่าที่แบบจำลองใช้ 0.0900")
        ratio = st.median(sp) / 0.0520
        print(f"อัตราส่วน {ratio:.2f}x ของค่ากลางทั่วกราฟ")
        if ratio > 3:
            print("-> spread ในช่วงนี้กว้างกว่าปกติมาก ซึ่งเป็นสิ่งที่กลัวไว้")
        else:
            print("-> spread ในช่วงนี้ไม่ได้กว้างผิดปกติ")
        rec["quote_summary"] = dict(n=len(sp), median=st.median(sp),
                                    lo=min(sp), hi=max(sp), ratio_vs_all=ratio)
    else:
        print("ไม่ได้ราคาเลย — ตลาดอาจปิด")

    if do_orders:
        if not is_demo:
            print("\nไม่ใช่บัญชีทดลอง -> ไม่ส่งคำสั่งเด็ดขาด")
        elif mt5.positions_total():
            print(f"\nมีสถานะเปิดอยู่ {mt5.positions_total()} -> ไม่ส่งคำสั่ง")
        else:
            print(f"\n--- ระยะที่ 2: probe {n_probes} ครั้ง (EXECUTION TEST ONLY) ---")
            print(f"ขนาด {VOLUME} lot, แนบ SL กับคำสั่ง, ถือ {HOLD_SECONDS}s, "
                  f"ปิดทันที, ไม่นับเป็นผลงานกลยุทธ์")
            for k in range(1, n_probes + 1):
                if mt5.positions_total():
                    print(f"  ครั้งที่ {k}: มีสถานะค้าง หยุดทันที")
                    break
                p = probe(mt5, info, f"ครั้งที่ {k}")
                if p:
                    rec["probes"].append(p)
                if k < n_probes:
                    time.sleep(8)
            if rec["probes"]:
                import statistics as st
                both = [p["both_sides"] for p in rec["probes"]]
                print(f"\nslippage รวมสองข้าง: ค่ากลาง {st.median(both):+.4f}  "
                      f"เฉลี่ย {st.mean(both):+.4f}")
                print(f"ค่าที่โปรเจกต์ใช้อยู่คือ 0.0330 รวมสองข้าง")
                print(f"อัตราส่วน {st.mean(both)/0.0330:.2f}x")
                print("\nต้นทุนรอบหนึ่งที่วัดได้ในช่วงนี้ = "
                      f"{rec['quote_summary']['median'] + 0.140 + st.mean(both):.4f}/oz")
                print("เทียบกับที่ใช้ในการทดสอบ W1 = 0.263/oz")
    else:
        print("\n(ไม่ได้ส่ง --orders จึงไม่มีการส่งคำสั่งใด ๆ)")

    print(f"\nสถานะเปิดคงเหลือ {mt5.positions_total()} (ต้องเป็น 0)")
    hist = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    hist.append(rec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    print(f"บันทึกที่ {OUT} (รวม {len(hist)} รอบ)")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
