"""Y6 of docs/BUNDLE2_2026-10-01_PREREG.md: can WRWR's fragility be fixed? On the corrected X7 weekly R matrices (and the two perturbed
rebuilds: cost + 1 bp, close exits filled one bar later): (c) the single pick per year (largest trailing t, as X7), (a) equal weight of all
144 configurations, (b) equal weight of the top 10 by trailing t at each year's first cut. PASS: an ensemble with out-of-sample R > 0 on
both metals AND a narrower range across the three versions than the single pick. Usage: python research/bundle/y6_wrwr_fix.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

OUT = C.ROOT / "data" / "bundle2"
YEARS = {"XAUUSD": list(range(2010, 2027)), "XAGUSD": list(range(2012, 2027))}


def oos(R, active, cuts, years, rule):
    NW = len(cuts); k = np.arange(NW)
    ks = {Y: int(np.searchsorted(cuts, C.ts(f"{Y}-01-01"))) for Y in years + [years[-1] + 1]}
    out = np.zeros(NW); used = np.zeros(NW, bool)
    for Y in years:
        hist = active & (k < ks[Y]); fut = active & (k >= ks[Y]) & (k < ks[Y + 1])
        X = R[hist]
        with np.errstate(invalid="ignore", divide="ignore"):
            t = np.nan_to_num(X.mean(0) / (X.std(0, ddof=1) / np.sqrt(len(X))), nan=-np.inf)
        order = np.lexsort((np.arange(len(t)), -t))
        if rule == "single":
            cols = order[:1]
        elif rule == "top10":
            cols = order[:10]
        else:
            cols = np.arange(R.shape[1])
        out[fut] = R[fut][:, cols].mean(1); used[fut] = True
    return out, used


def fin(out, used, cuts):
    eq = 10_000.0; peak = eq; dd = 0.0
    for kk in np.flatnonzero(used):
        eq *= 1 + 0.01 * out[kk]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
    yrs = used.sum() / 52.18
    return float(out[used].sum()), (eq / 10_000) ** (1 / max(yrs, 0.1)) - 1, dd


def main():
    rows = []
    for sym in ("XAUUSD", "XAGUSD"):
        for tag, lab in (("", "base"), ("_cost1", "cost +1 bp"), ("_exit1", "exit +1 bar")):
            f = C.OUT / f"x7_family_{sym}{tag}.npz"
            if not f.exists():
                continue
            z = np.load(f)
            for rule in ("single", "top10", "all144"):
                out, used = oos(z["R"], z["active"], z["cuts"], YEARS[sym], rule)
                R_, cagr, dd = fin(out, used, z["cuts"])
                rows.append(dict(sym=sym, version=lab, rule=rule, oos_R=R_, cagr=cagr, dd=dd))
    D = pd.DataFrame(rows)
    D.to_csv(OUT / "y6_wrwr_fix.csv", index=False)
    rng = D.groupby(["sym", "rule"]).oos_R.agg(["min", "max"]); rng["range"] = rng["max"] - rng["min"]
    base = D[D.version == "base"].set_index(["sym", "rule"]).oos_R
    verdict = {}
    for rule in ("top10", "all144"):
        pos = all(base.get((s, rule), -1) > 0 for s in ("XAUUSD", "XAGUSD"))
        narrower = all(rng.loc[(s, rule), "range"] < rng.loc[(s, "single"), "range"] for s in ("XAUUSD", "XAGUSD"))
        verdict[rule] = dict(oos_positive_both=pos, narrower_both=narrower, PASS=bool(pos and narrower))
    (OUT / "y6_verdict.json").write_text(json.dumps(dict(ranges=rng.reset_index().to_dict("records"), verdict=verdict), indent=1, default=float))
    pd.set_option("display.width", 200)
    print(D.round(3).to_string(index=False)); print(rng.round(1).to_string()); print(verdict)


if __name__ == "__main__":
    main()
