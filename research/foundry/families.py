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


# ------------------------------------------------------------------ batch 4: WPWB router (weekly regime -> tool)
def cont_union(H, hold=6):
    """One continuation tool pooled from the batch 1-3 signals: follow when the last bar moved
    > 3 ATR, or the last 6 h moved > 1.5 ATR*sqrt(6), or the last 12 h > 1.5 ATR*sqrt(12).
    Hold `hold` hours, stop 2 ATR, no target, one position at a time."""
    c, a = H.c, H.atr
    sigs = []
    r1 = np.r_[np.nan, np.diff(c)]
    sigs.append((np.abs(r1) > 3 * a, np.sign(r1)))
    for L in (6, 12):
        rL = np.r_[np.full(L, np.nan), c[L:] - c[:-L]]
        sigs.append((np.abs(rL) > 1.5 * a * np.sqrt(L), np.sign(rL)))
    fire = np.zeros(len(c), bool); d = np.zeros(len(c))
    for m, sg in sigs:
        new = m & ~fire
        d[new] = sg[new]; fire |= m
    ent = np.flatnonzero(fire[:-1]) + 1
    last = ent + hold - 1
    keep = nonoverlap(ent, last)
    ent, last = ent[keep], last[keep]
    dd = d[ent - 1]; aa = a[ent]
    ok = np.isfinite(aa) & (dd != 0)
    return Spec(f"CONT_UNION_h{hold}", "H1", ent[ok], dd[ok], 2 * aa[ok], np.full(ok.sum(), np.nan), last[ok])


def batch4(H, D):
    return [cont_union(H, 6)]


# ------------------------------------------------------------------ batch 5: continuation by entry session
SESSIONS = {"ASIA": range(0, 7), "LONDON": range(7, 12), "NYAM": range(12, 17), "LATE": range(17, 22), "OPEN": (22, 23)}


def by_session(H, spec):
    out = []
    hr = H.hour[spec.ent]
    for nm, hs in SESSIONS.items():
        m = np.isin(hr, list(hs))
        out.append(Spec(f"{spec.name}@{nm}", spec.tf, spec.ent[m], spec.dirs[m], spec.stop[m], spec.tgt[m], spec.last[m],
                        None if spec.eprice is None else spec.eprice[m]))
    return out


def batch5(H, D):
    base = [cont_union(H, 6)]
    base += [x for x in shock(H, follow=True) if x.name == "SHOCK_CONT_k3_h6"]
    base += [x for x in mom_h1(H) if x.name == "MOM_L6_z1.5"]
    out = []
    for b in base:
        out += by_session(H, b)
    return out


def menu1(H, D):
    """Selector menu v1: every variant of batches 1-2 plus CONT_UNION_h6, both directions, deduplicated."""
    seen, out = set(), []
    for s in batch1(H, D) + batch2(H, D) + [cont_union(H, 6)]:
        if s.name not in seen:
            seen.add(s.name); out.append(s)
    return out


def mirror(sp):
    return Spec(sp.name + "~INV", sp.tf, sp.ent, -sp.dirs, sp.stop, sp.tgt, sp.last, sp.eprice)


