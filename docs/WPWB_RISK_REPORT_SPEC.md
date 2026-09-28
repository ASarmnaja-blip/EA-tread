# WPWB weekly risk report — specification v2 (2026-09-28; v1 amended after Codex Round 5)

Operator approved items 4, 7, 9, 10, 11 on 2026-09-28 (Thai: "4/7/9/10/11 ส่วน
ข้อ2 รอลิมิต codex ก่อน · บันทึกหาช่วงที่ตลาดผันผวนไว้ด้วย ... ตอนนี้ช่วงตลาด
ผันผวนยังไม่ต้องเสี่ยงมาก"). Origin: debate rounds 3–4
(`docs/WPWB_DEBATE_2026-09-28.md`, P2-C). Code: `research/wpwb_weekly/`.
**v2 amendments (Codex Round 5, all accepted, before any forward week):**
(1) week completeness is judged by the clock — gold closes before the 22:15
cut, so v1 would have failed on every Saturday; (2) the out-of-calibration
fail-safe is now executed in code (effective scale 0.50) and both raw and
effective scales are logged; (3) H1 bars are assigned to weeks by their close
time; (4) a DATA_INVALID week (< 80 H1 bars) never re-enters EWMA/HAR/
calibration and forces scale 0.50; (5) forward QLIKE scoring joins each week
to the forecast logged exactly 7 days earlier; (6) "widen a stop" is only
allowed with lots cut to keep dollars at risk at or below the ceiling.
v1 dry-run log archived as `data/wpwb_weekly/log_v1_dryrun.csv`.

## What it is — and is not

- A **weekly risk report**, issued after each Friday 22:15 UTC cut (Saturday
  05:15 Thai time). It forecasts next week's XAUUSD volatility, lists next
  week's USD news with a fixed 8-scenario plan, classifies last week's news,
  and records everything append-only.
- **Not a trading signal.** The project's directional verdict remains
  **NO TRADE**. No code in `research/wpwb_weekly/` can send an order.
- It spends **no alpha** (`docs/ALPHA_LEDGER.md`): it claims no profit, only
  risk reduction, and is monitored by calibration, not by a superiority test.
  Reason (debate Round 4): against a free benchmark (last-week RV, EWMA) a
  superiority test has ~0–8% power in 52 weeks; against the 26-week mean it
  would confirm only the obvious.

## Frozen definitions (item 4)

| item | definition |
|---|---|
| Bars | canonical M5 + frozen fresh M5 (P1 snapshot) + weekly read-only MT5 fetch into `data/wpwb_weekly/fresh/` |
| Week | [cut, cut + 7 d), cut = Friday 22:15 UTC |
| RV | Σ (H1 close-to-close log return)² × 1e8 over the week's H1 bars (Codex Round 4 definition; verified identical) |
| Primary forecast | EWMA: F_t = 0.75 F_{t−1} + 0.25 RV_{t−1} |
| Logged only | HAR (Codex Round 4 spec, expanding OLS, v/2 correction); mean of last 26 RVs |
| Reference risk unit | B_REF = 38,193.9 bp² (weekly vol 195.4 bp) = median weekly RV of the 273 weeks 2021-07-02..2026-09-25; a constant, never re-estimated |
| **vol_scale** | clip(√(B_REF / F_t), 0.50, **1.00**) |
| Level label | EWMA forecast ÷ median RV of the past 52 weeks (variance ratio): < 0.75 สงบ · < 1.5 ปกติ · < 2.5 ผันผวนสูง · ≥ 2.5 ผันผวนรุนแรง (volatility ratio 0.87× / 1.22× / 1.58×) |
| Data validity | a week with < 80 H1 bars is DATA_INVALID; the report refuses to run |

`0.75` was used by Codex as a diagnostic benchmark in Round 4; it was not
tuned by Claude (no other lambda was tried). B_REF was computed once.

## Permitted use (items 4 and 7)

- vol_scale may only **reduce** lots relative to the frozen default risk unit;
  a wider stop is allowed only if lots are cut so dollars at risk stay at or
  below the frozen ceiling (a wider stop at unchanged lots adds risk). It can never exceed 1.00 — this is the
  useful half of VOLMAN (item 7); VOLMAN's scaling *up* in calm weeks and its
  long-only direction are **not** adopted (VOLMAN failed 2016–20: −588 bp vs exposure-matched long, Part 34).
- It never chooses direction, setup, entry, champion, and never authorises an
  order. It must not be changed while a position is open (CLAUDE.md §7).
- Operator instruction 2026-09-28: in volatile periods take little risk now.
  2026's normal level is ~1.6–1.7 × B_REF, so vol_scale is ~0.6 even in
  "ปกติ" weeks; in a forecast ผันผวนสูง/รุนแรง week it is at or near 0.50.

## Calibration monitoring (replaces an alpha test)

Weekly u_t = RV_t / F_t. "In calibration" while, over the trailing 26 valid
weeks (development weeks count; this is a safety alarm, not a test of skill),
|median log u| <= log 1.5 and the share of weeks with u > 4 is < 10%. Out of
calibration, undecidable, or last week DATA_INVALID → effective scale 0.50
(implemented in `vol.effective_scale`, logged as `vol_scale`; the raw value
is logged as `vol_scale_raw`). Passing this alarm does not validate the
forecast (Codex Round 5). HAR and the 26-week mean are scored
alongside by QLIKE, descriptively.

## News section (item 9)

Uses the existing CLAUDE.md §2 layer (`research/pilot/news.py`,
`newsdesk.py`, `calendar_feed.py`) unchanged:
- next week: USD HIGH releases, consensus, previous, and the hypothesis a
  surprise would set (declared sign table; two-sided series get none);
- a fixed 8-scenario playbook (in `news_plan.PLAYBOOK`). Because no news
  setup has a confirmed edge (Part 25), every scenario is RECORD or STAND
  ASIDE; before a release no new position is opened;
- last week: each release classified from M1 XAU and DXY reactions at
  1/5/15/60 min; the 60-min figure is circular (used to classify) and is
  recorded, not used as evidence;
- CFTC positioning from the calendar; yields, narrative and priced-in remain
  NOT ASSESSED.
Calendar freshness: `data/calendar.csv` comes from the MT5 script
CalendarDump. The report states when next week is not covered or last week's
actuals are missing; it never guesses them.

## Volatility episode log (operator request)

`research/wpwb_weekly/episodes.py` → `data/wpwb_weekly/volatility_log.xlsx`
(Thai): every week since 2022-07 with realised level (vs the past 52 weeks,
causal), the forecast made before it, gold's move, range, key news and the
three largest H1 bars with any USD HIGH release within ±1 h; volatile weeks
merged into episodes. Rerun weekly so forward weeks join the catalogue.
Descriptive only — it is the study material for the operator's goal of
trading volatile periods later, not a rule. Summary:
`docs/WPWB_VOLATILITY_LOG.md`.

## Forward logging (item 10)

- `python research/wpwb_weekly/weekly_report.py --fetch` after each cut.
  Writes `data/wpwb_weekly/reports/<cut>.md` and appends to
  `data/wpwb_weekly/log.csv` (append-only; a differing rewrite raises).
- Cuts before 2026-10-02 22:15 UTC are DRY RUN; from that cut on, rows are
  flagged forward = True.
- MT5 access is read-only (`copy_rates_range`); the report prints server and
  trade_mode.

## Tests

`research/wpwb_weekly/test_weekly.py`: vol_scale ∈ [0.5, 1.0] for all
inputs; EWMA and HAR use past weeks only; garbage bars after the cut leave
every reported value unchanged; the log refuses rewrites. RV and HAR match
Codex's Round-4 functions exactly (max relative difference 0.0).

## Automation (operator approved 2026-09-28: "คุณทำให้เลย")

- Windows Task Scheduler, current user, no admin: **"EA-tread WPWB weekly
  report"**, every Saturday 06:00 Asia/Bangkok (after the Friday 22:15 UTC
  cut), runs `pythonw research/wpwb_weekly/run_weekly.py`; start-when-available
  if the PC was off; 2 h limit. First run 2026-10-03 06:00 (first forward cut).
