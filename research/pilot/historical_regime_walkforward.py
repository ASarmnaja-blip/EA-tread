"""Annual expanding walk-forward of the fixed Amendment-19 tool universe.

The broker supplies continuous XAUUSD M5 history from early 2021.  At each
January anchor this script scores the 48 pre-existing FOLLOW/FLIP arms using
only the history available before that anchor, then runs that one selected arm
through the following calendar year.  It never changes an arm's signal, stop,
target, or holding period after selection.

This answers a historical-regime question.  It is not a search for a new live
candidate and does not modify the Demo autotrader.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import current_edge as ce
import current_edge_backtest as bt
import data as D


SYMBOL = "XAUUSD"
START_YEAR = 2021
FIRST_ANCHOR_YEAR = 2022
RAW_SPREAD_FLOOR = 0.090       # active Demo account: 90 points at 3 decimals


def _epoch(year: int) -> int:
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())


def _fetch_pre_csv(csv_start: int) -> D.Bars:
    """Read 2021..the CSV boundary in annual MT5 requests.

    MT5 returns old M5 history reliably in year-sized requests but can truncate
    a large multi-year request at the terminal's max-bars setting.
    """
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        info = mt5.symbol_info(SYMBOL)
        if info is None:
            raise RuntimeError(f"MT5 symbol unavailable: {SYMBOL}")
        chunks = []
        for year in range(START_YEAR, datetime.fromtimestamp(csv_start, timezone.utc).year + 1):
            a = datetime(year, 1, 1, tzinfo=timezone.utc)
            b = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, a, b)
            if rates is not None and len(rates):
                keep = rates["time"] < csv_start
                if np.any(keep):
                    chunks.append(rates[keep])
        if not chunks:
            raise RuntimeError("MT5 returned no pre-CSV M5 history")
        r = np.concatenate(chunks)
        order = np.argsort(r["time"])
        r = r[order]
        uniq = np.r_[True, r["time"][1:] != r["time"][:-1]]
        r = r[uniq]
        return D.Bars(r["time"], r["open"], r["high"], r["low"], r["close"],
                      r["tick_volume"], 300, SYMBOL, r["spread"] * info.point)
    finally:
        mt5.shutdown()


def load_history() -> D.Bars:
    recent = D.load_csv("data/XAUUSD_M5.csv")
    old = _fetch_pre_csv(int(recent.t[0]))
    t = np.r_[old.t, recent.t]
    o = np.r_[old.o, recent.o]
    h = np.r_[old.h, recent.h]
    l = np.r_[old.l, recent.l]
    c = np.r_[old.c, recent.c]
    v = np.r_[old.v, recent.v]
    sp_old = old.sp if old.sp is not None else np.full(len(old), RAW_SPREAD_FLOOR)
    sp_new = recent.sp if recent.sp is not None else np.full(len(recent), RAW_SPREAD_FLOOR)
    sp = np.maximum(np.r_[sp_old, sp_new], RAW_SPREAD_FLOOR)
    return D.Bars(t, o, h, l, c, v, 300, SYMBOL, sp)


def _last_closed_index(b5: D.Bars, at: int) -> int:
    idx = np.flatnonzero(b5.t + b5.step <= at)
    return int(idx[-1]) if len(idx) else -1


def _forward_metrics(events, flip, b15, b5, nxt, atr, profile, start, end):
    ev = [(i, d) for i, d in events if start <= int(b15.t[i]) < end]
    resolved = _last_closed_index(b5, end)
    rows = ce.evaluate_arm(ev, flip, b15, b5, nxt, atr, profile, resolved)
    return [r for r in rows if start <= r.t < end]


def run() -> int:
    # Standard 260-point-account cost is deliberately disabled.  The history
    # is evaluated at the live Demo 90-point floor plus commission/slippage.
    ce.SPREAD_STANDARD = 0.0
    b5 = load_history()
    now = int(b5.t[-1] + b5.step)
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) &
                   (b5.t[np.minimum(pos, len(b5) - 1)] == want), pos, -1)
    atr = ce.core.atr(b15, 14)
    profile = adaptive.hourly_spread_profile(b5)
    events = ce.event_universe(b15, nxt, ce._load_news())

    first = datetime.fromtimestamp(int(b5.t[0]), timezone.utc)
    last = datetime.fromtimestamp(int(b5.t[-1]), timezone.utc)
    print(f"data={first:%Y-%m-%d}..{last:%Y-%m-%d} M5_bars={len(b5):,}")
    print("cost=Demo raw floor spread 90 points (0.090) + commission 0.140 + "
          "slippage 0.033; standard 260-point model disabled")
    print("selection=annual expanding history; execution=following calendar period; "
          "tool geometry=fixed 1.5ATR stop, 1R target, 72 M5 bars")

    all_forward = []
    for year in range(FIRST_ANCHOR_YEAR, datetime.fromtimestamp(now, timezone.utc).year + 1):
        start = _epoch(year)
        end = min(_epoch(year + 1), now)
        if end - start < 7 * 86400:
            continue
        resolved_train = _last_closed_index(b5, start)
        ranked = []
        for family, ev in events.items():
            for mode, flip in (("FOLLOW", False), ("FLIP", True)):
                rows = ce.evaluate_arm(ev, flip, b15, b5, nxt, atr, profile,
                                       resolved_train)
                health = ce.arm_health(rows, start)
                if health["ready"]:
                    ranked.append((health["score"], family, mode, flip, health))
        ranked.sort(reverse=True, key=lambda x: x[0])
        print(f"\n[{year}] training {first:%Y-%m-%d}..{year - 1}-12-31  "
              f"ready={len(ranked)}")
        if not ranked:
            print("selected=NO_TOOL (no arm passed the frozen health gate)")
            continue
        for rank, (score, family, mode, _flip, h) in enumerate(ranked[:3], 1):
            w = h["windows"]
            print(f"rank{rank}={family} [{mode}] score={score:+.4f} "
                  f"E30={w['30']['mean']:+.4f} E60={w['60']['mean']:+.4f} "
                  f"E90={w['90']['mean']:+.4f}")
        score, family, mode, flip, _h = ranked[0]
        rows = _forward_metrics(events[family], flip, b15, b5, nxt, atr, profile,
                                start, end)
        all_forward.extend(rows)
        m = bt._metrics([r.net for r in rows])
        if not m:
            print(f"forward={year} selected={family} [{mode}] no completed trades")
        else:
            print(f"forward={year} selected={family} [{mode}] n={m['trades']} "
                  f"net={m['net_R']:+.3f}R mean={m['mean_R']:+.4f}R "
                  f"win={m['win_pct']:.1f}% PF={m['profit_factor']:.3f} "
                  f"DD={m['max_dd_R']:+.3f}R")
    if all_forward:
        all_forward.sort(key=lambda r: r.t)
        m = bt._metrics([r.net for r in all_forward])
        print("\n[combined forward-only selected tools]")
        print(f"n={m['trades']} net={m['net_R']:+.3f}R mean={m['mean_R']:+.4f}R "
              f"win={m['win_pct']:.1f}% PF={m['profit_factor']:.3f} "
              f"DD={m['max_dd_R']:+.3f}R")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
