#!/usr/bin/env python3
"""Render walkforward_round1.json as a Strategy-Tester-style page that also
shows every decision the controller made.

Usage: python3 render_walkforward.py walkforward_round1.json out.html
"""
import html
import json
import sys

SERIES = [("controller", "ผมคุมเอง (เดินหน้า)", "--s1"),
          ("no_decisions", "รูปแบบเดียวกัน ไม่ตัดสินใจ", "--s2"),
          ("g27k_1", "G27K อันดับ 1 (เลือกหลังเห็นผล)", "--s3")]


def e(x):
    return html.escape(str(x))


def pct(x, d=1):
    return "-" if x is None else f"{x * 100:+.{d}f}%"


def pct0(x, d=1):
    return "-" if x is None else f"{x * 100:.{d}f}%"


def usd(x):
    return "-" if x is None else f"${x:,.0f}"


def num(x, d=2):
    return "-" if x is None else f"{x:,.{d}f}"


def verdict(res):
    c, n, g = (res[k]["metrics"] for k in ("controller", "no_decisions", "g27k_1"))
    mc, mn, mg = c["mar"], n["mar"], g["mar"]
    if mc > mn and mc > mg:
        if mc <= 1.1 * max(mn, mg):
            return "same", "ดีกว่าเล็กน้อย (ภายใน 10%) นับว่าเท่าเดิม"
        return "better", "ดีกว่าทั้งสองแบบ"
    if mc >= 0.9 * mn or mc >= 0.9 * mg:
        return "same", "ใกล้เคียง (ภายใน 10% ของอย่างน้อยหนึ่งแบบ) แต่ไม่ชนะทั้งสอง"
    return "worse", "แย่กว่าทั้งสองแบบ"


ROWS = [
    ("กำไรสุทธิ", lambda m: usd(m["net"])),
    ("ยอดสุดท้าย (จาก $100,000)", lambda m: usd(m["final"])),
    ("ผลตอบแทนทบต้นต่อปี (CAGR)", lambda m: pct(m["cagr"])),
    ("Equity DD สูงสุด", lambda m: pct0(m["equity_dd"])),
    ("Balance DD สูงสุด", lambda m: pct0(m["balance_dd"])),
    ("MAR (CAGR ÷ Equity DD)", lambda m: num(m["mar"])),
    ("Profit Factor", lambda m: num(m["pf"])),
    ("จำนวนไม้", lambda m: f"{m['trades']:,}"),
    ("อัตราชนะ", lambda m: pct0(m["win_n"] / m["trades"])),
    ("R เฉลี่ยต่อไม้", lambda m: f"{m['avg_R']:+.3f}R"),
    ("R รวม (หน่วยความเสี่ยง)", lambda m: f"{m['total_R']:+.0f}R"),
    ("Sharpe รายปี (จากรายเดือน)", lambda m: num(m["sharpe_annual"])),
    ("Recovery factor", lambda m: num(m["recovery"])),
    ("แพ้ติดกันมากสุด", lambda m: f"{m['streaks']['max_losses']} ไม้"),
    ("อยู่ใต้ยอดสูงสุดนานสุด", lambda m: f"{m['longest_underwater_days']:.0f} วัน"),
    ("เดือนดีสุด / แย่สุด", lambda m: f"{pct(m['best_month'])} / {pct(m['worst_month'])}"),
    ("เดือนที่บวก", lambda m: pct0(m["pos_months"], 0)),
    ("ซื้อ / ขาย", lambda m: f"{m['long_n']} / {m['short_n']}"),
    ("ต้นทุน spread + swap", lambda m: f"{-(m['spread_R'] + m['swap_R']):+.0f}R"),
]

