"""Minimum-detectable-edge follow-up to harness.py: larger persistent planted
edges, plus how often P picks the planted family. Scrambled data only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
import procedure as P  # noqa: E402

SEED = 5
N_REP = 200


def main() -> int:
    z = np.load(H.MATRIX)
    R10, R15, NTR, V = z["R10"], z["R15"], z["NTR"], z["VALID"]
    names = [str(x) for x in z["names"]]
    fams = sorted({H.family_of(n) for n in names})
    w0 = P.first_scored_cut(V)
    sd = np.array([R10[i, w0:][V[i, w0:]].std() for i in range(len(names))])
    act = (NTR[:, w0:] > 0).mean(axis=1)
    print(f"tool weekly SD (bp): median {np.median(sd):.0f}, range {sd.min():.0f}..{sd.max():.0f}; "
          f"median activity {np.median(act):.2f}")
    rng = np.random.default_rng(SEED)
    for e in (20.0, 50.0, 100.0, 200.0):
        out, pick = [], []
        for _ in range(N_REP):
            A, B, N = H.scramble(R10, R15, NTR, V, rng)
            fam = fams[rng.integers(len(fams))]
            rows = [i for i, n in enumerate(names) if H.family_of(n) == fam]
            H.plant(A, B, N, rows, e, "persistent", w0, rng)
            res = P.run_fast(A, N, V, np.ones_like(A), w0, {"base": A, "stress": B})
            ok, _, _ = P.resource_screen(res)
            d = res["base"]["d"]
            E = P.e_process(d, P.clip_scale(d))
            out.append((ok, d.mean(), (E[:156] >= 40).any()))
            pick.append(np.isin(res["choice"], rows).mean())
        o = np.asarray(out, float)
        print(f"persistent +{e:.0f} bp: screen {o[:, 0].mean():.2f}  mean d {o[:, 1].mean():6.1f}  "
              f"e-process<=156w {o[:, 2].mean():.2f}  family pick-rate {np.mean(pick):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
