#!/usr/bin/env python3
"""Tests for the intraday session rules and the Exness cent account maths.

The account rules are the kind of thing that is quietly wrong for months: an
off-by-one on the deadline holds a position through rollover, a unit slip of
100x makes every lot size meaningless. Each case below states its expected
answer in the comment above it.

Run:  python3 research/test_session_rules.py
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import session_rules as S
from exness_cent import ExnessCent, POINT, SPREAD_SCENARIOS, slip_points

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

A = ExnessCent()

# --------------------------------------------------------------------------
print("\nGROUP 1  units: points, price and money")

ck("one point is 0.001 price units (digits 3, tick 0.001)",
   POINT == 0.001 and A.px(1) == 0.001, f"px(1 point) = {A.px(1)}")
ck("a 260-point spread is 0.260 in gold price terms",
   abs(A.px(260) - 0.260) < 1e-12, f"px(260) = {A.px(260)}")

# THE ANCHOR from the supplied spec: 0.01 lot on a 260-point spread costs
# about 0.26 USC. This is what pins contract size to 100.
cost = A.cost_round_trip(260.0, 0.01)
ck("the supplied cost anchor is reproduced: 0.01 lot @ 260 pts = 0.26 USC",
   abs(cost - 0.26) < 1e-9,
   f"cost_round_trip(260, 0.01) = {cost:.6f} USC "
   f"(contract size {A.contract_size:g}; at contract size 1 this would be "
   f"{0.260*1*0.01:.6f}, a hundred times too small)")

ck("commission is zero as supplied, so cost is spread plus slippage only",
   A.commission_per_lot_side == 0.0,
   f"commission per lot per side = {A.commission_per_lot_side}")

# slippage 0.1 x spread = 26 points, applied both sides = 52 points extra
c2 = A.cost_round_trip(260.0, 0.01, slip_points=slip_points(260.0, 0.1))
ck("slippage at 0.1x spread adds 2 x 26 points of cost",
   abs(c2 - (A.px(260 + 52) * 100 * 0.01)) < 1e-12,
   f"cost with 0.1x slippage = {c2:.6f} USC vs {cost:.6f} without "
   f"(+{(c2/cost-1)*100:.0f}%)")

# --------------------------------------------------------------------------
print("\nGROUP 2  rule 10: risk must clear 3x total cost")

# at 260 points with no slippage the cost is 0.260 price units, so the floor
# is 3 x 0.260 = 0.780 price units. This is LOT-INDEPENDENT.
mr = A.min_risk_price_units(260.0)
ck("the 3x floor at 260 points is 0.780 price units",
   abs(mr - 0.780) < 1e-12, f"min risk = {mr:.4f} price units "
   f"(the supplied estimate was 0.78 USC at 0.01 lot: "
   f"{mr * A.contract_size * A.min_lot:.4f} USC)")

# and it is computed from EACH scenario, not held constant
floors = {k: A.min_risk_price_units(v) for k, v in SPREAD_SCENARIOS.items()}
ck("the floor is recomputed per scenario, not a constant",
   len(set(floors.values())) == 3,
   "  ".join(f"{k}({v:g}pts) -> {floors[k]:.3f}px" for k, v in SPREAD_SCENARIOS.items()))

# with slippage the floor rises again
mr_slip = A.min_risk_price_units(600.0, slip_points(600.0, 0.3))
ck("the worst scenario (600 pts + 0.3x slippage) has the highest floor",
   mr_slip > floors["high"] > floors["normal"],
   f"600pts+0.3x slip -> {mr_slip:.3f} price units "
   f"({mr_slip/floors['normal']:.1f}x the normal-scenario floor)")

# --------------------------------------------------------------------------
print("\nGROUP 3  what a 500 USC account can actually deal")

# 0.01 lot is the smallest deal. With contract size 100, a stop D price units
# away risks D * 100 * 0.01 = D USC at the minimum lot.
for stop_px, label in ((0.78, "the 3x-cost floor"), (3.0, "M15-ish ATR stop"),
                       (10.0, "H1-ish 2xATR stop")):
    m = A.min_lot_risk_money(stop_px)
    pct = m / A.balance * 100
    print(f"          stop {stop_px:>5.2f} px ({label:<18}) -> minimum deal "
          f"risks {m:>6.2f} USC = {pct:>5.2f}% of a 500 USC account")

ck("a 10-price-unit stop at minimum lot already risks 2% of the account",
   abs(A.min_lot_risk_money(10.0) / A.balance - 0.02) < 1e-9,
   f"{A.min_lot_risk_money(10.0):.2f} USC on 500 USC = "
   f"{A.min_lot_risk_money(10.0)/A.balance*100:.2f}% - so risk budgets BELOW "
   f"this cannot be traded at all on such a stop, however small you set them")

# --------------------------------------------------------------------------
print("\nGROUP 4  session boundaries and the force-close deadline")

ck("the deadline is 20:30 UTC (21:00 rollover, 30 minutes early)",
   S.deadline_minutes() == 20 * 60 + 30,
   f"deadline = {S.deadline_minutes()//60:02d}:{S.deadline_minutes()%60:02d} UTC")

# three hourly bars around the boundary on a Tuesday
ix = pd.date_range("2024-01-02 18:00", periods=8, freq="1h", tz="UTC")
sid = S.session_ids(ix)
# 18:00, 19:00, 20:00 are the same server day; 21:00 starts the next
ck("21:00 UTC starts a new session, 20:00 does not",
   sid[0] == sid[1] == sid[2] and sid[3] != sid[2],
   f"hours {[t.hour for t in ix[:5]]} -> session ids {list(sid[:5])}")

dl, sid, closable = S.intraday_deadlines(ix, 60)
# an hourly bar starting 20:00 CLOSES at 21:00, which is rollover itself,
# so it cannot be an exit bar. 19:00 closes at 20:00 and can.
ck("an hourly bar closing at 21:00 is not a legal exit bar",
   not closable[2] and closable[1],
   f"20:00 bar closable={closable[2]} (closes 21:00), "
   f"19:00 bar closable={closable[1]} (closes 20:00)")
ck("a position opened at 18:00 must be out by the 19:00 bar's close",
   ix[dl[0]].hour == 19,
   f"deadline bar for the 18:00 entry is {ix[dl[0]]} "
   f"(exits at its close, 20:00 UTC, a full hour before rollover)")

# --------------------------------------------------------------------------
print("\nGROUP 5  the weekend needs no special case")

# Friday 19:00 through Monday 02:00, with the market shut over the weekend
fri = pd.date_range("2024-01-05 17:00", periods=3, freq="1h", tz="UTC")   # Fri
sun = pd.date_range("2024-01-07 22:00", periods=3, freq="1h", tz="UTC")   # Sun night
mon = pd.date_range("2024-01-08 01:00", periods=3, freq="1h", tz="UTC")   # Mon
ix2 = fri.append(sun).append(mon)
dl2, sid2, _ = S.intraday_deadlines(ix2, 60)
ck("Friday's bars and Sunday's opening bars are different sessions",
   sid2[0] != sid2[3],
   f"Fri 17:00 session {sid2[0]}, Sun 22:00 session {sid2[3]}")
ck("a Friday entry cannot be held into the new week",
   dl2[0] < 3 and dl2[0] >= 0,
   f"Friday 17:00 entry deadline bar = index {dl2[0]} ({ix2[dl2[0]]}), "
   f"which is still Friday - rule 7 falls out of rule 5's arithmetic")
ck("Sunday night and Monday morning ARE the same session",
   sid2[3] == sid2[5] == sid2[6],
   f"Sun 22:00 session {sid2[3]}, Mon 01:00 session {sid2[6]} - correct, "
   f"they are the same server day")

# --------------------------------------------------------------------------
print("\nGROUP 6  effective holds, and signals with no room left")

ix3 = pd.date_range("2024-01-02 15:00", periods=6, freq="1h", tz="UTC")
# 15,16,17,18,19,20 -> deadline is the 19:00 bar (index 4)
entries = np.array([0, 3, 4, 5])
hold, ok = S.effective_holds(ix3, entries, configured_hold=24, tf_minutes=60)
ck("a long configured hold is cut down to what the session allows",
   hold[0] == 5 and hold[1] == 2,
   f"entry at 15:00 gets hold {hold[0]} (bars 15..19), "
   f"entry at 18:00 gets {hold[1]} (bars 18..19), not the configured 24")
ck("a signal on the last closable bar still gets a one-bar trade",
   ok[2] and hold[2] == 1, f"entry at 19:00 -> ok={ok[2]}, hold={hold[2]}")
ck("a signal with NO room left is dropped, not traded at zero length",
   not ok[3],
   f"entry at 20:00 (closes 21:00, past the deadline) -> ok={ok[3]} - "
   f"dropped entirely rather than booked as an instant round trip")

print("\n" + "=" * 70)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("all session-rule and account-maths tests passed")
sys.exit(0)
