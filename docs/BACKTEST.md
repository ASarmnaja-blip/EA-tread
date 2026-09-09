# Backtest & Robustness Methodology

Covers spec sections 30–34 and 39. Nothing in this file reports results —
it is the procedure. No backtest has been run yet: this repository contains
the EA and the tooling, and the numbers have to come from your terminal on
your broker's history.

---

## 0. Account baseline used for parameter defaults

| Item | Value |
|---|---|
| Demo account | **$1,000 USD** |
| Symbol | XAU/USD, contract 100 oz |
| Minimum lot | 0.01 (= 1 oz, so a $1.00 gold move = $1.00) |
| Spread assumption | $0.26 |
| Risk per setup | 0.75 % of equity ($7.50) |
| Legs per setup | 3 independent positions |

**Lot granularity is a real constraint at this size.** Risking 0.75 % across
three legs means $2.50 per leg, which at minimum lot corresponds to a $2.50
stop. Structure-based stops on XAU M15 are frequently wider:

| SL distance | 3 legs at 0.01 lot | vs. 1 % cap |
|---|---|---|
| $2.50 | 0.75 % | fits |
| $3.00 | 0.90 % | fits |
| $4.00 | 1.20 % | drops to 2 legs |
| $5.00 | 1.50 % | drops to 2 legs |
| $6.00+ | 1.80 %+ | drops to 1 leg |

`InpLotFitMode = LOTFIT_REDUCE_POSITIONS` (default) degrades 3 → 2 → 1 legs
to stay under `InpMaxRiskPercent`, and rejects the setup if even one minimum
lot breaches the cap. Expect a meaningful share of setups to run fewer than
three legs on a $1,000 account. On a $3,000–5,000 account the full ladder
fits for most stops — that difference alone changes the trade distribution,
so **do not compare a $1,000 backtest against a $5,000 one.**

---

## 1. Data

```bash
pip install MetaTrader5 pandas
python tools/export_mt5_data.py --list                 # find the real symbol name
python tools/export_mt5_data.py --symbol XAUUSD --years 6
```

The script prints an intraday gap report. Gaps matter: the Strategy Tester
interpolates missing bars, which flatters any session- or liquidity-based
strategy. If gaps are numerous, get history from a different source before
trusting anything downstream.

**Broker history quality is the single biggest source of false confidence in
gold backtests.** Spread in the tester is usually modelled far tighter than
what you actually pay around the London and New York opens — exactly when
this EA trades.

## 2. Strategy Tester configuration

| Setting | Value | Why |
|---|---|---|
| Modelling | **Every tick based on real ticks** | Intrabar SL/TP sequencing decides which of the three legs fills |
| Symbol / TF | XAUUSD / **M15** | Primary timeframe per spec 1 |
| Deposit | 1000 USD | Match the target account |
| Leverage | as your broker | Affects margin, not signals |
| Spread | **Current** or a fixed 26 points | Never "variable-ideal" |
| Optimisation | Custom max (`OnTester`) | Deliberately not net profit |

`OnTester()` returns `expectancy × √trades × (PF / maxDD%)` and returns 0
below 30 trades or beyond the emergency drawdown. Net profit is never the
optimisation target (spec 39).

### Why "every tick based on real ticks" is non-negotiable here

The EA opens three positions with stops at the same price and targets at 1R,
2R and 3R. On a bar that spans both TP1 and the stop, cruder modelling picks
an order of events that can flip a setup from +0.33R to −1R. Open-price
modelling will overstate results substantially.

## 3. Split the history before you look at it

Decide the split **first**, then never optimise on the out-of-sample window.

```
|<--------- In-Sample 70% --------->|<--- Out-of-Sample 30% --->|
   optimise here                        touch once, at the end
```

With 6 years: roughly 4 years in-sample, 2 years out-of-sample.

## 4. Optimisation order (spec 34)

Never optimise everything at once — the parameter space is large enough that
a joint sweep finds noise. One phase at a time, carrying the winner forward:

| Phase | Parameters |
|---|---|
| 1. Session | `InpLondonStartHour`, `InpNewYorkStartHour`, `InpEntryWindowMinutes`, `InpTradeOverlapOnly` |
| 2. Liquidity | `InpSwingLookback`, `InpSweepMinPenATR`, `InpSweepMaxPenATR`, `InpSweepReclaimBars` |
| 3. ATR / volatility | `InpAtrPeriod`, `InpMinSLATR`, `InpMaxSLATR`, `InpSLBufferATR` |
| 4. Entry | `InpEntryMode`, `InpRetestMaxBars`, `InpRetestZoneATR`, `InpMinBodyATR` |
| 5. Volume profile | `InpVPBins`, `InpVPLookbackBars`, `InpValueAreaPercent`, `InpVPTouchATR` |
| 6. Risk | `InpRiskPercent`, `InpPositionsPerSetup`, `InpLotFitMode` |
| 7. Trade management | `InpBEMode`, `InpTimeStopBars`, `InpTP2R`, `InpTP3R` |

Then run out-of-sample **once**. If it fails, you do not get to re-optimise
and try again — that converts your out-of-sample window into in-sample data.

## 5. Filter ablation (spec 32)

```bash
python tools/make_ablation_sets.py --outdir sets --per-setup
```

Produces the full system, one file per filter disabled, a bare entry engine,
and each setup in isolation. Run every file over the same range and modelling.

For each filter compare **expectancy, profit factor and max drawdown**:

