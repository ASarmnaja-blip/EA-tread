#!/usr/bin/env python3
"""Every filter against every other filter, every subset, on 22 years.

WHY THIS EXISTS
  Everything in this repo was tested either alone or in a handful of chosen
  pairings. Nobody ever ran the full combinatorial sweep - all singles, all
  pairs, all triples, on up to ten conditions stacked together. The stated
  reason was that each component died alone so combinations looked
  unpromising. That is a guess, not a measurement, and a filter that is
  useless alone can still be useful in company: it may select a subpopulation
  only visible once another condition is held fixed. The sweep settles it.

THREE THINGS THAT MAKE A MILLION-COMBINATION SEARCH MEANINGFUL RATHER THAN
A NOISE GENERATOR

  1. THE BAR SCALES WITH THE SEARCH. Testing k combinations means the best of
     them, on pure noise, lands near t = sqrt(2 ln k). At k = 1e6 that is 5.72.
     Any cell below its own bar is a coin that came up heads, and the bar is
     computed from the k actually tested, after the run, not guessed before it.

  2. IT RUNS ON THE LARGEST HONEST DATASET, NOT THE NEWEST. 22.7 years of real
     XAUUSD H1 at the measured spread. On two months the maximum reachable t
     is far below the bar a large search demands, so a large search there can
     only manufacture false positives - it is arithmetically incapable of
     producing a defensible one.

  3. SAMPLE SHRINKAGE IS THE REAL LIMIT, AND IT PRUNES THE TREE. Ten filters
     that each keep half leave one signal in a thousand. `dobby_setup01_sweep_
     chain.py` already hit this: its four-stage chain kept 0.8% of candidates
     and its measured skill was smaller than its own minimum detectable
     effect. So any subset falling under MIN_N trades is dropped AND so is
     every superset of it, since adding conditions can only shrink the sample
     further. That is what makes the sweep finish.

HOW IT IS FAST
  Each candidate trade is resolved ONCE, up front, into an R outcome. A filter
  is then a boolean column over those same trades, and a combination is a
  bitwise AND - microseconds, not milliseconds. The expensive part of a
  backtest is run once per candidate trade in total, rather than once per
  candidate per combination.

TWO STAGES, BECAUSE A CHEAP SCREEN IS NOT A RESULT
  Stage 1 screens every surviving subset on expectancy and its t, allowing
  overlapping trades so the screen stays cheap.
  Stage 2 takes the handful of leaders and re-runs them properly: sequential
  non-overlapping trades and a matched random control, which is the standard
  the rest of this repo is held to. A leader that cannot survive stage 2 was
  an artefact of overlap.
"""
import argparse, itertools, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from breakout_h1_dd_target import (prep, signals, plan, resolve, book, stats,
                                   skill_vs_control, ATR_N)

COMMISSION = 0.07
MIN_N = 120          # below this an expectancy is not measurable, so prune
MAX_DEPTH = 10       # the user's ceiling: up to ten conditions at once
TOP_K = 12           # how many leaders go to stage 2

