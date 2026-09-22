"""VWAP and value-area interaction experiment (Amendment 18).

This runner adds only the VWAP/value-area event layer.  Path resolution, costs,
leave-one-day-out controls and clustered summaries reuse Amendment 17's tested
machinery.

Run only after test_vwap_value_area.py passes.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D
import session_acceptance as S


HOLDOUT_DAYS = 120
WARM_M15 = 60
SESSION_ANCHOR_HOUR = 22
MIN_SESSION_M5 = 12
VWAP_SIGMA = 2.0
VALUE_AREA_FRAC = 0.70
PRICE_BIN = 0.01
MIN_MATCHED = 100
MIN_DAYS = 50
PERM_DRAWS = 10_000
SEED = 20260922

FAMILY_ORDER = {"vwap_reversion": 0, "value_area_continuation": 1}


@dataclass(frozen=True)
class Feature:
    vwap: float
    sd: float
    val: float
    vah: float
    n_m5: int


@dataclass(frozen=True)
class Event:
    family: str
    decision15_i: int
    entry_i: int
    direction: int
    close: float
    vwap: float
    sd: float
    val: float
    vah: float
    dist_sd: float


def session_key(ts: int) -> int:
    return (int(ts) - SESSION_ANCHOR_HOUR * 3600) // 86400


def value_area(tp: np.ndarray, vol: np.ndarray, frac: float = VALUE_AREA_FRAC,
               bin_size: float = PRICE_BIN) -> tuple[float, float]:
    """70% value area from the highest-volume price bin, expanding outward."""
    good = np.isfinite(tp) & np.isfinite(vol)
    tp = tp[good]
    vol = np.where(vol[good] > 0, vol[good], 1.0)
    if len(tp) == 0 or np.sum(vol) <= 0:
        return np.nan, np.nan
    bins = np.rint(tp / bin_size).astype(np.int64)
    uniq, inv = np.unique(bins, return_inverse=True)
    by_bin = np.bincount(inv, weights=vol, minlength=len(uniq))
    center = int(np.argmax(by_bin))
    lo = hi = center
    covered = float(by_bin[center])
    target = float(np.sum(by_bin) * frac)
    while covered < target and (lo > 0 or hi < len(uniq) - 1):
        left = by_bin[lo - 1] if lo > 0 else -1.0
        right = by_bin[hi + 1] if hi < len(uniq) - 1 else -1.0
        if left > right:
            lo -= 1
            covered += float(by_bin[lo])
        elif right > left:
            hi += 1
            covered += float(by_bin[hi])
        else:
            if lo > 0:
                lo -= 1
                covered += float(by_bin[lo])
            if covered >= target:
                break
            if hi < len(uniq) - 1:
                hi += 1
                covered += float(by_bin[hi])
    return float(uniq[lo] * bin_size), float(uniq[hi] * bin_size)


def feature_before(b5: D.Bars, decision_close: int,
                   keys: np.ndarray | None = None) -> Feature:
    """Session-to-date VWAP/value area using only completed M5 bars."""
    anchor = session_key(decision_close - 1)
    if keys is None:
        keys = np.array([session_key(t) for t in b5.t], dtype=np.int64)
    lo = int(np.searchsorted(keys, anchor, side="left"))
    hi_sess = int(np.searchsorted(keys, anchor, side="right"))
    hi_time = int(np.searchsorted(b5.t, decision_close - 300, side="right"))
    hi = min(hi_sess, hi_time)
    ix = np.arange(lo, hi, dtype=np.int64)
    if len(ix) < MIN_SESSION_M5:
        return Feature(np.nan, np.nan, np.nan, np.nan, len(ix))
    tp = (b5.h[ix] + b5.l[ix] + b5.c[ix]) / 3.0
    vol = np.where(b5.v[ix] > 0, b5.v[ix], 1.0)
    sw = float(np.sum(vol))
    vwap = float(np.sum(tp * vol) / sw)
    var = max(float(np.sum(tp * tp * vol) / sw - vwap * vwap), 0.0)
    val, vah = value_area(tp, vol)
    return Feature(vwap, float(np.sqrt(var)), val, vah, len(ix))


def build_events(b5: D.Bars) -> tuple[list[Event], D.Bars, np.ndarray]:
    b15, nxt = D.to_15m(b5)
    keys = np.array([session_key(t) for t in b5.t], dtype=np.int64)
    events: list[Event] = []
    prev_pos = None
    for i in range(len(b15)):
        entry = int(nxt[i]) if i < len(nxt) else -1
        if i < WARM_M15 or entry < 0:
            prev_pos = None
            continue
        decision_close = int(b15.t[i]) + 900
        f = feature_before(b5, decision_close, keys)
        if not all(np.isfinite(x) for x in (f.vwap, f.sd, f.val, f.vah)) or f.sd <= 0:
            prev_pos = None
            continue
        close = float(b15.c[i])
        dist_sd = (close - f.vwap) / f.sd
        ev = None
        if dist_sd >= VWAP_SIGMA:
            ev = Event("vwap_reversion", i, entry, -1, close, f.vwap, f.sd,
                       f.val, f.vah, dist_sd)
        elif dist_sd <= -VWAP_SIGMA:
            ev = Event("vwap_reversion", i, entry, 1, close, f.vwap, f.sd,
                       f.val, f.vah, dist_sd)
        else:
            pos = 1 if close > f.vah else (-1 if close < f.val else 0)
            if prev_pos is not None:
                if pos == 1 and prev_pos <= 0:
                    ev = Event("value_area_continuation", i, entry, 1, close,
                               f.vwap, f.sd, f.val, f.vah, dist_sd)
                elif pos == -1 and prev_pos >= 0:
                    ev = Event("value_area_continuation", i, entry, -1, close,
                               f.vwap, f.sd, f.val, f.vah, dist_sd)
            prev_pos = pos
        if ev is not None:
            events.append(ev)
    events.sort(key=lambda e: (e.entry_i, FAMILY_ORDER[e.family], -e.direction))
    return events, b15, nxt


def score_events(events: list[Event], b5: D.Bars, out: S.Outcomes,
                 key: np.ndarray, pool: dict[int, np.ndarray]) -> pd.DataFrame:
    rows = []
    days = b5.t // 86400
    for e in events:
        k, d = e.entry_i, e.direction
        if k >= len(b5) or not out.ok[k] or key[k] < 0:
            continue
        ctl, ctl_n = S.leave_one_day_mean(out.gross[d],
                                          pool.get(int(key[k]), np.array([], dtype=int)),
                                          days, int(days[k]))
        matched = np.isfinite(ctl)
        row = dict(day=int(days[k]), t=int(b5.t[k]), family=e.family,
                   decision15_i=e.decision15_i, entry_i=k, direction=d,
                   close=e.close, vwap=e.vwap, sd=e.sd, val=e.val, vah=e.vah,
                   dist_sd=e.dist_sd, gross=out.gross[d][k], control=ctl,
                   excess=(out.gross[d][k] - ctl if matched else np.nan),
                   matched=matched, control_n=ctl_n, risk=out.risk[k],
                   held=int(out.held[d][k]), exit_i=int(out.exit_i[d][k]),
                   nights=int(out.nights[d][k]))
        for mult in S.COST_MULTIPLIERS:
            row[f"net_{mult:g}"] = out.net[mult][d][k]
        rows.append(row)
    return pd.DataFrame(rows)


def wild_mean_test(x: np.ndarray, day: np.ndarray) -> dict:
    x = np.asarray(x, float)
    day = np.asarray(day, np.int64)
    good = np.isfinite(x)
    x, day = x[good], day[good]
    if len(x) < 2:
        return dict(n=len(x), days=len(np.unique(day)), mean=np.nan, se=np.nan,
                    t=np.nan, p=np.nan, mde=np.nan)
    mu = float(np.mean(x))
    uniq, ix = np.unique(day, return_inverse=True)
    sums = np.bincount(ix, weights=x - mu, minlength=len(uniq))
    G = len(uniq)
    se = float(np.sqrt((G / (G - 1) if G > 1 else 1.0) * np.sum(sums ** 2)) / len(x))
    t = mu / se if se > 0 else np.nan
    rng = np.random.default_rng(SEED)
    denom = np.sqrt((G / (G - 1) if G > 1 else 1.0) * np.sum(sums ** 2))
    null_t = (rng.choice((-1.0, 1.0), size=(PERM_DRAWS, G)) @ sums) / denom if denom > 0 else np.full(PERM_DRAWS, np.nan)
    p = float((1 + np.sum(null_t >= t)) / (PERM_DRAWS + 1)) if np.isfinite(t) else np.nan
    return dict(n=len(x), days=G, mean=mu, se=se, t=t, p=p,
                mde=(1.645 + 0.842) * se)


def holm_two(p_a: float, p_b: float) -> tuple[float, float]:
    ps = np.array([p_a, p_b], float)
    order = np.argsort(ps)
    adj = np.empty(2)
    adj[order[0]] = min(1.0, ps[order[0]] * 2)
    adj[order[1]] = min(1.0, max(adj[order[0]], ps[order[1]]))
    return float(adj[0]), float(adj[1])


def one_position(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    z = df.copy()
    z["fo"] = z["family"].map(FAMILY_ORDER)
    z = z.sort_values(["entry_i", "fo", "direction"])
    keep, busy = [], -1
    for i, row in z.iterrows():
        if int(row.entry_i) <= busy:
            continue
        keep.append(i)
        busy = int(row.exit_i)
    return z.loc[keep].drop(columns=["fo"])


def _fmt(v: float) -> str:
    return "NA" if not np.isfinite(v) else f"{v:+.4f}"


def main() -> int:
    raw = D.load_csv("data/XAUUSD_M5.csv")
    cut = int(raw.t[-1]) - HOLDOUT_DAYS * 86400
    hi = int(np.searchsorted(raw.t, cut))
    b5 = raw.slice(0, hi)
    atr_known, _, _ = S.completed_atr_for_m5(b5)
    events, _, _ = build_events(b5)
    outcomes = S.precompute_outcomes(b5, atr_known)
    key, pool = S.build_strata(b5, atr_known, S.load_news())
    df = score_events(events, b5, outcomes, key, pool)
    matched = df[df["matched"]].copy()

    print("=" * 100)
    print("AMENDMENT 18 - VWAP / VALUE-AREA INTERACTION")
    print("=" * 100)
    print(f"data {pd.to_datetime(b5.t[0], unit='s', utc=True):%Y-%m-%d} to "
          f"{pd.to_datetime(b5.t[-1], unit='s', utc=True):%Y-%m-%d %H:%M} UTC")
    print(f"holdout starts {pd.to_datetime(cut, unit='s', utc=True):%Y-%m-%d %H:%M} UTC - not opened")
    print(f"events {len(events):,}  scored {len(df):,}  matched {len(matched):,}  "
          f"unmatched {int((~df['matched']).sum()) if len(df) else 0:,}")

    if len(matched) < 20:
        print("\nNOT ASSESSED - too few matched events")
        return 0

    results = {}
    for fam in ("vwap_reversion", "value_area_continuation"):
        z = matched[matched.family == fam]
        reg = wild_mean_test(z.excess.to_numpy(), z.day.to_numpy())
        net1, _, lo1 = S.clustered_mean(z["net_1"].to_numpy(), z.day.to_numpy())
        net15 = S.clustered_mean(z["net_1.5"].to_numpy(), z.day.to_numpy())[0]
        results[fam] = dict(reg, net1=net1, lo1=lo1, net15=net15)

    p_vwap, p_va = holm_two(results["vwap_reversion"]["p"],
                            results["value_area_continuation"]["p"])
    results["vwap_reversion"]["p_holm"] = p_vwap
    results["value_area_continuation"]["p_holm"] = p_va

    print("\nPRIMARY POWER AND TESTS")
    print(f"{'family':<27}{'n':>8}{'days':>8}{'excess':>11}{'SE':>10}{'MDE80':>10}{'p':>9}{'Holm':>9}{'net1':>10}{'net1.5':>10}")
    for fam in ("vwap_reversion", "value_area_continuation"):
        r = results[fam]
        print(f"{fam:<27}{r['n']:8,d}{r['days']:8,d}{_fmt(r['mean']):>11}"
              f"{r['se']:10.4f}{r['mde']:10.4f}{r['p']:9.4f}{r['p_holm']:9.4f}"
              f"{_fmt(r['net1']):>10}{_fmt(r['net15']):>10}")

    print("\nGATES")
    for fam in ("vwap_reversion", "value_area_continuation"):
        r = results[fam]
        passed = (r["n"] >= MIN_MATCHED and r["days"] >= MIN_DAYS
                  and r["mean"] > 0 and r["p_holm"] <= .05
                  and r["net1"] >= .05 and r["net15"] >= .05 and r["lo1"] > 0)
        assessed = r["n"] >= MIN_MATCHED and r["days"] >= MIN_DAYS
        verdict = "FORWARD-SHADOW PROTOCOL RIGHT" if passed else ("NOT ESTABLISHED" if assessed else "NOT ASSESSED")
        print(f"{fam}: {verdict}  lower95 net1 {_fmt(r['lo1'])}")

    print("\nDESCRIPTIVE ONLY - no subgroup selection rights")
    print(f"{'family':<27}{'dir':>5}{'n':>8}{'days':>8}{'excess':>11}{'net1':>10}")
    for (fam, d), g in matched.groupby(["family", "direction"]):
        ex = S.clustered_mean(g.excess.to_numpy(), g.day.to_numpy())[0]
        ne = S.clustered_mean(g["net_1"].to_numpy(), g.day.to_numpy())[0]
        print(f"{fam:<27}{int(d):5d}{len(g):8,d}{g.day.nunique():8,d}{_fmt(ex):>11}{_fmt(ne):>10}")
    pol = one_position(matched)
    pnet = S.clustered_mean(pol["net_1"].to_numpy(), pol.day.to_numpy())[0]
    print(f"\nsecondary one-position policy n {len(pol):,} days {pol.day.nunique():,} net1 {_fmt(pnet)}")
    print("\nstatus: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
