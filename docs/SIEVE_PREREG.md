# Five-layer sieve over every tool family — pre-registration (2026-09-30, before any feature is computed)

Operator 2026-09-30: "รันต่อในนี้เต็มระบบ" — run the whole sieve (frames 1–13 of the 2026-09-30 idea list) on every
tool family with the data on this machine. Descriptive research: the historical HOLD budget is spent
(ALPHA_LEDGER), so nothing here is confirmed by passing; survivors can only be nominated for a paper shadow record.
No order is placed by any code in `research/sieve/`.

## Data (frozen)
| scan | bars | span | DEV | CHECK |
|---|---|---|---|---|
| A | Dukascopy H1 mid (`engine.load()`) | 2003-05 .. 2026-08 | 2003-05 .. 2014-12 | C1 2015-01 .. 2020-12, C2 2021-01 .. 2026-08 |
| B | Exness M5 mid (`bars.load_bars`) resampled to M15 | 2021-01 .. 2026-09 | 2021-01 .. 2024-06 | 2024-07 .. 2026-09 |
| B2 | scan B restricted to bars with DXY / XAGUSD / US500 data (`data/fresh/*_M5.npz`) | 2023-09 .. 2026-09 | 2023-09 .. 2025-02 | 2025-03 .. 2026-09 |

## Features (layer 0; `research/sieve/features.py`)
Every feature is known at the close of bar t (entry at the open of t+1); time features describe the entry bar t+1,
which is known in advance. Leak check before any scan: every feature value at bars <= j must be identical when all
bars after j are replaced by garbage (3 cut points per scan).
- Indicators (continuous states): RSI14, RSI2, Stoch %K, CCI20, Williams %R, ROC10, MACD histogram/ATR, close minus
  SMA20/50/200 in ATR, SMA20 slope, EMA9-EMA21, Bollinger %b and width ratio, Keltner position, Donchian 20/55 position,
  ADX, +DI minus -DI, Aroon oscillator, Parabolic SAR side x distance, Supertrend side, Tenkan-Kijun, cloud position,
  daily VWAP distance, OBV z, Heikin Ashi signed run, candle body/upper wick/lower wick/range-to-ATR.
- Indicator events: the 31 `indicator_zoo.signals()` as +1 / -1 / 0.
- Quant: returns over 1/4/24/120/480 bars in ATR, z-score 20/100, efficiency ratio 24, lag-1 autocorrelation 24,
  variance ratio 4x24, distance to 52-week high/low, realised-vol ratio 24/240, ATR percentile (1 year), volume z.
- Levels: signed distance to the nearest $10/$50/$100, position in the prior day's and prior week's range, distance to
  the prior day high/low, classic pivot P/R1/S1, bar gap, daily gap, weekly gap.
- SMC: unfilled bull/bear FVG counts (20 bars) and distance to the nearest, swing structure state (fractal 2/2,
  confirmed 2 bars late), CHoCH event, prior-day-extreme sweep-and-reclaim, 20-bar sweep-and-reclaim.
- Volatility / WPWB: EWMA forecast ratio to the 52-week median, 13-week trend z, log forecast, NR7, inside day,
  bars since the last range expansion.
- Time (entry bar): hour of day (one flag per hour), day of week, month, turn of month (last trading day / first two),
  London AM fix (10:30 London) and PM fix (15:00 London) bar, New York cash open (09:30 NY) bar, first bar after the
  weekend. DST-aware (Europe/London, America/New_York).
- External (scan B, and scan A where covered): GVZ level z and 5-day change (2009+), US 2y nominal 5-day change (2016+),
  US 10y real 5-day change (2021+), CFTC managed-money net z at its release time (2022+), hours since the last USD HIGH
  release and its standardised surprise (PIT calendar, 2022+); B2 only: DXY, XAGUSD, US500 24-bar returns,
  gold-silver ratio z, gold-plus-DXY divergence z.
Missing coverage = NaN, never filled.

## Layer 1 (no test)
Scan B horizons below 1 hour are kept only if the round-trip cost is below 10 % of ATR(14) of that TF on the median
bar; a test needs >= 36 valid months in DEV (B2: >= 12) and >= 20 observations per month to count that month.

## Layer 2 — information scan (`research/sieve/scan.py`)
- Target: forward return from open(t+1) to open(t+1+h) divided by ATR(14) at t+1, winsorised at +/-5.
  Horizons: A {1, 4, 24, 120} H1 bars; B/B2 {4, 16, 96} M15 bars (1 h, 4 h, 1 d).
- Statistic: monthly Spearman IC (ranks within each month and subset), t = mean / sd x sqrt(months), p two-sided.
- Tests: every feature x horizon x mask, masks = ALL, 9 WPWB cells, 4 sessions (UTC 0-7, 7-12, 12-17, 17-24), and the
  top / bottom tercile of 20 pre-chosen state conditioners (RSI14, ADX, Bollinger width, ATR percentile, return 24,
  return 120, z100, Donchian 55 position, close-SMA200, efficiency ratio, variance ratio, prior-day-range position,
  WPWB vol ratio, WPWB trend z, volume z, distance to 52-week high, realised-vol ratio, MACD histogram, cloud position,
  DI difference). Full feature x feature pairs are NOT scanned; this is the declared limit.
- Survival: Benjamini-Hochberg q <= 0.05 over all valid DEV tests of that scan; then the same sign with t >= 1.5 in
  every CHECK period of that scan.

## Layer 3 — plausibility
(a) scan A: same sign in >= 3 of the 4 eras 2003-08, 2009-14, 2015-20, 2021-26; (b) price-only features: the IC on
XAGUSD (fresh M5 -> same TF, 2023-09+) must not be of opposite sign with t <= -1.5; (c) redundancy: keep the highest
DEV |t|, drop others on the same mask and horizon whose feature correlation exceeds 0.7; (d) cost: the CHECK-period
extreme-quintile (or flag) mean target minus the unconditional mean must exceed twice the round-trip cost in ATR
units; (e) mechanism: a one-line reason who pays; "none" is allowed but flagged and not promoted.

## Layer 4 — tradable test
Rule: enter at open(t+1) in the IC's direction when the feature is in its extreme quintile (thresholds from the
trailing 104 weeks only) or the flag is set, inside the mask; exits stop k ATR {1, 2} x the 9 exits of the
walk-forward test x hold {h, 2h}; one position at a time; 2 bp + swap. The exit is chosen on DEV only. Pass: net R > 0
on every CHECK period and better than hour-matched random entries (`engine.matched_control`) by t >= 2 over the
CHECK periods pooled. Survivors then enter one walk-forward selector (52-week LCB, top 1) against the
same-exit-config null.

## Layer 5
At most 4 survivors go to a paper SHADOW record (no alpha, like SELECTOR-SHADOW-1); spending reserve alpha on any of
them needs a separate registration and the operator's word.

## Honest priors
Across ~3,800 Foundry candidates, the zoo, the RR/TF sweeps and the walk-forward, no direction signal has survived.
The expected outcome of layer 2 is few or no survivors; that outcome is reported as a result, not a failure.
