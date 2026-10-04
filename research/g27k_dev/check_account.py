"""HANDOFF_G27K_FINAL.md section 3.1: does the connected MT5 account carry the four markets, and can the minimum lot respect the 1 % rule?
Read-only: account info, symbol specs (contract size, tick value/size, min lot, lot step, real swap long), server clock vs UTC, and the
minimum-lot risk at the research SL distances (gold 1.0 %, silver 1.9 %, BTC 3.1 %, JP225 1.4 % of price). Places no orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SL_PCT = {"XAUUSD": 0.010, "XAGUSD": 0.019, "BTCUSD": 0.031, "JP225": 0.014,      # handoff 3.1 step 3
          "USDJPY": 0.006}   # USDJPY: provisional until its trade list exists; only used for the min-lot printout
WANTED = ["XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY"]
TRADE_MODE = {0: "DEMO", 1: "CONTEST", 2: "REAL"}


def variants(base):
    """Naming a broker may use for the same market (Exness Standard Cent appends 'c'; indices vary)."""
    out = [base, base + "c", base + "m", base + ".c", base + "_c"]
    if base == "JP225":
        out += ["JP225Cash", "JPN225", "Nikkei225", "JP225c", "JPN225c", "JP225m", "NIKKEI"]
    if base == "BTCUSD":
        out += ["BTCUSDm", "BTCUSDT"]
    return out


def main():
    if not mt5.initialize(path=TERMINAL):
        if not mt5.initialize():
            print("initialize failed:", mt5.last_error()); return 1
    a = mt5.account_info()
    if a is None:
        print("account_info failed:", mt5.last_error()); mt5.shutdown(); return 1
    print(f"account   : login {a.login} | {TRADE_MODE.get(a.trade_mode, a.trade_mode)} | server {a.server} | company {a.company}")
    print(f"            currency {a.currency} | balance {a.balance:,.2f} | equity {a.equity:,.2f} | leverage 1:{a.leverage} | "
          f"margin mode {a.margin_mode} | trade allowed {a.trade_allowed} | expert allowed {a.trade_expert}")
    pos = mt5.positions_total(); ords = mt5.orders_total()
    print(f"            open positions {pos} | pending orders {ords}")

    tick = mt5.symbol_info_tick("XAUUSD") or mt5.symbol_info_tick("XAUUSDc")
    if tick:
        srv = datetime.fromtimestamp(tick.time, tz=timezone.utc); now = datetime.now(timezone.utc)
        off = (srv - now).total_seconds() / 3600
        print(f"server time: {srv:%Y-%m-%d %H:%M:%S} (from last tick) | PC UTC now {now:%Y-%m-%d %H:%M:%S} | offset {off:+.1f} h "
              f"-> {'GMT+0 as expected' if abs(off) < 0.75 else 'NOT GMT+0, H4 bar edges will differ'}")

    all_syms = {s.name for s in mt5.symbols_get()}
    rows = []
    for base in WANTED:
        name = next((v for v in variants(base) if v in all_syms), None)
        if name is None:
            near = sorted(n for n in all_syms if base[:3] in n.upper())[:8]
            print(f"\n{base}: NOT FOUND. closest names on this account: {near}")
            rows.append(dict(base=base, found=False)); continue
        if not mt5.symbol_info(name).visible:
            mt5.symbol_select(name, True)
        s = mt5.symbol_info(name); t = mt5.symbol_info_tick(name)
        price = t.ask if t and t.ask else s.ask or s.bid
        sl_dist = price * SL_PCT[base]
        per_lot = (sl_dist / s.trade_tick_size) * s.trade_tick_value if s.trade_tick_size else float("nan")
        risk_min = per_lot * s.volume_min
        pct = risk_min / a.balance if a.balance else float("nan")
        need = risk_min / 0.01
        swap_night = (s.swap_long / 1e4 * price * s.trade_contract_size) if s.swap_mode == 1 else s.swap_long
        print(f"\n{base} -> {name}")
        print(f"  contract size {s.trade_contract_size:g} | tick size {s.trade_tick_size:g} | tick value {s.trade_tick_value:g} {a.currency}"
              f" | digits {s.digits} | point {s.point:g}")
        print(f"  lot min {s.volume_min:g} | step {s.volume_step:g} | max {s.volume_max:g} | spread {s.spread} points"
              f" ({s.spread * s.point:g} price) | stops level {s.trade_stops_level}")
        print(f"  swap long {s.swap_long:g} | swap short {s.swap_short:g} | swap mode {s.swap_mode} | 3-day swap on weekday {s.swap_rollover3days}")
        print(f"  price now {price:,.5g} | research SL {SL_PCT[base]:.1%} = {sl_dist:,.5g} | risk per 1.00 lot {per_lot:,.2f} {a.currency}")
        print(f"  MIN LOT ({s.volume_min:g}) RISKS {risk_min:,.2f} {a.currency} = {pct:.2%} of balance"
              f"  -> {'OK (<= 1 %)' if pct <= 0.01 else 'OVER the 1 % rule'} | balance needed for 1 %: {need:,.0f} {a.currency}")
        rows.append(dict(base=base, name=name, found=True, contract=s.trade_contract_size, tick_size=s.trade_tick_size,
                         tick_value=s.trade_tick_value, vol_min=s.volume_min, vol_step=s.volume_step, vol_max=s.volume_max, spread_points=s.spread,
                         swap_long=s.swap_long, swap_short=s.swap_short, swap_mode=s.swap_mode, rollover3=s.swap_rollover3days,
                         price=price, sl_dist=sl_dist, risk_per_lot=per_lot, risk_min_lot=risk_min, pct_of_balance=pct,
                         balance_for_1pct=need, trade_mode=s.trade_mode, digits=s.digits))
    out = dict(checked_utc=datetime.now(timezone.utc).isoformat(), login=a.login, server=a.server, company=a.company,
               account_type=TRADE_MODE.get(a.trade_mode, a.trade_mode), currency=a.currency, balance=a.balance, leverage=a.leverage,
               open_positions=pos, symbols=rows)
    with open("data/g27k_account_check.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nwritten data/g27k_account_check.json")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
