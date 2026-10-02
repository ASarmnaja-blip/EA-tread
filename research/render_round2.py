#!/usr/bin/env python3
"""Round-2 page: the main-window comparison through render_walkforward.py,
plus the round-1 vs round-2 progression and the independent 2016-2021 window.

Usage: python3 render_round2.py walkforward_round2.json out.html
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import render_walkforward as RW

HERE = pathlib.Path(__file__).parent


def row(name, m):
    return (f"<tr><td>{RW.e(name)}</td><td class='n'>{m['trades']:,}</td><td class='n'>{RW.usd(m['net'])}</td>"
            f"<td class='n'>{RW.pct(m['cagr'])}</td><td class='n'>{RW.pct0(m['equity_dd'])}</td>"
            f"<td class='n'>{RW.num(m['mar'])}</td><td class='n'>{RW.num(m['pf'])}</td></tr>")


HEAD = ("<tr><th>รุ่น</th><th class='n'>ไม้</th><th class='n'>กำไร</th><th class='n'>CAGR</th>"
        "<th class='n'>Equity DD</th><th class='n'>MAR</th><th class='n'>PF</th></tr>")


def main():
    d = json.load(open(sys.argv[1]))
    mn, ind = d["main"], d["independent"]
    prog = (HEAD + row("กฎรอบ 1", mn["round1_rules"]["metrics"]) + row("กฎรอบ 2", mn["round2"]["metrics"])
            + row("รูปแบบรอบ 2 ไม่ตัดสินใจ", mn["no_decisions"]["metrics"]) + row("G27K อันดับ 1", mn["g27k_1"]["metrics"]))
    indt = (HEAD + row("กฎรอบ 1", ind["round1_rules"]["metrics"]) + row("กฎรอบ 2", ind["round2"]["metrics"])
            + row("รูปแบบรอบ 2 ไม่ตัดสินใจ", ind["no_decisions"]["metrics"]))
    yrs = sorted({y["year"] for k in ("round1_rules", "round2", "no_decisions") for y in ind[k]["metrics"]["yearly"]})
    yy = {k: {y["year"]: y for y in ind[k]["metrics"]["yearly"]} for k in ("round1_rules", "round2", "no_decisions")}
    ytab = ("<tr><th>ปี</th><th class='n'>กฎรอบ 1</th><th class='n'>กฎรอบ 2</th><th class='n'>ไม่ตัดสินใจ</th></tr>"
            + "".join(f"<tr><td>{y}</td>" + "".join(
                f"<td class='n'>{RW.pct(yy[k][y]['ret'])}</td>" if y in yy[k] else "<td class='n'>-</td>"
                for k in ("round1_rules", "round2", "no_decisions")) + "</tr>" for y in yrs))
    npat = len(ind["round2"]["patterns"])
    neg = sum(1 for p in ind["round2"]["patterns"] if p["live_R"] < 0)
    st = mn["round2"]["skipped"]
    extra = f"""<section><h2>รอบ 1 → รอบ 2 ช่วงหลัก (ต.ค. 2021 – ก.ย. 2026)</h2><div class="scroll"><table>{prog}</table></div>
<p class="sub">กฎรอบ 2 ลด DD จาก 13.3% เหลือ 6.4% และ MAR ดีขึ้นจาก 1.26 เป็น 1.78 แต่ใช้ความเสี่ยงน้อยเกินไป สัญญาณรวม {st['signals']:,} ครั้ง ถูกข้าม {st['busy']:,} ครั้งเพราะมีไม้ทิศเดียวกันในตลาดนั้นเปิดอยู่แล้ว</p></section>
<section><h2>ช่วงทดสอบอิสระ ต.ค. 2016 – ก.ย. 2021 (รอบ 1 ไม่เคยแตะ)</h2><div class="scroll"><table>{indt}</table></div>
<div class="scroll"><table>{ytab}</table></div>
<p class="sub">ทุกรุ่นขาดทุน ผมรับรูปแบบเข้ามา {npat} ตัวแบบไม่รู้อนาคต ติดลบในการเทรดจริง {neg} ตัว ช่วงนี้ทองและเงินเป็นกรอบแคบเกือบตลอด (2017–2019) รูปแบบเบรคที่หาเจอจากอดีตจึงไม่ทำงาน ข้อได้เปรียบที่เห็นในรอบ 1 (หลายรูปแบบยืนยัน, ไม้ใกล้ข่าว) จึงเป็นลักษณะของช่วงขาขึ้นแรง ไม่ใช่ข้อได้เปรียบถาวร</p></section>"""
    data = dict(controller=mn["round2"], no_decisions=mn["no_decisions"], g27k_1=mn["g27k_1"], config=mn["config"],
                labels=dict(controller="ผมคุมเอง รอบ 2", no_decisions="รูปแบบรอบ 2 ไม่ตัดสินใจ"),
                title="Walk-forward รอบ 2", h1="Walk-forward รอบ 2: แก้จากบทเรียนรอบ 1",
                round_name="ผลรอบ 2", ledger_id="walkforward_controller_round2", extra_html=extra)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    subprocess.run([sys.executable, str(HERE / "render_walkforward.py"), f.name, sys.argv[2]], check=True)


if __name__ == "__main__":
    main()
