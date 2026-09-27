# Amendment 29 — cross-asset generalization check: frozen A24 mechanism on GBPUSD

**Written 2026-09-27, before any Amendment 29 result.** Pre-registration,
Claude-led (ownership sixth revision). Prompted directly by the operator
asking whether a genuinely different asset — not just a fresh reviewer on
the same XAUUSD history — could give real new information tonight.

## 1. The question

> Applied completely unchanged — same six families, same causal fill-time
> chain, same friction-gate ratio, same decay/LCB selector, same basket
> rules — does the Amendment 24 mechanism find any edge on GBPUSD, an
> instrument no amendment in this project has ever touched?

This is **not** a search for a GBPUSD-specific strategy. No threshold,
family, or rule may be retuned for this instrument. If the mechanism was
capturing something real and general about how these six mechanical
patterns interact with execution cost, it should show *some* signal here,
even if weaker. If it shows nothing, or noise, that is evidence the XAUUSD
result was itself closer to noise than to a general phenomenon.

This is genuinely new data: GBPUSD has not been inspected, diagnosed, or
tuned against anywhere in this project's history. It cannot answer "will
XAUUSD's frozen policy work going forward" — only Amendment 27's forward
clock can do that. It can answer "does this mechanism generalize across
instruments," which is informative in its own right.

## 2. Data

MT5 returns genuine continuous M5 GBPUSD history (~1,440 bars/week, the
24/5 FX maximum) from **2021-07-01** on this broker; before that, bars are
sparse in the same way XAUUSD's pre-2021 bars were. The window used here is
**2021-08-01 through the latest available bar**, verified continuous by the
same `canonical_history.py` validator already used for XAUUSD (positive
spread, monotonic timestamps, consistent OHLC). A fresh, separate canonical
file is built; the XAUUSD canonical file is untouched.

## 3. Mechanism, unchanged

Everything from Amendments 24 and 26, with only the instrument and its cost
inputs changed:

- six families, five timeframes, five stops, five targets, eleven entry
  modes — the same declared 8,250-cell universe;
- Amendment 26's causal fill-time chain;
- Amendment 24's friction gate: `base_friction_R <= 1/12`,
  `1.5x <= 1/8`, using `max(sp[k-1], spread_floor)`;
- three-week decay, 26-week/8-nonzero eligibility, `LCB_stress`, 3–5
  members, one per family, correlation ≤ 0.70, weights 10–35%.

## 4. Cost inputs — measured where available, flagged where not

From `data/cost_model.json` (built 2026-09-22 on this account):

- spread floor: `0.00001` (GBPUSD point; `spread_live` measured ≈ 0.00001)
- commission round-turn: `0.00005`
- swap long: `-0.000021`/night, swap short: `-0.000006`/night

**Slippage has never been measured for GBPUSD** — the only measured
slippage figure in this project (0.0165 price units) came from real Demo
order probes on XAUUSD specifically, and no order is sent for this
amendment. Two scenarios are reported, both clearly labelled as
assumptions:

- **optimistic**: slippage = 0
- **conservative**: slippage = one spread-floor's worth per fill (i.e.
  round-turn slippage equal to the round-turn spread)

Neither is a measurement. If either scenario indicates something worth
pursuing, GBPUSD slippage must be measured for real before that carries
any weight.

## 5. Scope reduction, stated plainly

This does not repeat the full Amendment 26 audit suite (look-ahead mutation
tests, streaming-oracle cross-check, etc.) against a second instrument —
that would be its own multi-hour build. The causal chain and friction gate
are the same audited code (`causal_chain.py`, `basket_gate.py`) run against
new input data; only `mtf_engine`'s cost constants and the source `Bars`
object change. This is a lighter-weight generalization probe, not a full
audit-grade amendment, and is reported as such.

## 6. Required report

Net R, gross R, execution R, trades, PF, active weeks, MTM DD — at both
slippage scenarios — for the full available GBPUSD window, split at its own
midpoint (no XAUUSD-specific date has meaning here). Development data
labelling does not apply in the usual sense (this instrument was never
inspected before), but the mechanism's specific thresholds were chosen on
XAUUSD, so this is a transfer test, not a fresh design.

## 7. Status

No order sent, no autotrader touched, no PR. **NO TRADE.**
