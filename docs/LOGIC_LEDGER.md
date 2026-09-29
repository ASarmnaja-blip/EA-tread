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

## Part 30 — WPWB edge search closed: 0 of 40 pass, holdout never opened (2026-09-28)

**Source:** `docs/WPWB_EDGE_SEARCH_PREREG.md` (amendments 1-3, results
sections), `research/wpwb_search/run_round2.py`, `run_round3.py`,
`power_check.py`.

Round 2 (12 variants: hour-blocks merged into one position, UTC sessions,
daily reversal/follow retuned weekly, a WPWB meta-selector over the round-1
menu): 0 eligible. The meta-selector did worse than a random tool from its
own menu (min t −0.34 / −1.08) — the same selection-churn pathology Part 24
found in the old grid, now on structurally different tools. Round 3 (8
variants: swap-free intraday TSM, volatility-managed long vs exposure-
matched long, extreme-threshold H1 reversal): 0 eligible. A notable
cost fact surfaced along the way: on this account a week-long long pays
~14 bp of swap (0.5493/night at ~$1,900) while shorts pay nothing — larger
than most effects measured.

**Final: 0 of 40 pre-registered variants DEV-eligible across 12 families.
Holdout 2024-01..2026-09 never opened; it stays clean for any future
pre-registered test.** Power check: with 130 DEV weeks the pipeline detects
a 70%-accurate weekly direction 76% of the time but a 60%-accurate one only
22% and 55% only 4% — so large edges are ruled out among these ideas,
modest ones are not. Standing implication for WPWB: a modest real edge
could not be *statistically confirmed* within a few years of weekly data at
all; forward accumulation under a frozen rule is the only path, and a
26-week shadow is shorter still than the 130 weeks that could not.

---

## Part 31 — WPWB-live: current-era redo; what persists, and the one candidate (2026-09-28)

**Source:** `docs/WPWB_LIVE_PREREG.md`, `research/wpwb_live/`. User rejected
the closed search: WPWB means reading the *current* market each week, not
judging tools on 2021-2023. Redone on current data (fresh MT5 M5 through
2026-09-28 07:00, verified identical to the snapshot on 216,085 overlapping
bars).

**Two findings that change how WPWB should be built:**
1. Round-trip cost as a share of the median H1 move fell from ~19% (2021-
   2023) to 3.6% (2026) as gold went $1,800 -> $4,500 — the DEV era was the
   worst era in which to judge intraday tools. The user's objection was
   right on this point.
2. Week-to-week persistence (next-week Spearman rho, 2024-2026): realised
   volatility +0.81, XAU/DXY correlation +0.34, every direction/character
   trace (session drifts, weekly return, intraday autocorrelation, variance
   ratios) ~0. **What the market rewarded directionally last week does not
   predict next week; how volatile it was does.** This is why every
   direction-picking weekly selector tested (Part 24's grid, this search's
   META) failed or matched random.

**Current-era run of all 40 frozen tools (Bonferroni over 40): 0 pass.**
Hour-of-day tools (0 of 6) lost their DEV-era information despite cheaper
costs. TSM/META were very profitable but only as long gold (did not beat
always-long). DXY->XAU M5 lead-lag: +0.09 bp follow-through vs ~1 bp cost.
**One candidate: VOLMAN** (size the weekly long by trailing volatility):
+7.3 bp/week over exposure-matched long, positive every year, size-
permutation p 0.013 — but fails the 40-tool correction, 73-80% of its
excess comes from 5 weeks, and it works on XAU/XAG but not US500/FX. A
forward record would need ~162 weeks to reach t=2 at this effect size.
This week's rebuild value (cut 2026-09-25 22:15): daily sigma 142 bp,
1-sd weekly move ~317 bp (~$136 at $4,286), VOLMAN size 1.15x.

---

## Part 32 — WPWB backtest in money terms and attribution (2026-09-28)

**Source:** `research/wpwb_live/backtest_report.py`, `backtest_visuals.py`;
`data/wpwb_backtest.xlsx`, `data/wpwb_backtest_equity.png`. User asked to
see profit and which periods made/lost money and why. Weekly Sunday-open to
Friday-close, base costs incl. long swap, per 0.01 lot, $1,000 start, 142
weeks 2024-01-05..2026-09-18, gold $2,044 -> $4,286 (+110%).

| tool | net $ | win weeks | worst week | max DD $ | PF |
|---|---:|---:|---:|---:|---:|
| LONG | +1,921 | 57% | −522 | −1,198 (31% from a $3.9k peak) | 1.46 |
| VOLMAN | +2,056 | 57% | −292 | −727 | 1.63 |
| TSM26 | +2,277 | 61% | −522 | −831 | 1.57 |

**Where the money came from:** gold's trend, 2024-01..2026-02. Every
quarter from 2025Q1 to 2026Q1 made $270-$510 on LONG; the strongest,
2025Q1-Q2, coincided with DXY falling 6.5% and 7.0% (weekly LONG $ vs DXY %
corr −0.29). **Where it was lost:** 2024Q4 (DXY +6.9%, gold flat, −$44) and
2026Q2 (gold −8.2% in high volatility, LONG −$399); single worst week
2026-03-13 (FOMC week) −$520, −10.4%.

