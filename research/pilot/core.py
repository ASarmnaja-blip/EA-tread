"""
Pilot engine: indicators, the 18 registered setups, exit resolution, matched
random controls and the statistics.

Every rule here is fixed by docs/PILOT_PREREGISTRATION.md. Nothing in this file
may be changed after a result has been seen; a change is a new registered
configuration, not an edit.
"""
from __future__ import annotations

import datetime as dt
import numpy as np

from data import Bars

# ---------------------------------------------------------------- costs
SPREAD = 0.48          # $/oz, OANDA measured spot mean - an ASSUMPTION here
SLIPPAGE = 0.10        # $/oz per fill, one COMEX tick - an ASSUMPTION
COST_ROUND_TURN = SPREAD + 2 * SLIPPAGE      # $0.68

TIME_STOP_15M = 24                 # bars
TIME_STOP_5M = TIME_STOP_15M * 3   # 72 five-minute bars

# session buckets, UTC. CME gold reopens 22:00 UTC; 21:00-22:00 is the
# maintenance break and is never traded.
BREAK_HOUR = 21


def session_of(ts: int) -> str:
    h = dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).hour
    if h == BREAK_HOUR:
        return "BREAK"
    if 7 <= h < 13:
        return "LONDON"
    if 13 <= h < 21:
        return "NY"
    return "ASIA"


# ------------------------------------------------------------ indicators
def ema(x: np.ndarray, span: int) -> np.ndarray:
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(b: Bars, period: int = 14) -> np.ndarray:
    pc = np.concatenate(([b.c[0]], b.c[:-1]))
    tr = np.maximum(b.h - b.l, np.maximum(np.abs(b.h - pc), np.abs(b.l - pc)))
    out = np.empty_like(tr)
    out[0] = tr[0]
    a = 1.0 / period
    for i in range(1, len(tr)):
        out[i] = a * tr[i] + (1 - a) * out[i - 1]
    return out


def rolling_pct_rank(x: np.ndarray, window: int) -> np.ndarray:
    """Percentile rank of x[i] within the PRIOR `window` values (excludes i)."""
    out = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        w = x[i - window:i]
        out[i] = 100.0 * np.count_nonzero(w < x[i]) / window
    return out


def rolling_max(x: np.ndarray, window: int) -> np.ndarray:
    """max over the PRIOR `window` bars, excluding the current one."""
    out = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        out[i] = x[i - window:i].max()
    return out


