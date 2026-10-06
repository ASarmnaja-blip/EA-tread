#!/usr/bin/env python3
"""The stage-1 liquidity sweep, at real cost, on ten markets and 23 years.

WHY THIS RULE AND NOT ANOTHER

  It is the last candidate in this repo that has not collapsed.
  RESEARCH_FINDINGS records skill +0.051 at t +1.89 over 18,187 trades on 27
  futures and calls it "the only smart-money primitive in this repo that has
  not flipped sign".

TWO THINGS WRONG WITH THAT RECORD, BOTH SETTLED HERE

  ONE - it was measured at ZERO COST, and its expectancy there is -0.091.
  The rule loses money before a single spread is charged. Positive skill on a
  negative expectancy means random timing loses MORE, which is a statement
  about the control, not a reason to trade. It has never met a real quote.

  TWO - the repo contradicts itself about it. choch_fvg_three_setups.py line
  41 says a sign flip "disqualified the liquidity sweep, the strongest
  candidate in the program". RESEARCH_FINDINGS line 911 says it did not flip
  sign. Both cannot be true.

THE POWER PROBLEM, COMPUTED BEFORE THE RUN AND NOT AFTER

  At the original signal rate of 3.84% of bars, the 1,775,040 bars here yield
  roughly 68,000 trades, and carrying skill +0.051 forward that is a projected
  t of 3.66. The ledger's floor is 4.72. Clearing it would need about 113,000
  trades - 1.7x more than this data can produce.

  So this test CANNOT confirm the rule, and saying so afterwards would be an
  excuse. It is registered as a KILL test instead, because power limits
  confirmation and not refutation: a sign flip, an inconsistent sign across
  markets, or a negative expectancy at real cost each end it regardless of
  sample size.

NOTHING IS RE-TUNED

  The rule is taken verbatim from dobby_setup01_sweep_chain.py - prior 20-bar
  extreme, penetration between 0.08 and 1.50 ATR, body closing back inside.
  No parameter is swept, which is what keeps this one registered hypothesis
  rather than a new search, and it is the only reason the floor rose by 0.00
  rather than by the width of a grid.
"""
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from change_ledger import floor_for
from overfit_stats import deflated_sharpe_from_returns
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SWEEP_N = 20          # bars whose extreme the wick must clear
PEN_MIN = 0.08        # InpSweepMinPenATR
PEN_MAX = 1.50        # InpSweepMaxPenATR
K_AT_TEST = 824
SEED = 17


def sweep_signals(P):
    """Stage 1 only: a wick clears the prior extreme and the body closes back.

    Vectorised, but the levels are the same ones dobby_setup01_sweep_chain.py
    builds bar by bar: rolling extremes SHIFTED by one, so the bar being
    tested never contributes to the level it must clear."""
    h, l, c, A, N = P["h"], P["l"], P["c"], P["A"], P["N"]
    ph = pd.Series(h).rolling(SWEEP_N).max().shift(1).to_numpy()
    pl = pd.Series(l).rolling(SWEEP_N).min().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        pen_dn = pl - l                      # bullish sweep: wick under the low
        pen_up = h - ph                      # bearish sweep: wick over the high
        bull = ((pen_dn > 0) & (c > pl)
                & (pen_dn >= PEN_MIN * A) & (pen_dn <= PEN_MAX * A))
        bear = ((pen_up > 0) & (c < ph)
                & (pen_up >= PEN_MIN * A) & (pen_up <= PEN_MAX * A))
    bull = np.nan_to_num(bull, nan=0).astype(bool)
    bear = np.nan_to_num(bear, nan=0).astype(bool)
    both = bull & bear                        # a bar that swept both sides is
    bull &= ~both                             # ambiguous - take neither
    bear &= ~both
    d = np.zeros(N, np.int8)
    I = np.full(N, np.nan)
    d[bull] = 1
    I[bull] = l[bull]                         # invalidation = the sweep extreme
    d[bear] = -1
    I[bear] = h[bear]
    return d, I