**Why VOLMAN helps (the WPWB-usable part):** grouped by volatility at the
Weekend Rebuild, gold averaged +$21/week (low vol), +$32 (mid), **−$5.8
(high)** with the worst week −$520 in the high group. Volatility at the
rebuild predicts next week's |move| (corr +0.39) but not its direction
(−0.15), so cutting size when rebuild volatility is high (VOLMAN ~0.55x in
2026's turbulent weeks) cut max drawdown from $1,198 to $727 at slightly
higher net. TSM26 beat both only by being short through 2026Q2 (+$448),
then gave most of it back when gold rebounded in 2026Q3 (−$423).

**News:** FOMC weeks gold −$29/week on average (22 weeks), NFP weeks
+$32 (31); CPI/PCE ~0; news weeks were not larger-move weeks on average.

**Honest reading:** the backtest profit is real in the data but is mostly
gold's +110% trend; all three tools are long-gold bets underneath (TSM26
only partly). The WPWB value-add found is risk control via the volatility
trace, not a directional edge. Risk note for the actual demo account (~$995):
at 0.01 lot the current 1-sd weekly move is ~$136 (~14% of balance) and the
worst week in the sample was −$520 (−52% of a $1k balance) — full-week
holding at 0.01 lot is oversized for $1k at $4,300 gold.

---

## Part 33 — what was missed: FOMC weeks; what cannot be read: direction (2026-09-28)

**Source:** `research/wpwb_live/loss_diagnosis.py` (exploratory, both eras),
`rules_test.py` (rules frozen in `docs/WPWB_LIVE_PREREG.md` amendment 2
before running), `r2_visual.py`. User asked how not to lose and what was
missed or unreadable.

**Unreadable:** none of 13 pre-week traces (volatility level/trend, 1/4/13-
week returns, extension above the 20-week mean, distance from the 26-week
high, 4-week DXY change, CFTC rank/change, tier-1 event count, trailing
efficiency) predicted next-week direction in both eras. Mon-Wed gold did
not predict Thu-Fri. The remaining large losses mostly coincided with the
dollar rising IN the same week (2024-11-08 DXY +1.6%, 2026-05-08 +1.3%,
2026-03-06 +1.2%, 2026-05-29 +1.1%), which was not visible beforehand.

**Readable and missed: FOMC weeks.** Longs did worse in FOMC weeks in both
eras (old −59 vs +5 bp; new −55 vs +67 bp). Frozen rule R2 (VOLMAN, no
position in weeks with a scheduled FOMC decision) vs VOLMAN:

| era | VOLMAN | R2 | R2 vs skipping the same number of random weeks |
|---|---|---|---|
| 2022-01..2023-12 (104 wks) | −161 bp (−$69), DD −2,130 bp | **+779 bp (+$114), DD −1,759 bp** | net beats 87%, DD better than 75% |
| 2024-01..2026-09 (142 wks) | +$2,056, DD −$727 | **+$2,433, DD −$391** | net beats 96%, DD better than 95% |

Versus plain LONG in the new era: +$512 more net, max drawdown $1,198 ->
$391, worst week −$522 -> −$208, losing weeks 61 -> 51. Cross-checked: two
independent code paths give identical R2 numbers. **Caveats:** nominated
after seeing both eras (NOT BLIND); in the new era $292 of the $377 gain
comes from one week (2026-03-13, gold −10.4%) — without it the gain is
~$85; the old era's gain is spread more evenly. Skipped FOMC weeks: $820 of
losses avoided, $443 of gains given up.

**Tested and rejected:** catastrophe stops at 2.0 and 2.5 weekly sigma (R3,
R5) cut the worst week but stopped out recoveries — lower new-era net and
no drawdown gain. R4 (R2 + stop) was dominated by R2 in the new era.

---

## Part 34 — readable trace or luck? Tested on unseen 2016-2021: luck/regime (2026-09-28)

**Source:** `research/wpwb_live/luck_check.py`, `oos_2016.py`, `oos_2016_d1.py`;
`docs/WPWB_LIVE_PREREG.md` amendments 3-4. User asked what the traces
looked like in losing vs winning weeks and how to know profits came from
readable traces rather than repeated luck.

**Before the week, winning and losing weeks are indistinguishable:** 0 of 12
pre-week traces differ at p<0.05 over 246 weeks (0.6 expected by chance).
**During the week they differ:** losing weeks had the dollar rising 64% of
the time vs 42% for winning weeks, and wider ranges ($125 vs $103 median);
same-week DXY vs gold rho −0.34 — real, but only knowable afterwards.

**In-sample luck checks** on the two surviving rules: VOLMAN's $ edge over
LONG is its best 3 weeks (+$373; −$237 without them); the new-era FOMC
gain is one week; best-of-15 random skip rules beat the FOMC gain 30% of
the time; pooled FOMC p 0.008 -> ~0.12 after the selection penalty.

**Decisive test on never-examined data (single runs, registered first):**
broker H1 before 2020-12 turned out not to be intraday, so the H1 run
covered only 2020-12..2021-12 (56 weeks, both rules FAIL); a D1 run
(registered after that result, disclosed) covered 2016-08..2020-11 (224
weeks): **FOMC rule FAIL and reversed** (FOMC weeks +96 vs −21 bp, losing
30% vs 51%), **VOLMAN FAIL** (−588 bp vs exposure-matched long, p 0.90).
Hand-entered FOMC dates were verified against price (9/9 on H1 at 3.1-9.9x
statement-hour range; 27/34 on D1). Year by year the FOMC effect follows
the Fed cycle (positive 2016/2018-2020 easing years, negative 2021-2026),
pooled 2016-2026 ~0.

**Answer:** the extra profit attributed to "skip FOMC" and "size by
volatility" was regime-specific or luck; it did not survive data the rules
had never seen. What remains solid: volatility persists week to week
(forecastable size of moves, useful for risk sizing, not for profit);
direction does not. Open hypothesis for WPWB's Wednesday Report, untested:
the FOMC reaction may be readable only together with the Fed's current
direction (easing vs tightening) — with only ~2 policy cycles in the data,
this cannot be confirmed statistically soon.

---

## Part 35 — H1 trace library: what the traces were, and why they came too late (2026-09-28)

**Source:** `research/wpwb_live/h1_traces.py`, `level_break.py`;
`data/wpwb_h1_trace_library.xlsx`; `docs/WPWB_LIVE_PREREG.md` amendments
5-6. User: the weeks are past, so at H1 we should know what the trace was.

