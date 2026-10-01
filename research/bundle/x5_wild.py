"""X5 of docs/BUNDLE_2026-10-01_PREREG.md: wild ideas, each a contrast (flag vs rest, or top vs bottom quintile) of gold / silver returns in ATR,
weekly-cluster t on gold DEV 2009-15, gold CHECK 2016-26 and silver 2010-26, with a null from 50 mirrored gold paths (lab.mirror_base).
Timing: data conditions of UTC day d (Ap, Kp, sunspots, flux) are measured from 00:00 UTC of d+1 (next 1 / 5 / 20 D1 bars); calendar and
astronomical conditions (known in advance) on the D1 bar of their trade date; city weather on the same day's session (NY 13-21 UTC,
London 07-16 UTC). Descriptive tables: presidential cycle, Chinese zodiac year, BTC halving cycle. Usage: python research/bundle/x5_wild.py"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

L = C.L
W = C.ROOT / "data" / "macro" / "wild"
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
DAY = 86400
CNY = ["2003-02-01", "2004-01-22", "2005-02-09", "2006-01-29", "2007-02-18", "2008-02-07", "2009-01-26", "2010-02-14", "2011-02-03", "2012-01-23",
       "2013-02-10", "2014-01-31", "2015-02-19", "2016-02-08", "2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12", "2022-02-01",
       "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17"]
HALVINGS = ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]
ZODIAC = ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig"]


# ------------------------------------------------------------------ astronomy
def moon_phase(day):
    """Mean lunar phase in [0, 1) at noon UTC of each day number (0 = new moon, 0.5 = full); reference new moon 2000-01-06 18:14 UTC."""
    ref = (pd.Timestamp("2000-01-06 18:14").value // 10 ** 9) / DAY
    return (((day + 0.5) - ref) / 29.530588853) % 1.0


def _helio(el, rate, T):
    a, e, I, Lm, wbar, Om = [np.asarray(x0 + r * T) for x0, r in zip(el, rate)]
    I, Lm, wbar, Om = map(np.radians, (I, Lm, wbar, Om))
    w = wbar - Om; M = (Lm - wbar + np.pi) % (2 * np.pi) - np.pi
    E = M.copy()
    for _ in range(12):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    xp, yp = a * (np.cos(E) - e), a * np.sqrt(1 - e ** 2) * np.sin(E)
    x = (np.cos(w) * np.cos(Om) - np.sin(w) * np.sin(Om) * np.cos(I)) * xp + (-np.sin(w) * np.cos(Om) - np.cos(w) * np.sin(Om) * np.cos(I)) * yp
    y = (np.cos(w) * np.sin(Om) + np.sin(w) * np.cos(Om) * np.cos(I)) * xp + (-np.sin(w) * np.sin(Om) + np.cos(w) * np.cos(Om) * np.cos(I)) * yp
    return x, y


def mercury_retro(day):
    """True on days when Mercury's geocentric ecliptic longitude decreases (JPL approximate Keplerian elements, J2000)."""
    T = ((day + 0.5) * DAY / DAY - 10957.5) / 36525.0
    me = ([0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593],
          [0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081])
    ea = ([1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0],
          [0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0])
    xm, ym = _helio(*me, T); xe, ye = _helio(*ea, T)
    lon = np.unwrap(np.arctan2(ym - ye, xm - xe))
    return np.r_[np.diff(lon), np.nan] < 0


