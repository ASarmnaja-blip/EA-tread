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
import argparse, math, sys, pathlib, time, itertools
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D

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
MAX_DEPTH     = 8
TOP_BASE      = 12              # base rules promoted to the filter sweep
MAX_SUBSETS   = 400_000         # per base rule; 31 filters at depth 8 can
                                # otherwise reach millions of subsets, and a
                                # cap that binds is reported rather than
                                # silently shrinking the search
TOP_LEADERS   = 15              # leaders promoted to stage 3
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
def walk_rule(P, look, buf, stop_mode, cost, hold_max):
    """Resolve every signal of one base rule ONCE, recording enough to derive
    any (target, hold) pair afterwards.

    Returns arrays aligned per candidate trade:
      idx, dirn, risk, entry
      t_stop, p_stop          first bar the stop filled, and at what price
      t_tp[j], p_tp[j]        same for each target multiple in TPS
      c_at[k]                 close price at each horizon in HOLDS
    """
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    ph, pl = rolling_edges(P, look)
    tps = [t for t in TPS if t is not None]
    out = {k: [] for k in ("i", "d", "risk", "entry", "t_stop", "p_stop")}
    out["t_tp"] = [[] for _ in tps]; out["p_tp"] = [[] for _ in tps]
    out["c_at"] = [[] for _ in HOLDS]

    start = max(look, ATR_N) + 5
    for i in range(start, N - 1):
        a = A[i]
        if not np.isfinite(a) or a <= 0: continue
        up = c[i] > ph[i] + buf * a
        dn = c[i] < pl[i] - buf * a
        if not (up or dn): continue
        d = 1 if up else -1
        if stop_mode == "range":
            stop = (pl[i] - buf * a) if d > 0 else (ph[i] + buf * a)
        else:
            k_atr = float(stop_mode[3:])
            stop = c[i] - d * k_atr * a
        if not np.isfinite(stop): continue
        risk = (c[i] - stop) * d
        if risk <= 0: continue
        if not (MIN_STOP_ATR * a <= risk <= MAX_STOP_ATR * a): continue
        cst = cost[i + 1] if i + 1 < N else cost[i]
        if risk < MIN_RISK_COST * cst: continue

        e = i + 1
        entry = o[e]
        tp_px = [entry + d * t * risk for t in tps]
        t_stop, p_stop = np.inf, np.nan
        t_tp = [np.inf] * len(tps); p_tp = [np.nan] * len(tps)
        c_at = [np.nan] * len(HOLDS)
        limit = min(e + hold_max, N)
        for k in range(e, limit):
            step = k - e + 1
            if k > e:
                if (o[k] <= stop) if d > 0 else (o[k] >= stop):
                    if t_stop is np.inf or step < t_stop:
                        t_stop, p_stop = step, o[k]
                for j, px in enumerate(tp_px):
                    if t_tp[j] == np.inf and ((o[k] >= px) if d > 0 else (o[k] <= px)):
                        t_tp[j], p_tp[j] = step, o[k]
            if t_stop == np.inf and ((l[k] <= stop) if d > 0 else (h[k] >= stop)):
                t_stop, p_stop = step, stop
            for j, px in enumerate(tp_px):
                if t_tp[j] == np.inf and ((h[k] >= px) if d > 0 else (l[k] <= px)):
                    t_tp[j], p_tp[j] = step, px
            for hi, hh in enumerate(HOLDS):
                if step == hh: c_at[hi] = c[k]
            if t_stop != np.inf and all(t != np.inf for t in t_tp):
                # everything that can fill has filled; remaining horizons keep
                # their close only if we already passed them
                if step >= max(HOLDS): break
        # horizons beyond the data end fall back to the last available close
        last_c = c[min(limit - 1, N - 1)]
        for hi in range(len(HOLDS)):
            if not np.isfinite(c_at[hi]): c_at[hi] = last_c

        out["i"].append(i); out["d"].append(d); out["risk"].append(risk)
        out["entry"].append(entry)
        out["t_stop"].append(t_stop); out["p_stop"].append(p_stop)
        for j in range(len(tps)):
            out["t_tp"][j].append(t_tp[j]); out["p_tp"][j].append(p_tp[j])
        for hi in range(len(HOLDS)):
            out["c_at"][hi].append(c_at[hi])

    if not out["i"]: return None
    W = {k: np.asarray(v, float) for k, v in out.items() if k not in ("t_tp","p_tp","c_at")}
    W["i"] = W["i"].astype(int)
    W["t_tp"] = np.asarray(out["t_tp"], float)
    W["p_tp"] = np.asarray(out["p_tp"], float)
    W["c_at"] = np.asarray(out["c_at"], float)
    W["cost"] = cost[np.minimum(W["i"] + 1, P["N"] - 1)]
    return W

