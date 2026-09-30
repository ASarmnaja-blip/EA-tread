"""Descriptive regime x setup map for the current era (2021-01..2026-08), after 2 bp cost and swap,
written in Thai to docs/FOUNDRY_REGIME_MAP_TH.md. Seen data; not evidence; no gate, no alpha."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import forward_panel as FP  # noqa: E402

H, D, cuts, cell = E.load()
T = FP.trades(H, D, cell, FP.universe(H, D))
T = T[(T.et >= int(np.datetime64("2021-01-01T00:00:00", "s").astype(np.int64))) & (T.cell != "")]
T["vol"] = T.cell.str.split("/").str[0]; T["trend"] = T.cell.str.split("/").str[1]
T["family"] = T.name.str.replace(r"_(t\d|k[\d.]+|h\d+|s[\d.]+|N\d+|L\d+|z[\d.]+|p[\d.]+).*$", "", regex=True) + \
    np.where(T.name.str.contains("~INV"), " (กลับทิศ)", "")
VOL_TH = {"CALM": "สงบ", "NORMAL": "ปกติ", "HIGH": "ผันผวนสูง"}
TR_TH = {"UP": "ขาขึ้น", "FLAT": "ไซด์เวย์", "DOWN": "ขาลง"}
lines = ["# แผนที่สภาพตลาด × setup ยุคปัจจุบัน (2021–2026)", "",
         "> **เชิงบรรยาย ไม่ใช่หลักฐานยืนยัน** ผลหลังหักต้นทุน 2 bp และ swap แล้ว สภาพตลาดมาจาก WPWB "
         "(ความผันผวนที่คาดไว้ × เทรนด์ 13 สัปดาห์) ที่รู้ได้ตั้งแต่เช้าวันเสาร์ ตัวเลขทั้งหมดเป็นข้อมูลที่เห็นแล้วและลองมาหลายร้อยแบบ "
         "ตัวที่ดูดีจึงมีส่วนหนึ่งมาจากความบังเอิญ การยืนยันจริงดูได้ที่บันทึกล่วงหน้า (forward panel)", "",
         "| ความผันผวน | เทรนด์ | สัปดาห์ | ตระกูลที่เป็นบวก / ทั้งหมด | setup ที่เป็นบวกทั้ง 2021–23 และ 2024–26 (R ครึ่งแรก / ครึ่งหลัง) | ข้อสรุป |",
         "|---|---|---|---|---|---|"]
weeks = pd.Series(cell[(cuts >= int(np.datetime64("2021-01-01T00:00:00", "s").astype(np.int64)))[: len(cell)]])
mid = int(np.datetime64("2024-01-01T00:00:00", "s").astype(np.int64))
for v in ("CALM", "NORMAL", "HIGH"):
    for tr in ("UP", "FLAT", "DOWN"):
        x = T[(T.vol == v) & (T.trend == tr)]
        nw = int((weeks == f"{v}/{tr}").sum())
        g = x.groupby("family").R.agg(["mean", "count"])
        g = g[g["count"] >= 20]
        pos = int((g["mean"] > 0).sum())
        a1 = x[x.et < mid].groupby("family").R.agg(["mean", "count"])
        a2 = x[x.et >= mid].groupby("family").R.agg(["mean", "count"])
        both = a1[(a1["count"] >= 15)].join(a2[(a2["count"] >= 15)], lsuffix="_1", rsuffix="_2", how="inner")
        both = both[(both.mean_1 > 0) & (both.mean_2 > 0)].sort_values("mean_2", ascending=False)
        stab = ", ".join(f"{i} ({r.mean_1:+.2f} / {r.mean_2:+.2f})" for i, r in both.head(3).iterrows()) or "–"
        verdict = "งดเทรด" if not len(both) else f"ตัวเต็ง {len(both)} ตัว (ยังไม่ยืนยัน)"
        lines.append(f"| {VOL_TH[v]} | {TR_TH[tr]} | {nw} | {pos} / {len(g)} | {stab} | {verdict} |")
lines += ["", "**อ่านอย่างระวัง:** ถ้าไม่มี edge จริงเลย setup แต่ละตัวมีโอกาสเป็นบวกหลังหักต้นทุนราว 30% ต่อช่วงเวลา "
          "โอกาสบวกทั้งสองครึ่งจึงราว 9% หรือประมาณ 8–9 ตัวจากประมาณ 95 ตัวต่อช่อง จำนวนตัวเต็งที่เห็น (1–11) "
          "ใกล้กับที่ความบังเอิญให้ ตารางนี้จึง**ยังบอกไม่ได้**ว่า setup ไหนดีจริงในสภาพใด ใช้ดูภาพรวมเท่านั้น "
          "สิ่งที่พูดได้ชัดคือช่อง 'สงบ/ขาขึ้น' และ 'สงบ/ขาลง' ไม่มีตัวไหนผ่านเลย", ""]
lines += ["", "ตระกูลที่เห็นบ่อย: SHOCK = ตามหรือสวนหลังแท่งกระชาก, MOM = ตามแรง, NR7/INSIDE_DAY/NR4 = ทะลุหลังช่วงแคบ, "
          "ASIA_BRK = ทะลุกรอบเอเชีย, HOD = ชั่วโมงคงที่ของวัน, DONCH/SMA_TREND = ตามเทรนด์รายวัน, (กลับทิศ) = เล่นฝั่งตรงข้ามของ setup นั้น", ""]
out = E.ROOT / "docs" / "FOUNDRY_REGIME_MAP_TH.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", out)
