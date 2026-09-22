
# Protocol Amendment 13 — the geometry-neutral path diagnostic

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.**

Amends: nothing. It asks a question of every result already on the record, using
a measurement that does not depend on the barrier geometry those results assumed.

Does not amend: any closure (05–11), W1's protocol (12), the measured cost model
(08), the prohibition on real-money orders, or the prohibition on Grid and
Martingale.

---

## 1. The question, and why it is not answerable by anything built so far

Every search in this project has fixed:

```
stop    1.5 x ATR(14)
target  1.5 x ATR (RR 1:1) in the searches, 2R in ORDERLY_TREND
entry   the open of the next bar
exit    one stop, one target, one time stop, nothing in between
```

A setup carrying **real directional information at the wrong barrier distance**
produces exactly the same pass/fail record as a setup carrying **no information at
all**. Both look like noise. Five closures rest on that record, so the distinction
is not academic: it decides whether those closures are about the market or about
one choice of stop.

Amendment 11 removed the *holding horizon* as a hidden parameter. It did not touch
the *barriers*, and nothing else has.

## 2. Why this is not an RR-by-stop sweep

Sweeping stop distances and targets over a grid would multiply the search space
again, and Amendments 10 and 11 closed the case for more grid. Instead the path
itself is measured, which contains the answer to every barrier question at once
without any barrier being chosen.

For each entry, at fixed horizons `h` in M5 bars, with `d` the direction and
`ATR_i` the entry bar's ATR:

```
r(h)       = d x (close[k+h] - entry) / ATR        signed progress
MFE(h)     = max over 1..h of d x (extreme - entry) / ATR
MAE(h)     = max over 1..h of -d x (extreme - entry) / ATR
t_MFE      = the h at which MFE is first reached
P(fav)     = share of entries whose favourable move of size X arrives before
             an adverse move of the same size X
```

All in ATR units, so nothing depends on a stop. Horizons fixed now:

```
h = 3, 6, 12, 24, 48, 72, 144, 288 M5 bars   (15 min to 24 h)
X = 0.5, 1.0, 1.5, 2.0, 3.0 ATR              (the barrier sizes, for P(fav))
```

## 3. The control, unchanged

Each quantity is compared against the **same stratified direction-matched placebo**
frozen in Amendment 08 section 6.5 and corrected in Amendment 10 section 4 —
direction, calendar quarter, session, ATR tercile from prior bars, news state,
hourly spread bucket, with the focal bar's **whole calendar day removed** from the
control pool.

Without that control the diagnostic would just rediscover gold's drift, which is
the mistake Amendment 07 made and Amendment 08 corrected.

## 4. Inference, fixed now

**One simultaneous permutation band across all horizons**, not a test per horizon.
The horizons are nested — `MFE(288)` contains `MFE(72)` — so eight separate tests
would be eight readings of one quantity. Day-level sign flips, the same flip vector
applied to every horizon and every candidate in a draw, `G/(G-1)` cluster
correction, exactly as Amendment 10 section 5.

The reported statistic is the **maximum |t| over the horizon curve**, with its
permutation p-value. A curve is significant as a curve or not at all.

**Bonferroni over the number of subjects tested**, counted in section 5.

## 5. What is tested, counted before any result

| subject | why it is here |
|---|---|
| **W1** `gap_continuation/short` | the live candidate; its path shape decides whether its RR 1:1 is leaving money behind or taking on risk it does not need |
| **W2a** `rsi:40/short` | on the watchlist, loss unexplained after Amendment 11 |
| **W2b** `emax:50-200/long` | same |
| **ORDERLY_TREND v2 pullback** | the strongest closed family, and the one with a 2R target rather than 1:1 |
| **the tier-A aggregate** | all 233 assessable singles pooled, to ask whether the *family as a whole* has path structure that the pass/fail record destroyed |

**5 subjects.** Bonferroni for 5. No subject may be added after a result is seen.

## 6. The five readings, and what each would mean — fixed before the run

| pattern in the curve | reading | consequence |
|---|---|---|
| `r(h)`, MFE and MAE excess all flat at every horizon | there is no path structure to exploit | **the five closures get stronger**, and barrier geometry is eliminated as an explanation for them |
| MFE excess positive early, decaying to zero | the signal is real but **short-lived**; the holding period or target is wrong | a target/horizon amendment becomes justified — for the specific subject, not the family |
| `r(h)` excess positive while MAE excess is also large | **the stop was too tight**: the move happened but the barrier was hit first | the closures that used 1.5 ATR need re-reading, and this is the outcome with the largest consequence |
| MFE excess large but `r(h)` excess zero | the favourable move happens and is given back — **a trailing or partial-exit rule is the missing piece** | C5 on the backlog becomes justified |
| candidate and placebo curves indistinguishable | changing RR would have been optimising noise | RR and stop distance are **closed as gaps**, not just untested |

## 7. What this amendment may not do

- **It may not name a new candidate.** It tests five pre-specified subjects and
  nothing else. A pooled result is a statement about the family, never about a
  member of it.
- **It may not change any geometry.** If it finds the stop was too tight, that
  justifies a *new amendment* with its own untouched slice — not a re-run of a
  closed search at a wider stop, which would be re-tuning a frozen rule against a
  sample that has already been read.
- **It may not touch the 120-day holdout**, which is not read here.
- **It may not be used to revive W2.** W2's failures were trade count and
  significance; a favourable path shape does not supply either.

## 8. What failure looks like, so it cannot be argued away later

- all five subjects flat → **path structure is absent**, and the honest reading is
  that the closures were about information and not about barriers
- only the pooled aggregate shows anything → **one cell out of five**, reported
  with its multiplicity, pursued only under a new amendment
- a curve is significant at one horizon but not as a curve → **not significant**,
  because section 4 fixed the statistic as the maximum over the curve

None of these is a reason to add a horizon, add a subject, add a barrier size, or
lower the Bonferroni count.

## 9. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been sent,
no position is open, and no pull request is opened.
