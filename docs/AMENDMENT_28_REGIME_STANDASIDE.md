# Amendment 28 — volatility-regime stand-aside on the A24 causal basket

**Written 2026-09-27, before any Amendment 28 code or result.** Pre-
registration only, written and to be run by Claude directly (ownership sixth
revision — Claude leads). This does not authorize any run before this
document exists in the repository history exactly as written below.

## 1. Why this, stated honestly

Amendment 24 on the causal chain (Amendment 26) is positive in the trailing
12 months at both costs (+31.643 / +18.000 R) and negative over the 44-month
window (−80.397 / −109.119 R). The per-trade cost decomposition already
showed why: in the 44-month window the median stop was narrower (lower
realised volatility), so the same near-fixed dollar cost consumed more of a
similar gross edge. Amendment 24's friction gate rejects the worst individual
trades on this basis but does not stop the basket from trading through an
entire *regime* where the edge-to-cost ratio is thin everywhere.

**This design is informed by that finding. It is NOT BLIND.** The 44-month
failure has been seen, in detail, before this amendment is written. This
amendment does not claim to discover the regime effect; it tests one
specific, frozen mechanism for responding to it: stand aside entirely in
weeks where the recent volatility regime is not favourable, rather than
trying to filter trade-by-trade.

## 2. The question, and the order of proof

> Does adding one frozen, causal, weekly stand-aside rule — based only on
> trailing realised volatility, known before the week starts — turn
> Amendment 24's 44-month loss into a smaller loss or a gain, without
> materially damaging the already-positive trailing-12-month result?

Unit risk is judged first, exactly as in every prior amendment. This is a
diagnostic extension of Amendment 24, not a new selector, universe, cost
model, or basket-construction rule. Everything from Amendment 24 (causal
chain, `sp[k-1]` friction gate, stressed LCB ranking, membership and weight
rules, correlation caps, overlap, and costs) is retained unchanged. The only
addition is section 3.

## 3. Frozen regime measure and stand-aside rule

At every Weekend Rebuild cutoff `C`, using only M5 bars with `t < C`:

1. Resample to H1 (already-verified `mtf_engine.resample`).
2. Compute `atr_h1 = core.atr(bars_h1, 14)` (the same ATR function used
   throughout every amendment).
3. Take the last 480 completed H1 bars before `C` (20 trading days) and let
   `recent_atr = median(atr_h1[-480:])`.
4. Take the last 8,760 completed H1 bars before `C` (365 days, or all
   available if fewer — the history ceiling is 2021-01-03) and let
   `hist_atr = atr_h1` over that trailing window.
5. `regime_percentile = percentile_rank(recent_atr, within hist_atr)` — the
   fraction of the trailing-year hourly ATR distribution that `recent_atr`
   exceeds.

**Frozen rule:** if `regime_percentile < 0.40`, the basket is `NO TRADE` for
the coming week regardless of what section 4 of Amendment 24 would otherwise
select. Membership, weights, `n_eff`, and every other computed quantity for
that week are still logged (for the guideline library, rule 9) but no
position may open. If fewer than 480 trailing H1 bars exist at `C`, the
stand-aside rule cannot be evaluated and the week is also `NO TRADE`
(insufficient history, not a favourable-regime default).

**Threshold 0.40 is frozen now and may not be moved after seeing a result.**
It is chosen as a round, sub-median cutoff — deliberately not tuned to
reproduce the 44-month/trailing-12-month split exactly, precisely because
that split is already known and fitting to it would be circular. No sweep
over alternative thresholds is authorized inside this amendment; a different
threshold is a new amendment with a new NOT BLIND label restarting from
today.

## 4. Universe, chain, gate, costs — unchanged from Amendment 24/26

- Candidate universe: the declared 8,250 cells (six families, five
  timeframes, five stops, five targets, eleven entry modes).
- Candidate chain: Amendment 26's causal fill-time rule
  (`research/pilot/causal_chain.py`, `causal_indices`/`causal_gated_indices`),
  not the legacy signal-order chain.
- Friction gate: `max(b5.sp[k-1], 0.090)` at the first otherwise valid fill;
  `base_friction_R <= 1/12`, stress `<= 1/8`.
- Weekly ranking: three-week half-life decay, 26-week/8-nonzero-week
  eligibility, `LCB_stress = mu_stress - 0.75 * sd_stress / sqrt(n_eff)`,
  positive corresponding base mean required.
- Basket: 3–5 members, one per family, correlation ≤ 0.70, weights 10–35%,
  50% combined cap above 0.50 correlation.
- Cost profile: Demo90 (spread floor 0.090, commission 0.140, slippage
  0.0165/fill, long swap 0.5493/rollover, short swap 0).
- Exit-week assignment, zero-inclusive weeks, at most five concurrent
  positions, no netting/Grid/Martingale.

## 5. Required reports

Report, at base and 1.5x cost, for 2022-01-01–2025-09-21, 2025-09-21–end of
canonical data, and the full period:

- net R, gross R, execution R, swap R, trades, PF, active/positive/zero
  weeks, MTM DD, worst week/month, loss streak;
- **stand-aside weeks**: count and share of all decision weeks, separately
  for the 44-month and trailing windows, and the regime percentile on every
  stand-aside week (so a reviewer can see whether it concentrates in the
  44-month window, as the hypothesis predicts, or is scattered); and
- a side-by-side table: Amendment 24 as measured in Amendment 26 (no
  stand-aside) versus Amendment 28 (with stand-aside), same causal chain,
  same everything else.

## 6. Failure definitions

Fails for further consideration if:

- any existing Amendment 26 causal/no-look-ahead audit fails when re-run
  against this module;
- the regime measure at any cutoff uses a bar with `t >= C` (checked with a
  truncation/mutation test, as in every prior amendment);
- the 44-month result is still negative at 1.5x cost after standing aside
  (the mechanism did not work, and is reported as such — not adjusted);
- the trailing-12-month result turns negative at either cost (the fix broke
  the one thing that was working); or
- any threshold or rule is changed after the result is observed.

A positive 44-month result under this amendment is a development result,
informed by everything already seen. It is not confirmation. Amendment 27's
26-week forward shadow ledger remains the only path to confirmation for
whichever policy is ultimately frozen for that clock — this amendment does
not change Amendment 27's already-running (not yet started) forward clock,
and does not modify `research/pilot/a27_forward.py`.

## 7. Status and authorization

This is a diagnostic pre-registration. It does not authorize any order,
Demo or real, and does not touch `payoff_demo_autotrader.py` or Amendment
27's forward logger. **NO TRADE.**
