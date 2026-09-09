# Pine Script

| File | What it is |
|---|---|
| `Dobby_3Leg_Strategy.pine` | The Dobby EMA 9/21 cross with 3-leg management, converted from an indicator to a `strategy()` so it produces real fills |

---

## Before you run it

This exact system — EMA 9/21 cross plus a higher-timeframe direction filter —
is **round 01 of the research log**, and it was cut: z between 0.06 and 0.29
at n = 66–114, with all four direction variants turning green at once, which
cannot happen if the signal carries information.

Converting it to a strategy is still worth doing, because n = 66–114 is far
too small to conclude anything either way. A strategy run over years of bars
gives the sample the original test lacked. Treat the output as the real test,
not as a confirmation.

## What was wrong in the indicator

**1. Break-even had no spread, so every BE exit lost money.**

```pine
activeSLPrice := entryPrice      // 4 places
```

A long fills at the ask and exits at the bid. A stop left exactly at the
signal price returns **minus one spread** per leg — two open legs at BE means
−0.52 cent per trade, invisible in the tally. Fixed:

```pine
beLevel := up ? entryPrice + spreadPrice : entryPrice - spreadPrice
```

**2. The BE trigger tested the wrong variable, so fixing (1) alone changes nothing.**

```pine
if tp1Hit and fromP >= entryPrice and toP <= entryPrice
```

It compares against `entryPrice`, never against `activeSLPrice`. The moved
stop was decorative — the trade still closed at the raw entry. The strategy
now passes the real level into `strategy.exit(stop=)`.

**3. No spread was charged anywhere, on any leg.**

Profits were measured from the signal close, so every leg's win was overstated
by a spread and every loss understated by one — 0.78 cent per signal across
three legs. Now each leg is its own entry and exit and pays its own spread via
commission: **3 legs = 3 spreads per signal.**

**4. Risk was unbounded.**

`lastSwingLow` can be hundreds of bars old:

| Swing distance | 3-leg loss | % of a 1000-cent account |
|---|---|---|
| $2 | 6 cent | 0.6 % |
| $10 | 30 cent | 3.0 % |
| $50 | 150 cent | **15.0 %** |

`MinRiskATR` / `MaxRiskATR` now **skip** those setups rather than take them at
any size. The dashboard counts skips so you can see how often it fires.

**5. `waitForClose` defaulted to false**, which repaints the higher-timeframe
MA: historical signals were not the signals you would have seen live. Default
flipped to true, and the trend EMA/ATR now read `[1]`.

**6. "Win Rate" was the TP1 hit rate.** BE exits counted as neither win nor
loss, so wins + losses did not equal signals. Leg outcomes now come from real
closed fills with commission included.

**7. "ขาดทุนสูงสุด" was the largest single loss, not drawdown.** Kept, and a
real `Max Drawdown` row added beside it.

## Money model

| | |
|---|---|
| `initial_capital` | 1000 (cents) |
| qty per leg | `centPerPrice1At001Lot × lotSize/0.01` → 1 by default |
| so a 1.00 price move | = 1 cent per leg, as in the original |
| commission | `cash_per_contract`, 0.13 per order → **0.26 round trip per leg** |

**One wart:** Pine needs `commission_value` as a header constant, so it cannot
read the `Spread` input. If you change the spread, change the commission in
the `strategy()` header to half of it. The dashboard prints the cost per
signal so a mismatch is visible.

## Limitation versus the indicator

The indicator walked 1-minute bars inside each signal bar. A Pine strategy
cannot: it resolves stops and targets at chart-bar granularity, and when one
bar could hit both it assumes the worse. **Expect this build to report worse
numbers than the indicator on the same chart.** That direction is the safe
one — the indicator was flattering itself.

For a closer comparison, run the strategy on a 1-minute chart with the MA
timeframe set to 5 or 15.

## Reading the result

Judge it on **Profit Factor and Max Drawdown**, both on the dashboard, not on
net profit. The bar the earlier work set: PF > 1.30, max DD < 35 %, and a
result that does not depend on one or two outsized trades.

If `Skipped (risk cap)` is a large share of signals, the risk bounds are doing
the work rather than the entry — widen them and re-read, or accept that the
setup is mostly untradeable at this account size.
