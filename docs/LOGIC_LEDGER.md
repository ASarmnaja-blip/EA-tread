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

## Part 9 — clean re-measurement: nothing survives the full history (2026-09-27)

Amendment 26 (Codex) and Claude's recheck reran the earlier policies on the
**current engine with the causal chain**. Clean figures:

| policy | 44 months | last 12 months |
|---|---:|---:|
| A21 weekly single champion | −34.1 R | +3.5 R |
| A23 decay-weighted basket, base / 1.5x | −121.8 / −175.0 R | +5.3 / −13.5 R |
| A24 basket with friction gate, base / 1.5x | −80.4 / −109.1 R | **+31.6 / +18.0 R** |

**Why the old numbers were high.** They stacked two separate optimistic
biases:

1. The signal-order chain looked ahead (Part 8).
2. The pre-correction engine credited same-bar targets after an intrabar
   limit fill, and filled buy limits on the Bid instead of the Ask.

A21's +248.785 R lost about 338 R to the engine corrections and about 56 R to
the chain.

**Guideline:** a result is evidence only when it comes from the current engine
with the causal chain. Anything built on the legacy chain or on the old
engine is contaminated until it is re-run.

**Current-market reading (rule 1):** A24 is the only candidate that is
positive at both base and 1.5x cost in the last 12 months. It loses over the
44 months, and its last-12-month figure is development data. The honest next
step is forward observation of a frozen A24.

---

## Part 10 — regime stand-aside helps but does not flip the 44-month verdict (2026-09-27)

Amendment 28 (Claude, ownership sixth revision): stand aside for the week
whenever the trailing-20-day H1 ATR sits below the 40th percentile of the
trailing year, computed causally at each Weekend Rebuild. Everything else is
A24 on the causal chain (Part 9), unchanged.

| window | A24 baseline, base/1.5x | A28 stand-aside, base/1.5x |
|---|---:|---:|
| 44 months | −80.4 / −109.1 R | **−69.5 / −93.4 R** |
| trailing 12m | +31.6 / +18.0 R | +31.6 / +18.0 R (identical — 0% stand-aside) |

Stood aside 19.1% of 44-month weeks, 0% of trailing-12-month weeks — almost
exactly where the hypothesis predicted, with no threshold sweep (0.40 frozen
before running).

**Guideline:** removing the quietest 40% of weeks recovers real R without
touching the working window, but the 44-month verdict is still negative at
1.5x cost. The edge-to-cost ratio in that regime is thin even after removing
its calmest weeks — this is a per-trade problem (e.g. volatility-scaled
targets), not just a which-weeks-to-trade problem. Untried; a candidate for a
future amendment.

Does not change Amendment 27's frozen forward policy.

---

## Part 11 — an independent sibling research program reaches the same verdict (found 2026-09-27)

Branch `claude/order-position-choch-gab-im08db` diverged from the same
ancestor as this branch (`33d7453`, 2026-09-10) and ran an entirely separate,
much larger research program: 1,677 hypotheses across a 9-14 market FX panel
(not gold-specific, `research/` not `research/pilot/`). Its last commit is
2026-09-19 — stopped mid-run, not an active concurrent session.

**Its final verdict:** "the information is real and worth 12% of what it
costs" — a genuine, reproducible short-horizon reversal (51.71% direction hit
rate, 9 of 9 panel markets) that transaction cost swallows 88-93% of. This
independently reproduces tonight's headline finding (Part 6: cost ate 90% of
gross edge in XAUUSD's low-volatility regime) from a completely different
method, on different markets. Convergent evidence the "real-but-cost-
dominated" pattern is not a XAUUSD-specific or method-specific artifact.

**A methodological warning that applies to every amendment tonight (23-29):**
that project found "R through a stop-and-target bracket is a neutral way to
measure directional information" was a false assumption throughout its own
first 837 hypotheses. R divides by an ATR-derived stop distance; a family
that fires preferentially on high-ATR bars gets a larger denominator for the
same price move, which can shrink or inflate R independent of real skill. A
claimed +0.0171R edge fell to +0.0026-0.0066 (negative for one family) once
the comparison control's geometry was matched properly.

**Every amendment in this project's basket work (23, 24, 26, 27, 28, 29) uses
exactly this same R-through-ATR-bracket measure, and none of them has tested
whether the six declared families fire preferentially on high-ATR bars.**
This is flagged as an open audit item, not yet checked. If it turns out our
families do skew toward high-ATR conditions, the whole cost-vs-volatility
story in Part 6/10 needs re-examination: some of what looked like "cost eats
more when volatility is low" could partly be this geometry effect running
the other way.

