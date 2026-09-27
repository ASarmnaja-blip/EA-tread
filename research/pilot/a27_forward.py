"""Amendment 27 prospective logger and inactive Demo mirror.

The forward shadow is the evidence ledger.  It is deterministic from sealed
M5 bars and always applies Amendment 24's prior-closed-bar spread gate.  A live
quote is a diagnostic beside that decision and can reject only the optional
Demo mirror.

The module has no implicit loop and its default commands are read-only.  The
single ``order_send`` call is behind BOTH ``--live-demo`` and a separately
created activation record tied to the reviewed Amendment 27 commit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import canonical_history as canonical
import causal_chain as C26
import core
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E


SCHEMA = "a27-forward-v1"
DOCUMENT_COMMIT = "da52fef"
MAGIC = 20260927
PAYOFF_MAGIC = 20260923
W1_MAGIC = 20260922
COMMENT = "A27_A24_CAUSAL"
SYMBOL = "XAUUSD"
MIN_LOT = 0.01
MAX_SPREAD = 0.135
SOFT_DD = 0.35
HARD_DD = 0.40
OWN_LOSS_HALT = 0.10
MAX_POSITIONS = 5
QUOTE_MAX_AGE_SECONDS = 30
WEEKEND_SEAL_GRACE_SECONDS = 6 * 3600
SEED_FILE_SHA256 = "dfa12a60ac16c0260522ae30af5132322a6407e3a1be9d4f08a96472614f3c67"
SEED_CONTENT_SHA256 = "613d5e7476deeaa3dc473371028adf9d4724720788b5f1d424e410556dfad158"

ROOT = Path("data/a27_forward")
BAR_DIR = ROOT / "bars"
CACHE_DIR = ROOT / "cache"
STATE_DIR = ROOT / "state"
DECISION_DIR = ROOT / "decisions"
EVENT_DIR = ROOT / "events"
DRY_DIR = ROOT / "dry_run"
ACTIVATION_PATH = ROOT / "demo_activation.json"
DEMO_STATE_PATH = ROOT / "demo_state.json"
AUDIT_RECEIPT_PATH = ROOT / "audit_receipt.json"
W1_BLACKOUT_PATH = ROOT / "w1_probe_active.lock"
ACTUAL_STATE_PATH = STATE_DIR / "shadow_actual_state.json"
CANONICAL_PATH = Path("data/canonical_XAUUSD_M5.npz")
LEGACY_RAW_PATH = Path("data/amendment24_raw_opportunities_v1_sp090_co140.pkl")


class A27Error(RuntimeError):
    """Fail-closed Amendment 27 error."""


def utc(epoch: int | float | None = None) -> str:
    value = time.time() if epoch is None else float(epoch)
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, Path):
        return str(value).replace("\\", "/")
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _write_new(path: Path, payload: bytes) -> None:
    if Path(path).exists():
        raise FileExistsError(f"append-only target already exists: {path}")
    _atomic_write(Path(path), payload)


def code_hashes() -> dict[str, str]:
    files = [Path(__file__), Path(A24.__file__), Path(C26.__file__),
             Path(E.__file__), Path(core.__file__), Path(canonical.__file__)]
    return {str(p).replace("\\", "/"): sha256_file(p) for p in files}


def prefix_bars(bars: D.Bars, cutoff: int) -> D.Bars:
    """Return only fully closed bars strictly available at ``cutoff``."""
    n = int(np.searchsorted(bars.t + int(bars.step), int(cutoff), side="right"))
    return bars.slice(0, n)


def prefix_digest(bars: D.Bars, cutoff: int) -> str:
    return canonical.bars_digest(prefix_bars(bars, cutoff))


def _expected_gap(t0: int, t1: int) -> bool:
    """Conservative routine-session/weekend gap classifier for new bars."""
    a = datetime.fromtimestamp(int(t0), timezone.utc)
    b = datetime.fromtimestamp(int(t1), timezone.utc)
    seconds = int(t1 - t0)
    daily = (seconds <= 3 * 3600 and a.hour in {19, 20, 21, 22}
             and b.hour in {20, 21, 22, 23, 0})
    weekend = (a.weekday() == 4 and a.hour >= 18
               and b.weekday() in {6, 0} and seconds <= 4 * 86_400)
    return bool(daily or weekend)


def bar_quality(bars: D.Bars, extension_start: int = 0,
                grandfather_history: bool = False) -> dict[str, Any]:
    canonical.validate(bars)
    diff = np.diff(bars.t)
    duplicates = int(np.count_nonzero(diff <= 0))
    off_grid = int(np.count_nonzero(bars.t % int(bars.step)))
    gap_idx = np.flatnonzero(diff != int(bars.step))
    inspected = [int(i) for i in gap_idx if int(i) >= max(0, extension_start - 1)]
    unexpected = []
    for i in inspected:
        if not _expected_gap(int(bars.t[i] + bars.step), int(bars.t[i + 1])):
            unexpected.append({"left": int(bars.t[i]), "right": int(bars.t[i + 1]),
                               "seconds": int(diff[i])})
    passed = duplicates == 0 and off_grid == 0 and (grandfather_history or not unexpected)
    return {
        "passed": passed,
        "bars": len(bars),
        "duplicates": duplicates,
        "off_grid": off_grid,
        "all_gap_count": int(len(gap_idx)),
        "extension_gap_count": len(inspected),
        "unexpected_extension_gaps": unexpected,
        "grandfather_history": bool(grandfather_history),
    }


def assert_prefix_unchanged(previous: D.Bars, current: D.Bars) -> int:
    if current.step != previous.step or current.symbol != previous.symbol:
        raise A27Error("bar schema/symbol changed")
    if len(current) < len(previous):
        raise A27Error("bar history shrank")
    names = ("t", "o", "h", "l", "c", "v", "sp")
    for name in names:
        old = getattr(previous, name)
        new = getattr(current, name)
        if old is None or new is None or not np.array_equal(old, new[:len(old)]):
            raise A27Error(f"historical bar prefix changed: {name}")
    return len(previous)


def bar_manifest(bars: D.Bars, source: str, source_path: Path | None = None,
                 previous: D.Bars | None = None,
                 grandfather_history: bool = False) -> dict[str, Any]:
    extension_start = 0 if previous is None else assert_prefix_unchanged(previous, bars)
    quality = bar_quality(bars, extension_start, grandfather_history)
    if not quality["passed"]:
        raise A27Error(f"bar quality audit failed: {quality}")
    return {
        "schema": canonical.SCHEMA,
        "content_sha256": canonical.bars_digest(bars),
        "file_sha256": sha256_file(source_path) if source_path and source_path.exists() else None,
        "source": source,
        "bars": len(bars),
        "first_epoch": int(bars.t[0]),
        "last_epoch": int(bars.t[-1]),
        "last_close_epoch": int(bars.t[-1] + bars.step),
        "step_seconds": int(bars.step),
        "symbol": bars.symbol,
        "previous_content_sha256": (None if previous is None
                                     else canonical.bars_digest(previous)),
        "new_bars": len(bars) - extension_start,
        "quality": quality,
    }


def save_bar_snapshot(bars: D.Bars, manifest: dict[str, Any],
                      directory: Path = BAR_DIR) -> tuple[Path, Path]:
    digest = str(manifest["content_sha256"])
    data_path = Path(directory) / f"{digest}.npz"
    meta_path = Path(directory) / f"{digest}.json"
    if data_path.exists() or meta_path.exists():
        if not data_path.exists() or not meta_path.exists():
            raise A27Error("partial content-addressed bar snapshot")
        got = json.loads(meta_path.read_text(encoding="utf-8"))
        if got.get("content_sha256") != digest:
            raise A27Error("existing bar snapshot manifest mismatch")
        return data_path, meta_path
    data_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = data_path.with_suffix(".npz.tmp")
    with tmp.open("wb") as fh:
        np.savez_compressed(fh, t=bars.t, o=bars.o, h=bars.h, l=bars.l,
                            c=bars.c, v=bars.v, sp=bars.sp,
                            step=np.asarray([bars.step], np.int64),
                            symbol=np.asarray([bars.symbol]),
                            schema=np.asarray([canonical.SCHEMA]))
    os.replace(tmp, data_path)
    final = dict(manifest)
    final["snapshot_file_sha256"] = sha256_file(data_path)
    _write_new(meta_path, json.dumps(_jsonable(final), indent=2,
                                     ensure_ascii=False).encode("utf-8") + b"\n")
    return data_path, meta_path


def load_bar_snapshot(path: Path) -> D.Bars:
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        bars = D.Bars(z["t"], z["o"], z["h"], z["l"], z["c"], z["v"],
                      int(z["step"][0]), str(z["symbol"][0]), z["sp"])
    canonical.validate(bars)
    return bars


def fetch_mt5_extension(previous: D.Bars, cutoff: int) -> D.Bars:
    """Read-only MT5 extension with an overlap that must match byte-for-byte."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise A27Error(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        info = mt5.symbol_info(SYMBOL)
        if info is None or float(info.point) <= 0:
            raise A27Error("MT5 XAUUSD symbol/point unavailable")
        start = int(previous.t[max(0, len(previous) - 576)])
        rates = mt5.copy_rates_range(
            SYMBOL, mt5.TIMEFRAME_M5,
            datetime.fromtimestamp(start, timezone.utc),
            datetime.fromtimestamp(int(cutoff), timezone.utc))
        if rates is None or not len(rates):
            raise A27Error("MT5 returned no overlap/extension bars")
        keep = rates["time"] + previous.step <= int(cutoff)
        rates = rates[keep]
        if not len(rates):
            raise A27Error("MT5 returned no fully closed bars")
        incoming = D.Bars(rates["time"], rates["open"], rates["high"],
                          rates["low"], rates["close"], rates["tick_volume"],
                          previous.step, SYMBOL, rates["spread"] * float(info.point))
        canonical.validate(incoming)
        overlap = np.intersect1d(previous.t, incoming.t)
        if not len(overlap):
            raise A27Error("MT5 extension has no verifiable overlap")
        old_idx = np.searchsorted(previous.t, overlap)
        new_idx = np.searchsorted(incoming.t, overlap)
        for name in ("o", "h", "l", "c", "v", "sp"):
            if not np.array_equal(getattr(previous, name)[old_idx],
                                  getattr(incoming, name)[new_idx]):
                raise A27Error(f"MT5 revised overlap field {name}; append-only ingest refused")
        fresh = incoming.t > previous.t[-1]
        if not np.any(fresh):
            return previous
        return D.Bars(np.r_[previous.t, incoming.t[fresh]],
                      np.r_[previous.o, incoming.o[fresh]],
                      np.r_[previous.h, incoming.h[fresh]],
                      np.r_[previous.l, incoming.l[fresh]],
                      np.r_[previous.c, incoming.c[fresh]],
                      np.r_[previous.v, incoming.v[fresh]], previous.step,
                      previous.symbol, np.r_[previous.sp, incoming.sp[fresh]])
    finally:
        mt5.shutdown()


