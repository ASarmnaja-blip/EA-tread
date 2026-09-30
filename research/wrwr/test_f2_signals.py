"""Unit and leak tests of the Family 2 signal definitions (docs/WRWR_FAMILY2_PREREG.md). Run directly; raises on failure."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import f2_signals as F2  # noqa: E402
import signals as SG  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

T0 = int(pd.Timestamp("2026-03-02 00:00:00").timestamp())          # a Monday 00:00 UTC (no DST change near)
CUTS = np.array([int(pd.Timestamp("2026-02-27 22:15:00").timestamp()), int(pd.Timestamp("2026-03-06 22:15:00").timestamp()),
                 int(pd.Timestamp("2026-03-13 22:15:00").timestamp())], np.int64)


def mkB(o, h, l, c, t0=T0, step=3600, t=None):
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    tt = t0 + np.arange(len(c)) * step if t is None else np.asarray(t, np.int64)
    return SimpleNamespace(t=tt, o=o, h=h, l=l, c=c, v=np.ones(len(c)), step=step, atr=E._atr(h, l, c, 14))


def flat(n, px=100.0, rng=1.0):
    c = np.full(n, px); return c.copy(), c + rng / 2, c - rng / 2, c.copy()


def ev(S, name):
    lg, sh = S[name]
    return list(np.flatnonzero(lg)), list(np.flatnonzero(sh))


def _gap_series(n, expiry=False):
    """Flat series with one bull FVG: bar 19 is a tall bull bar (so later bars do not gap against it), bar 20 opens the gap:
    zone lower = high[18] = 100.5, upper = low[20] = 105; bars 21.. trade above the zone."""
    o, h, l, c = flat(n)
    o[19], h[19], l[19], c[19] = 100.5, 107.5, 100.0, 107.0
    o[20], h[20], l[20], c[20] = 106.8, 107.8, 105.0, 107.5
    for i in range(21, n):
        o[i], h[i], l[i], c[i] = 107, 108, 106.5, 107
    return o, h, l, c


def test_fvg_form_and_retest():
    o, h, l, c = _gap_series(40)
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert 20 in ev(S, "fvg_form")[0] and ev(S, "fvg_form")[0] == [20], ev(S, "fvg_form")
    # retest at bar 25 (low 104.5 <= upper 105, close 106 > lower 100.5); a second dip at 27 must not fire again
    o[25], h[25], l[25], c[25] = 107, 107.5, 104.5, 106
    o[27], h[27], l[27], c[27] = 107, 107.5, 104.6, 106
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert ev(S, "fvg_retest")[0] == [25], ev(S, "fvg_retest")
    # filled zone: bar 25 trades down to the lower edge (100.4 <= 100.5) -> no event
    l2 = l.copy(); l2[25] = 100.4
    S = F2.f2_signals(mkB(o, h, l2, c), CUTS)
    assert ev(S, "fvg_retest")[0] == [], ev(S, "fvg_retest")
    # expiry: a retest 26 bars after creation (bar 46) is ignored; 20 bars after (bar 40) still counts
    o3, h3, l3, c3 = _gap_series(60)
    l3[46] = 104.5
    S = F2.f2_signals(mkB(o3, h3, l3, c3), CUTS)
    assert ev(S, "fvg_retest")[0] == [], ev(S, "fvg_retest")
    o4, h4, l4, c4 = _gap_series(60)
    l4[40] = 104.5
    S = F2.f2_signals(mkB(o4, h4, l4, c4), CUTS)
    assert ev(S, "fvg_retest")[0] == [40], ev(S, "fvg_retest")
    # bear side mirror: flip prices around 200
    S = F2.f2_signals(mkB(200 - o, 200 - l, 200 - h, 200 - c), CUTS)
    assert ev(S, "fvg_form")[1] == [20] and ev(S, "fvg_retest")[1] == [25], (ev(S, "fvg_form"), ev(S, "fvg_retest"))
    print("PASS fvg_form / fvg_retest: one event at the first retest, filled zones silent, 20-bar life, bear mirror")


def test_sweep_disp_ob():
    o, h, l, c = flat(80)
    # 20-bar sweep: bar 30 low pierces the 20-bar low (99.5) and closes back above it
    o[30], h[30], l[30], c[30] = 100, 100.6, 98.5, 100.2
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert 30 in ev(S, "sweep20")[0]
    o, h, l, c = flat(80)
    o[30], h[30], l[30], c[30] = 100, 101.5, 99.6, 100.4
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert 30 in ev(S, "sweep20")[1]                                        # high pierces, closes back below -> short
    # displacement + order block: bearish bar 40, big bull bar 41 (range 5 > 2 x ATR=1, body 4.6 > 60%, close top 25%)
    o, h, l, c = flat(80)
    o[40], h[40], l[40], c[40] = 100.2, 100.4, 99.4, 99.6                   # bearish candle = order block [99.4, 100.4]
    o[41], h[41], l[41], c[41] = 99.6, 104.8, 99.6, 104.6
    for i in range(42, 50):
        o[i], h[i], l[i], c[i] = 104.6, 105, 104.2, 104.6
    o[50], h[50], l[50], c[50] = 104.6, 104.8, 100.0, 101.0                 # dips into the block, closes above its low
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert 41 in ev(S, "disp")[0] and ev(S, "ob_retest")[0] == [50], (ev(S, "disp"), ev(S, "ob_retest"))
    c2 = c.copy(); c2[45] = 99.0                                             # close below the block low invalidates it
    S = F2.f2_signals(mkB(o, h, l, c2), CUTS)
    assert ev(S, "ob_retest")[0] == []
    print("PASS sweep20 (both sides), disp, ob_retest (zone, single retest, invalidation)")


def test_levels_and_gap():
    # three trading days of 24 hourly bars: day 1 range 99..101, day 2 opens with a gap up, day 3 breaks day 2's high
    n = 24 * 4
    t = T0 + 22 * 3600 + np.arange(n) * 3600                               # starts Monday 22:00 UTC = start of a trading day
    o, h, l, c = flat(n)
    # day 2 starts at bar 24: gap up of 3 (ATR ~1) -> gap_day long
    for i in range(24, 48):
        o[i], h[i], l[i], c[i] = 103, 103.5, 102.5, 103
    o[24] = 103
    for i in range(48, 72):
        o[i], h[i], l[i], c[i] = 103, 103.5, 102.5, 103
    o[60], h[60], l[60], c[60] = 103, 105, 102.9, 104.8                    # crosses above day 2's high (103.5)
    S = F2.f2_signals(mkB(o, h, l, c, t=t), CUTS)
    assert 24 in ev(S, "gap_day")[0], ev(S, "gap_day")
    assert 60 in ev(S, "pd_break")[0], ev(S, "pd_break")
    # round50: close crosses 150 upward then downward
    o, h, l, c = flat(40, px=149.0)
    c[20] = 150.5; h[20] = 151; l[20] = 149.0; o[20] = 149.2
    c[21:] = 150.4; h[21:] = 151; l[21:] = 149.9; o[21:] = 150.4
    c[30] = 149.4; l[30] = 149.0
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    up, dn = ev(S, "round50_x")
    assert 20 in up and 30 in dn, (up, dn)
    print("PASS gap_day, pd_break, round50_x")


def test_structure():
    # zigzag with clear fractal(2,2) swings: up-leg, peak at 10, pullback to 16, rally through the peak at 22 (BOS up)
    px = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 109, 108, 107, 106, 105, 104, 105, 106, 107, 108, 109, 111, 112]
    c = np.array(px, float); o = c - 0.3; h = c + 0.5; l = c - 0.5
    pad = 20
    o = np.r_[np.full(pad, 100.0), o]; h = np.r_[np.full(pad, 100.5), h]; l = np.r_[np.full(pad, 99.5), l]; c = np.r_[np.full(pad, 100.0), c]
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    bos = ev(S, "bos")[0]
    assert len(bos) >= 1 and all(b >= pad + 10 for b in bos), bos         # only after the swing high at pad+10 is confirmed
    # CHoCH: a down-break after an up structure
    px2 = px + [110, 108, 106, 104, 102, 100, 98, 96]
    c = np.array(px2, float); o = c + 0.3; h = c + 0.5; l = c - 0.5
    o = np.r_[np.full(pad, 100.0), o]; h = np.r_[np.full(pad, 100.5), h]; l = np.r_[np.full(pad, 99.5), l]; c = np.r_[np.full(pad, 100.0), c]
    S = F2.f2_signals(mkB(o, h, l, c), CUTS)
    assert len(ev(S, "choch")[1]) >= 1, ev(S, "choch")
    print("PASS bos / choch on a constructed zig-zag")


def test_calendar():
    # London 10:30: winter (UTC = London) next bar 10:00 UTC -> event at the 09:00 UTC bar; summer (BST) -> 08:00 UTC bar
    for date, hour in (("2026-01-14", 9), ("2026-07-15", 8)):
        t = int(pd.Timestamp(f"{date} 00:00:00").timestamp()) + np.arange(24) * 3600
        o, h, l, c = flat(24)
        S = F2.f2_signals(mkB(o, h, l, c, t=t), CUTS)
        assert ev(S, "fix_am")[0] == [hour], (date, ev(S, "fix_am"))
    # NY 09:30 New York: winter 14:30 UTC (bar 14:00 is next -> event at 13:00), summer 13:30 UTC (event at 12:00)
    for date, hour in (("2026-01-14", 13), ("2026-07-15", 12)):
        t = int(pd.Timestamp(f"{date} 00:00:00").timestamp()) + np.arange(24) * 3600
        o, h, l, c = flat(24)
        S = F2.f2_signals(mkB(o, h, l, c, t=t), CUTS)
        assert ev(S, "ny_open")[0] == [hour], (date, ev(S, "ny_open"))
    # turn of month: January 2026 ends Saturday -> last trading day = Friday 2026-01-30; its day starts Thursday 22:00 UTC,
    # so the event sits on the bar before: Thursday 21:00 UTC
    start = int(pd.Timestamp("2026-01-26 00:00:00").timestamp())
    ts = start + np.arange(24 * 9) * 3600
    wd = pd.to_datetime(ts, unit="s").dayofweek.to_numpy()                      # 0 = Monday
    ts = ts[(wd < 5) & ~((wd == 4) & ((ts % 86400) >= 22 * 3600))]             # drop Friday 22:00 .. Sunday
    o, h, l, c = flat(len(ts))
    S = F2.f2_signals(mkB(o, h, l, c, t=ts), CUTS)
    idx = ev(S, "tom")[0]
    assert len(idx) == 1 and pd.Timestamp(ts[idx[0]], unit="s") == pd.Timestamp("2026-01-29 21:00:00"), [pd.Timestamp(ts[i], unit="s") for i in idx]
    print("PASS fix_am / ny_open (DST-aware) and tom (last trading day of the month, 22:00 UTC day anchor)")


def garbage_after(B, j, rng):
    G = copy.copy(B)
    n = len(B.t)
    for f in ("o", "h", "l", "c", "v"):
        a = np.asarray(getattr(B, f), float).copy()
        a[j + 1:] = a[j + 1:] * rng.uniform(0.5, 1.5, n - j - 1)
        setattr(G, f, a)
    hi = np.maximum.reduce([G.o, G.h, G.l, G.c]); lo = np.minimum.reduce([G.o, G.h, G.l, G.c])
    G.h = np.r_[B.h[: j + 1], hi[j + 1:]]; G.l = np.r_[B.l[: j + 1], lo[j + 1:]]
    G.atr = E._atr(G.h, G.l, G.c, 14)
    return G


def test_leak_real_data():
    rng = np.random.default_rng(5)
    for tf in ("H1", "H4", "D1"):
        B, cuts, _ = SG.load_xau(tf)
        n = len(B.t)
        base = F2.f2_signals(B, cuts)
        for j in (n // 6, n // 2, n - 400):
            G = garbage_after(B, j, rng)
            sig = F2.f2_signals(G, cuts)
            bad = [k for k in base if not (np.array_equal(base[k][0][: j + 1], sig[k][0][: j + 1])
                                           and np.array_equal(base[k][1][: j + 1], sig[k][1][: j + 1]))]
            assert not bad, f"{tf} f2 signals leak at j={j}: {bad}"
        print(f"PASS {tf}: {len(base)} Family-2 signals unchanged up to bar j when later bars are garbage ({n:,} bars, 3 cut points)")


if __name__ == "__main__":
    for t_ in (test_fvg_form_and_retest, test_sweep_disp_ob, test_levels_and_gap, test_structure, test_calendar, test_leak_real_data):
        t_()
    print("ALL FAMILY-2 SIGNAL TESTS PASS")
