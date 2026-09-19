#!/usr/bin/env python3
"""Wick-tip entries on gold, tuned, with the last third held back.

THE TRADE
  "Trading the tip of the wick" means being filled at the extreme, not at the
  close. Two ways to do that, and they are different claims:

  A  RESTING LIMIT ("ปลายไส้" proper)
     Put a buy limit BELOW the market, at the prior N-bar low minus k x ATR,
     and wait. When a spike wicks through it you are filled near the tip of
     that wick, at your price, and the wick's own low becomes the stop. You
     never chase. Most of the time nothing happens.

  B  REJECTION CLOSE
     Wait for a bar to CLOSE with a long lower wick, then buy at that close.
     Easier to execute, worse price - you are paying for the confirmation.

  Both are run long and short, so nothing here is a bet on gold going up.

THE DISCIPLINE
  60 days is all Yahoo serves at M5/M15, and a grid this size on 60 days will
  produce a good-looking cell whether or not anything is there. So:

    TUNE   the first 40 days. Every parameter is chosen here.
    TEST   the last 20 days. Touched once, at the end, by the winners only.

  The split is by date and was fixed before the first run. The expected maximum
  of k noise draws, sqrt(2 ln k), is printed under the tuning table - a winner
  below that line is what the best of k coin flips looks like.

COSTS
  Both spreads this repo has measured: $0.26 and $0.7525. A limit fill pays the
  spread once on entry and once on exit, same as a market order - what the limit
  buys you is the PRICE, not the toll.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd

SPREADS = (0.26, 0.7525)
MAX_HOLD = 288            # 24h of M5
TUNE_FRAC = 0.667         # first two thirds tune, last third tests

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
    s = pd.Series(c); pc = s.shift(1)
    A = pd.concat([pd.Series(h-l), (pd.Series(h)-pc).abs(),
                   (pd.Series(l)-pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1/14, adjust=False).mean().to_numpy()
    N = len(c)
    return dict(o=o, h=h, l=l, c=c, A=A, N=N, idx=df.index,
                hour=df.index.hour.to_numpy())

# ------------------------------------------------------------------ exits ---
def resolve(P, fill_bar, entry, d, sl, tp, spread, hold=MAX_HOLD, intrabar=False):
    """Stop tested before target on any bar that could have hit both.

    `intrabar=True` means the fill happened INSIDE bar `fill_bar` - a resting
    limit that a wick reached. Two mistakes are possible on that bar and both
    were made here before this comment existed:

      skipping it entirely  - the spike that reached the limit can keep going
                              and take the stop out in the same candle. Booking
                              those as live trades was worth a 74% win rate.
      testing all of it     - the bar's HIGH may have printed BEFORE the wick
                              down that filled you, so counting it as a target
                              hit books a win on a price that happened while
                              you were still flat. That was worth 78%.

    With OHLC alone the path inside the bar is unknowable, so the fill bar is
    tested for the STOP ONLY, which is the pessimistic reading. From the next
    bar on, both are tested, stop first."""
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    stop = entry - d*sl
    targ = entry + d*tp
    if intrabar:
        if (l[fill_bar] <= stop) if d > 0 else (h[fill_bar] >= stop):
            return -sl - spread, fill_bar
    k = fill_bar
    for k in range(fill_bar+1, min(fill_bar+1+hold, N)):
        if (l[k] <= stop) if d > 0 else (h[k] >= stop):
            return -sl - spread, k
        if (h[k] >= targ) if d > 0 else (l[k] <= targ):
            return tp - spread, k
    kx = min(k, N-1)
    return (c[kx] - entry)*d - spread, kx

# ------------------------------------------------- A: resting limit at tip ---
def trades_limit(P, look, off_atr, sl_atr, tp_mult, spread, sess=None, wick_min=0.0):
    """Rest a limit `off_atr` x ATR beyond the prior `look`-bar extreme. A wick
    that pierces it fills you at that price. Stop goes beyond the wick's own
    low, so the deeper the spike the wider the stop - the trade sizes itself.

    `wick_min` IS DISABLED AND MUST STAY DISABLED. It used to require the fill
    bar's own tail-to-range ratio - computed from that bar's CLOSE - to clear a
    threshold before the trade counted. That is a look-ahead bug, not a filter:
    the fill happens mid-bar at the touched low, but the bar's close is only
    known once the bar finishes, so gating on it means every accepted trade had
    already enjoyed that bar's own recovery from low to close for free, before
    the "entry" is even evaluated going forward. Calibrated on a driftless
    random walk at zero cost, wick_min=0 returns E close to zero (as it must);
    wick_min=0.35 alone was worth +0.4R to +0.6R of pure fiction, and it grew
    with the threshold. The same bug, on real XAUUSD 60-day data, is what
    turned a genuinely flat -0.182R into the +0.308R to +0.772R numbers this
    file reported earlier in this session. See RESEARCH_FINDINGS.md.

    There is no honest fix that keeps the idea: deciding whether a fill
    "counts" from the shape of the very bar you filled on cannot be done
    without the bar's close, and a live system does not have that at fill
    time. wick_min stays in the signature only so old call sites do not crash;
    passing anything but 0.0 raises."""
    if wick_min:
        raise ValueError(
            "wick_min>0 is a look-ahead bug (uses the fill bar's own close to "
            "gate a fill priced off that bar's low) - see the docstring above. "
            "It is disabled, not tunable.")
    h, l, c, A, N = P["h"], P["l"], P["c"], P["A"], P["N"]
    ph = pd.Series(h).rolling(look).max().shift(1).to_numpy()
    pl = pd.Series(l).rolling(look).min().shift(1).to_numpy()
    out, busy = [], -1
    for i in range(look+20, N-1):
        if i <= busy: continue
        a = A[i-1]          # a resting limit is placed BEFORE bar i prints
        if not np.isfinite(a) or a <= 0: continue
        if sess is not None and not (sess[0] <= P["hour"][i] < sess[1]): continue
        rng = h[i] - l[i]
        if rng <= 0: continue
        for d in (1, -1):
            lvl = (pl[i] - off_atr*a) if d > 0 else (ph[i] + off_atr*a)
            if not np.isfinite(lvl): continue
            hit = (l[i] <= lvl) if d > 0 else (h[i] >= lvl)
            if not hit: continue
            sl = sl_atr*a
            r, kx = resolve(P, i, lvl, d, sl, tp_mult*sl, spread, intrabar=True)
            out.append((P["idx"][i], d, r, sl))
            busy = kx          # one position at a time; overlapping trades
            break              # share a price path and inflate every t-stat
    return out

# ------------------------------------------------ B: buy the rejection close ---
def trades_close(P, wick_min, body_max, rng_atr, sl_atr, tp_mult, spread, sess=None):
    h, l, c, o, A, N = P["h"], P["l"], P["c"], P["o"], P["A"], P["N"]
    out, busy = [], -1
    for i in range(20, N-1):
        if i <= busy: continue
        a = A[i]
        if not np.isfinite(a) or a <= 0: continue
        if sess is not None and not (sess[0] <= P["hour"][i] < sess[1]): continue
        rng = h[i] - l[i]
        if rng <= 0 or rng < rng_atr*a: continue
        body = abs(c[i]-o[i])
        if body/rng > body_max: continue
        lower = (min(c[i], o[i]) - l[i]) / rng
        upper = (h[i] - max(c[i], o[i])) / rng
        d = 0
        if lower >= wick_min and lower > upper: d = 1
        elif upper >= wick_min and upper > lower: d = -1
        if d == 0: continue
        sl = sl_atr*a
        r, kx = resolve(P, i, c[i], d, sl, tp_mult*sl, spread, intrabar=False)
        out.append((P["idx"][i], d, r, sl))
        busy = kx
    return out

# ---------------------------------------------------------------- scoring ---
def control(P, tr, sl_atr, tp_mult, spread, seed=17, reps=8):
    """Same count, same direction mix, same stop and target - random bars.
    Entry at the bar close, since a random bar has no wick to be filled on."""
    if len(tr) < 15: return None
    rng = np.random.default_rng(seed)
    dirs = [t[1] for t in tr]
    A, c, N = P["A"], P["c"], P["N"]
    pool = np.flatnonzero(np.isfinite(A[:N-1]) & (A[:N-1] > 0))
    pool = pool[pool > 50]
    if len(pool) < len(tr): return None
    out = []
    for rep in range(reps):
        pick = np.sort(rng.choice(pool, size=len(tr), replace=False))
        busy = -1
        for j, i in enumerate(pick):
            i = int(i)
            if i <= busy: continue
            a = A[i-1]
            if not np.isfinite(a) or a <= 0: continue
            d = dirs[j % len(dirs)]
            sl = sl_atr*a
            r, kx = resolve(P, i, c[i], d, sl, tp_mult*sl, spread)
            out.append((P["idx"][i], d, r, sl)); busy = kx
    return score(out)

def score(tr, floor=15):
    if len(tr) < floor: return None
    R = np.array([t[2]/t[3] for t in tr])       # in R units
    D = np.array([t[2] for t in tr])            # in dollars
    w, l = R[R > 0], R[R <= 0]
    if not len(w) or not len(l): return None
    return dict(n=len(R), win=len(w)/len(R),
                rr=float(w.mean()/-l.mean()),
                pf=float(w.sum()/-l.sum()) if l.sum() < 0 else float("inf"),
                E=float(R.mean()), Eusd=float(D.mean()),
                t=float(R.mean()/(R.std(ddof=1)/math.sqrt(len(R)))))

def line(tag, s):
    if s is None: print(f"  {tag:<44} too few"); return
    print(f"  {tag:<44}{s['n']:>6}{s['win']:>9.3f}{s['rr']:>8.3f}{s['pf']:>8.3f}"
          f"{s['E']:>9.3f}{'$'+format(s['Eusd'],'+.3f'):>11}{s['t']:>8.3f}")

HDR = (f"  {'configuration':<44}{'n':>6}{'win%':>9}{'RR':>8}{'PF':>8}"
       f"{'E(R)':>9}{'E($)':>11}{'t':>8}")

def main():
    print("Wick-tip entries on XAUUSD. Tune on the first two thirds, test on the last.\n")
    data = {}
    for tf, iv in (("M5", "5m"), ("M15", "15m")):
        df = fetch("GC=F", "60d", iv)
        cut = df.index[int(len(df)*TUNE_FRAC)]
        data[tf] = (prep(df[df.index < cut]), prep(df[df.index >= cut]), df, cut)
        print(f"{tf}: {len(df):,} bars {df.index[0].date()} -> {df.index[-1].date()}"
              f" | split at {cut.date()}")
    print()

    grids = []
    # A - resting limit at the wick tip. wick_min is fixed at 0.0 - see the
    # docstring on trades_limit(): any positive value is a look-ahead bug.
    for look in (12, 24, 48):
        for off in (0.25, 0.50, 1.00):
            for sl in (1.0, 1.5):
                for tp in (0.7, 1.0, 1.5):
                    grids.append(("A limit", dict(look=look, off_atr=off,
                                  sl_atr=sl, tp_mult=tp, wick_min=0.0)))
    # B - rejection close
    for wm in (0.45, 0.60):
        for bm in (0.35, 0.50):
            for ra in (0.8, 1.3):
                for sl in (1.0, 1.5):
                    for tp in (0.7, 1.0, 1.5):
                        grids.append(("B close", dict(wick_min=wm, body_max=bm,
                                      rng_atr=ra, sl_atr=sl, tp_mult=tp)))

    rows = []
    for tf in ("M5", "M15"):
        Ptune, Ptest, _, _ = data[tf]
        for kind, kw in grids:
            fn = trades_limit if kind.startswith("A") else trades_close
            # Require enough trades in TUNING that the holdout - half its
            # length - can still be measured. A config selected here that
            # cannot be tested there is not a candidate, it is a coincidence.
            s = score(fn(Ptune, spread=SPREADS[0], **kw), floor=60)
            if s is None: continue
            rows.append(dict(tf=tf, kind=kind, kw=kw, **s))

    R = pd.DataFrame(rows)
    k = len(R)
    bar = math.sqrt(2*math.log(k)) if k > 1 else float("nan")
    print("="*104)
    print(f"TUNING WINDOW - {k} configurations, spread $0.26")
    print("="*104)
    print(f"  best t {R['t'].max():.3f} | expected max of {k} noise draws "
          f"sqrt(2*ln {k}) = {bar:.3f} | mean t {R['t'].mean():+.3f}")
    print()
    print(HDR); print("  " + "-"*(len(HDR)-2))
    top = R.sort_values("E", ascending=False).head(10)
    for _, x in top.iterrows():
        tag = f"{x.tf} {x.kind} " + " ".join(f"{a}={b}" for a, b in x.kw.items())
        line(tag[:44], x.to_dict())

    print(f"\n{'='*104}")
    print("HELD-OUT WINDOW - the last third, same parameters, both spreads")
    print("="*104)
    print(HDR); print("  " + "-"*(len(HDR)-2))
    for _, x in top.head(6).iterrows():
        Ptest = data[x.tf][1]
        fn = trades_limit if x.kind.startswith("A") else trades_close
        for sp in SPREADS:
            tr = fn(Ptest, spread=sp, **x.kw)
            s = score(tr)
            tag = (f"{x.tf} {x.kind} sp{sp} " +
                   " ".join(f"{a}={b}" for a, b in x.kw.items()))
            line(tag[:44], s)
            if s is not None:
                cs = control(Ptest, tr, x.kw["sl_atr"], x.kw["tp_mult"], sp)
                line("    ^ random control, same SL/TP/count", cs)
        print()

    print("Read the held-out block, not the tuning block. The tuning block is")
    print("where the parameters were chosen, so its best row is selected to look")
    print("good and cannot be evidence of anything.")

if __name__ == "__main__":
    main()
