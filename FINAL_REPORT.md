# FINAL AUTONOMOUS RUN COMPLETE

Branch `claude/order-position-choch-gab-im08db`. Sealed holdout **UNEXAMINED**.
1,615 cumulative hypotheses. 18 of 18 reproduction checks pass. 12 regression
suites pass.

---

## The one-sentence answer

**There is directional information in this data, it is real, universal and
stable over twenty-two years, and it is worth between 7% and 12% of what it
costs to act on — and every attempt to find a conditioning state, a horizon, a
target or an execution design that closes that gap was either falsified by
fresh data or turned out to be a defect in my own measurement.**

Five levers have now been closed on measured data rather than argument:
**conditioning states**, **horizon**, **financing**, **venue cheapness** and
**execution style**. The last one fails hardest: a resting order saves a
spread worth 1.0 and buys an adverse selection worth 7.3.

---

## The twelve questions

### 1. Is there exploitable directional information left after measurement bias, activity selection, volatility selection, execution assumptions, costs and strong controls?

**Information: yes. Exploitable: no, at these costs.**

Fading the previous hour's move wins the direction 51.71% of the time.
t +17.84 against 50%, positive on 9 of 9 panel markets, 52.87% in 2004–2014
and 51.72% in 2015–2026. It reproduces on USDSEK — a market no hypothesis in
this repository had ever used — at +0.075 of a round trip on 126,392 signals.

Measured with **no stop, no target, no tie-break rule and no one-position
constraint**, so it cannot be an artifact of any execution choice.

Its worth: +0.1198 of one round trip on the panel. The win rate needed to
break even while paying one spread is 59.91%; the measured rate is 52.24%.

### 2. What is the mechanism, and is the representation adding anything?

The unconditional effect is short-horizon mean reversion. The reversion
*representation* adds +0.53pp on top of it — t +5.96 against a floor of 4.74,
positive on 9 of 9 — and survives being computed one bar late with 58% of its
magnitude, so it is not purely microstructure. 42% of it does live in the most
recent quote and has no mechanism attached to it.

### 3. Does any horizon make the economics work?

No, and the reason is structural rather than a search failure.

The predictable move scales as **T^0.233** (fitted over six timeframes and
nine markets). Financing scales as **T**. Two curves of those shapes cross
once, so the net has a single maximum — and it is negative.

| | |
|---|---|
| H1 → W1 | 3.7× over a 168× bar length (a square root would give 13×) |
| net maximum | 2.68 hours, at −0.878 spreads |
| break-even financing rate | 0.2038 spreads/night |
| gold's known long swap | 1.2616 spreads/night — 6.2× too expensive |

**Corrected after this section was first written.** The exponent of 0.233 was
fitted over a ladder that stops at one week. Extending it shows the edge
**peaks at W1 and falls after it** — W2 +0.2415, M1 −2.2143, Q1 −6.5896 — so
the exponent was an average over a curve that rises and then turns. The
"8,900 hours to breakeven" figure this report originally quoted applied that
fit five times past its anchor and describes nothing real. See §12.

### 4. What if financing is removed entirely?

Swap is charged at one moment, not continuously, so a hold that never spans a
rollover pays none of it. That was the last lever and it does not close the
gap.

Best cell: enter 07:00 UTC, hold 3 hours. **+0.717 of one round trip**,
bootstrap t +4.14, skill against C7 +0.714 at t +3.18 on 8 of 9, 5,221 signals
per market. Shortfall **0.283 spreads, measured rather than extrapolated**.
5% of bootstrap draws put it above cost.

The scaling reverses inside a session: mean edge by hold length is +0.144 at
2h, +0.049 at 3h, −0.050 at 4h, −0.121 at 6h, −0.225 at 8h.

### 5. Does a different target have better arithmetic?

Yes in principle, no in fact. A bracket pays **its own width**, not the
expected move: expectancy is (2p−1)·D − one spread. At a 1.5-ATR bracket the
width is 27 spreads, so breakeven sits at p = 52.89% rather than at an
amplitude five times anything measured.

The unconditional p is **50.08%**. Zero of 118 hypotheses lifted it in both
halves of the sample, at any of three bracket widths.