def longer(H):
    """Longer-hold continuation (cost is a smaller share of the move)."""
    out = []
    r1 = np.r_[np.nan, np.diff(H.c)]
    for k in (2, 3):
        for hold in (24, 48):
            sig = np.abs(r1) > k * H.atr
            ent = np.flatnonzero(sig[:-1]) + 1
            last = ent + hold - 1
            keep = nonoverlap(ent, last); ent, last = ent[keep], last[keep]
            d = np.sign(r1[ent - 1]); a = H.atr[ent]; ok = np.isfinite(a) & (d != 0)
            out.append(Spec(f"SHOCK_CONT_k{k}_h{hold}", "H1", ent[ok], d[ok], 3 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    for L in (6, 12):
        rL = np.r_[np.full(L, np.nan), H.c[L:] - H.c[:-L]]
        sig = np.abs(rL) > 1.5 * H.atr * np.sqrt(L)
        ent = np.flatnonzero(sig[:-1]) + 1
        last = ent + 4 * L - 1
        keep = nonoverlap(ent, last); ent, last = ent[keep], last[keep]
        d = np.sign(rL[ent - 1]); a = H.atr[ent]; ok = np.isfinite(a) & (d != 0)
        out.append(Spec(f"MOM_L{L}_z1.5_h{4 * L}", "H1", ent[ok], d[ok], 3 * a[ok], np.full(ok.sum(), np.nan), last[ok]))
    return out


def menu2(H, D):
    base = menu1(H, D) + longer(H)
    return base + [mirror(s) for s in base]


def menu3(H, D):
    """menu2 restricted by a COST rule only: keep variants whose median stop is >= 100 bp
    (2 bp cost <= 2 % of R). No performance information is used to build it."""
    out = []
    for s in menu2(H, D):
        B = H if s.tf == "H1" else D
        ep = s.eprice if s.eprice is not None else B.o[s.ent]
        if len(s.ent) and np.nanmedian(s.stop / ep * 1e4) >= 100:
            out.append(s)
    return out


def hod(H):
    """Hour-of-day variants: enter at the open of UTC hour h every weekday, hold 4 h, stop 2 ATR,
    fixed direction (long and short separately)."""
    out = []
    for h in range(24):
        ent = np.flatnonzero(H.hour == h)
        ent = ent[ent + 3 < len(H.t)]
        a = H.atr[ent]; ok = np.isfinite(a)
        ent, a = ent[ok], a[ok]
        for d, nm in ((1.0, "L"), (-1.0, "S")):
            out.append(Spec(f"HOD_{h:02d}{nm}", "H1", ent, np.full(len(ent), d), 2 * a, np.full(len(ent), np.nan), ent + 3))
    return out


def dow(D):
    out = []
    for w in range(5):
        lab = pd.to_datetime(D.t + 2 * 3600, unit="s").dayofweek.to_numpy()
        ent = np.flatnonzero(lab == w)
        a = D.atr[ent]; ok = np.isfinite(a); ent, a = ent[ok], a[ok]
        for d, nm in ((1.0, "L"), (-1.0, "S")):
            out.append(Spec(f"DOW_{w}{nm}", "D1", ent, np.full(len(ent), d), 2 * a, np.full(len(ent), np.nan), ent))
    return out


def menu4(H, D):
    return menu2(H, D) + hod(H) + dow(D)


def extend_hold(sp, factor=4):
    """Same entries and direction, holding `factor` times longer, stop 1.5x wider, no target."""
    last = sp.ent + (sp.last - sp.ent + 1) * factor - 1
    return Spec(sp.name + f"^x{factor}", sp.tf, sp.ent, sp.dirs, sp.stop * 1.5, np.full(len(sp.ent), np.nan), last, sp.eprice)


def menu5(H, D):
    base = menu4(H, D)
    return base + [extend_hold(s) for s in base if s.tf == "H1"]


# ------------------------------------------------------------------ batch 18: WPWB forecast-scaled weekly OCO
def wpwb_oco(H):
    """At each Friday 22:15 UTC cut: sigma_hat = sqrt(WPWB B0 EWMA forecast of this week's RV).
    Reference C = open of the week's first H1 bar. Buy stop at C*(1 + k*s), sell stop at C*(1 - k*s)
    (s = sigma_hat in fraction); first touch wins (both in one bar -> skip, conservative); stop back
    to C (distance k*s*C) or at the opposite level (2k*s*C); exit at the week's last H1 bar."""
    import vol as V
    cuts = np.arange(E_FIRST_CUT, int(H.t[-1]), 7 * 86400, dtype=np.int64)
    rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
    f = V.ewma_forecast(V.mask_invalid(rv_raw, nb))
    close_t = H.t + 3600
    out = {}
    for k in (0.25, 0.5, 1.0):
        for sm in (1, 2):
            out[(k, sm)] = ([], [], [], [], [])
    for w in range(1, len(cuts)):
        if not np.isfinite(f[w]):
            continue
        a = cuts[w]
        i0 = np.searchsorted(H.t, a, side="right"); i1 = np.searchsorted(close_t, a + 7 * 86400, side="right") - 1
        if i1 - i0 < 80:
            continue
        C = H.o[i0]; s = np.sqrt(f[w]) / 1e4
        hi, lo = H.h[i0:i1 + 1], H.l[i0:i1 + 1]
        for k in (0.25, 0.5, 1.0):
            up, dn = C * (1 + k * s), C * (1 - k * s)
            hu = hi >= up; hd = lo <= dn
            j = np.flatnonzero(hu | hd)
            if not len(j) or (hu[j[0]] and hd[j[0]]):
                continue
            j = int(j[0]); d = 1.0 if hu[j] else -1.0
            ep = max(up, H.o[i0 + j]) if d > 0 else min(dn, H.o[i0 + j])
            for sm in (1, 2):
                L = out[(k, sm)]
                L[0].append(i0 + j); L[1].append(d); L[2].append(sm * k * s * C); L[3].append(i1); L[4].append(ep)
    res = []
    for (k, sm), (e, d, st, la, ep) in out.items():
        res.append(Spec(f"WPWB_OCO_k{k}_s{'C' if sm == 1 else 'OPP'}", "H1", e, d, st, np.full(len(e), np.nan), la, ep))
    return res


E_FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))