Not yet acted on tonight; recorded for the next amendment to address before
trusting the R-based figures further.

---

## Part 12 — the frozen A24 mechanism does not generalize to GBPUSD (2026-09-27)

Amendment 29 (Claude-led): the exact frozen Amendment 24/26 mechanism
(unchanged: six families, causal chain, 1/12 friction gate, decay/LCB
basket), applied to GBPUSD - genuinely new data, never inspected before -
with GBPUSD's own measured spread/commission/swap and two labelled slippage
scenarios (unmeasured).

**Negative everywhere, no exception:** full period −53.4/−97.8 R
(base/1.5x) at zero slippage, −49.1/−92.2 R at spread-equal slippage. Active
80.7–100% of weeks, so not an idleness artifact.

**Guideline:** this is consistent with, not contradicted by, Part 11's
independent finding that real cross-market structure can still lose money
after cost. It weakens rather than strengthens any case for skipping
XAUUSD's forward wait (Amendment 27): if the mechanism doesn't transfer to a
second market, that lowers confidence the XAUUSD result is a general
phenomenon rather than an XAUUSD-specific accident. Per the pre-registration,
no new design is registered tonight in reaction to this - repeatedly
adjusting after each unfavourable result on one fixed historical dataset is
the exact failure mode Amendment 10 already demonstrated.

Does not change Amendment 27's frozen forward policy or clock.

---

## Part 13 — why flipping a heavy RR=1:1 loser made it worse, not better (2026-09-28)

The operator asked to find the worst RR=1:1 (target R = 1.0) loser and flip
its direction. Worst bucket: `expansion/M5, stop=0.75 ATR, LONG`, 14,213
trades, net −0.5282 R/trade, win 36.0%. Flipped (same entry bar/ATR,
`resolve_plane` recomputed with reversed direction): net −0.7664 R/trade, win
24.1% — **worse, not the mirror-image winner a symmetric RR 1:1 should give.**

**Mechanism, found in `mtf_engine.resolve_plane` and verified empirically:**

```python
# a tie on the same bar goes to the stop: worst case, as core.resolve
if j_stop < len(adv_c) and j_stop <= j_tgt:
    out[(st, tg)] = (-1.0, "stop", j_stop)
```

When one M5 bar's range is wide enough to cross both the stop and target
threshold (a real possibility with a narrow 0.75-ATR stop on a family
literally selected for volatility *expansion*), the resolver cannot tell
which was touched first from bar data alone, and conservatively assumes its
**own** stop first. Applied independently per direction, this means a
same-bar tie is scored as a loss for **both** the original direction and its
mirror — not a win for whichever side the market actually favoured.

