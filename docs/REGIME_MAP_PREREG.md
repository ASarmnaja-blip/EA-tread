# Regime atlas and regime-change traces — pre-registration v2 (2026-09-29)

> v2 replaces v1 (kept below for the record) after Codex Round 8 (15 objections,
> all accepted). Operator approved the plan on 2026-09-29 ("อนุมัติ"). Committed
> before any real-data run of `research/pilot/regime_atlas.py`. The output is a
> **historical trace atlas**, not permission to build or switch on any tool.

## v2.0 Clock, calendar, validity
- Cuts C_t every Friday 22:15 UTC from 2003-05-09; week W_t = (C_{t-1}, C_t],
  H1 bars assigned by close time; σ_t = √RV_t (bp). Dukascopy H1 bid only,
  2003-05..2026-09, single vendor; run only when the cache is complete, gap-free.
- The weekly calendar is never compressed. A week with < 80 H1 bars is invalid:
  it is not scored, a state at an invalid week is unknown, and any invalid week
  breaks runs, streaks, spells and multi-week returns.

## v2.1 Part 1 — descriptive map (full-sample; NOT available at any cut)
Every Part 1 output is stamped "full-sample, descriptive". Equal-frequency bands
of σ over the whole history (LOW/MID/HIGH — bands, not discovered natural
regimes), with the within-band distribution (5/25/50/75/95%) and a boundary-
sensitivity table (quartiles, quintiles). Trend band from the 13-week
cumulative log return. Volatility spells and 9-state spells are defined
separately: completed spells, median and 25/75% length, censored spells
reported, gaps break spells. Week-to-week transition matrix with 26-week
moving-block bootstrap 95% intervals; shares by era.

