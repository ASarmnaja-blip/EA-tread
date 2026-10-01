"""Loaders for the news / macro data in data/macro/ (fetched 2026-10-01 with the operator's permission; manifest.json has sha256).
Every series is returned with the UTC epoch second from which it may be used (never before the value exists)."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "data" / "macro"
DAY = 86400


def _day_end(dates):
    """A daily value dated d is usable from 24:00 UTC of d."""
    return pd.to_datetime(dates).values.astype("datetime64[s]").astype(np.int64) + DAY


def gprd():
    g = pd.read_stata(M / "gpr_daily.dta")
    return pd.DataFrame(dict(date=pd.to_datetime(g.date), GPRD=g.GPRD.astype(float), ACT=g.GPRD_ACT.astype(float),
                             THREAT=g.GPRD_THREAT.astype(float), avail=_day_end(g.date))).dropna(subset=["GPRD"]).reset_index(drop=True)


def tpu():
    x = pd.read_excel(M / "tpu_web_latest.xlsx", sheet_name="TPU_DAILY")
    return pd.DataFrame(dict(date=pd.to_datetime(x.DATE), TPU=pd.to_numeric(x.TPUD_index, errors="coerce"), avail=_day_end(x.DATE))).dropna().reset_index(drop=True)


def fred(sid):
    x = pd.read_csv(M / f"fred_{sid}.csv")
    v = pd.to_numeric(x.iloc[:, 1], errors="coerce")
    d = pd.to_datetime(x.iloc[:, 0])
    return pd.DataFrame(dict(date=d, value=v, avail=_day_end(d))).dropna().reset_index(drop=True)


def cftc_gold():
    """Legacy futures-only COT, COMEX gold: as of Tuesday, released Friday 15:30 New York -> usable from Saturday 00:00 UTC."""
    files = sorted((M / "cftc").glob("deacot*.zip")) + sorted((ROOT / "data" / "cftc_legacy").glob("deacot*.zip"))
    parts = []
    for f in files:
        z = zipfile.ZipFile(f)
        c = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), low_memory=False)
        g = c[c["Market and Exchange Names"].astype(str).str.startswith("GOLD - COMMODITY EXCHANGE")]
        parts.append(pd.DataFrame(dict(date=pd.to_datetime(g["As of Date in Form YYYY-MM-DD"]), oi=g["Open Interest (All)"].astype(float),
                                       nc_net=g["Noncommercial Positions-Long (All)"].astype(float) - g["Noncommercial Positions-Short (All)"].astype(float),
                                       c_net=g["Commercial Positions-Long (All)"].astype(float) - g["Commercial Positions-Short (All)"].astype(float))))
    x = pd.concat(parts).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    x["nc_share"] = x.nc_net / x.oi
    x["avail"] = x.date.values.astype("datetime64[s]").astype(np.int64) + 4 * DAY          # Tuesday -> Saturday 00:00 UTC
    return x


def trump_posts():
    """All posts with exact UTC times: tweets 2009-2021 from the status id (Twitter snowflake), Truth Social 2022+ from created_at (UTC)."""
    rows = []
    for fn in ("tweets_bf_office.csv", "tweets_in_office.csv"):
        rd = csv.reader(open(M / fn, encoding="utf-8", errors="replace"), skipinitialspace=True)
        next(rd)
        for r in rd:
            if len(r) != 4:
                continue
            m = re.search(r"/status/(\d+)", r[2])
            if not m:
                continue
            sid = int(m.group(1))
            if sid < 2 ** 32:                                     # pre-snowflake ids (before Nov 2010): fall back to the file time as New York
                t = pd.Timestamp(r[1]).tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
                if pd.isna(t):
                    continue
                ts = int(t.tz_convert("UTC").timestamp())
            else:
                ts = ((sid >> 22) + 1288834974657) // 1000
            rows.append((ts, r[3].lower(), "twitter"))
    t = pd.read_csv(M / "truth_archive.csv")
    tt = pd.to_datetime(t.created_at, utc=True, errors="coerce")
    ok = tt.notna()
    secs = tt[ok].dt.tz_convert(None).values.astype("datetime64[s]").astype(np.int64); texts = t.content[ok].fillna("").astype(str).to_numpy()
    for ts, txt in zip(secs, texts):
        rows.append((int(ts), re.sub(r"<[^>]+>", " ", str(txt)).lower(), "truth"))
    return pd.DataFrame(rows, columns=["t", "text", "src"]).sort_values("t").reset_index(drop=True)


def asof(avail, values, times):
    """Latest value usable at each time (NaN before the first)."""
    j = np.searchsorted(np.asarray(avail, np.int64), np.asarray(times, np.int64), side="right") - 1
    v = np.asarray(values, float)
    return np.where(j >= 0, v[np.maximum(j, 0)], np.nan)
