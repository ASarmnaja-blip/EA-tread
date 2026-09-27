# Amendment 24 result — friction gate improves the corrected baseline but fails

**Run date:** 2026-09-27  
**Section 11 verdict:** **FAIL FOR PROMOTION**  
**Historical status:** **INFORMED BY AMENDMENT 23 — NOT BLIND**  
**DD sizing:** **NOT RUN** because unit risk failed section 11.

Amendment 24's gate materially reduced execution drag, widened the typical
stop, and improved every paired window relative to Amendment 23 on the same
state-correct engine. It still lost money in the 44-month development window at
both base and 1.5x cost. The full development period was also negative.

The separate state-fidelity correction proved material: Amendment 23 replayed
with the corrected selected-only forward state was much worse than its original
continuous-cell-thinned execution. This is not a look-ahead finding. The
candidate histories reproduced exactly; the forward opportunity stream changed
because hypothetical unselected-week positions no longer suppressed later
selected-week signals.

## 1. Inputs and implementation

- New module: `research/pilot/basket_gate.py`.
- Tests: `research/pilot/test_basket_gate.py`.
- New raw-opportunity cache:
  `data/amendment24_raw_opportunities_v1_sp090_co140.pkl`.
- Cache size: 523,450,014 bytes; SHA-256
  `bcde042029119a0d5fbddce33dd88b185d9974ba4bce789f1a75727bfde00ae9`.
- Raw output: `data/basket_gate_run.txt`, 13,467,986 bytes; SHA-256
  `1969f5fd10eb138eabef10ae803524a2a7856756bc8a64a59b8ac1bd284d9185`.
- Canonical data SHA-256:
  `613d5e7476deeaa3dc473371028adf9d4724720788b5f1d424e410556dfad158`.
- Universe: the unchanged 8,250 declared cells represented by 330 raw
  family/timeframe/entry streams and 25 stop/target planes per stream.
- Gate: prior fully closed M5 spread `sp[k-1]`; actual fill-bar `sp[k]` retained
  only for accounting.
- Base friction gate: at most 1/12 R; equivalent 1.5x friction at most 1/8 R.

No MT5 connection or order-sending path exists in the module. No Demo or real
order was sent and the autotrader was not started.

## 2. Section 10 audits — all passed before the result

| Audit | Result |
|---|---:|
| Old continuous-cell cache reproduction | PASS — 8,250/8,250 cells, zero mismatches |
| Order/fill/direction/exit sequence reproduction | PASS |
| Unselected hypothetical position does not block | PASS |
| Actual selected carried position still blocks | PASS |
| Weekend physical truncation: membership/weights unchanged | PASS |
| Future-column mutation: membership/weights unchanged | PASS |
| `sp[k]` mutation leaves gate unchanged but changes accounting | PASS |
| `sp[k-1]` threshold mutation flips gate | PASS |
| Full cache-hash mutation sensitivity | PASS |
| Existing no-look-ahead/timestamp/Bid-Ask/cost/resolver suite | PASS — 40/40 |

A DD multiplier was `NOT PERMITTED BEFORE UNIT-RISK PASS`, so no multiplier
value was generated or audited. This is the registered proof order, not a
missing result.

## 3. Amendment 24 unit-risk results first

The first window and all combined-history conclusions are development results
**informed by Amendment 23 and not blind confirmation**.

| Window / cost | Net R | Gross edge/trade | Cost share of gross | PF | Active weeks | Positive weeks | MTM DD R | Trades | Gate cancellations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 44-month, base | **-66.664** | +0.02688 R | 262.0% | 0.929 | 99.49% | 36.41% | -67.503 | 7,046 | 60.60% |
| 44-month, 1.5x | **-104.467** | +0.02688 R | 364.7% | 0.891 | 99.49% | 33.85% | -105.197 | 7,046 | 60.60% |
| Trailing 12m, base | +59.257 | +0.06846 R | 69.0% | 1.087 | 100.00% | 60.38% | -10.943 | 4,692 | 24.11% |
| Trailing 12m, 1.5x | +35.609 | +0.06846 R | 101.2% | 1.051 | 100.00% | 54.72% | -12.451 | 4,692 | 24.11% |
| Full, base | **-7.407** | +0.04350 R | 140.6% | 0.995 | 100.00% | 41.70% | -73.692 | 11,738 | 51.28% |
| Full, 1.5x | **-68.858** | +0.04350 R | 198.9% | 0.958 | 100.00% | 38.46% | -112.046 | 11,738 | 51.28% |

