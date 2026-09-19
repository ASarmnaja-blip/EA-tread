#!/usr/bin/env python3
"""XAUUSDc on the real account, under the real constraints.

WHAT THIS IS AND - MORE IMPORTANTLY - WHAT IT IS NOT

  It is NOT a search. The configuration grid below is small, declared in
  source before anything ran, and frozen. Everything upstream in this repo
  exists because searching a million cells and keeping the best produces a
  number that means nothing, and adding a real account's cost model to that
  process would not fix it. The grid is here so that "we tried N things" is a
  number you can read rather than a claim you have to take on faith.

  The PASS/FAIL CRITERIA ARE WRITTEN BELOW, BEFORE THE RUN. If nothing meets
  them the answer is FAIL and the answer stays FAIL; the grid does not get
  widened afterwards to find something that scrapes through.

THE THREE-WAY SPLIT, AND WHAT EACH PART IS ALLOWED TO DO
  DISCOVERY   2004-01-01 .. 2016-12-31   picks the configuration
  VALIDATION  2017-01-01 .. 2021-12-31   confirms it, once
  HOLDOUT     2022-01-01 .. end          opened ONCE, at the very end, only
                                         for a configuration that already
                                         passed both of the above
  Filter thresholds are fitted on DISCOVERY only and frozen. Trades that
  begin in one period and end in another are purged from both.

THE ACCOUNT'S OWN RULES, ENFORCED NOT ASSUMED
  bid/ask         every fill crosses the spread; nothing is priced at mid
  spread          260 / 400 / 600 points, each a separate run
  slippage        0 / 0.1x / 0.3x of the spread in force, both sides
  commission      0
  no rollover     every position force-closed by 20:30 UTC
  no weekends     falls out of the same session arithmetic
  swap            0 in the main test, because nothing is held overnight;
                  reported separately for the overnight case
  rule 10         a signal whose risk is under 3x the round-trip cost OF THAT
                  SCENARIO is not taken - recomputed per scenario, never a
                  constant
"""
import argparse, math, sys, pathlib, json, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import mega_search as M
import portfolio as PF
import session_rules as S
from exness_cent import (ExnessCent, SPREAD_SCENARIOS, SLIPPAGE_MULTIPLES,
                         RISK_LEVELS, DD_LIMITS, slip_points, POINT)
from split_guard import Split, purge, Thresholds
from exec_engine import plan_from_signal

ACC = ExnessCent()

DISCOVERY_END = "2017-01-01"
VALIDATION_END = "2022-01-01"
# M15/M5 only start in 2019 (M1 cache begins there); a different split is
# needed for those timeframes so discovery isn't empty. Declared here,
# before any M15 run, not chosen after seeing results.
DISCOVERY_END_M15 = "2023-01-01"
VALIDATION_END_M15 = "2025-01-01"

# ---- THE FROZEN GRID, declared before the run -----------------------------
LOOKBACKS = (10, 20, 40)
BUFFERS = (0.0, 0.1)
STOPS = ("range", "atr1", "atr2")
TPS = (1.0, 2.0, 3.0, None)
HOLDS_H1 = (4, 8, 12, 20)
FILTERS = (None, "long_side", "short_side", "atr_contracting",
           "london", "newyork")

# ---- PASS/FAIL CRITERIA, declared before the run --------------------------
CRITERIA = """
  A configuration PASSES DISCOVERY only if ALL of:
    1. at least 200 trades survive the cost filter and the session deadline
    2. mean net R per trade > 0 AFTER costs
    3. the percentile block bootstrap 95% CI on net R lies entirely above 0
    4. skill over the matched random control > 0
    5. |overlap-corrected t| exceeds sqrt(2 ln k) for the k cells actually
       tested in this run
  It PASSES VALIDATION only if, on data never used to choose it:
    6. mean net R > 0, and
    7. at least 100 trades
  Only then is the HOLDOUT opened, once.
  A configuration is TRADEABLE on the real account only if, additionally:
    8. it still has positive net R at 600-point spread with 0.3x slippage
    9. the account can actually deal it: not rejected for minimum lot
   10. floating drawdown stays inside the limit being considered
"""

# --------------------------------------------------------------------------
def scenario_cost_px(spread_pts, slip_mult):
    """Round-trip cost in PRICE UNITS for one scenario. The spread is crossed
    once; slippage is paid on both sides; commission is zero on this account."""
    sp = ACC.px(spread_pts)
    sl = ACC.px(slip_points(spread_pts, slip_mult))
    return sp + 2.0 * sl

