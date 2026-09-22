"""Seven pre-result verification checks required by Amendment 17 section 11."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D
import session_acceptance as S


FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = ""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


def bars(n=400, t0=0, price=100.0) -> D.Bars:
    t = t0 + np.arange(n, dtype=np.int64) * 300
    o = np.full(n, price)
    h = np.full(n, price + .1)
    l = np.full(n, price - .1)
    c = np.full(n, price)
    return D.Bars(t, o, h, l, c, np.ones(n), 300, "SYNTH", np.full(n, .09))


def test_level_no_future():
    b = bars(300)
    # Exact Asia window, then mutate the first bar AFTER it.
    ix = np.arange(72)
    b.h[ix] = 101.0
    before = [x for x in S.build_levels(b) if x.family == "asia" and x.side == "high"][0]
    b.h[72] = 999.0
    after = [x for x in S.build_levels(b) if x.family == "asia" and x.side == "high"][0]
    ok("1 level ignores bars after construction", before.price == after.price == 101.0)


def test_acceptance_timing():
    b = bars(30)
    level = S.Level(0, "prior-day", "high", 101.0, 300, 6000)
    b.c[0] = 100.0
    b.h[1], b.c[1] = 101.2, 101.1
    b.h[2], b.c[2] = 101.3, 101.2
    ev, _ = S.scan_level(b, level)
    good = len(ev) == 1 and ev[0].response == "acceptance" and ev[0].entry_i == 3
    ok("2 acceptance enters only after confirming close", good,
       f"entry={ev[0].entry_i if ev else 'none'}")


def test_episode_and_unclassified():
    b = bars(30)
    level = S.Level(0, "prior-day", "high", 101.0, 300, 8000)
    # First episode: unclassified because close equals level. Consecutive touch
    # bars must not create more episodes. Bar 4 is wholly clear and resets it.
    b.c[0] = 100.0
    b.h[1], b.c[1] = 101.2, 101.0
    b.h[2], b.c[2] = 101.2, 100.8
    b.h[3], b.c[3] = 101.1, 100.7
    b.h[4], b.c[4] = 100.8, 100.6
    # Second episode is a classified rejection.
    b.h[5], b.c[5] = 101.1, 100.5
    ev, raw = S.scan_level(b, level)
    ok("3 consecutive touching bars are one episode", raw == 2, f"episodes={raw}")
    good = len(ev) == 1 and ev[0].response == "rejection" and ev[0].touch == 1
    ok("4 unclassified episode consumes its touch number", good,
       f"event touch={ev[0].touch if ev else 'none'}")


def test_leave_day_out():
    vals = np.array([1., 3., 10., 14.])
    days = np.array([1, 1, 2, 2])
    mu, n = S.leave_one_day_mean(vals, np.arange(4), days, 1, min_pool=2)
    ok("5 control excludes the focal day in full", mu == 12.0 and n == 2,
       f"mean={mu} n={n}")


def test_atr_is_closed():
    b = bars(500, t0=0)
    # Add enough variation that ATR is finite and inspect the source close time.
    b.h += np.linspace(0, .5, len(b))
    a, b15, src = S.completed_atr_for_m5(b)
    checked = 0
    bad = 0
    for j in range(len(b)):
        q = int(src[j])
        if q < 0 or not np.isfinite(a[j]):
            continue
        checked += 1
        if int(b15.t[q]) + 900 > int(b.t[j]) + 300:
            bad += 1
    ok("6 mapped M15 ATR had closed by the M5 decision", checked > 0 and bad == 0,
       f"checked={checked} bad={bad}")


def test_boundary_path():
    b = bars(2000)
    a = np.full(len(b), 1.0)
    out = S.precompute_outcomes(b, a)
    first_forbidden = len(b) - S.TIME_STOP + 1
    good = out.ok[first_forbidden - 1] and not out.ok[first_forbidden]
    ok("7 no trade/control path can cross the data boundary", bool(good),
       f"last ok={np.flatnonzero(out.ok)[-1]}")


def test_swap_calendar():
    # Epoch day 4 is Monday 1970-01-05. Mon/Tue/Thu charge one, Wednesday
    # charges three; Saturday and Sunday charge zero.
    mon = 4 * 86400
    week = S._swap_units(mon + 20 * 3600, mon + 3 * 86400 + 22 * 3600)
    fri = mon + 4 * 86400
    weekend = S._swap_units(fri + 20 * 3600, mon + 7 * 86400 + 22 * 3600)
    ok("8 swap calendar skips weekends and triples Wednesday",
       week == 6 and weekend == 2, f"Mon-Thu={week} Fri-Mon={weekend}")


def main() -> int:
    print("Amendment 17 verification")
    test_level_no_future()
    test_acceptance_timing()
    test_episode_and_unclassified()
    test_leave_day_out()
    test_atr_is_closed()
    test_boundary_path()
    test_swap_calendar()
    print(f"\n{8-len(FAIL)}/8 passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