**The traces, in hindsight (rule-9 library, every week 2021-07..2026-09):**
losing weeks = the dollar strengthening through the week (median +0.21% vs
−0.11%), gold closing an H1 below the prior week's low (51% vs 16% of
winning weeks), selling in all three sessions (median Asia −49, London −39,
NY −49 bp), spread evenly over Monday-Friday, not concentrated in news
hours (~1% of absolute H1 movement) nor in a few jumps (top-3 H1 bars
~13%). A few losses were event shocks: 2026-03-13 (FOMC Wed 18:00 −148 bp
in 3h, then London Thursday −621 bp), 2026-05-29 (hot NFP −224 bp in 3h).
Winning weeks are the mirror: weak dollar, break above the prior week's
high, all sessions up.

**Readable in time? No (two single pre-registered tests):**
- Wednesday 00:00 UTC checkpoint: 0 of 5 H1 features (return so far, DXY
  so far, prior-week level state, realised/forecast volatility, news-
  reaction direction) predicted Thursday-Friday in both eras; DXY-so-far
  was significant in both DXY sub-eras but with opposite signs.
- First prior-week level break (Mon-Thu) as a continuation signal: FAIL.
  After an H1 close below the prior week's low gold continued down only 46%
  (2021-23) / 34% (2024-26) of the time (mean −18 / −59 bp for a short,
  i.e. it bounced); after a close above the high it continued 52% / 62%.
  An "exit the long when last week's low breaks" rule would have sold dips
  that were bought, in both eras.

**Reading:** the losing-week trace is real but coincident — it is the loss
itself happening (dollar strength, broad selling), not an early warning.
Knowing it after the week is the guideline library's job; it does not
become a tradable signal by being clear in hindsight.

---

## Status

Everything above is read-only against existing data and Codex's paused,
unmodified cache. No real-money order sent. No open position. No PR. **NO
TRADE.**

---

## Part 36 (Codex) — independent WPWB trace-code audit (2026-09-28)

**Source:** `docs/WPWB_LIVE_PREREG.md` amendments 7/7a/7b,
`research/wpwb_live/audit_codex.py`. The preregistration was committed before
tests (`390bd69`; end-cut corrections were separately registered in `c4e6a73`
and `ded650f`). Read-only throughout; no MT5 function was called.

All 7 existing `research/wpwb_search/test_common.py` tests passed. Independent
checks passed for exact/gapped M5→H1 resampling, Bid/Ask and stressed cost math,
entry/exit spread selection, vector/scalar rollover equivalence including
boundary instants, Friday 22:15 week containment, Wednesday 00:00 input
causality, pandas-3-safe epoch seconds, and W5 reaction completion. Fresh XAU
matched canonical on 216,085 overlap bars (99.9995% within 0.01; best offset
+0h), and `combined_bars()` preserved the canonical prefix and appended 1,373
strictly later, unique bars.

**Audit verdict:** no active bug found that would hide a real trace or bias the
reported tests toward “no trace.” Two non-result-changing robustness issues:
`fetch_fresh.py` writes fresh files before validation and does not remove them
if validation fails (a future failed fetch could bias either way), and the
hindsight day/session descriptions in `h1_traces.py` sum H1 bar bodies rather
than full close-to-close movement, omitting inter-bar gaps. The latter affects
descriptive attribution only, not W1-W5 or rest-of-week outcomes.

---

## Part 37 (Codex) — external pre-week traces: 0 of 10 pass both eras (2026-09-28)

**Source:** first-party Treasury, Cboe, and CFTC files in `data/external/`
(URLs, retrieval time, and SHA-256 in its README/manifest),
`research/wpwb_live/fetch_external.py`, `external_traces.py`. Data were aligned
causally to the Friday 22:15 rebuild: Treasury/GVZ no later than Thursday and
CFTC only after its release timestamp. Window: 273 complete weeks,
2021-07-02..2026-09-18; era A n=131, era B n=142. Each test used 20,000 seeded
circular random-timing controls; pass required registered sign and p<0.005 in
both eras (Bonferroni 10).

| trace | meaning | era A rho / p | era B rho / p | verdict |
|---|---|---:|---:|---|
| N1 | 2y yield level → gold | +0.077 / .853 | −0.119 / .178 | FAIL |
| N2 | 13w change in 2y → gold | −0.005 / .531 | −0.140 / .022 | FAIL |
| N3 | 10y nominal level → gold | +0.073 / .829 | −0.144 / .035 | FAIL |
| N4 | 13w change in 10y → gold | −0.003 / .453 | −0.107 / .086 | FAIL |
| R1 | 10y real-yield level → gold | +0.102 / .969 | −0.131 / .058 | FAIL |
| R2 | 13w change in real 10y → gold | +0.051 / .680 | −0.094 / .130 | FAIL |
| G1 | GVZ / realised vol → next absolute gold return | +0.143 / .090 | +0.042 / .373 | FAIL |
| G2 | 13w GVZ change → next absolute gold return | +0.056 / .246 | +0.154 / .061 | FAIL |
| C1 | managed-money 52w percentile → gold | −0.150 / .016 | −0.015 / .403 | FAIL |
| C2 | managed-money 4-report change → gold | −0.158 / .939 | +0.015 / .418 | FAIL |

Some raw p-values in one era look suggestive, but none reaches the registered
family threshold and none also holds in the other era. The first 272-week run
was superseded because Codex encoded the final date at midnight and omitted the
valid 22:15 cut; the correction was registered before rerun, restored the 273rd
week, and did not change any verdict. Fed-funds-futures/policy-expectation data
beyond the pre-registered 2-year-yield proxy were not retrieved: **NOT
ASSESSED**. No leading external trace was found; **NO TRADE**.

