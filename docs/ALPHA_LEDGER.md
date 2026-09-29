# Project alpha ledger (DRAFT — becomes binding when the WPWB procedure pre-registration is frozen)

Purpose: one place that records how much forward (confirmatory) false-positive
budget the project has spent, so a failed hypothesis cannot be tweaked and
re-tested on the same stream for free (Codex review Q5, debate objection 13).

## Rules

1. **Scope.** Only forward, genuinely unseen weeks carry confirmatory weight.
   Everything on data up to 2026-09-28 is development evidence and spends no
   alpha — and earns none.
2. **Project forward budget: alpha = 0.05 in total**, across every
   hypothesis that could lead to promotion toward Demo execution testing.
3. Each hypothesis gets a named allocation before its first forward outcome,
   an exact test (e-process), a start timestamp and an evidence threshold
   1/alpha_i. The sum of allocations never exceeds the budget.
4. **Any material change** (menu, constants, benchmark, costs, code) makes a
   new hypothesis with its own allocation. It may not reuse forward weeks the
   old hypothesis already consumed.
5. Stopping a hypothesis (futility, safety) releases nothing: its allocation
   stays spent.
6. Promotion never authorises real-money orders; those still need the
   operator's explicit per-order confirmation (CLAUDE.md section 8).

## Allocations

| ID | Hypothesis | alpha_i | Threshold | Forward start | Status |
|---|---|---|---|---|---|
| H-WPWB-P1 | Selector P beats random eligible tool B' (docs/WPWB_PROCEDURE_PREREG.md v2) | 0 (was 0.025) | — | never started | **abandoned 2026-09-28 before outcome evaluation for inadequate prospective power; no outcome observed; alpha unspent** |
| H-WPWB-P2A | Volatility-state router (debate Round 3) | 0 | — | never started | **dropped 2026-09-28 (Codex Round 5): quoted power came from a different simulation; map partly outcome-informed; a future router is a new hypothesis** |
| H-BP-VWAP | vwap 4 h, top ATR third, diff vs matched control (Part 46) | 0 | — | never started | **dropped 2026-09-29 (Codex Round 7): p = 0.24 in DEV, best-of-22 on a mined sample; ~11-18 forward years needed; zero-alpha passive log at most** |
| (reserve) | unallocated | 0.05 | — | — | — |

Note on H-WPWB-P1: rule 5 (a stopped hypothesis keeps its alpha spent)
applies once a forward test has started. P1's allocation was only a draft in
an unfrozen ledger and no forward week was ever observed, so it returns to
the reserve (agreed by Codex, debate Round 3).
