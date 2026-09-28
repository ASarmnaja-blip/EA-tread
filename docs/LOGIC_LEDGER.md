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

## Part 17 — win rate and net R across all stop widths, M1-corrected (2026-09-28)

Closes the RR=1:1 investigation (Parts 13-16) with one table: every trade
(not just ties) in expansion/M5, RR=1:1, LONG, by stop ATR, win rate and net
R/trade both full-period-original and M1-corrected on the identical
M1-covered subset.

| stop ATR | winrate, M1-covered, original | net/tr, original | **winrate, M1-corrected** | **net/tr, M1-corrected** |
|---:|---:|---:|---:|---:|
| 0.75 | 40.9% | −0.3290 | 42.4% | −0.3005 |
| 1.00 | 44.8% | −0.2157 | 45.1% | −0.2086 |
| 1.50 | 47.7% | −0.1208 | 47.7% | −0.1192 |
| 2.00 | 48.0% | −0.0956 | 48.0% | −0.0953 |
| 3.00 | 50.7% | −0.0243 | 50.7% | **−0.0239** |

**Update — the flipped SHORT side, same method, all five stops:**

| stop ATR | LONG win% M1-fix | LONG net/tr M1-fix | SHORT* win% M1-fix | SHORT* net/tr M1-fix |
|---:|---:|---:|---:|---:|
| 0.75 | 42.4% | −0.3005 | 21.1% | −0.7250 |
| 1.00 | 45.1% | −0.2086 | 30.5% | −0.5009 |
| 1.50 | 47.7% | −0.1192 | 43.5% | −0.2045 |
| 2.00 | 48.0% | −0.0953 | 47.4% | −0.1074 |
| 3.00 | 50.7% | −0.0239 | 47.9% | −0.0787 |

(*SHORT is the flipped simulation of the same LONG entries, not a real
signal.)