def outcome_variable_hold(W, P, tp_j, hold_vec):
    """mega_search.outcome(), but with a PER-TRADE horizon.

    The session deadline gives every trade a different maximum hold, so the
    fixed-horizon version cannot express it. The recorded walk already holds
    the first-hit step for the stop and for every target; the only thing the
    fixed version needed c_at for was the time-exit price, and that is just
    the close of bar (signal + hold), read directly."""
    n = len(W["i"])
    t_stop = W["t_stop"]
    hold_vec = np.asarray(hold_vec, float)
    if tp_j is None:
        t_tp = np.full(n, np.inf); p_tp = np.full(n, np.nan)
        ok = ~W["g_stop"]
    else:
        t_tp = W["t_tp"][tp_j]; p_tp = W["p_tp"][tp_j]
        ok = ~W["g_stop"] & ~W["g_tp"][tp_j]
    stop_ok = t_stop <= hold_vec
    tp_ok = t_tp <= hold_vec
    use_tp = tp_ok & (~stop_ok | (t_tp < t_stop))
    use_st = stop_ok & ~use_tp

    room = W["room"]
    time_held = np.minimum(hold_vec, room)
    time_bar = np.minimum(W["i"] + time_held, P["N"] - 1).astype(int)
    exit_px = np.where(use_tp, p_tp,
                       np.where(use_st, W["p_stop"], P["c"][time_bar]))
    held = np.where(use_tp, np.ceil(t_tp),
                    np.where(use_st, np.ceil(t_stop), time_held))
    R = ((exit_px - W["entry"]) * W["d"] - W["cost"]) / W["risk"]
    R = np.where(ok, R, np.nan)
    held = np.where(ok, held, np.nan)
    # the exit PRICE is returned too. The portfolio engine needs the price the
    # trade actually exited at - a stop fill is at the stop, not at wherever
    # that bar happened to close - and reconstructing it downstream from the
    # bar close is exactly the mispricing this returns to prevent.
    return R, held, ok, np.where(ok, exit_px, np.nan)

def walk_for(P, look, buf, stop_mode, cost_px, hold_max):
    """One recorded walk under a CONSTANT scenario cost.

    The cost array is flat because the scenario says so (260 points is 260
    points at every bar). The real, varying Dukascopy bid/ask is used in the
    separate `--real-spread` run, which is the honest comparison: the
    historical median is 377 points, WIDER than the 260 the terminal shows."""
    cost = np.full(P["N"], cost_px, float)
    return M.walk_rule(P, look, buf, stop_mode, cost, hold_max)

def resolve_side(W, P, tp_j, hold_cfg, split, side, deadline):
    """Trades for one side of the split, with the session deadline applied and
    straddling trades purged."""
    n = len(W["i"])
    e = W["i"] + 1
    e = np.minimum(e, P["N"] - 1)
    dl = deadline[e]
    room_session = dl - e + 1
    has_room = room_session >= 1
    hold_vec = np.minimum(hold_cfg, np.maximum(room_session, 1))
    R, held, ok, xpx = outcome_variable_hold(W, P, tp_j, hold_vec)
    ok = ok & has_room
    idx_ok = np.where(ok)[0]
    if len(idx_ok) == 0:
        return R, held, np.zeros(n, bool), dict(total=0, kept=0, straddling=0,
                                                other_side=0, no_room=int((~has_room).sum()))
    eb = (W["i"][idx_ok] + held[idx_ok]).astype(int)
    keep_sub, rep = purge(W["i"][idx_ok], eb, split, side)
    keep = np.zeros(n, bool)
    keep[idx_ok[keep_sub]] = True
    rep["no_room"] = int((~has_room).sum())
    return R, held, keep, rep

def dd_episodes(equity, levels):
    """How many DISTINCT drawdown episodes went past each level.

    Not 'how many bars were below it' - that counts one bad month a thousand
    times. An episode starts at an equity peak and ends when a new peak is
    made; it is counted once, against the deepest level it reached."""
    eq = np.asarray(equity, float)
    peak = eq[0]
    depth = 0.0
    counted = {lv: False for lv in levels}
    out = {lv: 0 for lv in levels}
    for x in eq:
        if x > peak:
            peak = x; depth = 0.0
            counted = {lv: False for lv in levels}
        else:
            d = 1.0 - x / peak if peak > 0 else 0.0
            depth = max(depth, d)
            for lv in levels:
                if depth >= lv and not counted[lv]:
                    out[lv] += 1
                    counted[lv] = True
    return out

