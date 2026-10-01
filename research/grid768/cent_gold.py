"""Operator 2026-10-01: can a 10,000 USC cent account trade the report768 system on XAUUSDc?
XAUUSDc on the real account (data/spec_real_XAUUSDc.json, 2026-09-21): 1 oz per lot, minimum and step 0.01 lot, so 0.01 lot moves
1 USC per $1 of gold. Re-runs the gold-only trades of systems A (adds, 0.25 % per unit) and B (one unit, 1 % per trade) with whole
0.01-lot steps: lots = floor(target risk x balance / stop), never below 0.01 (the broker minimum). Equity marked at every H4 close.
Prints the risk the minimum lot forces now and over the five years, and the balance each target needs."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

M = "XAUUSD"
DEPOSITS = (10_000.0, 20_000.0, 40_000.0)            # USC
SYSTEMS = {"A": ("I4", 0.0025), "B": ("I1", 0.01)}


def lot_account(trades, risk, deposit):
    """One market, one position at a time: size each trade in whole 0.01 lots from the realised balance (1 USC per $1 per 0.01 lot)."""
    rows = []; bal = deposit
    for tr in sorted(trades, key=lambda r: r["t"]):
        stop = tr["risk"]                                     # $ distance of the first unit's stop = USC lost per 0.01 lot
        n = max(1, int(np.floor(risk * bal / stop)))
        unit = n * stop
        r = dict(tr, lots=n / 100, unit_usd=unit, pnl=unit * tr["R"], bal_before=bal, risk_frac=unit / bal)
        bal += r["pnl"]; r["bal_after"] = bal; rows.append(r)
    return rows


def main():
    X = G.features(G.frames(G.load_h1(M)), M, "H4")
    stop_now = 2 * X["a20"][-1]; price_now = X["c"][-1]
    print(f"gold now {price_now:,.0f}, ATR20 H4 {X['a20'][-1]:.1f} -> stop 2N = ${stop_now:.0f} = {stop_now:.0f} USC per 0.01 lot")
    for dep in DEPOSITS:
        print(f"  {dep:,.0f} USC: 0.01 lot risks {stop_now / dep:.2%} per unit now")
    for k, (I, risk) in SYSTEMS.items():
        print(f"  system {k} target {risk:.2%}: balance for 0.01 lot to fit now = {stop_now / risk:,.0f} USC")
    d = G.signals(X, "D1", None); s = np.flatnonzero((d > 0) & (X["t"] >= G.START) & (X["htf"] == d))
    for k, (I, risk) in SYSTEMS.items():
        trades = [dict(tr, X=X) for tr in RP.sim_paths(X, M, s, d[s], I)]
        T = RP.timeline(trades, {M: X}); RP.prep_marks(trades, T)
        stops = np.array([r["risk"] for r in trades])
        print(f"\n== system {k} ({I}), {len(trades)} trades; stop 2N over the five years: ${stops.min():.0f}..${stops.max():.0f}, median ${np.median(stops):.0f}")
        for dep in DEPOSITS:
            RP.DEPOSIT = dep
            rows = lot_account(trades, risk, dep)
            Mx = RP.metrics(rows, T, risk)
            rf = np.array([r["risk_frac"] for r in rows]); lots = np.array([r["lots"] for r in rows])
            over = (rf > risk * 1.5).mean()
            ideal = RP.metrics(RP.account(trades, risk), T, risk, full=False)
            print(f"  {dep:>8,.0f} USC: final {Mx['final']:>9,.0f} USC ({Mx['net'] / dep:+.0%}, {Mx['cagr']:+.1%}/y) equity DD {Mx['equity_dd']['relative_pct']:.1%}"
                  f" ({Mx['equity_dd']['maximal']:,.0f} USC) balance DD {Mx['balance_dd']['relative_pct']:.1%} | risk per unit {np.median(rf):.2%} median,"
                  f" {rf.max():.2%} max, {over:.0%} of trades above 1.5x target | lots {lots.min():.2f}..{lots.max():.2f}"
                  f" | fractional sizing: {ideal['net'] / dep:+.0%}, DD {ideal['equity_dd']['relative_pct']:.1%}")
            last = rows[-1]
            yr = " ".join(f"{y['year']} {y['ret']:+.0%}" for y in Mx["yearly"])
            print(f"            worst trade {min(r['pnl'] for r in rows):,.0f} USC, longest losing run {Mx['streaks']['max_losses']} ({Mx['streaks']['max_losses_usd']:,.0f} USC); years {yr};"
                  f" now {Mx['dd_window']['now']:.0%} below the peak")
    RP.DEPOSIT = 100_000.0


if __name__ == "__main__":
    main()
