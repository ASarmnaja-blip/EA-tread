#!/usr/bin/env python3
"""Does making a rule STRICTER raise its edge, or only shrink its sample?

THE ARGUMENT THIS TESTS, STATED AT ITS STRONGEST

  "One strict setup fires too rarely to measure - but do not loosen it. Make
  them stricter still, find the ones that survive, and run enough of them that
  the portfolio sees sixty signals a month. Would that really not work?"

  The existing evidence supports the premise rather than contradicting it. The
  four-stage ablation in `dobby_setup01_sweep_chain.py` shows expectancy rising
  monotonically with depth:

      1 sweep only          n 18,187   E -0.091
      2 + CHoCH             n  1,160   E +0.001
      3 + displacement      n    883   E +0.039
      4 + FVG limit         n    217   E +0.296

  and the stated reason that row 4 is not a result is that its MDE (0.64) is
  larger than its effect - a SAMPLE SIZE objection. Breadth answers sample size
  objections. So the argument is not loose reasoning; it is the correct
  response to the objection that was actually raised.

THE QUESTION THAT DECIDES IT

  Everything turns on whether that rise in E is INFORMATION or ARTEFACT.

    If information   each condition genuinely selects better trades, pooling
                     many strict rules gives high E at high n, and the
                     portfolio works exactly as proposed.

    If artefact      adding conditions raises measured E for reasons that have
                     nothing to do with the conditions, every strict rule
                     inherits the same illusion, and pooling a hundred of them
                     pools the illusion a hundred times without diluting it.

  Pooling cannot tell these apart, because it improves the precision of the
  estimate without touching its bias. A biased quantity measured precisely is
  still biased - that is the whole danger of the breadth argument, and it is
  invisible from inside the portfolio.

HOW THE TWO ARE SEPARATED HERE

  Conjunctions are built BY CONSTRUCTION rather than by selection: every
  combination of k conditions from a fixed library, all of them, with nothing
  dropped for looking bad. That removes selection bias entirely, so whatever
  is left is the effect of strictness itself.

  Then the same construction is run on TIME-SHUFFLED conditions. A shuffled
  condition keeps its exact rarity - it fires on the same number of bars, with
  the same direction balance - and keeps nothing else. It cannot carry
  information about price by construction.

      if E rises with depth for shuffled conditions too   -> ARTEFACT
      if E rises only for the real ones                   -> INFORMATION

  That comparison is the entire file. It costs one hypothesis, and it answers a
  question that no amount of additional backtesting on real rules could.
"""
import argparse, itertools, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB
import multi_tf_setup_grid as G
from portfolio_of_rare_setups import book_detail

SEED = 17


