# Research frontier

Generated 2026-09-19T13:42:25Z at commit `1dff926c7b` (tree dirty).

28 registered changes, cumulative hypothesis count 1615, verdicts {'REJECTED': 21, 'INCONCLUSIVE': 6, 'ACCEPTED': 1}.

Sealed holdout: 14 symbols, `examined: False`.

30 progress records across phases phase0-data-integrity, phase0-engineering-audit, phase1-control-hierarchy, phase1-mechanism, phase1-reframe-target, phase1-timeframe-ratio, phase2-failure-distribution, phase2-falsification, phase2-fresh-market, phase2-pilot, phase2-validation, phase3-fresh-market-batch, phase3-intraday-window, phase4-expanded, phase4-straddle, phase4-straddle-intrabar.


## Confirmed

Survived a preregistered test against a criterion written before the result existed.


**Directional information exists at the one-hour horizon, is universal across ten markets, and is not an artifact of any execution assumption.**  
`short_horizon_reversal_mechanism`  
Fading the previous hour wins the direction 51.71% of the time, t +17.84 against 50%, positive on 9 of 9 panel markets, 52.87% in 2004-2014 and 51.72% in 2015-2026. It reproduces on USDSEK, which no hypothesis here had used, at +0.075 of a round trip on 126,392 signals. The reversion representation adds +0.53pp, t +5.96 against a 4.74 floor, 9 of 9, and survives being computed one bar late with 58% of its magnitude. Measured with no stop, no target, no tie-break and no one-position rule.


**That information is worth between seven and twelve percent of what it costs to act on, and the gap is structural rather than a search failure.**  
`short_horizon_reversal_mechanism`  
On the ratio of means the unconditional fade is +0.1198 of a round trip on the panel at t +4.94, 9 of 9, and +0.075 on USDSEK. Mean win 9.053 spreads against mean loss 9.706; the win rate needed to break even ignoring cost is 51.75% and 52.24% clears it, but the win rate needed while paying one round trip is 59.91% and it is short by 7.67 percentage points.


**The predictable move scales as horizon to the 0.233, far below the square root, so no horizon reaches one round trip.**  
`edge_to_cost_across_timeframes`  
Fitted over six timeframes and nine markets on the ratio of means. H1 +0.1203 becomes W1 +0.4397, which is 3.7x over a 168x bar length where a square root would give 13x. At that exponent the edge would not reach one round trip until about 8,900 hours. With gold's known long swap the net has a single maximum at 2.68 hours and is negative there; the financing rate at which it would break even is 0.2038 spreads a night against a known 1.2616.


**Removing financing entirely by never spanning a rollover does not close the gap, and the scaling reverses inside a session.**  
`intraday_no_rollover_window`  
Best cell enters 07:00 UTC and holds three hours: +0.717 of a round trip, bootstrap t +4.14, skill against C7 +0.714 at t +3.18 on 8 of 9, 5,221 signals a market. Shortfall 0.283 spreads, measured. Mean edge by hold length falls from +0.144 at two hours to -0.225 at eight, because a cross-timeframe bar spans sessions and an intraday window does not.


**29% of every bar this project had used is an hour the venue was shut, and it distorted which trades were eligible.**  
`weekend_contamination`  
58,233 flat bars in gold alone, 28.8% to 31.0% on every market in every year. Wilder ATR falls to 6.5% of its Thursday level by Sunday, and the engine's spread-under-10%-of-ATR gate rejected 84.8% of Monday bars against 56.9% of Thursday's. Fixed; Monday's share of entries moved from 14.5% to 17.6% against a flat week's 20%.


**A bracket pays its own width rather than the expected move, which makes path asymmetry the target with the better arithmetic - and nothing lifts it.**  
`expanded_three_targets`  
At a 1.5-ATR bracket the width is 27 spreads, so breakeven sits at p = 52.89% rather than at a five-fold amplitude increase. The unconditional p is 50.08% and 0 of 118 hypotheses lifted it in both halves of the sample at any of three bracket widths.


**The conditional breakout straddle's apparent edge was a scoring assumption, and minute data resolves it against the strategy.**  
`expanded_three_targets`  
Scoring windows that touch both barriers in one bar as no trade gave +2.498 round trips for a 2-ATR dislocation state against an unconditional -0.140, lift over C7 +1.078 at t +4.94 on 8 of 9. Those windows are 19.9% of that state against 7.9% of an unconditioned bar. Gold minute data 2019-2026 resolved every one of them: 130 of 130, 53 of 53 and 3,121 of 3,121 stopped out, none profitable, mean -16.2 to -25.8 spreads. The resolved figures land on the pessimistic bound and the state reads -0.647.


**The failure distribution names cost, not measurement.**  
`pilot_conditional_amplitude`  
Over 127 pilot hypotheses: COST_DOMINATED 52.0%, NO_DIRECTIONAL_SKILL 31.5%, CROSS_MARKET_INSTABILITY 27.6%, BELOW_MULTIPLICITY_FLOOR 18.1%. Activity selection accounts for 2.4% and session selection 1.6%, so the control hierarchy found almost no selection artifacts to remove.


**A control must inherit the rule's risk geometry or it is a different instrument, and a spread-normalised edge must be a ratio of means.**  
`control_geometry`  
random_like took the random bar's own high or low as the invalidation level, so its stop sat a third as far from entry as the rule's while R divides by that distance - dist/ATR median 0.559 against 1.638. The replacement measures a 0.00% gap across all eight levels. Separately, computing edge as the mean of move/spread ratios implicitly sizes inversely to each trade's own spread and reads 1.3x to 2.3x above the economics.


## Falsified