CSS = """
:root{
  /* layout: verdict first, then the three-way comparison, then the decisions that produced it */
  --bg:#f4f5f7; --panel:#ffffff; --ink:#15191f; --muted:#5b6470; --faint:#8a929d; --line:#e2e5ea; --grid:#eceef1;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --good:#1f8a4c; --warn:#b26a00; --bad:#c8352e; --chip:#eef1f5;
  --body:"IBM Plex Sans Thai",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#101318; --panel:#171b21; --ink:#e8ebef; --muted:#9aa3ae; --faint:#6f7884; --line:#2a3039; --grid:#20262e;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good:#4cc07f; --warn:#e3a33e; --bad:#ec6a62; --chip:#222831; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#101318; --panel:#171b21; --ink:#e8ebef; --muted:#9aa3ae; --faint:#6f7884; --line:#2a3039; --grid:#20262e;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good:#4cc07f; --warn:#e3a33e; --bad:#ec6a62; --chip:#222831; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.55}
.wrap{max-width:1080px;margin:0 auto;padding-inline:16px;padding-block:22px 48px;display:grid;gap:18px}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{font-size:25px;margin:2px 0 6px;line-height:1.25;text-wrap:balance}
h2{font-size:16px;margin:0 0 10px}
.sub{color:var(--muted);font-size:14px;max-width:75ch}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.verdict{display:flex;gap:14px;align-items:flex-start;border-left:5px solid var(--c);padding-left:14px}
.verdict b{font-size:20px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:500}
td.n,th.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.key{display:inline-flex;align-items:center;gap:6px}
.sw{width:12px;height:3px;border-radius:2px;background:var(--c);display:inline-block}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--muted);margin-bottom:6px}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px;
     box-shadow:0 4px 14px rgba(0,0,0,.12);min-width:190px}
.tip .r{display:flex;justify-content:space-between;gap:12px;font-family:var(--mono);font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:6px;font-size:12px;font-weight:600;background:var(--chip)}
.adopt{color:var(--good)} .retire{color:var(--bad)} .brake{color:var(--warn)} .refit{color:var(--faint)}
.log{max-height:520px;overflow:auto}
.log li{margin:3px 0}
ul{padding-left:18px;margin:6px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
footer{font-size:12px;color:var(--muted)}
"""

