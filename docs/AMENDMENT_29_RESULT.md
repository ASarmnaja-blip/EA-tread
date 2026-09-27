# Amendment 29 result — the frozen A24/A26 mechanism does not generalize to GBPUSD

**Run 2026-09-27, by Claude directly.** Pre-registered `ec386eb` before this
result existed. **Result: negative in every window, under both slippage
scenarios, with no exception.** This is a clean, unambiguous failure of the
generalization test.

## Result

| window | slippage=0, base | slippage=0, 1.5x | slippage=spread, base | slippage=spread, 1.5x | trades |
|---|---:|---:|---:|---:|---:|
| first half (2021-08 – 2024-02) | −0.482 | −22.367 | −5.387 | −25.763 | ~4,600–5,300 |
| second half (2024-02 – 2026-09) | −52.966 | −75.479 | −43.696 | −66.402 | ~4,600–5,000 |
| full (2021-08 – 2026-09) | −53.448 | −97.845 | −49.084 | −92.164 | ~9,200–10,300 |

Even the deliberately optimistic zero-slippage scenario is negative in the
second half and the full period. Active weeks were 80.7–100%, so this is not
an idle-basket artifact.

**Limitation carried over from the pre-registration:** GBPUSD short swap is
architecturally not charged by this codebase (`opportunities_from_decisions`
only applies `E.SWAP_LONG`, and only when `direction > 0`), so short trades
here are understated in cost by GBPUSD's real (small) short swap. This makes
the result, if anything, slightly *more* favourable than reality — it does
not explain the loss.

## Reading

The mechanism — six declared families, Amendment 26's causal chain,
Amendment 24's 1/12-friction gate, three-week-decay LCB selection, the same
basket rules, applied completely unchanged — does not find a tradable edge
on an instrument it has never touched. This is informative in a specific,
limited way:

1. **It does not disprove XAUUSD's trailing-12-month result**, which stands
   on its own evidence (or lack of it) and will be judged by Amendment 27's
   forward clock regardless.
2. **It is consistent with, not contradicted by,** the independent finding
   recorded in ledger Part 11 (a completely separate 9-14-market FX research
   program): real short-horizon structure can exist and still lose money
   after realistic cost, because the structure is small relative to what
   execution costs. A negative result here is the *expected* outcome under
   that finding, not a surprise.
3. **It weakens, rather than strengthens, any case for skipping XAUUSD's
   forward wait.** If the general mechanism does not transfer to a second
   market, that lowers (not raises) confidence that XAUUSD's specific
   positive window reflects a real, general phenomenon rather than a
   XAUUSD-specific historical accident.

## What this does not settle

Ledger Part 11's open audit item — whether R normalized by ATR-derived stop
distance is neutral for these six families, or biased by a correlation
between entry conditions and ATR — has still not been checked, on either
XAUUSD or GBPUSD. This result should not be read as a clean falsification of
the mechanism in general; it is a clean falsification of *this specific
frozen policy, measured this specific way,* on GBPUSD.

## What happens next

Nothing is changed automatically in response to this result. No new design
is registered tonight in reaction to it — repeatedly adjusting a design
after each unfavourable result on a fixed, fully-visible historical dataset
is the exact failure mode Amendment 10 already demonstrated on this
project's own data (a winner selected from 6,480 candidates regressed
through zero, not toward it, on unseen data). A follow-up hypothesis, if and
when one is well-reasoned enough to justify a new pre-registration, is a
separate decision for a separate session.

Amendment 27's forward shadow ledger is unaffected by this result and
remains the primary open question. Its first Weekend Rebuild is Saturday
2026-10-03.

**NO TRADE.** No order sent, no autotrader touched, no PR.
