# Account scaling, and what actually limits a 1000-unit account

Two questions get confused constantly. Separating them changes the answer.

1. Does a cent account behave differently from a USD account? — **No.**
2. Can a 1000-unit account trade gold at 0.5 % risk today? — **No, and a
   $1,000 USD account cannot either.**

---

## 1. The 100× scaling is exact

Claim under test: a 1000 USC cent account where the contract is 1 oz per lot
is equivalent to a $1,000 USD account where the contract is 100 oz per lot.

| | cent: 1000 USC | USD: $1,000 |
|---|---|---|
| 0.01 lot | 0.010 oz | 1.000 oz |
| value of a $1.00 gold move | 1.00 USC | 1.00 USD |
| spread $0.26 | 0.26 USC | 0.26 USD |
| stop of $20.43 | 20.43 USC | 20.43 USD |
| **spread as % of equity** | **0.0260 %** | **0.0260 %** |
| **stop as % of equity** | **2.0430 %** | **2.0430 %** |
| real money at stake | $10 | $1,000 |

Every ratio is identical to the last decimal. The account currency is a
display unit; what the strategy experiences is percentages, and those do not
change. **$10 of real money on a cent account buys the position granularity
of a $1,000 standard account.**

This corrects an earlier reading in this repository that treated cent
accounts as inherently disadvantaged. They are not.

## 2. The real constraint is minimum lot against volatility

Minimum lot is 0.01 on both account types and it does not scale with
anything. What it buys depends on the instrument's contract size and on how
far away the stop is — which is set by ATR.

At a 1.8 × ATR stop, on a 1000-unit account:

| ATR (M15) | Stop | Min-lot risk | Equity needed for 0.5 % |
|---|---|---|---|
| $11.35 (today) | $20.43 | **2.04 %** | 4,086 units |
| $8.00 (last 12m) | $14.40 | 1.44 % | 2,880 |
| $5.44 (2025) | $9.79 | 0.98 % | 1,958 |
| $2.58 (15-year mean) | $4.64 | 0.46 % | 929 |

The 15-year backtest ran at 0.5 % risk because the mean ATR over that period
was $2.58. **Gold's current ATR is 4.4× that mean**, so the identical rule on
the identical account now risks four times as much per trade.

The "$41 needed" figure from the research is a *volatility* statement, not a
cent-account statement. A $1,000 USD standard account needs $4,086 for the
same 0.5 % — the same multiple.

## 3. Why 2 % risk cannot be the answer

Modelled from the research's own reported statistics — 23.8 % win rate,
+0.142 R expectancy, implying an average winner of 3.80 R against a 1 R loser,
171 trades per year. The model reproduces the reported drawdowns closely:

| Risk | Model median DD | Research measured DD |
|---|---|---|
| 0.5 % | 31.7 % | 28.2 % |
| 1.0 % | 55.2 % | 51.5 % |
| 2.0 % | 83.1 % | 83.9 % |

Now run the EA's 35 % drawdown guard against those paths:

| Risk/trade | P(guard fires) 1 yr | 3 yr | 5 yr |
|---|---|---|---|
| 0.50 % | 0.1 % | 4.2 % | 10.2 % |
| 0.75 % | 3.4 % | 25.4 % | 42.9 % |
| 1.00 % | 14.4 % | 54.4 % | 76.1 % |
| **2.04 %** (min lot on 1000 units today) | **77.2 %** | **99.3 %** | **100 %** |

At the risk level the minimum lot forces, the drawdown guard is not a safety
net — it is a near-certain permanent shutdown, usually inside the first year.

Removing the guard does not rescue it. Without any guard, 2.04 % risk carries
a 1.6 % chance of losing 90 % of the account over five years and a 5th
percentile outcome of 0.31× starting equity. Certain halt, or a bad tail.
Neither is a plan.

**Only ~0.5 % risk is compatible with a 35 % drawdown stop.** That is the
number the research measured, and the guard and the risk setting have to be
chosen together.

## 4. What actually fits: the instrument, not the account

The metric that matters is **min-lot risk ÷ equity**. Gold is unusually
coarse because one ounce is expensive *and* its ATR is currently $11.

On a 1000-unit cent account, at a 1.8 × ATR stop:

| Instrument | ATR (M15) | Min-lot risk | % of equity | Lot for 0.5 % |
|---|---|---|---|---|
| XAUUSD (1 oz/lot) | 11.35 | 20.43 | **2.043 %** | 0.0024 — below minimum |
| XAGUSD (50 oz/lot) | 0.25 | 22.50 | **2.250 %** | 0.0022 — below minimum |
| XAUUSD at 15-y mean ATR | 2.58 | 4.64 | 0.464 % | 0.0108 |
| **EURUSD** (1000 u/lot) | 0.0006 | 1.08 | **0.108 %** | 0.0463 |
| **GBPUSD** (1000 u/lot) | 0.0009 | 1.62 | **0.162 %** | 0.0309 |
| **USDJPY** (1000 u/lot) | 0.09 | 1.08 | **0.108 %** | 0.0463 |

Majors are roughly **19× finer** than gold on the same account. On EURUSD the
target lot is 0.046 — comfortably *above* the minimum, so the account can
size properly instead of being forced to the floor.

These ATR figures are typical values, not measurements from your broker. Run
`tools/capital_check.py` to get the real table from live contract specs.

## 5. The convergence

The research's outstanding test is **cross-asset validation on EURUSD and
silver**: if the trend zone only exists on gold, it was fitted, not found.

That test is also the affordability answer. So:

- If the zone reproduces on EURUSD → it is more likely a real effect **and**
  it is tradeable at 0.5 % risk on 1000 units today.
- If it does not reproduce → the zone was gold overfit, and there is nothing
  to fund anyway.

**The test that could kill the system is the same test that could make it
affordable.** Run it before spending anything on capital.

## 6. Practical order of operations

```bash
# 1. What can this account actually trade?
python tools/capital_check.py --equity 1000 --risk 0.5

# 2. Pull history for whatever fits
python tools/export_mt5_data.py --symbol EURUSD --years 6

# 3. Cross-asset test: same rule, different symbol, change nothing else
python tools/make_ablation_sets.py --outdir sets
#    load 10_crossasset_check.set, run on EURUSD / GBPUSD / XAGUSD

# 4. See what gold does under a hard cap - read SIGNAL ACCOUNTING
#    load 11_gold_strict_cap.set on XAUUSD
```

## 7. What the EA now tells you

An EA that correctly refuses every setup looks exactly like a broken one.
Two reports close that gap:

- **Capital adequacy**, printed at startup: min-lot risk at the live ATR, the
  equity needed for the configured target, and a warning when setups will be
  rejected.
- **Signal accounting**, printed on deinit: how many valid signals were found,
  how many were traded, and how many were skipped because the minimum lot was
  too large. When more than half are skipped, the EA says so explicitly —
  that is a capital result, not a strategy result, and the measured edge was
  never given a chance to express itself.

---

### Modelling caveats

Sections 3 is a Monte Carlo fitted to two reported summary statistics (win
rate and expectancy) with an exponential winner distribution. It reproduces
the research's reported drawdowns, which is evidence the shape is roughly
right — it is not a substitute for the real trade sequence, and it assumes
trades are independent, which overlapping positions would violate. Treat the
probabilities as order-of-magnitude, not precise.

The ATR figures for non-gold instruments in section 4 are typical values used
to show the size of the gap. Your broker's contract sizes and current
volatility are what count: `tools/capital_check.py` reads both.
