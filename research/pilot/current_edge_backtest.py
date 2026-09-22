"""Walk-forward portfolio backtest for the Amendment 19 current-edge policy."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as ce


@dataclass
class Trade:
    t: int
    exit_t: int
    family: str
    mode: str
    score: float
    net: float
    stress: float
    gross: float
    direction: int


def _outcomes_with_exit(events, flip, b15, b5, nxt, atr, profile, resolved_through):
    out = []
    busy_until = -1
    for i, event_dir in events:
        if i < 0 or i >= len(nxt):
            continue
        k = int(nxt[i])
        if k < 0 or k <= busy_until:
            continue
        if k + ce.TIME_STOP_M5 > resolved_through + 1:
            continue
        a = float(atr[i])
        if not np.isfinite(a) or a <= 0:
            continue
        direction = -event_dir if flip else event_dir
        entry = float(b5.o[k])
        risk = ce.STOP_ATR * a
        stop = entry - direction * risk
        target = entry + direction * ce.TARGET_R * risk
        px, _why, bars = ce.core.resolve(
            b5, k, direction, entry, stop, target, ce.TIME_STOP_M5)
        exit_k = min(k + bars, resolved_through)
        gross = direction * (float(px) - entry) / risk
        swap = (ce._nights(int(b5.t[k]), int(b5.t[exit_k])) * ce.SWAP_LONG
                if direction > 0 else 0.0)
        base_cost = ce._cost_abs(b5, k, profile, 1.0) + swap
        stress_cost = ce._cost_abs(b5, k, profile, ce.STRESS_MULT) + swap
        out.append(Trade(
            int(b5.t[k]), int(b5.t[exit_k]), "", "",
            0.0, gross - base_cost / risk, gross - stress_cost / risk,
            gross, direction))
        busy_until = exit_k
    return out


def _arm_health_prior(rows, now):
    prior = [ce.Outcome(r.t, r.net, r.stress, r.gross, r.direction)
             for r in rows if r.t < now]
    return ce.arm_health(prior, now)


def _max_drawdown(xs):
    eq = np.cumsum(np.asarray(xs, dtype=float))
    if not len(eq):
        return 0.0
    peak = np.maximum.accumulate(np.r_[0.0, eq[:-1]])
    dd = eq - peak
    return float(dd.min())


def _streaks(xs):
    max_l = max_w = cur_l = cur_w = 0
    for x in xs:
        if x > 0:
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_l = max(max_l, cur_l)
        max_w = max(max_w, cur_w)
    return max_l, max_w


def _profit_factor(xs):
    wins = sum(x for x in xs if x > 0)
    losses = -sum(x for x in xs if x <= 0)
    return math.inf if losses == 0 else wins / losses


def _metrics(xs):
    vals = np.asarray(xs, dtype=float)
    if not len(vals):
        return {}
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    max_l, max_w = _streaks(vals)
    return {
        "trades": int(len(vals)),
        "net_R": float(vals.sum()),
        "mean_R": float(vals.mean()),
        "median_R": float(np.median(vals)),
        "win_pct": 100.0 * float((vals > 0).mean()),
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(_profit_factor(vals)),
        "max_dd_R": _max_drawdown(vals),
        "max_loss_streak": int(max_l),
        "max_win_streak": int(max_w),
    }


def _print_metrics(name, vals):
    m = _metrics(vals)
    print(f"\n[{name}]")
    for k, v in m.items():
        print(f"{k}={v}")
    return m


def _print_sizing(m):
    print("[position_sizing]")
    for risk in (0.03, 0.04):
        print(f"risk={risk:.0%} net_pct={m['net_R']*risk*100:.2f} "
              f"mean_pct_per_trade={m['mean_R']*risk*100:.3f} "
              f"max_dd_pct={m['max_dd_R']*risk*100:.2f}")


def _chosen_from_bucket(bucket):
    chosen = []
    busy_until = -1
    by_t = {}
    for r in bucket:
        by_t.setdefault(r.t, []).append(r)
    for t in sorted(by_t):
        if t <= busy_until:
            continue
        r = max(by_t[t], key=lambda x: x.score)
        chosen.append(r)
        busy_until = r.exit_t
    return chosen


def _group_report(trades, key_fn, limit=20):
    grouped = {}
    for t in trades:
        grouped.setdefault(key_fn(t), []).append(t.net)
    rows = []
    for key, xs in grouped.items():
        m = _metrics(xs)
        rows.append((m["net_R"], key, m))
    for _net, key, m in sorted(rows, reverse=True)[:limit]:
        print(f"{key} trades={m['trades']} net_R={m['net_R']:.4f} "
              f"mean_R={m['mean_R']:.4f} win_pct={m['win_pct']:.2f} "
              f"max_dd_R={m['max_dd_R']:.4f} max_L={m['max_loss_streak']}")


def run():
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
            rows = _outcomes_with_exit(ev, flip, b15, b5_all, nxt, atr,
                                       profile, last_closed)
            for r in rows:
                r.family = family
                r.mode = mode
            arms[(family, mode)] = rows

    candidates_by_time = {}
    for (family, mode), rows in arms.items():
        for r in rows:
            h = _arm_health_prior(rows, r.t)
            ready = h["ready"]
            if mode == "FLIP":
                follow_rows = arms[(family, "FOLLOW")]
                f60 = ce._window(
                    [ce.Outcome(x.t, x.net, x.stress, x.gross, x.direction)
                     for x in follow_rows if x.t < r.t],
                    r.t, 60)["mean"]
                if f60 is None or f60 >= 0:
                    ready = False
            if not ready:
                continue
            rr = Trade(r.t, r.exit_t, family, mode, float(h["score"]),
                       r.net, r.stress, r.gross, r.direction)
            candidates_by_time.setdefault(r.t, []).append(rr)

    trades = []
    busy_until = -1
    for t in sorted(candidates_by_time):
        if t <= busy_until:
            continue
        chosen = max(candidates_by_time[t], key=lambda r: r.score)
        trades.append(chosen)
        busy_until = chosen.exit_t

    vals = [t.net for t in trades]
    stress_vals = [t.stress for t in trades]
    print(f"source={source}")
    print(f"m5_bars={len(b5_closed)} m15_bars={len(b15)}")
    if trades:
        print(f"first_trade={ce.datetime.fromtimestamp(trades[0].t, ce.timezone.utc).isoformat()}")
        print(f"last_trade={ce.datetime.fromtimestamp(trades[-1].t, ce.timezone.utc).isoformat()}")
    base_m = _print_metrics("walk_forward_base", vals)
    _print_metrics("walk_forward_stress_1.5x_cost", stress_vals)
    _print_sizing(base_m)
    print("\n[top_families]")
    by_family = {}
    for t in trades:
        by_family.setdefault((t.family, t.mode), []).append(t.net)
    ranked = sorted(by_family.items(), key=lambda kv: sum(kv[1]), reverse=True)
    for (family, mode), xs in ranked[:10]:
        m = _metrics(xs)
        print(f"{family} [{mode}] trades={m['trades']} net_R={m['net_R']:.4f} "
              f"mean_R={m['mean_R']:.4f} win_pct={m['win_pct']:.2f} "
              f"max_L={m['max_loss_streak']}")

    ready_now = {}
    for key, rows in arms.items():
        h = ce.arm_health(
            [ce.Outcome(r.t, r.net, r.stress, r.gross, r.direction) for r in rows],
            now)
        ready = h["ready"]
        family, mode = key
        if mode == "FLIP":
            follow = arms[(family, "FOLLOW")]
            f60 = ce._window(
                [ce.Outcome(x.t, x.net, x.stress, x.gross, x.direction)
                 for x in follow], now, 60)["mean"]
            if f60 is None or f60 >= 0:
                ready = False
        if ready:
            ready_now[key] = h["score"]

    print("\n[current_ready_basket]")
    print(f"arms={len(ready_now)}")
    period_trades = {}
    for days in (30, 60, 90):
        lo = now - days * 86400
        bucket = []
        for (family, mode), score in ready_now.items():
            for r in arms[(family, mode)]:
                if r.t >= lo:
                    bucket.append(Trade(r.t, r.exit_t, family, mode, score,
                                        r.net, r.stress, r.gross, r.direction))
        chosen = _chosen_from_bucket(bucket)
        period_trades[days] = chosen
        m = _metrics([r.net for r in chosen])
        print(f"days={days} trades={m['trades']} net_R={m['net_R']:.4f} "
              f"mean_R={m['mean_R']:.4f} win_pct={m['win_pct']:.2f} "
              f"pf={m['profit_factor']:.4f} max_dd_R={m['max_dd_R']:.4f} "
              f"max_L={m['max_loss_streak']}")
        for risk in (0.03, 0.04):
            print(f"  risk={risk:.0%} net_pct={m['net_R']*risk*100:.2f} "
                  f"mean_pct={m['mean_R']*risk*100:.3f} "
                  f"max_dd_pct={m['max_dd_R']*risk*100:.2f}")

    print("\n[current_ready_by_discrete_period]")
    periods = [
        ("0-30d", now - 30 * 86400, now),
        ("30-60d", now - 60 * 86400, now - 30 * 86400),
        ("60-90d", now - 90 * 86400, now - 60 * 86400),
    ]
    for label, lo, hi in periods:
        bucket = []
        for (family, mode), score in ready_now.items():
            for r in arms[(family, mode)]:
                if lo <= r.t < hi:
                    bucket.append(Trade(r.t, r.exit_t, family, mode, score,
                                        r.net, r.stress, r.gross, r.direction))
        chosen = _chosen_from_bucket(bucket)
        m = _metrics([r.net for r in chosen])
        print(f"\n[{label}] trades={m['trades']} net_R={m['net_R']:.4f} "
              f"mean_R={m['mean_R']:.4f} win_pct={m['win_pct']:.2f} "
              f"pf={m['profit_factor']:.4f} max_dd_R={m['max_dd_R']:.4f} "
              f"max_L={m['max_loss_streak']}")
        print("by_mode")
        _group_report(chosen, lambda t: t.mode, limit=5)
        print("by_family")
        _group_report(chosen, lambda t: f"{t.family} [{t.mode}]", limit=20)


if __name__ == "__main__":
    run()
