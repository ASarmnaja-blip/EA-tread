"""Post-hoc robustness checks on VOLMAN, the only tool with meaningful
current-era evidence (disclosed as post-hoc: it was picked because it was
strongest). Checks: concentration, per-year, size-permutation (does the
TIMING of size matter, holding the size distribution fixed), and a gross
cross-asset breadth test on other symbols from the same terminal."""
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
from run_round3 import volman_size  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402


def xau_current(hl):
    m = C.Market(combined_bars())
    last = int(m.t[-1]) + C.HOUR
    cuts = np.array([c for c in m.cuts if c >= C.DEV_END and c + C.WEEK <= last])
    sc: dict = {}
    s, L = [], []
    for cut in cuts:
        lo, hi = m.week_bars(int(cut))
        s.append(volman_size(m, int(cut), hl, sc))
        L.append(float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0]))
    return cuts, np.array(s), np.array(L)


def gross_volman(t, c, hl=13, start=C.DEV_END):
    """Gross weekly log-return test on any symbol: size from trailing daily
    returns exactly as VOLMAN, excess vs exposure-matched constant long."""
    day = t // 86400
    uniq, first = np.unique(day, return_index=True)
    last = np.r_[first[1:] - 1, len(t) - 1]
    dret = np.log(c[last] / c[first]); dt = t[first]
    cut = _week_boundary(int(t[0]))
    sig = {}
    rows = []
    while cut + C.WEEK <= t[-1]:
        m26 = (dt < cut) & (dt >= cut - 26 * C.WEEK)
        if m26.sum() >= 40:
            w = 0.5 ** (((cut - dt[m26]) / C.WEEK) / hl)
            r = dret[m26]; mu = (w * r).sum() / w.sum()
            sig[cut] = float(np.sqrt((w * (r - mu) ** 2).sum() / w.sum()))
        lo = np.searchsorted(t, cut); hi = np.searchsorted(t, cut + C.WEEK) - 1
        if cut >= start and cut in sig and hi > lo:
            ref = [sig[cut - j * C.WEEK] for j in range(1, 53) if cut - j * C.WEEK in sig]
            if len(ref) >= 8:
                size = min(2.0, np.median(ref) / sig[cut])
                rows.append((size, np.log(c[hi] / c[lo]) * 1e4))
        cut += C.WEEK
    a = np.array(rows)
    s, L = a[:, 0], a[:, 1]
    ex = s * L - s.mean() * L
    return len(a), ex.mean(), ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex)))


def main() -> int:
    for hl in (13, 4):
        cuts, s, L = xau_current(hl)
        ex = s * L - s.mean() * L
        yrs = pd.to_datetime(cuts, unit="s").year
        print(f"== XAU VOLMAN hl={hl}: weeks {len(s)}, mean size {s.mean():.2f}, "
              f"size range {s.min():.2f}..{s.max():.2f}")
        print(f"   excess vs exposure-matched long: {ex.mean():+.2f} bp/week")
        for y in sorted(set(yrs)):
            k = yrs == y
            print(f"   {y}: excess {ex[k].mean():+7.2f} bp/week over {k.sum()} weeks")
        order = np.argsort(-ex)
        tot = ex.sum()
        print(f"   top 5 weeks = {ex[order[:5]].sum() / tot:.0%} of total excess; "
              f"excess positive in {(ex > 0).mean():.0%} of weeks")
        rng = np.random.default_rng(42)
        obs = (s * L).sum()
        perm = np.array([(rng.permutation(s) * L).sum() for _ in range(20000)])
        print(f"   size-permutation p (timing of size matters?) = {(perm >= obs).mean():.4f}")
        print(f"   corr(size, week P&L) = {np.corrcoef(s, L)[0, 1]:+.3f}")

    print("\n== gross cross-asset breadth (same method, 2024-01..latest, fresh data)")
    for sym in ("XAUUSD", "XAGUSD", "US500", "EURUSD", "USDJPY", "DXY"):
        f = np.load(f"data/fresh/{sym}_M5.npz")
        n, mean_ex, t = gross_volman(f["t"].astype(np.int64), f["c"])
        print(f"   {sym:7s} weeks {n:3d}  excess {mean_ex:+7.2f} bp/week  t {t:+5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
