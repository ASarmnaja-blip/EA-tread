#!/usr/bin/env python3
"""Real XAUUSD M1 with real bid and ask, straight from Dukascopy.

WHY THIS CHANGES THINGS
  Every intraday result in this repo has been limited by one of two ceilings:
  Yahoo serves only 60 days of M5/M15, and the six-year fallback
  (`fetch_m15_gold.py`) is PAXG, a crypto-venue token that trades weekends and
  carries a crypto spread. Both ceilings are gone here. Dukascopy publishes
  free, keyless, per-day M1 candles for XAUUSD separately for the BID and the
  ASK side, back to 2003.

  That gives three things nothing in this repo has had before:
    1. THE REAL INSTRUMENT - spot XAUUSD, not GC=F futures or a token proxy.
    2. TWENTY YEARS of minute data instead of sixty days.
    3. A MEASURED SPREAD, per minute, instead of a constant assumption. Every
       cost number in this repo so far (0.26, 0.7525, 0.36, 0.8525) was an
       assumption. The audit in `docs/RESEARCH_FINDINGS.md` flagged exactly
       this as the blocking gate before any result could be trusted.

THE FORMAT, AND HOW THE DECODER WAS VERIFIED
  URL: /datafeed/XAUUSD/{YYYY}/{MM}/{DD}/{BID|ASK}_candles_min_1.bi5 where MM
  is ZERO-INDEXED (00 = January). The payload is LZMA-alone compressed, 1440
  fixed 24-byte records per day, one per minute of the UTC day:
      >I  seconds from midnight UTC
      >i  open, close, low, high  - INTEGER POINTS, not floats (XAUUSD has 3
          decimals, so divide by 1000)
      >f  volume
  Note the field ORDER: open, CLOSE, LOW, HIGH. Getting that wrong silently
  produces plausible-looking bars with the high and low transposed.

  The decoder was checked against an independent source before use: the tick
  file for 2026-07-15 10:00 UTC opens at bid 4030.155, and minute 600 of that
  day's BID candle file reads open 4030.155. Same number from two different
  endpoints and two different binary layouts.

WHAT THIS IS STILL NOT
  Dukascopy is a Swiss broker's own feed, not the user's broker. Its spread is
  Dukascopy's spread. Commission, swap, contract size, minimum lot and stop
  level are account-specific and are NOT in this data - they still have to come
  from the user's own MT5 account before any live claim. The volume field is
  the provider's own number with no documented unit, and a material share of
  minutes carry zero volume on both sides, so it needs its own quality check
  before being used as a feature rather than being assumed meaningful.
"""
import argparse, datetime as dt, lzma, struct, sys, time, urllib.error, urllib.request
import pathlib
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

CACHE = pathlib.Path(__file__).parent / ".cache_duka"
BASE = "https://datafeed.dukascopy.com/datafeed"
REC = struct.Struct(">Iiiiif")
POINT = 1000.0          # XAUUSD quotes to 3 decimals
WORKERS = 10

