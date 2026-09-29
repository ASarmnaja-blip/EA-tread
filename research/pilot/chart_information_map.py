"""Required edge shape + information map of the chart.
See docs/CHART_MEASUREMENT_PREREG.md (committed before this ran). Read-only."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from edge_search_bp import COST_USD, ERAS, HORIZONS, WEEK, Market  # noqa: E402

B_REPS = 2000
N_PRIMARY = 30
ALPHA = 0.05 / N_PRIMARY
OUT = ROOT / "data" / "chart_information_map.xlsx"
RNG = np.random.default_rng(20260929)
CATEGORICAL = ("hour_utc", "weekday", "session")


def shift(a, k):
    out = np.full(len(a), np.nan)
    out[k:] = a[:-k]
    return out


def build_features(mk):
    b, c, cl = mk.b15, mk.c, mk.cl
    atr = np.asarray(c.atr, float)
    h, l = np.asarray(b.h, float), np.asarray(b.l, float)

    def dist(x):
        return (cl - np.asarray(x, float)) / atr

    path = pd.Series(np.abs(np.diff(cl, prepend=np.nan))).rolling(20).sum().to_numpy()
    er = np.abs(cl - shift(cl, 20)) / path
    return {
        "atr_pct": mk.pct,
        "dist_vwap_atr": dist(c.vwap),
        "dist_ema50_atr": dist(c.ema50),
        "dist_ema200_atr": dist(c.ema200),
        "dist_hh20_atr": dist(c.hh20),
        "dist_ll20_atr": dist(c.ll20),
        "ret1_atr": (cl - shift(cl, 1)) / atr,
        "ret4_atr": (cl - shift(cl, 4)) / atr,
        "ret16_atr": (cl - shift(cl, 16)) / atr,
        "range_ratio": (h - l) / atr,
        "efficiency20": er,
        "trend_sep": np.asarray(c.sep, float),
        "hour_utc": mk.dt.hour.to_numpy().astype(float),
        "weekday": mk.dt.weekday.to_numpy().astype(float),
        "session": pd.factorize(np.asarray(c.session))[0].astype(float),
    }


def valid_idx(mk, era, H, x):
    m = mk.era_mask[era] & mk.ok[H] & np.isfinite(mk.fwd[H]) & np.isfinite(x) & (np.arange(mk.n) >= mk.c.warm)
    return np.flatnonzero(m)


def target(mk, era, H, kind):
    allv = np.flatnonzero(mk.era_mask[era] & mk.ok[H] & np.isfinite(mk.fwd[H]) & (np.arange(mk.n) >= mk.c.warm))
    f = mk.fwd[H]
    if kind == "dir":
        return f - f[allv].mean()
    return np.abs(f)


def binner(name, x, idx):
    if name in CATEGORICAL:
        return lambda v: v
    edges = np.unique(np.quantile(x[idx], np.linspace(0.1, 0.9, 9)))
    return lambda v: np.searchsorted(edges, v)


def transfer(mk, name, x, kind, H, train, test):
    it, ie = valid_idx(mk, train, H, x), valid_idx(mk, test, H, x)
    if len(it) < 500 or len(ie) < 500:
        return None
    bn = binner(name, x, it)
    ytr = target(mk, train, H, kind)[it]
    means = pd.Series(ytr).groupby(bn(x[it])).mean().to_dict()
    bt = bn(x[ie])
    p = np.array([means.get(v, np.nan) for v in bt])
    y = target(mk, test, H, kind)[ie]
    ok = np.isfinite(p)
    p, y, wk = p[ok], y[ok], (mk.t[ie][ok] // WEEK)
    uw, inv = np.unique(wk, return_inverse=True)
    S = np.stack([np.bincount(inv, weights=v) for v in (p, y, p * p, y * y, p * y, np.ones_like(p))], 1)

    def corr(s):
        n, sp, sy, spp, syy, spy = s[5], s[0], s[1], s[2], s[3], s[4]
        return (n * spy - sp * sy) / math.sqrt(max((n * spp - sp * sp) * (n * syy - sy * sy), 1e-18))
    obs = corr(S.sum(0))
    idx = RNG.integers(0, len(uw), (B_REPS, len(uw)))
    tot = S[idx].sum(1)
    n, sp, sy, spp, syy, spy = (tot[:, k] for k in (5, 0, 1, 2, 3, 4))
    boot = (n * spy - sp * sy) / np.sqrt(np.maximum((n * spp - sp * sp) * (n * syy - sy * sy), 1e-18))
    dev = boot - boot.mean()
    pval = (np.sum(np.abs(dev) >= abs(obs)) + 1) / (B_REPS + 1)
    return dict(rho=obs, p=pval, lo=np.percentile(boot, 2.5), hi=np.percentile(boot, 97.5), n=len(p))


def required_edge_table(mk):
    rows = []
    later = mk.era_mask["LATER"]
    price = float(np.median(mk.o[later]))
    cost_bp = COST_USD / price * 1e4
    for H in HORIZONS:
        i = valid_idx(mk, "LATER", H, np.zeros(mk.n))
        s = float(np.std(mk.fwd[H][i]))
        for N in (250, 1000, 2500):
            for S in (1.0, 2.0):
                r = S / math.sqrt(N)
                rows.append({"hold": f"{H * 15} min", "trades/yr": N, "target Sharpe": S,
                             "per-trade SD (bp)": round(s, 1), "net edge needed (bp)": round(r * s, 2),
                             "gross edge needed (bp)": round(r * s + cost_bp, 2),
                             "win rate (symmetric)": round(0.5 + 0.4 * r, 4),
                             "rank corr needed": round(r / 0.8, 3),
                             "trades to detect": int((2.8 / r) ** 2),
                             "years to detect": round((2.8 / r) ** 2 / N, 1)})
    return pd.DataFrame(rows), cost_bp


def main() -> int:
    os.chdir(ROOT)
    mk = Market()
    feats = build_features(mk)
    req, cost_bp = required_edge_table(mk)
    print(f"round-trip cost at 2024-26 prices = {cost_bp:.2f} bp\n")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print("PART 1 — what an edge must look like")
    print(req.to_string(index=False))

    rows = []
    for kind in ("dir", "mag"):
        for H in HORIZONS:
            for name, x in feats.items():
                a = transfer(mk, name, x, kind, H, "DEV", "LATER")
                b = transfer(mk, name, x, kind, H, "LATER", "DEV")
                if a is None or b is None:
                    continue
                rows.append(dict(target=kind, H_bars=H, feature=name,
                                 rho_DEV_to_LATER=a["rho"], p_fwd=a["p"], ci_lo=a["lo"], ci_hi=a["hi"],
                                 rho_LATER_to_DEV=b["rho"], p_back=b["p"], n=a["n"]))
    R = pd.DataFrame(rows)
    d = R[R.target == "dir"].copy()
    d["LEAD"] = ((d.p_fwd < ALPHA) & (d.p_back < 0.05) & (np.sign(d.rho_DEV_to_LATER) == np.sign(d.rho_LATER_to_DEV)))
    m = R[R.target == "mag"].copy()
    with pd.ExcelWriter(OUT) as xw:
        req.to_excel(xw, sheet_name="required edge", index=False)
        d.to_excel(xw, sheet_name="direction", index=False)
        m.to_excel(xw, sheet_name="magnitude", index=False)

    print(f"\nPART 2a — DIRECTION (30 primary tests, alpha={ALPHA:.5f}); sorted by |rho|")
    show = d.reindex(d.rho_DEV_to_LATER.abs().sort_values(ascending=False).index).head(10)
    print(show[["feature", "H_bars", "rho_DEV_to_LATER", "p_fwd", "rho_LATER_to_DEV", "p_back", "LEAD"]].round(4).to_string(index=False))
    print(f"direction leads: {int(d.LEAD.sum())}/30;  largest |rho| = {d.rho_DEV_to_LATER.abs().max():.4f}")

    print("\nPART 2b — MAGNITUDE (descriptive); sorted by rho")
    mm = m.reindex(m.rho_DEV_to_LATER.sort_values(ascending=False).index).head(12)
    print(mm[["feature", "H_bars", "rho_DEV_to_LATER", "p_fwd", "rho_LATER_to_DEV"]].round(3).to_string(index=False))
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
