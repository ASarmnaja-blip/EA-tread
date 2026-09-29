"""Supervisor: keep the Dukascopy hourly download running until the cache is
complete, restarting it if the machine or the process drops it. Read-only
network fetches; writes only into data/history/dukascopy/cache/."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "history" / "dukascopy" / "cache" / "hour"
LOG = ROOT / "data" / "history" / "dl.log"
TARGET = "202609.npy"
PY = sys.executable


def log(msg):
    line = f"{datetime.now():%H:%M:%S} [supervisor] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def done():
    return (CACHE / "BID" / TARGET).exists() and (CACHE / "ASK" / TARGET).exists()


def kill_strays():
    """Two downloaders at once double the request rate and fight over the same
    files, so clear any left over from a previous run (e.g. a supervisor killed
    by a power cut leaves its child behind)."""
    me = os.getpid()
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -match 'dukascopy_m1|keep_downloading' } | "
         "ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True)
    for pid in (int(x) for x in ps.stdout.split() if x.strip().isdigit()):
        if pid == me:
            continue
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"])
        log(f"stopped stray downloader pid {pid}")
    time.sleep(2)


def main() -> int:
    kill_strays()
    tries = 0
    while not done():
        tries += 1
        n = len(list((CACHE / "BID").glob("*.npy")))
        log(f"start attempt {tries}; cached {n} months")
        p = subprocess.Popen([PY, str(ROOT / "research" / "history" / "dukascopy_m1.py"), "--kinds", "hour"],
                             cwd=ROOT, stdout=open(LOG, "a", encoding="utf-8"), stderr=subprocess.STDOUT)
        p.wait()
        if done():
            break
        log(f"downloader exited ({p.returncode}); waiting 60 s then restarting")
        time.sleep(60)
    log(f"COMPLETE: cache reaches {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
