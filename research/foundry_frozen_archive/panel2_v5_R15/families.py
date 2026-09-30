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
            if uh and dl:                      # order unknown: nearer side to the open, stop-first later
                uh = abs(hi_ - H.o[i]) <= abs(H.o[i] - lo_); dl = not uh
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
        # R12-4: clock-based exit = last bar opening within 3 h of the entry (skips a missing break hour)
        last = np.searchsorted(H.t, H.t[ent] + 3 * 3600, side="right") - 1
        for d, nm in ((1.0, "L"), (-1.0, "S")):
            out.append(Spec(f"HOD_{h:02d}{nm}", "H1", ent, np.full(len(ent), d), 2 * a, np.full(len(ent), np.nan), last))
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
            if not len(j):
                continue
            j = int(j[0])
            if hu[j] and hd[j]:                # order unknown: nearer side to the open, stop-first later
                d = 1.0 if abs(up - H.o[i0 + j]) <= abs(H.o[i0 + j] - dn) else -1.0
            else:
                d = 1.0 if hu[j] else -1.0
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
                    if not len(j):
                        continue
                    j = int(j[0])
                    if hu[j] and hd[j]:
                        d = 1.0 if abs(up - H.o[ic + j]) <= abs(H.o[ic + j] - dn) else -1.0
                    else:
                        d = 1.0 if hu[j] else -1.0
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


# ------------------------------------------------------------------ batch 22: continuation with trailing stops
def with_trail(sp, init_mult, trail_mult, max_bars=120):
    x = Spec(f"{sp.name}|TR{trail_mult}", sp.tf, sp.ent, sp.dirs, init_mult * np.ones(len(sp.ent)), np.full(len(sp.ent), np.nan),
             sp.ent + max_bars - 1)
    x.trail = (init_mult, trail_mult, max_bars)
    return x


def batch22(H, D):
    base = [cont_union(H, 6)]
    base += [x for x in shock(H, follow=True) if x.name in ("SHOCK_CONT_k2_h6", "SHOCK_CONT_k3_h6")]
    base += [x for x in mom_h1(H) if x.name in ("MOM_L6_z1.5", "MOM_L12_z1.5")]
    base += pdhl_break(H, D)[:1]
    base += _range_break(H, "ASIA_BRK", list(range(0, 7)), list(range(7, 16)), 20, (0,))
    out = []
    for b_ in base:
        for tm in (2.0, 3.0):
            x = with_trail(b_, 2.0, tm)
            x.stop = 2.0 * H.atr[x.ent]                    # stop distance in price for R units
            out.append(x)
    return out


# ------------------------------------------------------------------ batch 23: H1 continuation x D1 trend alignment
def d1_trend_at_h1(H, D, n=50):
    """+1 / -1 if the previous completed D1 close is above / below its SMA(n), per H1 bar."""
    sma = pd.Series(D.c).rolling(n).mean().to_numpy()
    sgn = np.sign(D.c - sma)                                   # known at the end of day d
    tday = (H.t - 22 * 3600) // 86400
    dday = (D.t - 22 * 3600) // 86400
    j = np.searchsorted(dday, tday, side="left") - 1           # last COMPLETED day before the H1 bar's day
    out = np.where(j >= 0, sgn[np.clip(j, 0, len(sgn) - 1)], 0.0)
    return np.nan_to_num(out)


def batch23(H, D):
    tr = d1_trend_at_h1(H, D)
    out = []
    for b_ in [cont_union(H, 6)] + [x for x in mom_h1(H) if x.name == "MOM_L6_z1.5"]:
        al = tr[b_.ent] == b_.dirs
        for nm, m in (("WITH", al), ("AGAINST", (tr[b_.ent] != 0) & ~al)):
            out.append(Spec(f"{b_.name}@D1{nm}", "H1", b_.ent[m], b_.dirs[m], b_.stop[m], b_.tgt[m], b_.last[m]))
    return out


# ------------------------------------------------------------------ batch 25: volume, spread and GVZ information
def _hour_norm(x, hour, n=20):
    """x divided by its trailing median at the same hour of day over the previous n occurrences."""
    s = pd.Series(x)
    med = s.groupby(hour).transform(lambda z: z.shift(1).rolling(n, min_periods=10).median())
    return (s / med).to_numpy()


