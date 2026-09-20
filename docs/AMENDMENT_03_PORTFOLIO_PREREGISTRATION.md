# Protocol Amendment 03 — the candidate portfolio, declared before the data

**Written 2026-09-21, before the MT5 export landed and before a single real
XAUUSD bar had been read. Committed alone, separately from every result it will
be judged against.**

Amends: `PILOT_PREREGISTRATION.md` §1 (instrument and data source), and the cost
constants in `research/pilot/core.py`.

Does not amend: the eighteen configurations, the circular-shift control,
Amendment 02's family-wise level, the order of operations, the sealed holdout,
or any standing prohibition in `ENGINE_PROTOCOL.md` §12.

---

## 0. What prompted this

Operator instruction, 2026-09-21: *build a portfolio out of the setups that work,
judge them on the current market only, and do not stop at analysis.*

This document turns that instruction into something that can be measured, and it
is written **before** the data so the rules cannot be chosen after seeing which
of them would have been kind to the result. That is the whole reason it exists
as an amendment rather than as a paragraph in a report.

---

## 1. The prior, printed beside every future result

`RESEARCH_FINDINGS.md` is 47 configurations deep. What it establishes about the
horizon this mandate targets:

| Measurement | n | Result |
|---|---|---|
| EMA 9/21 cross, XAUUSD M5, minute-resolved exits | 5,326 | **−0.2152 R**, t = −4.68 |
| Same crosses at **zero** spread | 5,326 | −0.03 R, t = −0.38 — no directional information |
| 13 signal families, gold H1 | — | gross ≈ −0.03 R |
| Donchian 20/55, **hourly**, 26 CME markets | 6,142 | **−0.2670 R**, t = −6.23, positive on 4/26 |
| Liquidity-sweep reversal, gold M1-resolved | 43,353 | −0.202 R; inverted −0.189 R → no information left |
| Donchian 55, **daily**, 27 CME markets | 1,464 | **+0.2232 R**, t = +2.48, positive on 20/27, p = 0.0096 |
| Donchian 55 long, **gold alone, daily** | 75 | skill +1.4655, t = **+2.78** vs a Bonferroni bar of 2.84 |

Two sentences summarise it: **the only positive finding in the whole program is
multi-week trend across many markets, and the intraday horizon is not merely
flat but reliably negative.** `ENGINE_PROTOCOL.md` §1 is explicit that this is a
prior and not a veto — but a candidate on M5/M15 is arguing against a t = −6.23,
and the report must say so every time.

---

## 2. "Current regime only" makes the test harder, not easier

`CLAUDE.md` §1 permits ignoring the distant past and in the same breath forbids
using that permission to tune one dataset into a false profit. The arithmetic is
what keeps both halves honest.

Shortening the window cuts `n`, and the smallest effect a sample can see is

```
MDE = 2.8 · sd / sqrt(n)          (core.summarise, unchanged)
```

At a typical `sd ≈ 1.2 R` for a 2R-target configuration:

| signals in the window | MDE |
|---|---|
| 30 (the protocol minimum) | 0.613 R |
| 60 | 0.434 R |
| 100 | 0.336 R |
| 200 | 0.238 R |
| 400 | 0.168 R |
| 800 | 0.119 R |

Against the MWE in §7 (0.054 R to 0.234 R depending on spread and volatility),
**a 30-day regime window cannot resolve an edge the size of the cost.** A 30-day
M15 window holds roughly 2,880 bars; a setup firing on 3 % of them yields about
86 signals, and 86 signals see nothing smaller than ~0.36 R.

This is not an argument against the mandate. It is the mandate's budget, and it
forces three consequences that are hereby fixed in advance:

1. **`INCONCLUSIVE` will be the common verdict in a single window, and it is
   recorded as such** — never rounded up to "promising".
2. Evidence accumulates **across consecutive regime windows** through the
   e-process of `ENGINE_PROTOCOL.md` §4, not by widening the window until the
   number turns positive.
3. A configuration that needs a longer window to reach significance is reported
   as needing one. Extending the window *after* seeing a near-miss is a change
   of test, and a change of test is a new amendment.

---

## 3. Data source and cost

**Declared before the first run on real data.**

`research/pilot/run.py` gains `--csv5 PATH [--csv1 PATH]`, which loads the MT5
export through `data.load_csv` instead of the Yahoo GC=F proxy. Without the flag
the behaviour is exactly as before. The gap this closes: `load_csv` existed and
**nothing called it**, so the export would have landed with no pipeline able to
read it.

`run.apply_measured_cost` then replaces the assumed cost with the broker's own:

| term | before | after |
|---|---|---|
| spread | `$0.48` **assumed**, carried from OANDA | **median of MT5's per-bar spread column**, measured |
| slippage | `$0.10` per fill, assumed | unchanged and still **assumed** — history cannot measure it, only live fills can |

