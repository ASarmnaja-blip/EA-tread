"""Amendment 6: after the first H1 close beyond the prior week's range
(Mon-Thu), does gold continue for the rest of the week? Runs once."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import common as C  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402


def main() -> int:
    m = C.Market(combined_bars())
    last = int(m.t[-1]) + C.HOUR
    rows = []
    for cut in m.cuts:
        cut = int(cut)
        if cut + C.WEEK > last:
            break
        lo, hi = m.week_bars(cut); plo, phi = m.week_bars(cut - C.WEEK)
        if hi - lo < 50 or phi - plo < 50:
            continue
        ph, pl = m.h[plo:phi].max(), m.l[plo:phi].min()
        for k in range(lo, hi - 1):
            if int(m.wday[k]) == 4:            # Friday: too little week left
                break
            d = 1 if m.c[k] > ph else -1 if m.c[k] < pl else 0
            if d:
                cont = d * (m.c[hi - 1] / m.c[k] - 1) * 1e4
                net = float(m.pnl_bp([k + 1], [hi - 1], [d], 1.0)[0])   # enter next bar open
                rows.append(dict(cut=cut, era="A" if cut < C.DEV_END else "B", side="BPL" if d < 0 else "BPH",
                                 day=int(m.wday[k]), cont_bp=cont, net_bp=net))
                break
    df = pd.DataFrame(rows)
    df.to_csv("data/wpwb_level_break.csv", index=False)
    rng = np.random.default_rng(66)
    ok_all = True
    for e, name in (("A", "2021-07..2023-12"), ("B", "2024-01..2026-09")):
        x = df[df.era == e]
        v = x.cont_bp.to_numpy()
        perm = np.array([(v * rng.choice([-1, 1], len(v))).mean() for _ in range(20000)])
        p = float((perm >= v.mean()).mean())
        bpl = x[x.side == "BPL"].cont_bp
        bph = x[x.side == "BPH"].cont_bp
        ok = v.mean() > 0 and p < 0.05 and bpl.mean() > 0
        ok_all &= ok
        print(f"{name}: breaks {len(x)} (BPL {len(bpl)}, BPH {len(bph)}); continuation mean {v.mean():+.1f} bp, "
              f"p={p:.3f}; BPL {bpl.mean():+.1f} bp (continued in {(bpl > 0).mean():.0%}), "
              f"BPH {bph.mean():+.1f} bp (continued in {(bph > 0).mean():.0%}); "
              f"after costs (trade from next bar) {x.net_bp.mean():+.1f} bp -> {'pass' if ok else 'fail'}")
    print(f"\nAMENDMENT 6: {'PASS' if ok_all else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
