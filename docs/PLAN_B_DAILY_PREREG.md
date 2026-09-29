# Plan B — daily-scale, drift-controlled, 13 unmined years — pre-registration v1 (2026-09-29)

Fallback fixed in `docs/H1_LONG_HISTORY_PREREG.md` (decision tree, step 2),
written and committed **before the result of Plan A is known**. It is run only
if Plan A yields no CONFIRMED family and no LEAD. Codex audits afterwards.

## Why daily-scale
At 1-20 day horizons the round-trip cost (0.8 bp) is negligible against a 100-
500 bp move, so the question is pure information. It is also where published
evidence for gold-relevant momentum, volatility timing and calendar effects
lives — and it is the scale at which the project's 2016-2026 tests (weekly
TSM, VOLMAN) were already run, so **2016 onward is contaminated for this class
and is used only as a consistency check**. 2003-05 .. 2015-12 is not.

## Data (frozen)
- Dukascopy XAUUSD **H1** bid OHLC (same cache as Plan A, complete to 2015-12).
- Daily bars are **built from H1**, day = (bar start − 22 h).date, i.e. the
  22:00 UTC anchor the project already uses for VWAP. The vendor's own D1 file
  is NOT used: it contains partial Sunday bars. A day needs ≥ 12 H1 bars.
- Daily return = close-to-close; entry next day's open, exit close of day t+h.

## Instruments (frozen list, 10, all causal at the day's close)
ret1, ret5, ret20, ret60, ret120, ret250 — each trailing return divided by
(trailing 60-day daily SD × √L), so eras with different volatility compare;
dist_ma200 (close vs 200-day mean, same scaling); vol_ratio (20-day SD ÷
250-day SD); dow (weekday, 5 categories); month (12 categories).

## Test (30 primary = 10 instruments × h ∈ {1, 5, 20} days)
- **Outcome:** forward h-day return in bp, **demeaned by the training-fold
  mean** (removes gold's drift, so a long-biased rule cannot look like skill).
- **Cross-fitting over the unmined era 2003-2015:** leave-one-year-out (13
  folds): bins (deciles of the training years' feature; categories as they
  are) and bin means of the outcome fitted on the other 12 years, applied to
  the held-out year. Held-out predictions are pooled; Pearson ρ between
  predictor and outcome.
- **Significance:** block bootstrap, block = max(7, 2h) days, 10,000 resamples,
  add-one two-sided p; α = 0.05 / 30 = 0.00167.
- **LEAD:** p < α **and** ρ has the same sign in at least 10 of the 13 held-out
  years (binomial one-sided p ≈ 0.046) **and** the same sign when the 2003-
  2015 fit is applied to 2016-2026 (consistency only; that era is mined).
- Reported for every test: implied annual Sharpe ≈ 0.8·ρ·√(252/h), the smallest
  detectable ρ for 12.6 years (≈ 0.05 at h = 1, ≈ 0.11 at h = 5, ≈ 0.23 at
  h = 20 because overlapping windows shrink the effective sample), and a
  circular-shift null check of the whole pipeline.

## Expected outcome, stated in advance
Prior: 0 of 30. Power is honest and low at h = 20, so a null there is weak; the
most informative cells are h = 1 and h = 5.

## What follows
- LEAD → freeze a rule (new pre-registration), run on 2016-2026, log forward.
- Nothing → Plan C (panel of instruments), then the honest conclusion in the
  H1 document.

## Amendment 1 (2026-09-29) — made BEFORE any real Plan B result was read

The frozen self-check gate failed: with the block bootstrap the circular-shift
null rejected 22% of the time (allowed band 1%-10%). `plan_b_calibrate.py`
(null data only) shows the rate stays at 13-22% for block lengths from 10 to 180
days, so block length is not the cause. The cause is structural: leave-one-year-
out cross-fitting makes the pooled ρ negatively biased under the null (the
held-out year's mean opposes the training years' mean), and a two-sided test of
that biased ρ over-rejects. Replacement, everything else unchanged:

- **p-value from the empirical shift null of the whole pipeline:** shift the
  feature series circularly by K = 2,000 random offsets of at least 260 trading
  days, rerun the full leave-one-year-out cross-fit each time, and take
  p = (1 + #{|ρ_shift| ≥ |ρ_obs|}) / (1 + K). This inherits the bias, the
  overlap and the regime persistence of the real statistic.
- The block bootstrap is dropped. LEAD needs the shift-null p < α = 0.05/30,
  ≥ 10 of 13 held-out years with the pooled sign, and the same sign in 2016+.
- Self-check (gate, unchanged band 1%-10%): 40 pseudo-real draws (a shifted
  feature treated as the real one) each tested against 400 further shifts must
  reject at nominal 5% within the band, and a planted ρ ≈ 0.10 must be found.
