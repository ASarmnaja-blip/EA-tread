# แผนหลัก WRWR รอบใหม่ (2026-09-30) — แก้บั๊ก → ตรวจทั้งระบบ → ทดสอบกับเงิน → บันทึกกระดาษ → ตะแกรง

> **ลำดับความสำคัญ (Amendment 2, หลัง Codex R18b):** Amendment 1–2 และ `docs/WRWR_CONTRACT_PREREG.md` (v2) มีผลเหนือทุกข้อในส่วน B–F ที่ขัดกัน เช่น K = 20, PBO ≤ 0.30, XAG p < 0.10, การแก้ B4 แบบมีเงื่อนไข, กติกาบันทึกกระดาษเดิม, "placebo BASE ≈ 0R", ตาราง "กำไร/DD" และตัวเลข "~20 เท่า/ปีแบบทบ" — ส่วนเหล่านั้นถูกยกเลิก ใช้ C6–C10 แทน


## Context
ผู้ใช้ต้องการระบบ WRWR (ชื่อใหม่ของ WPWB) ที่ย้อนหลังได้กำไร และเลือกตัวเต็งให้ทุกสัปดาห์ ตอนนี้ผลที่ดูดีส่วนใหญ่
**ยังเป็น in-sample** และเพิ่งเจอบั๊ก look-ahead ใน equity filter แผนนี้จัดลำดับตามที่ผู้ใช้สั่ง และกำหนดเกณฑ์ผ่าน/หยุด
เป็นตัวเลขทุกขั้น ก่อนลงมือต้องส่ง Codex ตรวจแผนนี้ก่อน (ขั้น −1) กติกาเดิมยังบังคับใช้ทุกข้อ: ห้าม Grid/Martingale/
ถัวเฉลี่ย, หักต้นทุน 2 bp + swap เสมอ, ประกาศแผนก่อนรัน (pre-register), ห้ามใช้เงินจริงถ้าผู้ใช้ไม่ยืนยันทีละออเดอร์

---

## A. สถานะความรู้ตอนนี้

**พิสูจน์แล้ว (มีหลักฐาน)**
| เรื่อง | ตัวเลข |
|---|---|
| ความผันผวนรายสัปดาห์ทำนายได้ (EWMA ของ WRWR) | calibration ผ่าน → ใช้ลดขนาดไม้ได้ (vol_scale 0.5–1.0) |
| ต่ำกว่า H1 ต้นทุนกินหมด | ค่าต้นทุนต่อไม้ M5 0.26R, M15 0.14R, H1 0.06R, H4 0.03R, D1 0.01R |
| ไม้สุ่ม = ขาดทุนเท่าต้นทุน, อินดิเคเตอร์ 31 ตัวเดี่ยวๆ ไม่ชนะสุ่ม | zoo 1:1 บวก 3%, ตัวบวกทุกยุคน้อยกว่าที่โชคให้ (113 < 163) |
| ตัวเต็งรายยุค (5–6 ปี) ไม่ต่อยุคหน้า | top-5% ยุคหน้าเฉลี่ย ≤ 0 เกือบทุก TF |
| **M5/M15 ตก holdout จริงครั้งแรก** (HistData 2009–2020 ไม่เคยเห็น) | −558R ถึง −609R, บวก 0–2 จาก 11 ปี |
| กฎ BASE (ประกาศก่อนดูผล, 52w LCB top2, H1) | +183R 2004–26 (+8R/ปี) แต่ 5 ปีล่าสุด −15R; เทียบสุ่ม SL/TP เดียวกัน p = 0.041 (ไม่ผ่านเกณฑ์ 0.0025) |

**ยังไม่พิสูจน์ / ปนเปื้อน**
| เรื่อง | ปัญหา |
|---|---|
| WRWR IS (+896R ถึง +1,159R), ทบต้น H4 3 ปี 55.7%/ปี | เลือกโดยรู้ผลแล้ว (184,320 ชุด) และหลายชุดใช้ equity filter ที่มี look-ahead |
| walk-forward-over-configs v2/v3 (+555R/+605R) | ชุดที่ถูกเลือกมี equity filter → อาจสูงเกินจริง |
| ตะแกรงชั้น 2 | สถิติ 3 แบบตก placebo (2,514–2,534 ตัวผ่านบนกราฟปลอม) |

