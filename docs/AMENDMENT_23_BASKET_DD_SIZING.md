# Amendment 23 — decay-weighted multi-tool basket and DD sizing

**Written 2026-09-27 before the basket backtest.** This amendment is a
pre-registration, not a result. It implements the operator's instruction to run
several tools together, reselect and reweight them only at Weekend Rebuild, and
size the combined basket toward a 35–40% mark-to-market drawdown. It does not
authorize a Demo or real-money order and does not change the frozen Demo bot.

Amends the research use of Amendments 21 and 22. The standing prohibitions in
Amendment 22 section 3.4, `data/DEMO_ORDER_PERMISSION.md`, and
`docs/OWNERSHIP.md` remain in force.

## 1. The question and the order of proof

The primary question is:

> Does a causal, decay-weighted basket of several distinct declared tools have
> positive net walk-forward performance after costs, including weeks in which
> it does not trade?

Only if that answer is positive is position sizing evaluated.

**The DD target sets how large the basket trades, not whether it makes money.**
Scaling cannot create expectancy. The unit-risk basket must produce a positive
walk-forward result before any 35–40% sizing result is treated as meaningful.

No honest past-only rule can guarantee that a future realized DD will be inside
35–40%. This amendment targets 37.5% on a rolling causal calibration replay,
then measures the unseen result. A realized result outside 35–40% is reported as
a sizing miss; it is not repaired with an ex-post multiplier.

## 2. Frozen candidate universe

The primary basket draws only from Amendment 14's already-declared 8,250 cells:

- six setup families: `breakout`, `pullback`, `sweep`, `failed`, `vwap`, and
  `expansion`;
- five signal timeframes: M5, M15, M30, H1, and H4;
- five ATR stops: 0.75, 1.0, 1.5, 2.0, and 3.0;
- five targets: 0.5, 1.0, 1.5, 2.0, and 3.0 R; and
- eleven entry modes: market, or 0.50/1.00 ATR limit entries expiring after
  5/8/10/12/15 signal bars.

No new family, indicator, direction flip, geometry, news gate, or macro gate is
added in this run. The six families are the declared gene pool for Amendment 23,
not a claim that the universe is complete. A later expansion requires a new
amendment written before its result is observed.

Each cell may have at most one position open. Exact duplicate realized order
signatures are collapsed before ranking so parameter copies do not receive
extra lottery tickets. Signal generation, pending-order placement, fills, and
exits must retain the canonical no-look-ahead and Bid/Ask rules already tested
by `test_mtf_engine.py`.

## 3. Weekend data boundary and decay weighting

Selection and reweighting occur only at Saturday Weekend Rebuild after XAUUSD
has closed. The chosen membership, weights, and sizing multiplier are frozen
until the next Weekend Rebuild.

At cutoff `C`, a result is available only if its exit was resolved before `C`.
A newly selected member cannot inherit a pending order created before `C`.
Pending orders left by the prior basket are cancelled at the boundary. An open
position is not rewritten: it continues under the rule and size frozen when it
was opened, occupies an overlap slot, and consumes the new basket's risk budget
until it exits.

For every candidate, construct one net unit-risk return for every completed
calendar week. A week with no executed trade is **zero**, not missing. All
available weeks remain in the calculation, with age in completed weeks `a`
weighted as:

```text
decay_weight(a) = 2 ** (-a / 3)
```

The most recent completed week has weight 1.0 and the half-life is three weeks
(21 calendar days), matching Amendment 22's natural starting point. Older data
therefore has progressively smaller but non-zero model influence and remains
permanently preserved in `docs/LOGIC_LEDGER.md` under rule 9.

For candidate `i`, calculate the exponentially weighted weekly mean `mu_i`,
weighted standard deviation `sd_i`, and effective sample size

```text
n_eff = (sum(weight) ** 2) / sum(weight ** 2)
LCB_i  = mu_i - 0.75 * sd_i / sqrt(n_eff)
```

using the zero-inclusive weekly series. A candidate is eligible only after 26
completed history weeks, at least eight non-zero weeks, `LCB_i > 0`, and a
positive weighted mean under the predeclared 1.5x cost stress. Undefined
variance or correlation is `NOT ASSESSED` and is ineligible, never replaced by
an assumed value.

The half-life, 0.75 LCB coefficient, history gates, and cost-stress gate are
frozen for this amendment. They may not be changed after seeing the result.

## 4. Membership, correlation, and overlap