### 6. What about a non-directional target?

A conditional breakout straddle looked like the best result in the project's
history: +2.498 round trips for a 2-ATR dislocation state against an
unconditional −0.140, lift over the C7 control +1.078 at t +4.94 on 8 of 9.

**That number was a scoring assumption, not a measurement.** It counted
windows touching both barriers inside one bar as *no trade*. Those are 19.9%
of the candidate state's windows against 7.9% of an unconditioned bar — the
state is selected for volatility, and volatility is what makes a bar span both
levels.

Gold minute data 2019–2026 resolved every one of them:

| state | resolved | stopped out | profitable | mean |
|---|---|---|---|---|
| dislocation 2.0 ATR | 130 | **130 (100%)** | 0 | −16.2 spreads |
| cheap + dislocation | 53 | **53 (100%)** | 0 | −25.8 spreads |
| every bar (baseline) | 3,121 | **3,121 (100%)** | 0 | −14.9 spreads |

Scored honestly, the state reads **−0.647** and the lift falls to +0.113 at
t +0.86. The resolved figures land on the pessimistic bound. The optimistic
one was a fiction.

### 7. Was the sealed holdout opened?

**No. `examined: false`.** It has never been opened, and no run in this
project has ever produced a FINALIST. 14 FX crosses with no USD leg,
2012–2026, sha256 manifest intact.

The protocol was tested rather than merely obeyed. The best candidate sat at a
bootstrap t of 3.67 against a floor of 4.84 — the expected maximum of 1,085
trials at this repository's own measured trial dispersion. A statistic *below*
the expected maximum of pure noise is what noise looks like. The ledger
refused to promote it. Independent data then agreed, twice.

### 8. What did the fresh market say?

USDSEK has a full 2003–2026 series in the cache, was never used by any
hypothesis here, and carries a USD leg so it is not part of the sealed
holdout. All eight surviving shapes were frozen and run on it **in one pass,
with every row reported**, so a single positive among eight could not be
promoted:

| | |
|---|---|
| panel mean | +1.447 round trips |
| USDSEK mean | **+0.086** — a seventeen-fold collapse |
| beat the unconditional fade | 4 of 7, which is what a coin gives |
| exceed one round trip | 0 of 7; best +0.363 |

The gradient did not reproduce either, and that is the more telling half. On
the panel the edge rose monotonically as the preceding bar got quieter, across
all four steps. On USDSEK 2 of 4 steps fall and the column means are U-shaped.
A gradient is much harder for noise to imitate than a level, which is why it
was named as the thing to watch *before* the market was loaded.

### 9. Why did 127 hypotheses die?

| code | n | share | upgrade it names |
|---|---|---|---|
| COST_DOMINATED | 66 | 52.0% | tradability layer |
| NO_DIRECTIONAL_SKILL | 40 | 31.5% | hypothesis generation |
| CROSS_MARKET_INSTABILITY | 35 | 27.6% | representation |
| BELOW_MULTIPLICITY_FLOOR | 23 | 18.1% | — |
| SAMPLE_TOO_SMALL | 4 | 3.1% | |
| ACTIVITY_SELECTION | 3 | 2.4% | |
| SESSION_SELECTION | 2 | 1.6% | |

The two smallest counts are the interesting ones. The control hierarchy found
almost no selection artifacts to remove.

By family, the deaths are specific: STATE dies 88% COST_DOMINATED, AMPLITUDE
dies 55% BELOW_MULTIPLICITY_FLOOR, DISLOCATION dies 71%
CROSS_MARKET_INSTABILITY.

### 10. What did this run find wrong with its own measurements?

Six defects, four of them in work done during this run. Each was found by
**measuring an assumption**, never by reading code.

**29% of every bar this project had ever used was an hour the venue was
shut.** 58,233 flat bars in gold alone, 28.8%–31.0% on every market in every
year. A flat bar has zero true range and Wilder's ATR is an exponential mean
of true range, so 48 consecutive zeros multiply it by (13/14)^48 = 0.030.

| ATR(14) median vs Thursday | Mon | Tue | Wed | Thu | Fri |
|---|---|---|---|---|---|
| as loaded | 55.6% | 86.5% | 94.3% | 100% | 97.7% |
| filtered | 97.5% | 94.0% | 94.9% | 100% | 99.2% |