**ข้อมูลที่มีเพิ่ม:** HistData XAU M1 2009–2021, XAU tick 2009-03..2026-09 (209 ไฟล์ 3.6 GB; ขาด 2009-01/02, 2012-06, 2014-12),
M5 ต่อเนื่อง 2009–2026, tick Exness จาก MT5 ตั้งแต่ 2026-01, Dukascopy news tick 105/1,958 (จะหยุด เพราะ HistData ครอบคลุมแล้ว)

---

## B. เป้ากำไรที่เป็นไปได้จริง เทียบ 300R/ปี
- 300R/ปี = เช่น 1,000 ไม้ × +0.30R หรือ 500 ไม้ × +0.60R; ที่เสี่ยง 1%/ไม้ ≈ +300%/ปี แบบไม่ทบ หรือ ~20 เท่า/ปีแบบทบ
- ผลจริงที่ดีที่สุดแบบไม่รู้อนาคต: BASE **+8R/ปี** (+0.033R/ไม้); ตัวเลขที่ดีกว่านั้นยังปนเปื้อนหรือเป็น in-sample
- **300R/ปี ไม่มีหลักฐานรองรับ** ต้องดีกว่าผลที่เชื่อได้ ~35 เท่า
- เป้าที่ใช้ตัดสิน (วัดจาก walk-forward / บันทึกกระดาษ หลังต้นทุน):

| ระดับ | R/ปี | กำไร/DD | ปีที่บวก | ≈ CAGR ที่ 1%/ไม้ |
|---|---|---|---|---|
| ใช้ได้ | ≥ +10R | ≥ 2 | ≥ 55% | ~8–10%, DD ≤ 20% |
| ดี | ≥ +25R | ≥ 3 | ≥ 60% | ~15–25%, DD ≤ 25% |
| ยอดเยี่ยม (หายาก) | ≥ +50R | ≥ 4 | ≥ 70% | ~35%+ |

---

## C. ลำดับงานและเกณฑ์ (ทุกขั้นมีเกณฑ์ผ่าน/หยุดเป็นตัวเลข)

### ขั้น −1 — Codex ตรวจแผน (ก่อนลงมือ)
- บันทึกแผนเป็น `docs/MASTER_PLAN_2026-09-30.md` → รัน `C:\Users\66985\.codex\.sandbox-bin\codex.exe exec` (sandbox read-only)
  ให้ตรวจแผน + โค้ดที่อ้างถึง → เก็บผลที่ `docs/CODEX_R18_MASTER_PLAN.md` → ตอบทุกข้อ (รับ/ไม่รับ + เหตุผล) ในแผน
- **ผ่าน:** ข้อที่ Codex ติดป้าย blocking = 0 ค้าง (แก้แล้วหรือผู้ใช้สั่งข้าม) · **หยุด:** ถ้า Codex ชี้ว่าลำดับหรือเกณฑ์ผิดหลัก → แก้แผนก่อน

### ขั้น 0 — งานด่วนก่อนงานเสาร์ 3 ต.ค. 06:00 (ไม่ขึ้นกับลำดับวิจัย)
- `research/wpwb_weekly/run_weekly.py`: `close_terminal()` ปิด MT5 แบบปกติไม่ได้วันนี้ → เพิ่ม fallback บังคับปิด (ตรวจ Demo +
  ไม่มีไม้เปิดก่อน) และ health check หลังเปิด (`copy_rates_from_pos` ต้องสำเร็จ ไม่งั้นรีสตาร์ต ≤ 2 ครั้ง)
- **ผ่าน:** ทดสอบฟังก์ชันใหม่แบบไม่ต่อท้ายบันทึกใดๆ แล้วดึงราคาได้ · **หยุด:** ถ้าแก้ไม่ทัน รันด้วย `--no-dump` และปล่อยให้แผง 3 เป็น DATA_GAP ตามกติกา fail-closed

