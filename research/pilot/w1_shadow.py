"""W1's forward shadow logger, implementing Amendment 12 section 6.

W1 passed its cost test, which triggers the shadow. This file starts and runs it.
It logs signals; it never sends an order.

THE STOPPING RULE IS FROZEN ON THE FIRST RUN and written to
data/w1_shadow_protocol.json, so it cannot drift afterwards:

    26 weeks from the first forward signal, OR 30 non-overlapping events,
    WHICHEVER COMES SECOND

It does not stop early because the result turned favourable and it does not
extend because the result turned unfavourable. Every signal is recorded whether
or not it would have been taken, because a shadow that only logs its winners is
a diary, not evidence.

WHAT IS STILL UNSETTLED, and is printed on every run so it cannot be forgotten:
W1 trades almost entirely in the 21:00-23:00 UTC rollover window - 66 percent of
its historical entries at 22:00 and 33 percent at 23:00 - while the measured
slippage floor of 0.0165 per fill was taken during liquid hours. Its net dies at
a 7x cost multiplier. Until slippage is measured AT THE ROLLOVER, no shadow
result settles anything.

Run it as often as you like. It is idempotent: a signal already in the log is not
logged twice, and open records are resolved as the bars arrive.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# the rule, frozen by Amendment 12 section 1
GAP_ATR = 0.5
STOP_ATR = 1.5
RR = 1.0
TIME_STOP_M5 = 72
ATR_N = 14
SYMBOL = "XAUUSD"

# the measured cost model, Amendment 08
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_SHORT = 0.0

# the stopping rule, Amendment 12 section 6
SHADOW_WEEKS = 26
SHADOW_EVENTS = 30

PROTO = Path("data/w1_shadow_protocol.json")
LOG = Path("data/w1_shadow_log.json")


def atr_from(h, l, c, n=ATR_N):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(c), np.nan)
    if len(c) > n:
        a = tr[1:n + 1].mean()
        out[n] = a
        for i in range(n + 1, len(c)):
            a = (a * (n - 1) + tr[i]) / n
            out[i] = a
    return out


def load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("ต่อ MT5 ไม่ได้:", mt5.last_error())
        return 1
    acc = mt5.account_info()
    if acc is None:
        print("อ่านบัญชีไม่ได้")
        mt5.shutdown()
        return 1
    now = datetime.now(timezone.utc)

    print("=" * 96)
    print("W1 FORWARD SHADOW (Amendment 12 ข้อ 6) — บันทึกสัญญาณ ไม่ส่งคำสั่ง")
    print("=" * 96)
    print(f"เวลา {now:%Y-%m-%d %H:%M} UTC   บัญชี {acc.login} @ {acc.server} "
          f"(trade_mode {acc.trade_mode}, 0=DEMO)   สถานะเปิด {mt5.positions_total()}")

    m15 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 400)
    m5 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 2000)
    if m15 is None or m5 is None or len(m15) < 100:
        print("ดึงแท่งไม่ได้ — ตลาดอาจปิด")
        mt5.shutdown()
        return 1

    o = m15["open"].astype(float)
    h = m15["high"].astype(float)
    l = m15["low"].astype(float)
    c = m15["close"].astype(float)
    t = m15["time"].astype(np.int64)
    atr = atr_from(h, l, c)

    proto = load(PROTO, None)
    log = load(LOG, {"records": []})
    recs = log["records"]
    seen = {r["signal_epoch"] for r in recs}

    # ------------------------------------------------ detect on CLOSED bars only
    # the last element of copy_rates_from_pos is the bar still forming, so it is
    # excluded: acting on it would be reading a close that does not exist yet
    new = []
    for i in range(len(m15) - 2, max(len(m15) - 40, ATR_N + 1), -1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        gap = o[i] - c[i - 1]
        if gap > -GAP_ATR * a:
            continue
        ep = int(t[i])
        if ep in seen:
            continue
        nxt5 = m5[m5["time"] == ep + 900]
        if len(nxt5) == 0:
            continue                      # the execution bar has not printed yet
        entry = float(nxt5["open"][0])
        risk = STOP_ATR * float(a)
        rec = dict(
            # --- CLAUDE.md section 6 schema, in full ---
            symbol=SYMBOL, timeframe="M15 signal / M5 execution",
            direction="SHORT",
            setup="W1 gap_continuation/short (Amendment 12)",
            regime="NOT USED — W1 carries no regime filter by design",
            signal_epoch=ep,
            signal_utc=datetime.fromtimestamp(ep, timezone.utc).isoformat(),
            gap=float(gap), gap_in_atr=float(gap / a), atr=float(a),
            entry=entry, stop=entry + risk, target=entry - RR * risk,
            risk_price=risk, risk_R=1.0,
            exit_logic=f"stop {STOP_ATR} ATR above, target {RR}R below, "
                       f"time stop {TIME_STOP_M5} M5 bars",
            expiry_epoch=ep + 900 + TIME_STOP_M5 * 300,
            confidence="NOT CALIBRATED — this shadow exists to calibrate it. "
                       "The discovery estimate was +0.2573 R net per trade on "
                       "76 events, which is not a forward figure",
            priced_in="a down-gap at the rollover is a liquidation print rather "
                      "than a re-pricing; what is NOT priced in is whether the "
                      "seller has finished",
            invalidation="close back above the pre-gap close before the target",
            news_risk="rollover-window gaps often follow late US-session news; "
                      "the calendar is not consulted by this rule",
            why="W1 passed Amendment 12's six pre-registered criteria",
            unsettled="slippage at 21:00-23:00 UTC has NEVER been measured; "
                      "W1's net dies at a 7x cost multiplier",
            status="open", outcome=None, gross_R=None, net_R=None,
        )
        new.append(rec)
        seen.add(ep)

    for r in sorted(new, key=lambda x: x["signal_epoch"]):
        recs.append(r)
        print(f"\nสัญญาณใหม่ {r['signal_utc']}  gap {r['gap']:+.3f} "
              f"({r['gap_in_atr']:+.2f} ATR)")
        print(f"  SHORT ที่ {r['entry']:.3f}  SL {r['stop']:.3f}  "
              f"TP {r['target']:.3f}  ({r['risk_price']:.3f}/oz = 1R)")

    # ------------------------------------------------ resolve the open records
    m5t = m5["time"].astype(np.int64)
    m5h = m5["high"].astype(float)
    m5l = m5["low"].astype(float)
    m5c = m5["close"].astype(float)
    resolved = 0
    for r in recs:
        if r["status"] != "open":
            continue
        k0 = int(np.searchsorted(m5t, r["signal_epoch"] + 900))
        if k0 >= len(m5t) or m5t[k0] != r["signal_epoch"] + 900:
            continue
        entry, stop, tgt = r["entry"], r["stop"], r["target"]
        end = min(k0 + TIME_STOP_M5, len(m5t))
        px = why = None
        for k in range(k0, end):
            if m5h[k] >= stop:
                px, why = stop, "stop"
                break
            if m5l[k] <= tgt:
                px, why = tgt, "target"
                break
        if px is None:
            if end - k0 < TIME_STOP_M5:
                continue                  # still running
            px, why = float(m5c[end - 1]), "time"
        g = -(px - entry) / r["risk_price"]
        sp = 0.090
        cost = sp + COMMISSION_RT + 2.0 * SLIP_PER_FILL
        r.update(status="closed", outcome=why, gross_R=round(g, 4),
                 net_R=round(g - cost / r["risk_price"], 4),
                 cost_note="spread assumed 0.090 at resolution; the rollover "
                           "figure is still unmeasured")
        resolved += 1

    # ------------------------------------------------ freeze / report the protocol
    closed = [r for r in recs if r["status"] == "closed"]
    if recs and proto is None:
        first = min(r["signal_epoch"] for r in recs)
        proto = dict(
            frozen_utc=now.isoformat(),
            first_signal_utc=datetime.fromtimestamp(first, timezone.utc).isoformat(),
            rule="26 weeks from the first forward signal OR 30 non-overlapping "
                 "events, whichever comes SECOND",
            end_by_time_utc=(datetime.fromtimestamp(first, timezone.utc)
                             + timedelta(weeks=SHADOW_WEEKS)).isoformat(),
            required_events=SHADOW_EVENTS,
            may_not="stop early on a favourable result, extend on an "
                    "unfavourable one, or change any parameter mid-run",
            geometry=dict(gap_atr=GAP_ATR, stop_atr=STOP_ATR, rr=RR,
                          time_stop_m5=TIME_STOP_M5, atr_n=ATR_N),
        )
        save(PROTO, proto)
        print(f"\nแช่แข็งกฎการหยุดไว้ที่ {PROTO}")

    save(LOG, {"records": recs})
    print(f"\nสัญญาณใหม่รอบนี้ {len(new)}   ปิดไปรอบนี้ {resolved}")
    print(f"บันทึกรวม {len(recs)} รายการ  ปิดแล้ว {len(closed)}  "
          f"ยังเปิด {len(recs)-len(closed)}   ที่ {LOG}")
    if proto:
        end = datetime.fromisoformat(proto["end_by_time_utc"])
        print(f"เริ่มนับจาก {proto['first_signal_utc'][:16]}  "
              f"ครบ 26 สัปดาห์ {proto['end_by_time_utc'][:16]}  "
              f"เหลือ {(end-now).days} วัน")
        print(f"ต้องได้ {SHADOW_EVENTS} เหตุการณ์ — ได้แล้ว {len(closed)}")
        print("จะจบเมื่อครบ 'ทั้งสองเงื่อนไข' ไม่ใช่เงื่อนไขใดเงื่อนไขหนึ่ง")
    if closed:
        nets = np.array([r["net_R"] for r in closed], float)
        print(f"\nผลที่ปิดแล้ว {len(nets)} ไม้: net เฉลี่ย {nets.mean():+.4f} R  "
              f"ชนะ {100*np.mean(nets>0):.0f}%")
        print("ยังไม่มีความหมายทางสถิติจนกว่าจะครบกฎการหยุด")

    print("\n" + "!" * 96)
    print("ยังไม่ได้วัด: slippage ในช่วง 21:00-23:00 UTC ซึ่งเป็นเวลาที่ W1 เทรดจริง")
    print("ค่า 0.0165 ที่ใช้อยู่วัดมาจากช่วงตลาดคึกคัก และ net ของ W1 ตายที่ต้นทุน 7 เท่า")
    print("ไม่ว่า shadow จะให้ผลอย่างไร เรื่องนี้ยังไม่จบจนกว่าจะวัดค่านั้นได้")
    print("!" * 96)
    print("\nไม่มีการส่งคำสั่งใด ๆ จากไฟล์นี้  สถานะคงเดิม: NO TRADE")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
