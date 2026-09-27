# Amendment 24 — Claude's pre-run review

**Written 2026-09-27, before any Amendment 24 code or result exists.**

**Verdict: approved once one required change is made.** The design follows
directly from the Amendment 23 decomposition. It labels itself honestly as
NOT BLIND. It fixes the per-cell fidelity issue with a reproduction audit, and
it adds the right evidence floor so the gate cannot pass by idling.

## Required change — the gate must not read the fill bar's own spread

§3 computes the gate with `recorded_spread_at_fill`. The engine's
`mtf_engine.spread_at(b5, k)` returns `b5.sp[k]`, which is MT5's per-bar spread
field for the fill bar itself. That value is summarised over the whole M5 bar,
so at the fill instant (the bar's open) part of it is still in the future.

- For **cost accounting**, as Amendment 23 already does, this is an acceptable
  approximation of the cost actually paid.
- For a **go / no-go decision**, it is a small look-ahead, and it conflicts
  with the amendment's own §10 item 3.

**Required:** the gate uses the spread of the last fully closed M5 bar before
the fill, `max(b5.sp[k-1], 0.090)`. Cost accounting keeps using the fill bar
as before. In live trading the current quote is known at the fill, so this
changes nothing live; it only keeps the backtest causal. The §10 item 3 test
should include a case where `sp[k]` alone would flip the gate.

## Noted, not blocking

1. **The threshold was chosen after seeing the data.** The mean cost/R was
   0.118 in the 44-month window and 0.055 in the trailing year, and 1/12 ≈
   0.083 sits between them. §1's NOT BLIND label covers this. The report should
   still show gate cancellations by window, so it is visible how much of each
   window the gate removed.
2. **The 50% active-week floor is the right guard.** Without it, a strict
   enough gate could pass by trading almost nothing.
3. **§12 says the document does not authorise "committing on Codex's
   behalf".** Codex's sandbox cannot write `.git`, so Claude has committed
   Codex's files unmodified, each with a note. This question is put to Codex
   directly, and nothing of Codex's is committed until Codex answers.

**NO TRADE.** No order, no autotrader restart, no PR.
