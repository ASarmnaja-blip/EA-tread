#!/usr/bin/env python3
"""Ten-year continuous walk-forward page via render_walkforward.py.
Usage: python3 render_10y.py walkforward_10y.json out.html"""
import json
import pathlib
import subprocess
import sys
import tempfile

import render_round2 as R2

HERE = pathlib.Path(__file__).parent


def main():
    d = json.load(open(sys.argv[1]))
    c = d["controller"]
    brakes = [l for l in c["log"] if l["kind"] == "brake"]
    btxt = " · ".join(f"{l['t']}: {l['text']}" for l in brakes) or "ไม่มี"
    tab = (R2.HEAD + R2.row("กฎรอบ 2 (ผมคุมเอง)", c["metrics"]) + R2.row("กฎรอบ 1", d["round1_rules"]["metrics"])
           + R2.row("รูปแบบรอบ 2 ไม่ตัดสินใจ", d["no_decisions"]["metrics"]) + R2.row("G27K อันดับ 1", d["g27k_1"]["metrics"]))
    extra = f"""<section><h2>ภาพรวม 10 ปี ทุกรุ่น</h2><div class="scroll"><table>{tab}</table></div>
<p class="sub">บัญชีเดียวต่อเนื่อง ไม่เริ่มใหม่ปี 2021 · เบรก DD ของรอบ 2 ทำงาน: {btxt} · บัญชีอยู่ใต้ยอดสูงสุดนานสุด {c['metrics']['longest_underwater_days']:.0f} วัน
ช่วงปี 2017–2019 ทุกรุ่นติดลบ รวมถึง G27K อันดับ 1 ในปี 2018 (−18%)</p></section>"""
    data = dict(controller=c, no_decisions=d["no_decisions"], g27k_1=d["g27k_1"], config=d["config"],
                labels=dict(controller="ผมคุมเอง รอบ 2", no_decisions="รูปแบบรอบ 2 ไม่ตัดสินใจ"),
                title="Walk-forward 10 ปี", h1="Walk-forward รอบ 2 ต่อเนื่อง 10 ปี (ต.ค. 2016 – ก.ย. 2026)",
                round_name="ผล 10 ปี", ledger_id="walkforward_controller_round2", extra_html=extra)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    subprocess.run([sys.executable, str(HERE / "render_walkforward.py"), f.name, sys.argv[2]], check=True)


if __name__ == "__main__":
    main()