---

## Part 38 (Codex) — FOMC direction from the 3-month 2-year-yield change fails (2026-09-28)

**Source:** `research/wpwb_live/external_traces.py`; hypothesis and controls in
Amendment 7. Signal known at the rebuild: falling/unchanged 63-trading-day 2y
yield = dovish/long gold; rising = hawkish/short gold. Score = signal × complete
FOMC-week gross gold return. Required in both eras: positive mean, hit >50%,
p<.05 versus 20,000 random directions, and p<.05 versus the same number of
random weeks.

- Era A: 20 FOMC weeks (6 dovish, 14 hawkish), mean score +5.0 bp, median
  +9.0, hit 55.0%; p=.451 random-direction, p=.314 random-week — **FAIL**.
- Era B: 22 (11 dovish, 11 hawkish), mean +102.2 bp, median +116.2, hit 68.2%;
  p=.0345 random-direction but p=.0954 random-week — **FAIL**.
- Already-examined 2016-08..2020-11 context: 27 verified FOMC weeks, +48.6 bp
  mean score and 59.3% hit. This is context only, not new confirmation.

Power is poor: for a true 60%/65%/70% hit rate, era-A power was
12.6%/24.5%/41.6% and era-B power 15.8%/30.2%/49.4%. More importantly, 42
recent FOMC events are not 42 independent policy cycles; 2016-2026 contains
only roughly two easing/tightening cycles. The event-level rule fails its
controls, and cycle-level generalisation remains **NOT ASSESSED**, not inferred
from the positive old-era context. Engine decision remains **NO TRADE**.

---

## Part 39 — Claude's verification of Codex Parts 36-38 (2026-09-28)

Codex was run non-interactively via the official `@openai/codex` CLI (user-
local install, the operator's existing ChatGPT login) against
`docs/CODEX_REQUEST_2026-09-28_WPWB_TRACES.md`, sandbox workspace-write with
network enabled, instructed never to call MT5 trading functions or push.

Checked: (1) pre-registration commit `390bd69` (16:56) precedes the results
commit `5fb2d7d` (17:10); the end-cut fix was registered (`ded650f`) before
the final run and adds one valid week without changing any verdict. (2) The
diff from `69d0761` to `5fb2d7d` contains **zero deleted or modified lines**
in `docs/LOGIC_LEDGER.md` and `docs/WPWB_LIVE_PREREG.md` — additions only.
(3) `external_traces.py` and `audit_codex.py` read local files only; the only
network script is `fetch_external.py` (treasury.gov, cboe.com, cftc.gov).
(4) **Independent rerun reproduces every reported number exactly**: audit
PASS; external traces 0 of 10 (identical rho/p per trace); FOMC x Fed-
direction FAIL (era A +5.0 bp, hit 55.0%, p .451/.314; era B +102.2 bp, hit
68.2%, p .0345/.0954).

Observation (not a finding): the Fed-direction FOMC rule leaned the right way
in all three windows (+5, +102 and, in the already-examined 2016-20 data,
+49 bp; hits 55% / 68% / 59%) yet fails its random-week control and has
12-49% power. It is a forward-shadow candidate at most, never a rule.

Hygiene note: Codex force-added ~100k lines of raw external data (incl.
~12 MB of CFTC zips) under the gitignored `data/` directory. Local branch
only; not removed here without the operator's say-so.

---

## Part 40 — Codex's review of Claude's measurement methodology, and what Claude verified (2026-09-28)

Operator asked Codex to review Claude's measurement methods. Codex ran
(`codex exec`, workspace-write, no network) but wrote no file and made no
commit; its full review is its final message, kept verbatim in
`data/codex_method_review_report.md` (gitignored) and summarised here. Most
of it examined the EARLY pilot engine (`research/pilot/core.py`, `run.py`,
`adaptive.py`, `flip_diagnosis.py`, `docs/ENGINE_PROTOCOL.md`, Amendments
03-08), not the WPWB work of Parts 29-39.

**Codex's verdict:** conservative at the decision layer (NO TRADE, forward
shadow, cost stress) but too loose in several measurements feeding it;
"the repository does not prove there is no edge — no edge has survived a
trustworthy validation yet." Claims: (1) ENGINE_PROTOCOL's posterior /
e-process / confidence-sequence machinery was never implemented; (2)
`adaptive.py` STABLE_TREND used a full-series median — look-ahead; (3) early
`core.py` subtracted scalar cost after resolving the path; (4) early MDE
tables used 2.8 x sd/sqrt(n) while requiring a Bonferroni critical value of
2.99 (consistent coefficient 3.83, ~1.87x more observations) and assumed
independent trades; (5) the circular-shift control pooled 20 replicas as
independent, understating uncertainty (Amendment 04 "timing skill" t=3.48
untrustworthy); (6) multiplicity is reset per amendment while the same
history is reused; (7) some conjunctive gates (Amendment 06) are
uncalibrated and too strict.

**Claude verified:** (2) is **correct** — `research/pilot/adaptive.py`
line 177 compared `st` to `np.nanmedian(st)` over the whole series while
every other threshold in the function is a rolling CONTEXT-window quantile.
**Fixed** to a rolling median over the same window. It is used by
`regime_v2.py`, `flip_diagnosis.py`, `current_signal.py` and Amendment 05;
results computed with it are contaminated and are NOT rerun here. **None of
the WPWB scripts (`research/wpwb_search/`, `research/wpwb_live/`) use it.**
(6) applies to today's WPWB work too: rounds and amendments reused 2021-2026
— it biases toward FALSE edges, and no edge was accepted, so it does not
overturn the negative WPWB conclusions; it does mean the per-test p-values
understate the true search. Claims (1), (3), (4), (5), (7) concern early
work superseded before WPWB; not re-verified line by line here.

