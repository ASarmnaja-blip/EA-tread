# Amendment 28 result — regime stand-aside helps, does not flip the 44-month verdict

**Run 2026-09-27, by Claude directly (ownership sixth revision).**
**Verdict per the amendment's own pre-registered section 6: FAILS to fully
work** — the 44-month window is still negative at 1.5x cost. It does not
damage the trailing-12-month result. Reported honestly rather than adjusted.

All figures below are **NOT BLIND** — this design was written after seeing
Amendment 24/26's cost decomposition.

## Audit

`AUDIT_FUTURE_MUTATION_INVARIANT=True` — the regime percentile at a fixed
cutoff is unchanged when every bar after that cutoff is mutated (tripled and
shifted). The measure is causal.

## Result

| window | policy | base net R | 1.5x net R | trades | active weeks |
|---|---|---:|---:|---:|---:|
| 44-month | A24 baseline (no stand-aside) | −80.397 | −109.119 | 5,855 | 99.5% |
| 44-month | **A28 (stand-aside)** | **−69.467** | **−93.428** | 5,023 | 82.1% |
| trailing 12m | A24 baseline | +31.643 | +18.000 | 3,627 | 100.0% |
| trailing 12m | **A28** | **+31.643** | **+18.000** | 3,627 | 100.0% |
| full | A24 baseline | −48.754 | −91.119 | 9,482 | 100.0% |
| full | **A28** | **−37.824** | **−75.427** | 8,650 | 86.2% |

**Stand-aside weeks: 49 of 273 (17.9%) overall — 37 of 194 (19.1%) in the
44-month window, 0 of 52 (0%) in the trailing 12 months.** The rule fired
almost exactly where the hypothesis said it should, and never touched the one
window that was already working.

## Reading

1. **The mechanism is doing what it was designed to do.** Standing aside in
   the bottom 40% of trailing-year volatility improved the 44-month result by
   +10.9 R at base cost and +15.7 R at 1.5x cost, entirely by removing weeks,
   never by changing a single trade's outcome — and it left the trailing
   12 months byte-for-byte identical.
2. **It is not enough.** −93.428 R at 1.5x cost over 44 months is still a
   clear loss. Section 6 of the pre-registration said in advance that this
   result counts as "did not work," and it is reported as exactly that — not
   softened, not re-parameterized.
3. **No threshold sweep is authorized here.** The pre-registration froze 0.40
   before this ran specifically so a better-looking number couldn't be
   found by trying 0.35, 0.45, etc. after seeing this result. A sweep is a
   different, new amendment, starting its own NOT BLIND disclosure from
   scratch.

## What this does and does not change

- Amendment 27's forward shadow ledger is unaffected: it still freezes plain
  Amendment 24 on the causal chain, per its own frozen text. This result is
  not swapped in.
- This is one more piece for the guideline library (rule 9): removing the
  worst-volatility weeks helps but the remaining edge-to-cost ratio in the
  44-month regime is still too thin, even after removing its quietest 40%.
  A cost-vs-volatility fix at the *trade* level (e.g., volatility-scaled
  targets) remains untried and is a candidate for a future amendment.

**NO TRADE.** No order sent, no autotrader touched, no PR.
