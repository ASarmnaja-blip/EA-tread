# WPWB Outlook v2 — frozen development contract (2026-09-29)

Operator instruction (Thai, 2026-09-29): free hand to find ways to read the
market and forecast the next week, without straying far from WPWB; report when
done, before the next step.

This file turns `docs/WPWB_OUTLOOK_PREREG.md` v1 (draft, Codex Round 6: 18
objections, all accepted) into an executable contract. It is committed before
any model below is fitted on real data. It adds one input from the regime atlas
(LOGIC_LEDGER Part 51): GVZ looked strongest for *exits* from high volatility,
so an exit target (Y1c) is scored next to onset.

## 0. Status and what it can and cannot do
- **All history is development.** 2019-01..2021-06 is a contaminated
  pseudo-holdout (Round 6 objection 1), reported once in the same run for
  effect size only. 2021-07..2026-08 is the mined era, descriptive only.
- **No superiority claim, no gate, no alpha spent.** Intervals are printed as
  effect-size uncertainty. Nothing here changes `vol_scale`, the frozen risk
  rules (riskrules.py) or any order. The only possible next step is a
  **forward shadow log** registered separately; if a model were ever used
  before prospective validation it could only enter as
  `effective_scale = min(scale_B0, scale_model)` (Round 6 objection 13).
- No direction target, no direction trace (Round 6 objection 14; Part 51).

## 1. Clock and data (spec v2 conventions)
- Cuts: Friday 22:15 UTC, week k = (cuts[k], cuts[k] + 7 d], H1 bars assigned
  by close time (open + 1 h); first cut 2003-05-09; weeks with < 80 H1 bars are
  invalid and never enter a fit, residual pool or score.
- Source: Dukascopy H1 (`build_all_tf.load_kind("hour")`), bid OHLC for RV,
  range and labels; bid and ask OHLC for Y3. Data end 2026-08-31, so the last
  scored target week is the one starting 2026-08-21.
- RV_k = Σ (H1 bid close-to-close log return)² × 1e8 over week k (vol.weekly_rv).

## 2. Inputs at cut k (all known before cuts[k])
| id | definition | status |
|---|---|---|
| L1 | log RV_{k-1} | core |
| L4 | mean log RV_{k-4..k-1} | core |
| L26 | mean log RV_{k-26..k-1} | core |
| G | log((GVZ_thu / 100)² / 52 × 1e8): GVZ from the latest Cboe row dated on or before Thursday (cut − 1 day), missing if that row is older than 6 days. Publication time **not verified** from the stored file (Round 6 objection 2) | core |
| S1 | log(last H1 bid close before the cut ÷ max H1 bid high over the prior 52 weeks) | **shadow diagnostic only**: printed, never promotable from history (trace registry rule) |

Any required input missing (an invalid week inside the 26-week reach, GVZ
missing) → that model issues no forecast that week.

## 3. Models (each gives a predictive distribution of log RV_k)
Every model's distribution = its point μ_k plus the **empirical pool of its
own past out-of-sample residuals** e_j = log RV_j − μ_j (j < k, target valid),
used only when the pool holds ≥ 52 residuals. One distributional method for
all models (Round 6 objections 9, 10). Point variance for QLIKE = mean of
exp(μ_k + e_j) over the pool.

| model | μ_k | fit |
|---|---|---|
| B0 | log F_k, F = WPWB frozen EWMA λ = 0.75 (`vol.ewma_forecast`) | none |
| B1 | climatology: the ensemble is the 52 most recent valid log RV (no residual step) | none |
| HAR | a + b1 L1 + b4 L4 + b26 L26 | expanding OLS on past complete rows, ≥ 104 rows |
| MVOL | HAR + g G | same; rows need G |
| MVOL+S1 | MVOL + s S1 | diagnostic only |

OLS refit every week on rows j < k whose target is valid; if the design's
condition number exceeds 1e6 that week issues no forecast (count printed). No
shrinkage, no coefficient constraint, no tuning.

## 4. Targets and scores
Scored set: weeks where B0, B1, HAR and MVOL all issued a distribution and the
target week is valid. Periods: **D1** first common week..2018-12-28;
**PH** 2019-01-04..2021-06-25 (pseudo-holdout); **D2** 2021-07-02..2026-08-21.

- **Y2 (primary): CRPS of log RV_k** from the ensemble,
  CRPS = mean|X − y| − ½ mean|X − X′|. Lower is better.
- Y2 diagnostic: QLIKE of the point variance, RV/F − log(RV/F) − 1.
- **Y1a**: 4-class level, class(RV_k / m_k) with variance edges 0.75 / 1.5 /
  2.5, m_k = median RV of the 52 valid weeks before cut k, frozen at the cut.
  Class probabilities = ensemble mass per class. Score: ranked probability score.
- **Y1b onset**: risk set = weeks whose just-completed week k−1 is not
  HIGH/EXTREME (class(RV_{k−1}/m_{k−1})); event = week k HIGH/EXTREME
  (ratio ≥ 1.5). P = ensemble mass above log(1.5 m_k). Brier score; alarm =
  P above the causal 80th percentile of that model's own past onset
  predictions (≥ 50 past); precision, sensitivity, FPR printed.
- **Y1c exit**: risk set = week k−1 HIGH/EXTREME; event = week k not
  HIGH/EXTREME. P = ensemble mass below log(1.5 m_k). Same scores.
