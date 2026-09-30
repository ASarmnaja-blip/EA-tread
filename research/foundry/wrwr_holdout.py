"""M5/M15 unseen-history holdout (registered in FOUNDRY_LEDGER 2026-09-30 before running): the four fixed WRWR
selector settings, evaluated on HistData 2009-03..2020-12 (never used) and, for comparison, on 2021-01..2026-08
(where they were chosen). Writes data/foundry/wrwr_holdout.xlsx. Descriptive; no orders."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import vol as V  # noqa: E402


def load(files):
    parts = []
    for tf, f in files:
        z = np.load(E.ROOT / "data" / "foundry" / f, allow_pickle=True)
        parts.append((pd.DataFrame(z["cands"].tolist()).assign(tf=tf), *(z[x] for x in ("S1", "S2", "NN", "E1", "EN"))))
    return pd.concat([p[0] for p in parts], ignore_index=True), *(np.vstack([p[i] for p in parts]) for i in range(1, 6))


H, _, cuts, cell = E.load()
NW = len(cuts)
rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
rv = V.mask_invalid(rv_raw, nb); F = V.ewma_forecast(rv)
scale = np.full(NW, V.SCALE_MIN)
for k in range(1, NW):
    scale[k] = V.effective_scale(V.vol_scale(F[k]), V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
wkdate = pd.to_datetime(cuts, unit="s")


def run(pool, L, zz, m, sized, eqf, minn=10):
    C, S1, S2, NN, E1, EN = pool
    weeks = np.arange(60, NW - 1)
    weeks = weeks[(cell[weeks] != "") & (EN[:, weeks].sum(0) > 0)]
    cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]
    cS1, cS2, cN = cum(S1), cum(S2), cum(NN)
    a = np.maximum(weeks - L, 0)
    s1, s2, n = cS1[:, weeks] - cS1[:, a], cS2[:, weeks] - cS2[:, a], cN[:, weeks] - cN[:, a]
    mu = s1 / np.maximum(n, 1); var = (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1)
    sc = np.where(n >= minn, mu - zz * np.sqrt(np.maximum(var, 0) / np.maximum(n, 1)), -np.inf)
    idx = np.argsort(-sc, axis=0)[:m]; cols = np.arange(len(weeks))
    R = np.zeros(len(weeks)); T = np.zeros(len(weeks))
    for j in range(m):
        ok = sc[idx[j], cols] > 0
        R += np.where(ok, E1[idx[j], weeks], 0.0); T += np.where(ok, EN[idx[j], weeks], 0.0)
    if eqf:
        c_ = np.r_[0.0, np.cumsum(R)]; live = (c_[cols] - c_[np.maximum(cols - eqf, 0)]) > 0
        R, T = np.where(live, R, 0.0), np.where(live, T, 0.0)
    if sized:
        R = R * scale[weeks]
    return wkdate[weeks], R, T


def metrics(d, R, T, a, b):
    m = (d >= a) & (d < b); r = R[m]; yrs = m.sum() / 52.18
    eq = np.cumprod(np.maximum(1 + 0.01 * r, 1e-9)); blocks = r[: len(r) // 52 * 52].reshape(-1, 52).sum(1)
    return dict(net_R=r.sum(), trades=T[m].sum(), R_per_year=r.sum() / yrs, R_per_trade=r.sum() / max(T[m].sum(), 1),
                pos_blocks=f"{int((blocks > 0).sum())}/{len(blocks)}", CAGR_1pct=eq[-1] ** (1 / yrs) - 1,
                maxDD_1pct=float((1 - eq / np.maximum.accumulate(eq)).max()))


M5 = load([("M5", "wpwb_walkforward_cache_M5L.npz")]); M15 = load([("M15", "wpwb_walkforward_cache_M15L.npz")])
M15H1 = load([("M15", "wpwb_walkforward_cache_M15L.npz"), ("H1", "wpwb_walkforward_cache.npz")])
SETTINGS = [("(a) pre-registered 52w LCB z1 top2 sized", "M5", M5, (52, 1.0, 2, True, 0)),
            ("(a) pre-registered 52w LCB z1 top2 sized", "M15", M15, (52, 1.0, 2, True, 0)),
            ("(b) M5 best-compounding 78w z1 top1 sized", "M5", M5, (78, 1.0, 1, True, 0)),
            ("(c) M15 best-compounding 78w z1 top5 eq26", "M15", M15, (78, 1.0, 5, False, 26)),
            ("(d) M15+H1 52w z2 top8 eq13", "M15+H1", M15H1, (52, 2.0, 8, False, 13))]
rows = []
for name, pool_name, pool, (L, zz, m, sz, eqf) in SETTINGS:
    d, R, T = run(pool, L, zz, m, sz, eqf)
    for per, a, b in (("HOLDOUT 2009-03..2020-12 (unseen)", "2009-03-01", "2021-01-01"), ("chosen on 2021-01..2026-08", "2021-01-01", "2026-09-01")):
        rows.append(dict(setting=name, pool=pool_name, period=per, **metrics(d, R, T, pd.Timestamp(a), pd.Timestamp(b))))
X = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(X.round(3).to_string(index=False))
X.to_excel(E.ROOT / "data" / "foundry" / "wrwr_holdout.xlsx", index=False)
