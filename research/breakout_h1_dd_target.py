#!/usr/bin/env python3
"""Can the 20-bar H1 breakout actually reach 1R/day, or 10-50% a year inside a
35% drawdown budget? An independent replication, a control the original never
ran, and the sizing arithmetic.

WHERE THE RULE CAME FROM
  `Nonnor_Backtest_V3_GC_H1.xlsx` and `Breakout_DD30_Upgrade.xlsx` (supplied by
  the user, produced outside this repo) tested seven setups on GC=F H1 and found
  exactly one with a confidence interval clear of zero: "Breakout", net +45.6R
  over 383 trades, t +2.85. Its DD upgrade sheet sizes that to +72.8% return at
  1.5% risk with ~9.9% observed drawdown.

  Rules, transcribed verbatim from that workbook's frozen-rules sheet - nothing
  here is tuned, searched or chosen by this file:
    entry signal   close beyond the prior 20-bar extreme by >= 0.1 x ATR(14)
    fill           next bar's OPEN (plan frozen at the signal bar's close)
    stop           the OPPOSITE prior-range edge, offset 0.1 x ATR - so the risk
                   is the RANGE WIDTH, not an ATR multiple
    planned risk   |signal close - stop|, measured from the signal price, so a
                   gap through the fill can and does lose more than 1R
    target         signal close +/- 2 x planned risk
    eligibility    planned stop distance between 0.25 and 8 x ATR
    hold cap       24 bars, then exit at the close
    same-bar       stop wins when stop and target are both touched
    gap            an open already beyond a bracket fills AT THAT OPEN

WHY THIS FILE EXISTS RATHER THAN TRUSTING THE WORKBOOK
  The workbook's verdict rests on the expectancy confidence interval being above
  zero. That is the exact test this repo has already documented as insufficient:
  gold rose ~70% across the 2024-2026 window, and a rule that is long more often
  than short in a rising market earns a positive expectancy while knowing
  nothing. `smc_entry_test.py` opens with the same warning; `choch_fvg_three_
  setups.py` had to retract a result for precisely this reason.

  So three things are added here, none of which the source workbook did:
    1. MATCHED RANDOM CONTROL - same trade count, same long/short mix, same
       exit machinery, random timing. skill = rule - control is the part that
       cannot be drift.
    2. CROSS-MARKET OUT-OF-SAMPLE - the same frozen rule on ~25 other futures.
       The GC=F window is the window that produced the claim, so it cannot
       confirm it. Other markets are data the rule has never seen. If a 20-bar
       breakout with a range-width stop is a real structural effect, it is not
       a gold-only one.
    3. DRAWDOWN-BUDGETED SIZING - what risk fraction the user's stated 35%
       ceiling actually buys, and what return that implies.

  Calibrated on a driftless random walk first, as every signal in this repo is.

WHAT THE USER ASKED FOR, STATED AS A TESTABLE TARGET BEFORE THE RUN
  >= 1R per calendar day, OR 10-50%+ annual return at <= 35% max drawdown.
  Both are reported as measured numbers, not as a verdict on whether the rule
  "works" - a rule can hit a return target on a window and still have no skill.
"""
import json, math, sys, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

RANGE_BARS, ATR_N = 20, 14
BUF_ATR, TP_R, MAX_HOLD = 0.1, 2.0, 24
MIN_STOP_ATR, MAX_STOP_ATR = 0.25, 8.0
COST_BASE, COST_HIGH = 0.36, 0.8525      # round-trip, price units, gold
SEED, CTRL_REPS = 17, 10

UNI = {"GC=F": "gold", "SI=F": "silver", "HG=F": "copper", "CL=F": "crude",
       "NG=F": "natgas", "ES=F": "S&P500", "NQ=F": "nasdaq", "YM=F": "dow",
       "RTY=F": "russell", "ZB=F": "30y", "ZN=F": "10y", "6E=F": "euro",
       "6J=F": "yen", "6B=F": "pound", "6A=F": "aud", "6C=F": "cad",
       "ZC=F": "corn", "ZS=F": "soy", "ZW=F": "wheat", "KC=F": "coffee",
       "SB=F": "sugar", "CT=F": "cotton", "PL=F": "platinum",
       "HO=F": "heatoil", "RB=F": "gasoline", "LE=F": "cattle"}

def fetch(sym, rng="730d", iv="1h"):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def prep(df):
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = pd.Series(c).shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1 / ATR_N, adjust=False).mean().to_numpy()
    # prior-range extremes, strictly excluding the signal bar itself
    ph = pd.Series(h).rolling(RANGE_BARS).max().shift(1).to_numpy()
    pl = pd.Series(l).rolling(RANGE_BARS).min().shift(1).to_numpy()
    return dict(o=o, h=h, l=l, c=c, A=A, ph=ph, pl=pl, N=len(c), idx=df.index)

