"""Tool Foundry engine (docs/FOUNDRY_PROTOCOL.md). Read-only research; no orders.

Bars: Dukascopy H1 mid OHLC, D1 from H1 (22:00 UTC anchor). A trade spec is
(entry bar index, direction, entry price or NaN for bar open, stop distance,
target distance, last bar index). simulate() resolves exits by first passage
(stop first when both touch; gap through the stop fills at the open)."""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in ("research/history", "research/wpwb_weekly", "research/pilot"):
    sys.path.insert(0, str(ROOT / p))
from build_all_tf import load_kind  # noqa: E402
import vol as V  # noqa: E402

COST_BP = 2.0
STRESS_BP = 4.0
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
PERIODS = {"DISC": ("2003-05-01", "2015-01-01"), "VAL": ("2015-01-01", "2021-01-01"),
           "HOLD": ("2021-01-01", "2026-09-01")}
CELLS = ["ALL"] + [f"{v}/{tr}" for v in ("CALM", "NORMAL", "HIGH") for tr in ("DOWN", "FLAT", "UP")]


@dataclass
class Bars:
    t: np.ndarray        # open time, epoch s
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray      # ATR(14) known at the bar's open (from bars before it)
    week: np.ndarray     # regime week index of each bar
    spread_bp: np.ndarray
    hour: np.ndarray
    dow: np.ndarray
    year: np.ndarray
    step: int


def _atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    a = pd.Series(tr).rolling(n, min_periods=n).mean().to_numpy()
    return np.r_[np.nan, a[:-1]]          # known at the open of each bar


def trend_z(lr, rv, end, L=13):
    s = end - L + 1
    if s < 0:
        return np.nan
    w, v = lr[s:end + 1], rv[s:end + 1]
    if not (np.isfinite(w).all() and np.isfinite(v).all()):
        return np.nan
    return w.sum() * 1e4 / math.sqrt(v.sum())


def regimes(t, c, h, l):
    """Per week k (cuts[k], cuts[k] + 7d]: vol cell from the B0 forecast known at cuts[k],
    trend cell from the 13 completed weeks before cuts[k]."""
    end = int(t[-1]) + 3600
    cuts = np.arange(FIRST_CUT, end, WEEK, dtype=np.int64)
    rv_raw, _, ret, nb = V.weekly_rv(t, c, h, l, cuts)
    rv = V.mask_invalid(rv_raw, nb)
    f = V.ewma_forecast(rv)
    lr = np.log1p(np.where(np.isfinite(rv), ret, np.nan) / 1e4)
    vol = np.full(len(cuts), "", object); trd = np.full(len(cuts), "", object)
    for k in range(53, len(cuts)):
        w = rv[k - 52:k]
        if np.isfinite(w).sum() >= 40 and np.isfinite(f[k]):
            r = f[k] / np.nanmedian(w)
            vol[k] = "CALM" if r < 0.75 else ("NORMAL" if r < 1.5 else "HIGH")
        z = trend_z(lr, rv, k - 1)
        if np.isfinite(z):
            trd[k] = "DOWN" if z <= -0.5 else ("UP" if z >= 0.5 else "FLAT")
    cell = np.array([f"{a}/{b}" if a and b else "" for a, b in zip(vol, trd)], object)
    return cuts, cell


_CACHE = {}


def load():
    if "bars" in _CACHE:
        return _CACHE["bars"]
    df = load_kind("hour")
    t = df.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    o = ((df.o + df.ao) / 2).to_numpy(float); hh = ((df.h + df.ah) / 2).to_numpy(float)
    ll = ((df.l + df.al) / 2).to_numpy(float); cc = ((df.c + df.ac) / 2).to_numpy(float)
    sp = ((df.ao - df.o) / df.o * 1e4).to_numpy(float)
    cuts, cell = regimes(t, df.c.to_numpy(float), df.h.to_numpy(float), df.l.to_numpy(float))
    wk = np.searchsorted(cuts, t, side="left") - 1          # bar opening after cuts[k] -> week k
    idx = pd.to_datetime(t, unit="s")
    H = Bars(t, o, hh, ll, cc, _atr(hh, ll, cc, 14), wk, sp, idx.hour.to_numpy(), idx.dayofweek.to_numpy(),
             idx.year.to_numpy(), 3600)
    # D1 from H1 mid, 22:00 UTC anchor; a day's start time = first bar open
    day = (idx - pd.Timedelta(hours=22)).floor("D")
    g = pd.DataFrame(dict(t=t, o=o, h=hh, l=ll, c=cc, sp=sp)).groupby(day.to_numpy())
    D = g.agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
              n=("t", "size"), sp=("sp", "median"))
    D = D[D.n >= 18]
    dt = D.t.to_numpy(np.int64)
    didx = D.index
    Dd = Bars(dt, D.o.to_numpy(float), D.h.to_numpy(float), D.l.to_numpy(float), D.c.to_numpy(float),
              _atr(D.h.to_numpy(float), D.l.to_numpy(float), D.c.to_numpy(float), 20),
              np.searchsorted(cuts, dt, side="left") - 1, D.sp.to_numpy(float), np.zeros(len(D), int),
              pd.DatetimeIndex(didx).dayofweek.to_numpy(), pd.DatetimeIndex(didx).year.to_numpy(), 86400)
    _CACHE["bars"] = (H, Dd, cuts, cell)
    return _CACHE["bars"]