def build_filters(m, P, sig_idx, sig_dir):
    """Binary conditions evaluated AT THE SIGNAL BAR, using only completed
    bars. Each returns one boolean per candidate trade.

    Direction-aware filters are expressed relative to the trade's own side, so
    'trend agrees' means the same thing for a long and for a short."""
    c, h, l = P["c"], P["h"], P["l"]
    A, ph, pl = P["A"], P["ph"], P["pl"]
    idx, N = m.index, P["N"]
    i = np.asarray(sig_idx); d = np.asarray(sig_dir)

    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().shift(1).to_numpy()
    ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().shift(1).to_numpy()
    atr_slow = pd.Series(A).rolling(50).mean().shift(1).to_numpy()
    rng = (ph - pl)
    body = np.abs(c - P["o"]) / np.maximum(h - l, 1e-9)
    move = np.abs(pd.Series(c).diff(20).to_numpy())
    path = pd.Series(np.abs(pd.Series(c).diff().to_numpy())).rolling(20).sum().to_numpy()
    eff = move / np.maximum(path, 1e-9)
    rsi_d = pd.Series(c).diff()
    up = rsi_d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-rsi_d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).shift(1).to_numpy()
    spread = m.spread.to_numpy(float)
    vol = m.volume.to_numpy(float)
    hour = idx.hour.to_numpy(); dow = idx.dayofweek.to_numpy()

    def med(x): return np.nanmedian(x[np.isfinite(x)])

    F = {
        "trend50_agrees":   d * (c[i] - ema50[i]) > 0,
        "trend200_agrees":  d * (c[i] - ema200[i]) > 0,
        "atr_expanding":    A[i] > atr_slow[i],
        "atr_contracting":  A[i] <= atr_slow[i],
        "range_wide":       rng[i] > med(rng),
        "range_narrow":     rng[i] <= med(rng),
        "efficiency_high":  eff[i] > med(eff),
        "body_strong":      body[i] > 0.5,
        "rsi_agrees":       ((rsi[i] > 50) & (d > 0)) | ((rsi[i] < 50) & (d < 0)),
        "rsi_not_extreme":  (rsi[i] > 25) & (rsi[i] < 75),
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

M1_CACHE = pathlib.Path(__file__).parent / ".cache_duka"

def load_tf(tf):
    """H1 comes from the 22-year hourly cache. Everything below it has to be
    built from M1, because Dukascopy serves only minute, hour and day - there
    is no M15 endpoint to fetch. The M1 cache is whatever years have been
    downloaded; the label printed alongside every result says which span the
    numbers actually cover, since a sweep on two months and a sweep on seven
    years are not comparable evidence even when they print the same way."""
    if tf == "1h":
        return D.clean(D.mid(D.load_h1(2003, 2026)))
    parts = sorted(M1_CACHE.glob("XAUUSD_M1_*.parquet"))
    if not parts:
        raise SystemExit("no M1 cache - run fetch_dukascopy.py first")
    frames = []
    for f in parts:
        df = pd.read_parquet(f)
        if "bid_close" in df.columns: df = D.mid(df)
        frames.append(df)
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    m1 = m1[(m1.volume > 0) & (m1.spread > 0)]
    return m1 if tf == "1min" else D.resample(m1, tf)

def main(tf="1h"):
    t0 = time.time()
    m = load_tf(tf)
    P = prep(m)
    cost = m.spread.to_numpy(float) + COMMISSION
    sig = signals(P)
    span = (m.index[-1] - m.index[0]).days / 365.25
    print(f"Real XAUUSD {tf}  {len(m):,} bars  {m.index[0].date()} -> "
          f"{m.index[-1].date()}  ({span:.1f} years)\n")

    # --- resolve every candidate ONCE -------------------------------------
    rows = []
    for i in range(ATR_N + 25, P["N"] - 1):
        if sig[i] == 0: continue
        r = resolve(P, i, int(sig[i]), cost)
        if r is None: continue
        rows.append((i, int(sig[i]), r[0]))
    sig_i = np.array([a for a, _, _ in rows])
    sig_d = np.array([b for _, b, _ in rows])
    R = np.array([c for _, _, c in rows], float)
    print(f"candidate trades resolved once: {len(R):,}  "
          f"E={R.mean():+.4f}  t={R.mean()/(R.std(ddof=1)/math.sqrt(len(R))):+.2f}")

    F = build_filters(m, P, sig_i, sig_d)
    names = list(F)
    cols = np.vstack([F[n] for n in names])
    print(f"filters: {len(names)}  -> 2^{len(names)} = "
          f"{2**len(names):,} possible subsets, pruned by MIN_N={MIN_N}\n")

    # --- breadth-first over subsets, pruning on sample size ---------------
    base_sd = R.std(ddof=1)
    tested, best = 0, []
    # level 1
    level = []
    for j, n in enumerate(names):
        msk = cols[j]
        if msk.sum() < MIN_N: continue
        level.append(((j,), msk))
    print(f"{'depth':>6}{'subsets kept':>14}{'tested':>10}{'best t':>9}  best combination")
    for depth in range(1, MAX_DEPTH + 1):
        if not level: break
        stats_level = []
        for combo, msk in level:
            n = int(msk.sum())
            tested += 1
            r = R[msk]
            e = r.mean(); t = e / (r.std(ddof=1) / math.sqrt(n))
            stats_level.append((t, e, n, combo))
        stats_level.sort(reverse=True)
        best.extend(stats_level[:TOP_K])
        bt, be, bn, bc = stats_level[0]
        print(f"{depth:>6}{len(level):>14}{tested:>10}{bt:>+9.2f}  "
              f"{'+'.join(names[x] for x in bc)} (n={bn}, E={be:+.4f})")
        # expand: add one more filter with a higher index, prune on MIN_N
        nxt = []
        for combo, msk in level:
            for j in range(combo[-1] + 1, len(names)):
                m2 = msk & cols[j]
                if m2.sum() < MIN_N: continue
                nxt.append((combo + (j,), m2))
        level = nxt

    k = tested
    bar = math.sqrt(2 * math.log(max(k, 2)))
    print(f"\nsubsets actually tested: {k:,}  ->  noise bar |t| > {bar:.2f}")
    print(f"screen took {time.time()-t0:.0f}s\n")

    best.sort(reverse=True)
    seen, leaders = set(), []
    for t, e, n, combo in best:
        if combo in seen: continue
        seen.add(combo); leaders.append((t, e, n, combo))
        if len(leaders) >= TOP_K: break

    print("STAGE 1 LEADERS (overlapping trades allowed - a screen, not a result)")
    print(f"  {'t':>7}{'E(R)':>9}{'n':>7}  combination")
    for t, e, n, combo in leaders:
        print(f"  {t:>+7.2f}{e:>+9.4f}{n:>7}  {'+'.join(names[x] for x in combo)}")

    print(f"\nSTAGE 2 - the leaders re-run properly: sequential non-overlapping")
    print("trades and a matched random control, the standard everything else")
    print("in this repo is held to.")
    print(f"  {'n':>6}{'E(R)':>9}{'t':>7}{'skill':>9}{'skill t':>9}  combination")
    survivors = []
    for t1, e1, n1, combo in leaders:
        msk = np.ones(len(R), bool)
        for j in combo: msk &= cols[j]
        keep = set(sig_i[msk].tolist())
        s2 = np.zeros(P["N"], np.int8)
        for i in keep: s2[i] = sig[i]
        rs, sk = skill_vs_control(P, s2, cost)
        if rs is None or sk is None:
            print(f"  {'-':>6}{'':>9}{'':>7}{'':>9}{'':>9}  "
                  f"{'+'.join(names[x] for x in combo)}  (too few after sequencing)")
            continue
        flag = "CLEARS" if abs(sk["t"]) > bar else ""
        survivors.append((sk["t"], rs, sk, combo))
        print(f"  {rs['n']:>6}{rs['E']:>+9.4f}{rs['t']:>+7.2f}"
              f"{sk['skill']:>+9.4f}{sk['t']:>+9.2f}  "
              f"{'+'.join(names[x] for x in combo)} {flag}")

    print(f"\nVERDICT AGAINST THE BAR THE SEARCH ITSELF CREATED (|t| > {bar:.2f})")
    passed = [s for s in survivors if abs(s[2]["t"]) > bar]
    if passed:
        for st, rs, sk, combo in sorted(passed, reverse=True):
            print(f"  PASSES: {'+'.join(names[x] for x in combo)}  "
                  f"skill {sk['skill']:+.4f} at t {sk['t']:+.2f}, n={rs['n']}")
    else:
        bestt = max((abs(s[2]['t']) for s in survivors), default=float('nan'))
        print(f"  Nothing passes. Best skill t among the leaders: {bestt:.2f}")
        print("  Searching more combinations cannot fix this - it raises the")
        print("  bar faster than it raises the best cell.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h",
                    choices=["1min", "5min", "15min", "30min", "1h"])
    main(ap.parse_args().tf)
