#!/usr/bin/env python3
"""At 1 to 5 trades a week, what is actually achievable? A portfolio answer.

THE QUESTION
  One instrument cannot supply that frequency at the horizon that works.
  Donchian 55 on gold daily fires 3.8 times a YEAR. 1-5 trades a week is
  52-260 a year, so the only way to reach it at the daily horizon is BREADTH -
  the same rule across many markets. That is not a workaround; it is the finding
  `universe_trend_test.py` already produced (+0.2232R, 20 of 27 markets,
  binomial p = 0.0096) and the reason R/day scales with market count.

WHAT IS SIMULATED
  A real book, not a list of trades:
    - 27 CME futures, daily bars, 20 years
    - Donchian breakout, several lookbacks, to tune FREQUENCY not returns
    - trail 2 ATR with break-even at 1R (the exit that measured best here)
    - fixed fractional risk on equity AT ENTRY, positions held concurrently
    - a cap on how many can be open at once

  Equity is marked to market EVERY DAY on every open position. Compounding on
  exits alone understates drawdown badly when positions overlap, and drawdown is
  the number the whole thing gets sized on.

THE CONTROL
  The identical book with random entry dates, matched count and matched
  direction mix per market. Anything the rule earns above that is what the rule
  knew; the rest is the futures book's own drift.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

SEED = 17
TRAIL, BE_AT, RMULT = 1.0, 1.0, 1.8   # trail 2xATR (1.0 x risk), BE at 1R
HOLD = 120                            # trading days
COST = 0.0002                         # 2bp of price per round turn
MAX_CONCURRENT = 12

UNI = {"GC=F":"gold","SI=F":"silver","HG=F":"copper","PL=F":"platinum",
       "CL=F":"crude","NG=F":"natgas","RB=F":"gasoline","HO=F":"heatoil",
       "ES=F":"S&P500","NQ=F":"nasdaq","YM=F":"dow","RTY=F":"russell",
       "ZB=F":"30y","ZN=F":"10y","ZF=F":"5y",
       "6E=F":"euro","6J=F":"yen","6B=F":"pound","6A=F":"aud","6C=F":"cad",
       "ZC=F":"corn","ZS=F":"soy","ZW=F":"wheat","KC=F":"coffee",
       "SB=F":"sugar","CT=F":"cotton","LE=F":"cattle"}

def fetch(sym):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + "?range=20y&interval=1d")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def prep(df):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    s = pd.Series(c); pc = s.shift(1)
    A = pd.concat([pd.Series(h-l), (pd.Series(h)-pc).abs(),
                   (pd.Series(l)-pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1/14, adjust=False).mean().to_numpy()
    return dict(h=h, l=l, c=c, A=A, N=len(c), idx=df.index)

def signals(P, n):
    s = pd.Series(P["c"])
    hi = s.rolling(n).max().shift(1).to_numpy()
    lo = s.rolling(n).min().shift(1).to_numpy()
    c = P["c"]; out = np.zeros(P["N"], np.int8)
    up = (c > hi) & ~(np.roll(c, 1) > np.roll(hi, 1))
    dn = (c < lo) & ~(np.roll(c, 1) < np.roll(lo, 1))
    out[up] = 1; out[dn] = -1; out[:2] = 0
    return out

def walk(P, i, d):
    """Run one trade. Returns (exit_idx, daily marks in R, final R).
    Trail starts one bar AFTER entry so the initial risk really is `risk`."""
    h, l, c, A, N = P["h"], P["l"], P["c"], P["A"], P["N"]
    risk = RMULT * A[i]
    if not np.isfinite(risk) or risk <= 0: return None
    entry = c[i]
    stop = entry - d*risk
    moved, best, marks = False, entry, []
    k = i + 1
    while k < min(i+1+HOLD, N):
        cur = entry if moved else stop
        if k-1 > i:
            best = max(best, h[k-1]) if d > 0 else min(best, l[k-1])
            t2 = best - d*TRAIL*risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            marks.append(((cur-entry)*d - COST*entry)/risk)
            return k, marks, marks[-1]
        if not moved and ((d > 0 and h[k] >= entry + d*BE_AT*risk) or
                          (d < 0 and l[k] <= entry + d*BE_AT*risk)):
            moved = True
        marks.append(((c[k]-entry)*d - COST*entry)/risk)
        k += 1
    kx = min(k, N-1)
    if not marks: return None
    return i + len(marks), marks, marks[-1]

def build(P, sig, rand=False, seed=SEED):
    """All trades for one market, one position at a time."""
    N, A = P["N"], P["A"]
    live = [i for i in range(260, N-1) if sig[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
    if not live: return []
    dirs = [int(sig[i]) for i in live]
    if rand:
        rng = np.random.default_rng(seed)
        pool = [i for i in range(260, N-1) if np.isfinite(A[i]) and A[i] > 0]
        pick = sorted(rng.choice(pool, size=min(len(live), len(pool)), replace=False))
        plan = [(int(i), dirs[j % len(dirs)]) for j, i in enumerate(pick)]
    else:
        plan = list(zip(live, dirs))
    out, busy = [], -1
    for i, d in plan:
        if i <= busy: continue
        t = walk(P, i, d)
        if t is None: continue
        kx, marks, final = t
        # dates and marks are built to the SAME length: one mark per bar held,
        # starting the bar after entry. Letting them drift apart by one is what
        # broke the first run of this file.
        dates = list(P["idx"][i+1:i+1+len(marks)])
        assert len(dates) == len(marks)
        out.append(dict(entry=P["idx"][i], exit=dates[-1], R=final,
                        marks=marks, dates=dates))
        busy = kx
    return out

def portfolio(trades, risk_pct, cap=MAX_CONCURRENT):
    """Daily mark-to-market book. Risk is a fixed fraction of equity AT ENTRY,
    so an open position's dollar risk does not move while it is running."""
    if not trades: return None
    trades = sorted(trades, key=lambda t: t["entry"])
    days = sorted({d for t in trades for d in t["dates"]})
    if not days: return None
    dayix = {d: j for j, d in enumerate(days)}

    # Map every trade onto positions in the global day index once, so the
    # daily loop is a lookup rather than a search.
    for t in trades:
        t["_pos"] = [dayix[d] for d in t["dates"] if d in dayix]
        t["_mk"] = [m for d, m in zip(t["dates"], t["marks"]) if d in dayix]

    equity = 1.0
    curve = np.empty(len(days))
    open_pos, taken, ti = [], [], 0
    for j, day in enumerate(days):
        while ti < len(trades) and trades[ti]["entry"] <= day:
            t = trades[ti]; ti += 1
            if len(open_pos) >= cap or not t["_pos"]: continue
            open_pos.append(dict(t=t, dollar=risk_pct*equity))
            taken.append(t)
        unreal, still = 0.0, []
        for p in open_pos:
            t = p["t"]; pos = t["_pos"]
            k = j - pos[0]
            if k < 0:
                still.append(p); continue
            if k >= len(t["_mk"]):
                equity += p["dollar"] * t["_mk"][-1]      # realise at last mark
                continue
            if k == len(t["_mk"]) - 1:
                equity += p["dollar"] * t["_mk"][k]       # realise on exit day
                continue
            unreal += p["dollar"] * t["_mk"][k]
            still.append(p)
        open_pos = still
        curve[j] = equity + unreal
    return pd.Series(curve, index=pd.DatetimeIndex(days)), taken

