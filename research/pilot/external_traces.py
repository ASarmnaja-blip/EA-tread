"""External traces of weekly regime change (Treasury yields, CFTC positioning,
scheduled tier-1 news, cross-asset volatility/return).
See docs/EXTERNAL_TRACE_PREREG.md. Read-only; every value is the latest
observation dated on or before the Thursday preceding the Friday cut, except
CFTC which additionally requires a release strictly before the cut."""
from __future__ import annotations

import io
import math
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data" / "external"
WEEK = 7 * 86400
TIER1 = ("Fed Interest Rate Decision", "Nonfarm Payrolls", "CPI m/m", "Core PCE Price Index m/m")
NS = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
      "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
      "a": "http://www.w3.org/2005/Atom"}


# ------------------------------------------------------------------ loaders
def treasury(kind):
    """kind: 'nominal' (BC_2YEAR, BC_10YEAR) or 'real' (TC_10YEAR)."""
    rows = []
    fields = ("BC_2YEAR", "BC_10YEAR") if kind == "nominal" else ("TC_10YEAR",)
    for f in sorted(EXT.glob(f"treasury_{kind}_*.xml")):
        root = ET.parse(f).getroot()
        for e in root.iter("{http://www.w3.org/2005/Atom}entry"):
            p = e.find(".//m:properties", NS)
            if p is None:
                continue
            d = p.find("d:NEW_DATE", NS)
            if d is None or not d.text:
                continue
            rec = {"date": pd.Timestamp(d.text[:10])}
            for k in fields:
                v = p.find(f"d:{k}", NS)
                rec[k] = float(v.text) if v is not None and v.text else np.nan
            rows.append(rec)
    if not rows:
        return None
    df = pd.DataFrame(rows).dropna(subset=["date"]).drop_duplicates("date").sort_values("date")
    return df.set_index("date")


def cftc():
    """Managed-money net for GOLD from the disaggregated futures-only files.
    Returns a frame indexed by report (Tuesday) date with the net position and
    the release date (Friday 15:30 ET = 19:30/20:30 UTC; we use Friday 20:30 UTC,
    which is before the 22:15 cut, and require the report date + 3 days <= cut)."""
    rows = []
    for z in sorted(EXT.glob("cftc_fut_disagg_*.zip")):
        with zipfile.ZipFile(z) as zf:
            name = [n for n in zf.namelist() if n.lower().endswith(".txt")][0]
            df = pd.read_csv(io.BytesIO(zf.read(name)), low_memory=False)
        def pick(prefix):
            m = [c for c in df.columns if c.strip().startswith(prefix)]
            return m[0] if m else None
        code = pick("CFTC_Contract_Market_Code")
        date = pick("Report_Date_as_YYYY-MM-DD")
        lon = pick("M_Money_Positions_Long_All")
        sho = pick("M_Money_Positions_Short_All")
        if not all((code, date, lon, sho)):
            continue
        # column names carry dashes, so index by label rather than itertuples
        g = df.loc[df[code].astype(str).str.strip() == "088691", [date, lon, sho]]
        rows.extend({"report": pd.Timestamp(d), "net": float(a) - float(b)}
                    for d, a, b in zip(g[date], g[lon], g[sho]))
    if not rows:
        return None
    out = pd.DataFrame(rows).dropna().drop_duplicates("report").sort_values("report").set_index("report")
    out["release"] = out.index + pd.Timedelta(days=3, hours=20, minutes=30)   # Tue book -> Fri 20:30 UTC
    return out


def calendar_tier1():
    sys.path.insert(0, str(ROOT / "research" / "pilot"))
    import calendar_feed
    cal = calendar_feed.load_calendar(str(ROOT / "data" / "calendar.csv"))
    d = cal[(cal.currency == "USD") & cal.event.isin(TIER1)]
    return np.sort(d.epoch.unique().astype(np.int64)), int(cal.epoch.min()), int(cal.epoch.max())


def cross_asset():
    out = {}
    for sym in ("DXY", "US500", "XAGUSD"):
        f = ROOT / "data" / "fresh" / f"{sym}_M5.npz"
        if not f.exists():
            continue
        z = np.load(f)
        s = pd.Series(z["c"], index=pd.to_datetime(z["t"], unit="s")).resample("1h").last().dropna()
        out[sym] = s
    return out


# ------------------------------------------------------------------ builder
def asof(idx_ts, values, cut):
    """Latest value dated on or before the Thursday preceding the cut."""
    thu = cut - 86400
    j = np.searchsorted(idx_ts, thu, side="right") - 1
    return (j, values[j]) if j >= 0 else (None, np.nan)


