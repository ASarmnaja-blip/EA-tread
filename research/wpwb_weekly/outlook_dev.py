"""WPWB Outlook v2 — development run (docs/WPWB_OUTLOOK_V2_PREREG.md).
Read-only. Usage:
  python research/wpwb_weekly/outlook_dev.py --tests   self-tests only (no score printed)
  python research/wpwb_weekly/outlook_dev.py           vendor audit + self-tests + full development run
Index convention as regime_atlas: cuts[k] starts week k = (cuts[k], cuts[k] + 7 d]."""
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
sys.path.insert(0, str(ROOT / "research" / "pilot"))
sys.path.insert(0, str(ROOT / "research" / "history"))
import vol as V  # noqa: E402
from regime_atlas import load  # noqa: E402

WEEK = 7 * 86400
MIN_ROWS = 104
MIN_POOL = 52
MIN_Y3 = 104
COND_MAX = 1e6
EDGES = (0.75, 1.5, 2.5)
THETAS = (100.0, 200.0, 300.0)
B_REPS = 2000
RNG = np.random.default_rng(20260930)
MODELS = ("B0", "B1", "HAR", "MVOL", "MVOL+S1")
CORE = ("B0", "B1", "HAR", "MVOL")
PERIODS = {"D1": ("2000-01-01", "2019-01-01"), "PH": ("2019-01-01", "2021-07-01"),
           "D2": ("2021-07-01", "2027-01-01"), "ALL": ("2000-01-01", "2027-01-01")}
OUT = ROOT / "data" / "wpwb_outlook_v2_dev.xlsx"


# ------------------------------------------------------------------ inputs
def gvz_series(drop=None):
    g = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
    if drop is not None:
        g = g[~g.d.between(*drop)]
    return g.d.astype("datetime64[s]").astype(np.int64).to_numpy(), g.GVZ.astype(float).to_numpy()


def weekly(t, c, hi, lo, cuts):
    rv_raw, rng, ret, nbar = V.weekly_rv(t, c, hi, lo, cuts)
    return V.mask_invalid(rv_raw, nbar)


def features(t, c, hi, lo, cuts, rv, gd, gv):
    n = len(cuts)
    lv = np.log(rv)
    L1, L4, L26, G, S1 = (np.full(n, np.nan) for _ in range(5))
    close_t = t + 3600
    for k in range(26, n):
        w = lv[k - 26:k]
        if np.isfinite(w).all():
            L1[k], L4[k], L26[k] = w[-1], w[-4:].mean(), w.mean()
        cut = int(cuts[k])
        j = np.searchsorted(gd, cut - 86400, side="right") - 1
        if j >= 0 and gd[j] > cut - 7 * 86400:
            G[k] = math.log((gv[j] / 100) ** 2 / 52 * 1e8)
        pos = np.searchsorted(close_t, cut, side="right") - 1
        lo_i = np.searchsorted(close_t, cut - 52 * WEEK, side="right")
        if pos - lo_i > 1000:
            S1[k] = math.log(c[pos] / hi[lo_i:pos + 1].max())
    return dict(L1=L1, L4=L4, L26=L26, G=G, S1=S1)


# ------------------------------------------------------------------ models
def ols_prequential(X, y):
    """mu[k] from OLS on rows j < k with complete X and valid y (>= MIN_ROWS)."""
    n = len(y)
    mu = np.full(n, np.nan)
    nocond = 0
    okx = np.isfinite(X).all(1)
    oky = np.isfinite(y)
    for k in range(n):
        if not okx[k]:
            continue
        rows = np.flatnonzero(okx[:k] & oky[:k])
        if len(rows) < MIN_ROWS:
            continue
        A = X[rows]
        if np.linalg.cond(A) > COND_MAX:
            nocond += 1
            continue
        beta = np.linalg.lstsq(A, y[rows], rcond=None)[0]
        mu[k] = float(X[k] @ beta)
    return mu, nocond


def point_models(rv, F):
    lv = np.log(rv)
    n = len(rv)
    one = np.ones(n)
    har_X = np.c_[one, F["L1"], F["L4"], F["L26"]]
    mv_X = np.c_[har_X, F["G"]]
    s1_X = np.c_[mv_X, F["S1"]]
    mu, cond = {}, {}
    f = V.ewma_forecast(rv)
    mu["B0"] = np.where(np.isfinite(f) & (f > 0), np.log(np.where(f > 0, f, 1)), np.nan)
    mu["HAR"], cond["HAR"] = ols_prequential(har_X, lv)
    mu["MVOL"], cond["MVOL"] = ols_prequential(mv_X, lv)
    mu["MVOL+S1"], cond["MVOL+S1"] = ols_prequential(s1_X, lv)
    return mu, cond


