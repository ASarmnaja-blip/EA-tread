#!/usr/bin/env python3
"""A large search that does not destroy itself - discovery stage.

THE DESIGN, AND THE CORRECTION IT RESTS ON

  change_ledger.py charges every hypothesis ever spent against every later
  test, which is why the floor now sits at |t| > 4.72 after 824 of them. That
  is the right rule for the failure it was built to stop: tweak a setup,
  retest it on the same data, keep the best-looking version. It is too strict
  for a properly nested design, and the difference is worth a great deal.

  If N rules are searched on data that has ALREADY been burned - and this
  repo's nine markets have been searched across 33 topics - and one finalist
  is chosen using nothing but that burned data, and it is then tested ONCE
  against a universe never examined, the holdout statistic is a single draw
  under the null. The selection consumed no holdout information, so it costs
  no holdout significance. That is ordinary train/test logic.

  It makes the search itself free. Only the finalists are paid for, and the
  number of them is fixed before the holdout is opened.

WHAT IS BEING SEARCHED

  Twelve causal features, each cut at five of its own quantiles from both
  sides, combined by AND at depths one, two and three, in both trade
  directions. Around 33,000 rules. None of them is novel and that is
  deliberate: the point is not a clever rule, it is an exhaustive sweep of
  the obvious ones under a protocol that can survive finding something.

THE SCREEN IS A NECESSARY CONDITION, NOT A RANKING

  Stage 1 scores every rule on signed forward return per ATR, entered at the
  next bar's open, at four horizons - vectorised, no exit structure, no cost.
  A rule with no directional information at all cannot be rescued by a
  bracket, so this is a filter rather than a judgement.

  Stage 2 runs the survivors through the real engine at ZERO COST. This is
  the screen that matters and the one this project learned the hard way to
  put first: venue_change.py showed the liquidity sweep losing 0.0574R per
  trade with no friction whatsoever. A rule negative at zero cost is dead at
  every venue, every account size, and every spread, and there is no point
  measuring it against a real quote.

  Stage 3 charges the real spread and the matched random-timing control.

CALIBRATION FIRST, AS ALWAYS

  The whole screen runs on an information-free random walk before it runs on
  anything real. The best of 33,000 rules on noise must land where the
  expected-maximum formula says it should. If it lands higher, the screen is
  finding structure that is not there and nothing downstream is readable.
"""
import argparse
import itertools
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from overfit_stats import expected_max_t, pbo_cscv
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

HERE = pathlib.Path(__file__).parent
QUANTS = (0.10, 0.25, 0.50, 0.75, 0.90)
HORIZONS = (6, 12, 24, 48)
MIN_FIRES = 300
N_DEPTH3 = 20000
N_FINALISTS = 3           # fixed here, before the holdout is opened
SEED = 17


# ------------------------------------------------------------- features ----
def features(P):
    """Twelve causal features. Every rolling window ends at bar t and every
    prior-extreme is shifted, so nothing here can see the bar it fires on."""
    o, h, l, c, A = P["o"], P["h"], P["l"], P["c"], P["A"]
    s = lambda a: pd.Series(a)
    rng_ = np.maximum(h - l, 1e-12)
    hi20 = s(h).rolling(20).max().shift(1).to_numpy()
    lo20 = s(l).rolling(20).min().shift(1).to_numpy()
    hi50 = s(h).rolling(50).max().shift(1).to_numpy()
    lo50 = s(l).rolling(50).min().shift(1).to_numpy()
    d = s(c).diff()
    up = s(np.where(d > 0, d, 0.0)).rolling(14).mean().to_numpy()
    dn = s(np.where(d < 0, -d, 0.0)).rolling(14).mean().to_numpy()
    atr5 = s(A).rolling(5).mean().to_numpy()
    atr50 = s(A).rolling(50).mean().to_numpy()
    v = P.get("vol")
    with np.errstate(invalid="ignore", divide="ignore"):
        F = {
            "donch20": (c - lo20) / np.maximum(hi20 - lo20, 1e-12),
            "donch50": (c - lo50) / np.maximum(hi50 - lo50, 1e-12),
            "z_sma50": (c - s(c).rolling(50).mean().to_numpy()) / A,
            "z_sma200": (c - s(c).rolling(200).mean().to_numpy()) / A,
            "ret5": (c - s(c).shift(5).to_numpy()) / A,
            "ret20": (c - s(c).shift(20).to_numpy()) / A,
            "atr_ratio": atr5 / np.maximum(atr50, 1e-12),
            "body": np.abs(c - o) / rng_,
            "upwick": (h - np.maximum(o, c)) / rng_,
            "dnwick": (np.minimum(o, c) - l) / rng_,
            "rsi14": up / np.maximum(up + dn, 1e-12),
            "range_atr": rng_ / A,
        }
    if v is not None:
        F["vol_surge"] = np.asarray(v, float) / np.maximum(
            s(v).rolling(20).mean().to_numpy(), 1e-12)
    return {k: np.where(np.isfinite(x), x, np.nan) for k, x in F.items()}