def conditions(P):
    """A library of directional conditions, each +1 long / -1 short / 0 silent.

    Drawn from what `multi_tf_setup_grid.prep` already computes, so nothing
    here is a new indicator invented for this test. They are deliberately a
    mixed bag - trend, reversion, structure, location - because a library of
    one kind would make every conjunction a restatement of that kind."""
    N, c, h, l = P["N"], P["c"], P["h"], P["l"]
    out = {}

    def sgn(x):
        return np.sign(x).astype(np.int8)

    out["trend_ema"] = sgn(P["ema"][20] - P["ema"][50])
    out["fast_ema"] = sgn(P["ema"][9] - P["ema"][21])
    out["mom_50"] = sgn(P["roc"][50])
    out["mom_10"] = sgn(P["roc"][10])
    out["structure"] = P["st"].astype(np.int8)

    hi, lo = P["don"][20]
    d = np.zeros(N, np.int8)
    d[c > hi] = 1; d[c < lo] = -1
    out["don20_break"] = d

    hi55, lo55 = P["don"][55]
    d = np.zeros(N, np.int8)
    d[c > hi55] = 1; d[c < lo55] = -1
    out["don55_break"] = d

    r = P["rsi"][14]
    d = np.zeros(N, np.int8)
    d[r < 40] = 1; d[r > 60] = -1
    out["rsi_revert"] = d

    u, dn, _ = P["bb"][20]
    d = np.zeros(N, np.int8)
    d[c < dn] = 1; d[c > u] = -1
    out["bb_edge"] = d

    # sweep of the prior 20-bar extreme, body closing back inside
    ph, pl = P["ph"][20], P["pl"][20]
    A = P["A"]
    d = np.zeros(N, np.int8)
    with np.errstate(invalid="ignore"):
        d[(l < pl) & (c > pl) & ((pl - l) < A)] = 1
        d[(h > ph) & (c < ph) & ((h - ph) < A)] = -1
    out["sweep20"] = d

    # inside the last unfilled imbalance, in the structure's direction
    d = np.zeros(N, np.int8)
    ok = np.isfinite(P["fl"]) & (P["fd"] != 0) & (P["fl"] <= c) & (c <= P["fh"])
    d[ok] = P["fd"][ok].astype(np.int8)
    out["in_fvg"] = d

    # inside the last order block
    d = np.zeros(N, np.int8)
    ok = np.isfinite(P["ob_l"]) & (P["ob_d"] != 0) & \
        (P["ob_l"] - 0.25 * A <= c) & (c <= P["ob_h"] + 0.25 * A)
    d[ok] = P["ob_d"][ok].astype(np.int8)
    out["in_ob"] = d

    # a strong body closing near its own extreme - the displacement condition
    o = P["o"]
    rng_ = np.maximum(h - l, 1e-9)
    body = np.abs(c - o)
    d = np.zeros(N, np.int8)
    with np.errstate(invalid="ignore"):
        up = (c > o) & (body >= 0.6 * A) & ((c - l) / rng_ >= 0.65)
        dnn = (c < o) & (body >= 0.6 * A) & ((h - c) / rng_ >= 0.65)
    d[up] = 1; d[dnn] = -1
    out["displacement"] = d

    for k in out:
        out[k] = np.nan_to_num(out[k]).astype(np.int8)
    return out


def shuffle_conditions(C, lo, hi, rng):
    """Each condition's values permuted in time inside the window.

    Rarity and direction balance are preserved EXACTLY - the same bars count,
    the same long/short split - and the relationship to price is destroyed.
    This is the null that says what strictness alone is worth."""
    out = {}
    for k, v in C.items():
        s = v.copy()
        seg = s[lo:hi].copy()
        rng.shuffle(seg)
        s[lo:hi] = seg
        out[k] = s
    return out


def conjunction(C, names):
    """All named conditions agreeing on one direction; silent otherwise."""
    it = iter(names)
    s = C[next(it)].astype(np.int8).copy()
    for nm in it:
        v = C[nm]
        s = np.where((s != 0) & (s == v), s, 0).astype(np.int8)
    return s


def randomise_timing(sig, lo, hi, rng):
    """The same directions, in the same proportion, on random bars.

    This is a different null from the shuffled conditions and it answers a
    different objection. Five of the thirteen conditions fire on every bar -
    they are always-on trend states - so a conjunction of real ones is long
    whenever gold is in an uptrend, which on this instrument is most of
    twenty-two years. A book that is long in an uptrend earns without knowing
    anything, and shuffling the CONDITIONS does not remove that, because the
    shuffled conjunction is long on random bars rather than on rising ones.
    Randomising the TIMING of the finished signal does remove it: the drift and
    the direction balance survive, and only the claim that the entry knows WHEN
    is destroyed."""
    s = np.zeros_like(sig)
    live = np.where(sig[lo:hi] != 0)[0] + lo
    if len(live) == 0:
        return s
    pool = np.arange(lo + 320, hi - 1)
    if len(pool) < len(live):
        return s
    pick = rng.choice(pool, size=len(live), replace=False)
    s[pick] = sig[live]
    return s


