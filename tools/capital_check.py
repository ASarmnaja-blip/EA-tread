#!/usr/bin/env python3
"""
Which instruments can this account actually trade at the target risk?

The binding constraint on a small account is not the strategy. It is that
the broker minimum lot cannot shrink, so for each symbol there is a floor:

    min-lot risk = min_lot x contract_size x (SL multiple x ATR)

If that floor is larger than the risk you intend to take, the EA will keep
rejecting setups and you will never know why. This script reads the live
contract specification and current ATR for every symbol your broker offers
and ranks them by how well they fit.

    pip install MetaTrader5 pandas
    python tools/capital_check.py --equity 1000 --risk 0.5
    python tools/capital_check.py --equity 1000 --risk 0.5 --filter XAU,EUR,GBP,XAG

Gold on a 1000-unit account at a 1.8xATR stop currently floors around 2% per
trade. Major FX pairs on the same account floor near 0.1-0.2%. That gap is
the difference between an account that can size properly and one that cannot.
"""
import argparse
import sys


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--equity", type=float, default=None,
                    help="account equity in account currency (default: read from terminal)")
    ap.add_argument("--risk", type=float, default=0.5,
                    help="target risk %% per trade (default 0.5)")
    ap.add_argument("--sl-atr", type=float, default=1.8,
                    help="stop distance in ATR (default 1.8, the tested value)")
    ap.add_argument("--atr-period", type=int, default=14)
    ap.add_argument("--filter", default="",
                    help="comma-separated substrings, e.g. XAU,EUR,GBP")
    ap.add_argument("--max-rows", type=int, default=40)
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
        import numpy as np
    except ImportError as exc:
        die(f"missing dependency: {exc}. Run: pip install MetaTrader5 numpy")

    if not mt5.initialize():
        die(f"could not attach to the MT5 terminal: {mt5.last_error()}")

    try:
        info = mt5.account_info()
        if info is None:
            die("could not read account info")
        equity = args.equity if args.equity is not None else info.equity
        currency = info.currency

        print(f"account   : {equity:,.2f} {currency}  (leverage 1:{info.leverage})")
        print(f"target    : {args.risk:.2f}% per trade = {equity*args.risk/100:,.2f} {currency}")
        print(f"stop model: {args.sl_atr} x ATR({args.atr_period}) on M15")
        print()

        wanted = [w.strip().upper() for w in args.filter.split(",") if w.strip()]
        rows = []

        for sym in mt5.symbols_get():
            name = sym.name
            if wanted and not any(w in name.upper() for w in wanted):
                continue
            if not sym.visible and not mt5.symbol_select(name, True):
                continue

            rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_M15, 0,
                                            args.atr_period + 60)
            if rates is None or len(rates) < args.atr_period + 2:
                continue

            high, low = rates["high"], rates["low"]
            close_prev = rates["close"][:-1]
            tr = np.maximum(high[1:] - low[1:],
                            np.maximum(abs(high[1:] - close_prev),
                                       abs(low[1:] - close_prev)))
            atr = float(tr[-args.atr_period:].mean())
            if atr <= 0:
                continue

            sl_distance = args.sl_atr * atr
            tick_size = sym.trade_tick_size or sym.point
            tick_value = sym.trade_tick_value
            if not tick_size or not tick_value:
                continue

            # money at risk for one minimum lot over the stop distance
            min_risk = sym.volume_min * (sl_distance / tick_size) * tick_value
            if min_risk <= 0:
                continue

            floor_pct = 100.0 * min_risk / equity
            ideal_lot = (equity * args.risk / 100.0) / ((sl_distance / tick_size) * tick_value)
            spread_pts = sym.spread
            spread_cost_r = (spread_pts * sym.point) / sl_distance if sl_distance else 0

            rows.append(dict(name=name, atr=atr, floor=floor_pct,
                             min_risk=min_risk, ideal=ideal_lot,
                             vmin=sym.volume_min, vstep=sym.volume_step,
                             cost_r=spread_cost_r,
                             contract=sym.trade_contract_size))

        if not rows:
            die("no tradeable symbols matched. Check --filter, or open the "
                "symbols in Market Watch so history is available.")

        rows.sort(key=lambda r: r["floor"])

        print(f"{'symbol':<16}{'ATR M15':>11}{'min-lot risk':>14}{'% equity':>10}"
              f"{'lot for target':>16}{'spread':>9}  fit")
        print("-" * 88)
        for r in rows[:args.max_rows]:
            if r["floor"] <= args.risk:
                fit = "FITS - can size up from minimum"
            elif r["floor"] <= args.risk * 2:
                fit = "tight - minimum lot is near the cap"
            else:
                fit = f"too coarse - needs {r['min_risk']/(args.risk/100):,.0f} equity"
            print(f"{r['name']:<16}{r['atr']:>11.5f}{r['min_risk']:>14.2f}"
                  f"{r['floor']:>9.3f}%{r['ideal']:>16.4f}{r['cost_r']:>8.3f}R  {fit}")

        if len(rows) > args.max_rows:
            print(f"... {len(rows)-args.max_rows} more (raise --max-rows)")

        print()
        print("min-lot risk = the SMALLEST position this broker will accept, in money.")
        print("'lot for target' below volume_min means the symbol cannot be traded at")
        print("your target risk no matter what the strategy does.")
        print("'spread' is the round-turn cost as a fraction of R - compare it against")
        print("the strategy's expectancy before trusting any backtest.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
