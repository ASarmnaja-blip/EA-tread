# D1 short-term trend basket — confirmation pre-registration (2026-10-01, after the scale-and-flip exploration, before the confirmation runs)

Exploration (research/hyp/explore_scale.py, data/hyp_explore_scale*.log) found daily trend / breakout signals (displacement, Bollinger, Donchian,
Keltner, MACD / EMA cross, CCI, turn of month ...) traded FOLLOW with a 1 ATR stop and a 5-day hold beating same-direction random timing on
gold 2016-26 and silver. That finding used the CHECK period and silver to look, so it is not evidence. This file fixes a confirmation that
selects only on gold DEV and is judged on markets never used for selection.

## Basket (selection on gold DEV 2004-15 only)
Every D1 signal x rule kept by the explore_scale DEV rule (direction and k as chosen there on DEV; hold = 5 x k D1 bars), equal weight: each
market's basket return per week = mean of the weekly R of its member rules (one position at a time per rule). Members are fixed now as the D1
rows of data/hyp/explore_scale.csv with rule != "drop" (the file's sha256 is recorded in the ledger entry of the run).

## Confirmation markets (never used for selection)
MT5 (Exness, read-only snapshot data/mt5): EURUSD, USDJPY, AUDUSD, USDCHF (D1 2016-08..), US500, USTEC (2019-10..), USOIL (2017-01..),
BTCUSD (2018-03..). Costs: round trip 3 bp FX, 4 bp indices and oil, 10 bp BTC (conservative vs the broker's recorded spreads); swap not
modelled (stated). Entry next D1 open, stop-first first passage, the basket's own D1 ATR(14).

## Endpoints
- **Primary:** pooled over the eight markets, the mean weekly basket R minus the mean weekly R of the same basket with random timing (each
  member's trades replaced by the same direction mix entered at every D1 open, one position at a time; computed exactly like batch 2 controls)
  > 0, one-sided stationary-bootstrap p (weeks, mean block 4, K 999, seed 20261001) <= 0.05.
- **Secondary:** the same on each market (reported), the basket's own mean weekly R > 0 pooled, and gold CHECK / silver as reported context.
- PASS = primary. A pass makes the basket a candidate for a forward paper record; it does not make it a live system.
