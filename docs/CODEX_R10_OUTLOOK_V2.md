Verdict: do not interpret the eventual historical output as validation or as authority to alter sizing. Forecast scoring is mostly prequential, but the implementation and contract still have material defects.

## Critical

1. **The contract contains a `vol_scale` authorization loophole.**  
   `docs/WPWB_OUTLOOK_V2_PREREG.md:18-22` first says nothing changes `vol_scale`, then explicitly describes pre-validation use via `min(scale_B0, scale_model)`. That can be read as permission to operationalize a historically selected model. `scale_model`, its calibration fail-safe, promotion trigger, and required authorization are also undefined. Section 8 says the next step is only a shadow log, but the contradiction remains. Historical results must explicitly be barred from changing either `vol_scale` or `effective_scale`.

## High

2. **B0, HAR and MVOL do not have distributional parity.**  
   `outlook_dev.py:113-132` gives each model an expanding pool beginning whenever that model first issues a point forecast. Consequently, at the first common scored date B0 has residuals reaching back near 2003, HAR starts much later, MVOL later still, while B1 uses only 52 trailing RV observations. This leaves the Round 6 baseline-parity objection unresolved and can manufacture calibration/tail differences through unequal era mixtures. The contract’s “one distributional method” claim at `WPWB_OUTLOOK_V2_PREREG.md:47-58` does not cure unequal windows and warm-ups.

3. **The reported “last-cut” MVOL coefficients use the target week.**  
   `outlook_dev.py:417-421` fits on every valid row, including the final cut’s realized `log RV`. The forecast at that cut was fitted only on `j < k`. Thus the printed coefficient vector is look-ahead-contaminated relative to the promised “coefficients … at the last cut” (`WPWB_OUTLOOK_V2_PREREG.md:97-99`). Scores are unaffected, but the reported model interpretation is not pre-cut.

4. **The vendor audit does not establish transportability or aligned weeks.**

   - `outlook_dev.py:309-315` declares weeks independently valid for each vendor and pairs them whenever both exceed 80 bars; it never verifies identical H1 timestamps/session coverage. Dukascopy accepts partially populated resampled hours (`build_all_tf.py:71-75`), whereas Exness creates an H1 bar only from 12 contiguous M5 bars (`mtf_engine.py:103-143`).
   - Round 6 required RV, range, labels and MAE comparison; `outlook_dev.py:317-323` checks only RV and labels. Y3 can therefore diverge through bid/ask spreads and extrema while the audit still passes.
   - Exness `m_k` is constructed only from the sliced audit series (`outlook_dev.py:308-315`), so class agreement omits the first 52 valid overlap weeks rather than auditing the whole stated interval.
   - A failed audit merely permits development to continue (`WPWB_OUTLOOK_V2_PREREG.md:105-108`).

5. **Moving-block intervals do not preserve calendar dependence for sparse targets.**  
   `outlook_dev.py:217-226` bootstraps adjacent elements after missing/risk-set weeks have been dropped at `:385`. For onset, exit and Y3, an “8-week” block is therefore eight eligible observations potentially spread across many calendar weeks. Gaps and regime durations are compressed. This is not the preregistered bootstrap of weekly paired differences and can materially understate uncertainty.

6. **`m_k` is causal but not actually frozen or auditable.**  
   `outlook_dev.py:137-143` recomputes medians from the current mutable dataset; the workbook does not store `m_k`, its 52 source cut IDs, validity mask, or hashes. This fails the specific Round 6 requirement at `WPWB_DEBATE_2026-09-28.md:1395-1398`. Corrections to history can silently relabel old outcomes.

## Medium

7. **Calibration reporting does not meet Round 6 or the v2 contract.**

   - `outlook_dev.py:194` uses the raw empirical CDF as PIT. For a finite empirical ensemble this is a discrete rank statistic, not an ordinary continuous PIT; a declared randomized/rank-PIT convention is needed.
   - `:412-415` reports PIT only overall, despite `WPWB_OUTLOOK_V2_PREREG.md:97-98` requiring it per model and period.
   - Coverage at `:195-196,359-362` is arithmetically correct, but has no block uncertainty or tail-coverage diagnostic, both requested in Round 6.
   - For models with missing rows, `:412` divides histogram counts by `len(s)`, including NaNs, so shares may sum to less than one.

8. **Period-specific alarms are not truly prequential from the full history.**  
   `outlook_dev.py:402-408` first restricts predictions to each reporting period and then `alarm_stats()` restarts the 50-case warm-up and percentile history (`:229-233`). PH and D2 therefore discard causally available earlier alarm predictions. The printed ALL row is causal, but the period rows written to Excel implement a different rule.

9. **Missing-forecast reporting is incomplete.**  
   The contract promises counts “per model and why,” but `outlook_dev.py:350` reports only condition-number failures—not warm-up, residual-pool shortage, invalid lag weeks, missing GVZ, or missing S1.

10. **The exact RPS convention was not frozen in the document.**  
    `outlook_dev.py:198-200` correctly computes normalized four-class RPS, dividing the three cumulative terms by 3. The formula is sound, but the preregistration merely says “ranked probability score,” despite Round 6 explicitly requiring the convention to be fixed.

## No defect found in these areas

- The CRPS formula at `outlook_dev.py:167-171` is the correct empirical-ensemble identity.
- Point-model fits use only `j < k` (`:75-94`).
- Residuals enter pools only after their target week (`:118-125`).
- Y3 ratio pools append the current outcome only after scoring it (`:185-213`).
- Fixed Y3 events are common across models; the model affects probabilities, not realized labels.
- The overall alarm threshold uses only prior eligible predictions.
- Current data contain zero Y3 entry bars whose open precedes the cut, although `y3_series()` should still formally select the first bar opening after the cut rather than infer that from close time.

`python research/wpwb_weekly/outlook_dev.py --tests` passed. Those tests cover point forecasts/residual ensembles only; they do not exercise scoring, `m_k`, Y3, alarms, calibration reporting, bootstrap validity, or vendor alignment.