- **Y3 worse-side H1 quote-touch excursion** (not a stop-hit probability;
  Round 6 objections 5, 6): first H1 bar of week k; long entry = its Ask open,
  adverse = entry − min Bid low over the week; short entry = its Bid open,
  adverse = max Ask high − entry; both in bp of entry; Y3 = the larger.
  Events at **fixed** thresholds θ = 100, 200, 300 bp. P(Y3 > θ) = share of
  past valid weeks j (≥ 104) with Y3_j / √F̂_j > θ / √F̂_k, F̂ = the model's
  own point variance. Brier per θ. Only the worse side is ever shown.

Comparisons (paired, same weeks): **MVOL − B0**, HAR − B0, **MVOL − HAR**
(does GVZ add information beyond the price's own volatility — the question
Part 51 left open), B1 − B0. Uncertainty: circular moving-block bootstrap of
the weekly paired differences, block 8 (Codex outlook_power.py), 2000 reps;
block 26 as sensitivity. Printed per period and overall. **Not a gate.**

Reported also: PIT histogram (10 bins) and 80 % / 95 % interval coverage per
model, per period; coefficients of MVOL at the last cut; count of weeks with
no forecast per model and why.

## 5. Vendor audit (Round 6 objection 16), run first in the same script
On cuts 2021-07-02..2026-08-21 valid in both, compare Dukascopy H1 with the
Exness H1 the live report uses (`wpwb_weekly/bars.py`, `market()`): Spearman
of weekly RV, median |log(RV_Exness / RV_Dukascopy)|, Y1a class agreement
(each vendor with its own m_k). **Tolerance frozen now:** Spearman ≥ 0.95,
median |log ratio| ≤ 0.10, class agreement ≥ 85 %. Failing any of them does
not stop the development run, but means a model fitted on Dukascopy cannot be
carried to the live Exness feed without a mapping, which would be stated.

## 6. Self-tests before the real run
- Future-garbage invariance: replacing every H1 bar after a cut with garbage
  leaves every model's forecast at that cut unchanged (3 random cuts).
- Missing-GVZ invariance: deleting one week's GVZ rows removes only MVOL's
  forecasts that need that row.
- Synthetic null: replace G by an AR(1) series (ρ = 0.9) unrelated to gold;
  over 20 such series, count MVOL − HAR CRPS intervals (block 8, overall)
  entirely below 0. Expected about 2.5 % per series; printed, not a stop rule.

## 7. Prior, stated before the run
MVOL beats B0 on CRPS by a small margin mostly through HAR (volatility
persistence at several horizons); GVZ adds a little beyond HAR, most visible
on Y1c (exits) and least on Y1b (onsets); onset alarms stay mostly wrong; Y3
gains follow the RV forecast. The vendor audit passes on RV, with class
agreement the weakest of the three.

## 8. Next step (not authorised by this file)
Whatever the result, the next step is a separately registered forward shadow
log (one immutable forecast object per cut with input hashes, B0 and every
model side by side). No model replaces B0 on history.

## Amendment 1 (2026-09-29, after Codex round 10, before any score was computed)
All ten findings in `docs/CODEX_R10_OUTLOOK_V2.md` accepted:
1. **No operational route from history (R10-1).** The sentence in section 0
   about `min(scale_B0, scale_model)` is withdrawn. Historical results may not
   change `vol_scale` or `effective_scale` in any form. Any operational use
   needs its own later pre-registration, prospective evidence and the
   operator's explicit approval.
2. **Distributional parity (R10-2).** Every model's residual pool is exactly
   its most recent **104** out-of-sample residuals (not an expanding pool);
   scoring starts only when all core models have a full pool, so from then on
   the pools cover the same calendar weeks. B1 stays the 52-week climatology.
3. Printed MVOL coefficients are those actually used at the last scored cut
   (rows j < k only) (R10-3).
4. **Vendor audit (R10-4).** Only weeks where Dukascopy and Exness have the
   identical set of H1 open times are paired. Added: median |log range ratio|
   ≤ 0.10 and median |log bid-only Y3 ratio| ≤ 0.10 (Exness carries bid OHLC
   only, so Y3 is compared bid-only). Each vendor's m_k comes from its own
   full series; Exness class comparison therefore starts ~52 weeks after its
   data begin. **If the audit fails, no Dukascopy-fitted model may be carried
   to the Exness feed**; a forward shadow would then have to be fitted on Exness
   data alone.
5. **Bootstrap on calendar weeks (R10-5):** circular blocks of 8 (and 26)
   consecutive calendar weeks; statistic = sum of paired differences in the
   drawn weeks ÷ their count, so sparse risk sets keep their calendar spacing.
6. m_k, its first/last source cut and the RV input hash are written to the
   workbook (R10-6). This freezes it from now on; it cannot recreate the
   vintage of past data.
7. PIT is the randomised rank PIT, (#{e < y} + U·(#{e = y} + 1)) / (n + 1),
   per model and period; tail shares below p5 / above p95 and 80 %/95 %
   coverage are printed with calendar-block intervals (R10-7).
8. Alarm flags are computed once over each model's whole causal history and
   then summarised per period (R10-8).
9. Missing forecasts are counted per model with reason: target invalid,
   missing input, no point forecast otherwise, no distribution (R10-9).
10. **RPS convention (R10-10):** four ordered classes, RPS = (1/3) Σ_{j=1..3}
    (F_j − O_j)², F = cumulative forecast probability, O = cumulative outcome.
Also: Y3 entry is the first H1 bar whose **open** is after the cut.
