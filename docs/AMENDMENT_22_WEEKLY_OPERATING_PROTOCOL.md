# Amendment 22 — the operator's weekly operating protocol

**Written 2026-09-26, at the operator's direct instruction.** This is not a
research result. It is the standing operating rule the project must follow from
here on, recorded in full before any system is reconciled against it.

Amends: how Amendment 19 (current edge scanner) and Amendment 21 (weekly
evolution grid) are used together, and the Saturday-report gate in the
`current-edge-wednesday-observation` automation. Does not amend: the standing
prohibitions (no real-money order without explicit per-order confirmation, no
Grid/Martingale, no PR without inspectable evidence), W1's protocol, or the
Claude/Codex ownership split in `docs/OWNERSHIP.md`.

## 1. The eight rules, as given

1. **Beat the current market only.** Not all-time history, not the future in
   general — the market as it exists now. This restates the founding principle
   in `CLAUDE.md` section 1 and is not new.
2. **Every Wednesday: Wednesday Report.** Collect everything about the chart in
   that week — traces, internal and external factors touching the market — in
   detail. Broader and deeper than a scanner health check.
3. **Every Saturday after close: Weekend Rebuild.** Same data collection as
   Wednesday, plus: retune the tool currently trading that week, and forecast
   the coming week.
4. **The traded tool may differ from any prior week.** High likelihood, most
   weeks, that this week's tool is not last week's or any earlier week's — this
   is the intended adaptation to the current market, not a defect.
5. **Tune from all data, but weight the latest week heaviest, with weight
   decreasing week by week going back.** Recent traces are clearer than old
   ones. This is a decay requirement, not a hard cutoff window.
6. **The tool must always be current.** The operating cadence exists to enforce
   this continuously, not as an occasional review.
7. **When the active tool starts to decay, retune or replace it — every
   Weekend Rebuild is the checkpoint for this**, not an emergency-only action.
8. **Stay within the scope already specified.** Read here as: the standing
   safety prohibitions, the ownership split, and the requirement that nothing
   above licenses guessing, fabricating data, or skipping verification.

## 2. What already exists, and how it maps

| rule | closest existing system | fit |
|---|---|---|
| 1 | founding principle, unchanged | exact |
| 2 | Amendment 19 section 9 Wednesday step (`current_edge_ops.py --mode wednesday`) | narrower than the rule — currently scanner health only, not full chart/factor traces |
| 3 | Amendment 19 section 9 Saturday step + `docs/WEEKEND_REBUILD_2026-09-26.md` | the manual report already produced satisfies this; the automated `--mode weekend` checklist alone does not yet |
| 4, 7 | Amendment 21's weekly evolution grid (hard winner-take-all reselection) | matches the mechanic, but is explicitly not yet promoted |
| 5 | Amendment 19's scanner (21-day half-life exponentially weighted mean) | matches |
| 5 | Amendment 21's ranker (flat 56-day trailing window, uniform weight inside it, zero outside) | does not match. No decay. Recorded as a defect against rule 5, not a style choice |
| 6 | the Wed/Sat cadence itself | structurally present, content needs widening per row 2 |
| 8 | `docs/OWNERSHIP.md`, `data/DEMO_ORDER_PERMISSION.md`, every amendment's standing prohibitions | unchanged, restated below |

## 3. The reconciliation this amendment makes

### 3.1 Amendment 21's selector must be decay-weighted before it can satisfy rule 5

Amendment 21 currently ranks the 8,250-cell grid on a flat 56-day window: every
trade inside the window counts equally, every trade outside it counts zero. Rule
5 asks for the opposite shape — all history usable, weight falling off smoothly
by week. A hard window is more, not less, exposed to noise at the boundary,
which is a plausible explanation for the 73 percent weekly champion-change rate
Codex already flagged as churn rather than regime detection.

**Required before Amendment 21 may feed a live decision:** replace the flat
56-day window with an explicit multi-week decay (a half-life on the order of
Amendment 19's 21 days is the natural starting point, but this is Codex's
parameter to justify, not to inherit unexamined) applied over the full available
history, and re-report the weekly champion-change rate and the era-by-era
breakdown Codex already called for in Amendment 21's own next-steps note. This is
queued for Codex, which owns `weekly_evolution_grid.py` per `docs/OWNERSHIP.md`;
Claude is not implementing this from here.

### 3.2 The Saturday gate in the automation is superseded, within stated limits

The `current-edge-wednesday-observation` automation currently says the Saturday
report "must not change strategy parameters, promote a new tool, or alter Demo
execution without a separately verified historical weekly walk-forward result and
user approval."

Rules 3, 4 and 7 are the operator's standing prior approval for the Weekend
Rebuild specifically to retune or replace the active tool as a normal, expected
weekly action — not an exception requiring a fresh ask each time. This replaces
only the "and user approval" clause of that gate, for actions taken inside the
Weekend Rebuild step, on the Demo account, within the existing risk and cost
model. It does not remove the "separately verified historical weekly walk-forward
result" clause: a retune or tool change still has to point at a backtest that was
run and reported, not asserted. It does not touch real money, which stays gated
exactly as before — every prohibition in Amendment 12 section 7,
`data/DEMO_ORDER_PERMISSION.md`, and every other amendment's real-order rule is
unchanged by this section.

### 3.3 The Wednesday and Saturday reports need a fixed content list

So "detail" in rules 2 and 3 is checkable rather than a matter of taste, both
reports must include, going forward:

- current scanner/grid state and any open Demo positions, per Amendment 19
  section 9
- DXY and XAUUSD state: recent range, direction, and — stated explicitly — no
  causal claim from co-movement alone
- the economic calendar for the relevant window, timestamped, sourced, with
  forecast/previous only, never actual, before release, and NOT ASSESSED
  wherever a figure or a primary source was not retrieved
- CFTC Gold positioning, from a source retrieved this run, with its
  survey-date-to-release lag stated, never presented as current
- (Saturday only) attribution of the past week's realized result by
  family/era, the retune or replacement decision and the evidence it points at,
  and a conditional scenario map for the coming week — conditions and readings,
  never a directional call
- `docs/WEEKEND_REBUILD_2026-09-26.md` is the template; it already satisfies
  this list once for one week

### 3.4 Scope, restated so rule 8 is not a blank check

Unchanged by any rule above:

- no real-money order, ever, without the operator's explicit confirmation on
  that specific order — a standing weekly approval for Demo retuning is not a
  standing approval for real money, and is not read as one
- Demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime
- no Grid, no Martingale, no averaging
- no PR until there is evidence ready to inspect
- NOT ASSESSED rather than a guess, always
- the 120-day holdout, wherever one still exists, may be used for diagnosis
  and never for promotion
- W1 stays Claude's per `docs/OWNERSHIP.md`; this amendment does not reassign
  it

## 4. What happens next, and who does it

- **Codex** (owns this thread): add decay weighting to `weekly_evolution_grid.py`
  per section 3.1, re-run, report by era, and only then propose feeding a
  selection into `payoff_demo_autotrader.py`. Widen
  `current_edge_ops.py --mode wednesday`'s content to section 3.3's list.
- **Claude**: continues W1 only, per `docs/OWNERSHIP.md`, unless separately
  asked to reconcile something else across the two threads as this task was.
- Neither may loosen section 3.4 without the operator saying so in those
  specific terms.

## 5. Status

No real-money order has been sent. No parameter of a live Demo system was
changed by this amendment — it is a documentation and reconciliation pass, not a
code change. The engine's answer remains NO TRADE.