def conditions(F):
    """Each feature cut at five of its own quantiles, from both sides."""
    out = []
    for name, x in F.items():
        fin = x[np.isfinite(x)]
        if len(fin) < 5000:
            continue
        for q in QUANTS:
            thr = float(np.quantile(fin, q))
            out.append((f"{name}>{q:.2f}", np.nan_to_num(x > thr, nan=False)))
            out.append((f"{name}<{q:.2f}", np.nan_to_num(x < thr, nan=False)))
    return out


def rule_space(cond_names, rng):
    """Depths one and two exhaustively, depth three sampled."""
    n = len(cond_names)
    base = [(i,) for i in range(n)]
    pairs = [(i, j) for i, j in itertools.combinations(range(n), 2)
             if cond_names[i].split(">")[0].split("<")[0]
             != cond_names[j].split(">")[0].split("<")[0]]
    trips = []
    if n >= 3:
        for _ in range(N_DEPTH3):
            i, j, k = sorted(rng.choice(n, 3, replace=False).tolist())
            f = [cond_names[z].split(">")[0].split("<")[0] for z in (i, j, k)]
            if len(set(f)) == 3:
                trips.append((i, j, k))
    return base + pairs + sorted(set(trips))


def forward(P):
    """Signed forward return per ATR, entered at the NEXT bar's open.

    Entry is o[t+1], not c[t]. Using the signal bar's close as the entry
    price is the one-bar look-ahead this project already had to retract once."""
    c, o, A, N = P["c"], P["o"], P["A"], P["N"]
    nxt = np.full(N, np.nan)
    nxt[:-1] = o[1:]
    out = {}
    for hzn in HORIZONS:
        fut = np.full(N, np.nan)
        fut[:-hzn] = c[hzn:]
        out[hzn] = (fut - nxt) / A
    return out


