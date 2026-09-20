"""
Data access for the setup pilot.

IMPORTANT: the only gold this container can reach is COMEX gold FUTURES.
There is no XAUUSD spot feed here. Nothing produced from this module may be
labelled XAUUSD. See docs/PILOT_PREREGISTRATION.md section 1.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

CACHE = Path(__file__).resolve().parent / "cache"
SYMBOL = "GC=F"          # COMEX gold futures, front contract
INSTRUMENT_LABEL = "COMEX gold futures (GC=F) - NOT XAUUSD spot"

SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


class Bars:
    """OHLCV with epoch-second timestamps, UTC throughout, nulls dropped."""

    __slots__ = ("t", "o", "h", "l", "c", "v", "step", "symbol", "sp")

    def __init__(self, t, o, h, l, c, v, step, symbol, sp=None):
        self.t = np.asarray(t, dtype=np.int64)
        self.o = np.asarray(o, dtype=float)
        self.h = np.asarray(h, dtype=float)
        self.l = np.asarray(l, dtype=float)
        self.c = np.asarray(c, dtype=float)
        self.v = np.asarray(v, dtype=float)
        self.step = step
        self.symbol = symbol
        # Per-bar spread in PRICE units, when the source recorded one.
        # None means the cost has to be assumed instead of measured.
        self.sp = None if sp is None else np.asarray(sp, dtype=float)

    def __len__(self):
        return len(self.t)

    def slice(self, i, j):
        return Bars(self.t[i:j], self.o[i:j], self.h[i:j], self.l[i:j],
                    self.c[i:j], self.v[i:j], self.step, self.symbol,
                    None if self.sp is None else self.sp[i:j])


def _fetch(symbol: str, rng: str, interval: str) -> dict:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol) + f"?range={rng}&interval={interval}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.load(resp)["chart"]["result"][0]


def load(symbol: str, rng: str, interval: str, refresh: bool = False) -> Bars:
    """Fetch (or reuse a cached copy of) one series. Null bars are dropped."""
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"{symbol.replace('=', '_')}_{rng}_{interval}.json"
    if key.exists() and not refresh:
        raw = json.loads(key.read_text())
    else:
        for attempt in range(4):
            try:
                raw = _fetch(symbol, rng, interval)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        key.write_text(json.dumps(raw))

    ts = raw["timestamp"]
    q = raw["indicators"]["quote"][0]
    keep = [i for i in range(len(ts))
            if q["close"][i] is not None and q["open"][i] is not None
            and q["high"][i] is not None and q["low"][i] is not None]
    return Bars([ts[i] for i in keep],
                [q["open"][i] for i in keep],
                [q["high"][i] for i in keep],
                [q["low"][i] for i in keep],
                [q["close"][i] for i in keep],
                [(q["volume"][i] or 0) for i in keep],
                SEC[interval], symbol)


def to_15m(b5: Bars) -> tuple[Bars, np.ndarray]:
    """Build 15m bars from 5m bars.

    A 15m bar exists only when all three of its 5m bars are present and
    contiguous, so a bar spanning a session break is never manufactured.

    A 15m bar LABELLED t covers [t, t+900) and CLOSES at t+900. The index
    returned alongside points at the 5m bar starting at t+900 - the first bar
    that could be traded on - or -1 when there is none. Getting this wrong in
    the other direction is the 15-minute look-ahead the research log records.
    """
    assert b5.step == 300
    t = b5.t
    start = t - (t % 900)
    n = len(b5)
    out_t, out_o, out_h, out_l, out_c, out_v, nxt = [], [], [], [], [], [], []

    i = 0
    while i + 2 < n:
        if t[i] % 900 != 0:
            i += 1
            continue
        if t[i + 1] != t[i] + 300 or t[i + 2] != t[i] + 600:
            i += 1
            continue
        out_t.append(t[i])
        out_o.append(b5.o[i])
        out_h.append(max(b5.h[i], b5.h[i + 1], b5.h[i + 2]))
        out_l.append(min(b5.l[i], b5.l[i + 1], b5.l[i + 2]))
        out_c.append(b5.c[i + 2])
        out_v.append(b5.v[i] + b5.v[i + 1] + b5.v[i + 2])
        # the tradeable bar is the 5m bar that starts exactly at close time
        k = i + 3
        nxt.append(k if (k < n and t[k] == t[i] + 900) else -1)
        i += 3

    b15 = Bars(out_t, out_o, out_h, out_l, out_c, out_v, 900, b5.symbol)
    return b15, np.asarray(nxt, dtype=np.int64)


def describe(b: Bars, name: str) -> str:
    import datetime as dt
    lo = dt.datetime.fromtimestamp(int(b.t[0]), dt.timezone.utc)
    hi = dt.datetime.fromtimestamp(int(b.t[-1]), dt.timezone.utc)
    gaps = int(np.sum(np.diff(b.t) > b.step * 1.5))
    return (f"{name:10s} n={len(b):6d} step={b.step:5d}s gaps={gaps:4d} "
            f"{lo:%Y-%m-%d %H:%M}..{hi:%Y-%m-%d %H:%M} UTC")


# --------------------------------------------------------------- MT5 CSV
def load_csv(path, meta_path=None, server_offset_hours=None) -> Bars:
    """Load a file written by tools/export_mt5_data.py.

    TIMEZONE. `mt5.copy_rates_range` returns BROKER SERVER TIME, encoded as an
    epoch, and the exporter writes it through unchanged. The meta file does not
    record the server's offset, so it must be supplied. Getting this wrong
    silently shifts every session bucket, which is the kind of error that is
    invisible in a summary statistic and fatal in a session-split result -
    so a missing offset is an error here rather than a default.

    SPREAD. The export carries MT5's own per-bar spread in points. With `point`
    from the meta file it becomes price units, and the cost side stops being an
    assumption. A file without that column loads with `sp = None`, and anything
    downstream must then say out loud that its cost is assumed.
    """
    import csv as _csv
    import datetime as _dt

    path = Path(path)
    point = None
    if meta_path is None:
        cand = path.with_suffix(".meta.json")
        meta_path = cand if cand.exists() else None
    if meta_path is not None:
        meta = json.loads(Path(meta_path).read_text())
        point = float(meta.get("point") or 0.0) or None
        if server_offset_hours is None and meta.get("server_offset_hours") is not None:
            server_offset_hours = float(meta["server_offset_hours"])

    if server_offset_hours is None:
        raise ValueError(
            "server_offset_hours is required: MT5 bar times are broker server "
            "time, not UTC. tools/mt5_export_all.py writes it into the meta "
            "file; pass it explicitly for a file exported without one.")

    ts, o, h, l, c, v, sp = [], [], [], [], [], [], []
    with path.open(newline="") as fh:
        for row in _csv.DictReader(fh):
            raw = row["time"]
            d = _dt.datetime.fromisoformat(raw) if "-" in raw or ":" in raw \
                else _dt.datetime.utcfromtimestamp(float(raw))
            epoch = int(d.replace(tzinfo=_dt.timezone.utc).timestamp())
            ts.append(epoch - int(round(server_offset_hours * 3600)))
            o.append(float(row["open"])); h.append(float(row["high"]))
            l.append(float(row["low"]));  c.append(float(row["close"]))
            v.append(float(row.get("tick_volume") or 0))
            if point is not None and row.get("spread") not in (None, ""):
                sp.append(float(row["spread"]) * point)

    if len(sp) != len(ts):
        sp = None
    step = int(np.median(np.diff(ts))) if len(ts) > 2 else 0
    return Bars(ts, o, h, l, c, v, step, path.stem, sp)


def spread_summary(b: Bars) -> str:
    if b.sp is None:
        return "no per-bar spread in this file - cost must be assumed"
    s = b.sp[np.isfinite(b.sp) & (b.sp > 0)]
    if len(s) == 0:
        return "spread column present but empty"
    return (f"spread $/unit: mean {s.mean():.4f} median {np.median(s):.4f} "
            f"p90 {np.percentile(s, 90):.4f} max {s.max():.4f}  n={len(s)}")
