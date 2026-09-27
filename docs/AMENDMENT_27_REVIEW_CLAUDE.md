# Amendment 27 — Claude's pre-implementation review

**Written 2026-09-27, before any Amendment 27 code, forward record or order.**

**Verdict: approved, with one binding clarification.** The clarification is
recorded here, before implementation, in the same way Amendment 23's
clarification A was. It is binding on the implementation.

## Why it is approved

- It freezes A24 exactly and changes only the candidate chain. The
  development figures are labelled NOT BLIND, and nothing is backfilled.
- The weighted shadow ledger is the only confirmation statistic. The Demo
  mirror, which trades an equal minimum lot per event, is correctly treated
  as execution evidence only.
- Account safety is account-wide: projected drawdown to every visible SL, a
  35% soft limit and a 40% hard limit, and an A27-only 10% kill switch. Every
  loop fails closed on non-Demo, missing SL, stale quote or a changed minimum
  lot. Magic numbers are separated from the payoff bot and W1, and W1's
  refusal to trade while any position is open is kept.
- The 26-week clock is fixed, with no early promotion and no extension, and
  zero weeks count.
- A logger outage is logged as an audit failure, not as a zero week. That is
  the correct handling.

## Binding clarification A — the shadow gate uses bar data, not the live quote

§2.2 says: "Live shadow and Demo decisions use the executable quote known
immediately before submission in place of the historical `sp[k-1]` proxy."

- **The shadow ledger must use `max(sp[k-1], 0.090)` from the ingested M5
  bars**, exactly as in development. There are two reasons. First, the
  forward test must measure the same frozen policy that was measured
  historically. Second, the shadow ledger must be reproducible later from the
  hash-chained bar data alone. A live quote is neither.
- **The live executable spread is recorded next to each shadow event** as a
  diagnostic, and **governs only the Demo mirror's submission**, together with
  the 0.135 spread cap.
- Where the two disagree (for example, the shadow admits but the live gate
  rejects), the shadow event stands and the Demo row records the rejection
  reason. §8 is judged on the shadow ledger alone.

## Notes, not blocking

1. §3 lists the canonical NPZ **file** SHA-256 (`DFA12A…`). The content digest
   used everywhere else is `613d5e…`. Record both in the activation record.
2. Each Weekend Rebuild has to extend the 330 raw streams with the new week's
   bars. Build time must fit between the Friday close and the Saturday
   decision record. If a rebuild misses the cutoff, that is §4's
   `DATA/AUDIT FAILURE`, not a late decision.
3. Timing: if the logger passes its §9 audits before the Weekend Rebuild on
   Saturday 2026-10-03, week 1 is the market week that starts on 2026-10-04 or
   2026-10-05, depending on the broker's open.

## What is authorised next

Build and audit the read-only forward logger (§10). The Demo mirror may be
built and tested in the same pass, but it must **not be activated** until its
implementation is reviewed. The operator has already said Demo orders are
acceptable. Activation still passes through this review step.

**NO RUN, NO ORDER.** No PR.