## v2.2 Causal state (used by Parts 2-3 only)
At C_t, q1_t, q2_t = terciles of σ over the 52 calendar weeks W_{t-52}..W_{t-1}
(≥ 40 valid), linear interpolation; σ ≥ q2 is HIGH, σ < q1 is LOW, else MID.
The **same** edges classify σ_t (state_t) and σ_{t+1} (state'_{t+1}). Trend
state at C_t: z13 = r13 / √(Σ RV of those 13 weeks), UP if z13 ≥ 0.5, DOWN if
≤ −0.5, else FLAT (13 consecutive valid weeks needed).

## v2.3 Targets (6), each for W_{t+1} from information at C_t
| id | risk set | event |
|---|---|---|
| V-change | state_t known | state'_{t+1} ≠ state_t |
| V-on | state_t ∈ {LOW, MID} | state'_{t+1} = HIGH |
| V-off | state_t = HIGH | state'_{t+1} ≠ HIGH |
| D-counterweek | 4 consecutive valid weeks and abs(r4) ≥ 0.5·√(Σ RV of those 4) | sign(r_{t+1}) ≠ sign(r4) |
| D-state-change | trend state known at t and after W_{t+1} | trend state changes |
| Next-sign (a forecast, not a change target) | r_{t+1} ≠ 0 | r_{t+1} > 0 |

Also reported: the full causal 3 × 3 next-state transition counts and a
multinomial baseline (past transition frequencies).

## v2.4 Traces (21) — see `docs/REGIME_TRACE_DICTIONARY.md`
Continuous (17): sig_ratio, sig4_26, ewma_ratio, range_exp, accel, gvz_lvl,
gvz_chg, gvz_prem, r4z, r13z, r26z, dist_ma50, dist_ma200, dist_hi52, dist_lo52,
streak, up_share8. Categorical (2): month, week_of_month. Binary (2): qend_flag,
**lag_short** (the just-completed week had < 100 bars). The v1 coming-week
short flag is dropped: no point-in-time holiday schedule is held.

## v2.5 Part 2 — prequential accuracy for ALL 21 × 6 = 126 pairs (no survivor gate)
- At each origin t a one-feature model is fitted on the pair's past risk-set
  weeks whose outcomes are known by C_t: continuous → 3 quantile bins, edges from
  the past; categorical/binary → its categories; each cell's rate shrunk toward
  the past base rate with a beta-binomial prior of strength 10. Orientation is
  implicit in the bin rates (no full-sample sign choice).
- Ready only when the pair's past has ≥ 30 events and ≥ 30 non-events.
- Two windows, both reported: expanding, and trailing 260 weeks.
- Baseline: the past base rate in the same window.
- Metrics, overall and by the causal state at issuance (V-on: LOW vs MID; V-off:
  HIGH only; others: LOW/MID/HIGH): Brier skill vs baseline, AUC of predictions,
  and a causal alarm (prediction strictly above the 80th percentile of the
  pair's ≥ 50 past predictions; ties do not alarm; prevalence reported) with
  confusion counts, precision, lift, sensitivity, false-positive rate
  FP/(FP+TN) and false-discovery share FP/(TP+FP). 95% intervals by 26-week
  moving-block bootstrap.
- Rolling picture: Brier skill in 5-year windows stepped yearly, per pair —
  birth, peak and decay are what history is for.
- **No p-value gate, no survivor.** Of 126 pairs ~6 intervals are expected to
  exclude 0 by chance at 95%. Self-check before results are read: 40 synthetic
  AR(1) traces (φ = 0.9, same missing pattern as sig_ratio) through the same
  pipeline must give 1-10% of Brier-skill intervals excluding 0.
- A count table (risk weeks, events, first ready week per pair) is printed first.
  Any cell with < 20 events or < 20 non-events is not printed.

## v2.6 Part 3 — no tool from history
Two routes, each needing its own later pre-registration: (a) change-alarm tool —
prospective timestamped shadow record, minimum current sample, calibration
metric, decay detector, automatic off rule; (b) observed-regime tool — built on
the causal current state even if change is not forecastable, with forward
confirmation. No setup, no size increase and no activation follows from this
atlas; an unconfirmed alarm may at most stay shadow or reduce risk under a
separately frozen conservative rule.

## v2 stated in advance
Volatility change targets: modest skill expected (clustering, GVZ). Direction
targets: none expected. Power (Codex): a null excludes only roughly AUC ≥ 0.65
for V-on/V-off and ≥ 0.57 for balanced direction targets.

---

# (superseded) v1 — kept for the record

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
**Traces (21, frozen):** σ_{t-1}/median52; σ4/σ26; spec-v2 EWMA ratio; range
expansion of last week; Thursday-Friday acceleration; GVZ level vs its 1-year
median; GVZ 1-week change; GVZ² ÷ realised variance (from 2009-09); 4-, 13-,
26-week return z-scores; distance to 50- and 200-day mean; distance to the 52-
week high; distance to the 52-week low; streak length of same-sign weeks;
share of up weeks in the last 8; month; week of month; quarter-end week flag;
short-week flag (trading days in the week).
**Stage 1 — detection (all weeks):** rank AUC of every trace against every
target (sign free, |AUC − 0.5|). p from the shift null: the trace series is
circularly shifted by ≥ 52 weeks, 5,000 times, and the same statistic recomputed;
p = (1 + #{|AUC_shift − 0.5| ≥ |AUC − 0.5|}) / 5,001. Tests: 21 × 4 = 84, α =
0.05 / 84 = 0.000595. Traces with p < α are **survivors**.
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

## Amendment 1 (2026-09-29, before any real-data run)
- The trace list has **21** entries (I miscounted 20): tests = 21 × 4 = **84**,
  α = 0.05 / 84 = **0.000595**. The code already used 84.
- Smoke run on the cached part (2003-05..2017-07, counts only): V-on 75 events of
  455 defined weeks, V-off 75 of 226, D-rev 337 of 681, D-up 389 of 681. With
  ~1,200 weeks expect ~120 events each for V-on / V-off, so Stage 1 can detect
  roughly AUC ≥ 0.60 and will miss weaker signals; a null is therefore limited
  to "no strong trace".
- Categorical traces (month, week of month) use a G statistic instead of AUC;
  each is tested against its own shift null.
