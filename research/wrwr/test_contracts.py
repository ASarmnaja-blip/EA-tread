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
    c = K.cost_bp("XAGUSD", [9.0, 2.0], entry_t=t)
    assert np.allclose(c, [K.xag_pre2023_constant(), 4.0]), c              # pre-2023: frozen constant; 2023+: max(4, spread + 1)
    assert abs(K.xag_pre2023_constant() - 11.615057998215441) < 1e-9
    try:
        K.cost_bp("XAGUSD", [9.0]); raise AssertionError("XAG without entry_t must fail closed")
    except ValueError:
        pass
    saved = K.XAG_FREEZE_FILE
    K.XAG_FREEZE_FILE = K.ROOT / "data" / "foundry" / "missing_freeze.json"; K._XAG.clear()
    try:
        K.cost_bp("XAGUSD", [9.0], entry_t=[t[0]]); raise AssertionError("missing freeze file must fail closed")
    except FileNotFoundError:
        pass
    finally:
        K.XAG_FREEZE_FILE = saved; K._XAG.clear()
    print("PASS C4 cost: XAU floor 2 bp, spread + 1 bp, stress + 2 bp; XAG frozen pre-2023 constant, fail closed without inputs")


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
    fwd = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, mode="forward")
    assert fwd.min() >= 0.5 and fwd.max() <= 1.0 and not np.allclose(fwd, full)
    try:
        K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, bar_seconds=14400); raise AssertionError("H4 bars must be refused")
    except ValueError:
        pass
    print(f"PASS C3 vol_scale: causal (identical up to cut {k0}), historical {full.min():.2f}..{full.max():.2f}, "
          f"frozen-forward mode differs, non-H1 bars refused")


def test_mark_price():
    bc = np.array([100, 200, 300]); px = np.array([1.0, 2.0, 3.0])
    m = K.mark_price(bc, px, [99, 100, 199, 200, 10_000])
    assert np.isnan(m[0]) and list(m[1:]) == [1.0, 1.0, 2.0, 3.0], m
    print("PASS C2 mark price = close of the last bar closed at or before t")


def _synth(n_a=900, n_b=900, off_bp=0.0, sp_b=1.0, jump=0.0, dup=False, gap_at=None, gap_days=5, seed=1):
    rng = np.random.default_rng(seed)
    seam = int(pd.Timestamp("2024-06-03 00:00:00").timestamp())
    tb = seam + np.arange(n_b) * 3600
    ta = seam - (n_a - np.arange(n_a)) * 3600
    # keep weekends out: drop Saturday and most of Sunday bars on the whole line
    dow = lambda t: pd.to_datetime(t, unit="s").dayofweek.to_numpy()                # 0 = Monday
    ok = lambda t: ~((dow(t) == 5) | ((dow(t) == 6) & ((t % 86400) < 22 * 3600)) | ((dow(t) == 4) & ((t % 86400) >= 22 * 3600)))
    ta, tb = ta[ok(ta)], tb[ok(tb)]
    base_t = np.r_[ta, tb] if False else None
    allt = np.union1d(ta, tb)
    px = 2000 * np.exp(np.cumsum(rng.normal(0, 0.0008, len(allt))))
    pmap = dict(zip(allt.tolist(), px))
    ca = np.array([pmap[int(t)] for t in ta]); cb = np.array([pmap[int(t)] for t in tb])
    # overlap: source B also has the last 4 weeks before the seam (shifted by off_bp)
    tb_pre = ta[ta >= seam - 28 * 86400]; cb_pre = np.array([pmap[int(t)] for t in tb_pre]) * (1 - off_bp / 1e4)
    tB = np.r_[tb_pre, tb]; cB = np.r_[cb_pre, cb * (1 - off_bp / 1e4)]
    cB = cB.copy()
    if jump:
        cB[len(tb_pre):] *= (1 + jump)
    if gap_at is not None:
        keep = ~((tB >= seam + gap_at * 86400) & (tB < seam + (gap_at + gap_days) * 86400))
        tB, cB = tB[keep], cB[keep]
    if dup:
        tB = tB.copy(); tB[len(tb_pre) + 5] = tB[len(tb_pre) + 4]
    A = dict(t=ta, c=ca, o=ca, sp=np.full(len(ta), 1.0))
    B = dict(t=tB, c=cB, o=cB, sp=np.full(len(tB), sp_b))
    return A, B, seam


def test_validate_seam():
    A, B, seam = _synth()
    r = K.validate_seam(A, B, seam)
    assert all(v[0] for v in r.values()), r
    bad = {"offset 5 bp": dict(off_bp=5.0), "spread x3": dict(sp_b=3.0), "price jump 2%": dict(jump=0.02), "5-day gap": dict(gap_at=8, gap_days=5)}
    for nm, kw in bad.items():
        A2, B2, seam2 = _synth(**kw)
        r2 = K.validate_seam(A2, B2, seam2, strict=False)
        assert not all(v[0] for v in r2.values()), (nm, r2)
    A3, B3, seam3 = _synth(dup=True)
    try:
        K.validate_seam(A3, B3, seam3); raise AssertionError("duplicate timestamps must be rejected")
    except ValueError:
        pass
    print("PASS C5 splice validator: clean seam passes; offset, spread ratio, jump, gap and duplicate timestamps are rejected")


def test_digests():
    assert K.holiday_sha() == K.HOLIDAY_SHA and len(K.holidays()) == 352
    assert K.symbols_sha() == K.SYMBOLS_SHA and K.treasury_sha() == K.TREASURY_SHA
    raw = K.HOLIDAY_FILE.read_bytes()
    assert chr(13).encode() not in raw, "holiday file must be LF"
    print("PASS C5 pinned digests: holiday list (LF-normalised), symbol JSON, Treasury snapshot")


if __name__ == "__main__":
    for f in (test_entry_week, test_known_at_cut, test_usable_bars_every_tf, test_cost, test_swap, test_vol_scale_causal,
              test_mark_price, test_validate_seam, test_digests):
        f()
    print("ALL CONTRACT TESTS PASS")