def metrics(curve, taken, years):
    eq = curve.dropna()
    if len(eq) < 50 or not taken: return None
    R = np.array([t["R"] for t in taken])
    dd = float((1 - eq/eq.cummax()).max())
    growth = float(eq.iloc[-1] / eq.iloc[0])
    cagr = growth**(1/years) - 1 if growth > 0 else float("nan")
    dr = eq.pct_change().dropna()
    sharpe = float(dr.mean()/dr.std()*math.sqrt(252)) if dr.std() > 0 else float("nan")
    w, l = R[R > 0], R[R <= 0]
    streak = mx = 0
    for r in R:
        streak = streak+1 if r <= 0 else 0
        mx = max(mx, streak)
    return dict(
        n=len(R), per_week=len(R)/(years*52.0), E=float(R.mean()),
        win=len(w)/len(R), avgW=float(w.mean()) if len(w) else float("nan"),
        avgL=float(-l.mean()) if len(l) else float("nan"),
        rr=float(w.mean()/-l.mean()) if len(w) and len(l) else float("nan"),
        pf=float(w.sum()/-l.sum()) if len(l) and l.sum() < 0 else float("inf"),
        cagr=cagr, dd=dd, sharpe=sharpe, mar=cagr/dd if dd > 0 else float("nan"),
        streak=mx, R_year=float(R.sum())/years)

