"""WRWR weekly champions (operator 2026-09-30: "ผมต้องการตัวเต็งทุกสัปดาห์ตามหลักคิด wrwr").
For every Friday 22:15 UTC cut: the WRWR regime of the coming week, vol_scale, and the champion(s) each system picks
from trades that had already closed, with the realised result once known. Systems:
  BASE = pre-registered walk-forward rule (52-week LCB, top 2, WRWR sizing) - fixed before its results were seen;
  IS   = the in-sample best of wrwr_optimize.py (52-week LCB, SL 2 ATR pool, top 5, equity filter, no sizing) - hindsight.
Uses the spliced cache (Dukascopy + live Exness) when present so the current week is included.
Writes data/foundry/wrwr_champions.xlsx and data/foundry/wrwr_champion_now.md. Paper only; no orders."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import vol as V  # noqa: E402

sp = E.ROOT / "data" / "foundry" / "wpwb_walkforward_cache_spliced.npz"
SPLICED = sp.exists()
z = np.load(sp if SPLICED else E.ROOT / "data" / "foundry" / "wpwb_walkforward_cache.npz", allow_pickle=True)
C = pd.DataFrame(z["cands"].tolist()); S1, S2, NN, E1, EN = (z[x] for x in ("S1", "S2", "NN", "E1", "EN"))
H, _, cuts, cell = E.load_spliced() if SPLICED else E.load()
NW = len(cuts)
rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
rv = V.mask_invalid(rv_raw, nb); F = V.ewma_forecast(rv)
scale = np.full(NW, V.SCALE_MIN)
for k in range(1, NW):
    scale[k] = V.effective_scale(V.vol_scale(F[k]), V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
data_end = int(H.t[-1]) + 3600
wkdate = pd.to_datetime(cuts, unit="s")
cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]
cS1, cS2, cN = cum(S1), cum(S2), cum(NN)
VOL_TH = {"CALM": "สงบ", "NORMAL": "ปกติ", "HIGH": "ผันผวนสูง"}; TR_TH = {"DOWN": "ขาลง", "FLAT": "ไซด์เวย์", "UP": "ขาขึ้น"}
th_cell = lambda c: f"{VOL_TH[c.split('/')[0]]} / {TR_TH[c.split('/')[1]]}" if c else "ยังไม่มี (ข้อมูลไม่พอ)"
MODE_TH = {"FOLLOW": "ตามสัญญาณ", "FADE": "สวนสัญญาณ"}


def exit_th(e):
    a, b = e.split(":")
    return f"TP {b} เท่าของ SL" if a == "1" and b != "1" else ("TP = SL" if e == "1:1" else f"TP 1/{a} ของ SL")


C["label_th"] = [f"{r.setup} · {MODE_TH[r.mode]} · SL {r.k_atr} ATR · {exit_th(r.exit)} · ถือไม่เกิน {r.hold} ชม." for r in C.itertuples()]
SYSTEMS = {"BASE": dict(window=52, z=1.0, minn=10, pool=np.ones(len(C), bool), m=2, sized=True, eqf=False,
                        desc="กฎที่ประกาศไว้ก่อนดูผล: 52 สัปดาห์ · LCB · 2 ตัว · ลดขนาดไม้ตาม WRWR (walk-forward แท้)"),
           "IS": dict(window=52, z=1.0, minn=10, pool=(C.k_atr == 2).to_numpy(), m=5, sized=False, eqf=True,
                      desc="ชุดที่จูนย้อนหลังดีที่สุด (in-sample): 52 สัปดาห์ · LCB · เฉพาะ SL 2 ATR · 5 ตัว · หยุดเทรดเมื่อผล 26 สัปดาห์ติดลบ")}
first = 60
out_rows, now_md = {}, []
for sname, P in SYSTEMS.items():
    rows, cumR, hist = [], 0.0, []
    for k in range(first, NW):
        if wkdate[k] > pd.Timestamp(data_end, unit="s"):
            break
        a = max(0, k - P["window"])
        s1, s2, n = cS1[:, k] - cS1[:, a], cS2[:, k] - cS2[:, a], cN[:, k] - cN[:, a]
        mu = s1 / np.maximum(n, 1); var = (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1)
        sc = np.where((n >= P["minn"]) & P["pool"], mu - P["z"] * np.sqrt(np.maximum(var, 0) / np.maximum(n, 1)), -np.inf)
        top = np.argsort(-sc)[: P["m"]]; top = top[sc[top] > 0]
        live = True
        if P["eqf"]:
            live = sum(hist[-26:]) > 0             # same rule as wrwr_optimize.py (no history -> no trade)
        if k >= len(cell) or cell[k] == "":
            top = top[:0]                           # no WRWR regime yet -> not traded (as in the optimiser)
        shadowR = float(E1[top, k].sum()) if len(top) else 0.0
        done = int(cuts[k]) + 7 * 86400 + 72 * 3600 <= data_end          # every trade of the week has had time to exit
        sz = scale[k] if P["sized"] else 1.0
        R = shadowR * sz if (live and len(top)) else 0.0
        hist.append(shadowR)
        cumR += R if done else 0.0
        status = "ผลออกครบ" if done else ("สัปดาห์นี้ (กำลังเทรด)" if int(cuts[k]) <= data_end < int(cuts[k]) + 7 * 86400 else "ไม้ยังเปิดอยู่บางส่วน")
        rec = dict(ตัดรอบ_ศุกร์_UTC=wkdate[k].strftime("%Y-%m-%d %H:%M"), สภาพตลาด_WRWR=th_cell(cell[k] if k < len(cell) else ""),
                   vol_scale=round(float(scale[k]), 2) if P["sized"] else 1.0,
                   เทรดไหม=("NO TRADE (ไม่มีตัวคะแนนบวก)" if not len(top) else ("เทรด" if live else "NO TRADE (ผล 26 สัปดาห์ติดลบ)")))
        for j in range(P["m"]):
            rec[f"ตัวเต็ง_{j + 1}"] = C.label_th[top[j]] if j < len(top) else ""
            rec[f"คะแนน_{j + 1}"] = round(float(sc[top[j]]), 3) if j < len(top) else np.nan
        rec.update(จำนวนไม้=int(EN[top, k].sum()) if len(top) else 0, R_สัปดาห์นี้=round(R, 3), R_สะสม=round(cumR, 2), สถานะ=status)
        rows.append(rec)
    out_rows[sname] = pd.DataFrame(rows)
    last = out_rows[sname].iloc[-1]
    now_md.append(f"### ระบบ {sname}\n{P['desc']}\n\n- ตัดรอบ: {last['ตัดรอบ_ศุกร์_UTC']} UTC · สภาพตลาด WRWR: **{last['สภาพตลาด_WRWR']}** · "
                  f"vol_scale {last['vol_scale']} · **{last['เทรดไหม']}** · สถานะ: {last['สถานะ']}\n" +
                  "".join(f"- ตัวเต็ง {j + 1}: {last[f'ตัวเต็ง_{j + 1}']} (คะแนน {last[f'คะแนน_{j + 1}']})\n"
                          for j in range(P["m"]) if last[f"ตัวเต็ง_{j + 1}"]) +
                  f"- R สะสมทั้งระบบ (สัปดาห์ที่ผลออกครบ): {last['R_สะสม']:+.1f} R\n")
xl = E.ROOT / "data" / "foundry" / "wrwr_champions.xlsx"
with pd.ExcelWriter(xl) as xw:
    pd.DataFrame({"อ่านก่อน": [
        f"ตัวเต็ง WRWR ทุกสัปดาห์ · ทองคำ H1 {'Dukascopy + Exness สด' if SPLICED else 'Dukascopy'} · ข้อมูลถึง {pd.Timestamp(data_end, unit='s'):%Y-%m-%d %H:%M} UTC",
        "ทุกเย็นศุกร์ 22:15 UTC เลือกตัวเต็งจากไม้ที่ปิดไปแล้วเท่านั้น (ไม่รู้อนาคต) แล้วใช้เทรดทั้งสัปดาห์ถัดไปเมื่อสัญญาณของตัวนั้นเกิด",
        "BASE = " + SYSTEMS["BASE"]["desc"], "IS = " + SYSTEMS["IS"]["desc"] + " · ผลย้อนหลังของ IS สวยเพราะเลือกชุดตั้งค่าโดยรู้ผลแล้ว",
        "R = หน่วยความเสี่ยงต่อไม้ หลังหักต้นทุนและ swap · ตัวเต็งหนึ่งตัวถือได้ทีละไม้ · กระดาษเท่านั้น ห้ามใช้เงินจริง"]}).to_excel(
        xw, sheet_name="README", index=False)
    for sname, D in out_rows.items():
        D.to_excel(xw, sheet_name=f"{sname} ทุกสัปดาห์", index=False)
md = E.ROOT / "data" / "foundry" / "wrwr_champion_now.md"
md.write_text(f"# ตัวเต็ง WRWR สัปดาห์ล่าสุด\n\nข้อมูลถึง {pd.Timestamp(data_end, unit='s'):%Y-%m-%d %H:%M} UTC · กระดาษเท่านั้น\n\n" + "\n".join(now_md),
              encoding="utf-8")
print(md.read_text(encoding="utf-8"))
for sname, D in out_rows.items():
    print(sname, len(D), "weeks; last 6:"); print(D.tail(6)[["ตัดรอบ_ศุกร์_UTC", "สภาพตลาด_WRWR", "เทรดไหม", "ตัวเต็ง_1", "R_สัปดาห์นี้", "R_สะสม", "สถานะ"]].to_string(index=False))
