# HANDOFF — สถานะโปรเจกต์ทั้งหมด

เอกสารนี้คือจุดเข้าเดียวสำหรับ Claude Code ที่รันบนเครื่องผู้ใช้
อ่านไฟล์นี้จบก่อนแตะอะไรทั้งสิ้น

```
branch   claude/claude-md-project-file-qh0ier
commit   4a672d0
ขนาด     88 ไฟล์ · 18,752 บรรทัด · 17 commits
สถานะ    working tree สะอาด
```

---

## 0. ลำดับการอ่าน

| # | ไฟล์ | ทำไมต้องอ่าน |
|---|---|---|
| 1 | `CLAUDE.md` | **คำสั่งประจำโปรเจกต์** เป็นกฎสูงสุด ทับทุกอย่างในไฟล์นี้ |
| 2 | `HANDOFF.md` | ไฟล์นี้ — สถานะและแผนที่ |
| 3 | `docs/ENGINE_PROTOCOL.md` | โปรโตคอล v2: เกณฑ์ ต้นทุน การแยกคะแนน การห้ามต่าง ๆ |
| 4 | `docs/MT5_RUNBOOK.md` | งานที่ต้องรันบนเครื่อง + พิสูจน์ว่าไม่เทรด |
| 5 | `docs/RESEARCH_FINDINGS.md` | 748 บรรทัด บันทึกว่าอะไรเคยถูกทดสอบแล้วตาย **อ่านก่อนเสนอ setup ใด ๆ** |

---

## 1. เป้าหมายของผู้ใช้

จาก `CLAUDE.md` ซึ่งส่งต่อมาจาก ChatGPT/Codex ในฐานะผู้ร่วมวางระบบ

### สิ่งที่ต้องการจริง

**ไม่ใช่กลยุทธ์ตายตัวที่ชนะทุกยุค** และ**ไม่ได้กำหนดว่าต้องทำกำไรตลอด
ประวัติศาสตร์** เป้าหมายคือ **Adaptive Current-Regime Signal Engine** สำหรับ
**XAUUSD บน M5/M15** ที่:

1. เหมาะกับสภาพตลาด**ปัจจุบัน**มากที่สุด
2. ประเมินตลาดใหม่อย่างต่อเนื่อง
3. ปรับตัวเมื่อ Regime, Narrative, Volatility หรือพฤติกรรมราคาเปลี่ยน
4. **ยอมเลิกใช้กลยุทธ์ที่เคยดีทันที** เมื่อหลักฐานปัจจุบันบอกว่า Edge เสื่อม
5. ไม่บังคับให้สัญญาณปัจจุบันต้องชนะตลาดในอดีตไกล
6. สร้างแผนรับมือครบทุกสถานการณ์

ข้อมูลอดีตระยะยาวใช้**ตรวจข้อผิดพลาดร้ายแรง** ไม่ใช่ข้อบังคับว่าต้องกำไรย้อนหลัง
แต่**ห้ามใช้ข้ออ้าง "เน้นตลาดปัจจุบัน" เพื่อจูนข้อมูลชุดเดียวจนได้กำไรลวง**

### หลักคิดเรื่องข่าว

**ข่าวกำหนดสมมติฐาน แต่ปฏิกิริยาของราคาตัดสินว่าสมมติฐานได้รับการยืนยันหรือไม่**
ต้องประเมินพร้อมกัน: สิ่งที่ตลาดคาด · Actual vs Consensus vs Previous ·
Revision · สิ่งที่ price-in แล้ว · Positioning · Narrative · ปฏิกิริยาของ
XAUUSD/DXY/US yields · การยอมรับหรือปฏิเสธราคาหลังข่าว

ต้องมีแผน 8 สถานการณ์: บวก+ยืนยัน · บวก+ปฏิเสธ · ลบ+ยืนยัน · ลบ+ปฏิเสธ ·
ออกใกล้คาด · ข้อมูลขัดแย้ง · กวาดสภาพคล่องสองด้าน · **สภาวะที่ไม่ควรเทรด**

### สิ่งที่ห้ามเด็ดขาด

- ห้ามอ้างว่ารับประกันกำไร
- ห้าม Grid / Martingale เพื่อซ่อนว่าวิเคราะห์ผิด
- ห้ามแก้กฎความเสี่ยงระหว่างถือสถานะ
- **ห้ามส่งคำสั่งเงินจริงก่อนได้คำยืนยันจากผู้ใช้**
- ห้ามสลับ Champion เพราะแพ้หนึ่งออเดอร์
- ห้าม Agent เดียวสร้าง+อนุมัติ+ส่งคำสั่ง+ประเมินผลตัวเอง