| Outcome | Reading |
|---|---|
| Removing it lowers expectancy | filter earns its place |
| Removing it changes little | filter is decoration — consider dropping it |
| Removing it raises net profit but also drawdown | it was suppressing risk, not returns |
| Removing it raises everything | the filter is actively harmful |

A prettier equity curve is not evidence a filter works. More filters means
fewer trades means a smaller sample means an easier curve to overfit.

## 6. Robustness (spec 33)

**Parameter perturbation.** Step each key parameter ±10 % and ±20 %:

| Parameter | Test values |
|---|---|
| `InpEmaSlow` = 200 | 180, 190, 200, 210, 220 |
| `InpAtrPeriod` = 14 | 10, 12, 14, 16, 20 |
| `InpMinBodyATR` = 0.60 | 0.45, 0.55, 0.60, 0.70, 0.80 |
| `InpSweepMinPenATR` = 0.08 | 0.05, 0.08, 0.12, 0.16 |

A system that collapses when 200 becomes 210 is fitted to noise. You want a
**plateau**, not a spike.

**Execution stress.** Re-run the best set with spread ×2 and ×3, and with
slippage raised. Gold spreads widen exactly at the session opens this EA
trades, so a system that only works at a 26-point spread will not survive.

**Walk-forward.** Rolling 12-month optimise → 3-month test, stepped forward
one quarter at a time. Consistency across windows matters more than the best
single window. A walk-forward efficiency below ~0.5 means the optimisation is
not generalising.

**Monte Carlo.** Take the trade list from `XAUM15_trades.csv`, shuffle the
sequence 10,000 times, and record the distribution of max drawdown and final
equity. The realised equity curve is one sample from that distribution — the
5th percentile is a fairer planning figure than the median.

## 7. Acceptance criteria (spec 39)

A configuration passes only if **all** of these hold:

- [ ] Max drawdown < 40 % (preferred < 35 %)
- [ ] Profit factor > 1.30
- [ ] Expectancy > 0 in R terms
- [ ] No single trade contributes an outsized share of net profit
- [ ] Out-of-sample still profitable
- [ ] Walk-forward consistent across windows
- [ ] Monte Carlo ruin risk acceptable at the 5th percentile
- [ ] Survives spread ×2
- [ ] Results hold on a second broker's history

Failing any one means the configuration is not ready, regardless of how good
the net profit looks.

## 8. Reading the EA's own output

`OnDeinit` prints the full statistics block: overall, by direction, by setup
(A/B/C reported separately per spec 16), by session, and the hour-of-day
table (spec 31). `XAUM15_trades.csv` in `MQL5/Files/` carries one row per
setup with entry, stop, targets, spread, ATR, VWAP, POC/VAH/VAL, the swept
liquidity level, sweep type, MSS and displacement flags, grade, R multiple,
MAE and MFE — enough to reconstruct why any trade was taken.

## 9. What these numbers are, and are not

- A **backtest** is a simulation on one broker's history with modelled spread.
- A **forward test** is a demo run on live data with real execution.
- **Expected performance** is a range inferred from both, with wide error bars.
- A **target** is what you would like to happen.

The 2 %/day figure in the specification is a target used to evaluate the
system statistically over a long sample. It is **not** a guarantee, not a
daily quota, and the EA is explicitly built to sit flat on days with no
qualifying setup. Any day, week or month can be negative.

---

## 10. Priority test: cross-asset validation of the trend zone

Everything in `docs/RESEARCH_FINDINGS.md` was measured on **gold only**, and
the zone boundaries were found on the full sample rather than a held-out
half. That makes cross-asset reproduction the single most informative test
remaining — and the one most likely to kill the system.

```bash
python tools/make_ablation_sets.py --outdir sets --per-setup
# then in Strategy Tester, load 10_crossasset_check.set and run it on:
#   XAGUSD   (silver  - same metals complex, different liquidity)
#   EURUSD   (FX      - unrelated market entirely)
```

Change **nothing** but the symbol. The zone boundaries, SMA period, stop
multiple and hold time stay exactly as they are.

| Result | Reading |
|---|---|
| Positive expectancy on both | the zone is a general effect; proceed to walk-forward |
| Positive on silver, flat on EURUSD | plausibly a metals/volatility effect; narrow the claim |
| Flat or negative on both | **fitted to gold.** Do not trade it |

Do not tune the zone to make another asset work. Re-fitting per market is how
a single overfit becomes three.

### Boundary sensitivity

`zone_*.set` steps the zone edges. A real effect degrades smoothly as the
boundary moves; a fitted one collapses the moment 1.08 becomes 1.40. Look for
a **plateau**, and treat a spike at exactly the published values as a warning
rather than a confirmation.

### Risk ladder

`risk_*.set` reproduces the 0.5 / 1.0 / 2.0 % comparison. The research
measured 28 % / 52 % / 84 % max drawdown across those three on identical
entry logic. Confirming that relationship on your data is a cheap check that
your equity accounting matches theirs.

## 11. Measure your spread before trusting any of it

```
Run the EA on a live $10 account for a month with InpEnableTrading = false.
It still samples spread. On deinit it writes XAUM15_spread_by_hour.csv.
```

The cost input is currently uncertain by a factor of three ($0.26 reported,
$0.4824 measured elsewhere, $0.7525 in Asian hours). At a 1.8×ATR stop that
is the difference between 0.013R and 0.037R per trade. Every backtest number
above is conditional on which of those is true, and no backtest can tell you.
