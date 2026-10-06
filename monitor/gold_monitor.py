#!/usr/bin/env python3
"""Gold monitor: live state of the three systems, a forward paper log, and the
market-condition gauges, from Dukascopy data no older than the last full hour.

No orders are sent. Everything is recomputed from data on every run, so the
paper log needs no saved state and two runs on the same data agree exactly.

Data: completed months from Dukascopy hourly files; the current (and, early
in a month, the previous) month from hourly tick files, which Dukascopy
publishes within the hour. Tick-built bars were checked against the monthly
files and match to the last decimal.

Systems (rules and formulas identical to the research code):
  H4-55  long when an H4 close exceeds the prior 55-bar high while ATR14 is at
         or above the median of its last 250 bars; stop 2 x ATR20; exit when a
         close falls below the prior 20-bar low.
  D1-1   long when a daily close exceeds the prior 20-day high while the last
         closed week is above the midpoint of its 55-week range; same stop and
         exit on daily bars.
  QB     (quiet breakout, the research candidate) H4, long or short: close
         within 1.879 ATR14 of the prior 100-bar extreme or beyond it, ATR14 in
         the lower 57.6% of its last 250 bars, and no close beyond the prior
         55-bar extreme that way for at least 37 bars; stop 2 x ATR20; exit on
         a close through the prior 10-bar channel.
Stops are walked on H1 bars inside each bar; entries at the next bar's open.

Usage: python3 monitor/gold_monitor.py --out-dir <dir>
"""
import argparse
import datetime as dt
import json
import lzma
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import fetch_dukascopy as DK  # noqa: E402

FORWARD_START = pd.Timestamp("2026-10-02 06:00", tz="UTC")
HISTORY_MONTHS = 16
SPREAD_USD = 0.26
SWAP_LONG_BP = 1.2968641458960126
W1_FIRST = pd.Timestamp("2003-05-09 22:15", tz="UTC")