def ensembles(rv, mu):
    """ens[m][k] = array of predictive log-RV draws, or None."""
    lv = np.log(rv)
    n = len(rv)
    ens = {}
    for m, x in mu.items():
        res, e = [], [None] * n
        for k in range(n):
            if np.isfinite(x[k]) and len(res) >= MIN_POOL:
                e[k] = x[k] + np.asarray(res)
            if np.isfinite(x[k]) and np.isfinite(lv[k]):
                res.append(lv[k] - x[k])
        ens[m] = e
    e, hist = [None] * n, []
    for k in range(n):
        if len(hist) >= 52:
            e[k] = np.asarray(hist[-52:])
        if np.isfinite(lv[k]):
            hist.append(lv[k])
    ens["B1"] = e
    return ens


# ------------------------------------------------------------------ targets
def med52(rv):
    m = np.full(len(rv), np.nan)
    for k in range(len(rv)):
        w = rv[:k][np.isfinite(rv[:k])]
        if len(w) >= 52:
            m[k] = np.median(w[-52:])
    return m


def cls(ratio):
    return np.where(np.isfinite(ratio), np.searchsorted(EDGES, ratio, side="right"), -1)


def y3_series(h, t, cuts):
    close_t = t + 3600
    ao, bo = h.ao.to_numpy(float), h.o.to_numpy(float)
    bl, ah = h.l.to_numpy(float), h.ah.to_numpy(float)
    y = np.full(len(cuts), np.nan)
    for k, a in enumerate(cuts):
        i0 = np.searchsorted(close_t, a, side="right")
        i1 = np.searchsorted(close_t, a + WEEK, side="right")
        if i1 - i0 < 80:
            continue
        long_adv = (ao[i0] - bl[i0:i1].min()) / ao[i0] * 1e4
        short_adv = (ah[i0:i1].max() - bo[i0]) / bo[i0] * 1e4
        y[k] = max(long_adv, short_adv)
    return y


# ------------------------------------------------------------------ scoring
def crps(x, y):
    x = np.sort(x)
    n = len(x)
    i = np.arange(1, n + 1)
    return float(np.mean(np.abs(x - y)) - (2 * i - n - 1) @ x / n ** 2)


def score(rv, ens, y3, mk, years_idx):
    lv = np.log(rv)
    n = len(rv)
    ratio_now = rv / mk
    c_now = cls(ratio_now)
    c_prev = np.r_[-1, c_now[:-1]]
    rows = []
    fpt = {}
    for m, E in ens.items():
        fpt[m] = np.array([np.mean(np.exp(e)) if e is not None else np.nan for e in E])
    for m, E in ens.items():
        # Y3 ratio pool uses the model's own past point variance
        r3 = []
        for k in range(n):
            e = E[k]
            rec = dict(k=k, model=m)
            if e is not None and np.isfinite(lv[k]) and np.isfinite(mk[k]):
                y = lv[k]
                F_ = fpt[m][k]
                rec.update(crps=crps(e, y), qlike=rv[k] / F_ - math.log(rv[k] / F_) - 1,
                           pit=float(np.mean(e <= y)),
                           in80=float(np.quantile(e, .1) <= y <= np.quantile(e, .9)),
                           in95=float(np.quantile(e, .025) <= y <= np.quantile(e, .975)))
                lm = math.log(mk[k])
                cdf = [np.mean(e < lm + math.log(q)) for q in EDGES]
                obs = [float(c_now[k] <= j) for j in range(3)]
                rec["rps"] = float(sum((a - b) ** 2 for a, b in zip(cdf, obs)) / 3)
                p_hi = float(np.mean(e >= lm + math.log(1.5)))
                if c_prev[k] in (0, 1):
                    rec.update(on_p=p_hi, on_y=float(c_now[k] >= 2))
                elif c_prev[k] in (2, 3):
                    rec.update(off_p=1 - p_hi, off_y=float(c_now[k] < 2))
                if np.isfinite(y3[k]) and len(r3) >= MIN_Y3:
                    rr = np.asarray(r3)
                    for th in THETAS:
                        p = float(np.mean(rr > th / math.sqrt(F_)))
                        rec[f"y3_{int(th)}"] = (p - float(y3[k] > th)) ** 2
            if e is not None and np.isfinite(y3[k]) and np.isfinite(lv[k]):
                r3.append(y3[k] / math.sqrt(fpt[m][k]))
            rows.append(rec)
    return pd.DataFrame(rows)