This satisfies `ENGINE_PROTOCOL.md` §2 Tier A item 4. The substitution prints
itself on every run, with p90 and max beside the median, so no result is ever
read against the wrong cost by accident.

**Without a `--csv1` series, P5 does not run.** The exit-resolution bias is the
single most dangerous shortcut in this program — `RESEARCH_FINDINGS.md` measures
resolving on the signal bar at roughly **+0.5 R of pure fiction** — so a run
without the M1 series carries a **RESEARCH WATCH ceiling** no matter what it
reports. The runner now says this out loud instead of leaving it implicit.

---

## 4. What a portfolio costs in evidence

Piling candidates in raises the bar for every one of them. `core.bonferroni_z`
computes it from the live count:

| candidates `k` in the window | family-wise z | required e-value `k/alpha` |
|---|---|---|
| 6 | 2.6383 | 120 |
| 12 | 2.8653 | 240 |
| **18 (today's registry)** | **2.9913** | **360** |
| 24 | 3.0781 | 480 |
| 30 | 3.1440 | 600 |
| 40 | 3.2272 | 800 |
| 60 | 3.3415 | 1,200 |
| 100 | 3.4808 | 2,000 |

`k` counts **every configuration evaluated in the current regime window**,
variants included — an S1 tested at three targets is three. It does not carry the
lifetime count of ~47 forward as a debt (`ENGINE_PROTOCOL.md` §3); that history
is the prior in §1.

The practical consequence, stated before anyone is tempted: **"try more setups
until one passes" does not work here.** Going from 18 candidates to 40 moves the
bar from 2.99 to 3.23 and roughly doubles the evidence each one must supply.
A portfolio is a way of *diversifying* candidates that already cleared their bar,
not a way of buying more lottery tickets.

---

## 5. The candidate set for the first real-data run

**The existing eighteen, unchanged.** No family is added before the first run on
real XAUUSD.

The reason is not conservatism. A family chosen *after* seeing which ones look
alive on the new data has been chosen by the data, and every number it produces
afterwards is contaminated. New families enter as Amendment 04, declared before
run 2, with their mechanism stated first.

Measured against the eight families `CLAUDE.md` §3 asks for:

| Mandated family | Registry coverage |
|---|---|
| Breakout continuation | **S1, S1V1, S1V2** |
| Trend pullback | **S2, S2V1, S2V2** |
| Liquidity sweep / reversal | **S3, S3V1, S3V2** (UNINTERPRETABLE status stands) |
| Failed breakout | **S4, S4V1, S4V2** |
| VWAP / value-area reversion | **S5, S5V1, S5V2** (UNINTERPRETABLE status stands) |
| Volatility expansion | **S6, S6V1, S6V2** |
| **News acceptance** | **absent — blocked** |
| **News rejection** | **absent — blocked** |

Six of eight are already registered. The two that are missing are missing for a
concrete reason, not an oversight: `research/pilot/news.py` implements the
eight-scenario decision layer and passes 30 tests, but it has **no calendar
feed** — `HANDOFF.md` §5 records `priced_in` and `positioning` as `NOT ASSESSED`
on every path. A news setup cannot be registered as a measurable candidate until
`MqlCalendarValue` actual/forecast/previous is being read. That is Amendment 04's
first item, and it is a data-plumbing job, not a research one.

---

## 6. How the portfolio is formed — fixed now, before any result

**Eligibility.** A configuration may enter the portfolio only when all hold:

1. Tier A structural safety passes in full (`ENGINE_PROTOCOL.md` §2).
2. P1 passes on the amended code, on the real series.
3. `P(net expectancy > 0) ≥ 0.75` on the current regime window — the SHADOW band.
4. `n ≥ 30` signals in the window. Below this no decision is permitted whatever
   the statistic says.
5. The skill interval versus the circular-shift control excludes zero at the
   family-wise `z` for the live `k`.

**Champion selection.** At most **two** champions, chosen by the paired
per-bar comparison of `ENGINE_PROTOCOL.md` §6 — both arms valued on every bar in
the window with no-position = 0, so the market path cancels. Exposure and
opportunity cost are reported beside the winner. Everything else that cleared
eligibility runs as a **shadow challenger** and emits no live signal.

**Correlation gate.** If two eligible configurations have per-bar R series
correlating above **0.70** in the window, only the one with the higher posterior
enters; the other stays shadow. Three variants of one family that fire on the
same bars are one bet wearing three names, and sizing them as three is the
mechanism by which a "diversified portfolio" quietly triples its risk.

**Weights.** Equal risk per eligible configuration, subject to:
- a hard cap on total simultaneous risk that nothing may exceed,
- the min-lot feasibility check — if the broker minimum forces risk above the
  per-setup cap the answer is **NO TRADE**, never a rounded-up position,
- **no Kelly**, fractional or otherwise (`ENGINE_PROTOCOL.md` §8).

At the ATR in `RESEARCH_FINDINGS.md` the minimum lot already floors gold near
**2.04 %** of a 1,000-unit account per trade. A portfolio of four concurrent
positions at that floor is over 8 % at risk at once. **Capital adequacy, not
signal quality, is likely to be the binding constraint on portfolio width**, and
the run must report how many eligible signals were dropped as unaffordable so a
capital limit is never mistaken for a strategy result.

**Demotion.** A champion returns to shadow when its Strategy Health Score breaks
its pre-declared kill condition — not on a losing trade, and never by changing
its rules mid-position (`ENGINE_PROTOCOL.md` §10). SHS never feeds MRS (§5).

---

## 7. MWE — undefined until the export, bounded now

`MWE = max(0.05 R, 2 × measured round-turn cost in R)`. The cost in R depends on
both the spread and the stop, and the stop is `1.5 × ATR(M15)` for S1/S2/S4/S6.
The three-way spread disagreement the export is meant to settle produces three
different tests:

| ATR(M15) | spread | round turn | cost in R | **MWE** |
|---|---|---|---|---|
| $11.35 (2026) | $0.2600 | $0.4600 | 0.0270 | **0.0540 R** |
| $11.35 | $0.4824 | $0.6824 | 0.0401 | **0.0802 R** |
| $11.35 | $0.7525 | $0.9525 | 0.0559 | **0.1119 R** |
| $8.00 | $0.4824 | $0.6824 | 0.0569 | **0.1137 R** |
| $5.44 | $0.7525 | $0.9525 | 0.1167 | **0.2335 R** |

Slippage is $0.10 per fill, both ways, and remains assumed.

Read against §2: at the pessimistic corner the test must resolve 0.23 R, which
needs roughly 200 signals; at the optimistic corner 0.054 R, which needs over
3,800. **The cheaper the broker, the more data the test needs** — because the
bar drops to the 0.05 R floor while the noise does not. This is not a paradox to
be optimised away; it is the shape of the problem, and it is stated here so that
whichever way the export falls, the required sample was fixed beforehand.

---

## 8. What makes the answer "no portfolio"

Declared now so it cannot be softened later. The run reports **NO PORTFOLIO** —
a conclusion, not a failure — when any of these holds:

- P1 fails on the real series. Nothing downstream is read; the instrument is
  broken before the market is examined.
- No configuration reaches `n ≥ 30` in the current regime window.
- No configuration clears `P(net > 0) ≥ 0.75` after measured cost.
- Every configuration that clears it collapses below 0.75 at **1.5× cost**. That
  is a cost artefact and is reported as one.
- The eligible set survives only because `k` was kept artificially small by not
  counting variants.

`NO TRADE` and `NO PORTFOLIO` are conclusions the log must justify by showing
what was evaluated and why each candidate was rejected (`ENGINE_PROTOCOL.md`
§11). They are never an unexamined default.

---

## 9. Order of operations — unchanged

The export lands → `load_csv` on the real files → the whole Amendment 01
calibration re-runs on real XAUUSD including the A3b scenario → **if** it passes,
P1 re-runs → **if** P1 passes, market prices are read → only then does §6 select
anything.

**The order does not change because the data got better, and it does not change
because the operator is in a hurry.**

---

## 10. What this amendment is not

It is not evidence that any setup has an edge. It is a specification of how a
portfolio would be chosen if the evidence arrives, written while the evidence is
still absent so that the specification cannot be bent by it.

Every number in `research/pilot/results/` today was measured on **synthetic data
containing no information at all**. S3, S3V1, S3V2, S5, S5V1, S5V2 and S2V1 stay
**UNINTERPRETABLE**. The sealed holdout stays sealed. No order is placed, and no
claim of profit is made here or anywhere downstream of here.

---

## 11. The window is 2 weeks to 1 month — what that buys

*Added 2026-09-21, after the operator fixed the window length and before any
data had been read. No result existed when this section was written.*

**Operator instruction:** "current" means **the last 2 weeks to 1 month**.
Anything older must not carry weight, and must not carry it indirectly either.

**What older data may still be used for, and why it is not a violation:**

| Use | Admissible | Reason |
|---|---|---|
| observations in the sample | **no** | this is the instruction |
| decay-weighted tail beyond the window | **no** | that is weight arriving by the back door |
| indicator warm-up (`Ctx.warm = 200`, `rolling_pct_rank` over 200) | **yes** | an ATR percentile at time `t` is an *input to a feature at t*, not an observation of an older market. 200 M15 bars is 2.2 trading days; 200 M5 bars is 16.7 hours. These are drawn from before the window so the window itself is not consumed by warm-up |
| the long-horizon prior of §1 | **yes, as reported context only** | `ENGINE_PROTOCOL.md` §1. It is printed beside the result and never enters the estimate |

### What the window physically contains

XAUUSD trades roughly 23 hours a day, five days a week.

| timeframe | 2 weeks (10 trading days) | 1 month (22 trading days) |
|---|---|---|
| M15 | **920 bars** | **2,024 bars** |
| M5 | **2,760 bars** | **6,072 bars** |

### How many signals that is

| timeframe | window | fires on 1 % | 3 % | 5 % | 10 % | 20 % |
|---|---|---|---|---|---|---|
| M15 | 2 weeks | 9 | 27 | 46 | 92 | 184 |
| M15 | 1 month | 20 | 60 | 101 | 202 | 404 |
| M5 | 2 weeks | 27 | 82 | 138 | 276 | 552 |
| M5 | 1 month | 60 | 182 | 303 | 607 | 1,214 |

### How many the test needs

From the MWE of §7 and `n = (2.8·sd / MWE)²` at `sd = 1.2 R`:

| timeframe | spread | cost in R | MWE | **n required** |
|---|---|---|---|---|
| M15 | $0.7525 | 0.0559 | 0.1119 R | **902** |
| M15 | $0.4824 | 0.0401 | 0.0802 R | **1,757** |
| M15 | $0.2600 | 0.0270 | 0.0540 R | **3,866** |
| M5 | $0.7525 | 0.0969 | 0.1938 R | **301** |
| M5 | $0.4824 | 0.0694 | 0.1388 R | **586** |
| M5 | $0.2600 | 0.0468 | 0.0936 R | **1,289** |

M5 stops are taken at `1.5 × ATR(M5)`, with `ATR(M5) ≈ ATR(M15)/√3`.

### The decisive table — firing rate the window demands

| timeframe | window | spread | needs | of bars | **= % of all bars** |
|---|---|---|---|---|---|
| M15 | 2 weeks | $0.7525 | 902 | 920 | **98.0 %** |
| M15 | 1 month | $0.7525 | 902 | 2,024 | **44.6 %** |
| M15 | 1 month | $0.2600 | 3,866 | 2,024 | **191 %** — impossible |
| M5 | 2 weeks | $0.7525 | 301 | 2,760 | **10.9 %** |
| M5 | 2 weeks | $0.2600 | 1,289 | 2,760 | **46.7 %** |
| M5 | 1 month | $0.7525 | 301 | 6,072 | **5.0 %** |
| M5 | 1 month | $0.2600 | 1,289 | 6,072 | **21.2 %** |

**Three conclusions, fixed before the data:**

1. **M15 is ruled out as the evaluation timeframe for a single window of this
   length.** A setup would have to fire on 45 % to 191 % of all bars. The
   mandate's M5/M15 pair survives, but M15 becomes a *context* timeframe, not
   the one the statistics are taken on.
2. **M5 over a full month is the only viable configuration**, and only for
   setups that fire on **5 % of bars or more** — roughly 300 signals. Over
   2 weeks the requirement is 11 %. None of the current eighteen was designed
   with a firing rate that high; that is a fact to measure on the export, and
   the count per configuration is now the first number to read off the first
   real run.
3. **A tighter spread makes the edge easier to earn and harder to prove.** At
   $0.7525 the MWE is set by cost (0.194 R on M5); at $0.26 it falls to the
   0.05 R floor, and the required sample more than quadruples. If the export
   reports a cheap broker, the honest response is *more time*, not a smaller
   bar.

### Where the missing sample comes from

Not from the past — that is closed by instruction, and §1 says the past argues
against this horizon anyway. It comes **forward**: consecutive 2-week to 1-month
windows, evaluated as they arrive, accumulated through the always-valid
e-process of `ENGINE_PROTOCOL.md` §4, which is valid at every stopping time and
therefore tolerates looking at it every window. The maximum of three consecutive
regime windows already stands in §4; at M5 that is roughly 900 signals for a
5 %-firing setup, which clears the $0.7525 and $0.4824 rows outright.

### What this means for the first run

**The expected verdict on window one is `INCONCLUSIVE`, and `NO PORTFOLIO` is
the expected first answer.** That is not a failure of the search and it is not
pessimism — it is what a 2,760-to-6,072-bar window can support. The deliverable
from run one is therefore:

- the **firing rate of each of the eighteen** on real XAUUSD M5, which decides
  which of them can even be tested inside this window,
- the **measured spread by hour**, which fixes MWE and with it the required `n`,
- an e-process started and carried forward, not a portfolio announced early.

A portfolio announced on window one, at these sample sizes, would be noise
wearing a table. The instruction to judge on the current market is followed
exactly — and the arithmetic of the current market is what says how long that
judgement takes.
