# งานสำหรับ session ที่ต่อ MT5 (บัญชี Demo บนเครื่องผู้ใช้)

จาก session วิจัย 5 ต.ค. 2026 · อ่าน `HANDOFF.md` ในโฟลเดอร์เดียวกันก่อน
**ทุกงานด้านล่างไม่ต้องส่งคำสั่งซื้อขาย** อ่านข้อมูลอย่างเดียว ยกเว้นงาน 4 ที่รันใน Strategy Tester
ข้อจำกัดใน `data/DEMO_ORDER_PERMISSION.md` ยังใช้ตามเดิม

ให้เขียนผลไว้ที่ `research/g27k_dev/handoff/mt5/` บน branch ของคุณ แล้ว push และบอกผู้ใช้ชื่อ branch
ใช้รูปแบบ CSV ธรรมดา และระบุเวลาเป็น UTC

---

## งาน 1 · ตรวจว่าบัญชี Cent มีตลาดอะไรเทรดได้จริง (สำคัญที่สุด)

ขัดกันอยู่: เอกสารของคุณ (`docs/G27K_EA_STATUS_2026-10-03.md`) บอกว่า Cent ไม่มี ETH แต่ภาพหน้าจอ Quotes จากแอปของผู้ใช้วันที่ 5 ต.ค. มี **ETHUSDc** (ราคา 2704.01 / 2705.01, spread 100 จุด)

สำหรับ XAUUSDc XAGUSDc BTCUSDc **ETHUSDc** USDJPYc บันทึกค่าต่อไปนี้:
- `trade_mode` (4 = เทรดได้เต็ม)
- contract size
- lot ต่ำสุด / ขั้น / สูงสุด
- margin mode / leverage ที่ใช้จริง
- swap long/short
- วัน swap ×3

วิธีทำ:
- ถ้าผู้ใช้อนุญาตให้ล็อกอินบัญชีจริง `184136077` แบบอ่านอย่างเดียว ให้ใช้ `SymbolInfo*`
- ถ้าไม่ ให้ขอให้ผู้ใช้ส่งภาพหน้าจอ Specification ของ ETHUSDc ในแอป

ผล: `mt5/cent_symbols.csv`

## งาน 2 · spread จริงทุกชั่วโมง

ต้นทุนคือความเสี่ยงหลักของไม้ M30 (ได้เปรียบแค่ราว +0.16R ต่อไม้) โมเดลใช้ spread ต่อรอบ = max(2 bp, spread กลาง + 1 bp)

ขอบเขต:
- **ตลาด:** XAUUSD XAGUSD BTCUSD ETHUSD USDJPY JP225 บนบัญชี demo
- **ข้อมูล:** tick ย้อนหลังมากที่สุดที่ `CopyTicksRange` ให้ได้ (อย่างน้อย 30 วัน)

ทำสองไฟล์:
- `mt5/spread_by_hour.csv`
  - คอลัมน์: `symbol, hour_utc, weekday, n_ticks, spread_median, spread_p90, mid_median, spread_bp_median`
  - `spread_bp = (ask − bid) / mid × 10,000`
- `mt5/spread_daily.csv`
  - คอลัมน์: `symbol, date, spread_bp_median, spread_bp_p90`

ถ้าเครื่องเปิดบัญชี Cent ได้ ให้ทำซ้ำกับสัญลักษณ์ `…c` ด้วย เพราะ spread ของ Cent อาจต่างจาก Standard

## งาน 3 · margin ต่อ lot

ใช้ `OrderCalcMargin` ที่ราคาปัจจุบัน 1 lot ทั้งซื้อและขาย กับ 6 ตลาดบน demo (และ Cent ถ้าทำได้)
ผล: `mt5/margin.csv` คอลัมน์ `symbol, account, price, margin_1lot_buy, margin_1lot_sell, leverage_effective`

เหตุผล: BTCUSDc ไม่มีเลเวอเรจ ถ้าไม้ BTC ของ G27K-F ไม้ M30 และไม้ H1 เปิดซ้อนกัน อาจใช้ margin เกิน balance งานวิจัยต้องใช้ค่าจริงไปทำ simulation ที่คิด margin

## งาน 4 · EA ไม้ M30 และเทียบกับงานวิจัย (ทำหลังงาน 1–3)

กฎอยู่ใน `HANDOFF.md` ข้อ 3.2 ห้ามเปลี่ยนค่าใดๆ:
- **TF:** M30 · TF ใหญ่ D1
- **เข้า:** ปิดไม่เกิน 1 ATR14 จาก High/Low 55 แท่งก่อนหน้า + ATR14/mean(ATR14,100) ≥ 1.5 + D1 ทางเดียวกัน
  - เทรดสองทาง เข้าราคาเปิดแท่งถัดไป
- **SL/TP:** SL 2 × ATR20 · TP 2R
- **ออกตามเวลา:** ครบ 30 แท่งยังไม่ชน SL/TP ปิดที่ราคาเปิดแท่งที่ 31
- **ไม้:** ตลาดละ 1 ไม้

แล้วทดสอบดังนี้:
- **Strategy Tester:** 2023-01-01 → 2026-09-30, 1 minute OHLC (หรือ every tick ถ้าทำได้) กับ XAUUSD XAGUSD BTCUSD ETHUSD USDJPY
- **เทียบไม้:** เทียบกับ `trades_M30.csv.gz` (คอลัมน์ `market, direction, entry_time_utc, exit_time_utc, R_gross, R_spread, R_swap`) แบบเดียวกับ `compare_ea_trades.py` รายงาน:
  - % แท่งเข้าและแท่งออกที่ตรงกัน
  - R ก่อนต้นทุนรวมเทียบกัน
  - **ต้นทุนรวมใน tester เทียบกับ `R_spread + R_swap` ของงานวิจัย** (สำคัญ: ตัวนี้บอกว่าไม้ M30 รอดต้นทุนจริงไหม)
- **ผล:** `mt5/m30_ea_compare.json` + ไฟล์ log ไม้จาก tester

ข้อมูลราคาต่างแหล่งจะทำให้ไม่ตรง 100%:
- งานวิจัยใช้ Dukascopy สำหรับทองและเงิน, Binance สำหรับ BTC และ ETH, histdata สำหรับ USDJPY
- ทองและเงินควรตรงสูงสุด

## งาน 5 · ต้นทุนของ G27K ใน tester สูงกว่าโมเดล (งานค้างเดิมของคุณ)

ใช้ผลงาน 2 ดูว่าส่วนต่าง −43.7R เทียบ −27.1R (2023–26) มาจาก spread, swap หรือ commission
ถ้าเป็น spread ให้บอกว่าโมเดลควรใช้กี่ bp ต่อตลาด

---

ส่งกลับ: push ไฟล์ใน `mt5/` แล้วบอกผู้ใช้ว่า branch ไหน session วิจัยจะเอาไปใส่ในโมเดลต้นทุนและคำนวณทุกชุดใหม่
