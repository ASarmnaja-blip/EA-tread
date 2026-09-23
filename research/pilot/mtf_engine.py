"""Multi-timeframe / geometry / entry-expiry engine, implementing Amendment 14.

Sweeps the three dimensions this project has never varied:

    signal timeframe   M5, M15, M30, H1, H4   (every tool so far is M15-only)
    barrier geometry   stop 0.75-3.0 ATR x target 0.5-3.0 R  (always 1.5 / 1:1)
    entry mode         market, or a limit 0.50/1.00 ATR away valid 5/8/10/12/15
                       signal bars (entry has always been the next bar's open)

over the six setup families CLAUDE.md section 3 asks for, five of which have never
appeared in any search here. Their internal parameters are NOT swept: that is the
dimension Amendments 10 and 11 closed.

    6 setups x 5 timeframes x 5 stops x 5 targets x 11 entry modes = 8,250 cells

EVERYTHING EXECUTES ON M5, whatever timeframe the signal came from, so a slower
signal does not get a cheaper fill by accident. A signal timeframe only decides
when a decision may be made.

ENTRY MODES, exactly. A market entry is the next bar's open. A limit mode places
the order `offset` ATR BETTER than the signal bar's close - below it for a long,
above it for a short - valid N bars of the SIGNAL timeframe. It fills only if price
comes back to it, and if it never does there is NO TRADE. That last clause is the
whole point: the variant asks the signal to wait for a better price and pays by
missing 24 to 48 percent of its signals outright, which is a measured cost rather
than an invisible one. The expiry rate is reported per cell.

WORST-CASE RESOLUTION throughout: the stop is tested before the target on every M5
bar, so a bar covering both is a loss. That rule is applied to candidate and
placebo alike.

This module computes. It makes no claim, names no candidate, and reads no holdout.
Amendment 14 section 6 requires test_mtf_engine.py to pass before it is run in
anger.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

# ---------------------------------------------------------------- the grid
TIMEFRAMES = (("M5", 1), ("M15", 3), ("M30", 6), ("H1", 12), ("H4", 48))
STOPS = (0.75, 1.0, 1.5, 2.0, 3.0)          # in ATR of the signal timeframe
TARGETS = (0.5, 1.0, 1.5, 2.0, 3.0)         # in R
# Entry modes: (limit offset in ATR, expiry in signal bars). Offset 0 with
# expiry 0 is a market order at the next bar's open.
#
# The offsets are NOT decoration. The first design used a limit at the signal
# bar's close, and measured on real XAUUSD that limit was touched almost
# immediately: the expiry rate was 1 percent at every N, so the five expiry
# values produced identical cells and a declared N of 4,500 would have been a
# fiction. Measured expiry rates are 24-16 percent at 0.50 ATR and 48-32 percent
# at 1.00 ATR, which is where the dimension starts to mean something. See
# Amendment 14 section 6a.
ENTRY_MODES = (((0.0, 0),)
               + tuple((0.50, e) for e in (5, 8, 10, 12, 15))
               + tuple((1.00, e) for e in (5, 8, 10, 12, 15)))
SETUPS = ("breakout", "pullback", "sweep", "failed", "vwap", "expansion")

TIME_STOP_M5 = 288        # 24 h, deliberately generous so it rarely binds
ATR_N = 14

# ---------------------------------------------- measured costs, Amendment 08
SPREAD_FALLBACK = 0.090
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_LONG = 0.5493
SWAP_SHORT = 0.0
ROLLOVER_H = 21


def rollover_nights(t0: int, t1: int) -> int:
    """Count 21:00 UTC rollover instants in the real interval [t0, t1]."""
    day0 = t0 - (t0 % 86400)
    cur = day0 + ROLLOVER_H * 3600
    if cur < t0:
        cur += 86400
    nights = 0
    while cur <= t1:
        nights += 1
        cur += 86400
    return nights


def n_cells() -> int:
    return (len(SETUPS) * len(TIMEFRAMES) * len(STOPS) * len(TARGETS)
            * len(ENTRY_MODES))


def spread_at(b5: D.Bars, k: int) -> float:
    if b5.sp is not None and np.isfinite(b5.sp[k]) and b5.sp[k] > 0:
        return max(float(b5.sp[k]), SPREAD_FALLBACK)
    return SPREAD_FALLBACK


# ================================================================ resampling
def resample(b5: D.Bars, mult: int) -> tuple[D.Bars, np.ndarray]:
    """Build bars of `mult` x 5 minutes from M5, and the index of the first M5
    bar that may be traded on.

    A bar exists only when ALL `mult` of its M5 bars are present and contiguous,
    so a bar spanning a session break is never manufactured - the same rule
    data.to_15m uses, generalised. A bar LABELLED t covers [t, t + mult*300) and
    CLOSES at the end of that window; the returned index points at the M5 bar
    starting at t + mult*300, which is the first bar a decision taken on this
    bar's close could act on. Pointing it anywhere earlier is the look-ahead the
    research log records, and test_mtf_engine.py checks for it.
    """
    assert b5.step == 300
    if mult == 1:
        nxt = np.arange(1, len(b5) + 1)
        nxt[-1] = -1
        return b5, nxt
    span = mult * 300
    t = b5.t
    n = len(b5)
    ot, oo, oh, ol, oc, ov, osp = [], [], [], [], [], [], []
    i = 0
    has_sp = b5.sp is not None
    while i + mult - 1 < n:
        if t[i] % span != 0:
            i += 1
            continue
        block = t[i:i + mult]
        if not np.all(block == t[i] + np.arange(mult) * 300):
            i += 1
            continue
        ot.append(int(t[i]))
        oo.append(b5.o[i])
        oh.append(float(np.max(b5.h[i:i + mult])))
        ol.append(float(np.min(b5.l[i:i + mult])))
        oc.append(b5.c[i + mult - 1])
        ov.append(float(np.sum(b5.v[i:i + mult])))
        if has_sp:
            osp.append(float(np.nanmedian(b5.sp[i:i + mult])))
        i += mult
    out = D.Bars(np.array(ot, np.int64), np.array(oo), np.array(oh),
                 np.array(ol), np.array(oc), np.array(ov), span, b5.symbol,
                 np.array(osp) if has_sp else None)
    want = out.t + span
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < n) & (b5.t[np.minimum(pos, n - 1)] == want), pos, -1)
    return out, nxt


# ================================================================ setups
def setup_signals(name: str, c: core.Ctx) -> list[tuple[int, int]]:
    """(bar index, direction) only. The stop and target baked into core's
    setups are DISCARDED here, because Amendment 14 imposes its own geometry -
    keeping theirs would silently pin two of the swept dimensions."""
    fn = {
        "breakout": core.s1_breakout,
        "pullback": core.s2_pullback,
        "sweep": core.s3_sweep,
        "failed": core.s4_failed,
        "vwap": core.s5_vwap,
        "expansion": core.s6_expansion,
    }[name]
    return [(int(s[0]), int(s[1])) for s in fn(c)]


# ================================================================ execution
def entry_fill_detail(b5: D.Bars, k0: int, d: int, limit: float,
                      bars_m5: int):
    """Return ``(bar, price, filled_at_open)`` for a limit order.

    The open-through check is required on every eligible bar, not only the
    first one: a session gap can occur while a pending order is still alive.
    """
    end = min(k0 + bars_m5, len(b5))
    for k in range(k0, end):
        if d > 0:
            # MT5 FX/metals bars are Bid bars; a buy order fills on Ask.
            sp = spread_at(b5, k)
            if b5.o[k] + sp <= limit:
                return k, float(b5.o[k] + sp), True
            if b5.l[k] + sp <= limit:
                return k, float(limit), False
        else:
            if b5.o[k] >= limit:
                return k, float(b5.o[k]), True
            if b5.h[k] >= limit:
                return k, float(limit), False
    return None


def entry_fill(b5: D.Bars, k0: int, d: int, limit: float, bars_m5: int):
    """Where a limit at `limit` fills within `bars_m5` M5 bars from k0, or None.

    A long fills when price trades DOWN to the limit, a short when it trades UP
    to it. The fill price is the limit itself, except when an eligible bar opens
    through it, in which case the open is the honest fill - a limit cannot
    fill better than the market gives.
    """
    got = entry_fill_detail(b5, k0, d, limit, bars_m5)
    return None if got is None else got[:2]


def run_cell(bs: D.Bars, nxt: np.ndarray, atr_s: np.ndarray,
             signals: list[tuple[int, int]], b5: D.Bars,
             stop_atr: float, target_r: float, entry_mode: tuple,
             mult: int, cost_mult: float = 1.0):
    """One cell of the grid. Returns per-trade records plus expiry statistics."""
    rows = []
    n_expired = 0
    n_tried = 0
    busy_until_m5 = -1
    for (i, d) in signals:
        k0 = int(nxt[i])
        a = atr_s[i]
        if k0 < 0 or not np.isfinite(a) or a <= 0:
            continue
        n_tried += 1
        risk = stop_atr * float(a)
        offset, expiry_bars = entry_mode
        if expiry_bars == 0:
            k = k0
            entry = float(b5.o[k0] + (spread_at(b5, k0) if d > 0 else 0.0))
            at_open = True
        else:
            # the limit sits `offset` ATR in the trader's favour: below the close
            # for a long, above it for a short
            limit = float(bs.c[i]) - d * offset * float(a)
            got = entry_fill_detail(b5, k0, d, limit, expiry_bars * mult)
            if got is None:
                n_expired += 1
                continue
            k, entry, at_open = got
        if k <= busy_until_m5:
            continue
        # With M5 OHLC alone, the high preceding an intrabar limit fill cannot
        # be distinguished from a high after it.  Never credit a target on that
        # entry bar.  A stop remains valid: moving from the open through the
        # limit and then beyond the stop necessarily crosses both in that order.
        g, why, nb = resolve_plane(
            b5, k, d, entry, float(a), (stop_atr,), (target_r,), TIME_STOP_M5,
            allow_entry_bar_target=at_open)[(stop_atr, target_r)]
        # Spread is embedded in the Ask entry/exit path.
        cost = cost_mult * (COMMISSION_RT + 2.0 * SLIP_PER_FILL)
        net = g - cost / risk
        t0 = int(b5.t[k])
        sw = SWAP_LONG if d > 0 else SWAP_SHORT
        if sw:
            # Bar counts are not elapsed wall time across a weekend/session
            # break.  Rollover is charged by actual timestamps.
            t1 = int(b5.t[min(k + nb, len(b5) - 1)])
            nights = rollover_nights(t0, t1)
            net -= nights * sw / risk
        rows.append(dict(i=i, k=k, t=t0, order_k=k0,
                         order_t=int(b5.t[k0]), d=d, g=g, net=net, why=why,
                         nb=nb, day=t0 // 86400, risk=risk))
        busy_until_m5 = k + nb
    return dict(rows=rows, n_expired=n_expired, n_tried=n_tried,
                expiry_rate=(n_expired / n_tried) if n_tried else float("nan"),
                time_stop_rate=(np.mean([r["why"] == "time" for r in rows])
                                if rows else float("nan")))


def cells():
    """Every cell of the declared grid, in a fixed order."""
    for s in SETUPS:
        for (tfname, mult) in TIMEFRAMES:
            for st in STOPS:
                for tg in TARGETS:
                    for (off, ex) in ENTRY_MODES:
                        yield dict(setup=s, tf=tfname, mult=mult, stop=st,
                                   target=tg, entry_mode=(off, ex),
                                   offset=off, expiry=ex,
                                   tag=f"{s}/{tfname}/s{st:g}/t{tg:g}"
                                       f"/o{off:g}e{ex}")


# ======================================================== fast resolution
# 8,250 cells x ~2,000 fills x core.resolve walking up to 288 bars is tens of
# millions of Python-level bar steps, which is hours. But for one fill the whole
# (stop, target) plane can be answered from ONE forward pass: the stop is hit at
# the first bar whose adverse excursion crosses stop_atr, the target at the first
# bar whose favourable excursion crosses stop_atr * target_r, and a tie goes to
# the stop. So the fill's running extremes are computed once with numpy and every
# geometry is read off by searchsorted.
#
# test_mtf_engine.py check 9 asserts this agrees with core.resolve exactly,
# because a fast path that quietly disagrees with the reference is worse than no
# fast path at all.

def first_cross(cummax: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Index of the first bar at which a non-decreasing running maximum reaches
    each threshold, or len(cummax) when it never does."""
    return np.searchsorted(cummax, thresholds, side="left")


