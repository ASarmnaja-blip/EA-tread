# Amendment 23 result — basket fails the unit-risk cost-stress gate

**Run date:** 2026-09-27  
**Section 10 verdict:** **FAIL FOR PROMOTION**  
**DD sizing:** **NOT RUN**, as required by sections 1, 6, 10, and 11 after
the unit-risk result failed.

The causal basket was positive at base Demo90 costs in both required windows,
but the 44-month result became negative at 1.5x cost. That is an explicit
section 10 failure. The recent 12-month strength does not repair the older
forward failure, and scaling it to a 35–40% DD would not create expectancy.

## 1. Frozen inputs and implementation

- Candidate universe: the declared 8,250 Amendment 14 cells, unchanged.
- Cache: `data/weekly_evolution_universe_v10_sp090_co140.pkl`; full data,
  engine-code, and cost-profile stamp matched before use. The run aborted if
  the cache was absent, mismatched, or rebuilt.
- Canonical M5 SHA-256:
  `613d5e7476deeaa3dc473371028adf9d4724720788b5f1d424e410556dfad158`.
- A trade's net R was assigned to its **exit/resolution calendar week**, per
  Claude clarification A. Every intervening no-trade week remained an explicit
  zero.
- Exact realised-order duplicates were collapsed before family, correlation,
  and weight constraints were applied.
- Pending orders born before a rebuild were not inherited. A member could act
  only on an order born in its frozen forward week and filled before the next
  boundary. Open positions carried their original member weight.
- The unit-risk admission replay enforced five open positions and a gross-risk
  cap. Gross risk included the geometric stop plus round-trip exit costs.
- No MT5 connection or order-sending path exists in the new module. No Demo or
  real order was sent, and `payoff_demo_autotrader.py` was not started.

The implementation is in `research/pilot/basket_dd.py`; its regression tests
are in `research/pilot/test_basket_dd.py`.

## 2. Audits

| Audit | Result |
|---|---:|
| Full-hash universe cache | PASS — 8,250/8,250 cells |
| Historical cutoff truncation: membership unchanged | PASS |
| Historical cutoff truncation: weights unchanged | PASS |
| Future-path mutation: causal calibration multiplier unchanged | PASS |
| Exit-week assignment and explicit zero weeks | PASS |
| Decay effective-sample-size test | PASS |
| Existing no-look-ahead, mutation-sensitivity, timestamp/resampling, Bid/Ask, ambiguous-bar, cost, grid, fast-resolver, and rollover suite | PASS — 40/40 |

The integration cutoff was 2025-01-10 22:15 UTC. Full versus physically
future-truncated data selected the same five tags and weights. Mutating the
post-cutoff path also left the pre-cutoff calibration value unchanged.

The raw basket run is `data/basket_dd_run.txt` (756,868 bytes), SHA-256
`e1bb98f096162c5eddda023e2103f36352abe61b288e32e7aab9983014bd2c40`.
The engine audit is `data/amendment23_mtf_audit.txt`, SHA-256
`c977c121eac90c2a04b80848b3dd0ef0cd28137a684acd0c94673f3e00fc350a`.

## 3. Unit-risk result — primary, reported before sizing

R below is portfolio unit risk, not USD and not a percent of account equity.
MTM DD is marked at every M5 close with simultaneous positions included.

| Window / cost | Net R | PF | Positive weeks | Realised DD R | MTM DD R | Worst week R | Worst month R | Loss streak | Zero weeks / total | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 44-month, base | +62.070 | 1.035 | 55.38% | -33.793 | -33.591 | -5.233 | -11.425 | 20 | 1 / 195 | 11,943 |
| 44-month, 1.5x cost | **-80.991** | 0.956 | 44.10% | -86.653 | -86.552 | -6.860 | -14.174 | 20 | 1 / 195 | 11,943 |
| Trailing 12m, base | +184.020 | 1.239 | 77.36% | -10.415 | -11.288 | -6.668 | -2.251 | 16 | 0 / 53 | 5,308 |
| Trailing 12m, 1.5x cost | +150.353 | 1.190 | 73.58% | -10.927 | -11.716 | -7.409 | -2.959 | 16 | 0 / 53 | 5,308 |
| Full walk-forward, base | +246.090 | 1.097 | 60.32% | -33.793 | -33.591 | -6.668 | -11.425 | 20 | 0 / 247 | 17,251 |
| Full walk-forward, 1.5x cost | +69.362 | 1.026 | 50.61% | -86.653 | -86.552 | -7.409 | -14.174 | 20 | 0 / 247 | 17,251 |

