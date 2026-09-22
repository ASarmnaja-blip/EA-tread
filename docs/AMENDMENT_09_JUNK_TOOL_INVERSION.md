# Protocol Amendment 09 — the deliberately-bad-tool inversion search

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.** The operator proposed this direction; the rules below are fixed
now so that whatever comes back can be believed.

Amends: nothing. It opens a second search direction and constrains it in
advance. It runs **in parallel with** the corrected cross-asset work, not
instead of it.

Does not amend: `ORDERLY_TREND` as frozen by Amendment 05, Amendment 06's failed
replication, Amendment 08's measured cost model or its matched-control strata,
Amendment 04's one-champion rule, the prohibition on real-money orders, or the
prohibition on Grid and Martingale.

---

## 1. The proposal, and the part of it that is sound

Gather the entry tools retail traders actually use, tune their parameters to be
**as bad as possible**, stack tools that **contradict each other**, find the
configurations that lose most consistently, and mirror them.

**What is sound.** Ordinary searches ask which of thousands of configurations
wins, and the winner is the maximum of thousands of noisy numbers. Asking which
loses does not escape that, but it points the search at a place nobody has
looked, and one of the reasons a configuration can lose is genuinely
invertible.

**What is not.** Three things can make a configuration lose, and only one of
them mirrors into a profit:

| cause of the loss | does mirroring it pay? |
|---|---|
| **cost** — trades too often, pays the spread and commission repeatedly | **No.** The mirror pays the same cost. Both sides lose. |
| **instrument drift** — it is short in a market that rose 126 % | **No.** The mirror reduces to being long gold, which is a bet on the drift continuing. |
| **genuine anti-timing information** — it enters where price reliably goes the other way | **Yes.** This is the only invertible one. |

Amendment 07's search was defeated by the second of these: the drift audit
measured a long-minus-short gap of **+0.1163 R** from random entries alone,
larger than any pattern's own gap. Amendment 08 built the instrument that
separates the third cause from the other two. This search uses it from the
start rather than discovering the problem afterwards.

### On Martingale, since the operator raised it again

Position sizing **cannot create or destroy per-trade expectancy.** Martingale
does not make a losing system lose *more per trade*; it makes the same
per-trade expectancy arrive with vastly greater variance and an unbounded
worst case. It therefore contributes nothing to finding a reliable loser: the
quantity this search measures is the per-trade expectancy, and Martingale
leaves it exactly where it was. Mirroring a Martingale gives anti-Martingale,
which also does not change per-trade expectancy. It remains prohibited by
`CLAUDE.md` section 8 and is not used here.

## 2. The mechanism, stated before any number is read

Amendment 07 section 6 requires a nameable reason a participant would be
systematically on the wrong side. For a contradictory stack it is this:

> A configuration that fires **when its own components disagree** fires at the
> moment when the largest number of chart readers are looking at the same bar
> and reaching opposite conclusions. That is where stop orders accumulate on
> both sides of a narrow band, and where a move that clears one side has the
> fuel to keep going against whoever entered on the other. A tool stack built
> to enter *into* that disagreement is built to be the fuel.

If the search finds nothing, this mechanism is not established, and that is a
result about the mechanism rather than a reason to keep adjusting the stack.

## 3. The tool library, fixed now

Ten entry tools, chosen because they are the ones actually used, not because
anything is known about them here:

| # | tool | signal |
|---|---|---|
| 1 | RSI | crossing back out of oversold / overbought |
| 2 | Stochastic | %K crossing %D in the extreme zone |
| 3 | MACD | line crossing its signal line |
| 4 | Bollinger | close outside the band |
| 5 | EMA cross | fast crossing slow |
| 6 | CCI | leaving an extreme reading |
| 7 | Williams %R | leaving an extreme reading |
| 8 | Donchian | breakout of the channel |
| 9 | round number | touch of a x.00 or x.50 level |
| 10 | candle pattern | engulfing or pin bar |

Each gets **three parameter settings** — deliberately too fast, the textbook
default, and deliberately too slow — because "tune it to be as bad as possible"
means searching the parameter space for the worst, and the worst has to be
searched for over a stated grid rather than asserted.

## 4. The search space and its size, counted before any result

