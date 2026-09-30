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
_HERE = Path(__file__).resolve().parent
for p in ("research/history", "research/wpwb_weekly", "research/pilot"):
    sys.path.insert(0, str(ROOT / p))
FROZEN = (_HERE / "FROZEN").exists()          # inside a forward-record snapshot: use its own copies (R13-3)
if FROZEN:
    import importlib.util as _ilu
    sys.path.insert(0, str(_HERE))
    for _m in ("vol", "build_all_tf", "external_traces"):   # R14-3: bind the snapshot copies before any
        _sp = _ilu.spec_from_file_location(_m, _HERE / f"{_m}.py")  # module can prepend a live directory
        _mod = _ilu.module_from_spec(_sp); sys.modules[_m] = _mod; _sp.loader.exec_module(_mod)
from build_all_tf import load_kind  # noqa: E402
import vol as V  # noqa: E402

COST_BP = 2.0
STRESS_BP = 4.0
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
PERIODS = {"DISC": ("2003-05-01", "2015-01-01"), "VAL": ("2015-01-01", "2021-01-01"),
           "HOLD": ("2021-01-01", "2026-09-01")}
import os as _os
TRACK = _os.environ.get("FOUNDRY_TRACK", "A")
if TRACK == "B":    # recent-era track (protocol Amendment 4)
    PERIODS = {"DISC": ("2015-01-01", "2021-01-01"), "VAL": ("2021-01-01", "2024-01-01"),
               "HOLD": ("2024-01-01", "2026-09-01")}
CELLS = ["ALL"] + [f"{v}/{tr}" for v in ("CALM", "NORMAL", "HIGH") for tr in ("DOWN", "FLAT", "UP")]
# marginal cells (added in batch2, docs/FOUNDRY_LEDGER.md): one axis only
CELLS2 = CELLS + [f"{v}/*" for v in ("CALM", "NORMAL", "HIGH")] + [f"*/{tr}" for tr in ("DOWN", "FLAT", "UP")] + ["NOTCALM/*"]


def cell_mask(cl, cell):
    if cell == "ALL":
        return cl != ""
    v, tr = cell.split("/")
    vv = np.array([x.split("/")[0] if x else "" for x in cl], object)
    tt = np.array([x.split("/")[1] if x else "" for x in cl], object)
    mv = (vv != "") if v == "*" else ((vv != "") & (vv != "CALM")) if v == "NOTCALM" else (vv == v)
    mt = (tt != "") if tr == "*" else (tt == tr)
    return mv & mt


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
    cuts = np.arange(FIRST_CUT, end + WEEK, WEEK, dtype=np.int64)   # includes the next cut after the data
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


def build(t, o, hh, ll, cc, sp, bid_c, bid_h, bid_l):
    cuts, cell = regimes(t, bid_c, bid_h, bid_l)
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
    return H, Dd, cuts, cell


def _dukascopy_arrays():
    df = load_kind("hour")
    t = df.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    o = ((df.o + df.ao) / 2).to_numpy(float); hh = ((df.h + df.ah) / 2).to_numpy(float)
    ll = ((df.l + df.al) / 2).to_numpy(float); cc = ((df.c + df.ac) / 2).to_numpy(float)
    sp = ((df.ao - df.o) / df.o * 1e4).to_numpy(float)
    _CACHE["vol"] = df.v.to_numpy(float)
    return t, o, hh, ll, cc, sp, df.c.to_numpy(float), df.h.to_numpy(float), df.l.to_numpy(float)


def load():
    if "bars" in _CACHE:
        return _CACHE["bars"]
    _CACHE["bars"] = build(*_dukascopy_arrays())
    _CACHE["bars"][0].v = _CACHE["vol"]
    return _CACHE["bars"]


def load_spliced(until=None):
    """Dukascopy H1 mid up to its last bar, then the live Exness H1 feed (bid + half the recorded
    spread ~ mid; measured offset vs Dukascopy mid $0.04) for later bars. `until`: drop bars
    opening at or after this epoch (so a forecast made at a cut cannot see later bars)."""
    sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
    import bars as BR
    t, o, hh, ll, cc, sp, bc, bh, bl = _dukascopy_arrays()
    m = BR.market(BR.load_bars(frozen=False))
    te = np.asarray(m.t, np.int64)
    k = te > t[-1]
    half = np.asarray(m.sp_in, float)[k] / 2
    eo, eh, el, ec = (np.asarray(getattr(m, a), float)[k] for a in ("o", "h", "l", "c"))
    esp = (2 * half) / ec * 1e4
    cat = lambda a, b: np.r_[a, b]
    arrs = [cat(t, te[k]), cat(o, eo + half), cat(hh, eh + half), cat(ll, el + half), cat(cc, ec + half), cat(sp, esp),
            cat(bc, ec), cat(bh, eh), cat(bl, el)]
    if until is not None:
        keep = arrs[0] < until
        arrs = [a[keep] for a in arrs]
    return build(*arrs)


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
    kk = B.hour if key == "hour" else (B.dow if key == "dow" else np.zeros(len(B.o), int))   # "none": time-free
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
        row = np.full(len(ce), np.nan)
        c2, d_, a2 = ce[ok], dirs[ok], a[ok]
        g, ex_ = simulate(B, c2, d_, stop_atr[ok] * a2, tgt_atr[ok] * a2, c2 + hold[ok])
        row[ok] = g - swap_bp(B, c2, ex_, d_)                 # R12-13: keep each control on its own trade
        out.append(row)
    return np.nanmean(np.vstack(out), axis=0)


