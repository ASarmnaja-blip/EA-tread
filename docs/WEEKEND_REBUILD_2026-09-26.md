# Weekly evolutionary rebuild — Saturday 2026-09-26

Produced under the `current-edge-wednesday-observation` automation
(`target_thread_id 01a0c7ca-a090-7023-b04c-58cd07c14178`), Saturday branch.
Read-only. **No manual, test or real-money order was sent.** The frozen Demo
autotrader handles its own allowed orders and was not touched.

Run late and by Claude rather than the automation: both agents hit their limits and
the machine was shut down on 2026-09-23 at 09:32 UTC. `--mode weekend` executed
2026-09-26 ~09:45 UTC (16:45 Asia/Bangkok), after XAUUSD closed.

**Two scheduled slots were missed and are not reconstructed:**

| slot | status |
|---|---|
| Wed 2026-09-23 05:15 Bangkok snapshot | **ran** — `data/current_edge_signal.json`, generated 2026-09-22T22:16:07Z |
| Wed 2026-09-23 12:15 Bangkok observation report | **MISSED** — machine off. Not reconstructed; the intraday state it would have compared against no longer exists |
| Sat 2026-09-26 05:15 Bangkok rebuild | **MISSED at its slot**, executed late here |

---

## 1. Previous week's realized results, and the condition of the active tool

### Realized: nothing traded

`data/payoff_demo_autotrader_state.json`, last written 2026-09-23T02:32:25Z:

```
mode                LIVE_DEMO
halted              False
start_equity        995.52
peak_equity         995.52
drawdown_fraction   0.0
signals_found       0
scan_reason         ok
last_event          2026-09-23T02:32:27Z  kind=no_trade  reason=ok
```

`data/payoff_demo_autotrader_log.json` holds 1,000 entries and **every one is
`no_trade / ok`**. Realized P&L for the week is **zero, from zero trades**. Equity
is unchanged at 995.52 and drawdown is 0.0 %.

### An operational failure that must be stated

The autotrader has produced **no log entry since 2026-09-23T02:32:27Z — about 3.4
days**, because the machine was shut down. It is not halted by its own risk logic
(`halted: False`); it is simply not running. Any claim that "nothing traded because
no signal fired" is only verified up to 2026-09-23 02:32 UTC. **What happened
between then and Friday's close is NOT ASSESSED**, and the week's zero is a zero of
absence, not a zero of decisions.

### Condition of the active set

`current_edge_ops.py --mode weekend`, generated 2026-09-25T20:57:59Z, source MT5
live (Exness-MT5Trial7). Cost charged: live Standard spread 0.260, commission 0.140
round turn, slippage 0.0165 per fill, long swap 0.5493/night.

**6 ready arms**, down from 8 at Wednesday's snapshot.

| arm | mode | score | m10 | m30 | m60 |
|---|---|---|---|---|---|
| crowded:post_news_chase | FOLLOW | +0.2411 | +0.9793 | +0.3822 | +0.2850 |
| crowded:breakout_into_level | FLIP | +0.1219 | −0.1670 | +0.4198 | +0.1627 |
| core:S5V1 VWAP reversion 2.5sd | FLIP | +0.1148 | +0.1788 | +0.2119 | +0.3493 |
| core:S4V1 failed breakout, lb 40 | FOLLOW | +0.0978 | +0.3096 | +0.1317 | +0.1211 |
| core:S6V1 expansion, pct 15 | FOLLOW | +0.0694 | +0.4698 | +0.0957 | +0.0933 |
| crowded:late_extension | FLIP | +0.0574 | +0.1538 | +0.1068 | +0.0499 |

Ready basket, by window:

```
30d  trades=149  net_R=+7.8978  mean=+0.0530  win=53.69%  pf=1.114  maxDD_R=-12.47  max_L=7
60d  trades=322  net_R=+13.2645 mean=+0.0412  win=53.42%  pf=1.088  maxDD_R=-12.47  max_L=7
90d  trades=465  net_R=+9.2893  mean=+0.0200  win=52.47%  pf=1.042  maxDD_R=-15.92  max_L=7
```

