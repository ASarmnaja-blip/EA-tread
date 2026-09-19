#!/usr/bin/env python3
"""Six layers that describe a market without ever asking whether it paid.

WHY PnL IS NOT IN HERE ANYWHERE

  A measurement tuned against strategy returns is a strategy, and a bad one:
  it will report that the market is most readable exactly where the last
  search happened to make money. The quality score in this file is built from
  coverage, precision and resolution - how much of the sample the measurement
  covers, how tight its own standard error is, and how much it actually
  separates cells from each other. All three can be computed with the return
  column deleted, and that is the test each one is held to.

  The consequence is that a layer can score well and be useless for trading.
  That is the intended behaviour. A thermometer that reads correctly in a room
  with nothing worth measuring is still a working thermometer, and knowing
  which is which is the entire research question.

THE LAYERS

  TRADABILITY       what it costs to be here, against what there is to win.
                    Spread over true range by hour, the holding period at
                    which the spread and the swap balance, and the smallest
                    move that pays for a round trip.

  ACTIVITY          how much is happening, separated from how much it varies.
                    Bar range over ATR, movement per hour, and whether the
                    volume field carries information or is tick count.

  STRUCTURE         where price is relative to what it has done. Position in
                    the recent range, distance to the prior session's value
                    area and point of control, and the shape of the last
                    swing.

  REGIME            trend against range, as the efficiency ratio and the
                    variance ratio - the latter reported only after the
                    illiquidity correction, because raw VR measures an empty
                    book as strongly as it measures a trend.

  EXECUTION         whether a measured level could have been traded. Gap
    RELIABILITY     frequency through a level, the share of bars that touch
                    two levels at once, and spread stability within the hour.

  MEASUREMENT       whether the number can be trusted at all. Bar coverage
    RELIABILITY     against the expected calendar, the day-blocked bootstrap
                    standard error of each cell, and whether the same quantity
                    measured on two timeframes agrees.

WHAT THE SIXTH LAYER IS FOR

  It is the only layer that can veto. A tradability figure computed on a
  symbol with 60% bar coverage is not a cheap market, it is an unmeasured one,
  and the difference has to be visible in the output rather than inferred from
  a footnote.
"""
import json
import math
import pathlib
import sys
import zoneinfo

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

PARAMS = dict(
    boot=400,             # day-blocked bootstrap draws
    atr_hours=14,         # ATR window in WALL CLOCK hours, not bars
    min_cell=120,         # a cell below this is reported as unmeasured
    tail_q=0.90,
    vr_k=4,               # variance-ratio horizon in bars
    range_look=50,        # bars for the structure layer's range
    er_look=20,           # bars for the efficiency ratio
    swap_points=534.9,    # Exness XAUUSDc long swap, points per night
    tick=0.001,
)

SESSIONS = (("sydney", 21, 6), ("tokyo", 0, 9), ("london", 7, 16),
            ("newyork", 12, 21))


# ============================================================== helpers ====
def _tr(h, l, c):
    pc = np.concatenate([[np.nan], np.asarray(c, float)[:-1]])
    h, l = np.asarray(h, float), np.asarray(l, float)
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]),
                     axis=0)


def _atr_hours(df, tf_min, hours):
    """ATR over a fixed wall-clock window so M1 and H4 mean the same thing.

    A 14-BAR ATR is 14 minutes on M1 and 56 hours on H4, which makes every
    cross-timeframe comparison in a project like this one a comparison of two
    different quantities wearing the same name."""
    n = max(2, int(round(hours * 60 / max(tf_min, 1))))
    tr = _tr(df["high"], df["low"], df["close"])
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False,
                             min_periods=n).mean().to_numpy(), tr


def _day_blocks(idx):
    d = pd.DatetimeIndex(idx).normalize()
    codes, _ = pd.factorize(d)
    return codes


def boot_se(vals, blocks, draws, rng, stat=np.nanmean):
    """Day-blocked bootstrap standard error.

    Blocked by day because hourly bars inside one day are not independent -
    an i.i.d. bootstrap here understates the error by roughly the square root
    of the bars per day, which on H1 is a factor near five."""
    vals = np.asarray(vals, float)
    ok = np.isfinite(vals)
    if ok.sum() < 30:
        return np.nan
    vals, blocks = vals[ok], np.asarray(blocks)[ok]
    uniq = np.unique(blocks)
    if len(uniq) < 20:
        return np.nan
    by = {b: vals[blocks == b] for b in uniq}
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        out[i] = stat(np.concatenate([by[b] for b in pick]))
    return float(np.nanstd(out, ddof=1))