def evaluate(name, B, cells_of_bar, ent, dirs, gross, ctrl, extra=None, periods=("DISC",), cells=None, stop_bp=None):
    """Rows per (period, cell) for one candidate family/params."""
    rows = []
    date = pd.to_datetime(B.t[ent], unit="s")
    wk = B.t[ent] // WEEK
    cl = cells_of_bar[ent]
    for per in periods:
        a, b = PERIODS[per]
        mp = (date >= a) & (date < b)
        for cell in (cells or CELLS):
            m = mp & cell_mask(cl, cell)
            n = int(m.sum())
            if n < 20:
                rows.append(dict(cand=name, period=per, cell=cell, n=n))
                continue
            g = gross[m]
            net = g - COST_BP
            exc = g - ctrl[m]
            ok = np.isfinite(exc)
            yrs = pd.Series(net).groupby(B.year[ent][m]).mean()
            rx = {}
            if stop_bp is not None:
                sb = stop_bp[m]
                nr = net / sb; er = exc / sb
                yr_r = pd.Series(nr).groupby(B.year[ent][m]).mean()
                rx = dict(net_R=nr.mean(), t_R=cluster_t(nr, wk[m]),
                          excess_R=er[ok].mean() if ok.any() else np.nan,
                          t_excess_R=cluster_t(er[ok], wk[m][ok]) if ok.sum() > 2 else np.nan,
                          yr_pos_R=float((yr_r > 0).mean()), stop_bp_med=float(np.median(sb)))
            rows.append(dict(cand=name, period=per, cell=cell, n=n, gross=g.mean(), net=net.mean(),
                             net_stress=(g - STRESS_BP).mean(), t_net=cluster_t(net, wk[m]),
                             excess=exc[ok].mean() if ok.any() else np.nan,
                             t_excess=cluster_t(exc[ok], wk[m][ok]) if ok.sum() > 2 else np.nan,
                             yr_pos=float((yrs > 0).mean()), years=len(yrs),
                             net_dukas=(g - B.spread_bp[ent][m] - 0.5).mean(),
                             long_share=float((dirs[m] > 0).mean()), **rx, **(extra or {})))
    return rows


def simulate_trail(B, ent, dirs, atr_e, init_mult, trail_mult, max_bars):
    """Trailing-stop exit. Initial stop init_mult*ATR; from the bar after entry the stop ratchets to
    (highest high of bars ent..t-1) - trail_mult*ATR for longs (mirror for shorts), never loosening.
    Stop checked on each bar's low/high (gap -> bar open); time exit at ent+max_bars-1 close."""
    ent = np.asarray(ent, int); dirs = np.asarray(dirs, float); atr_e = np.asarray(atr_e, float)
    n = len(ent)
    if n == 0:
        return np.zeros(0), np.zeros(0, int)
    last = np.minimum(ent + max_bars - 1, len(B.o) - 1)
    Hm = max_bars
    j = np.minimum(ent[:, None] + np.arange(Hm)[None, :], len(B.o) - 1)
    valid = (ent[:, None] + np.arange(Hm)[None, :]) <= last[:, None]
    hi, lo, op = B.h[j], B.l[j], B.o[j]
    ep = B.o[ent]
    up = dirs[:, None] > 0
    fav = np.where(up, hi, -lo)                              # favourable extreme per bar
    run = np.maximum.accumulate(fav, axis=1)
    prev = np.concatenate([np.full((n, 1), -np.inf), run[:, :-1]], axis=1)   # extreme of bars before t
    init = np.where(dirs > 0, ep - init_mult * atr_e, -(ep + init_mult * atr_e))[:, None]
    trail = prev - trail_mult * atr_e[:, None]
    stop_lvl = np.maximum(init, trail)                       # in "favourable" coordinates
    stop_lvl = np.maximum.accumulate(stop_lvl, axis=1)
    adverse = np.where(up, lo, -hi)
    hit = valid & (adverse <= stop_lvl)
    big = Hm + 5
    fs = np.where(hit.any(1), hit.argmax(1), big)
    r = np.arange(n)
    f_idx = np.minimum(fs, Hm - 1)
    lvl = stop_lvl[r, f_idx]
    o_f = np.where(dirs > 0, op[r, f_idx], -op[r, f_idx])
    fill_f = np.where((o_f < lvl) & (fs > 0), o_f, lvl)
    fill = np.where(dirs > 0, fill_f, -fill_f)
    exit_px = np.where(fs < big, fill, B.c[last])
    ex = np.where(fs < big, ent + fs, last)
    return dirs * (exit_px / ep - 1) * 1e4, ex


