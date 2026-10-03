"""HANDOFF_G27K_FINAL.md 3.1, follow-up: server clock read from a market that trades at the weekend, swap converted to bp per night and
compared with the costs the research used (data/bundle/broker_specs.json), margin per minimum lot, and the balance the 1 % rule needs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SL_PCT = {"XAUUSD": 0.010, "XAGUSD": 0.019, "BTCUSD": 0.031, "JP225": 0.014}
ORDER_BUY = 0


def main():
    if not mt5.initialize(path=TERMINAL) and not mt5.initialize():
        print("initialize failed:", mt5.last_error()); return
    a = mt5.account_info()
    specs = json.loads(Path("data/bundle/broker_specs.json").read_text()) if Path("data/bundle/broker_specs.json").exists() else {}

    print("== server clock (tick times; BTCUSD trades at the weekend, metals and the index do not)")
    now = datetime.now(timezone.utc)
    for s in ("BTCUSD", "XAUUSD", "JP225"):
        t = mt5.symbol_info_tick(s)
        if t and t.time:
            st = datetime.fromtimestamp(t.time, tz=timezone.utc)
            print(f"  {s:7s} last tick {st:%Y-%m-%d %H:%M:%S} | vs PC UTC {now:%Y-%m-%d %H:%M:%S} | diff {(st - now).total_seconds() / 3600:+.2f} h")
    print(f"  interpretation: a diff near 0 on a market that is open now = server is GMT+0; a large negative diff on a closed market is just a stale tick")

    print("\n== swap per night, and what the research used")
    for base in SL_PCT:
        s = mt5.symbol_info(base)
        if s is None:
            continue
        t = mt5.symbol_info_tick(base); price = t.ask if t and t.ask else s.ask or s.bid
        # swap_mode 1 = points: money per lot per night = swap_points * point * contract_size
        money = s.swap_long * s.point * s.trade_contract_size if s.swap_mode == 1 else float("nan")
        notional = price * s.trade_contract_size
        bp = -money / notional * 1e4 if notional else float("nan")
        used = specs.get(base, {})
        print(f"  {base:7s} swap_long {s.swap_long:>9.1f} pts (mode {s.swap_mode}) = {money:>8.2f} {a.currency}/lot/night on notional {notional:>12,.0f}"
              f" -> {bp:5.2f} bp/night | research used {used.get('swap_long_bp', float('nan')):5.2f} bp"
              f" | cost_rt {used.get('cost_rt_bp', float('nan')):.2f} bp vs live spread {s.spread * s.point / price * 1e4:5.2f} bp")

    print("\n== margin and the 1 % rule")
    tot_margin = 0.0
    for base in SL_PCT:
        s = mt5.symbol_info(base)
        if s is None:
            continue
        t = mt5.symbol_info_tick(base); price = t.ask if t and t.ask else s.ask or s.bid
        m = mt5.order_calc_margin(ORDER_BUY, base, s.volume_min, price)
        risk = (price * SL_PCT[base] / s.trade_tick_size) * s.trade_tick_value * s.volume_min
        tot_margin += m or 0
        print(f"  {base:7s} min lot {s.volume_min:>5g} | margin {m:>8.2f} {a.currency} | risk at the research SL {risk:>7.2f}"
              f" | balance for 1 % {risk / 0.01:>9,.0f} | for 0.5 % (brake) {risk / 0.005:>10,.0f}")
    need = max((((mt5.symbol_info_tick(b).ask or mt5.symbol_info(b).bid) * SL_PCT[b] / mt5.symbol_info(b).trade_tick_size)
                * mt5.symbol_info(b).trade_tick_value * mt5.symbol_info(b).volume_min) / 0.01 for b in SL_PCT if mt5.symbol_info(b))
    print(f"  all four at once: margin {tot_margin:,.2f} {a.currency} | balance so every market fits the 1 % rule: {need:,.0f} {a.currency}"
          f" | in a cent account that is {need * 100:,.0f} USC (= ${need:,.0f} of real money)")

    print("\n== trading sessions (server time) and symbol state")
    for base in SL_PCT:
        s = mt5.symbol_info(base)
        if s is None:
            continue
        days = []
        for d in range(7):
            q = mt5.symbol_info_session_quote(base, d, 0)
            days.append(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d] if q else None)
        print(f"  {base:7s} quotes on {[d for d in days if d] or 'n/a'} | trade mode {s.trade_mode} (4 = full) | "
              f"filling {s.filling_mode} | expiration {s.expiration_mode}")

    print("\n== cent-account symbols on this terminal")
    names = {x.name for x in mt5.symbols_get()}
    cent = sorted(n for n in names if n.endswith("c") and n[:-1] in ("XAUUSD", "XAGUSD", "BTCUSD", "JP225"))
    print("  ", cent or "none - this terminal is on the Standard (non-cent) demo account")
    mt5.shutdown()


if __name__ == "__main__":
    main()