**Not answered by Codex** (asked, skipped): the power of today's
significance rule on 130-142 weeks, and whether the "must hold in both eras"
requirement structurally rejects the regime-specific edges WPWB is built
for. Sent back to Codex as a follow-up.

---

## Part 41 (Codex) — WPWB measurement-method review: NO TRADE stands; the broad no-direction claim does not (2026-09-28)

**Source:** `docs/CODEX_METHOD_REVIEW_2026-09-28.md` and reproducible scripts/
outputs in `research/wpwb_live/codex_review/`. Scope is today's WPWB work in
Parts 29-40, not the early pilot engine already reviewed in Part 40. No MT5
function was called and no order was placed.

**Power:** 10,000-replication simulation exactly reproduced the repository's
`max(circular-block-8 bootstrap, Newey-West-8)` p rule with 5,000 bootstrap
draws. For iid weekly P&L, n=130-142, sd 150-200 bp, power for true 5/10/20
bp-per-week edges was only **5.8-7.2% / 9.7-13.7% / 22.8-37.0%** at the raw
`p<.025` rule. At `p<.025/40`, it was only **0.4-0.6% / 0.8-1.7% /
3.2-7.4%**; AR(1) phi=.3 was lower for the larger effects. Therefore 0 of 40
rules out only large, easy-to-detect effects. It cannot establish that modest
weekly direction is absent.

The far bootstrap tail is also not calibrated for the claimed Bonferroni
bound: `_cbb_p` uses `count/5000` without an add-one correction. At the `/40`
threshold the decision rests on roughly three exceedances. Simulated marginal
null rejection was 0.13-0.29%, not the 0.0625% required for a literal 2.5%
Bonferroni family bound. Use far more draws/add-one and validate the entire
family with joint block maxT/randomisation.

**Controls:** RDIR is appropriate for directional attribution. LONG is useful
against drift but absorbs a genuine long-timing edge when it inherits the
selected timestamps. RTIME is useful for timing attribution but inherits the
realised week's directional move and has inconsistently matched candidate
pools. Requiring a tool to beat every control makes attribution diagnostics
into conjunctive nulls and can reject a profitable timing-direction
interaction. Random-week skips are too weak for FOMC because they do not match
Fed regime, volatility, event load or calendar clustering. VOLMAN's LONGMATCH
matches mean exposure ex post but not risk and is not an online benchmark.

**Target mismatch:** requiring the same sign/significance in both 2021-2023
and 2024-2026 structurally rejects the regime-specific, decaying edges WPWB's
mission asks it to switch on and off. The fair target is a frozen **adaptive
procedure**, tested by nested rolling-origin replay with all tuning performed
on past data and the complete selector compared to block-randomised placebos.
Calendar-era results should be diagnostics, not same-sign gates. Because the
available history has been repeatedly mined, promotion requires future shadow
weeks under an anytime-valid sequential alpha plan.

**Hindsight and costs:** FOMC skip, catastrophe stops and prior-week level
break were frozen only after the same eras nominated them; this is transparent
but not independent. More seriously, the old-data FOMC scripts “verify” dates
by retaining only events whose XAU statement-hour/day range exceeds a median,
which conditions event inclusion on the price outcome. Event dates must come
from an independent authoritative calendar. Weekly bp sums, Sunday-to-Friday
holding, H1 resolution, 1.5x non-swap stress, today's swap back-cast to
2016-2020 and the $0.09 spread floor are mostly conservative, but they test a
weekly carry target and cannot be generalised to every M5/M15 conditional edge.

**Verdict:** the operational **NO TRADE** decision remains correct. The
scientific wording must be softened: **no tested weekly-direction procedure has
earned promotion; volatility magnitude is the strongest repeatable descriptive
trace and may help risk sizing, but neither a directional edge nor a VOLMAN
return edge is validated. Non-detection under these gates is not proof that
weekly direction is intrinsically unreadable.**

---

## Part 42 — Claude accepts Codex's methodology verdict; conclusion corrected (2026-09-28)

**Delivery defect, disclosed:** the first methodology-review run (Part 40)
and the first follow-up passed a multi-line prompt as a command-line argument
through `codex.cmd`, which truncated it at the first newline — Codex received
only the first line each time (it said so in the follow-up). Part 40's
general review and its `adaptive.py` finding stand, but the specific
questions never reached Codex until this run, which delivered the prompt via
stdin (verified first with a 3-line echo test). The external-trace task
(Parts 36-38) used a one-line prompt and was received in full.

**Verified by Claude before accepting:** `_cbb_p` returns `count/5000` with
no add-one correction (`research/wpwb_search/common.py:150`) — correct. An
independent 400-replication spot check with the repository's own
`block_boot` (n=142, sd 150 bp) gave power 10.8% per test / 0.8% at `/40` for
a 10 bp/week edge and 35.0% / 4.0% for 20 bp/week, consistent with Codex's
10,000-replication table within sampling error. The FOMC date "verification"
in `oos_2016.py`/`oos_2016_d1.py` did exclude 7 of 34 dates by XAU price
range — outcome-conditioned inclusion, as Codex says. The DEV gate
(`DEV_P_MAX = 0.025`) was per-test, with multiplicity deferred to a holdout
that was never opened — as Codex says.

**Corrected conclusion (replaces the wording in Parts 31-35 and the
presentations to the operator):** no tested weekly-direction procedure has
earned promotion; volatility magnitude is the strongest repeatable trace and
may support risk sizing, but neither a directional edge nor a VOLMAN return
edge is validated. **The tests had 1-7% power for realistic 5-20 bp/week
edges at the family threshold and required same-sign behaviour across eras,
which WPWB does not assume — so "weekly direction is unreadable" was an
overstatement.** Engine decision unchanged: **NO TRADE**.

