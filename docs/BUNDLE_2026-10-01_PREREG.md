# Big bundle — pre-registration (2026-10-01, written before any of these numbers is computed)

Operator, 2026-10-01: "มัดรวมทุกอย่างที่คุณเสนอและผมเสนอ ทดสอบทีเดียวเลย" and "เท่ากับทดลองหลายชุด ไม่ใช่ทุกอย่างมัดรวมในชุดเดียว".
So: many SEPARATE experiments (X1-X7), each with its own read-out and its own control, launched in one batch. Ideas are combined
into one strategy only later, and only from experiments that pass on their own. Operator rules in force: no caps (no take-profit,
no maximum hold, no winsorisation, memory feedback-no-caps); every point is autopsied ("ชันสูตรทุกจุด"); stacking is tested
("ซ้อนไม้"); martingale is tested at the operator's request ("ลองการทบไม้แบบมาติงเกลด้วย").

## Common rules
- Bars: Candle Lab (`research/candlelab/lab.py`): gold M5 2009-03..2026-09 (spliced), silver M5 from HistData M1 with the corrected
  clock 2010..2026, resampled to M5 / M15 / H1 / H4 / D1 (22:00 UTC anchor) / W1 (cut grid). Other markets: MT5 cache
  `data/mt5/*_D1.npz`, `*_H1.npz` (Exness demo history, read-only).
- Periods: gold DEV 2009-2015, gold CHECK 2016-2026-09; silver whole history (independent market); other markets whole history.
- Fills: signal at a bar close, entry at the next open; stops inside a bar fill at the stop (at the open if the bar gaps through);
  exits decided on a close fill at the next open. Trades still open at the end are closed at the last close and flagged.
- Costs, round trip: gold 2.5 bp; silver 11.615 bp (the pre-2023 constant for every year, conservative); other markets the
  broker's current spread + 1 bp (MT5 symbol_info, read-only, applied to the whole history). Swap: gold and silver
  `contracts.swap_bp` (longs pay, shorts 0); other markets the broker's current swap specification applied to the history (X6).
- R = the initial stop distance. Trend systems: 2 N, N = ATR20 of the timeframe. No take-profit, no time exit, no clipping.
- Finance: $10,000, risk a fixed % of realised equity at entry, compounding at exits; CAGR, max drawdown, positive years.

## X1 Every-signal autopsy and stacking
- Systems: Turtle S1 (20-bar entry / 10-bar exit), S2 (55 / 20), Chandelier (55-bar entry, exit on a close below the highest
  high since entry - 3 x ATR22, mirror for shorts); long and short; gold and silver on M5, M15, H1, H4, D1, W1; other markets D1, H1.
- Every bar whose close breaks the entry channel is a signal with its own independent trade (overlaps allowed). Flags: TAKEN (the
  one-position system takes it) / SKIPPED (a position was open).
- Per trade: R, gross R, MFE, MAE, bars to the best point, MAE before the best point, +1 R before -1 R, bars held; candle anatomy
  and higher-TF context of the signal bar (lab.anatomy, lab.htf_context).
- Read-outs: R per trade for ALL / TAKEN / SKIPPED per system x TF x market x period; share of total R from trades >= +3 R;
  features separating winners from losers (AUC on gold DEV, gold CHECK, silver; descriptive).
- Stacking portfolios (gold, silver; H1 / H4 / D1): P0 one position; P1 every signal opens a position (no limit; the maximum
  concurrent open risk is reported); P2 a signal opens a position only if every open same-direction position is in profit at the
  signal close (no adding to losers). Risk 0.25 / 0.5 / 1 % per position.

## X2 Martingale — research only
CLAUDE.md section 8 and `data/DEMO_ORDER_PERMISSION.md` keep martingale, grid and averaging FORBIDDEN for every demo or real
order; this experiment only measures what it does to the risk. It cannot create expectancy, so there is no pass / fail.
- M-SEQ: after a loss the next trade's dollar risk = previous x m (m = 1.5, 2); after a win it resets to 1 % of equity; if the
  required risk exceeds equity the trade risks all of it, and losing it is RUIN; a fresh $10,000 account then starts at the next
  trade (ruins are counted over the history). Applied to (a) the one-position trend trades of X1 (gold, silver; H4, D1) and
  (b) random-entry trades with the same exits (direction coin flip, waiting time between trades drawn to match the system's
  trade count, 200 seeds).
- M-ANTI: x 2 after a win, reset after a loss, same accounting.
- M-GRID (averaging, the usual "ทบไม้" EA): gold and silver H1. A cycle opens at a bar open with notional 20 % of equity; each time
  the price moves S against the latest order another order is added with notional x m; all orders close when the price reaches
  the notional-weighted average entry + 0.5 S in the trade direction; no stop-loss. S = 0.5 / 1 / 2 x ATR22(D1) at the cycle
  start; m = 1.0 / 1.5 / 2.0; direction LONG, SHORT, TREND (D1 close vs its 55-day Donchian midpoint at the cycle start) and
  RANDOM (100 seeds). Leverage 1:200 (assumption): an add needing more than the free margin is skipped. Ruin = equity <= 0
  (stop-out at margin level 0 %); a fresh account then restarts. Inside a bar the adverse extreme is taken first. Costs: half
  the round trip per fill; swap per order per night.
