"""Independent diagnostics for the K=5 diverse weekly candidate.

Checks what the fifth sleeve actually is, reports each setup separately, and
rebuilds sampled selected cells from data truncated at the historical cutoff.
No broker API or order code is imported or called.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import evolution_portfolio_audit as audit
import mtf_engine as E
import walk_forward as wf


DAY = 86400


def choose_five(ranked: list[str], meta: dict) -> list[str]:
    chosen = []
    seen = set()
    for tag in ranked:
        setup = meta[tag]["setup"]
        if setup in seen:
            continue
        seen.add(setup)
        chosen.append(tag)
        if len(chosen) == 5:
            break
    return chosen


def rebuild_cell(b5, tag: str, meta: dict):
    m = meta[tag]
    mult = dict(E.TIMEFRAMES)[m["tf"]]
    bs, nxt = E.resample(b5, mult)
    atr = core.atr(bs, E.ATR_N)
    sig = E.setup_signals(m["setup"], core.Ctx(bs, nxt))
    return E.run_cell(bs, nxt, atr, sig, b5, m["stop"], m["target"],
                      (m["off"], m["exp"]), mult)["rows"]


def truncation_audit(b5, uni: dict, meta: dict, rankings: list[tuple]) -> None:
    picks = np.linspace(0, len(rankings) - 1, 12, dtype=int)
    checked = mismatches = 0
    max_abs = 0.0
    for p in picks:
        cut, _end, ranked = rankings[int(p)]
        stop = int(np.searchsorted(b5.t, cut, side="left"))
        truncated = b5.slice(0, stop)
        for tag in choose_five(ranked, meta):
            rows = rebuild_cell(truncated, tag, meta)
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


def ranking_control(uni: dict, meta: dict, rankings: list[tuple]) -> None:
    top_week = []
    middle_week = []
    for cut, end, ranked in rankings:
        top_vals = []
        mid_vals = []
        for tag in choose_five(ranked, meta):
            family = meta[tag]["setup"]
            same = [x for x in ranked if meta[x]["setup"] == family]
            middle = same[len(same) // 2]
            for dest, cell in ((top_vals, tag), (mid_vals, middle)):
                a = uni[cell]
                mask = ((a["t_order"] >= cut) & (a["t_order"] < end)
                        & (a["t_in"] < end))
                dest.append(float(np.mean(a["net"][mask])) if mask.any() else 0.0)
        top_week.append(float(np.mean(top_vals)) if top_vals else 0.0)
        middle_week.append(float(np.mean(mid_vals)) if mid_vals else 0.0)
    diff = np.asarray(top_week) - np.asarray(middle_week)
    obs, p, _null = wf.block_flip_p(diff, block=8, draws=10_000,
                                     seed=20260922, one_sided=True)
    print(f"ranking_control_weeks={len(diff)} top_mean={np.mean(top_week):+.5f}R "
          f"family_middle_mean={np.mean(middle_week):+.5f}R "
          f"difference={obs:+.5f}R positive_weeks={100*np.mean(diff > 0):.1f}% "
          f"block8_one_sided_p={p:.4f}")


def main() -> int:
    b5 = audit.hist.load_history()
    first, last = int(b5.t[0]), int(b5.t[-1] + b5.step)
    uni, meta = audit.load_universe(b5)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    rows, info = audit.weekly_portfolio(b5, uni, meta, rankings, purged, 5, True)
    print("candidate", info)

    selected = Counter()
    rank_slot = Counter()
    param = Counter()
    for _cut, _end, ranked in rankings:
        for slot, tag in enumerate(choose_five(ranked, meta), 1):
            m = meta[tag]
            selected[m["setup"]] += 1
            rank_slot[(slot, m["setup"])] += 1
            param[(m["setup"], m["tf"], m["stop"], m["target"],
                   m["off"], m["exp"])] += 1
    print("selected_weeks_by_setup", dict(selected))
    print("fifth_slot_setup", {s: n for (slot, s), n in rank_slot.items()
                               if slot == 5})
    print("top_parameters")
    for key, n in param.most_common(20):
        print(n, key)

    by_setup = defaultdict(list)
    for row in rows:
        by_setup[meta[row.label]["setup"]].append(row)
    for setup, z in sorted(by_setup.items()):
        print("setup", setup, audit.metrics(z))
    print("portfolio", audit.metrics(rows))
    last = int(b5.t[-1] + 300)
    print("portfolio_mtm_full", audit.mark_to_market(rows, b5))
    print("portfolio_mtm_365d", audit.mark_to_market(
        [r for r in rows if r.t >= last - 365 * DAY], b5))
    print("portfolio_mtm_90d", audit.mark_to_market(
        [r for r in rows if r.t >= last - 90 * DAY], b5))
    print(f"direction_long_pct={100*np.mean([uni[r.label]['direction'][np.where(uni[r.label]['t_in'] == r.t)[0][0]] > 0 for r in rows]):.2f}")
    ranking_control(uni, meta, rankings)
    truncation_audit(b5, uni, meta, rankings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