The engine's spread-under-10%-of-ATR gate therefore rejected **84.8% of Monday
bars against 56.9% of Thursday's**. Every backtest here was three times less
likely to take a Monday trade for a reason with nothing to do with the market.

**The control was a different instrument.** `random_like` took the random
bar's own high or low as the invalidation level, so its stop sat a third as
far from entry as the rule's — dist/ATR median 0.559 against 1.638 — while R
divides by that distance. The replacement inherits the rule's own ratio and
measures a 0.00% gap across all eight levels.

**The edge metric was a mean of ratios.** That is what a trader earns only by
sizing inversely to each trade's own spread, putting the most capital exactly
where the quote is thinnest. The economics is the ratio of means. The gap is
1.3× to 2.3×, and correcting it removed **all five** apparent clears from the
pilot.

**Pooling across markets added gold points to pip points.** Caught before
publication.

**The expansion target was not an expectancy.** It scored range over spread
and returned +73 "round trips". A range is not a profit.

**The straddle's whipsaw was an assumption.** Resolved with minute data, as
above.

### 11. What was falsified that this project previously believed?

| claim | refutation |
|---|---|
| 91% of measured skill is activity selection | Measured through the defective control. With geometry matched, an activity-selecting rule facing a coin shows \|t\| below 2 at **every** level including C1. There was no activity artifact. The 91% was the geometry gap. |
| The four families carry +0.0171R of skill | +0.0026 to +0.0066 on the cleaned frame with a correct control, negative for one family, and all four negative at C7. |
| R through a bracket is a neutral measure of direction | It divides by an ATR-derived distance, so it **charges** volatility selection whether or not the direction is right. Two synthetic fixtures reproduce the sign. |
| Fading a range expansion after a quiet bar reaches +1.278 spreads | +0.724 on the corrected metric; zero of 127 clear; and the whole set collapses on USDSEK. |
| The G12 stop-first rule costs 0.10R a trade for nothing | Minute data: stop really is first 73.3% of the time. The overcharge is +0.534R, about half the claim. |

### 12. What should happen next?

**This answer has been superseded by a later measurement and the original is
kept below it.**

~~One lookup, not an experiment. Gold's short-side swap is not in this
repository, and the overnight economic verdict turns on it: 0.2038 spreads a
night is breakeven against a known long rate of 1.2616.~~

The swap is no longer decision-relevant. Extending the horizon ladder to two
weeks, one month and one quarter shows **every horizon is negative at a
financing rate of exactly zero**, and no venue can charge less than nothing:

| tf | hours | bars/mkt | edge | 95% interval | net at zero carry |
|---|---|---|---|---|---|
| H1 | 1 | 125,336 | +0.1203 | [+0.065, +0.176] | −0.880 |
| H4 | 4 | 32,581 | +0.1099 | [−0.096, +0.317] | −0.890 |
| D1 | 24 | 6,322 | +0.1648 | [−0.499, +0.850] | −0.835 |
| **W1** | 168 | 1,071 | **+0.4397** | [−0.774, +1.764] | **−0.560** |
| W2 | 336 | 546 | +0.2415 | [−2.324, +2.953] | −0.759 |
| M1 | 730 | 260 | −2.2143 | [−13.97, +8.79] | −3.214 |
| Q1 | 2,190 | 90 | −6.5896 | [−47.3, +29.3] | −7.590 |

**The interval does not exclude a positive net and that is stated rather than
glossed.** W1's net interval is [−1.774, +0.764], whose upper end is above
zero. On the point estimate it fails; on the interval it is not established
either way.

What closes it anyway is the horizon itself. W1 is seven nights, so carry is
charged seven times. At **0.05 spreads a night — a twenty-fifth of gold's
known long rate** — W1 falls to −0.910 and the best horizon reverts to H1 at
−0.882. The only horizon whose interval reaches positive is the one that any
nonzero swap destroys fastest, and at every rate above zero H1 is best at
about −0.88.

**Items 1 and 2 below have since been answered and are closed. What remains
is item 3.**

