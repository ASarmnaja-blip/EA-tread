"""Volatility episode log — which weeks were volatile, and what happened.

Descriptive only. It catalogues past weeks so the operator can later study
how to trade volatile periods; it does not claim any edge and nothing in it
chooses direction. Every label is causal: realised RV is compared with the
median of the 52 weeks BEFORE it, and the forecast label uses the EWMA
forecast made before the week began.

Output: data/wpwb_weekly/volatility_log.xlsx (Thai headers) and the summary
printed to stdout (pasted into docs/WPWB_VOLATILITY_LOG.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402

sys.path.insert(0, str(BR.ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402

OUT = BR.WEEKLY_DIR / "volatility_log.xlsx"
TH = 7 * 3600
KEY_EVENTS = {"FOMC": "Fed Interest Rate Decision", "NFP": "Nonfarm Payrolls",
              "CPI": "CPI m/m", "PCE": "Core PCE Price Index m/m"}


def _fmt(ep, offset=0):
    return pd.to_datetime(int(ep) + offset, unit="s").strftime("%Y-%m-%d %H:%M")


def usd_high(cal):
    d = cal[(cal.currency == "USD") & (cal.importance == "HIGH")]
    return d[["epoch", "event"]].reset_index(drop=True)


def build(m, cuts, cal_hi):
    rv, rng, ret, nbar = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    lr = np.full(len(m.t), np.nan)
    lr[1:] = np.diff(np.log(m.c)) * 1e4
    cal_first = int(cal_hi.epoch.min()) if len(cal_hi) else None
    rows = []
    for k, cut in enumerate(cuts):
        use = np.flatnonzero((m.t >= cut) & (m.t < cut + BR.WEEK))
        r_lab = V.label(rv[k] / med[k]) if np.isfinite(med[k]) else ("ไม่ทราบ", "UNKNOWN")
        f_lab = V.label(f[k] / med[k]) if np.isfinite(med[k]) and np.isfinite(f[k]) else ("ไม่ทราบ", "UNKNOWN")
        wk = cal_hi[(cal_hi.epoch >= cut) & (cal_hi.epoch < cut + BR.WEEK)]
        keys = [k2 for k2, name in KEY_EVENTS.items() if (wk.event == name).any()]
        big = []
        if len(use):
            order = use[np.argsort(-np.abs(np.nan_to_num(lr[use])))][:3]
            for i in order:
                near = cal_hi[(cal_hi.epoch >= m.t[i] - 3600) & (cal_hi.epoch < m.t[i] + 3600)]
                tag = ", ".join(sorted(set(near.event))) if len(near) else (
                    "-" if cal_first is not None and m.t[i] >= cal_first else "ไม่มีปฏิทิน")
                big.append(f"{_fmt(m.t[i], TH)} {lr[i]:+.0f}bp [{tag}]")
        rows.append({
            "จุดตัด (UTC)": _fmt(cut),
            "เริ่มสัปดาห์ (เวลาไทย)": _fmt(cut, TH),
            "แท่ง H1": int(nbar[k]),
            "ความผันผวนจริง (bp)": round(float(np.sqrt(rv[k])), 1),
            "ความผันผวนเทียบปกติ (เท่า)": round(float(np.sqrt(rv[k] / med[k])), 2) if np.isfinite(med[k]) else np.nan,
            "ระดับจริง": r_lab[0],
            "พยากรณ์ก่อนเริ่มสัปดาห์ (bp)": round(float(np.sqrt(f[k])), 1) if np.isfinite(f[k]) else np.nan,
            "ระดับที่พยากรณ์": f_lab[0],
            "ตัวคูณขนาดไม้ที่จะใช้": round(V.vol_scale(f[k]), 2) if np.isfinite(f[k]) else np.nan,
            "ทองทั้งสัปดาห์ (bp)": round(float(ret[k]), 0),
            "กรอบสูง-ต่ำ (bp)": round(float(rng[k]), 0),
            "ข่าวหลักในสัปดาห์": ", ".join(keys) if keys else ("-" if cal_first and cut >= cal_first - BR.WEEK else "ไม่มีปฏิทิน"),
            "3 แท่ง H1 ที่แรงที่สุด (เวลาไทย) [ข่าว USD สำคัญ ±1 ชม.]": " | ".join(big),
            "_real": r_lab[1], "_fc": f_lab[1], "_ret": float(ret[k]), "_rng": float(rng[k]),
            "_cut": int(cut),
        })
    return pd.DataFrame(rows)


def episodes(df):
    hi = df["_real"].isin(["HIGH", "EXTREME"]).to_numpy()
    out, k = [], 0
    while k < len(df):
        if not hi[k]:
            k += 1
            continue
        j = k
        while j + 1 < len(df) and hi[j + 1]:
            j += 1
        g = df.iloc[k:j + 1]
        out.append({
            "เริ่ม (เวลาไทย)": g["เริ่มสัปดาห์ (เวลาไทย)"].iloc[0][:10],
            "จำนวนสัปดาห์": j - k + 1,
            "ระดับสูงสุด": "ผันผวนรุนแรง" if (g["_real"] == "EXTREME").any() else "ผันผวนสูง",
            "สูงสุดกี่เท่าของปกติ": g["ความผันผวนเทียบปกติ (เท่า)"].max(),
            "พยากรณ์เตือนล่วงหน้าสัปดาห์แรก": "ใช่" if g["_fc"].iloc[0] in ("HIGH", "EXTREME") else "ไม่",
            "ทองรวมช่วงนี้ (bp)": round(float(g["_ret"].sum()), 0),
            "ข่าวหลัก": ", ".join(sorted({x for s in g["ข่าวหลักในสัปดาห์"] for x in s.split(", ")
                                        if x not in ("-", "ไม่มีปฏิทิน", "")})) or "-",
        })
        k = j + 1
    return pd.DataFrame(out)


def summary(df, ep):
    d = df[df["_real"] != "UNKNOWN"]
    hi = d["_real"].isin(["HIGH", "EXTREME"])
    fc_hi = d["_fc"].isin(["HIGH", "EXTREME"])
    lines = [
        f"สัปดาห์ที่จัดระดับได้: {len(d)} ({d['เริ่มสัปดาห์ (เวลาไทย)'].iloc[0][:10]} ถึง "
        f"{d['เริ่มสัปดาห์ (เวลาไทย)'].iloc[-1][:10]})",
        "ระดับจริง: " + ", ".join(f"{lab} {int((d['ระดับจริง'] == lab).sum())}" for lab in V.LABELS),
        f"สัปดาห์ผันผวนสูงขึ้นไป: {int(hi.sum())} ({hi.mean():.0%}); รวมเป็น {len(ep)} ช่วง",
        f"พยากรณ์เตือนล่วงหน้าได้: {int((hi & fc_hi).sum())}/{int(hi.sum())} สัปดาห์ผันผวน "
        f"({(fc_hi[hi]).mean():.0%}); เตือนแต่ไม่เกิด {int((fc_hi & ~hi).sum())} ครั้ง",
        f"สัปดาห์ผันผวน: ทองขึ้น {int((d.loc[hi, '_ret'] > 0).sum())} / ลง {int((d.loc[hi, '_ret'] < 0).sum())}; "
        f"เคลื่อนเฉลี่ย |{d.loc[hi, '_ret'].abs().mean():.0f}| bp เทียบสัปดาห์ปกติ |{d.loc[~hi, '_ret'].abs().mean():.0f}| bp",
        f"กรอบสูง-ต่ำเฉลี่ย: สัปดาห์ผันผวน {d.loc[hi, '_rng'].mean():.0f} bp, สัปดาห์อื่น {d.loc[~hi, '_rng'].mean():.0f} bp",
    ]
    return lines


def main() -> int:
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    cal = calendar_feed.load_calendar(str(BR.ROOT / "data" / "calendar.csv"))
    df = build(m, cuts, usd_high(cal))
    ep = episodes(df)
    lines = summary(df, ep)
    BR.WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    pub = [c for c in df.columns if not c.startswith("_")]
    with pd.ExcelWriter(OUT) as xw:
        pd.DataFrame({"สรุป": lines + ["", "ข้อมูลเชิงบรรยายเท่านั้น ไม่ใช่ edge และไม่ใช้เลือกทิศทาง"]}).to_excel(
            xw, sheet_name="สรุป", index=False)
        ep.to_excel(xw, sheet_name="ช่วงผันผวน", index=False)
        df[pub].to_excel(xw, sheet_name="รายสัปดาห์", index=False)
    print("\n".join(lines))
    print("\nช่วงผันผวน (ล่าสุด 15):")
    print(ep.tail(15).to_string(index=False))
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
