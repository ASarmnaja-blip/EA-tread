# What the evidence changed

This file records why the EA's defaults are what they are. It summarises a
16-round research program run on 15 years of XAUUSD minute data
(5,250,134 bars, 43,353 trades evaluated) and states, rule by rule, what
survived and what did not.

Source: *บันทึกวิจัย nonnor*, 9 September 2026 — OANDA data via QuantConnect.

---

## The headline: the original entry model has no edge

The specification this EA was first written to is built on liquidity-sweep
reversal — price takes a level, closes back, structure shifts, you enter the
reversal. That family was tested at **n = 43,353** with minute-level exit
evaluation, and then subjected to an **inversion test**:

| | Expectancy |
|---|---|
| The setup | **−0.202 R** |
| The same setup with every rule inverted | **−0.189 R** |
| Sum | −0.391 R |
| Two round turns of spread | 0.344 R |

Both directions lose, and the two losses add up to roughly the spread paid
twice. That is the signature of a series with **no directional information
left in it**. Buying and selling the same moment both lose, by the cost of
trading. There is nothing to invert into a winner and nothing to filter into
one.

Win rates against the gambler's-ruin baseline `1/(1+R)` were below chance at
every target, most significantly at 0.5R (**E/se = −15.55**).

**Consequence:** `InpEnableSetupA = false` by default. The code remains for
reference and for anyone who wants to reproduce the result, but it is not a
default trading path.

## The Asian session was never tradeable

An Asian-hours effect looked strong on the first half of the sample
(+$0.60/day) and vanished on the second (−$0.004/day). The measured spread
in those hours is **$0.7525**, not the $0.26 assumed. Recomputed against the
real cost, the profit-to-cost ratio falls from a claimed 7.9× to **0.82×**.

**Consequence:** the Asian range is no longer the structural centre of the
system. `InpBlockAsianEntries` stays true, and Setup A — which was built on
the Asian range — is off.

## What survived: the trend zone

One rule passed every test that was put to it:

```
z = (Close - SMA200) / ATR        on M15
long when   +1.08 <= z <= +7.21
```

| Test | Value | Threshold | Result |
|---|---|---|---|
| Permutation test at 1.5R | p = 0.0005 | p < 0.01 | pass |
| Permutation test at 2.5R | p = 0.0005 | p < 0.01 | pass |
| In-zone vs out-of-zone (long) | t = +9.33 | \|t\| > 2.5 | pass |
| Drift-adjusted, long | t = +5.08 | t > 2.0 | pass |
| Drift-adjusted, short | t = +2.65 | t > 2.0 | pass |
| **Cross-asset (silver, EURUSD)** | **not run** | — | **pending** |

The drift adjustment matters: gold rose for fifteen years, so any long
strategy shows a profit. Subtracting the market's own drift minute by minute
and re-measuring is what separates the rule from the tide.

**This is not yet a validated edge.** The zone was found on the *full* gold
sample rather than a held-out half, and cross-asset confirmation has not been
run. If it does not reproduce in silver and EURUSD, it is gold overfit. Ship
it as the working hypothesis, not the answer.

**Consequence:** implemented as **Setup D**, enabled by default, with the
zone boundaries, the SMA period and both side toggles exposed as inputs so
the cross-asset test can be run directly from the Strategy Tester.

## Corrections after reading the notebook directly

The summary this file was first written from compressed several results in
ways that changed the design. Working from the notebook output itself:

**The exit is an 8R target, not the absence of one.** The target scan on zone
entries is monotone all the way out:

| Target | Long E | Net | Sharpe |
|---|---|---|---|
| 1.5R | +0.0569 | +0.0008 | 0.02 |
| 2.5R | +0.0891 | +0.0330 | 0.91 |
| 4.0R | +0.1455 | +0.0894 | 2.46 |
| 6.0R | +0.2351 | +0.1791 | 4.93 |
| **8.0R** | **+0.2873** | **+0.2312** | **6.36** |

The 30-hour hold (`max_hold=120` bars) is the backstop *behind* that target.
An earlier revision of this repository placed no target at all and left the
whole right tail uncaptured. Fixed: `EXIT_SINGLE_TARGET` at `InpTargetR = 8.0`.

**Expectancy is +0.2312R net at 8R**, not the 0.142R quoted earlier — that
figure is the ~4R row.

**The drift decomposition inverts the direction story.** Gold rose across the
entire sample, so raw long numbers contain that drift. Removing it minute by
minute:

| | Raw E | t | Skill (raw − drift) | t |
|---|---|---|---|---|
| longs in zone | +0.0569 | +4.45 | **−0.0494** | **−4.14** |
| longs outside | −0.0293 | −2.82 | −0.1276 | −13.13 |
| shorts in zone | +0.0102 | +0.75 | **+0.1092** | **+7.56** |
| shorts outside | −0.0388 | −3.58 | +0.0600 | +5.14 |
| longs in − out | +0.0862 | +5.24 | +0.0781 | +5.08 |
| shorts in − out | +0.0490 | +2.83 | +0.0492 | +2.65 |

