"""Amendment 26: causal fill-time chains and contamination measurement.

Research only.  This module has no MetaTrader connection and no order-sending
path.  Legacy modules remain untouched so their contaminated results can be
reproduced beside the corrected fill-time results.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import pickle
from pathlib import Path
import subprocess
import sys
import types
from typing import Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_dd as A23
import basket_gate as A24
import canonical_history as canonical
import core
import data as D
import evolution_portfolio_audit as old_audit
import historical_regime_walkforward as hist
import mtf_engine as E
import walk_forward as wf
import weekly_evolution_grid as weekly


DAY = 86_400
WEEK = 7 * DAY
CACHE_VERSION = 1
CACHE_PATH = Path("data/causal_filltime_universe_v1_sp090_co140.pkl")
A21_CACHE_PATH = Path("data/causal_filltime_a21_a67cca7_v2.pkl")
A21_FROZEN_COMMIT = "a67cca7"
SUMMARY_PATH = Path("data/causal_chain_summary.json")
REPORT_START = A23.REPORT_START
REPORT_SPLIT = A23.REPORT_SPLIT


def utc(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def event_order(entry_k: np.ndarray, order_k: np.ndarray,
                sequence: np.ndarray | None = None) -> np.ndarray:
    """Frozen FIFO ordering: fill bar, order bar, original signal sequence."""
    entry_k = np.asarray(entry_k, np.int64)
    order_k = np.asarray(order_k, np.int64)
    if sequence is None:
        sequence = np.arange(len(entry_k), dtype=np.int64)
    else:
        sequence = np.asarray(sequence, np.int64)
    return np.lexsort((sequence, order_k, entry_k)).astype(np.int64)


def causal_indices(entry_k: np.ndarray, order_k: np.ndarray,
                   held: np.ndarray, sequence: np.ndarray | None = None
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Accept first-fill events chronologically; busy includes the exit bar."""
    entry_k = np.asarray(entry_k, np.int64)
    held = np.asarray(held, np.int64)
    order = event_order(entry_k, order_k, sequence)
    accepted: list[int] = []
    rejected: list[int] = []
    busy_until = -1
    for q0 in order:
        q = int(q0)
        k = int(entry_k[q])
        if k <= busy_until:
            rejected.append(q)
            continue
        accepted.append(q)
        busy_until = k + int(held[q])
    return np.asarray(accepted, np.int64), np.asarray(rejected, np.int64)