### ขั้น 1 — แก้บั๊กที่รู้แล้ว (effort Extra ตอนออกแบบ)
| # | บั๊ก | แก้ |
|---|---|---|
| B1 | equity filter ใช้ R ตามสัปดาห์ที่**เข้า** (ไม้ D1 ถือ ≤ 4 สัปดาห์ยังไม่ปิด) | cache เพิ่ม `E1` แยกตาม exit-lag (สัปดาห์ปิด − สัปดาห์เข้า, ≤ 5) แล้วให้ filter/การตัดสินใจใช้เฉพาะไม้ที่ปิดก่อน cut |
| B2 | walk-forward-over-configs เลือกจากผลรายปีตามสัปดาห์เข้า | ใช้ผลที่ปิดก่อนต้นปีตัดสินใจเท่านั้น |
| B3 | ตัวกรองสัปดาห์ใช้ `EN[:, week] > 0` (รู้ว่าสัปดาห์นั้นมีไม้หรือไม่) | ใช้เฉพาะ `cell[k] != ""` ที่รู้ ณ cut |
| B4 | ตัวเต็งอาจพลาดสัญญาณเพราะเงาของมันยังถือไม้จากสัปดาห์ที่ไม่ได้เป็นตัวเต็ง | วัดสัดส่วนก่อน ถ้า > 5% ให้ simulate ไม้ของตัวเต็งใหม่แบบเริ่มว่างที่ cut (ชุดเล็ก ≤ 9k คู่) |
| B5 | ทบต้นรายสัปดาห์ ไม่จำกัดความเสี่ยงรวม ไม่ปัด lot | จำลองรายไม้ตามลำดับเวลา + เพดานความเสี่ยงเปิดรวม ≤ 3R + lot ขั้นต่ำ 0.01 |
- ไฟล์: `research/foundry/wpwb_walkforward.py`, `wrwr_optimize3.py`, `wrwr_compound.py`, `wrwr_champions.py`, `wrwr_holdout.py`
- **ผ่าน:** รันซ้ำครบ, ตาราง "ก่อน/หลังแก้" ของ BASE, WF-over-configs, IS-best, ทบต้น (full / 5 ปี / 3 ปี) ลง ledger
- **หยุด:** ถ้า BASE (ไม่มี filter) เปลี่ยนเกิน ±20% จาก B3/B4 → หาสาเหตุก่อนไปขั้น 2 (ไม่ควรเปลี่ยนมาก)

### ขั้น 2 — ตรวจทั้งระบบ (โค้ด + สถิติ)
- **2a โค้ด:** รายการตรวจ — เวลา UTC/DST, การแบ่งสัปดาห์ที่ cut 22:15, เวลาปิดแท่ง, รอยต่อแหล่งข้อมูล, ต้นทุน/swap, SL-TP แท่งเดียว,
  gap, vol_scale/regime ที่รู้ ณ cut, ตำแหน่งทีละไม้, cache → Codex ตรวจโค้ดแบบ read-only → `docs/CODEX_R19_WRWR_AUDIT.md`
  **ผ่าน:** blocking = 0 · **หยุด:** มี look-ahead/บัญชีผิด → กลับขั้น 1
- **2b เพดานโชค (placebo):** สร้าง candidate cache บนกราฟปลอม 2 แบบ — (i) กลับทิศรายแท่ง (ไม่มีทิศ, ไม่มี drift) (ii) กลับทิศ + ใส่ drift จริงของทองคืน;
  K = 20 seeds (H1 ก่อน, เวลาคอมราว 7–10 ชม. ไม่กินโทเคน) → รัน BASE / WF-over-configs / IS-best ด้วยโค้ดเดียวกัน
  **ผ่าน:** WF-over-configs จริง ≥ เปอร์เซ็นไทล์ 95 ของแบบ (ii) และ BASE จริง ≥ เปอร์เซ็นไทล์ 90 · รายงาน IS-best หักเพดานโชค
  **หยุด:** WF จริง < เปอร์เซ็นไทล์ 90 → "การเลือกตัวเต็งไม่มีฝีมือเกินโชค+drift" → ขั้น 4 เป็น SHADOW ไม่ใช้ alpha
- **2c PBO (CSCV, 16 บล็อก)** บนเมทริกซ์ชุดตั้งค่าหลังแก้ · **ผ่าน:** PBO ≤ 0.30 · **หยุด:** PBO ≥ 0.50
- **2d ต้นทุนและลำดับแท่ง:** ใช้ tick/M1 ของ HistData แยกลำดับ SL/TP ในแท่งเดียว (2009+) และทดสอบต้นทุน 3 bp / 4 bp
  **ผ่าน:** BASE และชุดที่จะใช้ยังบวกที่ 4 bp และหลังแยกลำดับด้วย tick · **หยุด:** ติดลบที่ 3 bp → ตัดชุดนั้น

