"""Tasks 1-3 of research/g27k_dev/handoff/MT5_TASKS.md, read-only on whichever account the terminal is logged into.

Writes, into this folder:
  <prefix>symbols.csv     task 1: trade_mode, contract size, lot min/step/max, margin and swap per symbol
  <prefix>margin.csv      task 3: OrderCalcMargin for one lot, buy and sell, with the effective leverage it implies
  spread_by_hour.csv      task 2: median and p90 spread per symbol, UTC hour and weekday, from real ticks
  spread_daily.csv        task 2: the same per calendar day

The prefix is "cent_" when the terminal is on a cent account (balance currency ending in C), otherwise "demo_", so a later run on
the real cent account cannot overwrite the demo files. Places no orders and modifies nothing on the account.

Usage: python collect_mt5.py [--days 60] [--symbols XAUUSD,...] [--skip-ticks]
"""
from __future__ import annotations

import argparse
import pathlib
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
WANT = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY", "JP225"]
MODE = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
CALC = {0: "forex", 1: "futures", 2: "cfd", 3: "cfdindex", 4: "cfdleverage", 5: "forex_no_leverage"}
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def resolve(names, base):
    """The symbol on this account for a research market: exact, then the cent suffix, then a few broker variants."""
    for cand in (base, base + "c", base + "m", base + ".c"):
        if cand in names:
            return cand
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="how far back to ask for ticks")
    ap.add_argument("--symbols", default=",".join(WANT))
    ap.add_argument("--skip-ticks", action="store_true", help="symbols and margin only")
    a = ap.parse_args()
    if not mt5.initialize(path=TERMINAL) and not mt5.initialize():
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    acc = mt5.account_info()
    kind = MODE.get(acc.trade_mode, str(acc.trade_mode))
    cent = acc.currency.upper().endswith("C")
    prefix = "cent_" if cent else "demo_"
    print(f"account {acc.login} | {kind} | {acc.server} | {acc.currency} | balance {acc.balance:,.2f} | leverage 1:{acc.leverage}")
    print(f"writing files with prefix {prefix!r}")
    names = {s.name for s in mt5.symbols_get()}

    rows, mrows, picked = [], [], {}
    for base in [s.strip() for s in a.symbols.split(",") if s.strip()]:
        name = resolve(names, base)
        if name is None:
            print(f"  {base:8s} not on this account")
            rows.append(dict(research_market=base, symbol="", present=False))
            continue
        if not mt5.symbol_info(name).visible:
            mt5.symbol_select(name, True)
        s = mt5.symbol_info(name)
        t = mt5.symbol_info_tick(name)
        price = (t.ask if t and t.ask else 0.0) or s.ask or s.bid
        picked[base] = name
        # swap in points -> money per lot per night -> basis points of the contract's notional
        swap_money = s.swap_long * s.point * s.trade_contract_size if s.swap_mode == 1 else float("nan")
        notional = price * s.trade_contract_size
        rows.append(dict(
            research_market=base, symbol=name, present=True, account=kind, server=acc.server, currency=acc.currency,
            trade_mode=s.trade_mode, tradable=s.trade_mode == 4, calc_mode=s.trade_calc_mode, calc_mode_name=CALC.get(s.trade_calc_mode, ""),
            contract_size=s.trade_contract_size, digits=s.digits, point=s.point, tick_size=s.trade_tick_size, tick_value=s.trade_tick_value,
            volume_min=s.volume_min, volume_step=s.volume_step, volume_max=s.volume_max, stops_level=s.trade_stops_level,
            margin_currency=s.currency_margin, profit_currency=s.currency_profit, account_leverage=acc.leverage,
            swap_mode=s.swap_mode, swap_long_points=s.swap_long, swap_short_points=s.swap_short,
            swap_long_money_per_lot=swap_money, swap_long_bp_night=(-swap_money / notional * 1e4) if notional else float("nan"),
            swap_rollover3_weekday=s.swap_rollover3days, price_at_read=price,
            spread_points_now=s.spread, spread_bp_now=(s.spread * s.point / price * 1e4) if price else float("nan"),
            read_utc=datetime.now(timezone.utc).isoformat(timespec="seconds")))
        for side, otype in (("buy", mt5.ORDER_TYPE_BUY), ("sell", mt5.ORDER_TYPE_SELL)):
            px = (t.ask if side == "buy" else t.bid) if t else price
            m = mt5.order_calc_margin(otype, name, 1.0, px or price)
            mrows.append(dict(research_market=base, symbol=name, account=kind, side=side, price=px or price, volume=1.0,
                              margin_1lot=m, notional=(px or price) * s.trade_contract_size,
                              leverage_effective=((px or price) * s.trade_contract_size / m) if m else float("nan"),
                              calc_mode_name=CALC.get(s.trade_calc_mode, ""), account_leverage=acc.leverage))
        print(f"  {base:8s} -> {name:9s} trade_mode {s.trade_mode} | contract {s.trade_contract_size:g} | lot {s.volume_min:g}/{s.volume_step:g}"
              f" | calc {CALC.get(s.trade_calc_mode, s.trade_calc_mode)}")

    pd.DataFrame(rows).to_csv(HERE / f"{prefix}symbols.csv", index=False)
    M = pd.DataFrame(mrows)
    M.to_csv(HERE / f"{prefix}margin.csv", index=False)
    print(f"\nwrote {prefix}symbols.csv ({len(rows)} rows) and {prefix}margin.csv ({len(M)} rows)")
    if len(M):
        print(M[["symbol", "side", "price", "margin_1lot", "leverage_effective"]].round(2).to_string(index=False))
    if a.skip_ticks:
        mt5.shutdown()
        return

    #--- task 2: real spreads from ticks
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    hour_rows, day_rows = [], []
    for base, name in picked.items():
        s = mt5.symbol_info(name)
        ticks = mt5.copy_ticks_range(name, start, end, mt5.COPY_TICKS_INFO)
        if ticks is None or len(ticks) == 0:
            ticks = mt5.copy_ticks_range(name, start, end, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            print(f"  {name:9s} no ticks returned ({mt5.last_error()})")
            continue
        T = pd.DataFrame(ticks)
        T["ts"] = pd.to_datetime(T.time_msc, unit="ms", utc=True)
        T = T[(T.bid > 0) & (T.ask > 0) & (T.ask >= T.bid)]
        if T.empty:
            print(f"  {name:9s} ticks had no usable bid/ask")
            continue
        T["spread"] = T.ask - T.bid
        T["mid"] = (T.ask + T.bid) / 2
        T["spread_bp"] = T.spread / T.mid * 1e4
        T["hour_utc"] = T.ts.dt.hour
        T["weekday"] = T.ts.dt.weekday.map(lambda i: WD[i])
        T["date"] = T.ts.dt.date
        g = T.groupby(["hour_utc", "weekday"])
        h = g.agg(n_ticks=("spread", "size"), spread_median=("spread", "median"), spread_p90=("spread", lambda x: x.quantile(0.9)),
                  mid_median=("mid", "median"), spread_bp_median=("spread_bp", "median"),
                  spread_bp_p90=("spread_bp", lambda x: x.quantile(0.9))).reset_index()
        h.insert(0, "symbol", name)
        h.insert(1, "research_market", base)
        hour_rows.append(h)
        d = T.groupby("date").agg(n_ticks=("spread", "size"), spread_bp_median=("spread_bp", "median"),
                                  spread_bp_p90=("spread_bp", lambda x: x.quantile(0.9)),
                                  spread_median=("spread", "median"), mid_median=("mid", "median")).reset_index()
        d.insert(0, "symbol", name)
        d.insert(1, "research_market", base)
        day_rows.append(d)
        print(f"  {name:9s} {len(T):>9,} ticks {T.ts.min():%Y-%m-%d} .. {T.ts.max():%Y-%m-%d} | median {T.spread_bp.median():5.2f} bp"
              f" | p90 {T.spread_bp.quantile(0.9):5.2f} bp | model uses max(2, median+1) bp")
    if hour_rows:
        pd.concat(hour_rows).to_csv(HERE / "spread_by_hour.csv", index=False)
        pd.concat(day_rows).to_csv(HERE / "spread_daily.csv", index=False)
        print(f"\nwrote spread_by_hour.csv and spread_daily.csv")
    mt5.shutdown()


if __name__ == "__main__":
    main()
