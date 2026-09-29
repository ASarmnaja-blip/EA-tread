"""Fetch long daily gold history from Yahoo (instant) as a fast substitute for
the slow Dukascopy pull, and audit it against the broker feed.

GC=F is the COMEX front-month gold FUTURE, not spot XAUUSD: it carries roll
gaps and a different session. It is therefore usable for era context, weekly
magnitude and weekend gaps, but every use must state the instrument. The
overlap audit against Exness D1 quantifies how far apart they are.

Output: data/history/yahoo/GC=F_1d.npz, GLD_1d.npz + audit printout.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "history" / "yahoo"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
       "?interval=1d&period1=0&period2=9999999999")


def fetch(sym):
    req = urllib.request.Request(URL.format(sym=sym), headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=40).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(d["timestamp"], unit="s"))
    return df.dropna(subset=["close"])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = {}
    for sym in ("GC=F", "GLD"):
        df = fetch(sym)
        frames[sym] = df
        np.savez_compressed(OUT / f"{sym.replace('=', '')}_1d.npz",
                            t=df.index.astype("datetime64[s]").astype(np.int64).to_numpy(),
                            o=df.open.to_numpy(), h=df.high.to_numpy(),
                            l=df.low.to_numpy(), c=df.close.to_numpy(),
                            v=df.volume.to_numpy())
        print(f"{sym}: {len(df):,} daily bars {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")

    ex = ROOT / "data" / "history" / "XAUUSD_D1.npz"
    if not ex.exists():
        print("no Exness D1 to audit against"); return 0
    z = np.load(ex)
    xau = pd.Series(z["c"], index=pd.to_datetime(z["t"], unit="s").normalize())
    gc = frames["GC=F"].close
    gc.index = gc.index.normalize()
    j = pd.concat([xau.rename("xau"), gc.rename("gc")], axis=1, join="inner").dropna()
    rx, rg = np.log(j.xau).diff(), np.log(j.gc).diff()
    k = rx.notna() & rg.notna()
    print(f"\naudit on {int(k.sum())} common days {j.index[0]:%Y-%m-%d} .. {j.index[-1]:%Y-%m-%d}")
    print(f"  daily log-return correlation XAUUSD(Exness) vs GC=F(Yahoo): {np.corrcoef(rx[k], rg[k])[0,1]:.4f}")
    print(f"  return SD: XAU {rx[k].std()*1e4:.0f} bp, GC=F {rg[k].std()*1e4:.0f} bp")
    basis = (j.gc / j.xau - 1) * 1e4
    print(f"  futures basis vs spot: median {basis.median():+.0f} bp, "
          f"p5 {basis.quantile(.05):+.0f}, p95 {basis.quantile(.95):+.0f} bp")
    big = (rg[k] - rx[k]).abs().sort_values(ascending=False).head(3)
    print("  largest daily disagreements (roll days / session effects):")
    for d, v in big.items():
        print(f"    {d:%Y-%m-%d}: {v*1e4:.0f} bp apart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