def build(cuts):
    """Return {name: array over cuts} for the 14 external traces."""
    n = len(cuts)
    T = {k: np.full(n, np.nan) for k in (
        "y2_lvl", "y10_lvl", "y2_chg", "y10_chg", "slope_2s10s", "slope_chg",
        "y10r_lvl", "y10r_chg", "mm_net", "mm_pct", "mm_chg4", "news_tier1",
        "xasset_vol", "xasset_ret")}
    nom = treasury("nominal")
    real = treasury("real")
    mm = cftc()
    t1, cal_lo, cal_hi = calendar_tier1()
    xa = cross_asset()

    nom_ts = nom.index.astype("datetime64[s]").astype(np.int64).to_numpy() if nom is not None else None
    real_ts = real.index.astype("datetime64[s]").astype(np.int64).to_numpy() if real is not None else None
    mm_rel = mm.release.astype("datetime64[s]").astype(np.int64).to_numpy() if mm is not None else None
    xa_ts = {k: v.index.astype("datetime64[s]").astype(np.int64).to_numpy() for k, v in xa.items()}
    xa_v = {k: v.to_numpy(float) for k, v in xa.items()}

    for k, cut in enumerate(cuts.astype(np.int64)):
        cut = int(cut)
        # --- Treasury nominal
        if nom is not None:
            j, y2 = asof(nom_ts, nom["BC_2YEAR"].to_numpy(float), cut)
            if j is not None and nom_ts[j] > cut - 10 * 86400:
                y10 = nom["BC_10YEAR"].to_numpy(float)[j]
                T["y2_lvl"][k], T["y10_lvl"][k] = y2, y10
                T["slope_2s10s"][k] = y10 - y2
                j0 = np.searchsorted(nom_ts, nom_ts[j] - 7 * 86400, side="right") - 1
                if j0 >= 0 and nom_ts[j0] > nom_ts[j] - 13 * 86400:
                    y2b = nom["BC_2YEAR"].to_numpy(float)[j0]; y10b = nom["BC_10YEAR"].to_numpy(float)[j0]
                    T["y2_chg"][k] = y2 - y2b
                    T["y10_chg"][k] = y10 - y10b
                    T["slope_chg"][k] = (y10 - y2) - (y10b - y2b)
        # --- Treasury real
        if real is not None:
            j, v = asof(real_ts, real["TC_10YEAR"].to_numpy(float), cut)
            if j is not None and real_ts[j] > cut - 10 * 86400:
                T["y10r_lvl"][k] = v
                j0 = np.searchsorted(real_ts, real_ts[j] - 7 * 86400, side="right") - 1
                if j0 >= 0 and real_ts[j0] > real_ts[j] - 13 * 86400:
                    T["y10r_chg"][k] = v - real["TC_10YEAR"].to_numpy(float)[j0]
        # --- CFTC: only reports RELEASED strictly before the cut
        if mm is not None:
            j = np.searchsorted(mm_rel, cut, side="left") - 1
            if j >= 0 and mm_rel[j] > cut - 21 * 86400:
                net = mm.net.to_numpy(float)
                T["mm_net"][k] = net[j] / 1000.0
                lo = max(j - 51, 0)
                if j - lo >= 25:
                    T["mm_pct"][k] = float((net[lo:j + 1] < net[j]).mean() * 100)
                if j >= 4:
                    T["mm_chg4"][k] = (net[j] - net[j - 4]) / 1000.0
        # --- scheduled tier-1 releases in the coming week
        if cal_lo - WEEK <= cut <= cal_hi - WEEK:
            T["news_tier1"][k] = float(((t1 > cut) & (t1 <= cut + WEEK)).sum())
        # --- cross-asset weekly volatility ratio and return z (52-week baseline)
        rv, rz = [], []
        for sym, ts in xa_ts.items():
            v = xa_v[sym]
            lo_i = np.searchsorted(ts, cut - WEEK, side="right")
            hi_i = np.searchsorted(ts, cut, side="right")
            if hi_i - lo_i < 50:
                continue
            r = np.diff(np.log(v[lo_i:hi_i]))
            week_rv = float(np.sum(r * r))
            past = []
            for w in range(1, 53):
                a = np.searchsorted(ts, cut - (w + 1) * WEEK, side="right")
                b = np.searchsorted(ts, cut - w * WEEK, side="right")
                if b - a >= 50:
                    rr = np.diff(np.log(v[a:b]))
                    past.append(float(np.sum(rr * rr)))
            if len(past) >= 30:
                rv.append(math.sqrt(week_rv / np.median(past)))
                rz.append((math.log(v[hi_i - 1] / v[lo_i])) / math.sqrt(np.median(past)))
        if len(rv) >= 2:
            T["xasset_vol"][k] = float(np.median(rv))
            T["xasset_ret"][k] = float(np.median(rz))
    return T


def coverage(T, cuts):
    rows = []
    for k, v in T.items():
        ok = np.isfinite(v)
        rows.append(dict(trace=k, weeks=int(ok.sum()),
                         first=pd.to_datetime(cuts[np.flatnonzero(ok)[0]], unit="s").date() if ok.any() else None,
                         last=pd.to_datetime(cuts[np.flatnonzero(ok)[-1]], unit="s").date() if ok.any() else None))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import os
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "research" / "pilot"))
    from regime_atlas import load
    h, t, cuts, rv, rng, ret, nbar, big = load()
    T = build(cuts)
    print(coverage(T, cuts).to_string(index=False))
