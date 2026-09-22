# Demo payoff-sleeve autotrader

This is a demo-only operational wrapper for the three fixed payoff sleeves
identified on 2026-09-22. It is not evidence that the sleeves have a persistent
edge. It uses M15 decisions, enters only in the immediately following M5 bar,
and resolves exits with attached stop loss / take profit plus a 144-M5 time exit.

The configuration is fixed: A risks 2.0%, B 2.3%, C 2.0%. It permits only one
open MT5 position, rejects a live spread above 0.135 price units, and stops new
orders at a 40% peak-to-equity drawdown. A stop during a market gap can exceed
the limit; the drawdown stop is a circuit breaker, not a guarantee.

Run a read-only cycle:

```powershell
python research/pilot/payoff_demo_autotrader.py
```

The live invocation is intentionally separate and checks `ACCOUNT_TRADE_MODE_DEMO`
on every loop:

```powershell
python research/pilot/payoff_demo_autotrader.py --live --loop
```

State and execution logs live under `data/`, which is ignored by git. Never run
this against a real-money account.