def quality(coverage, se, spread_of_cells, n_cells, min_cells_met):
    """Coverage x precision x resolution. No return column is touched.

    precision   1 - (typical cell standard error) / (spread across cells).
                A measurement whose error bars are as wide as the differences
                it reports has resolved nothing.
    resolution  the share of cells that met the minimum sample. A layer that
                reports 24 hourly cells of which 6 are empty has measured 18.
    """
    if not np.isfinite(se) or not np.isfinite(spread_of_cells) \
            or spread_of_cells <= 0:
        precision = 0.0
    else:
        precision = max(0.0, 1.0 - se / spread_of_cells)
    resolution = (min_cells_met / n_cells) if n_cells else 0.0
    return dict(quality=float(coverage * precision * resolution),
                coverage=float(coverage), precision=float(precision),
                resolution=float(resolution))


def session_of(ts):
    h = ts.hour
    for name, a, b in SESSIONS:
        if a <= b:
            if a <= h < b:
                return name
        elif h >= a or h < b:
            return name
    return "offhours"


# ============================================================ layer 1 ======
def tradability(df, tf_min, rng, p=PARAMS):
    """What being here costs, against what there is to win.

    cost/range is the instrument's core number: the spread as a share of the
    true range of the same bar. Above about a third, no rule on that timeframe
    can pay for itself regardless of how well it predicts, because the whole
    distribution of available moves sits inside the cost."""
    A, tr = _atr_hours(df, tf_min, p["atr_hours"])
    spread = (df["ask_close"] - df["bid_close"]).to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        cr = spread / tr
    cr = np.where(np.isfinite(cr) & (tr > 0), cr, np.nan)
    idx = pd.DatetimeIndex(df.index)
    blocks = _day_blocks(idx)

    by_hour, met = {}, 0
    for h in range(24):
        m = idx.hour == h
        v = cr[m]
        v = v[np.isfinite(v)]
        if len(v) < p["min_cell"]:
            by_hour[h] = None
            continue
        met += 1
        by_hour[h] = dict(median=float(np.median(v)),
                          q90=float(np.quantile(v, p["tail_q"])),
                          n=int(len(v)))
    vals = [v["median"] for v in by_hour.values() if v]
    se = boot_se(cr, blocks, p["boot"], rng, np.nanmedian)
    spread_cells = (max(vals) - min(vals)) if len(vals) > 1 else np.nan
    q = quality(float(np.isfinite(cr).mean()), se, spread_cells, 24, met)

    # h* = S / w : the holding period at which the spread and one night's swap
    # are equal. Below it the spread dominates and the trade is too short to
    # be worth its own cost; above it the carry does.
    med_spread_pts = float(np.nanmedian(spread) / p["tick"])
    h_star = med_spread_pts / p["swap_points"] if p["swap_points"] else np.nan

    cheapest = min((h for h, v in by_hour.items() if v),
                   key=lambda h: by_hour[h]["median"], default=None)
    dearest = max((h for h, v in by_hour.items() if v),
                  key=lambda h: by_hour[h]["median"], default=None)
    return dict(layer="tradability", by_hour=by_hour,
                median_cost_over_range=float(np.nanmedian(cr)),
                cheapest_hour=cheapest, dearest_hour=dearest,
                cheapest=by_hour[cheapest]["median"] if cheapest is not None else None,
                dearest=by_hour[dearest]["median"] if dearest is not None else None,
                median_spread_points=med_spread_pts,
                h_star_nights=h_star,
                min_move_to_pay=float(2 * np.nanmedian(spread)),
                se=se, **q)