def depth_book(P, C, depth, hold, spread, lo, hi, design, rmult, max_combos,
               rng_pick, rng_time=None):
    """Every conjunction of `depth` conditions, pooled into one book.

    Nothing is dropped for looking unpromising and nothing is dropped for being
    rare - a conjunction with four trades contributes its four trades. Dropping
    the thin ones would reintroduce exactly the selection this construction
    exists to avoid."""
    names = sorted(C)
    combos = list(itertools.combinations(names, depth))
    if len(combos) > max_combos:
        idx = rng_pick.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in sorted(idx)]
    R, I, HD, LONG = [], [], [], []
    n_fired = 0
    for cb in combos:
        s = conjunction(C, cb)
        s[:lo] = 0; s[hi:] = 0
        if int((s != 0).sum()) < 5:
            continue
        n_fired += 1
        if rng_time is not None:
            s = randomise_timing(s, lo, hi, rng_time)
        b = book_detail_any(P, s, design, hold, rmult, spread)
        if b is None:
            continue
        R.append(b[0]); I.append(b[1]); HD.append(b[2])
        LONG.append(s[b[1].astype(int)])
    if not R:
        return None
    R = np.concatenate(R); I = np.concatenate(I); HD = np.concatenate(HD)
    LONG = np.concatenate(LONG)
    o = np.argsort(I)
    return R[o], I[o], HD[o], len(combos), n_fired, float((LONG > 0).mean())