```
single tools:       10 tools x 3 parameters x 2 directions   =  60
contradiction pairs: 45 pairs x 2 directions                 =  90
                                                      N = 150
```

**N = 150 is recorded here, before running.** Deliberately searching 150
configurations for the worst one is a data-mining machine by construction, and
saying so in advance is the only thing that makes the result readable.

## 5. The three-way split, which is what makes "tune to the worst" legitimate

Selecting the worst configuration and then testing the mirror **on the same
data** is the same error as selecting the best and reporting its backtest. The
data is therefore cut into three, and the cuts are fixed now:

| slice | days | use |
|---|---|---|
| **SELECT** | first 730 | where the search for the worst configuration happens. Every one of the 150 is scored here. |
| **CONFIRM** | next ~245 | **untouched by the selection.** Only the K = 5 worst carry forward, and the mirror is judged here. |
| HOLDOUT | last 120 | spent already (Amendment 05 section 5). Diagnosis only, never promotion. |

**K = 5 is fixed now.** Carrying forward more after seeing the SELECT ranking
would be widening the second test to fit the first.

## 6. Scoring, fixed now

**On SELECT**, every candidate is scored on **matched excess** using the
stratified direction-matched placebo control frozen in Amendment 08 section
6.5 — same direction, quarter, session, ATR tercile, news state, spread
bucket, 20 placebo draws, seed 20260922. Raw expectancy is **not** used for
ranking, because on this sample raw expectancy is mostly a reading of the
drift.

Significance on SELECT is judged by **permutation maxT across all 150**, which
is the right shape for candidates that overlap in time and are therefore
correlated. Bonferroni at N = 150 is reported alongside it.

**On CONFIRM**, each of the K = 5 must satisfy all of:

1. matched excess **negative again** — sign agreement with SELECT
2. the **mirror's net expectancy per trade ≥ +0.05 R** after the measured cost
   charged per trade, not as an average. Amendment 08 section 6.3: a negative
   excess does not mean the mirror can pay its own costs, and this is the
   condition that decides whether the idea is tradeable at all
3. net still positive at **1.5x** cost, with 3x and 7x reported
4. **ambiguity rate below 15 %**, worst case charged to both directions
5. at least **50 trades** on CONFIRM
6. significance at Bonferroni for **5** tests, which is the honest count for
   this stage because exactly five pre-specified tests are run

## 7. The prediction, recorded before the run

**No candidate is expected to pass section 6.** The reasoning, stated so it can
be checked against the outcome:

- the matched control removes the drift, and cost **cancels out of the excess**
  because the placebo pays it too. So the excess measures only anti-timing
  information, and the two causes that actually make junk tools lose have both
  been removed from the quantity being ranked.
- the excess is therefore expected to be **near zero for nearly all 150**, with
  the spread across candidates looking like sampling noise
- if a few show a negative excess on SELECT, most are expected to **fail sign
  agreement on CONFIRM**, because the ranking is the minimum of 150 draws
- any that keeps its sign is still expected to **fail condition 2**, since an
  excess near −0.05 R cannot pay a round-turn cost of roughly 0.042 R and leave
  +0.05 R

Being wrong about this would be a genuine finding. It would also immediately
raise the question of which defect produced it, and that question gets asked
first.

## 8. What failure looks like, so it cannot be argued away later

- no candidate's excess is significantly negative on SELECT under maxT →
  **the junk-tool losing tail is sampling noise**
- a candidate passes SELECT but flips sign on CONFIRM → **the minimum of 150
  draws**, not a finding
- sign holds but the mirror's net is below +0.05 R → **not tradeable**, which
  is the same wall `UNSTABLE_HIGH_VOL` hit at +0.031 R
- the mirror dies at 1.5x cost → **a cost artefact**
- ambiguity above 15 % → **not assessable**

Any of these is recorded as a failed search. None is a reason to add a tool,
widen the parameter grid, raise K, move a slice boundary, or relax the +0.05 R
requirement. If the route closes, the record reads **"closed for these 150
configurations, this instrument, this sample and this execution model"** —
that scope and no broader claim.

## 9. Status while this runs

Unchanged. `ORDERLY_TREND v2` is a rare shadow candidate with a failed
cross-asset replication against it. The engine's answer is **NO TRADE**. No
real-money order has been sent, no position is open, and no pull request is
opened.
