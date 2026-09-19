# XAU M15 Institutional Adaptive EA

A modular MetaTrader 5 Expert Advisor for XAU/USD on **M15**.

The default entry is a **trend-zone** rule: go long when price sits between
1.08 and 7.21 ATR above its 200-bar SMA, stop at 1.8 ATR, target 8R, one
position, 0.5 % risk, with a 30-hour time stop behind the target. That is the
whole signal.

It is deliberately plain, because a 16-round research program on 15 years of
XAUUSD minute data found that the elaborate version did not work and the
simple one did. **[docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md)
records what was tested, what died, and what survived** — read it before
changing any default.

> **Status: the trend zone FAILED the cross-asset test this README used to
> list as pending.** Nine markets at H1, 30-hour time stop matched in
> wall-clock hours: drift-adjusted skill is positive on **0 of 9**, on both
> sides (long mean −0.1322, across-market t −2.97; short −0.1226, t −3.51).
> Gold itself is in the failing set. This README previously said "if it does
> not reproduce there, it is gold overfit" — that is now the reading.
> Run `research/setup_d_crossasset.py` to reproduce. No performance is
> promised and the default-on setup should not be traded on the strength of
> the gold-only evidence below.

---

## What this EA will not do

Constraints from the specification, enforced in code:

- No martingale, no grid, no recovery lot
- No risk increase after a loss
- No lot increase to chase the daily profit target
- The daily profit target **stops** trading; it never demands a trade
- A day with no qualifying setup is a valid outcome — the EA sits flat

## Install

```
MQL5/
├── Experts/XAUM15/XAU_M15_Institutional_Adaptive.mq5
└── Include/XAUM15/*.mqh
```

1. In MetaTrader 5: **File → Open Data Folder**
2. Copy `MQL5/Experts/XAUM15/` into `MQL5/Experts/`
3. Copy `MQL5/Include/XAUM15/` into `MQL5/Include/`
4. In MetaEditor press **F7** on the `.mq5`
5. Attach to an **XAUUSD M15** chart with algo trading enabled

Includes resolve as `<XAUM15/...>`, so the `Include/XAUM15/` folder must sit
directly under `MQL5/Include/`.

## Architecture

Each module answers exactly one question. Nothing is a voting pool of
redundant oscillators (spec 37).

| Layer | Module | Question |
|---|---|---|
| **Gate** | Session, News, Spread, Daily risk, Drawdown | *May I trade at all?* |
| **Context** | Regime, AMD, VWAP, Macro | *What environment is this?* |
| **Location** | Liquidity map, Volume profile | *Where is price?* |
| **Event** | Sweep | *Did liquidity get taken?* |
| **Confirm** | Structure (MSS), Displacement | *Did structure and momentum agree?* |
| **Execute** | Setups A/B/C, Quality, Risk, Broker | *What order, what size?* |
| **Manage** | Trade manager | *Break-even, time stop, exit* |
| **Report** | Dashboard, Statistics, Logger | *What happened and why?* |

Gates can only ever **block**. None of them can create a trade.

### Order of evaluation

```
tick ──┬─ daily risk + drawdown guard        (every tick)
       ├─ manage open positions, BE, time stop
       └─ new M15 bar?
            └─ refresh context (structure, liquidity, AMD, VWAP, VP)
                 └─ veto chain: enabled → DD → daily → cooldown →
                    concurrent → session → news → spread → regime → one/bar
                      └─ evaluate Setup A, B, C independently
                           └─ grade quality → size → validate stops → order
```

### Four independent setups, one on by default

Each setup is a separate evaluator with its own enable flag and its own
statistics bucket. They never share a pooled score.

| Setup | Default | Idea | Evidence |
|---|---|---|---|
| **D — Trend zone** | **on** | `(Close − SMA200)/ATR` in [1.08, 7.21] → long. Flat 1.8 ATR stop, **8R target**, 30 h time stop | permutation p = 0.0005; net E +0.2312R at 8R (costed at $0.26) — but **cross-asset FAILED: drift-adjusted skill positive on 0 of 9 markets**, and the long side is the drift-negative one — see below |
| A — AMD liquidity reversal | off | Asian range → sweep → close back inside → MSS → displacement → retest | **no edge at n = 43,353**; inversion test conclusive |
| B — Volume profile continuation | off | Trend + VWAP + pullback into value → acceptance → structure → displacement | untested |
| C — Opening range expansion | off | London/NY opening range → breakout with volume *and* ATR expansion → retest | untested |

