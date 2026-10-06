#!/usr/bin/env python3
"""Build a long M15 gold history, and prove it is gold before using it.

THE PROBLEM
  Yahoo caps 15-minute data at 60 days and refuses older windows outright
  (HTTP 422 on any period1 further back), so every M15 result in this repo so
  far rests on one two-month window in one regime. That is why the M15 rows in
  `dobby_setup01_sweep_chain.py` and `multi_tf_setup_grid.py` came back with
  samples too small to conclude anything from.

THE SOURCE
  PAXG/USDT on Binance. PAX Gold is a token redeemable for allocated London
  gold, so it tracks spot XAUUSD, and the exchange serves years of 15-minute
  klines with no key. That buys roughly 100x the sample Yahoo will give.

WHAT IT IS NOT
  It is not XAUUSD from a forex broker, and the differences are real:
    - it trades 24/7, including weekends, when the metal does not
    - it carries its own premium and discount to spot, and its own liquidity
    - its spread is a crypto spread, not a metal spread
  So this file also VALIDATES: PAXG is resampled to H1 and correlated against
  GC=F H1 over the two-year overlap Yahoo does serve. A rule discovered here
  has to be confirmed on real XAUUSD M15 before it means anything, and the
  weekend bars are dropped so the session structure matches the metal.
"""
import json, time, urllib.parse, urllib.request, pathlib
import numpy as np, pandas as pd

CACHE = pathlib.Path(__file__).parent / ".cache_m15"
BINANCE = "https://data-api.binance.vision/api/v3/klines"

def _get(url, tries=4):
    for a in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(r, timeout=45))
        except Exception:
            if a == tries - 1: raise
            time.sleep(2 ** a)

def fetch_paxg_m15(symbol="PAXGUSDT", interval="15m", cache=True):
    """Page backwards through Binance klines to the listing date."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{symbol}_{interval}.parquet"
    if cache and f.exists():
        return pd.read_parquet(f)

    end = int(time.time() * 1000)
    rows, seen = [], set()
    while True:
        u = (f"{BINANCE}?symbol={symbol}&interval={interval}"
             f"&endTime={end}&limit=1000")
        batch = _get(u)
        if not batch: break
        batch = [b for b in batch if b[0] not in seen]
        if not batch: break
        for b in batch: seen.add(b[0])
        rows.extend(batch)
        end = min(b[0] for b in batch) - 1
        if len(batch) < 900: break
        if len(rows) > 400_000: break

    rows.sort(key=lambda b: b[0])
    df = pd.DataFrame(
        {"open":  [float(b[1]) for b in rows],
         "high":  [float(b[2]) for b in rows],
         "low":   [float(b[3]) for b in rows],
         "close": [float(b[4]) for b in rows],
         "volume":[float(b[5]) for b in rows]},
        index=pd.to_datetime([b[0] for b in rows], unit="ms", utc=True))
    df = df[~df.index.duplicated()].sort_index()
    if cache:
        try: df.to_parquet(f)
        except Exception: df.to_pickle(f.with_suffix(".pkl"))
    return df

def yahoo(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    d = _get(u)["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def drop_weekend(df):
    """The metal does not trade from Friday 21:00 UTC to Sunday 22:00 UTC.
    Leaving those bars in gives the token a session the metal never had."""
    dow, hr = df.index.dayofweek, df.index.hour
    closed = ((dow == 5) | ((dow == 4) & (hr >= 21)) | ((dow == 6) & (hr < 22)))
    return df[~closed]

def validate(paxg, verbose=True):
    """Correlate PAXG against real gold on the overlap Yahoo will serve."""
    gc = yahoo("GC=F", "730d", "1h")
    ph = paxg.resample("1h").agg({"open":"first","high":"max","low":"min",
                                  "close":"last"}).dropna()
    j = pd.concat([ph.close.rename("paxg"), gc.close.rename("gold")],
                  axis=1, join="inner").dropna()
    if len(j) < 500:
        if verbose: print("  too little overlap to validate")
        return np.nan, np.nan, j
    r = j.pct_change().dropna()
    lvl = float(j.paxg.corr(j.gold))
    ret = float(r.paxg.corr(r.gold))
    if verbose:
        bias = float((j.paxg / j.gold - 1).mean())
        print(f"  overlap            {len(j):,} hourly bars "
              f"{j.index[0].date()} -> {j.index[-1].date()}")
        print(f"  level correlation  {lvl:.4f}")
        print(f"  RETURN correlation {ret:.4f}   <- the one that matters")
        print(f"  mean premium       {bias:+.3%}")
    return lvl, ret, j

def main():
    print("Fetching PAXG/USDT 15m from Binance (paged back to listing) ...")
    p = fetch_paxg_m15()
    print(f"  {len(p):,} bars  {p.index[0].date()} -> {p.index[-1].date()}")
    pw = drop_weekend(p)
    print(f"  {len(pw):,} bars after dropping the metal's closed hours "
          f"({1-len(pw)/len(p):.1%} removed)\n")
    print("Validating against real gold (GC=F H1, Yahoo's 730 days):")
    lvl, ret, _ = validate(pw)
    print()
    if np.isfinite(ret) and ret >= 0.90:
        print(f"  Return correlation {ret:.3f} - close enough to test M15 LOGIC on,")
        print("  provided anything found is confirmed on real XAUUSD M15 after.")
    else:
        print(f"  Return correlation {ret:.3f} - too loose to stand in for gold.")
        print("  Treat findings from this series as a separate market.")

if __name__ == "__main__":
    main()