**Method changes adopted for any further WPWB testing:** (1) test a frozen
adaptive PROCEDURE by nested rolling-origin replay against a selection-aware,
block-randomised placebo, with calendar eras as diagnostics, not gates;
(2) one primary benchmark per economic claim, other controls descriptive;
(3) add-one bootstrap p with enough draws for the tail, family-level
maxT/hierarchical testing instead of flat Bonferroni; (4) event dates only
from an authoritative calendar, never filtered by price; (5) promotion only
from future shadow weeks under an anytime-valid sequential test, with a
single project-wide alpha ledger.

## Part 43 — Procedure test closed for no power; WPWB becomes a weekly risk report (2026-09-28)

**Debate with Codex, rounds 1–4** (`docs/WPWB_DEBATE_2026-09-28.md`):
- P1 (weekly one-tool selector over the 38 legacy tools vs a random eligible
  tool) was fully specified, coded and audited (12 tests, builder audit 12/12),
  then **closed before any real-data evaluation**: Codex's scale-preserving
  harness gives 12% forward power at a true +20 bp/calendar-week edge. The
  real P, B' and d were never computed; alpha returned to the reserve.
- P2-B (event-level matched evidence) withdrawn: the direction-agnostic paired
  residual SD is 52 / 102 / 174 bp for 1 / 4 / 12 h holds; power at 10 bp/week
  exists only for ~1 h holds with >= 12 independent events per week, and no
  uncontaminated direction rule exists.
- P2-C (volatility forecast) adopted as a **risk tool, not an edge**: HAR beats
  the 26-week mean by 41.6% QLIKE, but only 5.5% / 11.8% over last-week / EWMA,
  and a forward superiority test against those has 0–8% power in 52 weeks. So
  no alpha is spent; calibration is monitored instead.

**Built** (`research/wpwb_weekly/`, spec `docs/WPWB_RISK_REPORT_SPEC.md`,
operator approval items 4/7/9/10/11): weekly report after each Friday cut —
EWMA volatility forecast, vol_scale = clip(√(B_REF/F), 0.5, 1.0) that can only
reduce size, 8-scenario news plan using the existing news layer, last week's
news classification, CFTC positioning, append-only log; forward from
2026-10-02 22:15 UTC. Codex raw data untracked from git.

**Volatility log** (`docs/WPWB_VOLATILITY_LOG.md`): 68 of 221 weeks volatile
(31%), 25 episodes; direction in volatile weeks 34 up / 34 down; moves 1.7x
larger. The forecast flags 56% of volatile weeks but only 6 of 25 episode
onsets — the first week of a volatile episode is not predicted.

**Verdict unchanged: NO TRADE** on direction.

## Part 44 — Codex Round 5: Saturday blocker fixed, P2-A dropped, drawdown claims narrowed (2026-09-28)

Codex audited the weekly risk report and backtests. Accepted and fixed before
the first forward week (spec v2): v1 would have failed every Saturday because
gold closes before the 22:15 UTC cut (completeness now by clock); the
out-of-calibration fail-safe (scale 0.50) is now executed, not just written;
H1 bars assigned by close time; invalid weeks cannot re-enter forecasts;
forward scoring joins by date. 10/10 tests. Drawdown sizing claims narrowed:
0.03 lot/$10k breaches 45% in ~1% of favourable i.i.d. paths and 3–15% under
persistent or biased direction or unrounded lots; stop-out modelled only at
zero equity. P2-A router dropped (alpha 0). Verdict: NO TRADE on direction;
WPWB is a risk report.

## Part 45 — the R-geometry audit Part 11 flagged: CONFIRMED, and it biases every R figure (2026-09-29)

Part 11 warned that R = move / (k x ATR) is not a neutral unit if a family
fires preferentially at particular ATR levels, and recorded the check as "not
yet done". `research/pilot/audit_r_geometry.py` runs it on all six declared
families, 2021-07..2026-09 (51,374 signals). The skew is real and large:

| family | median ATR pct-rank at signal (all bars = 49) | bottom ATR third | top third | R bias vs an unmatched control |
|---|---|---|---|---|
| breakout | 72.5 | 3% | 59% | **R deflated 12%** |
| pullback | 59.5 | 23% | 41% | deflated 7% |
| failed | 59.5 | 20% | 40% | −1% |
| vwap | 61.5 | 29% | 46% | −1% |
| sweep | 47.0 | 37% | 32% | inflated 4% |
| **expansion** | **23.0** | **78%** | **0.3%** | **R inflated 36%** |

Readings:
1. **expansion fires almost only into low volatility** (78% of signals in the
   bottom ATR third, 0.3% in the top). Its stop denominator is 27% smaller
   than average, so the same dollar move is recorded as a 36% larger R than an
   unmatched control scores. CLAUDE.md appendix item 9 already recorded that
   expansion's apparent high-RR edge was directional drift; this is a second,
   independent reason its R numbers were never trustworthy.
2. **breakout is the mirror image** — it fires into high volatility, so its R
   was *understated* by about 12%. A family that looked flat in R may not be
   flat in money.
3. Therefore the gross-edge figures in Parts 6 and Amendments 23-29
   (+0.1308 R and +0.1686 R per trade) mix families whose R units are biased
   between −12% and +36%. They cannot be compared with each other, and a
   basket that reselects among them silently reweights the biases.

**Consequence for all future work: stop measuring edge in R.** Basis points of
entry price have no family-dependent denominator. Where a bracket is needed,
the control must be drawn from bars matched on ATR percentile, not from all
bars. The cost-share story (cost ate 90% then 33%) is a ratio of two R figures
and inherits the same bias, so it is now unverified as well.

## Part 46 — edge search in basis points with an ATR gate: 0 of 24 (2026-09-29)

