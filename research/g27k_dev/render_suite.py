#!/usr/bin/env python3
"""Render suite.json as one comparison page (every system, version and window).

Usage: python3 research/g27k_dev/render_suite.py --in research/g27k_dev/suite.json --out <html>
"""
import argparse
import json
import pathlib

SPLITS = {"PM": "2018-01-01", "POOL3": "2018-01-01", "ALL16": "2018-01-01", "ALL16>3": "2018-01-01"}
WIN_START = {"17y": "2009-09-01", "10y": "2016-10-01", "5y": "2021-10-01", "3y": "2023-10-01"}
SYS_INFO = {
    "A": ("G27K #1 · ทอง", "กฎ G27K อันดับ 1 เทรดทองตลาดเดียว"),
    "B": ("G27K #1 · ทอง เงิน BTC", "กฎเดียวกันบน 3 ตลาด (BTC ตั้งแต่ ส.ค. 2017)"),
    "B16": ("G27K #1 · 16 ตลาด", "กฎเดียวกันบนทั้ง 16 ตลาด 1% ต่อไม้ต่อตลาด"),
    "PM": ("ดีที่สุดรายตลาด", "แต่ละตลาดใช้รูปแบบที่ค้นจากตลาดตัวเอง"),
    "POOL3": ("รูปแบบเดียว · ค้นจาก 3 ตลาด", "รูปแบบเดียวที่ค้นจากทอง เงิน BTC รวมกัน"),
    "ALL16": ("รูปแบบเดียว · ค้นจาก 16 ตลาด", "เทรดทั้ง 16 ตลาด"),
    "ALL16>3": ("รูปแบบ 16 ตลาด → 3 ตลาด", "รูปแบบที่ค้นจาก 16 ตลาด แต่เทรดเฉพาะทอง เงิน BTC"),
    "W2": ("Walk-forward รอบ 2", "ระบบที่ผมตัดสินใจเองระหว่างทาง (ผลเดิม)"),
}
VER = {"normal": "ปกติ 1%", "half": "0.5%", "brake": "เบรก 25%", "monitor": "AI monitor", "macro": "มหภาค"}

