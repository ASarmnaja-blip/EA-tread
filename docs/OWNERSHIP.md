# Who owns what — 2026-09-22

Set by the operator: **Claude watches W1. Codex takes everything else.**

This file exists so two agents do not act on the same thing. Neither should
silently take work from the other's column.

---

## Claude — the W1 track only

| item | state |
|---|---|
| the **rollover cost measurement**, the one number that decides W1 | scheduled, fires **2026-09-22 21:52 UTC** (04:52 Thai, 23 Sep), jitter 0 |
| the **W1 forward shadow** logger | running 5x daily, read-only, never sends an order |
| judging W1 against `docs/AMENDMENT_12` section 4 | mine |
| recording W1 alive or dead on `docs/WATCHLIST.md` | mine |

**Codex: please do not run `tools/rollover_cost_probe.py`, do not judge W1, and do
not edit W1's entry on the watchlist.** Two agents sending demo orders into the
same one-hour window, or writing conflicting verdicts, is the specific failure this
file prevents.

### A trap in the data, flagged

`data/rollover_cost.json` already holds one record. **It is a smoke test, not a
measurement**, and it now carries a `NOT_A_MEASUREMENT` field saying so:

- taken at **01:26 UTC**, which is liquid hours. W1 trades at 22:00–23:00 UTC.
- `--orders` was not passed, so **zero probes were sent** and no fill was measured
- its 0.090 spread is the liquid-hours figure the cost model already used

Judging W1 from that record would conclude W1 survives on the strength of a
measurement that was never taken.

### The verdict arithmetic, fixed in advance

```
net = 0.3027 - (measured round-turn cost / R),   R = 1.5 x ATR
```

Below +0.05 R, W1 is dead and gets recorded dead. `AMENDMENT_12` section 7 forbids
moving the gap threshold, stop, target or time stop to save it.

### If the window is missed

If the app is closed at 21:52 UTC the task fires on next launch, which will be the
**wrong hour**. A slippage figure from any other hour is not the measurement.
**Wait for the next 21:52–22:03 UTC window. Do not substitute another hour.**

---

## Codex — everything else

Per `docs/HANDOVER_TO_CODEX.md`, in the order it agreed:

1. Session acceptance/rejection — Asia, pre-London and prior-day high/low, with
   **touch count as an ordinal variable** and one pre-registered hypothesis that
   the effect declines monotonically with touch count
2. VWAP — `core.s5_vwap` has existed since early on and appears in no search
3. The M1 series beyond DXY news timing
4. Both tails reported, holdout never read for promotion

Not recommended: more indicator grid. Amendments 10, 11 and 13 closed it.

---

## Shared, and not negotiable by either of us

- no real-money order, ever, without the operator's explicit confirmation
- demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime
- no PR until there is evidence ready to inspect
- no Grid, no Martingale, no averaging
- NOT ASSESSED rather than a guess
- every search gets its own amendment, written before it runs
- the 120-day holdout may be used for diagnosis and never for promotion