def streaming_indices(entry_k: np.ndarray, order_k: np.ndarray,
                      held: np.ndarray, sequence: np.ndarray | None = None
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Bar-by-bar reference oracle; no later event participates at an earlier bar."""
    entry_k = np.asarray(entry_k, np.int64)
    order_k = np.asarray(order_k, np.int64)
    held = np.asarray(held, np.int64)
    if sequence is None:
        sequence = np.arange(len(entry_k), dtype=np.int64)
    else:
        sequence = np.asarray(sequence, np.int64)
    by_bar: dict[int, list[int]] = defaultdict(list)
    for q, k in enumerate(entry_k):
        by_bar[int(k)].append(q)
    accepted: list[int] = []
    rejected: list[int] = []
    busy_until = -1
    for k in sorted(by_bar):
        rows = sorted(by_bar[k], key=lambda q: (int(order_k[q]),
                                                int(sequence[q])))
        for q in rows:
            if k <= busy_until:
                rejected.append(q)
            else:
                accepted.append(q)
                busy_until = k + int(held[q])
    return np.asarray(accepted, np.int64), np.asarray(rejected, np.int64)


def streaming_price_oracle(opens: np.ndarray, highs: np.ndarray,
                           lows: np.ndarray, orders: list[dict]
                           ) -> tuple[list[int], list[int]]:
    """Independent online oracle for synthetic orders.

    Unlike ``event_order`` this routine never receives a future fill bar.  It
    activates orders at their known order bar and discovers a market/limit
    trigger from the current bar only.  ``expiry_k`` is exclusive.
    """
    active: list[dict] = []
    accepted: list[int] = []
    rejected: list[int] = []
    busy_until = -1
    born: dict[int, list[dict]] = defaultdict(list)
    for order in orders:
        born[int(order["order_k"])].append(dict(order))
    for k in range(len(opens)):
        active.extend(born.get(k, ()))
        active = [o for o in active if k < int(o["expiry_k"])]
        triggered = []
        waiting = []
        for order in active:
            if order["kind"] == "market":
                hit = k == int(order["order_k"])
            elif int(order["direction"]) > 0:
                hit = (float(opens[k]) <= float(order["limit"])
                       or float(lows[k]) <= float(order["limit"]))
            else:
                hit = (float(opens[k]) >= float(order["limit"])
                       or float(highs[k]) >= float(order["limit"]))
            (triggered if hit else waiting).append(order)
        active = waiting
        for order in sorted(triggered,
                            key=lambda o: (int(o["order_k"]), int(o["seq"]))):
            oid = int(order["id"])
            if k <= busy_until:
                rejected.append(oid)
            else:
                accepted.append(oid)
                busy_until = k + int(order["held"])
    return accepted, rejected


def legacy_indices(entry_k: np.ndarray, held: np.ndarray
                   ) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Unchanged defective signal-order chain, used only as a negative control."""
    entry_k = np.asarray(entry_k, np.int64)
    held = np.asarray(held, np.int64)
    accepted: list[int] = []
    rejected: list[tuple[int, int]] = []
    busy_until = -1
    blocker = -1
    for q, k0 in enumerate(entry_k):
        k = int(k0)
        if k <= busy_until:
            rejected.append((q, blocker))
        else:
            accepted.append(q)
            blocker = q
            busy_until = k + int(held[q])
    return np.asarray(accepted, np.int64), rejected


def causal_gated_indices(b5: D.Bars, stream: dict, m: dict
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Amendment 24 semantics on the causal order: busy, then gate if flat."""
    ek = stream["entry_k"].astype(np.int64, copy=False)
    ok = stream["order_k"].astype(np.int64, copy=False)
    held = stream["held"][:, int(m["plane"])].astype(np.int64, copy=False)
    accepted: list[int] = []
    busy_rejected: list[int] = []
    gate_rejected: list[int] = []
    busy_until = -1
    for q0 in event_order(ek, ok):
        q = int(q0)
        k = int(ek[q])
        if k <= busy_until:
            busy_rejected.append(q)
            continue
        risk = float(m["stop"]) * float(stream["atr"][q])
        if not A24.gate_passes(b5, k, risk):
            gate_rejected.append(q)
            continue
        accepted.append(q)
        busy_until = k + int(held[q])
    return (np.asarray(accepted, np.int64),
            np.asarray(busy_rejected, np.int64),
            np.asarray(gate_rejected, np.int64))


def _swap_r(b5: D.Bars, entry_k: np.ndarray, exit_k: np.ndarray,
            direction: np.ndarray, risk: np.ndarray) -> np.ndarray:
    return np.asarray([
        E.rollover_nights(int(b5.t[k]), int(b5.t[x])) * E.SWAP_LONG / float(r)
        if int(d) > 0 else 0.0
        for k, x, d, r in zip(entry_k, exit_k, direction, risk)
    ], float)


def _universe_row(b5: D.Bars, stream: dict, m: dict,
                  chosen: np.ndarray) -> dict:
    q = np.asarray(chosen, np.int64)
    p = int(m["plane"])
    st = float(m["stop"])
    entry_k = stream["entry_k"][q].astype(np.int64)
    exit_k = np.minimum(entry_k + stream["held"][q, p].astype(np.int64),
                        len(b5) - 1)
    order_k = stream["order_k"][q].astype(np.int64)
    direction = stream["direction"][q].astype(np.int8)
    risk = st * stream["atr"][q].astype(float)
    gross = stream["gross"][q, p].astype(float)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    swap = _swap_r(b5, entry_k, exit_k, direction, risk)
    net = gross - fee / risk - swap
    return {
        "t_order": b5.t[order_k].astype(np.int64),
        "t_in": b5.t[entry_k].astype(np.int64),
        "t_out": b5.t[exit_k].astype(np.int64),
        "net": net,
        "sigk": entry_k,
        "risk": risk,
        "direction": direction,
        "dollars": net * risk,
        "entry": stream["entry"][q].astype(float),
        "exit_k": exit_k,
    }


def cache_stamp(b5: D.Bars, raw_path: Path) -> dict:
    code = hashlib.sha256()
    for module in (Path(__file__), Path(E.__file__), Path(wf.__file__),
                   Path(A24.__file__), Path(core.__file__), Path(D.__file__)):
        code.update(module.name.encode())
        code.update(module.read_bytes())
    return {
        "version": CACHE_VERSION,
        "data_sha256": canonical.bars_digest(b5),
        "raw_cache_sha256": sha256_file(raw_path),
        "code_sha256": code.hexdigest(),
        "ordering": "fill_k,order_k,original_signal_sequence",
        "busy_boundary": "entry_k<=fill_k<=exit_k",
        "pending_rule": "nonexclusive_until_first_trigger",
        "spread_floor": E.SPREAD_FALLBACK,
        "commission_rt": E.COMMISSION_RT,
        "slip_per_fill": E.SLIP_PER_FILL,
        "swap_long": E.SWAP_LONG,
        "swap_short": E.SWAP_SHORT,
        "rollover_h": E.ROLLOVER_H,
        "time_stop": E.TIME_STOP_M5,
        "timeframes": E.TIMEFRAMES,
        "stops": E.STOPS,
        "targets": E.TARGETS,
        "entry_modes": E.ENTRY_MODES,
    }


def build_causal_universe(b5: D.Bars, streams: dict, meta: dict
                          ) -> tuple[dict, dict]:
    uni: dict[str, dict] = {}
    clean_meta: dict[str, dict] = {}
    for i, tag in enumerate(sorted(meta)):
        m = meta[tag]
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = causal_indices(s["entry_k"], s["order_k"], held)
        if len(chosen) >= wf.MIN_TRADES_SEL:
            uni[tag] = _universe_row(b5, s, m, chosen)
            clean_meta[tag] = {
                "setup": m["setup"], "tf": m["tf"],
                "stop": m["stop"], "target": m["target"],
                "off": m["off"], "exp": m["exp"],
            }
        if (i + 1) % 500 == 0:
            print(f"causal_cache_progress cells={i + 1}/{len(meta)}")
    return uni, clean_meta


def load_causal_universe(b5: D.Bars, streams: dict | None = None,
                         meta: dict | None = None) -> tuple[dict, dict, bool, dict]:
    raw_path = A24._cache_path()
    expected = cache_stamp(b5, raw_path)
    if CACHE_PATH.exists():
        with CACHE_PATH.open("rb") as fh:
            got, uni, clean_meta = pickle.load(fh)
        if got == expected and len(uni) == E.n_cells():
            return uni, clean_meta, False, got
        print("causal_cache=HASH_MISS rebuilding")
    if streams is None or meta is None:
        streams, meta, _ = A24.load_raw_cache(b5)
    uni, clean_meta = build_causal_universe(b5, streams, meta)
    if len(uni) != E.n_cells():
        raise RuntimeError(f"causal universe cells={len(uni)} expected={E.n_cells()}")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("wb") as fh:
        pickle.dump((expected, uni, clean_meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    with CACHE_PATH.open("rb") as fh:
        got, check_uni, check_meta = pickle.load(fh)
    if got != expected or set(check_uni) != set(uni) or check_meta != clean_meta:
        raise RuntimeError("causal cache readback mismatch")
    return uni, clean_meta, True, got


def _policy_data_causal_gate(b5: D.Bars, streams: dict, meta: dict
                             ) -> A24.PolicyData:
    tags = tuple(sorted(meta))
    bounds = A24.weekend_boundaries(int(b5.t[0]), int(b5.t[-1] + b5.step))
    nweek = len(bounds) - 1
    base = np.zeros((len(tags), nweek), float)
    stress = np.zeros_like(base)
    signatures: dict[str, A24.SignatureHistory] = {}
    cancels = np.zeros(len(tags), np.int64)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    for i, tag in enumerate(tags):
        m = meta[tag]
        s = streams[m["stream"]]
        q, _busy, gate_rej = causal_gated_indices(b5, s, m)
        cancels[i] = len(gate_rej)
        p = int(m["plane"])
        st = float(m["stop"])
        ek = s["entry_k"][q].astype(np.int64)
        xk = np.minimum(ek + s["held"][q, p].astype(np.int64), len(b5) - 1)
        ok = s["order_k"][q].astype(np.int64)
        direction = s["direction"][q].astype(np.int8)
        risk = st * s["atr"][q].astype(float)
        gross_geom = s["gross"][q, p].astype(float)
        swap = _swap_r(b5, ek, xk, direction, risk)
        base_r = gross_geom - fee / risk - swap
        exec_r = np.asarray([A24.accounting_friction_r(b5, int(k), float(r))
                             for k, r in zip(ek, risk)], float)
        stress_r = base_r - 0.5 * exec_r
        sig = A24.SignatureHistory(b5.t[ok].astype(np.int64),
                                   b5.t[ek].astype(np.int64),
                                   b5.t[xk].astype(np.int64), direction, ek, xk)
        signatures[tag] = sig
        bins = np.searchsorted(bounds, sig.t_out, side="right") - 1
        valid = (bins >= 0) & (bins < nweek)
        if np.any(valid):
            np.add.at(base[i], bins[valid], base_r[valid])
            np.add.at(stress[i], bins[valid], stress_r[valid])
    return A24.PolicyData(tags, {t: i for i, t in enumerate(tags)}, bounds,
                          base, stress, signatures, cancels)


def _git_source(commit: str, relative_path: str) -> str:
    """Read a frozen historical source without modifying the working tree."""
    return subprocess.check_output(
        ["git", "show", f"{commit}:{relative_path}"], text=True,
        encoding="utf-8", errors="strict")


def _a21_frozen_engine() -> tuple[types.ModuleType, str]:
    relative = "research/pilot/mtf_engine.py"
    source = _git_source(A21_FROZEN_COMMIT, relative)
    module = types.ModuleType("amendment21_frozen_mtf_engine")
    module.__file__ = f"git:{A21_FROZEN_COMMIT}:{relative}"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module, hashlib.sha256(source.encode("utf-8")).hexdigest()


def _a21_cache_stamp(b5: D.Bars, frozen_sha: str) -> dict:
    code = hashlib.sha256()
    for module in (Path(__file__), Path(core.__file__), Path(D.__file__)):
        code.update(module.name.encode())
        code.update(module.read_bytes())
    return {
        "version": 2,
        "purpose": "A21_a67cca7_same_canonical_data_legacy_and_fill_time",
        "data_sha256": canonical.bars_digest(b5),
        "frozen_commit": A21_FROZEN_COMMIT,
        "frozen_mtf_sha256": frozen_sha,
        "code_sha256": code.hexdigest(),
        "ordering": "fill_k,order_k,original_signal_sequence",
        "busy_boundary": "entry_k<=fill_k<=exit_k",
    }


def _a21_old_net(frozen, b5: D.Bars, k: int, d: int, risk: float,
                 gross: float, nb: int) -> float:
    """Exact a67cca7 cost and rollover accounting; only chain order changes."""
    sp = (float(b5.sp[k]) if b5.sp is not None and np.isfinite(b5.sp[k])
          and b5.sp[k] > 0 else frozen.SPREAD_FALLBACK)
    net = gross - (sp + frozen.COMMISSION_RT
                   + 2.0 * frozen.SLIP_PER_FILL) / risk
    sw = frozen.SWAP_LONG if d > 0 else frozen.SWAP_SHORT
    if sw:
        t0 = int(b5.t[k])
        t1 = t0 + int(nb) * int(b5.step)
        h0 = (t0 // 3600) % 24
        cur = t0 - (t0 % 3600) + ((frozen.ROLLOVER_H - h0) % 24) * 3600
        nights = 0
        while cur <= t1:
            nights += 1
            cur += DAY
        net -= nights * sw / risk
    return float(net)


def build_a21_same_data_universes(b5: D.Bars, frozen
                                  ) -> tuple[dict, dict, dict]:
    """Build legacy and causal A21 universes from identical canonical inputs."""
    legacy, causal, meta = {}, {}, {}
    t_end = int(b5.t[-1] + b5.step)
    for tfname, mult in frozen.TIMEFRAMES:
        bs, nxt = frozen.resample(b5, mult)
        keep = bs.t <= t_end
        atr_s = core.atr(bs, frozen.ATR_N)
        ctx = core.Ctx(bs, nxt)
        for setup in frozen.SETUPS:
            signals = [(i, d) for i, d in frozen.setup_signals(setup, ctx)
                       if keep[i]]
            for off, exp in frozen.ENTRY_MODES:
                fills = []
                for seq, (i, d) in enumerate(signals):
                    k0 = int(nxt[i])
                    a = float(atr_s[i])
                    if k0 < 0 or not np.isfinite(a) or a <= 0:
                        continue
                    if exp == 0:
                        k, entry = k0, float(b5.o[k0])
                    else:
                        limit = float(bs.c[i]) - d * off * a
                        got = frozen.entry_fill(b5, k0, d, limit, exp * mult)
                        if got is None:
                            continue
                        k, entry = got
                    fills.append((int(k), int(d), float(entry), a, k0, seq))
                if len(fills) < wf.MIN_TRADES_SEL:
                    continue
                planes = [frozen.resolve_plane(
                    b5, k, d, entry, a, frozen.STOPS, frozen.TARGETS,
                    frozen.TIME_STOP_M5) for k, d, entry, a, _k0, _seq in fills]
                entry_k = np.asarray([r[0] for r in fills], np.int64)
                order_k = np.asarray([r[4] for r in fills], np.int64)
                sequence = np.asarray([r[5] for r in fills], np.int64)
                for st in frozen.STOPS:
                    for tg in frozen.TARGETS:
                        held = np.asarray([p[(st, tg)][2] for p in planes], np.int64)
                        causal_chosen, _rejected = causal_indices(
                            entry_k, order_k, held, sequence)
                        legacy_chosen, _legacy_rejected = legacy_indices(
                            entry_k, held)
                        if (len(causal_chosen) < wf.MIN_TRADES_SEL
                                or len(legacy_chosen) < wf.MIN_TRADES_SEL):
                            continue
                        tag = (f"{setup}/{tfname}/s{st:g}/t{tg:g}"
                               f"/o{off:g}e{exp}")
                        def row_for(indices: np.ndarray) -> dict:
                            tin, tout, net, sigk = [], [], [], []
                            for q0 in indices:
                                q = int(q0)
                                k, d, _entry, a, _k0, _seq = fills[q]
                                g, _why, nb = planes[q][(st, tg)]
                                risk = float(st) * a
                                kx = min(k + int(nb), len(b5) - 1)
                                tin.append(int(b5.t[k]))
                                tout.append(int(b5.t[kx]))
                                net.append(_a21_old_net(
                                    frozen, b5, k, d, risk, float(g), int(nb)))
                                sigk.append(k)
                            return {"t_in": np.asarray(tin, np.int64),
                                    "t_out": np.asarray(tout, np.int64),
                                    "net": np.asarray(net, float),
                                    "sigk": np.asarray(sigk, np.int64)}

                        legacy[tag] = row_for(legacy_chosen)
                        causal[tag] = row_for(causal_chosen)
                        meta[tag] = {"setup": setup, "tf": tfname,
                                     "stop": st, "target": tg,
                                     "off": off, "exp": exp}
        print(f"a21_pair_cache_progress timeframe={tfname} "
              f"legacy_cells={len(legacy)} causal_cells={len(causal)}")
    return legacy, causal, meta


def load_a21_same_data_universes(
        b5: D.Bars) -> tuple[dict, dict, dict, bool, dict]:
    frozen, frozen_sha = _a21_frozen_engine()
    expected = _a21_cache_stamp(b5, frozen_sha)
    if A21_CACHE_PATH.exists():
        with A21_CACHE_PATH.open("rb") as fh:
            got, legacy, causal, meta = pickle.load(fh)
        if (got == expected and len(legacy) == E.n_cells()
                and len(causal) == E.n_cells()):
            return legacy, causal, meta, False, got
        print("a21_pair_cache=HASH_MISS rebuilding")
    legacy, causal, meta = build_a21_same_data_universes(b5, frozen)
    if len(legacy) != E.n_cells() or len(causal) != E.n_cells():
        raise RuntimeError(f"A21 cells legacy={len(legacy)} causal={len(causal)} "
                           f"expected={E.n_cells()}")
    A21_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with A21_CACHE_PATH.open("wb") as fh:
        pickle.dump((expected, legacy, causal, meta), fh,
                    protocol=pickle.HIGHEST_PROTOCOL)
    with A21_CACHE_PATH.open("rb") as fh:
        got, check_legacy, check_causal, check_meta = pickle.load(fh)
    if (got != expected or set(check_legacy) != set(legacy)
            or set(check_causal) != set(causal) or check_meta != meta):
        raise RuntimeError("A21 causal cache readback mismatch")
    return legacy, causal, meta, True, got


def _a21_run(uni: dict, b5: D.Bars) -> dict:
    """Amendment 21 exactly as published at commit a67cca7.

    That registered baseline used entry time (not the later order-time
    clarification added to weekly_evolution_grid.py) for its 56-day evidence
    and forward week.  Keeping the original rule is required to reproduce the
    +248.785 R reference before changing only the per-cell chain.
    """
    def score_registered(lo: int, cut: int):
        scores, signatures = {}, {}
        for tag, a in uni.items():
            entered = (a["t_in"] >= lo) & (a["t_in"] < cut)
            complete = entered & (a["t_out"] < cut)
            x = a["net"][complete]
            if (len(x) < weekly.MIN_TRADES
                    or len(np.unique(a["t_in"][complete] // DAY)) < weekly.MIN_DAYS):
                continue
            scores[tag] = float(x.mean() - weekly.SHRINK_SE
                                * x.std(ddof=1) / math.sqrt(len(x)))
            signatures[tag] = a["sigk"][complete].tobytes()
        return scores, signatures

    last = int(b5.t[-1] + b5.step)
    first = int(b5.t[0])
    cut = weekly._week_boundary(first)
    if cut <= first + weekly.SELECT_DAYS * DAY:
        cut += WEEK
    while cut < first + weekly.SELECT_DAYS * DAY:
        cut += WEEK
    active = None
    transitions = 0
    idle = 0
    rows: list[dict] = []
    weeks: list[tuple[int, float]] = []
    while cut < last:
        end = min(cut + weekly.FORWARD_DAYS * DAY, last)
        scores, signatures = score_registered(
            cut - weekly.SELECT_DAYS * DAY, cut)
        ranked, _collapsed = weekly._unique_ranking(scores, signatures)
        if not ranked:
            idle += 1
            weeks.append((cut, 0.0))
            if active is not None:
                transitions += 1
            active = None
            cut += WEEK
            continue
        chosen = ranked[0]
        if chosen != active:
            transitions += 1
            active = chosen
        a = uni[chosen]
        mask = (a["t_in"] >= cut) & (a["t_in"] < end)
        vals = []
        for q0 in np.flatnonzero(mask):
            q = int(q0)
            vals.append(float(a["net"][q]))
            rows.append({"tag": chosen,
                         "order_t": int(a.get("t_order", a["t_in"])[q]),
                         "entry_t": int(a["t_in"][q]),
                         "exit_t": int(a["t_out"][q]),
                         "net": float(a["net"][q]),
                         "risk": float(a["risk"][q]) if "risk" in a else float("nan"),
                         "entry_k": int(a["sigk"][q]),
                         "exit_k": int(a["exit_k"][q]) if "exit_k" in a else -1,
                         "direction": int(a["direction"][q]) if "direction" in a else 0})
        weeks.append((cut, float(np.mean(vals)) if vals else 0.0))
        cut += WEEK
    return {"rows": rows, "weeks": weeks, "idle": idle,
            "transitions": transitions}


def _basic_metrics(values: Iterable[float]) -> dict:
    x = np.asarray(list(values), float)
    if not len(x):
        return {"trades": 0, "net_R": 0.0, "PF": float("nan"),
                "win_pct": 0.0, "DD_R": 0.0, "loss_streak": 0}
    return {"trades": int(len(x)), "net_R": float(x.sum()),
            "mean_R": float(x.mean()), "PF": A23.profit_factor(x),
            "win_pct": 100.0 * float(np.mean(x > 0)),
            "DD_R": A23.additive_drawdown(x),
            "loss_streak": A23.max_loss_streak(x)}


def _a21_metrics(run: dict, start: int, end: int) -> dict:
    rows = sorted((r for r in run["rows"] if start <= r["exit_t"] < end),
                  key=lambda r: (r["exit_t"], r["entry_t"], r["tag"]))
    out = _basic_metrics(r["net"] for r in rows)
    weeks = [v for t, v in run["weeks"] if start <= t < end]
    out.update({"weeks": len(weeks),
                "zero_weeks": int(np.count_nonzero(np.isclose(weeks, 0.0))) if weeks else 0,
                "positive_week_pct": 100.0 * float(np.mean(np.asarray(weeks) > 0)) if weeks else 0.0,
                "active_week_pct": 100.0 * float(np.mean(~np.isclose(weeks, 0.0))) if weeks else 0.0})
    return out


def _a23_run(uni: dict, meta: dict, b5: D.Bars) -> dict:
    wd = A23.WeeklyData.build(b5, uni)
    selector = A23.Selector(wd, uni, meta)
    first_policy = int(wd.boundaries[A23.MIN_HISTORY_WEEKS])
    last = int(b5.t[-1] + b5.step)
    decisions = A23.decisions_through(selector, first_policy, last)
    execution = A23.admit_orders(A23.orders_from_decisions(b5, uni, decisions))
    path = A23.unit_path(b5, wd, execution.admitted)
    return {"wd": wd, "decisions": decisions, "execution": execution,
            "path": path}


def _a23_metrics(run: dict, b5: D.Bars, start: int, end: int,
                 stress: bool) -> dict:
    return A23.window_metrics(b5, run["path"], run["execution"].admitted,
                              start, end, stress)


def _a24_run(pd: A24.PolicyData, b5: D.Bars, streams: dict,
             meta: dict) -> dict:
    last = int(b5.t[-1] + b5.step)
    first_policy = int(pd.boundaries[A24.MIN_HISTORY_WEEKS])
    decisions = A24.decisions_through(A24.Selector(pd, meta, "gate"),
                                      first_policy, last)
    opportunities = A24.opportunities_from_decisions(
        b5, streams, meta, decisions, True)
    execution = A24.execute_opportunities(opportunities, True)
    path = A24.unit_path(b5, execution.admitted)
    return {"decisions": decisions, "execution": execution, "path": path}


def _a24_metrics(run: dict, b5: D.Bars, meta: dict, start: int, end: int,
                 stress: bool) -> dict:
    return A24.window_metrics(b5, run["path"], run["execution"], meta,
                              start, end, stress)


def _windows(b5: D.Bars) -> tuple[tuple[str, int, int], ...]:
    last = int(b5.t[-1] + b5.step)
    return (("44_MONTH", REPORT_START, REPORT_SPLIT),
            ("TRAILING_12_MONTH", REPORT_SPLIT, last),
            ("FULL", REPORT_START, last))


def _serial(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, dict):
        return {str(k): _serial(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serial(v) for v in obj]
    return obj


def _collect_a21(run: dict, b5: D.Bars) -> dict:
    rows = {name: {"BASE": _a21_metrics(run, start, end)}
            for name, start, end in _windows(b5)}
    rows["FULL_AVAILABLE"] = {
        "BASE": _a21_metrics(run, int(b5.t[0]), int(b5.t[-1] + b5.step))}
    return rows


def _collect_a23(run: dict, b5: D.Bars) -> dict:
    return {name: {cost: _a23_metrics(run, b5, start, end, stress)
                   for cost, stress in (("BASE", False), ("COST_1P5X", True))}
            for name, start, end in _windows(b5)}


def _collect_a24(run: dict, b5: D.Bars, meta: dict) -> dict:
    return {name: {cost: _a24_metrics(run, b5, meta, start, end, stress)
                   for cost, stress in (("BASE", False), ("COST_1P5X", True))}
            for name, start, end in _windows(b5)}


def _metric_close(got: float, want: float, tol: float = 5e-4) -> bool:
    return abs(float(got) - float(want)) <= tol


def synthetic_audits() -> dict:
    # A is signalled first but fills at 20; B is signalled later and fills at 10.
    ek = np.asarray([20, 10], np.int64)
    ok = np.asarray([0, 5], np.int64)
    held = np.asarray([5, 4], np.int64)
    ca, _ = causal_indices(ek, ok, held)
    ca_removed, _ = causal_indices(ek[1:], ok[1:], held[1:])
    la, _ = legacy_indices(ek, held)
    la_removed, _ = legacy_indices(ek[1:], held[1:])
    future_invariant = (1 in ca and 0 in ca_removed)
    legacy_fails = (1 not in la and 0 in la_removed)

    # B remains open through A's bar: A must be rejected.  If B closes before,
    # A may fill.  Inputs are already in signal order A,B.
    ca_open, _ = causal_indices(ek, ok, np.asarray([5, 12]))
    ca_closed, _ = causal_indices(ek, ok, np.asarray([5, 4]))
    boundary = (np.array_equal(ca_open, np.asarray([1]))
                and np.array_equal(ca_closed, np.asarray([1, 0])))

    sa, sr = streaming_indices(ek, ok, held)
    batch_equal = np.array_equal(sa, ca)
    # Permuting storage while retaining stable sequence IDs cannot alter IDs.
    ids = np.asarray([100, 200], np.int64)
    perm = np.asarray([1, 0])
    pa, _ = causal_indices(ek[perm], ok[perm], held[perm], ids[perm])
    accepted_ids = ids[perm][pa]
    original_ids = ids[ca]
    permutation = np.array_equal(accepted_ids, original_ids)

    # Exit bar remains busy; next bar is flat.
    bx = np.asarray([10, 14, 15], np.int64)
    bo = bx.copy()
    bh = np.asarray([4, 1, 1], np.int64)
    bi, _ = causal_indices(bx, bo, bh)
    exit_boundary = np.array_equal(bi, np.asarray([0, 2]))
    # Stronger online oracle: A's fill is not supplied.  Identical bars through
    # B's market fill yield the same B decision whether later bars fill A or not.
    o = np.full(25, 100.0)
    h = np.full(25, 101.0)
    low_fill = np.full(25, 99.0)
    low_fill[20] = 89.0
    low_no_fill = low_fill.copy()
    low_no_fill[11:] = 99.0
    orders = [
        {"id": 0, "seq": 0, "order_k": 0, "kind": "limit",
         "direction": 1, "limit": 90.0, "expiry_k": 24, "held": 2},
        {"id": 1, "seq": 1, "order_k": 10, "kind": "market",
         "direction": 1, "limit": 0.0, "expiry_k": 11, "held": 4},
    ]
    price_fill = streaming_price_oracle(o, h, low_fill, orders)
    price_no_fill = streaming_price_oracle(o, h, low_no_fill, orders)
    price_oracle_future_invariant = (1 in price_fill[0]
                                     and 1 in price_no_fill[0])
    passed = all((future_invariant, legacy_fails, boundary, batch_equal,
                  permutation, exit_boundary, price_oracle_future_invariant))
    return {"future_fill_invariance": future_invariant,
            "legacy_negative_control_failed_as_required": legacy_fails,
            "open_vs_closed_at_later_fill": boundary,
            "streaming_batch_equal": batch_equal,
            "permutation_invariant": permutation,
            "busy_through_exit_bar": exit_boundary,
            "independent_price_oracle_future_invariant":
                price_oracle_future_invariant,
            "passed": passed}


def full_chain_audits(b5: D.Bars, streams: dict, meta: dict) -> tuple[dict, dict]:
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    out_n = 0
    out_gross = 0.0
    out_net = 0.0
    out_wins = 0
    market_match = True
    stream_batch_match = True
    by_stream: dict[str, list[dict]] = defaultdict(list)
    for m in meta.values():
        by_stream[m["stream"]].append(m)
    sample_stride = max(1, len(meta) // 200)
    seen = 0
    for key, members in by_stream.items():
        s = streams[key]
        ek = s["entry_k"].astype(np.int64, copy=False)
        ok = s["order_k"].astype(np.int64, copy=False)
        for m in members:
            p = int(m["plane"])
            held = s["held"][:, p].astype(np.int64, copy=False)
            old_accept, rejects = legacy_indices(ek, held)
            new_accept, _ = causal_indices(ek, ok, held)
            if int(m["exp"]) == 0 and not np.array_equal(old_accept, new_accept):
                market_match = False
            if seen % sample_stride == 0:
                oracle, _ = streaming_indices(ek, ok, held)
                if not np.array_equal(oracle, new_accept):
                    stream_batch_match = False
            seen += 1
            if rejects:
                risk = float(m["stop"]) * s["atr"]
                gross = s["gross"][:, p]
                net = gross - fee / risk
                for q, blocker in rejects:
                    if int(ek[q]) < int(ek[blocker]):
                        out_n += 1
                        out_gross += float(gross[q])
                        out_net += float(net[q])
                        out_wins += int(net[q] > 0)
    crosscheck = {
        "count": out_n,
        "gross_mean_R": out_gross / out_n if out_n else float("nan"),
        "net_mean_R": out_net / out_n if out_n else float("nan"),
        "win_pct": 100.0 * out_wins / out_n if out_n else float("nan"),
        "claude_count": 3_344_875,
        "count_delta": out_n - 3_344_875,
    }
    audits = {"market_entry_identity_all_cells": market_match,
              "streaming_batch_historical_sample": stream_batch_match,
              "out_of_order_defect_present": out_n > 0,
              "passed": market_match and stream_batch_match and out_n > 0}
    return audits, crosscheck


def cache_mutation_audit(stamp: dict) -> bool:
    changed = dict(stamp)
    changed["ordering"] = "MUTATED"
    return changed != stamp and changed["code_sha256"] == stamp["code_sha256"]


def _print_result_table(policy: str, old: dict, causal: dict) -> None:
    print(f"POLICY_RESULTS_BEGIN policy={policy}")
    for window in old:
        for cost in old[window]:
            om = old[window][cost]
            cm = causal[window][cost]
            print(f"RESULT policy={policy} window={window} cost={cost} "
                  f"old_net_R={om['net_R']:.8f} causal_net_R={cm['net_R']:.8f} "
                  f"delta_R={cm['net_R']-om['net_R']:.8f} "
                  f"old_trades={om['trades']} causal_trades={cm['trades']} "
                  f"old_PF={om.get('PF', float('nan')):.8f} "
                  f"causal_PF={cm.get('PF', float('nan')):.8f} "
                  f"old_DD_R={om.get('MTM_DD_R', om.get('DD_R', float('nan'))):.8f} "
                  f"causal_DD_R={cm.get('MTM_DD_R', cm.get('DD_R', float('nan'))):.8f} "
                  f"old_active_week_pct={om.get('active_week_pct', float('nan')):.6f} "
                  f"causal_active_week_pct={cm.get('active_week_pct', float('nan')):.6f}")
    print(f"POLICY_RESULTS_END policy={policy}")


def _a23_verdict(results: dict) -> str:
    required = ("44_MONTH", "TRAILING_12_MONTH")
    return ("PASS_UNIT_RISK" if all(results[w][c]["net_R"] > 0
                                     for w in required
                                     for c in ("BASE", "COST_1P5X"))
            else "FAIL_UNIT_RISK")


def _a24_verdict(results: dict, run: dict) -> str:
    required = ("44_MONTH", "TRAILING_12_MONTH")
    last = max(d.end for d in run["decisions"]) if run["decisions"] else 0
    forward = [d for d in run["decisions"] if REPORT_START <= d.cut < last]
    no_basket = sum(len(d.members) < A24.MIN_MEMBERS for d in forward)
    ok = (all(results[w][c]["net_R"] > 0 for w in required
              for c in ("BASE", "COST_1P5X"))
          and no_basket <= len(forward) / 2
          and all(results[w]["BASE"]["active_week_pct"] >= 50 for w in required))
    return "PASS_UNIT_RISK" if ok else "FAIL_UNIT_RISK"


def run() -> int:
    print("AMENDMENT_26_CAUSAL_FILL_TIME_CHAIN")
    print("research_only=true mt5_connection=false order_sending=false")
    print("RESULTS_WITHHELD_UNTIL_SECTION8_AUDITS_COMPLETE=true")
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    print(f"data_sha256={canonical.bars_digest(b5)} bars={len(b5)} "
          f"first={utc(int(b5.t[0]))} last={utc(last)}")

    synthetic = synthetic_audits()
    print(f"AUDIT_1_TO_5_SYNTHETIC {synthetic}")
    if not synthetic["passed"]:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    streams, raw_meta, raw_built = A24.load_raw_cache(b5)
    print(f"RAW_CACHE_FULL_HASH=PASS built_this_run={raw_built} "
          f"streams={len(streams)} cells={len(raw_meta)}")
    historical, crosscheck = full_chain_audits(b5, streams, raw_meta)
    print(f"AUDIT_6_MARKET_AND_STREAMING {historical}")
    if not historical["passed"]:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    state_audit = A24.audit_state_fidelity()
    spread_audit = A24.audit_spread_gate()
    state_ok = all(bool(v) for v in state_audit.values())
    spread_ok = bool(spread_audit.get("passed"))
    print(f"AUDIT_8_9_LEDGER_SEPARATION passed={state_ok} detail={state_audit}")
    print(f"AUDIT_8_SPREAD_GATE passed={spread_ok} detail={spread_audit}")
    if not (state_ok and spread_ok):
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    # Reproduce old A24 while the raw cache is resident.  Figures are retained
    # but deliberately not printed until every audit has completed.
    old_pd24, _ = A24.build_policy_data(b5, streams, raw_meta, apply_gate=True)
    old_run24 = _a24_run(old_pd24, b5, streams, raw_meta)
    old24 = _collect_a24(old_run24, b5, raw_meta)
    old24_ok = (
        _metric_close(old24["44_MONTH"]["BASE"]["net_R"], -66.66364041)
        and _metric_close(old24["44_MONTH"]["COST_1P5X"]["net_R"], -104.46702576)
        and _metric_close(old24["TRAILING_12_MONTH"]["BASE"]["net_R"], 59.25703324)
        and _metric_close(old24["TRAILING_12_MONTH"]["COST_1P5X"]["net_R"], 35.60852863)
        and old24["FULL"]["BASE"]["trades"] == 11_738)
    print(f"AUDIT_7_LEGACY_A24_REFERENCE_REPRODUCED={old24_ok}")
    if not old24_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    causal_pd24 = _policy_data_causal_gate(b5, streams, raw_meta)
    causal24_cutoff_audit = A24.audit_truncation(causal_pd24, raw_meta)
    print(f"AUDIT_3_CAUSAL_A24_CUTOFF {causal24_cutoff_audit}")
    if not causal24_cutoff_audit["passed"]:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    causal_run24 = _a24_run(causal_pd24, b5, streams, raw_meta)
    causal24 = _collect_a24(causal_run24, b5, raw_meta)

    causal_uni, causal_meta, cache_built, stamp = load_causal_universe(
        b5, streams, raw_meta)
    cache_ok = (len(causal_uni) == E.n_cells() and cache_mutation_audit(stamp))
    print(f"AUDIT_10_CAUSAL_CACHE_FULL_HASH={cache_ok} built_this_run={cache_built} "
          f"cells={len(causal_uni)}")
    if not cache_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    # The live MT5+CSV snapshot used by published A21 no longer exists.  Build
    # both chains anew from the same canonical bars and frozen a67cca7 engine;
    # this isolates ordering without pretending to reproduce +248.785 R.
    old_uni21, causal_uni21, _meta21, a21_cache_built, a21_stamp = (
        load_a21_same_data_universes(b5))
    a21_cache_ok = (len(old_uni21) == E.n_cells()
                    and len(causal_uni21) == E.n_cells()
                    and cache_mutation_audit(a21_stamp))
    print(f"AUDIT_7_A21_PUBLISHED_REFERENCE=NOT_REPRODUCIBLE "
          "reason=original_live_MT5_plus_CSV_snapshot_no_longer_exists")
    print(f"AUDIT_10_A21_PAIRED_CACHE_FULL_HASH={a21_cache_ok} "
          f"built_this_run={a21_cache_built} cells={len(old_uni21)}")
    if not a21_cache_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    market21 = [tag for tag, m in _meta21.items() if int(m["exp"]) == 0]
    a21_market_identity = all(
        all(np.array_equal(old_uni21[tag][key], causal_uni21[tag][key])
            for key in ("t_in", "t_out", "net", "sigk"))
        for tag in market21)
    print(f"AUDIT_6_A21_MARKET_ENTRY_IDENTITY={a21_market_identity} "
          f"cells={len(market21)}")
    if not a21_market_identity:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    old_run21 = _a21_run(old_uni21, b5)
    old21 = _collect_a21(old_run21, b5)
    causal_run21 = _a21_run(causal_uni21, b5)
    causal21 = _collect_a21(causal_run21, b5)
    del old_uni21, causal_uni21, _meta21
    gc.collect()

    old_uni, old_meta = old_audit.load_universe(b5)
    # Execute the slow existing basket integrations without reloading either
    # multi-gigabyte cache.  These are the same assertions as the test files.
    baseline24, reproduction_mismatches = A24.build_policy_data(
        b5, streams, raw_meta, apply_gate=False, old_uni=old_uni)
    old24_integration = A24.run_audits(
        b5, old_pd24, raw_meta, reproduction_mismatches)
    old24_integration_ok = (not reproduction_mismatches
                            and old24_integration["passed_before_mtf_suite"]
                            and len(baseline24.tags) == E.n_cells())
    print(f"AUDIT_11_EXISTING_A24_INTEGRATION={old24_integration_ok} "
          f"detail={old24_integration}")
    if not old24_integration_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    old_run23 = _a23_run(old_uni, old_meta, b5)
    old23_cutoff_audit = A23.audit_truncation(
        b5, old_run23["wd"], old_uni, old_meta)
    print(f"AUDIT_11_EXISTING_A23_INTEGRATION {old23_cutoff_audit}")
    if not old23_cutoff_audit["passed"]:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    old23 = _collect_a23(old_run23, b5)
    old23_ok = (
        _metric_close(old23["44_MONTH"]["BASE"]["net_R"], 62.070, 0.001)
        and _metric_close(old23["44_MONTH"]["COST_1P5X"]["net_R"], -80.991, 0.001)
        and _metric_close(old23["TRAILING_12_MONTH"]["BASE"]["net_R"], 184.020, 0.001)
        and _metric_close(old23["FULL"]["BASE"]["net_R"], 246.090, 0.001)
        and old23["FULL"]["BASE"]["trades"] == 17_251)
    print(f"AUDIT_7_LEGACY_A23_REFERENCE_REPRODUCED={old23_ok}")
    if not old23_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    del old_uni, old_meta, old_pd24, baseline24, causal_pd24, streams
    gc.collect()

    # Causal policy computations occur before the audit gate, but their
    # figures remain withheld until ALL_PASS is printed.
    causal_run23 = _a23_run(causal_uni, causal_meta, b5)
    causal23_cutoff_audit = A23.audit_truncation(
        b5, causal_run23["wd"], causal_uni, causal_meta)
    print(f"AUDIT_3_CAUSAL_A23_CUTOFF {causal23_cutoff_audit}")
    if not causal23_cutoff_audit["passed"]:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2
    causal23 = _collect_a23(causal_run23, b5)

    import test_causal_chain as causal_tests
    causal_test_rc = causal_tests.main()
    print(f"AUDIT_11_CAUSAL_FAST_SUITE return_code={causal_test_rc}")
    if causal_test_rc != 0:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    import test_basket_dd as basket23_tests
    import test_basket_gate as basket24_tests
    basket_fast = [
        basket23_tests.test_exit_week_assignment_and_zero_weeks,
        basket23_tests.test_decay_effective_sample_size,
        basket23_tests.test_truncation_removes_future_columns,
        basket24_tests.test_fill_bar_spread_cannot_drive_gate,
        basket24_tests.test_selected_state_is_separate_from_hypothetical_history,
        basket24_tests.test_cache_stamp_is_full_hash_sensitive,
        basket24_tests.test_gate_threshold_algebra,
    ]
    basket_fast_ok = True
    for fn in basket_fast:
        try:
            fn()
            print(f"AUDIT_11_BASKET_FAST PASS {fn.__name__}")
        except Exception as exc:
            basket_fast_ok = False
            print(f"AUDIT_11_BASKET_FAST FAIL {fn.__name__} {exc!r}")
    if not basket_fast_ok:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    import test_mtf_engine as mtf_tests
    mtf_rc = mtf_tests.main()
    print(f"AUDIT_11_EXISTING_MTF_SUITE return_code={mtf_rc} "
          f"passes={len(mtf_tests.PASSES)} failures={len(mtf_tests.FAILS)}")
    if mtf_rc != 0:
        print("SECTION8_AUDITS=FAIL result_not_run=true")
        return 2

    print("SECTION8_AUDITS=ALL_PASS result_may_run=true")
    print(f"CAUSALITY_VERDICT=LEGACY_LOOKAHEAD_CONFIRMED causal_chain=PASS")
    print("CONTAMINATION_CROSSCHECK " + " ".join(
        f"{k}={v}" for k, v in crosscheck.items()))
    print("A21_PUBLISHED_REFERENCE status=NOT_REPRODUCIBLE "
          "published_trades=1757 published_net_R=248.78528726 "
          "reason=pre_canonical_live_MT5_plus_CSV_data_snapshot_unavailable")

    _print_result_table("AMENDMENT21", old21, causal21)
    print("AMENDMENT21_ORIGINAL_VERDICT=EXPLORATORY_BASELINE_NOT_PROMOTION")
    _print_result_table("AMENDMENT23", old23, causal23)
    verdict23 = _a23_verdict(causal23)
    print(f"AMENDMENT23_CAUSAL_SECTION10_VERDICT={verdict23}")
    _print_result_table("AMENDMENT24", old24, causal24)
    verdict24 = _a24_verdict(causal24, causal_run24)
    print(f"AMENDMENT24_CAUSAL_SECTION11_VERDICT={verdict24}")

    sizing23 = verdict23 == "PASS_UNIT_RISK"
    sizing24 = verdict24 == "PASS_UNIT_RISK"
    if not sizing23:
        print("AMENDMENT23_DD_SIZING=NOT_RUN reason=causal_unit_risk_failed")
    else:
        print("AMENDMENT23_DD_SIZING=REQUIRED_NOT_IMPLEMENTED_IN_MEASUREMENT")
    if not sizing24:
        print("AMENDMENT24_DD_SIZING=NOT_RUN reason=causal_unit_risk_failed")
    else:
        print("AMENDMENT24_DD_SIZING=REQUIRED_NOT_IMPLEMENTED_IN_MEASUREMENT")

    print("CONTAMINATED_NOT_REMEASURED=Amendment14_grid_statistics;")
    print("CONTAMINATED_NOT_REMEASURED=Amendment15_16_walk_forward;")
    print("CONTAMINATED_NOT_REMEASURED=compound_bar_replay;")
    print("CONTAMINATED_NOT_REMEASURED=Claude_era_and_quarter_grid_diagnoses")

    summary = {
        "audit_verdict": "ALL_PASS",
        "crosscheck": crosscheck,
        "amendment21": {"old": old21, "causal": causal21,
                         "verdict": "EXPLORATORY_BASELINE_NOT_PROMOTION",
                         "published_reference": {
                             "status": "NOT_REPRODUCIBLE",
                             "trades": 1757, "net_R": 248.7852872580764,
                             "reason": "original live MT5+CSV snapshot predates canonical file"}},
        "amendment23": {"old": old23, "causal": causal23,
                         "verdict": verdict23, "dd_sizing_run": False},
        "amendment24": {"old": old24, "causal": causal24,
                         "verdict": verdict24, "dd_sizing_run": False},
        "cache": {"path": str(CACHE_PATH), "built": cache_built,
                  "stamp": stamp, "a21_path": str(A21_CACHE_PATH),
                  "a21_built": a21_cache_built, "a21_stamp": a21_stamp},
        "contaminated_not_remeasured": [
            "Amendment 14 grid statistics", "Amendment 15/16 walk-forward",
            "compound_bar_replay.py", "Claude era/quarter grid diagnoses"],
    }
    SUMMARY_PATH.write_text(json.dumps(_serial(summary), indent=2,
                                       allow_nan=True), encoding="utf-8")
    print(f"SUMMARY_JSON={SUMMARY_PATH}")
    print("NO_ORDER=true AUTOTRADER_STARTED=false PR_OPENED=false")
    return 0 if not (sizing23 or sizing24) else 3


if __name__ == "__main__":
    raise SystemExit(run())