def rolling_min(x: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        out[i] = x[i - window:i].min()
    return out


def session_vwap(b: Bars) -> tuple[np.ndarray, np.ndarray]:
    """VWAP and its volume-weighted sd, anchored at 22:00 UTC each day."""
    tp = (b.h + b.l + b.c) / 3.0
    vol = np.where(b.v > 0, b.v, 1.0)
    vwap = np.empty(len(b))
    sd = np.empty(len(b))
    spv = svv = sv = 0.0
    prev_anchor = None
    for i in range(len(b)):
        d = dt.datetime.fromtimestamp(int(b.t[i]), dt.timezone.utc)
        anchor = (d - dt.timedelta(hours=22)).date()
        if anchor != prev_anchor:
            spv = svv = sv = 0.0
            prev_anchor = anchor
        spv += tp[i] * vol[i]
        svv += tp[i] * tp[i] * vol[i]
        sv += vol[i]
        m = spv / sv
        var = max(svv / sv - m * m, 0.0)
        vwap[i] = m
        sd[i] = np.sqrt(var)
    return vwap, sd


class Ctx:
    """Everything a setup may read, all of it from CLOSED 15m bars."""

    def __init__(self, b15: Bars, nxt5: np.ndarray):
        self.b = b15
        self.nxt5 = nxt5
        self.atr = atr(b15, 14)
        self.atr_pct = rolling_pct_rank(self.atr, 200)
        self.ema20 = ema(b15.c, 20)
        self.ema50 = ema(b15.c, 50)
        self.ema200 = ema(b15.c, 200)
        self.hh20 = rolling_max(b15.h, 20)
        self.ll20 = rolling_min(b15.l, 20)
        self.hh40 = rolling_max(b15.h, 40)
        self.ll40 = rolling_min(b15.l, 40)
        self.vwap, self.vwap_sd = session_vwap(b15)
        self.session = np.array([session_of(t) for t in b15.t])
        sep = np.abs(self.ema50 - self.ema200) / np.where(self.atr > 0, self.atr, np.nan)
        self.sep = sep
        # Reporting buckets only. No entry rule reads these.
        regime = np.full(len(b15), "RANGE", dtype=object)
        regime[self.atr_pct >= 80] = "HIGH_VOL"
        trend = (self.atr_pct < 80) & (sep >= 0.5)
        regime[trend] = "TREND"
        self.regime = regime
        self.warm = 200   # no signal before this index


# ------------------------------------------------------------- signals
# Each returns a list of (i, direction, stop_price, tmode, tval)
#   tmode "R"     -> tval is an R multiple
#   tmode "PRICE" -> tval is an absolute price level

def _ok(c: Ctx, i: int) -> bool:
    return i >= c.warm and c.atr[i] > 0 and np.isfinite(c.atr_pct[i])


def s1_breakout(c: Ctx, lookback=20, target=2.0, sessions=("LONDON", "NY")):
    hh = c.hh20 if lookback == 20 else c.hh40
    ll = c.ll20 if lookback == 20 else c.ll40
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] not in sessions:
            continue
        if c.atr_pct[i] < 30:                       # NO TRADE: no fuel
            continue
        a = c.atr[i]
        if np.isfinite(hh[i]) and c.b.c[i] > hh[i]:
            out.append((i, 1, c.b.c[i] - 1.5 * a, "R", target))
        elif np.isfinite(ll[i]) and c.b.c[i] < ll[i]:
            out.append((i, -1, c.b.c[i] + 1.5 * a, "R", target))
    return out


def s2_pullback(c: Ctx, anchor="ema50", target=2.0, sessions=("LONDON", "NY")):
    ref = c.ema50 if anchor == "ema50" else c.ema20
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] not in sessions:
            continue
        a = c.atr[i]
        if c.sep[i] < 0.3:                          # NO TRADE: no trend
            continue
        up = c.ema50[i] > c.ema200[i]
        if up:
            if c.b.l[i] <= ref[i] + 0.5 * a and c.b.c[i] > ref[i]:
                out.append((i, 1, c.b.c[i] - 1.5 * a, "R", target))
        else:
            if c.b.h[i] >= ref[i] - 0.5 * a and c.b.c[i] < ref[i]:
                out.append((i, -1, c.b.c[i] + 1.5 * a, "R", target))
    return out


def s3_sweep(c: Ctx, lookback=20, far_third=False, target=2.0):
    hh = c.hh20 if lookback == 20 else c.hh40
    ll = c.ll20 if lookback == 20 else c.ll40
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] == "BREAK":
            continue
        a = c.atr[i]
        rng = c.b.h[i] - c.b.l[i]
        if np.isfinite(ll[i]) and c.b.l[i] < ll[i] and c.b.c[i] > ll[i]:
            if (ll[i] - c.b.l[i]) > 1.5 * a:        # NO TRADE: too extended
                continue
            if far_third and rng > 0 and (c.b.c[i] - c.b.l[i]) / rng < 2 / 3:
                continue
            out.append((i, 1, c.b.l[i] - 0.2 * a, "R", target))
        elif np.isfinite(hh[i]) and c.b.h[i] > hh[i] and c.b.c[i] < hh[i]:
            if (c.b.h[i] - hh[i]) > 1.5 * a:
                continue
            if far_third and rng > 0 and (c.b.h[i] - c.b.c[i]) / rng < 2 / 3:
                continue
            out.append((i, -1, c.b.h[i] + 0.2 * a, "R", target))
    return out


