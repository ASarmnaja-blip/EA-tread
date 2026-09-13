#!/usr/bin/env python3
"""The unconstrained search: every timeframe, every parameter, unlimited hold,
overlapping trades allowed, and every filter combination on top.

WHAT WAS UNLOCKED AND WHY IT MATTERS
  Previous sweeps froze the rule (20-bar lookback, 0.1 ATR buffer, range-edge
  stop, 2R target, 24-bar hold cap, no overlapping trades) and searched only
  which FILTERS were on. Four of those constraints are now searched too:

    hold cap        the frozen 24 bars turned out to dominate the frozen rule -
                    74.1% of its trades exited on the clock, only 6.2% ever
                    reached the 2R target. A 2R target that is almost never
                    touched is not a target, it is decoration. Holds up to
                    1000 bars are searched, which at H1 is six weeks.
    target          1R through 5R, and "no target at all"
    stop            the range edge, or 1/2/3 x ATR
    lookback        10 through 160 bars, and the breakout buffer 0 to 0.25 ATR
    overlap         allowed - a second signal no longer waits for the first
                    trade to close

THE TWO THINGS THAT MAKE THIS HONEST RATHER THAN A NOISE MACHINE

  1. OVERLAPPING TRADES INFLATE t, AND THE CORRECTION IS NOT OPTIONAL.
     Two trades that share holding time share price path, so they are not two
     independent observations. The naive per-trade t rises with overlap even
     when nothing real is there. Stage 3 therefore scores leaders with a BLOCK
     BOOTSTRAP whose block length is set from the actual holding period, which
     keeps correlated trades inside the same resample unit.

  2. TUNING EVERYTHING REQUIRES DATA THE TUNING NEVER SAW.
     With this many knobs the winner of any in-sample search is, by
     construction, whatever fits that sample best. So the record is split
     ONCE, before anything runs: DISCOVERY 2004-2018 for the entire search,
     HOLDOUT 2019-2026 touched exactly once at the end, on the single
     surviving configuration. A holdout looked at more than once stops being
     one.

ARCHITECTURE - THREE STAGES, BECAUSE THE FULL PRODUCT IS UNCOMPUTABLE
  Searching every rule x every exit x every filter subset at once is billions
  of backtests. Instead:
    Stage 1  rule x exit grid, no filters. One forward walk per rule records
             the first-hit bar for the stop and for EVERY candidate target,
             plus the close at every candidate horizon - so all 36 exit
             combinations are derived from one walk instead of 36.
    Stage 2  the leading base rules get the full filter-subset sweep, pruned
             on sample size the same way as before.
    Stage 3  the leaders face the matched control, the block bootstrap, and
             finally the untouched holdout.

  k is accumulated across all three stages and the noise bar is sqrt(2 ln k)
  computed from the real total, not from one stage.

CALIBRATION FIRST, AS ALWAYS
  The whole pipeline runs on a driftless random walk before it runs on gold.
  This repo has caught 8 bugs that way, the most recent of which faked a
  t +14.99 on M1. A search this large would manufacture far worse.
"""
import argparse, heapq, math, sys, pathlib, time, itertools
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from exec_engine import execute, plan_from_signal, REASON, GAP_SKIP
from split_guard import Split, purge, Thresholds, window_pool

# ----------------------------------------------------------------- config --
COMMISSION   = 0.07
ATR_N        = 14
MIN_RISK_COST = 3.0          # risk must clear 3x round-trip cost (bug #8 fix)
MIN_STOP_ATR, MAX_STOP_ATR = 0.25, 8.0

LOOKBACKS = (10, 20, 40, 80, 160)
BUFFERS   = (0.0, 0.1, 0.25)
STOPS     = ("range", "atr1", "atr2", "atr3")
TPS       = (1.0, 1.5, 2.0, 3.0, 5.0, None)      # None = no target
HOLDS     = (12, 24, 48, 96, 240, 1000)          # 1000 at H1 ~ six weeks

DISCOVERY_END = "2019-01-01"    # everything before this is searchable
MIN_N_BASE    = 200             # base rule needs this many trades
MIN_N_FILTER  = 150             # filtered subset floor
MAX_DEPTH     = 6
TOP_BASE      = 12              # base rules promoted to the filter sweep
MAX_SUBSETS   = 400_000         # per base rule; 31 filters at depth 8 can
                                # otherwise reach millions of subsets, and a
                                # cap that binds is reported rather than
                                # silently shrinking the search
TOP_LEADERS   = 15              # leaders promoted to stage 3
LEADER_POOL   = 300             # bounded heap; appending every tested subset
                                # is what exhausted memory - 400k subsets x 12
                                # base rules is ~5M records kept alive for no
                                # reason, since only the best handful are ever
                                # promoted
SEED          = 17

