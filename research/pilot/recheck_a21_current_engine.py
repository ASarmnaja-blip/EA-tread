"""Claude's review of Amendment 26: does Amendment 21 survive on the CURRENT
engine?

Amendment 26 measured A21's chain contamination on the frozen a67cca7 engine.
That isolates the chain effect correctly. But the a67cca7 engine predates two
later corrections that current mtf_engine carries:

  1. no same-bar target credit after an intrabar limit fill
     (allow_entry_bar_target)
  2. buy limits fill on Ask (Bid low + spread), not on the Bid low

Both corrections can only make results worse. So A21's surviving
+248 R on a67cca7 does not show that A21 survives on the corrected engine.
This script applies A21's frozen weekly-selection rules (Codex's _a21_run,
unchanged) to the two current-engine Demo90 universes:

  LEGACY chain  data/weekly_evolution_universe_v10_sp090_co140.pkl
  CAUSAL chain  data/causal_filltime_universe_v1_sp090_co140.pkl

It reports Codex's own base metrics. It also sums every trade's base and
1.5x-cost net R by entry time, as an independent cross-check. The 1.5x stress
adds half of spread + commission + slippage, spread floored at 0.090, the same
as Amendments 23-26. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import causal_chain as C
import evolution_portfolio_audit as audit
import historical_regime_walkforward as hist
import mtf_engine as E


def stress_sums(run: dict, b5, windows) -> dict:
    out = {}
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    for name, lo, hi in windows:
        base = stress = 0.0
        n = 0
        for r in run["rows"]:
            if not (lo <= r["entry_t"] < hi):
                continue
            k = r["entry_k"]
            spread = max(float(b5.sp[k]), E.SPREAD_FALLBACK) if b5.sp is not None \
                else E.SPREAD_FALLBACK
            execution = spread + fee
            base += r["net"]
            stress += r["net"] - 0.5 * execution / r["risk"]
            n += 1
        out[name] = (n, base, stress)
    return out


def main() -> int:
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    windows = (("44_MONTH", C.REPORT_START, C.REPORT_SPLIT),
               ("TRAILING_12M", C.REPORT_SPLIT, last),
               ("FULL_AVAILABLE", int(b5.t[0]), last))

    legacy_uni, _ = audit.load_universe(b5)
    causal_uni, _, _, _ = C.load_causal_universe(b5)

    for label, uni in (("LEGACY chain / current engine", legacy_uni),
                       ("CAUSAL chain / current engine", causal_uni)):
        run = C._a21_run(uni, b5)
        codex = C._collect_a21(run, b5)
        mine = stress_sums(run, b5, windows)
        print(f"\n== A21 rules, {label} ==  champion transitions {run['transitions']}")
        for name, _, _ in windows:
            key = name if name in codex else ("TRAILING_12_MONTH"
                                              if name == "TRAILING_12M" else name)
            cb = codex.get(key, {}).get("BASE", {})
            n, base, stress = mine[name]
            print(f"  {name:15s} trades {n:5d}  base {base:+9.3f} R  "
                  f"1.5x {stress:+9.3f} R   | Codex base {cb.get('net_R', float('nan')):+9.3f}"
                  f"  PF {cb.get('pf', float('nan')):.3f}  "
                  f"seqDD {cb.get('max_dd_R', cb.get('sequence_dd_R', float('nan')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