---

## 2. สถานะปัจจุบัน — 3 สายงาน

### Track A — EA (MQL5) · **PAUSED, AUTHORED ไม่ใช่ VERIFIED**

พักไว้ตามคำสั่งผู้ใช้ ไม่ถูกลบหรือย้อน

| | |
|---|---|
| ทำอะไรไปแล้ว | ขยาย signal schema เป็น 15 ช่อง + decision log ต่อแท่ง |
| ทดสอบแล้ว | 9 static invariants + 25 system tests (คอมไพล์ production source จริงด้วย g++ ผ่าน MQL5 shim) + 6 mutations |
| **ยังค้าง** | **C1–C7 (compile ใน MetaEditor) และ R1–R8 (A/B backtest)** ดู `docs/MT5_RUNBOOK.md` |
| บั๊กที่เจอจากการทดสอบ | `FileWrite` ของ MQL5 ไม่ escape อะไรเลย และ `Setups.mqh` เขียนสตริงที่มีจุลภาคลง CSV → หนึ่งแถวตรรกะถูกฉีกเป็นสองบรรทัด แก้ด้วย `CsvEscape()` ตาม RFC 4180 |

### Track B — Setup pilot บน futures proxy · **PAUSED**

พักเพราะผู้ใช้ตัดสินให้รอข้อมูล XAUUSD จริง

- ทำบน `GC=F` (COMEX gold futures) เพราะ container ไม่มี XAUUSD spot
- **ห้ามใช้เป็นตัวแทนของ XAUUSD** — ผู้ใช้สั่งห้ามแทนที่ด้วย GC/MGC/GLD/ข้อมูลจำลอง
- ราคาตลาด **ยังไม่เคยถูกอ่านเพื่อประเมินผล** — pipeline หยุดที่ P1 ทุกครั้ง

### Track C — Engine 3 ชั้น · **ทดสอบผ่านครบ**

สร้างและทดสอบได้โดยไม่ต้องมี MT5 เพราะทุกเคสมีคำตอบที่รู้ล่วงหน้า

| โมดูล | หน้าที่ | tests |
|---|---|---|
| `research/pilot/news.py` | แยก "ข่าวตั้งสมมติฐาน" จาก "ราคาตัดสิน" จัดเข้า 8 สถานการณ์ | 30 |
| `research/pilot/regime.py` | **Market Regime Score** — วัดว่าลักษณะตลาดเองเปลี่ยนไปแค่ไหน | 20 |
| `research/pilot/decide.py` | ประกอบเป็นสัญญาณหรือ NO TRADE ตาม schema 15 ช่อง | 26 |

**รวม 76 tests + 6 mutations ผ่านทั้งหมด**

---

## 3. แผนที่ไฟล์ทั้งหมด

### `CLAUDE.md` — กฎสูงสุด (282 บรรทัด)

### `docs/` — บันทึกการตัดสินใจ อ่านตามลำดับเวลา

| ไฟล์ | บรรทัด | เนื้อหา |
|---|---|---|
| `ENGINE_PROTOCOL.md` | 250 | โปรโตคอล v2 — AUTHORED vs VERIFIED, สองชั้นเกณฑ์, posterior bands, sequential protocol, การแยก MRS/SHS, paired comparison, ต้นทุน 5 ตัวแยกกัน, ห้าม Kelly |
| `PILOT_PREREGISTRATION.md` | 343 | Pre-registration ของ pilot — ข้อมูลที่มี, 18 configurations, cost model, pass/fail |
| `P1_FINDINGS.md` | 126 | **P1 ตกครั้งแรก** — เจอบั๊ก SE จริง (pooled ต่ำกว่าจริง 1.12–3.38×) + 4 สมมติฐานที่ตกไป |
| `AMENDMENT_01_CIRCULAR_SHIFT_CONTROL.md` | 174 | เปลี่ยน control เป็น circular time shift + เหตุผลเชิงกลไก |
| `AMENDMENT_01_CALIBRATION_RESULTS.md` | 122 | ผล calibration — A3b ตกเฉียดฉิว |
| `AMENDMENT_01_RULING.md` | 44 | คำตัดสินผู้ใช้: A3b อยู่ในงบ A2 |
| `P1_RERUN_AMENDMENT01.md` | 74 | P1 ตกซ้ำด้วยรูปแบบเดิม (S4V2) |
| `P1_CRITERION_OPTIONS.md` | 107 | 3 ทางเลือกเกณฑ์ พร้อมผลกระทบเชิงตัวเลข |
| `AMENDMENT_02_FAMILYWISE_CRITERION.md` | 102 | **เกณฑ์ปัจจุบัน** — Bonferroni z=2.9913 |
| `AMENDMENT_02_RESULTS.md` | 78 | **ผ่าน R1–R6 รวมข้อที่ต้องตก** |
| `MT5_RUNBOOK.md` | 165 | งานบนเครื่อง + พิสูจน์ไม่เทรดระดับบรรทัด |
| `MT5_ENV_REQUIREMENTS.md` | 80 | 7 ข้อกำหนด + ข้อห้ามแทนที่ข้อมูล |
| `RESEARCH_FINDINGS.md` | 748 | **งานวิจัยเดิม ~47 configurations** อ่านก่อนเสนอ setup |
| `BACKTEST.md` | 250 | ระเบียบวิธี backtest |
| `ACCOUNT_SCALING.md` | 172 | ข้อจำกัดเงินทุนและ min lot |

