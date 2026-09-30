"""Weekly champions history of the Family 2 shadow configurations (operator: "ผมต้องการตัวเต็งทุกสัปดาห์ตามหลักคิด wrwr"), from the
corrected WRWR pipeline (C1-C5 contracts, event-driven C2 portfolio, causal vol_scale). One row per Friday cut 2004 .. latest cut with the WRWR regime,
vol_scale, the champions in plain Thai and the realised weekly R of the live C2 replay. Backtest: champions are chosen with no look-ahead, but the
configurations themselves were picked after the Reality Check (in-sample). Writes data/wrwr/wrwr_champions_history.xlsx."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import forward_shadow as FS  # noqa: E402
import portfolio as PF  # noqa: E402

VOL_TH = {"CALM": "สงบ", "NORMAL": "ปกติ", "HIGH": "ผันผวนสูง"}
TR_TH = {"DOWN": "ขาลง", "FLAT": "ไซด์เวย์", "UP": "ขาขึ้น"}


def cell_th(c):
    if not c:
        return "ยังไม่มี"
    v, t = c.split("/")
    return f"{VOL_TH[v]} / {TR_TH[t]}"


def main():
    P, out, active, vs_fwd, cuts, cell, base, data_end = FS.compute(None)
    vs = K.causal_vol_scale(base.t, base.c, base.h, base.l, cuts, mode="historical")
    NW = len(cuts)
    latest = max(k for k in range(NW) if cuts[k] + 1800 <= pd.Timestamp.now(tz="UTC").timestamp() and data_end >= cuts[k] - 4 * 3600)
    wk = pd.to_datetime(cuts, unit="s")
    sheets = {}
    for name in FS.CONFIGS:
        ch = out[name][0]
        wr, eq, cnt = PF.simulate(P, ch, vs, f=0.01)
        rows = []
        cum = 0.0
        for k in range(60, latest + 1):
            if not active[k]:
                continue
            desc = [FS.describe(P, c)["text_th"] for c in ch[k]]
            complete = k < latest
            cum += wr[k] if complete else 0.0
            rows.append({"ตัดรอบ (ศุกร์ 22:15 UTC)": wk[k].strftime("%Y-%m-%d"), "สภาพตลาด WRWR": cell_th(cell[k]),
                         "vol_scale": round(float(vs[k]), 2), "เทรดไหม": "เทรด" if ch[k] else "NO TRADE",
                         "ตัวเต็ง 1": desc[0] if len(desc) > 0 else "", "คะแนน 1": round(float(out[name][1][ch[k][0], k]), 3) if len(ch[k]) > 0 else np.nan,
                         "ตัวเต็ง 2": desc[1] if len(desc) > 1 else "", "คะแนน 2": round(float(out[name][1][ch[k][1], k]), 3) if len(ch[k]) > 1 else np.nan,
                         "R สัปดาห์นั้น": round(float(wr[k]), 3) if complete else np.nan, "R สะสม": round(cum, 2) if complete else np.nan,
                         "สถานะ": "ผลออกครบ" if complete else "สัปดาห์ล่าสุด (กำลังเทรด)"})
        sheets[name] = pd.DataFrame(rows)
        print(name, len(rows), "weeks; total R", round(cum, 1))
    c = FS.CONFIGS
    readme = pd.DataFrame({"อ่านก่อน": [
        "ตัวเต็ง WRWR ทุกสัปดาห์ (Family 2: SMC / ระดับราคา / ปฏิทิน / ความผันผวน) จากท่อคำนวณที่แก้แล้ว: ตัวจำลองพอร์ตตามเหตุการณ์, ต้นทุน+swap จริงตามปี, equity แบบ mark-to-market",
        "ทุกเย็นศุกร์ 22:15 UTC เลือกตัวเต็งจากไม้ที่ปิดไปแล้วเท่านั้น (ไม่รู้อนาคต, ตรวจแล้วว่าตัดข้อมูลหลังรอบออกผลไม่เปลี่ยน) แล้วใช้เทรดสัปดาห์ถัดไปเมื่อสัญญาณเกิด",
        "ชุดกฎ: " + " · ".join(f"{n} = {v['window']} สัปดาห์, LCB z {v['lcb_z']}, กอง {v['pool']}, ตัวเต็ง {v['m']} ตัว" for n, v in c.items()),
        "R = หน่วยความเสี่ยงต่อไม้ (เสี่ยง 1% ของพอร์ตต่อไม้ × vol_scale) หลังหักต้นทุนและ swap · กติกา: หยุดเข้าไม้ใหม่เมื่อสัปดาห์ขาดทุน −3R, เพดานความเสี่ยงรวม 3×, lot ขั้นต่ำ 0.01",
        "นี่คือ backtest: ตัวเต็งเลือกแบบไม่รู้อนาคต แต่ตัวชุดกฎเองถูกเลือกหลังเห็นผล Reality Check (ผ่าน p = 0.003) และยังไม่ผ่านเกณฑ์ PBO กับเกณฑ์ต้นทุน → ไม่ใช่สัญญาณเทรดจริง",
        "ผลกระดาษจริงจะเริ่มสะสมจากรอบตัด 2026-10-02 (docs/WRWR_SHADOW_PREREG.md) กระดาษเท่านั้น ไม่มีคำสั่งเงินจริง"]})
    xl = K.ROOT / "data" / "wrwr" / "wrwr_champions_history.xlsx"
    with pd.ExcelWriter(xl) as xw:
        readme.to_excel(xw, sheet_name="README", index=False)
        for n, d in sheets.items():
            d.to_excel(xw, sheet_name=n, index=False)
    print("->", xl)


if __name__ == "__main__":
    main()
