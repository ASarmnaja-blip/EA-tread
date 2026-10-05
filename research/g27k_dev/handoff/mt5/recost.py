"""Re-cost every book with the spreads actually quoted on the operator's Cent account, and see what survives.

The research priced spread as cost_rt_bp = max(2 bp, broker spread + 1 bp) per market, and stored it per trade as
R_spread = cost_rt_bp / 1e4 / stop_pct (verified exactly against the trade files). So a different spread rescales that column
and nothing else: entries, exits, R_gross and R_swap are untouched.

Measured on 184136077 (Exness Cent) from 60 days of ticks, 2026-10-05. Scenarios:
  model     what the research published
  real      the measured spread alone
  real+1bp  the measured spread plus the same 1 bp allowance the model adds (the like-for-like comparison)

Usage: python recost.py [--levels 0.0075,0.01] [--start 100000]
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
HANDOFF = HERE.parent
MODEL_BP = {"XAUUSD": 2.0, "XAGUSD": 3.641, "BTCUSD": 2.0, "ETHUSD": 2.0, "USDJPY": 2.0, "JP225": 2.0}
CENT_BP = {"XAUUSD": 0.58, "XAGUSD": 4.60, "BTCUSD": 1.28, "ETHUSD": 4.03, "USDJPY": 0.64}   # JP225 is not on the Cent account
CENT = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY"]
BRAKE_ON, BRAKE_OFF, BRAKE_MULT = 0.25, 0.125, 0.5


def load():
    out = {}
    for b in ("F", "M30", "H1"):
        T = pd.read_csv(HANDOFF / f"trades_{b}.csv.gz")
        for c in ("entry_time_utc", "exit_time_utc"):
            T[c] = pd.to_datetime(T[c])
        T["book"] = b
        out[b] = T
    return out


def recost(T, scenario):
    """R with the spread column rescaled; R_gross and R_swap are unchanged."""
    T = T.copy()
    if scenario == "model":
        f = T.market.map(lambda m: 1.0)
    else:
        add = 1.0 if scenario.endswith("+1bp") else 0.0
        f = T.market.map(lambda m: (CENT_BP[m] + add) / MODEL_BP[m] if m in CENT_BP else 1.0)
    T["R_spread_new"] = T.R_spread * f
    T["R_new"] = T.R_gross - T.R_spread_new - T.R_swap
    return T


def account(trades, risk_of, start=100_000.0, brake=True):
    """Balance compounding with overlapping trades, risk taken as a share of balance at entry, optional NAV brake."""
    rows = sorted(trades, key=lambda r: r[0])
    bal = peak = start
    heap = []; pts = []; mult = 1.0; braked = 0
    for t, tx, R, book in rows:
        while heap and heap[0][0] <= t:
            _, p = heapq.heappop(heap)
            bal += p; peak = max(peak, bal); pts.append((_, bal))
        if brake:
            dd = 1 - bal / peak
            if mult == 1.0 and dd >= BRAKE_ON:
                mult = BRAKE_MULT
            elif mult < 1.0 and dd <= BRAKE_OFF:
                mult = 1.0
        braked += mult < 1.0
        heapq.heappush(heap, (tx, risk_of(book) * mult * bal * R))
    while heap:
        tx, p = heapq.heappop(heap)
        bal += p; peak = max(peak, bal); pts.append((tx, bal))
    if not pts:
        return None
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([t for t, _ in pts])).sort_index()
    dd = float((1 - eq / eq.cummax()).max())
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (bal / start) ** (1 / yrs) - 1 if bal > 0 and yrs > 0 else -1.0
    return dict(final=bal, cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.nan, n=len(rows),
                braked=braked / max(len(rows), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=100_000.0)
    a = ap.parse_args()
    B = load()
    scenarios = ["model", "real", "real+1bp"]

    print("== mean R per trade, Cent markets only (entries, exits and R_gross unchanged; only the spread cost differs)")
    for b, T in B.items():
        T = T[T.market.isin(CENT)]
        print(f"\n  book {b}  ({len(T)} trades)")
        head = f"    {'market':8s} {'n':>5s} {'gross':>8s} {'swap':>7s} " + " ".join(f"{s:>9s}" for s in scenarios) + "   verdict at real+1bp"
        print(head)
        for m in CENT:
            x = T[T.market == m]
            if not len(x):
                continue
            vals = {s: recost(x, s).R_new.mean() for s in scenarios}
            v = vals["real+1bp"]
            print(f"    {m:8s} {len(x):>5d} {x.R_gross.mean():>+8.3f} {-x.R_swap.mean():>+7.3f} "
                  + " ".join(f"{vals[s]:>+9.3f}" for s in scenarios)
                  + ("   still positive" if v > 0 else "   NEGATIVE"))
        allv = {s: recost(T, s).R_new.mean() for s in scenarios}
        print(f"    {'all':8s} {len(T):>5d} {T.R_gross.mean():>+8.3f} {-T.R_swap.mean():>+7.3f} "
              + " ".join(f"{allv[s]:>+9.3f}" for s in scenarios))

    print("\n\n== account results, Cent markets, start $100,000, G27K-F 1% + brake 25%, sleeves 0.5%")
    print(f"  {'combo':12s} {'markets':26s} {'scenario':9s} {'CAGR':>7s} {'DD':>7s} {'MAR':>6s} {'final':>14s}")
    drops = [("all five", CENT), ("no ETH", [m for m in CENT if m != "ETHUSD"]),
             ("no ETH, no XAG", [m for m in CENT if m not in ("ETHUSD", "XAGUSD")]),
             ("no USDJPY", [m for m in CENT if m != "USDJPY"]),
             ("gold+BTC only", ["XAUUSD", "BTCUSD"])]
    combos = {"F": ["F"], "F+M30": ["F", "M30"], "F+M30+H1": ["F", "M30", "H1"], "M30": ["M30"]}
    risk = lambda book: 0.01 if book == "F" else 0.005
    for cname, books in combos.items():
        for dname, mkts in drops:
            if cname == "M30" and dname not in ("all five", "no ETH", "no ETH, no XAG"):
                continue
            for s in scenarios:
                tr = []
                for b in books:
                    T = recost(B[b][B[b].market.isin(mkts)], s)
                    tr += list(zip(T.entry_time_utc, T.exit_time_utc, T.R_new, T.book))
                r = account(tr, risk, a.start)
                if r is None:
                    continue
                print(f"  {cname:12s} {dname:26s} {s:9s} {r['cagr']:>6.1%} {r['dd']:>6.1%} {r['mar']:>6.2f} {r['final']:>14,.0f}")
            print()


if __name__ == "__main__":
    main()