def matched_control_trail(B, cell_of_bar, ent, dirs, init_mult, trail_mult, max_bars, rng, reps=5, key="hour"):
    kk = B.hour if key == "hour" else B.dow
    keyarr = pd.Series(list(zip(B.year, kk, cell_of_bar)))
    groups = {i: g.to_numpy() for i, g in pd.Series(np.arange(len(B.o))).groupby(keyarr)}
    ekey = list(zip(B.year[ent], kk[ent], cell_of_bar[ent]))
    out = []
    for _ in range(reps):
        ce = np.minimum(np.array([rng.choice(groups[k_]) for k_ in ekey], int), len(B.o) - 2)
        a = B.atr[ce]; ok = np.isfinite(a)
        row = np.full(len(ce), np.nan)
        g, ex_ = simulate_trail(B, ce[ok], dirs[ok], a[ok], init_mult, trail_mult, max_bars)
        row[ok] = g - swap_bp(B, ce[ok], ex_, dirs[ok])      # R12-10 swap, R12-13 alignment
        out.append(row)
    return np.nanmean(np.vstack(out), axis=0)


# ------------------------------------------------------------------ swap (protocol Amendment 5)
_SWAP = {}
SWAP_MARKUP = 0.02      # % per year: measured Exness $0.5493/oz/night at $4,154.5 (4.83 %) minus the 2y yield then (4.81 %); frozen (R13-3)


def _swap_rate_series():
    """Annual long-swap rate (%) by calendar day = US 2y yield + markup (calibrated to the measured
    Exness $0.5493/oz/night at $4,154.5); before 2016 the first 2016 yield."""
    if "s" in _SWAP:
        return _SWAP["s"]
    fz = _HERE / "y2_frozen.csv"
    if fz.exists():                            # snapshot: frozen yield series (R13-3)
        y2 = pd.read_csv(fz, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        sys.path.insert(0, str(ROOT / "research" / "pilot"))
        import external_traces as X
        y2 = X.treasury("nominal")["BC_2YEAR"].dropna()
    s = (y2 + SWAP_MARKUP).clip(lower=0)
    _SWAP["s"] = (s, float(s.iloc[0]))
    return _SWAP["s"]


def swap_bp(B, ent, ex, dirs):
    """Long positions pay one night per daily rollover between the entry open and the exit bar's close.
    Rollover = 17:00 New York (21:00 UTC in US daylight time, 22:00 UTC otherwise; R12-10); the
    Wednesday rollover counts 3 nights; weekend days have none; each night uses its own date's rate.
    Shorts: 0."""
    s, s0 = _swap_rate_series()
    ent = np.asarray(ent, int); ex = np.asarray(ex, int); dirs = np.asarray(dirs, float)
    out = np.zeros(len(ent))
    idx = np.flatnonzero(dirs > 0)
    if not len(idx):
        return out
    t0 = B.t[ent[idx]]; t1 = B.t[ex[idx]] + B.step
    d0 = pd.to_datetime(t0.min() - 86400 * 2, unit="s").normalize(); d1 = pd.to_datetime(t1.max() + 86400 * 2, unit="s").normalize()
    days = pd.date_range(d0, d1, freq="D")
    roll = (days.tz_localize("America/New_York") + pd.Timedelta(hours=17)).tz_convert("UTC")
    roll_ep = (roll.tz_localize(None).astype("datetime64[s]").astype(np.int64)).to_numpy()
    dow = days.dayofweek.to_numpy()
    nights = np.where(dow == 2, 3, np.where(dow >= 5, 0, 1)).astype(float)
    rate = s.reindex(days, method="ffill").to_numpy()
    rate = np.where(np.isfinite(rate), rate, s0)
    cost = nights * rate / 100 / 365 * 1e4                         # bp for that rollover
    cum = np.r_[0.0, np.cumsum(cost)]
    a = np.searchsorted(roll_ep, t0, side="right"); b_ = np.searchsorted(roll_ep, t1, side="right")
    out[idx] = cum[b_] - cum[a]
    return out
