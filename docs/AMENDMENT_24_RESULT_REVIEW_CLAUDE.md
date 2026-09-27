# Amendment 24 result — Claude's review

**Written 2026-09-27.** Codex's verdict stands as registered: **FAIL FOR
PROMOTION**, with DD sizing correctly not run. This review finds, however,
that the result's main interpretation needs correcting, and that the
correction traces back to a mistake in Claude's own earlier review.

## What was verified

- Codex's section 10 audits passed and the reproduction audit is sound. The
  9,906 trades both engines share have **identical** results (+77.723 R
  weighted in both).
- The +62 R → −251 R swing in the paired Amendment 23 44-month result comes
  entirely from trades that exist in only one engine:
  - trades only the old engine took: 2,037, weighted −15.653 R
  - trades only the new engine took: 2,820, weighted **−328.759 R**
    (`research/pilot/recheck_a24_state.py`)
- The new-only trades are not session-gap artefacts. They are spread across
  Monday to Friday, and only 13 sit on the first bar after a gap. Claude's
  first hypothesis, that Sunday-open trades were to blame, is withdrawn.
- They are resolved by the same `resolve_plane` as every other fill. Their
  shape is simply bad: gross **−0.372 R**, win rate 18.3%, 79% full-stop
  losses. Shared trades show +0.154 R and 33.5%.

## What the new-only trades are

Every new-only trade is a signal that fired while the same cell's previous
trade was still open. That previous trade may have been hypothetical, from a
week when the cell was not selected, or rejected by the risk budget. The old
continuous chain skipped these signals. Amendment 24's "state-fidelity fix"
takes them.

`research/pilot/resignal_test.py` checks this across **all 8,250 cells and
the whole history** (about 47 million raw signals). Output is in
`data/resignal_test_run.txt`.

| signal class | gross R/signal | net R/signal | win |
|---|---:|---:|---:|
| FREE: the cell's chain is flat | −0.0110 | −0.0893 | 44.8% |
| RE_SAME: an earlier trade is open, same direction | **−0.0975** | **−0.1648** | 38.3% |
| RE_OPPOSE: an earlier trade is open, opposite direction | −0.0034 | −0.0604 | 35.7% |

The RE_SAME penalty is about −0.08 to −0.09 R and holds in **every period**:

| period | FREE gross R | RE_SAME gross R | penalty |
|---|---:|---:|---:|
| 2021 | −0.038 | −0.114 | −0.076 R |
| 44 months | −0.016 | −0.103 | −0.087 R |
| trailing 12 months | +0.026 | −0.067 | −0.093 R |

It also holds in **every timeframe** (M5 through H4), and in five of six
families. It is largest for breakout (+0.047 → −0.238) and expansion
(−0.087 → −0.255). Sweep is the exception: there, RE_SAME is no worse than
FREE.

**Reading:** a second same-direction signal while the first trade is still
running is a late entry into a move already under way, and it loses. This is
a genuine market trace in the sense of rule 9, not an engine defect.

## Correction, including Claude's own error

The old continuous per-cell chain was **not a fidelity defect**. It is
causal, because whether a cell's earlier trade is still open is known at the
time. It can also be run live, by tracking one shadow position per cell
whether or not the cell is selected. In practice it worked as a filter
against late re-entries.

Claude's Amendment 23 review called it "a minor fidelity note" and suggested
fixing it. That was wrong. Codex's Amendment 24 implemented the suggestion
faithfully, and in doing so removed a filter worth roughly 0.09 R per
affected signal. The statement in `docs/AMENDMENT_24_RESULT.md` that
Amendment 23's result "does not reproduce on the corrected execution engine"
should read instead: **Amendment 23's result depended on an implicit
shadow-position re-entry filter, which is a legitimate, causal rule.**

## What this means

1. Amendment 24's registered verdict (FAIL) stands; nothing is re-scored after
   the fact.
2. The obvious next design pairs an **explicit shadow-state re-signal filter**
   with Amendment 24's friction gate. It must be pre-registered as a new
   amendment.
3. That design is informed by everything seen so far. Every historical window
   is now development data. Genuine confirmation can only come from weeks
   after the design is frozen.
4. The per-signal figures above are unweighted means over heavily
   overlapping signals, not independent observations. No significance level
   is claimed. What carries the weight is how consistent the penalty is across
   periods, timeframes and families.

**NO TRADE.** No order, no autotrader restart, no PR.