def martingale_frame(n=60000, seed=3):
    """Information-free prices with the same shape as a real feed.

    A random walk with a real spread: skill must come out ~0 and expectancy
    must come out NEGATIVE by about the spread. This is the guard that caught
    the one-bar look-ahead which produced this project's best-ever result.

    Its volatility is scaled to a real feed's, not chosen for convenience:
    run_e01's G09 gate rejects any trade whose spread exceeds 10% of ATR, and
    a synthetic series with an unrealistically wide spread relative to its own
    range has every trade thrown out before the engine sees it. A first draft
    here did exactly that - spread/ATR 0.314 against a 0.10 gate, zero trades -
    which would have read as "the calibration produced no trades" rather than
    as a badly built fixture."""
    rng = np.random.default_rng(seed)
    step = rng.standard_normal(n) * 2.0
    mid = 1800 + np.cumsum(step)
    hi = mid + np.abs(rng.standard_normal(n)) * 1.6
    lo = mid - np.abs(rng.standard_normal(n)) * 1.6
    op = np.concatenate([[mid[0]], mid[:-1]])
    half = 0.10
    idx = pd.date_range("2005-01-03", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(dict(
        open=op, high=np.maximum(hi, np.maximum(op, mid)),
        low=np.minimum(lo, np.minimum(op, mid)), close=mid,
        bid_open=op - half, bid_high=hi - half, bid_low=lo - half,
        bid_close=mid - half,
        ask_open=op + half, ask_high=hi + half, ask_low=lo + half,
        ask_close=mid + half), index=idx)


def block_se(R, entry_idx, held, reps=2000, seed=SEED):
    """The bootstrap standard error, on the same blocks mega_search uses.

    block_bootstrap_t returns mean/se, which cannot be inverted safely when
    the mean is near zero - and a control's mean often is. The skill's error
    bar needs both standard errors, so it needs this rather than a division."""
    R = np.asarray(R, float)
    if len(R) < 30:
        return float("nan")
    span = max(int(np.nanmedian(held)) * 2, 10)
    block = np.maximum(np.asarray(entry_idx, float).astype(int) // span, 0)
    uniq = np.unique(block)
    if len(uniq) < 8:
        return float("nan")
    groups = [R[block == b] for b in uniq]
    rng = np.random.default_rng(seed)
    means = np.empty(reps)
    for r in range(reps):
        pick = rng.integers(0, len(groups), len(groups))
        means[r] = np.concatenate([groups[p] for p in pick]).mean()
    return float(means.std(ddof=1))


def run_market(df, tick):
    P = X.prep(df, 60)
    d, I = sweep_signals(P)
    R, I_, HD, RATIO = X.run_e01(P, d, I, 0, P["N"], tick)
    if len(R) < 200:
        return None
    rng = np.random.default_rng(SEED)
    C = X.run_e01_control(P, d, 0, P["N"], risk_ratios=np.asarray(RATIO),
                          rng=rng)
    # run_e01_control returns a THREE-TUPLE (R, entry, held), not a bare
    # array of returns. Averaging the tuple gives a number in the thousands.
    # The martingale calibration caught exactly that on the first run -
    # skill came back as -9975.87 - which is what the guard is for.
    if C is None:
        return None
    Cr, Cent, Chd = C
    ctrl = float(np.asarray(Cr, float).mean())
    Ra = np.asarray(R, float)
    ent = np.asarray(I_, float)
    hd = np.asarray(HD, float)
    se_r = block_se(Ra, ent, hd)
    se_c = block_se(np.asarray(Cr, float), np.asarray(Cent, float),
                    np.asarray(Chd, float))
    skill = float(Ra.mean() - ctrl)
    se_s = math.sqrt(se_r ** 2 + se_c ** 2) if np.isfinite(se_r + se_c) else np.nan
    return dict(R=Ra, entry=ent, held=hd, ctrl=ctrl, idx=P["idx"],
                n=len(Ra), E=float(Ra.mean()),
                t_E=float(M.block_bootstrap_t(Ra, ent, hd, 1)),
                skill=skill,
                t_skill=float(skill / se_s) if se_s and np.isfinite(se_s) else np.nan,
                win=float((Ra > 0).mean()) * 100)


def main():
    t0 = time.time()
    print("LIQUIDITY SWEEP, STAGE 1 - REAL COST, TEN MARKETS, 23 YEARS")
    print("=" * 96)
    print(__doc__.split("THE POWER PROBLEM")[1].split("NOTHING IS RE-TUNED")[0])

    # ---- 0. calibration ---------------------------------------------------
    print("=" * 96)
    print("0. CALIBRATION - the rule on information-free prices")
    print("=" * 96)
    mg = run_market(martingale_frame(), 0.001)
    if mg is None:
        print("  calibration produced no trades - cannot proceed")
        return
    ok = mg["E"] < 0 and abs(mg["skill"]) < 0.03
    print(f"  martingale data: n {mg['n']:,}  E {mg['E']:+.4f}  "
          f"skill {mg['skill']:+.4f}")
    print(f"  required: E < 0 (the spread is the only edge available) and")
    print(f"  skill ~ 0 (no timing information exists to find)")
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("\n  The detector or the engine is finding an edge in a random")
        print("  walk. Nothing below this line may be read. Stop here.")
        return

    # ---- 1. per market ----------------------------------------------------
    print("\n" + "=" * 96)
    print("1. PER MARKET - real bid/ask, entry at the entry bar's open")
    print("=" * 96)
    print(f"  {'market':<9}{'n':>8}{'win%':>7}{'E(R)':>10}{'t_E':>8}"
          f"{'control':>10}{'skill':>10}{'t_skill':>9}")
    books, rows = {}, []
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            continue
        r = run_market(df, TICKS.get(sym, 0.00001))
        if r is None:
            continue
        books[sym] = r
        rows.append(dict(symbol=sym, n=r["n"], E=r["E"], t_E=r["t_E"],
                         ctrl=r["ctrl"], skill=r["skill"],
                         t_skill=r["t_skill"], win=r["win"]))
        print(f"  {sym:<9}{r['n']:>8,}{r['win']:>6.1f}%{r['E']:>+10.4f}"
              f"{r['t_E']:>+8.2f}{r['ctrl']:>+10.4f}{r['skill']:>+10.4f}"
              f"{r['t_skill']:>+9.2f}")
    if not rows:
        print("  nothing produced a book")
        return
    D = pd.DataFrame(rows)
    n_tot = int(D.n.sum())

    # ---- 2. pooled --------------------------------------------------------
    print("\n" + "=" * 96)
    print("2. POOLED - and why the pooled t is not the naive one")
    print("=" * 96)
    allR = np.concatenate([b["R"] for b in books.values()])
    allE = np.concatenate([b["entry"] for b in books.values()])
    allH = np.concatenate([b["held"] for b in books.values()])
    naive = float(allR.mean() / (allR.std(ddof=1) / math.sqrt(len(allR))))
    blk = float(M.block_bootstrap_t(allR, allE, allH, 1))
    pooled_skill = float(D.skill.mean())
    pos = int((D.skill > 0).sum())
    print(f"  total trades          {n_tot:,}")
    print(f"  pooled E(R)           {float(allR.mean()):+.4f}")
    print(f"  naive t               {naive:+.2f}   <- wrong: treats 10 markets")
    print(f"                                   trading the same calendar as")
    print(f"                                   10 independent samples")
    print(f"  block-bootstrap t     {blk:+.2f}   <- overlap-aware")
    print(f"  mean skill/market     {pooled_skill:+.4f}")
    print(f"  skill positive on     {pos} of {len(D)} markets")

    # ---- 3. deflated sharpe ----------------------------------------------
    sr, dsr1 = deflated_sharpe_from_returns(allR, n_trials=1)
    _, dsrk = deflated_sharpe_from_returns(allR, n_trials=K_AT_TEST,
                                           sigma_trials=1.475)
    print(f"\n  per-trade Sharpe      {sr:+.5f}")
    print(f"  P(true SR>0), 1 trial {dsr1:.4f}")
    print(f"  DEFLATED for k={K_AT_TEST}    {dsrk:.4f}")

    # ---- 4. the declared kill conditions ----------------------------------
    print("\n" + "=" * 96)
    print("3. THE DECLARED KILL CONDITIONS")
    print("=" * 96)
    k1 = pooled_skill < 0
    k2 = pos < 6
    k3 = float(allR.mean()) < 0
    print(f"  dies if skill turns negative pooled      "
          f"skill {pooled_skill:+.4f}   {'KILL' if k1 else 'survives'}")
    print(f"  dies if skill positive on fewer than 6   "
          f"{pos} of {len(D)}       {'KILL' if k2 else 'survives'}")
    print(f"  dies if E at real bid/ask stays negative "
          f"E {float(allR.mean()):+.4f}   {'KILL' if k3 else 'survives'}")
    dead = k1 or k2 or k3
    fl = floor_for(K_AT_TEST)
    print(f"\n  floor at k={K_AT_TEST}: |t| > {fl:.2f}.  observed block t "
          f"{blk:+.2f}")
    proj = 1.89 * math.sqrt(n_tot / 18187)
    print(f"  projected before the run from n: t {proj:.2f} - "
          f"{'close to' if abs(proj-abs(blk))<1.0 else 'far from'} what came back")

    print("\n" + "=" * 96)
    print("VERDICT")
    print("=" * 96)
    if dead:
        print("  KILLED on the pre-declared conditions.")
        print("  This was the last candidate in the repo that had not")
        print("  collapsed, and it collapses on the condition that mattered")
        print("  most: whether the skill it has ever shown was worth anything")
        print("  once a real quote was charged against it.")
    else:
        print("  SURVIVES the kill conditions - which is NOT acceptance.")
        print(f"  The floor is {fl:.2f} and this test was registered as")
        print("  unable to reach it. What survives is a candidate worth more")
        print("  data, not a rule worth trading.")

    print("\n  On the documented contradiction:")
    print(f"    RESEARCH_FINDINGS line 911: skill +0.051, did NOT flip sign")
    print(f"    measured here at real cost: skill {pooled_skill:+.4f}")
    if pooled_skill > 0:
        print(f"    -> the sign holds. choch_fvg_three_setups.py line 41,")
        print(f"       which says a sign flip disqualified this rule, is")
        print(f"       wrong and should be corrected in the source.")
    else:
        print(f"    -> the sign does NOT hold at real cost. The claim that it")
        print(f"       never flipped was true only at zero cost.")

    out = pathlib.Path(__file__).parent / "liquidity_sweep_crossmarket.csv"
    D.to_csv(out, index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s   detail -> {out.name}")


if __name__ == "__main__":
    main()