def trade_stats(res, r_units):
    """Everything asked for that is not already in the portfolio result."""
    log = res["log"]
    pls = np.array([t["pl"] for t in log], float) if log else np.array([])
    wins = pls[pls > 0]; losses = pls[pls < 0]
    gross_win = wins.sum() if len(wins) else 0.0
    gross_loss = -losses.sum() if len(losses) else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else float("nan")
    # longest run of losing trades, in close order
    longest = cur = 0
    for x in pls:
        if x < 0:
            cur += 1; longest = max(longest, cur)
        else:
            cur = 0
    # profitable vs losing days, by close date
    if log:
        df = pd.DataFrame({"day": [t["exit_time"].date() for t in log], "pl": pls})
        daily = df.groupby("day").pl.sum()
        up_days = int((daily > 0).sum()); down_days = int((daily < 0).sum())
        flat_days = int((daily == 0).sum())
    else:
        up_days = down_days = flat_days = 0
    return dict(
        profit_factor=pf, gross_win=gross_win, gross_loss=gross_loss,
        win_rate=float((pls > 0).mean()) if len(pls) else float("nan"),
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        expectancy_money=float(pls.mean()) if len(pls) else float("nan"),
        longest_losing_streak=longest,
        up_days=up_days, down_days=down_days, flat_days=flat_days,
        net_R=float(np.nansum(r_units)) if len(r_units) else 0.0,
        avg_net_R=float(np.nanmean(r_units)) if len(r_units) else float("nan"),
    )

def cost_over_third_R(W, msk, cost_px):
    """Rule-10 audit: how many taken trades had cost above one third of their
    risk. Should be zero - the eligibility filter exists to make it zero - so
    a non-zero count means the filter is not doing its job."""
    risk = W["risk"][msk]
    return int((cost_px > risk / 3.0).sum()), len(risk)

def purge_range(sig, exi, lo, hi):
    """Keep only trades that BEGIN AND END inside [lo, hi).

    The three-way split needs an arbitrary window, not just 'before or after
    one boundary'. A trade that starts in validation and finishes in the
    holdout belongs to neither and is dropped from both, exactly as at the
    discovery boundary."""
    sig = np.asarray(sig, int); exi = np.asarray(exi, int)
    starts = (sig >= lo) & (sig < hi)
    ends = (exi >= lo) & (exi < hi)
    keep = starts & ends
    return keep, dict(total=len(sig), kept=int(keep.sum()),
                      straddling=int((starts & ~ends).sum()),
                      other_side=int((~starts).sum()))

def resolve_window(W, P, tp_j, hold_cfg, lo, hi, deadline):
    """Trades whose signal and exit both fall inside bar window [lo, hi)."""
    n = len(W["i"])
    e = np.minimum(W["i"] + 1, P["N"] - 1)
    room_session = deadline[e] - e + 1
    has_room = room_session >= 1
    hold_vec = np.minimum(hold_cfg, np.maximum(room_session, 1))
    R, held, ok, xpx = outcome_variable_hold(W, P, tp_j, hold_vec)
    ok = ok & has_room
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return R, held, np.zeros(n, bool), dict(total=0, kept=0, straddling=0,
                                                other_side=0,
                                                no_room=int((~has_room).sum())), xpx
    eb = (W["i"][idx] + held[idx]).astype(int)
    ks, rep = purge_range(W["i"][idx], eb, lo, hi)
    keep = np.zeros(n, bool); keep[idx[ks]] = True
    rep["no_room"] = int((~has_room).sum())
    return R, held, keep, rep, xpx

