"""Leak test of the WRWR signal construction (contract C1): for each TF (H1, H4, D1) and several cut points j, replace
every bar after j with garbage and require (a) the 31 zoo signals, (b) the ATR used for stops and (c) the simulated trades
of candidates entered at or before j (entry bar <= j) to be unchanged for everything known at bar j. Run directly."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402

sys.path[:0] = [str(K.ROOT / "research" / "sieve"), str(K.ROOT / "research" / "foundry")]
import engine as E  # noqa: E402
import features as FT  # noqa: E402


def garbage_after(B, j, rng):
    G = copy.copy(B)
    n = len(B.t)
    for f in ("o", "h", "l", "c", "v", "spread_bp"):
        a = np.asarray(getattr(B, f), float).copy()
        a[j + 1:] = a[j + 1:] * rng.uniform(0.5, 1.5, n - j - 1)
        setattr(G, f, a)
    hi = np.maximum.reduce([G.o, G.h, G.l, G.c]); lo = np.minimum.reduce([G.o, G.h, G.l, G.c])
    G.h = np.r_[B.h[: j + 1], hi[j + 1:]]; G.l = np.r_[B.l[: j + 1], lo[j + 1:]]
    G.atr = E._atr(G.h, G.l, G.c, 14)
    return G


def main():
    rng = np.random.default_rng(11)
    for tf in ("H1", "H4", "D1"):
        B, cuts, _ = SG.load_xau(tf)
        n = len(B.t)
        base = FT.zoo_signals(B)
        for j in (n // 6, n // 2, n - 400):
            G = garbage_after(B, j, rng)
            assert np.allclose(B.atr[: j + 2], G.atr[: j + 2], equal_nan=True), f"{tf} ATR leaks at j={j}"   # ATR at j+1's open uses bars <= j
            sig = FT.zoo_signals(G)
            bad = [k for k in base if not (np.array_equal(base[k][0][: j + 1], sig[k][0][: j + 1])
                                           and np.array_equal(base[k][1][: j + 1], sig[k][1][: j + 1]))]
            assert not bad, f"{tf} signals leak at j={j}: {bad}"
            # a trade entered at bar e <= j + 1 (open of e, decided on signal at e-1 <= j) must not depend on bars after e + hold
            e = np.array([j + 1])
            for hold in (HOLD := SG.HOLDS[tf]):
                stop = 1.0 * B.atr[e]
                g1, x1 = E.simulate(B, e, np.array([1.0]), stop, 3 * stop, e + hold - 1)
                g2, x2 = E.simulate(G, e, np.array([1.0]), stop, 3 * stop, e + hold - 1)
                if x1[0] <= j:                      # exit already inside the known region -> identical
                    assert g1[0] == g2[0] and x1[0] == x2[0], f"{tf} trade outcome changed inside the known region"
        print(f"PASS {tf}: zoo signals and ATR known at bar j are unchanged by garbage after j ({n:,} bars, 3 cut points)")
    print("ALL SIGNAL LEAK TESTS PASS")


if __name__ == "__main__":
    main()