def latest_snapshot(directory: Path = BAR_DIR) -> tuple[D.Bars, dict] | None:
    paths = list(Path(directory).glob("*.json"))
    if not paths:
        return None
    rows = []
    for p in paths:
        row = json.loads(p.read_text(encoding="utf-8"))
        data = p.with_suffix(".npz")
        if data.exists():
            rows.append((int(row["last_epoch"]), p, data, row))
    if not rows:
        return None
    _last, _meta, data_path, manifest = max(rows, key=lambda x: x[0])
    bars = load_bar_snapshot(data_path)
    if canonical.bars_digest(bars) != manifest["content_sha256"]:
        raise A27Error("latest bar snapshot digest mismatch")
    return bars, manifest


def _a27_raw_stamp(bars: D.Bars) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": "330_raw_stream_full_rebuild",
        "data_sha256": canonical.bars_digest(bars),
        "a24_raw_stamp": A24._cache_stamp(bars),
        "a27_code_sha256": sha256_file(Path(__file__)),
        "stream_count": 330,
        "cell_count": E.n_cells(),
    }


def load_raw_streams(bars: D.Bars, allow_build: bool = False
                     ) -> tuple[dict, dict, dict[str, Any]]:
    """Read a fully hashed cache or rebuild all 330 streams content-addressed."""
    expected_a24 = A24._cache_stamp(bars)
    started = time.monotonic()
    if LEGACY_RAW_PATH.exists():
        with LEGACY_RAW_PATH.open("rb") as fh:
            got, streams, meta = pickle.load(fh)
        if got == expected_a24 and len(streams) == 330 and len(meta) == E.n_cells():
            return streams, meta, {
                "source": "verified_read_only_amendment24_cache",
                "path": str(LEGACY_RAW_PATH).replace("\\", "/"),
                "file_sha256": sha256_file(LEGACY_RAW_PATH),
                "stamp_sha256": object_hash(got),
                "streams": len(streams), "cells": len(meta),
                "build_seconds": 0.0,
            }
    stamp = _a27_raw_stamp(bars)
    stamp_hash = object_hash(stamp)
    path = CACHE_DIR / f"raw_{stamp['data_sha256'][:16]}_{stamp_hash[:16]}.pkl"
    if path.exists():
        with path.open("rb") as fh:
            got, streams, meta = pickle.load(fh)
        if got != stamp or len(streams) != 330 or len(meta) != E.n_cells():
            raise A27Error("A27 raw cache hash/content mismatch")
        return streams, meta, {
            "source": "a27_content_addressed_cache", "path": str(path),
            "file_sha256": sha256_file(path), "stamp_sha256": stamp_hash,
            "streams": len(streams), "cells": len(meta), "build_seconds": 0.0,
        }
    if not allow_build:
        raise A27Error("no matching raw-stream cache; rerun with --allow-rebuild")
    streams, meta = A24.build_raw_cache(bars)
    elapsed = time.monotonic() - started
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pkl.tmp")
    with tmp.open("wb") as fh:
        pickle.dump((stamp, streams, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    with path.open("rb") as fh:
        got, check_streams, check_meta = pickle.load(fh)
    if got != stamp or set(check_streams) != set(streams) or check_meta != meta:
        raise A27Error("A27 rebuilt cache failed full readback")
    return streams, meta, {
        "source": "a27_full_rebuild", "path": str(path),
        "file_sha256": sha256_file(path), "stamp_sha256": stamp_hash,
        "streams": len(streams), "cells": len(meta), "build_seconds": elapsed,
    }


def resolve_asof(bars: D.Bars, k: int, direction: int, entry: float,
                 atr_unit: float, stop: float, target: float,
                 allow_entry_bar_target: bool) -> dict[str, Any]:
    """Resolve only if the stop, target, or full time horizon is observed."""
    if k < 0 or k >= len(bars):
        raise ValueError("entry outside available bars")
    result = E.resolve_plane(bars, k, direction, entry, atr_unit, (stop,),
                             (target,), E.TIME_STOP_M5,
                             allow_entry_bar_target=allow_entry_bar_target)[(stop, target)]
    gross, why, held = result
    full_horizon_seen = len(bars) >= k + E.TIME_STOP_M5
    if why == "time" and not full_horizon_seen:
        return {"resolved": False, "entry_k": k, "last_seen_k": len(bars) - 1,
                "why": "OPEN_AT_CUTOFF"}
    return {"resolved": True, "entry_k": k, "exit_k": k + int(held),
            "held": int(held), "why": str(why), "gross_r": float(gross)}


def pending_orders_asof(bars: D.Bars, cutoff: int) -> list[dict[str, Any]]:
    """Rebuild all raw orders still pending at the sealed bar prefix.

    Pending state is shared by the 25 stop/target planes belonging to a raw
    stream.  It is hypothetical candidate state only and never becomes an
    actual basket order across a Weekend Rebuild.
    """
    available = prefix_bars(bars, cutoff)
    out: list[dict[str, Any]] = []
    for tfname, mult in E.TIMEFRAMES:
        bs, nxt = E.resample(available, mult)
        atr_s = core.atr(bs, E.ATR_N)
        ctx = core.Ctx(bs, nxt)
        for setup in E.SETUPS:
            signals = E.setup_signals(setup, ctx)
            for seq, (i, direction) in enumerate(signals):
                atr = float(atr_s[i])
                if not math.isfinite(atr) or atr <= 0:
                    continue
                activation_t = int(bs.t[i] + mult * available.step)
                if activation_t > cutoff:
                    continue
                k0 = int(nxt[i])
                # Nothing older than the longest declared expiry can remain
                # pending.  This keeps the full-state rebuild bounded to the
                # causal tail instead of rescanning five years of dead orders.
                if k0 >= 0 and len(available) - k0 >= max(x[1] for x in E.ENTRY_MODES) * mult:
                    continue
                for offset, expiry in E.ENTRY_MODES:
                    if expiry == 0:
                        if k0 < 0:
                            raw = {"setup": setup, "tf": tfname, "offset": offset,
                                   "expiry": expiry, "signal_sequence": seq,
                                   "direction": int(direction), "atr": atr,
                                   "activation_t": activation_t,
                                   "kind": "MARKET_AWAITING_NEXT_BAR"}
                            raw["raw_order_id"] = object_hash(raw)
                            out.append(raw)
                        continue
                    limit = float(bs.c[i]) - int(direction) * float(offset) * atr
                    if k0 < 0:
                        pending = True
                        bars_seen = 0
                    else:
                        got = E.entry_fill_detail(available, k0, int(direction),
                                                  limit, int(expiry) * mult)
                        bars_seen = len(available) - k0
                        pending = got is None and bars_seen < int(expiry) * mult
                    if pending:
                        raw = {"setup": setup, "tf": tfname, "offset": float(offset),
                               "expiry": int(expiry), "signal_sequence": seq,
                               "direction": int(direction), "atr": atr,
                               "activation_t": activation_t, "limit": limit,
                               "bars_seen": max(0, int(bars_seen)),
                               "bars_remaining": max(0, int(expiry) * mult
                                                     - max(0, int(bars_seen))),
                               "kind": "LIMIT_PENDING"}
                        raw["raw_order_id"] = object_hash(raw)
                        out.append(raw)
    return sorted(out, key=lambda r: (r["activation_t"], r["raw_order_id"]))


def _policy_digest(pd: A24.PolicyData) -> str:
    h = hashlib.sha256()
    for label, arr in (("boundaries", pd.boundaries), ("base", pd.base),
                       ("stress", pd.stress),
                       ("cancels", pd.candidate_gate_cancels)):
        a = np.ascontiguousarray(arr)
        h.update(label.encode()); h.update(a.dtype.str.encode()); h.update(a.tobytes())
    for tag in pd.tags:
        h.update(tag.encode())
        sig = pd.signatures[tag]
        for arr in (sig.t_order, sig.t_in, sig.t_out, sig.direction,
                    sig.entry_k, sig.exit_k):
            h.update(np.ascontiguousarray(arr).tobytes())
    return h.hexdigest()


def build_policy_asof(bars: D.Bars, streams: dict, meta: dict, cutoff: int
                      ) -> tuple[A24.PolicyData, dict[str, Any]]:
    """Build the causal A24 candidate history with unresolved tails left open."""
    available = prefix_bars(bars, cutoff)
    if len(available) < 2:
        raise A27Error("no complete bars before cutoff")
    tags = tuple(sorted(meta))
    bounds = A24.weekend_boundaries(int(available.t[0]), int(cutoff))
    if int(bounds[-1]) < cutoff:
        bounds = np.r_[bounds, np.asarray([cutoff], np.int64)]
    nweek = len(bounds) - 1
    base = np.zeros((len(tags), nweek), float)
    stress = np.zeros_like(base)
    signatures: dict[str, A24.SignatureHistory] = {}
    cancels = np.zeros(len(tags), np.int64)
    open_positions: dict[str, dict[str, Any]] = {}
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    n_available = len(available)
    for i, tag in enumerate(tags):
        m = meta[tag]
        s = streams[m["stream"]]
        event_order = C26.event_order(s["entry_k"], s["order_k"])
        resolved_rows: list[tuple] = []
        busy_until = -1
        for q0 in event_order:
            q = int(q0)
            k = int(s["entry_k"][q])
            if k >= n_available:
                break
            if k <= busy_until:
                continue
            risk = float(m["stop"]) * float(s["atr"][q])
            if not A24.gate_passes(available, k, risk):
                cancels[i] += 1
                continue
            # The cached plane is exact when the entire 288-M5 horizon is in
            # the sealed prefix.  Re-resolve only the short tail; the legacy
            # resolver otherwise fabricates a time exit at end-of-data.
            if k + E.TIME_STOP_M5 <= n_available:
                p = int(m["plane"])
                held = int(s["held"][q, p])
                status = {"resolved": True, "entry_k": k,
                          "exit_k": k + held, "held": held,
                          "why": "cached_complete_horizon",
                          "gross_r": float(s["gross"][q, p])}
            else:
                status = resolve_asof(available, k, int(s["direction"][q]),
                                      float(s["entry"][q]), float(s["atr"][q]),
                                      float(m["stop"]), float(m["target"]),
                                      bool(s["at_open"][q]))
            if not status["resolved"]:
                open_positions[tag] = {
                    "raw_sequence": q, "entry_k": k,
                    "entry_t": int(available.t[k]),
                    "order_k": int(s["order_k"][q]),
                    "direction": int(s["direction"][q]),
                    "entry": float(s["entry"][q]), "risk": risk,
                    "stop": float(m["stop"]), "target": float(m["target"]),
                }
                busy_until = np.iinfo(np.int64).max
                break
            xk = int(status["exit_k"])
            busy_until = xk
            direction = int(s["direction"][q])
            swap = (E.rollover_nights(int(available.t[k]), int(available.t[xk]))
                    * E.SWAP_LONG / risk if direction > 0 else 0.0)
            base_r = float(status["gross_r"]) - fee / risk - swap
            exec_r = A24.accounting_friction_r(available, k, risk)
            stress_r = base_r - 0.5 * exec_r
            resolved_rows.append((int(s["order_k"][q]), k, xk, direction,
                                  base_r, stress_r))
        if resolved_rows:
            rows = np.asarray(resolved_rows, dtype=float)
            order_k = rows[:, 0].astype(np.int64)
            entry_k = rows[:, 1].astype(np.int64)
            exit_k = rows[:, 2].astype(np.int64)
            direction = rows[:, 3].astype(np.int8)
            sig = A24.SignatureHistory(available.t[order_k].astype(np.int64),
                                       available.t[entry_k].astype(np.int64),
                                       available.t[exit_k].astype(np.int64),
                                       direction, entry_k, exit_k)
            bins = np.searchsorted(bounds, sig.t_out, side="right") - 1
            valid = (bins >= 0) & (bins < nweek)
            if np.any(valid):
                np.add.at(base[i], bins[valid], rows[valid, 4])
                np.add.at(stress[i], bins[valid], rows[valid, 5])
        else:
            empty64 = np.asarray([], np.int64)
            sig = A24.SignatureHistory(empty64, empty64.copy(), empty64.copy(),
                                       np.asarray([], np.int8), empty64.copy(),
                                       empty64.copy())
        signatures[tag] = sig
    pd = A24.PolicyData(tags, {t: i for i, t in enumerate(tags)}, bounds,
                        base, stress, signatures, cancels)
    pending = pending_orders_asof(bars, cutoff)
    actual_state = _read_json(ACTUAL_STATE_PATH, {"positions": [], "virtual_orders": []})
    state = {
        "cutoff": int(cutoff), "available_bars": len(available),
        "available_digest": canonical.bars_digest(available),
        "open_candidate_positions": open_positions,
        "open_candidate_count": len(open_positions),
        "candidate_pending_orders": pending,
        "candidate_pending_count": len(pending),
        "shadow_actual_state": actual_state,
        "policy_digest": _policy_digest(pd),
    }
    return pd, state


def _decision_dict(d: A24.Decision, meta: dict) -> dict[str, Any]:
    members = []
    for rank, tag in enumerate(d.members, 1):
        members.append({"rank": rank, "tag": tag, "family": meta[tag]["setup"],
                        "timeframe": meta[tag]["tf"], "stop": float(meta[tag]["stop"]),
                        "target": float(meta[tag]["target"]),
                        "offset": float(meta[tag]["off"]), "expiry": int(meta[tag]["exp"]),
                        "weight": d.weights[tag], "score": d.scores[tag],
                        "risk_contribution": d.risk_contributions.get(tag)})
    return {
        "cutoff": int(d.cut), "week_end": int(d.end), "reason": d.reason,
        "eligible_count": int(d.eligible_count),
        "duplicate_collapsed": int(d.duplicate_collapsed), "n_eff": d.n_eff,
        "members": members, "binding_caps": list(d.binding_caps),
        "correlations": {"|".join(k): v for k, v in d.correlations.items()},
        "member_turnover": d.member_turnover, "weight_turnover": d.weight_turnover,
        "simultaneous_admission_order": list(d.members),
    }


def save_state_artifact(state: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    raw = canonical_json(state)
    digest = hashlib.sha256(raw).hexdigest()
    directory = DRY_DIR if dry_run else STATE_DIR
    path = directory / f"candidate_state_{digest}.json.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(tmp, "wb") as fh:
            fh.write(json.dumps(_jsonable(state), indent=2,
                                ensure_ascii=False).encode("utf-8") + b"\n")
        os.replace(tmp, path)
    return {"path": str(path).replace("\\", "/"), "content_sha256": digest,
            "file_sha256": sha256_file(path)}


def seal_record(payload: dict[str, Any], path: Path, prev_hash: str) -> dict[str, Any]:
    body = dict(payload)
    body["previous_record_hash"] = prev_hash
    body["record_hash"] = object_hash(body)
    _write_new(Path(path), json.dumps(_jsonable(body), indent=2,
                                      ensure_ascii=False).encode("utf-8") + b"\n")
    check = json.loads(Path(path).read_text(encoding="utf-8"))
    claimed = check.pop("record_hash")
    if claimed != object_hash(check):
        raise A27Error("sealed record readback hash mismatch")
    check["record_hash"] = claimed
    return check


def verify_record(path: Path, expected_prev: str | None = None) -> dict[str, Any]:
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    claimed = row.pop("record_hash", None)
    if claimed != object_hash(row):
        raise A27Error(f"record hash mismatch: {path}")
    if expected_prev is not None and row.get("previous_record_hash") != expected_prev:
        raise A27Error("record chain predecessor mismatch")
    row["record_hash"] = claimed
    return row


def append_event(path: Path, decision_hash: str, kind: str,
                 payload: dict[str, Any], observed_epoch: int | None = None) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    prev = "GENESIS_EVENT"
    for old in rows:
        claimed = old.pop("event_hash", None)
        if old.get("previous_event_hash") != prev or claimed != object_hash(old):
            raise A27Error("event ledger hash chain is invalid")
        prev = claimed
    row = {"schema": SCHEMA, "sequence": len(rows),
           "observed_utc": utc(observed_epoch), "decision_hash": decision_hash,
           "kind": kind, "payload": payload, "previous_event_hash": prev}
    row["event_hash"] = object_hash(row)
    with path.open("ab") as fh:
        fh.write(json.dumps(_jsonable(row), ensure_ascii=False,
                            separators=(",", ":")).encode("utf-8") + b"\n")
        fh.flush(); os.fsync(fh.fileno())
    return row


def verify_event_ledger(path: Path) -> list[dict[str, Any]]:
    prev = "GENESIS_EVENT"
    verified = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        claimed = row.pop("event_hash", None)
        if row.get("previous_event_hash") != prev or claimed != object_hash(row):
            raise A27Error("event ledger hash chain is invalid")
        row["event_hash"] = claimed
        prev = claimed
        verified.append(row)
    return verified


def verify_live_shadow_event(event: dict[str, Any]) -> dict[str, Any]:
    """A Demo entry must be anchored to an admitted, hash-chained shadow row."""
    required = ("event_id", "decision_record", "decision_hash", "event_ledger",
                "shadow_event_hash", "tag", "risk", "direction", "target_r", "weight",
                "time_exit_epoch")
    missing = [key for key in required if key not in event]
    if missing:
        raise A27Error(f"live event missing shadow authorization fields: {missing}")
    decision = verify_record(Path(event["decision_record"]))
    if decision["record_hash"] != event["decision_hash"]:
        raise A27Error("live event decision hash mismatch")
    matches = [row for row in verify_event_ledger(Path(event["event_ledger"]))
               if row["event_hash"] == event["shadow_event_hash"]]
    if len(matches) != 1:
        raise A27Error("authorized shadow event not found exactly once")
    row = matches[0]
    payload = row.get("payload", {})
    if (row.get("decision_hash") != event["decision_hash"]
            or row.get("kind") != "WOULD_BE_ADMISSION"
            or payload.get("event_id") != event["event_id"]
            or payload.get("shadow_gate_passed") is not True
            or payload.get("portfolio_admitted") is not True):
        raise A27Error("shadow event is not an admitted frozen-policy event")
    exact_keys = ("tag", "direction", "time_exit_epoch")
    float_keys = ("risk", "target_r", "weight")
    if any(payload.get(key) != event.get(key) for key in exact_keys):
        raise A27Error("Demo event changed a discrete shadow-admission field")
    for key in float_keys:
        if not math.isclose(float(payload.get(key, math.nan)),
                            float(event.get(key, math.nan)),
                            rel_tol=0.0, abs_tol=1e-12):
            raise A27Error(f"Demo event changed shadow-admission {key}")
    return row


def shadow_gate(prior_bar_spread: float, risk: float,
                live_spread_diagnostic: float | None = None) -> dict[str, Any]:
    """Binding clarification A: ``live_spread_diagnostic`` cannot affect this."""
    spread = max(float(prior_bar_spread), E.SPREAD_FALLBACK)
    friction_r = (spread + E.COMMISSION_RT + 2 * E.SLIP_PER_FILL) / float(risk)
    return {"passed": friction_r <= A24.GATE_BASE_MAX + 1e-15,
            "gate_spread": spread, "friction_r": friction_r,
            "live_spread_diagnostic": live_spread_diagnostic,
            "source": "ingested_M5_sp[k-1]"}


def demo_spread_gate(live_spread: float, risk: float) -> dict[str, Any]:
    friction_r = (max(float(live_spread), E.SPREAD_FALLBACK)
                  + E.COMMISSION_RT + 2 * E.SLIP_PER_FILL) / float(risk)
    absolute = float(live_spread) <= MAX_SPREAD + 1e-15
    ratio = friction_r <= A24.GATE_BASE_MAX + 1e-15
    return {"passed": bool(absolute and ratio), "absolute_cap_pass": absolute,
            "friction_gate_pass": ratio, "friction_r": friction_r,
            "live_spread": float(live_spread)}


def projected_drawdown(peak_equity: float, current_equity: float,
                       additional_losses: Iterable[float], proposed_loss: float) -> float:
    peak = float(peak_equity)
    if not math.isfinite(peak) or peak <= 0:
        return 1.0
    further = sum(max(0.0, float(x)) for x in additional_losses)
    return max(0.0, (peak - float(current_equity) + further
                     + max(0.0, float(proposed_loss))) / peak)


def managed_positions(positions: Iterable[Any], magic: int = MAGIC) -> list[Any]:
    return [p for p in positions if int(getattr(p, "magic", 0)) == int(magic)]


@dataclass
class DemoCheck:
    allowed: bool
    reasons: list[str]
    projected_dd: float
    observed_dd: float


def demo_preflight(*, account_is_demo: bool, hedging: bool, login_matches: bool,
                   server_matches: bool, quote_age: float, live_spread: float,
                   risk: float, volume_min: float, volume_step: float,
                   margin_ok: bool, all_positions_have_sl: bool,
                   peak_equity: float, current_equity: float,
                   additional_losses: Iterable[float], proposed_loss: float,
                   own_pnl: float, activation_equity: float,
                   own_positions: int, cell_flat: bool, event_seen: bool,
                   w1_blackout: bool = False) -> DemoCheck:
    reasons = []
    if not account_is_demo: reasons.append("ACCOUNT_NOT_DEMO")
    if not hedging: reasons.append("ACCOUNT_NOT_HEDGING")
    if not login_matches or not server_matches: reasons.append("ACTIVATION_ACCOUNT_MISMATCH")
    if quote_age > QUOTE_MAX_AGE_SECONDS: reasons.append("STALE_QUOTE")
    dg = demo_spread_gate(live_spread, risk)
    if not dg["absolute_cap_pass"]: reasons.append("SPREAD_ABOVE_0.135")
    if not dg["friction_gate_pass"]: reasons.append("LIVE_FRICTION_GATE")
    if abs(volume_min - MIN_LOT) > 1e-12 or abs(volume_step - MIN_LOT) > 1e-12:
        reasons.append("CHANGED_MINIMUM_LOT")
    if not margin_ok: reasons.append("INSUFFICIENT_MARGIN")
    if not all_positions_have_sl: reasons.append("UNBOUNDED_POSITION_WITHOUT_SL")
    if own_positions >= MAX_POSITIONS: reasons.append("A27_SLOT_LIMIT")
    if not cell_flat: reasons.append("A27_CELL_BUSY")
    if event_seen: reasons.append("DUPLICATE_EVENT")
    if w1_blackout: reasons.append("W1_PROBE_BLACKOUT")
    pdd = projected_drawdown(peak_equity, current_equity, additional_losses,
                             proposed_loss)
    observed = max(0.0, (peak_equity - current_equity) / peak_equity) if peak_equity > 0 else 1.0
    if pdd > SOFT_DD + 1e-15: reasons.append("PROJECTED_DD_ABOVE_35")
    if observed >= SOFT_DD: reasons.append("OBSERVED_DD_SOFT_HALT")
    if observed >= HARD_DD: reasons.append("OBSERVED_DD_HARD_HALT")
    if activation_equity <= 0 or own_pnl <= -OWN_LOSS_HALT * activation_equity:
        reasons.append("A27_10PCT_LOSS_HALT")
    return DemoCheck(not reasons, reasons, pdd, observed)


def load_activation(path: Path = ACTIVATION_PATH) -> dict[str, Any]:
    if not Path(path).exists():
        raise A27Error("Demo activation record is absent")
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    required = (row.get("enabled") is True
                and row.get("document_commit") == DOCUMENT_COMMIT
                and bool(row.get("implementation_review_commit"))
                and str(row.get("seed_file_sha256", "")).lower() == SEED_FILE_SHA256
                and str(row.get("seed_content_sha256", "")).lower() == SEED_CONTENT_SHA256
                and row.get("account_login") is not None
                and bool(row.get("account_server"))
                and float(row.get("activation_equity", 0.0)) > 0)
    if not required:
        raise A27Error("Demo activation record is incomplete or not approved")
    return row


def _read_json(path: Path, default: Any) -> Any:
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise A27Error(f"invalid state JSON {path}: {exc}") from exc


def _write_json_atomic(path: Path, value: Any) -> None:
    _atomic_write(Path(path), json.dumps(_jsonable(value), indent=2,
                                         ensure_ascii=False).encode("utf-8") + b"\n")


def _mt5_position_risk(mt5: Any, position: Any) -> float:
    """Further loss from the current executable close quote to attached SL."""
    sl = float(getattr(position, "sl", 0.0) or 0.0)
    if sl <= 0:
        raise A27Error("open position has no valid SL")
    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        raise A27Error(f"quote unavailable for open position {position.symbol}")
    is_buy = int(position.type) == mt5.POSITION_TYPE_BUY
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    current = float(tick.bid if is_buy else tick.ask)
    value = mt5.order_calc_profit(order_type, position.symbol,
                                  float(position.volume), current, sl)
    if value is None:
        raise A27Error("cannot calculate open-position loss to SL")
    return max(0.0, -float(value))


def _magic_realized_pnl(mt5: Any, activation: dict[str, Any]) -> float:
    started = activation.get("activated_utc")
    if not started:
        return 0.0
    start_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    deals = mt5.history_deals_get(start_dt, datetime.now(timezone.utc)) or ()
    return float(sum(float(getattr(d, "profit", 0.0) or 0.0)
                     + float(getattr(d, "commission", 0.0) or 0.0)
                     + float(getattr(d, "swap", 0.0) or 0.0)
                     + float(getattr(d, "fee", 0.0) or 0.0)
                     for d in deals if int(getattr(d, "magic", 0)) == MAGIC))


def _filling_mode(mt5: Any, info: Any) -> int:
    """Choose a symbol-permitted filling policy, preferring IOC then FOK.

    ``symbol_info.filling_mode`` is a bit mask of SYMBOL_FILLING_* flags,
    whereas an order request takes one ORDER_FILLING_* enum value.  RETURN is
    deliberately not used for market execution and is only the fallback for
    other execution modes.  Unknown/missing capabilities fail closed.
    """
    flags = int(getattr(info, "filling_mode", 0) or 0)
    ioc_flag = int(getattr(mt5, "SYMBOL_FILLING_IOC", 2))
    fok_flag = int(getattr(mt5, "SYMBOL_FILLING_FOK", 1))
    if flags & ioc_flag:
        return int(mt5.ORDER_FILLING_IOC)
    if flags & fok_flag:
        return int(mt5.ORDER_FILLING_FOK)
    execution = int(getattr(info, "trade_exemode", -1))
    market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))
    if execution != market_execution and hasattr(mt5, "ORDER_FILLING_RETURN"):
        return int(mt5.ORDER_FILLING_RETURN)
    raise A27Error("symbol exposes no safe supported filling mode")


def _rounded_price(value: float, digits: int) -> float:
    if not math.isfinite(value) or value <= 0:
        raise A27Error("invalid protected-order price")
    return float(round(float(value), int(digits)))


def _close_a27_positions(mt5: Any, positions: Iterable[Any], *, live_demo: bool,
                         activation_path: Path) -> list[dict[str, Any]]:
    """Protective close; cannot send without the same two activation gates."""
    results = []
    for position in managed_positions(positions):
        tick = mt5.symbol_info_tick(position.symbol)
        info = mt5.symbol_info(position.symbol)
        if tick is None or info is None:
            results.append({"ticket": int(position.ticket), "ok": False,
                            "reason": "NO_QUOTE_FOR_HALT_CLOSE"})
            continue
        is_buy = int(position.type) == mt5.POSITION_TYPE_BUY
        try:
            filling = _filling_mode(mt5, info)
            price = _rounded_price(float(tick.bid if is_buy else tick.ask),
                                   int(info.digits))
        except A27Error as exc:
            results.append({"ticket": int(position.ticket), "ok": False,
                            "reason": str(exc)})
            continue
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol,
            "volume": float(position.volume),
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "position": int(position.ticket),
            "price": price,
            "deviation": 100, "magic": MAGIC, "comment": COMMENT + "_HALT",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = guarded_order_send(mt5, request, live_demo=live_demo,
                                    activation_path=activation_path)
        ok = result is not None and int(result.retcode) == int(mt5.TRADE_RETCODE_DONE)
        results.append({"ticket": int(position.ticket), "ok": ok,
                        "retcode": None if result is None else int(result.retcode)})
    return results


def guarded_order_send(mt5: Any, request: dict[str, Any], *, live_demo: bool,
                       activation_path: Path = ACTIVATION_PATH) -> Any:
    """The only order-send choke point; both independent gates are mandatory."""
    if not live_demo:
        raise A27Error("order_send unreachable without --live-demo")
    load_activation(activation_path)
    return mt5.order_send(request)


def demo_request(mt5: Any, event: dict[str, Any], tick: Any,
                 info: Any) -> dict[str, Any]:
    """Build a complete native MT5 protected market-order request.

    This function never calls MT5.  It validates broker metadata and returns
    only fields accepted by ``order_check``/``order_send``.  It does not move
    a frozen-policy stop or target to satisfy a broker constraint; an
    unplaceable protected level is rejected instead.
    """
    direction = int(event["direction"])
    risk = float(event["risk"])
    target_r = float(event["target_r"])
    if direction not in {-1, 1} or not math.isfinite(risk) or risk <= 0:
        raise A27Error("invalid event direction or risk")
    if not math.isfinite(target_r) or target_r <= 0:
        raise A27Error("invalid event target_r")
    digits = int(getattr(info, "digits", -1))
    point = float(getattr(info, "point", 0.0) or 0.0)
    stops_level = int(getattr(info, "trade_stops_level", -1))
    if digits < 0 or point <= 0 or stops_level < 0:
        raise A27Error("invalid symbol digits/point/trade_stops_level")
    entry_raw = float(tick.ask if direction > 0 else tick.bid)
    entry = _rounded_price(entry_raw, digits)
    stop = _rounded_price(entry_raw - direction * risk, digits)
    target = _rounded_price(entry_raw + direction * target_r * risk, digits)
    bid = _rounded_price(float(tick.bid), digits)
    ask = _rounded_price(float(tick.ask), digits)
    min_distance = float(stops_level) * point
    epsilon = point * 1e-6
    if direction > 0:
        levels_valid = (stop < entry < target
                        and stop <= bid - min_distance + epsilon
                        and target >= bid + min_distance - epsilon)
        order_type = int(mt5.ORDER_TYPE_BUY)
    else:
        levels_valid = (target < entry < stop
                        and stop >= ask + min_distance - epsilon
                        and target <= ask - min_distance + epsilon)
        order_type = int(mt5.ORDER_TYPE_SELL)
    if not levels_valid:
        raise A27Error("frozen SL/TP violates symbol trade_stops_level")
    event_comment = "A27_" + hashlib.sha256(str(event["event_id"]).encode()).hexdigest()[:8]
    return {
        "action": int(mt5.TRADE_ACTION_DEAL),
        "symbol": SYMBOL,
        "volume": MIN_LOT,
        "type": order_type,
        "price": entry,
        "sl": stop,
        "tp": target,
        "deviation": 100,
        "magic": MAGIC,
        "comment": event_comment,
        "type_time": int(mt5.ORDER_TIME_GTC),
        "type_filling": _filling_mode(mt5, info),
    }


def dry_demo_evaluate(event: dict[str, Any], live_spread: float) -> dict[str, Any]:
    before = object_hash(event)
    gate = demo_spread_gate(live_spread, float(event["risk"]))
    return {"mode": "DRY_RUN_NO_ORDER", "event_id": event["event_id"],
            "demo_gate": gate, "shadow_event_hash_before": before,
            "shadow_event_hash_after": object_hash(event),
            "shadow_unchanged": before == object_hash(event)}


def policy_at_cutoff(bars: D.Bars, cutoff: int, allow_rebuild: bool = False
                     ) -> tuple[A24.Decision, dict, dict, dict]:
    streams, meta, raw_info = load_raw_streams(bars, allow_rebuild)
    pd, state = build_policy_asof(bars, streams, meta, cutoff)
    matches = np.flatnonzero(pd.boundaries == int(cutoff))
    if not len(matches):
        raise A27Error(f"cutoff is not a registered weekend boundary: {utc(cutoff)}")
    j = int(matches[0])
    selector = A24.Selector(pd, meta, "gate")
    current = selector.select(j)
    previous = selector.select(j - 1) if j > A24.MIN_HISTORY_WEEKS else None
    if previous is not None:
        A24.add_turnover([previous, current])
    return current, meta, state, raw_info


def build_record(bars: D.Bars, manifest: dict[str, Any], cutoff: int,
                 status: str, allow_rebuild: bool = False) -> dict[str, Any]:
    started = time.time()
    decision, meta, state, raw_info = policy_at_cutoff(bars, cutoff, allow_rebuild)
    dry = status == "DRY_RUN_NOT_WEEK_1"
    state_artifact = save_state_artifact(state, dry)
    complete = prefix_bars(bars, cutoff)
    record = {
        "schema": SCHEMA, "status": status, "sealed_utc": utc(),
        "document_commit": DOCUMENT_COMMIT, "cutoff": int(cutoff),
        "cutoff_utc": utc(cutoff), "week_end": int(cutoff + A24.WEEK),
        "week_end_utc": utc(cutoff + A24.WEEK),
        "bar_manifest": manifest,
        "decision_input_prefix_sha256": canonical.bars_digest(complete),
        "bars_after_cutoff_present": bool(np.any(bars.t + bars.step > cutoff)),
        "code_hashes": code_hashes(), "raw_stream_artifact": raw_info,
        "candidate_state_artifact": state_artifact,
        "candidate_state_summary": {
            "open_candidate_count": state["open_candidate_count"],
            "candidate_pending_count": state["candidate_pending_count"],
            "policy_digest": state["policy_digest"],
            "available_digest": state["available_digest"],
        },
        "decision": _decision_dict(decision, meta),
        "constants": {
            "shadow_gate_source": "max(ingested_M5_sp[k-1],0.090)",
            "live_spread_role": "Demo-only diagnostic/admission",
            "gate_base_max": A24.GATE_BASE_MAX, "demo_spread_cap": MAX_SPREAD,
            "half_life_weeks": 3, "lcb_coefficient": A24.LCB_COEF,
            "min_history_weeks": A24.MIN_HISTORY_WEEKS,
            "min_nonzero_weeks": A24.MIN_NONZERO_WEEKS,
            "member_range": [A24.MIN_MEMBERS, A24.MAX_MEMBERS],
            "weight_range": [A24.MIN_WEIGHT, A24.MAX_WEIGHT],
            "correlation_admission": A24.CORR_ADMISSION,
            "magic": MAGIC, "payoff_magic": PAYOFF_MAGIC, "w1_magic": W1_MAGIC,
        },
        "build_seconds": time.time() - started,
        "clock_started": False if dry else True,
    }
    return record


def latest_completed_cutoff(bars: D.Bars) -> int:
    bounds = A24.weekend_boundaries(int(bars.t[0]), int(bars.t[-1] + bars.step))
    closed = bounds[bounds <= int(bars.t[-1] + bars.step)]
    if not len(closed):
        raise A27Error("no completed weekend cutoff")
    return int(closed[-1])


def run_external_audits() -> list[dict[str, Any]]:
    scripts = ["test_causal_chain.py", "test_basket_dd.py",
               "test_basket_gate.py", "test_mtf_engine.py"]
    rows = []
    for script in scripts:
        proc = subprocess.run([sys.executable, str(Path(__file__).parent / script)],
                              text=True, capture_output=True)
        rows.append({"script": script, "returncode": proc.returncode,
                     "stdout": proc.stdout, "stderr": proc.stderr})
        print(f"EXTERNAL_AUDIT {script} returncode={proc.returncode}")
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip())
        if proc.returncode:
            raise A27Error(f"external audit failed: {script}")
    return rows