At the risk levels the checklist prints, over 90 days:

```
2.0%  net +18.58%   maxDD -31.85%
2.3%  net +21.37%   maxDD -36.63%
3.0%  net +27.87%   maxDD -47.77%
```

**The 60–90 day window is negative**: trades=143, net_R=−3.9752, mean=−0.0278,
win 50.35 %, pf 0.945. So the basket's positive 90-day total is carried entirely by
the two most recent months, and `late_extension FLIP` — the largest contributor at
0–30d (+5.2394 R over 93 trades) — was the **largest detractor** at 60–90d
(−6.4862 R over 88 trades). `S4V1 failed breakout` is the mirror image: +6.1645 R at
60–90d, **−6.4775 R at 0–30d**.

### The finding that matters most this week

```
LEAD TRACE CHECK
current gate            samples=76  future30_mean=-0.0420  hit=34.21%
fast recent-window      samples=69  future30_mean=-0.0734  hit=30.43%
accel recent>medium>long samples=39 future30_mean=-0.0413  hit=35.90%
flip pressure           samples=31  future30_mean=-0.0665  hit=32.26%
```

**Every gate is negative forward, with hit rates of 30–36 %.** The selection
machinery that chooses the ready basket does not, on this evidence, predict the
following 30 days — it anti-predicts them. That is the same result the Amendment 15
and 16 walk-forward reached from the other direction, and it is the central fact for
section 6.

---

## 2. Archived Wednesday state

`data/current_edge_signal.json`, generated **2026-09-22T22:16:07Z**
(= Wed 2026-09-23 05:16 Asia/Bangkok), source MT5 live (Exness-MT5Trial7).

```
symbol    XAUUSD
decision  NO_TRADE
reason    8 arm(s) are READY, but none fires on the latest closed M15 bar
policy    lookback 90d, half-life 21d, geometry 1.5 ATR stop / 1:1 target /
          72 M5 time stop, arms=48, ready_arms=8
data      latest closed M5 2026-09-22T22:15:00Z, latest closed M15 open
          2026-09-22T22:00:00Z, age 1.1 minutes
signal    None
```

Data freshness at that moment was good (1.1 minutes). **Ready arms fell from 8 on
Wednesday to 6 today**, and the Wednesday 12:15 comparison that would have shown
the intraday path between them was never taken.

---

## 3. Next week's material USD events

**Source and its limits, stated before the table.** Scheduled times, forecasts and
previous values below come from the **broker's MT5 calendar feed**
(Exness-MT5Trial7), dumped to `data/calendar.csv`. That dump is dated 2026-09-22, so
**any consensus revised after 2026-09-22 is not reflected here**. These figures are
**NOT verified against BLS, BEA or the FOMC calendar as primary sources** — that
verification is **NOT ASSESSED** for this report. Times are UTC.

| when (UTC) | imp | event | forecast | previous |
|---|---|---|---|---|
| Tue 29 Sep 14:00 | HIGH | JOLTS Job Openings | 7.106 | 7.271 |
| Tue 29 Sep 14:00 | HIGH | CB Consumer Confidence | 89.4 | 89.4 |
| Wed 30 Sep 12:15 | HIGH | ADP Nonfarm Employment Change | 41.0 | 38.0 |
| Wed 30 Sep 12:30 | HIGH | GDP q/q | 1.5 | 1.5 |
| Wed 30 Sep 12:30 | HIGH | **Core PCE Price Index m/m** | 0.2 | 0.2 |
| Wed 30 Sep 12:30 | HIGH | **Core PCE Price Index y/y** | 3.3 | 3.3 |
| Wed 30 Sep 12:30 | MED | PCE Price Index y/y | 4.2 | 3.7 |
| Wed 30 Sep 13:45 | HIGH | MNI Chicago Business Barometer | — | — |
| Thu 01 Oct 12:30 | HIGH | Initial Jobless Claims | — | — |
| Thu 01 Oct 13:45 | HIGH | S&P Global Manufacturing PMI | 52.6 | 53.9 |
| Thu 01 Oct 14:00 | HIGH | ISM Manufacturing PMI | 56.0 | 54.6 |
| Thu 01 Oct 14:00 | HIGH | ISM Manufacturing Prices Paid | 76.3 | 71.1 |
| **Fri 02 Oct 12:30** | **HIGH** | **Nonfarm Payrolls** | **52.0** | **162.0** |
| Fri 02 Oct 12:30 | HIGH | Unemployment Rate | 4.1 | 4.1 |
| Fri 02 Oct 12:30 | HIGH | Average Hourly Earnings m/m | 0.3 | 0.3 |
| Fri 02 Oct 12:30 | MED | Participation Rate | 61.7 | 61.6 |
| Fri 02 Oct 19:30 | MED | CFTC Gold Non-Commercial Net Positions | — | — |

