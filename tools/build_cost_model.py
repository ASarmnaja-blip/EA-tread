"""Build the measured cost model for every symbol, in PRICE units.

Until today this project charged a spread and an assumed slippage and nothing
else. Two components were missing entirely:

  COMMISSION, which was never charged anywhere. Measured from the demo's own
  deal history it is $7.00 per lot per side on XAUUSD - $0.14 per ounce per
  round turn, about 2.7 times the demo spread of 0.052. On a zero-spread
  account it is the ENTIRE cost: EURUSD and USDJPY quote at spread 0, which is
  not the same as trading for free.

  SWAP for anything but gold, which was charged in gold's units to every
  instrument and produced a GBPUSD mean of -65.95 R. It is available read-only
  from symbol_info, so it never needed to be guessed or transferred.

Commission is quoted by the broker in ACCOUNT CURRENCY per lot, and the rest of
the pipeline works in price units, so the conversion has to be exact. It is
done with order_calc_profit over a one-unit price move rather than by hand from
contract sizes, because USDJPY is quoted in JPY while the commission is in USD
and a hand conversion is where that kind of thing goes wrong.

Read-only. No order is sent by this file.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("MetaTrader5 package not installed")

OUT = Path("data/cost_model.json")

# Measured on 2026-09-21/22 from this account's own closed deals, by
# tools/demo_slippage_probe.py. Account currency per lot per side.
COMMISSION_USD_PER_LOT_SIDE = {
    "XAUUSD": 7.00,
    "XAGUSD": 3.50,
    "EURUSD": 2.50,
    "GBPUSD": 2.50,
    "USDJPY": 2.50,
    "US500": 0.131,
}
SYMBOLS = tuple(COMMISSION_USD_PER_LOT_SIDE)


def value_per_price_unit(sym: str, price: float) -> float | None:
    """Account-currency value of a one-price-unit move on one lot."""
    p = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, sym, 1.0, price, price + 1.0)
    if p is None or p == 0:
        return None
    return float(p)


def main() -> int:
    if not mt5.initialize():
        print("initialize failed:", mt5.last_error())
        return 1
    ai = mt5.account_info()
    print(f"account {ai.login} @ {ai.server}  trade_mode={ai.trade_mode} "
          f"(0=DEMO)  currency {ai.currency}   READ-ONLY\n")

    out = {}
    print(f"{'symbol':9s}{'spread':>10s}{'comm/rt':>11s}{'swapL/n':>12s}"
          f"{'swapS/n':>12s}{'per-unit $':>12s}")
    for s in SYMBOLS:
        info = mt5.symbol_info(s)
        if info is None:
            print(f"{s:9s}  ไม่พบสัญลักษณ์ -> NOT MEASURED")
            continue
        if not info.visible:
            mt5.symbol_select(s, True)
            info = mt5.symbol_info(s)
        tick = mt5.symbol_info_tick(s)
        px = float(tick.ask) if tick and tick.ask > 0 else float(info.ask or 1.0)
        spread = float(tick.ask - tick.bid) if tick and tick.ask > 0 else None
        vpu = value_per_price_unit(s, px)
        if vpu is None:
            print(f"{s:9s}  แปลงหน่วยไม่ได้ -> NOT MEASURED")
            continue
        comm_usd = COMMISSION_USD_PER_LOT_SIDE[s]
        comm_price_rt = 2.0 * comm_usd / vpu
        # swap_mode 1 is "points"; the broker quotes it per lot per night
        swap_l = float(info.swap_long) * float(info.point)
        swap_s = float(info.swap_short) * float(info.point)
        out[s] = dict(
            spread_live=spread,
            commission_usd_per_lot_side=comm_usd,
            value_per_price_unit=vpu,
            commission_price_round_turn=comm_price_rt,
            swap_long_price_per_night=swap_l,
            swap_short_price_per_night=swap_s,
            point=float(info.point), digits=int(info.digits),
            contract=float(info.trade_contract_size),
            volume_min=float(info.volume_min),
            swap_mode=int(info.swap_mode),
        )
        print(f"{s:9s}{spread:10.5f}{comm_price_rt:11.5f}{swap_l:12.6f}"
              f"{swap_s:12.6f}{vpu:12.2f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nบันทึกที่ {OUT}")
    print("ทั้งหมดนี้เป็นค่าของบัญชี DEMO บัญชีจริงอาจต่างออกไป")
    print("จึงยังต้องรายงานผลที่ตัวคูณต้นทุน 1x / 1.5x / 3x / 7x ตามเดิม")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
