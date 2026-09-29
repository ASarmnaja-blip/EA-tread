# Regime map and regime-change traces — pre-registration v1 (2026-09-29)

Operator instruction (Thai, 2026-09-29): use all the data going back; see what
market conditions exist, low / medium / high, clearly separated; then look for
the traces of WPWB that say, for each next week, whether the market will change
(regime or direction) and how accurate those traces are; find the traces first,
then build tools suited to each regime. This is the current-regime mission of
CLAUDE.md §1: history describes regimes and how long effects live; it is not a
persistence gate (Part 50). Committed BEFORE any real-data run; Codex reviews
the design before the run.

## Data
Dukascopy XAUUSD H1 bid, 2003-05 .. 2026-09, single vendor, run only after the
cache is complete and gap-free. GVZ (Cboe) from 2009-09. Weeks are the spec-v2
weeks between Friday 22:15 UTC cuts, H1 bars assigned by close time, ≥ 80 bars
else the week is invalid. ≈ 1,200 weeks.

## Part 1 — the regime map (description)
- **Volatility level** (weekly σ = √RV, bp): LOW / MID / HIGH = terciles of σ
  over the full history (cut-offs printed). Also shown: the causal 4-class label
  of spec v2 (CALM / NORMAL / HIGH / EXTREME vs the past 52 weeks).
- **Trend state:** 13-week return in terciles: DOWN / FLAT / UP.
- 3 × 3 = 9 regimes. For each: number and share of weeks, mean σ, mean |weekly
  return|, mean high-low range, share of weeks whose return flips sign vs the
  previous week, mean run length (weeks the vol level lasts), and the week-to-
  week transition matrix of the vol level; by era (2003-2008, 2009-2014,
  2015-2020, 2021-2026) to show how the map moves. Timeline chart.

## Part 2 — traces of change (all known at the Friday cut)
**Targets (binary, for the coming week; class edges causal = terciles of the
previous 52 weeks' σ):**
- **V-on:** the week is HIGH given this week is not HIGH (volatility onset).
- **V-off:** the week is not HIGH given this week is HIGH (volatility offset).
- **D-rev:** the week's return has the opposite sign of the last 4 weeks' return
  (direction reversal).
- **D-up:** the week's return is positive (direction; base rate reported).
**Traces (20, frozen):** σ_{t-1}/median52; σ4/σ26; spec-v2 EWMA ratio; range
expansion of last week; Thursday-Friday acceleration; GVZ level vs its 1-year
median; GVZ 1-week change; GVZ² ÷ realised variance (from 2009-09); 4-, 13-,
26-week return z-scores; distance to 50- and 200-day mean; distance to the 52-
week high; distance to the 52-week low; streak length of same-sign weeks;
share of up weeks in the last 8; month; week of month; quarter-end week flag;
short-week flag (trading days in the week).
**Stage 1 — detection (all weeks):** rank AUC of every trace against every
target (sign free, |AUC − 0.5|). p from the shift null: the trace series is
circularly shifted by ≥ 52 weeks, 5,000 times, and the same statistic recomputed;
p = (1 + #{|AUC_shift − 0.5| ≥ |AUC − 0.5|}) / 5,001. Tests: 20 × 4 = 80, α =
0.05 / 80 = 0.000625. Traces with p < α are **survivors**.
**Stage 2 — accuracy over time (survivors only):** walk-forward from week 260:
at each week the trace's bin-frequency model (5 bins, edges and frequencies from
past weeks only) issues a probability; report AUC, hit rate at the top-20%
alarm (precision and false-alarm rate against the base rate), and the same by
era, so decay and regime dependence are visible. No era-consistency gate.
**Stage 3 — by regime (survivors only, descriptive):** the same accuracy inside
LOW, MID and HIGH weeks.

## Part 3 — tools suited to regimes (only if Part 2 leaves survivors)
Named and specified only after Part 2, each with its own pre-registration; a
trace that does not survive Part 2 gets no tool. If none survives, the honest
statement is that the next week's regime change is not forecastable from these
traces, and the tools are the ones the risk report already has.

## Stated in advance
Prior: V-on and V-off show weak-to-moderate survivors (volatility clusters, GVZ
carries information); D-rev and D-up show none. If direction has none, the
map still gives the regime-specific risk tools; it does not give a direction
edge.