def command_audit(args: argparse.Namespace) -> int:
    import test_a27_forward
    rc = test_a27_forward.main()
    print(f"A27_FAST_AUDITS returncode={rc}")
    if rc:
        return rc
    run_external_audits()
    print("SECTION9_AUDITS=ALL_PASS")
    receipt = {"schema": SCHEMA, "verdict": "ALL_PASS", "utc": utc(),
               "document_commit": DOCUMENT_COMMIT, "code_hashes": code_hashes()}
    _write_json_atomic(AUDIT_RECEIPT_PATH, receipt)
    print(f"AUDIT_RECEIPT={AUDIT_RECEIPT_PATH}")
    return 0


def command_dry_run(args: argparse.Namespace) -> int:
    bars = canonical.load(CANONICAL_PATH)
    manifest = bar_manifest(bars, "canonical_seed_dry_run", CANONICAL_PATH,
                            grandfather_history=True)
    save_bar_snapshot(bars, manifest, DRY_DIR / "bars")
    cutoff = latest_completed_cutoff(bars) if args.cutoff is None else int(args.cutoff)
    payload = build_record(bars, manifest, cutoff, "DRY_RUN_NOT_WEEK_1",
                           args.allow_rebuild)
    name = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y%m%dT%H%MZ")
    path = DRY_DIR / f"decision_{name}.json"
    if path.exists() and args.replace_dry_run:
        path.unlink()
    row = seal_record(payload, path, "GENESIS_DRY_RUN")
    print(f"DRY_RUN_RECORD={path}")
    print(f"DRY_RUN_RECORD_HASH={row['record_hash']}")
    print(f"STATUS={row['status']} CLOCK_STARTED={row['clock_started']}")
    print(f"DECISION_REASON={row['decision']['reason']} "
          f"MEMBERS={len(row['decision']['members'])} "
          f"ELIGIBLE={row['decision']['eligible_count']} "
          f"N_EFF={row['decision']['n_eff']:.6f}")
    return 0