### ขั้น 3 — ทดสอบกับเงิน XAGUSD (ข้อมูลที่ไม่เคยเห็น)
- **การอนุมัติแผนนี้ = อนุญาตดาวน์โหลด** HistData XAGUSD M1 2009–2026 (18 zip, ประมาณ 60–100 MB); tick XAG ไม่โหลดตอนนี้
- สร้าง XAG H1/H4/D1, regime WRWR จากข้อมูลเงินเอง, ตัวเลือก 2,232 ตัว/TF เหมือนทอง; ต้นทุน = spread XAG ที่วัดจาก Exness
  (`data/XAGUSD_M5.csv` 2023+) + 1 bp; ใช้ชุดตั้งค่าที่ล็อกจากทอง (BASE + ≤ 3 ชุดที่รอดขั้น 2) **ห้ามจูนบนเงิน**
- **ผ่าน:** BASE บวกและ p (เทียบสุ่ม SL/TP เดียวกัน) < 0.10; แต่ละชุด: net R > 0 และบวก ≥ 55% ของช่วง 52 สัปดาห์; รายงานที่ต้นทุน 2 bp ด้วยเพื่อแยกผลของต้นทุน
- **หยุด:** ทุกชุดติดลบบนเงิน → edge เฉพาะทอง/จูนเกิน → ไม่ใช้ alpha

### ขั้น 4 — บันทึกกระดาษ (หลักฐานจริงอย่างเดียว)
- ล็อก snapshot แบบ `research/foundry_frozen_*` + hash ใน `docs/FOUNDRY_FROZEN_MANIFEST.md`: WRWR-BASE + ≤ 2 ชุดที่รอดขั้น 2–3,
  เขียน `docs/WRWR_FORWARD_PREREG.md` ก่อนเริ่ม; บันทึก hash-chained append-only แบบ `research/foundry/forward_panel.py`
  (ใช้ e-process mixture เดิม), ต่อเข้า `run_weekly.py` dispatcher, สรุปไทยใน `weekly_summary_th.py`
- ส่งออกสัญญาณตาม CLAUDE.md ข้อ 6 (TF, ทิศ, regime, setup, SL/TP, R, หมดอายุ, invalidation, ข่าวที่เสี่ยง, เหตุผลเทรด/NO TRADE)
- Risk Manager (กฎตายตัว ห้ามแก้ระหว่างถือ): vol_scale, ความเสี่ยงเปิดรวม ≤ 3R, หยุดสัปดาห์เมื่อขาดทุน −3R, ไม่เพิ่มไม้แก้ขาดทุน
- ตัวเต็งอันดับ 1 ส่งออเดอร์บน **Demo** ได้ (0.01 lot, ทีละไม้, มี SL) เพื่อวัด fill/slippage เท่านั้น ไม่นับเป็นผลงาน
- เริ่มสัปดาห์แรกที่พร้อมหลังขั้น 3 (เป้า cut ศุกร์ 9 ต.ค. หรือ 16 ต.ค.)
- alpha: ถ้าขั้น 2b และ 3 ผ่าน จะ**ขอผู้ใช้**จัดสรรจาก reserve 0.02 (เสนอ H-WRWR-1 α 0.01, e-value ≥ 100) ไม่งั้นเป็น SHADOW ไม่ใช้ alpha
- **จุดตัดสิน:** สัปดาห์ 13 / 26 / 52
  **ไปต่อ:** R สะสมอยู่ในแถบคาดการณ์ 80% จาก backtest หลังแก้ · **ลดขั้น/หยุด:** R สะสมต่ำกว่าเปอร์เซ็นไทล์ 5 ของแถบ ณ สัปดาห์ 13 หรือ 26,
  หรือ DD เกิน 1.5 เท่าของ DD backtest ที่สเกลตามระยะเวลา
  **ยืนยัน:** e-value ≥ 1/α; **เงินจริง:** ≥ 52 สัปดาห์ + ถึงระดับ "ใช้ได้" ในตาราง B + ผู้ใช้ยืนยันทีละออเดอร์

### ขั้น 5 — ตะแกรง (ซ่อมแล้วรัน)
- **5a Amendment 3:** สาเหตุที่คาด — ตัวแปรระดับราคา (persistent) มีความเอนเอียงแบบ Stambaugh และธงเวลาที่ไม่ได้ center ใน mask ที่ persistent
  → ใช้ null เชิงประจักษ์จาก placebo K = 50 seeds แทน t ทางทฤษฎี และวัดธงเวลาเทียบกับแท่งอื่นในเดือนและ mask เดียวกัน
  **ผ่าน (วิธีวัด):** placebo seed ที่กันไว้ 20 seeds มีตัวผ่าน FDR ≥ 1 ตัว ไม่เกิน 1 seed · **หยุด:** แก้ 2 รอบแล้วยังตก → เลิก scan เชิงสถิติ ใช้เฉพาะการทดสอบแบบเทรดได้ + null สุ่ม SL/TP เดียวกัน
