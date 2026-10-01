# Trend following vs simply holding — pre-registration (2026-10-01, before any of these numbers is computed)

Operator chose options ก and ค of `docs/BUNDLE2_2026-10-01_RESULTS_TH.md`: is the D1 trend result an edge in timing, or only the markets'
rise (beta)? And does it survive long bear markets (longer histories, downloaded only after the operator approves the file list)?

## Data and systems
- Clean: 15 MT5 markets (USDINR excluded), D1 2016-08..2026-09, broker cost and swap (`data/bundle/broker_specs.json`). Gold Dukascopy D1
  2003-05..2026-08 (2003-08 clean, reported per period); silver 2010-26 (reported). Later: the long histories of option ค.
- Systems: Turtle S1 (20 / 10), S2 (55 / 20), Chandelier (55, 3 ATR22); long-only and long + short; one position per market (TAKEN trades);
  2 N initial stop; no take-profit, no time exit.

## Test 1 — timing value against random placement (the beta control)
Each taken trade has a net % return (direction x (exit fill / entry - 1) - round-trip cost - swap) and a duration in bars. Control: the
same trades (same direction, same duration) placed at random entry bars where the whole duration fits, return = direction x (open at entry
+ duration / open at entry - 1) - the same cost - the swap for that span; 2,000 placements per market and system. Timing alpha of a market =
mean real net % return per trade - mean control net % return per trade. Pooled alpha = the average over markets (equal weight); one-sided p
= share of the 2,000 joint placements whose pooled control alpha is >= the real one.
PASS (per system, clean markets): pooled alpha > 0 with p < 0.05 AND alpha > 0 in >= 60 % of the markets.

## Test 2 — buy-and-hold matched to the same drawdown
Per market: the trend system at 1 % risk per trade (CAGR, maximum drawdown) vs buy-and-hold of the same market over the same span (daily
close-to-close, long swap charged) at a constant leverage L in (0, 5] chosen so that its maximum drawdown equals the trend system's.
Also an equal-weight 15-market buy-and-hold portfolio scaled to the trend portfolio's maximum drawdown.
PASS: the trend system's CAGR > the drawdown-matched buy-and-hold CAGR in >= 60 % of the markets AND at the portfolio level.

## Test 3 — bear phases (descriptive)
Every decline of >= 30 % from a peak to its trough in a market's sample: buy-and-hold vs trend (long-only and long + short) over that window.

## Option ค (only after the operator approves the download list)
Tests 1-3 repeated on long histories; close-only series use close-based channels (a stated deviation).
