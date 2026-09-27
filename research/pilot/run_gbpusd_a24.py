"""Amendment 29 — the frozen A24/A26 mechanism, unchanged, on GBPUSD.

Reuses causal_chain.py's `_policy_data_causal_gate` (pure in-memory, no disk
cache collision risk) and basket_gate.py's Selector/execution/window_metrics
completely unmodified. Only mtf_engine's cost constants and the source Bars
object change, exactly as compound_bar_replay.py's --profile flag already
did for a different cost scenario on XAUUSD. The XAUUSD raw-opportunity cache
is untouched: GBPUSD's cost inputs hash to a different cache filename, and
basket_gate.load_raw_cache's content-hash check would force a rebuild even on
an accidental name collision, never silently reuse the wrong data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import canonical_history as ch
import causal_chain as C
import mtf_engine as E

CANON = Path("data/canonical_GBPUSD_M5.npz")
COST = json.loads(Path("data/cost_model.json").read_text())["GBPUSD"]


def set_gbpusd_costs(slip_scenario: str) -> None:
    E.SPREAD_FALLBACK = float(COST["spread_live"]) or 1e-5  # never zero
    E.COMMISSION_RT = float(COST["commission_price_round_turn"])
    E.SWAP_LONG = -float(COST["swap_long_price_per_night"])  # E convention: positive charge
    E.SWAP_SHORT = -float(COST["swap_short_price_per_night"])
    if slip_scenario == "zero":
        E.SLIP_PER_FILL = 0.0
    elif slip_scenario == "spread_equal":
        # round-turn slippage set equal to round-turn spread (2x SLIP_PER_FILL
        # in the cost formulas below) => SLIP_PER_FILL = spread_floor / 2
        E.SLIP_PER_FILL = E.SPREAD_FALLBACK / 2.0
    else:
        raise ValueError(slip_scenario)


def windows_for(b5) -> tuple[tuple[str, int, int], ...]:
    t0, t1 = int(b5.t[0]), int(b5.t[-1] + b5.step)
    mid = (t0 + t1) // 2
    return (("FIRST_HALF", t0, mid), ("SECOND_HALF", mid, t1), ("FULL", t0, t1))


def run_scenario(b5, slip_scenario: str) -> dict:
    set_gbpusd_costs(slip_scenario)
    streams, raw_meta, built = A24.load_raw_cache(b5)
    pd = C._policy_data_causal_gate(b5, streams, raw_meta)
    last = int(b5.t[-1] + b5.step)
    first_policy = int(pd.boundaries[A24.MIN_HISTORY_WEEKS])
    decisions = A24.decisions_through(A24.Selector(pd, raw_meta, "gate"),
                                      first_policy, last)
    opportunities = A24.opportunities_from_decisions(b5, streams, raw_meta,
                                                     decisions, True)
    execution = A24.execute_opportunities(opportunities, True)
    path = A24.unit_path(b5, execution.admitted)
    out = {"decisions": decisions, "execution": execution, "path": path,
          "built_cache": built, "meta": raw_meta}
    n_sa = sum(1 for d in decisions if not d.members)
    out["no_trade_weeks"] = n_sa
    out["total_weeks"] = len(decisions)
    return out


def main() -> int:
    print("AMENDMENT_29_GBPUSD_CROSS_ASSET_CHECK")
    print("research_only=true mt5_connection=false order_sending=false")
    b5 = ch.load(CANON)
    print(f"GBPUSD bars={len(b5):,} "
          f"{datetime.fromtimestamp(int(b5.t[0]), timezone.utc)} .. "
          f"{datetime.fromtimestamp(int(b5.t[-1]), timezone.utc)}")
    wins = windows_for(b5)
    for w in wins:
        print(f"  window {w[0]}: {datetime.fromtimestamp(w[1], timezone.utc):%Y-%m-%d} "
              f".. {datetime.fromtimestamp(w[2], timezone.utc):%Y-%m-%d}")

    for scenario in ("zero", "spread_equal"):
        print(f"\n=== slippage scenario: {scenario} (NOT MEASURED for GBPUSD) ===")
        run = run_scenario(b5, scenario)
        print(f"  cache_built_this_run={run['built_cache']}  "
              f"decision_weeks={run['total_weeks']}  "
              f"no_trade_weeks={run['no_trade_weeks']} "
              f"({100*run['no_trade_weeks']/max(run['total_weeks'],1):.1f}%)")
        for name, start, end in wins:
            for cost, stress in (("BASE", False), ("COST_1P5X", True)):
                m = A24.window_metrics(b5, run["path"], run["execution"],
                                       run["meta"], start, end, stress)
                print(f"  {name:12s} {cost:10s} net_R={m['net_R']:+9.3f} "
                      f"trades={m['trades']:6d} PF={m.get('pf', float('nan')):.3f} "
                      f"active_wk={m.get('active_week_pct', float('nan')):5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
