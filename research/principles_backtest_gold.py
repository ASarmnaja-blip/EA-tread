#!/usr/bin/env python3
"""What I would actually trade, and what it does on gold.

THE PRINCIPLES, AND THE EVIDENCE IN THIS REPO FOR EACH

  P1  DO NOT TRY TO FORECAST DIRECTION.
      Sixteen research rounds, ~47 configurations, nine smart-money entries, a
      631-cell grid over 11 families and four timeframes. Not one entry rule
      has produced skill over a matched random control that clears a
      multiple-comparison bar. The correct response to that much evidence is
      not a better indicator; it is to stop paying for forecasts.

  P2  THE MEASURED ASYMMETRY IS IN THE EXIT.
      `cost_vs_exit_decomposition.py`: a 2-ATR trailing stop with break-even,
      on RANDOM entries at zero cost, returns +0.0336R per leg at t = +4.45
      across eight markets. A stop truncates the loss while a trend lets the
      winner run. That is the only thing in this program that replicates across
      markets without an entry rule attached.

  P3  TRADE THE HORIZON WHERE THE EFFECT EXISTS.
      `universe_trend_test.py`: daily trend across 27 futures, +0.2232R at
      t = +2.48, positive on 20 of 27 markets, binomial p = 0.0096. The
      identical rules on the identical markets hourly: -0.2670R at t = -6.23.
      This is the single strongest result in the repo and it is not intraday.

  P4  SIZE FOR THE DRAWDOWN, NOT THE TARGET.
      Same strategy at 0.5% / 1% / 2% risk: 20.2% / 38.6% / 64.1% a year, with
      28.2% / 51.5% / 83.9% drawdown. Position size is the only lever that
      moved drawdown in fifteen years of testing.

  P5  NOTHING IS BELIEVED UNTIL IT BEATS A MATCHED RANDOM CONTROL.
      Three separate bugs in this program manufactured discovery-sized numbers
      (a random-direction control, inverted stops, a trailing stop seeded from
      the entry bar). All three were caught the same way.

WHAT THIS FILE THEREFORE TESTS
  Not entry rules. Exit designs and horizon, on gold, against the benchmark
  that matters - buy and hold - and against a matched random control that says
  whether any of it is skill or simply gold going up.

  TWO NUMBERS ARE REPORTED FOR EVERY ROW AND THEY ANSWER DIFFERENT QUESTIONS.
  `E` is what the account would have made. `skill` is what the rule knew, with
  gold's own drift removed by a direction-matched control. A row with strong E
  and zero skill is not worthless - it is beta, and beta is money - but it must
  never be sold as an edge, which is the mistake this repo has recorded twice.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd

SEED, CTRL_REPS = 17, 10
RISK_PCT = 0.005          # P4: 0.5% of equity per trade
SPREAD = 0.7525           # the pessimistic measured OANDA number, not the quote

def fetch(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def prep(df):
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    N = len(c); s = pd.Series(c)
    pc = s.shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    sma200 = s.rolling(200).mean().to_numpy()
    don = {p: (s.rolling(p).max().shift(1).to_numpy(),
               s.rolling(p).min().shift(1).to_numpy()) for p in (20, 55)}
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - sma200) / A
    return dict(o=o, h=h, l=l, c=c, N=N, A=A, z=z, sma200=sma200, don=don,
                idx=df.index)

# ------------------------------------------------------- entry triggers ---
# None of these claims to forecast. Two are structural regime states, one is
# the incumbent in the EA, and one is deliberately information-free.
def t_none(P):
    """P1 taken literally: no view at all. Long every 20th bar."""
    s = np.zeros(P["N"], np.int8); s[::20] = 1
    return s

def t_trendzone(P):
    """The EA's Setup D: z = (close - SMA200)/ATR inside [1.08, 7.21], long
    only, firing on ENTERING the zone rather than every bar inside it."""
    z = P["z"]; s = np.zeros(P["N"], np.int8)
    inz = (z >= 1.08) & (z <= 7.21)
    s[1:][inz[1:] & ~inz[:-1]] = 1
    return s

def t_don55(P):
    """P3's rule, both directions: close beyond the 55-bar channel."""
    hi, lo = P["don"][55]; c = P["c"]; s = np.zeros(P["N"], np.int8)
    up = (c > hi) & ~(np.roll(c, 1) > np.roll(hi, 1))
    dn = (c < lo) & ~(np.roll(c, 1) < np.roll(lo, 1))
    s[up] = 1; s[dn] = -1; s[:2] = 0
    return s