The t = +5.08 and +2.65 quoted earlier are the **in-minus-out differentials**,
which show the zone doing real timing work on both sides. But in absolute
terms, **longs in the zone are negative once drift is removed**. Longs made
money because gold went up. The short side is where the measured skill sits.

Long-only is therefore a bet on gold continuing to trend up, *plus* the zone —
not the side with the cleaner evidence. The default stays long-only because
that is what the equity curves were built on, with the caveat recorded in
`Config.mqh` beside the toggles.

**The spread gap is worse than reported.** Measured OANDA quotes:

| Period | Spread | Cost at 1.8×ATR (15y mean ATR) | Net E at 8R |
|---|---|---|---|
| terminal quote | $0.26 | 0.056R | +0.2312R |
| 2012–2026 mean | $0.4824 | 0.104R | +0.1834R |
| **2023–2026 mean** | **$0.7525** | **0.162R** | **+0.1253R** |

That is a **46% haircut**, not the 17% quoted earlier. And it is not an
Asian-hours problem — the hourly table sits between $0.72 and $0.91 all day.

**Cost and affordability move in opposite directions.**

| Year | ATR | Cost in R | Min-lot risk on 1000 units |
|---|---|---|---|
| 2018 | $1.14 | 0.222R | 0.21% |
| 2021 | $2.13 | 0.128R | 0.38% |
| 2024 | $2.93 | 0.084R | 0.53% |
| 2025 | $5.44 | 0.051R | 0.98% |
| 2026 | $11.35 | **0.025R** | **2.04%** |

2026 is simultaneously the cheapest year to trade and the hardest to size on
a small account. These cannot both be optimised away.

**Partial exits are not settled.** Both configurations clear the DD < 35% bar:

| Config | CAGR | Max DD |
|---|---|---|
| no partial, 8R | **20.2%** | 28.2% |
| 50% at 1.5R, rest 8R | 12.3% | **24.5%** |

No-partial wins on CAGR; the partial version wins on Sharpe, which is why the
notebook's "best survivor" line names it. `EXIT_PARTIAL_RUNNER` supports it;
choose deliberately.

**Other figures corrected:** ~254 trades/year in the zone (not 171); the
equity curves span ~10 years against a buy-and-hold benchmark of 11.0% CAGR;
gold closed the sample at $4,437.88; and the base trade population the zone
filters has gross E of −0.0064R at 1.5R — the zone lifts a zero-edge
population, so it is a conditional filter, not a standalone signal.

## Simplicity won

The configuration that produced the best real equity curve was the plainest
one tested: **long in the zone, 1.8×ATR stop, hold 30 hours, no partial
close, 0.5% risk.** Every elaboration made it worse:

| Elaboration | Effect |
|---|---|
| Partial close at 1.5R | drawdown better by 3.7 points, **profit halved** |
| H4 direction filter | helped at every level, but only reached 1.44 of the 3.7 needed, and cut trade count in half |
| Trading the sweep direction (Osler) | z ≈ 0 at n = 34,137 |

The edge lives in a long right tail. Partial closes, tight time stops and
post-loss cooldowns all cut the tail off along with the noise.

**Consequences:**
- `InpExitMode = EXIT_TIME_STOP_ONLY` — Setup D places **no target**
- `InpTimeStopBars = 120` (30 hours), not 32
- `InpPositionsPerSetup = 1`, not 3
- `InpSLMode = SL_FIXED_ATR` at 1.8×ATR
- `InpCooldownBarsLoss = 0`
- `InpRiskPercent = 0.50`

The 1R/2R/3R ladder from the original specification is still available via
`InpExitMode = EXIT_TP_LADDER` with `InpPositionsPerSetup = 3`, but the
evidence is against it for this entry model.

## Position size, not strategy, controls drawdown

Same strategy, three risk settings, on the same 15 years:

| Risk/trade | Return p.a. | Max drawdown |
|---|---|---|
| 0.5 % | 20.2 % | 28.2 % |
| 1.0 % | 38.6 % | 51.5 % |
| 2.0 % | 64.1 % | 83.9 % |
| *buy and hold gold* | *11.0 %* | *~20 %* |

An 83.9% drawdown means the account was once worth one sixth of its peak.
Nothing in the entry logic changes between those rows.

**Fixed lot is strictly worse than percentage sizing**, and the difference
compounds exactly when it hurts. Through a 29-trade losing streak: floating
percentage leaves 550 USC, fixed 0.01 lot leaves **408 USC** — and the next
trade still risks the same absolute amount, which by then is 5% of what is
left. Percentage sizing shrinks with the account and mathematically cannot
reach zero; minimum lot cannot shrink at all.

**Consequence:** equity-based sizing was already the design and stays. The
EA never uses a fixed lot as its primary sizing.

## The numbers you must accept before running this

- Win rate **23.8 %**
- Longest losing streak actually observed: **19 trades**
- Theoretically expected longest streak: **~29 trades**
- Profit comes from a small number of large winners

