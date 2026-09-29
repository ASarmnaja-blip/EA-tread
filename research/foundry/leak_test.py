"""Look-ahead test for a Foundry family generator (added after the batch25 GVZ_JUMP bug).
For random H1 bars j: every H1 value from bar j on is replaced by garbage except bar j's OPEN
(the only price an entry at bar j may use); D1 bars are rebuilt from the garbaged H1. Every spec
entry at or before bar j (and every D1 entry whose day starts at or before t_j) must keep the same
entry, direction, stop and entry price. Usage: python research/foundry/leak_test.py <batch_fn>"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as FAM  # noqa: E402


def sig(specs, H, D, tj):
    """Entries up to bar j. A resting stop-entry order (eprice given) legitimately fills on bar j's
    high/low, so for those only entries strictly before bar j are compared."""
    out = {}
    for s in specs:
        B = H if s.tf == "H1" else D
        m = (B.t[s.ent] < tj) if s.eprice is not None else (B.t[s.ent] <= tj)
        ep = s.eprice[m] if s.eprice is not None else np.full(m.sum(), np.nan)
        last_t = B.t[np.minimum(s.last[m], len(B.t) - 1)]
        # the exit bar index may only be compared when it lies before the cut
        last_t = np.where(last_t < tj, last_t, -1)
        out[s.name] = (B.t[s.ent][m], s.dirs[m], np.round(s.stop[m], 6), np.round(ep, 6),
                       np.round(np.nan_to_num(s.tgt[m], nan=-1.0), 6), last_t)
    return out


def run(batch_fn, n_points=8, seed=7) -> bool:
    arrs = list(E._dukascopy_arrays())
    t = arrs[0]
    H0, D0, _, _ = E.build(*arrs); H0.v = E._CACHE["vol"]
    base = getattr(FAM, batch_fn)(H0, D0)
    rng = np.random.default_rng(seed)
    ok = True
    # cut points AT actual entries (an entry may use only its bar's open), plus random bars
    pts = set(int(x) for x in rng.integers(len(t) // 4, len(t) - 500, n_points))
    for s in base:
        if not len(s.ent):
            continue
        B = H0 if s.tf == "H1" else D0
        for e in rng.choice(s.ent, min(3, len(s.ent)), replace=False):
            pts.add(int(np.searchsorted(t, B.t[e])))
    for j in sorted(pts):
        if j >= len(t) - 2:
            continue
        g = [a.copy() for a in arrs]
        noise = rng.uniform(0.7, 1.3, len(t) - j)
        for idx in range(1, 9):                          # o, h, l, c, sp, bid c/h/l
            if idx == 1:
                g[idx][j + 1:] = g[idx][j + 1:] * noise[1:]   # keep bar j's open
            else:
                g[idx][j:] = g[idx][j:] * noise
        g[2] = np.maximum.reduce([g[2], g[1], g[4]]); g[3] = np.minimum.reduce([g[3], g[1], g[4]])
        H, D, _, _ = E.build(*g)
        v = E._CACHE["vol"].copy(); v[j:] = v[j:] * noise; H.v = v
        tj = int(t[j])
        a = sig(base, H0, D0, tj)
        b = sig(getattr(FAM, batch_fn)(H, D), H, D, tj)
        for name in a:
            x, y = a[name], b.get(name)
            same = y is not None and all(len(p) == len(q) and np.array_equal(p, q, equal_nan=True) for p, q in zip(x, y))
            if not same:
                ok = False
                print(f"  LEAK? {name} differs before bar {j} ({np.datetime64(tj, 's')})")
    print(f"leak test {batch_fn}: {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1]) else 1)
