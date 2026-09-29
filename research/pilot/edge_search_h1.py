"""Long-history H1 edge search on Dukascopy 2003-2015.
See docs/H1_LONG_HISTORY_PREREG.md (committed before this ran on real data).
Read-only.  Usage:  python research/pilot/edge_search_h1.py [--smoke]
--smoke uses two early pseudo-eras and prints COUNTS ONLY (no effect sizes), to
check the pipeline runs without looking at any result."""
from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research" / "history"))
import core  # noqa: E402
import data as D  # noqa: E402
import mtf_engine as E  # noqa: E402
from build_all_tf import load_kind  # noqa: E402

SMOKE = "--smoke" in sys.argv
HORIZONS = (1, 4)
if SMOKE:
    ERAS = {"DEV": ("2003-05-05", "2008-01-01"), "CONF": ("2008-01-01", "2011-01-01")}
    B_REPS = 200
else:
    ERAS = {"DEV": ("2003-05-05", "2013-01-01"), "CONF": ("2013-01-01", "2016-01-01")}
    B_REPS = 10000
N_TESTS = 54
ALPHA = 0.05 / N_TESTS
COST_BP = 0.80
STEP = 3600
WEEK = 7 * 86400
TOP_PCT = 66.7
OUT = ROOT / "data" / ("edge_search_h1_smoke.xlsx" if SMOKE else "edge_search_h1.xlsx")
RNG = np.random.default_rng(20260929)
CATEGORICAL = ("hour_utc", "weekday", "session")


