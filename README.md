# XAU M15 Institutional Adaptive EA

A modular MetaTrader 5 Expert Advisor for XAU/USD on **M15**.

Entries come from a liquidity sweep confirmed by a market structure shift and
a displacement candle, gated by session, news, regime, spread and drawdown
checks, sized from account equity, and managed as three independent positions
at 1R / 2R / 3R.

> **Status: not yet backtested.** The code and the test tooling are here; the
> numbers are not. Run `docs/BACKTEST.md` on your own broker's history before
> forming any view on whether this works. No performance is promised.

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

### The three setups are independent (spec 16)

Setup A, B and C are separate evaluators with their own enable flags and
their own statistics buckets. They never share a pooled score. If more than
one qualifies on the same bar the higher grade wins, breaking ties A → B → C.

| Setup | Idea |
|---|---|
| **A — AMD liquidity reversal** | Asian range → sweep of its extreme → close back inside → MSS → displacement → retest |
| **B — Volume profile continuation** | Trend + VWAP side + pullback into value → acceptance → structure → displacement → retest |
| **C — Opening range expansion** | London/NY opening range → breakout with volume *and* ATR expansion → structure → displacement → retest |

Setup C never enters on the breakout alone; a retest is required.

## Key parameters

Defaults are tuned for a **$1,000 USD demo** account.

| Input | Default | Notes |
|---|---|---|
| `InpRiskPercent` | 0.75 | % of equity per setup, split across legs |
| `InpMaxRiskPercent` | 1.00 | hard cap; setups that cannot fit are rejected |
| `InpPositionsPerSetup` | 3 | three real positions, not one partial-closed |
| `InpLotFitMode` | REDUCE_POSITIONS | degrade 3→2→1 legs rather than over-risk |
| `InpSLBufferATR` | 0.35 | ATR buffer beyond the structure level |
| `InpMinSLATR` / `InpMaxSLATR` | 0.50 / 3.00 | wider setups are rejected, not clipped |
| `InpTP1R/2R/3R` | 1 / 2 / 3 | the ladder |
| `InpBEMode` | BE_SPREAD | legs 2–3 to break-even once TP1 closes |
| `InpDailyProfitTarget` | 3.0 | % — stops new trades |
| `InpDailyLossLimit` | 2.5 | % — stops new trades |
| `InpDD_Preferred` / `InpDD_Emergency` | 35 / 40 | % — halt / close-all |
| `InpMaxTradesPerDay` | 3 | setups, not legs |
| `InpEntryMode` | RETEST | market / retest / limit / breakout |
| `InpAllowBSetup` | false | trade only A and A+ grades by default |
| `InpMaxSpread` | 0.60 | price units ($) |

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
```

Use **every tick based on real ticks**. With three legs sharing one stop
price, cruder modelling picks a favourable intrabar order of events and
overstates results.

## Known limitations

1. **Not yet backtested or forward tested.** No performance claim is made.
2. **Lot granularity on small accounts.** At $1,000, minimum lot forces many
   setups down to 1–2 legs. The trade distribution differs from a larger
   account, so results do not transfer between account sizes.
3. **Tick volume is not real volume.** See the disclosure above.
4. **Calendar API is unavailable in the Strategy Tester** on most builds. Use
   `InpManualNewsTimes` for backtests that need news blackouts, or accept that
   backtests trade through news that live trading would skip — this usually
   makes backtests look *better* than live.
5. **DST is manual.** `InpDSTOffsetHours` is not automatic; session windows
   drift by an hour twice a year unless you set it.
6. **Signal price vs. fill price.** Signals form on the closed M15 bar; the EA
   re-prices and re-sizes against the live bid/ask before ordering, but a fast
   market can still fill away from the intended entry.
7. **Partial ladders are kept, not unwound.** If only some legs fill, the EA
   keeps them rather than paying spread twice to correct the ladder.
8. **Sharpe in the report is per-trade R, not annualised.** It is comparable
   between runs of this EA, not with published fund Sharpe ratios.
9. **Single-symbol, single-timeframe.** No portfolio or correlation handling.
10. **Higher-timeframe bias (H1/H4) is not implemented**; regime uses M15
    EMA50/EMA200 only. Spec 1 lists HTF bias as optional.

## Repository layout

```
MQL5/Experts/XAUM15/   the EA
MQL5/Include/XAUM15/   17 modules, one job each
tools/                 MT5 data export, ablation set generator
docs/BACKTEST.md       backtest, optimisation and robustness procedure
```

## Disclaimer

Trading leveraged instruments carries substantial risk of loss. This software
is provided for research and testing. Backtest results, forward test results,
expected performance and targets are four different things and are kept
separate throughout this repository. Run it on demo until you have your own
evidence.
