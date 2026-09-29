# External traces of weekly regime change — pre-registration v1 (2026-09-29)

Operator instruction (Thai, 2026-09-29): now that WPWB describes the market's
condition, dig into every trace found — related and unrelated — focusing on what
makes the market change in the following week in that period; find traces
inside and outside, and report to move to the next step.

This extends `docs/REGIME_MAP_PREREG.md` v2 (the internal, price-only atlas)
with **external traces**. Same targets, same causal clock, same prequential
machinery, no survivor gate, no tool licence from history. Committed before the
external traces are computed. Codex reviews before the run.

## What "outside" is available, and the honest limit
| source | on disk | covers | weekly traces it can support |
|---|---|---|---|
| Cboe GVZ (gold implied vol) | `data/external/GVZ_History.csv` | 2009-09 → | already 3 of the internal 21 |
| US Treasury nominal yield curve | `treasury_nominal_20xx.xml` | **2016** → | 2y, 10y level/change, 2s10s slope |
| US Treasury real yield curve (TIPS) | `treasury_real_20xx.xml` | **2021** → | 10y real level/change |
| CFTC disaggregated COT (gold) | `cftc_fut_disagg_20xx.zip` | **2021** → | managed-money net, its percentile, its 4-week change |
| MT5 economic calendar | `data/calendar.csv` | **2022** → | count of tier-1 US releases scheduled in the coming week |
| Cross-asset M5 (DXY, US500, XAG, USDJPY, EURUSD) | `data/fresh/*_M5.npz` | **2023-09** → | each asset's weekly realised vol ratio and weekly return z |

**The binding constraint is history length, not ideas.** The internal atlas has
~1,200 weeks; these external traces have 520 (yields), 250 (real yields, CFTC),
190 (calendar) and 160 (cross-asset). Against ~120 volatility-onset events in
the full history, a trace starting in 2021 sees roughly 25. Per the power table
in REGIME_MAP v2, a null on such a trace excludes almost nothing. **Every
external result is therefore explicitly exploratory**, reported with its
sample, never as evidence of absence.

## Traces (14 external, frozen)
Causal rule for all: the value used at cut C_t is the latest observation
**dated on or before the Thursday preceding C_t** (Treasury and GVZ publish
end-of-day; CFTC is Tuesday's book released Friday, so only a report released
**strictly before** C_t is used and its own release timestamp is required).

