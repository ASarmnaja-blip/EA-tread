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
