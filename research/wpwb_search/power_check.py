"""How big an edge could the DEV test have detected? (self-check before
reporting 'nothing found'). Plants a weekly-direction strategy that knows the
coming week's sign with accuracy q, runs it through the exact same pipeline
(1.5x costs, LONG + RDIR controls, same significance rule), and reports the
detection rate over 200 random plantings per q. DEV weeks only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import evaluate as EV  # noqa: E402
from run_dev import dev_cuts, load_canonical  # noqa: E402


def main() -> int:
    m = load_canonical()
    cuts = dev_cuts(m)
    n = len(cuts)
    pl = np.zeros(n); ps = np.zeros(n); truth = np.zeros(n, int); has = np.zeros(n, bool)
    for w, cut in enumerate(cuts):
        lo, hi = m.week_bars(int(cut))
        if hi <= lo:
            continue
        pl[w] = m.pnl_bp([lo], [hi - 1], [1], 1.5)[0]
        ps[w] = m.pnl_bp([lo], [hi - 1], [-1], 1.5)[0]
        truth[w] = 1 if m.c[hi - 1] > m.o[lo] else -1
        has[w] = True
    print(f"DEV weeks {n}; weekly long P&L sd = {pl[has].std():.1f} bp")
    for q in (0.55, 0.60, 0.65, 0.70):
        hits, gains = 0, []
        for s in range(200):
            rng = np.random.default_rng(10_000 + s)
            right = rng.random(n) < q
            d = np.where(right, truth, -truth)
            strat = np.where(has, np.where(d > 0, pl, ps), 0.0)
            ser = dict(strat=strat, long=np.where(has, pl, 0.0),
                       rdir=np.where(has, 0.5 * (pl + ps), 0.0),
                       ntr=has.astype(int))
            r = EV.summarize("A", ser)
            gains.append(r["mean_week_bp"])
            hits += (r["mean_week_bp"] > 0 and r["max_p"] < C.DEV_P_MAX)
        print(f"direction accuracy {q:.2f}: mean {np.mean(gains):+7.1f} bp/week, "
              f"detected in {hits/200:.0%} of plantings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
