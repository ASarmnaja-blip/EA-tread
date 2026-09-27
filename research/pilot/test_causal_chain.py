"""Fast Amendment 26 regression tests; no historical result is produced."""
from __future__ import annotations

import numpy as np

import causal_chain as C


def test_future_fill_mutation_and_legacy_negative_control():
    a = C.synthetic_audits()
    assert a["future_fill_invariance"]
    assert a["legacy_negative_control_failed_as_required"]
    assert a["open_vs_closed_at_later_fill"]


def test_streaming_batch_and_permutation():
    ek = np.asarray([20, 10, 10, 30, 14], np.int64)
    ok = np.asarray([0, 5, 4, 8, 7], np.int64)
    held = np.asarray([2, 3, 1, 2, 1], np.int64)
    ids = np.asarray([50, 40, 30, 20, 10], np.int64)
    a, ar = C.causal_indices(ek, ok, held, ids)
    b, br = C.streaming_indices(ek, ok, held, ids)
    assert np.array_equal(a, b)
    assert np.array_equal(ar, br)
    perm = np.asarray([3, 0, 4, 2, 1])
    p, _ = C.causal_indices(ek[perm], ok[perm], held[perm], ids[perm])
    assert np.array_equal(ids[perm][p], ids[a])


def test_busy_includes_exit_bar():
    ek = np.asarray([10, 14, 15], np.int64)
    chosen, rejected = C.causal_indices(ek, ek, np.asarray([4, 1, 1]))
    assert np.array_equal(chosen, np.asarray([0, 2]))
    assert np.array_equal(rejected, np.asarray([1]))


def test_same_bar_fifo():
    ek = np.asarray([10, 10, 10], np.int64)
    ok = np.asarray([8, 7, 7], np.int64)
    seq = np.asarray([0, 2, 1], np.int64)
    chosen, rejected = C.causal_indices(ek, ok, np.ones(3, np.int64), seq)
    assert np.array_equal(chosen, np.asarray([2]))
    assert set(rejected.tolist()) == {0, 1}


def test_independent_price_oracle_never_receives_future_fill_bar():
    result = C.synthetic_audits()
    assert result["independent_price_oracle_future_invariant"]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failures.append((fn.__name__, repr(exc)))
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"tests={len(tests)} passed={len(tests)-len(failures)} failures={len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
