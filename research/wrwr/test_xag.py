"""Tests for the silver pieces of WRWR Test B (research/wrwr/xag.py): C4 XAG costs incl. 2023+ bars without a recorded spread,
the $0.50 / $1.00 round-number override, the fail-closed table loader and the silver mark-price patch.
(The builder's bit-parity with the frozen gold H4 tables is `python research/wrwr/xag.py parity`.)"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402
import xag as X  # noqa: E402


def _bars(close, t0="2024-03-04 00:00"):
    n = len(close)
    t = (pd.Timestamp(t0).value // 10**9) + 3600 * np.arange(n, dtype=np.int64)
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]]
    return SG.mk(t, o, np.maximum(o, c) + 0.01, np.minimum(o, c) - 0.01, c, np.ones(n), np.full(n, np.nan), 3600)


def test_cost():
    ts = [pd.Timestamp(x).value // 10**9 for x in ("2022-12-30 10:00", "2023-06-01 10:00", "2024-01-02 10:00", "2024-01-03 10:00")]
    B = SG.mk(np.array(ts), *(np.ones(4) for _ in range(5)), np.array([3.0, np.nan, 2.0, 7.0]), 3600)
    got = X.xag_cost(B)(np.arange(4))
    c = K.xag_pre2023_constant()
    exp = np.array([c, c, 4.0, 8.0])
    assert np.allclose(got, exp), (got, exp)


def test_round_override():
    c = np.r_[np.full(40, 24.40), np.linspace(24.40, 25.10, 30), np.full(40, 25.10)]
    B = _bars(c)
    cuts = np.arange(pd.Timestamp("2024-03-01 22:15").value // 10**9, B.t[-1] + 8 * 86400, 7 * 86400, dtype=np.int64)
    sig = X.xag_signals(B, cuts, "f2")
    up50, dn50 = sig["round50_x"]; up100, dn100 = sig["round100_x"]
    i50 = np.flatnonzero(up50); i100 = np.flatnonzero(up100)
    assert len(i50) == 2 and len(i100) == 1 and not dn50.any() and not dn100.any(), (i50, i100)
    assert c[i50[0] - 1] < 24.5 <= c[i50[0]] and c[i50[1] - 1] < 25.0 <= c[i50[1]]
    assert c[i100[0] - 1] < 25.0 <= c[i100[0]]
    assert list(sig)[:3] == ["fvg_form", "fvg_retest", "bos"]                      # order of the gold signal set is kept


def test_loader_fails_closed():
    src = X.table_path("D1", "f2")
    z = np.load(src, allow_pickle=False)
    arr = {k: z[k] for k in z.files}
    loader = X.make_loader("f2")
    meta, cands, a = loader("XAGUSD", "D1", verify=True)                           # the real table loads and verifies
    assert meta["symbol"] == "XAGUSD" and len(cands) == meta["n_cands"]
    with tempfile.TemporaryDirectory() as d:
        bad = dict(arr); g = bad["gross_bp"].copy(); g[5] += 1.0; bad["gross_bp"] = g
        p = Path(d) / "t.npz"; np.savez(p, **bad)
        old = X.table_path
        X.table_path = lambda tf, s: p
        try:
            loader("XAGUSD", "D1", verify=False)
            raise AssertionError("tampered table loaded")
        except ValueError as e:
            assert "differ" in str(e)
        finally:
            X.table_path = old
    try:
        loader("XAUUSD", "D1")
        raise AssertionError("silver loader served gold")
    except ValueError:
        pass


def test_marks_are_silver():
    X.patch_marks()
    B, cuts, cell = SG.load_xau("H1")
    a, _ = X.load_bars()
    assert np.array_equal(B.c, a["c"]) and B.c.max() < 200                        # silver prices, not gold
    assert len(cuts) == len(cell) and (np.diff(cuts) == 7 * 86400).all()


if __name__ == "__main__":
    for f in (test_cost, test_round_override, test_loader_fails_closed, test_marks_are_silver):
        f(); print("ok", f.__name__)
