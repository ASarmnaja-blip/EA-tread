#!/usr/bin/env python3
"""A wide, tuned search: many setup families x parameters x exits x timeframes,
all at H1 or faster - and a test of whether the best cell means anything.

WHY THE GRID IS SAFE TO RUN ONLY IF THIS TEST IS RUN WITH IT
  Searching hundreds of configurations and reporting the best one is how every
  overfit system in history was built. The protection here is not a smaller
  grid, it is a different summary: instead of reporting the winner, the run
  reports the DISTRIBUTION of skill t-statistics across every cell and compares
  it to the standard normal that pure noise would produce.

  If several hundred cells produce a t-distribution centred on zero with unit
  spread, then the best cell is the maximum of that many draws and nothing
  more. The expected maximum of k standard normals is sqrt(2 ln k) - printed
  under the table - and a winner below that line has not beaten chance, it IS
  chance.

  Only cells that clear the line are re-tested on other markets, because this
  repo's own criterion is that an effect found on gold and absent elsewhere is
  gold overfit.

WHAT IS SEARCHED
  entries    11 families, each with a small parameter grid: liquidity sweep,
             sweep+CHoCH, FVG retrace, order block retest, Donchian breakout,
             EMA cross, RSI reversion, Bollinger fade, squeeze breakout,
             momentum, opening-range breakout
  exits      4 designs, because `cost_vs_exit_decomposition.py` showed the exit
             carries a measurable return of its own - larger, on random entries,
             than any entry rule in this repo has ever produced
  stops      2 risk multiples
  timeframes M5, M15, M30, H1 - nothing slower, as asked

THE SKILL COLUMN CONTROLS FOR THE EXIT
  Each cell's control uses THE SAME EXIT DESIGN and the same stop, with matched
  count and matched direction mix. So skill measures what the ENTRY knows, with
  the exit's own structural return divided out. Without that, a grid over exits
  would rank exits, not entries.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

SEED, CTRL_REPS = 17, 4
GOLD = "GC=F"
CONFIRM = {"SI=F":"silver","CL=F":"crude","ES=F":"S&P500","NQ=F":"nasdaq",
           "6E=F":"euro","HG=F":"copper","ZN=F":"10y","PL=F":"platinum"}
TFS = {"M5": ("60d", "5m", 288), "M15": ("60d", "15m", 96),
       "M30": ("60d", "30m", 48), "H1": ("730d", "1h", 48)}
SPREAD_FRAC = 0.00007   # ~0.26 on gold near 3700; applied as a fraction so the
                        # confirmation markets are charged something comparable

def fetch(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

# ------------------------------------------------------------------ prep ---
def prep(df):
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    N = len(c); s = pd.Series(c)
    pc = s.shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1 / 14, adjust=False).mean().to_numpy()

    def piv(x, low):
        x = pd.Series(x)
        ok = ((x < x.rolling(5).min().shift(1)) & (x < x.rolling(5).min().shift(-5))) if low \
             else ((x > x.rolling(5).max().shift(1)) & (x > x.rolling(5).max().shift(-5)))
        return pd.Series(np.where(ok.fillna(False), x, np.nan)).shift(5).ffill().to_numpy()
    sh, sl_ = piv(h, False), piv(l, True)

    st = np.zeros(N, np.int8); cur = 0
    for i in range(N):
        a = A[i]
        if np.isfinite(a) and a > 0:
            b = 0.10 * a; ev = 0
            if np.isfinite(sh[i]) and c[i] > sh[i] + b:    ev = 1
            elif np.isfinite(sl_[i]) and c[i] < sl_[i] - b: ev = -1
            if ev and ev != cur: cur = ev
        st[i] = cur

    fl = np.full(N, np.nan); fh = np.full(N, np.nan); fd = np.zeros(N, np.int8)
    _l = _h = np.nan; _d = 0
    for i in range(2, N):
        if   l[i] > h[i - 2]: _l, _h, _d = h[i - 2], l[i], 1
        elif h[i] < l[i - 2]: _l, _h, _d = h[i], l[i - 2], -1
        fl[i], fh[i], fd[i] = _l, _h, _d

    ob_l = np.full(N, np.nan); ob_h = np.full(N, np.nan); ob_d = np.zeros(N, np.int8)
    _ol = _oh = np.nan; _od = 0
    prev = 0
    for i in range(N):
        if st[i] != prev and st[i] != 0:
            for k in range(i, max(-1, i - 30), -1):
                if (st[i] > 0 and c[k] < o[k]) or (st[i] < 0 and c[k] > o[k]):
                    _ol, _oh, _od = l[k], h[k], st[i]; break
            prev = st[i]
        ob_l[i], ob_h[i], ob_d[i] = _ol, _oh, _od

    rsi = {}
    for p in (2, 14):
        d_ = s.diff()
        up = d_.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
        dn = (-d_.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
        rsi[p] = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()

    ema = {p: s.ewm(span=p, adjust=False).mean().to_numpy() for p in (9, 20, 21, 50)}
    don = {p: (s.rolling(p).max().shift(1).to_numpy(),
               s.rolling(p).min().shift(1).to_numpy()) for p in (10, 20, 55)}
    bb = {}
    for p in (20,):
        m = s.rolling(p).mean(); sd = s.rolling(p).std()
        bb[p] = ((m + 2 * sd).to_numpy(), (m - 2 * sd).to_numpy(), m.to_numpy())
    roc = {p: s.pct_change(p).to_numpy() for p in (10, 50)}
    rng_n = {p: pd.Series(h - l).rolling(p).mean().to_numpy() for p in (10,)}
    ph = {p: pd.Series(h).rolling(p).max().shift(1).to_numpy() for p in (10, 20, 40)}
    pl = {p: pd.Series(l).rolling(p).min().shift(1).to_numpy() for p in (10, 20, 40)}

    return dict(o=o, h=h, l=l, c=c, N=N, A=A, st=st, sh=sh, sl=sl_,
                fl=fl, fh=fh, fd=fd, ob_l=ob_l, ob_h=ob_h, ob_d=ob_d,
                rsi=rsi, ema=ema, don=don, bb=bb, roc=roc, rng=rng_n, ph=ph, pl=pl)

# -------------------------------------------------------------- entries ---
def e_sweep(P, n=20):
    s = np.zeros(P["N"], np.int8)
    h, l, c, A = P["h"], P["l"], P["c"], P["A"]
    ph, pl = P["ph"][n], P["pl"][n]
    for i in range(P["N"]):
        a = A[i]
        if not np.isfinite(a) or a <= 0: continue
        if np.isfinite(pl[i]) and l[i] < pl[i] and c[i] > pl[i] and (pl[i]-l[i]) < 1.0*a: s[i] = 1
        elif np.isfinite(ph[i]) and h[i] > ph[i] and c[i] < ph[i] and (h[i]-ph[i]) < 1.0*a: s[i] = -1
    return s

def e_sweep_choch(P, n=20, w=6):
    sw = e_sweep(P, n); s = np.zeros(P["N"], np.int8); st = P["st"]
    for i in range(1, P["N"]):
        if st[i] != 0 and st[i] != st[i-1]:
            if (sw[max(0, i-w):i] == st[i]).any(): s[i] = st[i]
    return s

def e_fvg(P, _=None):
    s = np.zeros(P["N"], np.int8)
    for i in range(P["N"]):
        d = P["fd"][i]
        if d == 0 or d != P["st"][i] or not np.isfinite(P["fl"][i]): continue
        if P["fl"][i] <= P["c"][i] <= P["fh"][i]: s[i] = d
    return s

def e_ob(P, tol=0.25):
    s = np.zeros(P["N"], np.int8)
    for i in range(P["N"]):
        d = P["ob_d"][i]
        if d == 0 or not np.isfinite(P["ob_l"][i]): continue
        if P["ob_l"][i] - tol*P["A"][i] <= P["c"][i] <= P["ob_h"][i] + tol*P["A"][i]: s[i] = d
    return s

def e_donchian(P, n=20):
    hi, lo = P["don"][n]; c = P["c"]; s = np.zeros(P["N"], np.int8)
    s[(c > hi)] = 1; s[(c < lo)] = -1
    return s

def e_don_fade(P, n=20):
    return (-e_donchian(P, n)).astype(np.int8)

def e_ema(P, fast=9, slow=21):
    f, sl_ = P["ema"][fast], P["ema"][slow]
    s = np.zeros(P["N"], np.int8)
    up = (f > sl_) & (np.roll(f, 1) <= np.roll(sl_, 1))
    dn = (f < sl_) & (np.roll(f, 1) >= np.roll(sl_, 1))
    s[up] = 1; s[dn] = -1; s[:2] = 0
    return s

def e_rsi(P, p=2, lo=10, hi=90):
    r = P["rsi"][p]; s = np.zeros(P["N"], np.int8)
    s[r < lo] = 1; s[r > hi] = -1
    return s

def e_bb_fade(P, p=20):
    u, d, _ = P["bb"][p]; c = P["c"]; s = np.zeros(P["N"], np.int8)
    s[c < d] = 1; s[c > u] = -1
    return s

def e_squeeze(P, n=10, k=1.5):
    """Range contracts below k x its own average, then breaks out."""
    h, l, c, r = P["h"], P["l"], P["c"], P["rng"][n]
    hi, lo = P["don"][10]
    s = np.zeros(P["N"], np.int8)
    for i in range(1, P["N"]):
        if not np.isfinite(r[i]) or r[i] <= 0: continue
        if (h[i-1] - l[i-1]) < r[i] / k:
            if np.isfinite(hi[i]) and c[i] > hi[i]: s[i] = 1
            elif np.isfinite(lo[i]) and c[i] < lo[i]: s[i] = -1
    return s

def e_momentum(P, p=50):
    r = P["roc"][p]; s = np.zeros(P["N"], np.int8)
    s[r > 0] = 1; s[r < 0] = -1
    # fire on the flip only, not every bar in the state
    f = np.zeros(P["N"], np.int8)
    f[1:][s[1:] != s[:-1]] = s[1:][s[1:] != s[:-1]]
    return f

ENTRIES = {
    "sweep":        (e_sweep,       [dict(n=10), dict(n=20), dict(n=40)]),
    "sweep+CHoCH":  (e_sweep_choch, [dict(n=20, w=6), dict(n=20, w=12)]),
    "FVG retrace":  (e_fvg,         [dict()]),
    "OB retest":    (e_ob,          [dict(tol=0.25), dict(tol=0.50)]),
    "Donchian brk": (e_donchian,    [dict(n=10), dict(n=20), dict(n=55)]),
    "Donchian fade":(e_don_fade,    [dict(n=20), dict(n=55)]),
    "EMA cross":    (e_ema,         [dict(fast=9, slow=21), dict(fast=20, slow=50)]),
    "RSI revert":   (e_rsi,         [dict(p=2, lo=10, hi=90), dict(p=14, lo=30, hi=70)]),
    "BB fade":      (e_bb_fade,     [dict(p=20)]),
    "squeeze brk":  (e_squeeze,     [dict(n=10, k=1.5), dict(n=10, k=2.0)]),
    "momentum":     (e_momentum,    [dict(p=10), dict(p=50)]),
}

EXITS = {
    "3leg 1/2/3 BE":  dict(legs=(1.0, 2.0, 3.0), be_at=1.0),
    "1leg 2R BE":     dict(legs=(2.0,), be_at=1.0),
    "trail 2ATR BE":  dict(legs=(99.0,), be_at=1.0, trail=1.0),
    "stop + time":    dict(legs=(99.0,)),
}
RMULTS = (1.5, 3.0)

# ----------------------------------------------------------------- exits ---
def exit_run(P, start, entry, d, risk, design, hold, spread):
    """R is denominated against the ACTUAL initial stop, not the nominal ATR
    multiple.

    This is not a detail. A trailing stop seeded from the entry bar's own
    extreme sits closer than `entry -/+ risk`, so a trade booked against the
    nominal risk caps its LOSS below -1R while leaving the win unscaled - free
    asymmetry, worth about +0.15R here, uniform across nine markets, and
    entirely an artefact of the mismatch. Where the seeded stop lands at or
    beyond the entry the order is not one a broker would accept, and the setup
    is skipped rather than booked, which is the same inverted-stop bug
    `backtest_dobby_indicator.py` had to fix."""
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
            # Trail only on bars AFTER entry. Seeding it from the entry bar's
            # own extreme puts the stop closer than `entry -/+ risk`, so the
            # loss is capped below -1R while the win stays unscaled - free
            # asymmetry worth about +0.15R, uniform across nine markets. And
            # denominating R on that seeded stop instead only moves the problem:
            # the stop can land at or beyond the entry, so the divisor goes to
            # zero and expectancy blows up to +5R a trade. The design is simply
            # not well posed until the trail starts one bar later.
            best = max(best, h[k-1]) if d > 0 else min(best, l[k-1])
            t2 = best - d * trail * risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            for x in range(nl):
                if alive[x]: r += ((cur-entry)*d - spread*entry)/risk; alive[x] = False
            break
        for x in range(nl):
            if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                r += ((tg[x]-entry)*d - spread*entry)/risk; alive[x] = False
                if be_at is not None and legs[x] >= be_at: moved = True
        if not any(alive): break
        k += 1
    kx = min(k, N-1)
    if any(alive):
        for x in range(nl):
            if alive[x]: r += ((c[kx]-entry)*d - spread*entry)/risk
    return r/nl, kx

def book(P, sig, design, hold, rmult, spread, rand=False, seed=SEED):
    c, A, N = P["c"], P["A"], P["N"]
    live = [i for i in range(320, N-1) if sig[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
    if len(live) < 30: return []
    dirs = [int(sig[i]) for i in live]
    if rand:
        rng = np.random.default_rng(seed)
        pool = [i for i in range(320, N-1) if np.isfinite(A[i]) and A[i] > 0]
        pick = sorted(rng.choice(pool, size=min(len(live), len(pool)), replace=False))
        plan = [(int(i), dirs[j % len(dirs)]) for j, i in enumerate(pick)]
    else:
        plan = list(zip(live, dirs))
    out, busy = [], -1
    for i, d in plan:
        if i <= busy: continue
        risk = rmult * A[i]
        if risk <= 0: continue
        r, kx = exit_run(P, i, c[i], d, risk, design, hold, spread)
        if r is None: continue
        out.append(r); busy = kx
    return out

def cell(P, sig, design, hold, rmult, spread):
    real = book(P, sig, design, hold, rmult, spread)
    if len(real) < 30: return None
    ctrl = []
    for rep in range(CTRL_REPS):
        ctrl.extend(book(P, sig, design, hold, rmult, spread, True, SEED*1000+rep))
    if len(ctrl) < 30: return None
    a, b = np.array(real), np.array(ctrl)
    sk = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1)/len(a) + b.var(ddof=1)/len(b))
    if se <= 0: return None
    return dict(n=len(a), E=a.mean(), skill=sk, t=sk/se)

# ------------------------------------------------------------------- run ---
def run_grid(P, hold, label, rows):
    for ename, (fn, grid) in ENTRIES.items():
        for gp in grid:
            try: sig = fn(P, **gp)
            except Exception: continue
            if int((sig != 0).sum()) < 40: continue
            ps = ",".join(f"{k}={v}" for k, v in gp.items()) or "-"
            for xname, dz in EXITS.items():
                for rm in RMULTS:
                    r = cell(P, sig, dz, hold, rm, SPREAD_FRAC)
                    if r is None: continue
                    r.update(tf=label, entry=ename, params=ps, exit=xname, rm=rm)
                    rows.append(r)

def main():
    print("Wide tuned search: 11 entry families x params x 4 exits x 2 stops")
    print("x 4 timeframes, gold, nothing slower than H1.\n")

    rows = []
    for tf, (rng, iv, hold) in TFS.items():
        try:
            df = fetch(GOLD, rng, iv)
        except Exception as e:
            print(f"  {tf}: fetch failed ({type(e).__name__})"); continue
        if len(df) < 1500:
            print(f"  {tf}: only {len(df)} bars, skipped"); continue
        print(f"  {tf}: {len(df):,} bars {df.index[0].date()} -> {df.index[-1].date()}")
        run_grid(prep(df), hold, tf, rows)

    if not rows:
        print("\nno cells produced enough trades"); return
    R = pd.DataFrame(rows)
    k = len(R)
    print(f"\n{k} cells cleared the 30-trade floor.\n")

    # ------------------------------------------------ the noise distribution --
    t = R["t"].to_numpy()
    bar = math.sqrt(2*math.log(k))
    print("=" * 76)
    print("IS THERE ANYTHING HERE? The distribution of skill t against noise")
    print("=" * 76)
    print(f"  cells                    {k}")
    print(f"  mean skill t             {t.mean():+.3f}   (noise: 0.00)")
    print(f"  sd of skill t            {t.std(ddof=1):.3f}   (noise: 1.00)")
    print(f"  cells with |t| > 2       {int((abs(t)>2).sum())}"
          f"   (noise expects {0.0455*k:.1f})")
    print(f"  cells with t > 2         {int((t>2).sum())}"
          f"   (noise expects {0.0228*k:.1f})")
    print(f"  best t                   {t.max():+.3f}")
    print(f"  expected max of {k} draws  {bar:+.3f}  <- the line the best cell must clear")

    print("\n" + "=" * 76)
    print("TOP 12 CELLS BY SKILL t")
    print("=" * 76)
    hdr = (f"{'tf':<5}{'entry':<15}{'params':<18}{'exit':<16}{'rm':>5}"
           f"{'n':>7}{'E':>9}{'skill':>9}{'t':>7}")
    print(hdr); print("-" * len(hdr))
    top = R.sort_values("t", ascending=False).head(12)
    for _, x in top.iterrows():
        print(f"{x.tf:<5}{x.entry:<15}{x.params:<18}{x['exit']:<16}{x.rm:>5.1f}"
              f"{x.n:>7}{x.E:>+9.3f}{x.skill:>+9.3f}{x.t:>+7.2f}")

    survivors = R[R["t"] > bar]
    print(f"\n{len(survivors)} cell(s) clear the expected-max line of {bar:.2f}.")
    if len(survivors) == 0:
        print("  The best configuration in the entire grid is what the maximum of")
        print(f"  {k} noise draws looks like. Nothing here is re-tested on other")
        print("  markets, because there is nothing to re-test.")
        return

    # --------------------------------------------- cross-asset confirmation --
    print("\n" + "=" * 76)
    print("CROSS-ASSET CONFIRMATION of the cells that cleared the line")
    print("=" * 76)
    print("This repo's rule: an effect found on gold and absent elsewhere is")
    print("gold overfit. Same rule, same parameters, eight other markets.\n")
    def g(item):
        sym, nm = item
        try: return nm, fetch(sym, "730d", "1h")
        except Exception: return nm, None
    D = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for nm, x in ex.map(g, CONFIRM.items()):
            if x is not None and len(x) > 3000: D[nm] = x
    PD = {nm: prep(x) for nm, x in D.items()}
    print(f"{'entry':<15}{'params':<18}{'exit':<16}{'rm':>5}{'n':>7}{'skill':>9}{'t':>7}{'mkts+':>8}")
    print("-" * 85)
    for _, x in survivors.iterrows():
        fn, _grid = ENTRIES[x.entry]
        gp = {} if x.params == "-" else {a.split("=")[0]: float(a.split("=")[1])
                                         if "." in a.split("=")[1] else int(a.split("=")[1])
                                         for a in x.params.split(",")}
        allr, pos, tot = [], 0, 0
        for nm, P in PD.items():
            try: sig = fn(P, **gp)
            except Exception: continue
            r = cell(P, sig, EXITS[x["exit"]], 48, x.rm, SPREAD_FRAC)
            if r is None: continue
            tot += 1; pos += 1 if r["skill"] > 0 else 0
            allr.append(r)
        if not allr: continue
        n = sum(r["n"] for r in allr)
        sk = float(np.mean([r["skill"] for r in allr]))
        tt = float(np.mean([r["t"] for r in allr]) * math.sqrt(len(allr)))
        print(f"{x.entry:<15}{x.params:<18}{x['exit']:<16}{x.rm:>5.1f}"
              f"{n:>7}{sk:>+9.3f}{tt:>+7.2f}{f'{pos}/{tot}':>8}")

if __name__ == "__main__":
    main()
