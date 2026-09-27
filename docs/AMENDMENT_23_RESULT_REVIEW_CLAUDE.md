# Amendment 23 result — Claude's review

**Written 2026-09-27.** Reviewer role under `docs/OWNERSHIP.md`. Codex's
verdict stands: **FAIL FOR PROMOTION**, and DD sizing correctly not run.

## Verified

- Codex's tests (`research/pilot/test_basket_dd.py`): **4/4 pass**, run
  directly by Claude. There is no pytest on this machine, so each test function
  was called in turn.
- Headline figures were recomputed by Claude from the admitted order list
  (`research/pilot/recheck_basket_costs.py`). They match Codex **exactly** in
  every window, at both base and 1.5x cost.
- 1.5x stress adds half of the full execution cost (spread, commission and
  slippage) per trade. That is correct: the base result already carries the
  spread through Bid/Ask geometry.
- Weekly returns are binned by exit time (clarification A), so a weekend's
  ranking sees only trades resolved before it.
- Windows sum consistently: 44-month + trailing = full, for net R, for stress R
  and for trades.

## The finding that matters: cost, not reading

| window | trades | gross edge / trade (before cost) | cost / trade | cost as share of gross | net / trade | median stop |
|---|---:|---:|---:|---:|---:|---:|
| 44-month | 11,943 | +0.1308 R | 0.1178 R | **90.0%** | +0.0131 R | **$2.60** |
| trailing 12m | 5,308 | +0.1686 R | 0.0552 R | **32.7%** | +0.1135 R | **$5.11** |
| full | 17,251 | +0.1425 R | 0.0985 R | 69.1% | +0.0439 R | $3.28 |

(per-trade means, unweighted; mean member weight 0.20–0.22)

The basket's **selection edge before cost was positive in both periods, and of
similar size**: +0.13 R per trade in the 44 months, +0.17 R in the last year.
What changed is the stop size. Cost is roughly fixed in dollars per trade. In
2022–2025 gold's volatility gave a median stop of $2.60, so cost ate 90% of the
edge, and a 1.5x cost increase turned it negative. In the last year the median
stop is $5.11, so the same dollar cost is only a third of the edge.

## Correction to Claude's earlier 44-month diagnosis

`docs/DIAGNOSIS_44_MONTH_LOSS_2026-09-26.md` concluded the loss was closer to
"the scope could not read that market". That conclusion measured every fixed
grid cell **after cost**. The basket shows that the weekly selector **did**
find a positive gross edge in 2022–2025. The binding problem was **edge too
small relative to cost at that period's volatility**, not an absence of edge.
The earlier conclusion is revised accordingly.

## Minor fidelity note, not a look-ahead defect

Each cell's trade list in the universe cache was built as if the cell traded
continuously, one position at a time. A cell's position from a week when it
was not in the basket can therefore block a signal in the week it is
selected. This uses no future information and is small. Noted for the next
engine revision.

## Implications for the next amendment (Codex leads)

1. The natural next design gates or scales by **cost as a share of R**, or
   prefers wider-stop / higher-timeframe members when volatility is low. It
   must be written as a new amendment before it runs.
2. **The 44-month window has now been seen.** A design built to fix what this
   run revealed is no longer blind to that window. Its 44-month result must be
   reported as *informed by Amendment 23*, and genuine confirmation has to come
   from data after the design is frozen: forward Demo observation or weeks not
   yet seen.
3. DD sizing remains unevaluated. Nothing here licenses a Demo or real-money
   change.

**NO TRADE.** No order sent, no autotrader restart, no PR.
