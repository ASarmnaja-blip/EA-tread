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
    # forward panel
    L += ["## 2. แผงทดสอบล่วงหน้า 5 ตัว (H-FOUNDRY-PANEL-1)", "",
          "ผ่านเมื่อค่า E ถึง 500 (เริ่มที่ 1 ทุกตัว ถ้าต่ำกว่า 1 แปลว่ากำลังแพ้)", ""]
    P = read(SH / "forward_panel_weeks.csv")
    panel = json.loads((SH / "forward_panel.json").read_text()) if (SH / "forward_panel.json").exists() else None
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
    # selector
    S = read(SH / "selector_shadow_log.csv")
    Sc = read(SH / "selector_shadow_scores.csv")
    L += ["## 3. ตัวเลือก setup รายสัปดาห์ (SELECTOR-SHADOW-1)", ""]
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
    L += ["## 4. HOD21 (Buy ชั่วโมงก่อนตลาดพักรายวัน ช่วงฤดูหนาว)", ""]
    tr = T[T.exit_kind.isin(["TIME", "STOP"])] if len(T) else T
    if len(tr):
        L.append(f"ไม้ที่ปิดแล้ว {len(tr)} ไม้, สุทธิเฉลี่ย {tr.net_bp.mean():+.2f} bp ({tr.net_R.mean():+.3f} R) หลังต้นทุนและ swap")
    else:
        L.append("ยังไม่มีไม้ (แท่ง 21:00 UTC มีเฉพาะ พ.ย.–มี.ค. และเริ่มนับ 2 ต.ค.)")
    L.append("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