Setup D bypasses the quality grader on purpose: every confluence filter
tested on top of it reduced expectancy. Setups A–C remain in the codebase
because switching a hypothesis off is not the same as losing the ability to
re-test it.

## Key parameters

Every default below traces to a measurement in
[docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md).

| Input | Default | Why |
|---|---|---|
| `InpTrendZoneMin` / `Max` | 1.08 / 7.21 | the tested zone, in ATR from SMA200 |
| `InpTrendSmaPeriod` | 200 | **SMA**, not EMA — matches the research |
| `InpTrendZoneLong` / `Short` | true / false | long side t = +5.08, short only +2.65 |
| `InpTrendSLATR` | 1.8 | flat stop of the winning configuration |
| `InpTimeStopBars` | 120 | 30 hours; shortening it cut the tail |
| `InpExitMode` | TIME_STOP_ONLY | partial closes halved profit in testing |
| `InpPositionsPerSetup` | 1 | the ladder is available but unsupported by evidence |
| `InpRiskPercent` | 0.50 | 0.5 % → 20.2 % p.a. at 28.2 % DD; 2 % → 64 % p.a. at **84 % DD** |
| `InpMaxRiskPercent` | 1.00 | hard cap; setups that cannot fit are rejected |
| `InpCooldownBarsLoss` | 0 | losing streaks are normal here; a cooldown just deletes trades |
| `InpUseDailyLimits` | true | **see the warning below** |
| `InpDD_Preferred` / `Emergency` | 35 / 40 | % — halt / close-all |
| `InpMaxSpread` | 0.60 | price units ($) — measure yours first |
| `InpSLMode` | FIXED_ATR | STRUCTURE_ATR restores the Setup A/B/C behaviour |

### The long side is drift-dependent

Gold rose across the whole sample. Subtracting that drift minute by minute:

| | Raw E | t | Skill (raw − drift) | t |
|---|---|---|---|---|
| longs in zone | +0.0569 | +4.45 | **−0.0494** | **−4.14** |
| shorts in zone | +0.0102 | +0.75 | **+0.1092** | **+7.56** |
| longs in − out | +0.0862 | +5.24 | +0.0781 | +5.08 |
| shorts in − out | +0.0490 | +2.83 | +0.0492 | +2.65 |

The zone does real timing work on **both** sides — that is what the in-minus-out
rows say. But in absolute terms, longs in the zone are *negative* once drift is
removed. **Long-only is a bet that gold keeps trending up, plus the zone.** The
default stays long because that is what the equity curves were built on, not
because it is the better-evidenced side.

### Spread is the other open question

| Source | Spread | Cost at 1.8×ATR | Net E at 8R |
|---|---|---|---|
| terminal quote | $0.26 | 0.056R | +0.2312R |
| OANDA 2012–2026 | $0.4824 | 0.104R | +0.1834R |
| **OANDA 2023–2026** | **$0.7525** | **0.162R** | **+0.1253R** |

A 46 % haircut, and it is not confined to Asian hours — the hourly table runs
$0.72–$0.91 all day. `SpreadMonitor` measures your broker's real figure.

### The daily loss limit may need to be off

At the current gold ATR, minimum lot on a 1000 USC ($10) account risks
**2.04 % per trade**. A −2.5 % daily limit then halts trading after 1.2
losses — and this system has a 23.8 % win rate with a 19-trade losing streak
on record. It would sit halted almost every day.

The EA prints a **capital adequacy report** at startup with the real numbers
and warns when this applies. `InpUseDailyLimits = false` switches both daily
rules off together. This is a real conflict between the original
specification and the measured system, and it is your call.

Times are **broker server hours**. `InpDSTOffsetHours` shifts every window at
once when your broker's DST changes.

## Volume source disclosure

XAU/USD spot is OTC. `InpVolumeSource` defaults to `BROKER_TICK_VOLUME`,
which counts price updates at **one broker**. That is not global gold volume
and not COMEX futures volume. The volume profile is a broker-local
approximation of where that feed spent time — treat it as a location filter,
which is all the EA uses it for. `VOL_EXTERNAL` / `VOL_AUTO` pick up real
volume when your broker supplies it.