Cost share uses the unweighted per-trade ledger:

```text
gross_pre_cost_R = final_net_R + execution_friction_R + swap_R
cost_share = mean(execution friction at the stated cost multiple + swap)
             / mean(gross_pre_cost_R)
```

The trailing 12-month stress portfolio is positive despite a slightly negative
unweighted net edge per trade (-0.00084 R), because the frozen member weights
put more portfolio risk on the better trades. The table reports both the
portfolio result and the requested unweighted decomposition without conflating
them.

### Detailed unit metrics

| Window / cost | Realised DD R | Worst week R | Worst month R | Loss streak | Zero weeks |
|---|---:|---:|---:|---:|---:|
| 44-month, base | -67.511 | -5.125 | -8.761 | 15 | 1/195 |
| 44-month, 1.5x | -105.249 | -5.585 | -9.608 | 15 | 1/195 |
| Trailing 12m, base | -10.775 | -7.333 | -5.104 | 17 | 0/53 |
| Trailing 12m, 1.5x | -12.609 | -7.912 | -7.326 | 17 | 0/53 |
| Full, base | -73.675 | -7.333 | -8.761 | 17 | 0/247 |
| Full, 1.5x | -112.149 | -7.912 | -9.608 | 17 | 0/247 |

The partial split week remains explicit, explaining why it can be zero in the
44-month window and non-zero after the later days are present in the combined
window.

## 4. Per-trade cost ledger decomposition

Every admitted Amendment 24 and paired Amendment 23 trade is recorded in the
raw output with:

```text
tag, entry/exit UTC, frozen member weight, stop distance,
prior-bar gate friction R, fill-bar accounting friction R, swap R,
gross pre-cost R, base net R, and 1.5x-stress net R
```

The weighted window identity reconciles exactly:

| Window | Weighted gross R | Base execution R | Swap R | Base net R | 1.5x execution R | 1.5x net R |
|---|---:|---:|---:|---:|---:|---:|
| 44-month | +30.102 | 75.607 | 21.159 | -66.664 | 113.410 | -104.467 |
| Trailing 12m | +109.765 | 47.297 | 3.211 | +59.257 | 70.946 | +35.609 |
| Full | +139.868 | 122.904 | 24.370 | -7.407 | 184.356 | -68.858 |

The gate widened the median stop to $4.68 in the 44-month window and $6.00 in
the trailing year. Median fill-accounted execution friction fell to 0.0562 R
and 0.0442 R respectively. Nevertheless, the state-correct 44-month gross edge
was only 0.0269 R per trade, below both execution friction and swap.

## 5. Gate cancellations

| Window | Considered | Cancelled | Cancellation share | Largest cancellation groups |
|---|---:|---:|---:|---|
| 44-month | 18,007 | 10,913 | 60.60% | M5 8,893; breakout 3,488; sweep 2,611; stop 1.5 ATR 4,764 |
| Trailing 12m | 6,184 | 1,491 | 24.11% | all M5; stop 0.75 ATR 1,207; pullback 525; sweep 454 |
| Full | 24,191 | 12,404 | 51.28% | M5 10,384; breakout 3,526; sweep 3,065; stop 1.5 ATR 4,776 |

The raw output contains cancellations by calendar week, family, timeframe,
stop, and entry/expiry mode. Rejections were retained as zero opportunities;
they were not removed from weekly evidence.