def t_don55_long(P):
    s = t_don55(P); s[s < 0] = 0
    return s

def t_above200(P):
    """Long whenever price crosses above its own 200 SMA. The plainest
    structural regime statement there is."""
    c, m = P["c"], P["sma200"]; s = np.zeros(P["N"], np.int8)
    up = (c > m) & ~(np.roll(c, 1) > np.roll(m, 1))
    s[up] = 1; s[:2] = 0
    return s

TRIGGERS = {
    "no view (every 20)": t_none,
    "above SMA200":       t_above200,
    "trend zone (EA D)":  t_trendzone,
    "Donchian 55 long":   t_don55_long,
    "Donchian 55 both":   t_don55,
}

EXITS = {
    "trail 2ATR + BE":  dict(legs=(99.0,), be_at=1.0, trail=1.0),
    "trail 3ATR + BE":  dict(legs=(99.0,), be_at=1.0, trail=1.5),
    "8R target + time": dict(legs=(8.0,)),
    "3 legs 1/2/3 BE":  dict(legs=(1.0, 2.0, 3.0), be_at=1.0),
}

# ----------------------------------------------------------------- exits ---
def exit_run(P, start, entry, d, risk, design, hold, spread):
    """Stop tested before targets; break-even re-tested on the bar that moved
    it; the trail starts one bar AFTER entry so the initial risk really is
    `risk` and R means what it says."""
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    legs, be_at, trail = design["legs"], design.get("be_at"), design.get("trail")
    nl = len(legs)
    stop = entry - d * risk
    tg = [entry + d * risk * m for m in legs]
    alive = [True] * nl
    r, k, moved, best = 0.0, start + 1, False, entry
    while k < min(start + 1 + hold, N):
        cur = entry if moved else stop
        if trail and k - 1 > start:
            best = max(best, h[k-1]) if d > 0 else min(best, l[k-1])
            t2 = best - d * trail * risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            for x in range(nl):
                if alive[x]: r += ((cur-entry)*d - spread)/risk; alive[x] = False
            break
        for x in range(nl):
            if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                r += ((tg[x]-entry)*d - spread)/risk; alive[x] = False
                if be_at is not None and legs[x] >= be_at: moved = True
        if not any(alive): break
        k += 1
    kx = min(k, N-1)
    if any(alive):
        for x in range(nl):
            if alive[x]: r += ((c[kx]-entry)*d - spread)/risk
    return r/nl, kx

