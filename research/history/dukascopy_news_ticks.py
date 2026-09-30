"""Dukascopy XAUUSD tick files for news hours only (operator approved 2026-09-30: "อนุญาต").
One .bi5 per UTC hour (ask, bid, volumes). Hours:
  2022-01 ..: exact USD tier-1 releases from the PIT calendar (NFP, CPI, FOMC, core PCE) - the hour containing the
             release and the hour before it;
  2009-01 .. 2021-12 (no calendar): the 08:30 New York hour on the 1st/2nd Friday (payrolls slot) and on the 10th-15th
             (CPI slot), and the 14:00 New York hour on Wednesdays (FOMC slot) - chosen by the clock, not by what the price
             did, so the sample is not biased toward big moves.
Polite: one request at a time, 1 s pause, backoff on 503, resumable cache (.npy per hour).
Record: >i4 ms from hour start, >i4 ask, >i4 bid (x1000), >f4 ask volume, >f4 bid volume."""
from __future__ import annotations

import lzma
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "history" / "dukascopy" / "ticks"
BASE = "https://datafeed.dukascopy.com/datafeed/XAUUSD"
DT = np.dtype([("ms", ">i4"), ("ask", ">i4"), ("bid", ">i4"), ("av", ">f4"), ("bv", ">f4")])
PAUSE = 1.0


def log(m):
    print(f"{datetime.now():%H:%M:%S} {m}", flush=True)


def get(url):
    slow = 20 + random.random() * 10
    for _ in range(30):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
            return np.frombuffer(lzma.decompress(raw), dtype=DT) if raw else np.zeros(0, DT)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return np.zeros(0, DT)
            log(f"HTTP {e.code}; waiting {slow:.0f}s"); time.sleep(slow); slow = min(slow * 2, 120)
        except Exception:
            time.sleep(5)
    return None


def hours():
    sys.path[:0] = [str(ROOT / "research" / "foundry"), str(ROOT / "research" / "pilot")]
    import calendar_pit as P
    cal = P.load_pit()
    t1 = cal[(cal.currency == "USD") & cal.event.isin(["Nonfarm Payrolls", "CPI m/m", "Fed Interest Rate Decision", "Core PCE Price Index m/m"])]
    rel = pd.to_datetime(t1.epoch.unique(), unit="s", utc=True)
    hs = set()
    for r in rel:
        h = r.floor("h"); hs.update([h, h - pd.Timedelta(hours=1)])
    days = pd.date_range("2009-01-01", "2021-12-31", freq="B", tz="America/New_York")
    for d in days:                               # release hour only (08:30 is mid-hour, so it holds 30 min before)
        nfp = d.dayofweek == 4 and d.day <= 14   # 1st / 2nd Friday: payrolls slot
        cpi = 10 <= d.day <= 15                  # mid-month 08:30: CPI slot
        if nfp or cpi:
            hs.add((d + pd.Timedelta(hours=8, minutes=30)).tz_convert("UTC").floor("h"))
        if d.dayofweek == 2:                     # Wednesday 14:00: FOMC statement slot
            hs.add((d + pd.Timedelta(hours=14)).tz_convert("UTC").floor("h"))
    now = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=2)
    return sorted(h for h in hs if h < now)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    hs = hours()
    log(f"{len(hs)} hours to fetch")
    done = 0
    for i, h in enumerate(hs):
        f = CACHE / f"{h:%Y%m%d%H}.npy"
        if f.exists():
            continue
        arr = get(f"{BASE}/{h.year}/{h.month - 1:02d}/{h.day:02d}/{h.hour:02d}h_ticks.bi5")
        if arr is None:
            log(f"gave up on {h}"); continue
        np.save(f, arr); done += 1
        if done % 100 == 0:
            log(f"{i + 1}/{len(hs)} ({h:%Y-%m-%d %H}h), {len(arr)} ticks in last file")
        time.sleep(PAUSE)
    log("all done")


if __name__ == "__main__":
    main()
