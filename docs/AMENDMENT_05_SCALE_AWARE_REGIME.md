# Protocol Amendment 05 — a scale-aware regime, declared before it is run

**Written 2026-09-21. Committed alone, before the code it describes produces a
single return. Every threshold below comes from the distribution of data
BEFORE the holdout, or from a mechanism, and none from a P&L.**

Amends: the regime definition in `research/pilot/adaptive.py`.
Does not amend: the entry, stop, target or time stop of any tool, the cost
model, Amendment 02's family-wise level, or Amendment 04's one-champion rule.

---

## 1. What went wrong with v1, stated precisely

The pullback tool earned **+0.0853 R** on development and **−0.1359 R** on the
120-day holdout at a matched cost. The investigation ruled things out in
order:

| explanation | verdict |
|---|---|
| cost | **ruled out.** The gap is −0.221, −0.212, −0.199, −0.173 R at slippage 0.0165 / 0.05 / 0.10 / 0.20. It barely moves. Gross flips too: +0.1594 → −0.1080 |
| volatility composition | **ruled out as stated.** Matched at ATR ≥ 5 the development trades still earned +0.2086 R against the holdout's −0.1359 |
| chance | **ruled out.** Bootstrap on the gap gives [−0.3883, −0.0529], excluding zero |

That left "edge decay", and a peer review was right that the phrase claims
more than the evidence supports. What is established is narrower:

> **a conditional performance break under the v1 regime label**

Still live, and not separated: the pullback mechanism genuinely dying; the
label `STABLE_TREND` lumping together markets that are not the same thing; a
latent variable nobody measured; or the holdout concentrating in a few
volatility episodes.

## 2. The measurement error that forced this amendment

The ATR-matched comparison above compared **dollars**, and gold's price rose
56 % across the sample, so dollar ATR rises with the price level whether or
not anything became more volatile. Measured properly:

| | development | holdout | change |
|---|---|---|---|
| price | 2,756.67 | 4,310.99 | +56.4 % |
| ATR in dollars | 3.7487 | 8.4061 | **+124.2 %** |
| **ATR / price** | 0.1345 % | 0.1961 % | **+45.8 %** |
| jump share of range | 0.0077 | 0.0094 | +22.7 % |
| vol-of-vol | 0.4103 | 0.3839 | −6.4 % |
| cost / ATR | 0.0782 | 0.0349 | **−55.4 %** |

**More than half of the "volatility doubled" was the price level.** The real
proportional rise is 46 %, and a regime label built on a rolling percentile is
blind to both.

Note the last row. Trading became **55 % cheaper relative to the size of the
move**, and performance still flipped negative. Whatever broke, it was not the
economics of paying to trade.

## 3. The v2 regime — definitions fixed now

`STABLE_TREND` is replaced by three states. A pullback needs a trend that is
**orderly**, not merely a trend that is **large**, and v1 could not tell those
apart.

Inputs, all computed from prior bars only:

| input | definition | why it is here |
|---|---|---|
| `atr_rel` | ATR(14) / close | proportional volatility, immune to the price level |
| `jump_share` | \|open − previous close\| / range | how much of the move arrives as a gap rather than as a path |
| `vol_of_vol` | sd / mean of rolling 1-hour realised vol | whether the volatility itself is steady |
| `dir_eff` | \|net\| / path length, at 1 day, 4 hours and 1 hour | directional efficiency at three horizons |
| `slope_agree` | the three horizons' slopes share a sign | a trend that agrees with itself |
| `cost_over_atr` | (spread + measured slippage) / ATR | whether the move is large enough to pay for |

States:

```
ORDERLY_TREND      dir_eff high at 2 of 3 horizons AND slope_agree
                   AND jump_share low AND vol_of_vol low
SHOCK_TREND        directional but jump_share high OR vol_of_vol high
UNSTABLE_HIGH_VOL  atr_rel high AND dir_eff low
BALANCED_RANGE     dir_eff low AND atr_rel not high
EVENT              within 30 minutes of a USD HIGH release
UNDEFINED          anything else
```

**Only `ORDERLY_TREND` may run the pullback.** `SHOCK_TREND` and
`UNSTABLE_HIGH_VOL` run nothing until they have their own declared candidate.

### Thresholds, and how they are chosen

"High" and "low" are the **70th and 30th percentiles of a 45-day trailing
window**, computed from prior bars only, exactly as v1 did. No threshold is a
fixed number picked to make a table look better, and no threshold is chosen by
looking at returns.

`cost_over_atr` enters as a **gate, not a classifier**: a bar where the round
turn exceeds 8 % of one ATR is not traded whatever its state, because the move
cannot pay for itself. 8 % is a mechanism choice — it is roughly where one R
of 1.5 ATR leaves less than two thirds of a typical target after costs — and
it is fixed now.

## 4. Two frozen versions, with different rights

| version | regime | role | may become champion |
|---|---|---|---|
| **v1** | percentile only | **frozen control** | **no** — it already failed its holdout |
| **v2** | scale-aware, this amendment | **the single challenger** | yes, after forward shadow only |

v1 keeps running in shadow as a control. If v1 and v2 recover together the
market turned, not the rule; if v2 works while v1 stays broken, the regime
definition was the problem. **Declared now so that the comparison cannot be
made after the fact:** v2 is the only candidate eligible for promotion, and v1
exists to be compared against. Running both and crowning the winner afterwards
is a selection, and it is forbidden.

## 5. Forward shadow, fixed in advance

Promotion requires all of:

- **8–12 weeks** of forward data that did not exist when this was written
- **60–100 non-overlapping trades**
- at least **two distinct volatility episodes**
- costs charged from **measured** spread and slippage, including swap
- **net expectancy positive**
- **lower bound of the clustered 95 % interval above zero**
- results not concentrated in one week or one session
- passes **both** overall and within `ORDERLY_TREND`
- **no rule changed during the run**

The 120-day holdout is now spent. It has been read and used to diagnose a
failure, so it may be used for diagnosis again and never for promotion.

## 6. What this amendment is not

It is not a fix, and it is not evidence that a scale-aware regime works. It is
a statement of what will be measured and how, written before the measurement,
so that whatever comes back can be believed. v1 remains a documented failure
and the engine's answer today remains **NO TRADE**.