Eligible cells are sorted by descending LCB, with the tag as a deterministic
tie-break. The basket is built greedily under all of these constraints:

1. maximum five members, minimum three members to trade;
2. no more than one member from any setup family;
3. no duplicate order signature;
4. pairwise exponentially weighted correlation of the zero-inclusive weekly
   returns must be at most 0.70; and
5. the member must leave the basket's 1.5x-cost weighted mean positive after it
   is added.

If fewer than three members survive, the next week is `NO TRADE`. Idle capital
and every idle week count as zero in every portfolio result.

Distinct members may hold opposing directions at the same time. They remain
independent sleeves; positions are not netted into an invented fill, averaged,
martingaled, or used to increase a losing position. Both sides consume gross
risk and incur their own costs.

At most five basket positions may be open concurrently. A carried position from
the prior week occupies one of those five slots. If a simultaneous signal would
exceed five positions or the portfolio risk budget, signals are admitted in
current member-score order and the rest are skipped and reported. This order is
fixed before the forward week.

## 5. Member weights

The same three-week decay weights are used to estimate each selected member's
downside deviation and the basket covariance matrix. Initial raw weights are:

```text
raw_weight_i = max(LCB_i, 0) / max(downside_deviation_i, volatility_floor)
```

where `volatility_floor` is the 25th percentile of positive downside deviations
among that weekend's eligible cells. Raw weights are normalized to sum to one,
then deterministically redistributed until every member is between 10% and 35%.
If the bounds cannot be satisfied with the surviving membership, the basket is
`NO TRADE` for that week.

The pairwise 0.70 admission cap handles near-duplicate members. In addition,
any pair with correlation at least 0.50 may hold no more than 50% combined
weight; excess is redistributed pro rata to lower-correlation members within
the 10–35% bounds. The final covariance matrix, member risk contributions,
weights, and every binding cap are recorded at each Weekend Rebuild.

## 6. Unit-risk walk-forward must come first

The selector is replayed Saturday by Saturday. Every historical Saturday sees
only data that was available then, freezes the resulting members and weights,
and trades only the following seven calendar days. This nested weekly replay is
the primary result. It includes:

- zero-return weeks when no basket can be formed or no order fills;
- real overlap and floating P/L at every M5 bar;
- prior-week positions carried under their original rules;
- pending-order cancellation at the weekly boundary;
- the five-position and gross-risk admission caps; and
- all costs in section 8.

The unit-risk replay is run and judged before DD targeting. If it fails section
10, the sizing stage has no promotable interpretation even if an ex-post scale
could manufacture an attractive dollar curve.

## 7. Past-only 35–40% DD sizing

The operating aim is the midpoint, 37.5% mark-to-market DD. The 35% boundary is
a soft risk gate and 40% is a hard ceiling.

Sizing is recomputed at every Weekend Rebuild from a **trailing 52 completed
week** bar-by-bar replay of the nested basket policy. It is not calibrated once
on 2021. The calibration contains no deposits or withdrawals, because external
cash flow must not hide strategy drawdown. At least 26 causal policy weeks are
required; before that, the basket is `NO TRADE`.

At cutoff `C`, use bisection on one common portfolio risk multiplier to find the
largest multiplier whose unguarded trailing-52-week replay has MTM DD no greater
than 37.5%. The replay uses equity-proportional compounding, historical member
weights frozen at their own Weekend Rebuilds, volume steps, overlap, and costs.
Only bars before `C` participate. The future forward week never participates in
its own sizing.

Two conservative checks then apply:

1. replay that multiplier over all earlier causal walk-forward history; and
2. replay it over the trailing 52 weeks with costs multiplied by 1.5.

If either produces equity at or below zero or MTM DD above 50%, reduce the
multiplier by bisection until both pass. A weekly multiplier increase is capped
at 15% relative to the prior week; a decrease is immediate and unlimited. If a
guard or volume constraint leaves calibrated DD below 35%, report a sizing miss
instead of increasing size with knowledge of the forward result.

For a new order from member `i`, before broker limits:

```text
allowed_stop_USD_i = current_equity * portfolio_risk_multiplier * member_weight_i
cent_lot_i = floor_to_0.01(allowed_stop_USD_i / stop_loss_USD_at_1_cent_lot)
```

