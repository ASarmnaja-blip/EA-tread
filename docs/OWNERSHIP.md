# Who owns what — updated 2026-09-22 (third revision)

**Claude owns W1. Codex owns everything else.**

Set by the operator after Codex completed Amendment 17; he is telling Codex
directly to leave W1 alone. An earlier revision handed W1 to Codex and is
withdrawn. The revision history is left visible rather than tidied away, because
two agents reading a cleaned-up file would not know which way it had last moved.

---

## Claude's two running tasks

| task | state |
|---|---|
| `w1-rollover-cost-probe` — sends demo orders | **re-armed, fires 2026-09-22 21:52 UTC** (04:52 Thai, 23 Sep) |
| `w1-shadow-logger` — read-only, logs signals | running 5x daily, **0 signals so far** |

**Codex: please do not run `tools/rollover_cost_probe.py`, do not judge W1, and do
not edit W1's entry on `docs/WATCHLIST.md`.** Two agents sending demo orders into
the same one-hour window, or writing conflicting verdicts on the same candidate, is
the specific failure this file exists to prevent. Everything else in the repo is
yours.

The probe's task carries a **step 0 that aborts unless the current UTC hour is 21
or 22**. The app scheduler fires a missed one-time task on next launch, which would
be the wrong hour, and a slippage figure from the wrong hour is worse than none
because it would read as evidence.

### Checked after Amendment 17: W1's numbers are unaffected

Codex's commit `50fb43b "Correct Amendment 17 swap calendar accounting"` is exactly
the kind of shared-code fix that could have moved W1's cost arithmetic. It did not:
the diff touches only `session_acceptance.py` and its test, and none of
`adaptive.py`, `core.py`, `data.py`, `matched_control.py` or `wide_engine.py`, which
are what `w1_cost_test.py` imports.

Re-ran it to confirm rather than assume: **net +0.2573 R at 1x, 95 % lower bound
+0.0437** — identical to before. Nothing to re-derive.

---

## W1 — what remains to finish it

**The blocking measurement.** `tools/rollover_cost_probe.py --seconds 600
--probes 4 --orders`, **only inside 21:52–22:03 UTC**. W1 takes 66 % of its entries
at 22:00 UTC and 33 % at 23:00. The slippage floor of 0.0165 per fill that the
whole cost model uses was measured in liquid hours. The window recurs daily, so a
missed night costs a day and nothing else.

**The trap in the data.** `data/rollover_cost.json` holds one record that is a
**smoke test, not a measurement**, and carries a `NOT_A_MEASUREMENT` field saying
so: 01:26 UTC, liquid hours, `--orders` not passed so **zero probes sent**, and its
0.090 spread is the liquid-hours figure the cost model already assumed. Judging W1
from it would conclude W1 survives on a measurement that was never taken.

**The verdict arithmetic, fixed in advance and not adjustable:**

```
net = 0.3027 - (measured round-turn cost / R),    R = 1.5 x ATR
```

Below **+0.05 R**, W1 is dead and is recorded dead. `AMENDMENT_12` section 7 forbids
moving the gap threshold, the stop, the target or the time stop to save it.

**Surviving is a prerequisite, not confirmation.** The shadow's stopping rule is
frozen in `data/w1_shadow_protocol.json`: 26 weeks from the first forward signal
**or** 30 events, whichever comes **second**. It does not stop early on a favourable
result and does not extend on an unfavourable one.

---

## Codex — everything else

Amendment 17 is complete and is Codex's result: ordinal touch slope **+0.00008 R**,
one-sided p **0.4990** against an MDE of 0.03503, touch means not monotone, net
negative at every ordinal after cost. **Mechanism not established, no candidate**,
and the document correctly warns against mining a subgroup out of it.

Next on the backlog, per `docs/HANDOVER_TO_CODEX.md` and Codex's own proposal:
**Amendment 18, a small pre-registered VWAP / value-area experiment.** `core.s5_vwap`
has existed since early in the project and appears in no search at all.

Standing caution from Codex's own status note: the research line is a run of
negatives, so the move is to a **distinct untested channel** rather than a twist on
a closed one.

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
