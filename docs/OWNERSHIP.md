# Who owns what — updated 2026-09-22

**Codex owns everything, including W1.** The operator handed the whole project over
and will bring Claude back next Saturday to continue from wherever Codex has got
to. An earlier version of this file split W1 off to Claude; that split is
withdrawn.

---

## The one thing Claude left running, and why

| task | state |
|---|---|
| `w1-rollover-cost-probe` — sends demo orders | **DELETED** |
| `w1-shadow-logger` — read-only, logs signals | **still running, 5x daily** |

**The probe was deleted deliberately.** It sends demo orders in a one-hour window,
and two agents doing that in the same window is a real collision. Running it is now
Codex's call. Its prompt is recoverable at
`C:\Users\66985\.claude\scheduled-tasks\w1-rollover-cost-probe\SKILL.md`, and the
script is `tools/rollover_cost_probe.py`.

**The logger was kept because a missed signal cannot be recovered.** W1 fires about
25 times a year and the forward-shadow clock is already running; a signal that
passes unlogged is gone. It never sends an order, it only appends to
`data/w1_shadow_log.json`, which Codex can read freely. If Codex would rather own
that too, delete the `w1-shadow-logger` scheduled task and run
`research/pilot/w1_shadow.py` on whatever cadence suits.

---

## W1, handed to Codex — everything needed to finish it

**The blocking measurement.** Run
`tools/rollover_cost_probe.py --seconds 600 --probes 4 --orders`
**only inside 21:52–22:03 UTC.** W1 trades at 22:00 UTC (66 % of its entries) and
23:00 UTC (33 %). The slippage floor of 0.0165 per fill that the whole cost model
uses was measured in liquid hours. A figure from any other hour is not the
measurement, and the window recurs daily, so a missed night costs nothing but a day.

**The trap in the data.** `data/rollover_cost.json` already holds one record and it
is **a smoke test, not a measurement**. It carries a `NOT_A_MEASUREMENT` field
stating so: taken at 01:26 UTC in liquid hours, `--orders` not passed so **zero
probes were sent**, and its 0.090 spread is the liquid-hours figure the cost model
already assumed. Judging W1 from that record would conclude W1 survives on a
measurement that was never taken.

**The verdict arithmetic, fixed in advance and not adjustable:**

```
net = 0.3027 - (measured round-turn cost / R),    R = 1.5 x ATR
```

Below **+0.05 R** W1 is dead and gets recorded dead on `docs/WATCHLIST.md`.
`AMENDMENT_12` section 7 forbids moving the gap threshold, the stop, the target or
the time stop to save it.

**The shadow's stopping rule is frozen** in `data/w1_shadow_protocol.json`: 26 weeks
from the first forward signal **or** 30 events, whichever comes **second**. It does
not stop early on a favourable result and does not extend on an unfavourable one.

---

## The rest, as Codex agreed in `docs/HANDOVER_TO_CODEX.md`

1. Session acceptance/rejection — Asia, pre-London and prior-day high/low, with
   **touch count as an ordinal variable** and one pre-registered hypothesis that the
   effect declines monotonically with touch count
2. VWAP — `core.s5_vwap` has existed since early on and appears in no search at all
3. The M1 series beyond DXY news timing
4. Both tails reported; the holdout never read for promotion

Not recommended: more indicator grid. Amendments 10, 11 and 13 closed it.

---

## Not negotiable by any agent

- no real-money order, ever, without the operator's explicit confirmation
- demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime
- no PR until there is evidence ready to inspect
- no Grid, no Martingale, no averaging
- NOT ASSESSED rather than a guess
- every search gets its own amendment, written before it runs
- the 120-day holdout may be used for diagnosis and never for promotion

The engine's answer remains **NO TRADE**.
