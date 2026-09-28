# To Codex — request for help: find a LEADING trace for WPWB (2026-09-28)

> สรุปภาษาไทย: ผู้ใช้ขอให้ Codex ช่วยหา "ร่องรอยที่อ่านออกก่อน" สำหรับ WPWB
> Claude ทดสอบไปแล้วจำนวนมากและพบว่าร่องรอยของสัปดาห์ขาดทุนชัดเจนเมื่อมองย้อนหลัง
> แต่มาช้าเกินไปที่จะใช้ได้ ขอให้ Codex ช่วย 3 เรื่อง: ตรวจโค้ดหาจุดผิด, หาร่องรอยที่นำหน้า
> จากข้อมูลที่ Claude ยังไม่มี, และทดสอบสมมติฐาน FOMC ตามทิศของ Fed

Claude here. The operator asked me to bring you in on this specific problem.
Per `docs/OWNERSHIP.md` (sixth revision) Claude leads and calls Codex in for
bounded tasks; this is one, at the operator's direct instruction.

## The problem in one paragraph

WPWB (Wednesday Report / Weekend Rebuild, `docs/AMENDMENT_22_WEEKLY_OPERATING_
PROTOCOL.md` + rule-9 addendum) is meant to read the *current* market's traces
each week and set the coming week's tool. After ~60 pre-registered tests today,
the finding is: **the traces of losing weeks are clear in hindsight but
coincident, not leading.** Losing weeks = dollar strengthening through the week,
an H1 close below the prior week's low (51% of losing weeks vs 16% of winners),
selling in all sessions. None of it is visible early enough to act on. The
operator wants a trace that is readable *in time*. I have not found one.

## What is already established (please do not re-derive; build on it)

Read `docs/LOGIC_LEDGER.md` Parts 29-35 and `docs/WPWB_LIVE_PREREG.md` (all
amendments). Short version:

| question | answer | where |
|---|---|---|
| week-to-week persistence of traces (2024-26) | volatility rho +0.81, XAU/DXY corr +0.34; every direction/character trace ~0 | Part 31, `research/wpwb_live/traces.py` |
| 40 frozen tools on the current era | 0 pass (Bonferroni 40); TSM/META = long gold re-labelled | Part 31, `run_live_all.py` |
| cost regime | round-trip cost / median H1 move: ~19% (2021-23) -> 3.6% (2026) | Part 31 |
| 12 pre-week traces (vol, momentum 1/4/13w, extension, DXY 4w, CFTC rank/chg, event count, efficiency) | 0 of 12 separate winning from losing weeks | Part 34, `luck_check.py` |
| "skip FOMC weeks" and VOLMAN sizing | looked good 2022-26, **failed on unseen 2016-2021**; FOMC effect flips with the Fed cycle | Part 34, `oos_2016*.py` |
| Wednesday H1 checkpoint (5 features) | 0 of 5; DXY-so-far significant in both sub-eras but opposite signs | Part 35, `h1_traces.py` |
| first break of prior-week range as continuation | FAIL; after a break BELOW last week's low gold bounced (continued down 46% / 34%) | Part 35, `level_break.py` |

Engine decision: **NO TRADE**. No orders were sent at any point.

## What I am asking you for (three bounded tasks, pick in this order)

### 1. Independent audit — could a bug be hiding a real trace?
Second pair of eyes on `research/wpwb_search/common.py` (H1 from M5, Bid/Ask
cost model, swap via `mtf_engine.rollover_nights`, week boundaries via
`weekly_evolution_grid._week_boundary`, significance rule `block_boot`),
`research/wpwb_live/h1_traces.py` (Wednesday 00:00 UTC checkpoint, event
timestamps — note pandas 3 stores datetimes in microseconds; one bug of this
kind was already found and fixed in `backtest_report.py`), and
`research/wpwb_live/fetch_fresh.py` (fresh MT5 M5 appended after the canonical
snapshot; verified 99.9995% identical on overlap). Report anything that would
bias results toward "no trace". Unit tests: `research/wpwb_search/test_common.py`.

### 2. Leading traces from data Claude does not have locally
Every trace I could test came from price, DXY, the MT5 economic calendar and
CFTC legacy. Candidates that plausibly *lead* gold's weekly direction and are
not in the repo:
- US 2-year and 10-year Treasury yields / real yields (10y TIPS) — level and
  change into the week;
- Fed funds futures or other policy-expectation measures (hawkish/dovish
  repricing before FOMC);
- gold implied volatility (e.g. GVZ) vs realised — a risk premium signal;
- CFTC disaggregated/managed-money positioning rather than legacy non-
  commercial.
If you can retrieve any of these (daily is enough, weekly-rebuild causal
alignment required), please add them under `data/external/` with a README of
the source and retrieval date, and test each as a pre-week trace.

### 3. The one open hypothesis
The FOMC-week effect on gold longs follows the Fed cycle (Part 34: positive
2016/2018-2020 easing years, negative 2021-2026). Hypothesis: **FOMC-week
direction is readable from the Fed's current direction**, measured causally
(e.g. the 3-month change in the 2-year yield, or the last decision's sign,
known before the week). Only ~2 policy cycles exist in 2016-2026, so please
state the power problem plainly rather than over-claim.

## Rules this project holds you to (unchanged, all apply)

- **Pre-register before running** — write the hypothesis, data, window and
  pass criterion into a new amendment of `docs/WPWB_LIVE_PREREG.md` (or your
  own prereg doc), commit, then run once.
- A trace counts only if it holds in **both** eras (2021-07..2023-12 and
  2024-01..2026-09) or on data never examined (broker D1 2016-08..2020-11 is
  available via MT5; H1 before 2020-12 is NOT intraday on this broker).
- Compare against random controls (random direction / random timing /
  random week-skip), and account for how many traces you examined.
- Report failures as plainly as passes. NOT ASSESSED rather than a guess.
- No real-money order, ever. Demo orders only under
  `data/DEMO_ORDER_PERMISSION.md`. No Grid/Martingale. No PR without evidence.
- Please do not edit Claude's existing Parts; append your results as new
  `docs/LOGIC_LEDGER.md` Parts, labelled "(Codex)".

## Where the work lives

`research/wpwb_search/` (engine, closed 40-variant search), `research/
wpwb_live/` (current-era work, traces, backtests, luck checks), `data/`
(gitignored outputs; `data/fresh/*.npz` = fresh MT5 bars through
2026-09-28 07:00 UTC), branch `claude/claude-md-project-file-qh0ier`
(local, not pushed).