def s4_failed(c: Ctx, lookback=20, midpoint_target=False,
              target=2.0, sessions=("LONDON", "NY")):
    hh = c.hh20 if lookback == 20 else c.hh40
    ll = c.ll20 if lookback == 20 else c.ll40
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] not in sessions:
            continue
        if c.atr_pct[i] > 90:                       # NO TRADE: chaos
            continue
        a = c.atr[i]
        broke_up = any(np.isfinite(hh[j]) and c.b.c[j] > hh[j] for j in (i - 1, i - 2, i - 3))
        broke_dn = any(np.isfinite(ll[j]) and c.b.c[j] < ll[j] for j in (i - 1, i - 2, i - 3))
        if broke_up and np.isfinite(hh[i]) and c.b.c[i] < hh[i]:
            ext = max(c.b.h[i - 3:i + 1])
            tv = (hh[i] + ll[i]) / 2.0 if midpoint_target else target
            out.append((i, -1, ext + 0.2 * a, "PRICE" if midpoint_target else "R", tv))
        elif broke_dn and np.isfinite(ll[i]) and c.b.c[i] > ll[i]:
            ext = min(c.b.l[i - 3:i + 1])
            tv = (hh[i] + ll[i]) / 2.0 if midpoint_target else target
            out.append((i, 1, ext - 0.2 * a, "PRICE" if midpoint_target else "R", tv))
    return out


def s5_vwap(c: Ctx, sigma=2.0, half_target=False):
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] == "BREAK":
            continue
        if not np.isfinite(c.sep[i]) or c.sep[i] > 1.0:   # NO TRADE: trending
            continue
        a, w, s = c.atr[i], c.vwap[i], c.vwap_sd[i]
        if s <= 0:
            continue
        if c.b.c[i] > w + sigma * s:
            tgt = w + 0.5 * s if half_target else w
            out.append((i, -1, c.b.c[i] + 1.2 * a, "PRICE", tgt))
        elif c.b.c[i] < w - sigma * s:
            tgt = w - 0.5 * s if half_target else w
            out.append((i, 1, c.b.c[i] - 1.2 * a, "PRICE", tgt))
    return out


def s6_expansion(c: Ctx, pct=25, target=2.0):
    out = []
    for i in range(c.warm, len(c.b)):
        if not _ok(c, i) or c.session[i] == "BREAK":
            continue
        prev_atr = c.atr[i - 1]
        if not np.isfinite(c.atr_pct[i - 1]) or c.atr_pct[i - 1] >= pct:
            continue
        rng = c.b.h[i] - c.b.l[i]
        if prev_atr <= 0 or rng < 2 * prev_atr:
            continue
        if rng > 4 * prev_atr:                      # NO TRADE: already spent
            continue
        pos = (c.b.c[i] - c.b.l[i]) / rng
        if pos >= 0.75:
            out.append((i, 1, c.b.c[i] - 1.5 * prev_atr, "R", target))
        elif pos <= 0.25:
            out.append((i, -1, c.b.c[i] + 1.5 * prev_atr, "R", target))
    return out


