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


def close_terminal(wait=90):
    pids = main_terminal_pids()
    if not pids:
        return True
    ps(f"Get-Process -Id {','.join(map(str, pids))} | ForEach-Object {{ $null = $_.CloseMainWindow() }}")
    t0 = time.time()
    while time.time() - t0 < wait:
        if not main_terminal_pids():
            return True
        time.sleep(3)
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
    if len(new) < 0.9 * len(old) or new.epoch.max() < old.epoch.max():
        log(f"new dump rejected: rows {len(new)} vs {len(old)}, max {new.time.max()} vs {old.time.max()}")
        return False
    BACKUPS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CAL, BACKUPS / f"calendar_{datetime.now():%Y%m%d_%H%M}.csv")
    shutil.copy2(DUMP, CAL)
    log(f"calendar refreshed: {len(new):,} rows to {new.time.max()}")
    return True


def ensure_terminal():
    if main_terminal_pids():
        return
    subprocess.Popen([TERMINAL])
    log("MT5 started normally")
    time.sleep(45)


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
    log("done")
    return rc


if __name__ == "__main__":
    sys.exit(main())
