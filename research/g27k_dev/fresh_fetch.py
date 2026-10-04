#!/usr/bin/env python3
"""Data for ledger g27k_fresh_markets: Dukascopy H1 bid for 27 markets
(re-fetching any month with under 350 live bars), Dukascopy H1 ask for the
non-FX markets over 2024-01..2026-08 (spread measurement only), and Binance
ETHUSDT 1h as ETHUSD.

Usage: python3 research/g27k_dev/fresh_fetch.py
"""
import io
import json
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

CACHE = DK.CACHE
FX = ["GBPUSD", "USDCAD", "NZDUSD", "USDSEK", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY", "EURGBP",
      "EURAUD", "EURCAD", "EURCHF", "GBPAUD", "GBPCHF", "AUDCAD", "AUDNZD"]
OTHER = {"UK100": "GBRIDXGBP", "FRA40": "FRAIDXEUR", "AUS200": "AUSIDXAUD", "HK50": "HKGIDXHKD", "STOXX50": "EUSIDXEUR",
         "UKOIL": "BRENTCMDUSD", "XPTUSD": "XPTCMDUSD", "XPDUSD": "XPDCMDUSD", "XNGUSD": "GASCMDUSD"}
SYM = {**{m: m for m in FX}, **OTHER}
for m, s in SYM.items():
    DK.POINTS[s] = 1000.0 if ("JPY" in m or m in OTHER) else 100000.0
MONTHS = [(y, mo) for y in range(2009, 2027) for mo in range(1, 13) if (y, mo) <= (2026, 9)]


def month(task):
    m, (y, mo), side = task
    try:
        b = DK._period_side(f"{y}/{mo - 1:02d}", "hour_1", side, SYM[m])
    except Exception:
        b = None
    if b is None:
        return m, (y, mo), None
    df = pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4], v=b[5]),
                      index=pd.Timestamp(f"{y}-{mo:02d}-01", tz="UTC") + pd.to_timedelta(b[0], unit="s"))
    return m, (y, mo), df


def live_months(d):
    if not len(d):
        return set()
    x = d[d.h > d.l]
    n = x.groupby([x.index.year, x.index.month]).size()
    return {k for k, v in n.items() if v >= 350}


def fill_bid(passes=6, workers=8):
    have = {}
    for m in SYM:
        p = CACHE / f"{m}_H1BID.parquet"
        have[m] = pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=list("ohlcv"))
    for k in range(passes):
        todo = []
        for m, d in have.items():
            live = live_months(d)
            # after the first pass, months before a market's first live month are history Dukascopy does not have
            first = min(live) if (k > 0 and live) else (0, 0)
            todo += [(m, ym, "BID") for ym in MONTHS if ym not in live and ym >= first]
        print(f"  bid pass {k + 1}: {len(todo)} market-months to fetch", flush=True)
        if not todo:
            break
        got = 0
        with ThreadPoolExecutor(workers) as ex:
            for i, (m, ym, df) in enumerate(ex.map(month, todo), 1):
                if df is not None and (df.h > df.l).sum() > 0:
                    d = have[m]
                    keep = d[~((d.index.year == ym[0]) & (d.index.month == ym[1]))] if len(d) else d
                    have[m] = pd.concat([keep, df]).sort_index()
                    got += 1
                if i % 200 == 0:
                    print(f"    {i}/{len(todo)} fetched, {got} with data", flush=True)
                    for mm, dd in have.items():
                        dd[~dd.index.duplicated()].to_parquet(CACHE / f"{mm}_H1BID.parquet")
        for m, d in have.items():
            d[~d.index.duplicated()].to_parquet(CACHE / f"{m}_H1BID.parquet")
    for m, d in have.items():
        x = d[d.h > d.l]
        print(f"  {m}: {x.index[0].date() if len(x) else '-'}..{x.index[-1].date() if len(x) else '-'}  live bars {len(x):,}  "
              f"months >=350 bars {len(live_months(d))}", flush=True)


def spreads_other(workers=8):
    out = {}
    for m in OTHER:
        tasks = [(m, ym, "ASK") for ym in MONTHS if ym >= (2024, 1) and ym <= (2026, 8)]
        with ThreadPoolExecutor(workers) as ex:
            asks = [df for _, _, df in ex.map(month, tasks) if df is not None]
        if not asks:
            continue
        a = pd.concat(asks)
        b = pd.read_parquet(CACHE / f"{m}_H1BID.parquet")
        j = a[["c"]].join(b[["c"]], rsuffix="_b", how="inner")
        j = j[(j.c > 0) & (j.c_b > 0)]
        s = (j.c - j.c_b) / ((j.c + j.c_b) / 2) * 1e4
        out[m] = float(s[s > 0].median())
        print(f"  {m}: median spread {out[m]:.2f} bp over {len(s):,} hours", flush=True)
    (HERE / "fresh_spreads_other.json").write_text(json.dumps(out, indent=1))


def eth():
    def zipcsv(u):
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        return pd.read_csv(z.open(z.namelist()[0]), header=None)

    def one(p):
        try:
            return zipcsv(f"https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-{p.year}-{p.month:02d}.zip")
        except urllib.error.HTTPError:
            out = []
            for d in pd.date_range(p.start_time, p.end_time.normalize(), freq="D"):
                try:
                    out.append(zipcsv(f"https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1h/ETHUSDT-1h-{d:%Y-%m-%d}.zip"))
                except urllib.error.HTTPError:
                    pass
            return pd.concat(out, ignore_index=True) if out else None

    with ThreadPoolExecutor(6) as ex:
        df = pd.concat([x for x in ex.map(one, pd.period_range("2017-08", "2026-09", freq="M")) if x is not None], ignore_index=True)
    ts = df[0].astype(np.int64).to_numpy()
    ts = np.where(ts > 10 ** 14, ts // 1000, ts)
    out = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float),
                            c=df[4].to_numpy(float), v=df[5].to_numpy(float)),
                       index=pd.to_datetime(ts, unit="ms", utc=True)).sort_index()
    out = out[~out.index.duplicated()]
    out.to_parquet(CACHE / "ETHUSD_H1BID.parquet")
    print(f"  ETHUSD: {len(out):,} bars {out.index[0].date()}..{out.index[-1].date()}", flush=True)


if __name__ == "__main__":
    eth()
    fill_bid()
    spreads_other()
    print("ALL_DONE", flush=True)