# the 18 registered configurations, in pre-registration order
REGISTRY = [
    ("S1",   "breakout continuation",        lambda c: s1_breakout(c)),
    ("S1V1", "breakout, lookback 40",        lambda c: s1_breakout(c, lookback=40)),
    ("S1V2", "breakout, target 3R",          lambda c: s1_breakout(c, target=3.0)),
    ("S2",   "trend pullback",               lambda c: s2_pullback(c)),
    ("S2V1", "pullback to EMA20",            lambda c: s2_pullback(c, anchor="ema20")),
    ("S2V2", "pullback, target 3R",          lambda c: s2_pullback(c, target=3.0)),
    ("S3",   "liquidity sweep reversal",     lambda c: s3_sweep(c)),
    ("S3V1", "sweep, lookback 40",           lambda c: s3_sweep(c, lookback=40)),
    ("S3V2", "sweep, close in far third",    lambda c: s3_sweep(c, far_third=True)),
    ("S4",   "failed breakout",              lambda c: s4_failed(c)),
    ("S4V1", "failed breakout, lookback 40", lambda c: s4_failed(c, lookback=40)),
    ("S4V2", "failed breakout, mid target",  lambda c: s4_failed(c, midpoint_target=True)),
    ("S5",   "VWAP reversion 2sd",           lambda c: s5_vwap(c)),
    ("S5V1", "VWAP reversion 2.5sd",         lambda c: s5_vwap(c, sigma=2.5)),
    ("S5V2", "VWAP reversion, half target",  lambda c: s5_vwap(c, half_target=True)),
    ("S6",   "volatility expansion",         lambda c: s6_expansion(c)),
    ("S6V1", "expansion, pct 15",            lambda c: s6_expansion(c, pct=15)),
    ("S6V2", "expansion, target 3R",         lambda c: s6_expansion(c, target=3.0)),
]
assert len(REGISTRY) == 18


# ------------------------------------------------------- exit resolution
class Trade:
    __slots__ = ("t", "dir", "risk", "gross_R", "net_R", "session",
                 "regime", "why", "bars")

    def __init__(self, t, d, risk, g, n, sess, reg, why, bars):
        self.t, self.dir, self.risk = t, d, risk
        self.gross_R, self.net_R = g, n
        self.session, self.regime, self.why, self.bars = sess, reg, why, bars


def resolve(exec_bars: Bars, k0: int, direction: int, entry: float,
            stop: float, target: float, max_bars: int) -> tuple[float, str, int]:
    """Walk forward on the execution series. The stop is tested BEFORE the
    target on every bar, so a bar that could have hit both is booked as a
    loss. That is the conservative reading and the one the research log
    settled on."""
    hi, lo = exec_bars.h, exec_bars.l
    end = min(k0 + max_bars, len(exec_bars))
    for k in range(k0, end):
        if direction > 0:
            if lo[k] <= stop:
                return stop, "stop", k - k0
            if hi[k] >= target:
                return target, "target", k - k0
        else:
            if hi[k] >= stop:
                return stop, "stop", k - k0
            if lo[k] <= target:
                return target, "target", k - k0
    j = min(end, len(exec_bars)) - 1
    return exec_bars.c[j], "time", j - k0


def run_signals(c: Ctx, signals, exec_bars: Bars, exec_nxt: np.ndarray,
                cost: float, max_exec_bars: int) -> tuple[list[Trade], dict]:
    trades = []
    skipped = {"expired": 0, "bad_risk": 0, "bad_target": 0}
    for (i, d, stop, tmode, tval) in signals:
        k = exec_nxt[i]
        if k < 0:
            skipped["expired"] += 1
            continue
        entry = exec_bars.o[k]
        risk = abs(entry - stop)
        if risk <= 1e-9:
            skipped["bad_risk"] += 1
            continue
        if (d > 0 and stop >= entry) or (d < 0 and stop <= entry):
            skipped["bad_risk"] += 1      # inverted stop - never tradeable
            continue
        target = entry + d * tval * risk if tmode == "R" else tval
        if (d > 0 and target <= entry) or (d < 0 and target >= entry):
            skipped["bad_target"] += 1
            continue
        px, why, nb = resolve(exec_bars, k, d, entry, stop, target, max_exec_bars)
        g = d * (px - entry) / risk
        trades.append(Trade(int(exec_bars.t[k]), d, risk, g, g - cost / risk,
                            c.session[i], c.regime[i], why, nb))
    return trades, skipped


