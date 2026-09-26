# Who owns what — updated 2026-09-26 (fourth revision)

**Codex is PAUSED entirely. Claude runs everything from here**, at the
operator's direct instruction. Do not resume any Codex automation, scheduled
task, or in-progress thread until the operator says otherwise. The revision
history below is left visible rather than tidied away, so the sequence of
authority is auditable.

Prior revisions, in order: (1) Claude=W1 / Codex=rest, (2) Codex=everything
including W1, (3) reverted to Claude=W1 / Codex=rest. This revision supersedes
all of them: **Claude=everything, Codex=paused.**

## What is actually paused

- the `current-edge-wednesday-observation` automation
  (`target_thread_id 01a0c7ca-a090-7023-b04c-58cd07c14178`) — do not trigger its
  Wednesday or Saturday steps; Claude produces those reports manually until told
  otherwise (see `docs/WEEKEND_REBUILD_2026-09-26.md` as the template)
- `payoff_demo_autotrader.py` — do not start or restart it
- any further work on `weekly_evolution_grid.py`, `compound_bar_replay.py`,
  `evolution_portfolio_audit.py`, or the other uncommitted files from
  2026-09-22/23 — these stay exactly as found until the operator's current
  question is answered

## Standing rules, unchanged by this revision

- no real-money order, ever, without the operator's explicit confirmation on
  that specific order
- Demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime
- no Grid, no Martingale, no averaging
- no PR until there is evidence ready to inspect
- NOT ASSESSED rather than a guess, always
- the 120-day holdout, wherever one still exists, may be used for diagnosis
  and never for promotion
- every amendment's standing prohibitions carry forward unchanged

## W1

Unaffected by this revision; still Claude's, still waiting on the rollover
measurement scheduled for the next weekday window (Monday 2026-09-28 21:52 UTC).

The engine's answer remains **NO TRADE**.
