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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
