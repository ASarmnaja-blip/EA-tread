"""Build every timeframe from Dukascopy M1 (2003-), audit it against the
Exness broker feed, and extend the WPWB volatility log back to 2003.

Outputs (data/history/):
  dukascopy/XAUUSD_<TF>.npz for M5 M15 M30 H1 H4 D1 W1 MN1 (bid OHLC and
      ask OHLC - both sides are needed for long and short stop touches,
      Codex Round 6 - plus volume); W1 bars start Sunday 00:00 UTC, MN1 calendar months
  inventory_all.csv            coverage of every source x timeframe
  crosscheck_exness.txt        Dukascopy vs Exness on the overlap
  yearly_2003.xlsx             per-year behaviour + volatile weeks since 2003
Descriptive only; nothing here is a test of an edge.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
H = ROOT / "data" / "history"
DK = H / "dukascopy"
sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
import vol as V  # noqa: E402

TFS = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D"}
TH = 7 * 3600


CACHE = DK / "cache"


def _starts(kind, key):
    if kind == "min":
        return int(datetime(int(key[:4]), int(key[4:6]), int(key[6:8]), tzinfo=timezone.utc).timestamp())
    if kind == "hour":
        return int(datetime(int(key[:4]), int(key[4:6]), 1, tzinfo=timezone.utc).timestamp())
    return int(datetime(int(key), 1, 1, tzinfo=timezone.utc).timestamp())


def load_kind(kind):
    """Assemble cached Dukascopy files of one kind into a bid/ask DataFrame.
    Rows with zero bid volume (closed-market fills) are dropped."""
    frames = []
    for fb in sorted((CACHE / kind / "BID").glob("*.npy")):
        fa = CACHE / kind / "ASK" / fb.name
        b = np.load(fb)
        if not len(b) or not fa.exists():
            continue
        a = np.load(fa)
        t0 = _starts(kind, fb.stem)
        bt = t0 + b["s"].astype(np.int64)
        am = dict(zip((t0 + a["s"].astype(np.int64)).tolist(), range(len(a))))
        idx = np.array([am.get(int(x), -1) for x in bt])
        keep = (b["v"] > 0) & (idx >= 0)
        if not keep.any():
            continue
        b, a2 = b[keep], a[idx[keep]]
        frames.append(pd.DataFrame({
            "o": b["o"] / 1000.0, "h": b["h"] / 1000.0, "l": b["l"] / 1000.0, "c": b["c"] / 1000.0,
            "ao": a2["o"] / 1000.0, "ah": a2["h"] / 1000.0, "al": a2["l"] / 1000.0,
            "ac": a2["c"] / 1000.0, "v": b["v"].astype(float)}, index=pd.to_datetime(bt[keep], unit="s")))
    if not frames:
        return None
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated(keep="first")]


def resample(df, rule):
    g = df.resample(rule, label="left", closed="left")
    out = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                        "ao": g.ao.first(), "ah": g.ah.max(), "al": g.al.min(),
                        "ac": g.ac.last(), "v": g.v.sum()}).dropna(subset=["o"])
    return out


def save(df, name):
    t = (df.index.astype("datetime64[s]").astype(np.int64)).to_numpy()
    np.savez_compressed(DK / f"XAUUSD_{name}.npz", t=t, **{k: df[k].to_numpy() for k in df.columns})


def inventory_row(src, tf, t, sec):
    t = np.asarray(t, np.int64)
    per_day = pd.Series(1, index=t // 86400).groupby(level=0).size()
    return dict(source=src, tf=tf, bars=len(t), first=pd.to_datetime(t[0], unit="s"),
                last=pd.to_datetime(t[-1], unit="s"), median_bars_per_day=float(per_day.median()),
                largest_gap_days=round(float(np.diff(t).max() / 86400), 1) if len(t) > 1 else np.nan)


def crosscheck(h1d):
    lines = []
    f = H / "XAUUSD_H1.npz"
    if not f.exists():
        return ["Exness H1 file missing"]
    z = np.load(f)
    ex = pd.DataFrame({"c": z["c"], "sp": z["sp"]}, index=pd.to_datetime(z["t"], unit="s"))
    ex = ex[ex.index >= "2021-07-01"]
    dk = h1d[h1d.index >= "2021-07-01"]
    rx = np.log(ex.c).diff(); rd = np.log(dk.c).diff()
    best = []
    for lag in range(-4, 5):
        j = pd.concat([rx, rd.shift(lag)], axis=1, join="inner").dropna()
        best.append((lag, j.corr().iloc[0, 1], len(j)))
    lines.append("H1 return correlation Exness vs Dukascopy by Dukascopy shift (hours):")
    lines += [f"  shift {lag:+d}h: corr {c:.4f} (n={n})" for lag, c, n in best]
    j = pd.concat([ex.c.rename("ex"), dk.c.rename("dk"), (dk.ac - dk.c).rename("dk_sp"), ex.sp.rename("ex_sp")],
                  axis=1, join="inner").dropna()
    diff = j.ex - j.dk
    lines.append(f"close difference Exness - Dukascopy (bid): median {diff.median():+.3f}, "
                 f"p5 {diff.quantile(.05):+.3f}, p95 {diff.quantile(.95):+.3f} $ (n={len(j)})")
    lines.append(f"median spread at H1 close: Exness {j.ex_sp.median():.3f} $, Dukascopy {j.dk_sp.median():.3f} $")
    return lines


def yearly(h1):
    rows = []
    d1 = resample(h1, "1D")
    for y, g in h1.groupby(h1.index.year):
        r = np.log(g.c).diff().dropna()
        dd = d1[d1.index.year == y]
        rows.append({"ปี": y, "ราคาต้นปี ($)": round(g.o.iloc[0], 2), "ราคาปลายปี ($)": round(g.c.iloc[-1], 2),
                     "ทองทั้งปี (%)": round((g.c.iloc[-1] / g.o.iloc[0] - 1) * 100, 1),
                     "ความผันผวนต่อปี (%)": round(r.std() * np.sqrt(len(r)) * 100, 1),
                     "กรอบรายวันเฉลี่ย (% ราคา)": round(((dd.h - dd.l) / dd.c).mean() * 100, 2),
                     "spread กลาง ($)": round(float((g.ac - g.c).median()), 3)})
    return pd.DataFrame(rows)


def weekly_levels(h1):
    # WPWB weeks: cut Friday 22:15 UTC; H1 bars close-to-close
    t = h1.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    first_cut = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
    cuts = np.arange(first_cut, t[-1] - 7 * 86400, 7 * 86400)
    rv, rng, ret, n = V.weekly_rv(t, h1.c.to_numpy(), h1.h.to_numpy(), h1.l.to_numpy(), cuts)
    ok = n >= V.MIN_BARS
    cuts, rv, rng, ret = cuts[ok], rv[ok], rng[ok], ret[ok]
    f = V.ewma_forecast(rv); med = V.past_median52(rv)
    rows = []
    for k in range(len(cuts)):
        if not np.isfinite(med[k]):
            continue
        rows.append({"เริ่มสัปดาห์ (ไทย)": pd.to_datetime(cuts[k] + TH, unit="s").strftime("%Y-%m-%d"),
                     "ความผันผวน (bp)": round(float(np.sqrt(rv[k])), 0),
                     "เทียบปกติ (เท่า)": round(float(np.sqrt(rv[k] / med[k])), 2),
                     "ระดับ": V.label(rv[k] / med[k])[0],
                     "พยากรณ์เตือน": "ใช่" if V.label(f[k] / med[k])[1] in ("HIGH", "EXTREME") else "ไม่",
                     "ทองทั้งสัปดาห์ (bp)": round(float(ret[k]), 0), "กรอบ (bp)": round(float(rng[k]), 0)})
    return pd.DataFrame(rows)


def main() -> int:
    h1 = load_kind("hour"); d1 = load_kind("day"); m1 = load_kind("min")
    assert h1 is not None, "no hourly data cached yet"
    print(f"H1 {len(h1):,} bars {h1.index[0]} .. {h1.index[-1]}", flush=True)
    inv, built = [], {"H1": h1}
    ts = lambda df: df.index.astype("datetime64[s]").astype(np.int64)  # noqa: E731
    if m1 is not None:
        print(f"M1 {len(m1):,} bars {m1.index[0]} .. {m1.index[-1]} (partial until the download ends)")
        save(m1, "M1"); inv.append(inventory_row("Dukascopy", "M1", ts(m1), 60))
        for name in ("M5", "M15", "M30"):
            df = resample(m1, TFS[name]); save(df, name); built[name] = df
            inv.append(inventory_row("Dukascopy", name, ts(df), 0))
    save(h1, "H1"); inv.append(inventory_row("Dukascopy", "H1", ts(h1), 3600))
    h4 = resample(h1, "4h"); save(h4, "H4"); inv.append(inventory_row("Dukascopy", "H4", ts(h4), 0))
    if d1 is not None:
        save(d1, "D1"); inv.append(inventory_row("Dukascopy", "D1", ts(d1), 86400))
    w1 = resample(h1, "W-SAT"); w1.index = w1.index - pd.Timedelta(days=6); save(w1, "W1")
    mn = resample(h1, "MS"); save(mn, "MN1")
    inv += [inventory_row("Dukascopy", "W1", ts(w1), 0), inventory_row("Dukascopy", "MN1", ts(mn), 0)]
    ex = H / "inventory_mt5.csv"
    invdf = pd.DataFrame(inv)
    if ex.exists():
        e = pd.read_csv(ex).rename(columns={"symbol": "source"})
        e["source"] = "Exness MT5"
        invdf = pd.concat([invdf, e[["source", "tf", "bars", "first", "last", "median_bars_per_day",
                                     "largest_gap_days", "full_intraday_from"]]], ignore_index=True)
    invdf.to_csv(H / "inventory_all.csv", index=False)
    cc = crosscheck(h1)
    (H / "crosscheck_exness.txt").write_text("\n".join(cc), encoding="utf-8")
    yr = yearly(h1)
    wk = weekly_levels(h1)
    hi = wk["ระดับ"].isin(["ผันผวนสูง", "ผันผวนรุนแรง"])
    with pd.ExcelWriter(H / "yearly_2003.xlsx") as xw:
        yr.to_excel(xw, sheet_name="รายปี", index=False)
        wk.to_excel(xw, sheet_name="รายสัปดาห์", index=False)
        invdf.to_excel(xw, sheet_name="ความครอบคลุมข้อมูล", index=False)
    pd.set_option("display.width", 250)
    print(invdf.to_string(index=False)); print("\n".join(cc)); print(yr.to_string(index=False))
    print(f"weeks {len(wk)}; volatile {int(hi.sum())} ({hi.mean():.0%}); "
          f"forecast flagged {(wk.loc[hi, 'พยากรณ์เตือน'] == 'ใช่').mean():.0%} of volatile weeks; "
          f"direction in volatile weeks up {(wk.loc[hi, 'ทองทั้งสัปดาห์ (bp)'] > 0).sum()} / "
          f"down {(wk.loc[hi, 'ทองทั้งสัปดาห์ (bp)'] < 0).sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
