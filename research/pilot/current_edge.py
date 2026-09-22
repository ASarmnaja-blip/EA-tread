"""Tactical current-edge scanner specified by Amendment 19.

This module asks which pre-existing event/direction is healthy in the latest
market and whether it fires now.  It is intentionally descriptive rather than
confirmatory.  It reads quotes and bars, writes a JSON snapshot, and has no
broker execution capability.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import current_signal
import data as D
import inverse_search as IS


LOOKBACK_DAYS = 90
WINDOWS = (30, 60, 90)
HALF_LIFE_DAYS = 21.0
STOP_ATR = 1.5
TARGET_R = 1.0
TIME_STOP_M5 = 72
MIN_90 = 20
MIN_30 = 5
MIN_WEIGHTED_E = 0.05
SHRINK_SE = 0.5
STRESS_MULT = 1.5
STALE_MINUTES = 20
SPREAD_STANDARD = 0.260
COMMISSION_RAW_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_LONG = 0.5493
ROLLOVER_HOUR = 21
RAW_SPREAD_FALLBACK = 0.090
OUTPUT = Path("data/current_edge_signal.json")


@dataclass
class Outcome:
    t: int
    net: float
    stress: float
    gross: float
    direction: int


def _nights(t0: int, t1: int) -> int:
    """Number of 21:00 UTC rollover instants in [t0, t1]."""
    day0 = t0 - (t0 % 86400)
    cur = day0 + ROLLOVER_HOUR * 3600
    if cur < t0:
        cur += 86400
    n = 0
    while cur <= t1:
        n += 1
        cur += 86400
    return n


def _cost_abs(b5: D.Bars, k: int, profile: np.ndarray,
              stress: float = 1.0) -> float:
    hour = int((int(b5.t[k]) // 3600) % 24)
    standard = SPREAD_STANDARD * float(profile[hour])
    raw_spread = RAW_SPREAD_FALLBACK
    if b5.sp is not None and k < len(b5.sp):
        v = float(b5.sp[k])
        if np.isfinite(v) and v > 0:
            raw_spread = v
    raw = raw_spread + COMMISSION_RAW_RT
    execution = max(standard, raw) + 2.0 * SLIP_PER_FILL
    return stress * execution


def evaluate_arm(events: list[tuple[int, int]], flip: bool, b15: D.Bars,
                 b5: D.Bars, nxt: np.ndarray, atr: np.ndarray,
                 profile: np.ndarray, resolved_through: int) -> list[Outcome]:
    """Run one arm. FOLLOW and FLIP are both resolved, never algebraically negated."""
    out: list[Outcome] = []
    busy_until = -1
    for i, event_dir in events:
        if i < 0 or i >= len(nxt):
            continue
        k = int(nxt[i])
        if k < 0 or k <= busy_until:
            continue
        # A truncated path is unknown, not a short time-stop win or loss.
        if k + TIME_STOP_M5 > resolved_through + 1:
            continue
        a = float(atr[i])
        if not np.isfinite(a) or a <= 0:
            continue
        direction = -event_dir if flip else event_dir
        entry = float(b5.o[k])
        risk = STOP_ATR * a
        stop = entry - direction * risk
        target = entry + direction * TARGET_R * risk
        px, _why, bars = core.resolve(
            b5, k, direction, entry, stop, target, TIME_STOP_M5)
        exit_k = min(k + bars, resolved_through)
        gross = direction * (float(px) - entry) / risk
        swap = (_nights(int(b5.t[k]), int(b5.t[exit_k])) * SWAP_LONG
                if direction > 0 else 0.0)
        base_cost = _cost_abs(b5, k, profile, 1.0) + swap
        stress_cost = _cost_abs(b5, k, profile, STRESS_MULT) + swap
        out.append(Outcome(int(b5.t[k]), gross - base_cost / risk,
                           gross - stress_cost / risk, gross, direction))
        busy_until = exit_k
    return out


def _window(rows: list[Outcome], now: int, days: int) -> dict:
    vals = np.array([r.net for r in rows if r.t >= now - days * 86400], dtype=float)
    if not len(vals):
        return {"n": 0, "mean": None, "win_pct": None}
    return {"n": int(len(vals)), "mean": float(vals.mean()),
            "win_pct": 100.0 * float((vals > 0).mean())}


def arm_health(rows: list[Outcome], now: int) -> dict:
    recent = [r for r in rows if r.t >= now - LOOKBACK_DAYS * 86400]
    windows = {str(d): _window(recent, now, d) for d in WINDOWS}
    if not recent:
        return {"ready": False, "reasons": ["no completed trades in 90 days"],
                "windows": windows, "weighted_mean": None,
                "weighted_se": None, "score": None,
                "stress_weighted_mean": None, "latest10_mean": None}

    age_days = np.array([(now - r.t) / 86400.0 for r in recent], dtype=float)
    w = np.exp(-math.log(2.0) * age_days / HALF_LIFE_DAYS)
    x = np.array([r.net for r in recent], dtype=float)
    xs = np.array([r.stress for r in recent], dtype=float)
    wsum = float(w.sum())
    mean = float(np.dot(w, x) / wsum)
    stress_mean = float(np.dot(w, xs) / wsum)
    neff = float(wsum * wsum / np.dot(w, w))
    var = float(np.dot(w, (x - mean) ** 2) / wsum)
    se = math.sqrt(var / max(neff, 1.0))
    score = mean - SHRINK_SE * se
    latest10 = float(np.mean([r.net for r in recent[-10:]]))

    w30, w60, w90 = (windows[str(d)] for d in WINDOWS)
    reasons = []
    if w90["n"] < MIN_90:
        reasons.append(f"90d trades {w90['n']} < {MIN_90}")
    if w30["n"] < MIN_30:
        reasons.append(f"30d trades {w30['n']} < {MIN_30}")
    if w30["mean"] is None or w30["mean"] <= 0:
        reasons.append("30d net mean is not positive")
    if w60["mean"] is None or w60["mean"] <= 0:
        reasons.append("60d net mean is not positive")
    if mean < MIN_WEIGHTED_E:
        reasons.append(f"weighted mean {mean:+.4f} < {MIN_WEIGHTED_E:+.2f} R")
    if score <= 0:
        reasons.append(f"shrunken score {score:+.4f} is not positive")
    if stress_mean <= 0:
        reasons.append(f"1.5x-cost mean {stress_mean:+.4f} is not positive")
    if latest10 <= 0:
        reasons.append(f"latest-10 mean {latest10:+.4f} is not positive")
    return {"ready": not reasons, "reasons": reasons, "windows": windows,
            "weighted_mean": mean, "weighted_se": se, "effective_n": neff,
            "score": score, "stress_weighted_mean": stress_mean,
            "latest10_mean": latest10}


def _extend_one_bar(b: D.Bars) -> D.Bars:
    """Let inverse_search evaluate the last real bar; the dummy is never scored."""
    t = np.append(b.t, b.t[-1] + b.step)
    o = np.append(b.o, b.c[-1]); h = np.append(b.h, b.c[-1])
    l = np.append(b.l, b.c[-1]); c = np.append(b.c, b.c[-1])
    v = np.append(b.v, 0.0)
    return D.Bars(t, o, h, l, c, v, b.step, b.symbol)


def event_universe(b15: D.Bars, nxt: np.ndarray,
                   news_epochs: np.ndarray | None = None) -> dict[str, list[tuple[int, int]]]:
    ctx = core.Ctx(b15, nxt)
    events: dict[str, list[tuple[int, int]]] = {}
    for sid, label, fn in core.REGISTRY:
        events[f"core:{sid}:{label}"] = [(i, d) for i, d, *_ in fn(ctx)]
    ext = _extend_one_bar(b15)
    inv = IS.patterns(ext, core.atr(ext, IS.ATR_N), news_epochs)
    for name, rows in inv.items():
        events[f"crowded:{name}"] = [(i, d) for i, d in rows if i < len(b15)]
    return events


def _load_news() -> np.ndarray | None:
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        return np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)
    except Exception:
        return None


def load_market() -> tuple[D.Bars, dict | None, int, str]:
    live, spec, server = current_signal.fetch_live(bars=40000)
    if live is not None and spec is not None and len(live) > 1000:
        return live, spec, int(spec["server_time"]), f"MT5 live ({server})"

    b = D.load_csv("data/XAUUSD_M5.csv")
    meta = json.loads(Path("data/XAUUSD_M5.meta.json").read_text(encoding="utf-8"))
    now = int(datetime.fromisoformat(meta["exported_utc"]).timestamp())
    return b, None, now, "CSV fallback"


def scan(write: bool = True) -> dict:
    b5_all, spec, now, source = load_market()
    closed_idx = np.flatnonzero(b5_all.t + b5_all.step <= now)
    if not len(closed_idx):
        raise RuntimeError("no fully closed M5 bar")
    last_closed = int(closed_idx[-1])
    b5_closed = b5_all.slice(0, last_closed + 1)
    b15, _ = D.to_15m(b5_closed)
    if len(b15) < 500:
        raise RuntimeError("insufficient M15 history")

    # Historical and live entry maps point into the all-bars series.  Historical
    # trades are separately bounded by last_closed, so the open bar cannot leak
    # into their outcomes.
    want = b15.t + 900
    pos = np.searchsorted(b5_all.t, want)
    nxt = np.where((pos < len(b5_all))
                   & (b5_all.t[np.minimum(pos, len(b5_all) - 1)] == want), pos, -1)
    atr = core.atr(b15, 14)
    profile = adaptive.hourly_spread_profile(b5_closed)
    events = event_universe(b15, nxt, _load_news())

    arms: dict[str, dict] = {}
    for family, ev in events.items():
        for mode, flip in (("FOLLOW", False), ("FLIP", True)):
            rows = evaluate_arm(ev, flip, b15, b5_all, nxt, atr, profile, last_closed)
            health = arm_health(rows, now)
            arms[f"{family}|{mode}"] = {
                "family": family, "mode": mode, "event_count": len(ev),
                "completed_90d": health["windows"]["90"]["n"], **health,
            }

    # A flipped loser must have a currently negative source direction.
    for a in arms.values():
        if a["mode"] != "FLIP":
            continue
        follow = arms[f"{a['family']}|FOLLOW"]
        f60 = follow["windows"]["60"]["mean"]
        a["follow_source_60_mean"] = f60
        if f60 is None or f60 >= 0:
            a["ready"] = False
            a["reasons"] = list(a["reasons"]) + [
                "FOLLOW source is not a 60d loser, so FLIP is not a flipped loser"]

    ready = sorted((a for a in arms.values() if a["ready"]),
                   key=lambda a: a["score"], reverse=True)
    latest_i = len(b15) - 1
    firing = []
    for a in ready:
        dirs = [d for i, d in events[a["family"]] if i == latest_i]
        if dirs:
            firing.append((a, -dirs[-1] if a["mode"] == "FLIP" else dirs[-1]))

    last_close_time = int(b5_closed.t[-1] + b5_closed.step)
    age_min = (now - last_close_time) / 60.0
    result = {
        "generated_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "source": source, "symbol": "XAUUSD", "decision": "NO_TRADE",
        "reason": "", "data": {
            "latest_closed_m5_utc": datetime.fromtimestamp(
                last_close_time, timezone.utc).isoformat(),
            "latest_closed_m15_open_utc": datetime.fromtimestamp(
                int(b15.t[-1]), timezone.utc).isoformat(),
            "age_minutes": age_min, "m5_bars": len(b5_closed),
            "m15_bars": len(b15), "spread_now": spec.get("spread_now") if spec else None,
        },
        "policy": {
            "lookback_days": LOOKBACK_DAYS, "half_life_days": HALF_LIFE_DAYS,
            "geometry": "1.5 ATR stop, 1:1 target, 72 M5 time stop",
            "arms": len(arms), "ready_arms": len(ready),
        },
        "signal": None,
        "watchlist": ready[:10],
        "all_arms": arms,
    }

    if age_min > STALE_MINUTES:
        result["reason"] = (f"stale data: newest closed M5 bar is {age_min:.1f} minutes old")
    elif not ready:
        result["reason"] = "no arm passes all current-health and cost gates"
    elif not firing:
        result["reason"] = (f"{len(ready)} arm(s) are READY, but none fires on the latest "
                            "closed M15 bar")
    else:
        arm, direction = max(firing, key=lambda z: z[0]["score"])
        k = int(nxt[latest_i])
        if k < 0:
            result["reason"] = "latest event has no next M5 entry bar"
        else:
            hour = int((int(b5_all.t[k]) // 3600) % 24)
            model_spread = SPREAD_STANDARD * float(profile[hour])
            spread_now = float(spec["spread_now"]) if spec else None
            if spread_now is None:
                result["reason"] = "current spread unavailable"
            elif spread_now > 2.0 * model_spread:
                result["reason"] = (f"current spread {spread_now:.4f} exceeds 2x model "
                                    f"spread {model_spread:.4f}")
            else:
                entry = float(spec["ask"] if direction > 0 else spec["bid"])
                risk = STOP_ATR * float(atr[latest_i])
                signal = {
                    "direction": "LONG" if direction > 0 else "SHORT",
                    "family": arm["family"], "mode": arm["mode"],
                    "entry": entry, "stop": entry - direction * risk,
                    "target": entry + direction * risk,
                    "invalidation": f"price reaches {entry - direction * risk:.3f}",
                    "expiry_utc": datetime.fromtimestamp(
                        int(b5_all.t[k]) + TIME_STOP_M5 * 300, timezone.utc).isoformat(),
                    "spread_now": spread_now, "model_spread": model_spread,
                    "health": arm,
                }
                result.update(decision=signal["direction"], reason="READY arm fires now",
                              signal=signal)

    if write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _fmt(v) -> str:
    return "-" if v is None else (f"{v:+.4f}" if isinstance(v, float) else str(v))


def main() -> int:
    ap = argparse.ArgumentParser(description="Amendment 19 current edge scanner")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    r = scan(write=not args.no_write)
    print("=" * 100)
    print("CURRENT EDGE — FOLLOW WINNERS + FLIPPED LOSERS")
    print("=" * 100)
    print(f"data      : {r['source']}")
    print(f"closed M5 : {r['data']['latest_closed_m5_utc']} "
          f"(age {r['data']['age_minutes']:.1f} min)")
    print(f"universe  : {r['policy']['arms']} arms; READY {r['policy']['ready_arms']}")
    print(f"decision  : {r['decision']}")
    print(f"reason    : {r['reason']}")
    if r["signal"]:
        s = r["signal"]
        print(f"setup     : {s['family']} [{s['mode']}]")
        print(f"entry     : {s['entry']:.3f}")
        print(f"stop      : {s['stop']:.3f}")
        print(f"target    : {s['target']:.3f}")
        print(f"expiry    : {s['expiry_utc']}")
    print("\nREADY WATCHLIST")
    if not r["watchlist"]:
        print("  none")
    for i, a in enumerate(r["watchlist"], 1):
        w = a["windows"]
        print(f"  {i:2d}. {a['family']} [{a['mode']}] score {_fmt(a['score'])}  "
              f"E30 {_fmt(w['30']['mean'])} ({w['30']['n']})  "
              f"E60 {_fmt(w['60']['mean'])} ({w['60']['n']})  "
              f"E90 {_fmt(w['90']['mean'])} ({w['90']['n']})  "
              f"stress {_fmt(a['stress_weighted_mean'])}"
              + (f"  source60 {_fmt(a.get('follow_source_60_mean'))}"
                 if a["mode"] == "FLIP" else ""))
    if not args.no_write:
        print(f"\nsnapshot  : {OUTPUT}")
    print("read-only scanner; no broker execution capability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