- Read-outs: ruins, years to the first ruin, CAGR and max drawdown of each account life, share of cycles won; M-SEQ next to flat
  1 % sizing on the same trades.

## X3 Opposite side
- (a) Loser-profile fade: on gold DEV every-signal trend trades (X1; per system x TF x side), the feature decile with the lowest
  mean gross R (deciles on gold DEV, >= 300 trades in the decile) defines the loser profile; its signals are traded in the
  OPPOSITE direction with the mirrored system (same channel / Chandelier exits and 2 N stop on the other side).
- (b) Candle reversal with structural exits: every (TF, feature) among the M5 / M15 / H1 return effects of Candle Lab that are
  consistent on gold DEV, gold CHECK and silver: in the bucket where the next return is lower, go short; in the opposite bucket,
  go long; stop 1 ATR; exit on a Chandelier 1 ATR trailing stop from the best price (no target, no time).
- (c) Zoo inversion is not repeated: explore_scale already flipped every F2 signal (22 survivors, basket failed).
- Pass (a) and (b): gold CHECK net R per trade > 0 with weekly-cluster bootstrap p < 0.05 after Holm across the tests of that
  part, and silver net R per trade > 0.

## X4 Trend refinements
- (a) Candle filter: score = mean percentile rank (gold DEV distribution) of the signal bar's lower-wick fraction, clv_mean5,
  minus the 1-year ATR percentile, and the position of the close inside the forming W1 bar (signs from the gold autopsy).
  Trade only score >= its gold-DEV median. Gold is in-sample; clean confirmation = silver + 16 MT5 markets.
- (b) Multi-TF: H1 and H4 signals only when D1 agrees (D1 close above its 55-bar Donchian midpoint for longs, below for shorts);
  D1 signals only when W1 agrees. Versus the single-TF system.
- (c) Pyramiding into winners: add a unit every +0.5 N from the last add, up to 4 units (Turtle canonical) and unlimited; every
  stop moves to 2 N from the latest add; exits as the system.
- (d) Breakeven: stop to the entry price once MFE >= 1 R.
- Pass (a), (b): R per trade higher than the unfiltered system on silver AND on >= 60 % of the other markets, pooled difference
  p < 0.05 (bootstrap over market-weeks). (c), (d): CAGR and drawdown reported per market; no pass rule.

## X5 Wild ideas ("ไม่จำกัดแม้กระทั่งความคิดที่เป็นไปไม่ได้")
Each condition is known before the measured window. Outcomes in ATR: same-session return (NY 13-21 UTC, London 07-16 UTC) where
the idea is about a city, next D1 bar, next 5 D1 bars, next 20 D1 bars. Weekly-cluster t; gold DEV, gold CHECK, silver.
1 geomagnetic storm (daily Ap >= 30; Kp max >= 5); 2 sunspot number (monthly change, level percentile); 3 solar flux F10.7 high vs
low; 4 New York cloud cover (deseasonalised by month), sunshine, rain > 5 mm -> NY session; 5 London, same -> London session;
6 full moon +-3 days vs new moon +-3 days (synodic formula from the 2000-01-06 18:14 UTC new moon); 7 solar eclipse +-1 day (NASA
catalogue); 8 Mercury retrograde (mean orbital elements, checked against the 2024 dates); 9 Monday after a US / EU daylight-saving
change; 10 Friday the 13th vs other Fridays; 11 US presidential cycle year (descriptive); 12 Chinese zodiac year (descriptive) and
the 20 trading days before Chinese New Year; 13 BTC halving cycle (descriptive); 14 price digits: close within 0.25 ATR of a $50 /
$100 gold level -> break vs rejection within the next bar (H1, D1), placebo levels shifted by $25; 15 calendar classics: turn of
the month, day before a US holiday, Santa rally, Halloween (Nov-Apr vs May-Oct), day of week, week of month.
Placebo: 50 mirrored base paths (lab.mirror_base) give each test's null |t| distribution. Pass: |t| >= 2 on gold DEV, gold CHECK
and silver with one sign AND beyond the placebo 95th percentile; then a cost check.

## X6 Ten markets with broker swaps
As the last section of `docs/UNCAPPED_COMPARISON_PREREG.md`; the 8 extra cached markets (DE30, JP225, XCUUSD, XPTUSD, USDCNH,
USDINR, USDMXN, USDZAR) are reported separately as untouched markets, never mixed into the original ten.

## X7 WRWR uncapped vs Chandelier long-only
Exactly `docs/UNCAPPED_COMPARISON_PREREG.md`.

## Not in this bundle
The full C11 sieve (K = 999 whole-pipeline placebo paths) needs weeks of compute on this PC; it stays "run last". Candle Lab with
its placebo is the descriptive substitute.

## Reporting
Every test of every experiment is written to `data/bundle/` and reported, failures included; Thai summary in the night report.