def signals(P):
    """+1 / -1 / 0 at the signal bar's close. Uses only completed bars."""
    c, A, ph, pl = P["c"], P["A"], P["ph"], P["pl"]
    s = np.zeros(P["N"], np.int8)
    with np.errstate(invalid="ignore"):
        up = c > ph + BUF_ATR * A
        dn = c < pl - BUF_ATR * A
    s[np.nan_to_num(up, nan=0).astype(bool)] = 1
    s[np.nan_to_num(dn, nan=0).astype(bool)] = -1
    return s

def plan(P, i, d):
    """The frozen plan at the signal bar's close: stop at the opposite range
    edge, target at 2x the PLANNED risk. Returns None if ineligible."""
    a, c = P["A"][i], P["c"][i]
    if not np.isfinite(a) or a <= 0: return None
    stop = (P["pl"][i] - BUF_ATR * a) if d > 0 else (P["ph"][i] + BUF_ATR * a)
    if not np.isfinite(stop): return None
    risk = (c - stop) * d
    if risk <= 0: return None
    if not (MIN_STOP_ATR * a <= risk <= MAX_STOP_ATR * a): return None
    return stop, c + d * TP_R * risk, risk

def resolve(P, i, d, cost, exit_mode="target"):
    """Fill at the next bar's open, then walk. Returns (net R, exit index).

    exit_mode "target" is the frozen rule: a fixed 2R limit and the range-edge
    stop. "trail" drops the target and trails the stop 1x planned risk behind
    the best price, moving to break-even at 1R first - the shape this repo
    already validated in `cost_vs_exit_decomposition.py`. "hold" removes the
    target entirely and lets the bar cap do the work, which measures how much
    the exit contributes at all."""
    p = plan(P, i, d)
    if p is None: return None
    stop, targ, risk = p
    o, h, l, c, N = P["o"], P["h"], P["l"], P["c"], P["N"]
    e = i + 1
    if e >= N: return None
    entry = o[e]
    # cost may be a scalar assumption or a per-bar array of MEASURED round-trip
    # cost. The array form is what `fetch_dukascopy.py` makes possible and is
    # the only form that can price a 2004 spread differently from a 2026 one.
    if hasattr(cost, "__len__"): cost = float(cost[e])
    use_target = exit_mode == "target"
    cur, moved, best = stop, False, entry
    for k in range(e, min(e + MAX_HOLD, N)):
        if exit_mode == "trail" and k > e:
            # trail starts one bar after entry, so the initial risk is real
            best = max(best, h[k - 1]) if d > 0 else min(best, l[k - 1])
            t2 = best - d * risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
            if moved:
                cur = max(cur, entry) if d > 0 else min(cur, entry)
        if k > e:      # an open already beyond a bracket fills at that open
            if (o[k] <= cur) if d > 0 else (o[k] >= cur):
                return ((o[k] - entry) * d - cost) / risk, k
            if use_target and ((o[k] >= targ) if d > 0 else (o[k] <= targ)):
                return ((o[k] - entry) * d - cost) / risk, k
        if (l[k] <= cur) if d > 0 else (h[k] >= cur):        # stop wins ties
            return ((cur - entry) * d - cost) / risk, k
        if use_target and ((h[k] >= targ) if d > 0 else (l[k] <= targ)):
            return ((targ - entry) * d - cost) / risk, k
        if exit_mode == "trail" and not moved and \
           ((h[k] >= entry + risk) if d > 0 else (l[k] <= entry - risk)):
            moved = True
    kx = min(e + MAX_HOLD - 1, N - 1)
    return ((c[kx] - entry) * d - cost) / risk, kx

def book(P, sig, cost, rand=False, seed=SEED, exit_mode="target"):
    """Sequential, non-overlapping. rand=True keeps the direction mix and the
    trade count but randomises WHEN each trade is taken."""
    N = P["N"]
    live = [(i, int(sig[i])) for i in range(RANGE_BARS + ATR_N, N - 1) if sig[i] != 0]
    if rand:
        rng = np.random.default_rng(seed)
        pool = np.arange(RANGE_BARS + ATR_N, N - 1)
        pick = np.sort(rng.choice(pool, size=min(len(live), len(pool)), replace=False))
        live = [(int(b), live[j % len(live)][1]) for j, b in enumerate(pick)]
    out, busy = [], -1
    for i, d in live:
        if i <= busy: continue
        r = resolve(P, i, d, cost, exit_mode)
        if r is None: continue
        out.append((i, r[0])); busy = r[1]
    return out

def stats(trades):
    a = np.array([r for _, r in trades], float)
    if len(a) < 20: return None
    e, sd = a.mean(), a.std(ddof=1)
    return dict(n=len(a), E=e, sd=sd, t=e / (sd / math.sqrt(len(a))),
                net=a.sum(), win=float((a > 0).mean()),
                pf=float(a[a > 0].sum() / -a[a < 0].sum()) if (a < 0).any() else float("inf"))