### `research/pilot/` — engine + pilot (2,794 บรรทัด)

| ไฟล์ | บรรทัด | หน้าที่ |
|---|---|---|
| `core.py` | 562 | 18 setups, exit resolution, controls, สถิติ, `bonferroni_z` |
| `run.py` | 349 | orchestrator: P1 → P2/P4 → market → P5 · `--p1-only` กันไม่ให้อ่านราคา |
| `calibrate_control.py` | 248 | A1–A6 บน C1–C4 |
| `news.py` | 229 | news decision layer |
| `data.py` | 203 | โหลดข้อมูล + `load_csv` สำหรับไฟล์ MT5 (โยน error ถ้าไม่มี server offset) |
| `decide.py` | 175 | decision assembler |
| `regime.py` | 157 | Market Regime Score |
| `p1_diagnosis.py` | 146 | 3 การตรวจที่ชี้สาเหตุ P1 ตก |
| `synth.py` | 60 | C1/C2/C3 generators |
| `test_news.py` / `test_regime.py` / `test_decide.py` | 496 | 76 tests |
| `test_news_mutation.py` | 112 | ฉีดข้อบกพร่อง 6 แบบ คืนไฟล์ตรวจด้วย sha256 |
| `run_engine_tests.sh` | 17 | รันทั้งหมดคำสั่งเดียว |

### `tests/` — ชุดทดสอบฝั่ง MQL5 (1,129 บรรทัด)

คอมไพล์ **production source จริง** ด้วย g++ ผ่าน MQL5 shim — ไม่ใช่โค้ดเลียนแบบ

| ไฟล์ | หน้าที่ |
|---|---|
| `mql5_shim.h` | จำลอง MQL5 runtime (FileWrite ไม่ escape เหมือนของจริง) |
| `extract_source.py` | ดึงโค้ด production คำต่อคำ fail ถ้า anchor เลื่อน |
| `test_system.cpp` | 25 tests |
| `mutation_check.py` | 6 mutations |
| `run_all.sh` | รันทั้งหมด |

### `tools/`

| ไฟล์ | หน้าที่ |
|---|---|
| **`mt5_export_all.py`** | **คำสั่งเดียวจบ** — หา symbol, วัด offset, ดึง M1+M5, เขียนรายงาน |
| `export_mt5_data.py` | ตัวเดิม ทีละ timeframe |
| `capital_check.py` | จัดอันดับ symbol ตามความพอดีของ min lot |
| `check_schema_inert.py` | 9 static invariants |
| `make_ablation_sets.py` | สร้าง .set files |

### `MQL5/` — EA (3,290 บรรทัด) · `research/*.py` — งานวิจัยเดิม · `pine/` — TradingView

---

## 4. บันทึกการตัดสินใจ

| วันที่ | เรื่อง | ผล |
|---|---|---|
| 2026-09-20 | ตีความ mandate | ผลลบระยะยาวเป็น **prior** ไม่ใช่ข้อพิสูจน์ว่าทำไม่ได้ใน regime ปัจจุบัน |
| 2026-09-20 | Amendment 01 | control เปลี่ยนเป็น circular time shift |
| 2026-09-20 | ruling A3b | อยู่ในงบ false positive ของ A2 |
| 2026-09-20 | **Amendment 02** | **เกณฑ์ = family-wise 95%, z=2.9913** |
| 2026-09-20 | ข้อมูล | **XAUUSD จาก MT5 โบรกเกอร์จริงเท่านั้น** ห้ามแทนด้วย GC/GLD/ข้อมูลจำลอง |

### สถานะพิเศษที่ต้องเคารพ

