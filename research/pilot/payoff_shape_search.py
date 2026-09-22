"""Search payoff shapes that can pay the live XAUUSD cost model.

This is an operational design probe, not a promotion test.  It reuses the
Amendment 19 event universe, then varies stop size, target size and time stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as ce
import current_edge_backtest as bt


STOP_ATRS = (0.75, 1.0, 1.5, 2.0, 3.0)
TARGET_RS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)
TIME_STOPS = (12, 24, 48, 72, 144, 288)
DAY = 86400


@dataclass
class Variant:
    family: str
    mode: str
    stop_atr: float
    target_r: float
    time_bars: int


@dataclass
class Row:
    t: int
    exit_t: int
    net: float
    stress: float
    gross: float
    why: str


def _load_context():
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
    return b5_all, b15, nxt, atr, profile, events, last_closed, now, source


def _eval(events, flip, b15, b5, nxt, atr, profile, resolved_through,
          stop_atr, target_r, time_bars):
    out = []
    busy_until = -1
    for i, event_dir in events:
        if i < 0 or i >= len(nxt):
            continue
        k = int(nxt[i])
        if k < 0 or k <= busy_until:
            continue
        if k + time_bars > resolved_through + 1:
            continue
        a = float(atr[i])
        if not np.isfinite(a) or a <= 0:
            continue
        direction = -event_dir if flip else event_dir
        entry = float(b5.o[k])
        risk = stop_atr * a
        stop = entry - direction * risk
        target = entry + direction * target_r * risk
        px, why, bars = ce.core.resolve(b5, k, direction, entry, stop, target,
                                        time_bars)
        exit_k = min(k + bars, resolved_through)
        gross = direction * (float(px) - entry) / risk
        swap = (ce._nights(int(b5.t[k]), int(b5.t[exit_k])) * ce.SWAP_LONG
                if direction > 0 else 0.0)
        base_cost = ce._cost_abs(b5, k, profile, 1.0) + swap
        stress_cost = ce._cost_abs(b5, k, profile, ce.STRESS_MULT) + swap
        out.append(Row(int(b5.t[k]), int(b5.t[exit_k]),
                       gross - base_cost / risk,
                       gross - stress_cost / risk, gross, why))
        busy_until = exit_k
    return out


def _window(rows, now, days):
    return [r for r in rows if r.t >= now - days * DAY]


def _metrics(rows):
    vals = np.array([r.net for r in rows], dtype=float)
    if not len(vals):
        return None
    stress = np.array([r.stress for r in rows], dtype=float)
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    why = {k: 0 for k in ("target", "stop", "time")}
    for r in rows:
        why[r.why] = why.get(r.why, 0) + 1
    m = bt._metrics(vals)
    m.update({
        "stress_mean_R": float(stress.mean()),
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,
        "target_pct": 100.0 * why.get("target", 0) / len(rows),
        "stop_pct": 100.0 * why.get("stop", 0) / len(rows),
        "time_pct": 100.0 * why.get("time", 0) / len(rows),
        "p95_R": float(np.percentile(vals, 95)),
        "p05_R": float(np.percentile(vals, 5)),
    })
    return m


def _score(m30, m60, m90):
    if not (m30 and m60 and m90):
        return None
    if m90["trades"] < 20 or m30["trades"] < 5:
        return None
    if m30["mean_R"] <= 0 or m60["mean_R"] <= 0 or m90["mean_R"] <= 0:
        return None
    if m90["stress_mean_R"] <= 0:
        return None
    dd_penalty = abs(m90["max_dd_R"]) / max(m90["trades"], 1)
    return m30["mean_R"] + 0.5 * m60["mean_R"] + 0.25 * m90["mean_R"] - dd_penalty


def _kind(m):
    if m["win_pct"] < 45 and m["avg_win_R"] > 1.5:
        return "convex"
    if m["win_pct"] >= 55 and m["avg_win_R"] < 1.2:
        return "thin"
    return "balanced"


def run():
    b5, b15, nxt, atr, profile, events, last_closed, now, source = _load_context()
    print(f"source={source}")
    print("cost=live Standard spread 260 points at 3 decimals = 0.260 price units; "
          "commission 0.140 round turn; slippage 0.0165 per fill; long swap 0.5493/night")
    rows = []
    total = 0
    for family, ev in events.items():
        for mode, flip in (("FOLLOW", False), ("FLIP", True)):
            for stop_atr in STOP_ATRS:
                for target_r in TARGET_RS:
                    for time_bars in TIME_STOPS:
                        total += 1
                        outs = _eval(ev, flip, b15, b5, nxt, atr, profile,
                                     last_closed, stop_atr, target_r, time_bars)
                        m30 = _metrics(_window(outs, now, 30))
                        m60 = _metrics(_window(outs, now, 60))
                        m90 = _metrics(_window(outs, now, 90))
                        score = _score(m30, m60, m90)
                        if score is None:
                            continue
                        v = Variant(family, mode, stop_atr, target_r, time_bars)
                        rows.append((score, v, m30, m60, m90))
    print(f"searched={total} passed={len(rows)}")
    rows.sort(key=lambda x: x[0], reverse=True)
    for label, pred in (
        ("top_all", lambda _v, _m: True),
        ("thin", lambda _v, m: _kind(m) == "thin"),
        ("convex", lambda _v, m: _kind(m) == "convex"),
    ):
        print(f"\n[{label}]")
        shown = 0
        for score, v, m30, m60, m90 in rows:
            if not pred(v, m90):
                continue
            print(
                f"{v.family} [{v.mode}] stop={v.stop_atr:.2f}ATR "
                f"target={v.target_r:.2f}R time={v.time_bars}M5 "
                f"score={score:+.4f} kind={_kind(m90)} "
                f"E30={m30['mean_R']:+.4f}({m30['trades']}) "
                f"E60={m60['mean_R']:+.4f}({m60['trades']}) "
                f"E90={m90['mean_R']:+.4f}({m90['trades']}) "
                f"ret90@2.0={m90['net_R'] * 2.0:+.1f}% "
                f"dd90@2.0={m90['max_dd_R'] * 2.0:+.1f}% "
                f"win90={m90['win_pct']:.2f}% pf90={m90['profit_factor']:.3f} "
                f"dd90={m90['max_dd_R']:+.2f} maxL={m90['max_loss_streak']} "
                f"avgW={m90['avg_win_R']:+.2f} avgL={m90['avg_loss_R']:+.2f} "
                f"target%={m90['target_pct']:.1f} stop%={m90['stop_pct']:.1f} "
                f"time%={m90['time_pct']:.1f}")
            shown += 1
            if shown >= 12:
                break


if __name__ == "__main__":
    run()
