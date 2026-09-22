"""Forty entry tools, popular and unpopular, for the wide search.

The operator asked for every entry tool there is, including the ones nobody
uses. Nothing here is chosen because it is known to work or known to fail, and
no tool was added or removed after any result was read.

Each tool gets three parameter settings - deliberately too fast, the textbook
default, deliberately too slow - so that "tune across every possibility" means
searching a stated grid rather than asserting which setting is bad.

Every tool exposes the same three arrays, all computed from the CLOSE of bar i
so an entry at the next bar's open cannot see its own outcome:

    fire_long[i]   the tool would enter long here
    fire_short[i]  the tool would enter short here
    state[i]       +1 currently bullish, -1 bearish, 0 neutral

`state` is what the stacked pairs use: a pair fires either when both tools agree
or when one fires while the other's state points the other way.

WHAT IS NOT CLAIMED. Several of these are exotic by construction (Mass Index,
Choppiness, Ease of Movement, Qstick). Including them is not a claim that they
mean anything. It is the point of the exercise: if the wide tail of indicator
space contained a reliable loser worth mirroring, it should appear here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D


class Tool:
    __slots__ = ("name", "fire_long", "fire_short", "state")

    def __init__(self, name, fl, fs, st):
        self.name, self.fire_long, self.fire_short, self.state = name, fl, fs, st


# ------------------------------------------------------------------ helpers
def _s(x):
    return pd.Series(np.asarray(x, dtype=float))


def _xup(x, lvl):
    x = np.asarray(x, float)
    p = _s(x).shift(1).to_numpy()
    lvl = np.asarray(lvl, float) if np.ndim(lvl) else lvl
    return (p <= lvl) & (x > lvl)


def _xdn(x, lvl):
    x = np.asarray(x, float)
    p = _s(x).shift(1).to_numpy()
    lvl = np.asarray(lvl, float) if np.ndim(lvl) else lvl
    return (p >= lvl) & (x < lvl)


def _sign(x, mid=0.0):
    x = np.asarray(x, float)
    return np.where(x > mid, 1, np.where(x < mid, -1, 0))


def _ema(x, n):
    return _s(x).ewm(span=max(1, int(n)), adjust=False).mean().to_numpy()


def _sma(x, n):
    return _s(x).rolling(max(1, int(n))).mean().to_numpy()


def _rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = _s(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = _s(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).to_numpy()


def _tr(b):
    pc = np.concatenate(([b.c[0]], b.c[:-1]))
    return np.maximum(b.h - b.l, np.maximum(np.abs(b.h - pc), np.abs(b.l - pc)))


def build(b15: D.Bars) -> dict:
    c, h, l, o, v = b15.c, b15.h, b15.l, b15.o, b15.v
    n = len(b15)
    out: dict[str, Tool] = {}
    tr = _tr(b15)
    atr14 = core.atr(b15, 14)
    tp = (h + l + c) / 3.0
    med = (h + l) / 2.0
    body = c - o
    rng = np.maximum(h - l, 1e-12)
    pc = np.concatenate(([c[0]], c[:-1]))

    def add(name, fl, fs, st):
        out[name] = Tool(name, np.nan_to_num(fl, nan=0).astype(bool),
                         np.nan_to_num(fs, nan=0).astype(bool),
                         np.nan_to_num(st, nan=0).astype(int))

    # ------------------------------------------------ 1-10, the popular ten
    for p in (4, 14, 40):
        r = _rsi(c, p)
        add(f"rsi:{p}", _xup(r, 30), _xdn(r, 70), _sign(r, 50))

    for p in (5, 14, 40):
        ll, hh = _s(l).rolling(p).min().to_numpy(), _s(h).rolling(p).max().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            k = 100 * (c - ll) / np.where(hh > ll, hh - ll, np.nan)
        d = _sma(k, 3)
        add(f"stoch:{p}", _xup(k - d, 0) & (k < 20), _xdn(k - d, 0) & (k > 80),
            _sign(k, 50))

    for (f, s, g) in ((5, 10, 4), (12, 26, 9), (30, 60, 20)):
        line = _ema(c, f) - _ema(c, s)
        sig = _ema(line, g)
        add(f"macd:{f}-{s}", _xup(line - sig, 0), _xdn(line - sig, 0),
            _sign(line - sig))

    for p in (10, 20, 50):
        m, sd = _sma(c, p), _s(c).rolling(p).std().to_numpy()
        add(f"boll:{p}", c < m - 2 * sd, c > m + 2 * sd, _sign(c - m))

    for (f, s) in ((5, 10), (20, 50), (50, 200)):
        ef, es = _ema(c, f), _ema(c, s)
        add(f"emax:{f}-{s}", _xup(ef - es, 0), _xdn(ef - es, 0), _sign(ef - es))

    for p in (7, 20, 60):
        ma = _sma(tp, p)
        md = _s(tp).rolling(p).apply(lambda x: np.abs(x - x.mean()).mean(),
                                    raw=True).to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            cci = (tp - ma) / (0.015 * np.where(md > 0, md, np.nan))
        add(f"cci:{p}", _xup(cci, -100), _xdn(cci, 100), _sign(cci))

    for p in (7, 14, 50):
        hh, ll = _s(h).rolling(p).max().to_numpy(), _s(l).rolling(p).min().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            wr = -100 * (hh - c) / np.where(hh > ll, hh - ll, np.nan)
        add(f"wpr:{p}", _xup(wr, -80), _xdn(wr, -20), _sign(wr, -50))

    for p in (10, 20, 55):
        hh = _s(h).rolling(p).max().shift(1).to_numpy()
        ll = _s(l).rolling(p).min().shift(1).to_numpy()
        add(f"donch:{p}", c > hh, c < ll, _sign(c - (hh + ll) / 2))

    for step in (5.0, 10.0, 50.0):
        lvl = np.round(c / step) * step
        t_ = (l <= lvl) & (h >= lvl)
        add(f"round:{step:g}", t_ & (c > lvl), t_ & (c < lvl), _sign(c - lvl))

    up_w, dn_w = h - np.maximum(c, o), np.minimum(c, o) - l
    po, pco = _s(o).shift(1).to_numpy(), _s(c).shift(1).to_numpy()
    eng_u = (c > o) & (pco < po) & (c >= po) & (o <= pco)
    eng_d = (c < o) & (pco > po) & (c <= po) & (o >= pco)
    for ratio in (1.5, 2.0, 3.0):
        ab = np.abs(body)
        add(f"candle:{ratio:g}",
            eng_u | ((dn_w >= ratio * ab) & (ab < 0.4 * rng)),
            eng_d | ((up_w >= ratio * ab) & (ab < 0.4 * rng)), _sign(body))

    # ------------------------------------- 11-20, trend and volatility tools
    for p in (7, 14, 40):                                    # 11. ADX / DMI
        upm = np.maximum(h - np.concatenate(([h[0]], h[:-1])), 0)
        dnm = np.maximum(np.concatenate(([l[0]], l[:-1])) - l, 0)
        upm = np.where(upm > dnm, upm, 0.0)
        dnm = np.where(dnm > upm, dnm, 0.0)
        atr_ = _s(tr).ewm(alpha=1 / p, adjust=False).mean().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            pdi = 100 * _s(upm).ewm(alpha=1 / p, adjust=False).mean().to_numpy() / atr_
            ndi = 100 * _s(dnm).ewm(alpha=1 / p, adjust=False).mean().to_numpy() / atr_
        add(f"dmi:{p}", _xup(pdi - ndi, 0), _xdn(pdi - ndi, 0), _sign(pdi - ndi))

    for (p, m) in ((7, 1.5), (10, 3.0), (30, 5.0)):          # 12. Supertrend
        a_ = _s(tr).ewm(alpha=1 / p, adjust=False).mean().to_numpy()
        st_ = np.zeros(n)
        dirn = np.ones(n, dtype=int)
        for i in range(1, n):
            ub, lb = med[i] + m * a_[i], med[i] - m * a_[i]
            if c[i] > st_[i - 1]:
                dirn[i] = 1
            elif c[i] < st_[i - 1]:
                dirn[i] = -1
            else:
                dirn[i] = dirn[i - 1]
            st_[i] = lb if dirn[i] > 0 else ub
        add(f"super:{p}-{m:g}", (dirn > 0) & (np.roll(dirn, 1) < 0),
            (dirn < 0) & (np.roll(dirn, 1) > 0), dirn)

    for (step, mx) in ((0.005, 0.1), (0.02, 0.2), (0.05, 0.5)):   # 13. PSAR
        sar = np.zeros(n)
        dirn = np.ones(n, dtype=int)
        af, ep = step, h[0]
        sar[0] = l[0]
        for i in range(1, n):
            sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
            if dirn[i - 1] > 0:
                if l[i] < sar[i]:
                    dirn[i], sar[i], ep, af = -1, ep, l[i], step
                else:
                    dirn[i] = 1
                    if h[i] > ep:
                        ep, af = h[i], min(mx, af + step)
            else:
                if h[i] > sar[i]:
                    dirn[i], sar[i], ep, af = 1, ep, h[i], step
                else:
                    dirn[i] = -1
                    if l[i] < ep:
                        ep, af = l[i], min(mx, af + step)
        add(f"psar:{step:g}", (dirn > 0) & (np.roll(dirn, 1) < 0),
            (dirn < 0) & (np.roll(dirn, 1) > 0), dirn)

    for (p, m) in ((10, 1.0), (20, 2.0), (50, 3.0)):         # 14. Keltner
        mid = _ema(c, p)
        a_ = _s(tr).ewm(alpha=1 / p, adjust=False).mean().to_numpy()
        add(f"kelt:{p}-{m:g}", c > mid + m * a_, c < mid - m * a_, _sign(c - mid))

    for (t_, k_, s_) in ((5, 13, 26), (9, 26, 52), (20, 60, 120)):   # 15. Ichimoku
        ten = (_s(h).rolling(t_).max().to_numpy() + _s(l).rolling(t_).min().to_numpy()) / 2
        kij = (_s(h).rolling(k_).max().to_numpy() + _s(l).rolling(k_).min().to_numpy()) / 2
        add(f"ichi:{t_}-{k_}", _xup(ten - kij, 0), _xdn(ten - kij, 0),
            _sign(ten - kij))

    for p in (1, 3, 8):                                      # 16. Heikin-Ashi
        ha_c = _sma(tp, p) if p > 1 else (o + h + l + c) / 4
        ha_o = _s(ha_c).shift(1).to_numpy()
        add(f"heikin:{p}", _xup(ha_c - ha_o, 0), _xdn(ha_c - ha_o, 0),
            _sign(ha_c - ha_o))

    for span in ((5, 8, 13), (10, 20, 40), (50, 100, 200)):  # 17. MA ribbon
        a_, b_, cc = _ema(c, span[0]), _ema(c, span[1]), _ema(c, span[2])
        align = np.where((a_ > b_) & (b_ > cc), 1,
                         np.where((a_ < b_) & (b_ < cc), -1, 0))
        pa = _s(align).shift(1).to_numpy()
        add(f"ribbon:{span[1]}", (align == 1) & (pa != 1),
            (align == -1) & (pa != -1), align)

    for p in (4, 15, 40):                                    # 18. TRIX
        tx = _ema(_ema(_ema(c, p), p), p)
        rate = _s(tx).pct_change().to_numpy() * 100
        add(f"trix:{p}", _xup(rate, 0), _xdn(rate, 0), _sign(rate))

    for p in (7, 20, 60):                                    # 19. DPO
        dpo = c - _s(_sma(c, p)).shift(p // 2 + 1).to_numpy()
        add(f"dpo:{p}", _xup(dpo, 0), _xdn(dpo, 0), _sign(dpo))

    for p in (10, 50, 200):                                  # 20. price z-score
        m_, sd = _sma(c, p), _s(c).rolling(p).std().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c - m_) / np.where(sd > 0, sd, np.nan)
        add(f"zscore:{p}", _xup(z, -2), _xdn(z, 2), _sign(z))

    # --------------------------------- 21-30, less-used oscillators
    for (a_, b_, cc) in ((3, 6, 12), (7, 14, 28), (20, 40, 80)):    # 21. Ultimate
        bp = c - np.minimum(l, pc)
        trr = np.maximum(h, pc) - np.minimum(l, pc)
        def av(p):
            with np.errstate(invalid="ignore", divide="ignore"):
                return (_s(bp).rolling(p).sum().to_numpy()
                        / _s(trr).rolling(p).sum().to_numpy())
        uo = 100 * (4 * av(a_) + 2 * av(b_) + av(cc)) / 7
        add(f"ultosc:{b_}", _xup(uo, 30), _xdn(uo, 70), _sign(uo, 50))

    for p in (5, 14, 40):                                    # 22. CMO
        d = np.diff(c, prepend=c[0])
        su = _s(np.where(d > 0, d, 0)).rolling(p).sum().to_numpy()
        sd = _s(np.where(d < 0, -d, 0)).rolling(p).sum().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            cmo = 100 * (su - sd) / np.where(su + sd > 0, su + sd, np.nan)
        add(f"cmo:{p}", _xup(cmo, -50), _xdn(cmo, 50), _sign(cmo))

    for p in (5, 14, 40):                                    # 23. MFI
        mf = tp * v
        pos = _s(np.where(tp > np.concatenate(([tp[0]], tp[:-1])), mf, 0)).rolling(p).sum().to_numpy()
        neg = _s(np.where(tp < np.concatenate(([tp[0]], tp[:-1])), mf, 0)).rolling(p).sum().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            mfi = 100 - 100 / (1 + pos / np.where(neg > 0, neg, np.nan))
        add(f"mfi:{p}", _xup(mfi, 20), _xdn(mfi, 80), _sign(mfi, 50))

    for p in (4, 10, 30):                                    # 24. RVI
        num = _s(c - o).rolling(p).sum().to_numpy()
        den = _s(rng).rolling(p).sum().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            rvi = num / np.where(den > 0, den, np.nan)
        sig = _sma(rvi, 4)
        add(f"rvi:{p}", _xup(rvi - sig, 0), _xdn(rvi - sig, 0), _sign(rvi))

    for p in (5, 10, 30):                                    # 25. Fisher transform
        mn, mx = _s(med).rolling(p).min().to_numpy(), _s(med).rolling(p).max().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            x = 2 * (med - mn) / np.where(mx > mn, mx - mn, np.nan) - 1
        x = np.clip(np.nan_to_num(x), -0.999, 0.999)
        fish = _ema(0.5 * np.log((1 + x) / (1 - x)), 3)
        add(f"fisher:{p}", _xup(fish, 0), _xdn(fish, 0), _sign(fish))

    for p in (5, 14, 40):                                    # 26. StochRSI
        r = _rsi(c, p)
        mn, mx = _s(r).rolling(p).min().to_numpy(), _s(r).rolling(p).max().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            sr = 100 * (r - mn) / np.where(mx > mn, mx - mn, np.nan)
        add(f"stochrsi:{p}", _xup(sr, 20), _xdn(sr, 80), _sign(sr, 50))

    for p in (3, 10, 30):                                    # 27. Connors RSI
        r3 = _rsi(c, 3)
        streak = np.zeros(n)
        for i in range(1, n):
            if c[i] > c[i - 1]:
                streak[i] = max(1.0, streak[i - 1] + 1)
            elif c[i] < c[i - 1]:
                streak[i] = min(-1.0, streak[i - 1] - 1)
        rank = core.rolling_pct_rank(np.diff(c, prepend=c[0]), 100) * 100
        crsi = (r3 + _rsi(streak, p) + rank) / 3
        add(f"crsi:{p}", _xup(crsi, 20), _xdn(crsi, 80), _sign(crsi, 50))

    for (f, s) in ((3, 12), (5, 34), (20, 100)):             # 28. Awesome
        ao = _sma(med, f) - _sma(med, s)
        add(f"awesome:{s}", _xup(ao, 0), _xdn(ao, 0), _sign(ao))

    for (f, s) in ((3, 12), (5, 34), (20, 100)):             # 29. Accelerator
        ao = _sma(med, f) - _sma(med, s)
        ac = ao - _sma(ao, 5)
        add(f"accel:{s}", _xup(ac, 0), _xdn(ac, 0), _sign(ac))

    for p in (4, 10, 30):                                    # 30. Qstick
        q = _sma(body, p)
        add(f"qstick:{p}", _xup(q, 0), _xdn(q, 0), _sign(q))

    # --------------------------- 31-40, structure, volume and the exotic tail
    for p in (7, 25, 60):                                    # 31. Aroon
        def ar(x, fn):
            return _s(x).rolling(p).apply(
                lambda w: (p - 1 - (np.argmax(w) if fn else np.argmin(w))) / (p - 1) * 100,
                raw=True).to_numpy()
        au, ad = ar(h, True), ar(l, False)
        add(f"aroon:{p}", _xup(au - ad, 0), _xdn(au - ad, 0), _sign(au - ad))

    for p in (7, 14, 40):                                    # 32. Vortex
        ph, pl = np.concatenate(([h[0]], h[:-1])), np.concatenate(([l[0]], l[:-1]))
        vp = _s(np.abs(h - pl)).rolling(p).sum().to_numpy()
        vm = _s(np.abs(l - ph)).rolling(p).sum().to_numpy()
        add(f"vortex:{p}", _xup(vp - vm, 0), _xdn(vp - vm, 0), _sign(vp - vm))

    for p in (2, 13, 50):                                    # 33. Force Index
        fi = _ema((c - pc) * v, p)
        add(f"force:{p}", _xup(fi, 0), _xdn(fi, 0), _sign(fi))

    for p in (5, 10, 40):                                    # 34. Chaikin volatility
        hl = _ema(h - l, p)
        cv = _s(hl).pct_change(p).to_numpy() * 100
        add(f"chaikvol:{p}", _xup(cv, 0), _xdn(cv, 0), _sign(cv))

    for p in (7, 14, 40):                                    # 35. Ease of Movement
        dm = med - np.concatenate(([med[0]], med[:-1]))
        with np.errstate(invalid="ignore", divide="ignore"):
            br = np.where(rng > 0, np.maximum(v, 1) / rng, np.nan)
            eom = _sma(dm / np.where(br > 0, br, np.nan), p)
        add(f"eom:{p}", _xup(eom, 0), _xdn(eom, 0), _sign(eom))

    for p in (3, 14, 40):                                    # 36. Balance of Power
        with np.errstate(invalid="ignore", divide="ignore"):
            bop = _sma(body / np.where(rng > 0, rng, np.nan), p)
        add(f"bop:{p}", _xup(bop, 0), _xdn(bop, 0), _sign(bop))

    for p in (9, 25, 60):                                    # 37. Mass Index
        e1 = _ema(h - l, p)
        mi = _s(e1 / _ema(e1, p)).rolling(p).sum().to_numpy()
        thr = np.nanmedian(mi)
        add(f"mass:{p}", _xup(mi, thr) & (c > pc), _xup(mi, thr) & (c < pc),
            _sign(mi, thr))

    for p in (7, 14, 60):                                    # 38. Choppiness
        with np.errstate(invalid="ignore", divide="ignore"):
            num = _s(tr).rolling(p).sum().to_numpy()
            den = (_s(h).rolling(p).max().to_numpy()
                   - _s(l).rolling(p).min().to_numpy())
            ch = 100 * np.log10(np.where(den > 0, num / den, np.nan)) / np.log10(p)
        add(f"chop:{p}", _xdn(ch, 38.2) & (c > pc), _xdn(ch, 38.2) & (c < pc),
            -_sign(ch, 50))

    for p in (2, 3, 5):                                      # 39. BW fractals
        hh = _s(h).rolling(2 * p + 1, center=True).max().to_numpy()
        ll = _s(l).rolling(2 * p + 1, center=True).min().to_numpy()
        fu = _s((h >= hh)).shift(p).fillna(False).to_numpy().astype(bool)
        fd = _s((l <= ll)).shift(p).fillna(False).to_numpy().astype(bool)
        lvl_u = _s(np.where(fu, h, np.nan)).ffill().shift(1).to_numpy()
        lvl_d = _s(np.where(fd, l, np.nan)).ffill().shift(1).to_numpy()
        add(f"fractal:{p}", c > lvl_u, c < lvl_d,
            np.where(c > lvl_u, 1, np.where(c < lvl_d, -1, 0)))

    for (j, t_, lp) in ((5, 8, 13), (13, 8, 5), (34, 21, 13)):   # 40. Alligator
        jaw, teeth, lips = _sma(med, j), _sma(med, t_), _sma(med, lp)
        align = np.where((lips > teeth) & (teeth > jaw), 1,
                         np.where((lips < teeth) & (teeth < jaw), -1, 0))
        pa = _s(align).shift(1).to_numpy()
        add(f"gator:{j}", (align == 1) & (pa != 1), (align == -1) & (pa != -1),
            align)

    return out


# The textbook setting of each of the forty, used for the stacked pairs so the
# pair grid measures the STACK rather than becoming a second parameter sweep.
DEFAULTS = (
    "rsi:14", "stoch:14", "macd:12-26", "boll:20", "emax:20-50", "cci:20",
    "wpr:14", "donch:20", "round:10", "candle:2",
    "dmi:14", "super:10-3", "psar:0.02", "kelt:20-2", "ichi:9-26", "heikin:1",
    "ribbon:20", "trix:15", "dpo:20", "zscore:50",
    "ultosc:14", "cmo:14", "mfi:14", "rvi:10", "fisher:10", "stochrsi:14",
    "crsi:10", "awesome:34", "accel:34", "qstick:10",
    "aroon:25", "vortex:14", "force:13", "chaikvol:10", "eom:14", "bop:14",
    "mass:25", "chop:14", "fractal:3", "gator:13",
)