No FOMC meeting falls inside the window per this feed. **Whether an unscheduled
FOMC statement or speech is calendared is NOT ASSESSED** — the FOMC calendar was not
retrieved as a primary source for this report.

**These are catalysts, not directions.** Their actual outcomes are unknown. Nothing
above is labelled bullish or bearish, and none of it may be read as a directional
input until the release prints and the price reaction is observed.

---

## 4. DXY and XAU market state

From MT5 (Exness-MT5Trial7), D1 bars. The market is closed: the last XAUUSD M15 bar
opened **2026-09-25T20:45Z** and the last tick is **2026-09-25T20:57Z** with a
quoted spread of 0.0900. Everything below is as of Friday's close.

| symbol | last D1 close (2026-09-25) | 5-day change | 5-day high | 5-day low |
|---|---|---|---|---|
| XAUUSD | 4,285.982 | **−1.98 %** | 4,383.539 | 4,244.078 |
| DXY | 101.030 | **+0.75 %** | 101.400 | 100.179 |
| EURUSD | 1.139 | −0.67 % | 1.150 | 1.137 |

Gold fell and the dollar rose over the week, which is the conventional direction of
that pair. **No causal claim is made**: one week of two series is not evidence of a
mechanism, and this project has never tested DXY as a regime input (backlog C4).

`USDX` is not a symbol on this account; `DXY` was used. Real US yields: **NOT
ASSESSED — no bond or yield symbol is available on this account.**

---

## 5. CFTC Gold positioning

**Primary source, retrieved live for this report.**

- Source: CFTC Commitments of Traders, CMX Futures Only —
  <https://www.cftc.gov/dea/futures/deacmxsf.htm>
- Retrieved: **2026-09-26 ~09:50 UTC**
- Market: `GOLD - COMMODITY EXCHANGE INC.`, Code 088691, contracts of 100 troy oz

```
FUTURES ONLY POSITIONS AS OF 09/22/26      OPEN INTEREST: 412,800

non-commercial   LONG 253,982   SHORT 28,129   SPREADS 48,923
commercial       LONG  57,458   SHORT 320,361
CHANGES FROM 09/15/26 (open interest +2,901)
non-commercial   LONG -4,077    SHORT   +408   SPREADS   +960
percent of OI    LONG   61.5%   SHORT   6.8%
traders          293 total, 174 long, 47 short
```

**Net non-commercial = 253,982 − 28,129 = 225,853 contracts**, a change of
**−4,485** from the prior week.

### The lag, stated explicitly

- **Survey date: Tuesday 2026-09-22** — the positions are as they stood at that
  Tuesday's close.
- **Release date: Friday 2026-09-25**, 15:30 US Eastern.
- **Lag: 3 days from survey to release**, and by the time this report is written the
  data is **4 days old at the survey date**. Any positioning change after Tuesday
  2026-09-22 is **NOT ASSESSED**.

### A discrepancy in the local dump, worth recording

`data/cftc_legacy` (dumped 2026-09-22 23:12) ends at survey **2026-09-15**, net
**230,338**, percentile rank 73.4 %. It is one release behind. This report uses the
primary source for the current week; the local dump needs re-running before any
code path that reads it is trusted.

---

## 6. Conditional scenario map

No directional forecast is made. Each branch below is conditional on an observable
that has not yet occurred.