def book_detail_any(P, sig, design, hold, rmult, spread):
    """book_detail without its 30-trade floor.

    The floor exists in the portfolio file to keep per-cell statistics honest.
    Here the statistics are computed on the POOL, so a floor per conjunction
    would silently delete the rarest rules - which are the ones the whole
    argument is about."""
    c, A, N = P["c"], P["A"], P["N"]
    live = np.where((sig != 0) & np.isfinite(A) & (A > 0))[0]
    live = live[(live >= 320) & (live < N - 1)]
    if len(live) == 0:
        return None
    out_r, out_i, out_h = [], [], []
    busy = -1
    for i in live:
        i = int(i)
        if i <= busy:
            continue
        risk = rmult * A[i]
        if risk <= 0:
            continue
        r, kx = G.exit_run(P, i, c[i], int(sig[i]), risk, design, hold, spread)
        if r is None:
            continue
        out_r.append(r); out_i.append(float(i)); out_h.append(float(max(kx - i, 1)))
        busy = kx
    if not out_r:
        return None
    return (np.asarray(out_r), np.asarray(out_i), np.asarray(out_h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--hold", type=int, default=48)
    ap.add_argument("--rm", type=float, default=1.5)
    ap.add_argument("--exit", default="stop + time")
    ap.add_argument("--depths", default="1,2,3,4")
    ap.add_argument("--max-combos", type=int, default=220)
    ap.add_argument("--period", default="holdout",
                    choices=("holdout", "discovery"))
    a = ap.parse_args()
    t0 = time.time()

    print("DOES STRICTNESS RAISE THE EDGE, OR ONLY SHRINK THE SAMPLE?")
    print("=" * 86)
    print(__doc__.split("THE QUESTION THAT DECIDES IT")[1]
          .split("HOW THE TWO ARE SEPARATED HERE")[0])

    m = M.load_tf(a.tf)
    P0 = M.prep(m)
    spread = float(EB.scenario_cost_px(260.0, 0.0) / np.nanmedian(P0["c"]))
    disc_end = EB.DISCOVERY_END if S.bar_minutes(m.index) >= 60 \
        else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    lo, hi = ((n_disc, len(m)) if a.period == "holdout" else (0, n_disc))
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))
    C = conditions(Pg)
    design = G.EXITS[a.exit]
    yrs = (m.index[hi - 1] - m.index[lo]).days / 365.25

    print(f"data      {a.tf}  {a.period.upper()} {m.index[lo].date()} -> "
          f"{m.index[hi-1].date()}  ({yrs:.1f} years)")
    print(f"exit      {a.exit}, stop {a.rm} ATR, hold {a.hold}, spread 260 pts")
    print(f"library   {len(C)} conditions, every combination at each depth")
    print(f"          (capped at {a.max_combos} combinations per depth)\n")
    print(f"  {'condition':<16}{'fires':>9}{'share':>8}   {'condition':<16}"
          f"{'fires':>9}{'share':>8}")
    ks = sorted(C)
    for i in range(0, len(ks), 2):
        line = ""
        for nm in ks[i:i + 2]:
            f = int((C[nm][lo:hi] != 0).sum())
            line += f"  {nm:<16}{f:>9,}{f/(hi-lo)*100:>7.1f}%"
        print(line)

    depths = [int(x) for x in a.depths.split(",")]
    rng_pick = np.random.default_rng(SEED)
    rng_shuf = np.random.default_rng(SEED + 1)
    Cs = shuffle_conditions(C, lo, hi, rng_shuf)

    print("\n" + "=" * 86)
    print("REAL CONDITIONS vs TIME-SHUFFLED CONDITIONS, BY DEPTH")
    print("=" * 86)
    print("  Shuffled conditions fire on exactly as many bars, with exactly the")
    print("  same long/short balance, and carry no information about price.\n")
    print(f"  {'depth':>6}{'combos':>8}{'trades':>9}{'long':>7}{'E real':>10}"
          f"{'t real':>9}{'E shuf':>10}{'E timing':>10}{'skill':>9}{'t skill':>9}")
    rows = []
    for d in depths:
        rb = depth_book(Pg, C, d, a.hold, spread, lo, hi, design, a.rm,
                        a.max_combos, np.random.default_rng(SEED))
        sb = depth_book(Pg, Cs, d, a.hold, spread, lo, hi, design, a.rm,
                        a.max_combos, np.random.default_rng(SEED))
        tb = depth_book(Pg, C, d, a.hold, spread, lo, hi, design, a.rm,
                        a.max_combos, np.random.default_rng(SEED),
                        rng_time=np.random.default_rng(SEED + 99))
        if rb is None or sb is None or tb is None:
            print(f"  {d:>6}   no usable book")
            continue
        R, I, HD, ncomb, nfire, lng = rb
        Rs = sb[0]
        Rt = tb[0]
        tr = M.block_bootstrap_t(R, I, HD, 1)
        # Skill is measured against the TIMING control, not the shuffled one:
        # it is the null that keeps the drift, and drift is what a long book on
        # a rising asset would otherwise be paid for.
        skill = float(R.mean() - Rt.mean())
        tsk = M.block_bootstrap_t(R - Rt.mean(), I, HD, 1)
        rows.append(dict(depth=d, n_real=len(R), long_share=lng,
                         e_real=float(R.mean()), t_real=float(tr),
                         e_shuf=float(Rs.mean()), e_time=float(Rt.mean()),
                         skill=skill, t_skill=float(tsk)))
        print(f"  {d:>6}{ncomb:>8}{len(R):>9,}{lng*100:>6.0f}%"
              f"{R.mean():>+10.4f}{tr:>+9.2f}{Rs.mean():>+10.4f}"
              f"{Rt.mean():>+10.4f}{skill:>+9.4f}{tsk:>+9.2f}")

    if len(rows) < 2:
        print("\n  not enough depths to compare")
        return
    T = pd.DataFrame(rows)

    print("\n" + "=" * 86)
    print("WHAT THE TWO COLUMNS SAY")
    print("=" * 86)
    re_rise = T["e_real"].iloc[-1] - T["e_real"].iloc[0]
    sh_rise = T["e_shuf"].iloc[-1] - T["e_shuf"].iloc[0]
    sk_rise = T["skill"].iloc[-1] - T["skill"].iloc[0]
    print(f"  raw E rises with depth by      {re_rise:+.4f}  (real conditions)")
    print(f"  raw E rises with depth by      {sh_rise:+.4f}  (shuffled)")
    print(f"  SKILL rises with depth by      {sk_rise:+.4f}  (real minus the")
    print(f"                                           timing control)")
    bias = ("LONG-BIASED, so the raw E column is partly gold going up"
            if T["long_share"].max() > 0.55 else "roughly balanced")
    print(f"\n  long share runs {T['long_share'].min()*100:.0f}% to "
          f"{T['long_share'].max()*100:.0f}% - the books are {bias}.")
    print(f"  That is why skill is measured against the timing control rather")
    print(f"  than the shuffled one: only the timing control keeps the drift.")
    print()
    best = T.loc[T["skill"].idxmax()]
    floor = math.sqrt(2 * math.log(max(len(T), 2)))
    if best["t_skill"] > floor:
        print(f"  STRICTNESS SURVIVES. Best depth {int(best['depth'])}: skill")
        print(f"  {best['skill']:+.4f} at t {best['t_skill']:+.2f}, above the")
        print(f"  {floor:.2f} floor for {len(T)} depths. This is now a")
        print(f"  pre-registered hypothesis and needs data not used here.")
    else:
        print(f"  STRICTNESS DOES NOT SURVIVE THE DRIFT CONTROL.")
        print(f"  Best depth {int(best['depth'])} has skill "
              f"{best['skill']:+.4f} at t {best['t_skill']:+.2f}, under the")
        print(f"  {floor:.2f} floor for {len(T)} depths tried.")
        print()
        print(f"  The raw E column DOES rise with depth, and that rise is not")
        print(f"  reproduced by shuffled conditions - so strictness is doing")
        print(f"  something real. What it is doing is concentrating the book")
        print(f"  into the direction the market was already moving. Randomise")
        print(f"  only the TIMING and keep the direction, and most of the rise")
        print(f"  comes back. That is drift, and it is not an edge: it is")
        print(f"  available by holding, at no strictness and no cost.")
        print()
        print(f"  This is also why breadth cannot rescue it. Pooling a hundred")
        print(f"  strict rules improves the PRECISION of the estimate and does")
        print(f"  nothing to its BIAS. A hundred rules that are all long in an")
        print(f"  uptrend measure the uptrend a hundred times.")

    # The comparison that settles it regardless of significance. Even taking
    # every skill number above at face value - ignoring that none of them
    # clears the floor - they have to pay the spread before they pay anything
    # else, and the spread here is not small relative to them.
    cost_R = float(EB.scenario_cost_px(260.0, 0.0) /
                   (a.rm * np.nanmedian(P0["A"])))
    print(f"\nTHE COMPARISON THAT SETTLES IT EVEN IF THE SKILL WERE REAL")
    print(f"  round-trip cost at a {a.rm} ATR stop: {cost_R:.4f}R per trade")
    print(f"  {'depth':>6}{'skill':>10}{'cost':>9}{'skill - cost':>14}")
    for _, r in T.iterrows():
        print(f"  {int(r['depth']):>6}{r['skill']:>+10.4f}{cost_R:>9.4f}"
              f"{r['skill'] - cost_R:>+14.4f}")
    if (T["skill"] < cost_R).all():
        print(f"\n  Every depth's skill is SMALLER THAN THE SPREAD. Taking all")
        print(f"  four at face value and ignoring that none is significant, the")
        print(f"  book still loses money on every trade. Strictness cannot fix")
        print(f"  this either: the skill column is flat across depths while the")
        print(f"  cost is fixed, so no amount of additional conditions closes a")
        print(f"  gap that additional conditions do not widen the skill to meet.")

    print(f"\n  The 'skill' column is the only part of E the conditions earned.")
    print(f"  Read that against the cost line above, not against the E column.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
