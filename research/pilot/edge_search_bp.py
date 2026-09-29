"""Edge search in basis points with an ATR gate — see
docs/EDGE_SEARCH_BP_PREREG.md (committed before this ran). Read-only."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import core  # noqa: E402
import historical_regime_walkforward as hist  # noqa: E402
import mtf_engine as E  # noqa: E402

COST_USD = 0.09 + 0.14 + 2 * 0.0165
HORIZONS = (4, 16)
ERAS = {"DEV": ("2021-07-01", "2024-01-01"), "LATER": ("2024-01-01", "2026-10-01")}
B_REPS = 4000
N_TESTS = 24
ALPHA = 0.05 / N_TESTS
TOP_PCT = 66.7
WEEK = 7 * 86400
STEP = 900
OUT = ROOT / "data" / "edge_search_bp.xlsx"
RNG = np.random.default_rng(20260929)


class Market:
    def __init__(self):
        b5 = hist.load_history()
        self.b15, nxt = E.resample(b5, 3)
        self.c = core.Ctx(self.b15, nxt)
        b = self.b15
        self.t = np.asarray(b.t, np.int64)
        self.o, self.cl = np.asarray(b.o, float), np.asarray(b.c, float)
        self.n = len(b)
        self.pct = np.asarray(self.c.atr_pct, float)
        self.dt = pd.to_datetime(self.t, unit="s")
        dec = np.where(np.isfinite(self.pct), np.minimum((self.pct // 10).astype(float), 9), np.nan)
        sess = pd.factorize(np.asarray(self.c.session))[0].astype(float)
        self.bin = np.where(np.isfinite(dec), dec * 10 + sess, np.nan)
        self.fwd, self.ok = {}, {}
        for H in HORIZONS:
            f = np.full(self.n, np.nan)
            ok = np.zeros(self.n, bool)
            i = np.arange(self.n - H - 1)
            ent, ext = i + 1, i + H
            contiguous = (self.t[ext] - self.t[ent]) == (H - 1) * STEP
            k0 = np.floor((self.t[ent] - 75600) / 86400)
            k1 = np.floor((self.t[ext] + STEP - 1 - 75600) / 86400)
            good = contiguous & (k0 == k1)
            f[i] = (self.cl[ext] / self.o[ent] - 1) * 1e4
            ok[i] = good
            self.fwd[H], self.ok[H] = f, ok
        self.era_mask = {k: (self.dt >= a) & (self.dt < b) for k, (a, b) in ERAS.items()}
        self.bin_mean = {}
        for era, em in self.era_mask.items():
            for H in HORIZONS:
                m = em & self.ok[H] & np.isfinite(self.bin) & (np.arange(self.n) >= self.c.warm)
                s = pd.Series(self.fwd[H][m]).groupby(self.bin[m]).mean()
                self.bin_mean[(era, H)] = s.to_dict()

    def signals(self, fam):
        sig = E.setup_signals(fam, self.c)
        return sorted((int(i), int(d)) for i, d in sig)


def evaluate(mk, sigs, era, H, top_only=False, plant=0.0, reps=B_REPS):
    em, bm = mk.era_mask[era], mk.bin_mean[(era, H)]
    kept, last = [], -10 ** 9
    for i, d in sigs:
        if i < mk.c.warm or i + H + 1 >= mk.n or not em[i] or not mk.ok[H][i]:
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
        return dict(n=len(kept), net=np.nan, ctrl_net=np.nan, diff=np.nan, p=np.nan, lo=np.nan, hi=np.nan)
    ii = np.array([k[0] for k in kept]); dd = np.array([k[1] for k in kept], float)
    mb = np.array([k[2] for k in kept])
    r = dd * mk.fwd[H][ii] + plant
    cost = COST_USD / mk.o[ii + 1] * 1e4
    diff = r - dd * mb
    net = r - cost
    weeks = mk.t[ii] // WEEK
    uw, inv = np.unique(weeks, return_inverse=True)
    sd = np.bincount(inv, weights=diff); cn = np.bincount(inv).astype(float)
    obs = sd.sum() / cn.sum()
    idx = RNG.integers(0, len(uw), (reps, len(uw)))
    means = sd[idx].sum(1) / cn[idx].sum(1)
    dev = means - means.mean()
    p = (np.sum(np.abs(dev) >= abs(obs)) + 1) / (reps + 1)
    return dict(n=len(kept), net=float(net.mean()), ctrl_net=float((dd * mb - cost).mean()),
                diff=float(obs), p=float(p), lo=float(np.percentile(means, 2.5)),
                hi=float(np.percentile(means, 97.5)))


def self_check(mk):
    """Random 'signals' must reject at ~5%; a planted +4 bp must be found."""
    era, H = "DEV", 4
    pool = np.flatnonzero(mk.era_mask[era] & mk.ok[H] & np.isfinite(mk.bin) & (np.arange(mk.n) >= mk.c.warm))
    rej0 = rej1 = 0
    draws = 30
    for _ in range(draws):
        idx = np.sort(RNG.choice(pool, 3000, replace=False))
        sigs = [(int(i), int(RNG.choice([-1, 1]))) for i in idx]
        rej0 += evaluate(mk, sigs, era, H, reps=800)["p"] < 0.05
        rej1 += evaluate(mk, sigs, era, H, plant=4.0, reps=800)["p"] < 0.05
    return rej0 / draws, rej1 / draws


def main() -> int:
    os.chdir(ROOT)
    mk = Market()
    print(f"M15 bars {mk.n:,}; DEV signals evaluated per family below", flush=True)
    null_rate, power = self_check(mk)
    print(f"self-check: random-signal rejection rate {null_rate:.0%} (want ~5%); "
          f"planted +4 bp detected {power:.0%}", flush=True)
    rows, terc = [], []
    for fam in E.SETUPS:
        sigs = mk.signals(fam)
        for H in HORIZONS:
            for label, top in (("A all-ATR", False), ("B top-ATR-third", True)):
                res = {era: evaluate(mk, sigs, era, H, top) for era in ERAS}
                d, l = res["DEV"], res["LATER"]
                passed = bool(np.isfinite(d["p"]) and d["diff"] > 0 and d["p"] < ALPHA and d["net"] > 0)
                cand = bool(passed and l["diff"] > 0 and l["net"] > 0)
                rows.append(dict(family=fam, H_bars=H, test=label, DEV_n=d["n"], DEV_net_bp=d["net"],
                                 DEV_ctrl_net_bp=d["ctrl_net"], DEV_diff_bp=d["diff"],
                                 DEV_ci_lo=d["lo"], DEV_ci_hi=d["hi"], DEV_p=d["p"], DEV_PASS=passed,
                                 LATER_n=l["n"], LATER_net_bp=l["net"], LATER_diff_bp=l["diff"],
                                 LATER_p=l["p"], CANDIDATE=cand))
            # descriptive tercile table (all-ATR signals split by ATR third)
            for era in ERAS:
                for name, lo, hi in (("bottom", 0, 33.3), ("middle", 33.3, 66.7), ("top", 66.7, 100.1)):
                    sub = [(i, d) for i, d in sigs if np.isfinite(mk.pct[i]) and lo <= mk.pct[i] < hi]
                    r = evaluate(mk, sub, era, H, reps=1000)
                    terc.append(dict(family=fam, H_bars=H, era=era, atr_third=name, n=r["n"],
                                     net_bp=r["net"], diff_bp=r["diff"], p=r["p"]))
    R = pd.DataFrame(rows)
    T = pd.DataFrame(terc)
    with pd.ExcelWriter(OUT) as xw:
        R.to_excel(xw, sheet_name="24 tests", index=False)
        T.to_excel(xw, sheet_name="ATR thirds", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
    show = R[["family", "H_bars", "test", "DEV_n", "DEV_net_bp", "DEV_diff_bp", "DEV_p", "DEV_PASS",
              "LATER_net_bp", "LATER_diff_bp", "CANDIDATE"]].copy()
    for c in ("DEV_net_bp", "DEV_diff_bp", "LATER_net_bp", "LATER_diff_bp"):
        show[c] = show[c].round(2)
    show["DEV_p"] = show["DEV_p"].round(4)
    print(f"\nalpha per test = {ALPHA:.5f}")
    print(show.to_string(index=False))
    print(f"\nDEV passes: {int(R.DEV_PASS.sum())}/24   candidates (also LATER): {int(R.CANDIDATE.sum())}/24")
    print("\nDoes the family-vs-control difference grow with ATR? (mean diff bp by ATR third, DEV, pooled over families)")
    g = T[T.era == "DEV"].groupby(["H_bars", "atr_third"]).apply(
        lambda x: np.average(x.diff_bp, weights=x.n) if x.n.sum() else np.nan, include_groups=False)
    print(g.round(2).unstack().reindex(columns=["bottom", "middle", "top"]).to_string())
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