**1. Decompose the reversal — DONE, and it is volatility-scaled.** Log
absolute move on log spread and log ATR jointly, 5,461 market-hour-year cells,
market fixed effects: **log ATR +0.986** (se 0.045, t +22.0), **log spread
−0.103** (se 0.030, t −3.4), R² 0.513. Bid-ask bounce would have produced the
opposite pair. It is not a dollar artifact — USD-base +0.0996, USD-quote
+0.1581, metals +0.0448 — is positive in 21 of 23 years, and its worst
leave-one-market-out swing is 14%.

That matters because it means the edge in spread units is amplitude ÷ cost
ratio, so a tighter quote genuinely raises it. Had the spread coefficient come
back near one, the edge would have been a constant of the microstructure and
no execution improvement anywhere could have helped.

**2. Could a cheaper venue reach it? — DONE, and no.** The requirement is
execution **8.9× cheaper** than this feed, or **4.7× cheaper than its own
cheapest decile**. Sweeping the cost cross-section outward from the cheapest
half-percent:

| cheapest | spread/ATR | edge | amplitude | markets + |
|---|---|---|---|---|
| 0.5% | 0.00553 | +0.7901 | 0.00437 | — |
| **1%** | 0.00681 | **+0.8897** | 0.00606 | 2/3 |
| 5% | 0.01315 | +0.7753 | 0.01020 | 5/7 |
| 10% | 0.01835 | +0.5198 | 0.00954 | 6/8 |
| 20% | 0.02747 | +0.2232 | 0.00613 | 8/10 |
| all | 0.08881 | +0.1120 | 0.00995 | 10/10 |

**The curve turns.** From the whole sample to the cheapest half-percent the
quote tightens 16.1× and the edge grows only 7.1×, because the amplitude falls
from 0.00995 ATR to 0.00437. Where the spread is small the move is small too.
At the tightest step the edge is no longer climbing at all.

The best step, +0.8897, needs only 1.1× more — but it clears three markets, is
positive on two of them against a required six of nine, produces 189 signals a
year against a required 200, and is the maximum of an eight-step sweep. It is
62% EURUSD and 34% USDJPY: the two deepest books in the panel, not a
time-of-day corner.

**The cost floor is a property of this instrument class, not of the venue.**

**3. A fifth lever, never measured — and it fails worst of all.** Every
verdict above assumes the trade *crosses* the spread. A resting order does
not: limit-in/market-out pays nothing, limit-in/limit-out **earns** a spread.
Against a +0.1120 edge that is the entire shortfall, and it is the execution
the mechanism argues for — fading an extension is liquidity provision, and
short-horizon reversal is the textbook compensation for providing it.

It fails by the largest margin of anything tested. At an offset of 0.25 ATR
the order fills 53.1% of windows:

| | at market |
|---|---|
| windows that **filled** | **−4.3888** round trips |
| windows that **missed** | **+2.9145** |
| **adverse selection** | **−7.3033** |

The resting order fills precisely when the trade was going to be bad. It
saves a spread worth 1.0 and buys a selection that costs 7.3 — and the gap
widens with the offset: −5.11 at zero, −9.54 at 0.5 ATR, −14.95 at 1.0. Zero
of ten markets positive at any offset in either mode.

The apparent improvement at wide offsets is not one. Counting misses as zero,
the all-windows figure rises from −0.4280 to −0.0964, but the fill rate falls
from 53.1% to 10.5% and the edge **per fill** gets *worse*, from −0.8652 to
−1.0506. Approaching zero by trading a tenth as often is less of a loss, not
an edge.

Fills are assumed wherever the quote trades *through* the level by a tick,
with no queue, no partial fill, no rejection and no requote. That is an
**upper bound**, and since even the bound fails, no venue policy can rescue
it.

**4. Still open.** Re-examine whether any of the 837 pre-run hypotheses read
differently on the cleaned frame with the corrected control and metric. Most
are null and would stay null — but that is an assumption and it has not been
checked.

---

## What was built

