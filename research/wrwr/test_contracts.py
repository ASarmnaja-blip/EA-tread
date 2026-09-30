"""Synthetic tests for the WRWR contracts (C1 time axis, C3 causal vol_scale, C4 cost / swap). Run:
python research/wrwr/test_contracts.py  -> prints PASS lines, raises on the first failure."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts as K  # noqa: E402

CUT = int(pd.Timestamp("2026-10-02 22:15:00").timestamp())
CUTS = np.array([CUT - 7 * 86400, CUT, CUT + 7 * 86400], np.int64)


def test_entry_week():
    k, at = K.entry_week([CUT - 1, CUT, CUT + 1], CUTS)
    assert list(k[[0, 2]]) == [0, 1] and list(at) == [False, True, False], (k, at)
    k, at = K.entry_week([CUTS[0] - 1], CUTS)
    assert k[0] == -1 and not at[0]
    print("PASS C1 entry week: cut-1s -> old week, at cut -> rejected, cut+1s -> new week")


def test_known_at_cut():
    kk = K.known_at_cut([CUT - 1, CUT, CUT + 1], CUTS)
    assert list(kk) == [1, 1, 2], kk
    print("PASS C1 exits: close <= cut is known at that cut, a later close only at the next cut")


def test_usable_bars_every_tf():
    for L in (300, 900, 3600, 14400, 86400):
        opens = np.array([CUT - L - 1, CUT - L, CUT - L + 1, CUT - 1, CUT, CUT + 1], np.int64)
        u = K.usable_bars(opens, L, CUT)
        assert list(u) == [True, True, False, False, False, False], (L, u)
    straddle = int(pd.Timestamp("2026-10-02 22:00:00").timestamp())          # H1 22:00-23:00 straddles the 22:15 cut
    assert not K.usable_bars([straddle], 3600, CUT)[0]
    print("PASS C1 bars: only bars closed by the cut inform it (M5, M15, H1, H4, D1; straddling H1 excluded)")


def test_cost():
    c = K.cost_bp("XAUUSD", [0.5, 1.5, np.nan])
    assert np.allclose(c, [2.0, 2.5, 2.0]), c
    assert np.allclose(K.cost_bp("XAUUSD", [0.5], stress=True), [4.0])
    t = [int(pd.Timestamp("2020-06-01").timestamp()), int(pd.Timestamp("2024-06-03").timestamp())]
    c = K.cost_bp("XAGUSD", [9.0, 2.0], entry_t=t, xag_pre2023_const=6.5)
    assert np.allclose(c, [6.5, 4.0]), c
    print("PASS C4 cost: XAU floor 2 bp, spread + 1 bp, stress + 2 bp; XAG pre-2023 constant, 2023+ floor 4 bp")


def test_swap():
    tue = int(pd.Timestamp("2026-09-22 10:00:00").timestamp()); thu = int(pd.Timestamp("2026-09-24 10:00:00").timestamp())
    y2 = K._y2_series()
    r_tue = y2[y2.index < pd.Timestamp("2026-09-22")].iloc[-1] + K.MARKUP_PP["XAUUSD"]
    r_wed = y2[y2.index < pd.Timestamp("2026-09-23")].iloc[-1] + K.MARKUP_PP["XAUUSD"]
    expect = (1 * r_tue + 3 * r_wed) / 100 / 365 * 1e4
    got = K.swap_bp("XAUUSD", [tue, tue], [thu, thu], [1.0, -1.0])
    assert abs(got[0] - expect) < 1e-9 and got[1] == 0.0, (got, expect)
    fri = int(pd.Timestamp("2026-09-25 10:00:00").timestamp()); mon = int(pd.Timestamp("2026-09-28 10:00:00").timestamp())
    r_fri = y2[y2.index < pd.Timestamp("2026-09-25")].iloc[-1] + K.MARKUP_PP["XAUUSD"]
    got = K.swap_bp("XAUUSD", [fri], [mon], [1.0])
    assert abs(got[0] - r_fri / 100 / 365 * 1e4) < 1e-9, got           # only Friday's rollover; weekend none
    print("PASS C4 swap: Tue 1 night + Wed 3 nights with the prior Treasury date's yield; shorts 0; weekend 0")


def test_vol_scale_causal():
    sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
    import engine as E
    H, _, cuts, _ = E.load()
    k0 = 900
    full = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts)
    cut_t = cuts[k0]
    m = H.t + 3600 <= cut_t
    part = K.causal_vol_scale(H.t[m], H.c[m], H.h[m], H.l[m], cuts)
    assert np.allclose(full[:k0 + 1], part[:k0 + 1]), "vol_scale uses data after the cut"
    print(f"PASS C3 vol_scale: identical up to cut {k0} when later bars are removed; range {full.min():.2f}..{full.max():.2f}")


if __name__ == "__main__":
    for f in (test_entry_week, test_known_at_cut, test_usable_bars_every_tf, test_cost, test_swap, test_vol_scale_causal):
        f()
    print("ALL CONTRACT TESTS PASS")
