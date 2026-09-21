# Protocol Amendment 04 — Research Watch v1, frozen before the next test

**Written 2026-09-21. Committed alone, before any code of the next round runs.
Nothing below was chosen after seeing a result it will be judged against.**

Amends: nothing. This document freezes a state and declares the rules of the
round that follows it.

Does not amend: Amendment 02's family-wise level, Amendment 03's portfolio
eligibility, the order of operations, the sealed holdout, or any standing
prohibition.

---

## 1. What is frozen

`research/pilot/engine2.py` at commit `4eb34ba`, and its three variants,
become **RESEARCH WATCH v1**. Their numbers are fixed as of that commit:

| variant | trades | net R/trade | skill vs control | t |
|---|---|---|---|---|
| pullback + breakout | 11,044 | −0.0548 | +0.0291 | 2.19 |
| **pullback only** | 8,958 | −0.0631 | +0.0508 | **3.48** |
| breakout only | 2,518 | −0.0344 | +0.0412 | 1.45 |

Development period −0.069 R against a 120-day holdout of +0.061 R, and
quarterly results between −0.223 R and +0.143 R.

**These numbers are not to be improved by adjustment.** Specifically
forbidden from here on:

- changing any parameter because a quarter looked bad
- restricting the date range to the quarters that looked good
- adding a filter whose only justification is that it removes losing trades
- re-reading the 120-day holdout to choose between variants

The reason is not procedural tidiness. Four quarters of this system are
reliably negative and two are reliably positive; a parameter tuned to keep the
positive ones is fitted to six observations of a regime, and the research log
already records what that produces.

## 2. The selection bug this amendment also fixes

The first version chose its best variant by the skill t-statistic of the
**whole sample, holdout included**. That made the holdout part of the
selection, which is the single thing a holdout exists to prevent: whichever
variant the recent window happened to favour would have been picked and then
"confirmed" on that same window.

Selection now reads the development period only. The holdout is read once,
afterwards, and never fed back. This is a correctness fix, not a change of
rules, so the frozen numbers above stand.

## 3. What the frozen result actually established

Two things survive, and they are worth keeping separate:

1. **The timing has skill.** Against a circular-shift control — the same
   trades taken at times shifted together — the pullback variant is better by
   +0.0508 R at t = 3.48, which clears the family-wise bar of 2.39. The entry
   is not random.
2. **The system still loses.** Both arms are negative; the setup is merely
   less negative. *Better than random is not the same as profitable* and is
   never to be reported as though it were.

And one assumption was corrected by measurement: of the losing trades, 99.2 %
lost because the **direction** was wrong, and 0.8 % because the move was right
but too small to pay costs. Against a one-R stop the round turn is a minor
term. **The binding constraint is the hit rate, not the spread**, and earlier
rounds in this repo argued the opposite.

Target hits are 26.6 % where roughly 28.5 % is break-even. The gap between a
losing system and a flat one is about two points of hit rate, which is close
enough to be tempting and small enough to be regime noise.

---

## 4. The rules of the round that follows

Declared here, before that round's code runs.

### 4.1 One champion, at most one shadow challenger

The engine selects **one** tool for the regime it has measured, and may run
**one** challenger in shadow beside it. Not three, not eighteen.

Stacking every setup and letting the best one shine through is a search over
setups wearing the clothes of a portfolio, and the multiplicity arithmetic of
Amendment 03 §4 prices it: at 18 candidates the bar is z = 2.99; at 40 it is
3.23. A small set is not modesty, it is what keeps the bar reachable.

### 4.2 Regime selects the tool, from a fixed and small menu

| regime the engine measures | the one tool it is allowed to use |
|---|---|
| stable trend | trend pullback |
| volatility expansion | breakout continuation |
| event / around a release | news acceptance or rejection |
| balanced range | mean reversion to value |
| anything else, or conflicting | **NO TRADE** |

The mapping is declared now and is mechanism-based: a pullback needs a trend
to pull back inside, a breakout needs expansion to carry it, reversion needs a
balanced range to revert within. **No tool may be moved to a different regime
because it performed better there in the data.**

### 4.3 Data windows, fixed in advance

Following `CLAUDE.md` §5, and recency-weighted without letting the recent
window become the only window:

| window | used for |
|---|---|
| 30–60 days | broad context |
| 10–20 days | the regime label |
| 3–5 days | ranking the tools inside the allowed regime |
| latest session | entry, invalidation, expiry |

Older data is not deleted — it sets the prior and the control. What it may
never do is outvote the current regime on which tool is allowed.

### 4.4 Promotion requires forward shadow, not history

No tool becomes champion on a backtest, however good. Promotion requires:

1. positive net expectancy after **measured** cost, including swap, in the
   regime it claims,
2. on a **forward** shadow run that did not exist when the rule was written,
3. stable across the shadow period rather than carried by one week,
4. and it survives the paired comparison against the incumbent.

Until then every tool is a shadow challenger and the engine's output is
`NO TRADE`.

### 4.5 What must be reported when there is nothing

`NO TRADE` is a conclusion and carries the same reporting burden as a signal:
which regime was measured, which tool that regime allows, what that tool saw,
and why it declined. An empty output with no reason is not a NO TRADE, it is a
missing answer.

---

## 5. Starting position, stated before the code runs

The current market context is **conflicting** — the slow layer's components
disagree — and the correct output today is therefore `NO TRADE` until new
evidence arrives. Recording this in advance matters: if the next round reports
a signal for today, that report is arguing against a position stated before it
ran, and must say so.

---

## 6. What this amendment is not

It is not evidence of an edge. Research Watch v1 loses money on three years of
real XAUUSD after measured costs. Freezing it preserves an honest negative so
that the next round has something fixed to be compared against, which is the
only use a negative result has.

No order is placed. No pull request is opened. The sealed holdout stays
sealed.
