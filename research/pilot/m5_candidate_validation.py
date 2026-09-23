"""Focused validation for the winning M5-only K=5 diverse policy."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolution_candidate_validation as valid
import evolution_portfolio_audit as audit


def main() -> int:
    b5 = audit.hist.load_history()
    first, last = int(b5.t[0]), int(b5.t[-1] + b5.step)
    uni, meta = audit.load_universe(b5)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    m5 = [(cut, end, [tag for tag in ranked if meta[tag]["tf"] == "M5"])
          for cut, end, ranked in rankings]
    rows, info = audit.weekly_portfolio(b5, uni, meta, m5, purged, 5, True)
    print("candidate", info)
    print("full", audit.metrics(rows))
    print("365d", audit.metrics(rows, last - 365 * audit.DAY))
    print("90d", audit.metrics(rows, last - 90 * audit.DAY))
    print("mtm_full", audit.mark_to_market(rows, b5))
    print("mtm_365d", audit.mark_to_market(
        [r for r in rows if r.t >= last - 365 * audit.DAY], b5))
    print("mtm_90d", audit.mark_to_market(
        [r for r in rows if r.t >= last - 90 * audit.DAY], b5))
    long = []
    for r in rows:
        a = uni[r.label]
        j = np.flatnonzero(a["t_in"] == r.t)[0]
        long.append(a["direction"][j] > 0)
    print(f"direction_long_pct={100*np.mean(long):.2f}")
    params = Counter()
    omitted = Counter()
    for _cut, _end, ranked in m5:
        chosen = valid.choose_five(ranked, meta)
        chosen_setups = {meta[tag]["setup"] for tag in chosen}
        omitted.update(set(audit.wf.E.SETUPS) - chosen_setups)
        for tag in chosen:
            m = meta[tag]
            params[(m["setup"], m["stop"], m["target"], m["off"], m["exp"])] += 1
    print("omitted_family_weeks", dict(omitted))
    print("top_parameters", params.most_common(25))
    valid.ranking_control(uni, meta, m5)
    valid.truncation_audit(b5, uni, meta, m5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
