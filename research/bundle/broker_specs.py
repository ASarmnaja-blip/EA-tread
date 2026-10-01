"""X6 input (docs/BUNDLE_2026-10-01_PREREG.md): read-only broker specification of every cached market from the running MT5 terminal (demo
account enforced): swap mode and values, triple-swap day, contract size, plus the median H1 spread of the last 365 days from the cache.
Converts both to basis points of notional: cost_rt_bp = max(2, median spread + 1); swap_long_bp / swap_short_bp per night (positive =
the trader pays). Writes data/bundle/broker_specs.json. Usage: python research/bundle/broker_specs.py"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "USDJPY", "AUDUSD", "USDCHF", "US500", "USTEC", "USOIL", "BTCUSD",
        "DE30", "JP225", "XCUUSD", "XPTUSD", "USDCNH", "USDINR", "USDMXN", "USDZAR"]


def main():
    import MetaTrader5 as mt5
    assert mt5.initialize(), mt5.last_error()
    a = mt5.account_info()
    assert a is not None and a.trade_mode == 0, "not a demo account: refusing"
    out = {}
    for s in SYMS:
        mt5.symbol_select(s, True)
        i = mt5.symbol_info(s)
        z = np.load(ROOT / "data" / "mt5" / f"{s}_H1.npz")
        last = z["t"] >= z["t"][-1] - 365 * 86400
        sp_bp = float(np.median(z["spread_points"][last] * float(z["point"]) / z["c"][last] * 1e4))
        px = float(z["c"][-1])
        def to_bp(v):
            m = i.swap_mode
            if m == 0:
                return 0.0
            if m == 1:                                   # points per lot per night
                return -v * i.point / px * 1e4
            if m in (5, 6):                              # annual interest, % of price
                return -v / 100 / 360 * 1e4
            notional = i.trade_contract_size * (1.0 if s.startswith("USD") else px)      # USD-quoted or USD-base symbols
            if s in ("DE30", "JP225"):
                notional = None
            return float("nan") if notional is None else -v / notional * 1e4
        out[s] = dict(swap_mode=int(i.swap_mode), swap_long=float(i.swap_long), swap_short=float(i.swap_short), rollover3=int(i.swap_rollover3days),
                      contract=float(i.trade_contract_size), currency_profit=i.currency_profit, price=px, median_spread_bp=sp_bp,
                      cost_rt_bp=max(2.0, sp_bp + 1.0), swap_long_bp=to_bp(i.swap_long), swap_short_bp=to_bp(i.swap_short))
        print(f"{s:<7s} mode {i.swap_mode} long {i.swap_long:9.3f} short {i.swap_short:9.3f} x3 day {i.swap_rollover3days} | spread {sp_bp:6.2f} bp "
              f"-> cost {out[s]['cost_rt_bp']:5.2f} bp | swap/night long {out[s]['swap_long_bp']:+.3f} bp short {out[s]['swap_short_bp']:+.3f} bp", flush=True)
    mt5.shutdown()
    (ROOT / "data" / "bundle" / "broker_specs.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
