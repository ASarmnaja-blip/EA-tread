#!/usr/bin/env python3
"""The four KRV families again, this time against their written specifications.

WHY THERE IS A SECOND VERSION

  `vendor_families.py` tested four families reconstructed from their NAMES,
  because the .ex5 binaries are unreadable. The vendor then supplied written
  specifications, and against those my first implementation was wrong in ways
  that make its REJECTED verdict worthless as evidence about these families:

    volume_poc    I built a volume-profile point-of-control. The actual
                  strategy is a volume-weighted ORDER BLOCK with an ATR x 4
                  displacement trigger and a retest entry. Not a variant of
                  what I tested - a different strategy.

    exhaustion    I tested a run plus a wick rejection and ignored volume
                  entirely. Volume IS the mechanism: the run must show
                  DECLINING relative volume, and the reversal bar must trade
                  on volume ABOVE the run's own average. Without that it is
                  not the strategy, it is a streak counter.

    divergence    I tested Regular divergence with no trend filter. The spec
                  has Hidden divergence as a separate signal and names the
                  HTF trend gate as the single biggest win-rate lever.

    compression   I used a rolling range quantile. The spec requires BBW AND
                  ATR both under their own means, held for a minimum number
                  of bars, then a close breakout with an impulse-sized body
                  and optionally a volume surge.

  Two of four were the wrong strategy and two were missing their main filter.
  A negative result on a misimplementation says nothing about the strategy, so
  this file replaces that test rather than supplementing it.

WHAT IS STILL NOT BEING TESTED

  These are reimplementations from prose. They are much closer than v1 and
  they are still not the binaries. The asymmetry from v1 holds: a dead family
  is evidence against builds of it; a live one justifies asking for the .mq5
  and nothing more.

  Every signal is causal. Pivots are shifted by their right-hand lookback so
  they only exist once confirmed, volume averages are shifted by one bar, and
  entry is the next bar's open - the spec's own "No Repaint" requirement,
  which is also the bug that forced two retractions in this repo.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB
import multi_tf_setup_grid as G
from strictness import randomise_timing

SEED = 17
EXITS = ("1leg 2R BE", "3leg 1/2/3 BE")
RM = 1.5


def rsi_of(c, p):
    s = pd.Series(c); d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / p, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / p, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()


def pivots(x, left, right):
    """Confirmed pivot highs/lows, shifted right so they exist only once the
    right-hand bars have printed. The spec calls this No Repaint; this repo
    calls it the bug that invalidated the wick-tip and M1/M5 results."""
    s = pd.Series(x)
    w = left + right + 1
    hi = (s == s.rolling(w, center=True).max())
    lo = (s == s.rolling(w, center=True).min())
    return (hi.fillna(False).shift(right).fillna(False).to_numpy(),
            lo.fillna(False).shift(right).fillna(False).to_numpy())


# --------------------------------------------------------------------------
# 1. Divergence Reversal Navigator
# --------------------------------------------------------------------------
def f_divergence(P, mode="regular", left=5, right=5, rsi_p=14,
                 min_gap=5, max_gap=60, htf_gate=False, htf_ema=200):
    """Regular (reversal) or Hidden (continuation) price/RSI divergence.

      regular bullish   price Lower Low,  RSI Higher Low
      regular bearish   price Higher High, RSI Lower High
      hidden  bullish   price Higher Low, RSI Lower Low
      hidden  bearish   price Lower High, RSI Higher High

    min_gap is the spec's Range Filter: two pivots closer than this are one
    event seen twice, not two signals."""
    c, N = P["c"], P["N"]
    r = rsi_of(c, rsi_p)
    ph, pl = pivots(c, left, right)
    ema = pd.Series(c).ewm(span=htf_ema, adjust=False).mean().to_numpy()
    out = np.zeros(N, np.int8)
    last_lo = last_hi = -1
    for i in range(N):
        if pl[i]:
            if last_lo >= 0 and min_gap <= i - last_lo <= max_gap \
                    and np.isfinite(r[i]) and np.isfinite(r[last_lo]):
                if mode == "regular" and c[i] < c[last_lo] and r[i] > r[last_lo]:
                    out[i] = 1
                elif mode == "hidden" and c[i] > c[last_lo] and r[i] < r[last_lo]:
                    out[i] = 1
            last_lo = i
        if ph[i]:
            if last_hi >= 0 and min_gap <= i - last_hi <= max_gap \
                    and np.isfinite(r[i]) and np.isfinite(r[last_hi]):
                if mode == "regular" and c[i] > c[last_hi] and r[i] < r[last_hi]:
                    out[i] = -1
                elif mode == "hidden" and c[i] < c[last_hi] and r[i] > r[last_hi]:
                    out[i] = -1
            last_hi = i
    if htf_gate:
        # The spec's trend filter: only take signals aligned with the larger
        # trend. For Regular (counter-trend by design) this is deliberately
        # restrictive; for Hidden it is the intended use.
        with np.errstate(invalid="ignore"):
            out[(out > 0) & ~(c > ema)] = 0
            out[(out < 0) & ~(c < ema)] = 0
    return out


# --------------------------------------------------------------------------
# 2. Compression Range Breakout
# --------------------------------------------------------------------------
def f_compression(P, bb_p=20, look=100, min_bars=6, impulse=1.0,
                  vol_surge=False, vol_mult=1.2):
    """BBW and ATR both below their own rolling means for min_bars, then a
    close beyond the squeeze range with an impulse-sized body."""
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    s = pd.Series(c)
    ma = s.rolling(bb_p).mean()
    sd = s.rolling(bb_p).std()
    bbw = ((ma + 2 * sd) - (ma - 2 * sd)) / ma
    bbw_m = bbw.rolling(look).mean().shift(1)
    atr_s = pd.Series(A)
    atr_m = atr_s.rolling(look).mean().shift(1)
    with np.errstate(invalid="ignore"):
        squeezed = ((bbw < bbw_m) & (atr_s < atr_m)).fillna(False).to_numpy()
    run = np.zeros(N, int)
    for i in range(1, N):
        run[i] = run[i - 1] + 1 if squeezed[i] else 0

    v = np.nan_to_num(np.asarray(P.get("vol", np.zeros(N)), float))
    vma = pd.Series(v).rolling(20).mean().shift(1).to_numpy()

    out = np.zeros(N, np.int8)
    box_hi = box_lo = np.nan
    box_live = False
    cooldown = 0
    for i in range(1, N):
        if cooldown > 0:
            cooldown -= 1
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        # a squeeze that has just ended defines the box
        if run[i - 1] >= min_bars and not squeezed[i]:
            j = i - run[i - 1]
            box_hi = h[j:i].max(); box_lo = l[j:i].min()
            box_live = True
        if not box_live or not np.isfinite(box_hi) or cooldown > 0:
            continue
        body = abs(c[i] - o[i])
        if body < impulse * a:
            continue
        if vol_surge and not (np.isfinite(vma[i]) and v[i] > vol_mult * vma[i]):
            continue
        if c[i] > box_hi:
            out[i] = 1; box_live = False; cooldown = 5
        elif c[i] < box_lo:
            out[i] = -1; box_live = False; cooldown = 5
    return out


# --------------------------------------------------------------------------
# 3. Exhaustion Flow Reversal
# --------------------------------------------------------------------------
def f_exhaustion(P, run_min=4, run_max=9, flip_vol=1.0, body_ratio=0.5,
                 close_pos=0.6, require_decline=True, break_confirm=False):
    """A directional run on FADING volume, then an opposite bar on volume
    above the run's own average.

    The volume conditions are the strategy. A version without them is a streak
    counter, which is what v1 of this file tested."""
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    v = np.nan_to_num(np.asarray(P.get("vol", np.zeros(N)), float))
    rng_ = np.maximum(h - l, 1e-9)
    up = np.zeros(N, int); dn = np.zeros(N, int)
    for i in range(1, N):
        up[i] = up[i - 1] + 1 if c[i] > c[i - 1] else 0
        dn[i] = dn[i - 1] + 1 if c[i] < c[i - 1] else 0
    out = np.zeros(N, np.int8)
    for i in range(run_max + 2, N):
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        # the run ended on the PREVIOUS bar; this bar is the candidate shift
        for d, runlen in ((1, up[i - 1]), (-1, dn[i - 1])):
            if not (run_min <= runlen <= run_max):
                continue
            j0 = i - 1 - runlen + 1
            rv = v[j0:i]
            if len(rv) < 2 or rv.mean() <= 0:
                continue
            if require_decline:
                # volume fading through the run: second half below first half
                k = len(rv) // 2
                if k < 1 or rv[k:].mean() >= rv[:k].mean():
                    continue
            if v[i] < flip_vol * rv.mean():
                continue
            body = abs(c[i] - o[i])
            if body < body_ratio * rng_[i]:
                continue
            # shift bar must close against the run
            if d > 0:  # run was up -> shift is a down bar -> we SELL
                if c[i] >= o[i]:
                    continue
                if (h[i] - c[i]) / rng_[i] > (1 - close_pos):
                    continue
                if break_confirm and c[i] >= l[i - 1]:
                    continue
                out[i] = -1
            else:
                if c[i] <= o[i]:
                    continue
                if (c[i] - l[i]) / rng_[i] < close_pos:
                    continue
                if break_confirm and c[i] <= h[i - 1]:
                    continue
                out[i] = 1
    return out


# --------------------------------------------------------------------------
# 4. Volume Power Zones
# --------------------------------------------------------------------------
def f_power_zones(P, left=10, right=10, vol_ma=20, vol_min=0.5, disp=4.0,
                  cooldown=5, zone_tol=0.25):
    """Volume-weighted order block, ATR x disp displacement trigger, retest.

    This is the strategy v1 replaced with a volume profile. The zone is the
    pivot bar's range; it only becomes tradeable after price displaces away by
    disp x ATR, and the signal is price returning to it."""
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    v = np.nan_to_num(np.asarray(P.get("vol", np.zeros(N)), float))
    vma = pd.Series(v).rolling(vol_ma).mean().shift(1).to_numpy()
    ph, pl = pivots(c, left, right)
    out = np.zeros(N, np.int8)
    zones = []           # (dir, lo, hi, trigger, displaced, born)
    last_sig = -10 ** 9
    for i in range(N):
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        # a confirmed pivot with enough relative volume creates a zone
        for flag, d in ((pl[i], 1), (ph[i], -1)):
            if not flag:
                continue
            j = i - right
            if j < 0 or not np.isfinite(vma[j]) or vma[j] <= 0:
                continue
            strength = v[j] / vma[j]
            if strength < vol_min:
                continue
            trig = (l[j] + disp * a) if d > 0 else (h[j] - disp * a)
            zones.append([d, l[j], h[j], trig, False, i])
        # update and test
        for z in zones:
            d, zlo, zhi, trig, done, born = z
            if i <= born:
                continue
            if not done:
                if (c[i] > trig) if d > 0 else (c[i] < trig):
                    z[4] = True
                continue
            # displaced already: wait for a retest of the block
            if i - last_sig < cooldown:
                continue
            lo_, hi_ = zlo - zone_tol * a, zhi + zone_tol * a
            if lo_ <= c[i] <= hi_:
                # confirmation candle in the zone's direction
                if (c[i] > o[i]) if d > 0 else (c[i] < o[i]):
                    out[i] = d
                    last_sig = i
                    z[4] = False      # consume the zone
        zones = [z for z in zones if i - z[5] < 500]
    return out


FAMILIES = {
    "div_regular": (f_divergence, [
        dict(mode="regular", htf_gate=False),
        dict(mode="regular", htf_gate=True)]),
    "div_hidden": (f_divergence, [
        dict(mode="hidden", htf_gate=False),
        dict(mode="hidden", htf_gate=True)]),
    "compression": (f_compression, [
        dict(min_bars=6, impulse=1.0, vol_surge=False),
        dict(min_bars=6, impulse=1.0, vol_surge=True),
        dict(min_bars=10, impulse=1.5, vol_surge=False)]),
    "exhaustion": (f_exhaustion, [
        dict(run_min=4, run_max=9, require_decline=True),
        dict(run_min=4, run_max=9, require_decline=True, break_confirm=True),
        dict(run_min=3, run_max=12, require_decline=False)]),
    "power_zones": (f_power_zones, [
        dict(vol_min=0.5, disp=4.0),
        dict(vol_min=1.0, disp=3.0)]),
}


def book(Pg, sig, exit_name, hold, spread, lo, hi):
    c, A, N = Pg["c"], Pg["A"], Pg["N"]
    design = G.EXITS[exit_name]
    live = np.where((sig != 0) & np.isfinite(A) & (A > 0))[0]
    live = live[(live >= max(lo, 320)) & (live < min(hi, N - 1))]
    R, I, HD = [], [], []
    busy = -1
    for i in live:
        i = int(i)
        if i <= busy:
            continue
        risk = RM * A[i]
        if risk <= 0:
            continue
        r, kx = G.exit_run(Pg, i, c[i], int(sig[i]), risk, design, hold, spread)
        if r is None:
            continue
        R.append(r); I.append(float(i)); HD.append(float(max(kx - i, 1)))
        busy = kx
    if len(R) < 20:
        return None
    return np.asarray(R), np.asarray(I), np.asarray(HD)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--hold", type=int, default=48)
    a = ap.parse_args()
    t0 = time.time()

    print("THE FOUR KRV FAMILIES, AGAINST THEIR WRITTEN SPECS")
    print("=" * 100)
    print(__doc__.split("WHY THERE IS A SECOND VERSION")[1]
          .split("WHAT IS STILL NOT BEING TESTED")[0])

    m = M.load_tf(a.tf)
    P0 = M.prep(m)
    spread = float(EB.scenario_cost_px(260.0, 0.0) / np.nanmedian(P0["c"]))
    cost_R = float(EB.scenario_cost_px(260.0, 0.0) /
                   (RM * np.nanmedian(P0["A"])))
    disc_end = EB.DISCOVERY_END if S.bar_minutes(m.index) >= 60 \
        else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))
    Pg["vol"] = P0["vol"]

    k = sum(len(v[1]) for v in FAMILIES.values()) * len(EXITS)
    floor = math.sqrt(2 * math.log(k))
    print(f"data    {a.tf} {m.index[0].date()} -> {m.index[-1].date()}, "
          f"discovery {n_disc:,} bars")
    print(f"tests   {k}, floor |t| > {floor:.2f}   "
          f"cost {cost_R:.4f}R at a {RM} ATR stop\n")

    rng = np.random.default_rng(SEED)
    rows = []
    print(f"  {'family':<14}{'config':<44}{'exit':<16}{'n_d':>7}{'skill_d':>9}"
          f"{'t_d':>7}{'n_h':>7}{'skill_h':>9}{'t_h':>7}")
    for fam, (fn, grid) in FAMILIES.items():
        for gp in grid:
            try:
                sig = fn(Pg, **gp)
            except Exception as e:
                print(f"  {fam:<14}{str(gp)[:43]:<44}FAILED {type(e).__name__}: {e}")
                continue
            fired = int((sig != 0).sum())
            ps = ",".join(f"{x}={y}" for x, y in gp.items())
            if fired < 40:
                print(f"  {fam:<14}{ps[:43]:<44}only {fired} signals")
                continue
            for ex in EXITS:
                res = {}
                for lab, (lo, hi) in (("d", (0, n_disc)),
                                      ("h", (n_disc, len(m)))):
                    b = book(Pg, sig, ex, a.hold, spread, lo, hi)
                    cb = book(Pg, randomise_timing(sig, lo, hi, rng), ex,
                              a.hold, spread, lo, hi)
                    res[lab] = None if (b is None or cb is None) else dict(
                        n=len(b[0]), skill=float(b[0].mean() - cb[0].mean()),
                        t=float(M.block_bootstrap_t(
                            b[0] - cb[0].mean(), b[1], b[2], 1)))
                if res["d"] is None or res["h"] is None:
                    print(f"  {fam:<14}{ps[:43]:<44}{ex:<16}  too few trades")
                    continue
                d_, h_ = res["d"], res["h"]
                rows.append(dict(family=fam, cfg=ps, exit=ex, **{
                    "n_d": d_["n"], "skill_d": d_["skill"], "t_d": d_["t"],
                    "n_h": h_["n"], "skill_h": h_["skill"], "t_h": h_["t"]}))
                print(f"  {fam:<14}{ps[:43]:<44}{ex:<16}{d_['n']:>7,}"
                      f"{d_['skill']:>+9.4f}{d_['t']:>+7.2f}{h_['n']:>7,}"
                      f"{h_['skill']:>+9.4f}{h_['t']:>+7.2f}")

    if not rows:
        print("\n  nothing produced a usable book")
        return
    T = pd.DataFrame(rows)

    print("\n" + "=" * 100)
    print("VERDICT PER FAMILY  (all three parts of the registered criterion)")
    print("=" * 100)
    # The criterion says "at least ONE configuration" clears all three parts.
    # Judging only the highest-t_d configuration is a different and stricter
    # test, and it hid a passing row here: compression with the volume surge
    # at 1leg 2R BE clears everything, while the 3leg version of the same
    # signal has the higher t_d and a negative holdout. Same bug shape as v1 -
    # the code not implementing the criterion already on disk.
    T["passes"] = ((T["t_d"] > floor) & (T["skill_h"] > 0)
                   & (T["skill_h"] > cost_R))
    print(f"  {'family':<14}{'cfgs':>6}{'passing':>9}{'best t_d':>10}"
          f"{'best passing skill_h':>22}   verdict")
    for fam, g in T.groupby("family"):
        p = g[g["passes"]]
        best_t = g["t_d"].max()
        if len(p):
            b = p.loc[p["skill_h"].idxmax()]
            why = "ALIVE - ask for the .mq5"
            sh = f"{b['skill_h']:+.4f}"
        else:
            why = ("dead" if best_t <= floor
                   else "clears floor, fails holdout or cost")
            sh = "-"
        print(f"  {fam:<14}{len(g):>6}{len(p):>9}{best_t:>+10.2f}{sh:>22}"
              f"   {why}")

    if T["passes"].any():
        print(f"\n  CONFIGURATIONS THAT CLEAR ALL THREE PARTS")
        for _, r in T[T["passes"]].iterrows():
            print(f"    {r['family']} | {r['cfg']} | {r['exit']}")
            print(f"      discovery skill {r['skill_d']:+.4f} t {r['t_d']:+.2f}"
                  f"  ({int(r['n_d']):,} trades)")
            print(f"      holdout   skill {r['skill_h']:+.4f} t {r['t_h']:+.2f}"
                  f"  ({int(r['n_h']):,} trades)")
        print(f"\n  Before this is treated as a finding, three things about it:")
        print(f"    - it is {int(T['passes'].sum())} of {len(T)} tests, and a "
              f"space of {len(T)} dead tests returns\n"
              f"      about {0.0228*len(T):.1f} at t>2 by chance")
        print(f"    - the holdout t does NOT itself clear the floor, so the")
        print(f"      out-of-sample number is positive but not significant")
        print(f"    - sister configurations of the same signal disagree, which")
        print(f"      is what a fragile result looks like from the outside")
        print(f"  The registered criterion is met. That earns a cross-market")
        print(f"  replication, not a position.")

    print(f"\n  floor {floor:.2f} for {k} tests   cost {cost_R:.4f}R")
    print(f"\n  v1 of this file tested the wrong strategy for two of the four")
    print(f"  and dropped the main filter from the other two, so its REJECTED")
    print(f"  verdict is superseded by this table rather than confirmed by it.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
