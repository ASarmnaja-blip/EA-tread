"""Plan B — daily-scale, drift-controlled, cross-fitted over 2003-2015.
See docs/PLAN_B_DAILY_PREREG.md (committed before Plan A's result was known).
Read-only.  Usage: python research/pilot/plan_b_daily.py [--selfcheck-only]"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research" / "history"))
from build_all_tf import load_kind  # noqa: E402

HORIZONS = (1, 5, 20)
N_TESTS = 30
ALPHA = 0.05 / N_TESTS
B_REPS = 10000
BLOCK_DAYS = 10          # Amendment 1 replaces this after null calibration
MIN_BARS = 12
CATEGORICAL = ("dow", "month")
CLEAN = (2003, 2015)
OUT = ROOT / "data" / "plan_b_daily.xlsx"
RNG = np.random.default_rng(20260929)


def daily_from_h1():
    h = load_kind("hour")
    assert h is not None
    day = (h.index - pd.Timedelta(hours=22)).floor("D")
    g = h.groupby(day)
    d = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.size()})
    d = d[d.n >= MIN_BARS]
    return d


def make(d):
    c = d.c.to_numpy(float); o = d.o.to_numpy(float)
    lr = np.r_[np.nan, np.diff(np.log(c))]
    sd60 = pd.Series(lr).rolling(60).std().to_numpy()
    sd20 = pd.Series(lr).rolling(20).std().to_numpy()
    sd250 = pd.Series(lr).rolling(250).std().to_numpy()
    ma200 = pd.Series(c).rolling(200).mean().to_numpy()
    f = {}
    for L in (1, 5, 20, 60, 120, 250):
        prev = np.full(len(c), np.nan); prev[L:] = c[:-L]
        f[f"ret{L}"] = np.log(c / prev) / (sd60 * math.sqrt(L))
    f["dist_ma200"] = np.log(c / ma200) / (sd60 * math.sqrt(60))
    f["vol_ratio"] = sd20 / sd250
    f["dow"] = d.index.weekday.to_numpy().astype(float)
    f["month"] = d.index.month.to_numpy().astype(float)
    days = (d.index.astype("datetime64[s]").astype(np.int64).to_numpy() // 86400)
    fwd, ok = {}, {}
    n = len(c)
    for H in HORIZONS:
        y = np.full(n, np.nan); good = np.zeros(n, bool)
        j = np.arange(n - H - 1)
        y[j] = (c[j + H] / o[j + 1] - 1) * 1e4
        good[j] = (days[j + H] - days[j]) <= H + 4
        fwd[H], ok[H] = y, good
    return f, fwd, ok, days, d.index.year.to_numpy()


def bins_fn(name, x_train):
    if name in CATEGORICAL:
        return lambda v: v
    edges = np.unique(np.quantile(x_train, np.linspace(0.1, 0.9, 9)))
    return lambda v: np.searchsorted(edges, v)


def crossfit(x, name, y, ok, years, order, H, y_plant=None):
    """Leave-one-year-out over CLEAN years. Returns pooled (pred, target, day-index, year)."""
    yy = y if y_plant is None else y + y_plant
    P, T, I, Y = [], [], [], []
    valid = ok & np.isfinite(x) & np.isfinite(yy)
    for yr in range(CLEAN[0], CLEAN[1] + 1):
        test = valid & (years == yr)
        first_test = np.flatnonzero(years == yr)
        if len(first_test) == 0 or test.sum() < 50:
            continue
        train = valid & (years >= CLEAN[0]) & (years <= CLEAN[1]) & (years != yr)
        # embargo: training days whose forward window reaches into the test year
        lo = first_test[0] - (H + 1)
        train[max(lo, 0):first_test[0]] = False
        it, ie = np.flatnonzero(train), np.flatnonzero(test)
        bn = bins_fn(name, x[it])
        mu = yy[it].mean()
        means = pd.Series(yy[it] - mu).groupby(bn(x[it])).mean()
        p = means.reindex(bn(x[ie])).to_numpy()
        g = np.isfinite(p)
        P.append(p[g]); T.append((yy[ie] - mu)[g]); I.append(ie[g]); Y.append(np.full(g.sum(), yr))
    if not P:
        return None
    return np.concatenate(P), np.concatenate(T), np.concatenate(I), np.concatenate(Y)


def pooled_stats(p, y, idx, days, H, reps):
    blk = (days[idx] - days[0]) // BLOCK_DAYS
    ub, inv = np.unique(blk, return_inverse=True)
    S = np.stack([np.bincount(inv, weights=v) for v in (p, y, p * p, y * y, p * y, np.ones_like(p))], 1)

    def corr(s):
        n_, sp, sy, spp, syy, spy = s[5], s[0], s[1], s[2], s[3], s[4]
        return (n_ * spy - sp * sy) / math.sqrt(max((n_ * spp - sp * sp) * (n_ * syy - sy * sy), 1e-18))
    obs = corr(S.sum(0))
    ix = RNG.integers(0, len(ub), (reps, len(ub)))
    tot = S[ix].sum(1)
    n_, sp, sy, spp, syy, spy = (tot[:, q] for q in (5, 0, 1, 2, 3, 4))
    boot = (n_ * spy - sp * sy) / np.sqrt(np.maximum((n_ * spp - sp * sp) * (n_ * syy - sy * sy), 1e-18))
    dev = boot - boot.mean()
    return obs, (np.sum(np.abs(dev) >= abs(obs)) + 1) / (reps + 1)


def run_test(x, name, fwd, ok, years, days, H, reps, plant=None):
    r = crossfit(x, name, fwd[H], ok[H], years, None, H, plant)
    if r is None:
        return None
    p, y, idx, yrs = r
    rho, pv = pooled_stats(p, y, idx, days, H, reps)
    per = [np.corrcoef(p[yrs == yr], y[yrs == yr])[0, 1] for yr in np.unique(yrs) if (yrs == yr).sum() > 30]
    per = np.array(per)
    same = int(np.sum(np.sign(per) == np.sign(rho)))
    sd = float(np.std(y))
    return dict(rho=rho, p=pv, years_same_sign=same, years=len(per), sd=sd,
                sharpe=0.8 * rho * math.sqrt(252 / H) if H else np.nan, n=len(p))


def later_sign(x, name, fwd, ok, years, H):
    """Fit on all clean years, apply to 2016+ (consistency only)."""
    valid = ok[H] & np.isfinite(x) & np.isfinite(fwd[H])
    tr = valid & (years >= CLEAN[0]) & (years <= CLEAN[1])
    te = valid & (years > CLEAN[1])
    if te.sum() < 300:
        return np.nan
    it, ie = np.flatnonzero(tr), np.flatnonzero(te)
    bn = bins_fn(name, x[it])
    mu = fwd[H][it].mean()
    means = pd.Series(fwd[H][it] - mu).groupby(bn(x[it])).mean()
    p = means.reindex(bn(x[ie])).to_numpy()
    g = np.isfinite(p)
    return float(np.corrcoef(p[g], fwd[H][ie][g] - fwd[H][ie][g].mean())[0, 1])


def self_check(feats, fwd, ok, years, days):
    x, name, H = feats["ret5"], "ret5", 5
    n = len(x)
    rej = 0
    for _ in range(60):
        s = int(RNG.integers(260, n - 260))
        r = run_test(np.roll(x, s), name, fwd, ok, years, days, H, reps=300)
        rej += bool(r and r["p"] < 0.05)
    sd = np.nanstd(fwd[H])
    plant = np.where(np.isfinite(x), 0.10 * sd * (x - np.nanmean(x)) / np.nanstd(x), 0.0)
    r = run_test(x, name, fwd, ok, years, days, H, reps=1000, plant=plant)
    return rej / 60, r["p"], r["rho"]


def main() -> int:
    os.chdir(ROOT)
    d = daily_from_h1()
    feats, fwd, ok, days, years = make(d)
    last_clean = d.index[d.index.year <= CLEAN[1]][-1]
    print(f"daily bars {len(d):,} ({d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d}); clean era ends {last_clean:%Y-%m-%d}; "
          f"days in clean era {int(((years >= CLEAN[0]) & (years <= CLEAN[1])).sum()):,}")
    rej, pp, rp = self_check(feats, fwd, ok, years, days)
    print(f"self-check: circular-shift null rejection {rej:.0%} (band 1%-10%); planted rho~0.10 -> rho {rp:.3f}, p {pp:.4f}", flush=True)
    assert 0.01 <= rej <= 0.10, "self-check failed"
    if "--selfcheck-only" in sys.argv:
        return 0
    rows = []
    for name, x in feats.items():
        for H in HORIZONS:
            r = run_test(x, name, fwd, ok, years, days, H, B_REPS)
            if r is None:
                continue
            r.update(feature=name, H_days=H, later_rho=later_sign(x, name, fwd, ok, years, H))
            rows.append(r)
    R = pd.DataFrame(rows)
    R["LEAD"] = ((R.p < ALPHA) & (R.years_same_sign >= 10) &
                 (np.sign(R.later_rho.fillna(0)) == np.sign(R.rho)))
    R = R[["feature", "H_days", "rho", "p", "years_same_sign", "years", "later_rho", "sharpe", "sd", "n", "LEAD"]]
    R.to_excel(OUT, index=False)
    pd.set_option("display.width", 220)
    top = R.reindex(R.rho.abs().sort_values(ascending=False).index)
    print(f"\nalpha = {ALPHA:.5f}; 30 primary tests; sorted by |rho|")
    print(top.head(12).round(4).to_string(index=False))
    print(f"\nLEADS {int(R.LEAD.sum())}/{len(R)}   largest |rho| {R.rho.abs().max():.4f}")
    print(f"saved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
