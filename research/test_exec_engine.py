#!/usr/bin/env python3
"""Unit tests for the shared execution engine.

Every case is a hand-built path whose correct answer is computed by hand in
the comment above it. Non-zero exit on any failure.

Run:  python3 research/test_exec_engine.py
"""
import sys, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from exec_engine import execute, plan_from_signal, REASON, GAP_SKIP

fails = []

def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

def arrs(rows):
    o, h, l, c = map(np.asarray, zip(*rows))
    return o.astype(float), h.astype(float), l.astype(float), c.astype(float), len(rows)

ZERO = np.zeros(400)

# --------------------------------------------------------------------------
print("\nGROUP 1  the entry-gap defect, both directions")

# LONG. Signal bar index 0 closes 110, stop 98, risk 12, target 134 (2R).
# Entry bar (index 1) OPENS AT 90 - already below the stop. The plan is void.
rows = [(100, 110, 98, 110), (90, 92, 88, 89), (89, 91, 87, 88), (88, 90, 86, 87)]
o, h, l, c, N = arrs(rows)
r_skip = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=3,
                 cost_at=ZERO, on_gap="skip")
ck("long gap: skip policy records no R and marks the trade",
   r_skip["reason"] == GAP_SKIP and np.isnan(r_skip["R"]),
   f"reason={REASON[r_skip['reason']]}, R={r_skip['R']}")

r_open = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=3,
                 cost_at=ZERO, on_gap="open")
# fills and exits at the opening price 90: R = (90-90)*1/12 = 0 exactly
ck("long gap: open policy exits at the opening price, R = 0.0000",
   abs(r_open["R"] - 0.0) < 1e-12,
   f"R={r_open['R']:+.6f}, exit={r_open['exit']} (must be 90.0, never 98)")
ck("long gap: the engine never books the 98 that did not trade after entry",
   r_open["exit"] == 90.0, f"exit price recorded = {r_open['exit']}")

# SHORT mirror. Signal closes 90, stop 102, risk 12. Entry opens 110, above stop.
rows = [(100, 102, 90, 90), (110, 112, 108, 111), (111, 113, 109, 112),
        (112, 114, 110, 113)]
o, h, l, c, N = arrs(rows)
r_s = execute(o, h, l, c, N, 0, -1, stop=102, risk=12, target=66, hold=3,
              cost_at=ZERO, on_gap="open")
ck("short gap: exits at the opening price, R = 0.0000",
   abs(r_s["R"] - 0.0) < 1e-12,
   f"R={r_s['R']:+.6f}, exit={r_s['exit']} (must be 110.0, never 102)")

# --------------------------------------------------------------------------
print("\nGROUP 2  normal fills, hand-computed")

# Entry 110, stop 98, risk 12, target 134. Bar 2 highs 140 -> target fills at 134.
# R = (134-110)/12 = +2.0 exactly, at zero cost.
rows = [(100, 110, 98, 110), (110, 112, 109, 111), (111, 140, 110, 139),
        (139, 141, 138, 140)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=4, cost_at=ZERO)
ck("target fill returns exactly +2.0000000000",
   abs(r["R"] - 2.0) < 1e-12, f"R={r['R']:.10f}, reason={REASON[r['reason']]}")

# Same path but the stop is touched first on bar 1 (low 97 < 98).
rows = [(100, 110, 98, 110), (110, 112, 97, 99), (99, 140, 98, 139)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=3, cost_at=ZERO)
ck("stop fill returns exactly -1.0000000000",
   abs(r["R"] + 1.0) < 1e-12, f"R={r['R']:.10f}, reason={REASON[r['reason']]}")

# Both touched in the same bar -> stop wins.
rows = [(100, 110, 98, 110), (110, 140, 97, 120)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=2, cost_at=ZERO)
ck("stop wins when stop and target are both touched in one bar",
   abs(r["R"] + 1.0) < 1e-12, f"R={r['R']:.10f}, reason={REASON[r['reason']]}")

# --------------------------------------------------------------------------
print("\nGROUP 3  the horizon must be the same bar for everyone")

# hold=3 with the entry bar counting as bar 1 -> exit at the close of bar e+2.
rows = [(100, 110, 98, 110), (110, 111, 109, 110.5), (110.5, 112, 110, 111),
        (111, 113, 110, 112), (112, 114, 111, 113), (113, 115, 112, 114)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=None, hold=3, cost_at=ZERO)
# entry bar is index 1; hold 3 -> last bar index 1+3-1 = 3, close 112
ck("hold H exits on the close of bar e+H-1",
   r["exit_bar"] == 3 and abs(r["exit"] - 112.0) < 1e-12 and r["held"] == 3,
   f"exit_bar={r['exit_bar']} (expect 3), exit={r['exit']} (expect 112.0), "
   f"held={r['held']} (expect 3)")

# --------------------------------------------------------------------------
print("\nGROUP 4  cost is taken at the entry bar, not the signal bar")
costs = np.array([99.0, 6.0, 99.0, 99.0])     # only the entry bar's 6.0 may be used
rows = [(100, 110, 98, 110), (110, 112, 109, 111), (111, 140, 110, 139),
        (139, 141, 138, 140)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=4, cost_at=costs)
# R = ((134-110)*1 - 6)/12 = 18/12 = +1.5
ck("cost comes from the entry bar's own index",
   abs(r["R"] - 1.5) < 1e-12, f"R={r['R']:.10f} (expect +1.5 with cost 6)")

# --------------------------------------------------------------------------
print("\nGROUP 5  gaps AFTER entry fill at the open, not at the bracket")
# Entry 110, stop 98. Bar 2 opens at 80, far below the stop: the fill is 80.
rows = [(100, 110, 98, 110), (110, 112, 105, 111), (80, 82, 78, 79)]
o, h, l, c, N = arrs(rows)
r = execute(o, h, l, c, N, 0, +1, stop=98, risk=12, target=134, hold=3, cost_at=ZERO)
# R = (80 - 110)/12 = -2.5  -> a gap loses MORE than 1R, which is correct
ck("a gap through the stop after entry fills at the open and loses > 1R",
   abs(r["R"] + 2.5) < 1e-12,
   f"R={r['R']:.10f} (expect -2.5), exit={r['exit']} (expect 80.0)")

# --------------------------------------------------------------------------
print("\nGROUP 6  plan_from_signal eligibility")
p = plan_from_signal(c_sig=110, atr=4.0, ph=102, pl=98, d=+1, stop_mode="range",
                     buf=0.0, tp_mult=2.0)
ck("range stop and 2R target computed from the signal close",
   p is not None and abs(p[0] - 98) < 1e-12 and abs(p[1] - 12) < 1e-12
   and abs(p[2] - 134) < 1e-12, f"plan={p} (expect stop 98, risk 12, target 134)")

p_bad = plan_from_signal(c_sig=110, atr=1.0, ph=102, pl=98, d=+1,
                         stop_mode="range", buf=0.0, tp_mult=2.0)
ck("a risk of 12 against an ATR of 1 is rejected (outside 0.25-8 ATR)",
   p_bad is None, f"plan={p_bad} (expect None)")

p_cost = plan_from_signal(c_sig=110, atr=4.0, ph=102, pl=98, d=+1,
                          stop_mode="range", buf=0.0, tp_mult=2.0, cost=5.0)
ck("a risk of 12 against a round-trip cost of 5 is rejected (needs 3x)",
   p_cost is None, f"plan={p_cost} (expect None)")

print("\n" + "=" * 66)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("all execution-engine tests passed")
sys.exit(0)
