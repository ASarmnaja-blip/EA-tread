# Logic ledger — every gate, every win, every loss, and why

Compiled 2026-09-26, at the operator's direct instruction, to give the system
"well-rounded logic about what happened and why" across every amendment. This
is a reference, not a new finding: every row below points at the amendment,
document or run that established it. Nothing here is guessed; where a cause is
unconfirmed it is marked NOT ASSESSED rather than asserted.

**How to read this**: each row is one gate or one measurement. "What it checks"
is the mechanical rule. "What it found" is the number. "Why" is the causal
account, stated only as far as it is actually established — many rows say
"not established beyond this" rather than inventing a mechanism.

---

## Part 1 — the closures (setups/tools that were tested and rejected)

| # | what was tested | gate / what it checks | what it found | why (only as far as established) |
|---|---|---|---|---|
| 05/06 | `ORDERLY_TREND v2` scale-aware regime, pullback entry, 1.5 ATR stop, 2R target | dev period must beat holdout; cross-asset pooled lower bound must be above zero | dev +0.0853 R, holdout −0.1359 R. Cross-asset pooled +0.1693 R, HK interval [−0.2158, +0.5545] | interval straddles zero — not enough evidence either way, not "proven wrong," just unproven. XAGUSD alone carried 36% of the pooled weight |
| 07/08 | 24 hand-built patterns, then re-scored against a direction-matched placebo | raw expectancy vs. matched-control excess | raw shorts looked like losers; against the matched control the "loser" gap collapsed to near zero (excess +0.0067 to +0.0112 R where raw was −0.03) | gold rose ~126% over the sample. A random short lost −0.0507 R and a random long won +0.0656 R from drift alone — larger than any pattern's own long-short gap. The patterns were reading the drift, not information |
| 09 | 150 "junk" indicator configurations, inverted | matched excess must clear −0.092 R and pass step-down maxT | best excess −0.2278 R, p(maxT) 0.799 (not significant) | none beyond chance at the family level |
| 10 | 6,480-cell wide screen, 40 tools, both tails | max\|t\| and Berk-Jones vs. permutation null; CONFIRM on an untouched slice | tier A max\|t\|=2.425 vs critical 3.697 (p=0.854); nominal discoveries ran at 0.60x what pure chance produces; **all five CONFIRM winners flipped sign** | the family is quieter than chance, not merely inconclusive. A winner selected from 6,480 candidates regressed *through* zero on fresh data, not toward it — the textbook signature of picking the extreme of a noisy pile |
| 11 | holding horizon swept 12→576 M5 bars (1h to 48h), same tools | does any horizon reveal a hidden signal Amendment 10 missed | no horizon significant (p 0.58–0.85 against Bonferroni α=0.0071) | ruled out horizon-length as the hidden variable. Horizon mismatch is real but tiny (ρ=+0.10, p=0.015) and does **not** explain the two watchlist survivors it was invoked for |
| 13 | geometry-neutral path diagnostic (MFE/MAE/efficiency, no fixed stop) | does the tier-A aggregate show *any* exploitable path shape | flat at every horizon tested | the setups carry no information about the path shape either, not just about the fixed 1.5R/1:1 barriers used elsewhere |
| 17 | session acceptance/rejection at Asia, pre-London, prior-day levels, touch count 1st/2nd/3rd+ | ordinal touch-count slope must be negative and significant | slope +0.00008 R, one-sided p=0.4990 against MDE 0.03503; net negative at every ordinal after cost | mechanism ("later touches are weaker") not established; touch means were not even monotone |
| 20 | annual-expanding walk-forward, one Amendment-19 arm selected each January, held all year | forward-year net R after the selection | 2022 no ready arm (correctly NO_TRADE); 2023 −10.532 R; 2024 −22.938 R; 2025 −16.637 R; 2026-to-date +3.830 R (thin, PF 1.011). Combined **−46.277 R** | the arm chosen from prior-year evidence lost money three years running. A recent winner is not shown to survive the next year's regime |

---

## Part 2 — what is still open, and exactly why it is not yet a candidate

| id | what | the gate it failed | the number |
|---|---|---|---|
| **W1** `gap_continuation/short` | rollover-gap continuation, mechanical, no fitting | not yet judged — its own execution-hour slippage has never been measured | net +0.2573 R at measured cost (1x), dies at 7x. Blocked on one measurement scheduled for the next weekday rollover window |
| **W2** `rsi:40/short`, `emax:50-200/long` | two configurations that survived a stratified re-score | trade count (33, 47 vs. required 50) and step-down maxT (p=0.961, 0.899) | mirror net +0.1838, +0.1424 R, cost-robust to 7x — but the sample is too small to trust, and Amendment 11 ruled out the one explanation (horizon mismatch) that would have made their loss non-invertible either way |

---

## Part 3 — the 44-month diagnosis and its refinement (this session)

### First pass: annual buckets (`docs/DIAGNOSIS_44_MONTH_LOSS_2026-09-26.md`)