def block_ci(d, block=8):
    d = np.asarray(d, float)
    n = len(d)
    if n < 2 * block:
        return np.nan, np.nan
    nb = int(math.ceil(n / block))
    st = RNG.integers(0, n, (B_REPS, nb))
    idx = (st[:, :, None] + np.arange(block)) % n
    means = d[idx.reshape(B_REPS, -1)[:, :n]].mean(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def alarm_stats(p, y):
    a = np.zeros(len(p), bool)
    for i in range(len(p)):
        if i >= 50 and p[i] > np.quantile(p[:i], 0.8):
            a[i] = True
    tp = int((a & (y == 1)).sum()); fp = int((a & (y == 0)).sum()); fn = int((~a & (y == 1)).sum())
    tn = int((~a & (y == 0)).sum())
    return dict(alarms=tp + fp, precision=tp / (tp + fp) if tp + fp else np.nan, base=float(y.mean()),
                sensitivity=tp / (tp + fn) if tp + fn else np.nan, FPR=fp / (fp + tn) if fp + tn else np.nan)


# ------------------------------------------------------------------ pipeline
def run_models(h, t, cuts, gdrop=None, gvz_override=None):
    c, hi, lo = (h[k].to_numpy(float) for k in ("c", "h", "l"))
    rv = weekly(t, c, hi, lo, cuts)
    gd, gv = gvz_series(gdrop)
    F = features(t, c, hi, lo, cuts, rv, gd, gv)
    if gvz_override is not None:
        F["G"] = gvz_override
    mu, cond = point_models(rv, F)
    return rv, F, mu, cond


def self_tests(h, t, cuts):
    rv, F, mu, _ = run_models(h, t, cuts)
    ens = ensembles(rv, mu)
    ok_all = True
    ks = RNG.choice(np.arange(400, len(cuts) - 5), 3, replace=False)
    for k in ks:
        g = h.copy()
        late = (t + 3600) > cuts[k]
        noise = RNG.uniform(0.5, 2.0, late.sum())
        for col in ("o", "h", "l", "c", "ao", "ah", "al", "ac"):
            g.loc[g.index[late], col] = g[col].to_numpy()[late] * noise
        rv2, F2, mu2, _ = run_models(g, t, cuts)
        ens2 = ensembles(rv2, mu2)
        same = all((np.isnan(mu[m][k]) and np.isnan(mu2[m][k])) or abs(mu[m][k] - mu2[m][k]) < 1e-12 for m in mu)
        same &= all((ens[m][k] is None and ens2[m][k] is None) or np.allclose(ens[m][k], ens2[m][k]) for m in ens)
        print(f"  future-garbage at cut {pd.to_datetime(cuts[k], unit='s'):%Y-%m-%d}: {'unchanged' if same else 'CHANGED'}")
        ok_all &= same
    k0 = int(np.flatnonzero(np.isfinite(mu["MVOL"]))[200])
    cut0 = int(cuts[k0])
    drop = (pd.Timestamp(cut0 - 8 * 86400, unit="s"), pd.Timestamp(cut0, unit="s"))
    _, _, mu3, _ = run_models(h, t, cuts, gdrop=drop)
    same_other = all(np.array_equal(mu[m], mu3[m], equal_nan=True) for m in ("B0", "HAR"))
    same_before = np.array_equal(mu["MVOL"][:k0], mu3["MVOL"][:k0], equal_nan=True)
    gone = np.isnan(mu3["MVOL"][k0])
    print(f"  missing-GVZ week {pd.Timestamp(cut0, unit='s'):%Y-%m-%d}: B0/HAR unchanged {same_other}, "
          f"MVOL before unchanged {same_before}, MVOL that week removed {gone}")
    ok_all &= same_other and same_before and gone
    return ok_all


def synthetic_null(h, t, cuts, rv, F, mu, ens_real, scored_mask, nser=20):
    lv = np.log(rv)
    har_c = np.array([crps(ens_real["HAR"][k], lv[k]) if scored_mask[k] else np.nan for k in range(len(rv))])
    below = 0
    n = len(rv)
    for _ in range(nser):
        z = np.zeros(n); e = RNG.normal(size=n)
        for i in range(1, n):
            z[i] = 0.9 * z[i - 1] + e[i]
        z = np.where(np.isfinite(F["G"]), z, np.nan)
        X = np.c_[np.ones(n), F["L1"], F["L4"], F["L26"], z]
        m_syn, _ = ols_prequential(X, lv)
        E = ensembles(rv, {"SYN": m_syn})["SYN"]
        d = [crps(E[k], lv[k]) - har_c[k] for k in range(n) if scored_mask[k] and E[k] is not None]
        lo_, hi_ = block_ci(d)
        below += int(hi_ < 0)
    return below, nser


def vendor_audit(cuts_d, rv_d):
    import bars as BR
    b5 = BR.load_bars(frozen=False)
    m = BR.market(b5)
    lo_c = int(np.datetime64("2021-07-02T22:15:00", "s").astype(np.int64))
    hi_c = int(np.datetime64("2026-08-21T22:15:00", "s").astype(np.int64))
    sel = (cuts_d >= lo_c) & (cuts_d <= hi_c)
    cuts = cuts_d[sel]
    rv_e = weekly(np.asarray(m.t), np.asarray(m.c), np.asarray(m.h), np.asarray(m.l), cuts)
    rv_dd = rv_d[sel]
    # class labels, each vendor with its own m_k (needs 52 prior weeks inside each series)
    md = med52(rv_d)[sel]
    me_full = med52(rv_e)
    ok = np.isfinite(rv_e) & np.isfinite(rv_dd)
    ok2 = ok & np.isfinite(me_full) & np.isfinite(md)
    from scipy.stats import spearmanr
    sp = float(spearmanr(rv_e[ok], rv_dd[ok]).statistic)
    ml = float(np.median(np.abs(np.log(rv_e[ok] / rv_dd[ok]))))
    agree = float(np.mean(cls(rv_e[ok2] / me_full[ok2]) == cls(rv_dd[ok2] / md[ok2])))
    bias = float(np.median(np.log(rv_e[ok] / rv_dd[ok])))
    passed = sp >= 0.95 and ml <= 0.10 and agree >= 0.85
    return dict(weeks=int(ok.sum()), class_weeks=int(ok2.sum()), spearman=sp, median_abs_log_ratio=ml,
                median_log_ratio=bias, class_agreement=agree, passed=passed)


def main() -> int:
    os.chdir(ROOT)
    h, t, cuts, *_ = load()
    print(f"H1 {len(t):,} bars {pd.to_datetime(t[0], unit='s'):%Y-%m-%d}..{pd.to_datetime(t[-1], unit='s'):%Y-%m-%d}; cuts {len(cuts)}")
    print("self-tests:")
    ok = self_tests(h, t, cuts)
    print(f"self-tests {'PASSED' if ok else 'FAILED'}")
    if "--tests" in sys.argv or not ok:
        return 0 if ok else 1
    rv, F, mu, cond = run_models(h, t, cuts)
    print("\nvendor audit (Dukascopy vs Exness H1, 2021-07-02..2026-08-21):")
    va = vendor_audit(cuts, rv)
    print("  " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in va.items()))
    ens = ensembles(rv, mu)
    mk = med52(rv)
    y3 = y3_series(h, t, cuts)
    S = score(rv, ens, y3, mk, None)
    date = pd.to_datetime(cuts, unit="s")
    S["date"] = date[S.k.to_numpy()]
    have = S.dropna(subset=["crps"]).groupby("k").model.apply(set)
    common = np.array([k for k, s in have.items() if set(CORE) <= s])
    scored = np.zeros(len(cuts), bool); scored[common] = True
    print(f"\nscored weeks (all core models issued, target valid): {len(common)}, "
          f"{date[common[0]]:%Y-%m-%d}..{date[common[-1]]:%Y-%m-%d}")
    print("weeks with no forecast because condition number > 1e6: " + ", ".join(f"{k} {v}" for k, v in cond.items()))
    Sc = S[S.k.isin(common)].copy()
    per = []
    for pn, (a, b) in PERIODS.items():
        m_ = (Sc.date >= a) & (Sc.date < b)
        for mdl in MODELS:
            x = Sc[m_ & (Sc.model == mdl)]
            if not len(x):
                continue
            row = dict(period=pn, model=mdl, weeks=len(x), CRPS=x.crps.mean(), QLIKE=x.qlike.mean(), RPS=x.rps.mean(),
                       cover80=x.in80.mean(), cover95=x.in95.mean(),
                       onset_Brier=((x.on_p - x.on_y) ** 2).mean(), exit_Brier=((x.off_p - x.off_y) ** 2).mean(),
                       **{f"Y3_{int(th)}": x[f"y3_{int(th)}"].mean() for th in THETAS})
            per.append(row)
    P = pd.DataFrame(per)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print("\nmean scores (lower is better except coverage; nominal 0.80 / 0.95)")
    print(P.round(4).to_string(index=False))
    comps = [("MVOL", "B0"), ("HAR", "B0"), ("MVOL", "HAR"), ("B1", "B0"), ("MVOL+S1", "MVOL")]
    metrics = ("crps", "qlike", "rps", "onset", "exit", "y3_100", "y3_200", "y3_300")
    D = []
    piv = {}
    for mt in metrics:
        if mt in ("onset", "exit"):
            pcol, ycol = ("on_p", "on_y") if mt == "onset" else ("off_p", "off_y")
            v = Sc.assign(val=(Sc[pcol] - Sc[ycol]) ** 2)
        else:
            v = Sc.assign(val=Sc[mt])
        piv[mt] = v.pivot_table(index="k", columns="model", values="val")
    for pn, (a, b) in PERIODS.items():
        for x_, y_ in comps:
            for mt in metrics:
                pv = piv[mt]
                if x_ not in pv or y_ not in pv:
                    continue
                dd = (pv[x_] - pv[y_]).dropna()
                dts = date[dd.index.to_numpy()]
                dd = dd[(dts >= a) & (dts < b)]
                if len(dd) < 20:
                    continue
                lo8, hi8 = block_ci(dd.to_numpy(), 8)
                lo26, hi26 = block_ci(dd.to_numpy(), 26)
                base = pv[y_].reindex(dd.index).mean()
                D.append(dict(period=pn, compare=f"{x_} - {y_}", metric=mt, weeks=len(dd), mean_diff=dd.mean(),
                              pct_of_base=100 * dd.mean() / base if base else np.nan,
                              lo8=lo8, hi8=hi8, lo26=lo26, hi26=hi26))
    D = pd.DataFrame(D)
    print("\npaired differences (negative = first model better); 95% circular moving-block intervals, block 8 and 26")
    print(D[D.metric.isin(["crps", "qlike", "rps", "onset", "exit"])].round(4).to_string(index=False))
    print("\nY3 worse-side H1 quote-touch Brier differences (theta = 100/200/300 bp)")
    print(D[D.metric.str.startswith("y3")].round(5).to_string(index=False))
    A = []
    for pn, (a, b) in PERIODS.items():
        for mdl in CORE:
            for tgt, pc, yc in (("onset", "on_p", "on_y"), ("exit", "off_p", "off_y")):
                x = Sc[(Sc.model == mdl) & Sc[pc].notna() & (Sc.date >= a) & (Sc.date < b)].sort_values("k")
                if len(x) >= 60:
                    A.append(dict(period=pn, model=mdl, target=tgt, weeks=len(x),
                                  **alarm_stats(x[pc].to_numpy(), x[yc].to_numpy())))
    A = pd.DataFrame(A)
    print("\nalarms (causal top 20% of the model's own past probabilities)")
    print(A[A.period == "ALL"].round(3).to_string(index=False))
    pit = Sc.groupby("model").pit.apply(lambda s: np.histogram(s, bins=10, range=(0, 1))[0] / len(s))
    print("\nPIT histogram shares per decile (uniform = 0.10 each)")
    for mdl, hh in pit.items():
        print(f"  {mdl:8s} " + " ".join(f"{v:.3f}" for v in hh))
    # last-cut MVOL coefficients (descriptive)
    n = len(rv); lv = np.log(rv)
    X = np.c_[np.ones(n), F["L1"], F["L4"], F["L26"], F["G"]]
    okr = np.isfinite(X).all(1) & np.isfinite(lv)
    beta = np.linalg.lstsq(X[okr], lv[okr], rcond=None)[0]
    print("\nMVOL coefficients on all valid rows (const, L1, L4, L26, G): " + ", ".join(f"{b:.3f}" for b in beta))
    below, ns = synthetic_null(h, t, cuts, rv, F, mu, ens, scored)
    print(f"\nsynthetic null: {below}/{ns} random-G MVOL-HAR CRPS intervals entirely below 0 (expected ~2.5% each)")
    with pd.ExcelWriter(OUT) as xw:
        pd.DataFrame({"README": ["DEVELOPMENT ONLY (docs/WPWB_OUTLOOK_V2_PREREG.md). No superiority claim; no model replaces B0; nothing changes vol_scale.",
                                 "Y3 is an H1 quote-touch excursion, not a stop-hit probability; only the worse side is shown."]}
                     ).to_excel(xw, sheet_name="README", index=False)
        pd.DataFrame([va]).to_excel(xw, sheet_name="vendor audit", index=False)
        P.to_excel(xw, sheet_name="mean scores", index=False)
        D.to_excel(xw, sheet_name="paired diffs", index=False)
        A.to_excel(xw, sheet_name="alarms", index=False)
        S.to_excel(xw, sheet_name="weekly scores", index=False)
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