def volume_split(H):
    vr = _hour_norm(H.v, H.hour)                      # bar volume vs its usual level at that hour
    out = []
    bases = [cont_union(H, 6)] + [x for x in shock(H, follow=True) if x.name == "SHOCK_CONT_k2_h6"] \
        + [x for x in mom_h1(H) if x.name == "MOM_L6_z1.5"]
    for b in bases:
        r = vr[b.ent - 1]                              # the signal bar's volume ratio (known at its close)
        for nm, m in (("VOLHI", r >= 1.5), ("VOLLO", r < 1.0)):
            out.append(Spec(f"{b.name}@{nm}", "H1", b.ent[m], b.dirs[m], b.stop[m], b.tgt[m], b.last[m]))
    return out


def spread_shock(H):
    """Bar i-1 opened with a spread > 3x its usual level at that hour (a liquidity gap); at bar i
    follow or fade bar i-1's move, hold 3 h, stop 2 ATR."""
    sr = _hour_norm(H.spread_bp, H.hour)
    r1 = np.r_[np.nan, np.diff(H.c)]
    sig = (sr > 3) & np.isfinite(r1) & (np.abs(r1) > 0.5 * H.atr)
    ent = np.flatnonzero(sig[:-1]) + 1
    keep = nonoverlap(ent, ent + 2); ent = ent[keep]
    a = H.atr[ent]; ok = np.isfinite(a); ent, a = ent[ok], a[ok]
    d = np.sign(r1[ent - 1])
    return [Spec("SPREAD_SHOCK_FOLLOW", "H1", ent, d, 2 * a, np.full(len(ent), np.nan), ent + 2),
            Spec("SPREAD_SHOCK_FADE", "H1", ent, -d, 2 * a, np.full(len(ent), np.nan), ent + 2)]


def gvz_jump(D):
    """GVZ close of day d-1 (US close, before gold's next 22:00 UTC day starts... conservative: use
    the GVZ row dated two calendar days before the D1 bar's label) up > +10 % day on day:
    follow or fade gold's move of that day, hold 1 / 3 days, stop 2 ATR."""
    g = pd.read_csv(E_ROOT / "data" / "external" / "GVZ_History.csv")
    g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y"); g = g.set_index("d").GVZ.astype(float)
    chg = g.pct_change()
    lab = pd.to_datetime(D.t + 2 * 3600, unit="s").normalize()           # trading-day label
    known = chg.reindex(lab - pd.Timedelta(days=2), method="ffill").to_numpy()
    r_prev = np.r_[np.nan, np.nan, D.c[1:-1] - D.c[:-2]]                 # gold move of day d-1 (FIX: was day d)
    sig = np.isfinite(known) & (known > 0.10) & np.isfinite(r_prev)
    ent = np.flatnonzero(sig)
    a = D.atr[ent]; ok = np.isfinite(a); ent, a = ent[ok], a[ok]
    d = np.sign(r_prev[ent])
    out = []
    for hold in (1, 3):
        out.append(Spec(f"GVZ_JUMP_FOLLOW_h{hold}", "D1", ent, d, 2 * a, np.full(len(ent), np.nan), ent + hold - 1))
        out.append(Spec(f"GVZ_JUMP_FADE_h{hold}", "D1", ent, -d, 2 * a, np.full(len(ent), np.nan), ent + hold - 1))
    return out


from pathlib import Path as _P
E_ROOT = _P(__file__).resolve().parents[2]


def batch25b(H, D):
    return gvz_jump(D)


def batch25(H, D):
    return volume_split(H) + spread_shock(H) + gvz_jump(D)


def batch1nr7fix(H, D):
    """NR7 re-run after the both-touch fix (correction; counted as new candidates)."""
    return nr7(H, D)


