"""Amendment 23 causal multi-tool basket research engine.

Research only.  This module contains no MetaTrader connection and no order
sending code.  It consumes the full-hash-verified Amendment 14 universe cache,
selects/reweights a basket only at the frozen weekend boundary, and assigns a
trade return to the calendar week in which the trade exits.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import argparse
import hashlib
import math
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolution_portfolio_audit as audit
import historical_regime_walkforward as hist
import mtf_engine as E
import weekly_evolution_grid as weekly


DAY = 86_400
WEEK = 7 * DAY
HALF_LIFE_WEEKS = 3.0
DECAY = 2.0 ** (-1.0 / HALF_LIFE_WEEKS)
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
REPORT_START = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
REPORT_SPLIT = int(datetime(2025, 9, 21, tzinfo=timezone.utc).timestamp())


def utc(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def profit_factor(xs: Iterable[float]) -> float:
    a = np.asarray(list(xs), float)
    gains = float(a[a > 0].sum())
    losses = float(-a[a < 0].sum())
    return math.inf if losses == 0.0 else gains / losses


def additive_drawdown(xs: Iterable[float]) -> float:
    a = np.asarray(list(xs), float)
    if not len(a):
        return 0.0
    eq = np.cumsum(a)
    peak = np.maximum.accumulate(np.r_[0.0, eq[:-1]])
    return float(np.min(eq - peak))


def max_loss_streak(xs: Iterable[float]) -> int:
    best = cur = 0
    for x in xs:
        if x < 0:
            cur += 1
            best = max(best, cur)
        elif x > 0:
            cur = 0
    return best


def weekend_boundaries(first: int, last: int) -> np.ndarray:
    """Friday 22:15 UTC boundaries covering the complete data interval."""
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


@dataclass
class WeeklyData:
    tags: tuple[str, ...]
    tag_index: dict[str, int]
    boundaries: np.ndarray
    base: np.ndarray
    stress: np.ndarray

    @classmethod
    def build(cls, b5, uni: dict) -> "WeeklyData":
        tags = tuple(sorted(uni))
        bounds = weekend_boundaries(int(b5.t[0]), int(b5.t[-1] + b5.step))
        nweek = len(bounds) - 1
        base = np.zeros((len(tags), nweek), np.float64)
        stress = np.zeros_like(base)
        for i, tag in enumerate(tags):
            a = uni[tag]
            bins = np.searchsorted(bounds, a["t_out"], side="right") - 1
            valid = (bins >= 0) & (bins < nweek)
            if not np.any(valid):
                continue
            rows = np.flatnonzero(valid)
            np.add.at(base[i], bins[valid], a["net"][valid])
            sigk = a["sigk"][valid].astype(np.int64)
            if b5.sp is None:
                spread = np.full(len(sigk), E.SPREAD_FALLBACK, float)
            else:
                spread = np.maximum(b5.sp[sigk], E.SPREAD_FALLBACK)
            execution = spread + E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
            stressed = a["net"][valid] - 0.5 * execution / a["risk"][valid]
            np.add.at(stress[i], bins[valid], stressed)
        return cls(tags, {tag: i for i, tag in enumerate(tags)}, bounds,
                   base, stress)

    def truncated(self, cut_index: int) -> "WeeklyData":
        """An actual future-column truncation used by the look-ahead audit."""
        return WeeklyData(self.tags, self.tag_index,
                          self.boundaries[:cut_index + 1].copy(),
                          self.base[:, :cut_index].copy(),
                          self.stress[:, :cut_index].copy())


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
    dx = x - mx
    dy = y - my
    vx = float(np.dot(w, dx * dx) / sw)
    vy = float(np.dot(w, dy * dy) / sw)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return float(np.dot(w, dx * dy) / sw / math.sqrt(vx * vy))


def duplicate_signature(a: dict, cut: int) -> tuple[bytes, bytes, bytes]:
    """Exact realised order signature, using only resolved trades before cut."""
    m = a["t_out"] < cut
    return (a["t_order"][m].tobytes(), a["t_in"][m].tobytes(),
            a["direction"][m].tobytes())


class Selector:
    def __init__(self, weekly_data: WeeklyData, uni: dict, meta: dict):
        self.wd = weekly_data
        self.uni = uni
        self.meta = meta

    def _moments(self, j: int):
        """Exact exponentially weighted zero-inclusive moments before cut j."""
        ages = np.arange(j - 1, -1, -1, dtype=float)
        w = DECAY ** ages
        sw = float(w.sum())
        sw2 = float(np.dot(w, w))
        x = self.wd.base[:, :j]
        z = self.wd.stress[:, :j]
        mu = x @ w / sw
        mu2 = (x * x) @ w / sw
        sd = np.sqrt(np.maximum(mu2 - mu * mu, 0.0))
        stress_mu = z @ w / sw
        downside = np.sqrt((np.minimum(x, 0.0) ** 2) @ w / sw)
        nonzero = np.count_nonzero(x, axis=1)
        n_eff = sw * sw / sw2
        lcb = mu - LCB_COEF * sd / math.sqrt(n_eff)
        return w, mu, sd, stress_mu, downside, nonzero, n_eff, lcb

    def select(self, j: int) -> Decision:
        if j < MIN_HISTORY_WEEKS or j >= len(self.wd.boundaries):
            cut = int(self.wd.boundaries[min(j, len(self.wd.boundaries) - 1)])
            return Decision(cut, cut + WEEK, reason="insufficient_history")
        cut = int(self.wd.boundaries[j])
        end = cut + WEEK
        w, mu, sd, stress_mu, downside, nonzero, n_eff, lcb = self._moments(j)
        finite = np.isfinite(sd) & np.isfinite(lcb) & np.isfinite(downside)
        eligible_mask = (finite & (nonzero >= MIN_NONZERO_WEEKS)
                         & (lcb > 0.0) & (stress_mu > 0.0))
        eligible_idx = np.flatnonzero(eligible_mask)
        d = Decision(cut, end, n_eff=n_eff, eligible_count=len(eligible_idx))
        if not len(eligible_idx):
            d.reason = "no_eligible_cells"
            return d

        positive_down = downside[eligible_idx][downside[eligible_idx] > 0]
        if not len(positive_down):
            d.reason = "undefined_downside_floor"
            return d
        vol_floor = float(np.percentile(positive_down, 25))
        ranked = sorted(eligible_idx,
                        key=lambda i: (-float(lcb[i]), self.wd.tags[i]))
        # Collapse exact realised-order duplicates *before* applying family or
        # correlation constraints.  Otherwise a lower-ranked parameter copy
        # could re-enter after the canonical copy was rejected for a different
        # constraint, giving that realised strategy extra lottery tickets.
        unique_ranked: list[int] = []
        all_signatures: set[tuple[bytes, bytes, bytes]] = set()
        duplicate_collapsed = 0
        for i in ranked:
            sig = duplicate_signature(self.uni[self.wd.tags[i]], cut)
            if sig in all_signatures:
                duplicate_collapsed += 1
                continue
            all_signatures.add(sig)
            unique_ranked.append(i)

        selected: list[int] = []
        used_families: set[str] = set()
        corr_map: dict[tuple[str, str], float] = {}
        hist = self.wd.base[:, :j]

        for i in unique_ranked:
            tag = self.wd.tags[i]
            family = self.meta[tag]["setup"]
            if family in used_families:
                continue
            correlations = []
            assessed = True
            for k in selected:
                c = weighted_corr(hist[i], hist[k], w)
                if not np.isfinite(c):
                    assessed = False
                    break
                correlations.append((k, c))
            if not assessed or any(c > CORR_ADMISSION + 1e-12
                                   for _k, c in correlations):
                continue
            trial = selected + [i]
            # The predeclared cost gate is an equal-weight basket gate at the
            # admission stage.  All individually eligible members are already
            # positive, but keeping this explicit audits the frozen rule.
            if float(np.mean(stress_mu[trial])) <= 0.0:
                continue
            selected.append(i)
            used_families.add(family)
            for k, c in correlations:
                corr_map[tuple(sorted((tag, self.wd.tags[k])))] = c
            if len(selected) == MAX_MEMBERS:
                break

        d.duplicate_collapsed = duplicate_collapsed
        if len(selected) < MIN_MEMBERS:
            d.reason = f"fewer_than_{MIN_MEMBERS}_members"
            return d

        raw = np.asarray([max(float(lcb[i]), 0.0) /
                          max(float(downside[i]), vol_floor)
                          for i in selected], float)
        raw /= raw.sum()
        n = len(selected)
        pairs = []
        for a in range(n):
            for b in range(a + 1, n):
                ta, tb = self.wd.tags[selected[a]], self.wd.tags[selected[b]]
                c = corr_map.get(tuple(sorted((ta, tb))))
                if c is None:
                    c = weighted_corr(hist[selected[a]], hist[selected[b]], w)
                    corr_map[tuple(sorted((ta, tb)))] = c
                if not np.isfinite(c):
                    d.reason = "undefined_selected_correlation"
                    return d
                if c >= CORR_WEIGHT_CAP:
                    pairs.append((a, b))
        constraints = [{"type": "eq", "fun": lambda x: float(x.sum() - 1.0)}]
        for a, b in pairs:
            constraints.append({"type": "ineq",
                                "fun": lambda x, a=a, b=b:
                                float(PAIR_WEIGHT_CAP - x[a] - x[b])})
        result = minimize(lambda x: float(np.sum((x - raw) ** 2)),
                          np.full(n, 1.0 / n), method="SLSQP",
                          bounds=[(MIN_WEIGHT, MAX_WEIGHT)] * n,
                          constraints=constraints,
                          options={"ftol": 1e-12, "maxiter": 500})
        x = np.asarray(result.x, float)
        feasible = (result.success and abs(float(x.sum()) - 1.0) <= 1e-8
                    and np.all(x >= MIN_WEIGHT - 1e-8)
                    and np.all(x <= MAX_WEIGHT + 1e-8)
                    and all(x[a] + x[b] <= PAIR_WEIGHT_CAP + 1e-8
                            for a, b in pairs))
        if not feasible:
            d.reason = "weight_constraints_infeasible"
            return d

        members = tuple(self.wd.tags[i] for i in selected)
        weights = {tag: float(x[k]) for k, tag in enumerate(members)}
        scores = {tag: float(lcb[i]) for tag, i in zip(members, selected)}
        cov = np.cov(hist[selected], aweights=w, bias=True)
        if np.ndim(cov) == 0:
            cov = np.asarray([[float(cov)]])
        port_var = float(x @ cov @ x)
        rc = {}
        if port_var > 0:
            marginal = cov @ x
            rc = {tag: float(x[k] * marginal[k] / port_var)
                  for k, tag in enumerate(members)}
        binding = []
        for k, tag in enumerate(members):
            if abs(x[k] - MIN_WEIGHT) < 1e-6:
                binding.append(f"{tag}:min10")
            if abs(x[k] - MAX_WEIGHT) < 1e-6:
                binding.append(f"{tag}:max35")
        for a, b in pairs:
            if abs(x[a] + x[b] - PAIR_WEIGHT_CAP) < 1e-6:
                binding.append(f"{members[a]}+{members[b]}:corr50")

        middle = []
        for family in sorted(used_families):
            family_rows = [i for i in unique_ranked
                           if self.meta[self.wd.tags[i]]["setup"] == family]
            if family_rows:
                middle.append(self.wd.tags[family_rows[len(family_rows) // 2]])
        d.members = members
        d.weights = weights
        d.scores = scores
        d.correlations = corr_map
        d.risk_contributions = rc
        d.middle_members = tuple(middle)
        d.binding_caps = tuple(binding)
        d.reason = "active"
        return d


def add_turnover(decisions: list[Decision]) -> None:
    prev_members: set[str] = set()
    prev_weights: dict[str, float] = {}
    for d in decisions:
        current = set(d.members)
        denom = max(len(prev_members), len(current), 1)
        d.member_turnover = 1.0 - len(prev_members & current) / denom
        names = prev_members | current
        d.weight_turnover = 0.5 * sum(abs(d.weights.get(x, 0.0)
                                               - prev_weights.get(x, 0.0))
                                      for x in names)
        prev_members = current
        prev_weights = dict(d.weights)


@dataclass(frozen=True)
class Order:
    tag: str
    order_t: int
    entry_t: int
    exit_t: int
    entry_k: int
    exit_k: int
    direction: int
    entry: float
    risk: float
    net_r: float
    stress_r: float
    weight: float
    risk_charge: float
    score: float
    decision_cut: int


@dataclass
class Execution:
    admitted: list[Order]
    rejected_slot_times: list[int]
    rejected_risk_times: list[int]
    max_concurrent: int

    @property
    def rejected_slots(self) -> int:
        return len(self.rejected_slot_times)

    @property
    def rejected_risk(self) -> int:
        return len(self.rejected_risk_times)


def orders_from_decisions(b5, uni: dict, decisions: list[Decision],
                          control: bool = False) -> list[Order]:
    out: list[Order] = []
    for d in decisions:
        members = d.middle_members if control else d.members
        if len(members) < MIN_MEMBERS:
            continue
        weights = ({tag: 1.0 / len(members) for tag in members}
                   if control else d.weights)
        for tag in members:
            a = uni[tag]
            # A selected member may act only on an order born in this frozen
            # week.  A pending order not filled by end is cancelled.
            m = ((a["t_order"] >= d.cut) & (a["t_order"] < d.end)
                 & (a["t_in"] < d.end))
            for q in np.flatnonzero(m):
                k = int(a["sigk"][q])
                spread = E.spread_at(b5, k)
                execution = spread + E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
                stress_r = float(a["net"][q]
                                 - 0.5 * execution / a["risk"][q])
                out.append(Order(
                    tag, int(a["t_order"][q]), int(a["t_in"][q]),
                    int(a["t_out"][q]), k, int(a["exit_k"][q]),
                    int(a["direction"][q]), float(a["entry"][q]),
                    float(a["risk"][q]), float(a["net"][q]), stress_r,
                    float(weights[tag]),
                    float(weights[tag]) * (1.0 +
                        (E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL)
                        / float(a["risk"][q])),
                    float(d.scores.get(tag, 0.0)), d.cut))
    return out


def admit_orders(orders: list[Order]) -> Execution:
    """Apply the five-position and gross unit-risk caps causally at entry."""
    by_entry: dict[int, list[Order]] = defaultdict(list)
    for o in orders:
        by_entry[o.entry_t].append(o)
    open_rows: list[Order] = []
    admitted: list[Order] = []
    rejected_slots: list[int] = []
    rejected_risk: list[int] = []
    max_concurrent = 0
    for t in sorted(by_entry):
        # Exit before entry when timestamps match.
        open_rows = [o for o in open_rows if o.exit_t > t]
        rows = sorted(by_entry[t], key=lambda o: (-o.score, o.tag,
                                                  o.order_t, o.exit_t))
        for o in rows:
            if len(open_rows) >= MAX_MEMBERS:
                rejected_slots.append(t)
                continue
            # Charge the geometric stop plus round-trip exit costs.  Keeping
            # the initial charge while a trade is open is conservative versus
            # releasing budget from favourable movement.
            if (sum(x.risk_charge for x in open_rows) + o.risk_charge
                    > 1.0 + 1e-10):
                rejected_risk.append(t)
                continue
            admitted.append(o)
            if o.exit_t > t:
                open_rows.append(o)
                max_concurrent = max(max_concurrent, len(open_rows))
    return Execution(admitted, rejected_slots, rejected_risk, max_concurrent)


@dataclass
class UnitPath:
    base_equity: np.ndarray
    stress_equity: np.ndarray
    base_week: np.ndarray
    stress_week: np.ndarray


def unit_path(b5, wd: WeeklyData, rows: list[Order]) -> UnitPath:
    open_base = np.zeros(len(b5), float)
    open_stress = np.zeros(len(b5), float)
    realised_base = np.zeros(len(b5), float)
    realised_stress = np.zeros(len(b5), float)
    base_week = np.zeros(len(wd.boundaries) - 1, float)
    stress_week = np.zeros_like(base_week)
    for r in rows:
        k0 = r.entry_k
        k1 = min(r.exit_k, len(b5) - 1)
        realised_base[k1] += r.net_r * r.weight
        realised_stress[k1] += r.stress_r * r.weight
        wb = int(np.searchsorted(wd.boundaries, r.exit_t, side="right") - 1)
        if 0 <= wb < len(base_week):
            # Claude clarification A: resolution/exit week owns the net R.
            base_week[wb] += r.net_r * r.weight
            stress_week[wb] += r.stress_r * r.weight
        if k1 <= k0:
            continue
        fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
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
        extra = (r.net_r - r.stress_r) * r.weight
        open_base[k0:k1] += p
        open_stress[k0:k1] += p - extra
    return UnitPath(np.cumsum(realised_base) + open_base,
                    np.cumsum(realised_stress) + open_stress,
                    base_week, stress_week)


def causal_multiplier_from_path(b5, equity: np.ndarray, cut: int,
                                target_dd: float = 0.375) -> float:
    """Past-only bisection seed used by the audit and sizing gate.

    The input is the nested unit-risk MTM path.  It is sliced before ``cut``
    and to the trailing 52 completed weeks.  The production sizing stage may
    use this only after the unit-risk edge passes.
    """
    lo_t = cut - 52 * WEEK
    k0 = int(np.searchsorted(b5.t, lo_t, side="left"))
    k1 = int(np.searchsorted(b5.t, cut, side="left"))
    if k1 - k0 < 2:
        return 0.0
    segment = equity[k0:k1].copy()
    before = float(equity[k0 - 1]) if k0 else 0.0
    segment -= before

    def dd_pct(mult: float) -> float:
        curve = 100.0 + mult * segment
        if np.any(curve <= 0):
            return 1.0
        peak = np.maximum.accumulate(np.r_[100.0, curve[:-1]])
        return float(np.max((peak - curve) / peak))

    low, high = 0.0, 1.0
    while high < 4096.0 and dd_pct(high) <= target_dd:
        high *= 2.0
    for _ in range(64):
        mid = (low + high) / 2.0
        if dd_pct(mid) <= target_dd:
            low = mid
        else:
            high = mid
    return low


def mtm_dd_for_window(b5, equity: np.ndarray, start: int, end: int) -> float:
    k0 = int(np.searchsorted(b5.t, start, side="left"))
    k1 = int(np.searchsorted(b5.t, end, side="left"))
    if k1 <= k0:
        return 0.0
    before = float(equity[k0 - 1]) if k0 else 0.0
    x = equity[k0:k1] - before
    peak = np.maximum.accumulate(np.r_[0.0, x[:-1]])
    return float(np.min(x - peak))


def window_week_values(rows: list[Order], start: int, end: int,
                       stress: bool = False) -> np.ndarray:
    first = weekly._week_boundary(start)
    if first > start:
        first -= WEEK
    n = max(1, int(math.ceil((end - first) / WEEK)))
    values = np.zeros(n, float)
    for r in rows:
        if start <= r.exit_t < end:
            j = int((r.exit_t - first) // WEEK)
            if 0 <= j < n:
                values[j] += (r.stress_r if stress else r.net_r) * r.weight
    return values


def window_metrics(b5, path: UnitPath, rows: list[Order], start: int, end: int,
                   stress: bool = False) -> dict:
    z = sorted((r for r in rows if start <= r.exit_t < end),
               key=lambda r: (r.exit_t, r.entry_t, r.tag))
    pnl = np.asarray([(r.stress_r if stress else r.net_r) * r.weight
                      for r in z], float)
    weeks = window_week_values(rows, start, end, stress)
    months = defaultdict(float)
    for r, p in zip(z, pnl):
        months[datetime.fromtimestamp(r.exit_t, timezone.utc).strftime("%Y-%m")] += p
    # Insert zero calendar months, so idle time cannot disappear.
    cursor = datetime.fromtimestamp(start, timezone.utc)
    while int(cursor.timestamp()) < end:
        months.setdefault(cursor.strftime("%Y-%m"), 0.0)
        y = cursor.year + (cursor.month == 12)
        m = 1 if cursor.month == 12 else cursor.month + 1
        cursor = datetime(y, m, 1, tzinfo=timezone.utc)
    curve = path.stress_equity if stress else path.base_equity
    return {
        "net_R": float(pnl.sum()),
        "PF": profit_factor(pnl),
        "positive_week_pct": 100.0 * float(np.mean(weeks > 0)),
        "zero_weeks": int(np.count_nonzero(np.isclose(weeks, 0.0, atol=1e-15))),
        "weeks": int(len(weeks)),
        "worst_week_R": float(weeks.min()) if len(weeks) else 0.0,
        "worst_month_R": float(min(months.values())) if months else 0.0,
        "realised_DD_R": additive_drawdown(pnl),
        "MTM_DD_R": mtm_dd_for_window(b5, curve, start, end),
        "loss_streak": max_loss_streak(pnl),
        "trades": int(len(z)),
    }


def max_concurrent_window(rows: list[Order], start: int, end: int) -> int:
    events = []
    for r in rows:
        if r.entry_t < end and r.exit_t > start:
            events.append((max(r.entry_t, start), 1))
            events.append((min(r.exit_t, end), -1))
    current = best = 0
    for _t, kind in sorted(events, key=lambda z: (z[0], z[1])):
        current += kind
        best = max(best, current)
    return best


def window_policy_audit(decisions: list[Decision], execution: Execution,
                        meta: dict, start: int, end: int) -> dict:
    ds = [d for d in decisions if start <= d.cut < end]
    corrs = []
    families = Counter()
    members = Counter()
    for d in ds:
        for tag in d.members:
            families[meta[tag]["setup"]] += 1
            members[tag] += 1
        for (a, b), value in d.correlations.items():
            if a in d.members and b in d.members:
                corrs.append(value)
    return {
        "decision_weeks": len(ds),
        "no_basket_weeks": sum(len(d.members) < MIN_MEMBERS for d in ds),
        "avg_member_turnover": (float(np.mean([d.member_turnover for d in ds]))
                                if ds else 0.0),
        "avg_weight_turnover": (float(np.mean([d.weight_turnover for d in ds]))
                                if ds else 0.0),
        "max_concurrent": max_concurrent_window(execution.admitted, start, end),
        "rejected_slots": sum(start <= t < end
                              for t in execution.rejected_slot_times),
        "rejected_risk": sum(start <= t < end
                             for t in execution.rejected_risk_times),
        "mean_selected_corr": float(np.mean(corrs)) if corrs else float("nan"),
        "max_selected_corr": max(corrs) if corrs else float("nan"),
        "family_member_weeks": dict(families),
        "top_members": members.most_common(10),
    }


def decisions_through(selector: Selector, first_cut: int, last_cut: int) -> list[Decision]:
    lo = int(np.searchsorted(selector.wd.boundaries, first_cut, side="left"))
    hi = int(np.searchsorted(selector.wd.boundaries, last_cut, side="left"))
    out = [selector.select(j) for j in range(max(lo, MIN_HISTORY_WEEKS), hi)]
    add_turnover(out)
    return out


def audit_truncation(b5, wd: WeeklyData, uni: dict, meta: dict) -> dict:
    """Full vs physically truncated future columns at a historical cutoff."""
    wanted = int(datetime(2025, 1, 10, 22, 15, tzinfo=timezone.utc).timestamp())
    j = int(np.searchsorted(wd.boundaries, wanted, side="left"))
    if j >= len(wd.boundaries):
        j = len(wd.boundaries) - 2
    full_selector = Selector(wd, uni, meta)
    full = full_selector.select(j)
    truncated_wd = wd.truncated(j)
    truncated = Selector(truncated_wd, uni, meta).select(j)

    # Build only historical policy for a multiplier audit.  The full-path and
    # truncated-path calculations receive identical bars before C; future
    # equity is then mutated to prove it cannot affect the result.
    hist_decisions = decisions_through(full_selector,
                                       int(wd.boundaries[MIN_HISTORY_WEEKS]),
                                       int(wd.boundaries[j] + WEEK))
    exe = admit_orders(orders_from_decisions(b5, uni, hist_decisions))
    path = unit_path(b5, wd, exe.admitted)
    m_full = causal_multiplier_from_path(b5, path.base_equity, full.cut)
    mutated = path.base_equity.copy()
    future_k = int(np.searchsorted(b5.t, full.cut, side="left"))
    mutated[future_k:] += np.linspace(1e6, -1e6, len(mutated) - future_k)
    m_mutated = causal_multiplier_from_path(b5, mutated, full.cut)
    same_members = full.members == truncated.members
    same_weights = (set(full.weights) == set(truncated.weights)
                    and all(abs(full.weights[k] - truncated.weights[k]) < 1e-11
                            for k in full.weights))
    same_multiplier = abs(m_full - m_mutated) < 1e-11
    return {
        "cut": full.cut,
        "same_members": same_members,
        "same_weights": same_weights,
        "same_multiplier": same_multiplier,
        "multiplier": m_full,
        "members": full.members,
        "passed": same_members and same_weights and same_multiplier,
    }


def format_metrics(m: dict) -> str:
    parts = []
    for k, v in m.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.6f}" if math.isfinite(v) else f"{k}=inf")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


def run() -> int:
    print("AMENDMENT_23_BASKET_DD_RUN")
    print("research_only=true mt5_connection=false order_sending=false")
    b5 = hist.load_history()
    cache = audit._cache_path()
    expected = Path("data/weekly_evolution_universe_v10_sp090_co140.pkl")
    if cache.resolve() != expected.resolve():
        raise RuntimeError(f"wrong cost cache path: {cache}")
    before_mtime = cache.stat().st_mtime_ns if cache.exists() else None
    uni, meta = audit.load_universe(b5)
    after_mtime = cache.stat().st_mtime_ns if cache.exists() else None
    if before_mtime is None or before_mtime != after_mtime:
        raise RuntimeError("cache was missing, mismatched, or rebuilt; aborting")
    print(f"cache_full_hash=PASS path={cache} cells={len(uni)}")
    if len(uni) != 8250 or len(meta) != 8250:
        raise RuntimeError(f"declared universe mismatch uni={len(uni)} meta={len(meta)}")
    wd = WeeklyData.build(b5, uni)
    print(f"weekly_matrix=candidate_exit_week zero_inclusive=true cells={len(wd.tags)} "
          f"weeks={wd.base.shape[1]}")

    causal = audit_truncation(b5, wd, uni, meta)
    print("NO_LOOKAHEAD_AUDIT " + " ".join(f"{k}={v}" for k, v in causal.items()))
    if not causal["passed"]:
        print("SECTION_10_VERDICT=FAIL reason=no_lookahead_audit")
        return 2

    selector = Selector(wd, uni, meta)
    first_policy = int(wd.boundaries[MIN_HISTORY_WEEKS])
    last = int(b5.t[-1] + b5.step)
    decisions = decisions_through(selector, first_policy, last)
    print("WEEKEND_DECISIONS_BEGIN")
    for d in decisions:
        corr = ",".join(f"{a}|{b}:{v:.3f}"
                        for (a, b), v in sorted(d.correlations.items())
                        if a in d.members and b in d.members)
        weights = ",".join(f"{m}:{d.weights[m]:.4f}" for m in d.members)
        scores = ",".join(f"{m}:{d.scores[m]:.5f}" for m in d.members)
        print(f"week={utc(d.cut)} n_eff={d.n_eff:.6f} eligible={d.eligible_count} "
              f"members={len(d.members)} member_turnover={d.member_turnover:.6f} "
              f"weight_turnover={d.weight_turnover:.6f} reason={d.reason} "
              f"weights=[{weights}] scores=[{scores}] correlations=[{corr}] "
              f"risk_contributions={d.risk_contributions} caps={d.binding_caps}")
    print("WEEKEND_DECISIONS_END")

    primary_orders = orders_from_decisions(b5, uni, decisions)
    primary_execution = admit_orders(primary_orders)
    primary_path = unit_path(b5, wd, primary_execution.admitted)
    control_orders = orders_from_decisions(b5, uni, decisions, control=True)
    control_execution = admit_orders(control_orders)
    control_path = unit_path(b5, wd, control_execution.admitted)

    windows = (
        ("44_MONTH", REPORT_START, REPORT_SPLIT),
        ("TRAILING_12_MONTH", REPORT_SPLIT, last),
        ("FULL_WALK_FORWARD", REPORT_START, last),
    )
    print("UNIT_RISK_RESULTS_FIRST")
    result = {}
    for name, start, end in windows:
        result[name] = {}
        for label, stress in (("BASE", False), ("COST_1P5X", True)):
            m = window_metrics(b5, primary_path, primary_execution.admitted,
                               start, end, stress)
            result[name][label] = m
            print(f"UNIT {name} {label} start={utc(start)} end={utc(end)} "
                  + format_metrics(m))
        for label, stress in (("BASE", False), ("COST_1P5X", True)):
            m = window_metrics(b5, control_path, control_execution.admitted,
                               start, end, stress)
            print(f"CONTROL_FAMILY_MIDDLE {name} {label} " + format_metrics(m))
        wa = window_policy_audit(decisions, primary_execution, meta, start, end)
        print(f"WINDOW_POLICY_AUDIT {name} {wa}")

    forward = [d for d in decisions if REPORT_START <= d.cut < last]
    no_basket = sum(len(d.members) < MIN_MEMBERS for d in forward)
    avg_member_turnover = float(np.mean([d.member_turnover for d in forward]))
    avg_weight_turnover = float(np.mean([d.weight_turnover for d in forward]))
    neffs = [d.n_eff for d in forward]
    family_weeks = Counter()
    member_weeks = Counter()
    corr_values = []
    for d in forward:
        for tag in d.members:
            family_weeks[meta[tag]["setup"]] += 1
            member_weeks[tag] += 1
        for (a, b), c in d.correlations.items():
            if a in d.members and b in d.members:
                corr_values.append(c)
    print(f"PORTFOLIO_AUDIT forward_weeks={len(forward)} no_basket_weeks={no_basket} "
          f"no_basket_pct={100*no_basket/max(len(forward),1):.3f} "
          f"avg_member_turnover={avg_member_turnover:.6f} "
          f"avg_weight_turnover={avg_weight_turnover:.6f} "
          f"n_eff_min={min(neffs):.6f} n_eff_max={max(neffs):.6f} "
          f"n_eff_asymptotic={(1+DECAY)/(1-DECAY):.6f} "
          f"max_concurrent={primary_execution.max_concurrent} "
          f"rejected_slots={primary_execution.rejected_slots} "
          f"rejected_risk={primary_execution.rejected_risk} "
          f"mean_selected_corr={np.mean(corr_values) if corr_values else float('nan'):.6f} "
          f"max_selected_corr={max(corr_values) if corr_values else float('nan'):.6f}")
    print(f"FAMILY_COMPOSITION={dict(family_weeks)}")
    print(f"TOP_MEMBER_COMPOSITION={member_weeks.most_common(20)}")

    unit_pass = (
        causal["passed"]
        and result["44_MONTH"]["BASE"]["net_R"] > 0
        and result["TRAILING_12_MONTH"]["BASE"]["net_R"] > 0
        and result["44_MONTH"]["COST_1P5X"]["net_R"] > 0
        and result["TRAILING_12_MONTH"]["COST_1P5X"]["net_R"] > 0
        and no_basket <= len(forward) / 2
    )
    if not unit_pass:
        print("DD_SIZING=NOT_RUN reason=unit_risk_failed_per_sections_1_6_10_15")
        print("FINANCE_DCA=NOT_RUN reason=unit_risk_failed")
        print("DD_SCENARIOS_30_35_40_45_50=NOT_RUN reason=unit_risk_failed")
        print("SECTION_10_VERDICT=FAIL_PROMOTION unit_risk_pass=false")
        return 1

    # The unit-risk gate is deliberately before sizing.  A passing result must
    # not silently fall through to an approximate or ex-post scale.
    print("SECTION_10_VERDICT=BLOCKED sizing_replay_not_yet_implemented")
    return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
