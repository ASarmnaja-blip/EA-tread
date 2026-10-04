#!/usr/bin/env python3
"""M1 history for the M30 sleeve on ETH, USDJPY and JP225.

  ETH:    Binance ETHUSDT spot 1m (monthly zips, daily fallback), Aug 2017 on,
          stored like BTC as .cache_duka/ETHUSD_binance_M1.parquet
  USDJPY: Dukascopy M1 bid+ask from 2009, .cache_duka/USDJPY_M1_<year>.parquet
  JP225:  Dukascopy JPNIDXJPY M1 bid+ask from 2010 (whatever exists),
          .cache_duka/JPNIDXJPY_M1_<year>.parquet

Dukascopy days are fetched with fetch_dukascopy.fill (several low-concurrency
passes; the session proxy drops bursts). Re-running resumes.

Through this session's proxy Dukascopy served about one day-side a second
(~6 hours for both markets), so --histdata takes USDJPY and JP225 (histdata
JPXJPY) M1 bid from histdata.com instead: one zip per year (per month for
the current year), timestamps EST without daylight saving (UTC-5), stored as
.cache_duka/<SYM>_histdata_M1.parquet.

Usage: python3 research/g27k_dev/m30_fetch_new.py [--only eth|usdjpy|jp225] [--histdata]
"""
import argparse
import io
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK

CACHE = HERE.parent / ".cache_duka"
END = "2026-10-01"
DK.POINTS.setdefault("JPNIDXJPY", 1000.0)     # same divisor fetch_universe uses for the JP225 H1 bid


def eth():
    p = CACHE / "ETHUSD_binance_M1.parquet"

    def zipcsv(u):
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=180).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        return pd.read_csv(z.open(z.namelist()[0]), header=None)

    def month(per):
        for k in range(4):
            try:
                return zipcsv(f"https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-{per.year}-{per.month:02d}.zip")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    continue
                out = []
                for d in pd.date_range(per.start_time, per.end_time.normalize(), freq="D"):
                    try:
                        out.append(zipcsv(f"https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1m/ETHUSDT-1m-{d:%Y-%m-%d}.zip"))
                    except urllib.error.HTTPError:
                        pass
                return pd.concat(out, ignore_index=True) if out else None
            except Exception:
                continue
        raise RuntimeError(f"ETH {per} failed")

    with ThreadPoolExecutor(4) as ex:
        parts = [x for x in ex.map(month, pd.period_range("2017-08", "2026-09", freq="M")) if x is not None]
    df = pd.concat(parts, ignore_index=True)
    ts = df[0].astype(np.int64).to_numpy()
    ts = np.where(ts > 10 ** 14, ts // 1000, ts)                  # Binance moved to microseconds in 2025
    out = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float),
                            c=df[4].to_numpy(float), v=df[5].to_numpy(float)),
                       index=pd.to_datetime(ts, unit="ms", utc=True)).sort_index()
    out = out[~out.index.duplicated()]
    out.to_parquet(p)
    print(f"  ETHUSD: {len(out):,} minutes {out.index[0]}..{out.index[-1]}", flush=True)


def duka(sym, y0):
    for y in range(y0, 2027):
        got, want = DK.fill(sym, y, end=END, workers=6, passes=6, verbose=False)
        print(f"  {sym} {y}: {got}/{want} days", flush=True)


HD = "https://www.histdata.com"
HD_PAIR = {"USDJPY": "USDJPY", "JP225": "JPXJPY"}


def histdata(sym, y0=2010):
    import re
    pair = HD_PAIR[sym]

    def one(per):
        page = f"{HD}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair.lower()}/{per}"
        for k in range(4):
            try:
                html = urllib.request.urlopen(urllib.request.Request(page, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read().decode("utf-8", "ignore")
                tk = re.search(r'name="tk" id="tk" value="([0-9a-f]+)"', html).group(1)
                y, ym = (per[:4], per) if len(per) > 4 else (per, per)
                body = urllib.parse.urlencode(dict(tk=tk, date=y, datemonth=ym, platform="ASCII", timeframe="M1", fxpair=pair)).encode()
                raw = urllib.request.urlopen(urllib.request.Request(f"{HD}/get.php", data=body, headers={"User-Agent": "Mozilla/5.0", "Referer": page}), timeout=300).read()
                z = zipfile.ZipFile(io.BytesIO(raw))
                return pd.read_csv(z.open([n for n in z.namelist() if n.endswith(".csv")][0]), sep=";", header=None)
            except Exception as e:
                err = e
        print(f"  {sym} {per}: failed ({err})", flush=True)
        return None

    pers = [str(y) for y in range(y0, 2026)] + [f"2026{m:02d}" for m in range(1, 10)]
    with ThreadPoolExecutor(3) as ex:
        parts = [x for x in ex.map(one, pers) if x is not None]
    df = pd.concat(parts, ignore_index=True)
    ts = pd.to_datetime(df[0], format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)       # EST (no DST) -> UTC
    out = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float), c=df[4].to_numpy(float),
                            v=df[5].to_numpy(float)), index=ts.dt.tz_localize("UTC")).sort_index()
    out = out[~out.index.duplicated()]
    out.to_parquet(CACHE / f"{sym}_histdata_M1.parquet")
    print(f"  {sym}: {len(out):,} minutes {out.index[0]}..{out.index[-1]}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("eth", "usdjpy", "jp225"))
    ap.add_argument("--histdata", action="store_true")
    a = ap.parse_args()
    if a.histdata:
        for sym in (("USDJPY", "JP225") if a.only is None else {"usdjpy": ("USDJPY",), "jp225": ("JP225",)}.get(a.only, ())):
            histdata(sym)
        print("FETCH_DONE", flush=True)
        return
    if a.only in (None, "eth"):
        eth()
    if a.only in (None, "usdjpy"):
        duka("USDJPY", 2009)
    if a.only in (None, "jp225"):
        duka("JPNIDXJPY", 2010)
    print("FETCH_DONE", flush=True)


if __name__ == "__main__":
    main()