JS = r"""
const D = window.WF;
const S = [["controller","--s1"],["no_decisions","--s2"],["g27k_1","--s3"]];
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function draw(){
  const box = document.getElementById('eq'); const W = Math.max(320, box.clientWidth), H = 300;
  const m = {l:58,r:14,t:10,b:26};
  const all = S.map(([k])=>D[k].metrics.curve);
  const t0 = Math.min(...all.map(c=>c.t[0])), t1 = Math.max(...all.map(c=>c.t[c.t.length-1]));
  let lo = Infinity, hi = -Infinity;
  all.forEach(c=>c.eq.forEach(v=>{lo=Math.min(lo,v);hi=Math.max(hi,v)}));
  lo = Math.max(lo*0.9, 1); hi = hi*1.1;
  const X = t => m.l + (t-t0)/(t1-t0)*(W-m.l-m.r);
  const Y = v => m.t + (Math.log(hi)-Math.log(v))/(Math.log(hi)-Math.log(lo))*(H-m.t-m.b);
  const ticks = [50e3,75e3,100e3,150e3,200e3,300e3,500e3,750e3,1e6,1.5e6,2e6,3e6,5e6].filter(v=>v>=lo&&v<=hi);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="กราฟ equity ทั้งสามแบบ สเกล log">`;
  ticks.forEach(v=>{s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('--grid')}" stroke-width="1"/>`+
    `<text x="${m.l-6}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="${css('--muted')}">${v>=1e6?(v/1e6)+'M':(v/1e3)+'k'}</text>`});
  const y0 = new Date(t0*1000).getUTCFullYear(), y1 = new Date(t1*1000).getUTCFullYear();
  for(let y=y0+1;y<=y1;y++){const tt=Date.UTC(y,0,1)/1000; if(tt<t0||tt>t1)continue;
    s+=`<line x1="${X(tt)}" x2="${X(tt)}" y1="${m.t}" y2="${H-m.b}" stroke="${css('--grid')}"/><text x="${X(tt)}" y="${H-8}" text-anchor="middle" font-size="11" fill="${css('--muted')}">${y}</text>`}
  s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(100000)}" y2="${Y(100000)}" stroke="${css('--faint')}" stroke-dasharray="4 4"/>`;
  S.forEach(([k,c],i)=>{const cv=D[k].metrics.curve; let p='';
    cv.t.forEach((t,j)=>{p+=(j?'L':'M')+X(t).toFixed(1)+','+Y(cv.eq[j]).toFixed(1)});
    s+=`<path d="${p}" fill="none" stroke="${css(c)}" stroke-width="2" stroke-linejoin="round"/>`;
    const n=cv.t.length-1; s+=`<circle cx="${X(cv.t[n])}" cy="${Y(cv.eq[n])}" r="4" fill="${css(c)}" stroke="${css('--panel')}" stroke-width="2"/>`;});
  s+=`<line id="cross" x1="0" x2="0" y1="${m.t}" y2="${H-m.b}" stroke="${css('--muted')}" stroke-width="1" visibility="hidden"/></svg>`;
  box.innerHTML = s + '<div class="tip" id="tip" hidden></div>';
  const svg = box.querySelector('svg'), tip = document.getElementById('tip'), cross = document.getElementById('cross');
  svg.addEventListener('pointermove', ev=>{
    const r = svg.getBoundingClientRect(); const px = (ev.clientX-r.left)*W/r.width;
    if(px<m.l||px>W-m.r){tip.hidden=true;cross.setAttribute('visibility','hidden');return}
    const t = t0+(px-m.l)/(W-m.l-m.r)*(t1-t0);
    let h = `<div style="margin-bottom:4px;color:${css('--muted')}">${new Date(t*1000).toISOString().slice(0,10)}</div>`;
    S.forEach(([k,c])=>{const cv=D[k].metrics.curve; let j=0; while(j<cv.t.length-1&&cv.t[j+1]<=t)j++;
      h+=`<div class="r"><span class="key"><span class="sw" style="--c:var(${c})"></span>${D.names[k]}</span><span>$${Math.round(cv.eq[j]).toLocaleString()}</span></div>`});
    tip.innerHTML=h; tip.hidden=false; cross.setAttribute('x1',px); cross.setAttribute('x2',px); cross.setAttribute('visibility','visible');
    const bx = ev.clientX-r.left; tip.style.left = Math.min(bx+14, r.width-220)+'px'; tip.style.top='12px';
  });
  svg.addEventListener('pointerleave',()=>{tip.hidden=true;cross.setAttribute('visibility','hidden')});
}
draw(); let rz; addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(draw,120)});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
new MutationObserver(draw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
"""