# ------------------------------------------------------------------ external daily series (UTC day numbers)
def kp_ap():
    rows = []
    for line in open(W / "kp_ap_sn_f107_since_1932.txt"):
        if line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 28:
            continue
        kp = [float(x) for x in p[7:15]]
        rows.append((int(pd.Timestamp(f"{p[0]}-{p[1]}-{p[2]}").value // 10 ** 9 // DAY), max(kp), float(p[23]), float(p[24]), float(p[26])))
    D = pd.DataFrame(rows, columns=["day", "kpmax", "Ap", "SN", "F107"]).set_index("day")
    D.loc[D.F107 <= 0, "F107"] = np.nan; D.loc[D.SN < 0, "SN"] = np.nan
    return D


def weather(city):
    j = json.loads((W / f"weather_{city}.json").read_text())["daily"]
    d = pd.DataFrame(j)
    d["day"] = ((pd.to_datetime(d.time) - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).astype(int)
    d = d.set_index("day")[["sunshine_duration", "cloud_cover_mean", "precipitation_sum"]].astype(float)
    m = pd.to_datetime(d.index * DAY, unit="s").month
    for c in ("sunshine_duration", "cloud_cover_mean"):
        d[c + "_ds"] = d[c] - d.groupby(m)[c].transform("mean")
    return d


def eclipse_days():
    out = []
    for line in open(W / "nasa_solar_eclipses.txt", encoding="latin-1"):
        mm = re.match(r"\s*\d+\s+\d+\s+(-?\d+) (\w{3})\s+(\d+)\s", line)
        if mm and 2000 <= int(mm.group(1)) <= 2027:
            out.append(int(pd.Timestamp(f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}").value // 10 ** 9 // DAY))
    return np.array(out)


def us_holidays(y0=2003, y1=2027):
    from pandas.tseries.holiday import (USFederalHolidayCalendar, GoodFriday, USMartinLutherKingJr, USPresidentsDay, USMemorialDay,
                                        USLaborDay, USThanksgivingDay, Holiday, nearest_workday)
    rules = [Holiday("NY", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
             Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
             Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
             Holiday("Xmas", month=12, day=25, observance=nearest_workday)]
    cal = USFederalHolidayCalendar(); cal.rules = rules
    return ((cal.holidays(f"{y0}-01-01", f"{y1}-12-31") - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy().astype(int)


def dst_mondays():
    us, eu = [], []
    for y in range(2003, 2027):
        def nth_sunday(month, n):
            d = pd.Timestamp(f"{y}-{month:02d}-01"); d += pd.Timedelta(days=(6 - d.weekday()) % 7)
            return d + pd.Timedelta(weeks=n - 1)
        def last_sunday(month):
            d = pd.Timestamp(f"{y}-{month:02d}-01") + pd.offsets.MonthEnd(0)
            return d - pd.Timedelta(days=(d.weekday() + 1) % 7)
        us += ([nth_sunday(3, 2), nth_sunday(11, 1)] if y >= 2007 else [nth_sunday(4, 1), last_sunday(10)])
        eu += [last_sunday(3), last_sunday(10)]
    f = lambda xs: np.array([int((x + pd.Timedelta(days=1)).value // 10 ** 9 // DAY) for x in xs])
    return f(us), f(eu)


# ------------------------------------------------------------------ market frames
def frames(H1, D1):
    """Per trade date: same-day D1 return, next-window returns from 00:00 UTC of the next day, and session returns, all in D1 ATR."""
    td = (D1.t + 2 * 3600) // DAY                                   # trade date of each D1 bar (22:00 anchor)
    A = np.r_[np.nan, D1.atr[:-1]]                                  # ATR known at the bar open
    out = pd.DataFrame(dict(day=td, same=(D1.c - D1.o) / A, A=A))
    h1_open_at = pd.Series(H1.o, index=H1.t)
    start_t = (td + 1) * DAY                                        # 00:00 UTC of the next day
    j = np.searchsorted(H1.t, start_t, side="left")
    ok = j < len(H1.t)
    sp = np.where(ok, H1.o[np.minimum(j, len(H1.t) - 1)], np.nan)
    k = np.searchsorted(D1.t + DAY, H1.t[np.minimum(j, len(H1.t) - 1)], side="right")   # D1 bar containing that H1 bar
    Ak = np.where(k - 1 >= 0, D1.atr[np.clip(k - 1, 0, len(D1.t) - 1)], np.nan)
    for hzn in (1, 5, 20):
        e = k + hzn - 1
        out[f"next{hzn}"] = np.where(ok & (e < len(D1.t)), (D1.c[np.clip(e, 0, len(D1.t) - 1)] - sp) / Ak, np.nan)
    for name, (a, b) in (("ny", (13, 21)), ("ldn", (7, 16))):
        ta = td * DAY + a * 3600; tb = td * DAY + (b - 1) * 3600
        ia = np.searchsorted(H1.t, ta); ib = np.searchsorted(H1.t, tb)
        good = (ia < len(H1.t)) & (ib < len(H1.t))
        ia = np.minimum(ia, len(H1.t) - 1); ib = np.minimum(ib, len(H1.t) - 1)
        good &= (H1.t[ia] == ta) & (H1.t[ib] == tb)
        out[name] = np.where(good, (H1.c[ib] - H1.o[ia]) / A, np.nan)
    _ = h1_open_at
    return out.set_index("day")


def effect(y, top, bot, wk):
    m = np.isfinite(y); t_, b_ = m & top, m & bot
    nt, nb = int(t_.sum()), int(b_.sum())
    if nt < 15 or nb < 15:
        return np.nan, np.nan, nt
    mt, mb = y[t_].mean(), y[b_].mean()
    W_ = int(wk.max()) + 1
    st = np.bincount(wk[t_], y[t_] - mt, W_) / nt; sb = np.bincount(wk[b_], y[b_] - mb, W_) / nb
    se = np.sqrt(((st - sb) ** 2).sum())
    return float(mt - mb), float((mt - mb) / se) if se > 0 else np.nan, nt


def conditions(days, ext):
    """Every contrast: name -> (outcome column, top mask, bottom mask). Continuous thresholds from gold DEV days."""
    kp, ny, ldn, ecl, hol, (dst_us, dst_eu) = ext
    dts = pd.to_datetime(days * DAY, unit="s")
    dev = (days >= C.ts(C.GOLD_DEV[0]) // DAY) & (days < C.ts(C.GOLD_DEV[1]) // DAY)
    out = {}
    K = kp.reindex(days)
    for h in ("next1", "next5", "next20"):
        out[f"Ap>=30 storm -> {h}"] = (h, (K.Ap >= 30).to_numpy(), (K.Ap < 30).to_numpy())
        out[f"Kp max>=5 -> {h}"] = (h, (K.kpmax >= 5).to_numpy(), (K.kpmax < 5).to_numpy())
    sn_m = kp.SN.rolling(30).mean().reindex(days).to_numpy(); sn_ch = (kp.SN.rolling(30).mean() - kp.SN.rolling(30).mean().shift(30)).reindex(days).to_numpy()
    f107 = kp.F107.rolling(7).mean().reindex(days).to_numpy()
    for nm, x in (("sunspots 30d level", sn_m), ("sunspots 30d change", sn_ch), ("solar flux F10.7", f107)):
        q = np.nanquantile(x[dev], [0.2, 0.8])
        for h in ("next5", "next20"):
            out[f"{nm} top vs bottom quintile -> {h}"] = (h, x >= q[1], x <= q[0])
    for city, col, wx in (("NY", "ny", ny), ("London", "ldn", ldn)):
        X = wx.reindex(days)
        for nm, c_, sg in (("cloud cover", "cloud_cover_mean_ds", 1), ("sunshine", "sunshine_duration_ds", 1)):
            x = X[c_].to_numpy(); q = np.nanquantile(x[dev], [0.2, 0.8])
            out[f"{city} {nm} top vs bottom quintile -> {city} session"] = (col, x >= q[1], x <= q[0])
        out[f"{city} rain > 5 mm -> {city} session"] = (col, (X.precipitation_sum > 5).to_numpy(), (X.precipitation_sum <= 5).to_numpy())
    ph = moon_phase(days)
    full = np.abs(ph - 0.5) * 29.53 <= 3; new = np.minimum(ph, 1 - ph) * 29.53 <= 3
    out["full moon +-3d vs new moon +-3d -> same day"] = ("same", full, new)
    out["full moon +-3d vs new moon +-3d -> next5"] = ("next5", full, new)
    near_ecl = np.isin(days, np.r_[ecl - 1, ecl, ecl + 1])
    out["solar eclipse +-1d -> same day"] = ("same", near_ecl, ~near_ecl)
    mr = mercury_retro(np.arange(days.min() - 5, days.max() + 6))
    mr = mr[days - (days.min() - 5)]
    out["Mercury retrograde -> same day"] = ("same", mr, ~mr)
    out["Mercury retrograde -> next20"] = ("next20", mr, ~mr)
    mon = dts.weekday == 0; fri = dts.weekday == 4
    out["Monday after US DST change vs other Mondays"] = ("same", np.isin(days, dst_us), mon & ~np.isin(days, dst_us))
    out["Monday after EU DST change vs other Mondays"] = ("same", np.isin(days, dst_eu), mon & ~np.isin(days, dst_eu))
    f13 = fri & (dts.day == 13)
    out["Friday the 13th vs other Fridays"] = ("same", f13, fri & ~f13)
    cny = np.array([pd.Timestamp(x).value // 10 ** 9 // DAY for x in CNY])
    k = np.searchsorted(cny, days, side="left")
    nxt = np.where(k < len(cny), cny[np.minimum(k, len(cny) - 1)], 10 ** 9)
    pre_cny = (nxt - days > 0) & (nxt - days <= 28)
    out["20 trading days before Chinese New Year"] = ("same", pre_cny, ~pre_cny)
    s = pd.Series(days, index=days)
    ym = dts.year * 12 + dts.month
    first = pd.Series(days).groupby(ym).rank(method="first").to_numpy(); last = pd.Series(days).groupby(ym).rank(method="first", ascending=False).to_numpy()
    tom = (first <= 3) | (last <= 1)
    out["turn of the month (last + first 3 days)"] = ("same", tom, ~tom)
    pre_h = np.isin(days, np.r_[hol - 1, hol - 3])
    pre_h &= ~np.isin(days, hol)
    out["day before a US market holiday"] = ("same", pre_h, ~pre_h)
    santa = ((dts.month == 12) & (last <= 5)) | ((dts.month == 1) & (first <= 2))
    out["Santa rally (last 5 Dec + first 2 Jan)"] = ("same", santa, ~santa)
    hal = np.isin(dts.month, [11, 12, 1, 2, 3, 4])
    out["Halloween: Nov-Apr vs May-Oct"] = ("same", hal, ~hal)
    for wd, nm in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]):
        out[f"{nm} vs other days"] = ("same", dts.weekday == wd, (dts.weekday != wd) & (dts.weekday < 5))
    wom = (dts.day - 1) // 7 + 1
    for w_ in range(1, 6):
        out[f"week {w_} of the month vs rest"] = ("same", wom == w_, wom != w_)
    _ = s
    return {k: (v[0], np.asarray(v[1], bool), np.asarray(v[2], bool)) for k, v in out.items()}


def run_all(H1, D1, ext, periods):
    Fr = frames(H1, D1)
    days = Fr.index.to_numpy()
    wk = np.searchsorted(L.cut_grid(C.ts("2026-10-01")), days * DAY, side="right") - 1
    wk = np.maximum(wk, 0)
    conds = conditions(days, ext)
    rows = []
    for nm, (col, top, bot) in conds.items():
        y = Fr[col].to_numpy(float)
        for p, (a, b) in periods.items():
            m = (days >= C.ts(a) // DAY) & (days < C.ts(b) // DAY)
            e, t, n = effect(y, top & m, bot & m, wk)
            rows.append(dict(test=nm, outcome=col, period=p, eff=e, t=t, n_flag=n))
    return pd.DataFrame(rows)


def digits(B, step, periods, wk_cuts):
    """Close within 0.25 ATR of a round level (multiples of step): next-bar return in ATR and break probability, real levels vs levels
    shifted by step / 2 (placebo levels)."""
    c, h, l, o, A = B.c, B.h, B.l, B.o, B.atr
    rows = []
    wk = np.maximum(np.searchsorted(wk_cuts, B.t, side="right") - 1, 0)
    nr = np.r_[(c[1:] - o[1:]) / A[:-1], np.nan]
    for lab, off in (("real", 0.0), ("shifted", step / 2)):
        up = np.ceil((c - off) / step) * step + off; dn = np.floor((c - off) / step) * step + off
        below = (up - c > 0) & (up - c <= 0.25 * A); above = (c - dn > 0) & (c - dn <= 0.25 * A)
        brk_up = np.r_[h[1:] >= up[:-1] + 0.1 * A[:-1], False]; brk_dn = np.r_[l[1:] <= dn[:-1] - 0.1 * A[:-1], False]
        for p, (a, b) in periods.items():
            m = (B.t >= C.ts(a)) & (B.t < C.ts(b)) & np.isfinite(nr)
            for side, f, brk in (("just below a level", below, brk_up), ("just above a level", above, brk_dn)):
                x = m & f
                rows.append(dict(levels=lab, side=side, period=p, n=int(x.sum()), next_ret=float(np.nanmean(nr[x])), break_prob=float(brk[x].mean()),
                                 wk=wk[x], y=nr[x]))
    out = []
    D = pd.DataFrame(rows)
    for (side, p), g in D.groupby(["side", "period"]):
        r = g[g.levels == "real"].iloc[0]; s = g[g.levels == "shifted"].iloc[0]
        y = np.r_[r.y, s.y]; top = np.r_[np.ones(len(r.y), bool), np.zeros(len(s.y), bool)]; w = np.r_[r.wk, s.wk]
        e, t, _ = effect(y, top, ~top, w)
        out.append(dict(test=f"price digits {step:g}: {side}", period=p, n_real=r.n, ret_real=r.next_ret, ret_shifted=s.next_ret,
                        break_real=r.break_prob, break_shifted=s.break_prob, eff=e, t=t))
    return pd.DataFrame(out)


def main():
    kp = kp_ap(); ny = weather("newyork"); ldn = weather("london"); ecl = eclipse_days(); hol = us_holidays(); dst = dst_mondays()
    ext = (kp, ny, ldn, ecl, hol, dst)
    # astronomy self-checks (printed): Mercury retrograde spans in 2024 and moon phases on known dates
    d24 = np.arange(C.ts("2024-01-01") // DAY, C.ts("2025-01-01") // DAY)
    mr = mercury_retro(d24); edges = np.flatnonzero(np.diff(mr.astype(int)) != 0) + 1
    log("Mercury retrograde 2024 switches:", [str(pd.Timestamp(int(d24[k]) * DAY, unit="s").date()) for k in edges])
    log("moon phase 2024-04-08 (new) %.3f, 2024-04-23 (full) %.3f" % (moon_phase(np.array([C.ts("2024-04-08") // DAY]))[0],
                                                                    moon_phase(np.array([C.ts("2024-04-23") // DAY]))[0]))
    gold_p = {"DEV": C.GOLD_DEV, "CHECK": C.GOLD_CHECK}
    real = run_all(C.bars("XAUUSD", "H1"), C.bars("XAUUSD", "D1"), ext, gold_p)
    silv = run_all(C.bars("XAGUSD", "H1"), C.bars("XAGUSD", "D1"), ext, {"SILVER": ("2010-01-01", "2026-10-01")})
    cuts = L.cut_grid(C.ts("2026-10-01"))
    dig = pd.concat([digits(C.bars("XAUUSD", tf), st, gold_p, cuts).assign(tf=tf, market="gold") for tf in ("H1", "D1") for st in (50, 100)] +
                    [digits(C.bars("XAGUSD", tf), 0.5, {"SILVER": ("2010-01-01", "2026-10-01")}, cuts).assign(tf=tf, market="silver") for tf in ("H1", "D1")])
    log(f"real done: {len(real)} gold rows, {len(silv)} silver rows")
    base = L.base_gold(); cg = L.cut_grid(base["t"][-1])
    P = []
    PD = []
    for k in range(50):
        mb = L.mirror_base(base, 5000 + k)
        H1p, D1p = L.resample(mb, "H1", cg), L.resample(mb, "D1", cg)
        P.append(run_all(H1p, D1p, ext, gold_p).assign(path=k))
        PD.append(pd.concat([digits(L.resample(mb, tf, cg), st, gold_p, cuts).assign(tf=tf) for tf in ("H1", "D1") for st in (50, 100)]).assign(path=k))
        if k % 10 == 9:
            log(f"placebo {k + 1}/50")
        del mb
    P = pd.concat(P); PD = pd.concat(PD)
    q95 = P.assign(at=P.t.abs()).groupby(["test", "period"]).at.quantile(0.95).unstack()
    piv = real.pivot_table(index=["test", "outcome"], columns="period", values=["eff", "t"]).reset_index()
    piv.columns = ["test", "outcome", "eff_CHECK", "eff_DEV", "t_CHECK", "t_DEV"]
    piv = piv.merge(silv[["test", "eff", "t", "n_flag"]].rename(columns={"eff": "eff_SILVER", "t": "t_SILVER", "n_flag": "n_flag_silver"}), on="test")
    piv = piv.merge(q95.rename(columns={"DEV": "null95_DEV", "CHECK": "null95_CHECK"}), left_on="test", right_index=True, how="left")
    sg = np.sign(piv.t_DEV)
    piv["PASS"] = ((piv.t_DEV.abs() >= 2) & (piv.t_CHECK.abs() >= 2) & (piv.t_SILVER.abs() >= 2) & (np.sign(piv.t_CHECK) == sg) & (np.sign(piv.t_SILVER) == sg)
                   & (piv.t_DEV.abs() > piv.null95_DEV) & (piv.t_CHECK.abs() > piv.null95_CHECK))
    piv.to_csv(C.OUT / "x5_wild.csv", index=False)
    dq = PD.assign(at=PD.t.abs()).groupby(["test", "tf", "period"]).at.quantile(0.95).rename("null95").reset_index()
    dig = dig.merge(dq, on=["test", "tf", "period"], how="left")
    dig.to_csv(C.OUT / "x5_digits.csv", index=False)
    # descriptive tables
    D1 = C.bars("XAUUSD", "D1"); S1 = C.bars("XAGUSD", "D1")
    desc = []
    for nm, B in (("gold", D1), ("silver", S1)):
        yr = pd.Series(B.c, index=pd.to_datetime(B.t, unit="s")).resample("YE").last().pct_change().dropna()
        for y, r in yr.items():
            pres = (y.year - 2009) % 4 + 1
            desc.append(dict(market=nm, year=y.year, ret=r, presidential_year=pres))
    Dd = pd.DataFrame(desc)
    zrows = []
    cny = [pd.Timestamp(x) for x in CNY]
    for nm, B in (("gold", D1), ("silver", S1)):
        s = pd.Series(B.c, index=pd.to_datetime(B.t, unit="s"))
        for a, b in zip(cny[:-1], cny[1:]):
            x = s[(s.index >= a) & (s.index < b)]
            if len(x) > 100:
                zrows.append(dict(market=nm, start=a.date(), animal=ZODIAC[(a.year - 2008) % 12], ret=x.iloc[-1] / x.iloc[0] - 1))
        hv = [pd.Timestamp(x) for x in HALVINGS]
        for i, a in enumerate(hv):
            for k_, (lo_, hi_) in enumerate(((0, 365), (365, 730), (730, 1095), (1095, 1460))):
                x = s[(s.index >= a + pd.Timedelta(days=lo_)) & (s.index < min(a + pd.Timedelta(days=hi_), hv[i + 1] if i + 1 < len(hv) else s.index[-1]))]
                if len(x) > 50:
                    zrows.append(dict(market=nm, halving=str(a.date()), year_after=k_ + 1, ret=x.iloc[-1] / x.iloc[0] - 1))
    pd.concat([Dd, pd.DataFrame(zrows)]).to_csv(C.OUT / "x5_descriptive.csv", index=False)
    log(f"X5 done: {int(piv.PASS.sum())} pass of {len(piv)}")


if __name__ == "__main__":
    main()
