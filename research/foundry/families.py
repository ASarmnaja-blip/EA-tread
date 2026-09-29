"""Setup families for the Tool Foundry, batch 1 (registered in docs/FOUNDRY_LEDGER.md).
Every signal uses bars <= i-1; entry at bar i (open, or a stop level inside bar i+)."""
from __future__ import annotations

import numpy as np
import pandas as pd


class Spec:
    def __init__(self, name, tf, ent, dirs, stop, tgt, last, eprice=None):
        self.name, self.tf = name, tf
        self.ent = np.asarray(ent, int); self.dirs = np.asarray(dirs, float)
        self.stop = np.asarray(stop, float); self.tgt = np.asarray(tgt, float)
        self.last = np.asarray(last, int)
        self.eprice = None if eprice is None else np.asarray(eprice, float)


def nonoverlap(ent, last):
    keep, busy = [], -1
    for i, (e, l) in enumerate(zip(ent, last)):
        if e > busy:
            keep.append(i); busy = l
    return np.asarray(keep, int)


def _days(H):
    """Trading-day id per H1 bar (22:00 UTC anchor) and calendar date/hour."""
    idx = pd.to_datetime(H.t, unit="s")
    tday = ((H.t - 22 * 3600) // 86400).astype(np.int64)
    cal = (H.t // 86400).astype(np.int64)
    return tday, cal, idx.hour.to_numpy()


def _range_break(H, name, rng_hours, win_hours, exit_hour, tgts, fade=False):
    """Range = bars whose open hour is in rng_hours on a calendar date; first close beyond it
    during win_hours -> entry next bar (follow or, with fade=True, failed-break fade)."""
    _, cal, hr = _days(H)
    df = pd.DataFrame(dict(cal=cal, hr=hr, h=H.h, l=H.l, c=H.c, i=np.arange(len(H.c))))
    rg = df[df.hr.isin(rng_hours)].groupby("cal").agg(rh=("h", "max"), rl=("l", "min"), nr=("i", "size"))
    rg = rg[rg.nr == len(rng_hours)]
    w = df[df.hr.isin(win_hours)].join(rg, on="cal", how="inner")
    ex = df[df.hr == exit_hour].set_index("cal").i
    out = []
    if not fade:
        brk = w[(w.c > w.rh) | (w.c < w.rl)].groupby("cal").head(1)
        brk = brk[brk.cal.isin(ex.index)]
        ent = brk.i.to_numpy() + 1
        d = np.where(brk.c > brk.rh, 1.0, -1.0)
        last = ex.loc[brk.cal].to_numpy()
        ok = (ent <= last) & (cal[np.minimum(ent, len(cal) - 1)] == brk.cal.to_numpy())
        ent, d, last, rh, rl = ent[ok], d[ok], last[ok], brk.rh.to_numpy()[ok], brk.rl.to_numpy()[ok]
        e = H.o[ent]
        sd = np.where(d > 0, e - rl, rh - e)
        good = sd > 0
        for k in tgts:
            out.append(Spec(f"{name}_t{k}", "H1", ent[good], d[good], sd[good],
                            (sd * k)[good] if k else np.full(good.sum(), np.nan), last[good]))
    else:
        up = (w.h > w.rh) & (w.c <= w.rh)
        dn = (w.l < w.rl) & (w.c >= w.rl)
        f = w[up | dn].groupby("cal").head(1)
        f = f[f.cal.isin(ex.index)]
        ent = f.i.to_numpy() + 1
        d = np.where((f.h > f.rh).to_numpy() & (f.c <= f.rh).to_numpy(), -1.0, 1.0)
        last = ex.loc[f.cal].to_numpy()
        ok = (ent <= last) & (cal[np.minimum(ent, len(cal) - 1)] == f.cal.to_numpy())
        ent, d, last = ent[ok], d[ok], last[ok]
        fh, fl, rh, rl = (f[c_].to_numpy()[ok] for c_ in ("h", "l", "rh", "rl"))
        e = H.o[ent]
        sd = np.where(d < 0, fh - e, e - fl)
        tr = np.where(d < 0, e - rl, rh - e)
        good = (sd > 0) & (tr > 0)
        out.append(Spec(f"{name}_trange", "H1", ent[good], d[good], sd[good], tr[good], last[good]))
        out.append(Spec(f"{name}_t1", "H1", ent[good], d[good], sd[good], sd[good], last[good]))
    return out


def shock(H, follow):
    out = []
    r = np.r_[np.nan, np.diff(H.c)]
    for k in (2, 3):
        sig = np.abs(r) > k * H.atr            # bar i-1 move vs ATR known at i-1's open
        for hold in (3, 6, 12):
            ent = np.flatnonzero(sig[:-1]) + 1
            last = ent + hold - 1
            keep = nonoverlap(ent, last)
            ent, last = ent[keep], last[keep]
            d = np.sign(r[ent - 1]) * (1 if follow else -1)
            a = H.atr[ent]
            ok = np.isfinite(a) & (d != 0)
            out.append(Spec(f"SHOCK_{'CONT' if follow else 'REV'}_k{k}_h{hold}", "H1", ent[ok], d[ok],
                            2 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def donchian(D):
    out = []
    for N in (20, 55):
        hi = pd.Series(D.h).rolling(N).max().shift(1).to_numpy()   # channel of days d-N..d-1 known after d-1
        lo = pd.Series(D.l).rolling(N).min().shift(1).to_numpy()
        # signal on close of day d-1 vs channel of the N days before it -> enter open of day d
        cl = np.r_[np.nan, D.c[:-1]]; hi_p = np.r_[np.nan, hi[:-1]]; lo_p = np.r_[np.nan, lo[:-1]]
        d = np.where(cl > hi_p, 1.0, np.where(cl < lo_p, -1.0, 0.0))
        for hold in (10, 20):
            ent = np.flatnonzero(d != 0)
            last = ent + hold - 1
            keep = nonoverlap(ent, last)
            ent, last = ent[keep], last[keep]
            a = D.atr[ent]; ok = np.isfinite(a)
            out.append(Spec(f"DONCH_N{N}_h{hold}", "D1", ent[ok], d[ent][ok], 2.5 * a[ok],
                            np.full(ok.sum(), np.nan), last[ok]))
    return out


def sma_trend(D):
    c = pd.Series(D.c)
    s50, s200 = c.rolling(50).mean().to_numpy(), c.rolling(200).mean().to_numpy()
    cl = np.r_[np.nan, D.c[:-1]]; a50 = np.r_[np.nan, s50[:-1]]; a200 = np.r_[np.nan, s200[:-1]]
    d = np.where((cl > a200) & (a50 > a200), 1.0, np.where((cl < a200) & (a50 < a200), -1.0, 0.0))
    out = []
    for hold in (5, 20):
        ent = np.flatnonzero(d != 0)
        last = ent + hold - 1
        keep = nonoverlap(ent, last)
        ent, last = ent[keep], last[keep]
        a = D.atr[ent]; ok = np.isfinite(a)
        out.append(Spec(f"SMA_TREND_h{hold}", "D1", ent[ok], d[ent][ok], 3 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def rsi2(D):
    c = pd.Series(D.c)
    dlt = c.diff()
    up = dlt.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-dlt.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn)).to_numpy()
    s200 = c.rolling(200).mean().to_numpy()
    r_p = np.r_[np.nan, rsi[:-1]]; cl = np.r_[np.nan, D.c[:-1]]; a200 = np.r_[np.nan, s200[:-1]]
    d = np.where((r_p < 10) & (cl > a200), 1.0, np.where((r_p > 90) & (cl < a200), -1.0, 0.0))
    out = []
    for hold in (3, 5):
        ent = np.flatnonzero(d != 0)
        last = ent + hold - 1
        keep = nonoverlap(ent, last)
        ent, last = ent[keep], last[keep]
        a = D.atr[ent]; ok = np.isfinite(a)
        out.append(Spec(f"RSI2_h{hold}", "D1", ent[ok], d[ent][ok], 3 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def bb_rev(H):
    c = pd.Series(H.c)
    m, s = c.rolling(20).mean().to_numpy(), c.rolling(20).std().to_numpy()
    cl = H.c
    d0 = np.where(cl < m - 2 * s, 1.0, np.where(cl > m + 2 * s, -1.0, 0.0))   # at bar i-1 close
    out = []
    for hold in (6, 12):
        ent = np.flatnonzero(d0[:-1] != 0) + 1
        last = ent + hold - 1
        keep = nonoverlap(ent, last)
        ent, last = ent[keep], last[keep]
        d = d0[ent - 1]
        a = H.atr[ent]
        tgt = np.abs(m[ent - 1] - H.o[ent])
        ok = np.isfinite(a) & np.isfinite(tgt) & (tgt > 0)
        out.append(Spec(f"BB_REV_h{hold}", "H1", ent[ok], d[ok], 2 * a[ok], tgt[ok], last[ok]))
    return out


def nr7(H, D):
    """Day d-1 has the narrowest range of the last 7 -> OCO stop entries at its high/low
    during day d on H1 bars; stop at the other level; exit at the last H1 bar of day d."""
    rng = D.h - D.l
    nr = pd.Series(rng).rolling(7).apply(lambda x: float(x[-1] == x.min()), raw=True).to_numpy()
    tday, _, _ = _days(H)
    dday = (D.t - 22 * 3600) // 86400 + 0
    first = pd.Series(np.arange(len(H.t))).groupby(tday).min()
    lastb = pd.Series(np.arange(len(H.t))).groupby(tday).max()
    ents, dirs, stops, lasts, eps = [], [], [], [], []
    for di in np.flatnonzero(nr[:-1] == 1):
        nxt = int(dday[di + 1]) if di + 1 < len(dday) else None
        if nxt not in first.index:
            continue
        a, b = int(first[nxt]), int(lastb[nxt])
        hi_, lo_ = D.h[di], D.l[di]
        for i in range(a, b + 1):
            uh, dl = H.h[i] >= hi_, H.l[i] <= lo_
            if uh and dl:
                break
            if uh or dl:
                dirs.append(1.0 if uh else -1.0)
                ep = max(hi_, H.o[i]) if uh else min(lo_, H.o[i])
                ents.append(i); eps.append(ep); stops.append(abs(ep - (lo_ if uh else hi_))); lasts.append(b)
                break
    ents, dirs, stops, lasts, eps = map(np.asarray, (ents, dirs, stops, lasts, eps))
    ok = stops > 0
    return [Spec(f"NR7_t{k}", "H1", ents[ok], dirs[ok], stops[ok], stops[ok] * k, lasts[ok], eps[ok]) for k in (1, 2)]


def gap_fade(H):
    out = []
    gapt = np.r_[0, np.diff(H.t)] > 24 * 3600
    for k in (1, 2):
        g = np.r_[np.nan, H.o[1:] - H.c[:-1]]
        sig = gapt & (np.abs(g) > k * H.atr)
        ent = np.flatnonzero(sig)
        d = -np.sign(g[ent])
        tgt = np.abs(g[ent]); stop = np.abs(g[ent])
        ok = np.isfinite(tgt) & (d != 0)
        out.append(Spec(f"GAP_FADE_k{k}", "H1", ent[ok], d[ok], stop[ok], tgt[ok], ent[ok] + 11))
    return out


def tom(D):
    idx = pd.to_datetime(D.t + 2 * 3600, unit="s")    # day label (start 22:00 -> next calendar date)
    mon = idx.month.to_numpy()
    lastday = np.r_[mon[1:] != mon[:-1], False]
    ent = np.flatnonzero(lastday)
    a = D.atr[ent]; ok = np.isfinite(a)
    out = []
    for dsign, nm in ((1.0, "TOM_LONG"), (-1.0, "TOM_SHORT")):
        out.append(Spec(nm, "D1", ent[ok], np.full(ok.sum(), dsign), 3 * a[ok], np.full(ok.sum(), np.nan), ent[ok] + 3))
    return out


def batch1(H, D):
    s = []
    s += _range_break(H, "ASIA_BRK", list(range(0, 7)), list(range(7, 16)), 20, (1, 2, 0))
    s += _range_break(H, "ASIA_FAIL", list(range(0, 7)), list(range(7, 16)), 20, (), fade=True)
    s += _range_break(H, "NY_ORB", [13, 14], list(range(15, 20)), 20, (1, 2, 0))
    s += shock(H, follow=False) + shock(H, follow=True)
    s += donchian(D) + sma_trend(D) + rsi2(D)
    s += bb_rev(H) + nr7(H, D) + gap_fade(H) + tom(D)
    return s


# ------------------------------------------------------------------ batch 2 (momentum after batch-1 diagnosis)
def mom_h1(H):
    """Intraday time-series momentum: |return over the last L hours| > z * ATR * sqrt(L)
    -> follow at the next open, hold L hours, stop 2 ATR, no target."""
    out = []
    for L in (3, 6, 12, 24):
        rL = np.r_[np.full(L, np.nan), H.c[L:] - H.c[:-L]]            # known at close of bar i-1 -> use index i-1
        for z in (1.0, 1.5, 2.0):
            sig = np.abs(rL) > z * H.atr * np.sqrt(L)
            ent = np.flatnonzero(sig[:-1]) + 1
            last = ent + L - 1
            keep = nonoverlap(ent, last)
            ent, last = ent[keep], last[keep]
            d = np.sign(rL[ent - 1]); a = H.atr[ent]
            ok = np.isfinite(a) & (d != 0)
            out.append(Spec(f"MOM_L{L}_z{z}", "H1", ent[ok], d[ok], 2 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def pdhl_break(H, D):
    """Break of the previous trading day's high/low (first H1 close beyond it), follow,
    stop at the day's open-to-level midpoint distance = 1 ATR(H1)*2, exit at the day's last bar."""
    tday, _, _ = _days(H)
    dday = (D.t - 22 * 3600) // 86400
    ph = pd.Series(D.h, index=dday).shift(1); pl = pd.Series(D.l, index=dday).shift(1)
    lastb = pd.Series(np.arange(len(H.t))).groupby(tday).max()
    df = pd.DataFrame(dict(td=tday, c=H.c, i=np.arange(len(H.c))))
    df["ph"] = ph.reindex(df.td).to_numpy(); df["pl"] = pl.reindex(df.td).to_numpy()
    b = df[(df.c > df.ph) | (df.c < df.pl)].groupby("td").head(1)
    ent = b.i.to_numpy() + 1
    last = lastb.reindex(b.td).to_numpy()
    ok = np.isfinite(last) & (ent <= last)
    ent, last = ent[ok], last[ok].astype(int)
    d = np.where(b.c.to_numpy()[ok] > b.ph.to_numpy()[ok], 1.0, -1.0)
    a = H.atr[ent]; g = np.isfinite(a)
    return [Spec(f"PDHL_BRK_s{k}", "H1", ent[g], d[g], k * a[g], np.full(g.sum(), np.nan), last[g]) for k in (2, 4)]


def week_break(H):
    """Break of the previous week's high/low (weeks by Friday 22:15 cut), follow, hold to the
    end of the current week, stop 1x or 2x the previous week's range."""
    wk = (H.t - (22 * 3600 + 900) - 4 * 86400) // (7 * 86400)       # Friday-22:15-anchored week id
    g = pd.DataFrame(dict(wk=wk, h=H.h, l=H.l, c=H.c, i=np.arange(len(H.c))))
    agg = g.groupby("wk").agg(h=("h", "max"), l=("l", "min"), last=("i", "max"))
    g["ph"] = agg.h.shift(1).reindex(g.wk).to_numpy(); g["pl"] = agg.l.shift(1).reindex(g.wk).to_numpy()
    g["pr"] = (agg.h - agg.l).shift(1).reindex(g.wk).to_numpy()
    b = g[(g.c > g.ph) | (g.c < g.pl)].groupby("wk").head(1)
    ent = b.i.to_numpy() + 1
    last = agg["last"].reindex(b.wk).to_numpy()
    ok = ent <= last
    d = np.where(b.c.to_numpy() > b.ph.to_numpy(), 1.0, -1.0)
    out = []
    for k in (0.5, 1.0):
        out.append(Spec(f"WEEK_BRK_s{k}", "H1", ent[ok], d[ok], k * b.pr.to_numpy()[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def batch2(H, D):
    s = mom_h1(H) + pdhl_break(H, D) + week_break(H)
    s += shock(H, follow=True)                       # re-scored on the new marginal cells
    s += _range_break(H, "ASIA_BRK", list(range(0, 7)), list(range(7, 16)), 20, (0,))
    return s


def batch3(H, D):
    """Continuation families from batches 1-2 re-scored in risk units (R = net bp / stop bp)."""
    s = shock(H, follow=True) + mom_h1(H) + pdhl_break(H, D) + week_break(H)
    s += _range_break(H, "ASIA_BRK", list(range(0, 7)), list(range(7, 16)), 20, (0,))
    return s