# ------------------------------------------------------------------ data
def hour_ticks(t0):
    url = (f"{DK.BASE}/XAUUSD/{t0.year}/{t0.month - 1:02d}/{t0.day:02d}/"
           f"{t0.hour:02d}h_ticks.bi5")
    raw = DK._get(url)
    if not raw:
        return None
    try:
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(raw)
    except Exception:
        return None
    a = np.frombuffer(dec[:len(dec) // 20 * 20], dtype=">u4,>u4,>u4,>f4,>f4")
    if len(a) == 0:
        return None
    idx = t0 + pd.to_timedelta(a["f0"].astype(np.int64), unit="ms")
    return pd.DataFrame(dict(ask=a["f1"] / 1000.0, bid=a["f2"] / 1000.0), index=idx)


def ticks_to_h1(frames):
    rows, spreads = [], []
    for tk in frames:
        if tk is None or len(tk) == 0:
            continue
        mid = (tk.bid + tk.ask) / 2
        rows.append(dict(t=tk.index[0].floor("h"), o=mid.iloc[0], h=mid.max(),
                         l=mid.min(), c=mid.iloc[-1], v=float(len(tk))))
        spreads.append(((tk.ask - tk.bid) / mid * 1e4).to_numpy())
    df = pd.DataFrame(rows).set_index("t") if rows else None
    return df, (np.concatenate(spreads) if spreads else np.array([]))


def load_h1(now):
    first = (now - pd.DateOffset(months=HISTORY_MONTHS)).replace(day=1)
    months = pd.period_range(first, now, freq="M")
    parts, tick_hours = [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda p: DK.fetch_h1_month((p.year, p.month)), months))
    covered_until = None
    for p, df in zip(months, res):
        if df is None:
            continue
        mid = pd.DataFrame(dict(o=(df.bid_open + df.ask_open) / 2,
                                h=(df.bid_high + df.ask_high) / 2,
                                l=(df.bid_low + df.ask_low) / 2,
                                c=(df.bid_close + df.ask_close) / 2,
                                v=df.volume))
        parts.append(mid)
        covered_until = mid.index[-1]
    start = (covered_until + pd.Timedelta(hours=1)) if covered_until is not None else first
    hrs = pd.date_range(start.floor("h"), now.floor("h") - pd.Timedelta(hours=1), freq="h")
    hrs = [h for h in hrs if h.dayofweek != 5]
    with ThreadPoolExecutor(max_workers=16) as ex:
        tks = list(ex.map(hour_ticks, hrs))
    th1, _ = ticks_to_h1(tks)
    if th1 is not None:
        parts.append(th1)
    recent = [t for t in tks[-24:] if t is not None]
    _, spreads_24h = ticks_to_h1(recent)
    h1 = pd.concat(parts).sort_index()
    h1 = h1[~h1.index.duplicated(keep="last")]
    h1 = h1[h1.h > h1.l]
    return h1, spreads_24h


# ------------------------------------------------------------------ bars
def agg(h1, key):
    g = h1.assign(k=key).groupby("k", sort=True)
    X = pd.DataFrame(dict(t=g.apply(lambda d: d.index[0]), o=g.o.first(), h=g.h.max(),
                          l=g.l.min(), c=g.c.last()))
    X = X.reset_index(drop=True)
    X["ts"] = ((X.t - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype(np.int64)
    pc = X.c.shift()
    tr = np.maximum(X.h - X.l, np.maximum((X.h - pc).abs(), (X.l - pc).abs()))
    tr.iloc[0] = X.h.iloc[0] - X.l.iloc[0]
    for n in (14, 20):
        X[f"a{n}"] = tr.rolling(n, min_periods=n).mean()
    X["apct"] = X.a14.rolling(250, min_periods=100).rank(pct=True)
    for n in (10, 20, 55, 100):
        X[f"hi{n}"] = X.h.rolling(n).max().shift()
        X[f"lo{n}"] = X.l.rolling(n).min().shift()
    kk = np.asarray(key)
    X["k0"] = np.flatnonzero(np.r_[True, kk[1:] != kk[:-1]])
    X["k1"] = np.r_[X.k0.to_numpy()[1:], len(kk)]
    return X


def frames(h1):
    sec = (h1.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")
    sec = np.asarray(sec, np.int64)
    cuts = np.arange(int(W1_FIRST.timestamp()), int(sec[-1]) + 14 * 86400, 7 * 86400)
    return dict(H4=agg(h1, (sec - 22 * 3600) // 14400), D1=agg(h1, sec // 86400),
                W1=agg(h1, np.searchsorted(cuts, sec, side="right") - 1),
                sec=dict(H4=14400, D1=86400, W1=7 * 86400))


def w1_filter(D, W):
    """Sign of the last FULLY closed week against its 55-week midpoint, as of
    each daily close (the research anchor: a week counts once it has closed)."""
    BIG = np.iinfo(np.int64).max
    wt, dt_ = W.ts.to_numpy(), D.ts.to_numpy()
    ac = np.minimum(np.r_[wt[1:], BIG], wt + 7 * 86400)
    xc = np.minimum(np.r_[dt_[1:], BIG], dt_ + 86400)
    j = np.searchsorted(ac, xc, side="right") - 1
    mid = (W.h.rolling(55).max() + W.l.rolling(55).min()).to_numpy() / 2
    jj = np.maximum(j, 0)
    with np.errstate(invalid="ignore"):
        v = np.where(j >= 0, np.sign(W.c.to_numpy()[jj] - mid[jj]), 0)
    return np.nan_to_num(v)


def since_break(X, n=55):
    c = X.c.to_numpy()
    up, dn = (c > X[f"hi{n}"].to_numpy()), (c < X[f"lo{n}"].to_numpy())
    su, sd = np.zeros(len(c)), np.zeros(len(c))
    lu = ld = -10 ** 6
    for i in range(len(c)):
        su[i], sd[i] = min(i - lu, 500), min(i - ld, 500)
        if up[i]:
            lu = i
        if dn[i]:
            ld = i
    return su, sd


def signals(F):
    H, D = F["H4"], F["D1"]
    out = {}
    with np.errstate(invalid="ignore"):
        out["H4-55"] = ("H4", "ch20", np.where((H.c > H.hi55) & (H.apct >= 0.5), 1, 0))
        w1 = w1_filter(D, F["W1"])
        out["D1-1"] = ("D1", "ch20", np.where((D.c > D.hi20) & (w1 > 0), 1, 0))
        su, sd = since_break(H)
        a = H.a14
        lng = ((H.c - H.hi100) / a >= -1.879) & (H.apct <= 0.576) & (su >= 37)
        sht = ((H.lo100 - H.c) / a >= -1.879) & (H.apct <= 0.576) & (sd >= 37)
        out["QB"] = ("H4", "ch10", np.where(lng, 1, np.where(sht, -1, 0)))
    return out


# ------------------------------------------------------------------ paper trades
def simulate(X, h1, sig, exit_mode, sec, start):
    """Same rules as the research simulator; one open trade at a time."""
    o, h, l, c = (X[k].to_numpy() for k in ("o", "h", "l", "c"))
    a20 = X.a20.to_numpy()
    lo, hi = (X.lo20, X.hi20) if exit_mode == "ch20" else (X.lo10, X.hi10)
    lo, hi = lo.to_numpy(), hi.to_numpy()
    bh, bl, bo = h1.h.to_numpy(), h1.l.to_numpy(), h1.o.to_numpy()
    bt = h1.index
    k0, k1 = X.k0.to_numpy(), X.k1.to_numpy()
    n = len(c)
    trades, busy = [], -1
    first = int(np.searchsorted(X.ts.to_numpy(), int(start.timestamp()) - sec))
    for s in range(max(first, 0), n):
        d = sig[s]
        if d == 0 or s <= busy or not np.isfinite(a20[s]):
            continue
        rec = dict(signal_close=str(X.t.iloc[s] + pd.Timedelta(seconds=sec)), dir=int(d))
        if s + 1 >= n:
            rec.update(status="PENDING", note="enters at the next bar's open")
            trades.append(rec)
            break
        e = s + 1
        ep = o[e]
        risk = 2.0 * a20[s]
        stop = ep - d * risk
        rec.update(entry_time=str(X.t.iloc[e]), entry=round(ep, 3), stop=round(stop, 3),
                   risk_usd=round(risk, 3))
        j, px, tx, why = e, None, None, None
        while j < n:
            for q in range(k0[j], k1[j]):
                oq = ep if q == k0[e] else bo[q]
                if (d > 0 and bl[q] <= stop) or (d < 0 and bh[q] >= stop):
                    px = stop if d * (oq - stop) > 0 else oq
                    tx, why = bt[q], "stop"
                    break
            if px is not None:
                break
            if j + 1 < n and ((d > 0 and c[j] < lo[j]) or (d < 0 and c[j] > hi[j])):
                j += 1
                px, tx, why = o[j], X.t.iloc[j], "channel exit"
                break
            j += 1
        if px is None:
            last = c[-1]
            rec.update(status="OPEN", last=round(last, 3),
                       open_R=round(d * (last - ep) / risk, 2),
                       exit_level=round(lo[-1] if d > 0 else hi[-1], 3),
                       to_stop_atr=round(d * (last - stop) / X.a14.iloc[-1], 2))
            trades.append(rec)
            break
        nights = max(0, (pd.Timestamp(tx) - pd.Timestamp(X.t.iloc[e])).days)
        cost = SPREAD_USD + 1e-4 * ep + (ep * SWAP_LONG_BP / 1e4 * nights if d > 0 else 0)
        rec.update(status="CLOSED", exit_time=str(tx), exit=round(px, 3), reason=why,
                   R=round((d * (px - ep) - cost) / risk, 3))
        trades.append(rec)
        busy = j
    return trades


# ------------------------------------------------------------------ gauges
def gauges(F, h1, spreads_24h):
    H, D = F["H4"], F["D1"]
    last = H.iloc[-1]
    dr = np.log(D.c).diff()
    vol20 = float(dr.tail(20).std() * np.sqrt(252) * 100)
    hi55, c = H.hi55.to_numpy(), H.c.to_numpy()
    yr = H.t >= H.t.iloc[-1] - pd.Timedelta(days=365)
    brk = np.flatnonzero((c > hi55) & yr.to_numpy())
    fails = [bool((c[i + 1:i + 4] < hi55[i]).any()) for i in brk if i + 3 < len(c)]
    su, sd = since_break(H)
    a = last.a14
    g = dict(
        price=round(float(h1.c.iloc[-1]), 2), last_closed_h4=round(float(last.c), 2),
        bar_close=str(last.t + pd.Timedelta(hours=4)),
        h4_atr_usd=round(float(a), 2), h4_atr_pct_of_year=round(float(last.apct), 3),
        vol20_annual_pct=round(vol20, 1),
        vol_context="17-year annual range 8-18%, 2026 so far 29% (record)",
        false_breakout_rate_12m=round(float(np.mean(fails)), 3) if fails else None,
        false_breakout_context="17-year range 29-51%, 2025-26 lowest",
        spread_24h_median_bp=round(float(np.median(spreads_24h)), 2) if len(spreads_24h) else None,
        spread_24h_p999_bp=round(float(np.quantile(spreads_24h, 0.999)), 2) if len(spreads_24h) else None,
        spread_context="2023-26 median 1.5-1.7bp, worst-0.1% 4.9-8.2bp",
        last_h1=str(h1.index[-1]),
    )
    g["distance"] = {
        "H4-55 long": dict(to_trigger_atr=round(float((last.hi55 - last.c) / a), 2),
                           filter_ok=bool(last.apct >= 0.5)),
        "D1-1 long": dict(to_trigger_atr=round(float((D.hi20.iloc[-1] - D.c.iloc[-1]) / D.a14.iloc[-1]), 2),
                          w1_filter_ok=bool(w1_filter(D, F["W1"])[-1] > 0)),
        "QB long": dict(gap_atr=round(float((last.hi100 - last.c) / a), 2), need_gap_atr=1.879,
                        quiet_ok=bool(last.apct <= 0.576), bars_since_55_break=int(su[-1]), need=37),
        "QB short": dict(gap_atr=round(float((last.c - last.lo100) / a), 2), need_gap_atr=1.879,
                         quiet_ok=bool(last.apct <= 0.576), bars_since_55_break=int(sd[-1]), need=37),
    }
    return g


def noteworthy(sysmap, g):
    flags = []
    for name, tr in sysmap.items():
        for t in tr:
            if t["status"] in ("PENDING", "OPEN") or (
                    t["status"] == "CLOSED" and pd.Timestamp(t["exit_time"]) >= pd.Timestamp(g["bar_close"]) - pd.Timedelta(hours=8)):
                flags.append(f"{name}: {t['status']} {'long' if t['dir'] > 0 else 'short'}"
                             + (f" R {t['R']:+.2f}" if t["status"] == "CLOSED" else ""))
    dd = g["distance"]
    if dd["H4-55 long"]["filter_ok"] and dd["H4-55 long"]["to_trigger_atr"] < 0.5:
        flags.append("H4-55 within 0.5 ATR of a long signal")
    for k in ("QB long", "QB short"):
        q = dd[k]
        if q["quiet_ok"] and q["bars_since_55_break"] >= q["need"] and q["gap_atr"] < q["need_gap_atr"] + 0.5:
            flags.append(f"{k} within 0.5 ATR of a signal")
    if g["spread_24h_p999_bp"] and g["spread_24h_p999_bp"] > 16:
        flags.append(f"spread spike: worst-0.1% {g['spread_24h_p999_bp']}bp (normal 5-8)")
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "monitor" / "out"))
    a = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    h1, spreads_24h = load_h1(now)
    F = frames(h1)
    for tf in ("H4", "D1"):
        X = F[tf]
        done = (X.t + pd.Timedelta(seconds=F["sec"][tf])) <= h1.index[-1] + pd.Timedelta(hours=1)
        F[tf] = X[done.to_numpy()].reset_index(drop=True)
    sysmap = {}
    for name, (tf, ex, sig) in signals(F).items():
        sysmap[name] = simulate(F[tf], h1, sig, ex, F["sec"][tf], FORWARD_START)
    g = gauges(F, h1, spreads_24h)
    out = dict(run_utc=str(now), forward_start=str(FORWARD_START), gauges=g,
               paper=sysmap, flags=noteworthy(sysmap, g))
    od = pathlib.Path(a.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    (od / "latest.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