class H1:
    def __init__(self):
        df = load_kind("hour")
        assert df is not None, "hourly cache missing"
        df = df[df.index < "2016-01-01"]
        self.t = df.index.astype("datetime64[s]").astype(np.int64).to_numpy()
        self.o, self.h, self.l, self.cl = (df[k].to_numpy(float) for k in ("o", "h", "l", "c"))
        self.n = len(self.t)
        self.sha = hashlib.sha256(np.stack([self.t.astype(float), self.o, self.h, self.l, self.cl]).tobytes()).hexdigest()
        bars = D.Bars(self.t, self.o, self.h, self.l, self.cl, df["v"].to_numpy(float), STEP, "XAUUSD")
        self.c = core.Ctx(bars, np.arange(self.n) + 1)
        self.dt = df.index
        self.pct = np.asarray(self.c.atr_pct, float)
        dec = np.where(np.isfinite(self.pct), np.minimum((self.pct // 10).astype(float), 9), np.nan)
        sess = pd.factorize(np.asarray(self.c.session))[0].astype(float)
        self.bin = np.where(np.isfinite(dec), dec * 10 + sess, np.nan)
        self.era_mask = {k: np.asarray((self.dt >= a) & (self.dt < b)) for k, (a, b) in ERAS.items()}
        self.fwd, self.ok = {}, {}
        for H in HORIZONS:
            f = np.full(self.n, np.nan); good = np.zeros(self.n, bool)
            i = np.arange(self.n - H - 1)
            ent, ext = i + 1, i + H
            contig = (self.t[ext] - self.t[ent]) == (H - 1) * STEP
            step_ok = (self.t[ent] - self.t[i]) == STEP
            k0 = np.floor((self.t[ent] - 75600) / 86400)
            k1 = np.floor((self.t[ext] + STEP - 1 - 75600) / 86400)
            f[i] = (self.cl[ext] / self.o[ent] - 1) * 1e4
            good[i] = contig & step_ok & (k0 == k1)
            self.fwd[H], self.ok[H] = f, good
        self.bin_mean = {}
        for era, em in self.era_mask.items():
            for H in HORIZONS:
                m = em & self.ok[H] & np.isfinite(self.bin) & (np.arange(self.n) >= self.c.warm)
                self.bin_mean[(era, H)] = pd.Series(self.fwd[H][m]).groupby(self.bin[m]).mean().to_dict()

    def signals(self, fam):
        return sorted((int(i), int(d)) for i, d in E.setup_signals(fam, self.c))


def evaluate(mk, sigs, era, H, top_only=False, plant=0.0, reps=None):
    reps = reps or B_REPS
    em, bm = mk.era_mask[era], mk.bin_mean[(era, H)]
    kept, last = [], -10 ** 9
    for i, d in sigs:
        if i < mk.c.warm or i + H + 1 >= mk.n or not em[i] or not em[i + H] or not mk.ok[H][i]:
            continue
        if not np.isfinite(mk.pct[i]) or (top_only and mk.pct[i] < TOP_PCT):
            continue
        if i < last + H:
            continue
        b = mk.bin[i]
        if b not in bm:
            continue
        kept.append((i, d, bm[b]))
        last = i
    if len(kept) < 30:
        return dict(n=len(kept), net=np.nan, diff=np.nan, p=np.nan, lo=np.nan, hi=np.nan)
    ii = np.array([k[0] for k in kept]); dd = np.array([k[1] for k in kept], float)
    mb = np.array([k[2] for k in kept])
    r = dd * mk.fwd[H][ii] + plant
    diff = r - dd * mb
    net = r - COST_BP
    uw, inv = np.unique(mk.t[ii] // WEEK, return_inverse=True)
    sd = np.bincount(inv, weights=diff); cn = np.bincount(inv).astype(float)
    obs = sd.sum() / cn.sum()
    ix = RNG.integers(0, len(uw), (reps, len(uw)))
    means = sd[ix].sum(1) / cn[ix].sum(1)
    dev = means - means.mean()
    return dict(n=len(kept), net=float(net.mean()), diff=float(obs),
                p=float((np.sum(np.abs(dev) >= abs(obs)) + 1) / (reps + 1)),
                lo=float(np.percentile(means, 2.5)), hi=float(np.percentile(means, 97.5)))


def shift(a, k):
    out = np.full(len(a), np.nan)
    out[k:] = a[:-k]
    return out


def features(mk):
    c, cl = mk.c, mk.cl
    atr = np.asarray(c.atr, float)

    def dist(x):
        return (cl - np.asarray(x, float)) / atr
    path = pd.Series(np.abs(np.diff(cl, prepend=np.nan))).rolling(20).sum().to_numpy()
    return {
        "atr_pct": mk.pct, "dist_vwap_atr": dist(c.vwap), "dist_ema50_atr": dist(c.ema50),
        "dist_ema200_atr": dist(c.ema200), "dist_hh20_atr": dist(c.hh20), "dist_ll20_atr": dist(c.ll20),
        "ret1_atr": (cl - shift(cl, 1)) / atr, "ret4_atr": (cl - shift(cl, 4)) / atr,
        "ret16_atr": (cl - shift(cl, 16)) / atr, "range_ratio": (mk.h - mk.l) / atr,
        "efficiency20": np.abs(cl - shift(cl, 20)) / path, "trend_sep": np.asarray(c.sep, float),
        "hour_utc": mk.dt.hour.to_numpy().astype(float), "weekday": mk.dt.weekday.to_numpy().astype(float),
        "session": pd.factorize(np.asarray(c.session))[0].astype(float)}


def valid_idx(mk, era, H, x):
    m = mk.era_mask[era] & mk.ok[H] & np.isfinite(mk.fwd[H]) & np.isfinite(x) & (np.arange(mk.n) >= mk.c.warm)
    return np.flatnonzero(m)


def transfer(mk, name, x, H, train, test, reps=None):
    reps = reps or B_REPS
    it, ie = valid_idx(mk, train, H, x), valid_idx(mk, test, H, x)
    if len(it) < 500 or len(ie) < 300:
        return None
    if name in CATEGORICAL:
        bn = lambda v: v  # noqa: E731
    else:
        edges = np.unique(np.quantile(x[it], np.linspace(0.1, 0.9, 9)))
        bn = lambda v: np.searchsorted(edges, v)  # noqa: E731
    ytr = mk.fwd[H][it] - mk.fwd[H][it].mean()
    means = pd.Series(ytr).groupby(bn(x[it])).mean()
    p = means.reindex(bn(x[ie])).to_numpy()
    y = mk.fwd[H][ie] - mk.fwd[H][ie].mean()
    good = np.isfinite(p)
    p, y, wk = p[good], y[good], mk.t[ie][good] // WEEK
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
    return dict(rho=obs, p=(np.sum(np.abs(dev) >= abs(obs)) + 1) / (reps + 1), n=len(p),
                sd=float(np.std(mk.fwd[H][ie])))


def self_check(mk):
    era, H = "DEV", 1
    pool = np.flatnonzero(mk.era_mask[era] & mk.ok[H] & np.isfinite(mk.bin) & (np.arange(mk.n) >= mk.c.warm))
    k = min(2000, len(pool) // 2)
    rej0 = rej1 = 0
    for _ in range(100):
        idx = np.sort(RNG.choice(pool, k, replace=False))
        sigs = [(int(i), int(RNG.choice([-1, 1]))) for i in idx]
        rej0 += evaluate(mk, sigs, era, H, reps=500)["p"] < 0.05
        rej1 += evaluate(mk, sigs, era, H, plant=3.0, reps=500)["p"] < 0.05
    return rej0 / 100, rej1 / 100


def main() -> int:
    os.chdir(ROOT)
    mk = H1()
    dv, cf = mk.era_mask["DEV"], mk.era_mask["CONF"]
    print(f"{'SMOKE ' if SMOKE else ''}H1 bars {mk.n:,}  DEV {int(dv.sum()):,} ({mk.dt[dv][0]:%Y-%m-%d}..{mk.dt[dv][-1]:%Y-%m-%d})  "
          f"CONF {int(cf.sum()):,} ({mk.dt[cf][0]:%Y-%m-%d}..{mk.dt[cf][-1]:%Y-%m-%d})")
    print(f"input sha256 {mk.sha}")
    for H in HORIZONS:
        for e, m in (("DEV", dv), ("CONF", cf)):
            print(f"  H={H} {e}: usable entry bars {int((mk.ok[H] & m).sum()):,} of {int(m.sum()):,} "
                  f"({(mk.ok[H] & m).sum() / m.sum():.1%})")
    null_rate, power = self_check(mk)
    print(f"self-check: random-signal rejection {null_rate:.0%} (band 1%-10%); planted +3 bp found {power:.0%}", flush=True)
    assert 0.01 <= null_rate <= 0.10, "self-check failed: pipeline is mis-calibrated"
    rows = []
    for fam in E.SETUPS:
        sigs = mk.signals(fam)
        for H in HORIZONS:
            for label, top in (("A1 all-ATR", False), ("A1 top-ATR-third", True)):
                res = {e: evaluate(mk, sigs, e, H, top) for e in ERAS}
                rows.append(dict(family=fam, H_bars=H, test=label, **{f"DEV_{k}": v for k, v in res["DEV"].items()},
                                 **{f"CONF_{k}": v for k, v in res["CONF"].items()}))
    R = pd.DataFrame(rows)
    R["DEV_PASS"] = (R.DEV_diff > 0) & (R.DEV_p < ALPHA) & (R.DEV_net > 0)
    R["CONFIRMED"] = R.DEV_PASS & (R.CONF_diff > 0) & (R.CONF_p < 0.05) & (R.CONF_net > 0)
    if SMOKE:
        print(R[["family", "H_bars", "test", "DEV_n", "CONF_n"]].to_string(index=False))
        print("smoke: pipeline ran; no effect sizes shown by design")
        return 0
    feats = features(mk)
    A2 = []
    for name, x in feats.items():
        for H in HORIZONS:
            a = transfer(mk, name, x, H, "DEV", "CONF")
            b = transfer(mk, name, x, H, "CONF", "DEV")
            if a is None or b is None:
                continue
            A2.append(dict(feature=name, H_bars=H, rho_DEV_to_CONF=a["rho"], p_fwd=a["p"],
                           rho_CONF_to_DEV=b["rho"], p_back=b["p"], implied_gross_bp=0.8 * abs(a["rho"]) * a["sd"], n=a["n"]))
    A2 = pd.DataFrame(A2)
    A2["LEAD"] = ((A2.p_fwd < ALPHA) & (A2.p_back < 0.05) & (np.sign(A2.rho_DEV_to_CONF) == np.sign(A2.rho_CONF_to_DEV))
                  & (A2.implied_gross_bp > COST_BP))
    with pd.ExcelWriter(OUT) as xw:
        R.to_excel(xw, sheet_name="A1 24 tests", index=False)
        A2.to_excel(xw, sheet_name="A2 30 tests", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
    show = R[["family", "H_bars", "test", "DEV_n", "DEV_net", "DEV_diff", "DEV_p", "DEV_PASS",
              "CONF_n", "CONF_net", "CONF_diff", "CONF_p", "CONFIRMED"]].round(3)
    print(f"\nalpha = {ALPHA:.6f}\nA1 — six families (DEV 2003-2012, CONFIRM 2013-2015)")
    print(show.to_string(index=False))
    print(f"\nA1 DEV passes {int(R.DEV_PASS.sum())}/24   CONFIRMED {int(R.CONFIRMED.sum())}/24")
    print("\nA2 — information map, sorted by |rho| (DEV -> CONFIRM)")
    top = A2.reindex(A2.rho_DEV_to_CONF.abs().sort_values(ascending=False).index).head(10)
    print(top.round(4).to_string(index=False))
    print(f"\nA2 leads {int(A2.LEAD.sum())}/30   largest |rho| {A2.rho_DEV_to_CONF.abs().max():.4f}")
    print(f"saved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
