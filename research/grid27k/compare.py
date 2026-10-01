"""G27K: real results against the placebo paths (docs/plans/G27K_PREREG.md, section on checks). Prints pass counts, best-of-grid totals,
the choose-on-3-years / check-on-2-years persistence for real and placebo, and how the real top combinations compare with the same
combinations on the drift-preserving paths. Bootstrap p of 0 is floored at 1/(K+1) before Holm."""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[2] / "data" / "grid27k"
K = 1000


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); out = np.full(len(p), np.nan); run = 0.0
    for r, i in enumerate(np.argsort(np.where(np.isfinite(p), p, np.inf))):
        if np.isfinite(p[i]):
            run = max(run, min(1.0, (m - r) * p[i])); out[i] = run
    return out


def stats(D):
    pf = np.maximum(D.p.to_numpy(), 1 / (K + 1)); ph = holm(pf)
    top = D.nlargest(20, "totR_A")
    return dict(basic=int(((D.p < 0.05) & (D.R > 0)).sum()), strict=int(((ph < 0.05) & (D.R > 0) & (D.pos_mkts == 3)).sum()),
                positive=float((D.totR > 0).mean()), best=float(D.totR.max()), best_cagr=float(D.cagr.max()), median_totR=float(D.totR.median()),
                top20_B=float(top.totR_B.median()), all_B=float(D.totR_B.median()), top20_cagrB=float(top.cagr_B.median()),
                rho=float(D[["totR_A", "totR_B"]].corr(method="spearman").iloc[0, 1]))


def main():
    real = pd.read_csv(OUT / "g27k_real.csv"); rows = {"real": stats(real)}
    pls = {f.stem.replace("g27k_", ""): pd.read_csv(f) for f in sorted(OUT.glob("g27k_*.csv")) if f.stem.startswith(("g27k_drift", "g27k_placebo"))}
    for k, D in pls.items():
        rows[k] = stats(D)
    T = pd.DataFrame(rows).T
    print(T.round(3).to_string())
    top = real.nlargest(10, "totR").combo.tolist() + real.nlargest(5, "cagr").combo.tolist()
    drift = [D.set_index("combo") for k, D in pls.items() if k.startswith("drift")]
    print("\nreal top combinations against the same combination on the drift-preserving paths (total R):")
    for c in dict.fromkeys(top):
        r = real.set_index("combo").loc[c]; v = np.array([D.loc[c, "totR"] for D in drift]) if drift else np.array([])
        print(f"  {c}: real {r.totR:7.0f}  drift paths {np.round(np.sort(v)).astype(int).tolist()}  ({int((v >= r.totR).sum())} of {len(v)} >= real)")


if __name__ == "__main__":
    main()
