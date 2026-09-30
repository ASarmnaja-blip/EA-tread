"""WPWB weekly risk report — volatility core (docs/WPWB_RISK_REPORT_SPEC.md).

Weekly realised variance (RV) of XAUUSD H1 close-to-close log returns, in
squared basis points, over the week between two Friday 22:15 UTC cuts (the
definition Codex froze in debate Round 4; a return belongs to the week that
contains its later close, so a weekend gap counts toward the next week).

Forecasts for week t, all made from weeks < t only:
  EWMA  (primary, frozen)  F_t = 0.75 F_{t-1} + 0.25 RV_{t-1}
  HAR   (logged only)      Codex's expanding log-HAR with v/2 correction
  MEAN26 (logged only)     mean RV of weeks t-26..t-1

Risk use (the only permitted use):
  vol_scale_t = clip(sqrt(B_REF / F_t), 0.5, 1.0) — may only REDUCE lots
  relative to the frozen default risk unit; a wider stop is allowed only if
  lots are cut enough to keep dollars at risk at or below the frozen ceiling.
  Never increases risk, never chooses direction, setup, entry or champion.
  effective_scale() applies the fail-safe: 0.50 while out of calibration.
"""
from __future__ import annotations

import math

import numpy as np

EWMA_LAMBDA = 0.75
HAR_MIN_TRAIN = 104
SCALE_MIN, SCALE_MAX = 0.5, 1.0
CAL_WINDOW = 26
CAL_BAND = math.log(1.5)       # trailing median of log(RV/F) must stay inside +/-
CAL_TAIL_U = 4.0               # a week with RV > 4 F is a tail miss
CAL_TAIL_SHARE = 0.10
MIN_BARS = 80                  # fewer valid H1 bars in a week -> DATA_INVALID
LABEL_EDGES = (0.75, 1.5, 2.5)  # VARIANCE ratio to the past-52-week median RV
#                                 = volatility ratio 0.87x / 1.22x / 1.58x
LABELS = ("สงบ", "ปกติ", "ผันผวนสูง", "ผันผวนรุนแรง")
LABELS_EN = ("CALM", "NORMAL", "HIGH", "EXTREME")

# Frozen default risk unit: median weekly RV over the 273 completed weeks
# 2021-07-02 .. 2026-09-25 (cuts 2021-07-02 22:15 .. 2026-09-18 22:15),
# computed once by `python research/wpwb_weekly/vol.py --bref` and written
# here at freeze. It is a constant, not a forecast; it is never re-estimated.
B_REF = 38193.9                 # bp^2 (weekly vol 195.4 bp), computed 2026-09-28


def weekly_rv(t, c, h, l, cuts, bar_seconds=3600):
    """RV, range (bp of the week's first close), return and bar count for each
    week (cuts[k], cuts[k] + 7d], assigning every H1 bar by its CLOSE time
    (t + 1h), so a bar that straddles a cut belongs to the later week (Codex
    Round 5). Reads only bars that close by cuts[k] + 7d.
    bar_seconds is explicit (WRWR contract C3, Codex R19-5): MIN_BARS and B_REF are defined on H1 bars, so any other
    bar length is refused instead of silently mis-scaled."""
    if int(bar_seconds) != 3600:
        raise ValueError("weekly_rv is defined on H1 bars (bar_seconds=3600); H4/D1 bars must not feed it")
    week = 7 * 86400
    close_t = np.asarray(t) + int(bar_seconds)
    lr = np.full(len(t), np.nan)
    lr[1:] = np.diff(np.log(c))
    rv, ran, ret, n = [], [], [], []
    for a in cuts:
        use = (close_t > a) & (close_t <= a + week)
        vals = lr[use]
        vals = vals[np.isfinite(vals)]
        n.append(int(use.sum()))
        if not use.any():
            rv.append(np.nan); ran.append(np.nan); ret.append(np.nan)
            continue
        idx = np.flatnonzero(use)
        rv.append(float(np.sum(vals * vals) * 1e8))
        ran.append(float((h[use].max() - l[use].min()) / c[idx[0]] * 1e4))
        prev = idx[0] - 1
        base = c[prev] if prev >= 0 else c[idx[0]]
        ret.append(float((c[idx[-1]] / base - 1) * 1e4))
    return np.asarray(rv), np.asarray(ran), np.asarray(ret), np.asarray(n)


def mask_invalid(rv, n):
    """Weeks with fewer than MIN_BARS H1 bars are DATA_INVALID: their RV
    becomes NaN so it never re-enters a forecast or calibration."""
    rv = np.asarray(rv, float).copy()
    rv[np.asarray(n) < MIN_BARS] = np.nan
    return rv


