"""Codex audit checks frozen in WPWB_LIVE_PREREG amendment 7.1.

This script reads local files only.  It does not import MetaTrader5 and does
not call the fresh-data fetcher.
"""
from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import common as C  # noqa: E402
import data as D  # noqa: E402
import historical_regime_walkforward as hist  # noqa: E402
import mtf_engine as E  # noqa: E402
from backtest_report import load_events  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic(n: int = 576, start: int = C.ep(2024, 1, 1)) -> D.Bars:
    t = start + np.arange(n, dtype=np.int64) * 300
    o = 1000.0 + np.arange(n) * 0.01
    c = o + 0.005
    h = np.maximum(o, c) + 0.02
    l = np.minimum(o, c) - 0.03
    v = np.arange(1, n + 1, dtype=float)
    sp = 0.09 + np.arange(n) * 0.0001
    return D.Bars(t, o, h, l, c, v, 300, "SYN", sp)


def audit_h1() -> None:
    b = synthetic()
    h1, nxt = E.resample(b, 12)
    check(len(h1.t) == len(b.t) // 12, "unexpected complete H1 count")
    for j in range(len(h1.t)):
        q = slice(j * 12, j * 12 + 12)
        check(h1.t[j] == b.t[j * 12], "H1 label is not first M5 timestamp")
        check(h1.o[j] == b.o[j * 12] and h1.c[j] == b.c[j * 12 + 11],
              "H1 open/close mismatch")
        check(h1.h[j] == b.h[q].max() and h1.l[j] == b.l[q].min(),
              "H1 high/low mismatch")
        check(h1.v[j] == b.v[q].sum(), "H1 volume mismatch")
        expected_next = j * 12 + 12 if j * 12 + 12 < len(b.t) else -1
        check(nxt[j] == expected_next, "H1 next-tradable M5 index mismatch")

    keep = np.ones(len(b.t), dtype=bool)
    keep[17] = False
    g = D.Bars(b.t[keep], b.o[keep], b.h[keep], b.l[keep], b.c[keep],
               b.v[keep], 300, "GAP", b.sp[keep])
    gh, _ = E.resample(g, 12)
    check(C.ep(2024, 1, 1) + 3600 not in set(gh.t.tolist()),
          "resampler manufactured an H1 bar over a missing M5 bar")
    print("PASS independent H1 OHLC/continuity reconstruction")


def audit_costs() -> None:
    b = synthetic()
    m = C.Market(b)
    i, k = 5, 8
    entry = m.o[i]
    exit_ = m.c[k]
    long_expected = (exit_ - entry - m.sp_in[i] - C.FEES) / entry * 1e4
    short_expected = (entry - exit_ - m.sp_out[k] - C.FEES) / entry * 1e4
    check(np.isclose(m.pnl_bp([i], [k], [1])[0], long_expected),
          "long Bid/Ask cost mismatch")
    check(np.isclose(m.pnl_bp([i], [k], [-1])[0], short_expected),
          "short Bid/Ask cost mismatch")
    long_stress = (exit_ - entry - 1.5 * m.sp_in[i] - 1.5 * C.FEES) / entry * 1e4
    check(np.isclose(m.pnl_bp([i], [k], [1], 1.5)[0], long_stress),
          "1.5x cost stress mismatch")

    first = np.searchsorted(b.t, m.t)
    check(np.array_equal(m.sp_in, b.sp[first]), "entry spread is not first M5 spread")
    check(np.array_equal(m.sp_out, b.sp[np.minimum(first + 11, len(b.t) - 1)]),
          "exit spread is not final M5 spread")

    cases = np.array([
        [C.ep(2024, 1, 2) + 20 * C.HOUR, C.ep(2024, 1, 2) + 21 * C.HOUR - 1],
        [C.ep(2024, 1, 2) + 20 * C.HOUR, C.ep(2024, 1, 2) + 21 * C.HOUR],
        [C.ep(2024, 1, 2) + 21 * C.HOUR, C.ep(2024, 1, 2) + 21 * C.HOUR],
        [C.ep(2024, 1, 2) + 21 * C.HOUR + 1, C.ep(2024, 1, 3) + 21 * C.HOUR],
    ], dtype=np.int64)
    got = C.rollover_nights_vec(cases[:, 0], cases[:, 1])
    ref = np.array([E.rollover_nights(int(a), int(z)) for a, z in cases])
    check(np.array_equal(got, ref), "rollover boundary mismatch")
    print("PASS independent Bid/Ask, stress, spread-location, and rollover checks")


def audit_week_and_checkpoint() -> None:
    m = C.Market(combined_bars())
    check(len(m.t) > 0, "no combined H1 bars")
    for cut in m.cuts:
        dt = datetime.fromtimestamp(int(cut), timezone.utc)
        check((dt.weekday(), dt.hour, dt.minute) == (4, 22, 15),
              "weekly cut is not Friday 22:15 UTC")
        lo, hi = m.week_bars(int(cut))
        if hi > lo:
            check(m.t[lo] >= cut, "week includes a bar before cut")
            check(m.t[hi - 1] + C.HOUR <= cut + C.WEEK,
                  "week includes a bar ending after next cut")

        cp = int(cut) + 4 * 86400 + 105 * 60
        cpd = datetime.fromtimestamp(cp, timezone.utc)
        check((cpd.weekday(), cpd.hour, cpd.minute) == (2, 0, 0),
              "checkpoint is not Wednesday 00:00 UTC")
        kcp = int(np.searchsorted(m.t, cp))
        if 0 < kcp < len(m.t):
            check(m.t[kcp - 1] + C.HOUR <= cp, "pre-checkpoint close is not known")
            check(m.t[kcp] >= cp, "post-checkpoint bar leaks into features")

    ev = load_events()
    check(np.issubdtype(ev.ts.dtype, np.integer), "event timestamps are not integer seconds")
    check(ev.ts.between(1_500_000_000, 1_900_000_000).all(),
          "event timestamps are outside epoch-second range")
    for cut in m.cuts:
        cp = int(cut) + 4 * 86400 + 105 * 60
        kcp = int(np.searchsorted(m.t, cp))
        before = ev[ev.ts <= cp - 3 * C.HOUR]
        for ts in before.ts:
            k = int(np.searchsorted(m.t, int(ts), side="right")) - 1
            if 0 <= k and k + 2 < len(m.t) and k + 2 < kcp:
                check(m.t[k + 2] + C.HOUR <= cp,
                      "W5 reaction uses a close after the checkpoint")
    print("PASS week-boundary, checkpoint, event-second, and W5 causality checks")


def audit_fresh() -> None:
    fresh_dir = ROOT / "data" / "fresh"
    for path in sorted(fresh_dir.glob("*_M5.npz")):
        with np.load(path) as d:
            t = d["t"]
            check(np.all(np.diff(t) > 0), f"{path.name} timestamps are not sorted unique")

    canonical = hist.load_history()
    with np.load(fresh_dir / "XAUUSD_M5.npz") as f:
        common_t, ia, ib = np.intersect1d(canonical.t, f["t"], return_indices=True)
        check(len(common_t) > 0, "no canonical/fresh XAU overlap")
        match = float((np.abs(canonical.c[ia] - f["c"][ib]) <= 0.01).mean())
        offsets = {}
        for off_h in range(-3, 4):
            _, ja, jb = np.intersect1d(canonical.t, f["t"] + off_h * C.HOUR,
                                       return_indices=True)
            offsets[off_h] = (float((np.abs(canonical.c[ja] - f["c"][jb]) <= 0.01).mean())
                              if len(ja) else -1.0)
        best = max(offsets, key=offsets.get)
        check(best == 0 and match > 0.99,
              f"fresh overlap mismatch: best offset {best}, zero-offset match {match:.6f}")

    combined = combined_bars()
    check(np.all(np.diff(combined.t) > 0), "combined timestamps are not sorted unique")
    check(np.array_equal(combined.t[:len(canonical.t)], canonical.t),
          "combined data changed canonical prefix")
    check(np.all(combined.t[len(canonical.t):] > canonical.t[-1]),
          "combined append is not strictly after canonical end")
    print(f"PASS fresh-data invariants: overlap={len(common_t):,}, match={match:.4%}, "
          f"best_offset={best:+d}h, appended={len(combined.t) - len(canonical.t):,}")


def audit_no_trading_calls() -> None:
    files = [
        ROOT / "research" / "wpwb_search" / "common.py",
        ROOT / "research" / "wpwb_search" / "test_common.py",
        ROOT / "research" / "wpwb_live" / "h1_traces.py",
        ROOT / "research" / "wpwb_live" / "fetch_fresh.py",
    ]
    forbidden = {"order_send", "order_check", "positions_get", "position_close",
                 "orders_get", "history_orders_get"}
    found = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                found.append(f"{path.name}:{node.lineno}:{node.attr}")
    check(not found, f"trading API references in audit scope: {found}")
    print("PASS static scan: no MT5 trading API reference in audited files")


def main() -> int:
    audit_no_trading_calls()
    audit_h1()
    audit_costs()
    audit_week_and_checkpoint()
    audit_fresh()
    print("AUDIT RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