# -------------------------------------------------------------- controls
def control_signals(c: Ctx, signals, exec_nxt: np.ndarray, draws: int,
                    rng: np.random.Generator):
    """Matched random control: same count, same direction mix, same session
    mix, random entry bars, identical exit logic.

    The stop is carried across in ATR units and re-expressed at the random
    bar's volatility, and a price target is carried across as its equivalent
    R multiple. Only the timing is random - the payoff shape is the setup's
    own, which is what makes the difference attributable to timing.
    """
    if not signals:
        return []
    pools: dict[str, np.ndarray] = {}
    for s in set(c.session[i] for (i, *_rest) in signals):
        idx = np.flatnonzero((c.session == s) & (exec_nxt >= 0))
        idx = idx[(idx >= c.warm) & (c.atr[idx] > 0)]
        pools[s] = idx

    out = []
    for _ in range(draws):
        for (i, d, stop, tmode, tval) in signals:
            a = c.atr[i]
            if a <= 0:
                continue
            ref = c.b.c[i]
            risk_atr = abs(ref - stop) / a
            if risk_atr <= 0:
                continue
            target_R = tval if tmode == "R" else abs(tval - ref) / abs(ref - stop)
            if not np.isfinite(target_R) or target_R <= 0:
                continue
            pool = pools.get(c.session[i])
            if pool is None or len(pool) == 0:
                continue
            j = int(pool[rng.integers(len(pool))])
            new_stop = c.b.c[j] - d * risk_atr * c.atr[j]
            out.append((j, d, new_stop, "R", target_R))
    return out


# ------------------------------------------------------------ statistics
def block_bootstrap_ci(x: np.ndarray, block: int = 12, draws: int = 2000,
                       rng: np.random.Generator | None = None,
                       alpha: float = 0.05):
    """Percentile CI on the mean from a moving-block bootstrap.

    Trades that close near each other in time share a price path, so an
    i.i.d. resample understates the interval. Blocks keep local dependence.
    """
    n = len(x)
    if n < 2:
        return (float("nan"), float("nan"))
    rng = rng or np.random.default_rng(0)
    block = max(1, min(block, n))
    nblocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(draws, nblocks))
    means = np.empty(draws)
    for d in range(draws):
        parts = [x[s:s + block] for s in starts[d]]
        means[d] = np.concatenate(parts)[:n].mean()
    return (float(np.percentile(means, 100 * alpha / 2)),
            float(np.percentile(means, 100 * (1 - alpha / 2))))


def summarise(trades: list[Trade], field: str = "net_R") -> dict:
    if not trades:
        return dict(n=0, E=float("nan"), sd=float("nan"), se=float("nan"),
                    mde=float("nan"), win=float("nan"))
    x = np.array([getattr(t, field) for t in trades], dtype=float)
    n = len(x)
    sd = float(x.std(ddof=1)) if n > 1 else float("nan")
    se = sd / np.sqrt(n) if n > 1 else float("nan")
    return dict(n=n, E=float(x.mean()), sd=sd, se=se,
                mde=2.8 * sd / np.sqrt(n) if n > 1 else float("nan"),
                win=100.0 * float((x > 0).mean()), x=x)


def skill_ci(setup_x: np.ndarray, ctl_x: np.ndarray, block: int = 12,
             draws: int = 2000, rng: np.random.Generator | None = None,
             alpha: float = 0.05):
    """Block-bootstrap CI for (setup mean - control mean).

    Both arms are resampled in blocks. Trades that close near each other share
    a price path, so treating them as independent understates the interval -
    measured at 1.1x to 3.3x too small on random-walk data, which is what made
    the first P1 run report four false failures.
    """
    rng = rng or np.random.default_rng(0)
    if len(setup_x) < 2 or len(ctl_x) < 2:
        return (float("nan"), float("nan"))

    def boot(x):
        n = len(x)
        b = max(1, min(block, n))
        nb = int(np.ceil(n / b))
        st = rng.integers(0, n - b + 1, size=(draws, nb))
        out = np.empty(draws)
        for d in range(draws):
            out[d] = np.concatenate([x[s:s + b] for s in st[d]])[:n].mean()
        return out

    diff = boot(setup_x) - boot(ctl_x)
    return (float(np.percentile(diff, 100 * alpha / 2)),
            float(np.percentile(diff, 100 * (1 - alpha / 2))))
