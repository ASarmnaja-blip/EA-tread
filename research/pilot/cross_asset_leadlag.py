"""Cross-asset intraday lead-lag into gold.
See docs/CROSS_ASSET_LEADLAG_PREREG.md (committed before this ran). Read-only."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAMES = ["XAUUSD", "DXY", "XAGUSD", "US500", "USDJPY", "EURUSD"]
WINDOWS = (1, 3, 6)
HORIZONS = (3, 6)
ERAS = {"DEV": ("2023-09-01", "2025-04-01"), "LATER": ("2025-04-01", "2026-10-01")}
STEP = 300
WEEK = 7 * 86400
B_REPS = 4000
N_PRIMARY = 36
ALPHA = 0.05 / N_PRIMARY
BETA_WIN = 4000
COST_USD = 0.09 + 0.14 + 2 * 0.0165
OUT = ROOT / "data" / "cross_asset_leadlag.xlsx"
RNG = np.random.default_rng(20260929)


def load():
    cols, ohlc = {}, {}
    for n in NAMES:
        z = np.load(ROOT / "data" / "fresh" / f"{n}_M5.npz")
        cols[n] = pd.Series(z["c"], index=pd.to_datetime(z["t"], unit="s"))
        if n == "XAUUSD":
            ohlc = pd.DataFrame({"o": z["o"], "c": z["c"]}, index=pd.to_datetime(z["t"], unit="s"))
    df = pd.concat(cols, axis=1, join="inner").dropna()
    g = ohlc.loc[df.index]
    return df, g


def shifted(a, k):
    out = np.full(len(a), np.nan)
    out[k:] = a[:-k]
    return out


def build(df, g):
    t = df.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    logc = np.log(df.to_numpy())
    idx = {n: j for j, n in enumerate(df.columns)}
    gold = logc[:, idx["XAUUSD"]]
    n = len(t)
    r1 = np.diff(logc, axis=0, prepend=np.nan)
    feats = {}
    for name in NAMES:
        for k in WINDOWS:
            rk = logc[:, idx[name]] - shifted(logc[:, idx[name]], k)
            gk = gold - shifted(gold, k)
            if name == "XAUUSD":
                x = gk * 1e4
            else:
                a, b = pd.Series(r1[:, idx[name]]), pd.Series(r1[:, idx["XAUUSD"]])
                beta = (a.rolling(BETA_WIN, min_periods=BETA_WIN // 2).cov(b)
                        / b.rolling(BETA_WIN, min_periods=BETA_WIN // 2).var()).to_numpy()
                x = (rk - beta * gk) * 1e4
            contiguous = (t - shifted(t.astype(float), k)) == k * STEP
            feats[(name, k)] = np.where(contiguous, x, np.nan)
    go, gc = g["o"].to_numpy(float), g["c"].to_numpy(float)
    fwd, ok = {}, {}
    for h in HORIZONS:
        f = np.full(n, np.nan); good = np.zeros(n, bool)
        i = np.arange(n - h - 1)
        ent, ext = i + 1, i + h
        contig = (t[ext] - t[ent]) == (h - 1) * STEP
        k0 = np.floor((t[ent] - 75600) / 86400)
        k1 = np.floor((t[ext] + STEP - 1 - 75600) / 86400)
        f[i] = (gc[ext] / go[ent] - 1) * 1e4
        good[i] = contig & (k0 == k1) & ((t[ent] - t[i]) == STEP)
        fwd[h], ok[h] = f, good
    dt = pd.to_datetime(t, unit="s")
    era = {k: np.asarray((dt >= a) & (dt < b)) for k, (a, b) in ERAS.items()}
    return t, feats, fwd, ok, era


def transfer(t, x, fwd, ok, era, train, test, reps=B_REPS, shift=0):
    if shift:
        x = np.roll(x, shift)
    def valid(e):
        return np.flatnonzero(era[e] & ok & np.isfinite(fwd) & np.isfinite(x))
    it, ie = valid(train), valid(test)
    if len(it) < 2000 or len(ie) < 2000:
        return None
    edges = np.unique(np.quantile(x[it], np.linspace(0.1, 0.9, 9)))
    ytr = fwd[it] - fwd[it].mean()
    means = pd.Series(ytr).groupby(np.searchsorted(edges, x[it])).mean()
    p = means.reindex(np.searchsorted(edges, x[ie])).to_numpy()
    y = fwd[ie] - fwd[ie].mean()
    good = np.isfinite(p)
    p, y, wk = p[good], y[good], t[ie][good] // WEEK
    uw, inv = np.unique(wk, return_inverse=True)
    S = np.stack([np.bincount(inv, weights=v) for v in (p, y, p * p, y * y, p * y, np.ones_like(p))], 1)

    def corr(s):
        n_, sp, sy, spp, syy, spy = s[5], s[0], s[1], s[2], s[3], s[4]
        return (n_ * spy - sp * sy) / math.sqrt(max((n_ * spp - sp * sp) * (n_ * syy - sy * sy), 1e-18))
    obs = corr(S.sum(0))
    ix = RNG.integers(0, len(uw), (reps, len(uw)))
    tot = S[ix].sum(1)
    n_, sp, sy, spp, syy, spy = (tot[:, q] for q in (5, 0, 1, 2, 3, 4))
    boot = (n_ * spy - sp * sy) / np.sqrt(np.maximum((n_ * spp - sp * sp) * (n_ * syy - sy * sy), 1e-18))
    dev = boot - boot.mean()
    return dict(rho=obs, p=(np.sum(np.abs(dev) >= abs(obs)) + 1) / (reps + 1),
                lo=np.percentile(boot, 2.5), hi=np.percentile(boot, 97.5), n=len(p),
                sd=float(np.std(fwd[ie])))


def self_check(t, feats, fwd, ok, era):
    """100 random circular shifts (>= 2 weeks) must reject near 5%; planted rho ~0.05 found."""
    x = feats[("DXY", 3)]; h = 6
    n = len(x); wk = 2 * 7 * 288
    rej = 0
    for _ in range(100):
        s = int(RNG.integers(wk, n - wk))
        r = transfer(t, x, fwd[h], ok[h], era, "DEV", "LATER", reps=400, shift=s)
        rej += bool(r and r["p"] < 0.05)
    y = fwd[h].copy()
    sd = np.nanstd(y)
    plant = np.where(np.isfinite(x), 0.05 * sd * (x - np.nanmean(x)) / np.nanstd(x), 0.0)
    r = transfer(t, x, y + plant, ok[h], era, "DEV", "LATER", reps=800)
    return rej / 100, r["p"], r["rho"]


def main() -> int:
    os.chdir(ROOT)
    df, g = load()
    t, feats, fwd, ok, era = build(df, g)
    print(f"aligned M5 bars {len(t):,}; DEV {int(era['DEV'].sum()):,}  LATER {int(era['LATER'].sum()):,}", flush=True)
    rej, pp, rp = self_check(t, feats, fwd, ok, era)
    print(f"self-check: circular-shift null rejection {rej:.0%} (band 1%-10%); planted rho~0.05 -> rho {rp:.3f}, p {pp:.4f}",
          flush=True)
    cost_bp = COST_USD / float(np.median(g["o"].to_numpy()[era["LATER"]])) * 1e4
    rows = []
    for name in NAMES:
        for k in WINDOWS:
            for h in HORIZONS:
                a = transfer(t, feats[(name, k)], fwd[h], ok[h], era, "DEV", "LATER")
                b = transfer(t, feats[(name, k)], fwd[h], ok[h], era, "LATER", "DEV")
                if a is None or b is None:
                    continue
                gross = 0.8 * abs(a["rho"]) * a["sd"]
                rows.append(dict(instrument=name if name != "XAUUSD" else "gold own", window_bars=k,
                                 horizon_bars=h, rho_DEV_to_LATER=a["rho"], p_fwd=a["p"], ci_lo=a["lo"],
                                 ci_hi=a["hi"], rho_LATER_to_DEV=b["rho"], p_back=b["p"],
                                 implied_gross_bp=gross, cost_bp=cost_bp, n=a["n"]))
    R = pd.DataFrame(rows)
    R["LEAD"] = ((R.p_fwd < ALPHA) & (R.p_back < 0.05) &
                 (np.sign(R.rho_DEV_to_LATER) == np.sign(R.rho_LATER_to_DEV)))
    R["TRADEABLE"] = R.LEAD & (R.implied_gross_bp > R.cost_bp)
    R.to_excel(OUT, index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    show = R.reindex(R.rho_DEV_to_LATER.abs().sort_values(ascending=False).index).head(12)
    print(f"\nalpha per test = {ALPHA:.5f}; round-trip cost = {cost_bp:.2f} bp; 36 primary tests")
    print(show[["instrument", "window_bars", "horizon_bars", "rho_DEV_to_LATER", "p_fwd",
                "rho_LATER_to_DEV", "p_back", "implied_gross_bp", "LEAD", "TRADEABLE"]].round(4).to_string(index=False))
    print(f"\nleads: {int(R.LEAD.sum())}/36   tradeable after cost: {int(R.TRADEABLE.sum())}/36   "
          f"largest |rho| = {R.rho_DEV_to_LATER.abs().max():.4f}")
    print(f"required rho to cover cost at these horizons ~ {cost_bp / (0.8 * R.sd.mean()) if 'sd' in R else float('nan'):.3f}"
          if False else "")
    sd_mean = float(np.nanmean([transfer(t, feats[("DXY", 3)], fwd[h], ok[h], era, 'DEV', 'LATER', reps=50)['sd'] for h in HORIZONS]))
    print(f"mean SD of 15-30 min gold return ~ {sd_mean:.1f} bp -> rho needed just to cover cost ~ {cost_bp / (0.8 * sd_mean):.3f}")
    print(f"saved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
