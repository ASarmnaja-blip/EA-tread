"""Unattended weekly run of the WPWB risk report (scheduled Saturday 06:00
Thai time, after the Friday 22:15 UTC cut). Operator-approved 2026-09-28.

1. Refresh the economic calendar: close the MT5 terminal gracefully, start it
   with data/mt5_calendar_dump.ini (runs the read-only CalendarDump script and
   shuts down), validate the dump, back up and replace data/calendar.csv.
   If the dump does not refresh (e.g. an MT5 LiveUpdate waiting for a UAC
   prompt) it is logged and the report says the calendar is stale.
2. Start MT5 normally again (the operator's terminal is restored).
3. weekly_report.py --fetch (read-only bars) and episodes.py.
4. outlook_shadow.py: shadow log of next-week volatility forecasts (downloads the
   Cboe GVZ file once; operator permission 2026-09-29). Changes no sizing.
Everything is logged to data/wpwb_weekly/run_logs/<date>.log. Nothing here
can place an order.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DATA_PATH = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "D0E8209F77C8CF37AD8BF550E51FF075"
DUMP = DATA_PATH / "MQL5" / "Files" / "calendar_dump.csv"
INI = ROOT / "data" / "mt5_calendar_dump.ini"
CAL = ROOT / "data" / "calendar.csv"
BACKUPS = ROOT / "data" / "calendar_backups"
LOGDIR = ROOT / "data" / "wpwb_weekly" / "run_logs"
PY = sys.executable

_log_file = None


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    if _log_file:
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def main_terminal_pids():
    out = ps(f"Get-Process terminal64 -ErrorAction SilentlyContinue | "
             f"Where-Object {{ $_.Path -eq '{TERMINAL}' }} | ForEach-Object {{ $_.Id }}")
    return [int(x) for x in out.split() if x.strip().isdigit()]


_MT5_PROBE = r"""
import sys, MetaTrader5 as mt5
if not mt5.initialize():
    print("NOINIT"); sys.exit(0)
try:
    if sys.argv[1] == "safe":      # force-closing is allowed only on a demo account with nothing open
        a = mt5.account_info()
        print("SAFE" if a is not None and a.trade_mode == 0 and mt5.positions_total() == 0 and mt5.orders_total() == 0 else "UNSAFE")
    elif mt5.account_info() is None or not mt5.terminal_info().connected:
        print("NOT_LOGGED_IN")     # a restart cannot fix this and no code here ever types a password
    else:                          # health: bar history calls must work, not just the live quote
        mt5.symbol_select("XAUUSD", True)
        r = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M1, 0, 5)
        print("HEALTHY" if r is not None and len(r) == 5 else f"UNHEALTHY {mt5.last_error()}")
finally:
    mt5.shutdown()
