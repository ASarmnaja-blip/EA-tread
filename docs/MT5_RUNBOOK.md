# MT5 runbook — what to run on your machine, and what to send back

## Where the project stands

| Thing | State |
|---|---|
| Track 1.1 / 1.2 (EA schema + decision log) | **AUTHORED**, not verified. 40 container-side checks pass; C1–C7 and R1–R8 still need MetaEditor and the Strategy Tester |
| Setup pilot on COMEX futures | **PAUSED pending real XAUUSD data** — decision of 2026-09-20 |
| A3b calibration failure (S3V2) | **not ruled on.** Deferred: the whole calibration will be redone on real XAUUSD rather than argued over on the proxy |
| S3 / S5 earlier readings | **UNINTERPRETABLE**, unchanged |
| Real money | never, and nothing here goes near it |

The two jobs below are the ones that unblock everything else. Neither places an
order.

---

## Job 1 — export XAUUSD, with the spread your broker actually charged

This is the bigger of the two. The export carries **MT5's own per-bar spread**,
so the cost side of every future result stops being an assumption. It also
gives M1 over years instead of the eight days the free feed allowed, which
removes the exit-resolution compromise the pilot was built around.

```bash
pip install MetaTrader5 pandas
cd <your clone of EA-tread>

# 1. the real symbol name differs by broker: XAUUSD, XAUUSD.m, XAUUSDm, GOLD, XAUUSD#
python tools/export_mt5_data.py --list
```

### 1a. The server offset — do this before the export

`mt5.copy_rates_range` returns **broker server time**, not UTC, and the meta
file does not record the offset. Every session split downstream depends on it,
and a wrong offset is invisible in a summary and fatal in a session-split
result. Replace `XAUUSD` with the name `--list` printed:

```bash
python -c "import MetaTrader5 as mt5, datetime as dt; mt5.initialize(); \
t=mt5.symbol_info_tick('XAUUSD').time; \
print('server offset hours =', round((t-dt.datetime.now(dt.timezone.utc).timestamp())/3600)); \
mt5.shutdown()"
```

Send me that number. Usually +2 or +3 for European brokers.

### 1b. The exports

```bash
python tools/export_mt5_data.py --symbol XAUUSD --timeframe M1 --years 3
python tools/export_mt5_data.py --symbol XAUUSD --timeframe M5 --years 3
```

If M1 comes back short or empty, the terminal has not downloaded that history
yet: open an XAUUSD M1 chart, press **Home** and scroll back until it stops
loading, then re-run. Brokers often keep far less M1 than M5 — whatever you get
is what we work with, so just report the range it prints.

### What to send back

The console output of both runs. It already contains everything I need:

- symbol, digits, point, contract size, min lot
- bar count and date range
- **intraday gap count** — the data-quality gate
- the **spread table by hour**, mean / median / p90 / max

Plus the offset number from 1a. The CSVs stay on your machine — they are
gitignored and I do not need the files themselves to plan the next step.

---

## Job 2 — SpreadMonitor on a demo account, with trading switched off

The export gives historical spread as the broker *recorded* it. This measures
what it is *right now*, tick by tick, and the two disagreeing would itself be
worth knowing.

1. Copy `MQL5/Experts/XAUM15/` and `MQL5/Include/XAUM15/` into your terminal's
   data folder (**File → Open Data Folder**, then `MQL5/Experts/` and
   `MQL5/Include/`).
2. **F7** on the `.mq5` in MetaEditor. Report any error or warning — that is
   C1–C7 of the pending regression, and it costs you nothing extra here.
3. Attach to an **XAUUSD M15** chart with:

   | Input | Value | Why |
   |---|---|---|
   | **`InpEnableTrading`** | **`false`** | **the safety catch. Nothing else matters if this is wrong** |
   | `InpWriteDecisionLog` | `true` | fills the Track 1.2 log with real bars |

4. Leave it running. Detach after ~20 trading days.

**Why this cannot trade:** `OnTick` calls `g_spread.Sample()` on every tick
*before* any gate, while `EntryGatesPass()` returns false on its first line when
`InpEnableTrading` is false. So the monitor accrues and the order path is never
reached. Confirm the journal shows no `[ENTRY]` line, ever.

On deinit it prints the hour-by-hour table and writes
`XAUM15_spread_by_hour.csv` into the terminal's `MQL5/Files/`. Send me the
printed table and the deinit block.

---

## What I do with it

1. Point the pilot at the real series (`data.load_csv`, already written, with a
   hard error if the offset is missing).
2. Re-run the whole Amendment 01 calibration on **real XAUUSD** — including the
   A3b scenario that failed on the proxy. If it fails there too, that is a real
   instrument problem rather than the borderline false positive it looks like
   now.
3. Only after that calibration passes, re-run P1, and only after P1 passes, read
   market prices.

The order does not change because the data got better.

---

## Job 2, in detail — the no-trade proof, line by line

Before attaching anything, here is why `InpEnableTrading = false` is sufficient,
checked against the source rather than asserted. Line numbers are in
`MQL5/Experts/XAUM15/XAU_M15_Institutional_Adaptive.mq5` at commit `308681e`.

| Step | Line | What it establishes |
|---|---|---|
| `g_spread.Sample(now, g_broker.Spread())` | **637** | runs on **every tick**, inside `OnTick`, **before** the new-bar block at 654. The monitor accrues whatever else is switched off |
| `if(!InpEnableTrading) { why="trading disabled"; return false; }` | **320** | the **first line** of `EntryGatesPass`. Nothing after it is evaluated |
| `if(gatePassed) TryEnter(now);` | **665** | the **only** call site of `TryEnter` |
| `if(g_tm.OpenSetup(...))` | **479** | the **only** call that opens a position, and it sits inside `TryEnter` |
| `if(... && g_tm.hasOpenSetup) g_tm.CloseAll(...)` | **639**, 642 | the close paths are guarded by `hasOpenSetup`, which can only become true through 479 |

So: gates refuse at 320 → 665 never calls `TryEnter` → 479 never runs →
`hasOpenSetup` stays false → the close paths at 639 and 642 are unreachable
too. **No order path in the file is reachable.** The spread sampler at 637 sits
upstream of all of it and keeps working.

### Attach checklist

- [ ] Account is a **demo** account. The report script prints `DEMO` or `LIVE`
      at the top — check it
- [ ] `InpEnableTrading` = **`false`**
- [ ] `InpWriteDecisionLog` = `true`
- [ ] Chart is **XAUUSD M15** (the EA warns on any other period)
- [ ] Algo trading enabled in the terminal, otherwise the EA never gets ticks
      and the monitor records nothing

### After the first hour, confirm

- [ ] Journal has **no** `[ENTRY]` line — not one, ever
- [ ] Terminal → Trade tab shows **no open position** and **no pending order**
- [ ] The dashboard reads `DISABLED`
- [ ] `MQL5/Files/XAUM15_decisions.csv` is growing, and every row has
      `decision = NO_TRADE` with `decision_reason` starting
      `gate_blocked_before_evaluation: trading disabled`

That last one is a live test of Track 1.2 as a side effect: it is the first time
the decision log has run against real bars.

### After about 20 trading days

Remove the EA from the chart. On deinit it prints the hour-by-hour spread table
and writes `MQL5/Files/XAUM15_spread_by_hour.csv`. Send the printed block.
