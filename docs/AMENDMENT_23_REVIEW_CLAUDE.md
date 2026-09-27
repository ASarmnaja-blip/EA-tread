# Amendment 23 — Claude's pre-run review

**Written 2026-09-27, before any Amendment 23 result exists.** Reviewed under
`docs/OWNERSHIP.md` (fifth revision): whoever did not write a design reviews
it before it runs.

**Verdict: approved to run, with one clarification that must be implemented
and one power warning that must be reported.** No look-ahead defect was found.
Amendment 23 was committed unmodified as `bc38ed0`.

## Checked and sound

- resolution embargo: a result counts at cutoff C only if its exit resolved
  before C (§3)
- pending orders cancelled at each boundary; carried positions keep their
  frozen rule and size (§3, §6)
- zero-trade weeks count as zero everywhere (§3, §4, §10)
- sizing uses only the trailing 52 weeks before C, with no deposits in
  calibration; a size increase is capped at 15% a week and a decrease is
  immediate (§7)
- volume is never rounded up (§7)
- demo90 costs, with a full-hash cache check rather than name-only (§8)
- unit-risk result judged before any DD sizing (§1, §6, §10)
- the timeline fits: data from 2021-01-03 gives 26 history weeks by about
  2021-07-04, then 26 policy weeks for sizing by about 2022-01-02. The
  2022-01-01 start works, but only just, so early-2022 weeks may be NO TRADE
  (counted as zero)

## Clarification A — which week a trade's return belongs to (must implement)

§3 builds "one net unit-risk return for every completed calendar week" but
does not say which week receives a trade that enters in one week and exits in
the next. **Assign each trade's net R to the calendar week of its exit
(resolution).** This makes the weekly series causal by construction: at
cutoff C, every week before C contains only trades already resolved. It
matches §3's existing rule that only exits resolved before C are available.
This fills a gap in the design rather than changing a frozen rule, and it is
recorded before any result is observed.

## Warning B — effective sample size is about 8.7 weeks (must report)

With a 3-week half-life over an unbounded history, the decay ratio is
r = 2^(-1/3) ≈ 0.794, so

```text
n_eff -> (1 + r) / (1 - r) ≈ 8.7 weeks
```

The LCB and every pairwise correlation are therefore estimated from about nine
effective weekly observations, and each weekend ranks roughly 8,250 cells on
that. This is what rule 5 asks for, and it is frozen, so it is not a defect.
It does predict the main risk: the weekly top-by-LCB is likely to be driven
largely by noise, as in Amendment 10 (CONFIRM sign flips), Amendment 21 (73%
weekly churn), and the fine-grid walk (about −0.10 R/month forward).
Correlations near the 0.70 cap are also poorly determined at n_eff ≈ 8.7.

The walk-forward in §6 is exactly the test of this, so no change is proposed.
**The run must print n_eff per weekend and the weekly member turnover rate,**
so the result can be read against this warning.

## Not blocking, noted for the operator

The §10 criterion that full-period MTM DD must land inside 35–40% is a
two-sided band on one realised number. A basket could have a genuine edge and
still fail it by landing at 33% or 42%. The amendment already records the edge
result separately in that case, which is the right handling.

## Status

No run yet. No order, no autotrader restart, no PR. **NO TRADE.**
