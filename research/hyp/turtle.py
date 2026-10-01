"""Classic trend following with trailing exits ("cut losses, let profits run"), canonical parameters only (no tuning):
  TURTLE_S1  : enter on a close beyond the 20-day high (low); exit on a close beyond the 10-day low (high); initial stop 2 N (N = ATR20)
  TURTLE_S2  : 55-day entry, 20-day exit, 2 N stop
  CHANDELIER : 55-day entry; exit when the close falls below the highest high since entry - 3 x ATR22 (mirror for shorts); 2 N initial stop
Each as LONG+SHORT and LONG-ONLY. One position per system and market; next-open fills; stops checked on the bar's range (gap fills at the open);
exits on closes fill at the next open. Gold (Dukascopy D1, C4 cost + swap), silver (HistData D1), and eight MT5 markets (fixed cost 3/4/10 bp,
swap not modelled). Risk 1 % of equity per trade on $10,000 (R = initial 2 N stop). Usage: python research/hyp/turtle.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import explore_scale as ES  # noqa: E402
import trend_basket as TB  # noqa: E402

K = B1.K
SYSTEMS = {"TURTLE_S1": (20, 10, None), "TURTLE_S2": (55, 20, None), "CHANDELIER": (55, None, 3.0)}


def atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    return pd.Series(tr).rolling(n, min_periods=n).mean().to_numpy()            # known at the close of each bar


def run(t, o, h, l, c, entry_n, exit_n, chand, long_only, cost_fn):
    n = len(c)
    hiE = pd.Series(h).rolling(entry_n).max().shift(1).to_numpy(); loE = pd.Series(l).rolling(entry_n).min().shift(1).to_numpy()
    if exit_n:
        hiX = pd.Series(h).rolling(exit_n).max().shift(1).to_numpy(); loX = pd.Series(l).rolling(exit_n).min().shift(1).to_numpy()
    N = atr(h, l, c, 20); A22 = atr(h, l, c, 22)
    trades = []; pos = 0; i = entry_n + 2
    while i < n - 1:
        if pos == 0:
            sig = 1 if c[i] > hiE[i] else (-1 if (c[i] < loE[i] and not long_only) else 0)
            if sig == 0 or not np.isfinite(N[i]):
                i += 1; continue
            e = i + 1; ep = o[e]; stop = ep - sig * 2 * N[i]; risk = 2 * N[i]; best = ep; j = e
            exit_px = None
            while j < n:
                if sig > 0 and l[j] <= stop:
                    exit_px = min(o[j], stop) if j > e else stop; break
                if sig < 0 and h[j] >= stop:
                    exit_px = max(o[j], stop) if j > e else stop; break
                best = max(best, h[j]) if sig > 0 else min(best, l[j])
                if exit_n:
                    hit = (c[j] < loX[j]) if sig > 0 else (c[j] > hiX[j])
                else:
                    hit = (c[j] < best - chand * A22[j]) if sig > 0 else (c[j] > best + chand * A22[j])
                if hit and j + 1 < n:
                    exit_px = o[j + 1]; j = j + 1; break
                j += 1
            if exit_px is None:
                exit_px = c[n - 1]; j = n - 1
            gross = sig * (exit_px / ep - 1) * 1e4
            cost, sw = cost_fn(e, j, sig)
            trades.append(dict(t=int(t[e]), t_exit=int(t[j]), d=sig, R=(gross - cost - sw) / (risk / ep * 1e4), gR=gross / (risk / ep * 1e4),
                               days=int(j - e + 1)))
            i = j + 1
        else:
            i += 1
    return pd.DataFrame(trades)


def finance(tr, a, b):
    ta, tb = int(pd.Timestamp(a).timestamp()), int(pd.Timestamp(b).timestamp())
    x = tr[(tr.t >= ta) & (tr.t < tb)].sort_values("t_exit")
    yrs = (tb - ta) / (365.25 * 86400)
    if not len(x):
        return dict(n=0)
    eq = 10_000.0; peak = eq; dd = 0.0; yearly = {}
    for te, R in zip(x.t_exit, x.R):
        eq *= 1 + 0.01 * R; peak = max(peak, eq); dd = max(dd, 1 - eq / peak); yearly[pd.Timestamp(int(te), unit="s").year] = eq
    prev = 10_000.0; yr = []
    for y in sorted(yearly):
        yr.append(yearly[y] / prev - 1); prev = yearly[y]
    return dict(n=len(x), per_yr=len(x) / yrs, avg_R=float(x.R.mean()), win=float((x.R > 0).mean()), best_R=float(x.R.max()), end=eq,
                cagr=(eq / 10_000) ** (1 / yrs) - 1, dd=dd, pos_years=f"{sum(v > 0 for v in yr)}/{len(yr)}", days=float(x.days.mean()))


def main():
    t0 = time.time()
    G, _ = ES.bars("XAUUSD"); S, _ = ES.bars("XAGUSD")
    mk = {"XAUUSD": G["D1"], "XAGUSD": S["D1"]}
    for sym in TB.MARKETS:
        mk[sym] = TB.mt5_bars(sym)
    rows = []
    for sym, B in mk.items():
        if sym in ("XAUUSD", "XAGUSD"):
            def cost_fn(e, j, sig, B=B, sym=sym):
                c = float(B1.cost_bp(sym, B.spread_bp[[e]], B.t[[e]])[0])
                sw = float(K.swap_bp(sym, B.t[[e]], B.t[[j]] + 86400, np.array([float(sig)]))[0])
                return c, sw
        else:
            fixed = TB.MARKETS[sym]
            cost_fn = lambda e, j, sig, fixed=fixed: (fixed, 0.0)
        periods = {"XAUUSD": {"2004-15": ("2004-01-01", "2016-01-01"), "2016-26": ("2016-01-01", "2026-10-01")},
                   "XAGUSD": {"2010-26": ("2010-01-01", "2026-09-25")}}.get(sym, {"2016-26": ("2016-08-01", "2026-10-01")})
        for name, (en, ex, ch) in SYSTEMS.items():
            for lo in (False, True):
                tr = run(B.t, B.o, B.h, B.l, B.c, en, ex, ch, lo, cost_fn)
                for p, (a, b) in periods.items():
                    f = finance(tr, a, b) if len(tr) else dict(n=0)
                    rows.append(dict(market=sym, system=name + (" LONG-ONLY" if lo else ""), period=p, **f))
        print(f"{sym} done ({time.time() - t0:.0f}s)", flush=True)
    T = pd.DataFrame(rows)
    T.to_csv(B1.OUT / "turtle.csv", index=False)
    pd.set_option("display.width", 250)
    for sym in mk:
        x = T[T.market == sym]
        print(f"\n{sym}")
        print(x[["system", "period", "n", "per_yr", "avg_R", "win", "best_R", "days", "cagr", "dd", "end", "pos_years"]].round(3).to_string(index=False))
    o = T[~T.market.isin(["XAUUSD", "XAGUSD"])]
    print("\nCross-market (8 untouched markets, 2016-26): average CAGR by system")
    print(o.groupby("system")[["avg_R", "cagr", "dd"]].mean().round(3).to_string())
    print(f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
