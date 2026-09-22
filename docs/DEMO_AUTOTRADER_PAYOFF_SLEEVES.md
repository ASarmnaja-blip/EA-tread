# Demo payoff-sleeve autotrader

This is a demo-only operational wrapper for the three fixed payoff sleeves
identified on 2026-09-22. It is not evidence that the sleeves have a persistent
edge. It uses M15 decisions, enters only in the immediately following M5 bar,
and resolves exits with attached stop loss / take profit plus a 144-M5 time exit.

The configuration is fixed: every eligible A, B and C signal uses the broker's
minimum volume (currently 0.01 lot). It requires an MT5 hedging demo account so
each signal keeps its own stop, target and time exit. It rejects a live spread
above 0.135 price units and stops new orders at a 40% peak-to-equity drawdown. A
stop during a market gap can exceed the limit; the drawdown stop is a circuit
breaker, not a guarantee.

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
