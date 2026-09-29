"""Measure the tail quantities the H3/H4/H6 rules need, once, so they can be
frozen as constants in riskrules.py.

These are DESCRIPTIVE risk quantities (how big is a weekend gap, how far can
price move in the news minute, what does the broker require as margin) — not
parameters tuned to make a strategy profitable. They are read off the data and
then frozen; they are never re-fitted to improve a result.

Outputs the constants block to paste into riskrules.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402


def weekend_gaps(m, cuts):
    """Adverse move from the last quote before a cut to the first quote after,
    in bp. Sign kept: + means gold opened higher (bad for a short)."""
    out = []
    for c in cuts:
        before = np.flatnonzero(m.t < c)
        after = np.flatnonzero(m.t >= c)
        if not len(before) or not len(after):
            continue
        i, j = before[-1], after[0]
        if m.t[j] - m.t[i] < 24 * 3600:          # not a real weekend break
            continue
        out.append(dict(cut=int(c), gap_bp=(m.o[j] / m.c[i] - 1) * 1e4,
                        hours_closed=(m.t[j] - m.t[i]) / 3600))
    return pd.DataFrame(out)


def news_jumps():
    f = BR.WEEKLY_DIR / "news_tick_spread.csv"
    if not f.exists():
        return None
    return pd.read_csv(f)


def broker_specs():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None
    if not mt5.initialize():
        return None
    try:
        a = mt5.account_info(); s = mt5.symbol_info("XAUUSD")
        if a is None or s is None:
            return None
        out = dict(server=a.server, trade_mode=int(a.trade_mode), leverage=int(a.leverage),
                   so_call=float(a.margin_so_call), so_so=float(a.margin_so_so),
                   contract=float(s.trade_contract_size), vol_min=float(s.volume_min),
                   vol_step=float(s.volume_step), price=float(s.ask),
                   stops_level_points=int(s.trade_stops_level), point=float(s.point))
        for lot in (0.01, 0.03, 0.10):
            m = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, "XAUUSD", lot, s.ask)
            out[f"margin_{lot}"] = float(m) if m is not None else np.nan
        return out
    finally:
        mt5.shutdown()


def main() -> int:
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    lab = np.array([V.label(f[k] / med[k])[1] if np.isfinite(med[k]) and np.isfinite(f[k]) else "U"
                    for k in range(len(rv))])

    g = weekend_gaps(m, cuts)
    a = g.gap_bp.abs()
    print(f"=== H3 weekend gaps: n={len(g)}, closed {g.hours_closed.median():.0f} h median")
    for q in (0.5, 0.9, 0.95, 0.99):
        print(f"  |gap| q{q:.2f} = {a.quantile(q):7.1f} bp")
    print(f"  max {a.max():.1f} bp on {pd.to_datetime(g.loc[a.idxmax(), 'cut'], unit='s').date()}")
    lab_at = pd.Series(lab, index=cuts).reindex(g.cut).to_numpy()
    for cls in ("CALM", "NORMAL", "HIGH", "EXTREME"):
        sel = a[lab_at == cls]
        if len(sel) >= 5:
            print(f"  forecast {cls:8s} n={len(sel):3d}  median {sel.median():5.1f}  p95 {sel.quantile(.95):6.1f}  max {sel.max():6.1f} bp")

    nj = news_jumps()
    if nj is not None and len(nj):
        print(f"\n=== H4 news-minute jumps: n={len(nj)} releases ({nj.time.min()} .. {nj.time.max()})")
        for q in (0.5, 0.9, 0.95, 0.99):
            print(f"  1-min |move| q{q:.2f} = {nj.jump_1m_bp.quantile(q):7.1f} bp")
        print(f"  max {nj.jump_1m_bp.max():.1f} bp; spread max ${nj.spread_max_window.max():.3f} "
              f"(x{(nj.spread_max_window / nj.spread_pre_median).max():.0f})")
        TIER1 = ("Nonfarm Payrolls", "CPI m/m", "Fed Interest Rate Decision", "Core PCE Price Index m/m")
        t1 = nj[nj.events.apply(lambda s: any(k in str(s) for k in TIER1))]
        if len(t1):
            print(f"  tier-1 only (n={len(t1)}): median {t1.jump_1m_bp.median():.1f}, "
                  f"p95 {t1.jump_1m_bp.quantile(.95):.1f}, max {t1.jump_1m_bp.max():.1f} bp")

    bs = broker_specs()
    print(f"\n=== H6 broker specs: {bs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