Claims this project made and this project then refuted. Several were made in the same session that refuted them; they are kept rather than edited away.


**CLAIMED EARLIER IN THIS SESSION: 91% of all measured skill is activity selection.**  
`vol_matched_control`  
Measured through the defective control above. With geometry matched, a synthetic rule that selects busy bars and faces a coin shows |t| below 2 at every one of the eight control levels, C1 included. There is no activity artifact to remove. The 91% was the geometry gap. The mechanism runs the other way: R divides by an ATR-derived distance, so selecting volatile moments is charged, not rewarded.


**CLAIMED EARLIER: the four setup families carry skill worth +0.0171R against a timing control.**  
`control_hierarchy_restatement`  
On the cleaned frame with a geometry-matched control the same quantity is +0.0026 to +0.0066, and negative for one family. Against the strongest control all four are negative, the best being reversion at t -0.14.


**ASSUMED FOR 837 HYPOTHESES: R through a stop-and-target bracket is a neutral way to ask whether a rule has directional information.**  
`bracket_as_a_neutral_measure`  
R divides by a stop distance set from ATR. Every family here fires on high-ATR bars, so a larger denominator earns a smaller R for the same price move. Two independent synthetic fixtures reproduce the sign.


**CLAIMED MID-RUN: fading a range expansion after a quiet bar reaches +1.278 spreads, above the 1.105 cost.**  
`pilot_conditional_amplitude`  
Two independent refutations. The metric was a mean of ratios; on the ratio of means the same hypothesis is +0.724 and zero of 127 pilot hypotheses clear the bar where five appeared to. And on USDSEK the whole surviving set collapses - panel mean +1.447 against USDSEK mean +0.086, four of seven beating the unconditional fade, which is what a coin gives, and none exceeding one round trip.


**CLAIMED EARLIER: the G12 stop-first rule has been costing 0.10R a trade for no reason.**  
`ambiguous_bars`  
Gold minute data resolved the ambiguous bars: stop really is first 73.3% of the time at the 1x stop and 72.2% at the 2x. The overcharge is +0.534R per ambiguous bar, about half the claim.


## Unresolved


- Whether the short side of gold's swap is charged at the same rate as the long side. The whole overnight economic verdict turns on it: at 0.2038 spreads a night the reversal breaks even, at the known long rate of 1.2616 it cannot. Nothing in this repository holds the short figure. This is the single most decision-relevant unknown and it is one lookup, not an experiment.

- Whether a venue materially cheaper than the cached feed exists for a retail account. Every economic verdict is a ratio to that feed's spread, and the live account's quoted gold spread of 260 points is 1.5x tighter than the cache's 396-point median at 07:00 UTC. A venue three times cheaper would change the answer; whether one exists is not a question this data can settle.

- Why 42% of the conditional reversal lives in the most recent quote. It survives the one-bar lag, so it is not purely microstructure, but the part that does not survive has no mechanism attached to it.

- Whether the reversal is one phenomenon or several with a common sign. Leave-one-market-out moved the t by 17% on the candidate, but the unconditional effect has not been decomposed, and the dollar is on one side of six of the nine panel markets.

- The one blocking audit check left open: the engine's pre-trade gates read the spread, so a cost sweep reselects the population. At 4x spread only 4% of gold's momentum trades survive. Nothing this run concludes goes through that bracket, so it was recorded rather than fixed.

- The -0.048R bracket penalty at the 1x stop that survives the G12 correction. The wick-clipping hypothesis remains untested.



## Blind spots


- Every instrument in the panel is a retail CFD quote from one venue. No result here has been checked against an exchange-traded series, and the spread that decides every economic verdict is that venue's.

- Volume is present in the feed and has never been established as anything other than tick count. The activity layer now tests for it and reports proxy-for-range when the correlation with true range exceeds 0.8.

- Position sizing and portfolio construction are absent from every measurement. A per-trade edge of -0.878 spreads cannot be rescued by sizing, but a positive one's Sharpe would depend on it entirely.

- No measurement in this project conditions on anything outside the price series - no rates, no positioning, no calendar beyond the hour and the weekday. The NFP window was tested once and only for structure.

- The sealed holdout is 14 FX crosses with no USD leg. Nothing in it is gold, and the only instrument whose costs are known from a live account is gold.



## New measurements this cycle produced


- edge in spread units at the entry quote, rather than R through a bracket - the only measure so far that has produced a comparable number across timeframes

- the scaling exponent of predictable move against horizon, which turns a search over timeframes into a two-parameter question

- break-even financing rate, which converts an unmeasurable cost into a threshold that can be checked against a broker's published sheet

- sign accuracy reported apart from magnitude, which separates a rule that is right often from one that is right largely



## Next discriminating experiments


- Find the short-side swap for gold, from the account spec or the venue's published sheet. It decides an already-measured question and costs nothing, and it is the only item on this list that could change a conclusion without new research.

- Path asymmetry as a separate target: does any state predict which side of a bracket is touched first, independently of where price ends up? That is what a bracket monetises and it has never been asked directly. It is also the one target whose economics differ from direction's, because a bracket that resolves early pays less time-cost.

- Expansion probability as a non-directional target. If direction is structurally unaffordable at these costs, whether the next range is large is a different question - and the pilot's AMPLITUDE family already showed that range states are the only ones carrying anything.

- Decompose the unconditional reversal across the ten markets to establish whether it is one phenomenon or several. Everything conditional has failed; the unconditional effect is the only thing left standing and it has never been taken apart.

- Re-examine whether any of the 837 pre-run hypotheses would read differently on the cleaned frame with the corrected control and metric. Most are null and would stay null, but that is an assumption and it has not been checked.

