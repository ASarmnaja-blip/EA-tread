#!/usr/bin/env python3
"""G27K #1 on four market sets, 15 years, in the G27K Strategy-Tester layout
(ledger g27k_usdjpy_and_five_markets):

  S5   gold, silver, BTC, JP225, USDJPY
  S4U  gold, silver, BTC, USDJPY   (every market exists on Exness Standard Cent)
  S4J  gold, silver, BTC, JP225    (the previous final system)
  S3   gold, silver, BTC

A comparison section on top (monthly balance of all four, key numbers, years),
then the full report with system tabs, a version switch (brake 25%, normal 1%,
AI monitor) and market tabs.

Usage: python3 research/g27k_dev/report_five.py --root <data-snapshot checkout> --out <html>
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, END = "2011-09-01", "2026-10-01"      # JP225 history starts Sep 2011
M3 = ("XAUUSD", "XAGUSD", "BTCUSD")
SETS = {"S5": M3 + ("JP225", "USDJPY"), "S4U": M3 + ("USDJPY",), "S4J": M3 + ("JP225",), "S3": M3}
PORT = {"S5": "P5", "S4U": "P4U", "S4J": "P4J", "S3": "P3"}
NAME = {"S5": "5 ตลาด", "S4U": "4 ตลาด +USDJPY", "S4J": "4 ตลาด +JP225", "S3": "3 ตลาด"}
CENT = {"S5": False, "S4U": True, "S4J": False, "S3": True}
VERS = {"brake": "เบรก 25%", "normal": "ปกติ 1%", "monitor": "AI monitor"}
TH_M = RJ.TH_M

# categorical slots 1-4 of the dataviz reference palette, validated on this template's
# surfaces (#ffffff light, #141a23 dark); slots 3-4 sit under 3:1 in light mode, so the
# lines carry direct end labels and every value is in the tables
CSS = """<style>
:root{--c1:#2a78d6;--c2:#eb6834;--c3:#1baf7a;--c4:#eda100}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500}}
:root[data-theme="dark"]{--c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500}
.cmp-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:14px;margin-bottom:14px}
.cmp-grid .card{margin-bottom:0}
@media (max-width:900px){.cmp-grid{grid-template-columns:minmax(0,1fr)}}
.cmp td.win{font-weight:700}
.cmp td,.cmp th{white-space:normal}
@media (max-width:520px){.cmp{font-size:12.5px}.cmp td,.cmp th{padding:6px 4px}}
.sw{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
#cmpChart{position:relative}
#cmpTip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:13px;box-shadow:var(--shadow);display:none;white-space:nowrap;z-index:2}
.cmp-sum{margin:0 0 10px;font-size:14.5px}
.cmp-sum li{margin:3px 0}
</style>"""

SCRIPT = """<script>
(function(){
const C = __DATA__, el = document.getElementById("cmpChart");
const ts = s => Date.parse(s + "T00:00:00Z"), nf = new Intl.NumberFormat("en-US", {maximumFractionDigits: 0});
const short = v => v >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : "$" + Math.round(v / 1e3) + "k";
const tick = v => v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";
function draw(){
  const W = el.clientWidth, narrow = W < 560, H = narrow ? 250 : 320, L = 50, R = narrow ? 14 : 132, T = 12, B = 26;
  const x0 = ts(C.pts[0].x), x1 = ts(C.pts[C.pts.length - 1].x);
  const all = C.pts.flatMap(p => C.keys.map(k => p[k])), lo = Math.log(Math.min(...all) * 0.9), hi = Math.log(Math.max(...all) * 1.08);
  const X = t => L + (t - x0) / (x1 - x0) * (W - L - R), Y = v => T + (hi - Math.log(v)) / (hi - lo) * (H - T - B);
  const ticks = [5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7].filter(v => Math.log(v) > lo && Math.log(v) < hi);
  const ya = new Date(x0).getUTCFullYear() + 1, yb = new Date(x1).getUTCFullYear(), stp = Math.max(1, Math.ceil((yb - ya + 1) / (narrow ? 5 : 8)));
  const yearsT = []; for (let y = ya; y <= yb; y += stp) yearsT.push(y);
  const line = k => C.pts.map((p, i) => (i ? "L" : "M") + X(ts(p.x)).toFixed(1) + "," + Y(p[k]).toFixed(1)).join("");
  const last = C.pts[C.pts.length - 1];
  let s = `<svg class="svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Balance สิ้นเดือนของ 4 ชุดตลาด สเกล log">`;
  ticks.forEach(v => s += `<line class="gl" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="11.5" fill="var(--faint)">${tick(v)}</text>`);
  yearsT.forEach(y => { const x = X(ts(y + "-01-01")); s += `<text x="${x}" y="${H - 8}" text-anchor="middle" font-size="11.5" fill="var(--faint)">${y}</text>`; });
  C.keys.slice().reverse().forEach((k, j) => s += `<path d="${line(k)}" fill="none" stroke="var(--c${C.keys.length - j})" stroke-width="2" stroke-linejoin="round"/>`);
  if (!narrow) {
    const ly = C.keys.map((k, i) => [Y(last[k]), C.names[i], i + 1, last[k]]).sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < ly.length; i++) if (ly[i][0] - ly[i - 1][0] < 34) ly[i][0] = ly[i - 1][0] + 34;
    const over = ly[ly.length - 1][0] - (H - B - 4); if (over > 0) ly.forEach(l => l[0] -= over);
    ly.forEach(l => { l[0] = Math.max(l[0], T + 12); });
    ly.forEach(([y, t, c, v]) => s += `<circle cx="${X(ts(last.x))}" cy="${Y(v)}" r="4" fill="var(--c${c})" stroke="var(--panel)" stroke-width="2"/><text x="${X(ts(last.x)) + 9}" y="${y - 2}" font-size="12" fill="var(--ink)" font-weight="600">${t}</text><text x="${X(ts(last.x)) + 9}" y="${y + 12}" font-size="11.5" fill="var(--muted)">${short(v)}</text>`);
  }
  s += `<line id="cmpX" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--faint)" stroke-width="1" style="display:none"/>`;
  C.keys.forEach((k, i) => s += `<circle class="cmpDot" data-k="${k}" r="4" fill="var(--c${i + 1})" stroke="var(--panel)" stroke-width="2" style="display:none"/>`);
  s += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" id="cmpHit"/></svg>`;
  el.innerHTML = s + `<div id="cmpTip"></div>`;
  const tp = document.getElementById("cmpTip"), cx = document.getElementById("cmpX"), dots = [...el.querySelectorAll(".cmpDot")];
  const move = e => {
    const r = el.getBoundingClientRect(), px = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
    let best = C.pts[0], bd = 1e9; C.pts.forEach(p => { const d = Math.abs(X(ts(p.x)) - px); if (d < bd) { bd = d; best = p; } });
    const x = X(ts(best.x));
    cx.style.display = ""; cx.setAttribute("x1", x); cx.setAttribute("x2", x);
    dots.forEach(d => { d.style.display = ""; d.setAttribute("cx", x); d.setAttribute("cy", Y(best[d.dataset.k])); });
    tp.style.display = "block";
    tp.innerHTML = `<b>${best.lab}</b>` + C.keys.map((k, i) => `<br><span class="sw" style="background:var(--c${i + 1})"></span>${C.names[i]} $${nf.format(best[k])}`).join("");
    const tw = tp.offsetWidth; tp.style.left = Math.min(Math.max(x + 10, 0), W - tw) + "px"; tp.style.top = "8px";
  };
  const hide = () => { [cx, tp, ...dots].forEach(n => n.style.display = "none"); };
  const hit = document.getElementById("cmpHit");
  hit.addEventListener("mousemove", move); hit.addEventListener("touchstart", move, {passive: true}); hit.addEventListener("touchmove", move, {passive: true});
  hit.addEventListener("mouseleave", hide);
}
let w0 = 0; draw(); w0 = el.clientWidth;
window.addEventListener("resize", () => { if (el.clientWidth !== w0) { w0 = el.clientWidth; draw(); } });
})();
</script>"""


def compare(E, MC, maxopen, curves, corr):
    keys = list(SETS)
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    # (label, value per system, 1 = higher wins, -1 = lower wins, 0 = neither, formatter)
    rows = [("เงินสุดท้าย (เริ่ม $100,000)", lambda s: E[s]["final"], 1, lambda v: f"${v:,.0f}"),
            ("ผลตอบแทนทบต้นต่อปี", lambda s: E[s]["cagr"], 1, lambda v: f"{v:.1%}"),
            ("Equity DD สูงสุด", lambda s: E[s]["equity_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
            ("Balance DD สูงสุด", lambda s: E[s]["balance_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
            ("MAR (ต่อปี ÷ Equity DD)", lambda s: mar(E[s]), 1, lambda v: f"{v:.2f}"),
            ("Profit Factor", lambda s: E[s]["pf"], 1, lambda v: f"{v:.2f}"),
            ("ปีที่แย่สุด", lambda s: worst(E[s])["ret"], 1, lambda v: f"{v:+.0%}"),
            ("อยู่ใต้ยอดเดิมนานสุด (ปี)", lambda s: E[s]["longest_underwater_days"] / 365.25, -1, lambda v: f"{v:.1f}"),
            ("จำนวนไม้", lambda s: E[s]["trades"], 0, lambda v: f"{v:,}"),
            ("เปิดพร้อมกันสูงสุด (ไม้)", lambda s: maxopen[s], 0, lambda v: f"{v}"),
            ("สุ่ม 10 ปี: โอกาส DD เกิน 50%", lambda s: MC[s]["p_dd50"], -1, lambda v: f"{v:.1%}"),
            ("สุ่ม 10 ปี: DD มัธยฐาน", lambda s: MC[s]["dd_median"], -1, lambda v: f"{v:.0%}"),
            ("สุ่ม 10 ปี: ผลตอบแทนมัธยฐาน", lambda s: MC[s]["cagr_median"], 1, lambda v: f"{v:.1%}")]

    def tr(label, get, w, f):
        vals = {s: get(s) for s in keys}
        best = (max if w > 0 else min)(vals.values()) if w else None
        cells = "".join(f'<td class="n{" win" if w and f(v) == f(best) else ""}">{f(v)}</td>' for s, v in vals.items())
        return f"<tr><td>{label}</td>{cells}</tr>"

    head = "".join(f'<th class="n"><span class="sw" style="background:var(--c{i + 1})"></span>{NAME[s]}</th>' for i, s in enumerate(keys))
    cent = "".join(f'<td class="n">{"✓ ได้" if CENT[s] else "✗ ไม่มี JP225"}</td>' for s in keys)
    table = (f'<table class="cmp"><thead><tr><th></th>{head}</tr></thead><tbody>' + "".join(tr(*r) for r in rows)
             + f"<tr><td>เทรดในบัญชี Exness Cent ได้</td>{cent}</tr></tbody></table>"
             "<p class='muted small' style='margin:8px 0 0'>ตัวหนา = ดีที่สุดในข้อนั้น · เวอร์ชันเบรก 25% ทุกชุด · “สุ่ม 10 ปี” = Monte Carlo 4,000 รอบจากผลรายเดือน</p>")
    Y = {s: {y["year"]: y["ret"] for y in E[s]["yearly"]} for s in keys}
    years = sorted(set.intersection(*(set(Y[s]) for s in keys)))
    yt = (f'<table class="cmp"><thead><tr><th>ปี</th>{"".join(f"<th class=n>{NAME[s]}</th>" for s in keys)}</tr></thead><tbody>'
          + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {'pos' if Y[s][y] >= 0 else 'neg'}'>{Y[s][y]:+.0%}</td>" for s in keys) + "</tr>"
                    for y in years) + "</tbody></table>")
    e = {s: E[s] for s in keys}
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>5 ตลาด</b> ได้ผลตอบแทนสูงสุด {e['S5']['cagr']:.1%} ต่อปี (Equity DD {e['S5']['equity_dd']['relative_pct']:.0%}) "
               f"แต่ปีที่แย่สุดลึกกว่า ({worst(e['S5'])['ret']:+.0%} ปี {worst(e['S5'])['year']}) เปิดพร้อมกันได้ 5 ไม้ และ<b>ต้องใช้บัญชี Standard</b> เพราะบัญชี Cent ไม่มี JP225</li>"
               f"<li><b>4 ตลาด +USDJPY</b> ได้ {e['S4U']['cagr']:.1%} ต่อปี (Equity DD {e['S4U']['equity_dd']['relative_pct']:.0%}) "
               f"ใกล้เคียงหรือดีกว่า +JP225 ({e['S4J']['cagr']:.1%}, {e['S4J']['equity_dd']['relative_pct']:.0%}) และ<b>เป็นชุดเดียวที่ครบในบัญชี Cent</b> (BTC ต้องใช้ MT5)</li>"
               f"<li>ผลรายเดือนของตลาดที่เพิ่มแทบไม่ขยับตาม 3 ตลาดเดิม: USDJPY {corr['USDJPY']:+.2f} · JP225 {corr['JP225']:+.2f} · JP225 กับ USDJPY {corr['JP225~USDJPY']:+.2f}</li>"
               "<li><b>ทุกชุดแทบไม่ได้กำไรช่วงปี 2011–2018</b> ผลส่วนใหญ่มาจากปี 2019 เป็นต้นมา · USDJPY และ JP225 ถูกเลือกหลังเคยเห็นผลแล้ว ตัวเลขนี้จึงยืนยันอนาคตไม่ได้</li></ul>")
    pts = [dict(x=START, lab="เริ่ม " + START, **{s: float(W.DEPOSIT) for s in keys})]
    for d, vals in curves:
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {TH_M[d.month - 1]} {d.year}", **{s: float(v) for s, v in zip(keys, vals)}))
    data = json.dumps(dict(pts=pts, keys=keys, names=[NAME[s] for s in keys]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{NAME[s]}</span>' for i, s in enumerate(keys))
    html = (CSS + '<section class="card"><h2>เทียบ 4 ชุดตลาด · เบรก 25%</h2>' + summary +
            f'<div class="legend" style="margin-bottom:6px">{legend}<span class="muted">Balance สิ้นเดือน · สเกล log</span></div>'
            '<div id="cmpChart" class="chart"></div></section>'
            '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
            '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>')
    return html, SCRIPT.replace("__DATA__", data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    allm = SETS["S5"]
    H1 = {m: MMS.load(m, G) for m in allm}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(allm, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    systems = {s: [r for r in rows if r["mkt"] in mk] for s, mk in SETS.items()}
    RWF.UNIS.update({PORT[s]: list(mk) for s, mk in SETS.items()}, JP225=["JP225"], USDJPY=["USDJPY"])
    unis = {s: [PORT[s], *mk] for s, mk in SETS.items()}
    out, sized = {}, {}
    for s, rr in systems.items():
        for v in VERS:
            vr = RSD.sized(rr, v, news)
            sized[(s, v)] = vr
            for u in unis[s]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, 0.01, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
        print(f"  {s} done  {time.time() - t0:.0f}s", flush=True)

    frame = lambda rr: pd.DataFrame(dict(mkt=[r["mkt"] for r in rr], t=[r["t"] for r in rr], tx=[r["t_exit"] for r in rr],
                                         R=[r["R"] for r in rr], vp=[r["vp"] for r in rr], sc=[r["sc"] for r in rr]))
    MC, maxopen = {}, {}
    for s, rr in systems.items():
        _, eq, _ = SU.simulate(frame(rr), "brake", START, END, news=news)
        MC[s] = SU.monte_carlo(eq)
        ev = sorted([(r["t"], 1) for r in rr] + [(r["t_exit"], -1) for r in rr])
        cur = maxopen[s] = 0
        for _, k in ev:
            cur += k
            maxopen[s] = max(maxopen[s], cur)
    S, E = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    cur = {}
    for s in SETS:
        me, cur[s] = RJ.monthly(RWF.account_var(sized[(s, "brake")]), S, E)
    curves = [(d, [cur[s][i] for s in SETS]) for i, d in enumerate(me)]
    mon = lambda rs: pd.Series([r["R"] for r in rs], index=pd.to_datetime([r["t_exit"] for r in rs], unit="s")).resample("ME").sum()

    def cor(x, y):
        i = x.index.union(y.index)
        return float(np.corrcoef(x.reindex(i, fill_value=0), y.reindex(i, fill_value=0))[0, 1])
    base = mon(systems["S3"])
    mj, mu = mon([r for r in rows if r["mkt"] == "JP225"]), mon([r for r in rows if r["mkt"] == "USDJPY"])
    corr = {"JP225": cor(mj, base), "USDJPY": cor(mu, base), "JP225~USDJPY": cor(mj, mu)}
    E_ = {s: out[f"{s}~brake_{PORT[s]}"] for s in SETS}
    cmp_html, cmp_js = compare(E_, MC, maxopen, curves, corr)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้"]
    seen = "USDJPY และ JP225 เคยเห็นผลมาแล้วในการทดสอบ 16 ตลาด ตัวเลขช่วงนี้จึงยืนยันไม่ได้ว่าจะดีต่อ (ledger g27k_usdjpy_and_five_markets)"
    info = {
        "S5": dict(label="G27K #1 · 5 ตลาด (ทอง เงิน BTC JP225 USDJPY)", tab="5 ตลาด", rules=g_rules + ["ตลาด: ทอง เงิน BTC JP225 USDJPY · เปิดพร้อมกันได้สูงสุด 5 ไม้"],
                   notes=[f"<b>ต้องใช้บัญชี Exness Standard (USD)</b> เพราะบัญชี Standard Cent ไม่มี JP225 · ทั้ง 5 ตลาดต้องอยู่บัญชีเดียวกัน เบรก 25% จึงคิดจากยอดรวมได้ถูก",
                          f"<b>ความเสี่ยงรวมสูงสุด 5%</b> เมื่อเปิดครบ 5 ไม้พร้อมกัน · ปีที่แย่สุด {min(E_['S5']['yearly'], key=lambda y: y['ret'])['ret']:+.0%}",
                          seen]),
        "S4U": dict(label="G27K #1 · 4 ตลาด (ทอง เงิน BTC USDJPY)", tab="4 ตลาด +USDJPY", rules=g_rules + ["ตลาด: ทอง เงิน BTC USDJPY · เปิดพร้อมกันได้สูงสุด 4 ไม้"],
                    notes=["<b>ทุกตลาดมีในบัญชี Exness Standard Cent</b> (XAUUSDc XAGUSDc BTCUSDc USDJPYc) · BTCUSDc มีเฉพาะ MT5",
                           f"<b>USDJPY แทบไม่ขยับตาม 3 ตลาดเดิม</b> (correlation ผลรายเดือน {corr['USDJPY']:+.2f}) · swap ฝั่ง Buy ของ USDJPY ในข้อมูลโบรกที่ใช้คำนวณเป็น 0 ควรเช็คค่าจริงใน MT5",
                           seen]),
        "S4J": dict(label="G27K #1 · 4 ตลาด (ทอง เงิน BTC JP225)", tab="4 ตลาด +JP225", rules=g_rules + ["ตลาด: ทอง เงิน BTC JP225 · เปิดพร้อมกันได้สูงสุด 4 ไม้"],
                    notes=["ระบบสุดท้ายเดิมใน HANDOFF · <b>บัญชี Standard Cent ไม่มี JP225</b> ต้องใช้บัญชี Standard",
                           "swap ของ JP225 ในข้อมูลโบรกที่ใช้คำนวณเป็น 0 ควรเช็คค่าจริงใน MT5"]),
        "S3": dict(label="G27K #1 · 3 ตลาด (ทอง เงิน BTC)", tab="3 ตลาด", rules=g_rules,
                   notes=["ระบบเดิมก่อนเพิ่มตลาดที่ 4 · ช่วงนี้เริ่ม ก.ย. 2011 ให้ตรงกับข้อมูล JP225 จึงต่างจากรายงาน 17 ปีที่เริ่ม ก.ย. 2009"]),
    }
    for s in info:
        info[s].update(combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01, adds=False, tf="H4", risk_note=RSD.RISK_NOTE["brake"], risk_notes=RSD.RISK_NOTE)
    wf = {s: dict(patterns=[], pat_note="", pat_empty="กฎตายตัว G27K #1 กฎเดียว", log=[], log_note="",
                  log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า") for s in systems}
    last = E - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S.day} {TH_M[S.month - 1]} {S.year} – {last.day} {TH_M[last.month - 1]} {last.year}",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · JP225 และ USDJPY: Dukascopy H1 · BTC: Binance ตั้งแต่ ส.ค. 2017 · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>ตัวเลขทั้งหน้านี้คือบัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> (เดือนแรกที่มีข้อมูล JP225) จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap ของโบรกเกอร์",
                                     "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> ช่วงนั้นจึงดีเกินจริงทุกชุด",
                                     "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ตของระบบนั้น (เบรกดู DD ของทั้งพอร์ต)"],
                       footer="สร้างจาก research/g27k_dev/report_five.py · ledger: g27k_usdjpy_and_five_markets · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · คำนวณ 3 ต.ค. 2026")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    ulist = json.dumps(["P5", "P4U", "P4J", "P3", "XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY"])
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>G27K 5 ตลาด</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K 5 ตลาด"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "5 ตลาด และ 4 ตลาด +USDJPY · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>',
         '<button role="tab" data-u="P5">พอร์ต 5 ตลาด</button>\n        <button role="tab" data-u="P4U">พอร์ต 4 +USDJPY</button>\n'
         '        <button role="tab" data-u="P4J">พอร์ต 4 +JP225</button>\n        <button role="tab" data-u="P3">พอร์ต 3 ตลาด</button>'),
        ('<button role="tab" data-u="BTCUSD">BTC</button>',
         '<button role="tab" data-u="BTCUSD">BTC</button>\n        <button role="tab" data-u="JP225">JP225</button>\n        <button role="tab" data-u="USDJPY">USDJPY</button>'),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "brake";\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์",',
         'const UNI_TH = {P5: "พอร์ต 5 ตลาด: ทอง เงิน บิตคอยน์ JP225 USDJPY", P4U: "พอร์ต 4 ตลาด: ทอง เงิน บิตคอยน์ USDJPY", '
         'P4J: "พอร์ต 4 ตลาด: ทอง เงิน บิตคอยน์ JP225", P3: "พอร์ต 3 ตลาด: ทอง เงิน บิตคอยน์", '
         'JP225: "Nikkei 225 (JP225) ตลาดเดียว", USDJPY: "USDJPY ตลาดเดียว",'),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "P5"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         f'const fixUni = () => {{ if (!D[keyOf(SYS, UNI)]) UNI = {ulist}.find(u => D[keyOf(SYS, u)]); }};\n'
         'try { const vv = localStorage.getItem("fivever"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("fivever", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("let VER = \"brake\";", "let VER = \"brake\";\nconst PORTS = " + json.dumps(PORT) + ";", 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for s in systems:
        for v in VERS:
            m = out[f"{s}~{v}_{PORT[s]}"]
            print(f"  {s:4s} {v:7s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} balDD {m['balance_dd']['relative_pct']:.1%} "
                  f"PF {m['pf']:.2f} trades {m['trades']}")
    print("  MC p_dd50", {s: round(v["p_dd50"], 3) for s, v in MC.items()}, "max open", maxopen, "corr", {k: round(v, 2) for k, v in corr.items()})
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
