"""Search for observable lead traces before current-edge arms start working."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as ce
import current_edge_backtest as bt


DAY = 86400


@dataclass
class ArmState:
    family: str
    mode: str
    score: float
    m10: float | None
    m20: float | None
    m30: float | None
    m60: float | None
    m90: float | None
    latest10: float | None
    stress: float | None
    n10: int
    n20: int
    n30: int
    n60: int
    n90: int
    follow_m30: float | None
    follow_m60: float | None
    ready_current: bool
    ready_fast: bool
    ready_accel: bool
    ready_flip_pressure: bool


def _window(rows, now, days):
    vals = [r.net for r in rows if now - days * DAY <= r.t < now]
    if not vals:
        return 0, None
    return len(vals), float(np.mean(vals))


def _load_arms():
    b5_all, _spec, now, source = ce.load_market()
    closed_idx = np.flatnonzero(b5_all.t + b5_all.step <= now)
    last_closed = int(closed_idx[-1])
    b5_closed = b5_all.slice(0, last_closed + 1)
    b15, _ = ce.D.to_15m(b5_closed)
    want = b15.t + 900
    pos = np.searchsorted(b5_all.t, want)
    nxt = np.where((pos < len(b5_all))
                   & (b5_all.t[np.minimum(pos, len(b5_all) - 1)] == want), pos, -1)
    atr = ce.core.atr(b15, 14)
    profile = ce.adaptive.hourly_spread_profile(b5_closed)
    events = ce.event_universe(b15, nxt, ce._load_news())
    arms = {}
    for family, ev in events.items():
        for mode, flip in (("FOLLOW", False), ("FLIP", True)):
            rows = bt._outcomes_with_exit(ev, flip, b15, b5_all, nxt, atr,
                                          profile, last_closed)
            for r in rows:
                r.family = family
                r.mode = mode
            arms[(family, mode)] = rows
    return arms, now, source


def _state(arms, key, now):
    family, mode = key
    rows = [r for r in arms[key] if r.t < now]
    outcomes = [ce.Outcome(r.t, r.net, r.stress, r.gross, r.direction) for r in rows]
    health = ce.arm_health(outcomes, now)
    score = health["score"]
    if score is None:
        score = -999.0
    n10, m10 = _window(rows, now, 10)
    n20, m20 = _window(rows, now, 20)
    n30, m30 = _window(rows, now, 30)
    n60, m60 = _window(rows, now, 60)
    n90, m90 = _window(rows, now, 90)
    latest10 = health["latest10_mean"]
    stress = health["stress_weighted_mean"]
    ready_current = bool(health["ready"])

    follow_m30 = follow_m60 = None
    if mode == "FLIP":
        follow_rows = [r for r in arms[(family, "FOLLOW")] if r.t < now]
        _n30, follow_m30 = _window(follow_rows, now, 30)
        _n60, follow_m60 = _window(follow_rows, now, 60)
        if follow_m60 is None or follow_m60 >= 0:
            ready_current = False

    ready_fast = (
        n10 >= 3 and n20 >= 5 and n30 >= 5
        and m10 is not None and m20 is not None and m30 is not None
        and latest10 is not None and stress is not None
        and m10 > 0 and m20 > 0 and m30 > 0
        and latest10 > 0 and stress > 0 and score > 0
    )
    ready_accel = (
        ready_fast and m60 is not None
        and m10 > m30 and m30 > m60
    )
    ready_flip_pressure = (
        ready_fast and mode == "FLIP"
        and follow_m30 is not None and follow_m60 is not None
        and follow_m30 < 0 and follow_m60 < 0
        and (m10 is not None and m30 is not None and m10 > m30)
    )
    return ArmState(family, mode, score, m10, m20, m30, m60, m90,
                    latest10, stress, n10, n20, n30, n60, n90,
                    follow_m30, follow_m60, ready_current, ready_fast,
                    ready_accel, ready_flip_pressure)


def _future_trades(arms, state, start, horizon_days):
    hi = start + horizon_days * DAY
    out = []
    for r in arms[(state.family, state.mode)]:
        if start <= r.t < hi:
            out.append(bt.Trade(r.t, r.exit_t, state.family, state.mode,
                                state.score, r.net, r.stress, r.gross,
                                r.direction))
    return out


def _select(states, policy):
    if policy == "current":
        xs = [s for s in states if s.ready_current]
        return sorted(xs, key=lambda s: s.score, reverse=True)[:10]
    if policy == "fast":
        xs = [s for s in states if s.ready_fast]
        return sorted(xs, key=lambda s: (s.m10 or -99, s.score), reverse=True)[:8]
    if policy == "accel":
        xs = [s for s in states if s.ready_accel]
        return sorted(xs, key=lambda s: ((s.m10 or 0) - (s.m60 or 0), s.score),
                      reverse=True)[:8]
    if policy == "flip_pressure":
        xs = [s for s in states if s.ready_flip_pressure]
        return sorted(xs, key=lambda s: (s.m10 or -99, s.score), reverse=True)[:6]
    raise ValueError(policy)


def _simulate(arms, now, step_days, horizon_days, policy):
    first_t = min(r.t for rows in arms.values() for r in rows)
    start = first_t + 90 * DAY
    stop = now - horizon_days * DAY
    all_trades = []
    picks = []
    t = start
    while t <= stop:
        states = [_state(arms, key, t) for key in arms]
        selected = _select(states, policy)
        picks.append(len(selected))
        bucket = []
        for s in selected:
            bucket.extend(_future_trades(arms, s, t, horizon_days))
        all_trades.extend(bt._chosen_from_bucket(bucket))
        t += step_days * DAY
    return all_trades, picks


def _fmt_metrics(trades):
    m = bt._metrics([t.net for t in trades])
    if not m:
        return "trades=0"
    return (f"trades={m['trades']} net_R={m['net_R']:.4f} "
            f"mean_R={m['mean_R']:.4f} win_pct={m['win_pct']:.2f} "
            f"pf={m['profit_factor']:.4f} max_dd_R={m['max_dd_R']:.4f} "
            f"max_L={m['max_loss_streak']}")


def _lead_table(arms, now):
    rows = []
    first_t = min(r.t for xs in arms.values() for r in xs)
    for t in range(first_t + 90 * DAY, now - 30 * DAY, 10 * DAY):
        for key in arms:
            s = _state(arms, key, t)
            future = [r.net for r in _future_trades(arms, s, t, 30)]
            if len(future) < 2:
                continue
            rows.append((s, float(np.mean(future)), len(future)))
    print("\n[lead_trace_30d_future_by_condition]")
    checks = [
        ("current", lambda s: s.ready_current),
        ("fast_10_20_30", lambda s: s.ready_fast),
        ("accel_10_gt_30_gt_60", lambda s: s.ready_accel),
        ("flip_pressure", lambda s: s.ready_flip_pressure),
        ("m10_positive_only", lambda s: s.n10 >= 3 and s.m10 is not None and s.m10 > 0),
        ("m10_gt_m60", lambda s: s.m10 is not None and s.m60 is not None and s.m10 > s.m60),
    ]
    for name, fn in checks:
        vals = [f for s, f, _n in rows if fn(s)]
        if not vals:
            print(f"{name} samples=0")
            continue
        print(f"{name} samples={len(vals)} future_mean_R={np.mean(vals):+.4f} "
              f"hit_pct={100.0 * np.mean(np.asarray(vals) > 0):.2f}")


def _last90_walk(arms, now):
    print("\n[last90_walk_forward]")
    start = now - 90 * DAY
    policies = ("current", "fast", "accel", "flip_pressure")
    horizons = (10, 20, 30)
    aggregate = {(p, h): [] for p in policies for h in horizons}
    pick_counts = {(p, h): [] for p in policies for h in horizons}
    trace_rows = []

    t = start
    while t <= now - 10 * DAY:
        label = ce.datetime.fromtimestamp(t, ce.timezone.utc).strftime("%Y-%m-%d")
        states = [_state(arms, key, t) for key in arms]
        print(f"\ncheckpoint={label}")
        for horizon in horizons:
            if t + horizon * DAY > now:
                continue
            best = None
            for policy in policies:
                selected = _select(states, policy)
                bucket = []
                for s in selected:
                    bucket.extend(_future_trades(arms, s, t, horizon))
                    future = [r.net for r in _future_trades(arms, s, t, horizon)]
                    if len(future) >= 2:
                        trace_rows.append((s, horizon, float(np.mean(future))))
                trades = bt._chosen_from_bucket(bucket)
                vals = [r.net for r in trades]
                aggregate[(policy, horizon)].extend(vals)
                pick_counts[(policy, horizon)].append(len(selected))
                if not vals:
                    mean = -999.0
                    net = 0.0
                    win = 0.0
                    n = 0
                else:
                    mean = float(np.mean(vals))
                    net = float(np.sum(vals))
                    win = 100.0 * float(np.mean(np.asarray(vals) > 0))
                    n = len(vals)
                row = (mean, net, win, n, policy)
                if best is None or row > best:
                    best = row
            if best is not None:
                mean, net, win, n, policy = best
                print(f"  next{horizon}d best_policy={policy} trades={n} "
                      f"net_R={net:+.4f} mean_R={mean:+.4f} win={win:.2f}%")
        t += 10 * DAY

    print("\n[last90_policy_aggregate]")
    for horizon in horizons:
        for policy in policies:
            vals = aggregate[(policy, horizon)]
            if not vals:
                continue
            m = bt._metrics(vals)
            avg_picks = float(np.mean(pick_counts[(policy, horizon)]))
            print(f"horizon={horizon}d policy={policy} avg_picks={avg_picks:.2f} "
                  f"trades={m['trades']} net_R={m['net_R']:+.4f} "
                  f"mean_R={m['mean_R']:+.4f} win={m['win_pct']:.2f}% "
                  f"pf={m['profit_factor']:.3f} max_dd_R={m['max_dd_R']:+.4f} "
                  f"max_L={m['max_loss_streak']}")

    print("\n[last90_lead_condition_future]")
    checks = [
        ("current", lambda s: s.ready_current),
        ("fast_10_20_30", lambda s: s.ready_fast),
        ("accel_10_gt_30_gt_60", lambda s: s.ready_accel),
        ("flip_pressure", lambda s: s.ready_flip_pressure),
        ("flip_follow_losing_30_60", lambda s: (
            s.mode == "FLIP"
            and s.follow_m30 is not None and s.follow_m60 is not None
            and s.follow_m30 < 0 and s.follow_m60 < 0)),
        ("m10_pos_m30_pos", lambda s: (
            s.m10 is not None and s.m30 is not None and s.m10 > 0 and s.m30 > 0)),
        ("m10_gt_m30_gt_m60", lambda s: (
            s.m10 is not None and s.m30 is not None and s.m60 is not None
            and s.m10 > s.m30 and s.m30 > s.m60)),
    ]
    for horizon in horizons:
        print(f"horizon={horizon}d")
        for name, fn in checks:
            vals = [v for s, h, v in trace_rows if h == horizon and fn(s)]
            if not vals:
                print(f"  {name}: samples=0")
                continue
            print(f"  {name}: samples={len(vals)} future_mean_R={np.mean(vals):+.4f} "
                  f"hit={100.0 * np.mean(np.asarray(vals) > 0):.2f}%")

    print("\n[last90_family_forward_mean]")
    fam_rows = {}
    for s, horizon, v in trace_rows:
        if horizon != 20:
            continue
        fam_rows.setdefault((s.family, s.mode), []).append(v)
    ranked = []
    for key, vals in fam_rows.items():
        if len(vals) >= 2:
            ranked.append((float(np.mean(vals)), len(vals), key))
    for mean, n, (family, mode) in sorted(ranked, reverse=True)[:12]:
        print(f"{family} [{mode}] samples={n} future20_mean_R={mean:+.4f}")


def run():
    arms, now, source = _load_arms()
    print(f"source={source}")
    print(f"arms={len(arms)}")
    _lead_table(arms, now)
    _last90_walk(arms, now)
    print("\n[rebalance_backtests]")
    for step in (10, 20, 30):
        for policy in ("current", "fast", "accel", "flip_pressure"):
            trades, picks = _simulate(arms, now, step, step, policy)
            avg_picks = float(np.mean(picks)) if picks else 0.0
            print(f"step={step}d policy={policy} avg_picks={avg_picks:.2f} "
                  f"{_fmt_metrics(trades)}")


if __name__ == "__main__":
    run()
