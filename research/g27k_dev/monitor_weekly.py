#!/usr/bin/env python3
"""Weekly G27K #1 monitor: fresh prices, the system's recent trades, a paper
account, and the risk rule the user agreed to (2026-10-04).

Data: Dukascopy H1 bid (gold, silver, USDJPY, JP225) and Binance 1h (BTC, ETH)
from 2025-01-01 to now, cached under .cache_duka/live_*.parquet and topped up
each run. Trades: G27K #1 exactly as in the research (fresh_markets.trades).
Paper account: Standard 6 markets from LIVE_START, 0.75% per trade, BTC/ETH
0.375%, 25% brake.

Risk rule (results first, news only raises attention):
  NORMAL   0.75% (crypto 0.375%)
  WATCH    paper DD >= 12% or a losing streak >= 12 trades: tell the user, no change
  REDUCE   paper DD >= 20%: recommend 0.5% (crypto 0.25%)
  DEFENCE  paper DD >= 25%: the EA brake halves risk by itself; recommend 0.375%
  RESTORE  back to NORMAL once paper DD < 10%

Usage: python3 research/g27k_dev/monitor_weekly.py [--root <snapshot>]
"""
import argparse
import io
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK

FROM, LIVE_START = "2025-01-01", "2025-10-01"
DUKA = {"XAUUSD": ("XAUUSD", 1000.0), "XAGUSD": ("XAGUSD", 1000.0), "USDJPY": ("USDJPY", 1000.0), "JP225": ("JPNIDXJPY", 1000.0)}
BINANCE = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY", "JP225")
BASE, CRYPTO = 0.0075, 0.00375
SNAP_BRANCH = "origin/data-snapshot-2026-10-03"
LOG = HERE / "monitor_log.jsonl"


def snapshot(root):
    p = pathlib.Path(root) if root else HERE.parent / ".cache_duka" / "snap_monitor"
    if not (p / "research" / "grid768").exists():
        subprocess.run(["git", "-C", str(REPO), "fetch", "origin", SNAP_BRANCH.split("/", 1)[1]], check=True)
        subprocess.run(["git", "-C", str(REPO), "worktree", "add", "--detach", str(p), SNAP_BRANCH], check=True)
    return p


def duka(m):
    sym, pt = DUKA[m]
    DK.POINTS[sym] = pt
    cache = DK.CACHE / f"live_{m}_H1.parquet"
    old = pd.read_parquet(cache) if cache.exists() else None
    now = pd.Timestamp.now(tz="UTC")
    start = pd.Timestamp(FROM, tz="UTC") if old is None else old.index[-1].normalize().replace(day=1) - pd.offsets.MonthBegin(1)
    months = pd.period_range(start.tz_localize(None), now.tz_localize(None), freq="M")
    parts = []
    for p in months:
        if p == pd.Period(now.tz_localize(None), "M"):
            days = [d.date() for d in pd.date_range(p.start_time, now.tz_localize(None).normalize(), freq="D")]
            with ThreadPoolExecutor(8) as ex:
                got = list(ex.map(lambda d: (d, DK._day_side(d, "BID", sym)), days))
            for d, b in got:
                if b is None:
                    continue
                df = pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4], v=b[5]), index=pd.Timestamp(d, tz="UTC") + pd.to_timedelta(b[0], unit="m"))
                parts.append(df.resample("1h").agg(dict(o="first", h="max", l="min", c="last", v="sum")).dropna())
        else:
            b = DK._period_side(f"{p.year}/{p.month - 1:02d}", "hour_1", "BID", sym)
            if b is not None:
                parts.append(pd.DataFrame(dict(o=b[1], h=b[2], l=b[3], c=b[4], v=b[5]),
                                          index=pd.Timestamp(p.start_time, tz="UTC") + pd.to_timedelta(b[0], unit="s")))
    new = pd.concat(([old] if old is not None else []) + parts).sort_index()
    new = new[~new.index.duplicated(keep="last")]
    new = new[new.h > new.l]
    new.to_parquet(cache)
    return new