| | |
|---|---|
| **Measurement engine** | Six layers — tradability, activity, structure, regime, execution reliability, measurement reliability. Quality is coverage × precision × resolution and contains **no return column anywhere**. The sixth layer can veto the other five. |
| **Control hierarchy** | C0–C7, each holding constant what the one before it did plus one more. Every control inherits the rule's own dist/ATR ratio, so the two books are the same instrument. Matching on any post-signal variable **raises** rather than warns. |
| **Fixtures** | 14 on synthetic processes with known answers. Real information survives to C7 at t +14.5; a clock artifact dies at C4 and survives at C7; geometry gap 0.0%. |
| **Vectorised engine** | Bit-identical to the reference on 180 books across 9 markets, 4 families and 5 exit variants. 10× faster. |
| **Failure taxonomy** | 19 codes, each fired by a measured number. There is no code for "not profitable". |
| **Tool registry** | 10 live tools, 2 superseded — kept with the defect named, so an old number can be traced to the tool that made it. |
| **Reproduction** | 18 checks on numbers, not exit codes, with git state and a sha256 per cached series reported separately. |
| **Provenance** | Append-only progress log across 12 phases. |

## Corrections to this report after first writing

Kept rather than edited away, because a report that revises itself silently
is worth less than one that does not revise itself at all.

| where | what changed |
|---|---|
| §3 | The 0.233 exponent was fitted over a ladder ending at one week. The edge **peaks at W1 and falls after it**, so the exponent averages a curve that turns, and the "8,900 hours to breakeven" figure applied the fit five times past its anchor. Retracted. |
| §12 | Gold's short-side swap was named the most decision-relevant unknown. It is no longer: every horizon is negative at **zero** financing, so no swap rate can change the verdict. |
| §12 | A fifth execution lever — passive/limit orders — was identified as never having been measured, and measured. It fails worst of all: adverse selection of −7.3033 round trips against a spread worth 1.0. |
| §12 | Items 1 and 2 of the next-steps list have since been answered. The reversal is volatility-scaled (log ATR +0.986, log spread −0.103), so a cheaper quote genuinely helps — but the edge stops climbing at +0.8897 in the cheapest 1% of cells and turns down after it. Both execution levers are now closed on measured data. |

Both corrections make the negative conclusion stronger, not weaker, which is
worth saying because the opposite direction would deserve more suspicion.

## Integrity state

| | |
|---|---|
| Sealed holdout | 14 symbols, `examined: false`, never opened |
| Finalists declared | 0 |
| Cumulative hypotheses | 1,615 |
| Floor a new change must clear | \|t\| > 5.00 |
| Ledger verdicts | 21 rejected, 6 inconclusive, 1 "accepted" |
| Reproduction | 18 of 18 |
| Regression suites | 12 of 12 |

The single ACCEPTED entry is a **ledger-mechanics artifact, not a finding**.
`wider_stop_corrected_bracket` met its declared margin and the floor, which is
all the ledger checks, while the criterion written to disk before the run had
a third condition — non-negative pooled expectancy — that failed. It is
recorded as such in its own note rather than counted as a win.

## One blocking audit check left open

The engine's pre-trade gates read the spread, so widening it removes trades as
well as charging for them: at 4× spread only 4% of gold's momentum trades
survive, and expectancy *rises* from 2× to 4× because the survivors are a
different population. Every three-scenario cost comparison in this repository
measured cost and reselection together.

It is recorded rather than fixed, because nothing this run concludes goes
through that bracket.

## The standing rule this run earned

> Do not call an excess over any control "directional skill" until it survives
> a control matched on the same geometry, activity, volatility, session,
> regime and range position — and do not call any edge economic until it is a
> ratio of means against the real quote at the entry bar.

---

## Closing

The mandate was not to prove an edge exists. It was to establish whether this
system can separate a real edge from a false one.

It can, and it did so four times — the multiple-testing floor called the best
candidate noise before any out-of-sample data was touched; a fresh market
agreed; a batch test of all eight survivors agreed; and a metric correction
had already removed every apparent clear before the other three ran. It also
caught four of its own defects mid-run, two of which had inflated its own
headline numbers.

The answer to the underlying question is that the information is there, it is
small, and the distance between it and tradability is a factor of eight in the
ratio of edge to spread — a gap that no conditioning state, horizon, target or
execution design tested here closes.