# ------------------------------------------------------------------ batch 26: new calendar / session families
def compression_oco(H, D, name, cond):
    """Day d-1 satisfies cond (compression) -> OCO stop entries at its high/low during day d."""
    tday, _, _ = _days(H)
    dday = (D.t - 22 * 3600) // 86400
    first = pd.Series(np.arange(len(H.t))).groupby(tday).min()
    lastb = pd.Series(np.arange(len(H.t))).groupby(tday).max()
    ents, dirs, stops, lasts, eps = [], [], [], [], []
    for di in np.flatnonzero(cond[:-1]):
        nxt = int(dday[di + 1])
        if nxt not in first.index:
            continue
        a, b = int(first[nxt]), int(lastb[nxt])
        hi_, lo_ = D.h[di], D.l[di]
        for i in range(a, b + 1):
            uh, dl = H.h[i] >= hi_, H.l[i] <= lo_
            if uh and dl:
                uh = abs(hi_ - H.o[i]) <= abs(H.o[i] - lo_); dl = not uh
            if uh or dl:
                ep = max(hi_, H.o[i]) if uh else min(lo_, H.o[i])
                ents.append(i); dirs.append(1.0 if uh else -1.0); eps.append(ep)
                stops.append(abs(ep - (lo_ if uh else hi_))); lasts.append(b)
                break
    e, d_, st, la, ep = map(np.asarray, (ents, dirs, stops, lasts, eps))
    ok = st > 0
    return [Spec(f"{name}_t{k}", "H1", e[ok], d_[ok], st[ok], st[ok] * k, la[ok], ep[ok]) for k in (1, 2)]


def session_fade(H, name, from_hour, at_hour, exit_hour, k, weekday=None):
    """At the open of `at_hour` UTC, fade the move since the open of `from_hour` the same calendar
    day if it exceeds k * ATR(H1) * sqrt(hours); exit at the close of `exit_hour`; stop 2 ATR."""
    _, cal, hr = _days(H)
    df = pd.DataFrame(dict(cal=cal, hr=hr, o=H.o, i=np.arange(len(H.o))))
    f = df[df.hr == from_hour].set_index("cal")
    at = df[df.hr == at_hour].set_index("cal")
    ex = df[df.hr == exit_hour].set_index("cal").i
    j = f.index.intersection(at.index).intersection(ex.index)
    ent = at.loc[j, "i"].to_numpy(); last = ex.loc[j].to_numpy()
    mv = H.o[ent] - f.loc[j, "o"].to_numpy()
    a = H.atr[ent]; hours = at_hour - from_hour
    m = np.isfinite(a) & (np.abs(mv) > k * a * np.sqrt(hours)) & (last >= ent)
    if weekday is not None:
        m &= H.dow[ent] == weekday
    return Spec(name, "H1", ent[m], -np.sign(mv[m]), 2 * a[m], np.full(m.sum(), np.nan), last[m])


def nfp_cont(H):
    """First Friday of the month (NFP proxy): follow the move of the 12:00-14:00 UTC bars (covers
    13:30 winter / 12:30 summer releases) at the 14:00 open, hold 4 h, stop 2 ATR."""
    idx = pd.to_datetime(H.t, unit="s")
    first_fri = (idx.dayofweek == 4) & (idx.day <= 7)
    ent = np.flatnonzero(first_fri & (idx.hour == 14))
    ok = (ent >= 2) & (H.hour[ent - 2] == 12)
    ent = ent[ok]
    mv = H.o[ent] - H.o[ent - 2]
    a = H.atr[ent]; m = np.isfinite(a) & (np.abs(mv) > 0.5 * a)
    return Spec("NFP_CONT", "H1", ent[m], np.sign(mv[m]), 2 * a[m], np.full(m.sum(), np.nan), ent[m] + 3)


def monday_gap_cont(H):
    gapt = np.r_[0, np.diff(H.t)] > 24 * 3600
    g = np.r_[np.nan, H.o[1:] - H.c[:-1]]
    ent = np.flatnonzero(gapt & (np.abs(g) > H.atr))
    a = H.atr[ent]; ok = np.isfinite(a)
    return Spec("MONDAY_GAP_CONT", "H1", ent[ok], np.sign(g[ent][ok]), 2 * a[ok], np.full(ok.sum(), np.nan), ent[ok] + 11)


