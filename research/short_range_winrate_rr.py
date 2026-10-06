#!/usr/bin/env python3
"""Win rate and R:R at 3,000-10,000 points on gold. Measured, to 3 decimals.

Gold quoted to 3 decimals, so 1 point = 0.001 and the requested band is a
$3.00 to $10.00 stop and target - well under one M15 ATR at current
volatility. Exits are resolved on M5 bars so a $3 move is not smeared across a
15-minute candle, and the stop is tested BEFORE the target on any bar that
could have hit both.

Both spreads this repo has measured are charged: $0.26 (terminal quote) and
$0.7525 (2023-2026 OANDA mean).
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd

STOPS   = (3.0, 5.0, 7.0, 10.0)
TARGETS = (3.0, 5.0, 7.0, 10.0)
SPREADS = (0.26, 0.7525)
MAX_BARS = 288            # 24 hours of M5 before the trade is abandoned
STEP = 3                  # sample every 3rd bar so trades do not fully overlap

def fetch(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def run(h, l, c, N, i, d, stop_d, tgt_d, spread):
    """One trade. Returns +1 win / -1 loss / 0 unresolved, and its dollar P&L."""
    e = c[i]
    stop = e - d*stop_d
    tgt = e + d*tgt_d
    for k in range(i+1, min(i+1+MAX_BARS, N)):
        hit_stop = (l[k] <= stop) if d > 0 else (h[k] >= stop)
        hit_tgt  = (h[k] >= tgt)  if d > 0 else (l[k] <= tgt)
        if hit_stop:                       # pessimistic: stop first
            return -1, -stop_d - spread
        if hit_tgt:
            return +1, tgt_d - spread
    return 0, (c[min(k, N-1)] - e)*d - spread

def measure(df, stop_d, tgt_d, spread):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    N = len(c)
    wins = losses = unres = 0
    pnl = []
    for i in range(50, N-1, STEP):
        for d in (1, -1):
            r, p = run(h, l, c, N, i, d, stop_d, tgt_d, spread)
            pnl.append(p)
            if r > 0: wins += 1
            elif r < 0: losses += 1
            else: unres += 1
    n = len(pnl)
    if n == 0: return None
    a = np.array(pnl)
    dec = wins + losses
    w = a[a > 0]; lo = a[a <= 0]
    return dict(
        n=n, win=wins/dec if dec else float("nan"),
        rr=tgt_d/stop_d,
        real_rr=(w.mean()/-lo.mean()) if len(w) and len(lo) else float("nan"),
        exp=float(a.mean()),
        exp_R=float(a.mean())/stop_d,
        pf=float(w.sum()/-lo.sum()) if len(lo) and lo.sum() < 0 else float("inf"),
        unres=unres/n)

def breakeven(rr, stop_d, spread):
    """Win rate needed just to break even at this R:R once spread is paid."""
    win_amt = rr*stop_d - spread
    loss_amt = stop_d + spread
    return loss_amt/(win_amt + loss_amt) if (win_amt + loss_amt) > 0 else float("nan")

def table(df, label, spread):
    print(f"\n{label}   spread ${spread}")
    hdr = (f"  {'stop$':>6}{'target$':>9}{'set RR':>8}{'WIN%':>9}{'realRR':>8}"
           f"{'PF':>8}{'E per trade':>13}{'E in R':>9}{'need win%':>11}")
    print(hdr); print("  " + "-"*(len(hdr)-2))
    for s in STOPS:
        for t in TARGETS:
            m = measure(df, s, t, spread)
            if m is None: continue
            be = breakeven(t/s, s, spread)
            flag = "  <<" if m["exp"] > 0 else ""
            print(f"  {s:>6.3f}{t:>9.3f}{m['rr']:>8.3f}{m['win']:>9.3f}"
                  f"{m['real_rr']:>8.3f}{m['pf']:>8.3f}"
                  f"{'$'+format(m['exp'],'+.3f'):>13}{m['exp_R']:>9.3f}"
                  f"{be:>11.3f}{flag}")

def main():
    print("Gold, 3 decimals: 1 point = 0.001, so the band asked for is "
          "$3.000 to $10.000.")
    print("Exits resolved on M5 bars, stop tested before target, entries every "
          f"{STEP} bars both directions.\n")
    df = fetch("GC=F", "60d", "5m")
    atr = float((df.high - df.low).tail(500).mean())
    print(f"XAUUSD M5, {len(df):,} bars, {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"average M5 bar range ${atr:.3f}  |  gold ${df.close.iloc[-1]:,.3f}")

    for sp in SPREADS:
        table(df, "XAUUSD M5", sp)

    print("\n'need win%' is the win rate that R:R requires to break even AFTER")
    print("the spread. Compare it against the WIN% column beside it: the gap")
    print("between those two numbers is the whole result.")

if __name__ == "__main__":
    main()
