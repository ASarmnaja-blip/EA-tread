# Research frontier

Generated 2026-09-19T09:20:20Z at commit `66ec8984c7` (tree dirty).

23 registered changes, cumulative hypothesis count 885, verdicts {'REJECTED': 17, 'INCONCLUSIVE': 5, 'ACCEPTED': 1}.

Sealed holdout: 14 symbols, `examined: False`.

12 progress records across phases phase0-data-integrity, phase0-engineering-audit, phase1-control-hierarchy, phase1-mechanism, phase1-reframe-target, phase1-timeframe-ratio.


## Confirmed

Survived a preregistered test against a criterion written before the result existed.


**Directional information exists at the one-hour horizon and is not an artifact of any execution assumption.**  
`short_horizon_reversal_mechanism`  
Fading the previous hour wins the direction 51.71% of the time, t +17.84 against 50%, positive on 9 of 9 markets, 52.87% in 2004-2014 and 51.72% in 2015-2026. The reversion representation adds +0.53pp on top, t +5.96 against a 4.74 floor, 9 of 9. It survives being computed one bar late with 58% of its magnitude. Measured with no stop, no target, no tie-break and no one-position rule.


**The predictable move grows as the square root of the horizon while financing grows linearly, so the net has a single maximum and it is negative.**  
`edge_to_cost_across_timeframes`  
Exponent fitted at +0.536 over six timeframes and nine markets, against the 0.50 written down before the run. With gold's known long swap the maximum net sits at 2.68 hours and is -0.878 spreads. The financing rate at which it would break even is 0.2038 spreads a night against a known 1.2616 - a factor of 6.2.


**29% of every bar this project has used is an hour the venue was shut, and it distorted which trades were eligible.**  
`weekend_contamination`  
58,233 flat bars in gold alone, 28.8% to 31.0% on every market in every year. Wilder ATR falls to 6.5% of its Thursday level by Sunday, and the engine's spread-under-10%-of-ATR gate rejected 84.8% of Monday bars against 56.9% of Thursday's. Fixed; Monday's share of entries moved from 14.5% to 17.6% against a flat week's 20%.


**A control must inherit the rule's risk geometry or it is a different instrument.**  
`control_geometry`  
random_like took the random bar's own high or low as the invalidation level, so its stop sat a third as far from entry as the rule's - dist/ATR median 0.559 against 1.638 - while R divides by that distance. The replacement synthesises the level at the rule's own ratio and measures a 0.00% gap across all eight control levels.


## Falsified

Claims this project made and this project then refuted. Several were made in the same session that refuted them; they are kept rather than edited away.


**CLAIMED EARLIER IN THIS SESSION: 91% of all measured skill is activity selection.**  
`vol_matched_control`  
Measured through the defective control above. With geometry matched, a synthetic rule that selects busy bars and faces a coin shows |t| below 2 at every one of the eight control levels, C1 included. There is no activity artifact to remove. The 91% was the geometry gap.


**CLAIMED EARLIER: the four setup families carry skill worth +0.0171R against a timing control.**  
`control_hierarchy_restatement`  
On the cleaned frame with a geometry-matched control the same quantity is +0.0026 to +0.0066, and negative for one family. Against the strongest control all four are negative, the best being reversion at t -0.14.


**ASSUMED FOR 837 HYPOTHESES: R through a stop-and-target bracket is a neutral way to ask whether a rule has directional information.**  
`bracket_as_a_neutral_measure`  
R divides by a stop distance set from ATR. Every family here fires on high-ATR bars, so a larger denominator earns a smaller R for the same price move, and the measure charges a rule for selecting movement whether or not its direction is right. Two independent synthetic fixtures reproduce the sign.


**CLAIMED EARLIER: the G12 stop-first rule has been costing 0.10R a trade for no reason.**  
`ambiguous_bars`  
Gold minute data resolved the ambiguous bars: stop really is first 73.3% of the time at the 1x stop and 72.2% at the 2x. The overcharge is +0.534R per ambiguous bar, about half the claim.


## Unresolved


- Whether the short side of gold's swap is charged at the same rate as the long side. The whole economic verdict turns on it: at 0.2038 spreads a night the reversal breaks even, at the known long rate of 1.2616 it cannot. Nothing in this repository holds the short figure.

- Whether any conditioning state makes the one-to-three hour predictable move five times its unconditional size, which is what the maximum-net point requires. The unconditional effect at 2.68 hours is about 0.23 spreads against a cost of 1.105.

- Whether the reversal is the same phenomenon across all nine markets or several with a common sign. Leave-one-market-out has not been run, and the dollar is on one side of six of the nine, so nine markets are not nine independent samples.

- Why 42% of the conditional reversal lives in the most recent quote. It survives the one-bar lag, so it is not purely microstructure, but the part that does not survive has no mechanism attached to it.

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


- Conditional amplitude search. Find states in which the one-to-three hour signed move is a large multiple of its unconditional size, measured in spread units at the entry quote. The bar is set by the economics rather than by significance: 1.105 spreads at the 2.68-hour maximum, against an unconditional 0.23. This is the discovery phase and it is now a search for amplitude, not for a rule.

- Leave-one-market-out on the reversal, to establish whether nine markets are evidence or one dollar trade seen nine times.

- Path asymmetry as a separate target: does any state predict which side of a bracket is touched first, independently of where price ends up? That is what a bracket actually monetises and it has never been asked directly.

- Expansion probability as a non-directional target. If direction is structurally unaffordable, whether the next range is large is a different question with different economics.

- Find the short-side swap for gold, from the account spec or the venue's published sheet, because it decides an already-measured question.

