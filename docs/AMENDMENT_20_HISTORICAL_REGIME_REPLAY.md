# Amendment 20 — Historical regime replay

**Run 2026-09-22.**

## Question

If the Current Edge procedure had been available from the first continuous
broker history, which arm would it have selected in each era, and did that
selection make money in the following era?

This is a historical persistence audit, not a new search and not an
authorisation to change the Demo autotrader.

## Fixed procedure

The usable continuous XAUUSD M5 series begins on 2021-01-03.  At every 1
January from 2022 onward, the replay:

1. uses only fully closed M5 outcomes before that date;
2. applies the already-defined Amendment 19 90-day health gate to its fixed 48
   arms (24 event families times FOLLOW and independently resolved FLIP);
3. picks the highest shrunken-score READY arm; and
4. trades that one fixed arm, with no parameter changes, from that date until
   the next 1 January (or the last available bar).

The signal geometry is the frozen Current Edge geometry: event on M15, entry at
the next M5 open, 1.5 M15-ATR stop, 1R target, 72 M5-bar maximum hold, and one
position at a time *within the selected arm*.  This is an annual expanding
walk-forward replay, not the current Wednesday-observation / weekend-rebuild
cadence.

All rows use the active Demo raw-account model: a 90-point (`0.090`) minimum
spread on the 3-decimal XAUUSD price, recorded hourly spread when wider, `0.140`
round-turn commission, `0.033` round-turn slippage, and the existing swap
calculation.  The Standard 260-point cost model is disabled for this run.

## Anti-look-ahead boundary

For a selection at date `T`, the engine passes `resolved_through` as the final
M5 bar closed before `T`.  Any event whose 72-bar exit path cannot be fully
resolved by then is excluded.  The 30/60/90 day windows and the weighted score
are anchored at `T`; no event, price path, spread, or exit from the forward year
is available to the selector.  Forward results are resolved only after the
selection is fixed.

## Result

History available at the run was 372,614 M5 bars, from 2021-01-03 through
2026-09-21.  There was no READY arm on 2022-01-01, so the correct action that
year was no trade.

| forward period | arm selected from prior history | forward trades | net R | mean R | PF | max DD R |
|---|---|---:|---:|---:|---:|---:|
| 2022 | no READY arm | 0 | — | — | — | — |
| 2023 | `post_news_chase / FOLLOW` | 156 | -10.532 | -0.0675 | 0.868 | -17.997 |
| 2024 | `VWAP reversion 2.5sd / FLIP` | 220 | -22.938 | -0.1043 | 0.805 | -26.032 |
| 2025 | `breakout_into_level / FLIP` | 130 | -16.637 | -0.1280 | 0.772 | -23.962 |
| 2026 to 21 Sep | `pullback to EMA20 / FOLLOW` | 746 | +3.830 | +0.0051 | 1.011 | -29.678 |
| combined forward-only sequence | annual selections above | 1,252 | **-46.277** | **-0.0370** | **0.927** | **-72.899** |

The leading tool changed in every selection year.  Three full forward years
lost after passing their then-current gate.  The only positive forward segment
is 2026 so far, and its +0.0051 R/trade and PF 1.011 are too thin to establish
durability.  Therefore the tactical Current Edge scanner may describe what is
currently working, but this replay provides **no evidence that a recent winner
will survive the next regime**.

## Reproduction

```powershell
$env:PYTHONIOENCODING='utf-8'
python research/pilot/historical_regime_walkforward.py
```

The script fetches the pre-CSV 2021--2023 portion from MT5 in annual chunks and
combines it with `data/XAUUSD_M5.csv`.  It is read-only: it cannot place,
modify, or close any MT5 order.