| era | % of grid cells net-positive | gold's own return that year |
|---|---:|---:|
| 2022 | 23.8% | −0.4% |
| 2023 | 24.8% | +12.9% |
| 2024 | 31.3% | +27.1% |
| 2025 Jan–Sep | 42.0% | +40.4% |
| trailing 12 months | 59.1% | +18.5% |

**Direct finding:** gold trended hard in 2023–2025 (more, cumulatively, than in
the trailing 12 months), yet the fixed rule grid failed on 71–76% of its own
cells in every one of those years. **This is closer to "the scope could not
read that market" than to "gold was not rallying."**

### Second pass, at quarterly resolution (`research/pilot/diagnose_grid_by_quarter.py`) — corrects the first pass's shape

The annual view understated how noisy the series actually is. At quarterly
resolution:

```
2021Q1 55%  Q2 17%(worst on record)  Q3 22%  Q4 23%
2022   Q1 29%  Q2 33%  Q3 22%  Q4 36%
2023   Q1 34%  Q2 24%  Q3 27%  Q4 33%
2024   Q1 30%  Q2 33%  Q3 34%  Q4 47%
2025   Q1 34%  Q2 41%  Q3 46%  Q4 56%
2026   Q1 53%  Q2 55%  Q3 53%
```

Linear trend across all 23 quarters: slope +1.18 percentage points/quarter,
**R² = 0.435** — a real trend component, but less than half the variance is
explained by a straight line. The series was **volatile, not climbing, for
roughly four years** (2021Q2 through 2025Q2, bouncing between 17% and 47%
with no clear direction quarter to quarter), and only the **last five
consecutive quarters** (2025Q3 through 2026Q3: 46%, 56%, 53%, 55%, 53%) show a
sustained plateau clearly above the noise band of the prior four years.

**Correction to the first pass's framing:** "a smooth four-year climb" was an
artefact of annual averaging smoothing over quarter-to-quarter volatility.
2021Q1 alone hit 55% and was immediately followed by 17%, the worst quarter on
record — a single good quarter carries no information by itself. What is
distinctive is five quarters in a row above 45%, which the prior four years
never produced even once.

**Why this recent plateau exists: NOT ASSESSED.** It is consistent with either
a genuine, sustained change in market conditions that suits these mechanical
rules, or with an extended favourable run inside a noisy process — five
data points cannot distinguish those, and no attempt is made here to assert
one over the other.

### Data-ceiling finding (this session)

An attempt was made to extend the usable history further back than
2021-01-03, per the operator's request to use "every piece of data." MT5
returns bars for XAUUSD M5 requests back to 2016-08-09, but direct inspection
showed **roughly one bar per calendar day at 00:00:00 UTC with spread = 0** —
placeholder daily data mislabelled as M5, not real intrabar quotes. The
attempt to build an extended canonical file correctly failed at the existing
validator (`canonical_history.validate` rejects non-positive spread). No
corrupted file was produced; the attempt's temporary files were removed.

