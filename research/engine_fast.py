#!/usr/bin/env python3
"""The same engine, without the bar loop. Identical output, not similar output.

WHY THIS IS NEEDED AND WHY IT IS DANGEROUS

  The pilot needs 150 to 300 hypotheses, each measured against eight controls
  on nine markets. That is more than twenty thousand books. bracket_bias.engine
  walks 130,000 bars in Python for each one and takes about five seconds, so
  the pilot alone would run for a day and a half and the expanded phase for a
  week.

  Rewriting an execution engine for speed is the single easiest way to change
  a research result without noticing. So the rule here is not "close enough":
  every trade, every R, every holding period must be bit-identical to the
  engine already verified against run_e01, and the test asserts that on real
  data across nine markets and four families before anything reads the output.

WHAT MADE IT VECTORISABLE

  The loop looks sequential because of `busy` - one position at a time - but
  that rule only decides WHICH candidates are taken, never what a candidate
  would have returned. A trade's entry, stop, target and exit bar depend on
  the signal bar and the bars after it, and on nothing about earlier trades.

  So the work splits in two:

    every candidate is priced at once, in numpy, including the exit scan,
    which is a fixed 24-bar window and therefore a dense matrix;

    then one pass over the few thousand candidates applies `busy`.

  The second pass is sequential and stays in Python, because it is over
  candidates rather than bars - roughly 15,000 iterations instead of 130,000,
  each doing two comparisons instead of a full pricing.

THE PART THAT NEEDED CARE

  G12 resolves a bar touching both levels as a stop. The vectorised form gets
  that for free only if the stop test is evaluated before the target test at
  the same bar index, which is why the first-hit index is taken over the stop
  matrix and the target matrix separately and compared with <= rather than <.
  An argmax over the combined mask would silently make the tie a target on
  roughly half the ambiguous bars, and ambiguous bars are 8.5% to 10.5% of
  this book at the 1x stop.
"""
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import xauusd_1000_setups as X

HOLD = X.HOLD_BARS