def book(P, sig, design, hold, rmult, spread, rand=False, seed=SEED):
    c, A, N = P["c"], P["A"], P["N"]
    live = [i for i in range(260, N-1) if sig[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
    if len(live) < 10: return [], []
    dirs = [int(sig[i]) for i in live]
    if rand:
        rng = np.random.default_rng(seed)
        pool = [i for i in range(260, N-1) if np.isfinite(A[i]) and A[i] > 0]
        pick = sorted(rng.choice(pool, size=min(len(live), len(pool)), replace=False))
        plan = [(int(i), dirs[j % len(dirs)]) for j, i in enumerate(pick)]
    else:
        plan = list(zip(live, dirs))
    rows, when, busy = [], [], -1
    for i, d in plan:
        if i <= busy: continue
        risk = rmult * A[i]
        if risk <= 0: continue
        r, kx = exit_run(P, i, c[i], d, risk, design, hold, spread)
        rows.append(r); when.append(kx); busy = kx
    return rows, when

def equity(rows, f=RISK_PCT):
    """Compound at fixed fractional risk `f`. Returns total growth and max DD."""
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rows:
        eq *= max(1e-9, 1 + f * r)
        if eq > peak: peak = eq
        dd = max(dd, 1 - eq/peak)
    return eq, dd

def risk_for_dd(rows, target_dd, years):
    """The risk fraction that would have produced `target_dd`, and the CAGR it
    delivers. Comparing a 0.5%-risk system's CAGR against buy and hold is not a
    fair fight - buy and hold is 100% exposed and took its full drawdown. This
    puts both on the same drawdown budget, which is the only basis on which two
    return numbers mean anything next to each other.

    It assumes the same trade sequence at higher size, which is exactly what a
    fixed-fractional system does, and it ignores the minimum-lot floor that
    ACCOUNT_SCALING.md says binds on small accounts."""
    lo, hi = 0.0001, 0.5
    for _ in range(40):
        mid = (lo + hi) / 2
        _, dd = equity(rows, mid)
        if dd < target_dd: lo = mid
        else: hi = mid
    g, dd = equity(rows, lo)
    return lo, (g**(1/years) - 1 if years > 0 and g > 0 else float("nan")), dd

def analyse(P, sig, design, hold, rmult, years, bh_dd):
    real, _ = book(P, sig, design, hold, rmult, SPREAD)
    if len(real) < 10: return None
    ctrl = []
    for rep in range(CTRL_REPS):
        cr, _ = book(P, sig, design, hold, rmult, SPREAD, True, SEED*1000+rep)
        ctrl.extend(cr)
    a = np.array(real)
    E, sd, n = a.mean(), a.std(ddof=1), len(a)
    out = dict(n=n, E=E, t=E/(sd/math.sqrt(n)), per_year=n/years)
    if len(ctrl) >= 10:
        b = np.array(ctrl)
        sk = E - b.mean()
        se = math.sqrt(sd**2/n + b.var(ddof=1)/len(b))
        out.update(skill=sk, skt=sk/se if se > 0 else np.nan)
    else:
        out.update(skill=np.nan, skt=np.nan)
    g, dd = equity(real)
    out.update(cagr=g**(1/years)-1 if years > 0 else np.nan, dd=dd)
    f, cg, _ = risk_for_dd(real, bh_dd, years)
    out.update(fair_f=f, fair_cagr=cg)
    return out

def main():
    print("What I would trade, measured on gold.")
    print(f"Spread ${SPREAD} per leg (the measured OANDA number, not the quote);")
    print(f"risk {RISK_PCT:.1%} of equity per trade; one position at a time.\n")

    for tf, (rng, iv, hold, rmult) in {
            "D1": ("20y", "1d", 60, 1.8),
            "H1": ("730d", "1h", 240, 1.8)}.items():
        try:
            df = fetch("GC=F", rng, iv)
        except Exception as e:
            print(f"{tf}: fetch failed {type(e).__name__}"); continue
        P = prep(df)
        years = (df.index[-1] - df.index[0]).days / 365.25
        bh = df.close.iloc[-1] / df.close.iloc[0]
        bh_dd = float((1 - df.close / df.close.cummax()).max())
        print("=" * 94)
        print(f"GOLD {tf}   {len(df):,} bars   {df.index[0].date()} -> "
              f"{df.index[-1].date()}   ({years:.1f} years)")
        print(f"BUY AND HOLD over the same span: {bh**(1/years)-1:+.1%} a year, "
              f"max drawdown {bh_dd:.1%}")
        print("=" * 94)
        hdr = (f"{'trigger':<20}{'exit':<19}{'n':>6}{'/yr':>6}{'E':>8}{'t':>7}"
               f"{'skill':>8}{'sk t':>7}{'CAGR':>8}{'maxDD':>7}"
               f"{'risk%':>7}{'CAGR@BH-DD':>11}")
        print(hdr); print("-" * len(hdr))
        rows = []
        for tn, tfun in TRIGGERS.items():
            sig = tfun(P)
            for xn, dz in EXITS.items():
                r = analyse(P, sig, dz, hold, rmult, years, bh_dd)
                if r is None: continue
                r.update(trig=tn, ex=xn); rows.append(r)
                print(f"{tn:<20}{xn:<19}{r['n']:>6}{r['per_year']:>6.1f}"
                      f"{r['E']:>+8.3f}{r['t']:>+7.2f}{r['skill']:>+8.3f}"
                      f"{r['skt']:>+7.2f}{r['cagr']:>+8.1%}{r['dd']:>7.1%}"
                      f"{r['fair_f']:>7.2%}{r['fair_cagr']:>+11.1%}")
        k = len(rows)
        if k:
            best = max(rows, key=lambda x: x["skt"] if np.isfinite(x["skt"]) else -9)
            print(f"\n  {k} cells. Expected max of {k} noise draws: "
                  f"sqrt(2*ln {k}) = {math.sqrt(2*math.log(k)):.2f}")
            print(f"  best skill t = {best['skt']:+.2f} "
                  f"({best['trig']}, {best['ex']})")
        print()

    # ------------------------------------------------- split-sample check --
    print("=" * 94)
    print("SPLIT-SAMPLE CHECK, GOLD D1 - the number above that is least stable")
    print("=" * 94)
    print("CAGR@BH-DD is built on maximum drawdown, which is the single least")
    print("reproducible statistic in a backtest: it is one observation, the worst")
    print("one, and sizing to it is how accounts get destroyed. Same rules, the")
    print("20 years cut in half, each half sized to ITS OWN buy-and-hold drawdown.\n")
    df = fetch("GC=F", "20y", "1d")
    mid = len(df) // 2
    halves = [("first half ", df.iloc[:mid]), ("second half", df.iloc[mid:])]
    print(f"{'trigger':<20}{'exit':<19}" + "".join(f"{h[0]:>22}" for h in halves))
    print(f"{'':<39}" + "".join(f"{'n':>6}{'risk%':>7}{'CAGR':>9}" for _ in halves))
    print("-" * 83)
    for tn, tfun in TRIGGERS.items():
        for xn, dz in EXITS.items():
            cells = []
            for _, sub in halves:
                Ps = prep(sub)
                yrs = (sub.index[-1] - sub.index[0]).days / 365.25
                bhdd = float((1 - sub.close / sub.close.cummax()).max())
                rows, _ = book(Ps, tfun(Ps), dz, 60, 1.8, SPREAD)
                if len(rows) < 10: cells.append(None); continue
                f, cg, _ = risk_for_dd(rows, bhdd, yrs)
                cells.append((len(rows), f, cg))
            if any(c is None for c in cells): continue
            print(f"{tn:<20}{xn:<19}" + "".join(
                f"{c[0]:>6}{c[1]:>7.2%}{c[2]:>+9.1%}" for c in cells))
    print("\nA rule whose two halves disagree in SIZE by several fold has not")
    print("measured a drawdown budget, it has measured one bad week.\n")

    print("HOW TO READ THIS")
    print("  E and skill answer different questions. E is what the account did.")
    print("  skill is what the RULE knew, with gold's own drift removed by a")
    print("  direction-matched control. On a metal that went up tenfold, a")
    print("  long-only rule can post a fine E with skill indistinguishable from")
    print("  zero - that is beta, it spends the same, and it is not an edge.")
    print("  Compare every CAGR against the buy-and-hold line above its table,")
    print("  and every maxDD too. A rule that returns less than buy and hold")
    print("  with more drawdown has cost you money to run.")
    print("")
    print("  CAGR@BH-DD is the fair fight: the return each rule delivers when")
    print("  sized to take the SAME maximum drawdown buy and hold took, with")
    print("  the risk fraction that produces it in the column beside it. A rule")
    print("  earning less than buy and hold on the same drawdown budget is")
    print("  strictly worse than owning the metal. Note where those risk")
    print("  fractions land: several are far above anything ACCOUNT_SCALING.md")
    print("  says a small account can size, so they are arithmetic, not offers.")

if __name__ == "__main__":
    main()