Pre-registered in `docs/EDGE_SEARCH_BP_PREREG.md` (commit 99f8bde, before the
run), code `research/pilot/edge_search_bp.py`, output `data/edge_search_bp.xlsx`.
Six families × H ∈ {1 h, 4 h} × {all ATR, top ATR third} = 24 tests, outcome in
bp of entry price, no stop bracket, control matched on ATR decile × session,
Demo90 cost, week-clustered bootstrap, Bonferroni α = 0.00208.

- **0 of 24 pass in DEV; 0 candidates.** Pipeline self-check: random signals
  reject 3% of the time (null ~5%); a planted +4 bp is found 100% of the time.
- In DEV every family's net return is about −1.6 bp, i.e. minus the cost
  (≈1.4 bp at 2021-23 prices): there is **no gross edge over the matched
  control** in any family.
- **The ATR gate is not supported.** Pooled over families the difference vs
  the matched control does not grow with ATR: DEV bottom/middle/top third
  +0.07/−0.36/0.00 bp at 1 h and −0.28/−0.77/+0.03 at 4 h; LATER
  +0.10/−0.04/+0.10 and +0.52/+0.72/+0.64. Cost share does fall with ATR
  (Part 45 follow-up: 9.5% vs 18% of one ATR in 2021-23, 4.6% vs 7.4% in
  2024-26) but that is a smaller cost, not an edge.
- **Only lead, not an edge:** vwap at 4 h in the top ATR third: DEV diff
  +3.53 bp, 95% CI [−2.5, +9.2], p = 0.24, n = 250; LATER +4.35 bp; and it is
  negative in the bottom ATR third in both eras (−3.06, −2.85) — a sign
  pattern that grows with ATR. It is best-of-24 on a mined sample. Its
  standard deviation per signal is ~47 bp, so confirming a 3.5 bp effect needs
  ~1,400 signals ≈ 14 years at ~100 top-ATR vwap signals per year: not
  confirmable forward alone, which is the general reason weekly-to-hourly
  edges of this size have never been provable here.
- Half-width of the tests: ±1.6 bp (all ATR) and ±2.6 bp (top third): a
  per-trade difference below about 3 bp cannot be seen at these sample sizes.

## Part 47 — what an edge must look like, and what the chart's own information map shows (2026-09-29)

Pre-registered in `docs/CHART_MEASUREMENT_PREREG.md` (commit 0bc2514, before the
run); code `research/pilot/chart_information_map.py`; output
`data/chart_information_map.xlsx`.

**Required edge (arithmetic).** Sharpe ≈ (e/s)·√N, so the years needed to
*detect* an edge at 5%/80% are (2.8/Sharpe)² regardless of trade frequency:
**about 7.8 years for Sharpe 1 and 2 years for Sharpe 2**. Per-trade SD is
27 bp (1 h) and 54 bp (4 h); round-trip cost at 2024-26 prices is 0.80 bp. At
1,000 trades a year: Sharpe 1 needs a net edge of 0.87 bp (1 h) / 1.72 bp
(4 h), a win rate of 51.3%, and a signal rank-correlation with forward return
of about 0.04; Sharpe 2 needs 0.08. The sibling program's real 51.7% reversal
hit rate is exactly the size of edge that matters — and exactly the size that
cost and short samples hide.

**Information map (15 causal instruments, out-of-era, 30 primary tests).**
- **Direction: 0 of 30 leads.** Largest ρ = 0.022 (trend_sep, 4 h; p = 0.04
  against α = 0.00167). Best case if real: gross ≈ 0.8 × 0.022 × 54 bp ≈ 0.96 bp
  per trade against 0.80 bp cost → ~0.16 bp net, about zero. A small same-sign
  lean toward trend continuation appears in both eras (trend_sep, ret16,
  dist_ll20: ρ 0.01–0.02) but it is not significant and below the 0.04 needed.
- **Magnitude: strong, and it reproduces in both directions of transfer.**
  hour of day ρ = 0.19 (DEV→LATER) / 0.30 (LATER→DEV) at 1 h, ATR percentile
  0.15 / 0.21, current-bar range expansion 0.14 / 0.20, session 0.09 / 0.23,
  all p < 0.001.

**What kind of instrument the chart yields:** a *volatility/timing clock*
(hour × ATR × range expansion) that tells how big the next 1–4 hours will be —
useful for sizing, stop distance and when-not-to-trade — and no direction
instrument. Not tested here: cross-asset intraday lead-lag (DXY, US500, silver,
USDJPY, EURUSD → gold), whose M5 data exist only from 2023-09.

### Part 46 — corrections after Codex Round 7 (2026-09-29; wording superseded, numbers unchanged)

Codex audited `edge_search_bp.py` and Part 46. Verdict: the negative decision is
safe; the mechanics mostly implement the frozen design; the wording overstated.
Superseding statements:
1. **Not "every family's net return is about −1.6 bp".** The broad-family DEV
   means cluster near −1.5 bp, but individual cells range from −2.5 to +2.0 bp
   (e.g. vwap 1 h all-ATR −0.32, vwap 4 h top-third +2.00). The defensible
   statement: no cell passed the registered gate.
2. **Not "no gross edge".** It is "no statistically validated gross edge";
   several point estimates are positive.
3. **The ATR-gate conclusion is narrower than stated.** None of the evaluable
   top-ATR-third family × horizon tests passed and the pooled descriptive
   gradient was not increasing in DEV. That rejects promotion of this gate; it
   does not show ATR can never condition an edge. The pooled figure is a
   count-weighted mix of overlapping outcomes and expansion contributes nothing
   to the top third.
4. **Honest count: 0 passes among 22 evaluable cells**, plus 2 structurally
   empty cells (expansion/top third: DEV n = 0). "0/24" is grid bookkeeping.
