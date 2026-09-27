"""Amendment 24 fast and integration audits."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as G


def test_fill_bar_spread_cannot_drive_gate() -> None:
    result = G.audit_spread_gate()
    assert result["passed"]


def test_selected_state_is_separate_from_hypothetical_history() -> None:
    result = G.audit_state_fidelity()
    assert all(result.values())


def test_cache_stamp_is_full_hash_sensitive() -> None:
    # The integration run checks the real canonical stamp.  This test verifies
    # that any field mutation invalidates exact matching.
    a = {"data": "x", "code": "y", "gate": G.GATE_BASE_MAX}
    b = dict(a)
    b["gate"] += 1e-6
    assert G._stamp_matches(a, a)
    assert not G._stamp_matches(a, b)


def test_gate_threshold_algebra() -> None:
    assert abs(1.5 * G.GATE_BASE_MAX - 0.125) < 1e-15


def test_real_cache_reproduction_and_causality() -> None:
    """Slow Section 10 integration test against both versioned caches."""
    b5 = G.hist.load_history()
    streams, meta, _built = G.load_raw_cache(b5)
    old_uni, _old_meta = G.old_audit.load_universe(b5)
    baseline, mismatches = G.build_policy_data(
        b5, streams, meta, apply_gate=False, old_uni=old_uni)
    gated, _ = G.build_policy_data(b5, streams, meta, apply_gate=True)
    assert not mismatches
    audit = G.run_audits(b5, gated, meta, mismatches)
    assert audit["passed_before_mtf_suite"]
    # Baseline is intentionally built too: it proves all 8,250 continuously
    # selected histories reproduce before the new selected-state execution.
    assert len(baseline.tags) == 8250
