# Measuring the chart directly — what must an edge look like, and what does the data say (pre-registration v1, 2026-09-29)

Committed BEFORE `research/pilot/chart_information_map.py` is run. Operator
question: what shape must an edge have, and what instruments come out when the
measuring tools are pointed at the chart itself rather than at pre-fixed
setups. Codex has not reviewed this; it audits afterwards.

## Part 1 — what an edge must look like (arithmetic, no market claim)
For a strategy taking N independent trades a year with per-trade net edge e and
per-trade SD s, Sharpe ≈ (e/s)·√N. The script tabulates, from the measured s of
1 h and 4 h forward returns: the net and gross edge in bp required for Sharpe 1
and 2 at N = 250 / 1,000 / 2,500; the equivalent hit rate (≈ 0.5 + 0.4·e/s);
the rank correlation ρ a signal must have with forward return (≈ e/s ÷ 0.8 when
trading its sign); and the number of trades, hence years, needed to *detect*
that edge at 5% two-sided / 80% power (n = (2.8·s/e)²).

## Part 2 — an information map of the chart (measurement, not setups)
Instruments, all causal from closed M15 bars (frozen list, 15):
atr_pct, dist_vwap_atr, dist_ema50_atr, dist_ema200_atr, dist_hh20_atr,
dist_ll20_atr, ret1_atr, ret4_atr, ret16_atr, range_ratio, efficiency20,
trend_sep, hour_utc, weekday, session.
Outcome: forward return from the next open to the close of bar i+H, H ∈ {4, 16}
bars, rollover- and gap-free (same construction as edge_search_bp.py).
- **Out-of-era transfer:** bin each feature (deciles fitted on the TRAINING
  era; categories as they are), take the training-era bin mean of the outcome
  as the predictor, and measure Pearson ρ between predictor and outcome in the
  OTHER era. DEV (2021-07..2023-12) and LATER (2024-01..2026-09) both mined, so
  this is out-of-era, not a holdout. Week-clustered bootstrap (2,000 resamples).
- **Direction target:** forward return with the era mean removed (kills gold's
  drift). **Magnitude target:** |forward return|.
- **Primary tests (30):** direction, 15 features × 2 horizons, DEV → LATER,
  α = 0.05/30 = 0.00167. A feature is a *direction lead* only if it also has the
  same sign LATER → DEV with p < 0.05. Magnitude results are descriptive (strong
  effects are expected: volatility clusters and hours differ).
- Reported against the Part 1 requirement: does the best direction ρ come near
  the ρ needed for Sharpe 1 at 1,000 trades a year?

## Expected outcome, stated in advance
Magnitude instruments strong; direction instruments near zero (prior: 0 of 30).
