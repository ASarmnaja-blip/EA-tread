"""Test A of docs/WRWR_HISTORY_OOS_PREREG.md: the research procedure replayed through time on gold. At the first cut of every
year Y the studentized Reality Check runs on the weekly excess d = R - B of the weeks already known (R of week k is realised on
exits in (cut_k, cut_{k+1}], known at cut_{k+1}); the configuration it would adopt trades year Y. Frozen family and Stage F
benchmark files only; nothing is re-simulated. Also usable for silver (Test B read-outs) via run(fam_path, bench_path).
Writes data/wrwr/history_oos_A.json and prints the read-out."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import gates as G  # noqa: E402

WR = K.ROOT / "data" / "wrwr"
FAMS = {"zoo": (WR / "family_XAUUSD.npz", WR / "bench_F.npz"), "f2": (WR / "family_XAUUSD_f2.npz", WR / "bench_F_f2.npz")}
YEARS = list(range(2010, 2027))


def load(fam_path, bench_path):
    z = np.load(fam_path, allow_pickle=False)
    b = np.load(bench_path, allow_pickle=False)
    if str(b["family_sha"]) != str(z["meta"]):
        raise ValueError(f"{bench_path.name} was not computed from {fam_path.name}")
    fam = json.loads(str(z["family"]))
    if [int(x) for x in b["configs"]] != list(range(len(fam))):
        raise ValueError("benchmark does not cover the whole family")
    meta = json.loads(str(z["meta"]))
    return z["cuts"], z["active"], z["R_0.01"], b["B"], fam, meta


def label(c):
    return f"{c['window']}w z{c['lcb_z']:g} {c['pool']} m{c['m']}" + (f" eq{c['equity_filter']}" if c["equity_filter"] else "")


def run(fam_path, bench_path, years=YEARS, seed0=12345):
    cuts, active, R, B, fam, meta = load(fam_path, bench_path)
    NW = len(cuts); k = np.arange(NW)
    complete = np.r_[cuts[1:] <= meta["data_end"], False]                 # every exit of week k is in the data
    kstar = {Y: int(np.searchsorted(cuts, int(pd.Timestamp(f"{Y}-01-01").timestamp()), side="left")) for Y in years + [years[-1] + 1]}
    D = R - B
    rows = []
    for Y in years:
        hist = active & (k < kstar[Y])
        fut = active & complete & (k >= kstar[Y]) & (k < kstar[Y + 1])
        rc = G.reality_check(D[hist], mean_block=10, K=999, seed=seed0 + Y)
        t = np.nan_to_num(rc["t"], nan=-np.inf)
        order = np.lexsort((np.arange(len(t)), -t))
        rows.append(dict(Y=Y, p=rc["p"], V=rc["V"], T_hist=int(hist.sum()), top=[int(x) for x in order[:4]],
                         t_top=[float(t[x]) for x in order[:4]], fut=np.flatnonzero(fut)))
    res = {}
    for name, gate, m in (("P1", True, 1), ("P4", True, 4), ("F1", False, 1), ("F4", False, 4)):
        xr, xd, per = [], [], []
        for r in rows:
            if gate and r["p"] > 0.05:
                per.append(dict(Y=r["Y"], adopted=False, R=0.0, d=0.0, weeks=0)); continue
            js = r["top"][:m]
            yr = R[r["fut"]][:, js].mean(1); yd = D[r["fut"]][:, js].mean(1)
            xr.append(yr); xd.append(yd)
            per.append(dict(Y=r["Y"], adopted=True, cfg=js, R=float(yr.sum()), d=float(yd.sum()), weeks=int(len(yr))))
        xr = np.concatenate(xr) if xr else np.zeros(0); xd = np.concatenate(xd) if xd else np.zeros(0)
        out = dict(years_adopted=int(sum(p["adopted"] for p in per)), weeks=int(len(xr)), total_R=float(xr.sum()),
                   pos_year_share=float(np.mean([p["R"] > 0 for p in per if p["adopted"]])) if xr.size else float("nan"), years=per)
        if len(xr) >= 20:
            out["lbR"], out["meanR"] = G.lower_bound_mean(xr); out["lbd"], out["meand"] = G.lower_bound_mean(xd)
        res[name] = out
    p1 = res["P1"]
    if p1["weeks"] < 104:
        verdict = "INSUFFICIENT"
    elif p1["lbd"] > 0 and p1["meanR"] > 0:
        verdict = "PASS"
    elif p1["lbd"] > 0:
        verdict = "WEAK"
    else:
        verdict = "FAIL"
    return dict(verdict=verdict, procedures=res, decisions=[{k_: v for k_, v in r.items() if k_ != "fut"} for r in rows],
                labels={j: label(c) for j, c in enumerate(fam)})


def show(name, out):
    lab = out["labels"]
    print(f"\n=== {name}: P1 verdict {out['verdict']} ===")
    print("  Y     p      V   hist  top-1 by t (t)                       R(Y)   d(Y)")
    f1 = {p["Y"]: p for p in out["procedures"]["F1"]["years"]}
    for r in out["decisions"]:
        y = f1[r["Y"]]
        print(f"  {r['Y']} {r['p']:.3f} {r['V']:5.2f} {r['T_hist']:5d}  {lab[r['top'][0]]:<24s} ({r['t_top'][0]:+.2f})  "
              f"{y['R']:+7.1f} {y['d']:+7.1f}{'  <- adopted' if r['p'] <= 0.05 else ''}")
    for nm, p in out["procedures"].items():
        s = f"  {nm}: years adopted {p['years_adopted']:2d}, weeks {p['weeks']:4d}, total R {p['total_R']:+7.1f}"
        if "meanR" in p:
            s += (f", mean R/wk {p['meanR']:+.4f} (lb {p['lbR']:+.4f}), mean d/wk {p['meand']:+.4f} (lb {p['lbd']:+.4f}), "
                  f"positive years {p['pos_year_share']:.0%}")
        print(s)


def main():
    allout = {}
    for name, (fp, bp) in FAMS.items():
        out = run(fp, bp)
        show(name, out)
        allout[name] = out
    (WR / "history_oos_A.json").write_text(json.dumps(allout, indent=1, default=float))
    print("\n->", WR / "history_oos_A.json")


if __name__ == "__main__":
    main()
