"""Bars for the WPWB weekly report.

Frozen history = canonical M5 + the fresh M5 snapshot used by the closed P1
study (data/fresh/XAUUSD_M5.npz, never overwritten here). Weekly updates are
fetched READ-ONLY from the MT5 terminal into data/wpwb_weekly/fresh/ and
appended after the frozen history, so earlier study files keep their hashes.
No order function is ever called.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("research/wpwb_live", "research/wpwb_search", "research/pilot"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
import data as D  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402

WEEKLY_DIR = ROOT / "data" / "wpwb_weekly"
FRESH_DIR = WEEKLY_DIR / "fresh"
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2021-07-02T22:15:00", "s").astype(np.int64))
FREEZE_LAST_CUT = int(np.datetime64("2026-09-18T22:15:00", "s").astype(np.int64))


def _to_bars(z, symbol, step):
    return D.Bars(z["t"], z["o"], z["h"], z["l"], z["c"], z["v"], step, symbol, z.get("sp"))


def load_bars(frozen=False):
    """Canonical + frozen fresh M5; plus weekly-fetched M5 after it unless
    frozen=True."""
    os.chdir(ROOT)
    b = combined_bars()
    f = FRESH_DIR / "XAUUSD_M5.npz"
    if frozen or not f.exists():
        return b
    z = dict(np.load(f))
    k = z["t"] > b.t[-1]
    if not k.any():
        return b
    return D.Bars(np.r_[b.t, z["t"][k]], np.r_[b.o, z["o"][k]], np.r_[b.h, z["h"][k]],
                  np.r_[b.l, z["l"][k]], np.r_[b.c, z["c"][k]], np.r_[b.v, z["v"][k]],
                  300, "XAUUSD", np.r_[b.sp, z["sp"][k]])


def market(b5):
    return C.Market(b5)


def cuts_between(m, first, last):
    """Friday 22:15 UTC cuts first..last inclusive whose week is complete in m."""
    end = int(m.t[-1]) + C.HOUR
    c = [x for x in m.cuts if first <= x <= last and x + WEEK <= end]
    return np.asarray(c, np.int64)


def last_cut_before(now_epoch):
    """Most recent Friday 22:15 UTC cut at or before now."""
    k = (now_epoch - FIRST_CUT) // WEEK
    return int(FIRST_CUT + k * WEEK)


def fetch_weekly(days=60):
    """READ-ONLY fetch: XAUUSD M5, XAUUSD M1, DXY M1 for the last `days` days
    into data/wpwb_weekly/fresh/. Verifies it is only reading."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        acc = mt5.account_info()
        info = dict(server=acc.server, trade_mode=int(acc.trade_mode))
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        start = end - timedelta(days=days)
        FRESH_DIR.mkdir(parents=True, exist_ok=True)
        out = {}
        for sym, tf, name in (("XAUUSD", mt5.TIMEFRAME_M5, "XAUUSD_M5"),
                              ("XAUUSD", mt5.TIMEFRAME_M1, "XAUUSD_M1"),
                              ("DXY", mt5.TIMEFRAME_M1, "DXY_M1")):
            si = mt5.symbol_info(sym)
            if si is None or not mt5.symbol_select(sym, True):
                out[name] = "unavailable"
                continue
            r = mt5.copy_rates_range(sym, tf, start, end)
            if r is None or not len(r):
                out[name] = "no bars"
                continue
            r = r[np.argsort(r["time"])]
            r = r[np.r_[True, r["time"][1:] != r["time"][:-1]]]
            np.savez(FRESH_DIR / f"{name}.npz", t=r["time"].astype(np.int64), o=r["open"],
                     h=r["high"], l=r["low"], c=r["close"],
                     v=r["tick_volume"].astype(float), sp=r["spread"] * si.point)
            out[name] = f"{len(r):,} bars to {datetime.fromtimestamp(int(r['time'][-1]), timezone.utc):%Y-%m-%d %H:%M} UTC"
        return info, out
    finally:
        mt5.shutdown()


def load_m1(symbol):
    """M1 bars: exported CSV history + weekly-fetched M1 after it."""
    csv = ROOT / "data" / f"{symbol}_M1.csv"
    b = D.load_csv(str(csv)) if csv.exists() else None
    f = FRESH_DIR / f"{symbol}_M1.npz"
    if not f.exists():
        return b
    z = dict(np.load(f))
    if b is None:
        return _to_bars(z, symbol, 60)
    k = z["t"] > b.t[-1]
    return D.Bars(np.r_[b.t, z["t"][k]], np.r_[b.o, z["o"][k]], np.r_[b.h, z["h"][k]],
                  np.r_[b.l, z["l"][k]], np.r_[b.c, z["c"][k]], np.r_[b.v, z["v"][k]],
                  60, symbol, None if b.sp is None else np.r_[b.sp, z["sp"][k]])
