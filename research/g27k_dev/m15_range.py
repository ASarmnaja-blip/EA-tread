#!/usr/bin/env python3
"""How far an M15 bar moves on average (high - low), per market, per year and
for the last 12 months, also by session (UTC). Gold and silver from Dukascopy
M1 bid, BTC from Binance M1, ETH from Binance 15m klines, USDJPY and JP225
from Dukascopy M1 bid fetched for 2026-04..2026-09.

Usage: python3 research/g27k_dev/m15_range.py
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
END = pd.Timestamp("2026-10-01", tz="UTC")
LAST12 = END - pd.DateOffset(months=12)
SESS = {"เอเชีย 00–07": (0, 7), "ลอนดอน 07–13": (7, 13), "นิวยอร์ก 13–21": (13, 21), "ช่วงปิด 21–24": (21, 24)}


def m15(df, o, h, l, c):
    x = df[[o, h, l, c]].rename(columns={o: "o", h: "h", l: "l", c: "c"})
    g = x.resample("15min").agg(dict(o="first", h="max", l="min", c="last"))
    n = x.c.resample("15min").count()
    return g[n >= 10].dropna()


def duka_m1(m, years):
    return pd.concat([pd.read_parquet(CACHE / f"{m}_M1_{y}.parquet") for y in years if (CACHE / f"{m}_M1_{y}.parquet").exists()]).sort_index()


def eth15():
    def get(u):
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        return pd.read_csv(z.open(z.namelist()[0]), header=None)

    def one(p):
        try:
            return get(f"https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/15m/ETHUSDT-15m-{p.year}-{p.month:02d}.zip")
        except urllib.error.HTTPError:          # month not published yet: daily files
            out = []
            for d in pd.date_range(p.start_time, p.end_time.normalize(), freq="D"):
                try:
                    out.append(get(f"https://data.binance.vision/data/spot/daily/klines/ETHUSDT/15m/ETHUSDT-15m-{d:%Y-%m-%d}.zip"))
                except urllib.error.HTTPError:
                    pass
            return pd.concat(out, ignore_index=True) if out else None
    with ThreadPoolExecutor(6) as ex:
        df = pd.concat([x for x in ex.map(one, pd.period_range("2021-01", "2026-09", freq="M")) if x is not None], ignore_index=True)
    t = df[0].astype(np.int64).to_numpy()
    t = np.where(t > 10 ** 14, t // 1000, t)
    return pd.DataFrame(dict(o=df[1].astype(float).to_numpy(), h=df[2].astype(float).to_numpy(), l=df[3].astype(float).to_numpy(),
                             c=df[4].astype(float).to_numpy()), index=pd.to_datetime(t, unit="ms", utc=True))


def duka_recent(m, sym):
    DK.POINTS[sym] = 1000.0
    days = [d.date() for d in pd.date_range("2026-04-01", "2026-09-30", freq="D") if d.weekday() != 5]
    with ThreadPoolExecutor(12) as ex:
        got = list(ex.map(lambda d: (d, DK._day_side(d, "BID", sym)), days))
    parts = [pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4]), index=pd.Timestamp(d, tz="UTC") + pd.to_timedelta(b[0], unit="m"))
             for d, b in got if b is not None]
    return pd.concat(parts).sort_index()


def stats(g):
    g = g[g.index < END]
    r = g.h - g.l
    pct = r / g.c * 100
    yr = pd.DataFrame(dict(r=r, p=pct)).groupby(g.index.year).mean()
    last = g.index >= LAST12
    hr = g.index.hour
    ses = {k: dict(r=float(r[last & (hr >= a) & (hr < b)].mean()), p=float(pct[last & (hr >= a) & (hr < b)].mean())) for k, (a, b) in SESS.items()}
    return dict(from_=str(g.index[0].date()), last_mean=float(r[last].mean()), last_median=float(r[last].median()), last_p90=float(r[last].quantile(0.9)),
                last_pct=float(pct[last].mean()), price=float(g.c.iloc[-1]),
                years={int(y): dict(r=float(v.r), p=float(v.p)) for y, v in yr.iterrows()}, sessions=ses)


def main():
    out = {}
    out["XAUUSD"] = stats(m15(duka_m1("XAUUSD", range(2015, 2027)), "bid_open", "bid_high", "bid_low", "bid_close"))
    out["XAGUSD"] = stats(m15(duka_m1("XAGUSD", range(2015, 2027)), "bid_open", "bid_high", "bid_low", "bid_close"))
    b = pd.read_parquet(CACHE / "BTCUSD_binance_M1.parquet")
    out["BTCUSD"] = stats(m15(b, "o", "h", "l", "c"))
    out["ETHUSD"] = stats(eth15())
    for m, sym in (("USDJPY", "USDJPY"), ("JP225", "JPNIDXJPY")):
        out[m] = stats(m15(duka_recent(m, sym), "o", "h", "l", "c"))
    for m, s in out.items():
        print(f"  {m:7s} from {s['from_']}  last 12m: mean {s['last_mean']:.4g}  median {s['last_median']:.4g}  p90 {s['last_p90']:.4g}  = {s['last_pct']:.3f}% of price "
              f"(price {s['price']:.5g})")
        print("     years: " + "  ".join(f"{y}: {v['r']:.4g} ({v['p']:.3f}%)" for y, v in s["years"].items()))
        print("     sessions (last 12m): " + "  ".join(f"{k} {v['r']:.4g}" for k, v in s["sessions"].items()))
    (HERE / "m15_range.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
