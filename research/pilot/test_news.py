"""
Executable tests for the news decision layer.

Every case is synthetic and its answer is known in advance, so a failure means
the classifier is wrong rather than that the market was surprising.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news as N

T0 = 1_700_000_000          # release time, epoch UTC
ATR = 2.0

_pass, _fail, _msgs = 0, 0, []


def check(ok: bool, tid: str, what: str) -> None:
    global _pass, _fail
    if ok:
        _pass += 1
        print(f"  PASS  {tid:6s} {what}")
    else:
        _fail += 1
        _msgs.append(f"{tid}  {what}")
        print(f"  FAIL  {tid:6s} {what}")


def bars(pre_min=60, post_min=90, drift_atr_per_60=0.0, early_atr=0.0,
         spike_high=0.0, spike_low=0.0, base=4000.0):
    """1-minute bars around the release.

    `early_atr` is the move completed by minute 5; `drift_atr_per_60` is where
    the move ends at minute 60. Setting early large and drift small produces a
    spike that is given back, which is the acceptance/rejection case.
    """
    t = np.arange(T0 - pre_min * 60, T0 + post_min * 60, 60, dtype=np.int64)
    c = np.full(len(t), base, dtype=float)
    for i, tt in enumerate(t):
        if tt < T0:
            continue
        m = (tt - T0) / 60.0
        if m <= 5:
            lvl = early_atr * (m / 5.0)
        else:
            frac = min(1.0, (m - 5) / 55.0)
            lvl = early_atr + (drift_atr_per_60 - early_atr) * frac
        c[i] = base + lvl * ATR
    h = c + 0.02 * ATR
    l = c - 0.02 * ATR
    post = t >= T0
    if spike_high:
        h[post] = np.maximum(h[post], base + spike_high * ATR)
    if spike_low:
        l[post] = np.minimum(l[post], base - spike_low * ATR)
    return t, h, l, c


def ev(actual=1.0, consensus=0.0, sigma=1.0, previous=None, revised=None,
       name="NFP", gold_neg=True):
    return N.Event(t=T0, name=name, actual=actual, consensus=consensus,
                   sigma=sigma, previous=previous, previous_revised=revised,
                   higher_is_gold_negative=gold_neg)


def react(**kw):
    t, h, l, c = bars(**kw)
    return N.measure_reaction(T0, t, h, l, c, ATR)


print("=" * 78)
print("NEWS DECISION LAYER - executable tests on cases with known answers")
print("=" * 78)

# ---- surprise ---------------------------------------------------------
check(abs(N.surprise_z(ev(actual=2.0, consensus=0.5, sigma=0.5)) - 3.0) < 1e-9,
      "N1a", "surprise z = (actual - consensus) / sigma")
check(N.surprise_z(ev(consensus=None)) is None,
      "N1b", "no consensus -> surprise is undefined, not zero")
check(N.surprise_z(ev(sigma=None)) is None,
      "N1c", "no historical sigma -> undefined")
check(abs(N.revision(ev(previous=100.0, revised=70.0)) + 30.0) < 1e-9,
      "N1d", "revision of the prior print is carried separately")

# ---- direction convention --------------------------------------------
check(N.hypothesis_direction(ev(gold_neg=True), 2.0) == -1,
      "N2a", "strong print on a gold-negative series -> gold-bearish")
check(N.hypothesis_direction(ev(gold_neg=True), -2.0) == +1,
      "N2b", "weak print on a gold-negative series -> gold-bullish")
check(N.hypothesis_direction(ev(gold_neg=False), 2.0) == +1,
      "N2c", "the sign convention comes from the series, not from price")

# ---- reaction measurement --------------------------------------------
t, h, l, c = bars(drift_atr_per_60=1.0, early_atr=1.0)
r = N.measure_reaction(T0, t, h, l, c, ATR)
check(set(r.by_horizon) == set(N.HORIZONS_MIN),
      "N3a", "all four mandated horizons measured (1/5/15/60 min)")
check(all(r.bars_used[hh] <= hh for hh in N.HORIZONS_MIN),
      "N3b", "no horizon uses more bars than its own minutes - no look-ahead")
check(abs(r.by_horizon[60] - 1.0) < 0.05,
      "N3c", "a 1 ATR move reads as +1.00 ATR at 60 minutes")
# The anchor must be the last close BEFORE the release, not the release bar
# itself. Give the release bar a wildly different close: if it were used as
# the baseline the 60-minute reading would invert.
t2, h2, l2, c2 = bars(drift_atr_per_60=1.0, early_atr=1.0)
c2[int(np.flatnonzero(t2 >= T0)[0])] = 4000.0 + 5.0 * ATR
r2 = N.measure_reaction(T0, t2, h2, l2, c2, ATR)
check(abs(r2.by_horizon[60] - 1.0) < 0.05, "N3d",
      "baseline is the close before release, not the release bar")

# ---- the eight situations --------------------------------------------
seen = {}

a = N.assess([ev(actual=-2.0)], react(drift_atr_per_60=1.5, early_atr=1.2))
seen[a.scenario] = a
check(a.scenario == N.POS_CONFIRM and a.confirmed and a.tradeable,
      "N4a", "gold-bullish surprise + price up and held -> POSITIVE_CONFIRMED")

a = N.assess([ev(actual=-2.0)], react(drift_atr_per_60=-1.5, early_atr=-1.2))
seen[a.scenario] = a
check(a.scenario == N.POS_REJECT and a.confirmed is False,
      "N4b", "gold-bullish surprise + price down -> POSITIVE_REJECTED")

a = N.assess([ev(actual=2.0)], react(drift_atr_per_60=-1.5, early_atr=-1.2))
seen[a.scenario] = a
check(a.scenario == N.NEG_CONFIRM and a.confirmed,
      "N4c", "gold-bearish surprise + price down -> NEGATIVE_CONFIRMED")

a = N.assess([ev(actual=2.0)], react(drift_atr_per_60=1.5, early_atr=1.2))
seen[a.scenario] = a
check(a.scenario == N.NEG_REJECT and a.confirmed is False,
      "N4d", "gold-bearish surprise + price up -> NEGATIVE_REJECTED")

a = N.assess([ev(actual=0.2)], react(drift_atr_per_60=2.0, early_atr=2.0))
seen[a.scenario] = a
check(a.scenario == N.IN_LINE,
      "N4e", "release near consensus -> IN_LINE whatever price did")

a = N.assess([ev(actual=2.0, name="NFP"),
              ev(actual=-2.0, name="AHE")],
             react(drift_atr_per_60=1.5))
seen[a.scenario] = a
check(a.scenario == N.CONFLICTING,
      "N4f", "simultaneous releases with opposite hypotheses -> CONFLICTING")

a = N.assess([ev(actual=2.0)],
             react(drift_atr_per_60=-1.5, early_atr=-1.2,
                   spike_high=3.0, spike_low=3.0))
seen[a.scenario] = a
check(a.scenario == N.SWEEP_BOTH,
      "N4g", "both pre-event extremes taken -> SWEPT_BOTH_SIDES, no side read")

a = N.assess([ev(consensus=None)], react(drift_atr_per_60=1.5))
seen[a.scenario] = a
check(a.scenario == N.NO_TRADE and "not computable" in a.reason,
      "N4h", "missing consensus -> NO_TRADE naming what was missing")

check(set(seen) == set(N.SCENARIOS),
      "N5", f"all eight situations reachable ({len(seen)}/8)")

# ---- acceptance vs rejection -----------------------------------------
a = N.assess([ev(actual=-2.0)], react(early_atr=1.5, drift_atr_per_60=0.2))
check(a.scenario == N.POS_REJECT and "given back" in a.reason,
      "N6a", "a spike that is given back is a rejection, not a confirmation")

a = N.assess([ev(actual=-2.0)], react(early_atr=1.5, drift_atr_per_60=1.4))
check(a.scenario == N.POS_CONFIRM,
      "N6b", "a move that holds stays a confirmation")

# ---- stand-aside conditions come first --------------------------------
a = N.assess([ev(actual=-2.0)], react(drift_atr_per_60=1.5),
             spread_over_limit=True)
check(a.scenario == N.NO_TRADE and "spread" in a.reason,
      "N7a", "spread over limit beats a clean confirmation")

a = N.assess([ev(actual=2.0)], react(drift_atr_per_60=0.1, early_atr=0.1))
check(a.scenario == N.NO_TRADE and "noise band" in a.reason,
      "N7b", "reaction inside the noise band -> NO_TRADE, not a weak signal")

a = N.assess([ev(actual=2.0)], None)
check(a.scenario == N.NO_TRADE and not a.tradeable,
      "N7c", "no reaction measured yet -> NO_TRADE")

a = N.assess([], react())
check(a.scenario == N.NO_TRADE, "N7d", "no event -> NO_TRADE")

# ---- nothing is invented ---------------------------------------------
every = [N.assess([ev(actual=x)], react(drift_atr_per_60=y))
         for x in (-2.0, 0.0, 2.0) for y in (-1.5, 0.0, 1.5)]
check(all(a.priced_in.startswith("NOT ASSESSED") for a in every),
      "N8a", "priced-in is NOT ASSESSED on every path - never estimated")
check(all(a.positioning.startswith("NOT ASSESSED") for a in every),
      "N8b", "positioning is NOT ASSESSED on every path")
check(all(a.reason for a in every),
      "N8c", "every assessment carries a stated reason")
check(all(a.scenario in N.SCENARIOS for a in every),
      "N8d", "every assessment lands in exactly one declared situation")

print("-" * 78)
print(f"passed {_pass}, failed {_fail}")
for m in _msgs:
    print("  FAILED:", m)
sys.exit(0 if _fail == 0 else 1)
