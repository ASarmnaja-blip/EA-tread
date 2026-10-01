# WRWR uncapped vs simple trend following — pre-registration (2026-10-01, before any uncapped WRWR number is computed)

Operator: "งั้นทดลองทั้งระบบ wrwr และระบบตามเทรดได้เลย". Operator rule (memory feedback-no-caps): no profit caps, no time caps, no clipped P&L.

## WRWR uncapped
- Candidates: the Family 2 signal set (gold Dukascopy, silver HistData with the corrected clock), H1 / H4 / D1, sessions as before, FOLLOW / FADE,
  initial stop k = 1 or 2 ATR(14) of the timeframe. **No take-profit and no maximum hold.** Exit variants (4): Chandelier trailing stop at the best
  price since entry minus 2 or 3 x ATR at entry (never below the initial stop), or a close beyond the opposite 10- or 20-bar channel (initial stop
  still active). Trades run until the exit or the end of the data. Costs C4, swap contracts.swap_bp, stop-first inside a bar, gaps fill at the open.
- Selector, portfolio, risk rules, vol_scale, regime cells, 144 configurations, f = 1 %: unchanged (WRWR v2 / C2).
- Out-of-sample procedure (as batch 4): at the first cut of each year (gold 2010..2026, silver 2012..2026) adopt the configuration with the
  largest trailing t of weekly net R over the known active weeks; trade that year.

## Simple trend baseline (fixed now)
**Chandelier long-only** (55-day entry, exit on a close below the highest high since entry - 3 x ATR22, 2 N initial stop) on gold and on silver,
1 % risk per trade, C4 cost + swap. Turtle S1 / S2 and long+short versions are reported alongside, never as the baseline.

## Endpoints and reading
- Per metal over the same years as the WRWR procedure: total R, R per year, CAGR at 1 % risk, max drawdown, positive years.
- WRWR "adds value" only if its out-of-sample procedure beats the Chandelier long-only baseline on BOTH metals in total R and in CAGR. Otherwise
  the simple trend rule is the core and WRWR is at most a risk overlay.
- Also reported: full-sample totals of all 144 configurations (share positive, best, median) and of the SHADOW configuration indices.

## Trend systems across markets
The ten-market portfolio is re-run with swap for every market: the broker's current swap specification (MT5 symbol_info, read-only) applied to the
whole history (an assumption, stated), next to the earlier no-swap figures.
