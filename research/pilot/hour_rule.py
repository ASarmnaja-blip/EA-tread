"""Frozen hour-of-day rule on unseen eras. See docs/HOUR_RULE_PREREG.md
(committed before this ran). Read-only.
Usage: python research/pilot/hour_rule.py [--era E1|E2|both]"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research" / "history"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
from build_all_tf import load_kind  # noqa: E402

H = 4
STEP = 3600
WEEK = 7 * 86400
COST_BP = 0.80
MIN_N = 300
B_REPS = 10000
RNG = np.random.default_rng(20260929)
ERA = (sys.argv[sys.argv.index("--era") + 1] if "--era" in sys.argv else "both")
OUT = ROOT / "data" / "hour_rule.xlsx"


def windows(t, o, c):
    """fwd (bp), valid mask, signal hour for a signal at bar i."""
    n = len(t)
    fwd = np.full(n, np.nan); ok = np.zeros(n, bool)
    i = np.arange(n - H - 1)
    ent, ext = i + 1, i + H
    contig = (t[ext] - t[ent]) == (H - 1) * STEP
    step_ok = (t[ent] - t[i]) == STEP
    k0 = np.floor((t[ent] - 75600) / 86400)
    k1 = np.floor((t[ext] + STEP - 1 - 75600) / 86400)
    fwd[i] = (c[ext] / o[ent] - 1) * 1e4
    ok[i] = contig & step_ok & (k0 == k1)
    return fwd, ok, ((t // 3600) % 24).astype(int)


def fit():
    d = load_kind("hour")
    d = d[d.index < "2016-01-01"]
    t = d.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    fwd, ok, hr = windows(t, d.o.to_numpy(float), d.c.to_numpy(float))
    m = ok & np.isfinite(fwd)
    mu = fwd[m].mean()
    rows = {}
    for h in range(24):
        s = fwd[m & (hr == h)] - mu
        if len(s) < MIN_N:
            continue
        se = s.std(ddof=1) / np.sqrt(len(s) / 4)
        rows[h] = dict(mean=float(s.mean()), t=float(s.mean() / se), n=int(len(s)))
    r24 = {h: int(np.sign(v["mean"])) for h, v in rows.items() if v["mean"] != 0}
    rt2 = {h: r24[h] for h, v in rows.items() if abs(v["t"]) >= 2 and h in r24}
    return rows, r24, rt2


def trades(t, o, c, dirs, start, end):
    fwd, ok, hr = windows(t, o, c)
    dt = pd.to_datetime(t, unit="s")
    inrange = np.asarray((dt >= start) & (dt < end))
    idx = []
    last = -10 ** 9
    for i in np.flatnonzero(ok & np.isfinite(fwd) & inrange):
        d = dirs.get(int(hr[i]))
        if d is None or i < last + H:
            continue
        idx.append((i, d))
        last = i
    if not idx:
        return None
    ii = np.array([a for a, _ in idx]); dd = np.array([b for _, b in idx], float)
    return ii, dd, fwd[ii], t[ii], hr[ii]


def stats(ii, dd, f, tt):
    q = float((dd > 0).mean())
    diff = f * (dd - (2 * q - 1))
    net = dd * f - COST_BP
    uw, inv = np.unique(tt // WEEK, return_inverse=True)
    cn = np.bincount(inv).astype(float)
    sd, sn = np.bincount(inv, weights=diff), np.bincount(inv, weights=net)
    ix = RNG.integers(0, len(uw), (B_REPS, len(uw)))
    md, mn = sd[ix].sum(1) / cn[ix].sum(1), sn[ix].sum(1) / cn[ix].sum(1)
    obs = sd.sum() / cn.sum()
    p = (np.sum(np.abs(md - md.mean()) >= abs(obs)) + 1) / (B_REPS + 1)
    return dict(n=len(f), long_share=q, gross=float((dd * f).mean()), net=float(net.mean()),
                net_lo=float(np.percentile(mn, 2.5)), net_hi=float(np.percentile(mn, 97.5)),
                diff=float(obs), p=float(p), sd=float(f.std()))


def era_data(name):
    if name == "E1":
        import bars as BR
        m = BR.market(BR.load_bars(frozen=False))
        return m.t.astype(np.int64), m.o, m.c, "2021-07-01", "2026-10-01", "Exness H1 2021-07..2026-09"
    d = load_kind("hour")
    last = d.index[-1]
    if last < pd.Timestamp("2020-12-31"):
        return None
    d = d[(d.index >= "2016-01-01") & (d.index < "2021-01-01")]
    t = d.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    return t, d.o.to_numpy(float), d.c.to_numpy(float), "2016-01-01", "2021-01-01", "Dukascopy H1 2016-01..2020-12"


def main() -> int:
    os.chdir(ROOT)
    rows, r24, rt2 = fit()
    blob = json.dumps({"r24": r24, "rt2": rt2}, sort_keys=True)
    print("frozen map hash:", hashlib.sha256(blob.encode()).hexdigest()[:16])
    print("hour: sign (mean bp, t)  [fit 2003-05..2015-12]")
    print("  " + "  ".join(f"{h:02d}:{'+' if r24[h] > 0 else '-'}({rows[h]['mean']:+.1f},{rows[h]['t']:+.1f})" for h in sorted(r24)))
    print(f"R24 trades hours {sorted(r24)}\nRt2 trades hours {sorted(rt2)}")
    names = ["E1", "E2"] if ERA == "both" else [ERA]
    out, hourtab = [], []
    for nm in names:
        ed = era_data(nm)
        if ed is None:
            print(f"\n{nm}: Dukascopy cache does not yet cover 2020-12 -> skipped, run again later")
            continue
        t, o, c, a, b, label = ed
        for var, dirs in (("R24", r24), ("Rt2", rt2)):
            tr = trades(t, o, c, dirs, a, b)
            if tr is None:
                continue
            ii, dd, f, tt, hh = tr
            s = stats(ii, dd, f, tt)
            s.update(era=nm, variant=var, label=label,
                     replicates=bool(s["diff"] > 0 and s["p"] < 0.05 and s["net"] > 0))
            out.append(s)
            yr = pd.to_datetime(tt, unit="s").year
            yt = pd.DataFrame({"year": yr, "net": dd * f - COST_BP, "gross": dd * f, "n": 1}).groupby("year").agg(
                net=("net", "mean"), gross=("gross", "mean"), n=("n", "sum"))
            print(f"\n=== {nm} {label} | {var} ===")
            print(f"trades {s['n']}  long share {s['long_share']:.0%}  gross {s['gross']:+.2f} bp  net {s['net']:+.2f} bp "
                  f"[{s['net_lo']:+.2f}, {s['net_hi']:+.2f}]  drift-controlled diff {s['diff']:+.2f} bp  p {s['p']:.4f}  "
                  f"-> {'REPLICATES' if s['replicates'] else 'does not replicate'}")
            print("by year (net bp, n):", "  ".join(f"{y}:{r.net:+.1f}({int(r.n)})" for y, r in yt.iterrows()))
            if var == "R24":
                ht = pd.DataFrame({"h": hh, "g": dd * f}).groupby("h").g.agg(["mean", "count"]).round(2)
                ht["era"] = nm
                hourtab.append(ht.reset_index())
    if out:
        R = pd.DataFrame(out)
        with pd.ExcelWriter(OUT) as xw:
            R.to_excel(xw, sheet_name="results", index=False)
            if hourtab:
                pd.concat(hourtab).to_excel(xw, sheet_name="R24 by hour", index=False)
        print("\nverdict per pre-registration:")
        for var in ("R24", "Rt2"):
            r = R[R.variant == var]
            got = {e: bool(v) for e, v in zip(r.era, r.replicates)}
            state = ("ALIVE (replicates in both eras)" if len(got) == 2 and all(got.values())
                     else "partly alive, unproven" if any(got.values())
                     else "decayed (replicates in no era tested)" if len(got) == 2
                     else f"incomplete: only {list(got)} tested so far, replicates={got}")
            print(f"  {var}: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