# ============================================================ layer 2 ======
def activity(df, tf_min, rng, p=PARAMS):
    """How much is happening, and whether the volume field says anything."""
    A, tr = _atr_hours(df, tf_min, p["atr_hours"])
    with np.errstate(invalid="ignore", divide="ignore"):
        act = tr / A
    act = np.where(np.isfinite(act), act, np.nan)
    idx = pd.DatetimeIndex(df.index)
    blocks = _day_blocks(idx)

    vol = df["volume"].to_numpy(float) if "volume" in df else None
    if vol is None:
        vol_state = "absent"
    elif not np.isfinite(vol).any() or np.nanmedian(vol) <= 0:
        vol_state = "empty"
    elif float(np.mean(vol == np.nanmedian(vol))) > 0.3:
        vol_state = "degenerate"
    else:
        # tick count and true range on FX feeds are near-duplicates; a
        # correlation this high means the volume field adds no information
        # the range does not already carry, and treating it as order flow
        # would be reading the same variable twice
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(vol) & np.isfinite(tr)
            r = (float(np.corrcoef(vol[ok], tr[ok])[0, 1])
                 if ok.sum() > 100 else np.nan)
        vol_state = ("proxy-for-range" if np.isfinite(r) and r > 0.8
                     else "usable")

    by_hour, met = {}, 0
    for h in range(24):
        v = act[idx.hour == h]
        v = v[np.isfinite(v)]
        if len(v) < p["min_cell"]:
            by_hour[h] = None
            continue
        met += 1
        by_hour[h] = dict(mean=float(v.mean()), n=int(len(v)))
    vals = [v["mean"] for v in by_hour.values() if v]
    se = boot_se(act, blocks, p["boot"], rng)
    q = quality(float(np.isfinite(act).mean()), se,
                (max(vals) - min(vals)) if len(vals) > 1 else np.nan, 24, met)
    return dict(layer="activity", by_hour=by_hour, volume_state=vol_state,
                mean_activity=float(np.nanmean(act)),
                busiest_hour=max((h for h, v in by_hour.items() if v),
                                 key=lambda h: by_hour[h]["mean"], default=None),
                quietest_hour=min((h for h, v in by_hour.items() if v),
                                  key=lambda h: by_hour[h]["mean"], default=None),
                se=se, **q)


# ============================================================ layer 3 ======
def structure(df, tf_min, rng, p=PARAMS):
    """Where price sits in what it has already done."""
    h = pd.Series(df["high"].to_numpy(float))
    l = pd.Series(df["low"].to_numpy(float))
    c = df["close"].to_numpy(float)
    hi = h.rolling(p["range_look"]).max().to_numpy()
    lo = l.rolling(p["range_look"]).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = (c - lo) / (hi - lo)
    pos = np.where(np.isfinite(pos), pos, np.nan)
    idx = pd.DatetimeIndex(df.index)
    blocks = _day_blocks(idx)

    # how long price stays at an extreme once it gets there - the quantity a
    # breakout rule is implicitly betting on
    at_hi = np.isfinite(pos) & (pos > 0.95)
    at_lo = np.isfinite(pos) & (pos < 0.05)
    runs = []
    cur = 0
    for v in at_hi:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    med_run = float(np.median(runs)) if runs else np.nan

    nb = 10
    by_bin, met = {}, 0
    edges = np.nanquantile(pos[np.isfinite(pos)], np.linspace(0, 1, nb + 1)) \
        if np.isfinite(pos).sum() > nb * 10 else None
    fwd = np.concatenate([c[1:] - c[:-1], [np.nan]])
    if edges is not None:
        edges[0], edges[-1] = -np.inf, np.inf
        b = np.digitize(pos, edges[1:-1])
        for k in range(nb):
            m = np.isfinite(pos) & (b == k)
            if m.sum() < p["min_cell"]:
                by_bin[k] = None
                continue
            met += 1
            # forward move NORMALISED by ATR, reported as a description of
            # the conditional distribution and not as a return
            A, _ = _atr_hours(df, tf_min, p["atr_hours"])
            with np.errstate(invalid="ignore", divide="ignore"):
                z = fwd / A
            by_bin[k] = dict(n=int(m.sum()),
                             next_move_atr=float(np.nanmean(z[m])),
                             persistence=float(np.nanmean(
                                 (np.sign(z[m]) == np.sign(
                                     np.roll(z, 1)[m])).astype(float))))
    vals = [v["next_move_atr"] for v in by_bin.values() if v]
    se = boot_se(pos, blocks, p["boot"], rng)
    q = quality(float(np.isfinite(pos).mean()), se,
                (max(vals) - min(vals)) if len(vals) > 1 else np.nan, nb, met)
    return dict(layer="structure", by_range_decile=by_bin,
                share_at_high=float(at_hi.mean()),
                share_at_low=float(at_lo.mean()),
                median_bars_at_high=med_run,
                se=se, **q)


