#!/usr/bin/env python3
"""Index page and RESULTS.md for the hand-off set (handoff/matrix.csv.gz):
every combo x account x level x (no DCA | DCA), with the report links.

Usage: python3 research/g27k_dev/handoff_index.py --out <html>
"""
import argparse
import json
import pathlib

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
LINKS = {"F": "https://claude.ai/artifact/EPXhTeqc4ZRZcAsekYtkYV", "M30": "https://claude.ai/artifact/EwBjJCd4mPaohWmWx7rFn9",
         "H1": "https://claude.ai/artifact/QUoiy55RHNpKBsTXHdS7wM", "F_M30": "https://claude.ai/artifact/MDNZVJuxNd6dHohPnobNYe",
         "F_H1": "https://claude.ai/artifact/5Z8ufdZbmAS5TGA3rghhrD", "M30_H1": "https://claude.ai/artifact/LsMB1ecD2EnwL2LHpth6Qk",
         "F_M30_H1": "https://claude.ai/artifact/1511ha2N3qb5fy714rNRNU"}
STATUS = {"F": "ใช้", "M30": "ใช้", "H1": "ผ่านเฉียด"}
ORDER = list(LINKS)


def money(v):
    a = abs(v)
    return ("−" if v < 0 else "") + (f"${a / 1e9:,.2f}B" if a >= 1e9 else f"${a / 1e6:,.1f}M" if a >= 1e6 else f"${a:,.0f}")


def results_md(m):
    out = ["# ผลทั้งชุด (handoff/matrix.csv.gz)", "",
           "2011-09-01 – 2026-09-30 · ไม่ DCA เริ่ม $100,000 · DCA เริ่ม 0 เติม $100,000 ทุกต้นเดือน 181 ครั้ง ($18.1M)",
           "ระดับ = ความเสี่ยงต่อไม้ของ G27K-F (ไม้แยก 0.5%) หรือของทุกไม้ถ้าชุดไม่มี G27K-F", ""]
    for dca in ("no", "yes"):
        out.append("## " + ("ไม่ DCA" if dca == "no" else "DCA $100,000/เดือน"))
        out.append("")
        if dca == "no":
            out.append("| ชุด | บัญชี | ระดับ | เงินสุดท้าย | ต่อปี | Equity DD | MAR | MAR 2011–17 | MAR 2018–26 | MAR ถ้าแย่ลง 0.10R | P(DD>50%) | ไม้ |")
            out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        else:
            out.append("| ชุด | บัญชี | ระดับ | เงินที่ใส่ | มูลค่าสุดท้าย | IRR | DD หน่วยลงทุน | ต่ำกว่าเงินที่ใส่มากสุด |")
            out.append("|---|---|---|---|---|---|---|---|")
        for _, r in m[m.dca == dca].iterrows():
            if dca == "no":
                out.append(f"| {r.books} | {r.account} | {r.level} | {money(r.final)} | {r.cagr:.1%} | {r.equity_dd:.1%} | {r.mar:.2f} | {r.mar_2011_17:+.2f} | "
                           f"{r.mar_2018_26:+.2f} | {r.stress_mar:.2f} | {r.p_dd50:.1%} | {int(r.trades):,} |")
            else:
                out.append(f"| {r.books} | {r.account} | {r.level} | {money(r.deposited)} | {money(r.final)} | {r.irr:.1%} | {r.unit_dd:.1%} | {r.gap_below_deposits:.0%} |")
        out.append("")
    return "\n".join(out)


