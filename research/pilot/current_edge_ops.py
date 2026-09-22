"""Operational reports for the current-edge workflow.

Wednesday is for observation; weekend is for rule review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as ce
import current_edge_backtest as bt
import current_edge_lead_traces as lt


DAY = 86400
RISK_LEVELS = (0.02, 0.023, 0.03)
COST_NOTE = ("cost=live Standard spread 260 points at 3 decimals = 0.260 "
             "price units; commission 0.140 round turn; slippage 0.0165 "
             "per fill; long swap 0.5493/night")


def _as_outcomes(rows):
    return [ce.Outcome(r.t, r.net, r.stress, r.gross, r.direction) for r in rows]


def _current_ready(arms, now):
    ready = {}
    states = {}
    for key, rows in arms.items():
        state = lt._state(arms, key, now)
        states[key] = state
        health = ce.arm_health(_as_outcomes(rows), now)
        ok = bool(health["ready"])
        family, mode = key
        if mode == "FLIP":
            follow = arms[(family, "FOLLOW")]
            f60 = ce._window(_as_outcomes(follow), now, 60)["mean"]
            if f60 is None or f60 >= 0:
                ok = False
        if ok:
            ready[key] = float(health["score"])
    return ready, states


def _basket(arms, scores, now, lo_days, hi_days=0):
    lo = now - lo_days * DAY
    hi = now - hi_days * DAY
    bucket = []
    for (family, mode), score in scores.items():
        for r in arms[(family, mode)]:
            if lo <= r.t < hi:
                bucket.append(bt.Trade(r.t, r.exit_t, family, mode, score,
                                       r.net, r.stress, r.gross, r.direction))
    return bt._chosen_from_bucket(bucket)


def _fmt(x, digits=4):
    if x is None:
        return "-"
    return f"{x:+.{digits}f}"


def _line_metrics(label, trades):
    m = bt._metrics([t.net for t in trades])
    if not m:
        return f"{label}: no trades"
    return (f"{label}: trades={m['trades']} net_R={m['net_R']:+.4f} "
            f"mean_R={m['mean_R']:+.4f} win={m['win_pct']:.2f}% "
            f"pf={m['profit_factor']:.3f} max_dd_R={m['max_dd_R']:+.4f} "
            f"max_L={m['max_loss_streak']}")


def _risk_lines(metrics):
    out = []
    for risk in RISK_LEVELS:
        out.append(
            f"  risk={risk:.1%}: net={metrics['net_R'] * risk * 100:+.2f}% "
            f"mean/trade={metrics['mean_R'] * risk * 100:+.3f}% "
            f"max_dd={metrics['max_dd_R'] * risk * 100:+.2f}%")
    return out


def _by_family(trades, limit=8):
    groups = {}
    for t in trades:
        groups.setdefault((t.family, t.mode), []).append(t.net)
    rows = []
    for key, vals in groups.items():
        m = bt._metrics(vals)
        rows.append((m["net_R"], key, m))
    winners = [r for r in rows if r[0] > 0]
    losers = [r for r in rows if r[0] < 0]
    return sorted(winners, reverse=True)[:limit], sorted(losers)[:limit]


def _print_ready_table(ready, states, limit=12):
    print("\nREADY ARMS")
    rows = sorted(ready.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    for (family, mode), score in rows:
        s = states[(family, mode)]
        extra = ""
        if mode == "FLIP":
            extra = f" follow30={_fmt(s.follow_m30)} follow60={_fmt(s.follow_m60)}"
        print(f"- {family} [{mode}] score={score:+.4f} "
              f"m10={_fmt(s.m10)} m30={_fmt(s.m30)} m60={_fmt(s.m60)} "
              f"latest10={_fmt(s.latest10)}{extra}")


def _print_basket_summary(arms, ready, now):
    print("\nCURRENT READY BASKET")
    for days in (30, 60, 90):
        trades = _basket(arms, ready, now, days)
        print(_line_metrics(f"{days}d", trades))
        if days == 90 and trades:
            m = bt._metrics([t.net for t in trades])
            for line in _risk_lines(m):
                print(line)


def _print_period_drivers(arms, ready, now):
    periods = [
        ("0-30d", 30, 0),
        ("30-60d", 60, 30),
        ("60-90d", 90, 60),
    ]
    print("\nPERIOD DRIVERS")
    for label, lo, hi in periods:
        trades = _basket(arms, ready, now, lo, hi)
        print(_line_metrics(label, trades))
        winners, losers = _by_family(trades, limit=4)
        print("  contributors:")
        for _net, (family, mode), m in winners:
            print(f"    + {family} [{mode}] net_R={m['net_R']:+.4f} "
                  f"mean={m['mean_R']:+.4f} trades={m['trades']}")
        print("  detractors:")
        for _net, (family, mode), m in losers:
            print(f"    - {family} [{mode}] net_R={m['net_R']:+.4f} "
                  f"mean={m['mean_R']:+.4f} trades={m['trades']}")


def _lead_snapshot(arms, now):
    first_t = min(r.t for rows in arms.values() for r in rows)
    rows = []
    start = lt._next_weekend_anchor(first_t + 90 * DAY)
    for t in range(start, now - 30 * DAY, lt.WEEK):
        for key in arms:
            s = lt._state(arms, key, t)
            future = [r.net for r in lt._future_trades(arms, s, t, 30)]
            if len(future) >= 2:
                rows.append((s, float(np.mean(future))))
    checks = [
        ("current gate", lambda s: s.ready_current),
        ("fast recent-window", lambda s: s.ready_fast),
        ("accel recent>medium>long", lambda s: s.ready_accel),
        ("flip pressure", lambda s: s.ready_flip_pressure),
    ]
    print("\nLEAD TRACE CHECK")
    for name, fn in checks:
        vals = [v for s, v in rows if fn(s)]
        if not vals:
            print(f"- {name}: samples=0")
            continue
        hit = 100.0 * float(np.mean(np.asarray(vals) > 0))
        print(f"- {name}: samples={len(vals)} future30_mean={np.mean(vals):+.4f} "
              f"hit={hit:.2f}%")


def _wednesday():
    result = ce.scan(write=True)
    arms, now, source = lt._load_arms()
    ready, states = _current_ready(arms, now)
    print("WEDNESDAY OBSERVATION REPORT")
    print(f"generated={datetime.fromtimestamp(now, timezone.utc).isoformat()}")
    print(f"source={source}")
    print(COST_NOTE)
    print(f"decision={result['decision']} reason={result['reason']}")
    print(f"latest_m5={result['data']['latest_closed_m5_utc']} "
          f"age_min={result['data']['age_minutes']:.1f} "
          f"spread={result['data']['spread_now']}")
    print(f"ready_arms={len(ready)}")
    _print_ready_table(ready, states)
    _print_basket_summary(arms, ready, now)
    print("\nOBSERVE RULES")
    print("- Do not change rules on Wednesday unless data freshness, spread, or risk limits break.")
    print("- Watch whether crowded FLIP arms still carry the 0-30d basket.")
    print("- If max_L exceeds 9 or 90d DD exceeds -40% at 2.3% risk, flag weekend review.")


def _weekend():
    arms, now, source = lt._load_arms()
    ready, states = _current_ready(arms, now)
    print("WEEKEND REBUILD CHECKLIST")
    print(f"generated={datetime.fromtimestamp(now, timezone.utc).isoformat()}")
    print(f"source={source}")
    print(COST_NOTE)
    print(f"ready_arms={len(ready)}")
    _print_ready_table(ready, states)
    _print_basket_summary(arms, ready, now)
    _print_period_drivers(arms, ready, now)
    _lead_snapshot(arms, now)
    print("\nACTIONS TO REVIEW")
    print("- Keep post_news_chase FOLLOW as core only while 30d/60d remain positive.")
    print("- Treat breakout_into_level FLIP as tactical; inspect FOLLOW crowding before size-up.")
    print("- Cap late_extension FLIP unless it is positive in both recent and 30d windows.")
    print("- Cut or downsize families that are negative in 0-30d and also detractors by family.")
    print("- Recompute risk so 90d max DD maps to the 30%-40% target band.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Current-edge operational reports")
    ap.add_argument("--mode", choices=("wednesday", "weekend", "all"),
                    default="wednesday")
    args = ap.parse_args()
    if args.mode in ("wednesday", "all"):
        _wednesday()
    if args.mode == "all":
        print("\n" + "=" * 80 + "\n")
    if args.mode in ("weekend", "all"):
        _weekend()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
