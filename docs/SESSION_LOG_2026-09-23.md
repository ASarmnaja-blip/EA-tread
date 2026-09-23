# Session log — 2026-09-23, both agents at limit

Written before shutdown, so neither agent has to reconstruct this.

## Codex — Amendment 17, COMPLETE, negative

Session-level acceptance/rejection at Asia, pre-London and prior-day levels.
7,665 matched events over 681 days.

```
ordinal touch slope   +0.00008 R    SE 0.01408    one-sided p 0.4990   MDE 0.03503
touch means           NOT monotone — the declared hypothesis fails
first-touch excess    -0.0158 R     net -0.0716 R at 1x
```

**Mechanism not established. No candidate.** Codex checked
`data/rollover_cost.json` first as instructed and correctly refused to treat it as
a measurement. It also found and fixed a swap-calendar bug in its own runner
(`50fb43b`) — verified not to touch anything W1 imports.

Commits: `b1110d1` preregister, `c9bbe4b` touch-episode reset, `569558e` build,
`50fb43b` swap fix, `1efc546` negative result. Files:
`docs/AMENDMENT_17_SESSION_ACCEPTANCE_REJECTION.md`,
`research/pilot/session_acceptance.py`, `test_session_acceptance.py`,
`session_acceptance_run.txt`, plus `STATUS.md` and `BACKLOG.md`.

**Codex's own warnings, carried forward:** do not mine a subgroup out of this; the
research line is a run of negatives, so move to a **distinct channel** rather than
twisting a closed one. Its proposal: **Amendment 18, a small pre-registered
VWAP / value-area experiment**, preregistration written before any run.

## Claude — W1, still unjudged

Window missed twice.

- **2026-09-22 21:52 UTC:** task fired on time, stalled 23 s on a permission
  prompt. No orders, no positions, balance unchanged.
- **AutoTrading is OFF** in the MT5 terminal (`terminal_info().trade_allowed =
  False`), so every order returns retcode 10027. It worked earlier on 09-22, so
  the button was turned off since.
- `data/rollover_cost.json` holds **3 records, all junk**, all labelled
  `NOT_A_MEASUREMENT`. Two are mine, written while testing a guard whose patch had
  silently failed. None measured a fill.
- **Hour guard now lives in the script** (`tools/rollover_cost_probe.py`), refusing
  orders outside 21–23 UTC and labelling any record written outside them. Side
  effect: "Run now" is now safe for pre-approving permissions.
- Task re-armed for **2026-09-23 21:52 UTC** (04:52 Thai, 24 Sep), with an
  AutoTrading check as step 1.

W1 unchanged and unconfirmed: **net +0.2573 R at 1x, 95 % lower bound +0.0437**,
conditional on a slippage figure still taken in liquid hours. Shadow logger has
**0 signals** (expected at ~25/year).

## Two things the operator must do before the next window

1. **Turn AutoTrading green** in the MT5 toolbar.
2. **Click "Run now" once** on the rollover task and approve the prompt — it will
   decline to trade (wrong hour) but the approval is stored.

**Shutting the machine down means tonight's window is missed too.** The window
recurs daily; the cost is one day.

## Standing

No real-money order has ever been sent. No position open. No PR. **NO TRADE.**