def batch18(H, D):
    return wpwb_oco(H)


# ------------------------------------------------------------------ batch 19: WPWB pace-compression breakout
def pace_brk(H):
    """Checkpoint Tue or Wed 22:00 UTC. pace = RV so far / (F * bars_so_far / 115), F = WPWB B0
    forecast. If pace < p*: OCO stops at Cc(1 +/- k * sqrt(F * (1 - frac))) around the last close,
    first touch wins, stop back at Cc, exit at the week's last bar."""
    import vol as V
    cuts = np.arange(E_FIRST_CUT, int(H.t[-1]), 7 * 86400, dtype=np.int64)
    rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
    f = V.ewma_forecast(V.mask_invalid(rv_raw, nb))
    close_t = H.t + 3600
    lr = np.r_[np.nan, np.diff(np.log(H.c))]
    res = {}
    for w in range(1, len(cuts)):
        if not np.isfinite(f[w]):
            continue
        a = cuts[w]
        i0 = np.searchsorted(H.t, a, side="right"); i1 = np.searchsorted(close_t, a + 7 * 86400, side="right") - 1
        if i1 - i0 < 80:
            continue
        for day, off in (("TUE", 3 * 86400 + 23 * 3600 + 45 * 60), ("WED", 4 * 86400 + 23 * 3600 + 45 * 60)):
            tc = a + off
            ic = np.searchsorted(close_t, tc, side="right")          # first bar closing after tc
            if ic <= i0 + 10 or ic >= i1:
                continue
            nso = ic - i0
            rv_so = float(np.nansum(lr[i0 + 1:ic] ** 2) * 1e8)
            frac = min(nso / 115.0, 0.95)
            pace = rv_so / (f[w] * frac)
            Cc = H.c[ic - 1]
            srem = np.sqrt(f[w] * (1 - frac)) / 1e4
            for p_star in (0.6, 0.8):
                if pace >= p_star:
                    continue
                for k in (0.25, 0.5):
                    up, dn = Cc * (1 + k * srem), Cc * (1 - k * srem)
                    hu = H.h[ic:i1 + 1] >= up; hd = H.l[ic:i1 + 1] <= dn
                    j = np.flatnonzero(hu | hd)
                    if not len(j) or (hu[j[0]] and hd[j[0]]):
                        continue
                    j = int(j[0]); d = 1.0 if hu[j] else -1.0
                    ep = max(up, H.o[ic + j]) if d > 0 else min(dn, H.o[ic + j])
                    L = res.setdefault((day, p_star, k), ([], [], [], [], []))
                    L[0].append(ic + j); L[1].append(d); L[2].append(k * srem * Cc); L[3].append(i1); L[4].append(ep)
    return [Spec(f"PACE_BRK_{d}_p{p}_k{k}", "H1", e, dd, st, np.full(len(e), np.nan), la, ep)
            for (d, p, k), (e, dd, st, la, ep) in sorted(res.items())]


def batch19(H, D):
    return pace_brk(H)


def menu6(H, D):
    """menu4 + session-split copies (ASIA/LONDON/NYAM/LATE/OPEN) of every continuation and breakout
    H1 variant, with their mirrors."""
    base = menu4(H, D)
    fams = ("SHOCK_CONT", "MOM_", "CONT_UNION", "PDHL_BRK", "ASIA_BRK", "NY_ORB", "NR7")
    extra = []
    for s in base:
        if s.tf == "H1" and "~INV" not in s.name and s.name.startswith(fams):
            for x in by_session(H, s):
                if len(x.ent) >= 100:
                    extra.append(x); extra.append(mirror(x))
    return base + extra