def ewma_forecast(rv):
    """F[t] uses rv[:t] only. F[0] is undefined (NaN)."""
    f = np.full(len(rv), np.nan)
    if len(rv) < 2:
        return f
    f[1] = rv[0]
    for k in range(2, len(rv)):
        prev = rv[k - 1]
        if not np.isfinite(prev):            # invalid week: carry the forecast
            f[k] = f[k - 1]
        elif not np.isfinite(f[k - 1]):
            f[k] = prev
        else:
            f[k] = EWMA_LAMBDA * f[k - 1] + (1 - EWMA_LAMBDA) * prev
    return f


def mean26_forecast(rv):
    f = np.full(len(rv), np.nan)
    for k in range(26, len(rv)):
        w = rv[k - 26:k]
        f[k] = float(np.nanmean(w)) if np.isfinite(w).any() else np.nan
    return f


def har_forecast(rv):
    """Codex Round 4: expanding OLS of log RV on (1, lag1, mean lag1-4,
    mean lag1-26), fitted on targets before t, >= 104 training rows,
    lognormal v/2 bias correction."""
    lv = np.log(rv)
    f = np.full(len(rv), np.nan)

    def feat(k):
        return np.array((1.0, lv[k - 1], lv[k - 4:k].mean(), lv[k - 26:k].mean()))

    first = 26 + HAR_MIN_TRAIN
    for k in range(first, len(rv)):
        x = np.array([feat(s) for s in range(26, k)])
        y = lv[26:k]
        ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
        if ok.sum() < HAR_MIN_TRAIN or not np.isfinite(feat(k)).all():
            continue                             # an invalid week in reach: no HAR this week
        x, y = x[ok], y[ok]
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        res = y - x @ beta
        s2 = float(res @ res / max(len(y) - 4, 1))
        f[k] = math.exp(float(feat(k) @ beta) + 0.5 * s2)
    return f


def forecast_one_ahead(rv_done):
    """Forecasts for the week AFTER the last completed week in rv_done."""
    ext = np.r_[rv_done, np.nan]
    e = ewma_forecast(ext)[-1]
    m = float(np.nanmean(rv_done[-26:])) if len(rv_done) >= 26 else np.nan
    h = har_forecast(ext)[-1] if len(rv_done) >= 26 + HAR_MIN_TRAIN else np.nan
    return dict(ewma=float(e), har=float(h), mean26=m)


def past_median52(rv):
    """med[t] = median of valid rv[t-52..t-1] (NaN before 52 weeks)."""
    med = np.full(len(rv), np.nan)
    for k in range(52, len(rv)):
        med[k] = float(np.nanmedian(rv[k - 52:k]))
    return med


def label(ratio):
    if not np.isfinite(ratio):
        return "ไม่ทราบ", "UNKNOWN"
    i = int(np.searchsorted(LABEL_EDGES, ratio, side="right"))
    return LABELS[i], LABELS_EN[i]


def effective_scale(raw_scale, calibrated, last_week_valid=True):
    """Frozen fail-safe (spec): out of calibration, or last week DATA_INVALID,
    -> the strictest scale 0.50. Not enough history to judge (None) also
    falls back to 0.50."""
    if calibrated is not True or not last_week_valid:
        return SCALE_MIN
    return raw_scale


def vol_scale(forecast, b_ref=None):
    b = B_REF if b_ref is None else b_ref
    if b is None or not np.isfinite(forecast) or forecast <= 0:
        return SCALE_MIN          # unknown -> the most conservative size
    return float(np.clip(math.sqrt(b / forecast), SCALE_MIN, SCALE_MAX))


def calibration(rv, f):
    """Trailing-26-week calibration of forecast f against realised rv.
    Uses every logged week (development weeks included, not only forward
    ones) and skips DATA_INVALID weeks. Returns (ok, median_log_u,
    tail_share, n)."""
    u = rv / f
    m = np.isfinite(u) & (u > 0)
    u = u[m][-CAL_WINDOW:]
    if len(u) < CAL_WINDOW:
        return None, np.nan, np.nan, len(u)
    med = float(np.median(np.log(u)))
    tail = float((u > CAL_TAIL_U).mean())
    ok = abs(med) <= CAL_BAND and tail < CAL_TAIL_SHARE
    return bool(ok), med, tail, len(u)


def qlike(y, f):
    r = y / f
    return r - np.log(r) - 1.0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bars as BR
    if "--bref" in sys.argv:
        m = BR.market(BR.load_bars(frozen=True))
        cuts = BR.cuts_between(m, BR.FIRST_CUT, BR.FREEZE_LAST_CUT)
        rv, _, _, n = weekly_rv(m.t, m.c, m.h, m.l, cuts)
        print(f"weeks {len(rv)}, min bars {n.min()}, B_REF median RV = {np.median(rv):.1f} bp^2 "
              f"(weekly vol {math.sqrt(np.median(rv)):.1f} bp)")
