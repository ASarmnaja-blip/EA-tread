# P16 ตามเทรนด์เทียบกับถือเฉยๆ บนข้อมูลย้อนหลังยาว (ข้อ ค)
เขียน 1 ต.ค. 2026 ก่อนคำนวณ · ที่มา: `docs/HL_TEST_AND_LONG_HISTORY_PREREG.md` ส่วนที่ 2, `docs/TREND_VS_HOLD_PREREG.md`
- ข้อมูล: FRED ราคาปิดรายวัน 14 ชุด (`data/macro/fred_long/manifest.json`): NIKKEI225, NASDAQCOM, DEXJPUS, DEXUSUK, DEXSZUS, DEXUSAL, DEXCAUS,
  DEXSDUS, DEXSFUS, DEXMXUS, DEXUSEU, DCOILWTICO, DCOILBRENTEU, DHHNGSP. ค่าว่างตัดทิ้ง; ราคา ≤ 0 (น้ำมันปี 2020) ตัดแท่งนั้น.
- มีแต่ราคาปิด: open = ปิดวันก่อน, high = max(open, close), low = min(open, close). ต้นทุน 2 bp (ค่าเงิน, ดัชนี), 3 bp (น้ำมัน, ก๊าซ). ไม่มี swap / carry.
- ระบบ S1 / S2 / Chandelier ทั้งซื้ออย่างเดียวและ Long+Short, 1 ไม้ต่อตลาด, เสี่ยง 1 % ต่อไม้.
- ทดสอบ 1: จังหวะเข้าเทียบการวางไม้เดิมแบบสุ่ม 2,000 รอบ; ทดสอบ 2: ถือเฉยๆ ที่ปรับเลเวอเรจให้ DD เท่ากัน (รายตลาดและพอร์ตเท่าๆ กัน);
  ทดสอบ 3: ทุกช่วงที่ร่วง ≥ 30 % จากยอด; รายงานรายทศวรรษด้วย.
- เกณฑ์ผ่านตาม `docs/TREND_VS_HOLD_PREREG.md`.
