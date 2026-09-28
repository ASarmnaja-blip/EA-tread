"""Size/power harness for the complete procedure P (prereg v2 section 5).

Runs BEFORE the historical P result. It never evaluates P on the real
matrix; every replicate scrambles tool identities week by week.

Null DGP (NULL_DGP):
  For each week w, among rows valid at w (metadata mask): traded cells are
  centred by the mean of that week's traded valid cells (base and 1.5x each
  by their own mean); untraded cells stay exactly 0. Then (R10, R15, NTR) are
  permuted JOINTLY across the valid rows with a fresh permutation per week.
  INNER is set to 1 (the tools' own sizing is already inside R).
  Why E[d_w | past] = 0 exactly: P's choice and size at w are functions of
  columns < w and the fixed mask only; the week-w permutation is independent
  of them, so the chosen row's value is a uniform draw from a zero-mean
  column, and so is every term of B'. Cross-tool co-movement within a week,
  volatility clustering over time, fat tails, activity patterns and
  structural zeros are all kept; only tool-identity persistence is destroyed.
Drift-stress null ("scrambled"): same permutation, no centring. No identity
  skill exists, but common weekly level/drift remains; shows whether sizing
  differences alone can pass the screen.
Planted alternatives: centred null + e bp added to every TRADED cell of the
  rows of one randomly chosen family (row labels fixed after permutation):
  persistent (all weeks), switching (13-week regimes, each on w.p. 0.5),
  decaying (e * 0.5^(t/52) from the first scored week).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import procedure as P  # noqa: E402

MATRIX = ROOT / "data" / "wpwb_procedure_matrix.npz"
OUT = ROOT / "data" / "wpwb_procedure_harness.csv"
SEED = 20260928
N_REP = 1000


def family_of(name):
    return name.split(" ")[0]


def scramble(R10, R15, NTR, VALID, rng, centre=True):
    A, B, N = R10.copy(), R15.copy(), NTR.copy()
    for w in range(A.shape[1]):
        v = np.flatnonzero(VALID[:, w])
        if len(v) == 0:
            continue
        if centre:
            tr = v[N[v, w] > 0]
            if len(tr):
                A[tr, w] -= A[tr, w].mean()
                B[tr, w] -= B[tr, w].mean()
        perm = rng.permutation(v)
        A[v, w], B[v, w], N[v, w] = A[perm, w], B[perm, w], N[perm, w]
    return A, B, N


def plant(A, B, N, rows, e, kind, first_w, rng):
    n = A.shape[1]
    t = np.arange(n)
    if kind == "persistent":
        g = np.full(n, e, float)
    elif kind == "switching":
        on = rng.random(n // 13 + 1) < 0.5
        g = np.where(on[t // 13], e, 0.0)
    elif kind == "decaying":
        g = e * 0.5 ** (np.maximum(t - first_w, 0) / 52)
    else:
        raise ValueError(kind)
    for r in rows:
        add = np.where(N[r] > 0, g, 0.0)
        A[r] += add; B[r] += add


def one(R10, R15, NTR, VALID, first_w, rng, scen, e, fams, names):
    A, B, N = scramble(R10, R15, NTR, VALID, rng, centre=(scen != "null_scrambled"))
    if scen not in ("null_centred", "null_scrambled"):
        fam = fams[rng.integers(len(fams))]
        rows = [i for i, nm in enumerate(names) if family_of(nm) == fam]
        plant(A, B, N, rows, e, scen, first_w, rng)
    ones = np.ones_like(A)
    res = P.run_fast(A, N, VALID, ones, first_w, {"base": A, "stress": B})
    ok, checks, _ = P.resource_screen(res)
    d = res["base"]["d"]
    c = P.clip_scale(d)
    E = P.e_process(d, c)
    hit = {h: bool((E[:h] >= 40).any()) for h in (52, 104, 156)}
    return dict(scenario=scen, edge_bp=e, screen=ok, mean_d=float(d.mean()),
                mean_P_stress=float(res["stress"]["P"].mean()),
                flat_share=float((res["choice"] < 0).mean()),
                e52=hit[52], e104=hit[104], e156=hit[156], **checks)


def main() -> int:
    z = np.load(MATRIX)
    R10, R15, NTR, VALID = z["R10"], z["R15"], z["NTR"], z["VALID"]
    names = [str(x) for x in z["names"]]
    fams = sorted({family_of(n) for n in names})
    first_w = P.first_scored_cut(VALID)
    rng = np.random.default_rng(SEED)
    scen = [("null_centred", 0.0), ("null_scrambled", 0.0)]
    scen += [(k, e) for k in ("persistent", "switching") for e in (5.0, 10.0, 20.0)]
    scen += [("decaying", 20.0)]
    rows = []
    t0 = time.time()
    for s, e in scen:
        for _ in range(N_REP):
            rows.append(one(R10, R15, NTR, VALID, first_w, rng, s, e, fams, names))
        print(f"{s:15s} e={e:4.0f} done ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    g = df.groupby(["scenario", "edge_bp"], sort=False)
    summ = g.agg(n=("screen", "size"), screen=("screen", "mean"),
                 mean_d=("mean_d", "mean"), sd_mean_d=("mean_d", "std"),
                 flat=("flat_share", "mean"), e52=("e52", "mean"),
                 e104=("e104", "mean"), e156=("e156", "mean"))
    summ["mc_se_screen"] = np.sqrt(summ.screen * (1 - summ.screen) / summ.n)
    summ["mc_se_mean_d"] = summ.sd_mean_d / np.sqrt(summ.n)
    pd.set_option("display.width", 200)
    print(f"seed {SEED}, {N_REP} replicates/scenario, first scored week index {first_w}")
    print(summ.round(4).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