# ------------------------------------------------------------------ simulation
def simulate(B, ent, dirs, stop, tgt, last, eprice=None):
    """Vectorised first passage. ent/last: bar indices (inclusive window ent..last).
    stop/tgt: price distances (NaN = none). eprice: entry level (NaN = open of ent).
    Returns gross bp per trade and exit bar index."""
    ent = np.asarray(ent, int); dirs = np.asarray(dirs, float); last = np.minimum(np.asarray(last, int), len(B.o) - 1)
    stop = np.asarray(stop, float); tgt = np.asarray(tgt, float)
    n = len(ent)
    if n == 0:
        return np.zeros(0), np.zeros(0, int)
    ep = B.o[ent].copy()
    if eprice is not None:
        e2 = np.asarray(eprice, float)
        m = np.isfinite(e2)
        ep[m] = e2[m]
    H = int((last - ent).max()) + 1
    j = ent[:, None] + np.arange(H)[None, :]
    valid = j <= last[:, None]
    jj = np.minimum(j, len(B.o) - 1)
    hi, lo, op = B.h[jj], B.l[jj], B.o[jj]
    up = dirs[:, None] > 0
    sp_ = np.where(up, ep[:, None] - stop[:, None], ep[:, None] + stop[:, None])
    tp_ = np.where(up, ep[:, None] + tgt[:, None], ep[:, None] - tgt[:, None])
    s_hit = valid & np.isfinite(stop)[:, None] & np.where(up, lo <= sp_, hi >= sp_)
    t_hit = valid & np.isfinite(tgt)[:, None] & np.where(up, hi >= tp_, lo <= tp_)
    big = H + 5
    fs = np.where(s_hit.any(1), s_hit.argmax(1), big)
    ft = np.where(t_hit.any(1), t_hit.argmax(1), big)
    exit_px = B.c[last].copy()
    ex = last.copy()
    r = np.arange(n)
    sfirst = (fs <= ft) & (fs < big)
    tfirst = (ft < fs) & (ft < big)
    # stop fill: the stop level, or the bar open if the bar opened beyond it (gap); not on the entry bar's open
    so = op[r, np.minimum(fs, H - 1)]
    sl = sp_[r, 0]
    gap = np.where(dirs > 0, so < sl, so > sl) & (fs > 0)
    exit_px = np.where(sfirst, np.where(gap, so, sl), exit_px)
    ex = np.where(sfirst, ent + fs, ex)
    exit_px = np.where(tfirst, tp_[r, 0], exit_px)
    ex = np.where(tfirst, ent + ft, ex)
    gross = dirs * (exit_px / ep - 1) * 1e4
    return gross, ex


# ------------------------------------------------------------------ statistics
def cluster_t(x, wk):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return np.nan
    m = x.mean()
    s = pd.Series(x - m).groupby(np.asarray(wk)).sum().to_numpy()
    se = math.sqrt((s ** 2).sum()) / n
    return m / se if se > 0 else np.nan


def one_sided_p(t):
    from scipy.stats import norm
    return float(1 - norm.cdf(t)) if np.isfinite(t) else 1.0


def matched_control(B, cell_of_bar, ent, dirs, stop_atr, tgt_atr, hold, rng, reps=5, key="hour"):
    """Random entries in the same year x hour (or weekday) x regime cell; same direction,
    stop/target in the same ATR units, same holding length in bars."""
    strat = pd.Series(np.arange(len(B.o)))
    kk = B.hour if key == "hour" else B.dow
    keyarr = pd.Series(list(zip(B.year, kk, cell_of_bar)))
    groups = {}
    for i, g in strat.groupby(keyarr):
        groups[i] = g.to_numpy()
    out = []
    ekey = list(zip(B.year[ent], kk[ent], cell_of_bar[ent]))
    for _ in range(reps):
        ce = np.array([rng.choice(groups[k_]) for k_ in ekey], int)
        ce = np.minimum(ce, len(B.o) - 2)
        a = B.atr[ce]
        ok = np.isfinite(a)
        ce, d_, a = ce[ok], dirs[ok], a[ok]
        g, _ = simulate(B, ce, d_, stop_atr[ok] * a, tgt_atr[ok] * a, ce + hold[ok])
        out.append(np.r_[g, np.full((~ok).sum(), np.nan)])
    return np.nanmean(np.vstack(out), axis=0)


def evaluate(name, B, cells_of_bar, ent, dirs, gross, ctrl, extra=None, periods=("DISC",), cells=None):
    """Rows per (period, cell) for one candidate family/params."""
    rows = []
    date = pd.to_datetime(B.t[ent], unit="s")
    wk = B.t[ent] // WEEK
    cl = cells_of_bar[ent]
    for per in periods:
        a, b = PERIODS[per]
        mp = (date >= a) & (date < b)
        for cell in (cells or CELLS):
            m = mp & ((cl == cell) if cell != "ALL" else (cl != ""))
            n = int(m.sum())
            if n < 20:
                rows.append(dict(cand=name, period=per, cell=cell, n=n))
                continue
            g = gross[m]
            net = g - COST_BP
            exc = g - ctrl[m]
            ok = np.isfinite(exc)
            yrs = pd.Series(net).groupby(B.year[ent][m]).mean()
            rows.append(dict(cand=name, period=per, cell=cell, n=n, gross=g.mean(), net=net.mean(),
                             net_stress=(g - STRESS_BP).mean(), t_net=cluster_t(net, wk[m]),
                             excess=exc[ok].mean() if ok.any() else np.nan,
                             t_excess=cluster_t(exc[ok], wk[m][ok]) if ok.sum() > 2 else np.nan,
                             yr_pos=float((yrs > 0).mean()), years=len(yrs),
                             net_dukas=(g - B.spread_bp[ent][m] - 0.5).mean(),
                             long_share=float((dirs[m] > 0).mean()), **(extra or {})))
    return rows
