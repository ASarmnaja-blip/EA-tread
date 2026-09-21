"""Place one tightly guarded DEMO-only pending order for execution testing.

The order is explicitly labelled EXECUTION TEST ONLY because the research
engine has not promoted a champion.  It is a forward observation of a live
breakout hypothesis and must not be counted as historical strategy evidence.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "demo_execution_log.jsonl"
SYMBOL = "XAUUSD"
MAGIC = 26092101


def write_log(payload: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def main() -> int:
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        acct = mt5.account_info()
        if acct is None:
            raise SystemExit("No MT5 account")
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if acct.trade_mode != demo_mode or not any(x in acct.server.lower() for x in ("demo", "trial")):
            raise SystemExit(f"REFUSED: account is not verified DEMO: mode={acct.trade_mode} server={acct.server}")
        if mt5.positions_get(symbol=SYMBOL):
            raise SystemExit("REFUSED: an XAUUSD position already exists")
        if mt5.orders_get(symbol=SYMBOL):
            raise SystemExit("REFUSED: an XAUUSD pending order already exists")

        mt5.symbol_select(SYMBOL, True)
        info = mt5.symbol_info(SYMBOL)
        tick = mt5.symbol_info_tick(SYMBOL)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 6)
        if info is None or tick is None or rates is None or len(rates) < 4:
            raise SystemExit("Missing live symbol data")
        if abs(info.volume_min - 0.01) > 1e-12:
            raise SystemExit(f"REFUSED: broker minimum changed to {info.volume_min}")

        point_pad = 0.20
        recent_high = max(float(r[2]) for r in rates[-3:])
        recent_low = min(float(r[3]) for r in rates[-4:])
        entry = round(recent_high + point_pad, info.digits)
        stop = round(recent_low - 0.50, info.digits)
        risk = entry - stop
        target = round(entry + 1.50 * risk, info.digits)
        if entry <= tick.ask or risk <= 5.0 or risk >= 20.0 or target >= 4400.0:
            raise SystemExit(f"REFUSED: live geometry invalid ask={tick.ask} entry={entry} stop={stop} target={target}")

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY_STOP,
            "price": entry,
            "sl": stop,
            "tp": target,
            "deviation": 50,
            "magic": MAGIC,
            "comment": "EXEC_TEST_ONLY_BREAKOUT",
            "type_time": mt5.ORDER_TIME_SPECIFIED,
            "expiration": int(time.time() + 2 * 3600),
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        check = mt5.order_check(request)
        record = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "account": acct.login, "server": acct.server,
            "trade_mode": acct.trade_mode, "label": "EXECUTION TEST ONLY",
            "hypothesis": "London impulse continuation confirmed by XAG strength and DXY weakness",
            "quoted_bid": tick.bid, "quoted_ask": tick.ask,
            "recent_high": recent_high, "recent_low": recent_low,
            "request": request, "check": check._asdict() if check else None,
        }
        if check is None or check.retcode != 0:
            record["send"] = None; write_log(record)
            raise SystemExit(f"order_check refused: {check}")
        result = mt5.order_send(request)
        record["send"] = result._asdict() if result else None
        write_log(record)
        if result is None or result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
            raise SystemExit(f"order_send failed: {result}")
        print(json.dumps({
            "status": "PLACED", "ticket": result.order, "account": acct.login,
            "server": acct.server, "entry": entry, "stop": stop,
            "target": target, "expiry_utc": datetime.fromtimestamp(request["expiration"], timezone.utc).isoformat(),
            "label": "EXECUTION TEST ONLY",
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