PAGE = r"""<title>เทียบทุกระบบ G27K</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap">
<style>
/* layout: one column of cards; the matrix first, then risk vs return, then top-ups, Monte Carlo and definitions */
:root{
  --bg:#f3f5f8; --panel:#ffffff; --panel2:#f6f8fb; --ink:#131923; --muted:#566273; --faint:#8792a2; --line:#e1e6ed; --grid:#eceff4;
  --accent:#1f5eff; --accent-ink:#ffffff; --pos:#0f8a50; --neg:#d0342c; --hl:#eaf0ff; --warn-bg:#fff6e8; --warn-ink:#6f3a00;
  --v-normal:#1f5eff; --v-half:#0e9f8a; --v-brake:#e8890c; --v-monitor:#8a4fff; --v-macro:#d6457a;
  --sans:"IBM Plex Sans Thai",system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.07);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0c1016; --panel:#141a23; --panel2:#10161e; --ink:#e6ebf2; --muted:#9ba7b7; --faint:#6e7a8a; --line:#253041; --grid:#1c2431;
  --accent:#6a95ff; --accent-ink:#0c1016; --pos:#36d07c; --neg:#ff6b5f; --hl:#1a2440; --warn-bg:#271d0f; --warn-ink:#f4c98f;
  --v-normal:#5b8cff; --v-half:#14a08b; --v-brake:#d07a1c; --v-monitor:#9466f5; --v-macro:#e0628f; --shadow:none; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0c1016; --panel:#141a23; --panel2:#10161e; --ink:#e6ebf2; --muted:#9ba7b7; --faint:#6e7a8a; --line:#253041; --grid:#1c2431;
  --accent:#6a95ff; --accent-ink:#0c1016; --pos:#36d07c; --neg:#ff6b5f; --hl:#1a2440; --warn-bg:#271d0f; --warn-ink:#f4c98f;
  --v-normal:#5b8cff; --v-half:#14a08b; --v-brake:#d07a1c; --v-monitor:#9466f5; --v-macro:#e0628f; --shadow:none; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.55;margin:0}
.wrap{max-width:1120px;margin:0 auto;padding:22px 16px 56px}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{font-size:26px;margin:4px 0 6px;text-wrap:balance}
h2{font-size:17px;margin:0 0 4px;text-wrap:balance}
.sub{margin:0;color:var(--muted);font-size:14px;max-width:72ch}
.top{display:flex;flex-wrap:wrap;gap:14px 24px;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.ctl{display:flex;flex-wrap:wrap;gap:8px}
.seg{display:inline-flex;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:3px;gap:2px;box-shadow:var(--shadow)}
.seg button{font:inherit;font-size:14px;border:0;background:transparent;color:var(--muted);padding:6px 11px;border-radius:7px;cursor:pointer;white-space:nowrap}
.seg button[aria-selected="true"]{background:var(--accent);color:var(--accent-ink);font-weight:600}
.seg button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:var(--shadow);margin-bottom:14px;min-width:0}
.hint{color:var(--muted);font-size:13.5px;margin:0 0 10px;max-width:80ch}
.tbl{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:7px 9px;border-bottom:1px solid var(--grid);text-align:left;white-space:nowrap}
th{font-size:12.5px;color:var(--muted);font-weight:600;background:var(--panel2)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.sys{white-space:normal;min-width:170px}
td.sys small{display:block;color:var(--faint);font-size:12px;line-height:1.35}
td.best{font-weight:700;background:var(--hl)}
.pos{color:var(--pos)} .neg{color:var(--neg)} .muted{color:var(--muted)} .faint{color:var(--faint)}
.is{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.04em;padding:0 5px;border-radius:5px;background:var(--warn-bg);color:var(--warn-ink);margin-left:4px;vertical-align:1px}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--muted);margin:2px 0 8px}
#scatter{position:relative}
#tip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:13px;box-shadow:var(--shadow);display:none;white-space:nowrap;z-index:2}
.defs{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.def{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel2);min-width:0}
.def b{display:block;margin-bottom:2px}
.def code{font-family:var(--mono);font-size:12px;color:var(--muted);overflow-wrap:anywhere}
ol.notes{margin:6px 0 0;padding-left:20px;max-width:85ch}
ol.notes li{margin:6px 0}
footer{color:var(--faint);font-size:12.5px;margin-top:18px}
@media (max-width:520px){td.sys{min-width:128px} h1{font-size:22px} th,td{padding:6px 6px} .seg button{padding:6px 9px;font-size:13.5px}}
</style>

<div class="wrap">
  <header class="top">
    <div>
      <div class="eyebrow">Backtest suite · G27K</div>
      <h1>ทุกระบบ ทุกเวอร์ชัน ทุกช่วงเวลา</h1>
      <p class="sub" id="sub"></p>
    </div>
    <div class="ctl">
      <div class="seg" role="tablist" id="winTabs" aria-label="ช่วงเวลา"></div>
      <div class="seg" role="tablist" id="metTabs" aria-label="ตัวเลข"></div>
    </div>
  </header>

  <section class="card">
    <h2 id="mxTitle"></h2>
    <p class="hint" id="mxHint"></p>
    <div class="tbl" id="matrix"></div>
  </section>

  <section class="card">
    <h2>ผลตอบแทนเทียบความเสี่ยง</h2>
    <p class="hint">แต่ละจุดคือหนึ่งระบบในหนึ่งเวอร์ชัน (ตัวอักษรข้างจุดคือรหัสระบบในตารางด้านบน) · ขวา = ติดลบหนักกว่า · บน = ผลตอบแทนสูงกว่า · ซ้ายบนคือดีที่สุด · แตะที่จุดเพื่อดูชื่อ</p>
    <div class="legend" id="legend"></div>
    <div id="scatter"></div>
  </section>

  <section class="card">
    <h2>เติมเงิน $100 ทุกเดือน</h2>
    <p class="hint" id="dcaHint"></p>
    <div class="tbl" id="dca"></div>
  </section>

  <section class="card">
    <h2>สุ่มอนาคต 10 ปี (Monte Carlo)</h2>
    <p class="hint">สุ่มต่อผลรายเดือนจากประวัติ 17 ปีของแต่ละระบบเป็นช่วงละ 6 เดือน 4,000 รอบ · ตัวเลขคือโอกาสที่พอร์ตจะร่วงเกิน 50% และการร่วงหนักสุดแบบกลางๆ (มัธยฐาน)</p>
    <div class="tbl" id="mc"></div>
  </section>

  <section class="card">
    <h2>นิยามระบบและเวอร์ชัน</h2>
    <div class="defs" id="defs"></div>
  </section>

  <section class="card">
    <h2>อ่านก่อนเชื่อตัวเลข</h2>
    <ol class="notes" id="notes"></ol>
  </section>
  <footer id="foot"></footer>
</div>

<script>
const D = /*DATA*/;
const WIN = [["17y","17 ปี"],["10y","10 ปี"],["5y","5 ปี"],["3y","3 ปี"]];
const MET = [["cagr","ผลตอบแทน/ปี"],["dd","ติดลบหนักสุด"],["mar","MAR"],["pf","Profit Factor"],["final","เงินสุดท้าย"],["n","จำนวนไม้"]];
const VERS = ["normal","half","brake","monitor","macro"];
const VCOL = {normal:"var(--v-normal)",half:"var(--v-half)",brake:"var(--v-brake)",monitor:"var(--v-monitor)",macro:"var(--v-macro)"};
const SHAPE = {normal:"circle",half:"square",brake:"triangle",monitor:"diamond",macro:"cross"};
let WINK = "17y", METK = "cagr";
try { const w = localStorage.getItem("suiteWin"); if (w) WINK = w; const m = localStorage.getItem("suiteMet"); if (m) METK = m; } catch (e) {}
const pct = (v, d = 1) => v == null ? "–" : (v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%";
const money = v => v == null ? "–" : "$" + Math.round(v).toLocaleString("en-US");
const fmt = (k, v, dep) => v == null ? "–" : k === "cagr" || k === "dd" ? pct(v) : k === "final" ? money(v * (dep || 100000)) : k === "n" ? Math.round(v).toLocaleString("en-US") : Number(v).toFixed(2);
const better = k => k === "dd" ? -1 : 1;
const isIS = (s, w) => D.meta.splits[s] && D.meta.win_start[w] < D.meta.splits[s];
const tag = (s, w) => isIS(s, w) ? '<span class="is" title="ช่วงนี้รวมข้อมูลที่ใช้ค้นรูปแบบ">IS</span>' : "";

function seg(id, items, cur, key, cb) {
  const el = document.getElementById(id);
  el.innerHTML = items.map(([k, t]) => `<button role="tab" data-k="${k}" aria-selected="${k === cur}">${t}</button>`).join("");
  el.onclick = e => { const b = e.target.closest("button"); if (!b) return; try { localStorage.setItem(key, b.dataset.k); } catch (x) {} cb(b.dataset.k); };
}

function systems() { return D.order.filter(s => D.systems[s]); }

function matrix() {
  const ml = MET.find(m => m[0] === METK)[1], wl = WIN.find(w => w[0] === WINK)[1];
  document.getElementById("mxTitle").textContent = `${ml} · ${wl}`;
  document.getElementById("mxHint").innerHTML = `ทุกช่องคือบัญชีเริ่มใหม่ $100,000 ตั้งแต่ต้นช่วง · ช่องเน้นคือเวอร์ชันที่ดีที่สุดของระบบนั้นในตัวเลขนี้ · <span class="is">IS</span> = ช่วงนี้มีข้อมูลที่ใช้ค้นรูปแบบปนอยู่ ตัวเลขจึงดีเกินจริง`;
  let h = `<table><thead><tr><th>ระบบ</th>${VERS.map(v => `<th class="n"><span class="sw" style="background:${VCOL[v]}"></span>${D.ver[v]}</th>`).join("")}</tr></thead><tbody>`;
  for (const s of systems()) {
    const row = VERS.map(v => D.systems[s][v] && D.systems[s][v][WINK] ? D.systems[s][v][WINK][METK] : null);
    const vals = row.filter(x => x != null);
    const best = vals.length ? (better(METK) > 0 ? Math.max(...vals) : Math.min(...vals)) : null;
    h += `<tr><td class="sys"><b>${D.info[s][0]}</b> <span class="faint">${D.short[s]}</span>${tag(s, WINK)}<small>${D.info[s][1]}</small></td>` +
      row.map(x => `<td class="n ${x != null && x === best && vals.length > 1 ? "best" : ""} ${METK === "cagr" && x != null ? (x < 0 ? "neg" : "") : ""}">${fmt(METK, x)}</td>`).join("") + `</tr>`;
  }
  const w2 = D.W2[WINK];
  const w2v = !w2 ? null : METK === "cagr" ? w2.cagr : METK === "dd" ? w2.equity_dd : METK === "mar" ? w2.cagr / w2.equity_dd : METK === "pf" ? w2.pf : METK === "final" ? w2.final / 100000 : METK === "n" ? w2.trades : null;
  h += `<tr><td class="sys"><b>${D.info.W2[0]}</b><small>${D.info.W2[1]} · มีเฉพาะช่วง 10 และ 5 ปี · มี monitor ในตัว</small></td><td class="n">${w2 ? fmt(METK, w2v) : "–"}</td><td class="n faint" colspan="4">ไม่มีเวอร์ชันอื่น</td></tr>`;
  document.getElementById("matrix").innerHTML = h + `</tbody></table>`;
}

function scatter() {
  const el = document.getElementById("scatter");
  document.getElementById("legend").innerHTML = VERS.map(v => `<span><span class="sw" style="background:${VCOL[v]}"></span>${D.ver[v]}</span>`).join("");
  const pts = [];
  for (const s of systems()) for (const v of VERS) { const r = D.systems[s][v] && D.systems[s][v][WINK]; if (r && r.cagr != null && r.dd != null) pts.push({s, v, x: r.dd, y: r.cagr}); }
  const W = el.clientWidth, H = W < 520 ? 300 : 380, L = 50, R = 14, T = 12, B = 34;
  const xmax = Math.max(0.1, ...pts.map(p => p.x)) * 1.05, ymin = Math.min(0, ...pts.map(p => p.y)), ymax = Math.max(0.05, ...pts.map(p => p.y)) * 1.08;
  const X = x => L + x / xmax * (W - L - R), Y = y => T + (ymax - y) / (ymax - ymin) * (H - T - B);
  const step = (a, n) => { const r = a / n, p = Math.pow(10, Math.floor(Math.log10(r))); return [1, 2, 2.5, 5, 10].map(m => m * p).find(m => m >= r); };
  const xs = step(xmax, 5), ys = step(ymax - ymin, 5);
  let s = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="ผลตอบแทนต่อปีเทียบการติดลบหนักสุด">`;
  for (let x = 0; x <= xmax + 1e-9; x += xs) s += `<line x1="${X(x)}" x2="${X(x)}" y1="${T}" y2="${H - B}" stroke="var(--grid)"/><text x="${X(x)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="var(--faint)">${Math.round(x * 100)}%</text>`;
  for (let y = Math.ceil(ymin / ys) * ys; y <= ymax + 1e-9; y += ys) s += `<line x1="${L}" x2="${W - R}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(y) + 4}" text-anchor="end" font-size="11.5" fill="var(--faint)">${Math.round(y * 100)}%</text>`;
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--faint)" stroke-dasharray="4 4"/>`;
  s += `<text x="${W - R}" y="${H - 4}" text-anchor="end" font-size="11.5" fill="var(--muted)">ติดลบหนักสุด →</text><text x="${L + 4}" y="${T + 10}" font-size="11.5" fill="var(--muted)">↑ ผลตอบแทน/ปี</text>`;
  pts.forEach((p, i) => {
    const cx = X(p.x), cy = Y(p.y), c = VCOL[p.v], sh = SHAPE[p.v];
    const mk = sh === "circle" ? `<circle cx="${cx}" cy="${cy}" r="5"` : sh === "square" ? `<rect x="${cx - 4.5}" y="${cy - 4.5}" width="9" height="9"` :
      sh === "triangle" ? `<path d="M${cx} ${cy - 6}L${cx + 5.5} ${cy + 4}L${cx - 5.5} ${cy + 4}Z"` : sh === "diamond" ? `<path d="M${cx} ${cy - 6}L${cx + 6} ${cy}L${cx} ${cy + 6}L${cx - 6} ${cy}Z"` :
      `<path d="M${cx - 5} ${cy - 5}L${cx + 5} ${cy + 5}M${cx + 5} ${cy - 5}L${cx - 5} ${cy + 5}" stroke-width="2.5"`;
    s += `${mk} fill="${sh === "cross" ? "none" : c}" stroke="${sh === "cross" ? c : "var(--panel)"}" ${sh === "cross" ? "" : 'stroke-width="1.5"'}/>`;
    s += `<text x="${cx + 8}" y="${cy + 4}" font-size="10.5" fill="var(--muted)">${D.short[p.s]}</text>`;
    s += `<circle cx="${cx}" cy="${cy}" r="11" fill="transparent" data-i="${i}" class="hit"/>`;
  });
  el.innerHTML = s + `</svg><div id="tip"></div>`;
  const tip = document.getElementById("tip");
  el.querySelectorAll(".hit").forEach(n => {
    const show = () => { const p = pts[+n.dataset.i]; tip.style.display = "block";
      tip.innerHTML = `<b>${D.info[p.s][0]}</b>${tag(p.s, WINK)}<br><span class="sw" style="background:${VCOL[p.v]}"></span>${D.ver[p.v]} · ${pct(p.y)}/ปี · ติดลบ ${pct(p.x)}`;
      const cx = +n.getAttribute("cx"), tw = tip.offsetWidth; tip.style.left = Math.min(Math.max(cx + 10, 0), W - tw) + "px"; tip.style.top = Math.max(+n.getAttribute("cy") - 50, 0) + "px"; };
    n.addEventListener("mouseenter", show); n.addEventListener("touchstart", show, {passive: true}); n.addEventListener("mouseleave", () => tip.style.display = "none");
  });
}

function dca() {
  const wl = WIN.find(w => w[0] === WINK)[1];
  const any = Object.values(D.dca)[0].normal[WINK];
  document.getElementById("dcaHint").innerHTML = `เริ่ม $100 แล้วเติม $100 ทุกต้นเดือน ช่วง ${wl} · ใส่เงินรวม <b>${any ? money(any.deposited) : "–"}</b> · ตัวเลขคือเงินสุดท้าย / ผลตอบแทนต่อปีแบบคิดตามเงินที่ใส่ (IRR) / ติดลบหนักสุดของหน่วยลงทุน`;
  let h = `<table><thead><tr><th>ระบบ</th>${["normal", "brake", "monitor"].map(v => `<th class="n"><span class="sw" style="background:${VCOL[v]}"></span>${D.ver[v]}</th>`).join("")}</tr></thead><tbody>`;
  for (const s of systems()) {
    h += `<tr><td class="sys"><b>${D.info[s][0]}</b>${tag(s, WINK)}</td>` + ["normal", "brake", "monitor"].map(v => {
      const r = D.dca[s] && D.dca[s][v] && D.dca[s][v][WINK];
      return r ? `<td class="n">${money(r.final)}<br><span class="muted">${pct(r.irr)} · ติดลบ ${pct(r.dd, 0)}</span></td>` : `<td class="n">–</td>`;
    }).join("") + `</tr>`;
  }
  document.getElementById("dca").innerHTML = h + `</tbody></table>`;
}

function mc() {
  const vs = ["normal", "half", "brake", "monitor"];
  let h = `<table><thead><tr><th>ระบบ</th>${vs.map(v => `<th class="n"><span class="sw" style="background:${VCOL[v]}"></span>${D.ver[v]}</th>`).join("")}</tr></thead><tbody>`;
  for (const s of systems()) {
    h += `<tr><td class="sys"><b>${D.info[s][0]}</b>${tag(s, "17y")}</td>` + vs.map(v => {
      const r = D.mc[s] && D.mc[s][v];
      return r ? `<td class="n"><b class="${r.p_dd50 >= 0.05 ? "neg" : ""}">${pct(r.p_dd50)}</b><br><span class="muted">มัธยฐาน ${pct(r.dd_median, 0)}</span></td>` : `<td class="n">–</td>`;
    }).join("") + `</tr>`;
  }
  document.getElementById("mc").innerHTML = h + `</tbody></table>`;
}

function defs() {
  const items = D.defs.map(([t, b]) => `<div class="def"><b>${t}</b>${b}</div>`).join("");
  document.getElementById("defs").innerHTML = items;
  document.getElementById("notes").innerHTML = D.notes.map(n => `<li>${n}</li>`).join("");
  document.getElementById("sub").innerHTML = D.meta.sub;
  document.getElementById("foot").innerHTML = D.meta.footer;
}

function render() {
  seg("winTabs", WIN, WINK, "suiteWin", k => { WINK = k; render(); });
  seg("metTabs", MET, METK, "suiteMet", k => { METK = k; render(); });
  matrix(); scatter(); dca(); mc();
}
let rt, lw = 0;
window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { const w = document.getElementById("scatter").clientWidth; if (w !== lw) { lw = w; scatter(); } }, 150); });
defs(); render(); lw = document.getElementById("scatter").clientWidth;
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = json.loads(pathlib.Path(a.inp).read_text())
    order = [s for s in ("A", "B", "B16", "PM", "POOL3", "ALL16", "ALL16>3") if s in r["systems"]]
    for s in order:                                   # final as a multiple of the starting balance
        for v in r["systems"][s].values():
            for w in v.values():
                w["mar"] = w["cagr"] / w["dd"] if w.get("dd") else None
    notes = r.get("notes", {})
    pat = lambda n: f"<code>{n['tf']} · ออก {n['exit']} · {' & '.join(n['names'])}</code>"
    defs = [["ปกติ 1%", "เสี่ยง 1% ของ balance ทุกไม้"], ["0.5%", "เสี่ยงครึ่งหนึ่ง 0.5% ทุกไม้"],
            ["เบรก 25%", "1% ปกติ · balance ต่ำกว่ายอดสูงสุด 25% → 0.5% · กลับ 1% เมื่อห่างยอดไม่เกิน 12.5%"],
            ["AI monitor", "1% × ชั้นป้องกันของ walk-forward รอบ 2: DD 15% → ×0.5, 25% → ×0.25 (กลับ ×1 ใต้ 7.5%) · ตลาดนั้นแพ้ติด 8 ไม้เฉลี่ยต่ำกว่า −0.3R → ×0.5 · ATR สูงกว่า 95% ของปีที่ผ่านมา → ×0.5 · ข่าว USD ระดับสูงภายใน −1 ถึง +2 ชม. → ×0.5 · ความเสี่ยงที่เปิดรวมเกิน 6% ไม่เข้า"],
            ["มหภาค", "1% × (1 + คะแนนมหภาครายสัปดาห์) ปรับให้เฉลี่ยเท่ากับ 1 · ใช้ได้เฉพาะทอง เงิน BTC · การทดสอบที่ลงทะเบียนไว้ไม่ผ่าน ใส่ไว้ให้ครบ"],
            ["G27K #1", "เข้าเมื่อแท่ง H4 ปิดเหนือ High 10 แท่ง · ไม่เข้าถ้ามีข่าว USD สำคัญใน 8 ชม. · SL 2×ATR20 · ออกเมื่อปิดต่ำกว่า Low 20 แท่ง · ซื้ออย่างเดียว"]]
    if "PM" in notes:
        defs.append(["ดีที่สุดรายตลาด", "".join(f"<div><b style='display:inline'>{m}</b> {pat(n)}</div>" for m, n in notes["PM"].items())])
    for k, t in (("POOL3", "รูปแบบเดียว · 3 ตลาด"), ("ALL16", "รูปแบบเดียว · 16 ตลาด")):
        if k in notes:
            defs.append([t, pat(notes[k])])
    data = dict(
        systems=r["systems"], dca=r["dca"], mc=r["mc"], W2=r.get("W2", {}), order=order,
        info={k: list(v) for k, v in SYS_INFO.items()}, ver=VER, defs=defs,
        short={"A": "A", "B": "B", "B16": "B16", "PM": "PM", "POOL3": "P3", "ALL16": "P16", "ALL16>3": "P16→3"},
        meta=dict(splits=SPLITS, win_start=WIN_START,
                  sub="16 ตลาด ข้อมูลรายชั่วโมงถึง 30 ก.ย. 2026 · บัญชีเริ่มใหม่ทุกช่วง · ต้นทุน spread + 1 bp และ swap จริงของโบรกเกอร์ · จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                  footer="สร้างจาก research/g27k_dev/suite.py และ render_suite.py · ledger: g27k_two_systems_phase1, g27k_b_1pct_brake, per_market_free_search, multi_market_pooled_search, macro_only_portfolio, g27k_macro_overlay, walkforward_controller_round2"),
        notes=["<b>กฎ G27K #1 ถูกเลือกจาก 27,648 แบบหลังเห็นผลปี 2021–2026</b> ช่วง 5 และ 3 ปีของระบบ A, B, B16 จึงดีเกินจริง · ช่วงก่อนปี 2021 ไม่ได้ใช้เลือก",
               "<b>รูปแบบที่ค้นหา (รายตลาด, 3 ตลาด, 16 ตลาด) ค้นจากข้อมูลก่อนปี 2018</b> (BTC ก่อนปี 2021 หรือ 2024) ตัวเลขที่ติด IS จึงรวมช่วงที่รูปแบบ \"รู้คำตอบ\" อยู่แล้ว · ดูช่วง 5 และ 3 ปีเพื่อดูผลที่ไม่เคยเห็น",
               "<b>BTC ใช้ราคา Binance ตั้งแต่ ส.ค. 2017</b> ระบบ B จึงต่างจากรายงานก่อนหน้า (ที่ BTC เริ่มปี 2021) และรวมการร่วงของ BTC ปี 2018 ด้วย",
               "<b>ติดลบหนักสุดในหน้านี้วัดจาก balance เมื่อปิดไม้</b> ตัวเลขแบบ equity (รวมไม้ที่ยังเปิด) จะลึกกว่าราว 3–5 จุด",
               "<b>ระบบ 16 ตลาดเสี่ยง 1% ต่อไม้ต่อตลาด</b> อาจเปิดพร้อมกันได้ถึง 16% · AI monitor จำกัดไว้ที่ 6%",
               "<b>Walk-forward รอบ 2 เป็นผลเดิม</b> บนข้อมูลชุดเก่า (BTC ตั้งแต่ปี 2021) เสี่ยงฐาน 0.5% และมีชั้นป้องกันในตัว จึงไม่มีเวอร์ชันอื่นให้เทียบ",
               "<b>สิ่งที่ยังไม่ได้จำลอง:</b> margin, stop-out, lot ขั้นต่ำ, slippage เกิน 1 bp"])
    html = PAGE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False, default=float))
    pathlib.Path(a.out).write_text(html, encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    main()
