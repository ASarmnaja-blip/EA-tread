"""Seven-day evolutionary replay across the existing 8,250-cell grid.

At each weekly boundary the selector sees only completed outcomes from the
previous 56 calendar days.  It may change signal timeframe, setup, stop, target,
and entry/expiry mode.  The selected cell is then measured over the next seven
days.  This is deliberately a *baseline*: external context is logged separately
and must beat this procedure in a later, like-for-like replay before it is
allowed to influence selection.

The file never sends MT5 orders.  It starts from the first continuous broker
history supplied by MT5 (early 2021), not merely the local CSV boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge_backtest as bt
import historical_regime_walkforward as hist
import walk_forward as wf


DAY = 86400
SELECT_DAYS = 56
FORWARD_DAYS = 7
MIN_TRADES = 20
MIN_DAYS = 8
SHRINK_SE = 0.75


def _week_boundary(t: int) -> int:
    """Saturday 05:15 Bangkok is represented by the prior Friday 22:15 UTC.

    Boundaries are calendar points, not bar indices; data absent during the
    weekend cannot accidentally become a tradable synthetic bar.
    """
    d = datetime.fromtimestamp(t, timezone.utc)
    # Friday 22:15 UTC in the week containing d. Monday is zero.
    midnight = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
    return midnight + ((4 - d.weekday()) % 7) * DAY + 22 * 3600 + 15 * 60


def _score_universe(uni: dict, lo: int, cut: int) -> tuple[dict, dict, int]:
    """Lower-confidence-bound score using only outcomes resolved before cut."""
    out, signature, purged = {}, {}, 0
    for tag, a in uni.items():
        entered = (a["t_order"] >= lo) & (a["t_order"] < cut)
        complete = entered & (a["t_out"] < cut)
        purged += int(entered.sum() - complete.sum())
        x = a["net"][complete]
        if len(x) < MIN_TRADES or len(np.unique(a["t_order"][complete] // DAY)) < MIN_DAYS:
            continue
        score = float(x.mean() - SHRINK_SE * x.std(ddof=1) / np.sqrt(len(x)))
        out[tag] = score
        # Parameterisations that acted on the same entries get one seat in the
        # weekly ranking.  Otherwise a setup with many barrier variants receives
        # more lottery tickets than a genuinely distinct setup.
        # Keep the bytes themselves: Python's salted hash is process-specific
        # and, while collisions are unlikely, a collision must not silently
        # delete a genuinely distinct strategy from the ranking.
        signature[tag] = a["sigk"][complete].tobytes()
    return out, signature, purged


def _unique_ranking(scores: dict, signature: dict) -> tuple[list[str], int]:
    seen, ranked = set(), []
    for tag in sorted(scores, key=lambda x: (-scores[x], x)):
        sig = signature[tag]
        if sig in seen:
            continue
        seen.add(sig)
        ranked.append(tag)
    return ranked, len(scores) - len(ranked)


def _forward(a: dict, cut: int, end: int) -> list[float]:
    # Pending orders are cancelled at the next weekly rebuild.  A newly chosen
    # tool cannot inherit an order created by the previous week's policy.
    m = ((a["t_order"] >= cut) & (a["t_order"] < end)
         & (a["t_in"] < end))
    return a["net"][m].tolist()


def run() -> int:
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    first = int(b5.t[0])
    print(f"data={datetime.fromtimestamp(first, timezone.utc):%Y-%m-%d}.."
          f"{datetime.fromtimestamp(last, timezone.utc):%Y-%m-%d} bars={len(b5):,}")
    print(f"weekly_rebuild=7d selection={SELECT_DAYS}d min={MIN_TRADES} trades/"
          f"{MIN_DAYS} active days score=mean-{SHRINK_SE:g}*SE")
    print("cost=Demo raw 90-point floor + 0.140 commission + 0.033 slippage; "
          "each candidate uses its own declared stop/target/entry geometry")

    print("building fixed 8,250-cell universe once...")
    uni, meta = wf.build_universe(b5, last)
    print(f"eligible_cells={len(uni):,} declared_cells={len(meta):,}")
    if not uni:
        return 1

    cut = _week_boundary(first)
    if cut <= first + SELECT_DAYS * DAY:
        cut += 7 * DAY
    while cut < first + SELECT_DAYS * DAY:
        cut += 7 * DAY

    active = None
    transitions, all_net, top_week, mid_week = [], [], [], []
    rolls = idle = purged_total = collapsed_total = 0
    while cut < last:
        end = min(cut + FORWARD_DAYS * DAY, last)
        scores, signature, purged = _score_universe(uni, cut - SELECT_DAYS * DAY, cut)
        purged_total += purged
        rolls += 1
        ranked, collapsed = _unique_ranking(scores, signature)
        collapsed_total += collapsed
        if not ranked:
            idle += 1
            if active is not None:
                transitions.append((cut, active, "NO_TOOL", "no cell passed gate"))
            active = None
            cut += 7 * DAY
            continue
        chosen = ranked[0]
        middle = ranked[len(ranked) // 2]
        if chosen != active:
            transitions.append((cut, active or "NO_TOOL", chosen,
                                f"LCB score {scores[chosen]:+.4f}R"))
            active = chosen
        chosen_vals = _forward(uni[chosen], cut, end)
        middle_vals = _forward(uni[middle], cut, end)
        all_net.extend(chosen_vals)
        # Zero is a policy return when a selected tool does not fire that week.
        top_week.append(float(np.mean(chosen_vals)) if chosen_vals else 0.0)
        mid_week.append(float(np.mean(middle_vals)) if middle_vals else 0.0)
        cut += 7 * DAY

    print(f"rolls={rolls} idle={idle} selection_trade_outcomes_purged={purged_total:,} "
          f"duplicate_signatures_collapsed={collapsed_total:,}")
    print(f"transitions={len(transitions)}")
    for t, old, new, why in transitions:
        dt = datetime.fromtimestamp(t, timezone.utc)
        print(f"{dt:%Y-%m-%d} {old} -> {new} ({why})")
    m = bt._metrics(all_net)
    if not m:
        print("forward=NO_TRADES")
        return 0
    print("\n[weekly selected-cell forward results]")
    print(f"trades={m['trades']} net={m['net_R']:+.3f}R mean={m['mean_R']:+.4f}R "
          f"win={m['win_pct']:.1f}% PF={m['profit_factor']:.3f} "
          f"DD={m['max_dd_R']:+.3f}R max_loss_streak={m['max_loss_streak']}")
    d = np.asarray(top_week) - np.asarray(mid_week)
    print("[same-week ranking control]")
    print(f"top_weekly_mean={np.mean(top_week):+.4f}R "
          f"mid_weekly_mean={np.mean(mid_week):+.4f}R "
          f"top_minus_mid={np.mean(d):+.4f}R "
          f"positive_weeks={100*np.mean(d > 0):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
