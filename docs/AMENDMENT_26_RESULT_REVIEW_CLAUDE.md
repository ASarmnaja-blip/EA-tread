# Amendment 26 result — Claude's review

**Written 2026-09-27.** Codex's Amendment 26 measurement is accepted: all
audits passed. Codex's out-of-order count, **3,344,875**, matches Claude's
independent count exactly. A23 and A24 both fail their unit-risk gates on the
causal chain.

Review also found that Amendment 21's apparent survival does not hold on the
current engine. **No policy tested so far survives the corrected engine plus
the causal chain over the full history.**

## Verified

- Codex's run reproduced the A23 and A24 legacy references exactly. The
  market-entry identity audit passed on every cell. The A21 provenance
  explanation is recorded rather than forced.
- Claude reran A21's frozen weekly rules through Codex's own `_a21_run`
  (`research/pilot/recheck_a21_current_engine.py`). Codex's metrics and
  Claude's trade-by-trade sums agree exactly.

## Amendment 21 on the current engine

Amendment 26 measured A21 on the frozen `a67cca7` engine. That was the right
way to isolate the chain effect. But that engine predates two corrections,
and both can only make results worse:

1. same-bar target credit after an intrabar limit fill
   (`allow_entry_bar_target`)
2. buy limits filled on the Bid low rather than on Ask

On the current engine with Demo90 costs:

| A21 rules | 44 months | trailing 12 months | full history |
|---|---:|---:|---:|
| legacy chain, base / 1.5x | −2.543 / −27.474 R | +32.805 / +28.604 R | −34.603 / −73.337 R |
| **causal chain, base / 1.5x** | **−34.145 / −55.117 R** | **+3.495 / +1.788 R** | **−90.517 / −120.448 R** |
| a67cca7 engine, causal (Amendment 26) | +94.711 R | +169.829 R | +248.225 R |

**About +338 R of A21's full-history result came from the old engine's fill
and target optimism, not from the chain.** The chain then removes a further
~56 R. A21's +248.785 R is not evidence of an edge.

## Where things stand

| policy, current engine + causal chain | 44 months | trailing 12 months |
|---|---:|---:|
| A21 weekly single champion | −34.1 R | +3.5 R |
| A23 decay-weighted basket, base / 1.5x | −121.8 / −175.0 R | +5.3 / −13.5 R |
| **A24 basket + friction gate, base / 1.5x** | −80.4 / −109.1 R | **+31.6 / +18.0 R** |

Only A24 is positive in the trailing 12 months at **both** costs (PF 1.066 /
1.037, MTM DD −11.3 R). It loses over the 44 months, so it fails its own
registered gate. All of this is development data: A24 was designed after
Amendment 23's result, and the trailing year has been seen.

## What remains trustworthy

Clean:

- Claude's fine-grid walk (market entry, current engine): about
  −0.10 R/month forward
- W1 (its own resolver, market entry)
- the causal A21/A23/A24 figures above

Contaminated and not re-measured:

- Amendment 14's grid statistics
- the Amendment 15/16 walk-forward
- `compound_bar_replay.py`
- Claude's era and quarterly diagnoses

## Implication for the operator's goal

The operator's first rule is "beat the current market only." On clean
measurement, the only candidate positive in the current regime is A24 on the
causal chain, and that result was seen before this review. Historical replay
cannot confirm it further. **The only honest test left is forward
observation**: freeze A24 on the causal chain in a new amendment, then log it
read-only for the pre-registered 26 weeks. A Demo run of that frozen policy
would also serve.

**NO TRADE.** No order sent by Claude or Codex, no PR.