def main():
    res = json.load(open(sys.argv[1]))
    names = {k: lab for k, lab, _ in SERIES}
    v, vtxt = verdict(res)
    col = {"better": "var(--good)", "same": "var(--warn)", "worse": "var(--bad)"}[v]
    word = {"better": "ดีกว่า", "same": "เท่าเดิม", "worse": "แย่กว่า"}[v]
    M = {k: res[k]["metrics"] for k, _, _ in SERIES}
    head = "".join(f'<th class="n"><span class="key"><span class="sw" style="--c:var({c})"></span>{e(lab)}</span></th>' for _, lab, c in SERIES)
    body = "".join(f"<tr><td>{e(lab)}</td>" + "".join(f'<td class="n">{f(M[k])}</td>' for k, _, _ in SERIES) + "</tr>"
                   for lab, f in ROWS)
    years = sorted({y["year"] for k in M for y in (M[k]["yearly"] or [])})
    yr = {k: {y["year"]: y for y in M[k]["yearly"]} for k in M}
    ytab = "<tr><th>ปี</th>" + "".join(f'<th class="n">{e(lab)}<br>ผลตอบแทน / DD</th>' for _, lab, _ in SERIES) + "</tr>" + "".join(
        f"<tr><td>{y}</td>" + "".join(
            f'<td class="n">{pct(yr[k][y]["ret"])} / {pct0(yr[k][y]["dd"])}</td>' if y in yr[k] else '<td class="n">-</td>'
            for k, _, _ in SERIES) + "</tr>" for y in years)
    C = res["controller"]
    pm = "".join(f"<tr><td>{e(r['mkt'])}</td><td class='n'>{r['n']}</td><td class='n'>{pct0(r['win'])}</td>"
                 f"<td class='n'>{usd(r['net'])}</td><td class='n'>{r['R']:+.1f}R</td><td class='n'>{num(r['pf'])}</td></tr>"
                 for r in M["controller"]["per_market"])
    pats = "".join(
        f"<tr><td><b>{e(p['id'])}</b></td><td>{e(p['desc'])}</td><td class='n'>{e(p['adopted'])}</td>"
        f"<td class='n'>{e(p['retired'] or 'ยังใช้')}</td><td>{e(p['why'] or '')}</td>"
        f"<td class='n'>{p['disc']['n']} / {p['disc']['R']:+.2f}R</td><td class='n'>{p['val']['n']} / {p['val']['R']:+.2f}R</td>"
        f"<td class='n'>{p['live_n']}</td><td class='n'>{p['live_R']:+.1f}R</td></tr>" for p in C["patterns"])
    log = "".join(f"<li><span class='n' style='font-family:var(--mono)'>{e(l['t'])}</span> "
                  f"<span class='{e(l['kind'])}'>{e(l['text'])}</span></li>" for l in C["log"])
    sk = C["skipped"]
    best = "".join(f"<tr><td>{e(t['mkt'])}</td><td class='n'>{e(t['t'])}</td><td class='n'>{e(t['t_exit'])}</td>"
                   f"<td class='n'>{t['R']:+.2f}R</td><td class='n'>{usd(t['pnl'])}</td></tr>" for t in M["controller"]["best_trades"][:5])
    worst = "".join(f"<tr><td>{e(t['mkt'])}</td><td class='n'>{e(t['t'])}</td><td class='n'>{e(t['t_exit'])}</td>"
                    f"<td class='n'>{t['R']:+.2f}R</td><td class='n'>{usd(t['pnl'])}</td></tr>" for t in M["controller"]["worst_trades"][:5])
    data = {k: {"metrics": {"curve": M[k]["curve"]}} for k in M}
    data["names"] = names
    cfg = res["config"]
    elig = " · ".join(f"{c['date'][:7]}: {c['eligible']}" for c in cfg["candidates"])
    out = f"""<title>Walk-forward รอบ 1</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header><div class="eyebrow">Strategy Tester · Walk-forward · ทอง เงิน BTC · H4 และ D1</div>
<h1>Walk-forward รอบ 1: ผมคุมเองโดยไม่รู้อนาคต</h1>
<p class="sub">เริ่ม {e(cfg['start'])} ด้วยเงิน $100,000 · ทุกต้นไตรมาสค้นรูปแบบใหม่จากข้อมูลก่อนวันนั้นเท่านั้น ({cfg['refits']} ครั้ง) แล้วตัดสินใจรับ ปลด และปรับความเสี่ยงตามกฎที่เขียนลง ledger ก่อนรัน · ต้นทุนเดียวกับรายงาน G27K (spread + 1bp ขั้นต่ำ 2bp และ swap จริง) · จำลองบนข้อมูลจริง ไม่ใช่ผลเทรดจริง</p></header>
<section><div class="verdict" style="--c:{col}"><div><b>ผลรอบ 1: {word}</b><div>{e(vtxt)} · วัดด้วย MAR (CAGR ÷ Equity DD) ตามเกณฑ์ที่ล็อกไว้: ผม {num(M['controller']['mar'])} · ไม่ตัดสินใจ {num(M['no_decisions']['mar'])} · G27K อันดับ 1 {num(M['g27k_1']['mar'])}</div></div></div></section>
<section><h2>เทียบสามแบบ ช่วงเดียวกัน</h2><div class="scroll"><table><tr><th></th>{head}</tr>{body}</table></div></section>
<section><h2>Equity (สเกล log)</h2>
<div class="legend">{''.join(f'<span class="key"><span class="sw" style="--c:var({c})"></span>{e(lab)}</span>' for _, lab, c in SERIES)}</div>
<div class="chart" id="eq"></div></section>
<section><h2>รายปี</h2><div class="scroll"><table>{ytab}</table></div></section>
<div class="grid2">
<section><h2>แยกตามตลาด (ผมคุมเอง)</h2><div class="scroll"><table><tr><th>ตลาด</th><th class="n">ไม้</th><th class="n">ชนะ</th><th class="n">กำไร</th><th class="n">R</th><th class="n">PF</th></tr>{pm}</table></div></section>
<section><h2>ตัวเฝ้าดูทำงานกี่ครั้ง</h2><ul>
<li>ข้ามเพราะข่าว USD ระดับสูง: {sk['news']} ไม้</li>
<li>ข้ามเพราะตลาดเดียวมีไม้เปิดครบ 2 ไม้: {sk['cap_market']} ไม้</li>
<li>ข้ามเพราะความเสี่ยงรวมเกิน 4%: {sk['cap_risk']} ไม้</li>
<li>เบรกจาก DD และการลดขนาดรายรูปแบบ: ดูบันทึกการตัดสินใจ</li></ul>
<p class="sub">รูปแบบที่ผ่านเกณฑ์ในแต่ละไตรมาส: {e(elig)}</p></section></div>
<section><h2>รูปแบบที่ผมเลือกใช้ ({len(C['patterns'])} รูปแบบ)</h2><div class="scroll"><table>
<tr><th>รหัส</th><th>เงื่อนไข</th><th class="n">รับเมื่อ</th><th class="n">ปลดเมื่อ</th><th>เหตุผลที่ปลด</th><th class="n">ช่วงค้น ไม้/R</th><th class="n">ช่วงตรวจ ไม้/R</th><th class="n">เทรดจริง</th><th class="n">R จริง</th></tr>{pats}</table></div></section>
<section><h2>บันทึกการตัดสินใจ</h2><ul class="log">{log}</ul></section>
<div class="grid2">
<section><h2>5 ไม้ที่ดีที่สุด</h2><div class="scroll"><table><tr><th>ตลาด</th><th class="n">เข้า</th><th class="n">ออก</th><th class="n">R</th><th class="n">กำไร</th></tr>{best}</table></div></section>
<section><h2>5 ไม้ที่แย่ที่สุด</h2><div class="scroll"><table><tr><th>ตลาด</th><th class="n">เข้า</th><th class="n">ออก</th><th class="n">R</th><th class="n">กำไร</th></tr>{worst}</table></div></section></div>
<section><h2>ข้อจำกัดที่ต้องรู้</h2><ul>
<li>ผมรู้อยู่แล้วว่าตลาดช่วงปี 2021–2026 เป็นอย่างไร จึงล็อกกฎทั้งหมดลง ledger ก่อนรัน และไม่แก้กฎหลังเห็นผลรอบนี้ แต่การออกแบบกฎก็ยังทำโดยคนที่รู้อนาคต ข้อนี้กำจัดไม่ได้ 100%</li>
<li>G27K อันดับ 1 ถูกเลือกจาก 27,648 แบบโดยเห็นผลช่วงนี้แล้ว จึงเป็นเพดานที่การเลือกล่วงหน้าทำได้ยากมาก ส่วนแบบที่ไม่ตัดสินใจใช้รูปแบบชุดเดียวกับของผม จึงวัดคุณค่าของการตัดสินใจได้ตรงที่สุด</li>
<li>BTC มีข้อมูลครบตั้งแต่ปี 2021 เท่านั้น การค้นช่วงแรกจึงอาศัยทองและเงินเป็นหลัก</li>
<li>ปฏิทินข่าวมีตั้งแต่ปี 2022 ตัวกรองข่าวจึงยังไม่ทำงานในไตรมาสแรก</li></ul></section>
<footer>สร้างจาก research/walkforward_controller.py · ledger id walkforward_controller_round1 · ตัวเลขทุกตัวคำนวณด้วยโค้ดรายงานของ G27K (report768.metrics)</footer>
</div>
<script>window.WF={json.dumps(data)};</script>
<script>{JS}</script>
"""
    open(sys.argv[2], "w").write(out)


if __name__ == "__main__":
    main()