# ============================================================ layer 4 ======
def regime(df, tf_min, rng, p=PARAMS):
    """Trend against range, with the variance ratio corrected for cost.

    Raw VR was measured in this repo to correlate +0.41 to +0.53 with the
    spread: a thin book produces bid-ask bounce, bounce produces negative
    autocorrelation, and the statistic reads that as mean reversion. Reporting
    it without the correction measures how empty the book is, not how the
    price moves, so both figures are carried and the residual is the one to
    read."""
    c = pd.Series(df["close"].to_numpy(float))
    er_net = (c - c.shift(p["er_look"])).abs()
    er_path = c.diff().abs().rolling(p["er_look"]).sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        er = (er_net / er_path).to_numpy()
    er = np.where(np.isfinite(er), er, np.nan)

    r1 = c.diff().to_numpy()
    k = p["vr_k"]
    rk = (c - c.shift(k)).to_numpy()
    idx = pd.DatetimeIndex(df.index)
    spread = (df["ask_close"] - df["bid_close"]).to_numpy(float)
    blocks = _day_blocks(idx)

    by_hour, met, vr_h, cost_h = {}, 0, [], []
    for h in range(24):
        m = idx.hour == h
        v1, vk = r1[m], rk[m]
        okv = np.isfinite(v1) & np.isfinite(vk)
        if okv.sum() < p["min_cell"]:
            by_hour[h] = None
            continue
        var1, vark = float(np.nanvar(v1[okv])), float(np.nanvar(vk[okv]))
        vr = vark / (k * var1) if var1 > 0 else np.nan
        e = er[m]
        e = e[np.isfinite(e)]
        met += 1
        cm = float(np.nanmedian(spread[m]))
        by_hour[h] = dict(vr=vr, er=float(e.mean()) if len(e) else np.nan,
                          n=int(okv.sum()), median_spread=cm)
        if np.isfinite(vr):
            vr_h.append(vr)
            cost_h.append(cm)

    # regress VR on cost across hours and keep the residual
    vr_resid, vr_cost_r = None, np.nan
    if len(vr_h) >= 8:
        x, y = np.asarray(cost_h), np.asarray(vr_h)
        vr_cost_r = float(np.corrcoef(x, y)[0, 1])
        b, a = np.polyfit(x, y, 1)
        resid = y - (a + b * x)
        vr_resid = {h: float(r) for h, r in
                    zip([h for h in by_hour if by_hour[h]], resid)}

    vals = [v["er"] for v in by_hour.values() if v and np.isfinite(v["er"])]
    se = boot_se(er, blocks, p["boot"], rng)
    q = quality(float(np.isfinite(er).mean()), se,
                (max(vals) - min(vals)) if len(vals) > 1 else np.nan, 24, met)
    return dict(layer="regime", by_hour=by_hour,
                mean_efficiency_ratio=float(np.nanmean(er)),
                vr_vs_cost_corr=vr_cost_r,
                vr_residual_by_hour=vr_resid,
                se=se, **q)