- `run_weekly.py`: closes MT5 gracefully → runs the CalendarDump config →
  validates (rows >= 90% of old, later end) and backs up `data/calendar.csv`
  into `data/calendar_backups/` → restarts MT5 → `weekly_report.py --fetch` →
  `episodes.py`. Log: `data/wpwb_weekly/run_logs/`.
- Known blocker: an MT5 LiveUpdate asks for a UAC prompt; Claude never
  answers security prompts. While an update is pending the dump may not run;
  the report then states that the calendar is stale.
- Report markdown files may be regenerated for the same cut (e.g. after a
  calendar refresh); the numeric record is the append-only `log.csv`.

## Backtest (risk effect only) — `research/wpwb_weekly/backtest_risk.py`

Hold gold the whole week, LONG and SHORT, Demo90 costs incl. swap, $10,000,
0.10 lot fixed vs 0.10 × vol_scale rounded down to 0.01 lot (0.01 lot cannot
be scaled). 221 weeks 2022-07..2026-09, 68 volatile.

| exposure | total $ | max DD $ | worst week $ | weekly SD $ | profit ÷ maxDD |
|---|---|---|---|---|---|
| long, fixed | +19,437 | −11,984 | −5,223 | 839 | 1.62 |
| long, × vol_scale | +18,372 | **−5,992** | **−2,611** | 559 | **3.07** |
| short, fixed | −25,825 | −36,406 | −3,160 | 839 | — |
| short, × vol_scale | −23,695 | −29,749 | −1,896 | 559 | — |