**Codex's original constant (`START_YEAR = 2021` in
`historical_regime_walkforward.py`) was correct, not an unchecked
assumption — verified here, not merely inherited.** 2021-01-03 is the genuine
data ceiling for this instrument on this broker. Going further back would
require a different data vendor, which the project has avoided before for
comparability reasons (the GC=F/Yahoo confusion recorded earlier in this
project's history) and is not attempted without the operator's explicit
decision to accept that trade-off.

---

## Part 4 — what "more data" can and cannot do here, restated plainly

The mechanical rules in the grid (breakout, pullback, sweep, failed-breakout,
VWAP-reversion, expansion, at fixed stop/target/timeframe/entry-mode
combinations) have **no parameters that update from data**. Feeding them more
history does not make the *rules* smarter — an `if breakout of 20-bar range
then buy` rule means the same thing whether it is computed over one year or
ten.

What more (trustworthy) data *does* do, and is the actual mechanism already
built for this in Amendment 19:

- gives the **recency-weighted selector** (21-day half-life exponential
  weighting) a longer, better-documented track record of which of the fixed
  rules has recently been working, so its "current best guess" is built on
  more evidence
- gives statistical questions like "is this improvement real or noise" **more
  independent time buckets** to be tested against — which is exactly why the
  quarterly re-run above is more informative than the annual one, without
  requiring a single additional day of new data
- lets a genuinely new candidate's forward evidence be judged against a longer
  baseline of what "normal" looks like

What more data will **never** do on its own: turn a fixed IF-THEN rule into
something that learns, or turn noise into signal by re-averaging it into
smoother-looking buckets.

---

## Part 5 — single-tool reselection at fine geometry (2026-09-26)

`research/pilot/fine_grid_walk.py`: six families × five timeframes × 15 stops ×
20 targets = 9,000 geometries, market entry, real Demo cost. Each month the
single best geometry of the prior three months was carried forward.

| layer | result |
|---|---|
| in-sample ceiling (best geometry of each month, with hindsight) | +2.09 R/month average. Many winners had only 3–10 trades, so this is inflated by small samples |
| walk-forward (prior three months → next month, no look-ahead) | first run printed −0.1207 R/month over the 56 months that traded. Counting the 9 zero-trade months as 0 gives **about −0.10 R/month, about 34% of months positive** |

**Why:** the best single tool of the recent past did not carry into the next
month. This is the third time the project has measured this, after Amendment 20
(annual) and Amendment 10 (6,480 fixed cells).

**Operator's decision after this result:** do not fix on a single tool. Run a
basket and size it to a 35–40% maximum drawdown. That work moves to Codex-led
co-development (`docs/OWNERSHIP.md`, fifth revision).

The corrected rerun, which counted zero-trade months and added a
≥10-trade ceiling, was stopped before it finished when the operator changed
direction. The −0.10 figure above is arithmetic on the first run's printed
output, not a completed rerun.

---

## Part 6 — the multi-tool basket (Amendment 23, 2026-09-27)

Codex's decay-weighted basket of 3–5 tools, reselected every Weekend Rebuild.
It **fails** the pre-registered test: the 44-month window turns −80.991 R at
1.5x cost. Claude's recheck matches every figure.

| window | gross edge / trade | cost share of that edge | median stop |
|---|---:|---:|---:|
| 2022-01 → 2025-09 | +0.1308 R | 90.0% | $2.60 |
| last 12 months | +0.1686 R | 32.7% | $5.11 |

**Why it lost:** the selector found a gross edge in both periods. In the lower
volatility of 2022–2025, the roughly fixed dollar cost ate 90% of it.
**This revises Part 3's "the scope could not read that market"**: the edge was
there, but too small relative to cost at that volatility. Details are in
`docs/AMENDMENT_23_RESULT.md` and `docs/AMENDMENT_23_RESULT_REVIEW_CLAUDE.md`.

---

## Part 7 — late same-direction re-signals lose (2026-09-27) — **WITHDRAWN, see Part 8**

Found while reviewing Amendment 24 (`research/pilot/resignal_test.py`,
covering all 8,250 cells and about 47 million raw signals).

When a tool's trade is still open and the same tool fires **again in the same
direction**, that second signal is a late entry into a move already under
way.

| | gross R per signal | win rate |
|---|---:|---:|
| signal from a flat tool | −0.011 | 44.8% |
| same-direction re-signal while a trade is open | **−0.098** | 38.3% |

The penalty is about −0.08 to −0.09 R in 2021, in the 44 months and in the
last 12 months, in every timeframe, and in five of six families. It is
largest for breakout (+0.047 → −0.238 R). Sweep is the one exception.

**Guideline:** skip a tool's same-direction signal while that tool's
shadow position is still open. Track that shadow position whether or not
the tool is in the basket. This rule is causal and can run live.

This also explains Amendment 24: its "fidelity fix" removed exactly this
filter, which turned the Amendment 23 replay from +62 R into −251 R over the
44 months. Claude's review is what recommended that fix; the correction is
in `docs/AMENDMENT_24_RESULT_REVIEW_CLAUDE.md`.

---

## Part 8 — look-ahead in the signal-order chain (2026-09-27)

**Part 7's guideline is withdrawn.** Most of it came from a look-ahead in the
per-cell chain used by `mtf_engine.run_cell`, `walk_forward.build_universe`
and `basket_gate._cell_history`.

**What goes wrong:** in limit-entry modes, the chain walks fills in *signal*
order. An earlier signal's limit order can fill *after* a later signal's fill.
The chain then rejects that later fill, although no position was open when it
happened. It rejects it only because it already knows the earlier order will
fill later. That later fill usually means price kept moving against the
trade, so the rejected fill tends to be a loser. The chain was removing
future losers.

| | n | gross R |
|---|---:|---:|
| fills rejected out of order (only possible with limit entry) | 3.34M | **−0.331** |
| market entry, same-direction re-signal | 2.88M | −0.026 |
| market entry, fresh signal | 2.78M | −0.051 |

With market entry, where out-of-order fills cannot happen, a same-direction
re-signal is **not worse** than a fresh signal. A smaller penalty remains on
in-order re-signals in limit modes (−0.060 against −0.005 R). Whether that
part is real is NOT ASSESSED.

**Contaminated until re-run on a causal chain (size of the effect unknown):**
Amendments 14, 15/16, 21 (+248.785 R), 23 (+62.070 R and its cost
decomposition), `compound_bar_replay.py`, Amendment 24's candidate
histories, and Parts 3 and 6 of this ledger.

**Not affected:** Part 5 (market entry only) and W1.

The details and the required fix are in `docs/AMENDMENT_25_REVIEW_CLAUDE.md`.

---

## Status

Everything above is read-only against existing data and Codex's paused,
unmodified cache. No real-money order sent. No open position. No PR. **NO
TRADE.**
