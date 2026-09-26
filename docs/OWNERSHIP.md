# Who owns what — updated 2026-09-26 (fifth revision)

**Codex resumes from Sunday 2026-09-27 12:30 Asia/Bangkok. Claude and Codex
develop the project together**, at the operator's direct instruction. The
fourth revision (Codex paused, Claude runs everything) is superseded.

Revision history, kept visible: (1) Claude=W1 / Codex=rest, (2) Codex=all,
(3) Claude=W1 / Codex=rest, (4) Claude=all / Codex paused, (5) this one.

## The operator's target for this phase

1. **Not fixed to one tool.** Run a basket of several tools at once, chosen
   and re-weighted at each Weekend Rebuild. Selecting a single best tool per
   period is explicitly not what is wanted.
2. **Size the basket so its maximum drawdown lands at 35–40%.**
3. Stay inside the nine rules (Amendment 22 and its addendum).

## Split

| area | lead | the other agent's role |
|---|---|---|
| multi-tool basket engine (`current_edge*`, `payoff_*`, `weekly_evolution_grid.py`, `evolution_portfolio_audit.py`, `compound_bar_replay.py`) | **Codex** | Claude reviews each build before its result is reported: look-ahead, cost profile, zero-trade handling, tests |
| DD 35–40% sizing and the bar-by-bar portfolio replay | **Codex** | Claude independently re-checks the drawdown figures |
| Wednesday Report / Weekend Rebuild data collection (calendar, CFTC, DXY/XAU, sources) | **Claude** | Codex supplies the basket's own section |
| W1 | **Claude** | none |
| `docs/LOGIC_LEDGER.md` (the rule 9 guideline library) | both append, neither deletes | |

One owner edits a file at a time. Whoever did not write a result reviews it
before it goes to the operator.

## Standing rules, unchanged

- no real-money order without the operator's confirmation on that order
- Demo orders only under `data/DEMO_ORDER_PERMISSION.md`
- no Grid, Martingale or averaging
- no PR until evidence is ready to inspect
- NOT ASSESSED rather than a guess
- a change to Demo execution needs a verified walk-forward result
  (Amendment 22 §3.2)

The engine's answer remains **NO TRADE**.
