# WPWB hole register — where the risk frame still leaks (2026-09-29)

Operator request (Thai): read every chart trace, close the hole that volatile
periods cause the largest losses, and find holes not yet closed. Measured on
data already held (operator: use the latest data available). Development /
descriptive on 2021-07..2026-09; nothing here is a trading edge.
Scripts: `research/wpwb_weekly/holes_study.py`, `news_tick_spread.py`.
Outputs: `data/wpwb_weekly/holes_study.xlsx`, `news_tick_spread.csv`.

| # | hole | measured | status | what closes it |
|---|---|---|---|---|
| H1 | **onset week of a volatile episode is not forecast** | 24 onsets / 152 at-risk weeks. Best of 12 pre-declared traces: GVZ level vs its 1-year median AUC 0.68 [0.58, 0.77], price near 52-week high 0.67 [0.56, 0.77], last-week RV 0.65 [0.55, 0.73]; current EWMA 0.60 [0.48, 0.71]. At a 20% alarm rate the best catch 8–9 of 24 with ~22 false alarms. Cross-asset (DXY, US500, silver) and news count do not discriminate | **partly open** — prediction can at best narrow it; best-of-12 on n=24 is optimistic | Test GVZ level, near-high and last-week RV in the Outlook on an **independent era** (Dukascopy H1 + GVZ 2009–2021) before any use; meanwhile close it structurally with H2–H4 |
| H2 | **volatility explodes mid-week** after Saturday's scale is set | only ~20% of a volatile week's variance is realised by Monday close; RV after Monday vs forecast flags a volatile week with AUC 0.74 [0.68, 0.81] | **CLOSED 2026-09-29** (spec v3 H2: halve at 1.5x pace from bar 20; fires 66 times, left tail -558 -> -372) | intraweek breaker (CLAUDE.md §4 already requires re-evaluation during the week): if RV since the Sunday reopen runs above a frozen multiple of the forecast pace, no new positions and new risk × 0.5 for the rest of the week; threshold must be frozen before testing (Outlook v1) |
| H3 | **weekend gap jumps the stop** | 272 weekends: median |gap| 11.5 bp, p95 92 bp, max 306 bp (2026-01-30, −306 bp ≈ −$150) | **CLOSED 2026-09-29** (spec v3 H3: no carry into a forecast HIGH/EXTREME week + p99 175 bp lot cap; long max DD 13.9% -> 4.6%) | measured: gap size really does scale with the forecast class |
| H4 | **news minute: spread and jump** | ticks around 98 USD HIGH releases (Jun–Sep 2026): spread $0.09 → up to $0.96 (11×); largest 1-minute move median 10.7 bp ($4.4), p90 55 bp, max 177 bp ($79, NFP 2026-09-04) | **CLOSED 2026-09-29** (spec v3 H4: no holding through tier-1 unless the stop exceeds the p95 1-min move, 158 bp; note n=14) | also do not hold through NFP/CPI/FOMC with a stop closer than the p95 1-minute jump, or flatten before; bar spreads (M5) hide these spikes — only ticks show them |
| H5 | **unscheduled shocks** (e.g. 2026-01-29 H1 −590 bp, no calendar event) | cannot be calendared | **open by nature** | only size, a stop on every order, H2 breaker and the account stop limit it |
| H6 | broker margin stop-out not modelled | Codex Round 5 | **still open** — MT5 blocked by a pending Windows update prompt; riskrules.py refuses to invent the numbers | model Exness contract, leverage and stop-out level in the backtest |
| H7 | stop hits estimated from H1 extremes, not ticks | ticks exist only ~4 months back | partly open | use ticks forward; H1 extremes understate the news-minute jump (H4) |
| H8 | dollar risk grows with price; vol_scale is in bp | Codex Round 5 | partly closed | lots from equity × vol_scale; add stop distance and $/lot into the lot rule |
| H9 | operations: calendar staleness, MT5 LiveUpdate UAC, missed week | seen 2026-09-28 | partly closed | report flags stale calendar; UAC needs the operator once; missed weeks are not back-filled |
| H10 | macro traces (CFTC crowding, yields) tested only for direction | Part 37 | open | add as magnitude traces in the Outlook (they failed for direction, not necessarily for volatility) |

## What this means for "winning volatile periods"

- Direction in volatile weeks is a coin flip (34 up / 34 down); what differs
  is size of move (1.7×) and of range (1.8×).
- The first week of an episode cannot be reliably seen coming; the best
  traces catch about a third of onsets at a tolerable alarm rate.
- So the realistic path is not to predict the onset but to (a) not be
  oversized when it arrives (account stop, base 0.03 lot/$10k × vol_scale),
  (b) react inside the week (H2 breaker), (c) not be caught by gaps and news
  minutes (H3, H4), and (d) scale stops and targets to the forecast range
  (Outlook Y2/Y3). Only after those are frozen and running forward is a
  volatile-period trading setup worth designing.
