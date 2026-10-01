"""Candle Lab (operator 2026-10-01: "อยากรู้ว่าทำไมถึงแพ้ ทำไมถึงชนะ ... การขยับของแท่งเทียนมีผลยังไงบ้าง ... เขียนโค้ดที่โครตเทพเพื่อแกะรายละเอียด").
Multi-timeframe bars from one base series per asset, candle anatomy (single bar, multi-bar, inside-the-bar path, higher-timeframe context), and the
future of every bar (next-bar anatomy, forward returns, MFE / MAE, first passage), all leak-free and in ATR units. No clipping or capping of any
value (operator rule: no caps, no cut data). Research only.

Timing: a feature of bar t uses bars <= t only (it is known at the close of bar t); outcomes start at the open of bar t+1 (the earliest entry)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "wrwr"), str(ROOT / "research" / "foundry"), str(ROOT / "research" / "history")]

TF_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 7 * 86400}
ANCHOR = 22 * 3600                    # H4 and D1 are anchored at 22:00 UTC so that they nest inside the trading day and week
HORIZONS = (1, 2, 3, 5, 10, 20)


# ------------------------------------------------------------------ base series
def base_gold():
    """Gold M5 2009-03 .. 2026-09: HistData M1 -> M5 (corrected clock, mid-adjusted) spliced with Exness M5 mid from 2021."""
    z = np.load(ROOT / "data" / "history" / "XAUUSD_M5_2009_2026_spliced.npz")
    return dict(t=z["t"].astype(np.int64), o=z["o"], h=z["h"], l=z["l"], c=z["c"], v=np.ones(len(z["t"])), step=300)


def base_silver():
    import xag as X
    M, _ = X.read_m1()
    t = M.t.to_numpy(np.int64)
    k = t // 300
    g = pd.DataFrame(dict(k=k, o=M.o.to_numpy(float), h=M.h.to_numpy(float), l=M.l.to_numpy(float), c=M.c.to_numpy(float))).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("o", "size"))
    return dict(t=g.index.to_numpy(np.int64) * 300, o=g.o.to_numpy(float), h=g.h.to_numpy(float), l=g.l.to_numpy(float), c=g.c.to_numpy(float),
                v=g.v.to_numpy(float), step=300)


def cut_grid(t_end):
    first = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
    return np.arange(first, int(t_end) + 2 * 7 * 86400, 7 * 86400, dtype=np.int64)


# ------------------------------------------------------------------ bars
class Bars:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __len__(self):
        return len(self.t)


def resample(base, tf, cuts):
    """Bars of timeframe tf from the base series, with the position of each bar's high and low inside it (0 = first base bar, 1 = last)."""
    t = base["t"]
    if tf == "W1":
        key = np.searchsorted(cuts, t, side="left") - 1
    elif tf in ("H4", "D1"):
        key = (t - ANCHOR) // TF_SECONDS[tf]
    else:
        key = t // TF_SECONDS[tf]
    df = pd.DataFrame(dict(k=key, t=t, o=base["o"], h=base["h"], l=base["l"], c=base["c"], v=base["v"], i=np.arange(len(t))))
    g = df.groupby("k", sort=True)
    a = g.agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), n=("t", "size"),
              i0=("i", "first"), i1=("i", "last"))
    ih = df.loc[g.h.idxmax().to_numpy(), "i"].to_numpy(); il = df.loc[g.l.idxmin().to_numpy(), "i"].to_numpy()
    span = np.maximum(a.i1.to_numpy() - a.i0.to_numpy(), 1)
    minimum = {"M5": 1, "M15": 2, "H1": 6, "H4": 24, "D1": 120, "W1": 600}[tf]
    keep = a.n.to_numpy() >= minimum
    B = Bars(tf=tf, t=a.t.to_numpy(np.int64)[keep], o=a.o.to_numpy(float)[keep], h=a.h.to_numpy(float)[keep], l=a.l.to_numpy(float)[keep],
             c=a.c.to_numpy(float)[keep], v=a.v.to_numpy(float)[keep], n=a.n.to_numpy()[keep],
             hi_pos=((ih - a.i0.to_numpy()) / span)[keep], lo_pos=((il - a.i0.to_numpy()) / span)[keep], key=a.index.to_numpy()[keep])
    B.atr = atr(B.h, B.l, B.c, 14)
    return B


def atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    return pd.Series(tr).rolling(n, min_periods=n).mean().to_numpy()            # includes bar t: known at its close