An operator who cannot sit through 19 consecutive losses will switch the
system off in the middle of the drawdown it was designed to survive.

## Capital adequacy: the binding constraint

Minimum lot is 0.01, and it cannot go lower. On a cent account the contract
is **1 oz per lot**, so 0.01 lot = 0.01 oz and a $1.00 gold move is 1 USC.
1000 USC is **$10 of real money**.

**This is not a cent-account penalty.** Every ratio a strategy experiences —
spread as % of equity, stop as % of equity — is identical between a 1000 USC
cent account and a $1,000 USD standard account. The 100x scaling is exact;
see [ACCOUNT_SCALING.md](ACCOUNT_SCALING.md) for the proof. What binds is
that minimum lot does not scale with **volatility**, and gold's ATR is
currently 4.4x its 15-year mean. A $1,000 USD account faces the same 2.04%
floor and would need $4,086 for 0.5% risk — the same multiple.

| ATR (M15) | Stop at 1.8×ATR | Risk on 1000 USC | Equity needed for 0.5 % |
|---|---|---|---|
| $11.35 (current) | $20.43 | **2.04 %** | **$41** |
| $8.00 (last 12m) | $14.40 | 1.44 % | $29 |
| $5.44 (2025) | $9.79 | 0.98 % | $20 |
| $2.58 (15y mean) | $4.64 | 0.46 % | $9 |

The backtest ran at 0.5% because the 15-year mean ATR is $2.58. **Current
gold volatility is 4.4× that**, so the same rule on the same account now
risks four times as much per trade.

The EA prints a **capital adequacy report** on every init showing the
minimum-lot risk at the live ATR, the equity needed for the configured
target, and a warning when setups will be rejected — and a **signal
accounting** block on deinit showing how many valid signals were skipped for
being unaffordable, so a capital constraint is never mistaken for a strategy
result.

The instrument matters more than the account. On the same 1000-unit account
the minimum lot floors gold near 2% per trade but EURUSD near 0.11% — about
19x finer, and comfortably above the minimum so the account can size
properly. `tools/capital_check.py` reads live contract specs and ranks every
symbol your broker offers by how well it fits.

## The daily loss limit conflicts with this system

At 2.04% risk per trade, a −2.5% daily loss limit halts trading after **1.2
losses**. A system with a 23.8% win rate and a 19-trade losing streak cannot
operate under that rule: it would be stopped out on most days, and the days
it skips are indistinguishable from the days it needs.

`InpUseDailyLimits` now switches both daily rules off as a pair. The init
report warns when the limit is reachable in under three losses. This is a
genuine conflict between the original specification and the measured
character of the surviving edge — it is the operator's call, not a bug.

## The open cost question

| Source | Spread |
|---|---|
| Reported from the terminal | $0.26 |
| OANDA data, same period, average | $0.4824 |
| OANDA data, Asian hours | $0.7525 |

Nearly a three-fold spread. At a 1.8×ATR stop that moves cost per trade from
0.013R to 0.037R and expectancy from 0.142R to about 0.118R — a 17% haircut,
survivable but material.

**No backtest can settle this.** `SpreadMonitor.mqh` samples the live spread
once a second, buckets it by broker hour, prints the table on deinit and
writes `XAUM15_spread_by_hour.csv`. Run it on the $10 account for a month
and the question is answered with your broker's real numbers.

## Method that is worth keeping

Independent of any strategy, these are reusable:

- **Calibrate the measuring instrument first.** Run it on random data where
  the true answer is known to be `1/(1+R)` exactly. This caught three bugs
  that were about to ship, including a look-ahead error that produced a fake
  z = 4.56.
- **Block bootstrap nulls** (12-bar blocks) preserve candle shape and
  volatility while destroying sequence — they answer whether *order* matters.
- **Circular-shift nulls** for condition sweeps, because trades close in time
  share price paths and a naive shuffle manufactures significance (one p-value
  moved from 0.0075 to 0.31 when this was fixed).
- **Subtract market drift** before crediting a long-only rule on a
  fifteen-year uptrend.
- **Write the prediction and the kill condition before the run**, and print
  the multiple-comparison ceiling `√(2·ln k)` under every table.
- **Minute-level exit evaluation.** M15 bars are too coarse: they miss stops
  that were actually hit, inflating results by +0.06R at 1.5R and +0.20R at 3R.

The EA's own reporting reflects the last point: `docs/BACKTEST.md` requires
*every tick based on real ticks* for the same reason.

---

## Status of each setup in the code

| Setup | Default | Evidence |
|---|---|---|
| **D — Trend zone** | **on** | survived every test run; cross-asset validation pending |
| A — AMD liquidity reversal | off | tested at n = 43,353, no edge; inversion test conclusive |
| B — Volume profile continuation | off | never tested; the VP/VWAP machinery it depends on added nothing |
| C — Opening range expansion | off | never tested |

Setups A, B and C remain in the codebase because turning a hypothesis off is
different from deleting the ability to re-test it. Each has its own enable
flag and its own statistics bucket.
