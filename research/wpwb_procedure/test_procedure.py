"""Tests for procedure.py and harness.py.

Synthetic tests read no market data. The real-matrix tests only compare
DECISIONS under mutation; they never compute or print P's outcomes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
import procedure as P  # noqa: E402


def _synth(n_tools=12, n=200, seed=0):
    rng = np.random.default_rng(seed)
    R = rng.standard_t(4, (n_tools, n)) * rng.uniform(20, 200, (n_tools, 1))
    NTR = (rng.random((n_tools, n)) < 0.8).astype(int)
    R[NTR == 0] = 0.0
    VALID = np.ones((n_tools, n), bool)
    VALID[3, :80] = False                        # a late-starting tool
    INNER = np.ones((n_tools, n))
    INNER[7] = rng.uniform(0.5, 2.0, n)          # a self-sizing tool (like VOLMAN)
    return R, NTR, VALID, INNER


def _same(a, b):
    return (a.choice == b.choice and a.size == b.size
            and np.array_equal(a.eligible, b.eligible)
            and np.array_equal(np.nan_to_num(a.score, nan=-9), np.nan_to_num(b.score, nan=-9)))


def test_future_garbage_synthetic():
    R, NTR, V, I = _synth()
    rng = np.random.default_rng(1)
    for w in rng.choice(np.arange(60, 200), 30, replace=False):
        a = P.decide(R, NTR, V, I, int(w))
        R2, N2, V2, I2 = R.copy(), NTR.copy(), V.copy(), I.copy()
        R2[:, w:] = rng.normal(0, 1e4, R2[:, w:].shape)
        N2[:, w:] = rng.integers(0, 5, N2[:, w:].shape)
        V2[:, w + 1:] = rng.random(V2[:, w + 1:].shape) < 0.5
        I2[:, w + 1:] = 99.0
        assert _same(a, P.decide(R2, N2, V2, I2, int(w)))


def test_total_cap():
    R, NTR, V, I = _synth()
    res, path = P.run(R, NTR, V, I, 60)
    for d in path:
        if d.choice >= 0:
            assert d.size * I[d.choice, d.w] <= P.CAP + 1e-9


def test_fast_equals_reference():
    for seed in range(3):
        R, NTR, V, I = _synth(seed=seed)
        R15 = R * 1.1 - 3
        a, _ = P.run(R, NTR, V, I, 60, {"base": R, "stress": R15})
        b = P.run_fast(R, NTR, V, I, 60, {"base": R, "stress": R15})
        assert np.array_equal(a["choice"], b["choice"])
        assert np.allclose(a["size"], b["size"])
        for k in ("base", "stress"):
            for f in ("P", "Bp", "B", "d", "d_cond"):
                assert np.allclose(a[k][f], b[k][f]), (k, f)


def test_stress_path_uses_base_decisions():
    R, NTR, V, I = _synth()
    a, _ = P.run(R, NTR, V, I, 60, {"base": R, "stress": R - 50})
    b, _ = P.run(R, NTR, V, I, 60, {"base": R})
    assert np.array_equal(a["choice"], b["choice"])


def test_invalid_tool_never_chosen_early():
    R, NTR, V, I = _synth()
    R[3] = 500.0; NTR[3] = 1
    _, path = P.run(R, NTR, V, I, 60)
    for d in path:
        if d.w < 80 + 52:
            assert not d.eligible[3]


def test_planted_persistent_edge_found():
    R, NTR, V, I = _synth(seed=2)
    R[5] = np.abs(R[5]) * 0.3 + 30.0; NTR[5] = 1
    res, _ = P.run(R, NTR, V, I, 60)
    assert (res["choice"] == 5).mean() > 0.8 and res["base"]["d"].mean() > 0


def test_flat_when_all_lose():
    R, NTR, V, I = _synth()
    R[:, :] = -np.abs(R) - 1.0
    NTR[:, :] = 1
    res, _ = P.run(R, NTR, V, I, 60)
    assert (res["choice"] == -1).all()
    b = res["base"]
    assert (b["P"] == 0).all() and (b["B"] == 0).all() and (b["Bp"] < 0).all()
    assert (b["d"] > 0).all()                    # flat beats a losing menu vs B' ...
    ok, checks, _ = P.resource_screen({"base": b, "stress": b})
    assert not checks["abs_P_stress"] and not ok  # ... but the absolute gate stops it


def test_blocks():
    assert P.blocks(216) == [(i * 26, (i + 1) * 26) for i in range(7)] + [(182, 216)]
    assert P.blocks(20) == [(0, 20)]


def test_e_process_boundaries():
    c = P.C_FLOOR
    E = P.e_process(np.full(300, -1e6), c)       # worst possible weeks
    assert (E > 0).all() and E[-1] < 1e-3
    E = P.e_process(np.full(10, P.MARGIN_BP), c)  # exactly at the margin
    assert np.allclose(E, 1.0)
    for bad in (np.array([np.nan]),):
        try:
            P.e_process(bad, c); raise AssertionError("NaN accepted")
        except AssertionError as ex:
            assert "missing" in str(ex)
    assert P.clip_scale(np.zeros(50)) == P.C_FLOOR
    rng = np.random.default_rng(3)
    hits = 0
    for _ in range(400):                          # null at the margin
        d = rng.normal(P.MARGIN_BP, 15, 300)
        hits += P.e_process(d, 45.0).max() >= 40
    assert hits / 400 <= 1 / 40 + 0.02
    assert P.e_process(rng.normal(12, 15, 300), 45.0).max() >= 40


def test_null_dgp_properties():
    R, NTR, V, _ = _synth(seed=4)
    rng = np.random.default_rng(5)
    A, B, N = H.scramble(R, R * 1.2, NTR, V, rng)
    for w in range(R.shape[1]):
        v = V[:, w]
        assert np.isclose(A[v, w].sum(), 0.0, atol=1e-8)
        assert (A[v, w][N[v, w] == 0] == 0).all()
        assert sorted(N[v, w]) == sorted(NTR[v, w])


def test_null_mean_d_zero_synthetic():
    ds = []
    for s in range(60):
        R, NTR, V, _ = _synth(seed=100 + s)
        rng = np.random.default_rng(s)
        A, B, N = H.scramble(R, R, NTR, V, rng)
        res = P.run_fast(A, N, V, np.ones_like(A), 60)
        ds.append(res["base"]["d"].mean())
    ds = np.asarray(ds)
    assert abs(ds.mean()) < 3 * ds.std(ddof=1) / np.sqrt(len(ds))


def test_future_garbage_real_matrix():
    if not H.MATRIX.exists():
        print("  (skipped: matrix not built)"); return
    z = np.load(H.MATRIX)
    R, NTR, V, I = z["R10"], z["NTR"], z["VALID"], z["INNER"]
    rng = np.random.default_rng(7)
    w0 = P.first_scored_cut(V)
    for w in rng.choice(np.arange(w0, R.shape[1]), 50, replace=False):
        a = P.decide(R, NTR, V, I, int(w))
        R2, N2, V2, I2 = R.copy(), NTR.copy(), V.copy(), I.copy()
        R2[:, w:] = rng.normal(0, 1e4, R2[:, w:].shape)
        N2[:, w:] = rng.integers(0, 5, N2[:, w:].shape)
        V2[:, w + 1:] = rng.random(V2[:, w + 1:].shape) < 0.5
        I2[:, w + 1:] = 99.0
        assert _same(a, P.decide(R2, N2, V2, I2, int(w)))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
