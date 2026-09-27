# Amendment 26 result — causal fill-time chain and contamination re-measurement

**Run date:** 2026-09-27

**Audit verdict:** **ALL PASS**

**Causality verdict:** **LEGACY LOOK-AHEAD CONFIRMED; CAUSAL CHAIN PASSED**

**Orders/autotrader/PR:** none; `payoff_demo_autotrader.py` was not started,
stopped, or modified.

All results below are **CONTAMINATION RE-MEASUREMENT — DEVELOPMENT DATA —
NOT BLIND**. They do not confirm a strategy for future trading.

## 1. Causality verdict and contamination size

The old chain processed potential fills in signal order. With limit orders,
that let an earlier signal's later fill block a later signal that had already
filled while the cell was flat. The decision therefore depended on a future
fill.

Across all 8,250 cells and the whole canonical history, the independent
cross-check found:

| Measure | Codex | Claude | Difference |
|---|---:|---:|---:|
| Rejected fill occurred before blocker entered | **3,344,875** | 3,344,875 | **0** |
| Mean gross R | **-0.330654** | -0.3307 | rounding only |
| Mean net R, excluding swap as predeclared | **-0.402148** | -0.4021 | rounding only |
| Net win rate | **32.009%** | 32.0% | rounding only |

This is the contamination mechanism: the legacy chain disproportionately
removed losers using knowledge that another pending order would fill later.
It is not a causal re-signal filter.

## 2. Audit gate

Every Section 8 audit printed before any policy result. All passed:

- the future-fill mutation made the unchanged legacy chain fail and the causal
  chain pass;
- the fill-time batch chain matched the event-level streaming oracle;
- a second independent synthetic price-stream oracle received no future fill
  bar and made the same decision about the earlier fill after later prices
  were mutated;
- prefix/future mutation, permutation, same-bar FIFO, entry/exit-bar busy,
  expiry, gap, and never-filled boundaries passed;
- all market-entry cells were identical between chains; this included all 750
  frozen-A21 market-entry cells;
- A23 and A24 cutoff membership, weights, and multiplier were invariant to
  truncation and future mutation;
- A24's selected/actual ledger separation and `sp[k-1]` gate tests passed;
- A23 and A24 reproduced their registered legacy references exactly;
- the existing A24 slow integration passed with 8,250/8,250 histories and no
  reproduction mismatch;
- the Amendment 26 fast suite passed 5/5, basket fast tests passed 7/7, and the
  existing MTF suite passed 40/40; and
- both new caches passed full-hash and readback validation.

The historical streaming comparison remains an event-level oracle and is
structurally related to the batch sorter. The added price-stream oracle is the
independent check: it discovers fills one bar at a time without receiving a
future fill timestamp. Its scope is synthetic boundary coverage rather than a
second full 47-million-signal implementation. This limitation is explicit.

## 3. Amendment 21 provenance and same-data comparison

The original +248.785 R / 1,757-trade A21 input snapshot is **PUBLISHED
REFERENCE NOT REPRODUCIBLE** from its original source. At commit `a67cca7`, the
runner fetched live MT5 plus CSV data; the canonical NPZ did not yet exist, and
MT5 can revise historical bars. The later `weekly_evolution_universe_v2.pkl`
is not proof of the exact input used by that run.

For the clean chain measurement, Amendment 26 rebuilt both legacy and causal
universes from the **same canonical bars**, using the frozen `a67cca7` signal,
execution, cost, rollover, and A21 weekly-selection rules. Only cell-chain
ordering differs.

The canonical legacy rerun happens to reproduce the published aggregate
numerically—1,757 trades and +248.785287 R—but that numerical agreement does
not recover or prove identity of the unavailable original bar snapshot.