def screen_market(P, rules, cond_masks, fwd):
    """Rules fire different numbers of times, so their raw means are not on a
    common scale and the largest of them is mostly the rarest of them. The
    first calibration run made exactly that mistake: the best of 18,378 rules
    on a random walk came out at 3.62x the expected maximum, not because the
    screen found structure but because it was ranking sampling error.

    Each rule is therefore scored as a t-statistic against its OWN standard
    error, with the overlap of h-bar forward returns charged by shrinking the
    effective sample to n/h. Overlapping windows are not independent
    observations and treating them as such is how a screen manufactures
    significance."""
    nR = len(rules)
    best = np.full(nR, -np.inf)
    fires = np.zeros(nR, np.int64)
    vals = {hzn: np.where(np.isfinite(v), v, 0.0) for hzn, v in fwd.items()}
    oks = {hzn: np.isfinite(v) for hzn, v in fwd.items()}
    for ri, idx in enumerate(rules):
        m = cond_masks[idx[0]]
        for k in idx[1:]:
            m = m & cond_masks[k]
        n = int(m.sum())
        fires[ri] = n
        if n < MIN_FIRES:
            continue
        b = -np.inf
        for hzn in HORIZONS:
            ok = m & oks[hzn]
            cnt = int(ok.sum())
            eff = cnt / float(hzn)          # overlapping windows
            if cnt < MIN_FIRES or eff < 30:
                continue
            v = vals[hzn][ok]
            sd = float(v.std(ddof=1))
            if sd <= 0:
                continue
            # |t|, because a rule that reliably precedes a FALL is a short
            # signal of the same strength - the direction is read off the
            # sign rather than searched as a separate hypothesis
            b = max(b, abs(float(v.mean()) / (sd / math.sqrt(eff))))
        best[ri] = b
    return best, fires


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate-only", action="store_true")
    ap.add_argument("--null-reps", type=int, default=8)
    ap.add_argument("--top", type=int, default=200)
    a = ap.parse_args()
    t0 = time.time()
    rng = np.random.default_rng(SEED)

    print("RIGOROUS SEARCH - DISCOVERY STAGE (burned data, no holdout opened)")
    print("=" * 92)
    print(__doc__.split("THE DESIGN, AND THE CORRECTION IT RESTS ON")[1]
          .split("WHAT IS BEING SEARCHED")[0])

    # ---- empirical null, by Monte Carlo -----------------------------------
    print("=" * 92)
    print("0. THE NULL, MEASURED RATHER THAN ASSUMED")
    print("=" * 92)
    print("  The first attempt compared the best rule against the expected")
    print("  maximum of a standard normal. That comparison does not hold here:")
    print("  on a random walk the scores came back with a cross-sectional sd of")
    print("  0.34 and a maximum of 3.10, a ratio of nine, where a normal gives")
    print("  about four. The overlap correction varies rule by rule - fires that")
    print("  cluster in time are worth less than fires that are spread out - so")
    print("  the null is heavy-tailed and no closed form describes it.")
    print("  It is therefore SIMULATED: the identical screen, on independent")
    print("  information-free walks of the same length, and the bar a real rule")
    print("  must clear is what the best rule managed there.\n")
    nulls, names, masks, rules = [], None, None, None
    for rep in range(a.null_reps):
        r2 = np.random.default_rng(1000 + rep)
        n = 120000
        mid = 1800 + np.cumsum(r2.standard_normal(n) * 2.0)
        hi = mid + np.abs(r2.standard_normal(n)) * 1.6
        lo = mid - np.abs(r2.standard_normal(n)) * 1.6
        op = np.concatenate([[mid[0]], mid[:-1]])
        idx = pd.date_range("2005-01-03", periods=n, freq="h", tz="UTC")
        half = 0.10
        mg = pd.DataFrame(dict(
            open=op, high=np.maximum(hi, np.maximum(op, mid)),
            low=np.minimum(lo, np.minimum(op, mid)), close=mid,
            bid_open=op-half, bid_high=hi-half, bid_low=lo-half,
            bid_close=mid-half, ask_open=op+half, ask_high=hi+half,
            ask_low=lo+half, ask_close=mid+half), index=idx)
        Pm = X.prep(mg, 60)
        cm = conditions(features(Pm))
        if names is None:
            names = [c[0] for c in cm]
            rules = rule_space(names, np.random.default_rng(SEED))
            print(f"  {len(names)} conditions -> {len(rules):,} rules")
        mk = {c[0]: c[1] for c in cm}
        ms = [mk.get(nm, np.zeros(Pm["N"], bool)) for nm in names]
        bm, fm = screen_market(Pm, rules, ms, forward(Pm))
        live = np.isfinite(bm)
        nulls.append(float(bm[live].max()))
        print(f"    null walk {rep+1}/{a.null_reps}: best |t| "
              f"{nulls[-1]:.3f}  over {int(live.sum()):,} live rules  "
              f"{time.time()-t0:.0f}s", flush=True)
    nulls = np.array(nulls)
    BAR = float(nulls.max())
    print(f"\n  null maxima: mean {nulls.mean():.3f}  sd {nulls.std(ddof=1):.3f}"
          f"  range [{nulls.min():.3f}, {nulls.max():.3f}]")
    print(f"  BAR = {BAR:.3f}  (the highest any rule reached on data with no")
    print(f"  structure in it whatsoever, over {a.null_reps} independent walks)")
    print(f"\n  A rule on real data that does not clear {BAR:.3f} is doing")
    print(f"  nothing a random walk did not already do {a.null_reps} times out of")
    print(f"  {a.null_reps}. This is a permutation-style null and it assumes no")
    print(f"  distribution at all, which is the point.")

    if a.calibrate_only:
        return

    # ---- discovery -------------------------------------------------------
    print("\n" + "=" * 92)
    print("1. DISCOVERY - nine burned markets, no cost, no exit structure")
    print("=" * 92)
    agg, cnt, per_mkt = None, None, {}
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            continue
        P = X.prep(df, 60)
        F = features(P)
        cs = conditions(F)
        if [c[0] for c in cs] != names:
            cs = [c for c in cs if c[0] in set(names)]
        mk = {c[0]: c[1] for c in cs}
        ms = [mk.get(nm, np.zeros(P["N"], bool)) for nm in names]
        b, f = screen_market(P, rules, ms, forward(P))
        per_mkt[sym] = b
        good = np.isfinite(b)
        agg = np.where(good, b, 0.0) if agg is None else agg + np.where(good, b, 0.0)
        cnt = good.astype(int) if cnt is None else cnt + good.astype(int)
        print(f"  {sym:<8} scored  {int(good.sum()):,} live rules  "
              f"{time.time()-t0:.0f}s", flush=True)

    mean_score = np.where(cnt > 0, agg / np.maximum(cnt, 1), -np.inf)
    keep = (cnt >= 7) & np.isfinite(mean_score)
    order = np.argsort(-mean_score)
    order = [i for i in order if keep[i]][:a.top]
    clears = int(((mean_score > BAR) & keep).sum())
    print(f"\n  {int(keep.sum()):,} rules live on 7+ markets")
    print(f"  best mean |t| across markets: {mean_score[order[0]]:.3f}"
          if order else "  no live rules")
    print(f"  rules clearing the simulated null bar of {BAR:.3f}: {clears:,}")
    if clears == 0:
        print(f"\n  NOT ONE RULE in {len(rules):,} beats what a random walk")
        print(f"  managed. The screen has nothing to hand the engine stage, and")
        print(f"  the honest action is to stop here rather than run the top")
        print(f"  {a.top} anyway and describe them as candidates.")
    print(f"\n  taking the top {len(order)} into the engine stage regardless,")
    print(f"  so the engine-stage numbers exist either way")

    out = HERE / "rigorous_search_discovery.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_conditions=len(names), n_rules=len(rules),
        n_live=int(keep.sum()), n_finalists_declared=N_FINALISTS,
        null=dict(reps=int(a.null_reps), maxima=[float(x) for x in nulls],
                  bar=BAR),
        condition_names=names,
        top=[dict(rank=r + 1, rule=[names[k] for k in rules[i]],
                  score=float(mean_score[i]), markets=int(cnt[i]))
             for r, i in enumerate(order)]), indent=1))
    print(f"  written -> {out.name}")
    print(f"\n  The holdout has NOT been opened. {N_FINALISTS} finalists will be")
    print(f"  chosen from this file by the engine stage, and only those three")
    print(f"  are ever charged against it.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
