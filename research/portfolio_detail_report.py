#!/usr/bin/env python3
"""The specific portfolio-engine items requested: floating vs closed DD on
synthetic data, max concurrent exposure, lot-granularity isolated from
compounding, before/after lot rounding, three account sizes, the broker
constants in force, and a direct check that long/short swap signs land
correctly in P&L.

This does not search or fit anything - it runs one fixed, hand-designed
scenario through portfolio.py and prints what happened, so every number here
can be checked against the scenario description above it.

Run:  python3 research/portfolio_detail_report.py
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from portfolio import Broker, simulate, round_lot, summarise, log_frame

def idx(n):
    return pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")

print("PORTFOLIO ENGINE - DETAIL REPORT")
print("=" * 78)

BROKER = Broker()   # the defaults in force everywhere below
print("\n1. BROKER CONSTANTS IN FORCE (declared assumption, not measurement)")
print(f"   contract_size            {BROKER.contract_size} oz/lot (XAUUSD)")
print(f"   min_lot / lot_step        {BROKER.min_lot} / {BROKER.lot_step}")
print(f"   leverage                 1:{BROKER.leverage:.0f}")
print(f"   commission_per_lot_side   {BROKER.commission_per_lot_side} USD "
      f"({BROKER.commission_per_lot_side*2} round trip)")
print(f"   swap_long_per_lot_night   {BROKER.swap_long_per_lot_night:+.2f} USD "
      f"(negative = long pays)")
print(f"   swap_short_per_lot_night  {BROKER.swap_short_per_lot_night:+.2f} USD "
      f"(positive = short receives)")

# --------------------------------------------------------------------------
print("\n2. FLOATING DD vs CLOSED DD ON A SYNTHETIC SCENARIO")
print("   Scenario: 3 overlapping longs opened on bars 1,2,3, ALL at 1% risk,")
print("   all closing on bar 8 at their stop. Between bars 3-7 all three sit")
print("   open and losing (marked to a price already 10 points against them),")
print("   so floating equity dips well before anything closes.")
rng = np.random.default_rng(0)
n = 12
mid = np.concatenate([np.full(4, 2000.0), np.full(8, 1990.0)])
tr = [dict(entry_bar=b, exit_bar=8, d=1, entry_px=2000.0, exit_px=1990.0,
           stop_px=1990.0) for b in (1, 2, 3)]
r = simulate(tr, mid, idx(n), broker=BROKER, risk_frac=0.01,
             start_equity=10_000.0, spread=np.full(n, 0.50))
print(f"   max_concurrent           {r['max_concurrent']} positions")
print(f"   max_open_risk_frac       {r['max_open_risk_frac']*100:.2f}% of equity")
print(f"   dd_closed (balance curve, sampled at closes)   {r['dd_closed']*100:.2f}%")
print(f"   dd_floating (equity curve, bar by bar)         {r['dd_floating']*100:.2f}%")
print(f"   -> floating >= closed: {r['dd_floating'] >= r['dd_closed'] - 1e-12} "
      f"(floating sees the intermediate mark-to-market loss the closed curve")
print(f"      only samples once the trades actually settle)")

# a case where floating DD is STRICTLY worse: one position recovers before
# closing but was deep underwater mid-trade
print("\n   Second case: ONE long, opens at 2000, dips to 1950 mid-trade")
print("   (50-point drawdown while open), recovers, and exits at breakeven.")
n2 = 20
mid2 = np.concatenate([np.full(2, 2000.0), np.full(6, 1950.0),
                       np.full(12, 2000.0)])
tr2 = [dict(entry_bar=1, exit_bar=18, d=1, entry_px=2000.0, exit_px=2000.0,
           stop_px=1900.0)]
r2 = simulate(tr2, mid2, idx(n2), broker=BROKER, risk_frac=0.01,
              start_equity=15_000.0, spread=np.full(n2, 0.50))
print(f"   dd_closed   {r2['dd_closed']*100:.2f}%  (the trade closes near "
      f"breakeven, so the balance curve barely moves)")
print(f"   dd_floating {r2['dd_floating']*100:.2f}%  (the equity curve saw the "
      f"real 50-point paper loss while the position was open)")
print(f"   -> dd_floating STRICTLY exceeds dd_closed here: "
      f"{r2['dd_floating'] > r2['dd_closed'] + 1e-9}")

# --------------------------------------------------------------------------
print("\n3. LOT GRANULARITY ISOLATED FROM COMPOUNDING")
print("   40 sequential trades, each losing exactly its planned 1R stop.")
print("   Two accounts, identical trades, identical everything except size:")
seq_mid = np.full(400, 2000.0)
seq = [dict(entry_bar=1 + 8 * k, exit_bar=5 + 8 * k, d=1, entry_px=2000.0,
            exit_px=1980.0, stop_px=1980.0) for k in range(40)]
FREE = Broker(commission_per_lot_side=0.0, slippage_points=0.0,
              swap_long_per_lot_night=0.0, swap_short_per_lot_night=0.0)

r_big = simulate(seq, seq_mid, idx(400), broker=FREE, risk_frac=0.01,
                 start_equity=1_000_000.0)
r_small = simulate(seq, seq_mid, idx(400), broker=FREE, risk_frac=0.01,
                   start_equity=10_000.0)
exp_frac = 1.0 - 0.99 ** 40
big_frac = -r_big["net_pl"] / 1_000_000.0
small_frac = -r_small["net_pl"] / 10_000.0
print(f"   compounding-only prediction (1 - 0.99^40)     {exp_frac*100:.2f}%")
print(f"   $1,000,000 account (lot step negligible)      {big_frac*100:.2f}%  "
      f"-> isolates COMPOUNDING")
print(f"   $10,000 account (0.01 lot step bites)          {small_frac*100:.2f}%  "
      f"-> compounding AND granularity together")
print(f"   granularity's own contribution                 "
      f"{(big_frac - small_frac)*100:+.2f} percentage points")
print(f"   sum-of-R naive answer                          40.00% "
      f"(every effect above is invisible to it)")

print("\n   BEFORE vs AFTER lot rounding, on one position:")
print("   equity 10,000, risk 1% = $100, stop 15.3 points away (deliberately")
print("   not a clean multiple of the 0.01 lot step):")
want = (10_000 * 0.01) / (15.3 * 100.0)
got = round_lot(want, 0.01, 0.01, 100.0)
actual_risk = got * 15.3 * 100.0
print(f"   wanted lots (before rounding)   {want:.6f}")
print(f"   dealt lots (after rounding down){got:.2f}")
print(f"   risk actually taken             ${actual_risk:.2f} "
      f"(budget was $100.00, so {100.0-actual_risk:+.2f} of the 1% budget "
      f"went unused)")

# --------------------------------------------------------------------------
print("\n4. THREE ACCOUNT SIZES, SAME SCENARIO, SAME EVERYTHING ELSE")
print("   40 sequential 1R-stop losses (same trades as section 3), 1% risk:")
for eq in (20.0, 100.0, 10_000.0):
    rr = simulate(seq, seq_mid, idx(400), broker=Broker(), risk_frac=0.01,
                  start_equity=eq)
    frac = -rr["net_pl"] / eq if eq else float("nan")
    print(f"   ${eq:>10,.0f} start -> ${rr['final_equity']:>12,.2f} final  "
          f"(lost {frac*100:6.2f}%)  trades taken {rr['n_taken']}/{rr['n_offered']}  "
          f"rejected(min_lot)={rr['rejected']['min_lot']}")
print("   at $20 and $100 the position size for 1% risk against a 20-point")
print("   stop is far below the 0.01 minimum lot on most or all trades, so")
print("   almost everything is REJECTED rather than silently taken at zero")
print("   size - which is the correct behaviour for an account this small.")

# --------------------------------------------------------------------------
print("\n5. SWAP SIGN CONFIRMATION IN P&L (long pays, short receives)")
SWAP = Broker(swap_long_per_lot_night=-6.0, swap_short_per_lot_night=1.5,
              commission_per_lot_side=0.0, slippage_points=0.0)
n3 = 100
mid3 = np.full(n3, 2000.0)              # flat price: P&L is swap ONLY
ix3 = idx(n3)
long_tr = [dict(entry_bar=1, exit_bar=n3 - 2, d=1, entry_px=2000.0,
                exit_px=2000.0, stop_px=1990.0)]
short_tr = [dict(entry_bar=1, exit_bar=n3 - 2, d=-1, entry_px=2000.0,
                 exit_px=2000.0, stop_px=2010.0)]
rl = simulate(long_tr, mid3, ix3, broker=SWAP, risk_frac=0.01,
              start_equity=10_000.0)
rs = simulate(short_tr, mid3, ix3, broker=SWAP, risk_frac=0.01,
              start_equity=10_000.0)
print(f"   flat price (no directional P&L) - net_pl is swap alone:")
print(f"   LONG:  net_pl {rl['net_pl']:+.4f}  swap paid {rl['costs']['swap']:+.4f}"
      f"  -> {'PAYS (negative), correct' if rl['net_pl'] < 0 else '*** WRONG SIGN'}")
print(f"   SHORT: net_pl {rs['net_pl']:+.4f}  swap paid {rs['costs']['swap']:+.4f}"
      f"  -> {'RECEIVES (positive), correct' if rs['net_pl'] > 0 else '*** WRONG SIGN'}")
print(f"   net_pl equals costs['swap'] exactly on a flat price: "
      f"long {abs(rl['net_pl']-rl['costs']['swap']) < 1e-9}, "
      f"short {abs(rs['net_pl']-rs['costs']['swap']) < 1e-9}")

print("\n" + "=" * 78)
print("all figures above are computed directly from portfolio.py; no fitting")
print("or search took place in producing this report")