# ------------------------------------------------------------------ anatomy (known at the close of bar t)
def anatomy(B):
    o, h, l, c, A = B.o, B.h, B.l, B.c, B.atr
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        rngz = np.where(rng > 0, rng, np.nan)
        F = {}
        top, bot = np.maximum(o, c), np.minimum(o, c)
        F["body_atr"] = (c - o) / A
        F["body_frac"] = np.abs(c - o) / rngz
        F["upwick_atr"] = (h - top) / A
        F["lowick_atr"] = (bot - l) / A
        F["upwick_frac"] = (h - top) / rngz
        F["lowick_frac"] = (bot - l) / rngz
        F["uld"] = ((h - top) - (bot - l)) / rngz                               # upper minus lower shadow, share of the range
        F["clv"] = (c - l) / rngz                                               # where the close sits in the bar (0 low .. 1 high)
        F["range_atr"] = rng / A
        pc = np.r_[np.nan, c[:-1]]
        F["gap_atr"] = (o - pc) / A
        F["ret1_atr"] = (c - pc) / A
        color = np.sign(c - o)
        F["color"] = color
        run = np.zeros(len(c))
        for i in range(1, len(c)):
            run[i] = run[i - 1] + color[i] if (color[i] != 0 and np.sign(run[i - 1]) == color[i]) else color[i]
        F["run"] = run                                                          # signed count of consecutive same-colour bars
        for N in (3, 5, 10):
            s_up = pd.Series(h - top).rolling(N).sum(); s_lo = pd.Series(bot - l).rolling(N).sum(); s_rg = pd.Series(rng).rolling(N).sum()
            F[f"wickpress{N}"] = ((s_lo - s_up) / s_rg).to_numpy()              # + = buyers defending lows, - = sellers capping highs
            F[f"bodysum{N}_atr"] = (pd.Series(c - o).rolling(N).sum() / A).to_numpy()
            F[f"clv_mean{N}"] = pd.Series(F["clv"]).rolling(N).mean().to_numpy()
        ph, pl = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
        po = np.r_[np.nan, o[:-1]]
        F["inside"] = ((h < ph) & (l > pl)).astype(float)
        F["outside"] = ((h > ph) & (l < pl)).astype(float)
        F["engulf_bull"] = ((c > o) & (pc < po) & (c >= po) & (o <= pc)).astype(float)
        F["engulf_bear"] = ((c < o) & (pc > po) & (c <= po) & (o >= pc)).astype(float)
        body = np.abs(c - o)
        F["pin_bull"] = (((bot - l) >= 2 * body) & (((bot - l) / rngz) >= 0.6)).astype(float)
        F["pin_bear"] = (((h - top) >= 2 * body) & (((h - top) / rngz) >= 0.6)).astype(float)
        F["doji"] = ((body / rngz) <= 0.1).astype(float)
        F["marubozu_bull"] = ((c > o) & (((h - top) + (bot - l)) / rngz <= 0.1)).astype(float)
        F["marubozu_bear"] = ((c < o) & (((h - top) + (bot - l)) / rngz <= 0.1)).astype(float)
        hh5 = pd.Series(h).rolling(5).max().shift(1).to_numpy(); ll5 = pd.Series(l).rolling(5).min().shift(1).to_numpy()
        F["sweep_high_reject"] = ((h > hh5) & (c < hh5)).astype(float)          # wick above the 5-bar high, close back below
        F["sweep_low_reject"] = ((l < ll5) & (c > ll5)).astype(float)
        F["break_close_up"] = (c > hh5).astype(float)
        F["break_close_dn"] = (c < ll5).astype(float)
        r7 = pd.Series(rng).rolling(7)
        F["nr7"] = (rng <= r7.min().to_numpy()).astype(float)
        F["wr7"] = (rng >= r7.max().to_numpy()).astype(float)
        c3 = (color > 0) & (np.r_[0, color[:-1]] > 0) & (np.r_[0, 0, color[:-2]] > 0)
        F["three_up"] = c3.astype(float)
        F["three_down"] = ((color < 0) & (np.r_[0, color[:-1]] < 0) & (np.r_[0, 0, color[:-2]] < 0)).astype(float)
        F["hi_pos"] = B.hi_pos                                                   # inside-the-bar path: when the high was made (0 early, 1 late)
        F["lo_pos"] = B.lo_pos
        F["high_first"] = (B.hi_pos < B.lo_pos).astype(float)
        F["path_tilt"] = B.lo_pos - B.hi_pos                                     # + = low early / high late (bullish path)
        F["sma20_dist"] = ((c - pd.Series(c).rolling(20).mean().to_numpy()) / A)
        F["sma50_dist"] = ((c - pd.Series(c).rolling(50).mean().to_numpy()) / A)
    return pd.DataFrame(F)


