#!/usr/bin/env python3
"""Table page for gold_moonshot.json (experiment only, never for live use).

Usage: python3 research/g27k_dev/report_moonshot.py --out <html>
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SIG_TH = {"every": "every · ทะลุ High/Low 20 แท่ง", "trend": "trend · ใกล้ High/Low 55 แท่ง + D1 ทางเดียวกัน",
          "m30rule": "กฎ M30 · trend + ATR14/ATR100 ≥ 1.5", "valid": "รูปแบบ M15 ที่พิสูจน์แล้ว · ช่วงบน 10% ของ 250 แท่ง + ATR ≥ 1.5 + D1"}
SIG_SHORT = {"every": "every", "trend": "trend", "m30rule": "กฎ M30", "valid": "พิสูจน์แล้ว"}

CSS = """
/* layout: one column, a short brief, then one wide sortable table in its own scroller */
:root{
  --bg:#f6f5f1; --surface:#ffffff; --fg:#1d2126; --muted:#5d6670; --line:#dcdad2;
  --accent:#8a6a12; --accent-soft:#f3ead2; --pos:#17663a; --neg:#a3281f; --pos-bg:#e5f2ea; --neg-bg:#f8e5e2;
  --f-display:"Chakra Petch","Sarabun",system-ui,sans-serif; --f-body:"Sarabun",system-ui,sans-serif; --f-num:"IBM Plex Mono",ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#121417; --surface:#1a1d21; --fg:#e6e3da; --muted:#9aa1a8; --line:#2e3238;
  --accent:#d9b25a; --accent-soft:#2c2617; --pos:#6fcf97; --neg:#f08a7e; --pos-bg:#16271d; --neg-bg:#2c1816; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#121417; --surface:#1a1d21; --fg:#e6e3da; --muted:#9aa1a8; --line:#2e3238;
  --accent:#d9b25a; --accent-soft:#2c2617; --pos:#6fcf97; --neg:#f08a7e; --pos-bg:#16271d; --neg-bg:#2c1816; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:15px;line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:28px 48px;display:grid;gap:22px}
.eyebrow{font:600 12px/1 var(--f-display);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
h1{font:700 clamp(24px,4vw,34px)/1.15 var(--f-display);margin:6px 0 0;text-wrap:balance}
.lede{max-width:68ch;color:var(--muted);margin:8px 0 0}
.warn{display:inline-block;margin-top:10px;padding:4px 10px;border-radius:999px;background:var(--neg-bg);color:var(--neg);font-weight:600;font-size:13px}
.setup{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.setup div{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}
.setup b{display:block;font:600 12px/1.2 var(--f-display);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.controls span{color:var(--muted);font-size:13px;margin-right:4px}
.chip{font:600 13px var(--f-body);padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--fg);cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent-soft);border-color:var(--accent);color:var(--fg)}
.chip:focus-visible,th button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;min-width:1040px;font-variant-numeric:tabular-nums}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:var(--surface);font:600 12px/1.3 var(--f-body);color:var(--muted);vertical-align:bottom}
th button{all:unset;cursor:pointer;display:inline-flex;gap:4px;align-items:center}
th[aria-sort] button::after{content:"↕";opacity:.35}
th[aria-sort="descending"] button::after{content:"↓";opacity:1;color:var(--accent)}
th[aria-sort="ascending"] button::after{content:"↑";opacity:1;color:var(--accent)}
th.grp{text-align:center;border-bottom:none;color:var(--fg);font-family:var(--f-display);letter-spacing:.04em}
th.grp.full,td.full{background:color-mix(in srgb,var(--line) 22%,transparent)}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
td.num{font-family:var(--f-num);font-size:13.5px}
td .pill{display:inline-block;min-width:64px;text-align:right;padding:2px 8px;border-radius:6px;font-weight:600}
.pos .pill{background:var(--pos-bg);color:var(--pos)} .neg .pill{background:var(--neg-bg);color:var(--neg)}
tr.top td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
tbody tr:hover td{background:color-mix(in srgb,var(--accent-soft) 60%,transparent)}
.sig{color:var(--muted);font-size:13px}
.notes{display:grid;gap:10px;max-width:78ch}
.notes h2{font:700 18px/1.3 var(--f-display);margin:0}
.notes ol{margin:0;padding-left:20px;display:grid;gap:8px}
.foot{color:var(--muted);font-size:12.5px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = r"""
const rows = __ROWS__;
const tb = document.getElementById("tb");
let tf = "all", key = "trades", dir = -1;
const fx = (v, d=1) => (v>0?"+":"") + v.toFixed(d);
const pct = v => (v*100).toFixed(1) + "%";
function render(){
  const list = rows.filter(r => tf === "all" || r.tf === tf).sort((a,b) => dir*((a[key]>b[key])-(a[key]<b[key])));
  const top = new Set([...rows].sort((a,b)=>b.trades-a.trades).slice(0,3).map(r=>r.id));
  tb.innerHTML = list.map(r => `<tr class="${top.has(r.id)?"top":""}">
    <td>${r.tf}</td><td><b>${r.sig}</b></td>
    <td class="num">${r.k}R</td><td class="num">+${Math.round(r.k*100)}%</td>
    <td class="num">${r.trades}</td><td class="num">${r.perDay.toFixed(1)}</td>
    <td class="num">${pct(r.win)}</td><td class="num">${pct(r.be)}</td>
    <td class="num">${r.blow}</td><td class="num">${r.dep.toFixed(0)}</td><td class="num">${r.wd.toFixed(1)}</td>
    <td class="num ${r.net>=0?"pos":"neg"}"><span class="pill">${fx(r.net)}</span></td>
    <td class="num">$${Math.round(r.net*100).toLocaleString("en-US")}</td>
    <td class="num">+${Math.round(r.best*100)}%</td>
    <td class="num full">${r.n15.toLocaleString("en-US")}</td><td class="num full">${pct(r.win15)}</td>
    <td class="num full ${r.pt15>=0?"pos":"neg"}"><span class="pill">${fx(r.pt15,2)}</span></td></tr>`).join("");
  document.querySelectorAll("th[data-k]").forEach(th => th.setAttribute("aria-sort", th.dataset.k===key ? (dir<0?"descending":"ascending") : "none"));
  document.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", String(c.dataset.tf===tf)));
}
document.querySelectorAll("th[data-k] button").forEach(b => b.addEventListener("click", () => {
  const k = b.parentElement.dataset.k; dir = (k===key) ? -dir : -1; key = k; render(); }));
document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => { tf = c.dataset.tf; render(); }));
render();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = json.loads((HERE / "gold_moonshot.json").read_text())
    rows = []
    for i, (k, v) in enumerate(d.items()):
        tf, sig, tp = k.split()
        kk = float(tp[:-1])
        l3, fy = v["last3m"], v["15y"]
        rows.append(dict(id=i, tf=tf, sig=SIG_SHORT[sig], sigLong=SIG_TH[sig], k=kk, trades=l3["trades"], perDay=l3["per_day"], win=l3["win"],
                         be=1 / (kk + 1), blow=l3["blowups"], dep=l3["deposited"], wd=l3["withdrawn"], net=l3["net"], best=l3["best_trade"],
                         n15=fy["trades"], win15=fy["win"], pt15=fy["net"] / max(fy["trades"], 1)))
    best = max(rows, key=lambda r: r["trades"])
    head = [("tf", "TF"), ("sig", "สัญญาณ"), ("k", "TP"), ("k", "กำไรต่อไม้ชนะ"), ("trades", "ไม้"), ("perDay", "ไม้/วัน"), ("win", "ชนะ"),
            ("be", "ชนะขั้นต่ำ<br>ที่เสมอตัว"), ("blow", "พอร์ตแตก"), ("dep", "เติมเงิน<br>(เท่าของต้น)"), ("wd", "ถอนได้<br>(เท่าของต้น)"),
            ("net", "สุทธิ<br>(เท่าของต้น)"), ("net", "สุทธิ<br>ถ้าต้น $100"), ("best", "ไม้ดีสุด"),
            ("n15", "ไม้"), ("win15", "ชนะ"), ("pt15", "สุทธิต่อไม้<br>(เท่าของต้น)")]
    ths = "".join(f'<th data-k="{k}" class="{"full" if j >= 14 else ""}"><button type="button">{lab}</button></th>' for j, (k, lab) in enumerate(head))
    legend = " · ".join(f"<b>{SIG_SHORT[k]}</b> = {SIG_TH[k].split(' · ', 1)[1]}" for k in SIG_SHORT)
    page = f"""<title>Gold Moonshot</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@600;700&family=IBM+Plex+Mono:wght@400;600&family=Sarabun:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
<main class="wrap">
  <header>
    <div class="eyebrow">XAUUSD · การทดลอง backtest</div>
    <h1>ทองเสี่ยง 100% ต่อไม้ · TP 5–10R · 3 เดือนล่าสุด</h1>
    <p class="lede">ทุกไม้เสี่ยงเงินทั้งพอร์ต ไม้ชนะได้ +500% ถึง +1,000% ของเงินต้นและถอนออกทันที ไม้แพ้คือพอร์ตแตกแล้วเติมเงินต้นใหม่
    ช่วงทดสอบ 1 ก.ค. – 30 ก.ย. 2026 · ไม้มากที่สุดคือ <b>{best['tf']} {best['sig']} TP {best['k']:g}R</b>: {best['trades']} ไม้ ({best['perDay']:.1f} ไม้/วัน)
    สุทธิ {best['net']:+.1f} เท่าของเงินต้น</p>
    <span class="warn">ไม่ใช้เทรดจริง · ผลส่วนใหญ่มาจากโชคในช่วงสั้น</span>
  </header>
  <section class="setup" aria-label="ตั้งค่า">
    <div><b>ความเสี่ยง</b>100% ของพอร์ตต่อไม้ SL 2 × ATR20 ของ TF นั้น</div>
    <div><b>ทำกำไร</b>TP 5R / 7.5R / 10R กำไรเกินเงินต้นถอนออกทันที</div>
    <div><b>พอร์ตแตก</b>เหลือต่ำกว่า 10% ของต้น แล้วเติมเงินต้นใหม่ทันที</div>
    <div><b>ต้นทุน</b>spread 2 bp ของราคาต่อรอบ + swap · เข้าราคาเปิดแท่งถัดไป · เดิน SL/TP บน M1</div>
  </section>
  <p class="sig" style="margin:0">สัญญาณ: {legend}</p>
  <div class="controls" role="group" aria-label="เลือก TF"><span>TF</span>
    <button class="chip" type="button" data-tf="all">ทั้งหมด</button>
    <button class="chip" type="button" data-tf="M5">M5</button>
    <button class="chip" type="button" data-tf="M15">M15</button>
    <span style="margin-left:auto">กดหัวตารางเพื่อเรียง · แถบซ้ายสีทอง = 3 ตัวที่ไม้มากที่สุด</span></div>
  <div class="tbl"><table>
    <thead><tr><th colspan="14" class="grp">3 เดือนล่าสุด · ก.ค.–ก.ย. 2026</th><th colspan="3" class="grp full">ตั้งค่าเดียวกัน 15 ปี · 2011–2026</th></tr>
    <tr>{ths}</tr></thead><tbody id="tb"></tbody></table></div>
  <section class="notes">
    <h2>อ่านตารางนี้อย่างไร</h2>
    <ol>
      <li><b>ชนะขั้นต่ำที่เสมอตัว</b> = 1 ÷ (TP + 1) ถ้าอัตราชนะสูงกว่านี้ สุทธิเป็นบวก TP 5R ต้องชนะเกิน 16.7% และ TP 10R ต้องชนะเกิน 9.1%</li>
      <li>สามเดือนเป็นตัวอย่างเล็ก ผลบวกมาจากไม้ชนะแค่ราว 15–40 ไม้ ถ้าชนะน้อยลงไม่กี่ไม้ ผลก็พลิกเป็นลบได้</li>
      <li>คอลัมน์ 15 ปีคือการตั้งค่าเดียวกันตลอด 15 ปี: ส่วนใหญ่ยังบวก แต่ได้ต่อไม้น้อยกว่าสามเดือนนี้มาก ทองช่วง ก.ค.–ก.ย. 2026 วิ่งเป็นเทรนด์แรงกว่าปกติ</li>
      <li>SL บน M5 แคบมาก การเสี่ยง 100% ต้องเปิดไม้หลายร้อยเท่าของเงินในพอร์ต ต้องใช้ leverage ราว 1:2000 และยังไม่ได้คิด slippage ตอนข่าว</li>
      <li>สมมติว่าโบรกมี negative balance protection ไม้ที่ gap เกิน SL จึงเสียได้มากสุดแค่เงินในพอร์ต</li>
    </ol>
  </section>
  <p class="foot">สร้างจาก research/g27k_dev/gold_moonshot.py · ข้อมูลทอง Dukascopy M1 (ราคากลาง bid/ask)</p>
</main>
<script>{JS.replace("__ROWS__", json.dumps(rows, ensure_ascii=False))}</script>
"""
    pathlib.Path(a.out).write_text(page, encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    main()
