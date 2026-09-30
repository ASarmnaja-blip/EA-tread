# Hypothesis batch 2 — cross-asset drivers of gold — pre-registration (2026-10-01, committed before any statistic below is computed)

Operator (2026-10-01, before sleeping): find hypotheses in every possibility about gold and the assets that move gold, and apply them.
Research only, paper only, no orders, no alpha. Register: docs/HYPOTHESIS_REGISTER_TH.md (section E and new cross-asset rows).

## Data
- Signals: MT5 (Exness demo, read-only snapshot data/mt5/*.npz, manifest with sha256; research/hyp/mt5_cache.py): D1 and H1 of US500,
  USDJPY, USOIL, DXY, USDCNH (+ EURUSD, USDCHF, AUDUSD, BTCUSD, JP225, USTEC for the descriptive lead-lag map). Precondition: MT5 XAUUSD H1
  closes must match Dukascopy gold H1 best at shift 0 (MT5 time = UTC); otherwise the batch stops.
- Gold trades: Dukascopy gold D1 (22:00 UTC anchor) and H1 with recorded spreads (as batch 1). Silver trades (confirmation): HistData
  silver D1 / H1 with the corrected clock. Costs C4 + swap as batch 1; stop-first first passage; one position at a time per rule.
- A daily signal from an MT5 D1 bar (00:00-24:00 UTC) is known at 24:00 UTC; the trade enters at the open of the first gold (silver) D1 bar
  that opens after that time. Percentile thresholds are causal: computed from the previous 500 daily values of that series (>= 250 needed).

## Primaries (parameters fixed now)
| ID | rule | direction |
|---|---|---|
| X1 | US500 D1 return <= its causal 2.5th percentile (equity crash): short gold, stop 2 ATR(D1), exit after 10 D1 bars | short (flight to gold gives back within ~2 weeks: Baur & Lucey 2010) |
| X2 | USDJPY D1 return <= its causal 2.5th percentile (yen surge / carry unwind): gold for 5 D1 bars, stop 2 ATR(D1) | two-sided: DEV fixes the sign |
| X3 | \|USOIL D1 return\| >= its causal 97.5th percentile (oil shock): gold in the oil direction for 5 D1 bars, stop 2 ATR(D1) | same as oil (inflation channel) |
| X4 | every 20 gold D1 bars (non-overlapping blocks): sign of the DXY 60-day log return; gold opposite for the next 20 D1 bars, stop 3 ATR(D1) | opposite to the dollar trend |
| X5 | USDCNH 20-day log change >= its causal 90th percentile (yuan weakness): long gold for 20 D1 bars, stop 3 ATR(D1) | long (Chinese hedging demand) |
| X6 | gold H1 residual reversal: rolling OLS (previous 500 common hours) of gold H1 log returns on DXY, USDJPY and US500 H1 returns; z = sum of the last 6 residuals / (residual sd x sqrt 6); z <= -2.5 long, z >= +2.5 short at the next gold H1 open; stop 1.5 ATR(H1), exit after 6 H1 bars | against the residual |

## Periods and pass rule
- **DEV** = signal data start (after warm-up) .. 2021-12-31; **CHECK** = 2022-01-01 .. 2026-09-30 (gold); **SILVER** = the same signals traded
  on silver over the whole span.
- Statistics exactly as batch 1 (weekly sums, stationary bootstrap mean block 4, K = 999, seed 20261001; one-sided p; X2 two-sided).
- **Drift control (new, from the batch 1 lesson):** every rule is also run as the same-direction trade entered at EVERY D1 open (H1 open
  for X6) of the same period with the same stop and hold, one position at a time; excess = rule mean R - control mean R.
- **PASS** = DEV Holm-adjusted p <= 0.05 over the six primaries, AND CHECK same sign with one-sided p <= 0.05 AND CHECK excess > 0, AND
  SILVER same sign with p <= 0.10, AND net mean R > 0 in CHECK and SILVER.
- Descriptive only (never a pass): the H1 lead-lag map corr(r_X(t), r_gold(t + L)), L = 1..4 h, for every MT5 series; the same at D1.
