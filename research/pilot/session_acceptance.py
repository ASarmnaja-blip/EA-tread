"""Session-level acceptance/rejection experiment (Amendment 17).

This file is deliberately narrow.  It builds six visible levels, classifies the
initiating interaction as rejection or two-close acceptance, and asks one
question: does matched excess decline with ordinal touch count?

Run only after test_session_acceptance.py passes.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import calendar_feed
import core
import data as D


HOLDOUT_DAYS = 120
WARM_M15 = 60
ATR_N = 14
STOP_ATR = 1.5
RR = 1.0
TIME_STOP = 72
SPREAD_FALLBACK = 0.090
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_LONG = 0.5493
SWAP_SHORT = 0.0
ROLLOVER_HOUR = 21
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)
MIN_POOL = 30
PERM_DRAWS = 10_000
SEED = 20260922

FAMILY_ORDER = {"prior-day": 0, "asia": 1, "pre-london": 2}
RESPONSE_ORDER = {"rejection": 0, "acceptance": 1}


@dataclass(frozen=True)
class Level:
    day: int
    family: str
    side: str
    price: float
    start: int
    end: int


@dataclass(frozen=True)
class Event:
    day: int
    family: str
    side: str
    response: str
    touch: int                 # 0, 1, 2 = first, second, third+
    touch_raw: int
    touch_i: int
    decision_i: int
    entry_i: int
    direction: int
    level: float


@dataclass
class Outcomes:
    gross: dict[int, np.ndarray]
    net: dict[float, dict[int, np.ndarray]]
    held: dict[int, np.ndarray]
    exit_i: dict[int, np.ndarray]
    nights: dict[int, np.ndarray]
    risk: np.ndarray
    ok: np.ndarray


def completed_atr_for_m5(b5: D.Bars) -> tuple[np.ndarray, D.Bars, np.ndarray]:
    """Map each M5 bar close to the latest M15 ATR that had already closed."""
    b15, _ = D.to_15m(b5)
    a15 = core.atr(b15, ATR_N)
    close15 = b15.t + 900
    decision_close = b5.t + 300
    ix = np.searchsorted(close15, decision_close, side="right") - 1
    out = np.full(len(b5), np.nan)
    good = ix >= 0
    out[good] = a15[ix[good]]
    # Return the source index too: the test suite verifies no unclosed M15 bar.
    return out, b15, ix


def _complete_window(t: np.ndarray, start: int, end: int) -> np.ndarray | None:
    lo, hi = np.searchsorted(t, [start, end])
    got = t[lo:hi]
    want = np.arange(start, end, 300, dtype=np.int64)
    if len(got) != len(want) or not np.array_equal(got, want):
        return None
    return np.arange(lo, hi, dtype=np.int64)


def build_levels(b5: D.Bars) -> list[Level]:
    """Build levels entirely before their eligibility windows."""
    t = b5.t.astype(np.int64)
    days = np.unique(t // 86400)
    by_day: dict[int, np.ndarray] = {
        int(d): np.flatnonzero(t // 86400 == d) for d in days
    }
    daily = {
        d: (float(np.max(b5.h[ix])), float(np.min(b5.l[ix])))
        for d, ix in by_day.items() if len(ix) >= 200
    }
    out: list[Level] = []
    for day in days:
        d = int(day)
        base = d * 86400
        asia = _complete_window(t, base, base + 6 * 3600)
        if asia is not None:
            for side, px in (("high", np.max(b5.h[asia])),
                             ("low", np.min(b5.l[asia]))):
                out.append(Level(d, "asia", side, float(px),
                                 base + 6 * 3600, base + 21 * 3600))
        pre = _complete_window(t, base + 6 * 3600, base + 7 * 3600)
        if pre is not None:
            for side, px in (("high", np.max(b5.h[pre])),
                             ("low", np.min(b5.l[pre]))):
                out.append(Level(d, "pre-london", side, float(px),
                                 base + 7 * 3600, base + 21 * 3600))
        prev = daily.get(d - 1)
        if prev is not None:
            for side, px in (("high", prev[0]), ("low", prev[1])):
                out.append(Level(d, "prior-day", side, float(px),
                                 base, base + 21 * 3600))
    return out


def scan_level(b5: D.Bars, level: Level) -> tuple[list[Event], int]:
    """Return classified events and the number of all touch episodes.

    A touching run stays active until a later bar is wholly clear on the
    interior side.  Thus consecutive wicks are one episode, including when the
    first touching bar itself closed back inside.
    """
    t, h, l, c = b5.t, b5.h, b5.l, b5.c
    lo, hi = np.searchsorted(t, [level.start, level.end])
    events: list[Event] = []
    active = False
    raw = 0
    for i in range(lo, hi):
        if i <= 0 or t[i] != t[i - 1] + 300:
            active = False
            continue
        if level.side == "high":
            touched = h[i] >= level.price
            clear = h[i] < level.price
            prior_inside = c[i - 1] < level.price
            reject = c[i] < level.price
            outside = c[i] > level.price
            hold = lambda j: c[j] > level.price
            direction_rej, direction_acc = -1, 1
        else:
            touched = l[i] <= level.price
            clear = l[i] > level.price
            prior_inside = c[i - 1] > level.price
            reject = c[i] > level.price
            outside = c[i] < level.price
            hold = lambda j: c[j] < level.price
            direction_rej, direction_acc = 1, -1

        if active:
            if clear:
                active = False
            else:
                continue
        if not touched or not prior_inside:
            continue

        raw += 1
        active = True
        touch = min(raw - 1, 2)
        response = None
        decision = entry = direction = -1
        if reject:
            response = "rejection"
            decision, entry, direction = i, i + 1, direction_rej
        elif outside and i + 2 < len(t) and t[i + 1] == t[i] + 300 \
                and t[i + 2] == t[i] + 600 and hold(i + 1):
            response = "acceptance"
            decision, entry, direction = i + 1, i + 2, direction_acc

        if response is None:
            continue
        # Confirmation and entry must remain inside the level's eligible window.
        if entry >= len(t) or t[entry] >= level.end:
            continue
        events.append(Event(level.day, level.family, level.side, response,
                            touch, raw, i, decision, entry, direction,
                            level.price))
    return events, raw


def build_events(b5: D.Bars, levels: list[Level]) -> tuple[list[Event], int]:
    out: list[Event] = []
    episodes = 0
    for level in levels:
        ev, n = scan_level(b5, level)
        out.extend(ev)
        episodes += n
    out.sort(key=lambda e: (e.entry_i, FAMILY_ORDER[e.family],
                            RESPONSE_ORDER[e.response], e.side))
    return out, episodes


def _rollover_count(t0: int, t1: int) -> int:
    """Number of 21:00 UTC boundaries strictly after entry and before exit."""
    d0 = t0 // 86400
    cur = d0 * 86400 + ROLLOVER_HOUR * 3600
    if cur <= t0:
        cur += 86400
    n = 0
    while cur < t1:
        n += 1
        cur += 86400
    return n


def precompute_outcomes(b5: D.Bars, atr_known: np.ndarray) -> Outcomes:
    """Outcomes for an entry at each M5 open, with a fully known 72-bar path."""
    n = len(b5)
    gross = {d: np.full(n, np.nan) for d in (1, -1)}
    held = {d: np.zeros(n, np.int32) for d in (1, -1)}
    exit_i = {d: np.full(n, -1, np.int64) for d in (1, -1)}
    nights = {d: np.zeros(n, np.int16) for d in (1, -1)}
    risk = np.full(n, np.nan)
    ok = np.zeros(n, bool)
    # The signal decision is the preceding M5 close.
    for k in range(1, n):
        if k + TIME_STOP > n:
            continue
        a = atr_known[k - 1]
        if not np.isfinite(a) or a <= 0:
            continue
        risk[k] = STOP_ATR * float(a)
        ok[k] = True
        for d in (1, -1):
            entry = b5.o[k]
            stop = entry - d * risk[k]
            target = entry + d * RR * risk[k]
            px, _, nb = core.resolve(b5, k, d, entry, stop, target, TIME_STOP)
            gross[d][k] = d * (px - entry) / risk[k]
            held[d][k] = nb
            exit_i[d][k] = k + nb
            exit_close = int(b5.t[k + nb]) + 300
            nights[d][k] = _rollover_count(int(b5.t[k]), exit_close)

    net: dict[float, dict[int, np.ndarray]] = {}
    for mult in COST_MULTIPLIERS:
        net[mult] = {}
        for d in (1, -1):
            arr = np.full(n, np.nan)
            good = np.flatnonzero(ok)
            sp = np.array([
                float(b5.sp[k]) if b5.sp is not None
                and np.isfinite(b5.sp[k]) and b5.sp[k] > 0
                else SPREAD_FALLBACK for k in good
            ])
            friction = mult * (sp + COMMISSION_RT + 2 * SLIP_PER_FILL)
            swap = (SWAP_LONG if d > 0 else SWAP_SHORT) * nights[d][good]
            arr[good] = gross[d][good] - (friction + swap) / risk[good]
            net[mult][d] = arr
    return Outcomes(gross, net, held, exit_i, nights, risk, ok)


def load_news() -> np.ndarray:
    cal = calendar_feed.load_calendar("data/calendar.csv")
    rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
    return np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)


def build_strata(b5: D.Bars, atr_known: np.ndarray,
                 news_ep: np.ndarray) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """Amendment 10 strata on M5 entry bars, restricted to 00:00-20:59 UTC."""
    n = len(b5)
    t = b5.t.astype(np.int64)
    hours = (t // 3600) % 24
    q = pd.to_datetime(t, unit="s", utc=True).tz_localize(None).to_period("Q")
    qcode = pd.Series(np.asarray(q.astype(str))).astype("category").cat.codes.to_numpy()
    sess = np.where(hours < 7, 0, np.where(hours < 13, 1, 2))

    # Prior-only rolling terciles on M5-mapped completed ATR values.
    ar = pd.Series(atr_known).shift(1).rolling(30 * 24 * 12, min_periods=5 * 24 * 12)
    q33, q67 = ar.quantile(.33).to_numpy(), ar.quantile(.67).to_numpy()
    vt = np.where(atr_known <= q33, 0, np.where(atr_known >= q67, 2, 1))
    vt = np.where(np.isfinite(q33) & np.isfinite(q67), vt, -1)

    news = np.zeros(n, int)
    if len(news_ep):
        nx = np.searchsorted(news_ep, t, "left")
        pv = nx - 1
        to_n = np.where(nx < len(news_ep),
                        news_ep[np.minimum(nx, len(news_ep) - 1)] - t, 10**12)
        since = np.where(pv >= 0, t - news_ep[np.maximum(pv, 0)], 10**12)
        news = ((to_n <= 1800) | (since <= 1800)).astype(int)

    prof = adaptive.hourly_spread_profile(b5)
    edges = np.nanpercentile(prof, [33, 67])
    cb = np.digitize(prof[hours], edges)
    composite = qcode.astype(np.int64) * 1000 + sess * 100 + vt * 10 + news * 5 + cb
    ok = (hours < 21) & (vt >= 0) & np.isfinite(atr_known) & (atr_known > 0)
    key = np.where(ok, composite, -1).astype(np.int64)
    pool = {int(s): np.flatnonzero(key == s) for s in np.unique(key[ok])}
    return key, pool


def leave_one_day_mean(values: np.ndarray, members: np.ndarray,
                       days: np.ndarray, focal_day: int,
                       min_pool: int = MIN_POOL) -> tuple[float, int]:
    """Control mean after removing the focal UTC day in full."""
    mem = members[np.isfinite(values[members])]
    rem = mem[days[mem] != focal_day]
    if len(rem) < min_pool:
        return np.nan, len(rem)
    return float(np.mean(values[rem])), len(rem)


def score_events(events: list[Event], b5: D.Bars, out: Outcomes,
                 key: np.ndarray, pool: dict[int, np.ndarray]) -> pd.DataFrame:
    rows = []
    days = b5.t // 86400
    for e in events:
        k, d = e.entry_i, e.direction
        if k >= len(b5) or not out.ok[k] or key[k] < 0:
            continue
        ctl, ctl_n = leave_one_day_mean(out.gross[d], pool.get(int(key[k]),
                                      np.array([], dtype=int)), days,
                                      int(days[k]))
        matched = np.isfinite(ctl)
        row = dict(day=int(days[k]), t=int(b5.t[k]), family=e.family,
                   side=e.side, response=e.response, touch=e.touch,
                   touch_raw=e.touch_raw, touch_i=e.touch_i,
                   decision_i=e.decision_i, entry_i=k, direction=d,
                   level=e.level, risk=out.risk[k], gross=out.gross[d][k],
                   control=ctl, excess=(out.gross[d][k] - ctl if matched else np.nan),
                   matched=matched, control_n=ctl_n, held=int(out.held[d][k]),
                   exit_i=int(out.exit_i[d][k]), nights=int(out.nights[d][k]))
        for mult in COST_MULTIPLIERS:
            row[f"net_{mult:g}"] = out.net[mult][d][k]
        rows.append(row)
    return pd.DataFrame(rows)


def fixed_effect_slope(df: pd.DataFrame) -> dict:
    """Common ordinal slope with 12 stratum intercepts and day clusters."""
    z = df.dropna(subset=["excess"]).copy()
    labels = z["family"] + "/" + z["side"] + "/" + z["response"]
    dummies = pd.get_dummies(labels, dtype=float).to_numpy()
    x = z["touch"].to_numpy(float)
    y = z["excess"].to_numpy(float)
    X = np.column_stack([dummies, x])
    inv = np.linalg.pinv(X.T @ X)
    coef = inv @ X.T @ y
    resid = y - X @ coef
    uniq, di = np.unique(z["day"].to_numpy(np.int64), return_inverse=True)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in range(len(uniq)):
        v = X[di == g].T @ resid[di == g]
        meat += np.outer(v, v)
    G, N, K = len(uniq), len(y), X.shape[1]
    corr = (G / (G - 1) if G > 1 else 1.0) * ((N - 1) / max(1, N - K))
    cov = corr * inv @ meat @ inv
    beta = float(coef[-1])
    se = float(np.sqrt(max(0.0, cov[-1, -1])))

    # Wild-cluster score test under beta=0.  Residualise both variables by the
    # fixed-effect strata, then flip one score contribution per calendar day.
    xbar = pd.Series(x).groupby(labels.to_numpy()).transform("mean").to_numpy()
    ybar = pd.Series(y).groupby(labels.to_numpy()).transform("mean").to_numpy()
    xr, yr = x - xbar, y - ybar
    score = xr * yr
    sg = np.bincount(di, weights=score, minlength=G)
    sc_corr = G / (G - 1) if G > 1 else 1.0
    denom = np.sqrt(sc_corr * np.sum(sg ** 2))
    t_score = float(np.sum(sg) / denom) if denom > 0 else np.nan
    rng = np.random.default_rng(SEED)
    flips = rng.choice((-1.0, 1.0), size=(PERM_DRAWS, G))
    null_t = (flips @ sg) / denom if denom > 0 else np.full(PERM_DRAWS, np.nan)
    # One-sided alternative is negative.
    p = float((1 + np.sum(null_t <= t_score)) / (PERM_DRAWS + 1))
    return dict(n=N, days=G, strata=dummies.shape[1], beta=beta, se=se,
                t=(beta / se if se > 0 else np.nan), score_t=t_score, p=p,
                mde=(1.645 + 0.842) * se)


def clustered_mean(x: np.ndarray, day: np.ndarray) -> tuple[float, float, float]:
    x = np.asarray(x, float)
    day = np.asarray(day, np.int64)
    good = np.isfinite(x)
    x, day = x[good], day[good]
    if not len(x):
        return np.nan, np.nan, np.nan
    mu = float(np.mean(x))
    uniq, ix = np.unique(day, return_inverse=True)
    sums = np.bincount(ix, weights=x - mu, minlength=len(uniq))
    corr = len(uniq) / (len(uniq) - 1) if len(uniq) > 1 else 1.0
    se = float(np.sqrt(corr * np.sum(sums ** 2)) / len(x))
    return mu, se, mu - 1.96 * se


def one_position(df: pd.DataFrame) -> pd.DataFrame:
    """Predeclared descriptive portfolio tie-break and overlap filter."""
    if df.empty:
        return df.copy()
    z = df.copy()
    z["fo"] = z["family"].map(FAMILY_ORDER)
    z["ro"] = z["response"].map(RESPONSE_ORDER)
    z = z.sort_values(["entry_i", "fo", "ro", "side"])
    keep, busy = [], -1
    for i, row in z.iterrows():
        if int(row.entry_i) <= busy:
            continue
        keep.append(i)
        busy = int(row.exit_i)
    return z.loc[keep].drop(columns=["fo", "ro"])


def _fmt(v: float) -> str:
    return "NA" if not np.isfinite(v) else f"{v:+.4f}"


def main() -> int:
    raw = D.load_csv("data/XAUUSD_M5.csv")
    cut = int(raw.t[-1]) - HOLDOUT_DAYS * 86400
    hi = int(np.searchsorted(raw.t, cut))
    # Physically remove the protected slice before any levels or paths exist.
    b5 = raw.slice(0, hi)
    atr_known, b15, atr_source = completed_atr_for_m5(b5)
    levels = build_levels(b5)
    events, episodes = build_events(b5, levels)
    outcomes = precompute_outcomes(b5, atr_known)
    news_ep = load_news()
    key, pool = build_strata(b5, atr_known, news_ep)
    df = score_events(events, b5, outcomes, key, pool)
    matched = df[df["matched"]].copy()

    print("=" * 108)
    print("AMENDMENT 17 — SESSION-LEVEL ACCEPTANCE / REJECTION")
    print("=" * 108)
    print(f"ใช้ข้อมูล {pd.to_datetime(b5.t[0], unit='s', utc=True):%Y-%m-%d} ถึง "
          f"{pd.to_datetime(b5.t[-1], unit='s', utc=True):%Y-%m-%d %H:%M} UTC")
    print(f"ตัด holdout {HOLDOUT_DAYS} วัน เริ่ม "
          f"{pd.to_datetime(cut, unit='s', utc=True):%Y-%m-%d %H:%M} UTC — ไม่เปิดผล")
    print(f"levels {len(levels):,}  touch episodes {episodes:,}  "
          f"classified events {len(events):,}  scored {len(df):,}  matched {len(matched):,}")
    print(f"unmatched {int((~df['matched']).sum()) if len(df) else 0:,}  control strata {len(pool):,}")

    if len(matched) < 20:
        print("\nNOT ASSESSED — matched events น้อยเกินไป")
        return 0

    print("\nPRIMARY POWER (พิมพ์ก่อนตีความ p-value)")
    reg = fixed_effect_slope(matched)
    print(f"beta SE {reg['se']:.5f} R ต่อ touch step  |  80% MDE {reg['mde']:.5f} R")
    print(f"n {reg['n']:,}  active days {reg['days']:,}  fixed strata {reg['strata']}")

    print("\nORDINAL PROFILE — pooled, descriptive")
    print(f"{'touch':<10}{'n':>8}{'days':>8}{'excess':>12}{'net 1x':>12}{'net 1.5x':>12}")
    profile = []
    for touch, label in ((0, "first"), (1, "second"), (2, "third+")):
        z = matched[matched.touch == touch]
        ex = clustered_mean(z.excess.to_numpy(), z.day.to_numpy())[0]
        n1 = clustered_mean(z["net_1"].to_numpy(), z.day.to_numpy())[0]
        n15 = clustered_mean(z["net_1.5"].to_numpy(), z.day.to_numpy())[0]
        profile.append((len(z), z.day.nunique(), ex, n1, n15))
        print(f"{label:<10}{len(z):8,d}{z.day.nunique():8,d}{_fmt(ex):>12}{_fmt(n1):>12}{_fmt(n15):>12}")

    print("\nPRIMARY ORDINAL TEST")
    print(f"beta {reg['beta']:+.5f}  clustered SE {reg['se']:.5f}  t {reg['t']:+.2f}")
    print(f"wild-cluster score t {reg['score_t']:+.2f}  one-sided p(beta<0) {reg['p']:.4f} "
          f"({PERM_DRAWS:,} draws, seed {SEED})")
    ordered = profile[0][2] >= profile[1][2] >= profile[2][2]
    adequate = all(n >= 50 and d >= 30 for n, d, *_ in profile)
    mechanism = reg["beta"] < 0 and reg["p"] <= .05 and ordered and adequate
    print(f"observed order first>=second>=third+: {'YES' if ordered else 'NO'}")
    print(f"count gate 50 events + 30 days per category: {'PASS' if adequate else 'NOT ASSESSED'}")
    print(f"MECHANISM: {'SUPPORTED' if mechanism else ('NOT ESTABLISHED' if adequate else 'NOT ASSESSED')}")

    print("\nDESCRIPTIVE BREAKDOWN — no subgroup p-values")
    print(f"{'group':<29}{'touch':<8}{'n':>7}{'days':>7}{'excess':>11}{'net1x':>11}")
    for col in ("family", "response"):
        for name, g in matched.groupby(col):
            for touch, lab in ((0, "first"), (1, "second"), (2, "third+")):
                z = g[g.touch == touch]
                ex = clustered_mean(z.excess.to_numpy(), z.day.to_numpy())[0]
                ne = clustered_mean(z["net_1"].to_numpy(), z.day.to_numpy())[0]
                print(f"{col+'='+str(name):<29}{lab:<8}{len(z):7,d}{z.day.nunique():7,d}{_fmt(ex):>11}{_fmt(ne):>11}")

    first = matched[matched.touch == 0]
    ex_first = float(first.excess.mean()) if len(first) else np.nan
    net1, se1, lo1 = clustered_mean(first["net_1"].to_numpy(), first.day.to_numpy())
    net15 = clustered_mean(first["net_1.5"].to_numpy(), first.day.to_numpy())[0]
    shadow = (mechanism and len(first) >= 100 and first.day.nunique() >= 50
              and ex_first > 0 and net1 >= .05 and net15 >= .05 and lo1 > 0)
    print("\nFIRST-TOUCH FORWARD-SHADOW GATES")
    print(f"n {len(first):,} / 100  days {first.day.nunique():,} / 50  excess {_fmt(ex_first)}")
    print(f"net 1x {_fmt(net1)}  95% lower {_fmt(lo1)}  net 1.5x {_fmt(net15)}")
    print(f"VERDICT: {'FORWARD SHADOW ONLY' if shadow else 'NO CANDIDATE'}")

    # Dependence and execution diagnostics required by the amendment.
    dup = int(df.duplicated(["entry_i", "direction", "response"], keep=False).sum())
    print("\nDEPENDENCE / EXECUTION DIAGNOSTICS")
    print(f"rows sharing entry+direction+response {dup:,}")
    print(f"swap crossings {int(df.nights.sum()):,} across {int((df.nights>0).sum()):,} events")
    print("directions " + "  ".join(f"{int(k):+d}:{v:,}" for k, v in df.direction.value_counts().items()))
    pol = one_position(matched)
    pnet = clustered_mean(pol["net_1"].to_numpy(), pol.day.to_numpy())[0]
    print(f"secondary one-position policy n {len(pol):,}  days {pol.day.nunique():,}  net1x {_fmt(pnet)}")
    print("\nสถานะเครื่องยนต์: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