def page(m):
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    base = tpl[tpl.index("<style>"):tpl.index("</style>") + 8]
    fonts = "".join(l for l in tpl.splitlines(True) if "fonts.googleapis" in l or "fonts.gstatic" in l)
    rows = []
    for _, r in m.iterrows():
        rows.append(dict(combo=r.combo, books=r.books, acct=r.account, level=r.level, dca=r.dca, final=r.final,
                         ret=r.cagr if r.dca == "no" else r.irr, dd=r.equity_dd if r.dca == "no" else r.unit_dd,
                         mar=None if r.dca == "yes" else r.mar, smar=None if r.dca == "yes" else r.stress_mar,
                         gap=None if r.dca == "no" else r.gap_below_deposits, trades=int(r.trades)))
    cards = "".join(f"<a class='rc' href='{LINKS[c]}'><b>{m[m.combo == c].books.iloc[0]}</b><span>"
                    + " · ".join(f"{b}: {STATUS[b]}" for b in c.split("_")) + "</span></a>" for c in ORDER)
    js = """
const R = __ROWS__;
let f = {dca: "no", level: "1% + เบรก 25%", acct: "all"};
const money = v => v >= 1e9 ? "$" + (v / 1e9).toFixed(2) + "B" : "$" + (v / 1e6).toFixed(1) + "M";
const pc = (v, d = 1) => v == null ? "–" : (v * 100).toFixed(d) + "%";
function render() {
  const rows = R.filter(r => r.dca === f.dca && (f.level === "all" || r.level === f.level) && (f.acct === "all" || r.acct === f.acct));
  const no = f.dca === "no";
  document.getElementById("hd").innerHTML = `<tr><th>ชุด</th><th>บัญชี</th><th>ระดับ</th><th class="n">${no ? "เงินสุดท้าย (เริ่ม $100k)" : "มูลค่าสุดท้าย (ใส่ $18.1M)"}</th>
    <th class="n">${no ? "ต่อปี" : "IRR"}</th><th class="n">${no ? "Equity DD" : "DD หน่วยลงทุน"}</th>` +
    (no ? `<th class="n">MAR</th><th class="n">MAR ถ้าแย่ลง 0.10R</th>` : `<th class="n">ต่ำกว่าเงินที่ใส่มากสุด</th>`) + `<th class="n">ไม้</th></tr>`;
  document.getElementById("bd").innerHTML = rows.map(r => `<tr><td><a href="${LINKS[r.combo]}">${r.books}</a></td><td>${r.acct}</td><td>${r.level}</td>
    <td class="n"><b>${money(r.final)}</b></td><td class="n">${pc(r.ret)}</td><td class="n">${pc(r.dd)}</td>` +
    (no ? `<td class="n">${r.mar.toFixed(2)}</td><td class="n ${r.smar < 0.5 ? "neg" : ""}">${r.smar.toFixed(2)}</td>` : `<td class="n">${pc(r.gap, 0)}</td>`) +
    `<td class="n">${r.trades.toLocaleString("en-US")}</td></tr>`).join("");
  document.querySelectorAll("[data-k]").forEach(b => b.setAttribute("aria-pressed", String(f[b.dataset.k] === b.dataset.v)));
}
document.querySelectorAll("[data-k]").forEach(b => b.addEventListener("click", () => { f[b.dataset.k] = b.dataset.v; render(); }));
render();
"""
    seg = lambda k, opts: "".join(f'<button type="button" class="chip" data-k="{k}" data-v="{v}">{t}</button>' for v, t in opts)
    css = ("<style>.wrapd{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:22px 40px}.wrapd h1{font-size:clamp(22px,3.5vw,30px);margin:4px 0 6px;text-wrap:balance}"
           ".eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}"
           ".rcs{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}.rc{display:flex;flex-direction:column;gap:4px;padding:12px 14px;border:1px solid var(--line);"
           "border-radius:12px;background:var(--panel);color:var(--ink);text-decoration:none}.rc span{color:var(--muted);font-size:13px}.rc:hover{border-color:var(--muted)}"
           ".bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:4px 0 10px}.bar span{color:var(--muted);font-size:13px;margin-right:2px}"
           ".chip{font:inherit;font-size:13px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}"
           ".chip[aria-pressed=true]{border-color:var(--ink);font-weight:600}table.cmp{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}"
           "table.cmp th,table.cmp td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}table.cmp .n{text-align:right}"
           "table.cmp a{color:var(--ink)}</style>")
    levels = [("1% + เบรก 25%", "1% + เบรก"), ("1%", "1%"), ("0.75%", "0.75%"), ("all", "ทุกระดับ")]
    body = (f"<title>G27K Handoff</title>{fonts}{base}{css}<main class='wrapd'><div class='eyebrow'>ชุดส่งต่อ · 5 ต.ค. 2026</div>"
            "<h1>G27K-F · M30 · H1 ทุกชุด × บัญชี × ความเสี่ยง × DCA</h1>"
            "<section class='card'><h2>รายงานแบบ G27K แยกตามชุดไม้</h2><div class='rcs'>" + cards + "</div>"
            "<p class='muted' style='margin:10px 0 0;font-size:13px'>แต่ละรายงานมี Cent และ Standard × 0.75% / 1% / 1% + เบรก 25% ทั้งแบบไม่เติมเงินและ DCA · ข้อมูลดิบอยู่ใน research/g27k_dev/handoff/</p></section>"
            "<section class='card'><h2>ตารางรวม</h2><div class='bar'><span>แบบ</span>" + seg("dca", [("no", "ไม่ DCA"), ("yes", "DCA $100k/เดือน")])
            + "<span style='margin-left:8px'>ระดับ</span>" + seg("level", levels) + "<span style='margin-left:8px'>บัญชี</span>" + seg("acct", [("all", "ทั้งสอง"), ("Cent", "Cent"), ("Standard", "Standard")])
            + "</div><div class='tbl'><table class='cmp'><thead id='hd'></thead><tbody id='bd'></tbody></table></div>"
            "<p class='muted' style='margin:8px 0 0;font-size:13px'>ระดับ = ความเสี่ยงต่อไม้ของ G27K-F (ไม้ M30/H1 0.5%) หรือของทุกไม้ถ้าชุดไม่มี G27K-F · ชุดที่ไม่มี G27K-F ให้ผล Cent = Standard เพราะไม้แยกไม่เทรด JP225 · "
            "MAR ถ้าแย่ลง 0.10R ต่ำกว่า 0.5 แสดงเป็นสีแดง (เปราะต่อต้นทุน)</p></section>"
            "<p class='muted' style='font-size:12.5px'>จำลองย้อนหลังบนข้อมูลจริง ไม่ใช่ผลเทรดจริง · กฎเลือกจากข้อมูลชุดเดียวกัน ตัวเลขดีเกินจริงบางส่วน · ไม่ใช่คำแนะนำการลงทุน</p></main>"
            "<script>const LINKS = " + json.dumps(LINKS) + ";" + js.replace("__ROWS__", json.dumps(rows, ensure_ascii=False)) + "</script>")
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = pd.read_csv(HERE / "handoff" / "matrix.csv.gz")
    m["o"] = m.combo.map(ORDER.index)
    m = m.sort_values(["o", "account", "dca"], kind="stable").drop(columns="o")
    pathlib.Path(a.out).write_text(page(m), encoding="utf-8")
    (HERE / "handoff" / "RESULTS.md").write_text(results_md(m), encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    main()
