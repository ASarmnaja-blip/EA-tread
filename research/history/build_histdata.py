"""HistData XAUUSD M1 (2009-2021; local time per histdata_time.py: New York to 2018, EST + EU summer time from 2019; bar-open labels; price ~ bid) -> UTC mid M1, spliced
with the live Exness M5 feed from 2021-01-01 (bars.load_bars, bid + half spread). Mid adjustment: HistData + the median
(Dukascopy H1 mid close - HistData hourly close) per calendar year. Writes data/history/histdata/XAUUSD_M1_2009_2020_utc.npz
and data/history/XAUUSD_M5_2009_2026_spliced.npz. Operator approved the download 2026-09-30."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "foundry"), str(ROOT / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402
sys.path.insert(0, str(ROOT / "research" / "history"))
from histdata_time import histdata_utc  # noqa: E402

H, _, _, _ = E.load()
dh = pd.Series(H.c, index=pd.to_datetime(H.t, unit="s"))
parts = []
for y in range(2009, 2021):
    z = zipfile.ZipFile(ROOT / "data" / "history" / "histdata" / f"XAUUSD_M1_{y}.zip")
    n = [x for x in z.namelist() if x.endswith(".csv")][0]
    d = pd.read_csv(io.BytesIO(z.read(n)), sep=";", header=None, names=["ts", "o", "h", "l", "c", "v"])
    tu = histdata_utc(d.ts)                                   # New York time to 2018, EST + EU summer time from 2019 (histdata_time.py)
    d = d[tu.notna().to_numpy()].copy(); d["t"] = pd.to_datetime(tu.dropna().astype("int64").to_numpy(), unit="s")
    s = pd.Series(d.c.to_numpy(), index=d.t).resample("1h").last().dropna()
    j = s.index.intersection(dh.index)
    off = float((dh[j] - s[j]).median())
    for c in "ohlc":
        d[c] = d[c] + off
    parts.append(d[["t", "o", "h", "l", "c", "v"]])
    print(y, len(d), f"offset to Dukascopy mid {off:+.3f}", flush=True)
M1 = pd.concat(parts).drop_duplicates("t").sort_values("t")
t1 = M1.t.to_numpy().astype("datetime64[s]").astype(np.int64)
np.savez_compressed(ROOT / "data" / "history" / "histdata" / "XAUUSD_M1_2009_2020_utc.npz", t=t1,
                    **{c: M1[c].to_numpy(float) for c in "ohlcv"})
k = t1 // 300
g = pd.DataFrame(dict(k=k, o=M1.o.to_numpy(), h=M1.h.to_numpy(), l=M1.l.to_numpy(), c=M1.c.to_numpy(), v=M1.v.to_numpy())).groupby("k").agg(
    o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
import bars as BR
b5 = BR.load_bars(frozen=False)
half = np.asarray(b5.sp, float) / 2
te = np.asarray(b5.t, np.int64); keep = te >= int(pd.Timestamp("2021-01-01").timestamp())
t5 = np.r_[g.index.to_numpy() * 300, te[keep]]
arr = {c: np.r_[g[c].to_numpy(float), (np.asarray(getattr(b5, c), float) + half)[keep]] for c in "ohlc"}
arr["v"] = np.r_[g.v.to_numpy(float), np.asarray(b5.v, float)[keep]]
arr["sp_bp"] = np.r_[np.full(len(g), np.nan), (np.asarray(b5.sp, float) / (np.asarray(b5.c, float) + half) * 1e4)[keep]]
o = np.argsort(t5, kind="stable")
np.savez_compressed(ROOT / "data" / "history" / "XAUUSD_M5_2009_2026_spliced.npz", t=t5[o], **{c: v[o] for c, v in arr.items()})
print(f"M5 spliced: {len(t5):,} bars {pd.to_datetime(t5.min(), unit='s')} .. {pd.to_datetime(t5.max(), unit='s')}")
