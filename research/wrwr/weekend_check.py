"""Weekend risk (operator 2026-10-01: news and Trump posts over the weekend move gold at the Monday open; what if nothing is held over
the weekend?). Descriptive, not an endpoint.
Part 1: weekend gaps by year (Friday last H1 close -> first H1 open after the weekend): count, mean signed gap, mean |gap|, share of
|gap| > 50 / 100 bp, sum of gaps vs the year's total log return, and what the Monday session does after big gaps (continue or fill).
Part 2: the realised live trades of the four SHADOW configurations (and the year-by-year out-of-sample procedure) re-simulated with a
forced exit at the close of the last bar before the weekend: change in R, and the R earned or lost on the weekend gaps themselves.
Usage: python research/wrwr/weekend_check.py XAUUSD|XAGUSD"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402
import signals as SG  # noqa: E402
import history_oos as HO  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

SHADOW = {"F2-66": 66, "F2-78": 78, "F2-134": 134, "F2-86": 86}
MULT = dict(SG.EXITS)
ERAS = {"2004-14": (2004, 2015), "2015-20": (2015, 2021), "2021-24": (2021, 2025), "2025-26": (2025, 2027)}


def weekend_after(t, step):
    """True for bar i when the gap to bar i+1 contains a Saturday (UTC); the last bar is False."""
    t = np.asarray(t, np.int64)
    d0 = (t[:-1] + step) // 86400; d1 = t[1:] // 86400
    dow = (d0 + 3) % 7                                            # 1970-01-01 was a Thursday; Monday = 0
    first_sat = d0 + (5 - dow) % 7
    out = np.r_[first_sat <= d1, False]
    chk = pd.to_datetime(d0[:50] * 86400, unit="s").dayofweek.to_numpy()
    assert (chk == dow[:50]).all(), "weekday arithmetic"
    return out


def gap_table(t, o, c, sym):
    wk = weekend_after(t, 3600)
    i = np.flatnonzero(wk)
    g = (o[i + 1] / c[i] - 1) * 1e4
    yr = pd.to_datetime(t[i + 1], unit="s").year.to_numpy()
    ly = pd.Series(np.log(c), index=pd.to_datetime(t, unit="s")).groupby(lambda x: x.year).agg(["first", "last"])
    # Monday follow-through after big gaps: return from the Monday open to 24 H1 bars later, signed by the gap
    j = np.minimum(i + 1 + 24, len(c) - 1)
    after = (c[j] / o[i + 1] - 1) * 1e4 * np.sign(g)
    rows = []
    for y in range(int(yr.min()), int(yr.max()) + 1):
        m = yr == y
        if not m.any():
            continue
        big = m & (np.abs(g) > 50)
        tot = (ly.loc[y, "last"] - ly.loc[y, "first"]) * 1e4 if y in ly.index else np.nan
        rows.append(dict(year=y, weekends=int(m.sum()), mean_gap_bp=g[m].mean(), mean_abs_gap_bp=np.abs(g[m]).mean(),
                         share_gt50=(np.abs(g[m]) > 50).mean(), share_gt100=(np.abs(g[m]) > 100).mean(), sum_gaps_bp=g[m].sum(),
                         year_logret_bp=tot, big_gaps=int(big.sum()), monday_after_big_bp=after[big].mean() if big.any() else np.nan))
    X = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(f"\n{sym} weekend gaps by year (bp of the Friday close; monday_after_big = next 24 H1 bars after a |gap| > 50 bp, + = continues the gap):")
    print(X.round(2).to_string(index=False))
    allb = np.abs(g) > 50
    print(f"  all years: {len(g)} weekends, mean gap {g.mean():+.2f} bp, mean |gap| {np.abs(g).mean():.1f} bp, sum of gaps {g.sum():+.0f} bp; "
          f"after |gap| > 50 bp (n = {int(allb.sum())}) the next 24 h move {after[allb].mean():+.1f} bp in the gap direction")
    return X


def setup(sym):
    if sym == "XAUUSD":
        import build_f2 as BF2
        H, _, cuts, _ = E.load()
        P = PF.load_pool(sym, ["H1", "H4", "D1"], cuts, verify=True, loader=BF2.loader)
        z = np.load(K.ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz", allow_pickle=False)
        bars = {tf: SG.load_xau(tf)[0] for tf in ("H1", "H4", "D1")}
        oos = json.loads((K.ROOT / "data" / "wrwr" / "history_oos_A.json").read_text())["f2"]
        base = (H.t, H.o, H.c)
    else:
        import xag as X
        import xag_run as XR
        X.patch_marks()
        _, cuts, _ = X.load_xag("H1")
        P = PF.load_pool(sym, ["H1", "H4", "D1"], cuts, verify=True, loader=X.make_loader("f2"))
        z = np.load(XR.fam_path("f2"), allow_pickle=False)
        bars = {tf: X.load_xag(tf)[0] for tf in ("H1", "H4", "D1")}
        oos = HO.run(XR.fam_path("f2"), XR.OUT / "bench_F_f2.npz", years=list(range(2012, 2027)))
        a, _ = X.load_bars()
        base = (a["t"], a["o"], a["c"])
    return P, z, bars, oos, base


def trades(P, z, j, sym, bars, wk_idx, year_filter=None):
    ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
    log = []
    wr, eq, _ = PF.simulate(P, ch, z["vol_scale"], f=0.01, log=log)
    cuts = P.cuts; NW = len(cuts); act = z["active"]
    rows = []
    for (k, c, te, xt, lots, R_i, pnl, eqe) in log:
        kx = int(np.searchsorted(cuts, xt, side="left")) - 1
        if kx >= NW - 1 or not act[kx]:
            continue
        if year_filter is not None and not year_filter(kx):
            continue
        cd = P.cands[c]; B = bars[cd["tf"]]
        i = int(np.searchsorted(P.entry_t[c], te)); e = int(np.searchsorted(B.t, te))
        d = float(P.dir[c][i]); stop = cd["k_atr"] * B.atr[e]; last = e + cd["hold"] - 1
        w_ = wk_idx[cd["tf"]]
        q = int(np.searchsorted(w_, e, side="left"))
        wlast = int(w_[q]) if q < len(w_) else 10**9
        g1, ex1 = E.simulate(B, [e], [d], [stop], [MULT[cd["exit"]] * stop], [last])
        sb = float(P.stop_bp[c][i]); w = lots * float(P.stop_px[c][i]) * P.contract / (0.01 * eq[kx]) / sb
        spans = int(ex1[0]) > wlast
        dR = gapR = 0.0
        if spans:
            g2, ex2 = E.simulate(B, [e], [d], [stop], [MULT[cd["exit"]] * stop], [min(last, wlast)])
            sw1 = float(P.swap_bp[c][i]); sw2 = float(K.swap_bp(sym, B.t[[e]], B.t[ex2] + B.step, [d])[0])
            dR = ((float(g2[0]) - sw2) - (float(g1[0]) - sw1)) * w
            gapR = d * (B.o[wlast + 1] / B.o[e] - B.c[wlast] / B.o[e]) * 1e4 * w
        rows.append(dict(kx=kx, year=pd.Timestamp(int(cuts[kx]), unit="s").year, R=pnl / (0.01 * eq[kx]), spans=spans, dR=dR, gapR=gapR))
    return pd.DataFrame(rows)


def main():
    sym = sys.argv[1]
    P, z, bars, oos, base = setup(sym)
    gap_table(*base, sym)
    wk_idx = {tf: np.flatnonzero(weekend_after(B.t, B.step)) for tf, B in bars.items()}
    cuts = z["cuts"]
    ks = {Y: int(np.searchsorted(cuts, int(pd.Timestamp(f"{Y}-01-01").timestamp()))) for Y in range(2004, 2028)}
    print(f"\n{sym} SHADOW configurations: what if every position is closed at the last bar before the weekend (R, 1 % risk):")
    out = {}
    for nm, j in SHADOW.items():
        T = trades(P, z, j, sym, bars, wk_idx)
        out[nm] = T
    ymap = {}
    for y in oos["procedures"]["P1"]["years"]:
        if y["adopted"]:
            ymap[y["Y"]] = y["cfg"][0]
    parts = []
    for Y, j in ymap.items():
        parts.append(trades(P, z, j, sym, bars, wk_idx, year_filter=lambda kx, Y=Y: ks[Y] <= kx < ks[Y + 1]))
    out["P1 out-of-sample"] = pd.concat(parts) if parts else pd.DataFrame(columns=["R", "spans", "dR", "gapR", "year"])
    res = {}
    for nm, T in out.items():
        r = dict(trades=len(T), spanning=int(T.spans.sum()), total_R=float(T.R.sum()), flat_weekend_R=float(T.R.sum() + T.dR.sum()),
                 change_R=float(T.dR.sum()), weekend_gap_R=float(T.gapR.sum()))
        for e, (a, b) in ERAS.items():
            m = (T.year >= a) & (T.year < b)
            r[f"change_{e}"] = float(T.dR[m].sum()); r[f"gap_{e}"] = float(T.gapR[m].sum())
        res[nm] = r
        print(f"  {nm:<18s} trades {r['trades']:5d}, over a weekend {r['spanning']:4d} ({r['spanning'] / max(r['trades'], 1):.0%}); total {r['total_R']:+7.1f}R "
              f"-> flat on Friday {r['flat_weekend_R']:+7.1f}R (change {r['change_R']:+6.1f}R; weekend gaps alone {r['weekend_gap_R']:+6.1f}R); change by era "
              + ", ".join(f"{e} {r[f'change_{e}']:+.1f}" for e in ERAS))
    (K.ROOT / "data" / "wrwr" / f"weekend_check_{sym}.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
