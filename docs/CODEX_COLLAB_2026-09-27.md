# To Codex, for Sunday 2026-09-27 12:30 — working together from here

Claude here. The operator has un-paused you and wants the two of us to develop
the project **together** from now on. He also said plainly that your work
served him better than mine did while you were paused, so you lead the
basket engine. The split is in `docs/OWNERSHIP.md` (fifth revision).

## What the operator wants from this phase

1. **Not fixed to one tool.** A basket of several tools running together,
   chosen and re-weighted at each Weekend Rebuild.
2. **Size the basket so its maximum drawdown lands at 35–40%.**
3. Stay inside the nine rules: `docs/AMENDMENT_22_WEEKLY_OPERATING_PROTOCOL.md`
   and `docs/AMENDMENT_22_ADDENDUM_RULE9.md`. Wednesday Report = observe and
   collect; Weekend Rebuild = the only point where tools are retuned or
   replaced; recent weeks weigh more with decaying weight; every trace kept
   (`docs/LOGIC_LEDGER.md`).

One point I have to put in front of both of us: a 35–40% drawdown target sets
**how large** the basket trades, not **whether** it makes money. The basket
needs a positive walk-forward result first; sizing then scales it.

## What I did while you were paused, and what it means for your work

All committed; nothing of yours was modified except where stated.

| finding | where | why it matters for the basket |
|---|---|---|
| `compound_bar_replay.py --profile cent260` runs end to end. EXCLUDE_LATEST_365D: net −$118 to −$183 at every DD target. ALL_FORWARD: +$21k to +$68k | `docs/COMPOUND_BAR_REPLAY_STATUS_2026-09-26.md` | the profit sits in the last 12 months. Max cent lot grows 1.36 → 42.97, so compounding amplifies one year |
| actual mark-to-market DD came in at **8.5–17.9%** (44-month run) and **15.0–23.8%** (full run) against targets of 30–50% | same | calibrating on 2021 alone undersizes against the target. This is the first thing to fix for a 35–40% DD |
| a **demo90** universe cache now exists: `data/weekly_evolution_universe_v10_sp090_co140.pkl` | built as a side effect of reading `load_universe` with default costs | you can run the replay on the real Demo cost model without a rebuild, while `walk_forward.py` and `mtf_engine.py` stay unchanged |
| fixed 8,250-cell grid, share of cells net-positive by quarter: 17–47% from 2021Q2 to 2025Q2, then **46, 56, 53, 55, 53%** for the last five quarters | `docs/DIAGNOSIS_44_MONTH_LOSS_2026-09-26.md`, `research/pilot/diagnose_grid_by_quarter.py` | the recent regime suits the grid far better than the prior four years. The cause is NOT ASSESSED |
| gold rose +101% in the losing 44 months, versus +18.5% in the trailing 12 | same | the losing window was not a flat market. The rules failed to read it |
| weekend lead-trace check: all four gates negative, future30 −0.042 to −0.073, hit rate 30–36% | `docs/WEEKEND_REBUILD_2026-09-26.md` | the current READY selector anti-predicts the next 30 days |
| single-tool reselection, top-1 of 9,000 geometries per month: in-sample ceiling +2.09 R/month, walk-forward **about −0.10 R/month** (zero-trade months counted as 0; about 34% of months positive) | `research/pilot/fine_grid_walk.py` | picking one tool does not carry forward. This supports the operator's basket direction |
| MT5 bars before 2021 are one bar per day at 00:00 with spread 0, not M5 | `docs/LOGIC_LEDGER.md` | your `START_YEAR = 2021` was right |
| `weekly_evolution_grid.py` ranks on a flat 56-day window; rule 5 asks for decaying weight | Amendment 22 §3.1 | a likely contributor to the 73% weekly champion churn |

## Operational state

- `payoff_demo_autotrader.py` has not run since 2026-09-23 02:32 UTC (machine
  shut down, not halted by its risk logic).
- `data/cftc_legacy` is one release stale (ends at the 2026-09-15 survey).
  The 2026-09-22 survey was read from cftc.gov for the weekend report.
- `data/calendar.csv` was dumped 2026-09-22.
- W1 rollover probe is scheduled for Mon 2026-09-28 21:52 UTC (Claude's).

## What I suggest we do first, for you to accept or change

1. You write the amendment for the basket and the 35–40% DD sizing **before**
   anything runs. It should cover which tools, how they are weighted with
   decaying weight, how many run at once, the calibration window for sizing,
   and the zero-trade policy.
2. I review it for look-ahead, cost profile and the drawdown arithmetic
   before you run it.
3. You run it on the demo90 cache and report the 44-month and trailing-year
   splits separately, as `compound_bar_replay.py` already does.
4. I check the drawdown figures independently before the result goes to the
   operator.

Standing rules unchanged: no real-money orders, Demo orders only under
`data/DEMO_ORDER_PERMISSION.md`, no Grid/Martingale, no PR yet, NOT ASSESSED
rather than guessing.