# ============================================================ layer 5 ======
def execution_reliability(df, tf_min, rng, p=PARAMS):
    """Could a level measured here have been traded at it.

    Three things break that: the market gapping through a level between bars,
    a bar touching two levels so the order inside it decides the result, and
    the spread moving enough inside an hour that the quote used to plan the
    trade is not the quote that fills it."""
    o = df["open"].to_numpy(float)
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    A, tr = _atr_hours(df, tf_min, p["atr_hours"])
    pc = np.concatenate([[np.nan], c[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = np.abs(o - pc) / A
    gap = np.where(np.isfinite(gap), gap, np.nan)

    # a bar that spans more than 2 ATR can contain both sides of a 1-ATR
    # bracket, so its internal order decides the trade
    with np.errstate(invalid="ignore", divide="ignore"):
        span = tr / A
    two_sided = float(np.nanmean(span > 2.0))

    spread = (df["ask_close"] - df["bid_close"]).to_numpy(float)
    ss = pd.Series(spread)
    spread_vol = float(np.nanmedian(
        (ss.rolling(24).std() / ss.rolling(24).mean()).to_numpy()))

    idx = pd.DatetimeIndex(df.index)
    blocks = _day_blocks(idx)
    by_hour, met = {}, 0
    for hh in range(24):
        m = idx.hour == hh
        g = gap[m]
        g = g[np.isfinite(g)]
        if len(g) < p["min_cell"]:
            by_hour[hh] = None
            continue
        met += 1
        by_hour[hh] = dict(mean_gap_atr=float(g.mean()),
                           gap_over_quarter_atr=float((g > 0.25).mean()),
                           n=int(len(g)))
    vals = [v["mean_gap_atr"] for v in by_hour.values() if v]
    se = boot_se(gap, blocks, p["boot"], rng)
    q = quality(float(np.isfinite(gap).mean()), se,
                (max(vals) - min(vals)) if len(vals) > 1 else np.nan, 24, met)
    return dict(layer="execution_reliability", by_hour=by_hour,
                mean_gap_atr=float(np.nanmean(gap)),
                share_gap_over_quarter_atr=float(np.nanmean(gap > 0.25)),
                share_two_sided_bars=two_sided,
                spread_instability=spread_vol,
                se=se, **q)


# ============================================================ layer 6 ======
def measurement_reliability(df, tf_min, rng, p=PARAMS):
    """The only layer that can veto the other five.

    Coverage against the expected weekday calendar, the spread's own
    structural stability over time, and whether the sample is long enough for
    the cell counts the other layers need. A cheap market measured on 60% of
    its bars is not a cheap market, it is an unmeasured one."""
    idx = pd.DatetimeIndex(df.index)
    span_h = (idx[-1] - idx[0]).total_seconds() / 3600.0
    per_bar_h = max(tf_min, 1) / 60.0
    # FX trades about 120 of 168 hours a week; the expected count is scaled
    # by that rather than by the full calendar, which would call every clean
    # feed 71% complete
    expected = span_h / per_bar_h * (120.0 / 168.0)
    coverage = float(min(1.0, len(df) / expected)) if expected > 0 else 0.0

    spread = (df["ask_close"] - df["bid_close"]).to_numpy(float)
    yr = idx.year.to_numpy()
    by_year = {}
    for y in np.unique(yr):
        v = spread[yr == y]
        v = v[np.isfinite(v)]
        if len(v) < 200:
            continue
        by_year[int(y)] = float(np.median(v))
    ys = sorted(by_year)
    breaks = []
    for i in range(1, len(ys)):
        a, b = by_year[ys[i - 1]], by_year[ys[i]]
        if a > 0 and (b / a > 1.8 or b / a < 1 / 1.8):
            breaks.append(dict(year=ys[i], ratio=round(b / a, 2)))

    # do two halves of the sample agree on the hourly cost profile
    half = len(df) // 2
    def prof(g):
        s = (g["ask_close"] - g["bid_close"]).to_numpy(float)
        t = _tr(g["high"], g["low"], g["close"])
        with np.errstate(invalid="ignore", divide="ignore"):
            cr = s / t
        gi = pd.DatetimeIndex(g.index)
        return np.array([np.nanmedian(cr[gi.hour == h]) for h in range(24)])
    p1, p2 = prof(df.iloc[:half]), prof(df.iloc[half:])
    ok = np.isfinite(p1) & np.isfinite(p2)
    half_corr = (float(np.corrcoef(p1[ok], p2[ok])[0, 1])
                 if ok.sum() > 8 else np.nan)

    veto = []
    if coverage < 0.90:
        veto.append(f"coverage {coverage:.0%} below 90%")
    if breaks:
        veto.append(f"spread breaks at {[b['year'] for b in breaks]}")
    if np.isfinite(half_corr) and half_corr < 0.5:
        veto.append(f"two halves disagree on the hourly cost profile "
                    f"(r {half_corr:.2f})")
    return dict(layer="measurement_reliability", coverage=coverage,
                bars=len(df), expected_bars=int(expected),
                spread_by_year=by_year, spread_breaks=breaks,
                half_sample_profile_corr=half_corr,
                veto=veto, quality=float(coverage if not veto else 0.0),
                precision=np.nan, resolution=np.nan)


LAYERS = dict(tradability=tradability, activity=activity, structure=structure,
              regime=regime, execution_reliability=execution_reliability,
              measurement_reliability=measurement_reliability)


def profile(df, tf_min, seed=17, layers=None, p=PARAMS):
    """Run every layer and report the six quality scores side by side."""
    rng = np.random.default_rng(seed)
    names = layers or list(LAYERS)
    out = {}
    rel = LAYERS["measurement_reliability"](df, tf_min, rng, p)
    out["measurement_reliability"] = rel
    for name in names:
        if name == "measurement_reliability":
            continue
        out[name] = LAYERS[name](df, tf_min, rng, p)
        if rel["veto"]:
            out[name]["vetoed_by"] = rel["veto"]
    return out


if __name__ == "__main__":
    print(__doc__.split("THE LAYERS")[1])
