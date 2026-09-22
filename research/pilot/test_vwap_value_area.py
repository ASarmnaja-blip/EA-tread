"""Pre-result verification checks required by Amendment 18 section 10."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D
import session_acceptance as S
import vwap_value_area as V


FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = ""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


def bars(n=500, t0=0, price=100.0) -> D.Bars:
    t = t0 + np.arange(n, dtype=np.int64) * 300
    o = np.full(n, price)
    h = np.full(n, price + .1)
    l = np.full(n, price - .1)
    c = np.full(n, price)
    v = np.ones(n)
    return D.Bars(t, o, h, l, c, v, 300, "SYNTH", np.full(n, .09))


def test_feature_no_future():
    b = bars(80, t0=22 * 3600)
    b.c[:12] = 100.0
    f0 = V.feature_before(b, int(b.t[12]))
    b.c[12] = 200.0
    b.h[12] = 200.1
    b.l[12] = 199.9
    f1 = V.feature_before(b, int(b.t[12]))
    ok("1 VWAP/value area ignore bars after decision time",
       f0.vwap == f1.vwap and f0.val == f1.val and f0.vah == f1.vah)


def test_anchor_reset():
    b = bars(40, t0=21 * 3600)
    b.c[:12] = 90.0
    b.h[:12] = 90.1
    b.l[:12] = 89.9
    b.c[12:24] = 110.0
    b.h[12:24] = 110.1
    b.l[12:24] = 109.9
    f = V.feature_before(b, int(b.t[24]))
    ok("2 new 22:00 session does not carry prior volume",
       abs(f.vwap - 110.0) < 0.05 and f.n_m5 == 12,
       f"vwap={f.vwap} n={f.n_m5}")


def test_value_area_highest_bin():
    tp = np.array([99.0, 100.0, 100.0, 100.0, 101.0])
    vol = np.array([1.0, 10.0, 10.0, 10.0, 1.0])
    val, vah = V.value_area(tp, vol, frac=.70)
    ok("3 value area contains the highest-volume bin", val <= 100.0 <= vah,
       f"VAL={val} VAH={vah}")


def test_entry_after_decision():
    b = bars(260, t0=22 * 3600)
    # Create enough session variation, then force a VWAP extension on a closed
    # M15 bar after warm-up.
    b.c += np.sin(np.arange(len(b)) / 10.0)
    b.h = b.c + .1
    b.l = b.c - .1
    b.c[183:186] = 120.0
    b.h[183:186] = 120.1
    b.l[183:186] = 119.9
    ev, b15, _ = V.build_events(b)
    good = all(int(b.t[e.entry_i]) >= int(b15.t[e.decision15_i]) + 900 for e in ev)
    ok("4 entry occurs after completed M15 decision", len(ev) > 0 and good,
       f"events={len(ev)}")


def test_atr_is_closed():
    b = bars(500)
    b.h += np.linspace(0, .5, len(b))
    a, b15, src = S.completed_atr_for_m5(b)
    bad = 0
    checked = 0
    for j, q in enumerate(src):
        if q < 0 or not np.isfinite(a[j]):
            continue
        checked += 1
        bad += int(int(b15.t[q]) + 900 > int(b.t[j]) + 300)
    ok("5 mapped M15 ATR had closed by the event decision", checked > 0 and bad == 0)


def test_leave_day_out():
    vals = np.array([1., 3., 10., 14.])
    days = np.array([1, 1, 2, 2])
    mu, n = S.leave_one_day_mean(vals, np.arange(4), days, 1, min_pool=2)
    ok("6 control excludes focal UTC day", mu == 12.0 and n == 2)


def test_boundary_path():
    b = bars(2000)
    out = S.precompute_outcomes(b, np.full(len(b), 1.0))
    first_forbidden = len(b) - S.TIME_STOP + 1
    ok("7 no trade/control path can cross boundary",
       bool(out.ok[first_forbidden - 1] and not out.ok[first_forbidden]))


def test_primary_ignores_subgroup():
    df = np.array([1.0, -1.0, -1.0, -1.0])
    day = np.array([1, 2, 3, 4])
    r = V.wild_mean_test(df, day)
    ok("8 subgroup cannot change primary family mean",
       r["mean"] < 0, f"family mean={r['mean']}")


def main() -> int:
    print("Amendment 18 verification")
    test_feature_no_future()
    test_anchor_reset()
    test_value_area_highest_bin()
    test_entry_after_decision()
    test_atr_is_closed()
    test_leave_day_out()
    test_boundary_path()
    test_primary_ignores_subgroup()
    print(f"\n{8-len(FAIL)}/8 passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
