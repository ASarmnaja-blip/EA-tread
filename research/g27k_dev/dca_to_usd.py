"""How long a 10,000 USC cent account needs, with a monthly top-up, before it can move to a Standard USD account.

The move needs 573,700 USC (= 5,737 USD, the balance at which silver's minimum lot fits the 1 % rule on Standard) and really
1,147,500 USC (= 11,475 USD, where the 0.5 % brake also fits). This replays the real three-market trade sequence a cent account can
trade, sizes every position in real cent lots (round to nearest, floored at the broker minimum), adds the top-up on the first of each
month, and runs the 25 % brake on net asset value per unit so deposits cannot hide a drawdown.

Every historical start month is simulated, so the answer is a distribution rather than one lucky path.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
CENT = {"XAUUSD": 1.0, "XAGUSD": 50.0, "BTCUSD": 0.01}      # cent contract sizes, confirmed on the account 2026-10-03
VMIN = VSTEP = 0.01
BRAKE_ON, BRAKE_OFF, BRAKE_MULT = 0.25, 0.125, 0.5
TARGETS = {"5,737 USD (1 % rule fits)": 573_700.0, "11,475 USD (brake also fits)": 1_147_500.0}


def load():
    raw = json.loads((HERE / "handoff_expected_trades_h4_00utc.json").read_text(encoding="utf-8"))["trades"]
    T = pd.DataFrame(raw)
    T = T[T.market.isin(CENT)].copy()
    T["t"] = pd.to_datetime(T.entry_time_utc).astype("datetime64[s]").astype("int64")
    T["tx"] = pd.to_datetime(T.exit_time_utc).astype("datetime64[s]").astype("int64")
    # USC risked per 1.00 lot at the stop = stop distance in price x cent contract size x 100 cents per unit
    T["risk_per_lot"] = (T.entry_price - T.stop_price).abs() * T.market.map(CENT) * 100.0
    return T.sort_values("t").reset_index(drop=True)


def run(T, start_bal, monthly, t0, targets, cap_years=40):
    """Returns months taken to reach each target, or None if not reached inside the data."""
    sub = T[T.t >= t0]
    if sub.empty:
        return None
    bal = start_bal; nav = 1.0; pk_nav = 1.0; mult = 1.0
    heap = []; hit = {k: None for k in targets}
    months = pd.date_range(pd.Timestamp(t0, unit="s").normalize().replace(day=1), periods=cap_years * 12, freq="MS")
    mt = [int(x.timestamp()) for x in months][1:]            # first top-up one month in
    mi = 0; deposited = start_bal
    for r in sub.itertuples():
        while heap and heap[0][0] <= r.t:
            _, p = heapq.heappop(heap)
            before = bal
            bal += p
            if before > 0:                                   # NAV per unit moves only with P&L
                nav *= bal / before; pk_nav = max(pk_nav, nav)
        while mi < len(mt) and mt[mi] <= r.t:
            if monthly:                                      # a deposit adds units, it does not change NAV per unit
                bal += monthly; deposited += monthly
            mi += 1
        for k, v in targets.items():
            if hit[k] is None and bal >= v:
                hit[k] = (r.t - t0) / (365.25 * 86400 / 12)
        if bal <= 0:
            break
        dd = 1 - nav / pk_nav
        if mult == 1.0 and dd >= BRAKE_ON:
            mult = BRAKE_MULT
        elif mult < 1.0 and dd <= BRAKE_OFF:
            mult = 1.0
        want = 0.01 * mult * bal / r.risk_per_lot
        lot = max(round(math.floor(want / VSTEP + 0.5) * VSTEP, 2), VMIN)
        heapq.heappush(heap, (r.tx, lot * r.risk_per_lot * r.R_net))
    while heap:
        _, p = heapq.heappop(heap); bal += p
    for k, v in targets.items():
        if hit[k] is None and bal >= v:
            hit[k] = (sub.tx.max() - t0) / (365.25 * 86400 / 12)
    return hit, bal, deposited


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=10_000.0, help="starting balance in USC")
    ap.add_argument("--monthly", default="0,2000,5000,10000,20000,50000", help="monthly top-ups in USC")
    a = ap.parse_args()
    T = load()
    starts = pd.date_range("2011-09-01", "2021-09-01", freq="MS")      # leave at least 5 years of data after each start
    print(f"start {a.start:,.0f} USC (= ${a.start/100:,.0f}) | three markets | round-to-nearest, floored at 0.01 lot | brake on NAV per unit")
    print(f"{len(starts)} historical start months from {starts[0]:%Y-%m} to {starts[-1]:%Y-%m}\n")
    for monthly in [float(x) for x in a.monthly.split(",")]:
        print(f"-- top-up {monthly:>8,.0f} USC/month (= ${monthly/100:>6,.0f})")
        for label, target in TARGETS.items():
            got = []
            for s in starts:
                r = run(T, a.start, monthly, int(s.timestamp()), {label: target})
                if r and r[0][label] is not None:
                    got.append(r[0][label])
            n = len(starts)
            if not got:
                need = (target - a.start) / monthly if monthly else float("inf")
                print(f"   {label:28s} reached in 0 of {n} starts" + (f" (deposits alone would take {need/12:.1f} years)" if monthly else ""))
                continue
            q = np.percentile(got, [10, 25, 50, 75, 90])
            print(f"   {label:28s} reached in {len(got):>3d} of {n} starts | months: best {min(got):>5.0f}"
                  f" p25 {q[1]:>5.0f} median {q[2]:>5.0f} p75 {q[3]:>5.0f} worst {max(got):>5.0f}"
                  f" | median {q[2]/12:>4.1f} years")
        print()


if __name__ == "__main__":
    main()