| Window | Chain | Trades | Net R | PF | Sequence DD R | Active weeks |
|---|---|---:|---:|---:|---:|---:|
| 44 months | Legacy | 1,101 | +118.238 | 1.176 | -46.198 | 92.78% |
| 44 months | Causal | 1,072 | +94.711 | 1.163 | -47.444 | 88.66% |
| Trailing 12m | Legacy | 381 | +122.783 | 1.661 | -9.666 | 88.46% |
| Trailing 12m | Causal | 462 | +169.829 | 1.928 | -9.672 | 90.38% |
| 2022 onward | Legacy | 1,482 | +241.020 | 1.281 | -46.198 | 91.87% |
| 2022 onward | Causal | 1,534 | +264.540 | 1.345 | -47.444 | 89.02% |
| Full available | Legacy | 1,757 | +248.785 | 1.242 | -46.198 | 92.76% |
| Full available | Causal | 1,765 | +248.225 | 1.272 | -73.806 | 89.66% |

The full-available net difference is only -0.560 R, but the era distribution
and drawdown change materially: causal performance is weaker in the earlier
history and stronger after the 2025 split. Amendment 21 remains an exploratory
single-champion baseline, not a promotion result.

## 4. Amendment 23 — old versus causal

The registered A23 legacy result reproduced exactly. Replacing only its
per-cell chain removes the apparent basket edge.

| Window / cost | Legacy net R | Causal net R | Difference | Legacy / causal trades | Causal PF | Causal MTM DD R |
|---|---:|---:|---:|---:|---:|---:|
| 44 months, base | +62.070 | **-121.836** | -183.906 | 11,943 / 7,882 | 0.879 | -122.553 |
| 44 months, 1.5x | -80.991 | **-175.016** | -94.024 | 11,943 / 7,882 | 0.833 | -175.219 |
| Trailing 12m, base | +184.020 | +5.342 | -178.679 | 5,308 / 4,339 | 1.009 | -17.958 |
| Trailing 12m, 1.5x | +150.353 | **-13.471** | -163.825 | 5,308 / 4,339 | 0.977 | -29.413 |
| Full, base | +246.090 | **-116.494** | -362.584 | 17,251 / 12,221 | 0.927 | -130.564 |
| Full, 1.5x | +69.362 | **-188.487** | -257.849 | 17,251 / 12,221 | 0.885 | -192.113 |

Per-trade-ledger reconciliation:

| Chain / window | Gross R | Execution R | Swap R | Base net R | 1.5x net R |
|---|---:|---:|---:|---:|---:|
| Legacy, 44m | 386.078 | 286.122 | 37.885 | +62.070 | -80.991 |
| Legacy, trailing | 255.858 | 67.334 | 4.504 | +184.020 | +150.353 |
| Legacy, full | 641.936 | 353.456 | 42.389 | +246.090 | +69.362 |
| Causal, 44m | 7.587 | 106.360 | 23.063 | -121.836 | -175.016 |
| Causal, trailing | 46.566 | 37.626 | 3.598 | +5.342 | -13.471 |
| Causal, full | 54.153 | 143.986 | 26.661 | -116.494 | -188.487 |

The equations reconcile exactly:

```text
base net = gross - execution - swap
1.5x net = gross - 1.5 * execution - swap
```

**Original Section 10 verdict:** FAIL, because legacy 44-month stress was
negative.

**Causal Section 10 verdict:** **FAIL UNIT RISK**; 44-month base and stress are
negative, and trailing stress is negative. DD sizing was not run.

## 5. Amendment 24 — old versus causal

The registered A24 result and admitted-order reference reproduced exactly.
Its forward execution was already causal; this comparison corrects its
candidate-history ordering, which changes weekly evidence, membership, and
weights.

| Window / cost | Legacy net R | Causal net R | Difference | Legacy / causal trades | Causal PF | Causal MTM DD R |
|---|---:|---:|---:|---:|---:|---:|
| 44 months, base | -66.664 | **-80.397** | -13.733 | 7,046 / 5,855 | 0.893 | -80.583 |
| 44 months, 1.5x | -104.467 | **-109.119** | -4.652 | 7,046 / 5,855 | 0.859 | -109.283 |
| Trailing 12m, base | +59.257 | +31.643 | -27.614 | 4,692 / 3,627 | 1.066 | -11.293 |
| Trailing 12m, 1.5x | +35.609 | +18.000 | -17.608 | 4,692 / 3,627 | 1.037 | -12.873 |
| Full, base | -7.407 | **-48.754** | -41.347 | 11,738 / 9,482 | 0.960 | -89.193 |
| Full, 1.5x | -68.858 | **-91.119** | -22.261 | 11,738 / 9,482 | 0.928 | -119.403 |