Volume is never rounded up. A computed volume below 0.01 cent lot is skipped and
counts as zero. Volume above 200 cent lots is capped and reported. Existing open
loss-to-stop plus proposed loss-to-stop, including exit costs, may not exceed the
current basket risk budget. Leverage 1:2000 affects required margin only; it does
not change stop loss, P/L, or the DD target. An order that fails free-margin or
volume checks is skipped rather than resized upward elsewhere.

During a forward replay, reaching 35% DD cancels pending orders and blocks new
entries while existing positions remain governed by their stops. Reaching 40%
triggers protective liquidation at the next executable Bid/Ask quote and stands
the basket down until a later Weekend Rebuild explicitly finds it eligible
again. Gap and slippage may still make realized DD exceed 40%; any such excess is
reported and is a sizing failure.

## 8. Cost profile and execution assumptions

The primary run uses the frozen Demo cost profile represented by
`data/weekly_evolution_universe_v10_sp090_co140.pkl`:

- raw spread `max(recorded spread, 0.090)` price units, equivalent to 90 points
  at three decimals;
- round-turn commission 0.140 price units;
- slippage 0.0165 price units per fill;
- long swap 0.5493 price units per counted 21:00 UTC rollover and short swap
  0.0 under the currently recorded model; and
- Bid/Ask-aware fills and exits, worst-case stop before target on an ambiguous
  M5 bar, and no same-bar target credited after an intrabar limit fill.

The cache may be used only if its full data, engine-code, and cost-profile hash
matches. A cache-name match alone is insufficient. The 260-point Cent profile is
not substituted into this primary Demo run. It is a separate execution profile
and must be reported separately if evaluated later.

## 9. Required reports

Report the causal unit-risk result and the DD-sized finance result separately.
At minimum, show:

1. **44-month regime:** 2022-01-01 through 2025-09-21;
2. **trailing 12 months:** 2025-09-21 through 2026-09-21;
3. **complete weekly walk-forward:** all forward weeks from 2022-01-01 through
   the canonical data end;
4. starting USD 100 plus USD 100 deposited at each monthly boundary, as a
   finance view only, with deposits separated from trading profit; and
5. DD scenarios at 30%, 35%, 40%, 45%, and 50% for diagnosis, while 37.5% with
   the 35/40 guards remains the operating proposal.

For every window report net R, net USD, deposited USD, final equity, profit
factor, positive-week percentage, maximum realized and MTM DD, worst week and
month, loss streak, zero-trade weeks, trades, turnover, maximum concurrent
positions, rejected signals, maximum cent lot, margin rejections, member/family
composition, weekly weight changes, correlations, and the dates and reasons for
every stand-down. Report base costs and 1.5x cost stress separately.

Also report a same-week ranking control against an equal-weight basket drawn
from the eligible family-middle cells. It is diagnostic and cannot replace the
primary walk-forward result.

## 10. Failure definitions

The amendment fails for promotion if any of the following occurs:

- any truncation, mutation, timestamp, content-hash, Bid/Ask, or future-data
  audit fails;
- the unit-risk walk-forward net result is not positive after base costs in
  either the 44-month regime or the trailing 12 months;
- the same two windows are not both positive under 1.5x cost stress;
- fewer than three eligible, correlation-compliant members form the basket for
  more than half of forward weeks;
- zero-trade weeks are omitted, treated as missing, or removed from averages;
- the reported edge exists only after applying the DD multiplier while the
  unit-risk basket is non-positive;
- the operating sizing replay has MTM DD below 35% or above 40% over the full
  forward evaluation. Below 35% is an undersizing/calibration miss; above 40%
  is a risk failure. The edge result remains recorded either way;
- any result depends on rounding volume up, exceeding broker volume/margin
  limits, ignoring overlap, or using an order that could not have existed at
  that historical time; or
- changing a frozen rule after inspecting the result is required to make the
  basket pass.

No member, half-life, threshold, correlation cap, weight bound, calibration
window, DD multiplier, or failure definition may be altered inside this run.
A revised design requires a new amendment and a fresh walk-forward result.

## 11. Status and authorization

This amendment authorizes only the read-only historical research described
above after independent review. It does **not** authorize running it yet; Claude
reviews this document first under `docs/OWNERSHIP.md`.

It does not authorize starting or restarting `payoff_demo_autotrader.py`,
changing Demo execution, sending a test order, sending a real-money order, or
opening a PR. A Demo change still requires a verified positive walk-forward
result and the review path in Amendments 22 and 23. Real money remains subject
to explicit confirmation for the specific order.

Current engine decision: **NO TRADE**.