def _get(url, tries=4):
    """503 is Dukascopy's normal answer for an hour it has no data for AND its
    rate limit, so it is retried rather than treated as fatal, and an empty
    body is a legitimate 'market closed' answer."""
    for a in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(r, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return b""
            if a == tries - 1: return None
            time.sleep(1.5 * (a + 1))
        except Exception:
            if a == tries - 1: return None
            time.sleep(1.5 * (a + 1))
    return None

def _day_side(day, side):
    """One day, one side. Returns (minute_index, o, h, l, c, v) or None."""
    url = (f"{BASE}/XAUUSD/{day.year}/{day.month - 1:02d}/{day.day:02d}/"
           f"{side}_candles_min_1.bi5")
    raw = _get(url)
    if not raw: return None
    try:
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(raw)
    except Exception:
        return None
    n = len(dec) // REC.size
    if n == 0: return None
    a = np.frombuffer(dec[:n * REC.size], dtype=">u4,>i4,>i4,>i4,>i4,>f4")
    t = a["f0"].astype(np.int64)
    o, c, l, h = (a[f"f{i}"].astype(np.float64) / POINT for i in (1, 2, 3, 4))
    v = a["f5"].astype(np.float64)
    keep = (o > 0) & (h > 0) & (l > 0) & (c > 0)
    if not keep.any(): return None
    return t[keep] // 60, o[keep], h[keep], l[keep], c[keep], v[keep]

def fetch_day(day):
    """Both sides of one UTC day, joined on the minutes present in both."""
    b = _day_side(day, "BID")
    if b is None: return None
    a = _day_side(day, "ASK")
    if a is None: return None
    bi = pd.DataFrame({"bid_open": b[1], "bid_high": b[2], "bid_low": b[3],
                       "bid_close": b[4], "volume": b[5]}, index=b[0])
    ai = pd.DataFrame({"ask_open": a[1], "ask_high": a[2], "ask_low": a[3],
                       "ask_close": a[4]}, index=a[0])
    j = bi.join(ai, how="inner")
    if j.empty: return None
    j.index = pd.to_datetime(day) + pd.to_timedelta(j.index, unit="m")
    return j.tz_localize("UTC")

def fetch_range(start, end, workers=WORKERS, verbose=True):
    """Every UTC day in [start, end). Weekends are skipped - the metal is shut
    and Dukascopy serves nothing for them anyway."""
    days = [d.date() for d in pd.date_range(start, end, freq="D", inclusive="left")
            if d.weekday() < 5 or d.weekday() == 6]   # Sunday evening opens
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for df in ex.map(fetch_day, days):
            done += 1
            if df is not None: out.append(df)
            if verbose and done % 200 == 0:
                print(f"    {done}/{len(days)} days, {len(out)} with data",
                      flush=True)
    if not out: return None
    return pd.concat(out).sort_index()

def load(start="2020-01-01", end=None, refresh=False, verbose=True):
    """Cached M1. One parquet per calendar year so a partial year can be
    refreshed without redownloading the settled ones."""
    end = end or dt.date.today().isoformat()
    CACHE.mkdir(exist_ok=True)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    parts = []
    for year in range(s.year, e.year + 1):
        p = CACHE / f"XAUUSD_M1_{year}.parquet"
        y0 = max(s, pd.Timestamp(f"{year}-01-01"))
        y1 = min(e, pd.Timestamp(f"{year + 1}-01-01"))
        if p.exists() and not refresh:
            df = pd.read_parquet(p)
        else:
            if verbose: print(f"  downloading {year} ...", flush=True)
            df = fetch_range(y0, y1, verbose=verbose)
            if df is None: continue
            df.to_parquet(p)
        parts.append(df.loc[(df.index >= y0.tz_localize("UTC")) &
                            (df.index < y1.tz_localize("UTC"))])
    if not parts: return None
    return pd.concat(parts).sort_index()

def mid(df):
    """Mid-price OHLC plus the measured spread, which is the column this repo
    has never had. Spread is quoted in price units, per minute."""
    out = pd.DataFrame(index=df.index)
    for k in ("open", "high", "low", "close"):
        out[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2.0
    out["spread"] = df["ask_close"] - df["bid_close"]
    out["volume"] = df["volume"]
    return out

def resample(m1, rule):
    """M1 -> any timeframe. Spread is averaged, not summed."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last",
           "spread": "mean", "volume": "sum"}
    cols = {k: v for k, v in agg.items() if k in m1.columns}
    return m1.resample(rule).agg(cols).dropna(subset=["close"])

def main():
    ap = argparse.ArgumentParser(description="Download and cache XAUUSD M1")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    df = load(a.start, a.end, refresh=a.refresh)
    if df is None:
        print("no data"); sys.exit(1)
    m = mid(df)
    print(f"\nXAUUSD M1: {len(m):,} minutes  {m.index[0]} -> {m.index[-1]}")
    print(f"downloaded/loaded in {time.time()-t0:.0f}s\n")

    print("MEASURED SPREAD - the number every cost assumption in this repo")
    print("has been guessing at:")
    for q in (0.10, 0.50, 0.90, 0.99):
        print(f"  p{int(q*100):<3} {m.spread.quantile(q):.3f}")
    print(f"  mean {m.spread.mean():.3f}   "
          f"(repo has been assuming 0.26 / 0.7525 / 0.36 / 0.8525)")

    print("\nSPREAD BY UTC HOUR - a constant cost assumption cannot see this")
    by_h = m.groupby(m.index.hour).spread.median()
    for h in range(0, 24, 3):
        bars = "#" * int(by_h.get(h, 0) * 12)
        print(f"  {h:02d}:00  {by_h.get(h, float('nan')):.3f}  {bars}")

    z = (m.volume <= 0).mean()
    print(f"\nvolume: {z:.2%} of minutes report zero - matches the supplied")
    print("data note's warning; needs its own quality pass before use.")

if __name__ == "__main__":
    main()