Window definitions were 2022-01-01 00:00 UTC to 2025-09-21 00:00 UTC,
2025-09-21 00:00 UTC to the canonical end at 2026-09-21 08:40 UTC, and the
combined interval. The first/last partial calendar week remains present. This
is why the partial split week can be zero in the first window but later become
non-zero in the combined window; it was not dropped.

## 4. Policy behaviour and Warning B

Claude's power warning occurred exactly as anticipated. The three-week
half-life produced `n_eff` 8.69456–8.69464 weeks, with the asymptote 8.69464.
The selector therefore ranked roughly 8,250 cells from only about nine
effective weekly observations.

Member turnover is defined as
`1 - intersection(previous,current) / max(previous_count,current_count,1)`.
Weight turnover is one half of the absolute weight change across the union.

| Window | Decision weeks | No basket | Member turnover | Weight turnover | Max concurrent | Slot rejects | Gross-risk rejects | Mean / max selected correlation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 44-month | 194 | 0 | 73.51% | 74.00% | 5 | 0 | 26 | 0.137 / 0.698 |
| Trailing 12m | 52 | 0 | 71.15% | 67.69% | 4 | 0 | 4 | 0.070 / 0.697 |
| Full | 246 | 0 | 73.01% | 72.66% | 5 | 0 | 30 | 0.123 / 0.698 |

All 246 forward rebuilds from 2022 formed at least three members, so the
more-than-half NO TRADE failure did not occur. Across the full window, member
weeks by family were: pullback 239, breakout 233, failed 226, vwap 187, sweep
175, and expansion 170. The complete weekly memberships, weights, member risk
contributions, binding caps, correlations, `n_eff`, and turnover are in the raw
run file.

The principal interpretation is not that the basket never worked. It is that
the forward edge was thin relative to transaction costs over the long regime
and extraordinarily unstable week to week. The newest year was strong enough
to make the full-period stress result positive, but section 10 deliberately
requires the 44-month and trailing windows to pass separately.

## 5. Same-week family-middle control

| Window / cost | Net R | PF | Positive weeks | MTM DD R | Trades |
|---|---:|---:|---:|---:|---:|
| 44-month, base | +4.402 | 1.007 | 43.59% | -19.150 | 5,516 |
| 44-month, 1.5x cost | -30.862 | 0.952 | 40.00% | -45.530 | 5,516 |
| Trailing 12m, base | +15.307 | 1.070 | 67.92% | -13.153 | 2,017 |
| Trailing 12m, 1.5x cost | +10.326 | 1.046 | 62.26% | -14.454 | 2,017 |
| Full, base | +19.710 | 1.023 | 48.99% | -19.150 | 7,533 |
| Full, 1.5x cost | -20.535 | 0.976 | 44.94% | -45.530 | 7,533 |

The top-ranked basket beat the family-middle control, particularly in the
latest year, but that diagnostic does not override the primary cost-stress
failure.

## 6. Finance and DD sizing reports

These are deliberately **NOT RUN**, not zero:

- rolling 52-week 37.5% calibration and the 35%/40% forward guards;
- diagnostic DD targets 30%, 35%, 40%, 45%, and 50%;
- USD 100 initial equity plus USD 100 monthly deposits;
- net USD, deposited USD, final equity, maximum cent lot, margin rejects, and
  stand-down dates.

Running or interpreting those after the negative 44-month unit-risk stress
result would violate Amendment 23's proof order. There were therefore no
sizing stand-downs to report. Leverage 1:2000 was not used to manufacture a
finance result.

## 7. Section 10 verdict

**FAIL FOR PROMOTION.** Specifically:

1. Both base-cost windows were positive: pass.
2. The trailing 12-month 1.5x-cost window was positive: pass.
3. The 44-month 1.5x-cost window was **-80.991 R**: fail.
4. Causal/cache/execution audits passed, zero weeks were retained, and the
   basket formed in more than half of forward weeks.
5. Because item 3 fails, DD sizing has no promotable interpretation and was
   not executed.

No frozen threshold or rule was changed after observing the result. Amendment
23 does not replace the current Demo policy and authorizes no order.