| id | definition | from |
|---|---|---|
| y2_lvl, y10_lvl | 2y and 10y nominal yield, in percentage points | 2016 |
| y2_chg, y10_chg | 1-week change of the above | 2016 |
| slope_2s10s | 10y − 2y | 2016 |
| slope_chg | 1-week change of the slope | 2016 |
| y10r_lvl, y10r_chg | 10y real yield level and 1-week change | 2021 |
| mm_net | managed-money net (long − short), in thousands of contracts | 2021 |
| mm_pct | its percentile within the trailing 52 reports | 2021 |
| mm_chg4 | 4-report change of mm_net | 2021 |
| news_tier1 | number of distinct tier-1 US releases (FOMC, NFP, CPI, core PCE) scheduled in (C_t, C_t + 7 d] | 2022 |
| xasset_vol | median across DXY, US500, XAG of (last week's realised vol ÷ its own past-52 median) | 2023-09 |
| xasset_ret | median across the same of last week's return z-score | 2023-09 |

## Method (identical to REGIME_MAP v2 §2.5)
Six targets (V-change, V-on, V-off, D-counterweek, D-state-change, Next-sign);
one-feature shrunk bin model fitted on past risk-set weeks only; expanding and
trailing-260 windows; Brier skill vs the past base rate; AUC; causal top-20%
alarm with confusion counts, precision, lift, sensitivity, FPR, FDR; 26-week
moving-block 95% intervals; rolling 5-year skill; results suppressed when a
cell has < 20 events or < 20 non-events. **No p-value gate.** 14 × 6 = 84
external pair-results join the 126 internal ones; of 210 pairs about 10
positive-skill intervals are expected by chance at 95%, and the report states
that alongside any finding.

## Report (the "next step" deliverable)
One table per target, internal and external traces together, sorted by Brier
skill, with sample, interval, alarm metrics and the 5-year rolling row so
birth/peak/decay is visible; plus the causal 3 × 3 transition matrix and the
count table. Then, and only then, a written proposal of which regime-specific
tool is worth a separate pre-registration — with prospective confirmation, per
REGIME_MAP v2 §2.6.

## Stated in advance
Prior: GVZ and cross-asset volatility carry some information about volatility
change; yields, positioning and the news count carry little about the *change*
(as opposed to the level); nothing carries direction. Expected outcome: a
handful of positive-skill intervals on short samples that cannot be separated
from chance, and the honest next step is the prospective log.

## Amendment 1 (2026-09-29, measured before any result)
Coverage on the 1,220-week cut grid, and the smallest effect each sample can
detect for V-on (80% power, two-sided 5%, onset rate 15.5% of the risk set as
measured in the smoke run):

| trace group | weeks | onsets it sees | smallest AUC detectable |
|---|---|---|---|
| internal H1 price (21 traces) | 1,220 | ~125 | **0.58** |
| Treasury nominal yields (6) | 559 | ~57 | 0.62 |
| Treasury real yields, CFTC (5) | 298 | ~30 | 0.66 |
| scheduled tier-1 news count (1) | 247 | ~25 | 0.68 |
| cross-asset vol/return (2) | 129 | ~13 | **0.74** |

Consequences fixed now:
- The cross-asset traces start 2024-04 on this grid (the M5 files begin
  2023-09 but a 52-week volatility baseline is required first). With ~13 onsets
  they can only see an enormous effect; they are reported as **exploratory,
  not tested**, and their cells are printed only if ≥ 20 events exist, which
  they will not reach for V-on. This is stated now so it is not read later as
  a finding.
- CFTC uses only reports **released** before the cut (Tuesday book, Friday
  20:30 UTC release), so the first usable week is 2021-01-08 and mm_pct needs
  26 prior reports (2021-07-02).
- A loader defect found and fixed before any result: the CFTC column
  `Report_Date_as_YYYY-MM-DD` contains dashes, so `itertuples` renamed it and
  the first version silently produced zero rows. Fixed by indexing by label;
  299 weekly gold reports 2021-01-05..2026-09-22 now load.


## Amendment 2 (2026-09-29, after Codex round 9, before any real result)
Codex R9 (`docs/CODEX_R9_EXTERNAL_TRACES.md`) found three blocking defects and
several smaller ones. All are corrected below, in code or in text, before the
real run. No accuracy figure for any external trace had been computed.

Code corrected (`research/pilot/external_traces.py`, `regime_atlas.py`):
1. **Cross-asset post-cut data (R9-1).** Hourly bars were labelled by bucket
   start, so the 22:00 value could hold M5 bars up to 22:55. Now the bucket
   [T-1h, T) is labelled T and only bars closed by the cut are used; a value
   older than 6 h at the cut is treated as missing.
2. **CFTC release times were invented (R9-2).** Each Tuesday report is now
   matched to its own release timestamp from the MT5 calendar row
   "CFTC Gold Non-Commercial Net Positions" (published together with the
   disaggregated report). Holiday and disruption delays are honoured (checked:
   lags of 3.8 d normally, up to 17.9 d in Feb 2023). Reports before the
   calendar begins (2022-01-03) are **dropped, not guessed**, so CFTC traces now
   start 2022-01-07, not 2021-01-08 as Amendment 1 stated.
3. **External study now runs end to end (R9-3).** `regime_atlas.py` builds the 14
   external traces and scores them with the 21 internal ones (35 traces x 6
   targets = 210 pairs).
4. `news_tier1`: counts distinct (timestamp, event) pairs; no zero-fill before
   the calendar's first row (R9-12). `news_tier1` is treated as categorical
   (exact count) because it takes few integer values.
5. `mm_pct`: window = up to 52 reports including the current one, at least 26
   observations, ties count half (R9-10). Amendment 1's "26 prior reports" is
   replaced by "26 observations including the current report".
6. Moving-block bootstrap start range off by one, in both the accuracy
   intervals and the transition intervals (R9-13); fixed.

Text corrected:
- **Vintage limits (R9-4, R9-8), stated not solved.** `news_tier1` uses the
  calendar as it stands today, not the schedule as known at each cut;
  reschedules and late additions are known retrospectively. The four releases
  are mostly scheduled long ahead, so the effect is probably small, but it is
  unmeasured. Treasury yields are read from present-day files with no vintage
  metadata; later corrections cannot be excluded. Both are a limitation on any
  finding, not a demonstrated leak.
- **Cross-asset definitions (R9-9).** `xasset_ret` is last week's return divided
  by the square root of the past-52-week median weekly realised variance (a
  volatility-scaled return; no mean removed, no z-score). Requirement: at least
  30 usable past weeks per asset and **at least 2 of the 3** assets (DXY,
  US500, XAG), not all three. Amendment 1's wording is superseded.
- **Power (R9-5). Amendment 1's "smallest AUC detectable" column is withdrawn
  as a statement about the implemented procedure.** It counted every covered
  onset with an ordinary AUC approximation, but predictions only begin after 30
  prior events and 30 prior non-events, and the decision quantity is a
  bootstrapped Brier-skill interval. Real consequence: news and cross-asset
  V-on will have too few scored events to print; real-yield and CFTC V-on
  almost none. The run prints a **NOT ASSESSED** list; a blank there means "no
  test happened", never "no effect".
- **Multiplicity (R9-6).** 210 pairs x 2 windows = **420 pair-window
  intervals**. If the intervals behave as one-sided 2.5% each, about 10 lower
  bounds above 0 are expected by chance. Strata, rolling windows and the
  top-5 lists add further looks. The self-check now also runs the trailing
  window and the nominal-yield missingness pattern (expanding + trailing).
- **Reporting (R9-11).** Bootstrap intervals exist only for Brier skill and
  lift; AUC, precision, sensitivity, FPR and FDR are descriptive. "First scored
  week" is now the first week with a prediction after the 30/30 burn-in. The
  workbook holds one complete sorted table per target; the console shows the
  positive-interval rows and the top 5 per target. FDR is printed.
- **Gaps (R9-14).** The run asserts no gap longer than 8 days; shorter outages
  are handled by the weekly rule (a week with fewer than 80 H1 bars is invalid
  and excluded), not by demanding a gap-free cache.
- **No licence (R9-7).** See `REGIME_MAP_PREREG.md` Amendment 2: the phrase
  allowing an unconfirmed alarm to "reduce risk" is withdrawn.
