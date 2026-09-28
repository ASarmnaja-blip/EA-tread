"""Hand-computed checks for the WPWB search engine (prereg section 8)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import data as D  # noqa: E402  (pilot module, on path via common)
import mtf_engine as E  # noqa: E402


def synthetic(days: int = 10, price: float = 1000.0, start=C.ep(2024, 1, 1)):
    n = days * 288
    t = start + 300 * np.arange(n, dtype=np.int64)
    p = np.full(n, price)
    return D.Bars(t, p.copy(), p.copy(), p.copy(), p.copy(), np.ones(n), 300,
                  "SYN", np.full(n, 0.09))


def approx(a, b, tol=1e-9):
    assert abs(a - b) < tol, (a, b)


def test_flat_costs():
    m = C.Market(synthetic())
    i = int(np.searchsorted(m.t, C.ep(2024, 1, 2) + 10 * 3600))   # 10:00 UTC
    exp = -(0.09 + C.FEES) / 1000 * 1e4
    approx(float(m.pnl_bp([i], [i], [1])[0]), exp)
    approx(float(m.pnl_bp([i], [i], [-1])[0]), exp)
    exp15 = -(0.09 * 1.5 + C.FEES * 1.5) / 1000 * 1e4
    approx(float(m.pnl_bp([i], [i], [1], stress=1.5)[0]), exp15)


def test_directional_and_swap():
    m = C.Market(synthetic())
    i = int(np.searchsorted(m.t, C.ep(2024, 1, 2) + 10 * 3600))
    k = i + 2                                   # 10:00 -> 12:59, no rollover
    m.o = m.o.copy(); m.c = m.c.copy()
    m.o[i] = 1000.0; m.c[k] = 1010.0
    approx(float(m.pnl_bp([i], [k], [1])[0]), (10 - 0.09 - C.FEES) / 1000 * 1e4)
    approx(float(m.pnl_bp([i], [k], [-1])[0]), (-10 - 0.09 - C.FEES) / 1000 * 1e4)
    j = int(np.searchsorted(m.t, C.ep(2024, 1, 2) + 20 * 3600))  # 20:00
    kk = int(np.searchsorted(m.t, C.ep(2024, 1, 2) + 22 * 3600))  # holds past 21:00
    base = float(m.pnl_bp([j], [kk], [1])[0])
    no_swap = (m.c[kk] - m.o[j] - 0.09 - C.FEES) / m.o[j] * 1e4
    approx(base, no_swap - C.SWAP_LONG / m.o[j] * 1e4)
    short = float(m.pnl_bp([j], [kk], [-1])[0])
    approx(short, (m.o[j] - m.c[kk] - 0.09 - C.FEES) / m.o[j] * 1e4)


def test_rollover_matches_engine():
    rng = np.random.default_rng(0)
    t0 = rng.integers(C.ep(2022, 1, 1), C.ep(2023, 1, 1), 2000)
    t1 = t0 + rng.integers(0, 10 * 86400, 2000)
    vec = C.rollover_nights_vec(t0, t1)
    ref = np.array([E.rollover_nights(int(a), int(b)) for a, b in zip(t0, t1)])
    assert np.array_equal(vec, ref)


def test_calendar_and_weeks():
    m = C.Market(synthetic(days=21))
    i = int(np.searchsorted(m.t, C.ep(2024, 1, 1)))   # 2024-01-01 is a Monday
    assert m.wday[i] == 0 and m.hour[i] == 0
    for cut in m.cuts[:3]:
        lo, hi = m.week_bars(int(cut))
        if hi > lo:
            assert m.t[lo] >= cut and m.t[hi - 1] + 3600 <= cut + C.WEEK
    assert all((m.cuts - m.cuts[0]) % C.WEEK == 0)
    from datetime import datetime, timezone
    d = datetime.fromtimestamp(int(m.cuts[0]), timezone.utc)
    assert d.weekday() == 4 and d.hour == 22 and d.minute == 15


def test_exit_index_truncates_at_gap():
    m = C.Market(synthetic())
    i = 5
    assert m.exit_index(i, 3, len(m.t)) == i + 2
    m.t = m.t.copy(); m.t[i + 1:] += 3600          # open a 1h gap after i
    assert m.exit_index(i, 3, len(m.t)) == i


def test_boot_size_under_null():
    """False-pass rate at DEV_P_MAX must be <= ~5% on autocorrelated nulls."""
    for phi in (0.0, 0.3):
        hits = 0
        for s in range(300):
            e = np.random.default_rng(5000 + s).normal(0, 1, 140)
            x = np.empty(140); x[0] = e[0]
            for i in range(1, 140):
                x[i] = phi * x[i - 1] + e[i]
            hits += C.block_boot(x, draws=1000)["p"] < C.DEV_P_MAX
        assert hits / 300 <= 0.065, (phi, hits / 300)


def test_boot_detects_real_effect():
    x = np.random.default_rng(7).normal(0.5, 1, 140)
    assert C.block_boot(x)["p"] < C.DEV_P_MAX


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