def batch26(H, D):
    rng_ = D.h - D.l
    inside = np.r_[False, (D.h[1:] <= D.h[:-1]) & (D.l[1:] >= D.l[:-1])]
    nr4 = pd.Series(rng_).rolling(4).apply(lambda x: float(x[-1] == x.min()), raw=True).to_numpy() == 1
    s = compression_oco(H, D, "INSIDE_DAY", inside) + compression_oco(H, D, "NR4", nr4)
    s += [session_fade(H, "LONDON_CLOSE_FADE", 7, 16, 20, 1.0),
          session_fade(H, "FRIDAY_FADE", 7, 14, 20, 1.0, weekday=4),
          nfp_cont(H), monday_gap_cont(H)]
    return s


def trackB1(H, D):
    """Track B first batch: every setup family built so far (menu4 + batch26 + corrected GVZ jump),
    re-discovered on 2015-20."""
    seen, out = set(), []
    for s in menu4(H, D) + batch26(H, D) + gvz_jump(D):
        if s.name not in seen:
            seen.add(s.name); out.append(s)
    return out


def trackB2(H, D):
    """Time-defined variants re-scored with a time-free control (design correction)."""
    base = hod(H) + dow(D) + tom(D)
    return base + [mirror(s) for s in tom(D)]


# ------------------------------------------------------------------ Track B batch 3: DST-aware overnight / intraday split
def _local_hours(H, tz):
    return pd.to_datetime(H.t, unit="s", utc=True).tz_convert(tz).hour.to_numpy()


def overnight_split(H):
    """OVERNIGHT_LONG: long at the H1 bar opening 16:00 New York (last hour before the daily break),
    exit at the close of the bar before 08:00 London (London open), stop 3 ATR.
    INTRADAY_SHORT: short at 08:00 London, exit at the close of the 15:00 New York bar, stop 3 ATR.
    Both DST-aware; one trade per day each."""
    ny = _local_hours(H, "America/New_York"); ld = _local_hours(H, "Europe/London")
    out = []
    ent = np.flatnonzero(ny == 16)
    last = []
    for e in ent:
        j = e + 1
        while j < len(H.t) and ld[j] != 8 and H.t[j] - H.t[e] < 20 * 3600:
            j += 1
        last.append(j - 1)
    last = np.asarray(last)
    ok = (last > ent) & np.isfinite(H.atr[ent])
    out.append(Spec("OVERNIGHT_LONG", "H1", ent[ok], np.ones(ok.sum()), 3 * H.atr[ent][ok], np.full(ok.sum(), np.nan), last[ok]))
    ent2 = np.flatnonzero(ld == 8)
    last2 = []
    for e in ent2:
        j = e + 1
        while j < len(H.t) and ny[j] != 16 and H.t[j] - H.t[e] < 14 * 3600:
            j += 1
        last2.append(j - 1)
    last2 = np.asarray(last2)
    ok2 = (last2 > ent2) & np.isfinite(H.atr[ent2])
    out.append(Spec("INTRADAY_SHORT", "H1", ent2[ok2], -np.ones(ok2.sum()), 3 * H.atr[ent2][ok2], np.full(ok2.sum(), np.nan), last2[ok2]))
    out += [mirror(s) for s in out]
    return out


def trackB3(H, D):
    return overnight_split(H)


# ------------------------------------------------------------------ Panel-2 candidate (Amendment 9)
def shock_fade_clock(H, k=2.5, hold_h=72, stop_atr=3.0):
    """Fade an H1 bar whose close-to-close move exceeds k ATR: enter at the next open against it,
    exit at the last bar opening within hold_h-1 clock hours, stop stop_atr ATR, one at a time."""
    r1 = np.r_[np.nan, np.diff(H.c)]
    sig = np.abs(r1) > k * H.atr
    ent = np.flatnonzero(sig[:-1]) + 1
    last = np.searchsorted(H.t, H.t[ent] + (hold_h - 1) * 3600, side="right") - 1
    keep = nonoverlap(ent, last); ent, last = ent[keep], last[keep]
    d = -np.sign(r1[ent - 1]); a = H.atr[ent]; ok = np.isfinite(a) & (d != 0)
    return Spec(f"SHOCK_FADE_k{k}_h{hold_h}_s{stop_atr}", "H1", ent[ok], d[ok], stop_atr * a[ok],
                np.full(ok.sum(), np.nan), last[ok])


def panel2(H, D):
    return [shock_fade_clock(H)]
