# Why did 2022-01-01..2025-09-21 lose money? — diagnosis, 2026-09-26

The operator asked directly: did the loss happen because the tool/scope
genuinely could not read that market, or because gold simply was not rallying
the way it is now? Answered with two independent measurements, both run by
Claude using already-tested primitives (`core.resolve`, `core.atr`) or Codex's
fixed, pre-registered grid definitions (never his untested selection
algorithms).

## Measurement 1 — what the market itself did

`research/pilot/diagnose_2022_2025_loss.py`, against the full canonical XAUUSD
M5 history (2021-01-03 to present).

| era | price return (whole period) | weekly directional efficiency | random Long-Short drift gap (gross R) |
|---|---:|---:|---:|
| 2022 | −0.4% | 0.046 | −0.0762 |
| 2023 | +12.9% | 0.054 | +0.0339 |
| 2024 | +27.1% | 0.044 | +0.1239 |
| 2025 Jan-Sep | +40.4% | 0.047 | +0.0610 |
| **losing window, 2022-01..2025-09-21** | **+101.3%** | 0.047 | +0.0183 |
| **current trailing 12 months** | **+18.5%** | 0.047 | −0.0180 |

**Gold rallied more, not less, during the losing window than it has in the
trailing 12 months** — +101.3% over 44 months against +18.5% over the most
recent 12. Weekly directional efficiency (how cleanly price moved, versus
chopping in place) is essentially identical in both — 0.047 either way. At the
project's simplest shared reference geometry, the long-favouring drift was not
smaller in the losing window; if anything it was comparable or larger in three
of the four sub-years.

**This directly refutes the "gold was not trending like now" hypothesis** as a
sufficient explanation. Every one of 2023, 2024 and the first nine months of
2025 was individually a strongly positive, trending year for gold. Only 2022
alone was flat-to-down with a genuinely unfavourable (short-favouring) drift.

## Measurement 2 — does the fixed rule grid itself contain information, era by era

`research/pilot/diagnose_grid_by_era.py`, against Amendment 14's declared,
test-covered 8,250-cell grid (six setup families × five timeframes × five
stops × five targets × eleven entry modes), using the project's real Demo cost
model (spread 0.090 + commission 0.140 — not Codex's `cent260` exploration
profile). This does not use or trust any of Codex's weekly-selection code; it
asks whether the raw, pre-registered rules had any edge at all, before any
selection layer.

| era | cells with ≥15 trades | % of cells net-positive | median cell net R | mean cell net R | % of trades that were Long |
|---|---:|---:|---:|---:|---:|
| 2022 | 7,990 | 23.8% | −0.0620 | −0.0762 | 49.3% |
| 2023 | 8,205 | 24.8% | −0.0656 | −0.0847 | 49.7% |
| 2024 | 8,022 | 31.3% | −0.0481 | −0.0439 | 48.5% |
| 2025 Jan-Sep | 7,954 | 42.0% | −0.0264 | −0.0157 | 49.3% |
| **losing window, full** | 8,250 | 29.0% | −0.0446 | −0.0535 | 49.2% |
| **current trailing 12mo** | 7,702 | **59.1%** | **+0.0281** | **+0.0336** | 49.2% |

## Reading this together

1. **The long/short mix barely moves** — 48.5% to 49.7% Long in every single
   era. The grid is not becoming more aggressively long-biased now; it is
   taking essentially the same balanced mix of long and short trades
   throughout. So the change is not "the rules learned to bet with the trend
   now" — it is that the trades themselves, on both sides, started working
   better.
2. **Only 23.8% to 42.0% of cells were net-positive in every year of the
   losing window, worst in 2022-2023** — meaningfully below the roughly-50% a
   coin-flip-with-no-information would produce, before cost. That is a
   structural failure of the fixed rule set to extract anything from that
   market, not an absence of a trend for it to extract.
3. **The improvement from 2022 to now is a smooth, four-step climb** — 23.8%
   → 24.8% → 31.3% → 42.0% → 59.1% — not a sudden jump concentrated in one
   quarter. This is recorded as an observation, not yet an explanation: it is
   consistent with either a genuine multi-year regime change toward
   conditions these specific mechanical setups suit, or with the kind of slow
   drift a noisy process can produce over only five sequential yearly
   buckets. **This is NOT ASSESSED as to cause** — distinguishing those two
   needs more than four years of annual buckets and is not attempted here.

## Direct answer to the operator's question

**Closer to "the scope could not read that market" than to "gold was not
rallying."** Gold rallied hard in 2023, 2024 and the first three quarters of
2025 — more, in total, than in the trailing twelve months — and the fixed rule
grid still failed on 71 to 76% of its own declared cells in each of those
years. The one sub-year that was genuinely a harder market by the market's own
measurements was 2022 alone (flat price, short-favouring drift), and 2022 is
only about a quarter of the 44-month window, so it cannot be the primary
explanation for a loss spanning all 44 months.

What is not yet established is *why* the fixed rules' hit rate has been
climbing steadily for four years running into the present. That question is
open, and answering it would need more than the annual buckets used here.

## What this does and does not license

This is a diagnosis, not a promotion. It says nothing about whether Codex's
weekly-selection layer, or any specific cell, has a persistent edge — every
closure already on the record (Amendments 07, 09, 10, 11, 13: this family of
mechanical setups is "quieter than chance" when tested with proper
multiplicity correction on prior data) stands unchanged. It explains a number,
it does not clear a candidate.

## Status

Read-only against Codex's cached universe; no code of his was modified. One
side effect worth recording: inspecting the cache structure built a new one at
the project's real Demo cost model,
`data/weekly_evolution_universe_v10_sp090_co140.pkl`, which did not exist
before — the project's standard cost model has now been applied to this grid
at least once, closing part of the gap flagged in the previous status check.

No real-money order sent. No open position. NO TRADE.
