# Who owns what — updated 2026-09-27 (sixth revision)

**Claude leads. Codex is secondary, called in only when Claude specifically
needs it**, at the operator's direct instruction, to conserve Codex's token
budget. The fifth revision (co-development) is superseded.

Revision history, kept visible: (1) Claude=W1 / Codex=rest, (2) Codex=all,
(3) Claude=W1 / Codex=rest, (4) Claude=all / Codex paused, (5) Claude and
Codex co-develop, (6) this one — Claude leads.

## What that means operationally

- Claude builds, tests, and runs new work directly instead of routing it
  through Codex first.
- Codex is not paused. Claude may still ask Codex to review a specific
  Claude-authored design, or to do a bounded task Claude cannot do itself
  (e.g. anything requiring the Codex sandbox specifically), but that is the
  exception, not the default path.
- Every result Claude produces alone still gets the same rigor this project
  has required throughout: pre-register before running, no look-ahead, real
  Demo90 cost model, report failure as plainly as success.

## The operator's target for this phase (unchanged)

1. **Not fixed to one tool.** A basket of several tools, chosen and
   re-weighted at each Weekend Rebuild.
2. **Size the basket so its maximum drawdown lands at 35–40%.**
3. Stay inside the nine rules (Amendment 22 and its addendum).

## Where things stand (2026-09-27)

- **Amendment 26**: causal (non-look-ahead) chain built and verified. On it,
  no tested policy survives the full 2022–2026 history. Only Amendment 24's
  basket is positive in the trailing 12 months, at both base and 1.5x cost.
  That is seen development data, not confirmation.
- **Amendment 27**: A24 on the causal chain frozen for a 26-week read-only
  forward shadow ledger, plus an inactive optional Demo mirror (magic
  20260927). Implemented, all audits pass, **clock not started** — the first
  Weekend Rebuild after commit is Saturday 2026-10-03.
- **Next (Claude-led):** a new pre-registered design attacking the actual
  open problem — cost relative to volatility/stop size at low-volatility
  regimes — since gating on cost/R alone (Amendment 24) was not enough. Must
  be pre-registered and frozen before it runs, per every prior amendment.

## W1

Unchanged. Still Claude's. Rollover probe scheduled Mon 2026-09-28 21:52 UTC.

## Standing rules, unchanged

- no real-money order without the operator's explicit confirmation on that
  specific order
- Demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime
- no Grid, no Martingale, no averaging
- no PR until there is evidence ready to inspect
- NOT ASSESSED rather than a guess, always
- a Demo execution change needs a verified walk-forward result and review

The engine's answer remains **NO TRADE**.
