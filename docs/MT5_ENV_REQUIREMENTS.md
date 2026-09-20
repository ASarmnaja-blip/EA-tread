# What the export needs, and why it cannot run here

## The blocker, verified rather than assumed

```
$ uname -s -r
Linux 6.18.44-fc-v37
$ pip install MetaTrader5
ERROR: Could not find a version that satisfies the requirement MetaTrader5
       (from versions: none)
```

The `MetaTrader5` package ships **Windows wheels only** — there is no Linux
build to install, not a missing dependency I could add. It also does not talk
to a broker on its own: it attaches to a **running MetaTrader 5 terminal** over
local IPC and reads what that terminal already has. Two things this container
has neither of.

## What the machine running the export needs

| # | Requirement | Check |
|---|---|---|
| 1 | **Windows** (or a Wine prefix with MT5 installed) | `MetaTrader5` has no Linux wheel |
| 2 | **MetaTrader 5 terminal installed, running, and logged in** | the package attaches to it; it is not a broker API client |
| 3 | **Python 3.8–3.12, 64-bit, on that same machine** | the wheel is CPython-ABI specific and IPC is local |
| 4 | `pip install MetaTrader5 pandas` | |
| 5 | The gold symbol **visible in Market Watch** | the script calls `symbol_select` but a hidden symbol can still return nothing |
| 6 | **History actually downloaded**, M1 especially | brokers serve M1 lazily. Open the M1 chart, press **Home**, scroll back until it stops loading |
| 7 | Terminal connected to the broker | the offset is read from a live tick |

## Could it be made to run here?

Only through Wine plus a full terminal install plus a broker login inside the
container. That is a large amount of moving parts to reproduce something your
machine already does in one command, and the login would put broker credentials
in an ephemeral container. Not worth it.

## The command

```bash
pip install MetaTrader5 pandas
cd <your clone>
git pull
python tools/mt5_export_all.py
```

Nothing to fill in: it finds the symbol, measures the server offset, pulls M1
and M5, and writes everything to `data/mt5_export_report.txt`. Send that one
file back. The CSVs stay with you.

**It places no order.** It calls `copy_rates_range` and `symbol_info_tick` and
nothing else that touches an account.

---

## Status: export blocked — 2026-09-20

**No MT5 terminal is reachable from this environment, so the export has not
run.** Requirements 1–7 above are the specific list of what is missing.

### Substitution is not permitted

User decision of 2026-09-20: the engine is to be measured on **real XAUUSD M1
and M5 from the broker's own MetaTrader 5 terminal, and nothing else.**

| Candidate stand-in | Ruling |
|---|---|
| `GC=F` COMEX gold futures | **not a substitute** — different instrument, different microstructure, no bid/ask |
| `MGC=F`, `GLD` | **not a substitute**, same reasons |
| Synthetic or simulated prices | **not a substitute** for any market claim |

Synthetic series keep exactly one job, unchanged: **calibrating the
instrument** on data whose true answer is known to be zero. That is not a
market measurement and is never reported as one.

The consequence is recorded plainly: **until the export lands, nothing in this
project may state anything about XAUUSD.** Work continues on the parts that can
be built and tested without it — the news layer, the regime score and the
decision assembler — none of which needs a price to be tested, because every
case they are tested on has a known answer.