def outcome(W, tp_j, hold_k):
    """Derive R for one (target, hold) pair from the recorded walk. Stop wins
    ties, matching the frozen convention."""
    hold = HOLDS[hold_k]
    t_stop = W["t_stop"]
    stop_ok = t_stop <= hold
    if tp_j is None:
        tp_ok = np.zeros(len(t_stop), bool); t_tp = np.full(len(t_stop), np.inf)
        p_tp = np.full(len(t_stop), np.nan)
    else:
        t_tp = W["t_tp"][tp_j]; p_tp = W["p_tp"][tp_j]
        tp_ok = t_tp <= hold
    exit_px = W["c_at"][hold_k].copy()
    use_tp = tp_ok & (~stop_ok | (t_tp < t_stop))
    use_st = stop_ok & ~use_tp
    exit_px = np.where(use_tp, p_tp, exit_px)
    exit_px = np.where(use_st, W["p_stop"], exit_px)
    held = np.where(use_tp, t_tp, np.where(use_st, t_stop, float(hold)))
    R = ((exit_px - W["entry"]) * W["d"] - W["cost"]) / W["risk"]
    return R, held

# --------------------------------------------------------------- filters --
def build_filters(P, W):
    """A much wider library than the 18 used before - adds a daily-timeframe
    trend (never tested despite being asked about), ADX, MACD, stochastic,
    Bollinger position, ROC, gap, session VWAP distance, volatility
    percentile, streaks, and finer session buckets."""
    c, h, l, o, A, N = P["c"], P["h"], P["l"], P["o"], P["A"], P["N"]
    idx = P["idx"]
    i = W["i"]; d = W["d"].astype(int)
    S = pd.Series(c)

    ema = {n: S.ewm(span=n, adjust=False).mean().shift(1).to_numpy() for n in (20, 50, 200)}
    atr_slow = pd.Series(A).rolling(50).mean().shift(1).to_numpy()
    atr_pct = pd.Series(A).rolling(500).rank(pct=True).shift(1).to_numpy()

    # daily trend, forward-filled without look-ahead
    dly = pd.Series(c, index=idx).resample("1D").last().dropna()
    d_ema = dly.ewm(span=20, adjust=False).mean().shift(1)
    d_ema.index = d_ema.index + pd.Timedelta(days=1)
    d_tr = d_ema.reindex(idx, method="ffill").to_numpy()

    # ADX
    up_m = pd.Series(h).diff(); dn_m = -pd.Series(l).diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_s = pd.Series(A)
    pdi = 100 * pd.Series(plus).ewm(alpha=1/14, adjust=False).mean() / atr_s
    mdi = 100 * pd.Series(minus).ewm(alpha=1/14, adjust=False).mean() / atr_s
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1/14, adjust=False).mean().shift(1).to_numpy()

    macd = (S.ewm(span=12, adjust=False).mean() - S.ewm(span=26, adjust=False).mean())
    macd_h = (macd - macd.ewm(span=9, adjust=False).mean()).shift(1).to_numpy()

    lo14 = pd.Series(l).rolling(14).min(); hi14 = pd.Series(h).rolling(14).max()
    stoch = (100 * (S - lo14) / (hi14 - lo14).replace(0, np.nan)).shift(1).to_numpy()

    sma20 = S.rolling(20).mean(); sd20 = S.rolling(20).std()
    bb_pos = ((S - sma20) / (2 * sd20).replace(0, np.nan)).shift(1).to_numpy()

    dif = S.diff()
    up_e = dif.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn_e = (-dif.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up_e / dn_e.replace(0, np.nan))).shift(1).to_numpy()

    roc = S.pct_change(20).shift(1).to_numpy()
    body = np.abs(c - o) / np.maximum(h - l, 1e-9)
    gap = (o - pd.Series(c).shift(1).to_numpy()) / np.maximum(A, 1e-9)
    move = np.abs(S.diff(20).to_numpy())
    path = pd.Series(np.abs(dif.to_numpy())).rolling(20).sum().to_numpy()
    eff = move / np.maximum(path, 1e-9)
    streak = pd.Series(np.sign(dif.fillna(0))).groupby(
        (np.sign(dif.fillna(0)) != np.sign(dif.fillna(0)).shift()).cumsum()
    ).cumcount().shift(1).to_numpy()

    tp_px = (h + l + c) / 3.0
    day_id = pd.Series(idx.normalize())
    vwap = (pd.Series(tp_px * P["vol"]).groupby(day_id).cumsum() /
            pd.Series(P["vol"]).groupby(day_id).cumsum().replace(0, np.nan)).shift(1).to_numpy()
    vw_d = (c - vwap) / np.maximum(A, 1e-9)

    hour = idx.hour.to_numpy(); dow = idx.dayofweek.to_numpy()
    spread = P["spread"]; vol = P["vol"]
    def med(x): return np.nanmedian(x[np.isfinite(x)])

    F = {
        "trend20_agrees":   d * (c[i] - ema[20][i]) > 0,
        "trend50_agrees":   d * (c[i] - ema[50][i]) > 0,
        "trend200_agrees":  d * (c[i] - ema[200][i]) > 0,
        "daily_trend_agrees": d * (c[i] - d_tr[i]) > 0,
        "atr_contracting":  A[i] <= atr_slow[i],
        "atr_expanding":    A[i] > atr_slow[i],
        "vol_pct_low":      atr_pct[i] <= 0.33,
        "vol_pct_high":     atr_pct[i] >= 0.67,
        "adx_strong":       adx[i] > 25,
        "adx_weak":         adx[i] <= 25,
        "macd_agrees":      d * macd_h[i] > 0,
        "stoch_agrees":     ((stoch[i] > 50) & (d > 0)) | ((stoch[i] < 50) & (d < 0)),
        "stoch_not_extreme": (stoch[i] > 20) & (stoch[i] < 80),
        "bb_inside":        np.abs(bb_pos[i]) < 1.0,
        "bb_beyond":        np.abs(bb_pos[i]) >= 1.0,
        "rsi_agrees":       ((rsi[i] > 50) & (d > 0)) | ((rsi[i] < 50) & (d < 0)),
        "rsi_not_extreme":  (rsi[i] > 25) & (rsi[i] < 75),
        "roc_agrees":       d * roc[i] > 0,
        "efficiency_high":  eff[i] > med(eff),
        "body_strong":      body[i] > 0.5,
        "no_gap":           np.abs(gap[i]) < 0.5,
        "vwap_agrees":      d * vw_d[i] > 0,
        "streak_short":     streak[i] <= 2,
        "spread_tight":     spread[i] <= med(spread),
        "volume_high":      vol[i] > med(vol),
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
    if len(R) < 20: return float("nan")
    sd = R.std(ddof=1)
    return R.mean() / (sd / math.sqrt(len(R))) if sd > 0 else float("nan")

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

def matched_control(P, W, tp_j, hold_k, reps=6, seed=SEED):
    """Same trade count, same direction mix, same exit machinery, random
    timing - the repo's standard control, adapted to the recorded-walk form by
    re-walking at random bars."""
    rng = np.random.default_rng(seed)
    N = P["N"]; out = []
    dirs = W["d"].astype(int)
    pool = np.arange(ATR_N + 200, N - max(HOLDS) - 2)
    if len(pool) < 50: return np.array([])
    hold = HOLDS[hold_k]
    tp_mult = None if tp_j is None else [t for t in TPS if t is not None][tp_j]
    o, h, l, c, A = P["o"], P["h"], P["l"], P["c"], P["A"]
    for rep in range(reps):
        pick = rng.choice(pool, size=min(len(W["i"]), len(pool)), replace=False)
        for j, b in enumerate(pick):
            d = dirs[j % len(dirs)]
            a = A[b]
            if not np.isfinite(a) or a <= 0: continue
            risk = W["risk"][j % len(W["risk"])]      # same risk distribution
            e = b + 1
            if e + hold >= N: continue
            entry = o[e]
            stop = entry - d * risk
            targ = None if tp_mult is None else entry + d * tp_mult * risk
            px = c[min(e + hold, N - 1)]
            for k in range(e, min(e + hold, N)):
                if (l[k] <= stop) if d > 0 else (h[k] >= stop):
                    px = stop; break
                if targ is not None and ((h[k] >= targ) if d > 0 else (l[k] <= targ)):
                    px = targ; break
            out.append(((px - entry) * d - W["cost"][j % len(W["cost"])]) / risk)
    return np.asarray(out, float)

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

def run(m, tf, label, calib=False):
    t0 = time.time()
    P = prep(m)
    cost = P["spread"] + COMMISSION
    disc = P["idx"] < pd.Timestamp(DISCOVERY_END, tz="UTC")
    n_disc = int(disc.sum())
    print(f"{label}: {len(m):,} bars  {m.index[0].date()} -> {m.index[-1].date()}")
    print(f"  discovery {n_disc:,} bars (< {DISCOVERY_END}), "
          f"holdout {len(m)-n_disc:,} bars - holdout is opened once, at the end\n")

    k_total = 0
    hold_max = max(HOLDS)

    # ---- stage 1: rule x exit, no filters, DISCOVERY ONLY -----------------
    print("STAGE 1  rule x exit grid, no filters")
    walks = {}
    base = []
    for look, buf, sm in itertools.product(LOOKBACKS, BUFFERS, STOPS):
        W = walk_rule(P, look, buf, sm, cost, hold_max)
        if W is None: continue
        keep = W["i"] < n_disc
        if keep.sum() < MIN_N_BASE: continue
        Wd = {kk: (vv[..., keep] if kk in ("t_tp", "p_tp", "c_at") else vv[keep])
              for kk, vv in W.items()}
        walks[(look, buf, sm)] = (W, Wd)
        tp_list = [None] + list(range(len([t for t in TPS if t is not None])))
        for tp_j in tp_list:
            for hk in range(len(HOLDS)):
                R, held = outcome(Wd, tp_j, hk)
                k_total += 1
                if len(R) < MIN_N_BASE: continue
                base.append((naive_t(R), R.mean(), len(R), (look, buf, sm, tp_j, hk)))
    base = [b for b in base if np.isfinite(b[0])]
    base.sort(key=lambda x: -x[0])
    print(f"  {k_total:,} rule x exit cells tested, {len(base):,} with enough trades")
    for t, e, n, cfg in base[:6]:
        look, buf, sm, tp_j, hk = cfg
        tpname = "none" if tp_j is None else f"{[x for x in TPS if x is not None][tp_j]}R"
        print(f"    t {t:+.2f}  E {e:+.4f}  n {n:>6}  look {look:>3} buf {buf} "
              f"{sm} tp {tpname} hold {HOLDS[hk]}")

    # ---- stage 2: filter sweep on the leading base rules -------------------
    print(f"\nSTAGE 2  full filter sweep on the top {TOP_BASE} base rules")
    leaders = []
    for t, e, n, cfg in base[:TOP_BASE]:
        look, buf, sm, tp_j, hk = cfg
        W, Wd = walks[(look, buf, sm)]
        R, held = outcome(Wd, tp_j, hk)
        F = build_filters(P, Wd)
        names = list(F); cols = np.vstack([F[nm] for nm in names])
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
                leaders.append((naive_t(r), r.mean(), len(r), cfg, combo, names))
            nxt = []
            for combo in level:
                msk = mask_of(combo)
                for j in range(combo[-1] + 1, len(names)):
                    if (msk & cols[j]).sum() >= MIN_N_FILTER: nxt.append(combo + (j,))
            level = nxt
        if tested_here >= MAX_SUBSETS:
            print(f"    (subset cap hit on one base rule at {tested_here:,})")
    leaders = [x for x in leaders if np.isfinite(x[0])]
    leaders.sort(key=lambda x: -x[0])
    bar = math.sqrt(2 * math.log(max(k_total, 2)))
    print(f"  total cells tested across both stages: {k_total:,}")
    print(f"  noise bar from the search itself: |t| > {bar:.2f}")
    print(f"\n  top {min(8,len(leaders))} by naive t (overlap NOT yet corrected):")
    for t, e, n, cfg, combo, names in leaders[:8]:
        look, buf, sm, tp_j, hk = cfg
        tpname = "none" if tp_j is None else f"{[x for x in TPS if x is not None][tp_j]}R"
        print(f"    t {t:+.2f}  E {e:+.4f}  n {n:>5}  [look{look} {sm} tp{tpname} "
              f"hold{HOLDS[hk]}] {'+'.join(names[x] for x in combo)}")

    if calib:
        best = leaders[0][0] if leaders else float("nan")
        print(f"\n  CALIBRATION VERDICT: best naive t on pure noise = {best:+.2f} "
              f"vs bar {bar:.2f}")
        print("  " + ("PASS - the bar holds on noise.\n" if abs(best) <= bar else
              "*** FAIL - the pipeline manufactures significance. Stop.\n"))
        return

    # ---- stage 3: control, bootstrap, then the holdout once ---------------
    print(f"\nSTAGE 3  leaders re-scored with a matched control and an "
          f"overlap-aware block bootstrap")
    print(f"  {'n':>6}{'E(R)':>9}{'naive t':>9}{'boot t':>8}{'skill':>9}"
          f"{'ctrl t':>8}  configuration")
    final = []
    seen = set()
    for t, e, n, cfg, combo, names in leaders:
        key = (cfg, combo)
        if key in seen: continue
        seen.add(key)
        look, buf, sm, tp_j, hk = cfg
        W, Wd = walks[(look, buf, sm)]
        R, held = outcome(Wd, tp_j, hk)
        F = build_filters(P, Wd)
        nm = list(F); msk = np.ones(len(R), bool)
        for j in combo: msk &= F[nm[j]]
        r = R[msk]
        if len(r) < MIN_N_FILTER: continue
        bt = block_bootstrap_t(r, Wd["i"][msk], held[msk], 1)
        Wf = {kk: (vv[..., msk] if kk in ("t_tp","p_tp","c_at") else vv[msk])
              for kk, vv in Wd.items()}
        ctrl = matched_control(P, Wf, tp_j, hk)
        if len(ctrl) < 30: continue
        sk = r.mean() - ctrl.mean()
        se = math.sqrt(r.var(ddof=1)/len(r) + ctrl.var(ddof=1)/len(ctrl))
        ct = sk / se if se > 0 else float("nan")
        tpname = "none" if tp_j is None else f"{[x for x in TPS if x is not None][tp_j]}R"
        cfgs = f"look{look} buf{buf} {sm} tp{tpname} hold{HOLDS[hk]}"
        print(f"  {len(r):>6}{r.mean():>+9.4f}{t:>+9.2f}{bt:>+8.2f}"
              f"{sk:>+9.4f}{ct:>+8.2f}  {cfgs} | {'+'.join(nm[x] for x in combo)}")
        final.append((bt, ct, r.mean(), len(r), cfg, combo, nm))
        if len(final) >= TOP_LEADERS: break

    survivors = [f for f in final
                 if np.isfinite(f[0]) and abs(f[0]) > bar and np.isfinite(f[1]) and f[1] > 0]
    print(f"\n  clearing the {bar:.2f} bar on the OVERLAP-CORRECTED t, with a "
          f"positive control-adjusted skill: {len(survivors)}")
    if not survivors:
        print("  Nothing survives. The holdout stays closed - opening it for a")
        print("  configuration that already failed in discovery would only")
        print("  spend the one clean test this record still has.")
        print(f"\n  elapsed {time.time()-t0:.0f}s")
        return

    # ---- the holdout, opened exactly once ---------------------------------
    bt, ct, e, n, cfg, combo, nm = survivors[0]
    look, buf, sm, tp_j, hk = cfg
    print(f"\n  HOLDOUT - opened once, on the single best survivor only")
    W, _ = walks[(look, buf, sm)]
    keep = W["i"] >= n_disc
    Wh = {kk: (vv[..., keep] if kk in ("t_tp","p_tp","c_at") else vv[keep])
          for kk, vv in W.items()}
    if len(Wh["i"]) < 30:
        print("  too few holdout trades to judge"); return
    Rh, heldh = outcome(Wh, tp_j, hk)
    Fh = build_filters(P, Wh)
    mh = np.ones(len(Rh), bool)
    for j in combo: mh &= Fh[nm[j]]
    rh = Rh[mh]
    tpname = "none" if tp_j is None else f"{[x for x in TPS if x is not None][tp_j]}R"
    print(f"  config: look{look} buf{buf} {sm} tp{tpname} hold{HOLDS[hk]} | "
          f"{'+'.join(nm[x] for x in combo)}")
    print(f"  discovery : n={n:>5}  E={e:+.4f}  boot t={bt:+.2f}  ctrl t={ct:+.2f}")
    if len(rh) < 30:
        print(f"  holdout   : n={len(rh)} - too few to judge")
    else:
        bth = block_bootstrap_t(rh, Wh["i"][mh], heldh[mh], 1)
        print(f"  holdout   : n={len(rh):>5}  E={rh.mean():+.4f}  boot t={bth:+.2f}"
              f"  net={rh.sum():+.1f}R")
        agree = (rh.mean() > 0) == (e > 0) and rh.mean() > 0
        print(f"  -> {'HOLDS UP' if agree else 'DOES NOT HOLD UP'} out of sample")
    print(f"\n  elapsed {time.time()-t0:.0f}s")

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
