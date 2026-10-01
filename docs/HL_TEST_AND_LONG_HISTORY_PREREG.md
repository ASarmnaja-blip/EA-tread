# Plan — (1) buy the failed test of the HL, exit at the HH (and its mirror), (2) trend vs holding on long histories
Written 2026-10-01 before any of these numbers is computed. Nothing here is run until the operator says go.

Operator: "เราเคยเปิดออเดอร์ตอน HL แล้ว ปิดตอน HH ไหม เงื่อนไขคือต้องเทส HL ไม่ผ่านก่อน ในฝั่ง LL ก็ไม่เหมือนกัน" and "เขียนแผนไว้ก่อน".
Not tested before: `research/hyp/structure_entries.py` (PULL_HL) bought the moment a new higher low was confirmed and exited by time or a
2 R target; it had no "test that fails" condition and never exited at the HH.

## Part 1 — HL test that fails -> long to the HH; LH test that fails -> short to the LL
**Swings.** Fractal pivots with k bars on each side (k = 2 primary, k = 3 secondary). A swing is known only k bars after its pivot bar.
**Structure at the close of bar i** (confirmed swings only):
- UP: last two swing highs rising (HH) and last two swing lows rising (HL), and the latest swing high came after the latest swing low
  (sequence HL -> HH; price is now pulling back from the HH).
- DOWN: the mirror (LH -> LL; price is now rallying from the LL).
**Trigger (long, in UP)** — the HL is tested and fails to break, on a closing basis:
- TOUCH: low(i) <= HL + 0.25 x ATR14(i), low(i) >= HL, close(i) > HL.
- WICK: low(i) < HL, close(i) > HL (a wick through the HL, close back above it).
- First test of that HL only (one trade per HL). Short = the mirror on the LH in DOWN (TOUCH: high >= LH - 0.25 ATR, high <= LH,
  close < LH; WICK: high > LH, close < LH).
**Entry** at the next bar's open; skipped if that open is already at or beyond the target or the stop.
**Stop** min(HL, low(i)) - 0.1 x ATR14 (short: max(LH, high(i)) + 0.1 x ATR14).
**Exits** (both reported):
- A, the operator's rule: take-profit at the HH (short: at the LL), the stop above, no time limit; stop first when both are touched in one bar.
- B, uncapped (memory feedback-no-caps): no take-profit; exit on a close below the latest confirmed swing low (short: above the latest
  swing high), the initial stop active.
**Timeframes** M15, M30, H1, H4, D1. **Samples** gold DEV 2009-15, gold CHECK 2016-26, silver 2010-26 (Candle Lab bars), 15 MT5 markets
(USDINR excluded; D1 / H4 / H1 / M30 2016-26, M15 2022-26), gold Dukascopy 2003-08 (H1 / H4 / D1). The rule is new, so all are fair samples.
**Costs** as Bundle 1 / 2 (gold 2.5 bp, silver 11.6 bp, broker spread + 1 bp, swaps). Net R in units of the stop distance.
**Control** (separates the trigger from merely being in a trend): for every real trade, a random bar of the SAME structure state (UP for
longs, DOWN for shorts) in the same market and TF, entered at the next open with the real trade's stop and target distances in ATR
multiples; 20 draws -> excess = real - control.
**Read-outs:** n, win rate, average win / loss, reward-to-risk (target distance / stop distance), net R, excess, 1 % risk finance.
**PASS** (per trigger x k x exit x TF, sides pooled and reported separately): gold CHECK net R > 0 and excess > 0 with weekly-cluster
bootstrap p < 0.05 after Holm over all 40 tests, AND gold DEV net R > 0, AND silver net R > 0, AND net R > 0 in >= 60 % of the clean
markets for that TF.

## Part 2 — option ค: trend following vs holding on long histories
**Data** (downloaded with the operator's approval, `data/macro/fred_long/manifest.json`, 3.2 MB): FRED daily closes NIKKEI225 (1949-),
NASDAQCOM (1971-), DEXJPUS, DEXUSUK, DEXSZUS, DEXUSAL, DEXCAUS, DEXSDUS (1971-), DEXSFUS (1980-), DEXMXUS (1993-), DEXUSEU (1999-),
DCOILWTICO (1986-), DCOILBRENTEU (1987-), DHHNGSP (1997-). Missing values dropped.
**Close-only adaptation (stated deviation):** open = previous close, high = max(open, close), low = min(open, close); channels and ATR from
these bars. Costs 2 bp round trip (FX, indices), 3 bp (oil, gas). Swap and FX carry NOT modelled (a known bias, reported).
**Systems** S1 / S2 / Chandelier, long-only and long + short, one position per market, 1 % risk per trade.
**Tests** exactly as `docs/TREND_VS_HOLD_PREREG.md`: (1) timing alpha against 2,000 random placements of the same trades; (2) buy-and-hold at
the leverage that matches the trend system's maximum drawdown, per market and for an equal-weight portfolio; (3) every >= 30 % decline
from a peak (e.g. Nikkei after 1989, NASDAQ 2000-02, oil 2008 / 2014-16 / 2020). Also per decade.
**PASS** as that pre-registration (pooled alpha > 0 with p < 0.05 and > 0 in >= 60 % of markets; drawdown-matched holding beaten in >= 60 %
of markets and at the portfolio level).
