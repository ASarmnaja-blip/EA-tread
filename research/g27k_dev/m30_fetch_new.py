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
the current year), timestamps New York local time with daylight saving (checked against
Dukascopy minutes; histdata's own note says EST without DST), stored as
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
        sub = per if len(per) == 4 else f"{per[:4]}/{int(per[4:])}"
        page = f"{HD}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair.lower()}/{sub}"
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
    # New York local time WITH daylight saving: matched minute by minute against Dukascopy USDJPY
    # (10 Feb 2015 aligns at UTC-5, 14 Jul 2015 at UTC-4; return correlation 0.99, mean gap 0.001 yen)
    ts = pd.to_datetime(df[0], format="%Y%m%d %H%M%S").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    out = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float), c=df[4].to_numpy(float),
                            v=df[5].to_numpy(float)), index=pd.DatetimeIndex(ts, name="t"))
    out = out[out.index.notna()].sort_index()
    out = out[~out.index.duplicated()]
    out.to_parquet(CACHE / f"{sym}_histdata_M1.parquet")
    (CACHE / f"{sym}_histdata_raw_M1.parquet").unlink(missing_ok=True)
    print(f"  {sym}: {len(out):,} minutes {out.index[0]}..{out.index[-1]}", flush=True)


REF_H1 = {"USDJPY": "USDJPY_H1BID", "JP225": "JP225_H1BID"}
MIN_CORR = 0.9          # fixed before any sleeve result on these markets was seen


def align(sym):
    """histdata's clock is not one rule: New York time with US daylight saving
    to 2018, then 1 hour off in the weeks where US and EU daylight saving
    differ. Each UTC week is shifted by the -1/0/+1 hour that best matches the
    Dukascopy H1 bid (rank correlation of hourly log returns); then any
    calendar year whose aligned hourly rank correlation is below MIN_CORR is
    dropped as bad data, with every year before it (no islands). Writes <SYM>_histdata_M1.parquet in place
    (raw copy kept as <SYM>_histdata_raw_M1.parquet) and a quality json."""
    import json
    raw_p, p = CACHE / f"{sym}_histdata_raw_M1.parquet", CACHE / f"{sym}_histdata_M1.parquet"
    if not raw_p.exists():
        p.rename(raw_p)
    m = pd.read_parquet(raw_p)
    H = pd.read_parquet(CACHE / f"{REF_H1[sym]}.parquet").c
    hc = m.c.resample("1h").last().dropna()
    week = lambda ix: ix.tz_localize(None).to_period("W-SUN")
    rc = lambda a, b: float(a.rank().corr(b.rank())) if len(a) > 20 else float("nan")
    lr = {}
    for sh in (-1, 0, 1):
        x = hc.shift(sh, freq="1h")
        j = pd.concat([x.rename("a"), H.rename("b")], axis=1, sort=True).dropna()
        lr[sh] = np.log(j).diff().dropna()
    wk = sorted(set(week(lr[0].index)))
    best = {}
    for w in wk:
        sc = {sh: rc(*(lambda r: (r.a, r.b))(lr[sh][week(lr[sh].index) == w])) for sh in (-1, 0, 1)}
        best[w] = max(sc, key=lambda k: -1 if not np.isfinite(sc[k]) else sc[k])
    mw = week(m.index)
    shift = pd.Series(mw.map(lambda w: best.get(w, 0)), index=m.index).fillna(0).astype(int)
    out = m.copy()
    out.index = m.index + pd.to_timedelta(shift.to_numpy(), unit="h")
    out = out[~out.index.duplicated()].sort_index()
    hc2 = out.c.resample("1h").last().dropna()
    j = pd.concat([hc2.rename("a"), H.rename("b")], axis=1, sort=True).dropna()
    r = np.log(j).diff().dropna()
    yr = {int(y): rc(g.a, g.b) for y, g in r.groupby(r.index.year)}
    bad = [y for y, v in yr.items() if not v >= MIN_CORR]
    if bad:                                   # keep only the unbroken run of good years up to now (no islands),
        bad = sorted(set(out.index.year[out.index.year <= max(bad)]))      # unchecked years before it included
    out = out[~out.index.year.isin(bad)]
    out.to_parquet(p)
    q = dict(weeks_shifted={str(k): int((np.array(list(best.values())) == k).sum()) for k in (-1, 0, 1)}, year_rank_corr=yr, dropped_years=bad,
             minutes=int(len(out)), first=str(out.index[0]), last=str(out.index[-1]))
    (HERE / f"histdata_quality_{sym}.json").write_text(json.dumps(q, indent=1))
    print(f"  {sym} aligned: weeks shifted {q['weeks_shifted']}, year corr " + " ".join(f"{y}:{v:.2f}" for y, v in yr.items()) + f", dropped {bad}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("eth", "usdjpy", "jp225"))
    ap.add_argument("--histdata", action="store_true")
    ap.add_argument("--align-only", action="store_true")
    a = ap.parse_args()
    if a.align_only:
        for sym in ("USDJPY", "JP225"):
            align(sym)
        return
    if a.histdata:
        for sym in (("USDJPY", "JP225") if a.only is None else {"usdjpy": ("USDJPY",), "jp225": ("JP225",)}.get(a.only, ())):
            histdata(sym)
            align(sym)
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
