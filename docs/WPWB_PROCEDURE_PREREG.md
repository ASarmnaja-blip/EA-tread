# WPWB procedure test — pre-registration (DRAFT v0, under debate, NOT frozen)

Written by Claude 2026-09-28 after Codex's methodology review
(`docs/CODEX_METHOD_REVIEW_2026-09-28.md`, Ledger Parts 41-42). This draft is
sent to Codex for adversarial review before anything is frozen or run. The
debate is recorded in `docs/WPWB_DEBATE_2026-09-28.md`. No order, EA change
or PR is authorised.

## 1. The claim under test

WPWB's claim is about a **procedure**, not a fixed rule: *each Friday, using
only past data and weighting recent weeks most, choose which tool(s) to run
next week (or stand aside); tools may change every week.* The question:

> Does that adaptive weekly choice deliver better next-week results than
> choices that carry no information about the coming week?

Calendar eras are diagnostics, not gates. A rule may change sign across eras
and still count, if the procedure switched it correctly.

## 2. The procedure P (to be frozen after debate)

- **Menu:** the 40 frozen tools of the closed search (`research/wpwb_search`,
  rounds 1-3, parameters unchanged), each producing a weekly net P&L series
  (bp, Demo90 base costs incl. long swap) for every week 2021-07..2026-09.
  Plus "flat" (0).
- **Risk normalisation (past-only):** each tool's week-w P&L is divided by the
  sd of that tool's weekly P&L over weeks w-26..w-1 (floor: tools with fewer
  than 8 active weeks in that window are ineligible at w). So every tool is
  judged per unit of its own recent risk.
- **Score at cut w:** decay-weighted mean of the tool's normalised P&L over
  weeks < w (last 26 weeks, half-life h).
- **Action:** hold the top-k tools by score, equal risk weight, if their score
  > 0; otherwise flat. Procedure outcome at w = mean of chosen tools'
  normalised P&L at w.
- **Hyper-parameters tuned inside, past only (nested):** h in {3, 8, 13}
  weeks x k in {1, 3} = 6 settings. At each cut w, P uses the setting whose
  OWN prequential outcome over weeks w-26..w-1 (each of those weeks computed
  with information before that week only) has the highest mean. Warm-up:
  the first 52 weeks produce no evaluated outcome.

## 3. Primary test — selection-aware placebo

Placebo = the entire procedure P run identically, but each week's chosen
tools are scored on the outcome row of a **different** week: week w's picks
are evaluated at week w+s (circular), for every shift s with 13 <= s <=
N-13. This keeps which tools P tends to pick (and hence their long-drift and
risk profile) while destroying the link between the information P used and
the week it is applied to.

- Statistic: mean weekly normalised outcome of P over evaluated weeks.
- p = (b+1)/(B+1), b = number of placebo shifts with mean >= P's mean.
- **Historical gate: p < 0.05.** This single primary hypothesis is the only
  one this pre-registration tests. The history 2021-2026 has been mined
  repeatedly (Parts 18-42), so a pass is **development evidence only**: it
  makes P a candidate for the forward shadow (section 6), nothing more.

## 4. Diagnostics (reported, never gates)

- P vs equal-weight all eligible tools (1/N, non-adaptive) and vs a risk-
  normalised always-long.
- By era (2021-07..2023-12, 2024-01..2026-09), by rebuild-volatility tercile,
  by chosen family; turnover (tool changes per week); leave-one-26-week-
  block-out stability of the mean.
- 1.5x cost stress; share of weeks flat.
- Which hyper-parameter setting was active, and how often it changed.

## 5. Statistics housekeeping

- Add-one p-values everywhere; no raw b/B.
- Nothing here reuses `common.block_boot`'s tail at tiny thresholds.
- No price-filtered event sets (none are used here).

## 6. Forward confirmation (only if section 3 passes)

Freeze P (code hash). Every Friday 22:15 UTC from 2026-10-02 the shadow
records P's choice and next week's outcome. Promotion requires an anytime-
valid sequential test (e-process on the weekly outcome vs the placebo-
expected outcome, alpha 0.05 spent once, project-wide alpha ledger in
`docs/ALPHA_LEDGER.md`). A 26-week safety review is not confirmation unless
the evidence threshold is reached.

## 7. Known weaknesses I (Claude) already see — to be debated

- The menu is the closed search's 40 tools, all of which failed individually;
  a procedure over weak tools may just be noise.
- Shifts s are limited to ~247 distinct values: p resolution ~0.004.
- Week-to-week persistence of direction traces measured ~0 (Part 31); if
  tool performance also does not persist, P should fail — which is the point.