5. **The vwap "only lead" label was selective.** vwap 1 h top-third is also
   positive and net-positive in both eras (DEV +1.88 bp, p = 0.10; LATER +2.20).
   Both fail. Several mined vwap point estimates are positive and none merits
   confirmation.
6. **The control is descriptive and ex-post**, not a causal random-entry
   benchmark: full-era bin means use future bars and the signals' own outcomes.
   Causal confirmation would need past-only rolling controls repeated inside the
   bootstrap.
7. **The self-check is not adequate validation** (30 trials at α = 0.05, one
   horizon, 800 draws, no acceptance band); it says the machinery is not
   grossly biased, nothing more.
8. **Undeclared boundary defect, verified:** signal-to-entry contiguity was not
   checked, so a signal on the last bar before a gap enters after it: 668 of
   93,750 evaluated signal-horizon pairs (0.09%–1.24% by family; vwap 0.30%).
   The era-boundary exit defect touches 0 bars (both era ends fall on a weekend
   or after the data). Neither can move a p-value near the gate, so no rerun is
   planned; a rerun would be a new version.
9. **vwap forward alpha = 0.** Confirming a 3.5 bp effect needs ~1,100 signals
   even spending the whole 0.05 reserve (~11 years at ~98 top-third signals a
   year), ~14 years at α 0.025, ~18 years at α 0.01. Dropped as a promotion
   hypothesis; it may stay a zero-alpha passive log at no cost.

## Part 48 — cross-asset intraday lead-lag into gold: 0 of 36 leads, 0 tradeable (2026-09-29)

Pre-registered in `docs/CROSS_ASSET_LEADLAG_PREREG.md` (commit 4ed0b85, before
the run); code `research/pilot/cross_asset_leadlag.py`; output
`data/cross_asset_leadlag.xlsx`. 215,533 aligned M5 bars 2023-09..2026-09;
instruments DXY, silver, US500, USDJPY, EURUSD (each as its causal residual
against gold's own move over 5/15/30 min) plus gold's own return; outcome gold
15 and 30 min ahead; out-of-era transfer DEV (2023-09..2025-03) ↔ LATER
(2025-04..2026-09); 36 tests, α = 0.00139.

- **0 of 36 leads; 0 tradeable.** Largest |ρ| = 0.0144. Round-trip cost is
  0.64 bp; at a mean 15-30 min SD of 19.8 bp, a signal needs ρ ≈ 0.04 just to
  cover cost. The best signal's implied gross edge is 0.19 bp.
- Three cells were significant DEV → LATER (silver 5 min → 15 and 30 min,
  p = 0.0002 and 0.0012; DXY 15 min → 15 min, p = 0.0007) but **none
  reproduces LATER → DEV** (p = 0.17, 0.19, 0.88), and all carry 0.13-0.19 bp
  of implied gross edge against 0.64 bp of cost: informative about how markets
  co-move, untradeable.
- Self-check: circular-shift null rejected 3% (acceptance band 1-10%). A planted
  raw ρ = 0.05 came back as transfer ρ = 0.028 (decile-mean prediction
  attenuates) with p = 0.0012: the test is only marginally able to see a raw
  ρ of 0.05, so it can rule out tradeable leads (raw ρ ≥ 0.04 needed) only
  approximately, not decisively.
- Together with Parts 30-47 this closes the last intraday trace class that the
  project's data can measure. What remains is not another feature but more
  independent history: see the ledger note in `docs/WPWB_DEBATE_2026-09-28.md`.

## Part 49 — long-history H1 search on Dukascopy 2003-2015: families 0/24, one information-map lead (2026-09-29)

Pre-registered in `docs/H1_LONG_HISTORY_PREREG.md` (commit 59cfb01), code
`research/pilot/edge_search_h1.py` (78ef645), run once after the H1 cache
reached 2015-12 (152 months, no gaps; input sha256 30f6b77f…c684d1d4). DEV
2003-05..2012-12 (60,311 bars), CONFIRM 2013-01..2015-12 (18,087 bars, untouched
by any project result). Self-check: random-signal rejection 5%, planted +3 bp
found 100%.

- **A1, six families × {1 h, 4 h} × {all ATR, top ATR third}: 0 of 24 pass in
  DEV, 0 confirmed.** The one DEV p below 0.06 is *negative* (sweep 4 h, −1.69 bp).
  Expansion top-third has too few signals (16 in DEV). The families that looked
  best in 2021-2026 (vwap top-third) are negative here (−2.2 and −5.0 bp).
- **A2, 15 chart instruments × 2 horizons, DEV → CONFIRM: 1 lead of 30**, α =
  0.000926: **hour of day (UTC) → the next 4 h**: ρ = +0.0402 (p = 0.0001), reverse
  transfer ρ = +0.0183 (p = 0.0015), implied gross 1.40 bp vs 0.80 bp cost. Nothing
  else comes near (next |ρ| 0.026, p 0.03).
- The hour map (drift removed, 4 h, by signal hour, DEV | CONFIRM): positive in
  the overnight/Asian hours (21-04 UTC, +0.3 to +2.1 bp | +0.4 to +4.9) and
  negative into the London open (05-07 UTC, −0.8 to −3.8 | −3.0 to −6.9). Signs
  agree in 16 of 24 hours, mainly those two groups. Individual hours are small
  (|t| < 2.6). Overall 4 h drift changed sign between eras (+1.41 bp DEV, −1.40
  CONFIRM), so the lead is not the drift.
- Caveat set by earlier parts: Part 47 measured hour of day on 2021-2026 M15
  and found ρ < 0.01 for direction. A pattern present in 2003-2015 and absent in
  2021-2026 would be a decayed edge, not a live one. The next test is exactly
  that: freeze the rule, then apply it to eras it has never seen.
- Plan B (`docs/PLAN_B_DAILY_PREREG.md`) is **not** run: the decision tree sends
  a LEAD to a frozen rule first.
