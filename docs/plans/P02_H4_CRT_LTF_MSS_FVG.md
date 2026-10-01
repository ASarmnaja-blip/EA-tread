เขียน 1 ต.ค. 2026 ก่อนคำนวณตัวเลขใดๆ ของแผนนี้ · กติการ่วมตาม `P00_COMMON.md` · ที่มาของกฎ: `docs/VIDEO_SETUPS_PLAN.md`

# P02 H4 Sweep + 5m Shift + Target 4H High (CRT แบบ ICT, คลิป 1)
- HTF H4 (22:00 UTC anchor). ซื้อ: C1 = แท่ง k, C2 = k+1 มี low(C2) < low(C1), low(C1) < close(C2) < high(C1). ขายกลับด้าน.
- TF เล็ก: M5 สำหรับทอง / เงิน (หลัก; แบบรอง M15); M15 สำหรับตลาด MT5. ช่วงหา = แท่ง TF เล็กภายใน C3 (หลัก; แบบรอง C3–C4).
- MSS: แท่ง TF เล็ก j ปิด > swing high (fractal 2) ล่าสุดก่อนแท่งที่ทำ Low กวาด; ช่วงจาก Low กวาดถึง j มีแท่ง body ≥ 1.0 × ATR14(TF เล็ก).
- FVG: FVG ซื้อล่าสุดในช่วงนั้น (low[i] > high[i−2], i ≤ j). เข้า limit ที่กึ่งกลาง FVG ตั้งแต่ j+1 ถึงจบช่วงหา.
- SL = Low กวาด − 0.1 ATR; TP = High ของ C1; ข้ามถ้า TP ≤ limit หรือ limit ≤ SL; 1 ไม้ต่อ C2.
- ตัวเปรียบเทียบ: แท่งสุ่มในช่วง C3 ใดๆ.
