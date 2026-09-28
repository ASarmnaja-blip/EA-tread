"""Tests for the WPWB weekly risk report. Run from the repo root."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402
import weekly_report as WR  # noqa: E402


def test_vol_scale_never_increases_risk():
    for f in (1.0, 1e3, V.B_REF, 4 * V.B_REF, 1e9, np.nan, -1.0, 0.0):
        s = V.vol_scale(f)
        assert V.SCALE_MIN <= s <= V.SCALE_MAX <= 1.0
    assert V.vol_scale(np.nan) == V.SCALE_MIN          # unknown -> most conservative


def test_ewma_uses_past_only():
    rng = np.random.default_rng(0)
    rv = rng.lognormal(10, 0.5, 200)
    f = V.ewma_forecast(rv)
    for k in (5, 50, 150):
        rv2 = rv.copy(); rv2[k:] = 1e12
        assert V.ewma_forecast(rv2)[k] == f[k]
        h1 = V.har_forecast(rv)
        h2 = V.har_forecast(rv2)
        if np.isfinite(h1[k]):
            assert h1[k] == h2[k]


def test_label_edges():
    assert V.label(0.5)[1] == "CALM" and V.label(1.0)[1] == "NORMAL"
    assert V.label(2.0)[1] == "HIGH" and V.label(3.0)[1] == "EXTREME"


def test_report_ignores_bars_after_cut():
    """Garbage after the cut must not change any forecast or last-week value."""
    b = BR.load_bars(frozen=True)
    m = BR.market(b)
    cut = int(np.datetime64("2026-09-11T22:15:00", "s").astype(np.int64))
    a = WR.compute(m, cut)
    k = int(np.searchsorted(b.t, cut))
    rng = np.random.default_rng(1)
    c = b.c.copy(); c[k:] = c[k - 1] * np.exp(np.cumsum(rng.normal(0, 0.01, len(c) - k)))
    o = b.o.copy(); o[k:] = c[k:]
    h = np.maximum(b.h, 0); h[k:] = c[k:] * 1.01
    l = b.l.copy(); l[k:] = c[k:] * 0.99
    g = BR.D.Bars(b.t, o, h, l, c, b.v, b.step, b.symbol, b.sp)
    z = WR.compute(BR.market(g), cut)
    for sec in ("last", "next", "cal"):
        for key, v in a[sec].items():
            w = z[sec][key]
            same = (v == w) or (isinstance(v, float) and np.isnan(v) and np.isnan(w))
            assert same, (sec, key, v, w)
    assert a["price"] == z["price"]


def test_log_is_append_only():
    with tempfile.TemporaryDirectory() as d:
        WR.LOG = Path(d) / "log.csv"
        row = {"cut_utc": "2026-10-02 22:15", "spec": "v1", "forward": True, "f_ewma": 1.0,
               "data_end_utc": "x", "generated_utc": "t1"}
        assert WR.append_log(dict(row)) == "appended"
        assert WR.append_log(dict(row, generated_utc="t2", data_end_utc="y")) == "exists"
        try:
            WR.append_log(dict(row, f_ewma=2.0))
            raise AssertionError("rewrite accepted")
        except RuntimeError as e:
            assert "append-only" in str(e)


def test_saturday_run_with_friday_close_data():
    """Codex Round 5 blocker: on Saturday the data ends at Friday's close,
    before the 22:15 cut. The week must still count as complete."""
    b = BR.load_bars(frozen=True)
    cut = int(np.datetime64("2026-09-11T22:15:00", "s").astype(np.int64))
    k = int(np.searchsorted(b.t, cut))
    t = BR.D.Bars(b.t[:k], b.o[:k], b.h[:k], b.l[:k], b.c[:k], b.v[:k], b.step, b.symbol, b.sp[:k])
    m = BR.market(t)
    assert int(m.t[-1]) + 3600 < cut                       # really no bar at the cut
    r = WR.compute(m, cut)
    full = WR.compute(BR.market(b), cut)
    assert r["next"] == full["next"] and r["last"] == full["last"]


def test_straddling_bar_goes_to_later_week():
    t = np.array([0, 3600, 7200, 10800], np.int64)
    c = np.array([100.0, 101.0, 102.0, 103.0])
    rv, _, _, n = V.weekly_rv(t, c, c, c, np.array([5400 - 7 * 86400, 5400]))
    assert list(n) == [1, 3]                               # close 3600 -> first week; later closes -> second


def test_fail_safe_scale():
    assert V.effective_scale(0.9, True) == 0.9
    assert V.effective_scale(0.9, False) == V.SCALE_MIN
    assert V.effective_scale(0.9, None) == V.SCALE_MIN
    assert V.effective_scale(0.9, True, last_week_valid=False) == V.SCALE_MIN


def test_invalid_week_never_reenters():
    rv = np.array([100.0, 200.0, np.nan, 400.0, 300.0])
    f = V.ewma_forecast(rv)
    assert f[3] == f[2]                                    # invalid week carried, not used
    assert np.isfinite(f[4])


def test_forward_scores_join_by_date():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        WR.LOG = Path(d) / "log.csv"
        rows = [dict(cut_utc="2026-10-02 22:15", forward=True, f_ewma=100.0, f_har=100.0, f_mean26=100.0,
                     prev_rv=50.0, prev_valid=True),
                dict(cut_utc="2026-10-16 22:15", forward=True, f_ewma=100.0, f_har=100.0, f_mean26=100.0,
                     prev_rv=80.0, prev_valid=True),       # 10-09 missing: must not be scored
                dict(cut_utc="2026-10-23 22:15", forward=True, f_ewma=90.0, f_har=90.0, f_mean26=90.0,
                     prev_rv=100.0, prev_valid=True)]
        pd.DataFrame(rows).to_csv(WR.LOG, index=False)
        fs = WR.forward_scores()
        assert fs["n"] == 1 and abs(fs["ewma"]) < 1e-12   # only 10-23 vs forecast logged 10-16


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
