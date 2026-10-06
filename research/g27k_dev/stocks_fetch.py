#!/usr/bin/env python3
"""Dukascopy H1 bid for the Exness stock list (ledger g27k_us_stocks),
2017-01..2026-09, plus ask for the last six months (spread). Raw prices; split
adjustment happens at load (stocks_load).

Usage: python3 research/g27k_dev/stocks_fetch.py [first] [count]
"""
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK

# Exness stock list: the 90 tickers under "Stocks by industry", help centre article 17854435814428 (updated 2026-09-25)
STOCKS = ['AAPL', 'ABBV', 'ABT', 'ADBE', 'ADP', 'AMD', 'AMGN', 'AMT', 'AMZN', 'AVGO', 'BA', 'BABA', 'BAC', 'BEKE', 'BIDU', 'BIIB', 'BILI',
          'BMY', 'C', 'CHTR', 'CMCSA', 'CME', 'COST', 'CSCO', 'CSX', 'CVS', 'EBAY', 'EDU', 'EQIX', 'F', 'FTNT', 'FUTU', 'GILD', 'GOOGL', 'HD',
          'IBM', 'INTC', 'INTU', 'ISRG', 'JD', 'JNJ', 'JPM', 'KO', 'LI', 'LIN', 'LLY', 'LMT', 'MA', 'MCD', 'MDLZ', 'META', 'MMM', 'MO', 'MRK',
          'MS', 'MSFT', 'NFLX', 'NIO', 'NKE', 'NTES', 'NVDA', 'ORCL', 'PDD', 'PEP', 'PFE', 'PG', 'PM', 'PYPL', 'REGN', 'SBUX', 'SPCX', 'T',
          'TAL', 'TME', 'TMO', 'TMUS', 'TSLA', 'TSM', 'UNH', 'UPS', 'V', 'VIPS', 'VRTX', 'VZ', 'WFC', 'WMT', 'XOM', 'XPEV', 'YUMC', 'ZTO']
CACHE = DK.CACHE
MONTHS = [(y, m) for y in range(2017, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
ASK_MONTHS = [(2026, m) for m in range(4, 10)]


def sym(s):
    return f"{s}USUSD"


def one(task):
    s, (y, m), side = task
    DK.POINTS[sym(s)] = 1000.0
    try:
        b = DK._period_side(f"{y}/{m - 1:02d}", "hour_1", side, sym(s))
    except Exception:
        b = None
    if b is None:
        return s, (y, m), side, None
    df = pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4], v=b[5]),
                      index=pd.Timestamp(f"{y}-{m:02d}-01", tz="UTC") + pd.to_timedelta(b[0], unit="s"))
    return s, (y, m), side, df[df.h > df.l]


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else len(STOCKS)
    names = STOCKS[first:first + count]
    for s in names:
        p = CACHE / f"STK_{s}_H1BID.parquet"
        if p.exists():
            continue
        tasks = [(s, ym, "BID") for ym in MONTHS] + [(s, ym, "ASK") for ym in ASK_MONTHS]
        with ThreadPoolExecutor(12) as ex:
            got = list(ex.map(one, tasks))
        bid = [df for _, _, side, df in got if side == "BID" and df is not None and len(df)]
        ask = [df for _, _, side, df in got if side == "ASK" and df is not None and len(df)]
        if not bid:
            print(f"  {s}: no data", flush=True)
            continue
        B = pd.concat(bid).sort_index()
        B = B[~B.index.duplicated()]
        B.to_parquet(p)
        spread = np.nan
        if ask:
            A = pd.concat(ask).sort_index()
            j = A[["c"]].join(B[["c"]], rsuffix="_b", how="inner")
            sp = (j.c - j.c_b) / ((j.c + j.c_b) / 2) * 1e4
            spread = float(sp[sp > 0].median()) if (sp > 0).any() else np.nan
        meta = CACHE / "STK_spreads.json"
        d = json.loads(meta.read_text()) if meta.exists() else {}
        d[s] = spread
        meta.write_text(json.dumps(d, indent=1))
        print(f"  {s}: {len(B):,} bars {B.index[0].date()}..{B.index[-1].date()}  months {B.index.to_period('M').nunique()}  spread {spread:.1f} bp", flush=True)


if __name__ == "__main__":
    main()