## 6. Paired Amendment 23 baseline on the same corrected engine

This baseline uses Amendment 23 ranking and no friction gate, but the identical
raw-opportunity and selected-only state engine. Its gate cancellation share is
therefore 0% by definition.

| Window / cost | Net R | Gross edge/trade | Cost share of gross | Active weeks | Gate cancellations |
|---|---:|---:|---:|---:|---:|
| 44-month, base | -251.037 | +0.03754 R | 353.2% | 99.49% | 0% |
| 44-month, 1.5x | -405.092 | +0.03754 R | 511.1% | 99.49% | 0% |
| Trailing 12m, base | +43.657 | +0.06100 R | 97.6% | 100.00% | 0% |
| Trailing 12m, 1.5x | +7.204 | +0.06100 R | 143.2% | 100.00% | 0% |
| Full, base | -207.380 | +0.04476 R | 246.0% | 100.00% | 0% |
| Full, 1.5x | -397.888 | +0.04476 R | 356.8% | 100.00% | 0% |

Amendment 24 improved paired net R by:

| Window | Base improvement | 1.5x improvement |
|---|---:|---:|
| 44-month | +184.373 R | +300.625 R |
| Trailing 12m | +15.600 R | +28.404 R |
| Full | +199.973 R | +329.030 R |

The correction explains why this paired baseline differs from Amendment 23's
original reported +62.070 R base result in the 44-month window. Candidate
histories and weekend rankings reproduce; actual forward execution no longer
inherits the old continuously busy-thinned trade stream. The previously noted
fidelity issue was therefore materially important, although it was not a
future-data defect.

## 7. Same-week family-middle control

| Window | Base net R | 1.5x net R | Base / stress PF | Active weeks |
|---|---:|---:|---:|---:|
| 44-month | -41.679 | -59.000 | 0.901 / 0.863 | 99.49% |
| Trailing 12m | +0.344 | -3.752 | 1.002 / 0.982 | 100.00% |
| Full | -41.335 | -62.752 | 0.934 / 0.902 | 100.00% |

The control does not rescue the design.

## 8. Basket behaviour

| Window | Decision weeks | No basket | Member turnover | Weight turnover | Max concurrent | Cell-busy rejects | Slot rejects | Risk rejects |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 44-month | 194 | 0 | 73.92% | 74.02% | 5 | 17,604 | 1 | 47 |
| Trailing 12m | 52 | 0 | 70.77% | 69.36% | 5 | 7,546 | 0 | 2 |
| Full | 246 | 0 | 73.25% | 73.03% | 5 | 25,150 | 1 | 49 |

`n_eff` remained approximately 8.6946 weeks. All six declared families were
used. The complete weekly memberships, scores, weights, risk contributions,
binding caps, correlations, and turnover appear before the unit result in the
raw output.

## 9. DD sizing and finance

The following are **NOT RUN**, not zero:

- rolling 52-week 37.5% DD calibration;
- 35% soft and 40% hard guards;
- 30/35/37.5/40/45/50% DD diagnostics;
- USD 100 initial capital plus USD 100 monthly DCA;
- net USD, final equity, cent-lot, margin, liquidation, and stand-down reports.

Unit risk failed first, so producing these would violate the registered proof
order. Leverage was not used to manufacture a finance result.

## 10. Section 11 verdict

**FAIL FOR PROMOTION.** Specifically:

1. All causality, cache, reproduction, state, and execution audits passed.
2. The evidence floor passed: active weeks were 99.49% and 100%, and a basket
   formed in every required forward decision week.
3. The trailing 12-month window was positive at base and 1.5x cost.
4. The required 44-month window was negative at base (-66.664 R) and 1.5x cost
   (-104.467 R): failure.
5. The complete development period was also negative at both costs.
6. Therefore DD sizing was not run and there is no Demo or real-money promotion.

This result is a seen-history development failure, not blind confirmation. No
frozen threshold or rule was changed after observing it.
