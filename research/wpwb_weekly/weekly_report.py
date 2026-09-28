"""WPWB weekly risk report (docs/WPWB_RISK_REPORT_SPEC.md).

Run after each Friday 22:15 UTC cut:
    python research/wpwb_weekly/weekly_report.py --fetch
Optional --cut YYYY-MM-DD (UTC date of the Friday cut; default = latest cut).

Writes data/wpwb_weekly/reports/<cut date>.md (Thai) and appends one row to
data/wpwb_weekly/log.csv. The log is append-only: a row for an existing cut is
never rewritten (a differing recomputation raises instead).

This report is NOT a trading signal. Its only permitted output for risk is
vol_scale <= 1.0. No order function exists anywhere in this package.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import news_plan as NP  # noqa: E402
import vol as V  # noqa: E402

LOG = BR.WEEKLY_DIR / "log.csv"
REPORTS = BR.WEEKLY_DIR / "reports"
FORWARD_START = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))
TH = 7 * 3600
SPEC_VERSION = "v1"


def md_table(df):
    """Markdown table without the optional tabulate dependency."""
    cols = [str(c) for c in df.columns]
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        rows.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v)
                                      for v in r) + " |")
    return "\n".join(rows)


def th(ep, fmt="%a %d %b %Y %H:%M"):
    return pd.to_datetime(int(ep) + TH, unit="s").strftime(fmt)


def compute(m, cut):
    """Everything the report needs at `cut`, using only bars before `cut`."""
    done = BR.cuts_between(m, BR.FIRST_CUT, cut - BR.WEEK)
    assert len(done) and done[-1] == cut - BR.WEEK, "last completed week missing"
    assert int(done[-1]) + BR.WEEK <= cut
    rv, rng, ret, nbar = V.weekly_rv(m.t, m.c, m.h, m.l, done)
    if nbar[-1] < V.MIN_BARS:
        raise RuntimeError(f"DATA_INVALID: last week has {nbar[-1]} H1 bars (< {V.MIN_BARS})")
    fc_now = V.forecast_one_ahead(rv)                       # for week starting `cut`
    f_hist = V.ewma_forecast(rv)                             # f_hist[k] = forecast made for week k
    har_hist = V.har_forecast(rv)
    m26_hist = V.mean26_forecast(rv)
    med = float(np.median(rv[-52:]))
    lab_th, lab_en = V.label(fc_now["ewma"] / med)
    real_th, real_en = V.label(rv[-1] / float(np.median(rv[-53:-1])))
    ok, medlog, tail, ncal = V.calibration(rv, f_hist)
    k = np.flatnonzero(m.t < cut)[-1]
    price = float(m.c[k])
    ratio = rng[-104:] / np.sqrt(rv[-104:])
    range_hat = float(np.median(ratio) * math.sqrt(fc_now["ewma"]))
    return dict(
        cut=cut, data_end=int(m.t[-1]), price=price,
        last=dict(cut=int(done[-1]), rv=float(rv[-1]), bars=int(nbar[-1]), ret=float(ret[-1]),
                  rng=float(rng[-1]), label=real_th, label_en=real_en,
                  f_ewma=float(f_hist[-1]), f_har=float(har_hist[-1]), f_m26=float(m26_hist[-1]),
                  u=float(rv[-1] / f_hist[-1])),
        next=dict(ewma=fc_now["ewma"], har=fc_now["har"], mean26=fc_now["mean26"], med52=med,
                  label=lab_th, label_en=lab_en, vol_scale=V.vol_scale(fc_now["ewma"]),
                  range_hat=range_hat),
        cal=dict(ok=ok, medlog=medlog, tail=tail, n=ncal),
    )


def log_row(r, generated):
    L = r["last"]; N = r["next"]
    return {
        "cut_utc": pd.to_datetime(r["cut"], unit="s").strftime("%Y-%m-%d %H:%M"),
        "spec": SPEC_VERSION, "forward": bool(r["cut"] >= FORWARD_START),
        "data_end_utc": pd.to_datetime(r["data_end"], unit="s").strftime("%Y-%m-%d %H:%M"),
        "f_ewma": round(N["ewma"], 3), "f_har": round(N["har"], 3), "f_mean26": round(N["mean26"], 3),
        "med52": round(N["med52"], 3), "label_fc": N["label_en"], "vol_scale": round(N["vol_scale"], 4),
        "prev_rv": round(L["rv"], 3), "prev_bars": L["bars"], "prev_label": L["label_en"],
        "prev_f_ewma": round(L["f_ewma"], 3), "prev_u": round(L["u"], 4),
        "prev_qlike_ewma": round(float(V.qlike(L["rv"], L["f_ewma"])), 5),
        "prev_qlike_har": round(float(V.qlike(L["rv"], L["f_har"])), 5),
        "prev_qlike_mean26": round(float(V.qlike(L["rv"], L["f_m26"])), 5),
        "prev_ret_bp": round(L["ret"], 1), "prev_range_bp": round(L["rng"], 1),
        "generated_utc": generated,
    }


def append_log(row):
    BR.WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    keys = [k for k in row if k not in ("generated_utc", "data_end_utc")]
    if LOG.exists():
        old = pd.read_csv(LOG, dtype=str)
        hit = old[old.cut_utc == row["cut_utc"]]
        if len(hit):
            prev = hit.iloc[0]
            diff = [k for k in keys if str(prev[k]) != str(row[k])]
            if diff:
                raise RuntimeError(f"log already has cut {row['cut_utc']} with different {diff}; "
                                   "append-only log is never rewritten")
            return "exists"
        pd.DataFrame([row]).to_csv(LOG, mode="a", header=False, index=False)
    else:
        pd.DataFrame([row]).to_csv(LOG, index=False)
    return "appended"


def forward_scores():
    if not LOG.exists():
        return None
    d = pd.read_csv(LOG)
    d = d[d.forward.astype(str) == "True"]
    # a row's prev_* fields score the week before its cut; count only weeks
    # whose forecast was itself made at a forward cut
    d = d.iloc[1:] if len(d) else d
    if not len(d):
        return None
    return dict(n=len(d), ewma=d.prev_qlike_ewma.mean(), har=d.prev_qlike_har.mean(),
                mean26=d.prev_qlike_mean26.mean())


def render(r, nxt, covered, cal_end, lastwk, lw_note, pos_line, fetch_note, status):
    L, N, K = r["last"], r["next"], r["cal"]
    usd = lambda bp: r["price"] * bp / 1e4  # noqa: E731
    fv = math.sqrt(N["ewma"])
    out = [f"# รายงาน WPWB รายสัปดาห์ — สัปดาห์เริ่ม {th(r['cut'])} (เวลาไทย)", "",
           f"**สถานะ:** {status} · สเปก {SPEC_VERSION} · ข้อมูลราคาถึง {th(r['data_end'])} · "
           f"ทองล่าสุดก่อนจุดตัด ${r['price']:,.2f}", ""]
    if fetch_note:
        out += [f"การดึงข้อมูล: {fetch_note}", ""]
    out += ["> รายงานนี้ **ไม่ใช่สัญญาณเทรด** ข้อสรุปทิศทางของโปรเจกต์ยังเป็น **NO TRADE** "
            "(ไม่มี edge ทิศทางที่ผ่านการตรวจ) สิ่งเดียวที่รายงานนี้ให้ใช้คือตัวคูณลดความเสี่ยง", ""]
    out += ["## 1. สัปดาห์ที่แล้ว (เริ่ม " + th(L["cut"], "%d %b") + ")", "",
            "| รายการ | ค่า |", "|---|---|",
            f"| ความผันผวนจริง | {math.sqrt(L['rv']):.0f} bp (≈ ${usd(math.sqrt(L['rv'])):,.0f}) |",
            f"| ระดับ | {L['label']} |",
            f"| เคยพยากรณ์ไว้ (EWMA) | {math.sqrt(L['f_ewma']):.0f} bp |",
            f"| จริง ÷ พยากรณ์ (ความแปรปรวน) | {L['u']:.2f} เท่า |",
            f"| ทองทั้งสัปดาห์ | {L['ret']:+.0f} bp |",
            f"| กรอบสูง-ต่ำ | {L['rng']:.0f} bp (≈ ${usd(L['rng']):,.0f}) |",
            f"| แท่ง H1 | {L['bars']} |", ""]
    out += ["## 2. สัปดาห์หน้า — พยากรณ์ความผันผวน", "",
            "| รายการ | ค่า |", "|---|---|",
            f"| ระดับที่พยากรณ์ | **{N['label']}** ({math.sqrt(N['ewma'] / N['med52']):.2f} เท่าของปกติ 52 สัปดาห์) |",
            f"| ความผันผวนคาด (EWMA, ตัวหลัก) | {fv:.0f} bp (≈ ${usd(fv):,.0f}) |",
            f"| HAR / ค่าเฉลี่ย 26 สัปดาห์ (บันทึกเทียบ) | {math.sqrt(N['har']):.0f} / {math.sqrt(N['mean26']):.0f} bp |",
            f"| กรอบสูง-ต่ำที่คาด (รอง, ยังไม่ยืนยัน) | ≈ {N['range_hat']:.0f} bp (≈ ${usd(N['range_hat']):,.0f}) |",
            f"| ความเคลื่อนไหวต่อแท่ง H1 โดยประมาณ | ≈ {fv / math.sqrt(115):.0f} bp (≈ ${usd(fv / math.sqrt(115)):,.2f}) |",
            f"| เทียบค่าอ้างอิงระยะยาวที่ตรึงไว้ ({math.sqrt(V.B_REF):.0f} bp) | {fv / math.sqrt(V.B_REF):.2f} เท่า |",
            f"| **ตัวคูณขนาดไม้ vol_scale** | **{N['vol_scale']:.2f}** (สูงสุด 1.00 · ต่ำสุด 0.50) |", "",
            "ระดับ (สงบ/ปกติ/ผันผวน) เทียบกับ 52 สัปดาห์ล่าสุด ส่วน vol_scale เทียบกับค่าอ้างอิงระยะยาวที่ตรึงไว้ "
            "ช่วงที่ทองผันผวนกว่าอดีตทั้งยุค จึงลดขนาดไม้แม้ระดับจะ \"ปกติ\"", "",
            "vol_scale ใช้ได้เฉพาะ **ลด** ขนาดไม้หรือเผื่อระยะ SL เทียบกับค่าเริ่มต้นที่ตรึงไว้ "
            "ห้ามใช้เพิ่มความเสี่ยง ห้ามใช้เลือกทิศ/setup/จุดเข้า", ""]
    cal_txt = ("ยังไม่ครบ 26 สัปดาห์" if K["ok"] is None else
               ("อยู่ในเกณฑ์" if K["ok"] else "**หลุดเกณฑ์ → Risk Manager ใช้ค่าเริ่มต้นที่เข้มกว่า**"))
    out += ["## 3. ความแม่นของพยากรณ์ (26 สัปดาห์ล่าสุด)", "",
            f"- สถานะ: {cal_txt}",
            f"- ค่ากลางของ log(จริง/พยากรณ์): {K['medlog']:+.2f} (เกณฑ์ ±{V.CAL_BAND:.2f})",
            f"- สัดส่วนสัปดาห์ที่จริงเกิน 4 เท่าของพยากรณ์: {K['tail']:.0%} (เกณฑ์ < {V.CAL_TAIL_SHARE:.0%})"]
    fs = forward_scores()
    if fs:
        out.append(f"- เดินหน้าจริง {fs['n']} สัปดาห์: QLIKE EWMA {fs['ewma']:.3f} · HAR {fs['har']:.3f} · "
                   f"เฉลี่ย 26 สัปดาห์ {fs['mean26']:.3f} (ต่ำกว่าดีกว่า; เชิงบรรยาย ไม่ใช่การทดสอบ)")
    out += ["", "## 4. ข่าว USD สำคัญสัปดาห์หน้า", ""]
    if not covered:
        out += [f"**ปฏิทินครอบคลุมถึง {th(cal_end)} เท่านั้น — ต้องดัมป์ปฏิทินใหม่ "
                "(MT5 script CalendarDump) ก่อนเชื่อรายการด้านล่าง**", ""]
    out += [md_table(nxt) if len(nxt) else "ไม่มีข่าว USD HIGH ในปฏิทินช่วงนี้", ""]
    out += ["### แผนรับมือ 8 สถานการณ์ (ตรึงไว้ ใช้ทุกข่าว)", "", "| สถานการณ์ | ทำอะไร |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in NP.PLAYBOOK]
    out += ["", "## 5. ข่าวสัปดาห์ที่แล้ว — ราคาตัดสินอย่างไร", ""]
    if lastwk is None or not len(lastwk):
        out += [lw_note, ""]
    else:
        cols = ["เวลาไทย", "events", "สถานการณ์", "surprise_z", "xau_1m", "xau_15m", "xau_60m", "dxy_60m"]
        t = lastwk[cols].copy()
        for c in ("surprise_z", "xau_1m", "xau_15m", "xau_60m", "dxy_60m"):
            t[c] = t[c].map(lambda x: "" if pd.isna(x) else f"{x:+.2f}")
        t.columns = ["เวลาไทย", "ข่าว", "สถานการณ์", "surprise (σ)", "ทอง 1น (ATR)", "ทอง 15น", "ทอง 60น", "DXY 60น"]
        out += [md_table(t), "",
                "ค่า 60 นาทีถูกใช้จัดประเภท จึงไม่ใช่หลักฐานอิสระ (วงกลม); ใช้เพื่อบันทึกเท่านั้น", ""]
        if lw_note != "ok":
            out += [lw_note, ""]
    out += ["## 6. Positioning (CFTC)", "", f"- {pos_line}", "",
            "## 7. สิ่งที่ยังไม่ได้ประเมิน", "",
            "- US yields รายนาที: NOT ASSESSED (บัญชีนี้ไม่มีสัญลักษณ์พันธบัตร)",
            "- Narrative: NOT ASSESSED (ไม่มีแหล่งข้อมูล)",
            "- สิ่งที่ตลาด price-in แล้ว: NOT ASSESSED (ไม่มีข้อมูลตลาดคาดการณ์ดอกเบี้ย)", "",
            "## 8. ข้อสรุป", "",
            f"- ทิศทาง: **NO TRADE** — ไม่มี edge ทิศทางที่ผ่านการตรวจ",
            f"- ความเสี่ยง: ถ้ามีแผนเทรดใดๆ ในสัปดาห์นี้ ใช้ขนาดไม้ × {N['vol_scale']:.2f}",
            f"- สัปดาห์หน้าพยากรณ์ว่า **{N['label']}** — บันทึกไว้ในคลังช่วงผันผวนเพื่อศึกษาต่อ", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", help="UTC date of the Friday cut, YYYY-MM-DD")
    ap.add_argument("--fetch", action="store_true", help="read-only MT5 fetch first")
    args = ap.parse_args()
    fetch_note = ""
    if args.fetch:
        info, res = BR.fetch_weekly()
        fetch_note = f"{info['server']} (trade_mode {info['trade_mode']}, อ่านอย่างเดียว) · " + \
            " · ".join(f"{k}: {v}" for k, v in res.items())
    now = int(datetime.now(timezone.utc).timestamp())
    cut = (int(np.datetime64(args.cut + "T22:15:00", "s").astype(np.int64)) if args.cut
           else BR.last_cut_before(now))
    assert (cut - BR.FIRST_CUT) % BR.WEEK == 0, "cut must be a Friday 22:15 UTC"
    m = BR.market(BR.load_bars(frozen=False))
    if int(m.t[-1]) + 3600 < cut:
        raise RuntimeError("price data ends before the cut; run with --fetch")
    r = compute(m, cut)
    cal = NP.load_cal()
    nxt, covered, cal_end = NP.next_week(cal, cut)
    lastwk, lw_note = NP.last_week(cal, cut - BR.WEEK, cut)
    pos_line = NP.positioning_line(cal, cut)
    status = "FORWARD (นับเป็นข้อมูลเดินหน้าจริง)" if cut >= FORWARD_START else \
        "DRY RUN (ก่อนเริ่มเดินหน้าจริง 2026-10-02 — ไม่นับ)"
    md = render(r, nxt, covered, cal_end, lastwk, lw_note, pos_line, fetch_note, status)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{pd.to_datetime(cut, unit='s'):%Y-%m-%d}.md"
    path.write_text(md, encoding="utf-8")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    state = append_log(log_row(r, generated))
    print(f"report {path} · log {state} · label {r['next']['label_en']} · vol_scale {r['next']['vol_scale']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
