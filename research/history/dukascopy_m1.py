"""Polite, resumable Dukascopy XAUUSD downloader (operator approved 2026-09-28).

Data files only (datafeed.dukascopy.com .bi5, LZMA); no third-party code.
One request at a time with a pause; on 503/timeouts it backs off (up to 10
minutes) instead of hammering, and never crashes on a single file. Every file
is cached as .npy the moment it arrives, so a restart resumes where it
stopped; confirmed-missing files (404 / empty) are cached as empty.

Order: hour candles (one file per month, H1 2003-) -> day candles (one file
per year) -> minute candles (one file per day, slow; M1 2003-).
Record: >i4 seconds from file start, >i4 open, >i4 close, >i4 low, >i4 high
(price x 1000), >f4 volume.  Usage:
    python research/history/dukascopy_m1.py [--wait SECONDS] [--kinds hour,day,min]
"""
from __future__ import annotations

import argparse
import lzma
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "history" / "dukascopy" / "cache"
BASE = "https://datafeed.dukascopy.com/datafeed/XAUUSD"
DT = np.dtype([("s", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])
START = date(2003, 5, 5)
PAUSE = 1.0
MAX_BACKOFF = 120        # observed: files clear after 1-2 retries; 600 s was pure waste


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def get(url):
    """Return decoded array, or empty array for 404/empty. Retries politely.

    A 503 is the server rate-limiting us, so it earns a long doubling backoff.
    A dropped connection (URLError/timeout) is transient flakiness, not a
    request to slow down, so it gets a short fixed retry: doubling on those
    was costing minutes per file for no reason.
    """
    slow = 20 + random.random() * 10      # jitter so retries do not lock step
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=60).read()
            return np.frombuffer(lzma.decompress(raw), dtype=DT) if raw else np.zeros(0, DT)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return np.zeros(0, DT)
            log(f"HTTP {e.code} on {url.split('XAUUSD/')[1]}; waiting {slow}s")
            time.sleep(slow)
            slow = min(slow * 2, MAX_BACKOFF)
        except Exception as e:
            time.sleep(5)


def jobs(kind, today):
    if kind == "hour":
        y, m = START.year, START.month
        while (y, m) <= (today.year, today.month):
            yield f"{y}/{m - 1:02d}", f"{y}{m:02d}"
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    elif kind == "day":
        for y in range(START.year, today.year + 1):
            yield f"{y}", f"{y}"
    else:
        d = START
        while d < today:
            if d.weekday() != 5:
                yield f"{d.year}/{d.month - 1:02d}/{d.day:02d}", d.strftime("%Y%m%d")
            d += timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=0)
    ap.add_argument("--kinds", default="hour,day,min")
    a = ap.parse_args()
    if a.wait:
        log(f"cool-down {a.wait}s before the first request")
        time.sleep(a.wait)
    today = datetime.now(timezone.utc).date()
    fname = {"hour": "candles_hour_1", "day": "candles_day_1", "min": "candles_min_1"}
    for kind in a.kinds.split(","):
        todo = list(jobs(kind, today))
        done = 0
        for path, key in todo:
            # the current period is still growing: always refetch it
            current = key.startswith(f"{today:%Y%m}") if kind != "day" else key == str(today.year)
            for side in ("BID", "ASK"):
                f = CACHE / kind / side / f"{key}.npy"
                if f.exists() and not current:
                    continue
                arr = get(f"{BASE}/{path}/{side}_{fname[kind]}.bi5")
                f.parent.mkdir(parents=True, exist_ok=True)
                np.save(f, arr)
                time.sleep(PAUSE)
            done += 1
            if done % 50 == 0 or done == len(todo):
                log(f"{kind}: {done}/{len(todo)} ({key})")
    log("all done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
