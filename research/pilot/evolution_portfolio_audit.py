"""Fair portfolio comparison for the fixed Demo sleeves and weekly evolution.

Every weekly decision is made from trades whose exits precede the cutoff.  The
same 90-point raw spread floor, commission, slippage and swap are used for both
policies.  The report includes normalized R and the XAUUSD 0.01-lot dollar P/L.
This is research only; it has no order-sending code.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import hashlib
import pickle
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import canonical_history as canonical
import current_edge as ce
import data as D
import historical_regime_walkforward as hist
import payoff_demo_autotrader as demo
import weekly_evolution_grid as weekly
import walk_forward as wf


DAY = 86400
ACCOUNT_USD = 995.52


@dataclass(frozen=True)
class Trade:
    t: int
    exit_t: int
    net_r: float
    dollars: float
    risk_dollars: float
    label: str
    stress_r: float = 0.0
    entry: float = float("nan")
    entry_k: int = -1
    exit_k: int = -1
    direction: int = 0


def _drawdown(xs: list[float]) -> float:
    if not xs:
        return 0.0
    eq = np.cumsum(np.asarray(xs, float))
    peaks = np.maximum.accumulate(np.r_[0.0, eq[:-1]])
    return float(np.min(eq - peaks))


def _profit_factor(xs: list[float]) -> float:
    pos = sum(x for x in xs if x > 0)
    neg = -sum(x for x in xs if x <= 0)
    return math.inf if neg == 0 else pos / neg


def _max_loss_streak(xs: list[float]) -> int:
    best = cur = 0
    for x in xs:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def _open_risk(trades: list[Trade]) -> tuple[int, float]:
    """Maximum concurrent trades and their summed initial stop dollars."""
    events = []
    for r in trades:
        events.append((r.t, 1, r.risk_dollars))
        events.append((r.exit_t, -1, -r.risk_dollars))
    n = 0
    risk = 0.0
    max_n = 0
    max_risk = 0.0
    # Exit first at identical timestamps, then entry.
    for _t, kind, amount in sorted(events, key=lambda x: (x[0], x[1])):
        n += kind
        risk += amount
        max_n = max(max_n, n)
        max_risk = max(max_risk, risk)
    return max_n, max_risk


def mark_to_market(trades: list[Trade], bars: D.Bars) -> dict:
    """Close-to-close portfolio equity with simultaneous positions open."""
    usable = [r for r in trades if r.entry_k >= 0 and r.exit_k >= r.entry_k
              and np.isfinite(r.entry) and r.direction in (-1, 1)]
    open_value = np.zeros(len(bars), float)
    realised_delta = np.zeros(len(bars), float)
    for r in usable:
        k0 = r.entry_k
        k1 = min(r.exit_k, len(bars) - 1)
        realised_delta[k1] += r.dollars
        if k1 <= k0:
            continue
        fee = wf.E.COMMISSION_RT + 2 * wf.E.SLIP_PER_FILL
        if r.direction > 0:
            path = bars.c[k0:k1] - r.entry - fee
        else:
            if bars.sp is None:
                spreads = np.full(k1 - k0, wf.E.SPREAD_FALLBACK)
            else:
                spreads = np.maximum(bars.sp[k0:k1], wf.E.SPREAD_FALLBACK)
            path = r.entry - (bars.c[k0:k1] + spreads) - fee
        if r.direction > 0:
            t0 = int(bars.t[k0])
            t1 = int(bars.t[k1 - 1])
            day0 = t0 - (t0 % DAY)
            cur = day0 + wf.E.ROLLOVER_H * 3600
            if cur < t0:
                cur += DAY
            rolls = []
            while cur <= t1:
                rolls.append(cur)
                cur += DAY
            if rolls:
                nights = np.searchsorted(np.asarray(rolls, np.int64),
                                         bars.t[k0:k1], side="right")
                path = path - nights * wf.E.SWAP_LONG
        open_value[k0:k1] += path
    equity = np.cumsum(realised_delta) + open_value
    peak = np.maximum.accumulate(np.r_[0.0, equity[:-1]])
    dd = equity - peak
    worst = float(dd.min()) if len(dd) else 0.0
    return {"trades": len(usable), "mtm_DD_USD_001": worst,
            "mtm_DD_pct_001": 100 * worst / ACCOUNT_USD,
            "min_equity_USD": ACCOUNT_USD + float(equity.min()),
            "end_pnl_USD": float(equity[-1])}


def metrics(rows: list[Trade], start: int | None = None) -> dict:
    z = [r for r in rows if start is None or r.t >= start]
    z.sort(key=lambda r: (r.exit_t, r.t, r.label))
    rs = [r.net_r for r in z]
    usd = [r.dollars for r in z]
    stress_rs = [r.stress_r for r in z]
    stress_usd = [r.stress_r * r.risk_dollars for r in z]
    n, open_risk = _open_risk(z)
    if not z:
        return {"trades": 0}
    months = defaultdict(float)
    months_usd = defaultdict(float)
    for r in z:
        key = datetime.fromtimestamp(r.t, timezone.utc).strftime("%Y-%m")
        months[key] += r.net_r
        months_usd[key] += r.dollars
    mv = np.asarray(list(months.values()))
    mu = np.asarray(list(months_usd.values()))
    return {
        "trades": len(z), "net_R": sum(rs), "mean_R": float(np.mean(rs)),
        "win_pct": 100 * float(np.mean(np.asarray(rs) > 0)),
        "PF": _profit_factor(rs), "DD_R": _drawdown(rs),
        "stress_net_R": sum(stress_rs),
        "max_loss_streak": _max_loss_streak(rs),
        "net_USD_001": sum(usd), "DD_USD_001": _drawdown(usd),
        "stress_net_USD_001": sum(stress_usd),
        "return_pct_001": 100 * sum(usd) / ACCOUNT_USD,
        "DD_pct_001": 100 * _drawdown(usd) / ACCOUNT_USD,
        "months": len(months), "avg_R_month": float(mv.mean()),
        "median_R_month": float(np.median(mv)), "min_R_month": float(mv.min()),
        "positive_month_pct": 100 * float(np.mean(mv > 0)),
        "avg_USD_month_001": float(mu.mean()),
        "max_concurrent": n, "max_open_stop_USD_001": open_risk,
        "max_open_stop_pct_001": 100 * open_risk / ACCOUNT_USD,
    }


def _print_metrics(name: str, rows: list[Trade], now: int) -> None:
    print(f"\n[{name}]")
    for label, start in (("FULL", None), ("365D", now - 365 * DAY),
                         ("90D", now - 90 * DAY)):
        m = metrics(rows, start)
        print(label, " ".join(f"{k}={v:.4f}" if isinstance(v, float)
                              else f"{k}={v}" for k, v in m.items()))


def fixed_demo_trades(b5: D.Bars) -> tuple[list[Trade], list[Trade]]:
    """Exact frozen A/B/C geometry with the same within-sleeve busy rule."""
    ce.SPREAD_STANDARD = 0.0
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) &
                   (b5.t[np.minimum(pos, len(b5) - 1)] == want), pos, -1)
    atr = ce.core.atr(b15, 14)
    profile = adaptive.hourly_spread_profile(b5)
    events = ce.event_universe(b15, nxt, ce._load_news())
    out = []
    gated = []
    for sleeve in demo.SLEEVES:
        sleeve_rows = []
        busy = -1
        for i, event_dir in events[sleeve.family]:
            k = int(nxt[i]) if 0 <= i < len(nxt) else -1
            if k < 0 or k <= busy or k + sleeve.time_bars > len(b5):
                continue
            a = float(atr[i])
            if not np.isfinite(a) or a <= 0:
                continue
            d = -event_dir if sleeve.flip else event_dir
            risk = sleeve.stop_atr * a
            entry = float(b5.o[k] + (wf.E.spread_at(b5, k) if d > 0 else 0.0))
            gross, _why, bars = wf.E.resolve_plane(
                b5, k, d, entry, float(a), (sleeve.stop_atr,),
                (sleeve.target_r,), sleeve.time_bars)[
                    (sleeve.stop_atr, sleeve.target_r)]
            xk = min(k + bars, len(b5) - 1)
            swap = (ce._nights(int(b5.t[k]), int(b5.t[xk])) * ce.SWAP_LONG
                    if d > 0 else 0.0)
            fee = wf.E.COMMISSION_RT + 2 * wf.E.SLIP_PER_FILL
            base = fee + swap
            stress_extra = 0.5 * (wf.E.spread_at(b5, k) + fee)
            stress = gross - (base + stress_extra) / risk
            net = gross - base / risk
            row = Trade(int(b5.t[k]), int(b5.t[xk]), net, net * risk,
                        risk, sleeve.name, stress, entry, k, xk, int(d))
            out.append(row)
            sleeve_rows.append(row)
            busy = xk
        # This reproduces the live bot's health gate at each historical entry:
        # only outcomes already resolved before that entry may be inspected.
        for row in sleeve_rows:
            prior = [demo.ps.Row(r.t, r.exit_t, r.net_r, r.stress_r, 0.0, "time")
                     for r in sleeve_rows if r.exit_t < row.t]
            ready, _health = demo._health(prior, row.t)
            if ready:
                gated.append(row)
    return out, gated


def _universe_stamp(b5: D.Bars) -> dict:
    code = hashlib.sha256()
    for module in (Path(wf.__file__), Path(wf.E.__file__)):
        code.update(module.name.encode())
        code.update(module.read_bytes())
    return {
        "data_sha256": canonical.bars_digest(b5),
        "code_sha256": code.hexdigest(),
        "spread_floor": wf.E.SPREAD_FALLBACK,
        "commission_rt": wf.E.COMMISSION_RT,
        "slip_per_fill": wf.E.SLIP_PER_FILL,
        "swap_long": wf.E.SWAP_LONG,
        "swap_short": wf.E.SWAP_SHORT,
        "rollover_h": wf.E.ROLLOVER_H,
        "time_stop": wf.E.TIME_STOP_M5,
        "timeframes": wf.E.TIMEFRAMES,
        "stops": wf.E.STOPS,
        "targets": wf.E.TARGETS,
        "entry_modes": wf.E.ENTRY_MODES,
    }


def _cache_path() -> Path:
    sp = int(round(1000 * wf.E.SPREAD_FALLBACK))
    co = int(round(1000 * wf.E.COMMISSION_RT))
    return Path(f"data/weekly_evolution_universe_v10_sp{sp:03d}_co{co:03d}.pkl")


def load_universe(b5: D.Bars) -> tuple[dict, dict]:
    # Timestamp/length stamps are insufficient: MT5 has revised OHLC values
    # without changing either.  The entire input is now part of the cache key.
    stamp = _universe_stamp(b5)
    cache = _cache_path()
    if cache.exists():
        with cache.open("rb") as fh:
            got_stamp, uni, meta = pickle.load(fh)
        if got_stamp == stamp and all("entry" in a for a in uni.values()):
            print(f"universe_cache=HIT cells={len(uni):,}")
            return uni, meta
    print("universe_cache=MISS building 8,250 declared cells...")
    uni, meta = wf.build_universe(b5, int(b5.t[-1] + b5.step))
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as fh:
        pickle.dump((stamp, uni, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    return uni, meta


def _rank(uni: dict, lo: int, cut: int) -> tuple[list[str], int]:
    scores, signatures, purged = weekly._score_universe(uni, lo, cut)
    ranked, _collapsed = weekly._unique_ranking(scores, signatures)
    return ranked, purged


def weekly_rankings(uni: dict, first: int, last: int) -> tuple[list[tuple], int]:
    """Compute each expensive weekly ranking once for every portfolio size."""
    cut = weekly._week_boundary(first)
    if cut <= first + weekly.SELECT_DAYS * DAY:
        cut += 7 * DAY
    while cut < first + weekly.SELECT_DAYS * DAY:
        cut += 7 * DAY
    out = []
    purged = 0
    while cut < last:
        end = min(cut + 7 * DAY, last)
        ranked, p = _rank(uni, cut - weekly.SELECT_DAYS * DAY, cut)
        purged += p
        out.append((cut, end, ranked))
        cut += 7 * DAY
    return out, purged


def weekly_portfolio(b5: D.Bars, uni: dict, meta: dict, rankings: list[tuple],
                     purged: int, k: int, diverse: bool) -> tuple[list[Trade], dict]:
    out = []
    transitions = 0
    prior: tuple[str, ...] = ()
    for cut, end, ranked in rankings:
        chosen = []
        used_setups = set()
        for tag in ranked:
            setup = meta[tag]["setup"]
            if diverse and setup in used_setups:
                continue
            chosen.append(tag)
            used_setups.add(setup)
            if len(chosen) == k:
                break
        now_choice = tuple(chosen)
        transitions += int(now_choice != prior)
        prior = now_choice
        for tag in chosen:
            a = uni[tag]
            mask = ((a["t_order"] >= cut) & (a["t_order"] < end)
                    & (a["t_in"] < end))
            for j in np.flatnonzero(mask):
                bar = int(a["sigk"][j])
                execution = (wf.E.spread_at(b5, bar) + wf.E.COMMISSION_RT
                             + 2 * wf.E.SLIP_PER_FILL)
                stress_r = float(a["net"][j] - 0.5 * execution / a["risk"][j])
                out.append(Trade(int(a["t_in"][j]), int(a["t_out"][j]),
                                 float(a["net"][j]), float(a["dollars"][j]),
                                 float(a["risk"][j]), tag, stress_r,
                                 float(a["entry"][j]), int(a["sigk"][j]),
                                 int(a["exit_k"][j]), int(a["direction"][j])))
    return out, {"rolls": len(rankings), "transitions": transitions,
                 "purged": purged, "k": k, "diverse": diverse}


def main() -> int:
    b5 = hist.load_history()
    first = int(b5.t[0])
    last = int(b5.t[-1] + b5.step)
    print(f"data={datetime.fromtimestamp(first, timezone.utc):%Y-%m-%d}.."
          f"{datetime.fromtimestamp(last, timezone.utc):%Y-%m-%d} bars={len(b5):,}")
    print("cost=spread max(recorded,0.090)+0.140 commission+0.033 slippage+swap")
    fixed, gated = fixed_demo_trades(b5)
    _print_metrics("FIXED_DEMO_A_B_C", fixed, last)
    _print_metrics("LIVE_POLICY_A_B_C_WITH_HEALTH_GATE", gated, last)
    uni, meta = load_universe(b5)
    rankings, purged = weekly_rankings(uni, first, last)
    for diverse in (False, True):
        for k in range(1, 7):
            rows, audit = weekly_portfolio(
                b5, uni, meta, rankings, purged, k, diverse)
            print(f"\naudit={audit}")
            _print_metrics(f"WEEKLY_K{k}_{'DIVERSE' if diverse else 'RAW'}",
                           rows, last)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
