"""docs/TREND_VS_HOLD_PREREG.md: is D1 trend following an edge in timing or only beta? Test 1 timing alpha vs random placement of the same
trades; Test 2 buy-and-hold at the leverage that matches the trend system's maximum drawdown; Test 3 bear phases (>= 30 % declines).
Markets: 15 MT5 (USDINR excluded), gold Dukascopy D1 2003-26 (periods 2003-08 / 2009-26), silver. Optional argv: a module path providing
extra markets (option ค). Usage: python research/bundle/z1_trend_vs_hold.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import y1_htf_system as Y  # noqa: E402

OUT = C.ROOT / "data" / "bundle2"
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
K_DRAWS = 2000


def taken_trades(B, sym):
    out = {}
    for system in C.SYSTEMS:
        TL = C.trend_trades(B, sym, system, 1); TS = C.trend_trades(B, sym, system, -1)
        out[(system, "long")] = TL[C.one_position(TL)]
        both = pd.concat([TL, TS], ignore_index=True)
        out[(system, "both")] = both[C.one_position(both)]
    return out


def net_pct(T):
    return (T.d * (T.px / T.ep - 1) - (T.cost_bp + T.swap_bp) / 1e4).to_numpy()


def control_draws(B, sym, T, rng):
    """K_DRAWS random placements of the trades (same direction and duration): mean net % return per trade per draw."""
    n = len(B.o); dur = np.maximum((T.xf - T.e).to_numpy(), 1); d = T.d.to_numpy()
    first = 60
    hi = n - 1 - dur
    ok = hi > first
    dur, d, hi = dur[ok], d[ok], hi[ok]
    if not len(dur):
        return np.full(K_DRAWS, np.nan)
    r = (first + rng.random((K_DRAWS, len(dur))) * (hi - first)).astype(np.int64)
    ex = r + dur
    gross = d * (B.o[ex] / B.o[r] - 1)
    sw = C.swap_bp(sym, B.t[r].ravel(), B.t[ex].ravel(), np.broadcast_to(d, r.shape).ravel()).reshape(r.shape)
    net = gross - (C.cost_rt_bp(sym) + sw) / 1e4
    return net.mean(1)


def bh_returns(B, sym):
    r = B.c[1:] / B.c[:-1] - 1
    sw = C.swap_bp(sym, B.t[:-1], B.t[1:], np.ones(len(r))) / 1e4
    return pd.Series(r - sw, index=B.t[1:])


def lev_curve(r, L):
    eq = np.cumprod(1 + L * r); peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    return eq, float((1 - eq / peak).max())


def dd_matched(r, target_dd, yrs):
    lo, hi = 0.0, 5.0
    for _ in range(40):
        mid = (lo + hi) / 2
        _, dd = lev_curve(r, mid)
        lo, hi = (mid, hi) if dd < target_dd else (lo, mid)
    eq, dd = lev_curve(r, lo)
    return lo, (eq[-1]) ** (1 / yrs) - 1, dd


def bear_phases(B, min_drop=0.30):
    c = B.c; out = []; i = 0; n = len(c)
    peak_i = 0
    while i < n:
        if c[i] > c[peak_i]:
            peak_i = i
        dd = 1 - c[i] / c[peak_i]
        if dd >= min_drop:
            j = i
            trough = i
            while j < n and c[j] < c[peak_i]:
                if c[j] < c[trough]:
                    trough = j
                j += 1
            out.append((peak_i, trough))
            i = j; peak_i = min(j, n - 1)
            continue
        i += 1
    return out


def markets():
    m = {s: (C.bars(s, "D1"), s, {"2016-26": (None, None)}) for s in Y.CLEAN if s != "USDINR"}
    m["GOLD_DUKAS"] = (Y.early_bars("D1"), "XAUUSD", {"2003-08 (clean)": ("2003-08-01", "2009-01-01"), "2009-26": ("2009-01-01", "2026-10-01")})
    m["XAGUSD"] = (C.bars("XAGUSD", "D1"), "XAGUSD", {"2010-26": ("2010-01-01", "2026-10-01")})
    return m


def main():
    rng = np.random.default_rng(2026)
    rows, draws, bears, fin = [], {}, [], []
    for mkt, (B, sym, periods) in markets().items():
        tk = taken_trades(B, sym)
        for (system, sides), T in tk.items():
            for p, (a, b) in periods.items():
                TT = T if a is None else T[(T.t >= C.ts(a)) & (T.t < C.ts(b))]
                if len(TT) < 5:
                    continue
                real = net_pct(TT).mean()
                ctl = control_draws(B, sym, TT, rng)
                draws[(mkt, p, system, sides)] = ctl
                eqr = C.equity(TT, 0.01, a, b) if a else C.equity(TT, 0.01)
                t0 = int(TT.t.min()) if a is None else C.ts(a); t1 = int(B.t[-1]) if a is None else min(C.ts(b), int(B.t[-1]))
                r = bh_returns(B, sym); r = r[(r.index >= t0) & (r.index < t1)].to_numpy()
                yrs = (t1 - t0) / (365.25 * 86400)
                L1, bh1 = lev_curve(r, 1.0)
                Lm, cagr_m, dd_m = dd_matched(r, max(eqr.get("dd", 0.0), 1e-4), yrs)
                rows.append(dict(mkt=mkt, period=p, system=system, sides=sides, n=len(TT), real_pct=real * 100, ctl_pct=np.nanmean(ctl) * 100,
                                 alpha_pct=(real - np.nanmean(ctl)) * 100, p_mkt=float(np.mean(ctl >= real)), trend_cagr=eqr.get("cagr"), trend_dd=eqr.get("dd"),
                                 bh_cagr_L1=L1[-1] ** (1 / yrs) - 1, bh_dd_L1=bh1, bh_L_matched=Lm, bh_cagr_matched=cagr_m))
        for (pk, tr) in bear_phases(B):
            a_t, b_t = int(B.t[pk]), int(B.t[tr])
            bh = B.c[tr] / B.c[pk] - 1
            for (system, sides), T in tk.items():
                TT = T[(T.t >= a_t) & (T.t <= b_t)]
                eq = C.equity(TT, 0.01) if len(TT) else dict(end=10_000.0)
                bears.append(dict(mkt=mkt, peak=str(pd.Timestamp(a_t, unit="s").date()), trough=str(pd.Timestamp(b_t, unit="s").date()), bh_pct=bh * 100,
                                  system=system, sides=sides, trades=len(TT), trend_pct=(eq.get("end", 10_000.0) / 10_000 - 1) * 100))
        log(f"{mkt} done")
    D = pd.DataFrame(rows); D.to_csv(OUT / "z1_trend_vs_hold.csv", index=False)
    pd.DataFrame(bears).to_csv(OUT / "z1_bear_phases.csv", index=False)
    clean = [m for m in Y.CLEAN if m != "USDINR"]
    verdict = []
    for system in C.SYSTEMS:
        for sides in ("long", "both"):
            x = D[D.mkt.isin(clean) & (D.system == system) & (D.sides == sides)]
            real_alpha = x.alpha_pct.mean()
            ks = [(m, "2016-26", system, sides) for m in x.mkt]
            M = np.vstack([draws[k] for k in ks])                                  # markets x draws (control means)
            real = x.real_pct.to_numpy()[:, None] / 100
            ctl_mean = np.nanmean(M, axis=1, keepdims=True)
            # pooled control alpha of each joint draw: control draw minus the control mean (alpha under the null)
            null = np.nanmean(M - ctl_mean, axis=0) * 100
            p = float(np.mean(null >= real_alpha))
            share = float((x.alpha_pct > 0).mean())
            beat_bh = float((x.trend_cagr > x.bh_cagr_matched).mean())
            verdict.append(dict(system=system, sides=sides, markets=len(x), pooled_alpha_pct=real_alpha, p=p, share_alpha_pos=share,
                                share_beats_dd_matched_bh=beat_bh, PASS_timing=bool(real_alpha > 0 and p < 0.05 and share >= 0.6), PASS_vs_bh_markets=beat_bh >= 0.6))
    V = pd.DataFrame(verdict)
    # portfolio level (Test 2): trend portfolio of the clean markets vs equal-weight buy-and-hold scaled to the same drawdown
    for system in C.SYSTEMS:
        for sides in ("long", "both"):
            allT = []
            for m in clean:
                B, sym, _ = markets_cache[m]
                tk = taken_cache[(m, system, sides)]
                allT.append(tk)
            P = pd.concat(allT)
            eq = C.equity(P, 0.01)
            R = pd.concat([bh_returns(markets_cache[m][0], m).rename(m) for m in clean], axis=1)
            R = R[(R.index >= int(P.t.min()))].fillna(0.0).mean(axis=1).to_numpy()
            yrs = len(R) / 252.0
            Lm, cagr_m, dd_m = dd_matched(R, eq["dd"], yrs)
            fin.append(dict(system=system, sides=sides, trend_cagr=eq["cagr"], trend_dd=eq["dd"], bh_L=Lm, bh_cagr_dd_matched=cagr_m, bh_dd=dd_m,
                            PASS_portfolio=bool(eq["cagr"] > cagr_m)))
    Fp = pd.DataFrame(fin); Fp.to_csv(OUT / "z1_portfolio.csv", index=False)
    V = V.merge(Fp[["system", "sides", "PASS_portfolio"]], on=["system", "sides"])
    V["PASS_vs_bh"] = V.PASS_vs_bh_markets & V.PASS_portfolio
    V.to_csv(OUT / "z1_verdict.csv", index=False)
    pd.set_option("display.width", 220)
    print(V.round(4).to_string(index=False)); print(Fp.round(4).to_string(index=False))
    log("done")


markets_cache, taken_cache = {}, {}


def _prime():
    for m in [x for x in Y.CLEAN if x != "USDINR"]:
        B = C.bars(m, "D1"); markets_cache[m] = (B, m, None)
        tk = taken_trades(B, m)
        for (system, sides), T in tk.items():
            taken_cache[(m, system, sides)] = T


if __name__ == "__main__":
    _prime()
    main()
