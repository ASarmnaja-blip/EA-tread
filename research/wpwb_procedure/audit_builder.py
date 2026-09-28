"""Bars-after-week audit for the matrix builder (prereg v2 section 7).

For random cuts w, every bar at or after cut_w + 1 week is replaced by a
random walk; every tool's r_{i,w}, NTR and INNER at w must be unchanged. So
column w of the matrix depends only on bars before its own week ends, and the
selector at w (which reads columns < w) sees nothing after cut_w.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("research/wpwb_procedure", "research/wpwb_live", "research/wpwb_search"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
import menu as M  # noqa: E402
import run_live_hod as RL  # noqa: E402

N_CUTS = 12


def garbage_after(b5, t_end, rng):
    k = int(np.searchsorted(b5.t, t_end))
    n = len(b5.t) - k
    c = b5.c.copy(); o = b5.o.copy(); h = b5.h.copy(); l = b5.l.copy()
    walk = b5.c[k - 1] * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    o[k:] = np.r_[b5.c[k - 1], walk[:-1]]; c[k:] = walk
    h[k:] = np.maximum(o[k:], c[k:]) * 1.001; l[k:] = np.minimum(o[k:], c[k:]) * 0.999
    sp = b5.sp.copy(); sp[k:] = rng.uniform(0.05, 2.0, n)
    return RL.D.Bars(b5.t, o, h, l, c, b5.v, b5.step, b5.symbol, sp)


def main() -> int:
    os.chdir(ROOT)
    z = np.load(ROOT / "data" / "wpwb_procedure_matrix.npz")
    cuts = z["cuts"]
    b5 = RL.combined_bars()
    man = M.manifest()
    rng = np.random.default_rng(11)
    ws = sorted(rng.choice(np.arange(60, len(cuts)), N_CUTS, replace=False))
    for w in ws:
        cut = int(cuts[w])
        mg = C.Market(garbage_after(b5, cut + C.WEEK, rng))
        R, NTR, INNER = M.build_matrix(mg, np.array([cut]), (1.0, 1.5), man)
        assert np.allclose(R[1.0][:, 0], z["R10"][:, w]), f"R10 differs at w={w}"
        assert np.allclose(R[1.5][:, 0], z["R15"][:, w]), f"R15 differs at w={w}"
        assert np.array_equal(NTR[:, 0], z["NTR"][:, w]), f"NTR differs at w={w}"
        assert np.allclose(INNER[:, 0], z["INNER"][:, w]), f"INNER differs at w={w}"
        print(f"w={w} cut={np.datetime64(cut, 's')} ok", flush=True)
    print(f"builder audit: {N_CUTS}/{N_CUTS} cuts unchanged under garbage after week end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
