"""Immutable, content-addressed OHLC history for reproducible research.

MT5 can revise old bars while retaining the same timestamps.  A timestamp-only
cache key therefore cannot establish that a universe build and its later audit
used the same observations.  This module freezes every input array and verifies
its SHA-256 digest on every load.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

import data as D


SCHEMA = "xau-bars-v1"


def bars_digest(bars: D.Bars) -> str:
    h = hashlib.sha256()
    h.update(SCHEMA.encode())
    h.update(str(int(bars.step)).encode())
    h.update(str(bars.symbol).encode())
    arrays = (("t", bars.t), ("o", bars.o), ("h", bars.h),
              ("l", bars.l), ("c", bars.c), ("v", bars.v))
    if bars.sp is not None:
        arrays += (("sp", bars.sp),)
    for name, value in arrays:
        a = np.ascontiguousarray(value)
        h.update(name.encode())
        h.update(a.dtype.str.encode())
        h.update(np.asarray(a.shape, dtype=np.int64).tobytes())
        h.update(a.tobytes())
    return h.hexdigest()


def validate(bars: D.Bars) -> None:
    n = len(bars)
    arrays = (bars.o, bars.h, bars.l, bars.c, bars.v)
    if n < 2 or any(len(a) != n for a in arrays):
        raise ValueError("canonical history arrays have inconsistent lengths")
    if bars.sp is None or len(bars.sp) != n:
        raise ValueError("canonical history must contain one spread per bar")
    if not np.all(np.diff(bars.t) > 0):
        raise ValueError("canonical timestamps are not strictly increasing")
    if not all(np.all(np.isfinite(a)) for a in arrays + (bars.sp,)):
        raise ValueError("canonical history contains non-finite values")
    if np.any(bars.h < np.maximum.reduce((bars.o, bars.c, bars.l))):
        raise ValueError("canonical high is below another OHLC component")
    if np.any(bars.l > np.minimum.reduce((bars.o, bars.c, bars.h))):
        raise ValueError("canonical low is above another OHLC component")
    if np.any(bars.sp <= 0):
        raise ValueError("canonical history contains a non-positive spread")


def save(path: Path, bars: D.Bars, source: str) -> dict:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite canonical history: {path}")
    validate(bars)
    digest = bars_digest(bars)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        np.savez_compressed(
            fh, t=bars.t, o=bars.o, h=bars.h, l=bars.l, c=bars.c,
            v=bars.v, sp=bars.sp, step=np.asarray([bars.step], np.int64),
            symbol=np.asarray([bars.symbol]), schema=np.asarray([SCHEMA]))
    os.replace(tmp, path)
    meta = {
        "schema": SCHEMA,
        "sha256": digest,
        "source": source,
        "bars": len(bars),
        "first_epoch": int(bars.t[0]),
        "last_epoch": int(bars.t[-1]),
        "step_seconds": int(bars.step),
        "symbol": str(bars.symbol),
    }
    path.with_suffix(path.suffix + ".json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def load(path: Path) -> D.Bars:
    path = Path(path)
    meta_path = path.with_suffix(path.suffix + ".json")
    if not path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"canonical history or manifest missing: {path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    with np.load(path, allow_pickle=False) as z:
        schema = str(z["schema"][0])
        if schema != SCHEMA or meta.get("schema") != SCHEMA:
            raise ValueError(f"unsupported canonical schema: {schema}")
        bars = D.Bars(z["t"], z["o"], z["h"], z["l"], z["c"],
                      z["v"], int(z["step"][0]), str(z["symbol"][0]),
                      z["sp"])
    validate(bars)
    got = bars_digest(bars)
    if got != meta.get("sha256"):
        raise ValueError(f"canonical SHA-256 mismatch: {got} != {meta.get('sha256')}")
    return bars
