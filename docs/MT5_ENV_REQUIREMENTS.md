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