## Backtesting

See **[docs/BACKTEST.md](docs/BACKTEST.md)** for the full procedure.

```bash
pip install MetaTrader5 pandas
python tools/export_mt5_data.py --list
python tools/export_mt5_data.py --symbol XAUUSD --years 6
python tools/make_ablation_sets.py --outdir sets --per-setup
python tools/capital_check.py --equity 1000 --risk 0.5   # what can this account trade?
```

Use **every tick based on real ticks**. With three legs sharing one stop
price, cruder modelling picks a favourable intrabar order of events and
overstates results.

## Known limitations

1. **The trend zone failed cross-asset validation.** It was found on the full
   gold sample, not a held-out half. `research/setup_d_crossasset.py` ran the
   confirmation on nine markets at H1: drift-adjusted skill positive on 0 of 9
   on both sides. Only USDJPY long showed positive raw E (+0.0557) and its
   skill was −0.0535 — the market rose, counted twice. The implementation was
   verified first (gold M15 reproduces +0.1788R at zero cost vs the documented
   +0.2312R, which the cost table below prices at the $0.26 quote), so this is
   a real failure and not a coding artefact. Separately, the shipped config
   trades **longs only** — the side the drift table below gives −0.0494 skill
   (t −4.14) — while shorts, at +0.1092 (t +7.56), are switched off.
2. **Capital adequacy is the binding constraint — and it is about volatility,
   not account currency.** A 1000 USC cent account is arithmetically identical
   to a $1,000 USD account ([proof](docs/ACCOUNT_SCALING.md)). What binds is
   that minimum lot does not shrink while gold's ATR sits 4.4× above its
   15-year mean: 0.5 % risk needs ~4,000 units either way. At 2.04 % risk the
   35 % drawdown guard fires with ~77 % probability inside a year, so that
   configuration shuts itself down. Majors on the same account floor near
   0.11 % — run `tools/capital_check.py` to see your broker's real table.
3. **Spread is unsettled by a factor of three** ($0.26 reported vs $0.4824
   measured vs $0.7525 in Asian hours). `SpreadMonitor` writes
   `XAUM15_spread_by_hour.csv` so you can settle it with your own broker.
4. **Win rate is 23.8 %** with a 19-trade observed losing streak and ~29
   expected. Profit is a long right tail. This is psychologically hard to run.
5. **Tick volume is not real volume.** See the disclosure above.
6. **Calendar API is unavailable in the Strategy Tester** on most builds. Use
   `InpManualNewsTimes` for backtests that need news blackouts, or accept that
   backtests trade through news that live trading would skip — this usually
   makes backtests look *better* than live.
7. **DST is manual.** `InpDSTOffsetHours` is not automatic; session windows
   drift by an hour twice a year unless you set it.
8. **Signal price vs. fill price.** Signals form on the closed M15 bar; the EA
   re-prices and re-sizes against the live bid/ask before ordering, but a fast
   market can still fill away from the intended entry.
9. **Partial ladders are kept, not unwound.** If only some legs fill, the EA
   keeps them rather than paying spread twice to correct the ladder.
10. **Sharpe in the report is per-trade R, not annualised.** It is comparable
   between runs of this EA, not with published fund Sharpe ratios.
11. **Single-symbol, single-timeframe.** No portfolio or correlation handling.
12. **Higher-timeframe bias (H1/H4) is not implemented**; regime uses M15
    EMA50/EMA200 only. Spec 1 lists HTF bias as optional.

## Repository layout

```
MQL5/Experts/XAUM15/   the EA
MQL5/Include/XAUM15/   17 modules, one job each
tools/                 MT5 data export, ablation set generator
docs/BACKTEST.md       backtest, optimisation and robustness procedure
docs/RESEARCH_FINDINGS.md  what was tested, what died, what survived
docs/ACCOUNT_SCALING.md    cent vs USD, minimum lot, and what fits
```

## Disclaimer

Trading leveraged instruments carries substantial risk of loss. This software
is provided for research and testing. Backtest results, forward test results,
expected performance and targets are four different things and are kept
separate throughout this repository. Run it on demo until you have your own
evidence.