def validate_weekend_seal_time(cutoff: int, now: int) -> int:
    """Return the seal deadline or fail outside the Saturday work window."""
    if int(now) < int(cutoff):
        raise A27Error("Weekend Rebuild attempted before the Friday-close cutoff")
    deadline = int(cutoff) + WEEKEND_SEAL_GRACE_SECONDS
    if int(now) > deadline:
        raise A27Error("late Weekend Rebuild: six-hour Saturday seal window passed")
    return deadline


def _previous_production_hash() -> str:
    rows = sorted(DECISION_DIR.glob("decision_*.json"))
    if not rows:
        return "GENESIS_A27"
    prev = "GENESIS_A27"
    for path in rows:
        row = verify_record(path, prev)
        prev = row["record_hash"]
    return prev


def command_weekly(args: argparse.Namespace) -> int:
    """Production weekly seal.  No broker order is present in this command."""
    receipt = _read_json(AUDIT_RECEIPT_PATH, {})
    if receipt.get("verdict") != "ALL_PASS" or receipt.get("code_hashes") != code_hashes():
        raise A27Error("current code has no matching ALL_PASS audit receipt")
    cutoff = int(args.cutoff)
    now = int(time.time())
    deadline = validate_weekend_seal_time(cutoff, now)
    prior = latest_snapshot()
    if prior is None:
        previous = canonical.load(CANONICAL_PATH)
    else:
        previous, _old_manifest = prior
    if args.source == "mt5":
        bars = fetch_mt5_extension(previous, cutoff)
        source = "MT5 append-only overlap-verified extension"
        source_path = None
    elif args.source == "snapshot":
        if not args.snapshot:
            raise A27Error("--snapshot is required for source=snapshot")
        bars = load_bar_snapshot(Path(args.snapshot))
        source = f"supplied snapshot {args.snapshot}"
        source_path = Path(args.snapshot)
    else:
        bars = canonical.load(CANONICAL_PATH)
        source = "canonical seed"
        source_path = CANONICAL_PATH
    if np.any(bars.t + bars.step > cutoff):
        raise A27Error("source contains bars not closed before the decision cutoff")
    manifest = bar_manifest(bars, source, source_path, previous=previous,
                            grandfather_history=False)
    save_bar_snapshot(bars, manifest)
    payload = build_record(bars, manifest, cutoff, "FORWARD_WEEK",
                           args.allow_rebuild)
    if int(time.time()) > deadline:
        raise A27Error("raw rebuild missed Saturday seal deadline; no record sealed")
    name = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y%m%dT%H%MZ")
    path = DECISION_DIR / f"decision_{name}.json"
    row = seal_record(payload, path, _previous_production_hash())
    print(f"FORWARD_DECISION={path} HASH={row['record_hash']}")
    return 0