**Measured directly** (`research/pilot/verify_tie_asymmetry.py`): of 28,449
trades in this stop/target combination, **14.5% are exact same-bar ties**,
and of those, **100% also resolve as "own stop first" for the mirrored
opposite direction** — a clean, deterministic confirmation of the mechanism
(derivable algebraically: the mirrored stop/target crossing indices are
each other's target/stop indices, so the tie condition is symmetric).

**Guideline:** a heavy loser at RR 1:1 is not automatically an inverted
winner. Check the same-bar tie rate first, especially for narrow-stop,
high-volatility-selected setups — a high tie rate means the reported win
rate for BOTH directions is being conservatively deflated by bars the M5
data genuinely cannot resolve, and flipping does not undo that.

This affects every amendment that uses `resolve_plane` (all of them since
Amendment 14) whenever the stop is narrow relative to typical bar range. It
is a documented, deliberate conservative convention, not a bug - but its
consequence for direction-flip tests specifically was not previously
recorded.

---

## Part 14 — closing the tie-break investigation: real but small across the whole M5 grid (2026-09-28)

Part 13 found the conservative "tie goes to stop" convention charges a loss
to both directions on a same-bar ambiguity, and a zoom into one narrow-stop
bucket (`expansion/M5/stop=0.75`) found 1-minute data resolved 87% of its
ties as "target actually touched first". The operator asked to check this
across every M5 signal, restricted to the period M1 data covers, before
drawing a conclusion.

**Scope:** all 1,650 M5 cells (6 families x 5 stops x 5 targets x 11 entry
modes), causal chain, entries restricted to on/after 2023-11-20 (M1's first
bar) - 6,729,184 trades over about 2.85 years.

**The 87% finding does not generalize.** Same-bar ties are only 0.89% of all
M5 trades here (not 14.5% - that bucket's narrow 0.75-ATR stop was an
outlier), and of those ties, resolution at 1-minute data is close to even:
34.7% truly stop-first, 52.2% truly target-first, 13.1% still tied even at
one minute.

**Net effect of correcting every resolvable tie with real M1 data:**

| | net R/trade | win% |
|---|---:|---:|
| original (conservative) | −0.1051 | 43.7% |
| M1-corrected | −0.0969 | 44.1% |
| difference | **+0.0082** | +0.4pp |

Uniform across every family (+0.0069 to +0.0091 R/trade, no outlier).

**Guideline:** the conservative tie-break convention is real and costs about
0.008 R/trade on average - small but genuine, and it should be corrected in
any future engine revision. It does not rescue the grid: average performance
moves from −0.105 to −0.097 R/trade, still clearly negative. The dramatic
87% figure was a property of one extreme corner (narrowest stop, most
volatile family, limit-order entries specifically - Part 13's own
entry-mode breakdown showed market orders alone were close to a coin flip,
37.9/56.8/5.3), not a general phenomenon.

---

## Part 15 — final, fully-corrected verdict on the RR=1:1 flip (2026-09-28)

Closes the investigation opened in Part 13. The operator asked directly:
have the two original headline numbers (LONG −0.5282 R, flipped SHORT
−0.7920 R full-period, corrected from an earlier −0.7664 once entry-bar
target-credit exclusion for limit fills was matched to production exactly)
themselves been M1-corrected yet? They had not been - Part 13/14 corrected
the tie mechanism in general and across the whole M5 grid, but never
re-applied it to this specific bucket's own two numbers.

**Done, on the identical 6,611 trades (the 46.5% of this bucket inside M1
coverage, since correction requires M1 data):**

| | M1-subset, original | M1-corrected |
|---|---:|---:|
| LONG (real entries) | −0.3290 | **−0.3005** |
| SHORT (flipped, same entries) | −0.7407 | **−0.7250** |

**Verdict stands, now on its most solid footing:** flipping this heavy
RR=1:1 loser is still worse, not better, after every correction found
tonight (tie-break asymmetry resolved with real M1 data, entry-bar
target-exclusion matched to production for limit fills). The gap is large
(−0.30 vs −0.73 R/trade) and not an artifact.

**Also found:** this bucket's recent (M1-covered, post-2023-11) performance
is much better than its full-history average (LONG −0.33 vs −0.53
full-period) - one more data point consistent with the recent-regime
improvement pattern in Parts 3, 9 and 10.

---

## Part 16 — correction to Part 13's tie percentage, and the tie rate by stop ATR (2026-09-28)

**Correction.** Part 13's 14.5% tie rate and 87.1% target-first figure for
`expansion/M5/stop=0.75/target=1.0` were computed by
`verify_tie_asymmetry.py` and `zoom_m1_ties.py`, and **neither script applied
the entry-bar target-exclusion rule** (`resolve_plane`'s
`allow_entry_bar_target`, false for an intrabar limit fill) that production
uses. Both figures were overstated. `m5_m1_corrected_summary.py` (Part 14)
and `m1_correct_both_bucket.py` (Part 15) already applied this correctly, so
their conclusions stand; only Part 13's two specific numbers are revised.

**Corrected same-bar-tie percentage, expansion/M5, RR=1:1, LONG, by stop ATR:**

| stop ATR | trades | tie % (M5) | ties w/ M1 | stop-first % | target-first % | tied@M1 % |
|---:|---:|---:|---:|---:|---:|---:|
| 0.75 | 14,213 | **3.64%** | 203 | 40.4% | 46.3% | 13.3% |
| 1.00 | 14,103 | 1.47% | 85 | 62.4% | 27.1% | 10.6% |
| 1.50 | 13,674 | 0.28% | 20 | 35.0%* | 25.0%* | 40.0%* |
| 2.00 | 12,900 | 0.05% | 1* | 0%* | 100%* | 0%* |
| 3.00 | 11,405 | 0.02% | 2* | 50%* | 50%* | 0%* |

(*fewer than 30 samples - not statistically meaningful, shown for completeness)

**Guideline:** the tie rate falls off sharply and monotonically as the stop
widens - 3.64% at 0.75 ATR to 0.02% at 3.0 ATR - confirming this is
specifically a narrow-stop phenomenon, not a general one. At the one stop
width with enough resolved ties to read (0.75 ATR, n=203), target-first
(46.3%) and stop-first (40.4%) are close to even, not the extreme 87%/7%
split Part 13 originally reported.

---

## Status

Everything above is read-only against existing data and Codex's paused,
unmodified cache. No real-money order sent. No open position. No PR. **NO
TRADE.**