**The framing constraint first.** The lead-trace check in section 1 is negative on
all four gates. Until that is explained or reversed, a positive 30-day basket figure
is **not** evidence that next week will be positive, and the scenarios below are
about risk management rather than expected profit.

| if this is observed | then the reading is | what it does NOT license |
|---|---|---|
| Core PCE m/m (Wed 30 Sep 12:30) prints **at** 0.2 and XAU holds its post-release range | the release was already priced; no new information for the basket | any size increase |
| Core PCE prints **away** from 0.2 **and** XAU closes the following M15 bars outside the pre-release range | a re-pricing occurred; `post_news_chase FOLLOW` is the only ready arm with a news mechanism, and its m10 is +0.9793 on **4 trades** in 0–30d | acting on 4 trades. That sample cannot carry a size decision |
| NFP (Fri 02 Oct 12:30) prints near 52.0 with the unemployment rate at 4.1 | consensus met; the week's largest catalyst passes without a regime change | nothing |
| NFP prints far from 52.0 — the previous was 162.0, so the forecast implies a sharp deceleration and the surprise band is wide | the highest-variance moment of the week, in the hour where spread and slippage are worst measured | trading it. This project has never measured slippage in an NFP minute |
| DXY continues above its 5-day high of 101.400 while XAU stays below 4,244.078 | the week's inverse move extended | a DXY-conditioned rule. DXY has never been tested as a regime input |
| CFTC net (next release Fri 02 Oct 19:30, survey Tue 29 Sep) falls materially below 225,853 | long positioning is unwinding | a directional conclusion. Positioning is a crowding measure, not a signal, and it arrives 3 days stale |
| The autotrader log shows entries resuming and `halted: False` | the operational gap is closed | treating the prior week's zero as a decision rather than an absence |

### Recommendation for the coming week

Under the automation's terms this report may recommend keeping, replacing or
standing aside, and **may not change parameters, promote a tool, or alter Demo
execution**. It does none of those.

> **STAND ASIDE on any change. Keep the frozen configuration exactly as it is, and
> restore observation rather than act.**

The reasoning, in order of weight:

1. **The lead trace is negative on all four gates.** Replacing the tool would be
   choosing a new arm using the same selection machinery that just failed its
   forward check. Keeping it is not an endorsement; it is the only option that adds
   no new untested decision.
2. **The week produced no decisions to learn from.** Zero trades, and 3.4 days with
   the autotrader not running. There is no realized evidence this week either way.
3. **The 60–90 day window is negative and the drivers invert between windows.**
   `late_extension` is the top contributor recently and the worst detractor before
   that; `S4V1` is the reverse. That is the signature of regime-dependent noise, not
   of a stable arm.
4. **At 2.3 % risk the 90-day max drawdown is −36.63 %**, inside the operator's
   stated 30–40 % band — so the sizing is not the problem, and no sizing change is
   proposed.

### Required before any promotion, per the automation

A **separately verified historical weekly walk-forward result** and **explicit user
approval**. Neither exists. Note also that this project's own walk-forward
(Amendment 16) found the roll-level minimum detectable effect to be **0.5342 R**
against effects of interest near 0.05–0.26 R, so a walk-forward that would satisfy
this condition has not yet been shown to be attainable from the data on hand.

---

## Operational items for the operator

1. **The autotrader is not running.** It stopped at 2026-09-23T02:32:27Z when the
   machine was shut down. It is not halted by risk logic. Restart it if the Demo
   observation is meant to continue.
2. **`data/cftc_legacy` is one release stale** (ends survey 2026-09-15). Re-run its
   dump before any code that reads it is trusted.
3. **`data/calendar.csv` was dumped 2026-09-22.** Forecasts revised since then are
   not reflected. Re-dump before the Wednesday snapshot.
4. **W1 is still unjudged** and outside this automation's scope. Its rollover
   measurement needs AutoTrading enabled in the MT5 terminal
   (`terminal_info().trade_allowed` was `False` on 2026-09-23) and the scheduled
   task's permission approved once. See `docs/OWNERSHIP.md`.

**No order was sent. No parameter was changed. The engine's answer remains NO TRADE.**