**UNINTERPRETABLE** — S3, S3V1, S3V2, S5, S5V1, S5V2, S2V1
ไม่ใช่ PASS ไม่ใช่ FAIL วัดด้วยเครื่องมือที่ภายหลังรู้ว่าไม่เหมาะกับกฎเหล่านั้น
**ห้ามอ้างว่าเป็นหลักฐานว่ามี edge และห้ามอ้างว่าเป็นหลักฐานว่าไม่มี**

---

## 5. สิ่งที่ถูกบล็อก

### Export ยังทำไม่ได้ — **นี่คืองานอันดับหนึ่ง**

`MetaTrader5` มี**เฉพาะ Windows wheel** (`pip install` → `from versions: none`
บน Linux) และเกาะเทอร์มินัลที่เปิดอยู่ผ่าน IPC ในเครื่อง

ต้องมี: Windows native (**ไม่ใช่ WSL**) · MT5 เปิดและ login · Python 3.8–3.12
64-bit · symbol อยู่ใน Market Watch · history โหลดแล้ว (M1 โบรกเกอร์ส่งแบบ lazy
— เปิดชาร์ต M1 กด Home เลื่อนย้อนจนหยุด)

```powershell
pip install MetaTrader5 pandas
python tools\mt5_export_all.py
```

ผลออกที่ `data\mt5_export_report.txt` — **ไม่ส่งออเดอร์** เรียกแค่
`copy_rates_range` กับ `symbol_info_tick`

### ยังขาด feed

| | ผลกระทบ |
|---|---|
| DXY / US yields | `regime.py` รายงาน `cross_asset_correlation` ว่าขาดเสมอ |
| Economic calendar | `news.py` ทำงานได้แต่ไม่มีข้อมูลป้อน (`MqlCalendarValue` มี actual/forecast/previous อยู่แล้ว โค้ด EA เดิมทิ้งไป) |
| Positioning / COT | `priced_in` และ `positioning` เป็น `NOT ASSESSED` ทุกเส้นทาง |

---

## 6. งานถัดไปตามลำดับ

1. **รัน export** (ข้อ 5) แล้วตรวจ: offset สมเหตุผลไหม · M1 ย้อนได้แค่ไหนเทียบ M5 · intraday gaps · **ตาราง spread รายชั่วโมง** ซึ่งจะชี้ขาดความขัดแย้งสามทางที่ค้างมานาน ($0.26 / $0.4824 / $0.7525)
2. **ทดสอบ `data.load_csv()` กับไฟล์จริง** — มันโยน error ถ้าไม่มี offset ถ้าพังคือ finding จริง
3. **calibrate ใหม่ทั้งชุดบน XAUUSD จริง** ใต้เกณฑ์ Amendment 02 รวมฉาก A3b
4. **ถ้า calibration ผ่าน → rerun P1 → ถ้า P1 ผ่าน จึงอ่านราคา** ลำดับไม่เปลี่ยนเพราะข้อมูลดีขึ้น
5. งานคู่ขนาน: SpreadMonitor (`InpEnableTrading=false`) · C1–C7 compile

---

## 7. ข้อห้ามที่ยังมีผล

- **ห้ามส่งคำสั่งเงินจริง** — `decide.py` คืน `tradeable=False` ทุกเส้นทาง มี test เดินครบ 8 combination
- **ห้ามแทนข้อมูล** — GC=F / MGC=F / GLD / ข้อมูลจำลอง ไม่ใช่ตัวแทน XAUUSD
- **ห้ามอ้างว่า setup ใดมี edge** — ทุกตัวเลขวัดบนข้อมูลสังเคราะห์ที่ไม่มีข้อมูลอยู่เลย
- **ห้ามเปิด sealed holdout**
- **ห้ามเปิด Setup B/C เพราะโค้ดมีอยู่** — ต้องผ่าน pipeline เดียวกับ candidate ใหม่
- **ห้ามเปิด PR** จนกว่าผู้ใช้ตรวจ export เสร็จ
- **ห้ามเปลี่ยนเกณฑ์เองหลังเห็นผล** — ทุกการเปลี่ยนต้องเป็น amendment ที่ commit แยกก่อนรัน

---

## 8. ตรวจสอบทุกอย่างด้วยคำสั่งเดียว

```bash
./research/pilot/run_engine_tests.sh    # 76 tests + 6 mutations
./tests/run_all.sh                      # 9 invariants + 25 tests + 6 mutations
```

ต้องได้: `passed 30/20/26, failed 0` · `6/6 caught; tree clean` ·
`9/9 invariants hold` · `passed 25, failed 0`

**ทั้งสองชุดไม่ต้องใช้ MT5 ไม่อ่านราคาตลาด และไม่ส่งออเดอร์**
