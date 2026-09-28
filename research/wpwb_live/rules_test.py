"""Test the frozen loss-reduction rules (WPWB_LIVE_PREREG.md amendment 2) on
both eras, with a random-week-skip control for the FOMC rule."""
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
from backtest_report import load_events  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from run_round3 import sigma_at, volman_size  # noqa: E402

CAL_START = C.ep(2022, 1, 1)       # the economic calendar begins here


def week_long(m, cut, stop_k):
    """(bp, entry price, stopped?) of a 1-oz long Sunday open -> Friday close,
    optional catastrophe stop at stop_k x weekly sigma, resolved on M5."""
    lo, hi = m.week_bars(cut)
    entry = m.o[lo] + m.sp_in[lo]
    b5 = m.b5
    if stop_k is None:
        return float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0]), m.o[lo], False
    wsig = sigma_at(m, cut, 13) * np.sqrt(5)
    stop = entry * (1 - stop_k * wsig)
    j0 = int(np.searchsorted(b5.t, m.t[lo])); j1 = int(np.searchsorted(b5.t, m.t[hi - 1] + C.HOUR))
    hit = np.flatnonzero(b5.l[j0:j1] <= stop)
    if len(hit) == 0:
        return float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0]), m.o[lo], False
    j = j0 + int(hit[0])
    fill = min(stop, b5.o[j])
    nights = int(C.rollover_nights_vec([m.t[lo]], [b5.t[j]])[0])
    pnl = fill - entry - C.FEES - C.SWAP_LONG * nights
    return float(pnl / m.o[lo] * 1e4), m.o[lo], True


def run_rule(m, cuts, fomc, skip_fomc, stop_k, sc):
    out = []
    for cut in cuts:
        s = volman_size(m, int(cut), 13, sc)
        if skip_fomc and fomc[int(cut)]:
            out.append((0.0, 0.0, False, False))
            continue
        bp, px, stopped = week_long(m, int(cut), stop_k)
        out.append((s * bp, s * bp / 1e4 * px, True, stopped))
    a = np.array(out, dtype=object)
    return (np.array(a[:, 0], float), np.array(a[:, 1], float),
            np.array(a[:, 2], bool), np.array(a[:, 3], bool))


def maxdd(x):
    eq = np.cumsum(x)
    return float((eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min())


def main() -> int:
    m = C.Market(combined_bars())
    last = int(m.t[-1]) + C.HOUR
    allc = np.array([c for c in m.cuts if c + C.WEEK <= last and c >= CAL_START])
    ev = load_events()
    fomc_ts = ev[ev.event == "Fed Interest Rate Decision"].ts.to_numpy()
    fomc = {int(c): bool(((fomc_ts >= c) & (fomc_ts < c + C.WEEK)).any()) for c in allc}
    eras = {"old 2022-01..2023-12": allc[allc < C.DEV_END], "new 2024-01..2026-09": allc[allc >= C.DEV_END]}
    rules = {"R1 VOLMAN": (False, None), "R2 skip FOMC": (True, None),
             "R3 stop 2.0sd": (False, 2.0), "R4 skip FOMC + stop 2.0sd": (True, 2.0),
             "R5 stop 2.5sd": (False, 2.5)}
    sc: dict = {}
    rows = []
    rng = np.random.default_rng(2026)
    for era, cuts in eras.items():
        print(f"\n== {era}: {len(cuts)} weeks, FOMC weeks {sum(fomc[int(c)] for c in cuts)}")
        base_bp = None
        for name, (skip, k) in rules.items():
            bp, usd, traded, stopped = run_rule(m, cuts, fomc, skip, k, sc)
            r = dict(era=era, rule=name, net_bp=bp.sum(), net_usd=usd.sum(), maxdd_bp=maxdd(bp),
                     maxdd_usd=maxdd(usd), worst_usd=usd.min(), weeks=int(traded.sum()),
                     stops=int(stopped.sum()))
            if name == "R1 VOLMAN":
                base_bp = bp
            if skip:
                # control: the same series WITHOUT the FOMC skip (R1, or R3 for R4),
                # with the same number of weeks skipped at random instead
                ref = base_bp if k is None else run_rule.cache[(era, k)]
                S = int((~traded).sum())
                nets, dds = [], []
                for _ in range(5000):
                    x = ref.copy()
                    x[rng.choice(len(x), S, replace=False)] = 0.0
                    nets.append(x.sum()); dds.append(maxdd(x))
                nets, dds = np.array(nets), np.array(dds)
                r["net_pctile_vs_random_skip"] = float((nets <= bp.sum()).mean())
                r["dd_pctile_vs_random_skip"] = float((dds <= maxdd(bp)).mean())
            if k is not None and not skip:
                run_rule.cache[(era, k)] = bp.copy()
            rows.append(r)
            extra = ""
            if "net_pctile_vs_random_skip" in r:
                extra = (f" | vs random skip of {int((~traded).sum())} wks: net beats "
                         f"{r['net_pctile_vs_random_skip']:.0%}, DD better than "
                         f"{r['dd_pctile_vs_random_skip']:.0%}")
            print(f"  {name:26s} net {r['net_bp']:+7.0f} bp (${r['net_usd']:+6.0f})  "
                  f"maxDD {r['maxdd_bp']:+6.0f} bp (${r['maxdd_usd']:+5.0f})  worst wk "
                  f"${r['worst_usd']:+5.0f}  stops {r['stops']}{extra}")
    pd.DataFrame(rows).to_csv("data/wpwb_rules_test.csv", index=False)
    return 0


run_rule.cache = {}

if __name__ == "__main__":
    raise SystemExit(main())
