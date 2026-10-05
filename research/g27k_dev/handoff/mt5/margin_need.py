"""How much margin the system actually needs, and the smallest account that can hold it.

Replays the research trades through the account rules (risk % of balance at entry, 25 % NAV brake, overlapping positions), sizes
every trade in real Cent lots, and tracks the margin used at the same time. Reports the peak margin as a share of the account,
the lowest margin level reached, and the balance at which the broker's minimum lot stops fitting the risk rule.

Leverage is the measured one: 1:2000 on gold, silver and USDJPY, 1:400 on BTC and ETH (Exness grants it despite the
forex_no_leverage calc mode). Exness margin call is at 60 % and stop-out at 0 %, read from the account.

Usage: python margin_need.py [--balances 10000,50000,100000] [--combo F,M30,H1]
"""
from __future__ import annotations

import argparse
import heapq
import math
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
HANDOFF = HERE.parent
# measured on the Cent account 2026-10-05: contract in units, minimum and step in lots, leverage actually granted
SPEC = {
    "XAUUSD": dict(sym="XAUUSDc", contract=1.0,    vmin=0.01, vstep=0.01, leverage=2000),
    "XAGUSD": dict(sym="XAGUSDc", contract=50.0,   vmin=0.01, vstep=0.01, leverage=2000),
    "BTCUSD": dict(sym="BTCUSDc", contract=0.01,   vmin=0.01, vstep=0.01, leverage=400),
    "ETHUSD": dict(sym="ETHUSDc", contract=0.01,   vmin=0.10, vstep=0.01, leverage=400),
    "USDJPY": dict(sym="USDJPYc", contract=1000.0, vmin=0.01, vstep=0.01, leverage=2000),
}
CENT_BP = {"XAUUSD": 0.58, "XAGUSD": 4.60, "BTCUSD": 1.28, "ETHUSD": 4.03, "USDJPY": 0.64}
MODEL_BP = {"XAUUSD": 2.0, "XAGUSD": 3.641, "BTCUSD": 2.0, "ETHUSD": 2.0, "USDJPY": 2.0}
BRAKE_ON, BRAKE_OFF, BRAKE_MULT = 0.25, 0.125, 0.5


def lots(risk_money_usc, entry, stop_pct, s):
    """Lots the broker accepts: round to nearest step, floored at the minimum. risk in USC, prices in USD."""
    risk_per_lot_usc = stop_pct * entry * s["contract"] * 100.0
    want = risk_money_usc / risk_per_lot_usc
    lot = math.floor(want / s["vstep"] + 0.5) * s["vstep"]
    return max(round(lot, 2), s["vmin"]), risk_per_lot_usc


def margin_usc(lot, entry, s):
    """Margin in USC: notional in USD over the granted leverage, times 100."""
    notional = lot * s["contract"] * (1.0 if s["sym"] != "USDJPYc" else 1.0) * entry
    if s["sym"] == "USDJPYc":
        notional = lot * s["contract"]          # FX: one lot is `contract` units of the base currency (USD)
    return notional / s["leverage"] * 100.0