def engine(P, dvec, Ivec, tick, tp_R=1.0, hold=HOLD, stop_mult=1.0,
           use_stop=True, use_target=True, min_trades=20):
    """Bit-identical to bracket_bias.engine. Returns (R, signal_bar, held)."""
    N = int(P["N"])
    d_all = np.asarray(dvec)
    A = np.asarray(P["A"], float)
    spread = np.asarray(P["spread"], float)
    bid_o, ask_o = np.asarray(P["bid_o"], float), np.asarray(P["ask_o"], float)
    bid_h, bid_l = np.asarray(P["bid_h"], float), np.asarray(P["bid_l"], float)
    ask_h, ask_l = np.asarray(P["ask_h"], float), np.asarray(P["ask_l"], float)
    bid, ask = np.asarray(P["bid"], float), np.asarray(P["ask"], float)

    t = np.arange(300, N - 1)
    t = t[d_all[300:N - 1] != 0]
    if len(t) == 0:
        return None
    d = d_all[t].astype(np.int64)
    long_ = d > 0
    a = A[t]
    ok = np.isfinite(a) & (a > 0)

    e = t + 1
    entry = np.where(long_, ask_o[e], bid_o[e])
    inval = np.asarray(Ivec, float)[t]
    ok &= np.isfinite(entry) & np.isfinite(inval)

    sp_t = np.where(np.isfinite(spread[t]), spread[t], 0.0)
    b = np.maximum(np.maximum(0.10 * a, sp_t), 2 * tick)
    # tick_round away from entry: floor for a long's level, ceil for a short's
    with np.errstate(invalid="ignore"):
        raw = np.where(long_,
                       np.floor((inval - b) / tick) * tick,
                       np.ceil((inval + b) / tick) * tick)
    dist = np.abs(entry - raw) * stop_mult
    ok &= dist > 0

    stop = entry - d * dist
    sp_e = np.where(np.isfinite(spread[e]), spread[e], spread[t])
    ok &= np.isfinite(sp_e) & (sp_e <= 0.10 * a)

    gap_lo = np.maximum(0.30 * a, 5 * sp_e)
    ad = np.abs(entry - raw)
    ok &= (gap_lo <= ad) & (ad <= 3 * a)
    # gapped through the invalidation level before the order could exist
    ok &= np.where(long_, entry > raw, entry < raw)

    idx = np.where(ok)[0]
    if len(idx) == 0:
        return None
    t_c, d_c, e_c = t[idx], d[idx], e[idx]
    entry_c, dist_c, stop_c = entry[idx], dist[idx], stop[idx]
    long_c = d_c > 0
    target_c = entry_c + d_c * tp_R * dist_c

    # ---- exit scan, as a dense (candidates x hold) window ----------------
    K = e_c[:, None] + np.arange(hold)[None, :]
    valid = K < N
    Kc = np.clip(K, 0, N - 1)
    ex_lo = np.where(long_c[:, None], bid_l[Kc], ask_l[Kc])
    ex_hi = np.where(long_c[:, None], bid_h[Kc], ask_h[Kc])
    with np.errstate(invalid="ignore"):
        hit_s = np.where(long_c[:, None], ex_lo <= stop_c[:, None],
                         ex_hi >= stop_c[:, None]) & valid
        hit_t = np.where(long_c[:, None], ex_hi >= target_c[:, None],
                         ex_lo <= target_c[:, None]) & valid
    if not use_stop:
        hit_s = np.zeros_like(hit_s)
    if not use_target:
        hit_t = np.zeros_like(hit_t)

    BIG = hold + 1
    fs = np.where(hit_s.any(1), hit_s.argmax(1), BIG)
    ft = np.where(hit_t.any(1), hit_t.argmax(1), BIG)
    # G12: a bar that touches both is a stop, so <= rather than <
    stop_first = fs <= ft
    first = np.minimum(fs, ft)
    resolved = first < BIG

    bar = np.where(resolved, e_c + first,
                   np.minimum(e_c + hold - 1, N - 1))
    px = np.where(resolved,
                  np.where(stop_first, stop_c, target_c),
                  np.where(long_c, bid[np.clip(bar, 0, N - 1)],
                           ask[np.clip(bar, 0, N - 1)]))
    R_all = (px - entry_c) * d_c / dist_c
    HD_all = np.maximum(bar - t_c, 1)

    # ---- one position at a time, over candidates rather than bars --------
    keep = np.empty(len(t_c), bool)
    busy = -1
    tl, bl = t_c.tolist(), bar.tolist()
    for i in range(len(tl)):
        if tl[i] <= busy:
            keep[i] = False
            continue
        keep[i] = True
        busy = bl[i]

    R = R_all[keep]
    if len(R) < min_trades:
        return None
    return R, t_c[keep].astype(float), HD_all[keep].astype(float)


def verify(P, dvec, Ivec, tick, **kw):
    """Assert bit-identity with the reference engine on one book."""
    from bracket_bias import engine as ref
    a = ref(P, dvec, Ivec, tick, **kw)
    b = engine(P, dvec, Ivec, tick, **kw)
    if a is None or b is None:
        return dict(ok=a is None and b is None, note="one or both empty",
                    ref_n=None if a is None else len(a[0]),
                    fast_n=None if b is None else len(b[0]))
    same_n = len(a[0]) == len(b[0])
    return dict(ok=bool(same_n and np.array_equal(a[0], b[0])
                        and np.array_equal(a[1], b[1])
                        and np.array_equal(a[2], b[2])),
                ref_n=len(a[0]), fast_n=len(b[0]),
                max_abs_diff=(float(np.max(np.abs(a[0] - b[0])))
                              if same_n else None),
                ref_E=float(a[0].mean()), fast_E=float(b[0].mean()))