- **5b** รันสแกนจริง A (H1 2003–26), B (M15 2009–26 จาก HistData+Exness), B2 (ข้อมูลภายนอก)
- **5c แผนที่ทีละระดับ** ("ส่วนไหน ระดับเท่าไร"): decile และตาราง 5×5 ของตัวที่รอด + 50 อันดับแรก
  **ผ่านต่อช่อง:** ทิศเดียวกันทุกช่วง, ช่องติดกันทิศเดียวกัน, edge ≥ 2 เท่าของต้นทุน, เกินเปอร์เซ็นไทล์ 95 ของ placebo
- **5d** ตัวที่รอด → กฎเทรดได้ → เข้ากองตัวเลือก WRWR → ต้องผ่านขั้น 2–4 ใหม่

---

## D. ไฟล์หลักที่จะแก้/สร้าง
- แก้: `research/foundry/wpwb_walkforward.py` (E1 ตาม exit-lag, ตัวกรองสัปดาห์, ไม้ตัวเต็งแบบเริ่มว่าง), `wrwr_optimize3.py`, `wrwr_compound.py`,
  `wrwr_champions.py`, `wrwr_holdout.py`, `research/wpwb_weekly/run_weekly.py` (MT5 fallback), `research/sieve/run_scan.py` (Amendment 3),
  `research/history/build_histdata.py` (รองรับ XAGUSD)
- สร้าง: `research/foundry/wrwr_placebo.py`, `wrwr_pbo.py`, `wrwr_forward.py`, `research/history/build_ticks.py`,
  `docs/MASTER_PLAN_2026-09-30.md`, `docs/CODEX_R18_MASTER_PLAN.md`, `docs/CODEX_R19_WRWR_AUDIT.md`, `docs/WRWR_FORWARD_PREREG.md`
- ใช้ของเดิม: `engine.simulate / swap_bp / matched_control / cluster_t`, `vol.effective_scale`, `run_scan.mirror()`,
  e-process + hash chain ของ `forward_panel.py`, รูปแบบ snapshot `foundry_frozen_*`, `weekly_summary_th.py`, `calendar_pit.py`

## E. เวลา / โทเคน / effort (ประมาณการ)
| ขั้น | เวลาจริง | โทเคน | effort |
|---|---|---|---|
| −1 Codex ตรวจแผน + 0 งานด่วน | วันนี้–พรุ่งนี้ | 80–150k | High |
| 1 แก้บั๊ก | 1 วัน | 150–250k | Extra ตอนออกแบบ |
| 2 ตรวจทั้งระบบ (+คอม 7–10 ชม.) | 2–3 วัน | 200–300k | Extra |
| 3 เงิน | 1 วัน | 100–150k | High |
| 4 บันทึกกระดาษ | ตั้งค่า 1 วัน แล้ว 20–30k/สัปดาห์ | 100–150k | Extra ตอนล็อก |
| 5 ตะแกรง | 1–2 สัปดาห์ | 300–500k | Extra ที่ 5a |

## F. Verification
- ทุกขั้น: รันสคริปต์ซ้ำได้ผลเดิม, leak test ผ่าน, ตัวเลขหลักลง `docs/FOUNDRY_LEDGER.md` พร้อม commit
- ขั้น 1: ตาราง ก่อน/หลัง; ตรวจตัวอย่างสุ่ม 20 สัปดาห์ด้วยมือว่าการตัดสินใจใช้แต่ไม้ที่ปิดแล้ว
- ขั้น 2: placebo ต้องให้ BASE ≈ 0R; โค้ดเดียวกันทั้งจริงและ placebo; Codex review ปิดครบ
- ขั้น 4: dry-run dispatcher ก่อน cut แรก ต้องไม่ต่อท้ายบันทึก; hash ตรงกับ manifest
- ขั้น 5: placebo held-out ผ่านก่อนอ่านผลจริง

---

