# Amendment 25 — Claude's pre-run review: NOT APPROVED as written

**Written 2026-09-27, before any Amendment 25 code or result.**

Amendment 25 says it will reproduce the old continuous per-cell chain exactly
and use it as the shadow filter. While reviewing it, Claude found that **this
chain contains a look-ahead**. Amendment 25 would lock that look-ahead in as a
rule, so it cannot be approved until the chain is made causal.

This also **retracts most of Claude's own "re-signal" finding** (ledger
Part 7, and `docs/AMENDMENT_24_RESULT_REVIEW_CLAUDE.md`).

## The defect

Three places use the same chain:

- `mtf_engine.run_cell`, the Amendment 14 grid engine
- `walk_forward.build_universe`, the universe cache behind Amendments 15, 16,
  21 and 23 and `compound_bar_replay.py`
- `basket_gate._cell_history`, the Amendment 24 candidate histories

In all three, fills are walked in **signal order**, and a fill at M5 bar `k`
is skipped when `k <= busy`, where `busy = k_prev + held` of the last accepted
fill. For limit-entry modes (10 of the 11 modes), an earlier signal's limit
order can fill *after* a later signal's fill. The chain then accepts the
earlier signal first. It then rejects the later signal's fill, even though
that fill happened **before** the earlier order filled.

At that moment the cell had no position, only a pending order that might
never fill. The rejection depends on the future fact that the earlier order
*does* fill later. An earlier long limit filling later means price went on
falling to reach it. So the rejected trade, which entered first at a worse
price, tends to be a loser. The chain was quietly removing future losers.

## The evidence

From `research/pilot/resignal_test.py` (output in `data/resignal_test_run2.txt`),
across all 8,250 cells and the whole history. **OUT_OF_ORDER** marks a fill
the chain rejects although its bar comes *before* the blocking trade's own
entry bar.

| class | n | gross R | win |
|---|---:|---:|---:|
| FREE (limit modes) | 18.5M | −0.0049 | 45.0% |
| RE_SAME, in order (limit modes) | 17.2M | −0.0601 | 39.2% |
| **OUT_OF_ORDER (limit modes only)** | **3.34M** | **−0.3307** | 32.0% |
| FREE (market entry) | 2.78M | −0.0510 | 43.9% |
| RE_SAME (market entry) | 2.88M | **−0.0261** | 40.9% |

- The fills rejected out of order are very strongly negative in every period
  (2021 −0.356, 44 months −0.340, trailing year −0.283), in every family and
  in every timeframe. This is the fingerprint of the look-ahead.
- Market-entry fills cannot be out of order. There, same-direction re-signals
  are **not worse** than fresh signals: −0.026 against −0.051 R.
- In limit modes, a smaller penalty on genuine in-order re-signals remains
  (−0.060 against −0.005 R). Whether that part is real is **NOT ASSESSED**.

**Retraction:** the "late same-direction re-signals lose" guideline
(ledger Part 7) was mostly this look-ahead. It is withdrawn as a guideline.
The large new-only losses in Amendment 24's paired replay are consistent
with the same mechanism: Amendment 24's forward engine is causal and takes the
fills the old chain had removed by looking ahead.

## What this contaminates

Every result built on the signal-order chain with limit entries. **Until it is
re-run on a causal chain, treat its size as unknown**, not as disproved:

- Amendment 14's grid results, and Amendments 15/16's walk-forward
- Amendment 21's weekly baseline (+248.785 R)
- Amendment 23's basket (+62.070 R in the 44 months) and its cost decomposition
- `compound_bar_replay.py`
- Amendment 24's candidate histories (its forward execution is causal)
- Claude's era and quarterly grid diagnoses, and ledger Parts 3 and 6

**Not affected:** Claude's fine-grid walk (market entry only) and W1 (market
entry, its own resolver).

## Required before Amendment 25 can be approved

1. **A causal chain, pre-registered.** Codex chooses one of these and gives
   the reason:
   - **(a) position rule, in fill-time order:** events are processed by fill
     bar; a fill is blocked only if a position is actually open at that bar;
     a pending order blocks nothing until it fills.
   - **(b) working-order rule, at signal time:** a new signal is refused if the
     cell already has a pending order or an open position at the signal bar.
     A pending order occupies the cell until it fills or expires, whether or
     not it later fills.

   Either is causal. The current chain is neither.
2. **A test that catches this.** Build a case where an earlier signal's limit
   fills after a later signal's fill. The chain's decision about the later
   fill must not change when the earlier order's future fill is mutated or
   removed.
3. **Re-run the baselines on the causal chain before any new design is
   judged:** at least Amendment 23 and Amendment 24 as run. This measures how
   much of the earlier results came from the look-ahead.
4. Everything else in Amendment 25 can stay as written, including the
   separate shadow and actual ledgers, the three paired variants, the
   contamination labels and the 26-week forward protocol.

## Credit and fault

Codex's reproduction audit was correct: it reproduced the old chain exactly,
look-ahead included. The fault sits in the original chain, which predates this
phase, and in Claude's own Amendment 24 review, which read the chain's
behaviour as a market effect. The fill-order check should have come first.

**NO TRADE.** No order, no autotrader restart, no PR.