The LONG-vs-SHORT gap narrows steadily as the stop widens, and in the raw
full-period numbers it actually **crosses over** at 2.0-3.0 ATR (SHORT's
full-period win rate edges ahead: 49.2%/50.2% vs LONG's 44.8%/47.5%). But
**in the M1-covered recent period specifically, LONG stays ahead at every
single stop width, with no crossover.** Consistent with the recent-regime
drift favouring longs (gold's strong uptrend in the recent period) outweighing
whatever the older, flatter 2021-2022 era contributed to the full-period
SHORT numbers. The single best cell in either table remains LONG at 3.0 ATR,
recent period: −0.0239 R/trade.

**Guideline:** win rate climbs toward 50% and net R toward zero smoothly as
the stop widens - at 3.0 ATR (the widest in the declared grid) this specific
slice is within a hair of breakeven in the recent (M1-covered) period. The
M1 tie-correction itself matters only at narrow stops (+0.0285 R at 0.75 ATR)
and is negligible by 2.0-3.0 ATR (+0.0003-0.0004 R), consistent with Part 16's
tie-rate table falling to near zero over the same range. The recent period
outperforms the full-history average at every stop width tested, consistent
with Parts 3, 9, 10 and 15.

This does not establish a positive edge anywhere in this table - the closest
result (3.0 ATR, M1-corrected) is still negative. It is a clean, complete
picture of how far the wider-stop / recent-regime effects already found
tonight can take a single narrow slice, nothing more.

---

## Part 18 — RR sweep to 1:10, both stop and target varied, finance conversion (2026-09-28)

**Source:** `research/pilot/rr_sweep_finance.py` (72 cells: stop ATR in
{0.75, 1.0, 1.5} x target R in {1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0,
8.0, 9.0, 10.0} x {LONG real, SHORT* flipped}), `data/rr_sweep_finance.xlsx`.
Same expansion/M5 signal set as Parts 13-17. Time stop extended from 288 to
8,640 M5 bars (30 calendar days) so distant targets can resolve; `timeexp%`
was 0.0% in every one of the 72 cells, so the extended window was never
itself the binding constraint. M1-covered subset ties corrected exactly as
before. Finance: XAUUSD minimum 0.01 lot = 1 oz, so $1 P&L = 1.0 price-unit
move.

**Headline finding — the first genuinely positive cells of the whole
session:**

| stop ATR | RR | side | win% (M1-fix) | net R/tr (M1-fix) | $ total (M1-fix) |
|---:|---:|---|---:|---:|---:|
| 1.0 | 1:6 – 1:10 | LONG | 16.0% → 11.7% | +0.0115 → **+0.1712** | +1,777 → +2,408 |
| 1.5 | 1:4 – 1:10 | LONG | 22.5% → 12.0% | +0.0492 → **+0.2414** (peak +0.2066 @ 1:7, $+3,230) | +2,100 → +3,230 |

SHORT* (flipped) stayed negative across essentially the entire sweep at
every stop/RR combination — no crossover here, unlike Part 17's RR=1:1
table. Full grid detail in the Excel file / `data/rr_sweep_finance_out.txt`.

**Concentration check (`research/pilot/check_concentration.py`), stop=1.5,
RR=1:7, LONG, the single best cell:** n=6,397, 1,024 wins / 5,373 losses,
mean win $24.77, mean loss $-4.12. Top 20 winning trades (of 1,024) contribute
48.5% of total profit; top 5 contribute 13.0%; top 1 contributes 2.6%. **Not**
dominated by one or two lucky trades - the positive average survives a look
at the tail.

**Two reasons this is NOT a confirmed edge, stated plainly:**

1. **This is an unregistered 72-cell parameter sweep**, and picking the best-
   looking cell out of 72 after the fact is exactly the pattern Amendment 10
   already proved fails on unseen data (a winner chosen from 6,480 candidates
   regressed through zero, not toward it). Nothing here was pre-registered
   before running.
2. **The trade count is inflated by cross-entry-mode duplication.** The
   concentration check's top-10 list showed six trades at the *identical*
   timestamp (2026-03-10 01:05) and *identical* dollar value ($83.86) - the
   same underlying price move counted once per entry-mode variant (o0e0 plus
   ~10 limit variants), not six independent signals. `n=6,397` therefore
   overstates the number of independent market events behind this result;
   the true independent-event sample is smaller than reported and has not
   yet been measured.

**Before this cell (or any other in the sweep) can be treated as a
candidate:** dedupe trades to independent entry bars/events, pre-register the
specific stop/RR/direction combination in isolation, and confirm on a forward
or otherwise-unseen period - the same bar every other finding tonight has
been held to.

---

## Part 19 — Part 18's positive cells are directional drift, not a setup edge (2026-09-28)

**Source:** `research/pilot/check_fake_edge.py`. Follow-up on Part 18's two
open concerns (unregistered sweep, duplicated n). Both are now resolved -
the second more damningly than expected.

**Dedup result:** collapsing to one row per unique entry bar (dropping
duplicate rows fired by different entry-mode variants on the same bar)
shrinks the sample far more than a rounding correction:

| stop ATR | n reported in Part 18 | n after dedup (unique bars) |
|---:|---:|---:|
| 1.0 | 14,103 | **1,292** |
| 1.5 | 13,674 | **1,269** |

The independent-event sample behind Part 18's numbers is about 1/11th of
what was reported - consistent with 11 entry-mode variants tagging the same
underlying bar.

**Fake-edge test:** built an unconditional random-entry baseline of the same
size, same window (M1-covered period), same stop, ATR(14) computed directly
on M5 - any bar, always LONG, market fill, zero relationship to the
expansion setup. Ran the identical RR sweep on both:

| stop | RR | net R/tr, real (deduped) setup | net R/tr, random baseline |
|---:|---:|---:|---:|
| 1.0 | 1:7 | −0.0344 | **+0.0110** |
| 1.0 | 1:10 | +0.0461 | **+0.1410** (random wins) |
| 1.5 | 1:4 | +0.0245 | −0.0392 |
| 1.5 | 1:7 | +0.1420 | +0.0687 |
| 1.5 | 1:10 | +0.1995 | +0.1538 |

The random baseline turns positive at essentially the same RR levels as the
real setup, and at stop=1.0 it **outperforms** the real setup at every RR
from 1:6 upward. This is the standard signature of directional drift, not a
timing edge: in a window where gold trended up steadily (already flagged in
Parts 3, 9, 10, 15), *any* sufficiently-wide-target long trade looks
profitable, regardless of when it was entered.

**Verdict: Part 18's positive net-R cells (stop=1.0 LONG RR>=1:6, stop=1.5
LONG RR>=1:4) do not represent a setup-specific edge.** They are consistent
with pure long-side market drift over the M1-covered period. The expansion
setup's entry conditioning adds no measurable value over picking entries at
random once the target is wide enough not to get stopped out - if anything,
at stop=1.0 the setup's timing is slightly worse than random. This
supersedes the "may be worth pursuing" framing in Part 18; treat those cells
as **confirmed fake edge**, not a candidate, unless a genuinely different
test (e.g. de-trended/detrended-return version of this same comparison, or
a forward period with a different regime) says otherwise.

---

## Part 20 — MT5's real usable history depth, and Part 19's test repeated in a flat window (2026-09-28)

**MT5 history depth**, probed directly against the live terminal
(`Exness-MT5Trial7` demo, login 434191008) via the `MetaTrader5` python
package - not an assumption:

| timeframe | real continuous data starts |
|---|---|
| M1 | **2023-11-27** (matches `data/XAUUSD_M1.csv`) |
| M5 | **~2021-01** (2016-2020 exists but is sparse - 100-700 bars/year, not usable) |
| M15 / H1 / D1 | 2016-08-09 |

So M5-level backtesting is only reliable from 2021 on, and tick-quality
(M1) modelling only from 2023-11-27 on. This bounds every M5-grid finding
in this ledger to that window, and it is the same bound Strategy Tester
would face if this were run there.

**Flat-period repeat of Part 19's fake-edge test.** `find_flat_period.py`
ranked every calendar month from 2021-01 by trend efficiency ratio
(|net move| / sum|bar-to-bar moves|; near 0 = chop, near 1 = one-way
trend), restricted to MT5's real-data window. May-June 2025 is the
flattest *consecutive* two-month stretch inside the M1-tick-quality period
(efficiency 0.001 and 0.001 individually, 0.0020 combined).

`check_fake_edge_flat.py` reran Part 19's real-vs-random comparison
restricted to that window (n=82-88 deduped signals per stop - small, noisy,
but the pattern is what matters):

| stop | RR | net R, real setup | net R, random baseline |
|---:|---:|---:|---:|
| 1.5 | 1:1 | −0.1968 | +0.0361 |
| 1.5 | 1:4 | −0.3188 | −0.0005 |
| 1.5 | 1:7 | −0.3675 | −0.1590 |
| 1.5 | 1:10 | −0.1115 | −0.2322 |
| 1.0 | 1:10 | −0.3254 | −0.1854 |

**No cell turns positive.** Unlike the trending M1-covered window, wider RR
does not rescue net R here - if anything it gets worse for the real setup
(win% collapses toward 7-9% by RR 1:7-10, chop keeps clipping the stop
before a distant target is ever reached). This is the expected signature if
Part 19's diagnosis is right: remove the drift, and the "edge" has nothing
left to stand on.

**Caveat stated plainly:** n=82-88 is too small for precise numbers: this
is not a second confirmed result, it is a directional check that is
consistent with Part 19 and does not contradict it.

**Not done:** this remains a Python simulation against cached history, not
an actual MT5 Strategy Tester run - the `MetaTrader5` package used to probe
history depth can read data and (per the demo-only order permission) place
orders, but cannot drive the Strategy Tester GUI from this session. No EA
in this repo implements the "expansion" setup tested tonight, so there is
nothing yet that could be loaded into Strategy Tester for this specific
finding even if the GUI step were done manually.

---

## Part 21 — Current market (as of 2026-09-21) is flat, not trending; scope check (2026-09-28)

**Source:** ad-hoc trailing-window efficiency check (same ratio as
`find_flat_period.py`), against the canonical M5 history's latest bar.

User asked whether Parts 18-20's setup could be used now on the premise
that "gold isn't flat right now" (unlike the May-June 2025 test window).
Checked directly instead of assuming:

| trailing window (from 2026-09-21) | net move | efficiency ratio |
|---:|---:|---:|
| 14d | −59.4 (−11.7 ATR) | 0.009 |
| 30d | −254.0 (−47.8 ATR) | 0.017 |
| 60d | +264.3 (+53.2 ATR) | 0.009 |
| 90d | +253.7 (+50.9 ATR) | 0.006 |
| 180d | −207.1 (−37.8 ATR) | **0.002** |

Direction flips sign across windows (down 14d, down 30d, up 60-90d, down
180d) - chop, not a sustained trend. The 180-day efficiency (0.002) equals
Part 20's flat test window (0.0020) almost exactly. **The premise was
false: the current market is at least as flat as the window already shown
to give Parts 18-20's setup no edge.** Even setting that aside, "trending
implies usable" was never a valid inference from Part 19 either way - Part
19 showed random entries matched or beat the real setup inside a genuine
trend, meaning a trend being present doesn't make the *setup* useful; it
would only make being-long-with-a-wide-target-of-any-kind look profitable,
which is a directional bet on trend persistence, not a validated edge.

**Scope note:** this whole RR-sweep / fake-edge detour (Parts 13-21) was a
deep-dive on one narrow question (why does flipping one RR=1:1 bucket lose
more, and is the resulting RR-sweep result real) that grew well past the
original question. Per the user's instruction, work returns to the CLAUDE.md
mission (section 9: read what the market currently rewards, build the
Adaptive Current-Regime Signal Engine, per section 5's recent-data
windowing) rather than continuing to extend this detour further.

---

## Pre-registration — setup survey vs random baseline, current (flat) regime (2026-09-28)

**Registered BEFORE running**, per this project's standing rule against
searching until something looks good (Amendment 10).

**Hypothesis:** Part 21 established the current market (trailing 180d as
of 2026-09-21) is flat/choppy, efficiency ratio 0.002. In a flat regime,
mean-reversion-style setups (`vwap` = VWAP/value-area reversion, `failed`
= failed breakout) should show a real edge over the Part 19-style random-
entry baseline; continuation-style setups (`breakout`, `pullback`) should
NOT, since they structurally need a trend that Part 21 shows is not
currently present. `expansion` and `sweep` are excluded - already shown
dead (Parts 18-21 and CLAUDE.md item 9 respectively).

**Setups:** `vwap`, `failed` (primary hypothesis - expected to show edge),
`breakout`, `pullback` (negative control - expected to show none).

**Grid:** the already-declared M5 grid only, no extension - stop ATR in
{0.75, 1.0, 1.5, 2.0, 3.0} x target R in {0.5, 1.0, 1.5, 2.0, 3.0}, time
stop 288 M5 bars (24h, the grid's own default) - not the 30-day extension
used for the abandoned RR>3 sweep.

**Window:** trailing 180 days from the latest bar (2026-09-21), i.e.
~2026-03-25 onward - chosen because Part 21 already measured this exact
window as uniformly flat (0.002), and it is long enough to give a less
noisy sample than the 82-88-trade May-June-2025 window used in Part 20.

**Method:** identical to Part 19 - dedupe real signals to one row per
independent entry bar, build an unconditional random-entry baseline of the
same size/window/stop, compare win% and net R/trade, LONG only (the setups'
own declared direction, not a flipped simulation).

**Success criterion, stated in advance:** a setup counts as a candidate
worth investigating further only if its net R/trade beats the random
baseline by a clear margin across MULTIPLE target values at a given stop
(not one cherry-picked cell), and the direction of the gap matches the
mean-reversion-in-chop hypothesis. A result that only beats random at one
isolated cell, or that beats random by roughly the same amount `breakout`/
`pullback` do, is not a candidate - same standard Parts 18-19 were held to.

---

## Part 22 — setup survey result: hypothesis rejected, no family clears the bar (2026-09-28)

**Source:** `research/pilot/check_setup_survey.py`, `data/setup_survey.csv`.
Executes the pre-registration immediately above. Window: trailing 180 days
from the latest bar, 2026-03-25 to 2026-09-18 (5,780,349 M5 bars checked
for signals; n=449-3,329 deduped independent entries per stop, real
declared direction, not flipped).

**Result at stop=0.75 (all 5 targets, gap = net R real − net R random):**

| setup | 0.5R | 1.0R | 1.5R | 2.0R | 3.0R |
|---|---:|---:|---:|---:|---:|
| vwap (predicted to win) | −0.121 | +0.004 | +0.140 | +0.221 | +0.267 |
| failed (predicted to win) | −0.076 | +0.027 | +0.173 | +0.194 | +0.206 |
| breakout (control) | −0.102 | +0.017 | +0.139 | +0.214 | +0.233 |
| pullback (control) | −0.062 | +0.032 | +0.149 | +0.185 | +0.227 |

All four setups - both the mean-reversion pair predicted to win and the
continuation pair used as a negative control - produce essentially the
same gap curve: negative at 0.5R, crossing positive by 1.0-1.5R, growing to
+0.19 to +0.27 by 3.0R. Same shape holds (with smaller magnitudes) at
stop=1.0/1.5/2.0/3.0; full table in the CSV.

**Verdict against the pre-stated success criterion: hypothesis rejected.**
`vwap` and `failed` do not beat random by a margin distinguishable from
`breakout`/`pullback` - the exact "gaps similar in size to the continuation
setups = noise, not edge" disqualifier written into the pre-registration.
The rising-gap-with-target pattern is a property of this specific 180-day
window shared by any reasonably-sized subset of entries (real or random),
not a property of any one setup's detection logic.

**Standing implication:** combined with `sweep` (dead per the original
CLAUDE.md appendix) and `expansion` (dead per Parts 18-21), **none of the
6 setup families in the cached research grid (`sweep`, `expansion`,
`vwap`, `failed`, `breakout`, `pullback`) has now survived a real-vs-random
check.** `breakout` and `pullback` were only ever run here as a control,
not evaluated on their own terms - that remains open, but nothing found so
far suggests they would fare differently.

---

## Part 23 — Regime Stability Score v1 (CLAUDE.md gap #2, first cut) (2026-09-28)

**Source:** `research/pilot/regime_stability_score.py`. User pointed out
that the CLAUDE.md 9-point scope already names the tool that should answer
"is the table hot or did the setup actually play well" - a working Regime
Stability Score (item 2), rather than a one-off random-baseline script each
time. Starting to build it from what already exists: `Regime.mqh`'s
`Classify()` logic (ported to Python 1:1, same constants as
`MQL5/Include/XAUM15/Config.mqh`: EMA 50/200, ATR(14), 100-bar ATR-percentile
lookback, compression/slope/vol thresholds) plus the efficiency-ratio
diagnostic validated in Parts 20-22.

**Deliberately reads FRESH data from the live MT5 terminal**, not the
frozen `data/canonical_XAUUSD_M5.npz` snapshot that every other Part in
this ledger cites by sha256 for backtest reproducibility - a *current*-
regime score needs current data, and freezing it would defeat the purpose.
Confirmed live as of 2026-09-28 04:00 UTC (`MetaTrader5` package, same
Exness-MT5Trial7 demo terminal probed in Part 20).

**v1 score definition:** % of the last 100 M15 bars (matching
`InpAtrRegimeLookback`) classified with the SAME discrete regime label as
the current bar. High = the label has held, adjust slowly (CLAUDE.md
section 4). Low = the label is flipping, adjust fast.

**Current reading (2026-09-28 04:00 UTC):** regime=**TREND_DOWN**, ATR
percentile 64.0, **Regime Stability Score = 22.0%** (10 label changes in
the last 100 M15 bars). Efficiency ratio near zero at every trailing window
(14d 0.034, 30d 0.033, 60d 0.009, 90d 0.009, 180d 0.009) - consistent with
Part 21's flat-regime finding, not a strong trend. Both signals agree: the
TREND_DOWN label should be treated as unstable/low-confidence right now,
not acted on directly.

**Explicitly NOT included in this v1** (still open against CLAUDE.md item
2): correlation with DXY/yields, liquidity proxies, narrative/positioning,
recent setup performance. This is price-structure + volatility only -
labelled honestly as a first cut, not a finished Regime Stability Score.

---

## Part 24 — WPWB's own champion selector confirms Parts 18-22 by an independent method (2026-09-28)

**Source:** re-ran the existing (Amendment 21, "explicitly not yet
promoted") `research/pilot/weekly_evolution_grid.py` fresh against the
canonical history. Context: user redirected focus to WPWB (Wednesday
Report / Weekend Rebuild, `docs/AMENDMENT_22_WEEKLY_OPERATING_PROTOCOL.md`
+ its rule-9 addendum). This selector draws its weekly "champion" from the
**same 8,250-cell, 6-setup-family grid** (`sweep`/`expansion`/`vwap`/
`failed`/`breakout`/`pullback`) that Parts 18-22 tested tonight - not a
different pool.

**Result, 2021-01-03 to 2026-09-21, 290 weekly rolls:**

- **213/290 = 73.4% weekly champion-change rate** - reproduces the 73%
  figure Codex flagged in Amendment 21/`docs/CODEX_COLLAB_2026-09-27.md`
  exactly.
- Forward performance of the selected champion each week: 1,223 trades,
  net **−32.246R**, mean **−0.0264R/trade**, win 30.0%, PF 0.964, max
  drawdown −110.263R.
- **Built-in same-week ranking control (top-ranked cell vs the median-
  ranked cell, same week): top beats mid by only +0.0042R, and only in
  49.7% of weeks** - statistically indistinguishable from a coin flip.
  Both top and mid are net negative (−0.0491R and −0.0533R respectively).

**Why this matters:** rule 9's own random-look-alike test says the same
thing Parts 19/22 said with an unconditional random-entry baseline, but
here it comes from WPWB's own walk-forward selector, on the actual full
history, using a completely different method (LCB shrinkage score, 56-day
selection, 7-day forward test) - **two independent methods now agree**: the
weekly "champion" is not distinguishable from an arbitrary cell in this
pool, because the pool itself carries no real edge. The 73% churn is not a
tuning defect (e.g. the missing decay-weighting flagged in Amendment 22
§3.1) by itself - a selector cannot reliably find and hold a winner inside
a pool where there is nothing to find.

**Implication for WPWB:** decay-weighting `weekly_evolution_grid.py`'s
56-day window (Amendment 22 §3.1) is still worth doing for its own sake,
but it will not fix the churn or the negative forward result on its own,
since the underlying grid has no distinguishable edge regardless of how
the window is weighted. The blocking problem is upstream: **WPWB has no
tool in its current candidate pool worth selecting.** This matches
`docs/OWNERSHIP.md`'s already-stated next step ("a new pre-registered
design attacking the actual open problem... since gating on cost/R alone
was not enough") - tonight's finding is independent evidence for why that
next step is necessary, not a replacement for it.

---

## Part 25 — existing news acceptance/rejection test also fails at development (2026-09-28)

**Source:** `research/pilot/news_acceptance_edge.py` + `research/pilot/
results/news_assessments.csv` - pre-existing code, not written tonight.
User asked for a genuinely new setup family (not a re-test of the six dead
ones); this one already exists in the repo, already pre-registered with a
70/30 dev/holdout split on event epoch, already using a non-circular
design (only information available 1 minute after a USD HIGH release: XAU's
first-minute reaction, DXY's first-minute reaction, surprise z-score - no
5/15/60-minute hindsight value as an input).

**Ran it as-is, no changes:**

```
M1 NEWS REACTION - NON-CIRCULAR  events=150  holdout starts 2025-10-16
accept dev   n=80  E=-0.0026R  win=46.2%  CI=[-0.2588, +0.2517]
reject dev   n=25  E=-0.0722R  win=44.0%  CI=[-0.5277, +0.3982]
DECISION FAIL: neither mechanism passes development (needs n>=20 and
  95% bootstrap CI lower bound > 0)
```

Neither the "acceptance" (price continues the hypothesized direction) nor
"rejection" (price reverses it) mechanism clears its own pre-registered
development bar - both CIs straddle zero widely. **Reported as a clean
failure, not modified or re-tuned to pass** - changing this design post-hoc
to search for a positive result would be exactly the pattern this project
prohibits (Amendment 10). If a news-based setup is still wanted, it needs a
genuinely different, freshly pre-registered mechanism, not a parameter
tweak on this one.

**Standing count:** `sweep`, `expansion`, `vwap`, `failed`, `breakout`,
`pullback` (Parts 18-22) and now `news acceptance/rejection` (this Part) -
**7 of 7 setup ideas tested against a real pre-registered bar in this
project have failed.** CLAUDE.md item 8 updated.

---

## Part 26 — moving the setup survey to M15 does not reveal a hidden edge either (2026-09-28)

**Source:** `research/pilot/check_setup_survey_m15.py`, `data/
setup_survey_m15.csv`. User asked directly whether cost was killing the
setups and, if so, whether widening ATR would fix it. Answered with Part
17's own numbers (net R improves from -0.30 to -0.02 as stop widens 0.75
to 3.0 ATR) - cost is a real, sizeable drag - but Parts 18-22's random-
baseline gap never separates real from random at any width, meaning
widening the stop reduces cost drag for real and random equally without
creating distinguishable edge. User then asked to move the whole survey to
M15, where the timeframe's own naturally larger ATR reduces the fixed-
dollar cost's share of R without artificially stretching the ATR multiplier.

**Correctness note:** the M5 survey's random baseline reused the M5 ATR(14)
array for both real and random entries, which was fair because M5 setups
also use M5-scale ATR. Real M15 setups use M15-scale ATR (larger), so this
script builds an M15-ATR-aligned-to-M5-bar-index array via `mtf_engine.
resample` + `core.atr` for the random baseline instead - reusing the raw M5
array here would have unfairly inflated the random baseline's cost drag
and made real setups look relatively better for a spurious reason. Sanity-
checked against real streams' own `atr` values: ~8.7% mean relative
difference (a reasonable approximation, not exact - the streams' own ATR
computation pipeline was not fully reverse-engineered).

**Result at stop=0.75 (gap = net R real - net R random, M15-scale ATR
throughout, time stop scaled to 72h to match M15's 3x M5 multiplier):**

| setup | 0.5R | 1.0R | 1.5R | 2.0R | 3.0R |
|---|---:|---:|---:|---:|---:|
| vwap | −0.120 | +0.024 | +0.133 | +0.112 | +0.212 |
| failed | −0.094 | +0.023 | +0.088 | +0.147 | +0.098 |
| breakout | −0.136 | +0.027 | +0.080 | +0.072 | +0.073 |
| pullback | −0.041 | +0.018 | +0.011 | +0.011 | +0.018 |

Same signature as the M5 survey (Part 22): all four setups rise from
negative to positive with target distance, all four track each other in
magnitude, and the ranking is not stable across stops (at stop=1.0,
`pullback` - a continuation control - shows the largest gaps of all four,
+0.057 to +0.095, while `vwap`/`failed` are flat-to-negative there). No
setup clears Part 22's pre-registered bar (consistent, real, above-control
separation across multiple targets).

**Verdict:** moving to M15 does not reveal a hidden edge suppressed by
cost on M5. The rising-gap-with-target pattern persists at the new
timeframe and ATR scale, reinforcing Part 22's diagnosis that it is a
property of the market window shared by any similarly-sized entry subset,
not something cost was masking. Cost is a real drag (confirmed, sizeable)
but is not the reason these 7 setup ideas have no edge - removing or
reducing it does not create one.

---

## Part 27 — WPWB champion vs a TRUE random baseline, and a multiple-comparisons probe (2026-09-28, in progress)

**Source:** `research/pilot/champion_vs_random_wpwb.py` and `research/
pilot/champion_challenger_v1.py`, both building on Part 24. User asked
whether the random-entry methodology (Parts 19/22) had been applied to
WPWB's actual selector, and pointed out Part 24's control (champion vs the
median-ranked cell, BOTH still drawn from the same 8,250-cell pool) is
weaker than a genuinely unconditional random baseline, since the median
cell could share whatever pool-wide drift effect inflated Parts 18-22's
apparent edges.

**Result 1 - champion vs true random, at the CURRENT (uncorrected,
shrink=0.75) selector, matched week-by-week to whatever stop/target/tf was
actually champion:**

```
champion (top-ranked cell), real forward trades:
  trades=1223  net_R=-32.246  mean_R=-0.0264  win=30.0%  PF=0.964
matched UNCONDITIONAL random baseline (same weeks/stop/target/tf, random
bar + random direction, zero relationship to the setup grid):
  trades=1242  net_R=-98.621  mean_R=-0.0794  win=27.5%  PF=0.897
champion mean_R - random mean_R = +0.0530R/trade
```

This gap (+0.0530R) is **larger** than Part 24's within-pool champion-vs-
median gap (+0.0042R) - the champion clearly beats true random even though
it is itself still net negative. **Open question, not yet resolved:** does
this reflect real selection skill, or does the median cell (any grid
member) ALSO beat true random by a similar margin, in which case the gap
would be a property of grid membership (the same drift artifact from Parts
19/22), not of the LCB-based selection step? A second run, adding the
median cell's own matched-random comparison for a clean three-way split,
is in progress at the time of this entry - result to follow in a later Part.

**Result 2 - multiple-comparisons probe.** `champion_challenger_v1.py`
reran the identical selection loop at several LCB shrinkage multipliers
(0.75 = current/uncorrected, up to ~4.65 = an approximate Bonferroni
correction for ~8,250 simultaneous weekly comparisons at alpha=0.05):

| shrink | active weeks | trades | net_R | mean_R | win% |
|---:|---:|---:|---:|---:|---:|
| 0.75 (current) | 100.0% | 1223 | −32.246 | −0.0264 | 30.0% |
| 2.00 | 97.6% | 1714 | +60.883 | +0.0355 | 38.6% |
| 3.00 | 62.8% | 1553 | **+128.935** | +0.0830 | 46.2% |
| 4.00 | 25.5% | 726 | +74.171 | +0.1022 | 59.6% |
| 4.65 (~Bonferroni) | 15.2% | 340 | +36.509 | +0.1074 | 65.9% |
| 5.50 | 5.9% | 80 | +1.148 | +0.0143 | 68.8% |

Net R and win% both rise sharply and roughly monotonically as the
selection bar is corrected for testing ~8,250 candidates a week - a
striking result, and explicitly **NOT YET TRUSTED**, for reasons stated
plainly before any further interpretation:

1. **This is itself an unregistered sweep across 6 shrink levels**, and
   reporting shrink=3.00 as "the good one" after seeing all six results is
   exactly Amendment 10's prohibited pattern. No shrink level was
   pre-registered before this ran.
2. Active weeks fall to 15.2%/5.9% at the higher shrink levels - small
   samples (340/80 trades) at exactly the levels with the highest win%.
3. **Not yet checked: whether the surviving active weeks at high shrink
   cluster in the same recent trending period (2024-2025) already shown to
   fake a positive edge via drift** (Parts 18-22). If they do, this is the
   same artifact wearing a new face, not a second, independent discovery.

**Nothing here is a finding yet.** Recorded promptly per this project's
practice of logging every attempt, positive-looking or not, before it is
verified - not after cherry-picking survives review. Next steps before any
conclusion: (a) the median-vs-its-own-random three-way split already
running, (b) a time-distribution check of which weeks survive at
shrink=3.0/4.65, and (c) only then, if still positive, applying the same
Part 19/22-style random-baseline check to the specific chosen shrink level
rather than to the uncorrected selector.

**Addendum - the three-way split (a) has now run**, at the current
uncorrected (shrink=0.75) selector:

| | trades | mean_R | vs its OWN matched random |
|---|---:|---:|---:|
| champion (top-ranked) | 1,223 | −0.0264 | **+0.0534** |
| median-ranked cell | 4,730 | −0.1006 | **+0.0270** |
| champion − median (trade-weighted, pooled) | | +0.0742 | |

Both champion and median beat their own matched random baseline - grid
membership alone carries some of Parts 19/22's drift-artifact advantage,
confirming the concern was not unfounded. But champion's edge over random
(+0.0534) is roughly **2x** median's edge over random (+0.0270): the
LCB-based weekly selection appears to add something beyond mere grid
membership, not nothing - though not enough to make the champion itself
net positive at the current, uncorrected threshold. This trade-weighted
comparison (champion −0.0264 vs median −0.1006, gap +0.0742) differs from
Part 24's week-weighted comparison (+0.0042, a coin flip) because the
median cell fires roughly 4x as often per week as the champion cell
(4,730 vs 1,223 total trades over the same 290 weeks) - a real
methodological difference in aggregation, not a contradiction: Part 24
answers "in a typical week, is champion an equally good bet as median";
this answers "across all individual trades taken, does champion's trade
stream outperform median's." Both are legitimate questions with different
answers.

**Reading so far: not clean fake edge, not clean real edge either** - a
small, genuine-looking selection effect that is not yet large enough to be
profitable at current settings, which would be consistent with why
correcting for multiple comparisons (result 2 above) reveals more of it.
Still pending before any conclusion: the time-distribution check (b).

**Addendum - the time-distribution check (b) has now run
(`research/pilot/check_shrink3_time_distribution.py`), and it resolves the
question decisively: this is the same drift artifact, not a new finding.**

| year | active weeks | approx weeks in year | approx pass rate |
|---|---:|---:|---:|
| 2021 | 17 | ~43 (partial, starts Jan 3) | ~40% |
| 2022 | 22 | 52 | ~42% |
| 2023 | 25 | 52 | ~48% |
| 2024 | 33 | 52 | ~63% |
| 2025 | 47 | 52 | ~90% |
| 2026 (through Sep) | 38 | 38 | ~100% |

The pass rate at shrink=3.0 climbs monotonically from ~40% in 2021 to
~100% in 2026 - **not** a stable, time-independent rate that would support
a genuine, regime-robust selection skill. It tracks gold's sustained
uptrend through 2024-2026, the exact period Parts 18-22 already
established makes almost any sufficiently-selected long-biased cell look
falsely positive. 44.0% of all active weeks fall in just 2024-2025 (about
35% of the calendar span), and adding the 2026 partial year pushes it
higher still.

**Verdict: Part 27's positive-looking results (both the champion-vs-random
gap exceeding median's, and the multiple-comparisons-corrected net R
turning sharply positive) are the same directional-drift artifact from
Parts 18-22, reappearing through the weekly selector rather than through a
single fixed setup.** The selector is not discovering skill when corrected
for multiple comparisons - it is more reliably finding *whatever recently
rode the prevailing trend*, which is abundant in 2025-2026 and scarce in
2021-2022. This is consistent with, not a contradiction of, every prior
finding tonight: **8 of 8 things tested in this entire session (7 setup
families/mechanisms plus this multiple-comparisons-corrected selector) show
no edge that survives a genuine trend-independence check.**

---

## Part 28 — pooled similar-regime sample: the strongest-sample test yet, same verdict (2026-09-28)

**Source:** `research/pilot/find_similar_regime_periods.py` and
`research/pilot/check_setup_survey_similar_regime.py`. User's point,
stated directly: design/test a setup against data matching the CURRENT
regime, not an arbitrary window, and if measuring, measure against a
similarly-regimed period - correctly identifying that Part 20's flat-period
test (n=82-88) was too small to trust on its own.

**Finding similar periods:** using the current reading (regime_stability_
score.py, Part 23: ATR percentile ~64, efficiency ratio 0.009-0.034) as the
target, scanned all 272 weeks of the full canonical history for weeks
matching efficiency <= 0.05 and ATR percentile in [40, 85]. **145 weeks
(53.3% of the full 2021-2026 history) matched, spread evenly across every
year** (2021:15, 2022:31, 2023:32, 2024:27, 2025:25, 2026:15) - explicitly
checked and confirmed NOT concentrated in the 2024-2026 trending period
that inflated every earlier "positive" finding tonight. This is a
genuinely time-robust "similar regime" pool, not a repeat of the drift
artifact.

**Result, pooled across all 145 weeks (n now in the thousands per cell -
e.g. `failed`/stop=0.75 has n=21,194, versus Part 20's 82-88):**

| setup | best gap (stop=0.75) | pattern |
|---|---:|---|
| vwap | +0.190 | negative at short target, rising to positive at long target |
| failed | +0.249 | same shape |
| breakout | +0.196 | same shape |
| pullback | +0.245 | same shape |
| **expansion** | **negative at every cell (−0.013 to −0.375)** | consistently worse than random in this regime type |

**vwap/failed/breakout/pullback still show the identical rising-gap-with-
target signature, still cluster together with no setup separating from the
others** - now on a sample an order of magnitude larger than any earlier
test tonight, which makes the "shared window property, not setup skill"
diagnosis (Parts 22/26) considerably more solid, not less.
**`expansion` is new information: it underperforms random consistently in
this specific (moderate-chop) regime type** - plausibly because expansion/
breakout-continuation logic gets whipsawed in chop, unlike in the trending
window where Parts 18-21 found it looked (falsely) positive.

**Verdict against the standing pre-registered criterion (unchanged from
Part 22): no setup passes.** This is the methodologically strongest test
run tonight - largest sample, regime-matched, time-robust across all six
years - and it reaches the same conclusion as every smaller/narrower test
before it. The user's suggested refinement (test like-for-like regime,
pooled properly) was sound and worth doing; it just does not change the
answer.

---

## Part 29 — WPWB edge search, round 1: 0 of 20 pass DEV (2026-09-28)

**Source:** `docs/WPWB_EDGE_SEARCH_PREREG.md` (committed before any run),
`research/wpwb_search/`. User instruction: search autonomously across
multiple approaches for a WPWB-fitting edge, self-check, present only the
final result for a pass/fail verdict. Design: 5 structurally new approaches
(weekly TS momentum, hour-of-day and day-of-week seasonality retuned
weekly, regime-gated H1 reversal with ungated twin, weekend gap
fade/follow), 20 variants, DEV 2021-07..2023-12 (130 weeks), HOLDOUT
2024-01..2026-09 sealed. Controls: random direction, always-long, random
timing, all as exact expectations under identical costs.

Self-checks that fired and were fixed before any approach ran: the
pre-registered block-4 bootstrap gave p<0.05 in ~9% of null runs; replaced
by max(circular-block-8, Newey-West-8) against a halved threshold (true
size 3.3-5.0% measured). A run from the wrong working directory was
refused by the data loader rather than silently using non-canonical data;
the runner now pins cwd and asserts the canonical snapshot.

Pipeline sanity: planted oracle detected (p=0.0000), coin-flip rejected
(p=0.163), leaky tool caught by the look-ahead audit (13/25 cuts); all 20
real variants 0 audit failures. **Result: 0 of 20 DEV-eligible.** Closest:
HOD W=52 T=3.0 beat its controls weakly (min t +1.40) but was net negative
after costs (−3.36 bp/week at 1.5x); CHOPREV z=2.5 net positive (+2.90
bp/week) but min t +0.43; regime gate added nothing. Weekly TSM negative at
every lookback in DEV. Holdout unopened. Round 2 pre-registered under a
declared cap (3 rounds, 50 variants, one holdout opening at the end).

---

## Status

Everything above is read-only against existing data and Codex's paused,
unmodified cache. No real-money order sent. No open position. No PR. **NO
TRADE.**
