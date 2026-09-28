# WPWB Weekly Outlook — probability forecast pre-registration (DRAFT v1, not frozen)

> **v1 status after Codex Round 6 (18 objections, all accepted):** this is a
> **shadow research programme**, not a replacement test. All history to
> 2026-09 is development; 2019-01..2021-06 is a contaminated pseudo-holdout
> used once for effect-size and power estimates; confirmation is prospective
> only. If M-vol is ever used before prospective validation, the risk report
> takes `min(scale_B0, scale_Mvol)` — it can only cut risk. Targets are
> redefined: Y1a level class (denominator m_t frozen and logged), Y1b onset
> probability (scored on onset cases), Y2 weekly RV predictive distribution
> (primary score CRPS of log RV; range is display only, not stops/targets),
> Y3 MAE distribution at fixed bp thresholds from full bid/ask OHLC (shown as
> the worse side only), Y4 removed from the operator report. Traces are fixed
> in `docs/WPWB_TRACE_REGISTRY.md` (core: HAR RV + GVZ level; others shadow).
> News flags enter forward only. The ±5-point per-bin reliability veto and the
> two-score gate are dropped (Codex power simulation). Sections below are the
> v0 text kept for the record where not superseded by this box.

Operator direction 2026-09-29 (Thai): "เราจะหาข้อมูลเพื่ออ่านร่องรอยให้ได้มากที่สุด
เพื่อพยากรณ์ความเป็นไปได้ในสัปดาห์ถัดไปในเวลานั้นๆ" — read as many traces as
possible to forecast next week's possibilities at each Friday cut. The risk
frame (weekly risk report v2.1: 0.03 lot/$10k × vol_scale, account stop 30%)
stays in force regardless of this work. Draft for Codex debate; nothing is run
on the evaluation periods before freeze. No order, EA change or PR authorised.

## 1. What is forecast (targets, all observable after the week ends)

At each Friday 22:15 UTC cut, for the coming week (cut, cut + 7 d]:

| id | target | forecast form | why it matters |
|---|---|---|---|
| Y1 | volatility level class of the week (สงบ/ปกติ/ผันผวนสูง/รุนแรง, RV vs median of the past 52 weeks, spec v2 edges) | 4 probabilities | size and whether to trade at all; includes the probability of a volatile-episode **onset** |
| Y2 | weekly high–low range (bp of the first close) | quantiles 10 / 50 / 90 | stop and target distances |
| Y3 | worst adverse excursion within the week for a long and for a short opened at the first H1 bar (bp) | P(MAE > 1σ̂), P(MAE > 2σ̂), σ̂ = forecast weekly vol | how often a stop of a given width is hit, either side |
| Y4 | sign of the week's return | P(up) | **measured, not claimed**: every weekly direction trace so far failed (0/40, 0/10); the default model is the base rate |

## 2. Traces (causal: available before the cut)

| group | trace | available from | note |
|---|---|---|---|
| A | XAU H1 realised variance: last week, mean of last 4, mean of last 26 (HAR) | 2003-05 (Dukascopy H1), 2021-07 (Exness) | persistence of volatility, rho ≈ 0.81 |
| B | GVZ (Cboe gold implied volatility): Thursday close, 1-week change, GVZ² ÷ realised variance (risk premium) | 2009-09 | forward-looking; Thursday only, so no Friday look-ahead |
| C | scheduled USD news next week: FOMC decision, NFP, CPI flags | 2022-01 (MT5 calendar); earlier only from an authoritative Fed/BLS schedule, never inferred from price | dates are known in advance; used for magnitude only |
| D | short-week flag (trading days next week from the exchange calendar) | all | holidays compress or extend risk |
| E | cross-asset realised vol last week: DXY, US500 | 2023-09 | too short for development; logged only |
| F | CFTC managed-money percentile, 2-year yield 13-week change | 2021 / 2016 | logged only; failed as direction traces (Part 37) |

## 3. Models (few knobs, fixed now)

- **M-vol:** log RV_{t} = a + b1 log RV_{t−1} + b4 mean log RV_{t−4..t−1} + b26 mean
  log RV_{t−26..t−1} + g log GVZ²_{Thu} + c·news flags + d·short-week + e,
  expanding OLS on past weeks only (>= 104), residual SD s_t; predictive
  distribution lognormal with the v/2 correction.
- Y1 probabilities = predictive probability mass in each class interval
  (edges from the past-52 median at the cut).
- Y2 quantiles = predictive √RV × expanding past quantiles of range ÷ √RV.
- Y3 = expanding past frequencies of MAE ÷ √RV exceeding 1 and 2, scaled by
  the forecast (separately long / short).
- Y4 = expanding base rate of up weeks (no direction trace enters unless a
  separately pre-registered forward test passes).

## 4. Baselines and scores

- B0 = the current report (EWMA 0.75 lognormal, residual SD from EWMA errors).
- B1 = climatology: past-52 class frequencies / quantiles.
- Scores: ranked probability score (Y1), pinball loss (Y2), Brier (Y3, Y4),
  plus reliability tables (predicted vs realised frequency per bin) and PIT.

## 5. Periods (proposal for debate)

- Development: 2009-09 .. 2018-12 (Dukascopy H1 + GVZ); fit and choose nothing
  else — the model form is fixed above.
- Holdout: 2019-01 .. 2021-06 (Dukascopy H1; not part of the project's mined
  2021–2026 set), opened once.
- 2021-07 .. 2026-09: already used for P2-C (volatility), so descriptive only.
- Forward: from the first cut after freeze; the report shows the Outlook next
  to B0 until the adoption rule is met.

**Adoption rule (proposal):** the Outlook replaces B0's volatility forecast in
the risk report only if, on the holdout, its RPS and pinball loss are both
better than B0 with a block-bootstrap 95% interval excluding zero, and its
reliability stays within ±5 points per bin. Y4 is displayed only as "base rate
≈ x%, not a signal". No alpha is spent: this is a risk forecast, not a
trading edge (same reasoning as spec v2).

## 5b. Candidates added from the hole study (2026-09-29, see docs/WPWB_HOLES.md)

Found on 2021-07..2026-09 (already mined), so they may only be **confirmed on
an independent era**: GVZ level vs its 1-year median (AUC 0.68 for onset),
price near the 52-week high (0.67), last-week RV (0.65). They enter M-vol as
fixed extra regressors and are judged on 2009-09..2021-06 only. Intraweek
breaker (H2): RV since the Sunday reopen vs the forecast pace, threshold to
be frozen in v1 before any evaluation.

## 6. Open questions for Codex

1. Is GVZ (GLD options, US hours) valid for a Friday 22:15 UTC XAU cut when
   taken from Thursday's close; is the Friday close usable instead?
2. News flags before 2022 need an authoritative schedule; is it worth
   downloading Fed/BLS schedules, or should C enter only forward?
3. Is 2019-01..2021-06 clean enough as holdout given the project touched 2016–2021
   D1/H1 for direction tests (Parts 34–37)? Those were direction, not
   magnitude, tests.
4. Power: with ~120 holdout weeks, what RPS improvement over B0 is detectable?
5. Anything that makes Y3 (adverse excursion) misleading for real stops
   (weekend gaps, spread widening at news, H1 vs tick extremes)?