"""


def mt5_probe(kind):
    try:
        r = subprocess.run([PY, "-c", _MT5_PROBE, kind], capture_output=True, text=True, timeout=120)
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "NOOUTPUT"
    except Exception as e:
        return f"ERROR {e!r}"


def close_terminal(wait=90):
    """Graceful close first; if MT5 ignores it (seen 2026-09-30), force-stop - but only on a demo account with no open
    position or pending order (operator 2026-09-30: restarting MT5 is Claude's job)."""
    pids = main_terminal_pids()
    if not pids:
        return True
    ps(f"Get-Process -Id {','.join(map(str, pids))} | ForEach-Object {{ $null = $_.CloseMainWindow() }}")
    t0 = time.time()
    while time.time() - t0 < wait:
        if not main_terminal_pids():
            return True
        time.sleep(3)
    safe = mt5_probe("safe")
    if safe != "SAFE":
        log(f"MT5 ignored the graceful close and force-stop is not allowed ({safe})")
        return False
    ps(f"Stop-Process -Id {','.join(map(str, main_terminal_pids()))} -Force -Confirm:$false")
    t0 = time.time()
    while time.time() - t0 < 30:
        if not main_terminal_pids():
            log("MT5 did not close gracefully; force-stopped (demo, nothing open)")
            return True
        time.sleep(2)
    return False


def dump_calendar():
    before = DUMP.stat().st_mtime if DUMP.exists() else 0
    if not close_terminal():
        log("MT5 did not close gracefully; calendar not refreshed")
        return False
    log("MT5 closed; starting CalendarDump config")
    p = subprocess.Popen([TERMINAL, f"/config:{INI}"])
    t0 = time.time()
    while time.time() - t0 < 300:
        if DUMP.exists() and DUMP.stat().st_mtime > before and p.poll() is not None:
            break
        time.sleep(5)
    if not DUMP.exists() or DUMP.stat().st_mtime <= before:
        log("calendar dump NOT refreshed (MT5 update or UAC prompt pending?)")
        return False
    sys.path.insert(0, str(ROOT / "research" / "pilot"))
    import calendar_feed
    new = calendar_feed.load_calendar(str(DUMP))
    old = calendar_feed.load_calendar(str(CAL))
    # Codex R16: the dump starts 2025-04 while the file starts 2022, so MERGE instead of replacing:
    # rows of the new dump replace the same value_id, older rows are kept. Reject only a dump that ends
    # before the current file or that is empty.
    if len(new) == 0 or new.epoch.max() < old.epoch.max():
        log(f"new dump rejected: rows {len(new)}, max {new.time.max() if len(new) else None} vs {old.time.max()}")
        return False
    import pandas as pd
    import io

    def _txt(pth):                      # MQL5 writes the ANSI codepage; the merged file keeps UTF-8
        raw = pth.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1252")
    raw_old = pd.read_csv(io.StringIO(_txt(CAL)), dtype=str, keep_default_na=False)
    raw_new = pd.read_csv(io.StringIO(_txt(DUMP)), dtype=str, keep_default_na=False)
    merged = pd.concat([raw_old[~raw_old.value_id.isin(set(raw_new.value_id))], raw_new]).sort_values(["time", "value_id"], kind="stable")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CAL, BACKUPS / f"calendar_{datetime.now():%Y%m%d_%H%M}.csv")
    merged.to_csv(CAL, index=False, encoding="utf-8")
    log(f"calendar merged: {len(raw_new):,} dumped rows into {len(merged):,} total, to {new.time.max()}")
    try:  # point-in-time calendar for the news panel (append-only, first-published actuals)
        r = subprocess.run([PY, str(ROOT / "research" / "foundry" / "calendar_pit.py"), str(DUMP)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
        log(f"calendar_pit.py exit {r.returncode}: {r.stdout.strip()[-300:]}")
    except Exception as e:
        log(f"calendar_pit error: {e!r}")
    return True


def ensure_terminal():
    if not main_terminal_pids():
        subprocess.Popen([TERMINAL])
        log("MT5 started normally")
        time.sleep(45)
    for attempt in range(3):         # a running terminal can still fail every history call ("Terminal: Call failed")
        h = mt5_probe("health")
        if h == "HEALTHY":
            if attempt:
                log(f"MT5 healthy after {attempt} restart(s)")
            return True
        if h == "NOT_LOGGED_IN":
            log("MT5 is not logged in (saved login missing?) - the operator must log in; no restart, no password entry")
            break
        log(f"MT5 health check failed ({h}); restarting (attempt {attempt + 1} of at most 2)")
        if attempt == 2 or not close_terminal():
            break
        subprocess.Popen([TERMINAL])
        time.sleep(60)
    log("MT5 still unhealthy; the report continues and data steps will fail closed")
    return False


def run(script, *args):
    r = subprocess.run([PY, str(ROOT / "research" / "wpwb_weekly" / script), *args],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=1800)
    log(f"{script} exit {r.returncode}: {r.stdout.strip()[-600:]}")
    if r.returncode:
        log(f"stderr: {r.stderr.strip()[-1500:]}")
    return r.returncode


def main() -> int:
    global _log_file
    LOGDIR.mkdir(parents=True, exist_ok=True)
    _log_file = LOGDIR / f"{datetime.now():%Y-%m-%d_%H%M}.log"
    log(f"WPWB weekly run start (UTC {datetime.now(timezone.utc):%Y-%m-%d %H:%M})")
    skip_dump = "--no-dump" in sys.argv
    if not skip_dump:
        try:
            dump_calendar()
        except Exception as e:  # never let the calendar block the report
            log(f"calendar step error: {e!r}")
    ensure_terminal()
    rc = run("weekly_report.py", "--fetch")
    run("episodes.py")
    try:  # shadow only (docs/WPWB_OUTLOOK_SHADOW_PREREG.md): never alters or blocks the report
        run("outlook_shadow.py")
    except Exception as e:
        log(f"outlook shadow error: {e!r}")
    try:  # paper-only selector record (docs/FOUNDRY_SHADOW_PREREG.md); never alters the report
        r = subprocess.run([PY, str(ROOT / "research" / "foundry" / "selector_shadow.py")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=3600)
        log(f"selector_shadow.py exit {r.returncode}: {r.stdout.strip()[-400:]}")
    except Exception as e:
        log(f"selector shadow error: {e!r}")
    try:  # paper-only HOD21 record (docs/FOUNDRY_SHADOW_PREREG.md Amendment 2)
        r = subprocess.run([PY, str(ROOT / "research" / "foundry" / "hod21_shadow.py")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=1800)
        log(f"hod21_shadow.py exit {r.returncode}: {r.stdout.strip()[-300:]}")
    except Exception as e:
        log(f"hod21 shadow error: {e!r}")
    try:  # paper-only Foundry forward panel (Amendment 6, H-FOUNDRY-PANEL-1)
        r = subprocess.run([PY, str(ROOT / "research" / "foundry" / "forward_panel.py")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=3600)
        log(f"forward_panel.py exit {r.returncode}: {r.stdout.strip()[-500:]}")
    except Exception as e:
        log(f"forward panel error: {e!r}")
    try:  # one Thai page for the operator
        r = subprocess.run([PY, str(ROOT / "research" / "foundry" / "weekly_summary_th.py")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=600)
        log(f"weekly_summary_th.py exit {r.returncode}: {r.stdout.strip()[-200:]}")
    except Exception as e:
        log(f"summary error: {e!r}")
    log("done")
    return rc


if __name__ == "__main__":
    sys.exit(main())
