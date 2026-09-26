# Amendment 22 addendum — rule 9, and where Weekend Rebuild actually sits

**Written 2026-09-26, at the operator's direct instruction, as a second
addendum to Amendment 22.**

## Rule 9, as given

> Historical trace data already encountered is organized as a standing
> guideline. Every piece of data ever received has value.

## What this changes about Weekend Rebuild, stated precisely

The operator clarified that **Weekend Rebuild is specifically the single
point** where:

1. data is adjusted/tuned for the current market, combined with every factor
   (calendar, CFTC, DXY/XAU state, and now the fine-grid walk below);
2. that combination is used to **forecast the coming week**, so the active
   tool has a higher chance of winning it; and
3. every trace of data ever produced by this process — every era's win/loss
   reason, every gate's result, every diagnosis — becomes a **permanent,
   accumulating guideline library**, never discarded, that future Weekend
   Rebuilds draw on.

This does not loosen rule 8's scope or any standing prohibition. It is a
statement of *where in the weekly cycle* tuning happens (only at the Weekend
Rebuild boundary, never mid-week) and *that nothing measured is thrown away*.

## The guideline library, named

From here, `docs/LOGIC_LEDGER.md` is the guideline library rule 9 describes.
Every Weekend Rebuild appends to it rather than replacing it:

- every closure's gate and result (already compiled)
- every diagnosis run (the 44-month loss diagnosis, the quarterly-resolution
  refinement, the data-ceiling finding)
- the fine-grid walk's per-period findings (`research/pilot/fine_grid_walk.py`,
  running as of this addendum) — this **is** the mechanism rule 9 and the
  operator's "ปรับจูนให้ชนะตลาดในช่วงนั้นๆ" instruction call for: a fine
  (not 5x5-limited) stop/target search per period, reported as both an
  in-sample ceiling (the guideline trace) and a walk-forward reality check
  (the honest forecast number), never only the former

## One alignment note, not yet resolved

The fine-grid walk currently reports at **monthly** resolution. Weekend Rebuild
operates **weekly**. Before this becomes the live Weekend Rebuild mechanism
rather than a diagnostic, the selection granularity needs to match the actual
weekly cadence - this is flagged here rather than silently mismatched, and is
the next step once the current monthly run's result is read.

## Status

No real-money order sent. No open position. No PR. Codex remains paused per
`docs/OWNERSHIP.md`. NO TRADE.