Cost-ledger decomposition:

| Chain / window | Gross R | Base execution R | Swap R | Base net R | 1.5x net R |
|---|---:|---:|---:|---:|---:|
| Legacy, 44m | +30.102 | 75.607 | 21.159 | -66.664 | -104.467 |
| Legacy, trailing | +109.765 | 47.297 | 3.211 | +59.257 | +35.609 |
| Legacy, full | +139.868 | 122.904 | 24.370 | -7.407 | -68.858 |
| Causal, 44m | **-5.718** | 57.445 | 17.234 | -80.397 | -109.119 |
| Causal, trailing | +61.280 | 27.286 | 2.351 | +31.643 | +18.000 |
| Causal, full | +55.562 | 84.731 | 19.585 | -48.754 | -91.119 |

Causal active-week coverage is 99.49% in the 44-month window and 100% in the
trailing and full windows, so this failure is not manufactured by idleness.
Cost share of gross is `NOT ASSESSED` for causal 44 months because aggregate
gross edge is negative.

**Original Section 11 verdict:** FAIL UNIT RISK.

**Causal Section 11 verdict:** **FAIL UNIT RISK**; the required 44-month base
and stress results remain negative. DD sizing was not run.

## 6. Interpretation

The causal correction does not merely lower the number of trades. It changes
which candidate evidence is available at every Weekend Rebuild and therefore
changes membership and weights. A23's apparently positive base-cost basket was
largely dependent on the contaminated chain. A24's cost/R gate remains useful
as a cost-control mechanism, but it does not create positive full-period
expectancy after the candidate chain is corrected.

No corrected basket passes its own unit-risk gate. Therefore the 35–40% DD
sizing, leverage analysis, DCA/finance projections, and 30/35/37.5/40/45/50%
diagnostics are **NOT RUN**, not zero.

Amendment 26 nominates no policy for the 26-week forward-confirmation clock.
A new reviewed amendment is required before that clock can start.

## 7. Contaminated — not re-measured

The following remain explicitly **CONTAMINATED — NOT RE-MEASURED**:

- Amendment 14's published grid statistics;
- the Amendment 15/16 walk-forward;
- `compound_bar_replay.py`; and
- Claude's era and quarterly grid diagnoses.

They must not be treated as clean evidence in a future Weekend Rebuild.

## 8. Artifacts

- Implementation: `research/pilot/causal_chain.py`, SHA-256
  `90F3EB5EFB1A7B77B0086B6C24E47CC0B6370A9CF7374E4CF7B92D18359FA129`.
- Tests: `research/pilot/test_causal_chain.py`, SHA-256
  `9A4C18449C922D387F8DBA6DA40BEBF191AC7CF8E493CAEAD296F478B549AD01`.
- Raw output: `data/causal_chain_run.txt`, 18,749 bytes, SHA-256
  `E8CC7DACDA2ABBA1D5B9498EF666C05C530D0965F8213770210A5ABDEAE32313`.
- Machine-readable summary: `data/causal_chain_summary.json`, 44,416 bytes,
  SHA-256
  `09AF419E7F711880FEC1D5F0D79676103EE2DAECF913DA0FA93AB201449681B5`.
- Current-engine causal universe cache:
  `data/causal_filltime_universe_v1_sp090_co140.pkl`, SHA-256
  `66F2988E12A52FD1418E6F1958B3C14BB5FB5E405EA2889E0FF38AA5EC959A69`.
- Frozen-A21 paired cache:
  `data/causal_filltime_a21_a67cca7_v2.pkl`, SHA-256
  `4455B0626BC0FEEB7DC6B71004BF04527C09E0032099742B890C38C1178567BB`.

No Demo or real order was sent. No autotrader process or policy was changed.
No PR was opened and no commit was made by Codex.