def run(T, start_usc, risk_of, brake=True):
    ev = []
    for r in T.itertuples():
        ev.append((r.entry_time_utc, 0, r))
    ev.sort(key=lambda x: x[0])
    bal = peak = start_usc
    heap = []; open_m = 0.0; mult = 1.0
    peak_margin = 0.0; peak_margin_pct = 0.0; peak_at = None; min_level = float("inf"); min_level_at = None
    peak_open = 0; forced = 0; over_risk = 0; trades = 0
    curve = []
    for t, _, r in ev:
        while heap and heap[0][0] <= t:
            _, pnl, m = heapq.heappop(heap)
            bal += pnl; open_m -= m; peak = max(peak, bal); curve.append((heap and heap[0][0] or t, bal))
        if brake:
            dd = 1 - bal / peak
            if mult == 1.0 and dd >= BRAKE_ON:
                mult = BRAKE_MULT
            elif mult < 1.0 and dd <= BRAKE_OFF:
                mult = 1.0
        if bal <= 0:
            break
        s = SPEC[r.market]
        want_risk = risk_of(r.book) * mult * bal
        lot, rpl = lots(want_risk, r.entry_price, r.stop_pct, s)
        real_risk = lot * rpl
        if real_risk > want_risk * 1.5:
            over_risk += 1
        if lot <= s["vmin"] + 1e-9 and want_risk < rpl * s["vmin"]:
            forced += 1
        m = margin_usc(lot, r.entry_price, s)
        open_m += m
        trades += 1
        equity = bal                                  # closed-trade equity; open P&L is not tracked here
        if open_m > peak_margin:
            peak_margin, peak_at = open_m, t
        if equity > 0:
            peak_margin_pct = max(peak_margin_pct, open_m / equity)
            lvl = equity / open_m * 100 if open_m > 0 else float("inf")
            if lvl < min_level:
                min_level, min_level_at = lvl, t
        peak_open = max(peak_open, len(heap) + 1)
        heapq.heappush(heap, (r.exit_time_utc, lot * rpl * r.R_new / 1.0 * 1.0, m))
        # P&L in USC: lot x risk_per_lot x R
    while heap:
        _, pnl, m = heapq.heappop(heap)
        bal += pnl; open_m -= m
    return dict(final=bal, trades=trades, peak_margin_usc=peak_margin, peak_margin_pct=peak_margin_pct,
                peak_at=peak_at, min_margin_level=min_level, min_level_at=min_level_at, peak_open=peak_open,
                min_lot_forced=forced, over_risk=over_risk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balances", default="10000,20000,50000,100000,1000000")
    ap.add_argument("--books", default="F,M30,H1")
    a = ap.parse_args()
    books = [b.strip() for b in a.books.split(",")]
    T = []
    for b in books:
        X = pd.read_csv(HANDOFF / f"trades_{b}.csv.gz")
        X["book"] = b
        T.append(X)
    T = pd.concat(T, ignore_index=True)
    for c in ("entry_time_utc", "exit_time_utc"):
        T[c] = pd.to_datetime(T[c])
    T = T[T.market.isin(SPEC)].copy()
    f = T.market.map(lambda m: (CENT_BP[m] + 1.0) / MODEL_BP[m])
    T["R_new"] = T.R_gross - T.R_spread * f - T.R_swap            # real Cent spread plus the model's 1 bp allowance
    T = T.sort_values("entry_time_utc").reset_index(drop=True)
    risk_of = lambda b: 0.01 if b == "F" else 0.005

    print("margin per one lot at today's prices (USC), and what the minimum lot needs")
    print(f"  {'market':8s} {'symbol':9s} {'contract':>9s} {'min lot':>8s} {'leverage':>9s} {'margin/lot':>11s} {'margin at min lot':>18s}")
    px = T.groupby("market").entry_price.last()
    for m, s in SPEC.items():
        one = margin_usc(1.0, px[m], s)
        print(f"  {m:8s} {s['sym']:9s} {s['contract']:>9g} {s['vmin']:>8g} {'1:'+str(s['leverage']):>9s} {one:>11,.2f} {one*s['vmin']:>18,.2f}")

    print(f"\nreplay of {len(T):,} trades, books {'+'.join(books)}, G27K-F 1% + brake 25%, sleeves 0.5%, real Cent spreads")
    print(f"  {'start USC':>11s} {'= USD':>8s} {'final USC':>16s} {'peak margin':>13s} {'% of account':>13s} {'lowest margin level':>20s} {'max open':>9s} {'min-lot forced':>15s}")
    for b in [float(x) for x in a.balances.split(",")]:
        r = run(T, b, risk_of)
        lvl = r["min_margin_level"]
        print(f"  {b:>11,.0f} {b/100:>8,.0f} {r['final']:>16,.0f} {r['peak_margin_usc']:>13,.0f} {r['peak_margin_pct']:>12.2%} "
              f"{lvl:>19,.0f}% {r['peak_open']:>9d} {r['min_lot_forced']:>15d}")
    print("\n  margin level = equity / margin used. Exness calls margin at 60% and stops out at 0%, so a level above 100% is comfortable.")
    print("  equity here counts closed trades only, so the real level during an open drawdown is lower than shown.")


if __name__ == "__main__":
    main()
