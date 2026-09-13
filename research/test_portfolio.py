#!/usr/bin/env python3
"""Tests for the overlapping-trade portfolio engine.

Every expected number below is computed by hand in the comment above it, from
the broker parameters, before the code runs. The engine is only worth having
if its arithmetic can be checked on paper.

Run:  python3 research/test_portfolio.py
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from portfolio import (Broker, simulate, stressed, round_lot, summarise,
                       log_frame, STRESS)

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

def idx(n):
    return pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")

# a broker with every cost switched off, so sizing arithmetic is visible
FREE = Broker(contract_size=100.0, min_lot=0.01, lot_step=0.01, leverage=100.0,
              commission_per_lot_side=0.0, slippage_points=0.0,
              swap_long_per_lot_night=0.0, swap_short_per_lot_night=0.0)

# --------------------------------------------------------------------------
print("\nGROUP 1  position sizing and lot rounding")

ck("lots always round DOWN, never to nearest",
   round_lot(0.1799, 0.01, 0.01, 100) == 0.17,
   f"0.1799 -> {round_lot(0.1799, 0.01, 0.01, 100)} (0.18 would exceed the "
   f"risk budget)")
ck("a size below the minimum lot is zero, not the minimum",
   round_lot(0.004, 0.01, 0.01, 100) == 0.0,
   f"0.004 -> {round_lot(0.004, 0.01, 0.01, 100)}")

# equity 10,000, risk 1% = $100. Stop is 10 points away, contract 100 oz,
# so one lot risks 10 * 100 = $1,000. Wanted lots = 100/1000 = 0.10 exactly.
mid = np.full(10, 2000.0)
tr = [dict(entry_bar=1, exit_bar=5, d=1, entry_px=2000.0, exit_px=2000.0,
           stop_px=1990.0)]
r = simulate(tr, mid, idx(10), broker=FREE, risk_frac=0.01,
             start_equity=10_000.0)
lg = r["log"][0]
ck("1% of 10,000 against a 10-point stop sizes exactly 0.10 lots",
   abs(lg["lots"] - 0.10) < 1e-12,
   f"lots={lg['lots']} (want 100 / (10 * 100) = 0.10)")
ck("the money at risk is exactly the risk budget",
   abs(lg["risk_money"] - 100.0) < 1e-9,
   f"risk_money={lg['risk_money']:.4f} (want 1% of 10,000 = 100.00)")

# --------------------------------------------------------------------------
print("\nGROUP 2  P&L arithmetic, cost by cost")

# 0.10 lots, price moves 2000 -> 2020, long. 20 points * 0.10 * 100 = $200.
mid = np.concatenate([np.full(3, 2000.0), np.full(7, 2020.0)])
tr = [dict(entry_bar=1, exit_bar=5, d=1, entry_px=2000.0, exit_px=2020.0,
           stop_px=1990.0)]
r = simulate(tr, mid, idx(10), broker=FREE, risk_frac=0.01, start_equity=10_000.0)
ck("a 20-point win on 0.10 lots is exactly $200",
   abs(r["net_pl"] - 200.0) < 1e-9,
   f"net P&L {r['net_pl']:.6f}, final equity {r['final_equity']:.2f}")

# Same trade with a 0.60 spread. THE FIRST DRAFT OF THIS TEST WAS WRONG and
# the engine was right: the long buys at 2000.30, so the distance left to the
# 1990 stop is 10.30 points, not 10.00. Sizing 1% of 10,000 against 10.30
# points gives 100/(10.30*100) = 0.0971 lots, which rounds DOWN to 0.09.
#   gross = (2019.70 - 2000.30) * 0.09 * 100 = 19.40 * 9 = 174.60
#   spread paid = 0.30 * 0.09 * 100 * 2 sides = 5.40
sp = np.full(10, 0.60)
r = simulate(tr, mid, idx(10), broker=FREE, risk_frac=0.01,
             start_equity=10_000.0, spread=sp)
lg = r["log"][0]
ck("risk is measured from the FILL, so the spread shrinks the position",
   abs(lg["lots"] - 0.09) < 1e-12 and abs(lg["entry_fill"] - 2000.30) < 1e-9,
   f"entry fill {lg['entry_fill']:.4f}, lots {lg['lots']} "
   f"(1% / (10.30 pts * 100) = 0.0971 -> 0.09)")
ck("a 0.60 spread on 0.09 lots costs 0.30 * 0.09 * 100 each way = $5.40",
   abs(r["net_pl"] - 174.6) < 1e-9 and abs(r["costs"]["spread"] - 5.40) < 1e-9,
   f"net {r['net_pl']:.4f} (want 174.60), spread paid "
   f"{r['costs']['spread']:.4f} (want 5.40)")

# commission 3.5/lot/side on 0.10 lots = 0.35 each way = 0.70 round trip
COMM = Broker(**{**FREE.__dict__, "commission_per_lot_side": 3.5})
r = simulate(tr, mid, idx(10), broker=COMM, risk_frac=0.01,
             start_equity=10_000.0)
ck("commission is charged on BOTH sides",
   abs(r["costs"]["commission"] - 0.70) < 1e-9,
   f"commission {r['costs']['commission']:.4f} (want 3.5 * 0.10 * 2 = 0.70)")

# Slippage 0.20 points, against the trade on entry AND exit. Same feedback:
# buy at 2000.20, risk 10.20 pts, lots = 100/1020 = 0.098 -> 0.09.
# gross = (2019.80 - 2000.20) * 0.09 * 100 = 19.60 * 9 = 176.40
SLIP = Broker(**{**FREE.__dict__, "slippage_points": 0.20})
r = simulate(tr, mid, idx(10), broker=SLIP, risk_frac=0.01, start_equity=10_000.0)
ck("slippage works against the trade on entry and on exit",
   abs(r["net_pl"] - 176.4) < 1e-9,
   f"net {r['net_pl']:.4f} (want 19.60 pts on 0.09 lots = 176.40)")

# --------------------------------------------------------------------------
print("\nGROUP 3  a short is the mirror, and pays the spread the same way")
mid_s = np.concatenate([np.full(3, 2000.0), np.full(7, 1980.0)])
tr_s = [dict(entry_bar=1, exit_bar=5, d=-1, entry_px=2000.0, exit_px=1980.0,
             stop_px=2010.0)]
r = simulate(tr_s, mid_s, idx(10), broker=FREE, risk_frac=0.01,
             start_equity=10_000.0, spread=sp)
# short SELLS at the bid 1999.70 and buys back at the ask 1980.30.
# risk = 2010 - 1999.70 = 10.30 pts -> 0.09 lots, same as the long mirror.
# gross = (1999.70 - 1980.30) * 0.09 * 100 = 19.40 * 9 = 174.60
lgs = r["log"][0]
ck("a short sells at the bid and buys back at the ask",
   abs(lgs["entry_fill"] - 1999.70) < 1e-9 and abs(lgs["exit_fill"] - 1980.30) < 1e-9,
   f"entry {lgs['entry_fill']:.4f} (bid), exit {lgs['exit_fill']:.4f} (ask)")
ck("the short mirrors the long exactly, cost for cost",
   abs(r["net_pl"] - 174.6) < 1e-9,
   f"net {r['net_pl']:.4f} (want 174.60, identical to the long mirror)")

# --------------------------------------------------------------------------
print("\nGROUP 4  swap is charged per night held, by side")
SWAP = Broker(**{**FREE.__dict__, "swap_long_per_lot_night": -6.0,
                 "swap_short_per_lot_night": 1.5})
n = 100
mid_l = np.full(n, 2000.0)
ix = idx(n)                                  # hourly, so ~4 day boundaries
tr_l = [dict(entry_bar=1, exit_bar=n - 2, d=1, entry_px=2000.0,
             exit_px=2000.0, stop_px=1990.0)]
r = simulate(tr_l, mid_l, ix, broker=SWAP, risk_frac=0.01, start_equity=10_000.0)
nights = int((ix.normalize().to_numpy()[1:] != ix.normalize().to_numpy()[:-1]).sum())
# the position is open for all of them; 0.10 lots at -6/lot/night
# swap is a SIGNED CASH FLOW: negative means the position paid.
exp = -6.0 * 0.10 * nights
ck("a long pays swap on every night it is held, reported as negative",
   abs(r["costs"]["swap"] - exp) < 1e-9,
   f"swap {r['costs']['swap']:+.4f} over {nights} nights (want {exp:+.4f}) - "
   f"the first version negated this and reported a cost as income")
r2 = simulate([{**tr_l[0], "d": -1, "stop_px": 2010.0}], mid_l, ix, broker=SWAP,
              risk_frac=0.01, start_equity=10_000.0)
ck("a short RECEIVES swap at a positive rate",
   r2["costs"]["swap"] > 0,
   f"swap {r2['costs']['swap']:+.4f} (positive rate 1.5/lot/night)")

# --------------------------------------------------------------------------
print("\nGROUP 5  overlapping positions are not a sum of R")

# Three identical longs open on bars 1, 2, 3 and all close on bar 8, each
# risking 1% - so at bar 3 the account has 3% at risk, not 1%.
mid_o = np.concatenate([np.full(4, 2000.0), np.full(6, 1990.0)])
tr_o = [dict(entry_bar=b, exit_bar=8, d=1, entry_px=2000.0, exit_px=1990.0,
             stop_px=1990.0) for b in (1, 2, 3)]
r = simulate(tr_o, mid_o, idx(10), broker=FREE, risk_frac=0.01,
             start_equity=10_000.0)
ck("three overlapping positions are counted as three, not one",
   r["max_concurrent"] == 3, f"max_concurrent={r['max_concurrent']}")
ck("open risk at the peak is about 3% of equity, not 1%",
   0.028 <= r["max_open_risk_frac"] <= 0.031,
   f"peak open risk {r['max_open_risk_frac']*100:.2f}% of equity - summing R "
   f"would have reported one 1% unit three times")

# every one of them loses a full stop, so the account loses ~3%, and it loses
# it on FLOATING equity before any of them closes
ck("floating drawdown is at least as deep as the closed-trade drawdown",
   r["dd_floating"] >= r["dd_closed"] - 1e-12,
   f"floating {r['dd_floating']*100:.2f}% vs closed {r['dd_closed']*100:.2f}%")
ck("the three stops cost about 3% of the account",
   0.027 <= r["dd_floating"] <= 0.032,
   f"floating DD {r['dd_floating']*100:.2f}%")

# --------------------------------------------------------------------------
print("\nGROUP 5b  compounding, which summing R also gets wrong")
# 40 SEQUENTIAL full-stop losses at 1% risk each. Summing R says -40.00R,
# i.e. -40% of the starting account. The account actually loses
# 1 - 0.99^40 = 33.10%, because every position after the first is sized off
# an account that has already shrunk. The gap is 6.9 percentage points on a
# losing run, and it works the other way on a winning one.
# The account is 1,000,000 so that lot granularity is negligible here and the
# only thing left is the compounding. (The granularity effect is real and is
# measured separately below - at 10,000 it dominates this same test, which is
# how the first draft of it failed.)
seq_mid = np.full(400, 2000.0)
seq = [dict(entry_bar=1 + 8 * k, exit_bar=5 + 8 * k, d=1, entry_px=2000.0,
            exit_px=1980.0, stop_px=1980.0) for k in range(40)]
rs = simulate(seq, seq_mid, idx(400), broker=FREE, risk_frac=0.01,
              start_equity=1_000_000.0)
# exit_px equals stop_px, so each trade loses exactly its planned risk
exp_frac = 1.0 - 0.99 ** 40
got_frac = -rs["net_pl"] / 1_000_000.0
ck("40 losses of 1R each cost 33.10% of the account, not 40%",
   abs(got_frac - exp_frac) < 1e-3,
   f"account lost {got_frac*100:.2f}% (1 - 0.99^40 = {exp_frac*100:.2f}%); "
   f"summing R reports -40.0R = 40.00%, overstating this losing run by "
   f"{40.0 - got_frac*100:.2f} percentage points")

# the same 40 trades on a small account, where the minimum lot step bites
rs_small = simulate(seq, seq_mid, idx(400), broker=FREE, risk_frac=0.01,
                    start_equity=10_000.0)
small_frac = -rs_small["net_pl"] / 10_000.0
ck("lot granularity is a real effect, not a rounding nuisance",
   small_frac < got_frac - 0.02,
   f"the identical 40 trades cost {small_frac*100:.2f}% on a 10,000 account "
   f"against {got_frac*100:.2f}% on a 1,000,000 one. 1% of 9,900 against a "
   f"20-point stop wants 0.0495 lots and can only be dealt 0.04, so a small "
   f"account silently risks less than its budget - and a backtest in R units "
   f"cannot see this at all.")

# --------------------------------------------------------------------------
print("\nGROUP 6  margin and minimum lot actually bind")

# leverage 1:1 makes margin equal to full notional, so a second position
# cannot be afforded
TIGHT = Broker(**{**FREE.__dict__, "leverage": 1.0})
r = simulate(tr_o, mid_o, idx(10), broker=TIGHT, risk_frac=0.01,
             start_equity=10_000.0)
ck("a position that cannot be margined is REJECTED, not silently taken",
   r["rejected"]["margin"] > 0,
   f"{r['rejected']['margin']} of {r['n_offered']} rejected for margin, "
   f"{r['n_taken']} taken")

# a tiny account against a wide stop rounds below the minimum lot
r = simulate([dict(entry_bar=1, exit_bar=5, d=1, entry_px=2000.0,
                   exit_px=2000.0, stop_px=1000.0)],
             np.full(10, 2000.0), idx(10), broker=FREE, risk_frac=0.01,
             start_equity=100.0)
ck("a size below the minimum lot is a rejection, not a free trade",
   r["rejected"]["min_lot"] == 1 and r["n_taken"] == 0,
   f"rejected={r['rejected']}, taken={r['n_taken']}")

# --------------------------------------------------------------------------
print("\nGROUP 7  cost stress moves the answer in the right direction")
mid_w = np.concatenate([np.full(3, 2000.0), np.full(7, 2020.0)])
tr_w = [dict(entry_bar=1, exit_bar=5, d=1, entry_px=2000.0, exit_px=2020.0,
             stop_px=1990.0)]
base_b = Broker(commission_per_lot_side=3.5, slippage_points=0.0,
                swap_long_per_lot_night=0.0, swap_short_per_lot_night=0.0)
out = {}
for lvl in ("base", "elevated", "adverse"):
    rr = simulate(tr_w, mid_w, idx(10), broker=stressed(base_b, lvl),
                  risk_frac=0.01, start_equity=10_000.0, spread=np.full(10, 0.70))
    out[lvl] = rr["net_pl"]
ck("each stress level is strictly worse than the one below it",
   out["base"] > out["elevated"] > out["adverse"],
   "  ".join(f"{k}: {v:+.2f}" for k, v in out.items()))
ck("the stress levels are declared configuration, not measurements",
   set(STRESS) == {"base", "elevated", "adverse"} and
   all("spread_mult" in v for v in STRESS.values()),
   f"STRESS = {STRESS}")

# --------------------------------------------------------------------------
print("\nGROUP 8  the trade log can be traced back to the fills")
r = simulate(tr_o, mid_o, idx(10), broker=Broker(), risk_frac=0.01,
             start_equity=10_000.0, spread=np.full(10, 0.50))
df = log_frame(r)
need = {"entry_time", "exit_time", "d", "lots", "entry_fill", "exit_fill",
        "stop_px", "risk_money", "gross", "commission", "swap", "spread_cost",
        "pl", "balance_after"}
ck("every closed trade records its own fills, costs and resulting balance",
   need <= set(df.columns) and len(df) == r["n_taken"],
   f"{len(df)} rows, columns {sorted(df.columns)}")
if len(df):
    row = df.iloc[0]
    recomputed = ((row.exit_fill - row.entry_fill) * row.d * row.lots * 100.0
                  - row.commission - row.swap)
    ck("P&L recomputed from the logged fills matches the logged P&L",
       abs(recomputed - row.pl) < 1e-9,
       f"logged {row.pl:.6f}, recomputed from fills {recomputed:.6f}")

print("\nGROUP 9  a trade that opens and closes on the SAME bar")
# The intraday session deadline produces these constantly: a signal on the
# last closable bar of the day gets a one-bar trade, so entry_bar == exit_bar.
# With an equality test in the close step these were opened AFTER the close
# check had already run and were never closed at all - they held margin for
# the rest of the backtest. Thirteen years of them fired a false margin call
# whose liquidation booked +4,737 USC of stale profit in one bar.
mid_sb = np.concatenate([np.full(3, 2000.0), np.full(9, 2010.0)])
tr_sb = [dict(entry_bar=1, exit_bar=1, d=1, entry_px=2000.0, exit_px=2005.0,
              stop_px=1990.0)]
r_sb = simulate(tr_sb, mid_sb, idx(12), broker=FREE, risk_frac=0.01,
                start_equity=10_000.0)
ck("a same-bar trade is closed, not left open forever",
   r_sb["n_taken"] == 1 and not r_sb["blown"],
   f"taken={r_sb['n_taken']} (want 1), blown={r_sb['blown']} (want False), "
   f"max_concurrent={r_sb['max_concurrent']}")
# 0.10 lots, 5 points of profit = $50
ck("its P&L is priced from its own exit, not carried to the end of the data",
   abs(r_sb["net_pl"] - 50.0) < 1e-9,
   f"net {r_sb['net_pl']:.4f} (want 5 points on 0.10 lots = 50.00)")
# peak margin use is legitimately 0 here: the position is opened and closed
# inside the same bar, so it never survives to a mark-to-market point. What
# matters is that nothing is left tied up afterwards.
ck("no margin is left tied up after it closes",
   r_sb["equity"][-1] == r_sb["final_equity"] and r_sb["rejected"]["margin"] == 0,
   f"final equity {r_sb['final_equity']:.2f} = last equity point "
   f"{r_sb['equity'][-1]:.2f}, margin rejections {r_sb['rejected']['margin']}; "
   f"peak margin use is {r_sb['max_margin_use']*100:.2f}% because the trade "
   f"never lives to a mark-to-market bar, which is correct")

# many of them in a row must not accumulate
many = [dict(entry_bar=b, exit_bar=b, d=1, entry_px=2000.0, exit_px=2000.0,
             stop_px=1990.0) for b in range(1, 200)]
r_many = simulate(many, np.full(400, 2000.0), idx(400), broker=FREE,
                  risk_frac=0.01, start_equity=10_000.0)
ck("199 same-bar trades never stack up into a false margin call",
   not r_many["blown"] and r_many["max_concurrent"] <= 1,
   f"blown={r_many['blown']}, max_concurrent={r_many['max_concurrent']} "
   f"(want <= 1 - each closes on the bar it opened)")

print("\n" + "=" * 70)
print(summarise(r, "sample account (3 overlapping longs, all stopped):"))
print("=" * 70)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("all portfolio tests passed")
sys.exit(0)

# --------------------------------------------------------------------------