def command_event(args: argparse.Namespace) -> int:
    decision = verify_record(Path(args.decision))
    if decision.get("status") != "FORWARD_WEEK":
        raise A27Error("events may be appended only to a production FORWARD_WEEK")
    payload = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
    if args.kind == "WOULD_BE_ADMISSION":
        required = ("event_id", "tag", "direction", "risk", "target_r", "weight",
                    "time_exit_epoch", "prior_bar_spread", "portfolio_admitted")
        missing = [key for key in required if key not in payload]
        if missing:
            raise A27Error(f"admission event missing fields: {missing}")
        members = {row["tag"]: row for row in decision["decision"]["members"]}
        member = members.get(str(payload["tag"]))
        if member is None:
            raise A27Error("admission event tag is not a selected member")
        if int(payload["direction"]) not in {-1, 1} or float(payload["risk"]) <= 0:
            raise A27Error("invalid admission direction/risk")
        if not math.isclose(float(payload["target_r"]), float(member["target"]),
                            rel_tol=0.0, abs_tol=1e-12):
            raise A27Error("admission target_r differs from sealed member")
        if not math.isclose(float(payload["weight"]), float(member["weight"]),
                            rel_tol=0.0, abs_tol=1e-12):
            raise A27Error("admission weight differs from sealed member")
        gate = shadow_gate(float(payload["prior_bar_spread"]), float(payload["risk"]),
                           payload.get("live_spread_diagnostic"))
        payload["shadow_gate"] = gate
        payload["shadow_gate_passed"] = bool(gate["passed"])
        if bool(payload["portfolio_admitted"]) and not gate["passed"]:
            raise A27Error("portfolio admission cannot override failed shadow gate")
    cutoff = int(decision["cutoff"])
    observed = int(time.time()) if args.observed_epoch is None else int(args.observed_epoch)
    if args.kind != "CORRECTION" and not (cutoff <= observed < int(decision["week_end"])):
        raise A27Error("event observation is outside the sealed forward week")
    if observed > int(time.time()) + 1:
        raise A27Error("future-dated event refused")
    name = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y%m%dT%H%MZ")
    ledger = EVENT_DIR / f"events_{name}.jsonl"
    row = append_event(ledger, decision["record_hash"], args.kind, payload,
                       observed)
    print(f"EVENT_LEDGER={ledger} EVENT_HASH={row['event_hash']}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    event = (None if not args.event_json else
             json.loads(Path(args.event_json).read_text(encoding="utf-8")))
    if not args.live_demo:
        if event is None:
            print(json.dumps({"mode": "DRY_RUN_NO_ORDER",
                              "maintenance": "NOT_RUN_WITHOUT_LIVE_ACTIVATION"}, indent=2))
            return 0
        result = dry_demo_evaluate(event, float(args.live_spread))
        print(json.dumps(result, indent=2))
        return 0
    # The live path is deliberately not a loop.  It cannot reach MetaTrader
    # without the explicit flag above and a reviewed activation record.
    activation = load_activation(Path(args.activation))
    if event is not None:
        verify_live_shadow_event(event)
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise A27Error(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        info = mt5.symbol_info(SYMBOL)
        tick = mt5.symbol_info_tick(SYMBOL)
        if account is None or info is None or tick is None:
            raise A27Error("MT5 account/symbol/quote unavailable")
        if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise A27Error("account is not DEMO")
        if account.margin_mode != mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING:
            raise A27Error("account is not hedging")
        if int(account.login) != int(activation["account_login"]) or str(account.server) != str(activation["account_server"]):
            raise A27Error("activation account mismatch")
        state = _read_json(DEMO_STATE_PATH, {"seen_events": [], "open_cells": {},
                                             "halted": False})
        equity = float(account.equity)
        peak = max(float(state.get("peak_equity", equity)), equity)
        state["peak_equity"] = peak
        state.setdefault("activation_equity", float(activation["activation_equity"]))
        positions = list(mt5.positions_get() or ())
        by_comment = {str(getattr(p, "comment", "")): p for p in managed_positions(positions)}
        # Broker SL/TP closures remove their cell from local state.  Time exits
        # are enforced whenever this one-cycle mirror is polled, including a
        # maintenance-only call with no event file.
        for cell, row in list(state.get("open_cells", {}).items()):
            if str(row.get("comment", "")) not in by_comment:
                state["open_cells"].pop(cell, None)
        expired = []
        now_epoch = int(time.time())
        for row in state.get("open_cells", {}).values():
            p = by_comment.get(str(row.get("comment", "")))
            if p is not None and now_epoch >= int(row.get("time_exit_epoch", 2**62)):
                expired.append(p)
        if expired:
            state.setdefault("maintenance", []).append({
                "utc": utc(), "kind": "TIME_EXIT",
                "results": _close_a27_positions(mt5, expired, live_demo=True,
                                                 activation_path=Path(args.activation))})
            positions = list(mt5.positions_get() or ())
        additional_losses = []
        all_have_sl = True
        for position in positions:
            if float(getattr(position, "sl", 0.0) or 0.0) <= 0:
                all_have_sl = False
                continue
            additional_losses.append(_mt5_position_risk(mt5, position))
        own_positions = managed_positions(positions)
        realized = _magic_realized_pnl(mt5, activation)
        floating = sum(float(getattr(p, "profit", 0.0) or 0.0)
                       + float(getattr(p, "swap", 0.0) or 0.0)
                       for p in own_positions)
        own_pnl = realized + floating
        observed_dd = max(0.0, (peak - equity) / peak) if peak > 0 else 1.0
        own_halt = own_pnl <= -OWN_LOSS_HALT * float(state["activation_equity"])
        if state.get("halted") or observed_dd >= HARD_DD or own_halt:
            state["halted"] = True
            state["halt_reason"] = ("ACCOUNT_40PCT_DD" if observed_dd >= HARD_DD
                                    else "A27_10PCT_LOSS" if own_halt
                                    else state.get("halt_reason", "PERSISTENT_HALT"))
            state["halt_close_results"] = _close_a27_positions(
                mt5, positions, live_demo=True, activation_path=Path(args.activation))
            _write_json_atomic(DEMO_STATE_PATH, state)
            print(json.dumps({"submitted": False, "halted": True,
                              "reason": state["halt_reason"],
                              "close_results": state["halt_close_results"]}, indent=2))
            return 2
        if event is None:
            _write_json_atomic(DEMO_STATE_PATH, state)
            print(json.dumps({"submitted": False, "maintenance_only": True,
                              "expired_positions": len(expired)}, indent=2))
            return 0
        request = demo_request(mt5, event, tick, info)
        is_buy = int(event["direction"]) > 0
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        proposed = mt5.order_calc_profit(order_type, SYMBOL, MIN_LOT,
                                         float(request["price"]), float(request["sl"]))
        if proposed is None:
            raise A27Error("cannot calculate proposed SL loss")
        margin = mt5.order_calc_margin(order_type, SYMBOL, MIN_LOT,
                                       float(request["price"]))
        seen = set(str(x) for x in state.get("seen_events", []))
        tag = str(event.get("tag", ""))
        check = demo_preflight(
            account_is_demo=account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
            hedging=account.margin_mode == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING,
            login_matches=int(account.login) == int(activation["account_login"]),
            server_matches=str(account.server) == str(activation["account_server"]),
            quote_age=max(0.0, time.time() - float(tick.time)),
            live_spread=float(tick.ask - tick.bid), risk=float(event["risk"]),
            volume_min=float(info.volume_min), volume_step=float(info.volume_step),
            margin_ok=margin is not None and float(margin) <= float(account.margin_free),
            all_positions_have_sl=all_have_sl, peak_equity=peak,
            current_equity=equity, additional_losses=additional_losses,
            proposed_loss=max(0.0, -float(proposed)), own_pnl=own_pnl,
            activation_equity=float(state["activation_equity"]),
            own_positions=len(own_positions),
            cell_flat=bool(tag) and tag not in state.get("open_cells", {}),
            event_seen=str(event["event_id"]) in seen,
            w1_blackout=W1_BLACKOUT_PATH.exists())
        if not check.allowed:
            print(json.dumps({"submitted": False, "reasons": check.reasons,
                              "projected_dd": check.projected_dd,
                              "observed_dd": check.observed_dd}, indent=2))
            return 2
        checked = mt5.order_check(request)
        if checked is None or int(getattr(checked, "retcode", -1)) not in {
                0, int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))}:
            raise A27Error("MT5 order_check rejected the protected request")
        result = guarded_order_send(mt5, request, live_demo=True,
                                    activation_path=Path(args.activation))
        # Ambiguous responses are still marked seen: retrying could duplicate a
        # deal whose acknowledgement was lost.
        state.setdefault("seen_events", []).append(str(event["event_id"]))
        state["seen_events"] = state["seen_events"][-10_000:]
        if result is not None and int(result.retcode) == int(mt5.TRADE_RETCODE_DONE):
            state.setdefault("open_cells", {})[tag] = {
                "event_id": str(event["event_id"]),
                "deal": int(result.deal), "recorded_utc": utc(),
                "comment": request["comment"],
                "time_exit_epoch": int(event["time_exit_epoch"])}
        _write_json_atomic(DEMO_STATE_PATH, state)
        print(json.dumps({"retcode": None if result is None else int(result.retcode),
                          "price": None if result is None else float(result.price)}, indent=2))
        return 0
    finally:
        mt5.shutdown()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="run section 9 audits; sends no order")
    a.set_defaults(func=command_audit)
    d = sub.add_parser("dry-run", help="seal DRY_RUN_NOT_WEEK_1 on canonical data")
    d.add_argument("--cutoff", type=int)
    d.add_argument("--allow-rebuild", action="store_true")
    d.add_argument("--replace-dry-run", action="store_true")
    d.set_defaults(func=command_dry_run)
    w = sub.add_parser("weekly", help="seal one production week; sends no order")
    w.add_argument("--cutoff", required=True, type=int)
    w.add_argument("--source", choices=("mt5", "snapshot", "canonical"),
                   default="mt5")
    w.add_argument("--snapshot")
    w.add_argument("--allow-rebuild", action="store_true")
    w.set_defaults(func=command_weekly)
    e = sub.add_parser("event", help="append one hash-chained shadow event")
    e.add_argument("--decision", required=True)
    e.add_argument("--kind", required=True)
    e.add_argument("--payload-json", required=True)
    e.add_argument("--observed-epoch", type=int)
    e.set_defaults(func=command_event)
    m = sub.add_parser("demo", help="one inactive-by-default Demo event")
    m.add_argument("--event-json",
                   help="authorized shadow event; omit for maintenance-only cycle")
    m.add_argument("--live-spread", type=float, default=999.0)
    m.add_argument("--live-demo", action="store_true")
    m.add_argument("--activation", default=str(ACTIVATION_PATH))
    m.set_defaults(func=command_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