# ------------------------------------------------------------------ prep --
def prep(m):
    o, h, l, c = (m[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = pd.Series(c).shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1 / ATR_N, adjust=False).mean().to_numpy()
    return dict(o=o, h=h, l=l, c=c, A=A, N=len(c), idx=m.index,
                spread=m.spread.to_numpy(float), vol=m.volume.to_numpy(float))

def rolling_edges(P, look):
    h = pd.Series(P["h"]).rolling(look).max().shift(1).to_numpy()
    l = pd.Series(P["l"]).rolling(look).min().shift(1).to_numpy()
    return h, l

# ------------------------------------------------------- one walk per rule --
# WHY THE RECORDED WALK EXISTS, AND WHY IT IS SAFE
#
#   The search prices 36 (target, hold) pairs per base rule. Calling
#   exec_engine.execute() once per pair per signal is 36x the work and the
#   sweep does not finish. So each signal is walked ONCE and every event that
#   any (target, hold) pair could need is recorded; outcome() then resolves a
#   pair by arithmetic.
#
#   That is only legitimate if the recorded walk is the SAME FUNCTION as
#   exec_engine.execute(). It is not enough to believe that. test_walk_
#   equivalence.py asserts it: on random paths, every signal, every target,
#   every hold, outcome() must return exactly what execute() returns - the
#   same R, the same exit price, the same exit bar, the same skip decision.
#   The matched control calls execute() directly, so strategy and control are
#   measured by one set of rules, which is what the review demanded.
#
#   EVENT ORDER. execute() checks, per bar: stop-at-open, target-at-open,
#   stop-intrabar, target-intrabar, and returns on the first hit. The recorded
#   walk reproduces that ordering by timestamping an at-open fill at
#   step - 0.5 and an intrabar fill at step, with the stop winning ties. A bar
#   that opens through the target therefore fills at that open even if the same
#   bar later trades through the stop, which is what actually happens.
#
#   ENTRY GAP. If the entry bar's open is already beyond the stop, or already
#   beyond a target, the plan was void before it could be placed and the trade
#   is SKIPPED (exec_engine's declared default). The stop gap is one flag; the
#   target gap depends on the multiple, so it is one flag PER target.
def walk_rule(P, look, buf, stop_mode, cost, hold_max):
    """Resolve every signal of one base rule ONCE, recording enough to derive
    any (target, hold) pair afterwards.

    Returns arrays aligned per candidate trade:
      i, d, risk, entry, stop, cost
      t_stop, p_stop          when the stop filled (half-step = at an open)
      t_tp[j], p_tp[j]        same for each target multiple in TPS
      c_at[k]                 close price at each horizon in HOLDS
      g_stop                  entry bar opened beyond the stop -> skip
      g_tp[j]                 entry bar opened beyond target j -> skip
    """
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    ph, pl = rolling_edges(P, look)
    tps = [t for t in TPS if t is not None]
    out = {k: [] for k in ("i", "d", "risk", "entry", "stop", "t_stop",
                           "p_stop", "g_stop")}
    out["t_tp"] = [[] for _ in tps]; out["p_tp"] = [[] for _ in tps]
    out["g_tp"] = [[] for _ in tps]
    out["c_at"] = [[] for _ in HOLDS]

    start = max(look, ATR_N) + 5
    for i in range(start, N - 1):
        a = A[i]
        if not np.isfinite(a) or a <= 0: continue
        up = c[i] > ph[i] + buf * a
        dn = c[i] < pl[i] - buf * a
        if not (up or dn): continue
        d = 1 if up else -1
        e = i + 1
        cst = float(cost[e]) if e < len(cost) else float(cost[-1])
        # the plan is the SAME function the control and the unit tests use
        plan = plan_from_signal(c[i], a, ph[i], pl[i], d, stop_mode, buf,
                                None, MIN_STOP_ATR, MAX_STOP_ATR,
                                MIN_RISK_COST, cst)
        if plan is None: continue
        stop, risk, _ = plan
        entry = o[e]
        if not np.isfinite(entry): continue

        # targets are frozen at the SIGNAL close, exactly as plan_from_signal
        # computes them - not at the fill, which the strategy cannot know yet
        tp_px = [c[i] + d * t * risk for t in tps]

        g_stop = bool((entry <= stop) if d > 0 else (entry >= stop))
        g_tp = [bool((entry >= px) if d > 0 else (entry <= px)) for px in tp_px]

        t_stop, p_stop = np.inf, np.nan
        t_tp = [np.inf] * len(tps); p_tp = [np.nan] * len(tps)
        c_at = [np.nan] * len(HOLDS)
        limit = min(e + hold_max, N)
        for k in range(e, limit):
            step = k - e + 1
            if k > e:
                # an open already beyond a bracket fills AT THAT OPEN, and does
                # so BEFORE anything the same bar reaches intrabar
                if t_stop == np.inf and ((o[k] <= stop) if d > 0 else (o[k] >= stop)):
                    t_stop, p_stop = step - 0.5, o[k]
                for j, px in enumerate(tp_px):
                    if t_tp[j] == np.inf and ((o[k] >= px) if d > 0 else (o[k] <= px)):
                        t_tp[j], p_tp[j] = step - 0.5, o[k]
            if t_stop == np.inf and ((l[k] <= stop) if d > 0 else (h[k] >= stop)):
                t_stop, p_stop = step, stop
            for j, px in enumerate(tp_px):
                if t_tp[j] == np.inf and ((h[k] >= px) if d > 0 else (l[k] <= px)):
                    t_tp[j], p_tp[j] = step, px
            for hi, hh in enumerate(HOLDS):
                if step == hh: c_at[hi] = c[k]
            if t_stop != np.inf and all(t != np.inf for t in t_tp):
                if step >= max(HOLDS): break
        # horizons beyond the data end fall back to the last available close,
        # matching execute()'s last = min(e + hold, N)
        last_c = c[min(limit - 1, N - 1)]
        for hi in range(len(HOLDS)):
            if not np.isfinite(c_at[hi]): c_at[hi] = last_c

        out["i"].append(i); out["d"].append(d); out["risk"].append(risk)
        out["entry"].append(entry); out["stop"].append(stop)
        out["t_stop"].append(t_stop); out["p_stop"].append(p_stop)
        out["g_stop"].append(g_stop)
        for j in range(len(tps)):
            out["t_tp"][j].append(t_tp[j]); out["p_tp"][j].append(p_tp[j])
            out["g_tp"][j].append(g_tp[j])
        for hi in range(len(HOLDS)):
            out["c_at"][hi].append(c_at[hi])

    if not out["i"]: return None
    skip = ("t_tp", "p_tp", "c_at", "g_tp")
    W = {k: np.asarray(v, float) for k, v in out.items() if k not in skip}
    W["i"] = W["i"].astype(int)
    W["g_stop"] = W["g_stop"].astype(bool)
    W["t_tp"] = np.asarray(out["t_tp"], float)
    W["p_tp"] = np.asarray(out["p_tp"], float)
    W["g_tp"] = np.asarray(out["g_tp"], bool)
    W["c_at"] = np.asarray(out["c_at"], float)
    W["cost"] = cost[np.minimum(W["i"] + 1, P["N"] - 1)]
    # bars actually available after entry. A trade opened near the end of the
    # data cannot hold for its full horizon: execute() stops at the last bar,
    # so a time exit there is held for `room` bars, not `hold`. Recording this
    # is what makes the two implementations agree at the right-hand edge -
    # the equivalence test found the disagreement before this line existed.
    W["room"] = (P["N"] - (W["i"] + 1)).astype(float)
    return W

# arrays that are indexed [target_or_hold, trade] rather than [trade]
STACKED = ("t_tp", "p_tp", "c_at", "g_tp")

def subset(W, keep):
    """Slice a recorded walk down to a subset of its trades."""
    return {k: (v[..., keep] if k in STACKED else v[keep]) for k, v in W.items()}

def outcome(W, tp_j, hold_k):
    """Derive one (target, hold) pair from the recorded walk.

    Returns (R, held, ok). `ok` is False where the entry bar gapped through a
    bracket and the trade is skipped; R and held are NaN there. Callers must
    mask by `ok` - a skipped trade is not a zero, it is an absence."""
    hold = HOLDS[hold_k]
    t_stop = W["t_stop"]
    n = len(t_stop)
    if tp_j is None:
        t_tp = np.full(n, np.inf); p_tp = np.full(n, np.nan)
        ok = ~W["g_stop"]
    else:
        t_tp = W["t_tp"][tp_j]; p_tp = W["p_tp"][tp_j]
        ok = ~W["g_stop"] & ~W["g_tp"][tp_j]
    stop_ok = t_stop <= hold
    tp_ok = t_tp <= hold
    use_tp = tp_ok & (~stop_ok | (t_tp < t_stop))
    use_st = stop_ok & ~use_tp
    exit_px = np.where(use_tp, p_tp, np.where(use_st, W["p_stop"],
                                              W["c_at"][hold_k]))
    # a half-step fill happened on the bar it half-indexes: ceil it back
    time_held = np.minimum(float(hold), W["room"])
    held = np.where(use_tp, np.ceil(t_tp),
                    np.where(use_st, np.ceil(t_stop), time_held))
    R = ((exit_px - W["entry"]) * W["d"] - W["cost"]) / W["risk"]
    R = np.where(ok, R, np.nan)
    held = np.where(ok, held, np.nan)
    return R, held, ok

def exit_bars(W, held):
    """Absolute bar index each trade exits on: entry bar + held - 1."""
    return (W["i"] + held).astype(float)

# --------------------------------------------------------------- filters --
# THE SECOND LEAK, AND WHY IT WAS SUBTLE
#
#   The old build_filters took the median of spread, volume and efficiency over
#   the WHOLE series. Nothing about that looks like cheating - a median is not
#   an outcome - but "below median spread" in 2012 was then a statement about
#   where 2019-2026's spreads would land. The discovery period was being
#   filtered with a number that could not have existed at the time.
#
#   Recomputing the median separately per period does not fix it either: that
#   makes discovery and holdout two different strategies and the holdout stops
#   being a test of the thing that was found. The fix is the one a live system
#   is forced into: FIT ONCE ON DISCOVERY, FREEZE, and carry the same number
#   into the holdout however badly it fits there.
#
#   bar_features() is also cached on P. The old code rebuilt every indicator -
#   ADX, MACD, stochastic, a daily resample - on every call, and stage 3 calls
#   it once per leader.
def bar_features(P):
    """Every per-bar indicator, full length, computed once and cached."""
    if "_feat" in P:
        return P["_feat"]
    c, h, l, o, A, N = P["c"], P["h"], P["l"], P["o"], P["A"], P["N"]
    idx = P["idx"]
    S = pd.Series(c)

    f = {}
    for n in (20, 50, 200):
        f[f"ema{n}"] = S.ewm(span=n, adjust=False).mean().shift(1).to_numpy()
    f["atr_slow"] = pd.Series(A).rolling(50).mean().shift(1).to_numpy()
    f["atr_pct"] = pd.Series(A).rolling(500).rank(pct=True).shift(1).to_numpy()

    # daily trend, forward-filled without look-ahead
    dly = pd.Series(c, index=idx).resample("1D").last().dropna()
    d_ema = dly.ewm(span=20, adjust=False).mean().shift(1)
    d_ema.index = d_ema.index + pd.Timedelta(days=1)
    f["d_tr"] = d_ema.reindex(idx, method="ffill").to_numpy()

    up_m = pd.Series(h).diff(); dn_m = -pd.Series(l).diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_s = pd.Series(A)
    pdi = 100 * pd.Series(plus).ewm(alpha=1/14, adjust=False).mean() / atr_s
    mdi = 100 * pd.Series(minus).ewm(alpha=1/14, adjust=False).mean() / atr_s
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    f["adx"] = dx.ewm(alpha=1/14, adjust=False).mean().shift(1).to_numpy()

    macd = (S.ewm(span=12, adjust=False).mean() - S.ewm(span=26, adjust=False).mean())
    f["macd_h"] = (macd - macd.ewm(span=9, adjust=False).mean()).shift(1).to_numpy()

    lo14 = pd.Series(l).rolling(14).min(); hi14 = pd.Series(h).rolling(14).max()
    f["stoch"] = (100 * (S - lo14) / (hi14 - lo14).replace(0, np.nan)).shift(1).to_numpy()

    sma20 = S.rolling(20).mean(); sd20 = S.rolling(20).std()
    f["bb_pos"] = ((S - sma20) / (2 * sd20).replace(0, np.nan)).shift(1).to_numpy()

    dif = S.diff()
    up_e = dif.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn_e = (-dif.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    f["rsi"] = (100 - 100 / (1 + up_e / dn_e.replace(0, np.nan))).shift(1).to_numpy()

    f["roc"] = S.pct_change(20).shift(1).to_numpy()
    f["body"] = np.abs(c - o) / np.maximum(h - l, 1e-9)
    f["gap"] = (o - pd.Series(c).shift(1).to_numpy()) / np.maximum(A, 1e-9)
    move = np.abs(S.diff(20).to_numpy())
    pth = pd.Series(np.abs(dif.to_numpy())).rolling(20).sum().to_numpy()
    f["eff"] = move / np.maximum(pth, 1e-9)
    sgn = np.sign(dif.fillna(0))
    f["streak"] = pd.Series(sgn).groupby(
        (sgn != sgn.shift()).cumsum()).cumcount().shift(1).to_numpy()

    tp_px = (h + l + c) / 3.0
    day_id = pd.Series(idx.normalize())
    vwap = (pd.Series(tp_px * P["vol"]).groupby(day_id).cumsum() /
            pd.Series(P["vol"]).groupby(day_id).cumsum().replace(0, np.nan)).shift(1).to_numpy()
    f["vw_d"] = (c - vwap) / np.maximum(A, 1e-9)

    f["hour"] = idx.hour.to_numpy(); f["dow"] = idx.dayofweek.to_numpy()
    P["_feat"] = f
    return f

# the three filters whose cut-point is a fitted quantity rather than a constant
FITTED = ("eff", "spread", "vol")

def fit_thresholds(P, split):
    """The only place a median is allowed to be computed, and it reads
    discovery bars only."""
    f = bar_features(P)
    return Thresholds().fit({"eff": f["eff"], "spread": P["spread"],
                             "vol": P["vol"]}, split)

def build_filters(P, W, th):
    """The filter library. `th` must be a Thresholds already fitted on
    discovery; passing an unfitted one raises rather than leaking."""
    c, A = P["c"], P["A"]
    f = bar_features(P)
    i = W["i"]; d = W["d"].astype(int)
    spread = P["spread"]; vol = P["vol"]
    hour, dow = f["hour"], f["dow"]

    F = {
        "trend20_agrees":   d * (c[i] - f["ema20"][i]) > 0,
        "trend50_agrees":   d * (c[i] - f["ema50"][i]) > 0,
        "trend200_agrees":  d * (c[i] - f["ema200"][i]) > 0,
        "daily_trend_agrees": d * (c[i] - f["d_tr"][i]) > 0,
        "atr_contracting":  A[i] <= f["atr_slow"][i],
        "atr_expanding":    A[i] > f["atr_slow"][i],
        "vol_pct_low":      f["atr_pct"][i] <= 0.33,
        "vol_pct_high":     f["atr_pct"][i] >= 0.67,
        "adx_strong":       f["adx"][i] > 25,
        "adx_weak":         f["adx"][i] <= 25,
        "macd_agrees":      d * f["macd_h"][i] > 0,
        "stoch_agrees":     ((f["stoch"][i] > 50) & (d > 0)) | ((f["stoch"][i] < 50) & (d < 0)),
        "stoch_not_extreme": (f["stoch"][i] > 20) & (f["stoch"][i] < 80),
        "bb_inside":        np.abs(f["bb_pos"][i]) < 1.0,
        "bb_beyond":        np.abs(f["bb_pos"][i]) >= 1.0,
        "rsi_agrees":       ((f["rsi"][i] > 50) & (d > 0)) | ((f["rsi"][i] < 50) & (d < 0)),
        "rsi_not_extreme":  (f["rsi"][i] > 25) & (f["rsi"][i] < 75),
        "roc_agrees":       d * f["roc"][i] > 0,
        "efficiency_high":  f["eff"][i] > th["eff"],
        "body_strong":      f["body"][i] > 0.5,
        "no_gap":           np.abs(f["gap"][i]) < 0.5,
        "vwap_agrees":      d * f["vw_d"][i] > 0,
        "streak_short":     f["streak"][i] <= 2,
        "spread_tight":     spread[i] <= th["spread"],
        "volume_high":      vol[i] > th["vol"],
        "london":           (hour[i] >= 7) & (hour[i] < 12),
        "newyork":          (hour[i] >= 12) & (hour[i] < 18),
        "not_asia":         (hour[i] >= 7) & (hour[i] < 21),
        "early_week":       dow[i] <= 2,
        "long_side":        d > 0,
        "short_side":       d < 0,
    }
    return {k: np.nan_to_num(v, nan=0).astype(bool) for k, v in F.items()}

# ---------------------------------------------------------------- scoring --
def naive_t(R):
    """A per-trade t, WINSORIZED at the 1st/99th percentile first.

    Found by an independent sanity check, not by calibration: a stop-only
    design with no target (tp=None) and a long hold has capped downside
    (near -1R) but UNCAPPED upside - over up to 1000 bars a pure martingale's
    range grows like sqrt(steps), so a small fraction of trades reach R of
    +15 to +20 purely from random walk range expansion, nothing to do with
    drift. Median R on synthetic noise was -1.04 (as expected - most trades
    hit their stop) while the raw mean read +0.12 at a naive t of +4.65,
    entirely because roughly 0.5% of trades in the far right tail dragged it
    there. The optional stopping theorem still guarantees E[R]=0 in the
    limit, but the empirical mean's SAMPLING VARIANCE is dominated by that
    tail, and a t-test that assumes roughly normal errors is not valid on it -
    a few lucky excursions can manufacture apparent significance that has
    nothing to do with any rule's skill. Winsorizing bounds the influence any
    single trade can have on the statistic used to rank candidates; stage 3's
    block bootstrap is the real arbiter for anything promoted this way, since
    resampling on the actual (fat-tailed) distribution is honest where a
    parametric t is not."""
    if len(R) < 20: return float("nan")
    lo, hi = np.percentile(R, [1, 99])
    Rw = np.clip(R, lo, hi)
    sd = Rw.std(ddof=1)
    return Rw.mean() / (sd / math.sqrt(len(Rw))) if sd > 0 else float("nan")

def block_bootstrap_ci(R, entry_idx, held, reps=2000, seed=SEED):
    """PERCENTILE block bootstrap: a 95% interval for the mean of R.

    Chosen over a t-ratio because `metric_audit.py` measured both on data
    whose true mean is known to be zero:
        naive per-trade t, fat-tailed book      18.4% false positives
        percentile bootstrap, same data          5.3%
        naive t, overlapping trades             70.7%
        block bootstrap t, same data            10.3%
        percentile BLOCK bootstrap, both         0.5%
    Blocks handle the overlap; the percentile form handles the fat tail that a
    stop-loss book always has. The combination is conservative - it will miss
    real effects before it invents one - which is the correct direction to err
    for a gate, given how much of this program has been spent retracting
    effects that were never there.

    Returns (lo, hi) of the 95% interval, or None when there are too few
    blocks to resample honestly."""
    if len(R) < 30: return None
    span = max(int(np.nanmedian(held)) * 2, 10)
    block = np.maximum(entry_idx // span, 0).astype(int)
    uniq = np.unique(block)
    if len(uniq) < 8: return None
    groups = [R[block == b] for b in uniq]
    rng = np.random.default_rng(seed)
    means = np.empty(reps)
    for r in range(reps):
        pick = rng.integers(0, len(groups), len(groups))
        means[r] = np.concatenate([groups[p] for p in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

def block_bootstrap_t(R, entry_idx, held, bar_minutes, reps=2000, seed=SEED):
    """Overlap-aware significance. Trades are grouped into contiguous blocks
    long enough to contain a full holding period, so trades that share price
    path stay in the same resample unit. Returns the observed mean divided by
    the bootstrap standard error - directly comparable to a t."""
    if len(R) < 30: return float("nan")
    span = max(int(np.nanmedian(held)) * 2, 10)
    block = np.maximum(entry_idx // span, 0)
    uniq = np.unique(block)
    if len(uniq) < 8: return float("nan")
    groups = [R[block == b] for b in uniq]
    rng = np.random.default_rng(seed)
    means = np.empty(reps)
    for r in range(reps):
        pick = rng.integers(0, len(groups), len(groups))
        means[r] = np.concatenate([groups[p] for p in pick]).mean()
    se = means.std(ddof=1)
    return R.mean() / se if se > 0 else float("nan")

def matched_control(P, W, tp_j, hold_k, split, side, reps=6, seed=SEED):
    """The strategy's timing, replaced by random timing. Everything else held
    identical - and 'identical' now means the same function, not a second
    implementation that agrees in spirit.

    WHAT THE REVIEW FOUND WRONG WITH THE OLD ONE, AND WHAT CHANGED

      same execution   the old control had its own inline loop, which expired
                       at c[e + hold] while the strategy expired at the close
                       of bar e + hold - 1. One free bar on every control
                       trade. It now calls exec_engine.execute(), the same
                       function the strategy is proven equivalent to, so the
                       expiry bar, the gap handling and the stop-wins-ties
                       rule cannot drift apart again.
      its own cost     the old control charged the ORIGINAL SIGNAL's spread to
                       a trade placed at a completely different time. A
                       control drawn into a wide-spread hour must pay that
                       hour's spread, or the comparison quietly favours
                       whichever side was sampled in the cheaper regime.
                       execute() takes the cost from its own entry bar.
      its own side     the old pool was np.arange(ATR_N + 200, N - ...), the
                       WHOLE history, so a discovery-period control could be
                       priced on holdout bars. window_pool() confines it.
      plan shape       the control's stop sits `risk` away from ITS OWN bar's
                       close and its target `tp_mult * risk` beyond that -
                       the same construction the strategy uses, so the two
                       differ in when they trade and in nothing else.

    Returns (R, stats). stats carries what the review asked to see: how many
    control trades there actually are, the long/short mix, and the hold
    duration, so a reader can check the match instead of taking it on faith."""
    rng = np.random.default_rng(seed)
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    cost = P["spread"] + COMMISSION
    hold = HOLDS[hold_k]
    tp_mult = None if tp_j is None else [t for t in TPS if t is not None][tp_j]
    n = len(W["i"])
    if n == 0:
        return np.array([]), dict(n=0, long_frac=float("nan"),
                                  mean_held=float("nan"), skipped=0, pool=0)
    # hi_pad keeps the WHOLE trade inside its own side: a control drawn at the
    # last eligible bar still resolves without borrowing a bar from across
    # the line, which is the entire point of the guard.
    pool = window_pool(split, side, lo_pad=ATR_N + 200, hi_pad=hold + 2)
    if len(pool) < 50:
        return np.array([]), dict(n=0, long_frac=float("nan"),
                                  mean_held=float("nan"), skipped=0,
                                  pool=len(pool))
    dirs = W["d"].astype(int); risks = W["risk"]
    Rs, helds, longs, skipped = [], [], 0, 0
    for rep in range(reps):
        take = min(n, len(pool))
        pick = rng.choice(pool, size=take, replace=False)
        # pair each drawn bar with a real trade's (direction, risk) without
        # replacement, so the long/short mix is carried over exactly rather
        # than re-derived from whatever the random bars happen to break
        order = rng.permutation(n)[:take]
        for j, b in enumerate(pick):
            q = int(order[j])
            d = int(dirs[q]); risk = float(risks[q])
            a = A[b]
            if not np.isfinite(a) or a <= 0 or risk <= 0:
                skipped += 1; continue
            c_sig = c[b]
            stop = c_sig - d * risk
            targ = None if tp_mult is None else c_sig + d * tp_mult * risk
            t = execute(o, h, l, c, N, int(b), d, stop, risk, targ, hold, cost,
                        on_gap="skip")
            if t is None or t["reason"] == GAP_SKIP:
                skipped += 1; continue
            Rs.append(t["R"]); helds.append(t["held"])
            longs += 1 if d > 0 else 0
    R = np.asarray(Rs, float)
    stats = dict(n=len(R), long_frac=(longs / len(R)) if len(R) else float("nan"),
                 mean_held=float(np.mean(helds)) if helds else float("nan"),
                 skipped=skipped, pool=len(pool), reps=reps)
    return R, stats

# --------------------------------------------------------------- the run --
def load_tf(tf):
    if tf == "1h":
        return D.clean(D.mid(D.load_h1(2003, 2026)))
    cache = pathlib.Path(__file__).parent / ".cache_duka"
    parts = [p for p in sorted(cache.glob("XAUUSD_M1_*.parquet")) if "recent" not in p.name]
    if not parts: raise SystemExit("no M1 cache")
    frames = []
    for p in parts:
        df = pd.read_parquet(p)
        frames.append(D.mid(df) if "bid_close" in df.columns else df)
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    m1 = m1[(m1.volume > 0) & (m1.spread > 0)]
    return m1 if tf == "1min" else D.resample(m1, tf)

def synth(n, seed, sigma):
    """An ARITHMETIC martingale, not a geometric one.

    The first version of this used price * exp(cumsum(zero-mean steps)), which
    is driftless in LOG space and therefore has POSITIVE drift in price space,
    since E[e^X] = e^(sigma^2/2) > 1. Calibration caught it immediately: the
    breakout rule scored E +0.2893R at t +5.29 on supposedly information-free
    data. The arithmetic matches exactly - drift of sigma^2/2 per bar over a
    240-bar hold is about 0.28R at a 1xATR stop - and the mechanism is the one
    that matters here: an upward-drifting series produces more upside breakouts
    than downside, so the rule ends up net long and simply collects the drift.

    That is the same way gold's 11x rise can masquerade as skill, so the
    generator has to be a true martingale: E[P_(t+1) | P_t] = P_t exactly."""
    rng = np.random.default_rng(seed)
    step_abs = 2000.0 * sigma
    steps = rng.normal(0.0, step_abs, size=(n, 4))
    price = 2000.0
    o = np.empty(n); h = np.empty(n); lo = np.empty(n); c = np.empty(n)
    for i in range(n):
        path = price + np.cumsum(steps[i])
        o[i], h[i], lo[i], c[i] = price, max(price, path.max()), min(price, path.min()), path[-1]
        price = path[-1]
    idx = pd.date_range("2004-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c,
                         "spread": np.full(n, 0.40), "volume": np.ones(n)}, index=idx)

def resolve(W, tp_j, hold_k, split, side):
    """One (target, hold) pair, restricted to ONE SIDE of the split with
    straddling trades purged.

    THE FIRST LEAK. The old code selected discovery trades with
    `W["i"] < n_disc` - the SIGNAL index alone. At hold=1000 a trade signalled
    on the last discovery bar read a thousand holdout bars to decide its own
    outcome and still counted as a discovery result. Whether a trade straddles
    the line depends on its horizon, so the purge cannot be done once per base
    rule: it has to be done per (target, hold) pair, which is why it lives
    here rather than in stage 1's setup.

    Returns (R, held, keep, report). `keep` already excludes entry-gap skips."""
    R, held, ok = outcome(W, tp_j, hold_k)
    idx_ok = np.where(ok)[0]
    n_gap = int((~ok).sum())
    if len(idx_ok) == 0:
        return R, held, np.zeros(len(R), bool), dict(
            total=0, kept=0, straddling=0, other_side=0, gap_skipped=n_gap)
    eb = (W["i"][idx_ok] + held[idx_ok]).astype(int)
    k, rep = purge(W["i"][idx_ok], eb, split, side)
    keep = np.zeros(len(R), bool)
    keep[idx_ok[k]] = True
    rep["gap_skipped"] = n_gap
    return R, held, keep, rep

def run(m, tf, label, calib=False):
    t0 = time.time()
    P = prep(m)
    cost = P["spread"] + COMMISSION
    split = Split(P["idx"], DISCOVERY_END)
    n_disc = split.n_disc
    # Fitted ONCE, on discovery bars only, and frozen. Every "below median
    # spread" decision the search makes - in discovery and in the holdout
    # alike - uses these numbers and no others.
    th = fit_thresholds(P, split)
    print(f"{label}: {len(m):,} bars  {m.index[0].date()} -> {m.index[-1].date()}")
    print(f"  discovery {n_disc:,} bars (< {DISCOVERY_END}), "
          f"holdout {len(m)-n_disc:,} bars - holdout is opened once, at the end")
    print(f"  thresholds fitted on DISCOVERY ONLY and frozen: "
          + ", ".join(f"{k}={v:.4g}" for k, v in th.values.items()))
    print(f"  trades straddling the boundary are purged from both sides\n")

    k_total = 0
    hold_max = max(HOLDS)
    tps_real = [t for t in TPS if t is not None]
    tp_list = [None] + list(range(len(tps_real)))
    purge_tot = dict(straddling=0, gap_skipped=0, cells=0)

    # ---- stage 1: rule x exit, no filters, DISCOVERY ONLY -----------------
    print("STAGE 1  rule x exit grid, no filters")
    walks = {}
    base = []
    for look, buf, sm in itertools.product(LOOKBACKS, BUFFERS, STOPS):
        W = walk_rule(P, look, buf, sm, cost, hold_max)
        if W is None: continue
        if int((W["i"] < n_disc).sum()) < MIN_N_BASE: continue
        walks[(look, buf, sm)] = W
        for tp_j in tp_list:
            for hk in range(len(HOLDS)):
                # A stop with NO target caps the loss near -1R but leaves the
                # win side open. Over a long hold a driftless walk's range
                # grows like sqrt(steps), so a small tail of trades reaches
                # R of +15 to +20 purely from range expansion, nothing to do
                # with drift or skill. Found by an independent sanity check:
                # winsorizing the naive t at the 1st/99th percentile still left
                # many pure-noise configs scoring |t| of 5-10 at hold=1000,
                # sign essentially decided by whether that finite sample
                # happened to catch one of the rare compensating tail events.
                # A target caps BOTH sides, so this does not apply once tp_j
                # is set - only the no-target branch is restricted here.
                if tp_j is None and HOLDS[hk] > 96: continue
                R, held, keep, rep = resolve(W, tp_j, hk, split, "discovery")
                k_total += 1
                purge_tot["straddling"] += rep["straddling"]
                purge_tot["gap_skipped"] += rep["gap_skipped"]
                purge_tot["cells"] += 1
                if keep.sum() < MIN_N_BASE: continue
                r = R[keep]
                base.append((naive_t(r), r.mean(), int(keep.sum()),
                             (look, buf, sm, tp_j, hk)))
    base = [b for b in base if np.isfinite(b[0])]
    base.sort(key=lambda x: -x[0])
    print(f"  {k_total:,} rule x exit cells tested, {len(base):,} with enough trades")
    print(f"  purged across those cells: {purge_tot['straddling']:,} straddling "
          f"trades, {purge_tot['gap_skipped']:,} entry-gap skips")
    for t, e, n, cfg in base[:6]:
        look, buf, sm, tp_j, hk = cfg
        tpname = "none" if tp_j is None else f"{tps_real[tp_j]}R"
        print(f"    t {t:+.2f}  E {e:+.4f}  n {n:>6}  look {look:>3} buf {buf} "
              f"{sm} tp {tpname} hold {HOLDS[hk]}")

    # ---- stage 2: filter sweep on the leading base rules -------------------
    print(f"\nSTAGE 2  full filter sweep on the top {TOP_BASE} base rules")
    leaders = []          # bounded min-heap of (t, tiebreak, payload)
    seq = 0
    for t, e, n, cfg in base[:TOP_BASE]:
        look, buf, sm, tp_j, hk = cfg
        W = walks[(look, buf, sm)]
        R, held, keep, rep = resolve(W, tp_j, hk, split, "discovery")
        F = build_filters(P, W, th)
        names = list(F)
        # `keep` is folded into every column, so a filter subset can only ever
        # select trades that begin and end inside discovery
        cols = np.vstack([F[nm] & keep for nm in names])
        # Masks are RECOMPUTED from the index tuples rather than stored. Holding
        # one boolean array per surviving subset was what killed the first run:
        # 31 filters at depth 8 over ten thousand trades is gigabytes of masks
        # alive at once. Tuples of small ints cost a hundred bytes each.
        def mask_of(combo):
            m = cols[combo[0]].copy()
            for j in combo[1:]: m &= cols[j]
            return m
        level = [(j,) for j in range(len(names)) if cols[j].sum() >= MIN_N_FILTER]
        tested_here = 0
        for depth in range(1, MAX_DEPTH + 1):
            if not level or tested_here >= MAX_SUBSETS: break
            for combo in level:
                k_total += 1; tested_here += 1
                r = R[mask_of(combo)]
                if len(r) < MIN_N_FILTER: continue
                tt = naive_t(r)
                if not np.isfinite(tt): continue
                seq += 1
                rec = (tt, seq, (r.mean(), len(r), cfg, combo, names))
                if len(leaders) < LEADER_POOL: heapq.heappush(leaders, rec)
                elif tt > leaders[0][0]: heapq.heapreplace(leaders, rec)
            nxt = []
            for combo in level:
                msk = mask_of(combo)
                for j in range(combo[-1] + 1, len(names)):
                    if (msk & cols[j]).sum() >= MIN_N_FILTER: nxt.append(combo + (j,))
            level = nxt
        if tested_here >= MAX_SUBSETS:
            print(f"    (subset cap hit on one base rule at {tested_here:,})")
    leaders = sorted(leaders, key=lambda x: -x[0])
    leaders = [(t, *payload) for t, _, payload in leaders]
    bar = math.sqrt(2 * math.log(max(k_total, 2)))
    print(f"  total cells tested across both stages: {k_total:,}")
    # sqrt(2 ln k) is the EXPECTED MAXIMUM of k standard normal draws. It is
    # NOT a 5% family-wise threshold: measured directly in bug_reproductions.py,
    # at least one of k noise draws exceeds it 16.5% of the time at k=1000 and
    # 18.8% at k=10000. It is reported as a rough floor, and the gate that
    # actually decides is the percentile block bootstrap.
    print(f"  heuristic noise floor from the search size: |t| > {bar:.2f} "
          f"(expected max of k noise draws; NOT a 5% family-wise bar)")
    print(f"\n  top {min(8,len(leaders))} by naive t (overlap NOT yet corrected):")
    for t, e, n, cfg, combo, names in leaders[:8]:
        look, buf, sm, tp_j, hk = cfg
        tpname = "none" if tp_j is None else f"{tps_real[tp_j]}R"
        print(f"    t {t:+.2f}  E {e:+.4f}  n {n:>5}  [look{look} {sm} tp{tpname} "
              f"hold{HOLDS[hk]}] {'+'.join(names[x] for x in combo)}")

    if calib:
        best = leaders[0][0] if leaders else float("nan")
        print(f"\n  STAGE 1-2 CALIBRATION: best naive t on pure noise = {best:+.2f} "
              f"vs heuristic floor {bar:.2f}")
        print("  (the binding calibration is the FULL pipeline through stage 3;")
        print("   see calibrate_pipeline.py, which is the one that gates.)")
        return dict(best_naive_t=best, bar=bar, leaders=leaders, walks=walks,
                    P=P, split=split, th=th, k_total=k_total)

    # ---- stage 3: control, bootstrap, then the holdout once ---------------
    print(f"\nSTAGE 3  leaders re-scored with a matched control and an "
          f"overlap-aware block bootstrap")
    print(f"  {'n':>6}{'E(R)':>9}{'naive t':>9}{'boot t':>8}{'skill':>9}"
          f"{'ctrl t':>8}{'ctrl n':>8}{'ctrl L%':>8}{'hold s/c':>11}  configuration")
    final = []
    seen = set()
    for t, e, n, cfg, combo, names in leaders:
        key = (cfg, combo)
        if key in seen: continue
        seen.add(key)
        look, buf, sm, tp_j, hk = cfg
        W = walks[(look, buf, sm)]
        R, held, keep, rep = resolve(W, tp_j, hk, split, "discovery")
        F = build_filters(P, W, th)
        nm = list(F); msk = keep.copy()
        for j in combo: msk &= F[nm[j]]
        r = R[msk]
        if len(r) < MIN_N_FILTER: continue
        bt = block_bootstrap_t(r, W["i"][msk], held[msk], 1)
        ci = block_bootstrap_ci(r, W["i"][msk], held[msk])
        ctrl, cst = matched_control(P, subset(W, msk), tp_j, hk, split, "discovery")
        if len(ctrl) < 30: continue
        sk = r.mean() - ctrl.mean()
        se = math.sqrt(r.var(ddof=1)/len(r) + ctrl.var(ddof=1)/len(ctrl))
        ct = sk / se if se > 0 else float("nan")
        tpname = "none" if tp_j is None else f"{tps_real[tp_j]}R"
        cfgs = f"look{look} buf{buf} {sm} tp{tpname} hold{HOLDS[hk]}"
        s_long = float((W["d"][msk] > 0).mean())
        s_hold = float(held[msk].mean())
        print(f"  {len(r):>6}{r.mean():>+9.4f}{t:>+9.2f}{bt:>+8.2f}"
              f"{sk:>+9.4f}{ct:>+8.2f}{cst['n']:>8}"
              f"{cst['long_frac']*100:>7.0f}%"
              f"{s_hold:>6.0f}/{cst['mean_held']:<4.0f}  {cfgs} | "
              f"{'+'.join(nm[x] for x in combo)}")
        print(f"         strategy long {s_long*100:.0f}%, control long "
              f"{cst['long_frac']*100:.0f}% | control drew from {cst['pool']:,} "
              f"discovery bars over {cst['reps']} reps, {cst['skipped']:,} "
              f"draws skipped (entry gap / no ATR)")
        ci_clear = ci is not None and ci[0] > 0
        final.append((bt, ct, r.mean(), len(r), cfg, combo, nm, ci_clear, ci))
        if len(final) >= TOP_LEADERS: break

    # THE GATE: the percentile block bootstrap's 95% interval must sit
    # entirely above zero, AND the control-adjusted skill must be positive,
    # AND the overlap-corrected t must clear the search's own noise floor. All
    # three, because each catches something the others do not.
    survivors = [f for f in final
                 if np.isfinite(f[0]) and abs(f[0]) > bar
                 and np.isfinite(f[1]) and f[1] > 0 and f[7]]
    print(f"\n  clearing all three gates (bootstrap CI above zero, positive "
          f"control-adjusted skill, |t| > {bar:.2f}): {len(survivors)}")
    if not survivors:
        print("  Nothing survives. The holdout stays closed - opening it for a")
        print("  configuration that already failed in discovery would only")
        print("  spend the one clean test this record still has.")
        print(f"\n  elapsed {time.time()-t0:.0f}s")
        return None

    # ---- the holdout, opened exactly once ---------------------------------
    bt, ct, e, n, cfg, combo, nm, _, ci = survivors[0]
    look, buf, sm, tp_j, hk = cfg
    print(f"\n  HOLDOUT - opened once, on the single best survivor only")
    W = walks[(look, buf, sm)]
    Rh, heldh, keeph, reph = resolve(W, tp_j, hk, split, "holdout")
    # the SAME frozen thresholds - not refitted on the holdout, which would
    # make this a test of a different strategy
    Fh = build_filters(P, W, th)
    mh = keeph.copy()
    for j in combo: mh &= Fh[nm[j]]
    rh = Rh[mh]
    tpname = "none" if tp_j is None else f"{tps_real[tp_j]}R"
    print(f"  config: look{look} buf{buf} {sm} tp{tpname} hold{HOLDS[hk]} | "
          f"{'+'.join(nm[x] for x in combo)}")
    print(f"  discovery : n={n:>5}  E={e:+.4f}  boot t={bt:+.2f}  ctrl t={ct:+.2f}"
          f"  bootstrap 95% CI [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    if len(rh) < 30:
        print(f"  holdout   : n={len(rh)} - too few to judge")
    else:
        bth = block_bootstrap_t(rh, W["i"][mh], heldh[mh], 1)
        cth, csh = matched_control(P, subset(W, mh), tp_j, hk, split, "holdout")
        skh = rh.mean() - cth.mean() if len(cth) >= 30 else float("nan")
        print(f"  holdout   : n={len(rh):>5}  E={rh.mean():+.4f}  boot t={bth:+.2f}"
              f"  net={rh.sum():+.1f}R  ctrl skill={skh:+.4f} (ctrl n={len(cth)})")
        agree = (rh.mean() > 0) == (e > 0) and rh.mean() > 0
        print(f"  -> {'HOLDS UP' if agree else 'DOES NOT HOLD UP'} out of sample")
    print(f"\n  elapsed {time.time()-t0:.0f}s")
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h",
                    choices=["1min", "5min", "15min", "30min", "1h"])
    ap.add_argument("--calibrate", action="store_true")
    a = ap.parse_args()
    if a.calibrate:
        run(synth(40000, 11, 0.0012), a.tf, "CALIBRATION (driftless random walk)",
            calib=True)
    else:
        run(load_tf(a.tf), a.tf, f"Real XAUUSD {a.tf}")

if __name__ == "__main__":
    main()