def skill_vs_control(P, sig, cost, exit_mode="target"):
    real = book(P, sig, cost, exit_mode=exit_mode)
    rs = stats(real)
    if rs is None: return None, None
    ctrl = np.concatenate([np.array([r for _, r in book(P, sig, cost, rand=True,
                                                        seed=SEED * 1000 + k,
                                                        exit_mode=exit_mode)])
                           for k in range(CTRL_REPS)])
    if len(ctrl) < 20: return rs, None
    sk = rs["E"] - ctrl.mean()
    se = math.sqrt(rs["sd"] ** 2 / rs["n"] + ctrl.var(ddof=1) / len(ctrl))
    return rs, dict(ctrlE=float(ctrl.mean()), skill=float(sk),
                    t=float(sk / se) if se > 0 else float("nan"))

# ------------------------------------------------------------- calibration --
def synth(n_bars, seed, sub=8, sigma=0.0011):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, size=(n_bars, sub))
    price, o, h, lo, c = 2000.0, *[np.empty(n_bars) for _ in range(4)]
    for i in range(n_bars):
        path = price * np.exp(np.cumsum(steps[i]))
        o[i], h[i], lo[i], c[i] = price, max(price, path.max()), min(price, path.min()), path[-1]
        price = path[-1]
    idx = pd.date_range("2020-01-01", periods=n_bars, freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)

def calibrate():
    print("CALIBRATION - driftless random walk, zero cost. A rule with no")
    print("information must read E ~ 0 and skill ~ 0 here.\n")
    ok = True
    for seed in (11, 23, 47):
        P = prep(synth(13000, seed))
        rs, sk = skill_vs_control(P, signals(P), cost=0.0)
        if rs is None:
            print(f"  seed {seed}: too few trades"); continue
        print(f"  seed {seed:>3}  n={rs['n']:>4}  E={rs['E']:+.4f}  "
              f"t={rs['t']:+.2f}  skill={sk['skill']:+.4f}  skill t={sk['t']:+.2f}")
        if abs(sk["t"]) > 2.5: ok = False
    print("\n  " + ("calibration clean.\n" if ok else
          "*** FAKE SKILL ON NOISE - this is a bug, stop here.\n"))
    return ok

# ------------------------------------------------------------------ sizing --
def equity_path(trades, f):
    """Fixed-fractional compounding. Returns (final multiple, max DD)."""
    eq, peak, dd = 1.0, 1.0, 0.0
    for _, r in trades:
        eq *= (1.0 + f * r)
        if eq <= 0: return 0.0, 1.0
        peak = max(peak, eq)
        dd = max(dd, 1.0 - eq / peak)
    return eq, dd

