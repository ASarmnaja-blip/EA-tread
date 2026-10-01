"""Operator 2026-10-01: can a 10,000 USC cent account trade the report768 system, on gold alone and on gold + silver + BTC?
Cent contracts: XAUUSDc measured on the real account (data/spec_real_XAUUSDc.json, 2026-09-21: 1 oz per lot, 0.01 minimum, so 0.01 lot
moves 1 USC per $1 of gold). XAGUSDc and BTCUSDc are assumed at 1/100 of the standard contracts (5,000 oz and 1 BTC): 0.01 lot = 0.5 oz
(50 USC per $1 of silver) and 0.0001 BTC (0.01 USC per $1 of BTC); not verified, the connected terminal is a standard demo.
Each trade is sized in whole 0.01 lots from the realised balance, never below 0.01; positions in different markets overlap as in the
report; equity marked at every H4 close. Systems A (adds, 0.25 % per unit) and B (one unit, 1 % per trade)."""
from __future__ import annotations

import heapq
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

USC = {"XAUUSD": 1.0, "XAGUSD": 50.0, "BTCUSD": 0.01}          # USC per $1 move per 0.01 lot
SETS = {"gold": ["XAUUSD"], "gold+silver": ["XAUUSD", "XAGUSD"], "gold+silver+BTC": ["XAUUSD", "XAGUSD", "BTCUSD"]}
DEPOSITS = (10_000.0, 20_000.0, 40_000.0)
SYSTEMS = {"A": ("I4", 0.0025), "B": ("I1", 0.01)}


def lot_account(trades, risk, deposit):
    """Like report768.account, but each trade gets whole 0.01 lots: max(1, floor(risk x balance / USC lost per 0.01 lot at the stop))."""
    order = sorted(range(len(trades)), key=lambda i: (trades[i]["t"], trades[i]["mkt"]))
    bal = deposit; heap = []; live = {}; rows = []
    for i in order:
        tr = trades[i]
        while heap and heap[0][0] <= tr["t"]:
            _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; r["bal_after"] = bal; rows.append(r)
        per_lot = tr["risk"] * USC[tr["mkt"]]
        n = max(1, int(np.floor(risk * bal / per_lot)))
        live[i] = dict(tr, lots=n / 100, unit_usd=n * per_lot, pnl=n * per_lot * tr["R"], bal_before=bal, risk_frac=n * per_lot / bal)
        heapq.heappush(heap, (tr["t_exit"], i))
    while heap:
        _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; r["bal_after"] = bal; rows.append(r)
    rows.sort(key=lambda r: (r["t_exit"], r["t"]))
    return rows


def main():
    Xs = {m: G.features(G.frames(G.load_h1(m)), m, "H4") for m in USC}
    print("now, per 0.01 lot at the 2 x ATR20 (H4) stop:")
    for m, X in Xs.items():
        stop = 2 * X["a20"][-1]
        print(f"  {m}: price {X['c'][-1]:,.2f}, stop ${stop:,.2f} -> {stop * USC[m]:,.0f} USC = {stop * USC[m] / 10_000:.2%} of 10,000 USC")
    for k, (I, risk) in SYSTEMS.items():
        allt = []
        for m, X in Xs.items():
            d = G.signals(X, "D1", None); s = np.flatnonzero((d > 0) & (X["t"] >= G.START) & (X["htf"] == d))
            allt += [dict(tr, X=X) for tr in RP.sim_paths(X, m, s, d[s], I)]
        T = RP.timeline(allt, Xs); RP.prep_marks(allt, T)
        print(f"\n== system {k} ({'adds, 0.25 % per unit' if k == 'A' else 'one unit, 1 % per trade'})")
        for nm, mk in SETS.items():
            tr = [r for r in allt if r["mkt"] in mk]
            for dep in DEPOSITS:
                RP.DEPOSIT = dep
                rows = lot_account(tr, risk, dep); Mx = RP.metrics(rows, T, risk)
                ideal = RP.metrics(RP.account(tr, risk), T, risk, full=False)
                rf = np.array([r["risk_frac"] for r in rows])
                yr = " ".join(f"{y['year']}:{y['ret']:+.0%}" for y in Mx["yearly"] if y["year"] > 2021)
                print(f"  {nm:16s} {dep:>7,.0f} USC -> {Mx['final']:>9,.0f} USC ({Mx['net'] / dep:+.0%}, {Mx['cagr']:+.1%}/y)  equity DD {Mx['equity_dd']['relative_pct']:5.1%}"
                      f" ({Mx['equity_dd']['maximal']:,.0f} USC)  risk/unit median {np.median(rf):.2%} max {rf.max():.2%}  worst run {Mx['streaks']['max_losses']}"
                      f" ({Mx['streaks']['max_losses_usd']:,.0f} USC)  | fractional {ideal['net'] / dep:+.0%} DD {ideal['equity_dd']['relative_pct']:.1%} | {yr}")
    RP.DEPOSIT = 100_000.0


if __name__ == "__main__":
    main()