Reading: vol_scale halved long's max drawdown and worst week for 5% less
profit, and cut losses in volatile weeks by about a third on both sides. It
**cannot rescue a wrong direction** (short still loses, and a 0.10-lot short
on $10,000 would have wiped the account). LONG's profit is gold's trend, not
a system edge. In-sample caveat: B_REF was computed on this history.

### Compounding backtest, DD sizing, side kill-switch — `backtest_compound.py`

Lots = base per $10,000 × equity/10,000 × vol_scale, floor to 0.01; stop-out
if equity at the week's worst H1 price <= 0. 2,000 random-direction paths
(seed 20260928) stand in for "direction unknown in advance".

- Current 0.10 lot/$10k (≈1.7× notional at $1,700 gold, 4.3× at $4,300):
  long × vol_scale max DD −50%; long fixed −78%; short −89 to −93%;
  random direction median −68%. Far above a 30–45% tolerance.
- For max DD 30–40%, never above 45% (random direction, × vol_scale):
  0.03 lot/$10k → median −22%, worst 5% −40%, P(DD > 45%) 0.9%;
  0.04 → median −31%, worst 5% −50%, P 11%; 0.05 → −39% / −60% / 31%.
  A persistently wrong side (the real short path) still reaches −51% at 0.03,
  so only a hard stop can guarantee a ceiling.
- Kill-switch (stop a side at X% DD from its peak), applied to both sides
  because a rule cannot know which side is wrong: at 20% it stops the short
  in 2023-01 but also stops the long in 2023-09, before gold's rise; at 30%
  it stops the short in 2023-04 and the long in 2026-03. It caps loss; it
  does not identify the wrong side. In-sample, one history.

### Codex Round 5 caveats on the backtests (accepted)

- The fixed-lot table is an exposure illustration, not an account backtest
  (the fixed short keeps trading below $0), and scaled vs fixed differ in
  average exposure; an exposure-matched control is needed to credit timing.
- B_REF uses the whole sample; the pre-2022 median (32,012.6 bp²) would have
  been more conservative. A return-variance reference is not a full dollar-risk
  budget: dollars per bp rise with price; a portable lot rule needs price,
  stop distance, contract size, equity and broker margin.
- The 0.03-lot result is **not a 45% guarantee**: 0.9–1.0% of i.i.d. paths
  breach 45%; persistent direction (90% repeat) 3.3%; a 25/75 side bias
  14.6%; continuous (unrounded) lots 8.2%. Lot rounding to 0.01 lowers mean
  exposure to ~82% of intended and acts as a hidden stop below ~$3.3–6.7k.
  Stop-out was modelled only at equity <= 0, not the broker's margin level;
  the kill-switch acts on weekly closes and overshoots (36.4% at a 30% switch).
- Therefore no lot size is called "safe" until order-level SL/gap rules, real
  margin stop-out, intraweek equity and forward execution data exist.

## v2.1 (report text only, 2026-09-29) — operator-adopted sizing

The operator adopted the risk frame as the one to use. Each report now states:
recommended lots = floor(0.03 × equity/10,000 × effective vol_scale, 0.01);
below 0.01 lot = no trade; account hard stop at 30% drawdown from peak, then
review before restarting; and that this is **not** a guarantee against a 45%
drawdown (~1% of i.i.d. random-direction paths breach it, 3–15% with
persistent or one-sided errors; broker margin stop-out not yet modelled).
The forecast and log specification stays v2 (log rows unchanged).