def binance(m):
    pair = BINANCE[m]
    cache = DK.CACHE / f"live_{m}_H1.parquet"
    old = pd.read_parquet(cache) if cache.exists() else None
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    start = pd.Timestamp(FROM) if old is None else old.index[-1].tz_localize(None).normalize().replace(day=1) - pd.offsets.MonthBegin(1)

    def zipcsv(u):
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        return pd.read_csv(z.open(z.namelist()[0]), header=None)

    def one(p):
        try:
            return zipcsv(f"https://data.binance.vision/data/spot/monthly/klines/{pair}/1h/{pair}-1h-{p.year}-{p.month:02d}.zip")
        except urllib.error.HTTPError:
            out = []
            for d in pd.date_range(p.start_time, min(p.end_time.normalize(), now.normalize()), freq="D"):
                try:
                    out.append(zipcsv(f"https://data.binance.vision/data/spot/daily/klines/{pair}/1h/{pair}-1h-{d:%Y-%m-%d}.zip"))
                except urllib.error.HTTPError:
                    pass
            return pd.concat(out, ignore_index=True) if out else None

    with ThreadPoolExecutor(6) as ex:
        dfs = [x for x in ex.map(one, pd.period_range(start, now, freq="M")) if x is not None]
    df = pd.concat(dfs, ignore_index=True)
    t = df[0].astype(np.int64).to_numpy()
    t = np.where(t > 10 ** 14, t // 1000, t)
    new = pd.DataFrame(dict(o=df[1].to_numpy(float), h=df[2].to_numpy(float), l=df[3].to_numpy(float), c=df[4].to_numpy(float),
                            v=df[5].to_numpy(float)), index=pd.to_datetime(t, unit="ms", utc=True))
    new = pd.concat(([old] if old is not None else []) + [new]).sort_index()
    new = new[~new.index.duplicated(keep="last")]
    new.to_parquet(cache)
    return new


def as_bars(d):
    t = ((d.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    return dict(t=t, o=d.o.to_numpy(float), h=d.h.to_numpy(float), l=d.l.to_numpy(float), c=d.c.to_numpy(float), v=d.v.to_numpy(float), step=3600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    a = ap.parse_args()
    root = snapshot(a.root)
    import fresh_markets as FM
    import h4d1_pattern_search as P
    import walkforward_controller as W
    P.setup(str(root))
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(root / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    C.SPECS["ETHUSD"] = dict(C.SPECS["BTCUSD"])
    ext = K.externals()
    bars = {m: (binance(m) if m in BINANCE else duka(m)) for m in MKTS}
    last = {m: str(d.index[-1]) for m, d in bars.items()}
    T = pd.concat([FM.trades(m, as_bars(d), RP, G, K, ext).assign(mkt=m) for m, d in bars.items()], ignore_index=True)
    end_t = min(int(d.index[-1].timestamp()) for d in bars.values())
    T = T[T.t >= W.ts(LIVE_START)].sort_values("t").reset_index(drop=True)
    T["open"] = T.tx >= end_t - 4 * 3600
    closed = T[~T.open]
    # paper account: closed trades, brake 25%
    bal, peak, dd_max, braked, path = 1.0, 1.0, 0.0, False, []
    for _, r in closed.sort_values("tx").iterrows():
        risk = (CRYPTO if r.mkt in BINANCE else BASE) * (0.5 if braked else 1.0)
        bal += bal * risk * r.R
        peak = max(peak, bal)
        now = 1 - bal / peak
        dd_max = max(dd_max, now)
        braked = now >= 0.25 or (braked and now > 0.125)
        path.append(now)
    dd_now = path[-1] if path else 0.0
    streak = 0
    for R in closed.sort_values("tx").R[::-1]:
        if R > 0:
            break
        streak += 1
    prev = json.loads(LOG.read_text().strip().splitlines()[-1]) if LOG.exists() and LOG.read_text().strip() else {}
    state = prev.get("state", "NORMAL")
    if dd_now >= 0.25:
        state = "DEFENCE"
    elif dd_now >= 0.20:
        state = "REDUCE"
    elif dd_now >= 0.12 or streak >= 12:
        state = state if state in ("REDUCE", "DEFENCE") and dd_now >= 0.10 else "WATCH"
    elif dd_now < 0.10:
        state = "NORMAL"
    risk = {"NORMAL": "0.75% (คริปโต 0.375%)", "WATCH": "0.75% (คริปโต 0.375%) เฝ้าระวัง", "REDUCE": "0.5% (คริปโต 0.25%)",
            "DEFENCE": "0.375% (คริปโต 0.19%) และเบรกของ EA ทำงาน"}[state]
    wk = W.ts(str((pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).date()))
    q = W.ts(str((pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=91)).date()))
    rec = dict(run=str(pd.Timestamp.now(tz="UTC").floor("min")), data_to=last, state=state, risk=risk, paper_return=bal - 1, dd_now=dd_now, dd_max=dd_max,
               losing_streak=streak, closed=len(closed), week_R=float(closed.R[closed.tx >= wk].sum()), q_R=float(closed.R[closed.tx >= q].sum()),
               q_n=int((closed.tx >= q).sum()),
               per_mkt_q={m: float(closed.R[(closed.tx >= q) & (closed.mkt == m)].sum()) for m in MKTS},
               open=[dict(mkt=r.mkt, since=str(pd.Timestamp(r.t, unit="s")), R_now=round(float(r.R), 2)) for _, r in T[T.open].iterrows()],
               new_this_week=[dict(mkt=r.mkt, t=str(pd.Timestamp(r.t, unit="s")), R=round(float(r.R), 2), open=bool(r.open)) for _, r in T[T.t >= wk].iterrows()])
    with LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=float) + "\n")
    print(json.dumps(rec, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
