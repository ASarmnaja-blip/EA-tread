#!/usr/bin/env python3
"""H1 bid history for the multi-market search (ledger multi_market_pooled_search).

Dukascopy hourly files (one per month per side, bid only: prices for the
signals, costs come from the broker specs) for 13 markets, 2009-01..2026-09,
filled in several low-concurrency passes because the session proxy drops
bursts; existing FX caches seed the files. BTC from Binance BTCUSDT 1h,
2017-08 onward. Writes research/.cache_duka/<MKT>_H1BID.parquet.

Usage: python3 research/g27k_dev/fetch_universe.py
"""
import io
import pathlib
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK

# market -> (Dukascopy symbol, point divisor); divisors checked on May 2015
# (S&P 2060.97, Nasdaq 4392.9, DAX 10995.8, Nikkei 20206, WTI 59.04,
# copper 2.6188, USDCNH 6.206, USDMXN 15.708, USDZAR 12.139)
DUKA = {"XCUUSD": ("COPPERCMDUSD", 10000.0), "USOIL": ("LIGHTCMDUSD", 1000.0),
        "US500": ("USA500IDXUSD", 1000.0), "USTEC": ("USATECHIDXUSD", 1000.0),
        "DE30": ("DEUIDXEUR", 1000.0), "JP225": ("JPNIDXJPY", 1000.0),
        "EURUSD": ("EURUSD", 100000.0), "USDJPY": ("USDJPY", 1000.0), "AUDUSD": ("AUDUSD", 100000.0),
        "USDCHF": ("USDCHF", 100000.0), "USDCNH": ("USDCNH", 100000.0), "USDMXN": ("USDMXN", 100000.0),
        "USDZAR": ("USDZAR", 100000.0)}
MONTHS = [(y, m) for y in range(2009, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
CACHE = DK.CACHE


def month_bid(task):
    mkt, (y, m) = task
    sym = DUKA[mkt][0]
    b = DK._period_side(f"{y}/{m - 1:02d}", "hour_1", "BID", sym)
    if b is None:
        return mkt, (y, m), None
    df = pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4], v=b[5]),
                      index=pd.Timestamp(f"{y}-{m:02d}-01", tz="UTC") + pd.to_timedelta(b[0], unit="s"))
    return mkt, (y, m), df


def seed(mkt):
    p = CACHE / f"{mkt}_H1BID.parquet"
    if p.exists():
        return pd.read_parquet(p)
    old = CACHE / f"{mkt}_H1_2003_2026.parquet"
    if old.exists():
        d = pd.read_parquet(old)
        return pd.DataFrame(dict(o=d.bid_open, h=d.bid_high, l=d.bid_low, c=d.bid_close, v=d.volume))
    return pd.DataFrame(columns=["o", "h", "l", "c", "v"])


def fill_dukascopy(passes=6, workers=8):
    for mkt, (sym, pt) in DUKA.items():
        DK.POINTS[sym] = pt
    have = {m: seed(m) for m in DUKA}
    for k in range(passes):
        todo = []
        for m, d in have.items():
            got = set(zip(d.index.year, d.index.month)) if len(d) else set()
            todo += [(m, ym) for ym in MONTHS if ym not in got]
        print(f"  pass {k + 1}: {len(todo)} market-months missing", flush=True)
        if not todo:
            break
        with ThreadPoolExecutor(workers) as ex:
            for i, (m, ym, df) in enumerate(ex.map(month_bid, todo), 1):
                if df is not None:
                    have[m] = pd.concat([have[m], df]).sort_index()
                    have[m] = have[m][~have[m].index.duplicated(keep="last")]
                if i % 100 == 0:
                    for mm, dd in have.items():
                        dd.to_parquet(CACHE / f"{mm}_H1BID.parquet")
                    print(f"    {i}/{len(todo)}", flush=True)
        for m, d in have.items():
            d.to_parquet(CACHE / f"{m}_H1BID.parquet")
    for m, d in have.items():
        print(f"  {m}: {len(d):,} bars {d.index[0].date()}..{d.index[-1].date()}", flush=True)


def fetch_binance_btc():
    def zipcsv(u):
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        return pd.read_csv(z.open(z.namelist()[0]), header=None)

    def month(p):
        try:
            return zipcsv(f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-{p.year}-{p.month:02d}.zip")
        except urllib.error.HTTPError:
            out = []
            for d in pd.date_range(p.start_time, p.end_time.normalize(), freq="D"):
                try:
                    out.append(zipcsv(f"https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-{d:%Y-%m-%d}.zip"))
                except urllib.error.HTTPError:
                    pass
            return pd.concat(out, ignore_index=True)

    with ThreadPoolExecutor(6) as ex:
        df = pd.concat(list(ex.map(month, pd.period_range("2017-08", "2026-09", freq="M"))), ignore_index=True)
    ts = df[0].astype(np.int64).to_numpy()
    ts = np.where(ts > 10 ** 14, ts // 1000, ts)
    out = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float),
                            c=df[4].to_numpy(float), v=df[5].to_numpy(float)),
                       index=pd.to_datetime(ts, unit="ms", utc=True)).sort_index()
    out = out[~out.index.duplicated()]
    out.to_parquet(CACHE / "BTCUSD_H1BID.parquet")
    print(f"  BTCUSD: {len(out):,} bars {out.index[0].date()}..{out.index[-1].date()}", flush=True)


if __name__ == "__main__":
    fetch_binance_btc()
    fill_dukascopy()
    print("ALL_DONE", flush=True)
