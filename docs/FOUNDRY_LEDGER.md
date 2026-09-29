# Tool Foundry ledger (append-only; each batch registered before it runs)

Protocol: `docs/FOUNDRY_PROTOCOL.md`. Trials: `data/foundry/trials.csv`; state (cumulative VAL
count M, HOLD looks j): `data/foundry/state.json`.

## Batch `batch1` (registered 2026-09-30, before running)
36 variants from 12 families, each × direction {both, long, short} × 10 cells (ALL + 9):
ASIA_BRK (Asia 00-07 UTC range break 07-16, stop opposite side, target 1R/2R/none, exit 20:00),
ASIA_FAIL (failed break of the Asia range, fade, target range opposite / 1R), NY_ORB (13-15 UTC
range, break 15-20), SHOCK_REV / SHOCK_CONT (H1 move > 2 or 3 ATR, fade or follow, hold 3/6/12 h,
stop 2 ATR), DONCH (D1 20/55-day channel, hold 10/20 d, stop 2.5 ATR), SMA_TREND (D1 close vs
SMA200 with SMA50, hold 5/20 d, stop 3 ATR), RSI2 (Connors RSI(2) < 10 above SMA200 / > 90 below,
hold 3/5 d), BB_REV (H1 Bollinger 20/2 fade to the middle band, hold 6/12 h, stop 2 ATR), NR7 (D1
narrowest range of 7 -> next-day OCO stop entries on H1, target 1R/2R), GAP_FADE (weekend gap > 1/2
H1 ATR, fade to Friday close), TOM_LONG / TOM_SHORT (turn of month, 4 days).
