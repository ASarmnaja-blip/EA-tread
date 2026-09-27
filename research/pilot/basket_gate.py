"""Amendment 24: causal execution-friction-to-R basket research.

Research only.  There is no MetaTrader connection or order-sending code here.
Raw signal/fill opportunities are cached before a cell busy filter so the
always-on candidate history and the actually selected basket state can be
replayed independently.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import math
import pickle
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_dd as A23
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
DECAY = 2.0 ** (-1.0 / 3.0)
LCB_COEF = 0.75
MIN_HISTORY_WEEKS = 26
MIN_NONZERO_WEEKS = 8
MIN_MEMBERS = 3
MAX_MEMBERS = 5
MIN_WEIGHT = 0.10
MAX_WEIGHT = 0.35
CORR_ADMISSION = 0.70
CORR_WEIGHT_CAP = 0.50
PAIR_WEIGHT_CAP = 0.50
GATE_BASE_MAX = 1.0 / 12.0
REPORT_START = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
REPORT_SPLIT = int(datetime(2025, 9, 21, tzinfo=timezone.utc).timestamp())
CACHE_VERSION = 1


def utc(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def stream_key(setup: str, tf: str, off: float, exp: int) -> str:
    return f"{setup}/{tf}/o{off:g}e{exp}"


def cell_tag(setup: str, tf: str, st: float, tg: float,
             off: float, exp: int) -> str:
    return f"{setup}/{tf}/s{st:g}/t{tg:g}/o{off:g}e{exp}"


def gate_spread(b5: D.Bars, k: int) -> float:
    """Only the last fully closed M5 bar may drive the historical gate."""
    if k > 0 and b5.sp is not None:
        value = float(b5.sp[k - 1])
        if np.isfinite(value) and value > 0:
            return max(value, E.SPREAD_FALLBACK)
    return E.SPREAD_FALLBACK


def gate_friction_r(b5: D.Bars, k: int, risk: float) -> float:
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    return (gate_spread(b5, k) + fee) / risk


def accounting_friction_r(b5: D.Bars, k: int, risk: float) -> float:
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    return (E.spread_at(b5, k) + fee) / risk


def gate_passes(b5: D.Bars, k: int, risk: float) -> bool:
    return gate_friction_r(b5, k, risk) <= GATE_BASE_MAX + 1e-15


def weekend_boundaries(first: int, last: int) -> np.ndarray:
    cut = weekly._week_boundary(first)
    if cut > first:
        cut -= WEEK
    while cut + WEEK <= first:
        cut += WEEK
    out = []
    while cut <= last + WEEK:
        out.append(cut)
        cut += WEEK
    return np.asarray(out, np.int64)


def _cache_path() -> Path:
    sp = int(round(1000 * E.SPREAD_FALLBACK))
    co = int(round(1000 * E.COMMISSION_RT))
    return Path(f"data/amendment24_raw_opportunities_v{CACHE_VERSION}_"
                f"sp{sp:03d}_co{co:03d}.pkl")


def _cache_stamp(b5: D.Bars) -> dict:
    code = hashlib.sha256()
    for module in (Path(__file__), Path(E.__file__), Path(wf.__file__),
                   Path(core.__file__), Path(D.__file__)):
        code.update(module.name.encode())
        code.update(module.read_bytes())
    return {
        "version": CACHE_VERSION,
        "data_sha256": canonical.bars_digest(b5),
        "code_sha256": code.hexdigest(),
        "spread_floor": E.SPREAD_FALLBACK,
        "commission_rt": E.COMMISSION_RT,
        "slip_per_fill": E.SLIP_PER_FILL,
        "swap_long": E.SWAP_LONG,
        "swap_short": E.SWAP_SHORT,
        "rollover_h": E.ROLLOVER_H,
        "time_stop": E.TIME_STOP_M5,
        "setups": E.SETUPS,
        "timeframes": E.TIMEFRAMES,
        "stops": E.STOPS,
        "targets": E.TARGETS,
        "entry_modes": E.ENTRY_MODES,
        "gate_base_max": GATE_BASE_MAX,
        "gate_spread_lag_bars": 1,
    }


def _stamp_matches(got: dict, expected: dict) -> bool:
    return got == expected


def build_raw_cache(b5: D.Bars) -> tuple[dict, dict]:
    """Build raw fills and 25 resolution planes before any cell busy filter."""
    streams: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    t_end = int(b5.t[-1] + b5.step)
    plane_keys = tuple((st, tg) for st in E.STOPS for tg in E.TARGETS)
    for tfname, mult in E.TIMEFRAMES:
        bs, nxt = E.resample(b5, mult)
        keep = bs.t <= t_end
        atr_s = core.atr(bs, E.ATR_N)
        ctx = core.Ctx(bs, nxt)
        for setup in E.SETUPS:
            signals = [(i, d) for i, d in E.setup_signals(setup, ctx) if keep[i]]
            for off, exp in E.ENTRY_MODES:
                order_k, entry_k, direction = [], [], []
                entries, atrs, at_open = [], [], []
                for i, d in signals:
                    k0 = int(nxt[i])
                    a = float(atr_s[i])
                    if k0 < 0 or not np.isfinite(a) or a <= 0:
                        continue
                    if exp == 0:
                        k = k0
                        entry = float(b5.o[k] + (E.spread_at(b5, k)
                                                  if d > 0 else 0.0))
                        opened = True
                    else:
                        limit = float(bs.c[i]) - d * off * a
                        got = E.entry_fill_detail(b5, k0, d, limit, exp * mult)
                        if got is None:
                            continue
                        k, entry, opened = got
                    order_k.append(k0)
                    entry_k.append(k)
                    direction.append(d)
                    entries.append(entry)
                    atrs.append(a)
                    at_open.append(opened)
                n = len(entry_k)
                gross = np.empty((n, len(plane_keys)), np.float64)
                held = np.empty((n, len(plane_keys)), np.uint16)
                for q in range(n):
                    plane = E.resolve_plane(
                        b5, int(entry_k[q]), int(direction[q]), float(entries[q]),
                        float(atrs[q]), E.STOPS, E.TARGETS, E.TIME_STOP_M5,
                        allow_entry_bar_target=bool(at_open[q]))
                    for p, key in enumerate(plane_keys):
                        g, _why, nb = plane[key]
                        gross[q, p] = g
                        held[q, p] = nb
                key = stream_key(setup, tfname, off, exp)
                streams[key] = {
                    "order_k": np.asarray(order_k, np.int32),
                    "entry_k": np.asarray(entry_k, np.int32),
                    "direction": np.asarray(direction, np.int8),
                    "entry": np.asarray(entries, np.float64),
                    "atr": np.asarray(atrs, np.float64),
                    "at_open": np.asarray(at_open, np.bool_),
                    "gross": gross,
                    "held": held,
                }
                print(f"raw_cache_build stream={key} fills={n}")
                for p, (st, tg) in enumerate(plane_keys):
                    tag = cell_tag(setup, tfname, st, tg, off, exp)
                    meta[tag] = {"setup": setup, "tf": tfname, "mult": mult,
                                 "stop": st, "target": tg, "off": off,
                                 "exp": exp, "stream": key, "plane": p}
    if len(streams) != len(E.SETUPS) * len(E.TIMEFRAMES) * len(E.ENTRY_MODES):
        raise RuntimeError(f"raw stream count mismatch: {len(streams)}")
    if len(meta) != E.n_cells():
        raise RuntimeError(f"declared cell count mismatch: {len(meta)}")
    return streams, meta


def load_raw_cache(b5: D.Bars) -> tuple[dict, dict, bool]:
    path = _cache_path()
    expected = _cache_stamp(b5)
    if path.exists():
        with path.open("rb") as fh:
            got, streams, meta = pickle.load(fh)
        if (_stamp_matches(got, expected) and len(meta) == E.n_cells()
                and len(streams) == 330):
            print(f"amendment24_cache=HIT path={path} streams={len(streams)} "
                  f"cells={len(meta)}")
            return streams, meta, False
        print("amendment24_cache=HASH_MISS rebuilding")
    else:
        print("amendment24_cache=MISS building raw opportunity cache")
    streams, meta = build_raw_cache(b5)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump((expected, streams, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    with path.open("rb") as fh:
        got, check_streams, check_meta = pickle.load(fh)
    if not _stamp_matches(got, expected):
        raise RuntimeError("new cache failed full-hash readback")
    if set(check_streams) != set(streams) or check_meta != meta:
        raise RuntimeError("new cache failed content readback")
    print(f"amendment24_cache=BUILT_FULL_HASH_PASS path={path}")
    return streams, meta, True


@dataclass(frozen=True)
class SignatureHistory:
    t_order: np.ndarray
    t_in: np.ndarray
    t_out: np.ndarray
    direction: np.ndarray
    entry_k: np.ndarray
    exit_k: np.ndarray


@dataclass
class PolicyData:
    tags: tuple[str, ...]
    tag_index: dict[str, int]
    boundaries: np.ndarray
    base: np.ndarray
    stress: np.ndarray
    signatures: dict[str, SignatureHistory]
    candidate_gate_cancels: np.ndarray

    def truncated(self, j: int) -> "PolicyData":
        return PolicyData(self.tags, self.tag_index,
                          self.boundaries[:j + 1].copy(),
                          self.base[:, :j].copy(), self.stress[:, :j].copy(),
                          self.signatures, self.candidate_gate_cancels.copy())


def _cell_history(b5: D.Bars, stream: dict, m: dict,
                  apply_gate: bool) -> tuple[SignatureHistory, np.ndarray, int]:
    st = float(m["stop"])
    p = int(m["plane"])
    chosen = []
    busy = -1
    gate_cancels = 0
    for q, k_value in enumerate(stream["entry_k"]):
        k = int(k_value)
        if k <= busy:
            continue
        risk = st * float(stream["atr"][q])
        if apply_gate and not gate_passes(b5, k, risk):
            gate_cancels += 1
            continue
        nb = int(stream["held"][q, p])
        chosen.append(q)
        busy = k + nb
    q = np.asarray(chosen, np.int64)
    if not len(q):
        empty64 = np.asarray([], np.int64)
        sig = SignatureHistory(empty64, empty64.copy(), empty64.copy(),
                               np.asarray([], np.int8), empty64.copy(),
                               empty64.copy())
        return sig, np.empty((0, 5), float), gate_cancels
    entry_k = stream["entry_k"][q].astype(np.int64)
    exit_k = np.minimum(entry_k + stream["held"][q, p].astype(np.int64),
                        len(b5) - 1)
    order_k = stream["order_k"][q].astype(np.int64)
    direction = stream["direction"][q].astype(np.int8)
    risk = st * stream["atr"][q]
    gross_geom = stream["gross"][q, p]
    fee_r = (E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL) / risk
    swap_r = np.asarray([
        (E.rollover_nights(int(b5.t[k]), int(b5.t[x])) * E.SWAP_LONG / r)
        if d > 0 else 0.0
        for k, x, d, r in zip(entry_k, exit_k, direction, risk)], float)
    base = gross_geom - fee_r - swap_r
    exec_r = np.asarray([accounting_friction_r(b5, int(k), float(r))
                         for k, r in zip(entry_k, risk)], float)
    stress = base - 0.5 * exec_r
    gross_pre = base + exec_r + swap_r
    sig = SignatureHistory(b5.t[order_k].astype(np.int64),
                           b5.t[entry_k].astype(np.int64),
                           b5.t[exit_k].astype(np.int64), direction,
                           entry_k, exit_k)
    # columns: base, stress, gross-pre-cost, execution friction, swap
    ledger = np.column_stack((base, stress, gross_pre, exec_r, swap_r))
    return sig, ledger, gate_cancels


def build_policy_data(b5: D.Bars, streams: dict, meta: dict,
                      apply_gate: bool, old_uni: dict | None = None
                      ) -> tuple[PolicyData, list[str]]:
    tags = tuple(sorted(meta))
    bounds = weekend_boundaries(int(b5.t[0]), int(b5.t[-1] + b5.step))
    nweek = len(bounds) - 1
    base = np.zeros((len(tags), nweek), np.float64)
    stress = np.zeros_like(base)
    signatures = {}
    cancels = np.zeros(len(tags), np.int64)
    mismatches: list[str] = []
    for i, tag in enumerate(tags):
        m = meta[tag]
        sig, ledger, nc = _cell_history(b5, streams[m["stream"]], m,
                                        apply_gate)
        signatures[tag] = sig
        cancels[i] = nc
        bins = np.searchsorted(bounds, sig.t_out, side="right") - 1
        valid = (bins >= 0) & (bins < nweek)
        if np.any(valid):
            np.add.at(base[i], bins[valid], ledger[valid, 0])
            np.add.at(stress[i], bins[valid], ledger[valid, 1])
        if old_uni is not None:
            old = old_uni.get(tag)
            if old is None:
                mismatches.append(f"{tag}:missing_old")
            else:
                checks = (
                    ("t_order", sig.t_order, old["t_order"]),
                    ("t_in", sig.t_in, old["t_in"]),
                    ("t_out", sig.t_out, old["t_out"]),
                    ("direction", sig.direction, old["direction"]),
                    ("entry_k", sig.entry_k, old["sigk"]),
                    ("exit_k", sig.exit_k, old["exit_k"]),
                )
                for name, got, want in checks:
                    if not np.array_equal(got, want):
                        mismatches.append(f"{tag}:{name}:{len(got)}!={len(want)}")
                        break
    return (PolicyData(tags, {tag: i for i, tag in enumerate(tags)}, bounds,
                       base, stress, signatures, cancels), mismatches)


def signature_at(history: SignatureHistory, cut: int) -> tuple[bytes, bytes, bytes]:
    mask = history.t_out < cut
    return (history.t_order[mask].tobytes(), history.t_in[mask].tobytes(),
            history.direction[mask].tobytes())


@dataclass
class Decision:
    cut: int
    end: int
    members: tuple[str, ...] = ()
    weights: dict[str, float] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    risk_contributions: dict[str, float] = field(default_factory=dict)
    middle_members: tuple[str, ...] = ()
    n_eff: float = 0.0
    eligible_count: int = 0
    duplicate_collapsed: int = 0
    reason: str = ""
    member_turnover: float = 0.0
    weight_turnover: float = 0.0
    binding_caps: tuple[str, ...] = ()


def weighted_corr(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    sw = float(w.sum())
    if sw <= 0:
        return float("nan")
    mx = float(np.dot(w, x) / sw)
    my = float(np.dot(w, y) / sw)
    dx, dy = x - mx, y - my
    vx = float(np.dot(w, dx * dx) / sw)
    vy = float(np.dot(w, dy * dy) / sw)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return float(np.dot(w, dx * dy) / sw / math.sqrt(vx * vy))


class Selector:
    """Amendment 24 stressed selector or paired Amendment 23 baseline."""
    def __init__(self, pd: PolicyData, meta: dict, mode: str):
        if mode not in {"gate", "a23"}:
            raise ValueError(mode)
        self.pd = pd
        self.meta = meta
        self.mode = mode

    def _moments(self, j: int):
        ages = np.arange(j - 1, -1, -1, dtype=float)
        w = DECAY ** ages
        sw = float(w.sum())
        n_eff = sw * sw / float(np.dot(w, w))
        rank_series = self.pd.stress[:, :j] if self.mode == "gate" else self.pd.base[:, :j]
        other_series = self.pd.base[:, :j] if self.mode == "gate" else self.pd.stress[:, :j]
        mu = rank_series @ w / sw
        mu2 = (rank_series * rank_series) @ w / sw
        sd = np.sqrt(np.maximum(mu2 - mu * mu, 0.0))
        other_mu = other_series @ w / sw
        downside = np.sqrt((np.minimum(rank_series, 0.0) ** 2) @ w / sw)
        nonzero = np.count_nonzero(rank_series, axis=1)
        lcb = mu - LCB_COEF * sd / math.sqrt(n_eff)
        return w, rank_series, mu, sd, other_mu, downside, nonzero, n_eff, lcb

    def select(self, j: int) -> Decision:
        cut = int(self.pd.boundaries[min(j, len(self.pd.boundaries) - 1)])
        if j < MIN_HISTORY_WEEKS or j >= len(self.pd.boundaries):
            return Decision(cut, cut + WEEK, reason="insufficient_history")
        end = cut + WEEK
        w, hist_rank, mu, sd, other_mu, downside, nonzero, n_eff, lcb = self._moments(j)
        finite = np.isfinite(sd) & np.isfinite(lcb) & np.isfinite(downside)
        eligible = finite & (nonzero >= MIN_NONZERO_WEEKS) & (lcb > 0) & (other_mu > 0)
        idx = np.flatnonzero(eligible)
        d = Decision(cut, end, n_eff=n_eff, eligible_count=len(idx))
        if not len(idx):
            d.reason = "no_eligible_cells"
            return d
        positive_down = downside[idx][downside[idx] > 0]
        if not len(positive_down):
            d.reason = "undefined_downside_floor"
            return d
        vol_floor = float(np.percentile(positive_down, 25))
        ranked = sorted(idx, key=lambda i: (-float(lcb[i]), self.pd.tags[i]))

        unique_ranked = []
        seen = set()
        collapsed = 0
        for i in ranked:
            tag = self.pd.tags[i]
            sig = signature_at(self.pd.signatures[tag], cut)
            if sig in seen:
                collapsed += 1
                continue
            seen.add(sig)
            unique_ranked.append(i)

        selected: list[int] = []
        used_families: set[str] = set()
        corr_map: dict[tuple[str, str], float] = {}
        for i in unique_ranked:
            tag = self.pd.tags[i]
            family = self.meta[tag]["setup"]
            if family in used_families:
                continue
            cs = []
            assessed = True
            for k in selected:
                c = weighted_corr(hist_rank[i], hist_rank[k], w)
                if not np.isfinite(c):
                    assessed = False
                    break
                cs.append((k, c))
            if not assessed or any(c > CORR_ADMISSION + 1e-12 for _k, c in cs):
                continue
            # For Amendment 24 rank-series is already 1.5x stressed.  For the
            # paired A23 baseline the other series is stressed, matching A23.
            stress_mu = mu if self.mode == "gate" else other_mu
            if float(np.mean(stress_mu[selected + [i]])) <= 0:
                continue
            selected.append(i)
            used_families.add(family)
            for k, c in cs:
                corr_map[tuple(sorted((tag, self.pd.tags[k])))] = c
            if len(selected) == MAX_MEMBERS:
                break
        d.duplicate_collapsed = collapsed
        if len(selected) < MIN_MEMBERS:
            d.reason = f"fewer_than_{MIN_MEMBERS}_members"
            return d

        raw = np.asarray([max(float(lcb[i]), 0.0) /
                          max(float(downside[i]), vol_floor) for i in selected])
        raw /= raw.sum()
        n = len(selected)
        capped_pairs = []
        for a in range(n):
            for b in range(a + 1, n):
                ta, tb = self.pd.tags[selected[a]], self.pd.tags[selected[b]]
                key = tuple(sorted((ta, tb)))
                c = corr_map.get(key)
                if c is None:
                    c = weighted_corr(hist_rank[selected[a]], hist_rank[selected[b]], w)
                    corr_map[key] = c
                if not np.isfinite(c):
                    d.reason = "undefined_selected_correlation"
                    return d
                if c >= CORR_WEIGHT_CAP:
                    capped_pairs.append((a, b))
        constraints = [{"type": "eq", "fun": lambda x: float(x.sum() - 1.0)}]
        for a, b in capped_pairs:
            constraints.append({"type": "ineq",
                                "fun": lambda x, a=a, b=b:
                                float(PAIR_WEIGHT_CAP - x[a] - x[b])})
        result = minimize(lambda x: float(np.sum((x - raw) ** 2)),
                          np.full(n, 1.0 / n), method="SLSQP",
                          bounds=[(MIN_WEIGHT, MAX_WEIGHT)] * n,
                          constraints=constraints,
                          options={"ftol": 1e-12, "maxiter": 500})
        weights = np.asarray(result.x, float)
        feasible = (result.success and abs(float(weights.sum()) - 1) <= 1e-8
                    and np.all(weights >= MIN_WEIGHT - 1e-8)
                    and np.all(weights <= MAX_WEIGHT + 1e-8)
                    and all(weights[a] + weights[b] <= PAIR_WEIGHT_CAP + 1e-8
                            for a, b in capped_pairs))
        if not feasible:
            d.reason = "weight_constraints_infeasible"
            return d

        members = tuple(self.pd.tags[i] for i in selected)
        d.members = members
        d.weights = {tag: float(weights[k]) for k, tag in enumerate(members)}
        d.scores = {tag: float(lcb[i]) for tag, i in zip(members, selected)}
        d.correlations = corr_map
        cov = np.cov(hist_rank[selected], aweights=w, bias=True)
        if np.ndim(cov) == 0:
            cov = np.asarray([[float(cov)]])
        port_var = float(weights @ cov @ weights)
        if port_var > 0:
            marginal = cov @ weights
            d.risk_contributions = {
                tag: float(weights[k] * marginal[k] / port_var)
                for k, tag in enumerate(members)}
        caps = []
        for k, tag in enumerate(members):
            if abs(weights[k] - MIN_WEIGHT) < 1e-6:
                caps.append(f"{tag}:min10")
            if abs(weights[k] - MAX_WEIGHT) < 1e-6:
                caps.append(f"{tag}:max35")
        for a, b in capped_pairs:
            if abs(weights[a] + weights[b] - PAIR_WEIGHT_CAP) < 1e-6:
                caps.append(f"{members[a]}+{members[b]}:corr50")
        d.binding_caps = tuple(caps)
        middle = []
        for family in sorted(used_families):
            rows = [i for i in unique_ranked
                    if self.meta[self.pd.tags[i]]["setup"] == family]
            if rows:
                middle.append(self.pd.tags[rows[len(rows) // 2]])
        d.middle_members = tuple(middle)
        d.reason = "active"
        return d


def add_turnover(decisions: list[Decision]) -> None:
    prev_members: set[str] = set()
    prev_weights: dict[str, float] = {}
    for d in decisions:
        current = set(d.members)
        d.member_turnover = 1.0 - len(prev_members & current) / max(
            len(prev_members), len(current), 1)
        d.weight_turnover = 0.5 * sum(
            abs(d.weights.get(x, 0.0) - prev_weights.get(x, 0.0))
            for x in prev_members | current)
        prev_members, prev_weights = current, dict(d.weights)


def decisions_through(selector: Selector, first_cut: int, last_cut: int) -> list[Decision]:
    lo = int(np.searchsorted(selector.pd.boundaries, first_cut, side="left"))
    hi = int(np.searchsorted(selector.pd.boundaries, last_cut, side="left"))
    rows = [selector.select(j) for j in range(max(lo, MIN_HISTORY_WEEKS), hi)]
    add_turnover(rows)
    return rows


@dataclass(frozen=True)
class Opportunity:
    tag: str
    family: str
    tf: str
    stop: float
    target: float
    off: float
    exp: int
    order_t: int
    entry_t: int
    exit_t: int
    entry_k: int
    exit_k: int
    direction: int
    entry: float
    risk: float
    gross_geom_r: float
    gross_pre_cost_r: float
    execution_r: float
    swap_r: float
    base_r: float
    stress_r: float
    gate_r: float
    gate_pass: bool
    weight: float
    score: float
    decision_cut: int


@dataclass(frozen=True)
class GateEvent:
    t: int
    tag: str
    passed: bool
    gate_r: float


@dataclass
class Execution:
    admitted: list[Opportunity]
    gate_events: list[GateEvent]
    rejected_cell_busy: list[int]
    rejected_slots: list[int]
    rejected_risk: list[int]
    max_concurrent: int


def opportunities_from_decisions(b5: D.Bars, streams: dict, meta: dict,
                                 decisions: list[Decision], apply_gate: bool,
                                 control: bool = False) -> list[Opportunity]:
    out = []
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    for d in decisions:
        members = d.middle_members if control else d.members
        if len(members) < MIN_MEMBERS:
            continue
        weights = ({tag: 1.0 / len(members) for tag in members}
                   if control else d.weights)
        for tag in members:
            m = meta[tag]
            s = streams[m["stream"]]
            order_t = b5.t[s["order_k"]]
            entry_t = b5.t[s["entry_k"]]
            mask = ((order_t >= d.cut) & (order_t < d.end) & (entry_t < d.end))
            for q in np.flatnonzero(mask):
                k = int(s["entry_k"][q])
                p = int(m["plane"])
                xk = min(k + int(s["held"][q, p]), len(b5) - 1)
                risk = float(m["stop"] * s["atr"][q])
                gross_geom = float(s["gross"][q, p])
                swap_r = (E.rollover_nights(int(b5.t[k]), int(b5.t[xk]))
                          * E.SWAP_LONG / risk
                          if int(s["direction"][q]) > 0 else 0.0)
                base = gross_geom - fee / risk - swap_r
                execution_r = accounting_friction_r(b5, k, risk)
                stress = base - 0.5 * execution_r
                gross_pre = base + execution_r + swap_r
                gr = gate_friction_r(b5, k, risk)
                out.append(Opportunity(
                    tag, m["setup"], m["tf"], float(m["stop"]),
                    float(m["target"]), float(m["off"]), int(m["exp"]),
                    int(order_t[q]), int(entry_t[q]), int(b5.t[xk]), k, xk,
                    int(s["direction"][q]), float(s["entry"][q]), risk,
                    gross_geom, gross_pre, execution_r, swap_r, base, stress,
                    gr, (not apply_gate) or gr <= GATE_BASE_MAX + 1e-15,
                    float(weights[tag]), float(d.scores.get(tag, 0.0)), d.cut))
    return out


def execute_opportunities(opportunities: list[Opportunity],
                          apply_gate: bool) -> Execution:
    by_entry: dict[int, list[Opportunity]] = defaultdict(list)
    for o in opportunities:
        by_entry[o.entry_t].append(o)
    open_rows: list[Opportunity] = []
    cell_busy_until: dict[str, int] = {}
    admitted = []
    gate_events = []
    rejected_cell, rejected_slots, rejected_risk = [], [], []
    max_concurrent = 0
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    for t in sorted(by_entry):
        open_rows = [o for o in open_rows if o.exit_t > t]
        rows = sorted(by_entry[t], key=lambda o: (-o.score, o.tag,
                                                  o.order_t, o.exit_t))
        for o in rows:
            # A selected position locks its cell through the exit bar.  An
            # unselected hypothetical trade is never present in this state.
            if cell_busy_until.get(o.tag, -1) >= t:
                rejected_cell.append(t)
                continue
            if apply_gate:
                gate_events.append(GateEvent(t, o.tag, o.gate_pass, o.gate_r))
                if not o.gate_pass:
                    continue
            if len(open_rows) >= MAX_MEMBERS:
                rejected_slots.append(t)
                continue
            risk_charge = o.weight * (1.0 + fee / o.risk)
            open_charge = sum(x.weight * (1.0 + fee / x.risk) for x in open_rows)
            if open_charge + risk_charge > 1.0 + 1e-10:
                rejected_risk.append(t)
                continue
            admitted.append(o)
            cell_busy_until[o.tag] = o.exit_t
            if o.exit_t > t:
                open_rows.append(o)
                max_concurrent = max(max_concurrent, len(open_rows))
    return Execution(admitted, gate_events, rejected_cell, rejected_slots,
                     rejected_risk, max_concurrent)


@dataclass
class UnitPath:
    base_equity: np.ndarray
    stress_equity: np.ndarray


def unit_path(b5: D.Bars, rows: list[Opportunity]) -> UnitPath:
    open_base = np.zeros(len(b5), float)
    open_stress = np.zeros(len(b5), float)
    realised_base = np.zeros(len(b5), float)
    realised_stress = np.zeros(len(b5), float)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    for r in rows:
        k0, k1 = r.entry_k, min(r.exit_k, len(b5) - 1)
        realised_base[k1] += r.base_r * r.weight
        realised_stress[k1] += r.stress_r * r.weight
        if k1 <= k0:
            continue
        if r.direction > 0:
            p = b5.c[k0:k1] - r.entry - fee
        else:
            spreads = (np.full(k1 - k0, E.SPREAD_FALLBACK)
                       if b5.sp is None else
                       np.maximum(b5.sp[k0:k1], E.SPREAD_FALLBACK))
            p = r.entry - (b5.c[k0:k1] + spreads) - fee
        if r.direction > 0 and E.SWAP_LONG:
            rolls = []
            t0, t1 = int(b5.t[k0]), int(b5.t[k1 - 1])
            cur = t0 - t0 % DAY + E.ROLLOVER_H * 3600
            if cur < t0:
                cur += DAY
            while cur <= t1:
                rolls.append(cur)
                cur += DAY
            if rolls:
                nights = np.searchsorted(np.asarray(rolls, np.int64),
                                         b5.t[k0:k1], side="right")
                p = p - nights * E.SWAP_LONG
        p = p * r.weight / r.risk
        open_base[k0:k1] += p
        open_stress[k0:k1] += p - 0.5 * r.execution_r * r.weight
    return UnitPath(np.cumsum(realised_base) + open_base,
                    np.cumsum(realised_stress) + open_stress)


def profit_factor(xs: np.ndarray) -> float:
    pos = float(xs[xs > 0].sum())
    neg = float(-xs[xs < 0].sum())
    return math.inf if neg == 0 else pos / neg


def additive_dd(xs: np.ndarray) -> float:
    if not len(xs):
        return 0.0
    eq = np.cumsum(xs)
    peak = np.maximum.accumulate(np.r_[0.0, eq[:-1]])
    return float(np.min(eq - peak))


def loss_streak(xs: np.ndarray) -> int:
    best = cur = 0
    for x in xs:
        if x < 0:
            cur += 1
            best = max(best, cur)
        elif x > 0:
            cur = 0
    return best


def window_weeks(rows: list[Opportunity], start: int, end: int,
                 stress: bool) -> tuple[np.ndarray, np.ndarray]:
    first = weekly._week_boundary(start)
    if first > start:
        first -= WEEK
    n = max(1, int(math.ceil((end - first) / WEEK)))
    pnl = np.zeros(n, float)
    counts = np.zeros(n, np.int64)
    for r in rows:
        if start <= r.exit_t < end:
            j = int((r.exit_t - first) // WEEK)
            if 0 <= j < n:
                pnl[j] += (r.stress_r if stress else r.base_r) * r.weight
                counts[j] += 1
    return pnl, counts


def mtm_dd(b5: D.Bars, equity: np.ndarray, start: int, end: int) -> float:
    k0 = int(np.searchsorted(b5.t, start, side="left"))
    k1 = int(np.searchsorted(b5.t, end, side="left"))
    if k1 <= k0:
        return 0.0
    before = float(equity[k0 - 1]) if k0 else 0.0
    x = equity[k0:k1] - before
    peak = np.maximum.accumulate(np.r_[0.0, x[:-1]])
    return float(np.min(x - peak))


def _quartiles(xs: np.ndarray) -> tuple[float, float, float]:
    if not len(xs):
        return (float("nan"),) * 3
    q = np.percentile(xs, [25, 50, 75])
    return float(q[0]), float(q[1]), float(q[2])


def gate_breakdown(events: list[GateEvent], meta: dict,
                   start: int, end: int) -> dict:
    z = [e for e in events if start <= e.t < end and not e.passed]
    return {
        "family": dict(Counter(meta[e.tag]["setup"] for e in z)),
        "tf": dict(Counter(meta[e.tag]["tf"] for e in z)),
        "stop": dict(Counter(str(meta[e.tag]["stop"]) for e in z)),
        "entry": dict(Counter(f"o{meta[e.tag]['off']}e{meta[e.tag]['exp']}" for e in z)),
    }


def window_metrics(b5: D.Bars, path: UnitPath, execution: Execution,
                   meta: dict, start: int, end: int, stress: bool) -> dict:
    rows = sorted((r for r in execution.admitted if start <= r.exit_t < end),
                  key=lambda r: (r.exit_t, r.entry_t, r.tag))
    pnl = np.asarray([(r.stress_r if stress else r.base_r) * r.weight
                      for r in rows], float)
    weekly, active = window_weeks(execution.admitted, start, end, stress)
    months = defaultdict(float)
    for r, value in zip(rows, pnl):
        months[datetime.fromtimestamp(r.exit_t, timezone.utc).strftime("%Y-%m")] += value
    cursor = datetime.fromtimestamp(start, timezone.utc)
    while int(cursor.timestamp()) < end:
        months.setdefault(cursor.strftime("%Y-%m"), 0.0)
        y = cursor.year + (cursor.month == 12)
        m = 1 if cursor.month == 12 else cursor.month + 1
        cursor = datetime(y, m, 1, tzinfo=timezone.utc)
    gross = np.asarray([r.gross_pre_cost_r for r in rows], float)
    exec_cost = np.asarray([r.execution_r * (1.5 if stress else 1.0)
                            for r in rows], float)
    swaps = np.asarray([r.swap_r for r in rows], float)
    total_cost = exec_cost + swaps
    gross_mean = float(gross.mean()) if len(gross) else float("nan")
    cost_share = (float(total_cost.mean() / gross_mean)
                  if len(gross) and gross_mean > 0 else float("nan"))
    stops = np.asarray([r.risk for r in rows], float)
    base_fr = np.asarray([r.execution_r for r in rows], float)
    gate_fr = np.asarray([r.gate_r for r in rows], float)
    events = [e for e in execution.gate_events if start <= e.t < end]
    cancels = sum(not e.passed for e in events)
    curve = path.stress_equity if stress else path.base_equity
    return {
        "net_R": float(pnl.sum()),
        "gross_R_weighted": float(sum(r.gross_pre_cost_r * r.weight for r in rows)),
        "execution_cost_R_weighted": float(sum(
            r.execution_r * (1.5 if stress else 1.0) * r.weight for r in rows)),
        "swap_R_weighted": float(sum(r.swap_r * r.weight for r in rows)),
        "gross_edge_per_trade_R": gross_mean,
        "execution_cost_per_trade_R": float(exec_cost.mean()) if len(rows) else float("nan"),
        "swap_per_trade_R": float(swaps.mean()) if len(rows) else float("nan"),
        "net_per_trade_R": float(np.mean([r.stress_r if stress else r.base_r
                                           for r in rows])) if rows else float("nan"),
        "cost_share_of_gross": cost_share,
        "PF": profit_factor(pnl),
        "positive_week_pct": 100.0 * float(np.mean(weekly > 0)),
        "active_week_pct": 100.0 * float(np.mean(active > 0)),
        "zero_weeks": int(np.count_nonzero(np.isclose(weekly, 0.0, atol=1e-15))),
        "weeks": int(len(weekly)),
        "worst_week_R": float(weekly.min()),
        "worst_month_R": float(min(months.values())) if months else 0.0,
        "realised_DD_R": additive_dd(pnl),
        "MTM_DD_R": mtm_dd(b5, curve, start, end),
        "loss_streak": loss_streak(pnl),
        "trades": len(rows),
        "stop_q25_med_q75": _quartiles(stops),
        "accounting_friction_q25_med_q75": _quartiles(base_fr),
        "gate_friction_q25_med_q75": _quartiles(gate_fr),
        "stress_friction_q25_med_q75": _quartiles(1.5 * base_fr),
        "gate_considered": len(events),
        "gate_cancellations": cancels,
        "gate_cancellation_share": cancels / len(events) if events else 0.0,
        "gate_breakdown": gate_breakdown(execution.gate_events, meta, start, end),
    }


def max_concurrent_window(rows: list[Opportunity], start: int, end: int) -> int:
    events = []
    for r in rows:
        if r.entry_t < end and r.exit_t > start:
            events.append((max(start, r.entry_t), 1))
            events.append((min(end, r.exit_t), -1))
    cur = best = 0
    for _t, kind in sorted(events, key=lambda x: (x[0], x[1])):
        cur += kind
        best = max(best, cur)
    return best


def policy_audit(decisions: list[Decision], execution: Execution, meta: dict,
                 start: int, end: int) -> dict:
    ds = [d for d in decisions if start <= d.cut < end]
    corrs = []
    families = Counter()
    members = Counter()
    for d in ds:
        for tag in d.members:
            families[meta[tag]["setup"]] += 1
            members[tag] += 1
        for (a, b), c in d.correlations.items():
            if a in d.members and b in d.members:
                corrs.append(c)
    return {
        "decision_weeks": len(ds),
        "no_basket_weeks": sum(len(d.members) < MIN_MEMBERS for d in ds),
        "member_turnover": float(np.mean([d.member_turnover for d in ds])) if ds else 0.0,
        "weight_turnover": float(np.mean([d.weight_turnover for d in ds])) if ds else 0.0,
        "n_eff_min": min((d.n_eff for d in ds), default=0.0),
        "n_eff_max": max((d.n_eff for d in ds), default=0.0),
        "mean_corr": float(np.mean(corrs)) if corrs else float("nan"),
        "max_corr": max(corrs) if corrs else float("nan"),
        "max_concurrent": max_concurrent_window(execution.admitted, start, end),
        "cell_busy_rejects": sum(start <= t < end for t in execution.rejected_cell_busy),
        "slot_rejects": sum(start <= t < end for t in execution.rejected_slots),
        "risk_rejects": sum(start <= t < end for t in execution.rejected_risk),
        "family_member_weeks": dict(families),
        "top_members": members.most_common(12),
    }


def _dummy_opportunity(tag: str, entry_t: int, exit_t: int) -> Opportunity:
    return Opportunity(tag, "breakout", "M5", 1.0, 1.0, 0.0, 0,
                       entry_t, entry_t, exit_t, entry_t, exit_t, 1,
                       100.0, 10.0, 0.0, 0.1, 0.01, 0.0, 0.09, 0.085,
                       0.02, True, 0.2, 1.0, 0)


def audit_state_fidelity() -> dict:
    later = _dummy_opportunity("x", 20, 21)
    unselected = execute_opportunities([later], apply_gate=False)
    earlier = _dummy_opportunity("x", 10, 30)
    carried = execute_opportunities([earlier, later], apply_gate=False)
    return {
        "unselected_hypothetical_does_not_block":
            [x.entry_t for x in unselected.admitted] == [20],
        "actual_carried_position_blocks":
            [x.entry_t for x in carried.admitted] == [10]
            and carried.rejected_cell_busy == [20],
    }


def audit_spread_gate() -> dict:
    t = np.arange(4, dtype=np.int64) * 300
    base = np.full(4, 100.0)
    # risk=4: prior 0.09 passes; fill 0.50 would fail the old fill-bar gate.
    b = D.Bars(t, base, base + 1, base - 1, base, np.ones(4), 300,
               "SYNTH", np.asarray([0.09, 0.09, 0.50, 0.09]))
    risk = 4.0
    original_decision = gate_passes(b, 2, risk)
    original_accounting = accounting_friction_r(b, 2, risk)
    b_fill_mut = D.Bars(t, base, base + 1, base - 1, base, np.ones(4), 300,
                        "SYNTH", np.asarray([0.09, 0.09, 1.00, 0.09]))
    fill_mut_decision = gate_passes(b_fill_mut, 2, risk)
    fill_mut_accounting = accounting_friction_r(b_fill_mut, 2, risk)
    b_prior_mut = D.Bars(t, base, base + 1, base - 1, base, np.ones(4), 300,
                         "SYNTH", np.asarray([0.09, 0.50, 0.09, 0.09]))
    prior_mut_decision = gate_passes(b_prior_mut, 2, risk)
    return {
        "prior_pass_fill_would_fail_old_gate": original_decision,
        "sp_k_mutation_leaves_decision": original_decision == fill_mut_decision,
        "sp_k_mutation_changes_accounting": original_accounting != fill_mut_accounting,
        "sp_k_minus_1_mutation_flips_decision": original_decision != prior_mut_decision,
        "passed": (original_decision and original_decision == fill_mut_decision
                   and original_accounting != fill_mut_accounting
                   and original_decision != prior_mut_decision),
    }


def audit_truncation(pd: PolicyData, meta: dict) -> dict:
    wanted = int(datetime(2025, 1, 10, 22, 15, tzinfo=timezone.utc).timestamp())
    j = int(np.searchsorted(pd.boundaries, wanted, side="left"))
    full = Selector(pd, meta, "gate").select(j)
    truncated = Selector(pd.truncated(j), meta, "gate").select(j)
    mutated = PolicyData(pd.tags, pd.tag_index, pd.boundaries.copy(),
                         pd.base.copy(), pd.stress.copy(), pd.signatures,
                         pd.candidate_gate_cancels.copy())
    if j < mutated.base.shape[1]:
        mutated.base[:, j:] += 1e6
        mutated.stress[:, j:] -= 1e6
    future = Selector(mutated, meta, "gate").select(j)
    same_weights = lambda a, b: (set(a.weights) == set(b.weights)
        and all(abs(a.weights[k] - b.weights[k]) < 1e-11 for k in a.weights))
    return {
        "cut": full.cut,
        "truncated_members": full.members == truncated.members,
        "truncated_weights": same_weights(full, truncated),
        "future_mutation_members": full.members == future.members,
        "future_mutation_weights": same_weights(full, future),
        "multiplier": "NOT_PERMITTED_BEFORE_UNIT_RISK_PASS",
        "passed": (full.members == truncated.members and same_weights(full, truncated)
                   and full.members == future.members and same_weights(full, future)),
    }


def run_audits(b5: D.Bars, pd_gate: PolicyData, meta: dict,
               reproduction_mismatches: list[str]) -> dict:
    spread = audit_spread_gate()
    state = audit_state_fidelity()
    trunc = audit_truncation(pd_gate, meta)
    expected = _cache_stamp(b5)
    mutated = dict(expected)
    mutated["gate_base_max"] = expected["gate_base_max"] + 1e-6
    cache_hash = _stamp_matches(expected, expected) and not _stamp_matches(mutated, expected)
    result = {
        "reproduction": len(reproduction_mismatches) == 0,
        "reproduction_mismatches": reproduction_mismatches[:20],
        "spread_gate": spread,
        "state_fidelity": state,
        "truncation_mutation": trunc,
        "cache_full_hash_sensitive": cache_hash,
    }
    result["passed_before_mtf_suite"] = (
        result["reproduction"] and spread["passed"]
        and all(state.values()) and trunc["passed"] and cache_hash)
    return result


def format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.8f}" if math.isfinite(value) else "NOT_ASSESSED"
    return str(value)


def print_decisions(label: str, decisions: list[Decision]) -> None:
    print(f"{label}_WEEKEND_DECISIONS_BEGIN")
    for d in decisions:
        weights = ",".join(f"{m}:{d.weights[m]:.5f}" for m in d.members)
        scores = ",".join(f"{m}:{d.scores[m]:.6f}" for m in d.members)
        corrs = ",".join(f"{a}|{b}:{c:.4f}" for (a, b), c in sorted(
            d.correlations.items()) if a in d.members and b in d.members)
        print(f"policy={label} week={utc(d.cut)} n_eff={d.n_eff:.6f} "
              f"eligible={d.eligible_count} members={len(d.members)} "
              f"member_turnover={d.member_turnover:.6f} "
              f"weight_turnover={d.weight_turnover:.6f} reason={d.reason} "
              f"weights=[{weights}] scores=[{scores}] correlations=[{corrs}] "
              f"risk_contributions={d.risk_contributions} caps={d.binding_caps}")
    print(f"{label}_WEEKEND_DECISIONS_END")


def print_metrics(prefix: str, metrics: dict) -> None:
    print(prefix + " " + " ".join(f"{k}={format_value(v)}"
                                    for k, v in metrics.items()))


def print_trade_ledger(label: str, rows: list[Opportunity]) -> None:
    print(f"{label}_PER_TRADE_COST_LEDGER_BEGIN")
    print("policy,tag,entry_utc,exit_utc,weight,stop,gate_friction_R,"
          "accounting_execution_R,swap_R,gross_pre_cost_R,base_net_R,stress_net_R")
    for r in rows:
        print(f"{label},{r.tag},{utc(r.entry_t)},{utc(r.exit_t)},"
              f"{r.weight:.10f},{r.risk:.10f},{r.gate_r:.10f},"
              f"{r.execution_r:.10f},{r.swap_r:.10f},"
              f"{r.gross_pre_cost_r:.10f},{r.base_r:.10f},{r.stress_r:.10f}")
    print(f"{label}_PER_TRADE_COST_LEDGER_END")


def run() -> int:
    print("AMENDMENT_24_EXECUTION_FRICTION_GATE")
    print("research_only=true mt5_connection=false order_sending=false")
    print(f"gate_base_max={GATE_BASE_MAX:.10f} gate_stress_max={1.5*GATE_BASE_MAX:.10f} "
          "gate_spread_source=last_fully_closed_M5_bar_k_minus_1 "
          "accounting_spread_source=fill_bar_k")
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    streams, meta, cache_built = load_raw_cache(b5)
    print(f"cache_full_hash=PASS built_this_run={cache_built} "
          f"data_sha256={canonical.bars_digest(b5)} streams={len(streams)} cells={len(meta)}")

    # The old cache is used only for the required continuous-cell reproduction
    # audit.  It is never the forward execution source.
    old_uni, _old_meta = old_audit.load_universe(b5)
    print("building paired A23 candidate history and reproduction audit...")
    pd_a23, reproduction_mismatches = build_policy_data(
        b5, streams, meta, apply_gate=False, old_uni=old_uni)
    print("building Amendment24 gated candidate history...")
    pd_gate, _ = build_policy_data(b5, streams, meta, apply_gate=True)

    audits = run_audits(b5, pd_gate, meta, reproduction_mismatches)
    print(f"SECTION10_AUDITS_PRE_MTF={audits}")
    if not audits["passed_before_mtf_suite"]:
        print("SECTION11_VERDICT=FAIL_AUDIT result_not_run=true")
        return 2
    import test_mtf_engine as mtf_tests
    mtf_rc = mtf_tests.main()
    print(f"SECTION10_EXISTING_MTF_SUITE return_code={mtf_rc} "
          f"passes={len(mtf_tests.PASSES)} failures={len(mtf_tests.FAILS)}")
    if mtf_rc != 0:
        print("SECTION11_VERDICT=FAIL_AUDIT result_not_run=true")
        return 2
    print("SECTION10_AUDITS=ALL_PASS result_may_run=true")

    first_policy = int(pd_gate.boundaries[MIN_HISTORY_WEEKS])
    gate_decisions = decisions_through(Selector(pd_gate, meta, "gate"),
                                       first_policy, last)
    a23_decisions = decisions_through(Selector(pd_a23, meta, "a23"),
                                      first_policy, last)
    print_decisions("AMENDMENT24", gate_decisions)
    print_decisions("PAIRED_A23_NEW_ENGINE", a23_decisions)

    gate_exe = execute_opportunities(
        opportunities_from_decisions(b5, streams, meta, gate_decisions, True), True)
    gate_path = unit_path(b5, gate_exe.admitted)
    control_exe = execute_opportunities(
        opportunities_from_decisions(b5, streams, meta, gate_decisions, True,
                                     control=True), True)
    control_path = unit_path(b5, control_exe.admitted)
    a23_exe = execute_opportunities(
        opportunities_from_decisions(b5, streams, meta, a23_decisions, False), False)
    a23_path = unit_path(b5, a23_exe.admitted)

    windows = (
        ("44_MONTH_INFORMED_BY_AMENDMENT23_NOT_BLIND", REPORT_START, REPORT_SPLIT),
        ("TRAILING_12_MONTH_ALREADY_SEEN", REPORT_SPLIT, last),
        ("FULL_DEVELOPMENT_PERIOD_NOT_BLIND", REPORT_START, last),
    )
    primary_results: dict[str, dict[str, dict]] = {}
    baseline_results: dict[str, dict[str, dict]] = {}
    print("UNIT_RISK_RESULTS_FIRST")
    for name, start, end in windows:
        primary_results[name] = {}
        for cost_name, stress in (("BASE", False), ("COST_1P5X", True)):
            m = window_metrics(b5, gate_path, gate_exe, meta, start, end, stress)
            primary_results[name][cost_name] = m
            print_metrics(f"UNIT_AMENDMENT24 {name} {cost_name} "
                          f"start={utc(start)} end={utc(end)}", m)
        print(f"AMENDMENT24_POLICY_AUDIT {name} "
              f"{policy_audit(gate_decisions, gate_exe, meta, start, end)}")

    print("PAIRED_A23_BASELINE_ON_NEW_STATE_ENGINE")
    for name, start, end in windows:
        baseline_results[name] = {}
        for cost_name, stress in (("BASE", False), ("COST_1P5X", True)):
            m = window_metrics(b5, a23_path, a23_exe, meta, start, end, stress)
            baseline_results[name][cost_name] = m
            print_metrics(f"PAIRED_A23 {name} {cost_name} "
                          f"start={utc(start)} end={utc(end)}", m)
            p = primary_results[name][cost_name]
            diff = {k: p[k] - m[k] for k in
                    ("net_R", "gross_R_weighted", "execution_cost_R_weighted",
                     "trades", "zero_weeks", "MTM_DD_R")}
            print(f"PAIRED_WEEKLY_DIFFERENCE A24_MINUS_A23 {name} {cost_name} {diff}")
        print(f"PAIRED_A23_POLICY_AUDIT {name} "
              f"{policy_audit(a23_decisions, a23_exe, meta, start, end)}")

    print("SAME_WEEK_FAMILY_MIDDLE_CONTROL")
    for name, start, end in windows:
        for cost_name, stress in (("BASE", False), ("COST_1P5X", True)):
            m = window_metrics(b5, control_path, control_exe, meta, start, end, stress)
            print_metrics(f"FAMILY_MIDDLE_CONTROL {name} {cost_name}", m)

    weekly_gate = Counter()
    for e in gate_exe.gate_events:
        if not e.passed:
            cut = weekly._week_boundary(e.t)
            if cut > e.t:
                cut -= WEEK
            weekly_gate[utc(cut)] += 1
    print(f"GATE_CANCELLATIONS_BY_WEEK={dict(sorted(weekly_gate.items()))}")
    print_trade_ledger("AMENDMENT24", gate_exe.admitted)
    print_trade_ledger("PAIRED_A23", a23_exe.admitted)

    required_names = (windows[0][0], windows[1][0])
    forward = [d for d in gate_decisions if REPORT_START <= d.cut < last]
    no_basket = sum(len(d.members) < MIN_MEMBERS for d in forward)
    unit_pass = (
        all(primary_results[n][c]["net_R"] > 0
            for n in required_names for c in ("BASE", "COST_1P5X"))
        and no_basket <= len(forward) / 2
        and all(primary_results[n]["BASE"]["active_week_pct"] >= 50.0
                for n in required_names)
    )
    print(f"SECTION11_UNIT_GATE unit_pass={unit_pass} "
          f"forward_weeks={len(forward)} no_basket_weeks={no_basket} "
          f"active_week_44={primary_results[required_names[0]]['BASE']['active_week_pct']:.6f} "
          f"active_week_12={primary_results[required_names[1]]['BASE']['active_week_pct']:.6f}")
    if not unit_pass:
        print("DD_SIZING=NOT_RUN reason=unit_risk_failed_section11")
        print("FINANCE_DCA=NOT_RUN reason=unit_risk_failed_section11")
        print("DD_SCENARIOS_30_35_37P5_40_45_50=NOT_RUN reason=unit_risk_failed_section11")
        print("SECTION11_VERDICT=FAIL_FOR_PROMOTION unit_risk_pass=false")
        return 1

    print("SECTION11_UNIT_VERDICT=PASS_DEVELOPMENT_NOT_BLIND")
    print("DD_SIZING_REQUIRED=true")
    print("SECTION11_VERDICT=INCOMPLETE_UNTIL_CONDITIONAL_SIZING")
    return 3


if __name__ == "__main__":
    raise SystemExit(run())
