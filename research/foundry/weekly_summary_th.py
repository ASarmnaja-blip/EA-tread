"""One Thai page summarising every paper forward record after the Saturday job:
data/wpwb_weekly/forward_summary_th.md. Read-only; changes nothing."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / "data" / "foundry" / "shadow"
OUT = ROOT / "data" / "wpwb_weekly" / "forward_summary_th.md"


def read(p):
    try:
        return pd.read_csv(p) if p.exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main():
    L = [f"# สรุปบันทึกล่วงหน้า (กระดาษ) — สร้าง {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
         "> ทุกอย่างในหน้านี้เป็นการบันทึกแบบกระดาษ **ไม่มีการส่งคำสั่ง ไม่เปลี่ยนขนาดไม้** "
         "ขนาดไม้ยังใช้รายงานความเสี่ยง WPWB ตามเดิม", ""]
    # outlook
    lat = ROOT / "data" / "wpwb_weekly" / "outlook_shadow_latest.md"
    L += ["## 1. พยากรณ์ความผันผวนสัปดาห์หน้า (Outlook)", ""]
    L += (lat.read_text(encoding="utf-8").splitlines()[2:] if lat.exists() else ["ยังไม่มีข้อมูล"]) + [""]
    # forward panels
    for js, sc, title in [(SH / "forward_panel.json", SH / "forward_panel_weeks.csv", "แผงทดสอบล่วงหน้า 1 (H-FOUNDRY-PANEL-1)")] + \
            [(j, SH / (j.stem + "_weeks.csv"), f"แผงทดสอบล่วงหน้า {j.stem.split('panel')[-1]} (H-FOUNDRY-PANEL-{j.stem.split('panel')[-1]})")
             for j in sorted(SH.glob("forward_panel*.json")) if j.name != "forward_panel.json"]:
        if js.exists():
            L += _panel_section(js, sc, title)
    L += _auditor()
    Pf = read(SH / "forward_portfolio1_weeks.csv")
    L += ["## พอร์ตรวม 6 ตัว (H-FOUNDRY-PORTFOLIO-1)", "", "ผ่านเมื่อค่า E ถึง 100", ""]
    L.append(f"สัปดาห์ที่นับ {len(Pf)}, R เฉลี่ยต่อสัปดาห์ {Pf.week_R.mean():+.3f}, ค่า E {Pf.E.iloc[-1]:.2f}"
             if len(Pf) else "รอสัปดาห์แรก (เริ่มนับ 2 ต.ค.)")
    L.append("")
    L += _rest()
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", OUT)


def _panel_section(js, sc, title):
    L = []
    panel = json.loads(js.read_text())
    L += [f"## {title}", "", f"ผ่านเมื่อค่า E ถึง {1 / panel['alpha_each']:.0f} (เริ่มที่ 1 ถ้าต่ำกว่า 1 แปลว่ากำลังแพ้)", ""]
    P = read(sc)
    if panel:
        L += ["| setup | สภาพตลาด | สัปดาห์ที่นับ | ไม้ทั้งหมด | R เฉลี่ยต่อสัปดาห์ | ค่า E | สถานะ |", "|---|---|---|---|---|---|---|"]
        for c in panel["candidates"]:
            g = P[P.name == c["name"]] if len(P) else P
            if len(g):
                L.append(f"| {c['name']} | {c['cell']} | {len(g)} | {int(g.trades.sum())} | {g.week_R.mean():+.3f} | "
                         f"{g.E.iloc[-1]:.2f} | {'ผ่าน → เสนอทดสอบ Demo' if g.reject.any() else 'กำลังเก็บ'} |")
            else:
                L.append(f"| {c['name']} | {c['cell']} | 0 | 0 | – | 1.00 | รอสัปดาห์แรก |")
        L.append("")
        if len(P) and "row_sha" in P:
            tips = ", ".join(f"{n}: `{g.row_sha.iloc[-1]}`" for n, g in P.groupby("name"))
            L += [f"hash ปลายลูกโซ่ (จดไว้เพื่อยืนยันว่าไฟล์ไม่ถูกลบย้อนหลัง): {tips}", ""]
    return L


def _auditor():
    """Drift check (CLAUDE.md gap 7): forward mean of week_R_clip vs the 2021-26 expectation. A flag is a
    warning to look, not a test and not a reason to change any frozen rule."""
    ex = SH / "expectations.json"
    if not ex.exists():
        return []
    X = json.loads(ex.read_text())
    frames = [read(p) for p in sorted(SH.glob("forward_panel*_weeks.csv"))]
    A = pd.concat([f for f in frames if len(f)]) if any(len(f) for f in frames) else pd.DataFrame()
    L = ["## ผู้ตรวจสอบ (Auditor): เทียบผลจริงกับที่คาดจากอดีต", "",
         "ธงเตือนขึ้นเมื่อผ่านไปแล้วอย่างน้อย 8 สัปดาห์ และค่าเฉลี่ยจริงต่ำกว่าค่าคาดเกิน 2 เท่าของความคลาดเคลื่อน",
         "ธงเป็นแค่สัญญาณให้เข้าไปดู ไม่ใช่เหตุให้แก้กฎที่ล็อกไว้", "",
         "| setup | สัปดาห์ | R จริงเฉลี่ย | R ที่คาด | ความคลาดเคลื่อน | สถานะ |", "|---|---|---|---|---|---|"]
    for name, e in X.items():
        g = A[(A.name == name) & (A.status == "OK")] if len(A) else A
        n = len(g)
        if n == 0:
            L.append(f"| {name} | 0 | – | {e['mean']:+.3f} | – | รอข้อมูล |"); continue
        m = float(g.week_R_clip.mean()); se = e["sd"] / np.sqrt(n)
        flag = "⚠ ต่ำกว่าคาดชัดเจน (drift?)" if n >= 8 and m < e["mean"] - 2 * se else ("ปกติ" if n >= 8 else "ยังน้อยเกินไป")
        L.append(f"| {name} | {n} | {m:+.3f} | {e['mean']:+.3f} | ±{se:.3f} | {flag} |")
    return L + [""]


def _rest():
    L = []
    # selector
    S = read(SH / "selector_shadow_log.csv")
    Sc = read(SH / "selector_shadow_scores.csv")
    L += ["## ตัวเลือก setup รายสัปดาห์ (SELECTOR-SHADOW-1)", ""]
    if len(S):
        r = S.iloc[-1]
        L.append(f"สัปดาห์ล่าสุด {r.cut_utc} UTC: {r.status}, เลือก {r.n_selected} setup, สภาพ {r.vol_class}")
    else:
        L.append("ยังไม่มีสัปดาห์จริง (เริ่มนับ 2 ต.ค.)")
    if len(Sc):
        sc = Sc[Sc.status == "SCORED"]
        if len(sc):
            L.append(f"ผลที่นับแล้ว {len(sc)} สัปดาห์: R เฉลี่ยต่อสัปดาห์ {sc.week_R.mean():+.3f}")
    L += ["", "หมายเหตุ: ในข้อมูลย้อนหลังช่วง 2021–2026 ตัวเลือกแบบนี้ขาดทุน จึงไม่ได้คาดหวังสูง", ""]
    # hod21
    T = read(SH / "hod21_shadow_trades.csv")
    L += ["## HOD21 (Buy ชั่วโมงก่อนตลาดพักรายวัน ช่วงฤดูหนาว)", ""]
    tr = T[T.exit_kind.isin(["TIME", "STOP"])] if len(T) else T
    if len(tr):
        L.append(f"ไม้ที่ปิดแล้ว {len(tr)} ไม้, สุทธิเฉลี่ย {tr.net_bp.mean():+.2f} bp ({tr.net_R.mean():+.3f} R) หลังต้นทุนและ swap")
    else:
        L.append("ยังไม่มีไม้ (แท่ง 21:00 UTC มีเฉพาะ พ.ย.–มี.ค. และเริ่มนับ 2 ต.ค.)")
    L.append("")
    return L


if __name__ == "__main__":
    main()
