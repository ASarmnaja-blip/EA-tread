# WRWR SHADOW manifest (frozen 2026-09-30, before the first forward cut 2026-10-02 22:15 UTC)
Pre-registration: docs/WRWR_SHADOW_PREREG.md. The weekly job refuses to run (fail closed) unless the digest below equals the sha256 of the
concatenated LF-normalised files listed in `research/wrwr/forward_shadow.py` SHADOW_FILES (forward_shadow.py, contracts.py, portfolio.py,
f2_signals.py, signals.py, research/foundry/engine.py, research/wpwb_weekly/vol.py).

- code digest (sha256): `47471ee21ad894d5dabd13e55eabc402f97ae165c731b8751f83aa00bbd8065e`
- configurations: F2-66, F2-78, F2-134, F2-86 (Family 2, indices of the frozen 144-configuration family)
- candidate hash salt: `shadow-f2`; first forward cut 2026-10-02 22:15 UTC
- tests behind this freeze: test_contracts, test_portfolio, test_integrity, test_signal_leak, test_f2_signals, test_forward_shadow (A: forward pipeline = research
  pipeline for 4,852 champion sets; B: truncation at a cut leaves 4,620 champion sets unchanged), scratch runs (28 rows, idempotent second run, tamper detection).
