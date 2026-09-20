"""Executable tests for the Market Regime Score."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regime as RG

_pass, _fail, _msgs = 0, 0, []


def check(ok, tid, what):
    global _pass, _fail
    if ok:
        _pass += 1
        print(f"  PASS  {tid:6s} {what}")
    else:
        _fail += 1
        _msgs.append(f"{tid}  {what}")
        print(f"  FAIL  {tid:6s} {what}")


def series(n=2000, sigma=1.0, seed=0, break_at=None, break_mult=1.0):
    rng = np.random.default_rng(seed)
    s = np.full(n, sigma)
    if break_at is not None:
        s[break_at:] = sigma * break_mult
    c = 4000.0 + np.cumsum(rng.normal(0.0, 1.0, n) * s)
    atr = np.empty(n)
    tr = np.abs(np.diff(c, prepend=c[0]))
    a = 1.0 / 14.0
    atr[0] = tr[0] if tr[0] > 0 else sigma
    for k in range(1, n):
        atr[k] = a * tr[k] + (1 - a) * atr[k - 1]
    vol = np.full(n, 1000.0)
    return c, atr, vol


print("=" * 78)
print("MARKET REGIME SCORE - executable tests")
print("=" * 78)

# --- the separation Amendment 01 section 5 requires --------------------
params = set(inspect.signature(RG.score_at).parameters)
banned = {"trades", "performance", "pnl", "returns", "expectancy", "health",
          "skill", "equity", "wins", "r_multiple"}
check(not (params & banned), "M1a",
      f"score_at takes no performance input (params: {sorted(params)})")
src = Path(RG.__file__).read_text().lower()
check(not any(w in src for w in ("expectancy", "win_rate", "pnl", "r_multiple")),
      "M1b", "the module never mentions a performance quantity")

# --- bounds and warm-up -------------------------------------------------
c, atr, vol = series()
r = RG.score_at(500, c, atr, vol)
check(r.score is None and r.label == RG.UNKNOWN, "M2a",
      "before the long window is filled the score is UNKNOWN, not a guess")
r = RG.score_at(1500, c, atr, vol, n_events_in_window=0)
check(r.score is not None and 0.0 <= r.score <= 100.0, "M2b",
      f"score is bounded 0-100 (got {r.score:.1f})")
check(all(0.0 <= v <= 100.0 for v in r.components.values()), "M2c",
      "every component is bounded 0-100")

# --- a stationary market scores higher than one that just broke ---------
c_s, atr_s, vol_s = series(seed=1)
r_stable = RG.score_at(1500, c_s, atr_s, vol_s, n_events_in_window=0)
c_b, atr_b, vol_b = series(seed=1, break_at=1400, break_mult=4.0)
r_break = RG.score_at(1500, c_b, atr_b, vol_b, n_events_in_window=0)
check(r_break.score < r_stable.score, "M3a",
      f"a 4x volatility break lowers the score "
      f"({r_stable.score:.1f} -> {r_break.score:.1f})")
check(r_break.components["atr_level"] < r_stable.components["atr_level"],
      "M3b", "the drop shows up in the volatility component")
check(r_stable.label in (RG.STABLE, RG.SHIFTING), "M3c",
      f"the undisturbed series is not labelled BREAKING (got {r_stable.label})")

# --- nothing is imputed -------------------------------------------------
r_nov = RG.score_at(1500, c, atr, None, n_events_in_window=0)
check("liquidity" in r_nov.missing and "liquidity" not in r_nov.components,
      "M4a", "no volume -> liquidity listed missing, never filled in")
check("spread" in r_nov.missing, "M4b",
      "no spread series -> spread listed missing")
check("cross_asset_correlation" in r_nov.missing, "M4c",
      "cross-asset correlation is always missing here - there is no DXY feed")
r_sp = RG.score_at(1500, c, atr, vol, spread=np.full(len(c), 0.5),
                   n_events_in_window=0)
check("spread" in r_sp.components and "spread" not in r_sp.missing, "M4d",
      "a spread series supplied -> the component appears")
check(r_nov.n_components < r_sp.n_components, "M4e",
      f"fewer inputs means fewer components, not the same score "
      f"({r_nov.n_components} vs {r_sp.n_components})")

# --- too few components -> no score at all ------------------------------
flat = np.full(2000, 4000.0)
r_few = RG.score_at(1500, flat, np.zeros(2000), None)
check(r_few.score is None and r_few.label == RG.UNKNOWN and not r_few.usable,
      "M5a", "below the component minimum the score is withheld entirely")
check("required" in r_few.reason, "M5b",
      "and the reason says how many were available")

# --- no look-ahead ------------------------------------------------------
c2 = c.copy()
c2[1501:] = 99999.0                      # destroy everything after the anchor
atr2 = atr.copy()
atr2[1501:] = 500.0
r_before = RG.score_at(1500, c, atr, vol, n_events_in_window=0)
r_after = RG.score_at(1500, c2, atr2, vol, n_events_in_window=0)
check(abs(r_before.score - r_after.score) < 1e-9, "M6a",
      "corrupting every bar after the anchor changes nothing - no look-ahead")

# --- scheduled events are part of the character -------------------------
r0 = RG.score_at(1500, c, atr, vol, n_events_in_window=0)
r4 = RG.score_at(1500, c, atr, vol, n_events_in_window=4)
check(r4.score < r0.score and r4.components["events"] == 0.0, "M7a",
      f"a window crowded with high-impact events scores lower "
      f"({r0.score:.1f} -> {r4.score:.1f})")

# --- every result is auditable ------------------------------------------
every = [RG.score_at(i, c, atr, vol, n_events_in_window=0)
         for i in (960, 1200, 1500, 1999)]
check(all(x.reason for x in every), "M8a", "every score carries a reason")
check(all(x.label in (RG.STABLE, RG.SHIFTING, RG.BREAKING, RG.UNKNOWN)
          for x in every), "M8b", "every score carries a declared label")
check(all(x.missing for x in every), "M8c",
      "the missing list is always populated - correlation is never available")

print("-" * 78)
print(f"passed {_pass}, failed {_fail}")
for m in _msgs:
    print("  FAILED:", m)
sys.exit(0 if _fail == 0 else 1)
