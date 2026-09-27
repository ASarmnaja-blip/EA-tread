# Amendment 26 — Claude's pre-run review: APPROVED

**Written 2026-09-27, before any Amendment 26 code or result.** No required
changes.

## Why it is approved

- **Option (a) is the narrowest fix.** Fills are processed by fill bar, and a
  pending order blocks nothing until it fills. This removes the dependence on
  a future fill without introducing a different trading rule.
- **The defect-catching test (§3) is the right one.** The legacy chain must
  *fail* it as a negative control, and the run stops if it doesn't. This is
  the check that was missing from the 35-check engine suite.
- **A streaming oracle (§4)** proves that the fast event-sorted build is
  causal, rather than taking it on trust.
- **The market-entry identity audit (§8.6)** agrees with Claude's
  independent measurement: across every market-entry stream,
  `research/pilot/resignal_test.py` found zero out-of-order rejections, so the
  legacy and causal chains should match exactly there.
- **Scope is kept narrow.** Old references are reproduced before any
  comparison. Only the chain changes, and no Amendment 25 policy or new rule
  is appended. Success is defined as a valid measurement, not a profit.

## Requested cross-check (not blocking)

§10 reports "out-of-order legacy rejects". Please also report the count of
legacy-chain rejections, across all 8,250 cells and the whole canonical
history, where the rejected fill's bar comes **before** the blocking accepted
fill's own entry bar. Claude's script counts **3,344,875** (gross −0.3307 R,
net −0.4021 R). Agreement would show the two independent codebases are
measuring the same thing. A mismatch should be explained, not adjusted.

## Known contamination not re-measured here

Amendment 26 re-measures Amendments 21, 23 and 24. It does not re-measure:

- Amendment 14's published grid statistics
- the Amendment 15/16 walk-forward (its result was "the sample cannot answer";
  a look-ahead that inflates results would not rescue a null, but the figures
  are still contaminated)
- `compound_bar_replay.py`
- Claude's era and quarterly grid diagnoses

The result report should list these as **CONTAMINATED — NOT RE-MEASURED**, so
no future Weekend Rebuild treats them as clean.

**NO TRADE.** No order, no autotrader restart, no PR.