## Amendment 1 — response to Codex R18 (`docs/CODEX_R18_MASTER_PLAN.md`, verdict NOT OK TO START)
All 12 findings accepted; the contracts they ask for are frozen in `docs/WRWR_CONTRACT_PREREG.md` before any code change.
| R18 | decision | where |
|---|---|---|
| 1 B1-B5 real, fixes incomplete (BLOCKING) | accepted: one event-driven portfolio simulator with trade tables, handover rule, chronological sizing, skip below 0.01 lot | contract C2 |
| 2 cut boundary (BLOCKING) | accepted: half-open intervals + synthetic boundary tests on every TF | C1 |
| 3 vol_scale uses future B_REF; weekly_rv 1-h offset (BLOCKING) | accepted: causal rolling B_REF for history, unsized also reported; RV only from H1 | C3 |
| 4 pools/cache/splice/labels (IMPORTANT) | accepted: np.isin pools, versioned caches, splice checks, day/bar labels; ledger corrected (H4+D1 pool in v3 included M5/M15) | C5 |
| 5 XAG needs its own cost/swap (BLOCKING) | accepted: per-symbol table from MT5 (read 2026-09-30) | C4 |
| 6 order | accepted: contracts + tests first; XAG downloaded early but unopened; paper logging starts right after the corrected freeze, alpha-bearing test only after XAG | revised order below |
| 7 per-bar flip placebo, K=20 (BLOCKING) | accepted: primary = SPA / reality check with stationary bootstrap K=999 over the whole family vs a matched benchmark; path null = week-block flips, K=199, supporting | C6 |
| 8 gates too permissive | accepted: PBO upper bound <= 0.20, bootstrap lower-bound cost gate, XAG primary p <= 0.05, maxT/Holm for secondaries | C6, C7 |
| 9 sieve diagnosis (BLOCKING) | accepted: recompute regimes on placebo, centre, matched contrasts, HAC / non-overlap, maxT with >= 999 seeds | C11 |
| 10 forward estimand / alpha (BLOCKING) | accepted: payoff = actual portfolio R floored at -4 under a -3R weekly stop; alpha per hypothesis; weeks 13/26 safety only | C8 |
| 11 target table incoherent | accepted: Calmar-based tiers | C10 |
| 12 champions / scope / roles / prereg | accepted: deployable m <= 2; WRWR = H1-D1 router + risk overlay; role artefacts; hashes in prereg | scope, C2, C9 |

**Revised order:** 0 urgent MT5 fix for Saturday -> 1 contracts + synthetic tests -> 2 event-driven simulator and
versioned trade-table caches (H1/H4/D1) with every fix -> 3 Codex read-only re-audit + old/new reconciliation ->
4 SPA / PBO / cost gates (path null in background) -> 5 freeze candidate hashes and rules; start paper logging (SHADOW) ->
6 XAG readout (downloaded in step 1, opened only now) -> 7 alpha request to the operator if gates pass -> 8 sieve.
Step −1 is closed when Codex confirms no BLOCKING item remains at plan level (R18b).

## Amendment 2 — response to Codex R18b (`docs/CODEX_R18b_MASTER_PLAN.md`)
All 12 R18b findings accepted; `docs/WRWR_CONTRACT_PREREG.md` rewritten as v2: C1 bars must be closed by the cut, entries
open strictly after it, event order exits -> selection -> entries, straddling-bar test (R18b-2); C2 potential-signal
table, U_k, -3U_k entry stop, 3xf stop-dollar cap incl. former champions, 1:100 free-margin test, skip semantics
(R18b-1); C3 exact causal B_REF (R18b-3); C4 full MT5 symbol contract hashed, XAU swap calibration kept and reconciled,
XAG markup -0.20%, candidate-independent pre-2023 XAG cost (R18b-5); C5 numeric splice tests (R18b-4); C6 144-config
deployable family, configuration-specific random-router benchmark with 10,000 seeded paths, studentized White Reality
Check with stationary bootstrap block 10 K = 999 (R18b-7); C6-C7 single methods for PBO bound, XAG lower bound, maxT;
5-week CSCV embargo (R18b-8); C8 winsorised payoff wording, two independent shadow portfolios, 1/3 lambda weights, SEL
fixed before XAG, outcome-blind DATA_GAP, shifted-mean LCB, rules frozen for 52 weeks (R18b-10, R18b-12); C10 replaces
the old target table (R18b-11); C11 exact sieve contract (R18b-9); precedence clause added at the top (R18b-6).