def resolve_plane(b5: D.Bars, k: int, d: int, entry: float, atr_unit: float,
                  stops: tuple, targets: tuple, time_stop: int,
                  allow_entry_bar_target: bool = True):
    """Gross R and exit reason for every (stop, target) pair, from one pass.

    Returns dict[(stop, target)] = (gross_R, why, bars_held).
    """
    end = min(k + time_stop, len(b5))
    if end <= k:
        return {}
    hi = b5.h[k:end]
    lo = b5.l[k:end]
    if d > 0:
        fav = (hi - entry) / atr_unit
        adv = (entry - lo) / atr_unit
        last_c = float(b5.c[end - 1])
    else:
        if b5.sp is None:
            spreads = np.full(end - k, SPREAD_FALLBACK)
        else:
            spreads = np.maximum(b5.sp[k:end], SPREAD_FALLBACK)
        ask_hi = hi + spreads
        ask_lo = lo + spreads
        fav = (entry - ask_lo) / atr_unit
        adv = (ask_hi - entry) / atr_unit
        last_c = float(b5.c[end - 1] + spreads[-1])
    if not allow_entry_bar_target and len(fav):
        fav = fav.copy()
        fav[0] = -np.inf
    fav_c = np.maximum.accumulate(fav)
    adv_c = np.maximum.accumulate(adv)
    nb_last = end - k - 1
    out = {}
    for st in stops:
        j_stop = int(first_cross(adv_c, np.array([st]))[0])
        for tg in targets:
            j_tgt = int(first_cross(fav_c, np.array([st * tg]))[0])
            # a tie on the same bar goes to the stop: worst case, as core.resolve
            if j_stop < len(adv_c) and j_stop <= j_tgt:
                out[(st, tg)] = (-1.0, "stop", j_stop)
            elif j_tgt < len(fav_c):
                out[(st, tg)] = (float(tg), "target", j_tgt)
            else:
                g = d * (last_c - entry) / (st * atr_unit)
                out[(st, tg)] = (float(g), "time", nb_last)
    return out