def main():
    print(__doc__.split("\n")[0] + "\n")
    if not calibrate(): sys.exit(1)

    gold = fetch("GC=F")
    P = prep(gold)
    days = (gold.index[-1] - gold.index[0]).days
    years = days / 365.25
    print(f"GC=F H1: {len(gold):,} bars  {gold.index[0].date()} -> "
          f"{gold.index[-1].date()}  ({years:.2f} years)\n")

    print("1) REPLICATION + THE CONTROL THE WORKBOOK DID NOT RUN")
    print(f"  {'cost':<14}{'n':>5}{'win':>7}{'PF':>7}{'E(R)':>9}{'t':>7}"
          f"{'net R':>9}{'ctrlE':>9}{'skill':>9}{'skill t':>9}")
    ref = None
    for nm, cost in (("base 0.36", COST_BASE), ("high 0.8525", COST_HIGH)):
        rs, sk = skill_vs_control(P, signals(P), cost)
        if rs is None: continue
        if ref is None: ref = (rs, cost)
        print(f"  {nm:<14}{rs['n']:>5}{rs['win']:>7.3f}{rs['pf']:>7.2f}"
              f"{rs['E']:>+9.4f}{rs['t']:>+7.2f}{rs['net']:>+9.2f}"
              f"{sk['ctrlE']:>+9.4f}{sk['skill']:>+9.4f}{sk['t']:>+9.2f}")
    print("\n  Workbook reference: n=383, net +45.60R, E +0.1191, t +2.85")
    print("  (it reported no control column - that is what 'skill' adds here)\n")

    print("2) THE USER'S TWO TARGETS, MEASURED")
    rs, cost = ref
    trades = book(P, signals(P), cost)
    r_per_day = rs["net"] / days
    print(f"  trades: {rs['n']} over {days} calendar days "
          f"({rs['n']/days:.2f} per day)")
    print(f"  R per calendar day: {r_per_day:+.4f}   "
          f"(target 1.0 -> short by {1.0/max(r_per_day,1e-9):.0f}x)" if r_per_day > 0
          else f"  R per calendar day: {r_per_day:+.4f}   (target 1.0 - not reachable)")
    print()
    print(f"  {'risk/trade':<12}{'final':>9}{'total ret':>11}{'CAGR':>9}{'max DD':>9}{'<=35%?':>8}")
    best = None
    for f in (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05):
        eq, dd = equity_path(trades, f)
        cagr = eq ** (1 / years) - 1 if eq > 0 else -1
        fits = dd <= 0.35
        if fits and (best is None or cagr > best[1]): best = (f, cagr, dd, eq)
        print(f"  {f:<12.3f}{eq:>9.3f}{eq-1:>+11.2%}{cagr:>+9.2%}{dd:>9.2%}"
              f"{'yes' if fits else 'NO':>8}")
    if best:
        print(f"\n  Best inside the 35% ceiling: risk {best[0]:.1%}/trade -> "
              f"{best[1]:+.2%} a year, max DD {best[2]:.2%}")
    print("  (max DD here is measured on trade-exit equity marks only - the true")
    print("   intrabar drawdown is worse, and gaps can breach a planned stop.)\n")

    print("3) CROSS-MARKET OUT-OF-SAMPLE - the same frozen rule, markets the")
    print("   claim has never seen. This is the test that decides whether the")
    print("   GC=F number is an effect or a window.")
    with ThreadPoolExecutor(max_workers=10) as ex:
        data = {n: d for n, d in zip(UNI.values(), ex.map(
            lambda s: (fetch(s) if True else None), UNI.keys()))}
    print(f"  {'market':<12}{'n':>5}{'E(R)':>9}{'skill':>9}{'skill t':>9}")
    rows, pooled = [], []
    for name, df in data.items():
        if df is None or len(df) < 3000: continue
        Q = prep(df)
        # cost in price units cannot be shared across markets; use a fraction
        # of each market's own ATR so the drag is comparable, not identical.
        c_i = 0.02 * float(np.nanmedian(Q["A"]))
        rs2, sk2 = skill_vs_control(Q, signals(Q), c_i)
        if rs2 is None or sk2 is None: continue
        rows.append((name, rs2, sk2)); pooled.append(sk2["skill"])
        print(f"  {name:<12}{rs2['n']:>5}{rs2['E']:>+9.4f}"
              f"{sk2['skill']:>+9.4f}{sk2['t']:>+9.2f}")
    if pooled:
        a = np.array(pooled)
        tt = a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))
        pos = int((a > 0).sum())
        print(f"\n  {len(a)} markets: mean skill {a.mean():+.4f}, "
              f"t {tt:+.2f}, positive in {pos}/{len(a)}")
        print("  A real structural effect shows up positive in most markets.")
        print("  A gold-window artefact does not.")

    print("\n4) IS GOLD'S NUMBER STABLE IN TIME, AND IS IT BETTER THAN JUST")
    print("   OWNING GOLD? Two checks the workbook did not run.")
    half = P["N"] // 2
    cut = P["idx"][half]
    early = [(i, r) for i, r in trades if i < half]
    late = [(i, r) for i, r in trades if i >= half]
    print(f"\n  chronological split at {cut.date()}")
    for nm, part in (("first half", early), ("second half", late)):
        st = stats(part)
        if st is None:
            print(f"  {nm:<13} too few trades"); continue
        print(f"  {nm:<13} n={st['n']:>4}  E={st['E']:+.4f}  t={st['t']:+.2f}"
              f"  net={st['net']:+.2f}R  win={st['win']:.3f}")
    print("  An edge that lives in one half only is a window, not a rule.")

    # Buy and hold, sized to the SAME realised drawdown, is the benchmark a
    # directional gold strategy has to beat to have earned its complexity.
    gc = gold.close.to_numpy(float)
    bh_ret = gc[-1] / gc[0] - 1.0
    eq = gc / gc[0]
    bh_dd = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
    lev = 0.35 / bh_dd if bh_dd > 0 else float("nan")
    print(f"\n  buy & hold GC=F over the same window: {bh_ret:+.2%} total, "
          f"{(1+bh_ret)**(1/years)-1:+.2%} a year, max DD {bh_dd:.2%}")
    print(f"  the same hold levered to the 35% DD ceiling ({lev:.2f}x): "
          f"{(1+bh_ret*lev)**(1/years)-1:+.2%} a year (approximate, ignores")
    print("  compounding path and financing cost)")
    if best:
        print(f"\n  the breakout rule at its best sizing: {best[1]:+.2%} a year "
              f"at {best[2]:.2%} DD")
    print("  If the rule does not clearly beat the levered hold, the signal is")
    print("  not what produced the return - gold's direction is.")

if __name__ == "__main__":
    main()
