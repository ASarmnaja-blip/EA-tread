# WPWB Outlook shadow log — pre-registration v1 (2026-09-29)

Operator approval (Thai, 2026-09-29): option 1 of the Part 52 report — log the
Outlook forecasts every Friday without using them — and "อนุญาตโหลด GVZ ทุกสัปดาห์"
(permission to download the Cboe GVZ history file every week).

## What it is
A **prospective, append-only record** of next-week volatility forecasts made
before each week starts, so they can later be scored on weeks nobody has seen.
**It changes nothing:** position size stays on the frozen WPWB EWMA
(`vol_scale`, `effective_scale`, riskrules.py untouched); no order is placed;
no direction is forecast. Any operational use needs a separate
pre-registration, prospective evidence and the operator's explicit approval
(`WPWB_OUTLOOK_V2_PREREG.md` Amendment 1 item 1).

## Frozen model (version OUTLOOK-V2.0, identical to the development run)
B0 (EWMA 0.75), HAR (L1, L4, L26), MVOL (HAR + G), expanding OLS on past rows
(≥ 104), predictive distribution = point + the model's last 104 out-of-sample
residuals; classes by RV / m_k with edges 0.75 / 1.5 / 2.5 (variance ratio).
Code: `research/wpwb_weekly/outlook_shadow.py`, reusing `outlook_dev.py`.

## Inputs at each cut C (Friday 22:15 UTC)
- **Weekly RV series:** Dukascopy H1 for weeks starting on or before
  2026-08-21 (fixed, the development series); from the week starting
  2026-08-28 on, the live Exness H1 feed (vendor audit passed, median log RV
  ratio −0.001, Part 52). Same weekly rules (close-time, ≥ 80 bars).
- **GVZ:** downloaded once per run from
  `https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv`.
  Every download is saved unchanged as `data/wpwb_weekly/gvz/GVZ_<UTC time>.csv`
  with its retrieval time, byte count and SHA-256 in the log row. The value
  used is the latest row dated on or before Thursday (C − 1 day); if that row
  is more than 6 days old, or the download fails, MVOL is **not issued** that
  week (B0 and HAR still are). The development file
  `data/external/GVZ_History.csv` is never overwritten. The row for the same
  Thursday in every earlier snapshot is compared, and any revision is logged.

## Log (`data/wpwb_weekly/outlook_shadow_log.csv`)
One row per cut, never rewritten (a second run for the same cut is refused).
Fields: cut, generated UTC, model version, status, RV input hash, m_k, the
current week's class, GVZ date/value/file hash/retrieval time, and for B0,
HAR and MVOL: point variance, RV quantiles 10/50/90 %, the four class
probabilities, P(next week HIGH or EXTREME). Cuts before 2026-10-02 22:15 UTC
go to `outlook_shadow_dryrun.csv` and are never scored.

## Scoring (after each week ends; `outlook_shadow_scores.csv`, recomputable)
Same scores as the development run: CRPS of log RV (primary), QLIKE, RPS,
onset / exit Brier, 80 % / 95 % coverage. Paired MVOL − B0 and MVOL − HAR,
reported as a running tally with calendar-block intervals once ≥ 26 weeks
exist. **No stopping rule, no gate, no alpha spent**: power in Part 52 says
about 256 weeks (≈ 5 years) are needed to confirm MVOL vs B0 and about 414
weeks for GVZ beyond HAR, so interim tallies are descriptive only.

## Operation
Runs inside the existing Saturday 06:00 (Bangkok) job `run_weekly.py`, after
the risk report. A failure here is logged and never alters or blocks the
risk report. A short Thai summary is written to
`data/wpwb_weekly/outlook_shadow_latest.md` labelled "shadow — not used for
sizing".

## Amendment 1 (2026-09-29, after Codex round 11, before the first forward cut)
All ten findings in `docs/CODEX_R11_OUTLOOK_SHADOW.md` accepted; the logger was rewritten.
1. **Durable inputs (R11-1, R11-9).** Dukascopy weekly RV for week starts ≤ 2026-08-21 is frozen
   once in `data/wpwb_weekly/outlook_rv_dukascopy_frozen.csv` (1,216 weeks, SHA-256
   `9c1722e6…f471a`); the development GVZ file is pinned (SHA-256 `670e620d…bca13`). A changed
   hash refuses the run. Each Exness week is written once to the append-only
   `outlook_rv_archive.csv` when it is complete by the wall clock and by the feed; the model
   reads only these two files, so the 60-day rolling fetch can no longer erase history. A week
   the PC never archived (off > 60 days) stays missing, and HAR/MVOL then pause for 26 weeks.
2. **Full scoring (R11-2):** CRPS, QLIKE, RPS, onset/exit Brier, 80 %/95 % coverage, on weeks
   where all three models issued (status OK, run FORWARD), with calendar-block intervals.
3. **Authenticated ensembles (R11-3):** draws saved atomically (temp file + rename) before the
   row; the row stores the file name and SHA-256; scoring refuses a missing or changed file. A
   lock file prevents two runs at once; an orphan file from a crash is kept, not overwritten.
4. **Fixed schema (R11-4):** one frozen column list; an append with a different header is refused.
5. **Lateness (R11-5):** a forward row counts as prospective only if generated before Sunday
   22:00 UTC (cut + 47 h 45 m), i.e. before any bar of the target week; later runs are logged
   as `LATE` and never scored. Skipped cuts are logged as `MISSED`; nothing is backfilled.
   The normal Saturday 06:00 Bangkok run is about 45 minutes after the cut, with the market closed.
6. **GVZ revisions (R11-6):** the used Thursday value is compared with every earlier snapshot
   and the previous value and a revised flag are logged. Past G inputs are never rebuilt:
   cuts ≤ 2026-08-21 use the pinned development file, later cuts the value archived in
   `outlook_g_archive.csv` when first computed.
7. **Completeness (R11-7):** a week is archived only after its end by the wall clock and with
   the feed reaching end − 6 h; the development 80-bar rule is kept for parity, and the largest
   internal gap is logged. Scoring uses only archived weeks.
8. **Calendar parity (R11-8):** the residual pool is the last 104 weeks in which all three
   models issued and the target was valid. On the development sample this equals per-model
   pools (no missing week after the first common week, Part 52).
9. **Bad downloads (R11-10):** the file is validated (columns, ≥ 4,000 rows, 5 ≤ GVZ ≤ 200,
   last row within 10 days of the cut); otherwise MVOL is not issued. Any exception still writes
   a row with status ERROR. The Thai summary is regenerated from the log on every run and now
   says "ห้ามใช้ตัดสินขนาดไม้หรือทิศทาง" (must not be used for size or direction).
Dry run 2026-09-25 (after the fix): status OK, pool 2024-09-27..2026-09-18, Thursday GVZ 22.58
unrevised, rerun refused. A second GVZ download was made for this test (two in total today).
