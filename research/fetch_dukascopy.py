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
WORKERS = 10

# Prices arrive as INTEGER POINTS, and the divisor is per instrument - it is
# the quote's decimal count. Getting it wrong does not error, it silently
# scales every price, so each symbol is listed explicitly rather than assumed.
# Verified against known levels: silver 16.040 and yen 108.846 in Jan 2019,
# euro 1.14482, pound 1.31081.
POINTS = {"XAUUSD": 1000.0, "XAGUSD": 1000.0, "USDJPY": 1000.0,
          "EURUSD": 100000.0, "GBPUSD": 100000.0, "AUDUSD": 100000.0,
          "USDCHF": 100000.0, "USDCAD": 100000.0, "NZDUSD": 100000.0}
POINT = POINTS["XAUUSD"]      # kept so existing XAUUSD callers are unchanged

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

# ------------------------------------------------------------------- H1 ----
# The same binary layout is served at coarser granularities with far fewer
# files: hourly is ONE FILE PER MONTH and daily ONE FILE PER YEAR, against M1's
# one file per day per side. Twenty-four years of H1 is ~576 requests instead
# of ~12,000, which is minutes instead of hours - and H1 is the timeframe the
# only setup with measured skill actually trades. The time field is seconds
# from the start of the containing period (month for hourly, year for daily).

def _period_side(path, origin, side, symbol="XAUUSD"):
    point = POINTS.get(symbol)
    if point is None:
        raise ValueError(f"no point divisor recorded for {symbol} - add it to "
                         f"POINTS rather than guessing, a wrong divisor scales "
                         f"every price silently")
    raw = _get(f"{BASE}/{symbol}/{path}/{side}_candles_{origin}.bi5")
    if not raw: return None
    try:
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(raw)
    except Exception:
        return None
    n = len(dec) // REC.size
    if n == 0: return None
    a = np.frombuffer(dec[:n * REC.size], dtype=">u4,>i4,>i4,>i4,>i4,>f4")
    o, c, l, h = (a[f"f{i}"].astype(np.float64) / point for i in (1, 2, 3, 4))
    keep = (o > 0) & (h > 0) & (l > 0) & (c > 0)
    if not keep.any(): return None
    return (a["f0"].astype(np.int64)[keep], o[keep], h[keep], l[keep],
            c[keep], a["f5"].astype(np.float64)[keep])

def fetch_h1_month(ym):
    year, month, symbol = ym if len(ym) == 3 else (*ym, "XAUUSD")
    path = f"{year}/{month - 1:02d}"
    b = _period_side(path, "hour_1", "BID", symbol)
    if b is None: return None
    a = _period_side(path, "hour_1", "ASK", symbol)
    if a is None: return None
    bi = pd.DataFrame({"bid_open": b[1], "bid_high": b[2], "bid_low": b[3],
                       "bid_close": b[4], "volume": b[5]}, index=b[0])
    ai = pd.DataFrame({"ask_open": a[1], "ask_high": a[2], "ask_low": a[3],
                       "ask_close": a[4]}, index=a[0])
    j = bi.join(ai, how="inner")
    if j.empty: return None
    j.index = pd.Timestamp(f"{year}-{month:02d}-01") + pd.to_timedelta(j.index, unit="s")
    return j.tz_localize("UTC")

def load_h1(start_year=2003, end_year=None, refresh=False, verbose=True,
            symbol="XAUUSD"):
    """Cached H1 for whole years. One parquet for the lot - it is small."""
    end_year = end_year or dt.date.today().year
    CACHE.mkdir(exist_ok=True)
    p = CACHE / f"{symbol}_H1_{start_year}_{end_year}.parquet"
    if p.exists() and not refresh:
        return pd.read_parquet(p)
    months = [(y, m, symbol) for y in range(start_year, end_year + 1)
              for m in range(1, 13)
              if not (y == dt.date.today().year and m > dt.date.today().month)]
    if verbose: print(f"  downloading {len(months)} months of H1 ...", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, df in enumerate(ex.map(fetch_h1_month, months), 1):
            if df is not None: out.append(df)
            if verbose and i % 60 == 0:
                print(f"    {i}/{len(months)} months", flush=True)
    if not out: return None
    df = pd.concat(out).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.to_parquet(p)
    return df

def clean(m, start_year=2004):
    """Drop what a quality pass says cannot be traded or cannot be trusted.

    2003 IS UNUSABLE: it carries placeholder rows (gold quoted at 1.25) and
    33% of its bars have a zero spread. Every year from 2004 on has a zero
    spread share of 0.000 and a price range that matches gold's real history
    (2011 peak 1918, 2015 trough 1050, 2020 peak 2070).

    ZERO VOLUME MEANS THE MARKET IS SHUT, and that was verified rather than
    assumed: zero-volume bars are 100% of Saturdays, 91.6% of Sundays, 12.6%
    of Fridays and 2.5-3.7% of Mon-Thu, and the weekday remainder clusters at
    21:00-23:00 UTC - the daily close. Dropping on volume rather than on a
    hardcoded weekend rule also removes holidays, which a calendar rule would
    keep as flat synthetic bars and a breakout rule would then trade."""
    out = m[(m.index.year >= start_year) & (m.volume > 0) & (m.spread > 0)]
    return out[(out.high >= out.low) & (out.low > 0)]

def validate(m, verbose=True):
    """Correlate daily returns against Yahoo's GC=F, the way `fetch_m15_gold.py`
    validates the PAXG proxy. Spot XAUUSD and the front future are different
    instruments, so this is a sanity check on the decode and the timestamps,
    not a claim they are the same thing."""
    import json, urllib.parse
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote("GC=F") + "?range=10y&interval=1d")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    gc = pd.Series(d["indicators"]["quote"][0]["close"],
                   index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()
    gc = gc.resample("1D").last().dropna()
    mine = m.close.resample("1D").last().dropna()
    j = pd.concat([mine.rename("duka"), gc.rename("gc")], axis=1, join="inner").dropna()
    c = j.pct_change().dropna().corr().iloc[0, 1]
    if verbose:
        print(f"  daily-return correlation vs GC=F over {len(j)} shared days: {c:.4f}")
        print(f"  level gap (mean duka - gc): {(j.duka - j.gc).mean():+.2f}")
    return c

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
