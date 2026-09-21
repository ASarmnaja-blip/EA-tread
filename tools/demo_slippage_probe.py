#!/usr/bin/env python3
"""
Measure what execution ACTUALLY costs, on the demo account only.

Every conclusion in this repo rests on a slippage figure nobody has measured.
The sensitivity is not academic: the best tool found so far returns +0.057 R
at $0.05 per fill, +0.035 at $0.10 and -0.009 at $0.20, so the sign of the
answer is decided by an assumption.

A pending order cannot answer this. The one placed earlier was never
triggered, so it produced no fill and no number. Only a market order that
fills immediately reveals the gap between the price quoted and the price
received.

Obeys data/DEMO_ORDER_PERMISSION.md, checked at runtime rather than trusted:

  1. refuses to run unless account_info().trade_mode is DEMO
  2. 0.01 lot, and refuses if any position is already open
  3. a stop loss is attached to the order itself, not added afterwards
  4. opens and closes within seconds; the position is never left overnight
  5. logs request, retcode, both quotes, both fills, spread and slippage
  6. labels everything EXECUTION TEST ONLY - the P&L of these probes is an
     execution measurement and must never be counted as strategy performance

It measures. It does not trade a signal, and it does not decide direction:
the side is fixed at BUY because the question is about the mechanics of a
fill, not about where price goes next.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SYMBOL = "XAUUSD"        # overridden by --symbol; see _resolve_symbol()
SL_DIST = 2.0            # price units below entry, set per symbol at runtime
VOLUME = 0.01
DEVIATION = 100          # points of price tolerance, so the order fills and
                         # the slippage can be MEASURED rather than rejected
MAGIC = 20260921
HOLD_SECONDS = 1         # long enough to be a real round trip, short enough
                         # that drift does not swamp the cost being measured
GAP_SECONDS = 5          # spacing between samples, so they are not one moment
LOG = Path("data/execution_probe_log.json")


def abort(mt5, msg: str) -> None:
    print(f"ยกเลิก: {msg}")
    mt5.shutdown()
    raise SystemExit(1)


def _stop_distance(mt5, symbol: str, info) -> float:
    """A stop far enough below entry that it cannot be touched during a
    one-second hold, expressed in the SYMBOL'S OWN units.

    The original probe hardcoded 2.0, which is about half an ATR on gold and
    a nonsensical or even negative price on EURUSD at 1.11. It is now derived
    from the symbol's own recent range, with the broker's minimum stop
    distance as a floor, so the same probe is valid on every instrument.
    """
    r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 300)
    if r is not None and len(r) > 20:
        rng = float(sum(x["high"] - x["low"] for x in r) / len(r))
        d = max(10.0 * rng, 50 * info.point)
    else:
        d = 500 * info.point
    floor = (info.trade_stops_level or 0) * info.point * 2.0
    return max(d, floor)


def _deal_costs(mt5, symbol: str, t_from) -> dict:
    """Commission and swap actually charged, read back from the account's own
    deal history. Commission had never been charged anywhere in this project;
    on XAUUSD it turned out to be $7.00 per lot per side, which is 2.7 times
    the demo spread, so it is measured here rather than assumed."""
    import datetime as _dt
    d = mt5.history_deals_get(t_from - _dt.timedelta(minutes=5),
                              _dt.datetime.now() + _dt.timedelta(minutes=5))
    if not d:
        return {}
    mine = [x for x in d if x.symbol == symbol and x.magic == MAGIC]
    if not mine:
        return {}
    comm = sum(x.commission for x in mine)
    vol = sum(x.volume for x in mine) or 1.0
    return dict(deals=len(mine), commission_total=comm, volume_total=vol,
                commission_per_lot_per_side=comm / vol)


def one_probe(mt5, info, n_label: str) -> dict | None:
    """One open-and-close round trip. Returns the record, or None if it could
    not be completed cleanly."""
    q0 = mt5.symbol_info_tick(SYMBOL)
    if q0 is None or not q0.time:
        print(f"  {n_label}: ไม่มีราคา ข้าม")
        return None
    spread0 = q0.ask - q0.bid
    sl = q0.bid - SL_DIST
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=VOLUME,
               type=mt5.ORDER_TYPE_BUY, price=q0.ask, sl=sl,
               deviation=DEVIATION, magic=MAGIC, comment="EXEC_TEST_ONLY",
               type_time=mt5.ORDER_TIME_GTC, type_filling=mt5.ORDER_FILLING_IOC)
    t0 = time.time()
    res = mt5.order_send(req)
    t1 = time.time()
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  {n_label}: เปิดไม่สำเร็จ {res.retcode if res else None}")
        return None
    entry, slip_in = res.price, res.price - q0.ask

    time.sleep(HOLD_SECONDS)
    q1 = mt5.symbol_info_tick(SYMBOL)
    pos = mt5.positions_get(symbol=SYMBOL)
    if not pos:
        print(f"  {n_label}: หาสถานะไม่เจอ")
        return None
    p = pos[0]
    creq = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=p.volume,
                type=mt5.ORDER_TYPE_SELL, position=p.ticket, price=q1.bid,
                deviation=DEVIATION, magic=MAGIC, comment="EXEC_TEST_ONLY_CLOSE",
                type_time=mt5.ORDER_TIME_GTC, type_filling=mt5.ORDER_FILLING_IOC)
    t2 = time.time()
    cres = mt5.order_send(creq)
    t3 = time.time()
    if cres is None or cres.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  {n_label}: !! ปิดไม่สำเร็จ มีสถานะค้าง ต้องปิดด้วยมือ")
        return None
    exit_fill, slip_out = cres.price, q1.bid - cres.price
    print(f"  {n_label}: spread {spread0:.4f}  ขาเข้า {slip_in:+.4f}  "
          f"ขาออก {slip_out:+.4f}  ไป-กลับ {entry-exit_fill:+.4f}  "
          f"({1000*(t1-t0):.0f}/{1000*(t3-t2):.0f} ms)")
    return dict(when_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                label="EXECUTION TEST ONLY - not strategy performance",
                bid=q0.bid, ask=q0.ask, spread=spread0,
                entry_fill=entry, slip_in=slip_in,
                exit_fill=exit_fill, slip_out=slip_out,
                round_trip=entry - exit_fill,
                ms_in=round(1000*(t1-t0)), ms_out=round(1000*(t3-t2)))


def main() -> int:
    global SYMBOL, SL_DIST, VOLUME
    import MetaTrader5 as mt5
    samples = 1
    if "--samples" in sys.argv:
        samples = int(sys.argv[sys.argv.index("--samples") + 1])
    if "--symbol" in sys.argv:
        SYMBOL = sys.argv[sys.argv.index("--symbol") + 1]
    if not mt5.initialize():
        print("ต่อ MT5 ไม่ได้:", mt5.last_error())
        return 1

    acc = mt5.account_info()
    if acc is None:
        abort(mt5, "อ่านข้อมูลบัญชีไม่ได้")
    is_demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    print("=" * 84)
    print("EXECUTION TEST ONLY - วัดต้นทุนการส่งคำสั่งจริง ไม่ใช่สัญญาณกลยุทธ์")
    print("=" * 84)
    print(f"บัญชี {acc.login} @ {acc.server} | "
          f"{'DEMO' if is_demo else 'LIVE'} | {acc.currency} {acc.balance:,.2f}")
    if not is_demo:
        abort(mt5, "นี่ไม่ใช่บัญชีทดลอง - สิทธิ์ครอบคลุมเฉพาะ demo เท่านั้น")

    if mt5.positions_total():
        abort(mt5, f"มีสถานะเปิดอยู่แล้ว {mt5.positions_total()} รายการ")

    if not mt5.symbol_select(SYMBOL, True):
        abort(mt5, f"เลือก {SYMBOL} ไม่ได้")
    info = mt5.symbol_info(SYMBOL)
    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        abort(mt5, "สัญลักษณ์นี้ปิดการเทรดอยู่")
    SL_DIST = _stop_distance(mt5, SYMBOL, info)
    # DEMO_ORDER_PERMISSION fixes the size at the minimum. On most symbols that
    # is 0.01, but US500's own minimum is 0.14 and an order below it is
    # rejected with 10014. The size is therefore the larger of the permission's
    # floor and the symbol's own minimum: never smaller than the rule allows,
    # and never larger than the smallest order the broker will accept.
    if info.volume_min > VOLUME:
        VOLUME = float(info.volume_min)
        print(f"หมายเหตุ: ขั้นต่ำของ {SYMBOL} คือ {info.volume_min} "
              f"ไม่ใช่ 0.01 จึงใช้ {VOLUME} ซึ่งเป็นขนาดเล็กที่สุดที่ส่งได้")
    import datetime as _dt
    t_start = _dt.datetime.now()
    print(f"สัญลักษณ์ {SYMBOL}  จุด {info.point}  ทศนิยม {info.digits}  "
          f"ระยะ SL ที่ใช้ {SL_DIST:.5f}  ขนาด {VOLUME}")

    if samples > 1:
        print(f"\nเก็บ {samples} ตัวอย่าง เว้นระยะ {GAP_SECONDS}s "
              f"(เครื่องมือวัดการกระจาย ไม่ใช่การเทรด)")
        recs = []
        for k in range(1, samples + 1):
            if mt5.positions_total():
                print(f"  ครั้งที่ {k}: มีสถานะค้างอยู่ หยุดทันที")
                break
            r = one_probe(mt5, info, f"ครั้งที่ {k}")
            if r:
                recs.append(r)
            if k < samples:
                time.sleep(GAP_SECONDS)
        if recs:
            import statistics as st
            si = [r["slip_in"] for r in recs]
            so = [r["slip_out"] for r in recs]
            rt = [r["round_trip"] for r in recs]
            sp = [r["spread"] for r in recs]
            print("\n" + "-" * 84)
            print(f"สรุปจาก {len(recs)} ตัวอย่าง (หน่วย $/oz)")
            print(f"  spread ที่เห็น   กลาง {st.median(sp):.4f}  "
                  f"ต่ำสุด {min(sp):.4f}  สูงสุด {max(sp):.4f}")
            print(f"  ส่วนต่างขาเข้า  กลาง {st.median(si):+.4f}  เฉลี่ย {st.mean(si):+.4f}  "
                  f"ต่ำสุด {min(si):+.4f}  สูงสุด {max(si):+.4f}")
            print(f"  ส่วนต่างขาออก   กลาง {st.median(so):+.4f}  เฉลี่ย {st.mean(so):+.4f}")
            print(f"  ไป-กลับจริง     กลาง {st.median(rt):+.4f}  เฉลี่ย {st.mean(rt):+.4f}")
            tot = st.mean(si) + st.mean(so)
            print(f"\n  slippage รวมสองข้างเฉลี่ย {tot:+.4f} (หน่วยราคาของ {SYMBOL})")
            cc = _deal_costs(mt5, SYMBOL, t_start)
            if cc:
                print(f"  คอมมิชชั่นที่ถูกหักจริง {cc['commission_total']:+.2f} "
                      f"จาก {cc['deals']} ดีล ปริมาณรวม {cc['volume_total']:.2f} lot")
                print(f"  = {cc['commission_per_lot_per_side']:+.4f} ต่อลอตต่อข้าง")
                print("  ต้นทุนรอบหนึ่ง = spread + คอมมิชชั่นสองข้าง + slippage สองข้าง")
            else:
                print("  คอมมิชชั่น: อ่านจากประวัติดีลไม่ได้ -> NOT MEASURED")
            hist = json.loads(LOG.read_text()) if LOG.exists() else []
            hist.extend(recs)
            LOG.parent.mkdir(parents=True, exist_ok=True)
            LOG.write_text(json.dumps(hist, indent=2))
            print(f"  บันทึกรวม {len(hist)} ครั้งที่ {LOG}")
        print(f"\nสถานะเปิดคงเหลือ: {mt5.positions_total()}  (ต้องเป็น 0)")
        mt5.shutdown()
        return 0

    q0 = mt5.symbol_info_tick(SYMBOL)
    if q0 is None or not q0.time:
        abort(mt5, "ไม่มีราคา - ตลาดอาจปิดอยู่")
    spread0 = (q0.ask - q0.bid)
    sl = q0.bid - SL_DIST
    print(f"\nก่อนส่ง: bid {q0.bid:.3f}  ask {q0.ask:.3f}  "
          f"spread {spread0:.4f} ({info.spread} points)")
    print(f"จะส่ง: BUY {VOLUME} lot, SL {sl:.3f}, ทนส่วนต่างได้ {DEVIATION} points")

    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=VOLUME,
               type=mt5.ORDER_TYPE_BUY, price=q0.ask, sl=sl,
               deviation=DEVIATION, magic=MAGIC,
               comment="EXEC_TEST_ONLY", type_time=mt5.ORDER_TIME_GTC,
               type_filling=mt5.ORDER_FILLING_IOC)
    chk = mt5.order_check(req)
    if chk is None or chk.retcode not in (0, mt5.TRADE_RETCODE_DONE):
        print("order_check:", chk)
        if chk is not None and chk.retcode not in (0,):
            for f in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
                req["type_filling"] = f
                chk = mt5.order_check(req)
                if chk is not None and chk.retcode == 0:
                    print(f"  ใช้ filling mode {f} แทน")
                    break
    t_send = time.time()
    res = mt5.order_send(req)
    t_ack = time.time()
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        abort(mt5, f"ส่งคำสั่งไม่สำเร็จ: {res}")

    entry_fill = res.price
    slip_in = entry_fill - q0.ask
    print(f"\nเปิดสำเร็จ: retcode {res.retcode}  fill {entry_fill:.3f}  "
          f"deal {res.deal}  ({1000*(t_ack-t_send):.0f} ms)")
    print(f"  ส่วนต่างขาเข้า: {slip_in:+.4f} $/oz "
          f"({'จ่ายแพงกว่าที่เห็น' if slip_in > 0 else 'ได้ดีกว่าที่เห็น'})")

    time.sleep(HOLD_SECONDS)

    q1 = mt5.symbol_info_tick(SYMBOL)
    pos = mt5.positions_get(symbol=SYMBOL)
    if not pos:
        abort(mt5, "หาสถานะที่เพิ่งเปิดไม่เจอ - ต้องปิดด้วยมือ")
    p = pos[0]
    creq = dict(action=mt5.TRADE_ACTION_DEAL, symbol=SYMBOL, volume=p.volume,
                type=mt5.ORDER_TYPE_SELL, position=p.ticket, price=q1.bid,
                deviation=DEVIATION, magic=MAGIC, comment="EXEC_TEST_ONLY_CLOSE",
                type_time=mt5.ORDER_TIME_GTC, type_filling=req["type_filling"])
    t_send2 = time.time()
    cres = mt5.order_send(creq)
    t_ack2 = time.time()
    if cres is None or cres.retcode != mt5.TRADE_RETCODE_DONE:
        print("!! ปิดไม่สำเร็จ:", cres)
        print("!! มีสถานะค้าง ต้องปิดด้วยมือทันที")
        mt5.shutdown()
        return 2

    exit_fill = cres.price
    slip_out = q1.bid - exit_fill
    round_trip = entry_fill - exit_fill
    print(f"\nปิดสำเร็จ: fill {exit_fill:.3f}  ({1000*(t_ack2-t_send2):.0f} ms)")
    print(f"  ส่วนต่างขาออก: {slip_out:+.4f} $/oz")

    print("\n" + "-" * 84)
    print(f"ต้นทุนไป-กลับที่จ่ายจริง : {round_trip:+.4f} $/oz")
    print(f"  spread ที่เห็นตอนเปิด  : {spread0:.4f}")
    print(f"  ส่วนต่างขาเข้า+ขาออก   : {slip_in + slip_out:+.4f}")
    print(f"สมมติฐานที่ใช้มาตลอด    : 0.260 spread + 2 x 0.10 slippage = 0.460")
    print(f"ต่างจากสมมติฐาน         : {round_trip - 0.460:+.4f} $/oz")

    rec = dict(when_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               label="EXECUTION TEST ONLY - not strategy performance",
               account=acc.login, server=acc.server, mode="DEMO",
               symbol=SYMBOL, volume=VOLUME,
               quote_before=dict(bid=q0.bid, ask=q0.ask, spread=spread0,
                                 spread_points=info.spread),
               entry=dict(retcode=res.retcode, fill=entry_fill, deal=res.deal,
                          slippage=slip_in, ms=round(1000*(t_ack-t_send))),
               quote_at_close=dict(bid=q1.bid, ask=q1.ask),
               exit=dict(retcode=cres.retcode, fill=exit_fill,
                         slippage=slip_out, ms=round(1000*(t_ack2-t_send2))),
               round_trip_cost=round_trip, sl_used=sl,
               assumption_used_in_research=0.460)
    hist = json.loads(LOG.read_text()) if LOG.exists() else []
    hist.append(rec)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(hist, indent=2))
    print(f"\nบันทึกไว้ที่ {LOG}  (ทั้งหมด {len(hist)} ครั้ง)")
    print("ย้ำ: กำไรขาดทุนของการทดสอบนี้เป็นการวัดต้นทุน ห้ามนับเป็นผลงานกลยุทธ์")
    print(f"สถานะเปิดคงเหลือ: {mt5.positions_total()}  (ต้องเป็น 0)")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