def htf_context(X, Y, prefix):
    """Higher-timeframe context for every bar of X (lower TF): the last COMPLETED Y bar (anatomy) and the FORMING Y bar up to X's close."""
    xc = X.t + TF_SECONDS[X.tf]                                                   # close time of each X bar
    yc = Y.t + TF_SECONDS[Y.tf] if Y.tf != "W1" else np.r_[Y.t[1:], Y.t[-1] + TF_SECONDS["W1"]]
    j = np.searchsorted(yc, xc, side="right") - 1                                 # last Y bar closed by X's close
    FA = anatomy(Y)
    out = {}
    for f in ("clv", "body_atr", "uld", "color", "run", "range_atr", "sma20_dist"):
        v = FA[f].to_numpy()
        out[f"{prefix}_last_{f}"] = np.where(j >= 0, v[np.maximum(j, 0)], np.nan)
    # forming Y bar: the Y bar that contains X's close (open_Y <= X close < close_Y)
    k = np.searchsorted(Y.t, xc - 1, side="right") - 1
    grp = pd.Series(k)
    hi_so_far = pd.Series(X.h).groupby(grp.values).cummax().to_numpy(); lo_so_far = pd.Series(X.l).groupby(grp.values).cummin().to_numpy()
    yo = np.where(k >= 0, Y.o[np.maximum(k, 0)], np.nan)
    ya = np.where(j >= 0, Y.atr[np.maximum(j, 0)], np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[f"{prefix}_form_pos"] = (X.c - lo_so_far) / np.where(hi_so_far > lo_so_far, hi_so_far - lo_so_far, np.nan)
        out[f"{prefix}_form_ret_atr"] = (X.c - yo) / ya
        out[f"{prefix}_form_range_atr"] = (hi_so_far - lo_so_far) / ya
    return pd.DataFrame(out)


# ------------------------------------------------------------------ outcomes (from the open of bar t+1)
def outcomes(B):
    o, h, l, c, A = B.o, B.h, B.l, B.c, B.atr
    n = len(c); Hmax = max(HORIZONS)
    e = np.r_[o[1:], np.nan]                                                      # entry price for a signal at bar t
    O = {}
    for k in HORIZONS:
        O[f"ret{k}"] = (np.r_[c[k:], np.full(k, np.nan)] - e) / A                 # close of bar t+k minus the open of bar t+1
    hw = swv(np.r_[h[1:], np.full(Hmax, np.nan)], Hmax)[:n]; lw = swv(np.r_[l[1:], np.full(Hmax, np.nan)], Hmax)[:n]
    for k in (1, 5, 20):
        with np.errstate(invalid="ignore"):
            O[f"mfe{k}"] = (np.nanmax(hw[:, :k], axis=1) - e) / A                    # best excursion for a long within k bars
            O[f"mae{k}"] = (e - np.nanmin(lw[:, :k], axis=1)) / A
    for a in (1.0, 2.0):
        up = (hw >= (e + a * A)[:, None]); dn = (lw <= (e - a * A)[:, None])
        fu = np.where(up.any(1), up.argmax(1), Hmax + 1); fd = np.where(dn.any(1), dn.argmax(1), Hmax + 1)
        fp = np.where(fu < fd, 1.0, np.where(fd < fu, 0.0, np.where(fu <= Hmax, 0.5, np.nan)))
        O[f"fp_up{int(a)}"] = fp                                                  # 1 = +a ATR touched before -a ATR within 20 bars
    nxt = anatomy(B).shift(-1)
    for f in ("color", "body_atr", "upwick_atr", "lowick_atr", "range_atr", "clv"):
        O[f"next_{f}"] = nxt[f].to_numpy()
    O["next_up"] = (O["next_color"] > 0).astype(float); O["next_up"][np.isnan(O["next_color"])] = np.nan
    return pd.DataFrame(O)


def mirror_base(base, seed):
    """Placebo: every base bar mirrored at random around the previous close (direction destroyed, volatility and clock kept)."""
    rng = np.random.default_rng(seed)
    o, h, l, c = (np.asarray(base[x], float) for x in ("o", "h", "l", "c"))
    c1 = np.r_[o[0], c[:-1]]
    lo_, lh, ll, lc = (np.log(x / c1) for x in (o, h, l, c))
    s = np.where(rng.random(len(c)) < 0.5, -1.0, 1.0)
    ncl = np.log(c[0]) + np.cumsum(np.r_[0.0, (s * lc)[1:]]); nc1 = np.r_[ncl[0] - lc[0], ncl[:-1]]
    out = dict(base)
    out["o"] = np.exp(nc1 + s * lo_); out["c"] = np.exp(ncl)
    out["h"] = np.exp(nc1 + np.where(s > 0, lh, -ll)); out["l"] = np.exp(nc1 + np.where(s > 0, ll, -lh))
    return out