def row(label, m):
    if m is None: print(f"{label:<26}  insufficient"); return
    print(f"{label:<26}{m['n']:>6}{m['per_week']:>8.3f}{m['E']:>+9.3f}"
          f"{m['win']:>8.3f}{m['rr']:>7.3f}{m['pf']:>7.3f}{m['R_year']:>9.3f}"
          f"{m['cagr']:>9.3f}{m['dd']:>8.3f}{m['sharpe']:>8.3f}{m['mar']:>7.3f}"
          f"{m['streak']:>8}")

HDR = (f"{'configuration':<26}{'n':>6}{'/week':>8}{'E(R)':>9}{'win':>8}{'RR':>7}"
       f"{'PF':>7}{'R/year':>9}{'CAGR':>9}{'maxDD':>8}{'Sharpe':>8}{'MAR':>7}{'loseStk':>8}")

def main():
    print("Fetching 27 futures, daily, 20 years ...")
    def g(it):
        sym, nm = it
        try:
            x = fetch(sym)
            return nm, (x if len(x) > 1500 else None)
        except Exception:
            return nm, None
    D = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for nm, x in ex.map(g, UNI.items()):
            if x is not None: D[nm] = x
    P = {nm: prep(x) for nm, x in D.items()}
    span = max(x.index[-1] for x in D.values()) - min(x.index[0] for x in D.values())
    years = span.days / 365.25
    print(f"  {len(P)} markets, {years:.1f} years\n")

    print("="*118)
    print("FREQUENCY IS SET BY THE LOOKBACK. Risk 0.5% of equity per trade, "
          f"max {MAX_CONCURRENT} positions open.")
    print("="*118)
    print(HDR); print("-"*len(HDR))
    keep = {}
    for n in (200, 120, 80, 55, 34, 20):
        tr, ctr = [], []
        for nm, Pm in P.items():
            s = signals(Pm, n)
            tr.extend(build(Pm, s))
            ctr.extend(build(Pm, s, rand=True))
        r = portfolio(tr, 0.005); c = portfolio(ctr, 0.005)
        m = metrics(*r, years) if r else None
        mc = metrics(*c, years) if c else None
        keep[n] = (tr, ctr, m, mc)
        row(f"Donchian {n}", m)
        row(f"  random control", mc)
    print()

    print("="*118)
    print("THE SAME BOOKS AT DIFFERENT RISK. Position size is the only lever that")
    print("moved drawdown in fifteen years of testing here - this is that lever.")
    print("="*118)
    print(HDR); print("-"*len(HDR))
    for n in (120, 55, 20):
        tr = keep[n][0]
        for f in (0.0025, 0.005, 0.010, 0.020):
            r = portfolio(tr, f)
            row(f"Donchian {n} @ {f:.2%}", metrics(*r, years) if r else None)
        print()

    print("="*118)
    print("HOW MANY MARKETS DO YOU NEED? Donchian 55, risk 0.5%.")
    print("="*118)
    print(HDR); print("-"*len(HDR))
    names = list(P.keys())
    for k in (1, 3, 6, 12, len(names)):
        sub = names[:k]
        tr = []
        for nm in sub:
            tr.extend(build(P[nm], signals(P[nm], 55)))
        r = portfolio(tr, 0.005)
        row(f"{k} market(s)", metrics(*r, years) if r else None)

    print("\nAll figures to three decimals as asked. 'MAR' is CAGR divided by max")
    print("drawdown - the honest single number for comparing two systems, because")
    print("either one alone can be bought with leverage. 'loseStk' is the longest")
    print("run of losing trades that actually occurred, which is the number that")
    print("decides whether a person can run the system at all.")

if __name__ == "__main__":
    main()
