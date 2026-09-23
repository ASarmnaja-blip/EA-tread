"""Focused no-look-ahead and portfolio audit for the M1 extension."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import evolution_candidate_validation as valid
import evolution_portfolio_audit as audit
import minute_timeframe_extension as minute
import mtf_engine as E


DAY = 86400


def rebuild_m1(b1, tag: str, meta: dict):
    m = meta[tag]
    nxt = np.arange(1, len(b1) + 1, dtype=np.int64)
    nxt[-1] = -1
    atr = core.atr(b1, E.ATR_N)
    sig = E.setup_signals(m["setup"], core.Ctx(b1, nxt))
    old = E.TIME_STOP_M5
    try:
        E.TIME_STOP_M5 = 1440
        return E.run_cell(b1, nxt, atr, sig, b1, m["stop"], m["target"],
                          (m["off"], m["exp"]), 1)["rows"]
    finally:
        E.TIME_STOP_M5 = old


def truncation(b1, uni, meta, rankings):
    picks = np.linspace(0, len(rankings) - 1, 8, dtype=int)
    checked = mismatches = 0
    max_abs = 0.0
    for p in picks:
        cut, _end, ranked = rankings[int(p)]
        stop = int(np.searchsorted(b1.t, cut, side="left"))
        truncated = b1.slice(0, stop)
        for tag in valid.choose_five(ranked, meta):
            rows = rebuild_m1(truncated, tag, meta)
            got = {int(r["k"]): float(r["net"]) for r in rows
                   if r["k"] + r["nb"] <= len(truncated) - 1
                   and (r["k"] + r["nb"] < len(truncated) - 1
                        or r["why"] != "time")
                   and cut - 56 * DAY <= int(r["order_t"]) < cut}
            a = uni[tag]
            mask = ((a["t_order"] >= cut - 56 * DAY) & (a["t_order"] < cut)
                    & (a["t_out"] < cut))
            want = {int(k): float(v) for k, v in zip(a["sigk"][mask],
                                                     a["net"][mask])}
            checked += 1
            common = set(got) & set(want)
            if common:
                max_abs = max(max_abs, max(abs(got[k] - want[k]) for k in common))
            if set(got) != set(want) or any(abs(got[k] - want[k]) > 1e-9
                                             for k in common):
                mismatches += 1
                print("TRUNCATION_MISMATCH", datetime.fromtimestamp(
                    cut, timezone.utc).date(), tag, len(want), len(got),
                    len(set(want) ^ set(got)))
    print(f"truncation_cells_checked={checked} mismatches={mismatches} "
          f"max_common_net_diff={max_abs:.3e}")


def main() -> int:
    b1, uni, meta = minute.load_m1_universe()
    first, last = int(b1.t[0]), int(b1.t[-1] + 60)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    rows, info = audit.weekly_portfolio(b1, uni, meta, rankings, purged, 5, True)
    print("candidate", info)
    print("full", audit.metrics(rows))
    print("365d", audit.metrics(rows, last - 365 * DAY))
    print("90d", audit.metrics(rows, last - 90 * DAY))
    print("mtm_full", audit.mark_to_market(rows, b1))
    print("mtm_90d", audit.mark_to_market(
        [r for r in rows if r.t >= last - 90 * DAY], b1))
    long = []
    for r in rows:
        a = uni[r.label]
        j = np.flatnonzero(a["t_in"] == r.t)[0]
        long.append(a["direction"][j] > 0)
    print(f"direction_long_pct={100*np.mean(long):.2f}")
    valid.ranking_control(uni, meta, rankings)
    truncation(b1, uni, meta, rankings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