def intraday_control(P, W, msk, tp_j, hold_cfg, deadline, lo, hi, cost_px,
                     reps=6, seed=17):
    """Matched random control that obeys the SAME session deadline.

    Using a fixed horizon for the control while the strategy's horizon varies
    with the time of day would make the two incomparable in exactly the way
    the engine audit spent this whole project removing. The control draws a
    random bar in the same window, takes the direction and risk of a real
    trade, and is then cut off by the same 20:30 deadline."""
    from exec_engine import execute, GAP_SKIP
    rng = np.random.default_rng(seed)
    o, h, l, c, N = P["o"], P["h"], P["l"], P["c"], P["N"]
    cost = np.full(N, cost_px, float)
    dirs = W["d"][msk].astype(int); risks = W["risk"][msk]
    n = len(dirs)
    if n == 0: return np.array([]), {}
    tps = [t for t in M.TPS if t is not None]
    tp_mult = None if tp_j is None else tps[tp_j]
    lo2 = max(lo, M.ATR_N + 200)
    pool = np.arange(lo2, max(lo2 + 1, hi - 2))
    e_pool = np.minimum(pool + 1, N - 1)
    pool = pool[(deadline[e_pool] - e_pool + 1) >= 1]
    if len(pool) < 50: return np.array([]), {}
    Rs, helds, longs, skipped = [], [], 0, 0
    for _ in range(reps):
        take = min(n, len(pool))
        pick = rng.choice(pool, size=take, replace=False)
        order = rng.permutation(n)[:take]
        for j, b in enumerate(pick):
            q = int(order[j]); d = int(dirs[q]); risk = float(risks[q])
            e = int(b) + 1
            hv = min(hold_cfg, max(int(deadline[e] - e + 1), 1))
            c_sig = c[b]
            stop = c_sig - d * risk
            targ = None if tp_mult is None else c_sig + d * tp_mult * risk
            t = execute(o, h, l, c, N, int(b), d, stop, risk, targ, hv, cost,
                        on_gap="skip")
            if t is None or t["reason"] == GAP_SKIP:
                skipped += 1; continue
            Rs.append(t["R"]); helds.append(t["held"]); longs += 1 if d > 0 else 0
    R = np.asarray(Rs, float)
    return R, dict(n=len(R), long_frac=(longs/len(R)) if len(R) else float("nan"),
                   mean_held=float(np.mean(helds)) if helds else float("nan"),
                   skipped=skipped, pool=len(pool), reps=reps)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("XAUUSDc ON THE REAL ACCOUNT - " + a.tf.upper())
    print("=" * 78)
    print(ACC.describe())
    print("\nPASS/FAIL CRITERIA, FIXED BEFORE THIS RUN:" + CRITERIA)

    m = M.load_tf(a.tf)
    P = M.prep(m)
    tf_min = S.bar_minutes(m.index)
    deadline, sid, closable = S.intraday_deadlines(m.index, tf_min)
    print("SESSION RULES IN FORCE")
    print(S.audit(m.index, tf_min))

    # M15/M5 data only starts in 2019 (the M1 cache's first year), so the H1
    # split would leave discovery empty. A SEPARATE split is declared for
    # sub-hourly timeframes, in source, before this run - not picked after
    # seeing where the data happens to start.
    disc_end = DISCOVERY_END if tf_min >= 60 else DISCOVERY_END_M15
    val_end = VALIDATION_END if tf_min >= 60 else VALIDATION_END_M15

    real_sp = P["spread"][np.isfinite(P["spread"]) & (P["spread"] > 0)]
    print(f"\nREAL BID/ASK IN THE DATA (Dukascopy, measured not assumed)")
    print(f"  median {np.median(real_sp)*1000:.0f} points, mean "
          f"{real_sp.mean()*1000:.0f}, p95 {np.percentile(real_sp,95)*1000:.0f}")
    print(f"  the terminal's current 260 points is TIGHTER than the historical"
          f" median - the 260-point scenario is therefore the optimistic one")

    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    n_val = int((m.index < pd.Timestamp(val_end, tz="UTC")).sum())
    N = P["N"]
    print(f"\nSPLIT   discovery [0,{n_disc}) = {m.index[0].date()}..{disc_end}"
          f"   validation [{n_disc},{n_val})   holdout [{n_val},{N}) "
          f"= {val_end}..{m.index[-1].date()}")
    if n_disc < 1000:
        print("  *** discovery too short for this timeframe - aborting");
        return None

    split = Split(m.index, disc_end)
    th = M.fit_thresholds(P, split)
    print(f"  thresholds fitted on DISCOVERY only: "
          + ", ".join(f"{k}={v:.4g}" for k, v in th.values.items()))

    # selection runs at the NORMAL scenario; stress is applied afterwards
    sel_cost = scenario_cost_px(SPREAD_SCENARIOS["normal"], 0.0)
    print(f"\n  selection cost model: {SPREAD_SCENARIOS['normal']:.0f} points "
          f"= {sel_cost:.3f} price units round trip, commission 0, swap 0")
    print(f"  rule-10 eligibility floor: risk >= {3*sel_cost:.3f} price units")

    holds = HOLDS_H1 if tf_min >= 60 else (8, 16, 32, 48)
    hold_max = int(max(holds))
    tps_real = [t for t in M.TPS if t is not None]

    print(f"\nGRID (frozen, declared in source): "
          f"{len(LOOKBACKS)}x{len(BUFFERS)}x{len(STOPS)} rules "
          f"x {len(TPS)} targets x {len(holds)} holds x {len(FILTERS)} filters")

    rows = []
    k_total = 0
    for look in LOOKBACKS:
        for buf in BUFFERS:
            for sm in STOPS:
                W = walk_for(P, look, buf, sm, sel_cost, hold_max)
                if W is None: continue
                F = M.build_filters(P, W, th)
                for tp in TPS:
                    tp_j = None if tp is None else tps_real.index(tp)
                    for hold in holds:
                        Rd, heldd, keepd, repd, _xp = resolve_window(
                            W, P, tp_j, hold, 0, n_disc, deadline)
                        for fname in FILTERS:
                            k_total += 1
                            msk = keepd.copy()
                            if fname is not None: msk &= F[fname]
                            nn = int(msk.sum())
                            if nn < 200: continue
                            r = Rd[msk]
                            rows.append(dict(
                                look=look, buf=buf, stop=sm, tp=tp, hold=hold,
                                filt=fname, n=nn, E=float(r.mean()),
                                sumR=float(r.sum()),
                                key=(look, buf, sm, tp, hold, fname)))
    bar = math.sqrt(2 * math.log(max(k_total, 2)))
    print(f"  cells actually tested: {k_total:,}  -> noise floor "
          f"|t| > {bar:.2f} (heuristic, not a 5% bar)")
    print(f"  cells with >= 200 discovery trades: {len(rows):,}")

    rows.sort(key=lambda x: -x["E"])
    print(f"\nTOP 10 BY DISCOVERY NET E(R) (selection view only - NOT a result)")
    print(f"  {'E(R)':>9}{'n':>7}{'sumR':>9}  configuration")
    for rr in rows[:10]:
        print(f"  {rr['E']:>+9.4f}{rr['n']:>7}{rr['sumR']:>+9.1f}  "
              f"look{rr['look']} buf{rr['buf']} {rr['stop']} "
              f"tp{rr['tp']} hold{rr['hold']} {rr['filt'] or '-'}")

    # ---- full gate on the leaders ----------------------------------------
    print(f"\nDISCOVERY GATE (all five criteria)")
    print(f"  {'n':>6}{'E(R)':>9}{'bootCI_lo':>11}{'skill':>9}{'boot t':>8}"
          f"  verdict  configuration")
    passed = []
    for rr in rows[:25]:
        look, buf, sm, tp, hold, fname = rr["key"]
        tp_j = None if tp is None else tps_real.index(tp)
        W = walk_for(P, look, buf, sm, sel_cost, hold_max)
        F = M.build_filters(P, W, th)
        Rd, heldd, keepd, _, _xp = resolve_window(W, P, tp_j, hold, 0, n_disc, deadline)
        msk = keepd.copy()
        if fname is not None: msk &= F[fname]
        r = Rd[msk]
        if len(r) < 200: continue
        ci = M.block_bootstrap_ci(r, W["i"][msk], heldd[msk])
        bt = M.block_bootstrap_t(r, W["i"][msk], heldd[msk], 1)
        ctrl, cst = intraday_control(P, W, msk, tp_j, hold, deadline, 0,
                                     n_disc, sel_cost)
        skill = (r.mean() - ctrl.mean()) if len(ctrl) >= 30 else float("nan")
        ok = (len(r) >= 200 and r.mean() > 0 and ci is not None and ci[0] > 0
              and np.isfinite(skill) and skill > 0
              and np.isfinite(bt) and abs(bt) > bar)
        print(f"  {len(r):>6}{r.mean():>+9.4f}"
              f"{(ci[0] if ci is not None else float('nan')):>+11.4f}"
              f"{skill:>+9.4f}{bt:>+8.2f}  "
              f"{'PASS' if ok else 'fail':>7}  "
              f"look{look} buf{buf} {sm} tp{tp} hold{hold} {fname or '-'}")
        if ok:
            passed.append(dict(key=rr["key"], n=len(r), E=float(r.mean()),
                               ci=list(ci), bt=float(bt), skill=float(skill)))

    print(f"\n  configurations clearing ALL FIVE discovery criteria: {len(passed)}")
    result = dict(tf=a.tf, k_total=k_total, bar=bar, n_rows=len(rows),
                  passed=passed, elapsed=time.time() - t0,
                  top=[{k: v for k, v in rr.items() if k != "key"}
                       for rr in rows[:10]])
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(result, indent=1, default=str))
    if not passed:
        print("\n  *** NOTHING PASSED DISCOVERY.")
        print("  Validation and the holdout stay closed. Opening them for a")
        print("  configuration that already failed in discovery would spend the")
        print("  only clean test this record has left, to confirm a failure.")
        print(f"\n  elapsed {time.time()-t0:.0f}s")
        return result
    print(f"\n  elapsed {time.time()-t0:.0f}s")
    return result

if __name__ == "__main__":
    main()
