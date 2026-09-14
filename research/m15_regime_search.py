#!/usr/bin/env python3
"""M15 gold, six years: is the tradeable variable the ENTRY, or the REGIME?

WHERE THE HYPOTHESIS CAME FROM
  Reading five consecutive M15 gold charts, the thing that separates them is
  not which entry fired. It is that some two-day windows trend cleanly and some
  are pure range, and the range ones break every breakout. On a clean trend
  window a channel break runs 3R; on a range window the identical rule takes
  three or four stops in a row. Nothing in this repo has ever tested a rule
  that decides WHICH KIND OF WINDOW IT IS before trading.

  That is a different claim from "a better entry", and it is the one the charts
  actually support.

THE DESIGN, FIXED BEFORE ANY RESULT WAS SEEN
  discovery   2020-08 -> 2023-09   (~half the bars). The grid runs here ONLY.
  holdout     2023-09 -> 2026-09   Touched ONCE, by whatever survives, at the
                                   end. No tuning against it, no second look.
  confirm     real XAUUSD (GC=F) M15 60d and H1 730d, because PAX Gold is a
                                   token that tracks gold, not gold.

  Every earlier search in this repo was run on the whole sample and then
  admired. That is what the holdout is for.

THE REGIME MEASURE
  Kaufman efficiency ratio over n bars:

      ER = |close[t] - close[t-n]| / sum(|close[i] - close[i-1]|)

  1.0 is a straight line, 0 is pure noise with no net travel. It is the
  cheapest honest statement of "is this window going somewhere", it needs no
  fitting, and it has never been tested anywhere in this program.

READ THE SKILL COLUMN, NOT E
  Every cell is measured against a control with matched count, matched
  direction mix and the SAME exit, so the exit's own return - which this repo
  measured at +0.034R for a trailing stop on random entries - is divided out.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fetch_m15_gold import fetch_paxg_m15, drop_weekend, yahoo

SEED, CTRL_REPS = 17, 3
SPLIT = "2023-09-01"
COST_FRAC = 0.00007          # ~$0.30 a leg at $4,400 gold
HOLD = 96                    # 24 hours of M15 bars
MIN_TRADES = 60

# --------------------------------------------------------------- indicators --
def prep(df):
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    N = len(c); s = pd.Series(c)
    pc = s.shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1/14, adjust=False).mean().to_numpy()

    er = {}
    for n in (32, 96):
        move = (s - s.shift(n)).abs()
        path = s.diff().abs().rolling(n).sum()
        er[n] = (move / path.replace(0, np.nan)).to_numpy()

    don = {n: (s.rolling(n).max().shift(1).to_numpy(),
               s.rolling(n).min().shift(1).to_numpy()) for n in (20, 48, 96)}
    ph = {n: pd.Series(h).rolling(n).max().shift(1).to_numpy() for n in (20, 48)}
    pl = {n: pd.Series(l).rolling(n).min().shift(1).to_numpy() for n in (20, 48)}
    atr_exp = (pd.Series(A) / pd.Series(A).rolling(96).mean()).to_numpy()
    return dict(o=o, h=h, l=l, c=c, N=N, A=A, er=er, don=don, ph=ph, pl=pl,
                aexp=atr_exp, hour=df.index.hour.to_numpy())

# ------------------------------------------------------------------ entries --
def e_don(P, n=48):
    hi, lo = P["don"][n]; c = P["c"]; s = np.zeros(P["N"], np.int8)
    up = (c > hi) & ~(np.roll(c, 1) > np.roll(hi, 1))
    dn = (c < lo) & ~(np.roll(c, 1) < np.roll(lo, 1))
    s[up] = 1; s[dn] = -1; s[:2] = 0
    return s

def e_sweep(P, n=48):
    """Wick clears the prior extreme, body closes back inside - the reclaim
    that showed up at the low of every clean reversal in the charts."""
    s = np.zeros(P["N"], np.int8)
    h, l, c, A = P["h"], P["l"], P["c"], P["A"]
    ph, pl = P["ph"][n], P["pl"][n]
    for i in range(P["N"]):
        a = A[i]
        if not np.isfinite(a) or a <= 0: continue
        if np.isfinite(pl[i]) and l[i] < pl[i] and c[i] > pl[i] and (pl[i]-l[i]) < 1.0*a:
            s[i] = 1
        elif np.isfinite(ph[i]) and h[i] > ph[i] and c[i] < ph[i] and (h[i]-ph[i]) < 1.0*a:
            s[i] = -1
    return s

ENTRIES = {"Donchian 20": (e_don, dict(n=20)),
           "Donchian 48": (e_don, dict(n=48)),
           "Donchian 96": (e_don, dict(n=96)),
           "sweep 20":    (e_sweep, dict(n=20)),
           "sweep 48":    (e_sweep, dict(n=48))}

# ------------------------------------------------------------------ regimes --
def r_all(P):   return np.ones(P["N"], bool)
def r_er_hi(P, n=96, k=0.35): return np.nan_to_num(P["er"][n], nan=0) >= k
def r_er_lo(P, n=96, k=0.20): return np.nan_to_num(P["er"][n], nan=1) <= k
def r_vol_hi(P, k=1.2):       return np.nan_to_num(P["aexp"], nan=0) >= k
def r_session(P):
    """London and New York only - 07:00 to 21:00 UTC."""
    return (P["hour"] >= 7) & (P["hour"] < 21)

REGIMES = {
    "any":              (r_all, {}),
    "ER96 >= 0.30":     (r_er_hi, dict(n=96, k=0.30)),
    "ER96 >= 0.40":     (r_er_hi, dict(n=96, k=0.40)),
    "ER32 >= 0.40":     (r_er_hi, dict(n=32, k=0.40)),
    "ER96 <= 0.20":     (r_er_lo, dict(n=96, k=0.20)),
    "ATR exp >= 1.2":   (r_vol_hi, dict(k=1.2)),
    "London+NY hours":  (r_session, {}),
}

EXITS = {"trail 2ATR BE": dict(legs=(99.0,), be_at=1.0, trail=1.0),
         "trail 3ATR BE": dict(legs=(99.0,), be_at=1.0, trail=1.5),
         "3leg 1/2/3 BE": dict(legs=(1.0, 2.0, 3.0), be_at=1.0)}
RMULTS = (1.5, 2.5)

# -------------------------------------------------------------------- exits --
def exit_run(P, start, entry, d, risk, design, hold, cost):
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    legs, be_at, trail = design["legs"], design.get("be_at"), design.get("trail")
    nl = len(legs)
    stop = entry - d * risk
    tg = [entry + d * risk * m for m in legs]
    alive = [True]*nl
    r, k, moved, best = 0.0, start+1, False, entry
    while k < min(start+1+hold, N):
        cur = entry if moved else stop
        if trail and k-1 > start:       # trail starts AFTER the entry bar
            best = max(best, h[k-1]) if d > 0 else min(best, l[k-1])
            t2 = best - d*trail*risk
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            for x in range(nl):
                if alive[x]: r += ((cur-entry)*d - cost*entry)/risk; alive[x] = False
            break
        for x in range(nl):
            if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                r += ((tg[x]-entry)*d - cost*entry)/risk; alive[x] = False
                if be_at is not None and legs[x] >= be_at: moved = True
        if not any(alive): break
        k += 1
    kx = min(k, N-1)
    if any(alive):
        for x in range(nl):
            if alive[x]: r += ((c[kx]-entry)*d - cost*entry)/risk
    return r/nl, kx

def book(P, sig, design, rmult, rand=False, seed=SEED, warm=200):
    c, A, N = P["c"], P["A"], P["N"]
    live = [i for i in range(warm, N-1) if sig[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
    if len(live) < MIN_TRADES: return []
    dirs = [int(sig[i]) for i in live]
    if rand:
        rng = np.random.default_rng(seed)
        pool = np.flatnonzero(np.isfinite(A[warm:N-1]) & (A[warm:N-1] > 0)) + warm
        if len(pool) < len(live): return []
        pick = np.sort(rng.choice(pool, size=len(live), replace=False))
        plan = [(int(i), dirs[j % len(dirs)]) for j, i in enumerate(pick)]
    else:
        plan = list(zip(live, dirs))
    out, busy = [], -1
    for i, d in plan:
        if i <= busy: continue
        risk = rmult * A[i]
        if risk <= 0: continue
        r, kx = exit_run(P, i, c[i], d, risk, design, HOLD, COST_FRAC)
        out.append(r); busy = kx
    return out

def cell(P, sig, design, rmult):
    real = book(P, sig, design, rmult)
    if len(real) < MIN_TRADES: return None
    ctrl = []
    for rep in range(CTRL_REPS):
        ctrl.extend(book(P, sig, design, rmult, True, SEED*1000+rep))
    if len(ctrl) < MIN_TRADES: return None
    a, b = np.array(real), np.array(ctrl)
    sk = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1)/len(a) + b.var(ddof=1)/len(b))
    if se <= 0: return None
    w = a[a > 0]; lo = a[a <= 0]
    return dict(n=len(a), E=a.mean(), t=a.mean()/(a.std(ddof=1)/math.sqrt(len(a))),
                skill=sk, skt=sk/se,
                win=len(w)/len(a) if len(a) else np.nan,
                rr=(w.mean()/-lo.mean()) if len(w) and len(lo) else np.nan)

def run_grid(P, label):
    rows = []
    sigs = {en: fn(P, **kw) for en, (fn, kw) in ENTRIES.items()}
    regs = {rn: fn(P, **kw) for rn, (fn, kw) in REGIMES.items()}
    for en, base in sigs.items():
        for rn, mask in regs.items():
            sig = base.copy(); sig[~mask] = 0
            if int((sig != 0).sum()) < MIN_TRADES: continue
            for xn, dz in EXITS.items():
                for rm in RMULTS:
                    r = cell(P, sig, dz, rm)
                    if r is None: continue
                    r.update(entry=en, regime=rn, exit=xn, rm=rm, part=label)
                    rows.append(r)
    return rows

def show(rows, title, top=12):
    R = pd.DataFrame(rows); k = len(R)
    t = R["skt"].to_numpy()
    bar = math.sqrt(2*math.log(k)) if k > 1 else np.nan
    print(f"\n{'='*100}\n{title}\n{'='*100}")
    print(f"  {k} cells | mean skill t {t.mean():+.3f} (noise 0) | "
          f"sd {t.std(ddof=1):.3f} (noise 1) | best {t.max():+.3f} | "
          f"expected max {bar:+.3f}")
    hdr = (f"{'entry':<13}{'regime':<17}{'exit':<16}{'rm':>4}{'n':>7}"
           f"{'win%':>7}{'RR':>6}{'E':>8}{'skill':>8}{'sk t':>7}")
    print(hdr); print("-"*len(hdr))
    for _, x in R.sort_values("skt", ascending=False).head(top).iterrows():
        print(f"{x.entry:<13}{x.regime:<17}{x['exit']:<16}{x.rm:>4.1f}{x.n:>7}"
              f"{x.win:>7.1%}{x.rr:>6.2f}{x.E:>+8.3f}{x.skill:>+8.3f}{x.skt:>+7.2f}")
    return R, bar

def main():
    print("Loading M15 gold (PAXG, weekend bars removed) ...")
    df = drop_weekend(fetch_paxg_m15())
    disc, hold = df[df.index < SPLIT], df[df.index >= SPLIT]
    print(f"  discovery {len(disc):,} bars {disc.index[0].date()} -> {disc.index[-1].date()}")
    print(f"  holdout   {len(hold):,} bars {hold.index[0].date()} -> {hold.index[-1].date()}")

    Pd = prep(disc)
    rows = run_grid(Pd, "discovery")
    if not rows:
        print("no cells cleared the trade floor"); return
    R, bar = show(rows, "DISCOVERY HALF 2020-08 -> 2023-09  (the grid runs only here)")

    surv = R[R["skt"] > bar]
    print(f"\n{len(surv)} cell(s) clear the expected-max line of {bar:.2f}.")
    if len(surv) == 0:
        print("  Nothing to carry to the holdout. The holdout stays untouched,")
        print("  which is the point of having fixed it in advance.")
        cands = R.sort_values("skt", ascending=False).head(3)
        print("\n  Carrying the top 3 anyway, LABELLED AS FAILED, purely to show")
        print("  what happens to a cell selected below the line:")
    else:
        cands = surv

    Ph = prep(hold)
    print(f"\n{'='*100}\nHOLDOUT 2023-09 -> 2026-09  (touched once, no tuning)\n{'='*100}")
    hdr = (f"{'entry':<13}{'regime':<17}{'exit':<16}{'rm':>4}{'n':>7}"
           f"{'win%':>7}{'RR':>6}{'E':>8}{'skill':>8}{'sk t':>7}  disc skt")
    print(hdr); print("-"*len(hdr))
    for _, x in cands.iterrows():
        fn, kw = ENTRIES[x.entry]; rfn, rkw = REGIMES[x.regime]
        sig = fn(Ph, **kw); sig[~rfn(Ph, **rkw)] = 0
        r = cell(Ph, sig, EXITS[x["exit"]], x.rm)
        if r is None:
            print(f"{x.entry:<13}{x.regime:<17}{x['exit']:<16}{x.rm:>4.1f}"
                  f"   too few trades"); continue
        print(f"{x.entry:<13}{x.regime:<17}{x['exit']:<16}{x.rm:>4.1f}{r['n']:>7}"
              f"{r['win']:>7.1%}{r['rr']:>6.2f}{r['E']:>+8.3f}{r['skill']:>+8.3f}"
              f"{r['skt']:>+7.2f}{x.skt:>+10.2f}")

    # ------------------------------------------- the regime question, direct --
    print(f"\n{'='*100}")
    print("DOES THE REGIME FILTER CARRY INFORMATION? - the question this file exists for")
    print("="*100)
    print("One entry, one exit, every regime side by side. If the chart reading was")
    print("right, the trend-regime rows beat the 'any' row by more than noise.\n")
    for en, xn, rm in (("sweep 20", "3leg 1/2/3 BE", 1.5),
                       ("Donchian 48", "trail 2ATR BE", 1.5)):
        print(f"  {en} + {xn} + rm{rm}")
        print(f"    {'regime':<18}{'disc n':>8}{'disc skill':>12}{'disc t':>8}"
              f"{'hold n':>8}{'hold skill':>12}{'hold t':>8}")
        print("    " + "-"*74)
        fn, kw = ENTRIES[en]
        for rn, (rfn, rkw) in REGIMES.items():
            out = []
            for PP in (Pd, Ph):
                sig = fn(PP, **kw); sig[~rfn(PP, **rkw)] = 0
                out.append(cell(PP, sig, EXITS[xn], rm))
            if out[0] is None: continue
            d0 = out[0]; h0 = out[1]
            hs = (f"{h0['n']:>8}{h0['skill']:>+12.3f}{h0['skt']:>+8.2f}"
                  if h0 else f"{'-':>8}{'-':>12}{'-':>8}")
            print(f"    {rn:<18}{d0['n']:>8}{d0['skill']:>+12.3f}{d0['skt']:>+8.2f}{hs}")
        print()

    # ------------------------------------------------- real gold confirmation --
    print(f"\n{'='*100}\nREAL XAUUSD (GC=F), same rules, no refitting\n{'='*100}")
    for tag, rng, iv in (("M15 60d", "60d", "15m"), ("H1 730d", "730d", "1h")):
        try: g = yahoo("GC=F", rng, iv)
        except Exception as e:
            print(f"  {tag}: fetch failed {type(e).__name__}"); continue
        Pg = prep(g)
        print(f"  {tag}: {len(g):,} bars")
        for _, x in cands.iterrows():
            fn, kw = ENTRIES[x.entry]; rfn, rkw = REGIMES[x.regime]
            sig = fn(Pg, **kw); sig[~rfn(Pg, **rkw)] = 0
            r = cell(Pg, sig, EXITS[x["exit"]], x.rm)
            nm = f"{x.entry} / {x.regime} / {x['exit']} rm{x.rm}"
            if r is None:
                print(f"    {nm:<58} too few trades"); continue
            print(f"    {nm:<58} n={r['n']:>5} E={r['E']:+.3f} "
                  f"skill={r['skill']:+.3f} t={r['skt']:+.2f}")

    # ------------------------------- is the signal gold's, or the token's? --
    print(f"\n{'='*100}")
    print("IS ANY M15 SIGNAL GOLD'S, OR PAX GOLD THE CRYPTO TOKEN'S?")
    print("="*100)
    print("The metal is shut Fri 21:00 - Sun 22:00 UTC; the token keeps trading.")
    print("An effect belonging to GOLD price discovery should be weaker or absent")
    print("in those hours. One belonging to a thin crypto book with no metal to")
    print("arbitrage against should be STRONGER. This test costs one minute and")
    print("decides whether anything above is about gold at all.\n")
    full = fetch_paxg_m15()
    wk = drop_weekend(full)
    wd = full[~full.index.isin(wk.index)]
    print(f"    {'series':<22}{'n':>7}{'win%':>7}{'RR':>6}{'E':>9}{'skill':>9}{'t':>7}")
    print("    " + "-"*63)
    for nm, d in (("metal OPEN", wk), ("metal SHUT (weekend)", wd)):
        PP = prep(d)
        sig = (-e_don(PP, 48)).astype(np.int8)      # the fade, the best cell found
        r = cell(PP, sig, EXITS["trail 2ATR BE"], 1.5)
        if r is None:
            print(f"    {nm:<22}  too few trades"); continue
        print(f"    {nm:<22}{r['n']:>7}{r['win']:>7.1%}{r['rr']:>6.2f}"
              f"{r['E']:>+9.3f}{r['skill']:>+9.3f}{r['skt']:>+7.2f}")

    print("\nThe regime columns are the point of this file. Compare each entry's")
    print("'any' row against its filtered rows: if a regime filter carried real")
    print("information, the filtered skill would rise above the unfiltered one by")
    print("more than the sample noise, in the discovery half AND the holdout.")

if __name__ == "__main__":
    main()
