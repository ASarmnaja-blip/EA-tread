#!/usr/bin/env python3
"""System B (gold + silver + BTC, G27K #1 rules) at 1% risk with the 25%
drawdown brake, in the G27K Strategy-Tester layout, 2009-09..2026-09.

Tabs: B 1% + brake 25% (ledger g27k_b_1pct_brake), constant 1% and
constant 0.5%. Trades come from the G27K report's own fill engine
(report768.sim_paths) and every metric from report768.metrics.

Usage: python3 research/g27k_dev/report_brake.py --root <data-snapshot checkout> --out <html>
"""
import argparse
import heapq
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import brake as BR
import report_walkforward10y as RWF
import walkforward_controller as W

START, END = "2009-09-01", "2026-10-01"
X_BRAKE = 0.25


def brake_fracs(rows, base=0.01, X=X_BRAKE, deposit=W.DEPOSIT):
    """Give each trade its risk fraction under the brake, in the order
    RWF.account_var settles and opens trades, and log every switch."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["t"], rows[i]["mkt"]))
    bal, peak, heap, mult, log = deposit, deposit, [], 1.0, []
    for i in order:
        tr = rows[i]
        while heap and heap[0][0] <= tr["t"]:
            _, _, p = heapq.heappop(heap)
            bal += p
            peak = max(peak, bal)
        now = 1 - bal / peak
        if mult == 1.0 and now >= X:
            mult = 0.5
            log.append(dict(t=str(pd.Timestamp(tr["t"], unit="s").date()), kind="brake",
                            text=f"Balance DD {now:.1%} ถึงเกณฑ์ {X:.0%} → ลดความเสี่ยงเหลือ {base * 0.5:.1%} ต่อไม้"))
        elif mult < 1.0 and now <= X / 2:
            mult = 1.0
            log.append(dict(t=str(pd.Timestamp(tr["t"], unit="s").date()), kind="brake",
                            text=f"Balance DD เหลือ {now:.1%} (ไม่เกิน {X / 2:.1%}) → กลับไปใช้ {base:.0%} ต่อไม้"))
        tr["risk_frac"] = base * mult
        heapq.heappush(heap, (tr["t_exit"], i, base * mult * bal * tr["R"]))
    return log


CMP_CSS = """<style>
:root{--s-bk:#1f5eff;--s-nb:#e8890c;--band:rgba(31,94,255,.07)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--s-bk:#5b8cff;--s-nb:#d07a1c;--band:rgba(91,140,255,.10)}}
:root[data-theme="dark"]{--s-bk:#5b8cff;--s-nb:#d07a1c;--band:rgba(91,140,255,.10)}
.cmp-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);gap:14px;margin-bottom:14px}
.cmp-grid .card{margin-bottom:0}
@media (max-width:820px){.cmp-grid{grid-template-columns:minmax(0,1fr)}}
.cmp td.win{font-weight:700}
.cmp td,.cmp th{white-space:normal}
@media (max-width:520px){.cmp{font-size:13px}.cmp td,.cmp th{padding:6px 5px}}
.sw{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
#cmpChart{position:relative}
#cmpTip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:13px;box-shadow:var(--shadow);display:none;white-space:nowrap;z-index:2}
.cmp-sum{margin:0 0 10px;font-size:14.5px}
</style>"""


def compare_section(bk, b1, log, mc, dca_rows, start, nyears, curves):
    """Static side-by-side of the brake and no brake (three-market portfolio)."""
    on = pd.Timestamp(log[0]["t"]) if log else None
    off = pd.Timestamp(log[1]["t"]) if len(log) > 1 else None
    yrs_bk = {y["year"]: y for y in bk["yearly"]}
    yrs_nb = {y["year"]: y for y in b1["yearly"]}
    years = sorted(yrs_bk)
    TH = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    pts = [dict(x=start, bk=bk["deposit"], nb=b1["deposit"], lab="เริ่ม " + start)]
    for d, vb, vn in curves:
        pts.append(dict(x=str(d.date()), bk=vb, nb=vn, lab=f"สิ้น {TH[d.month - 1]} {d.year}"))

    def state(y):
        if on is None or y < on.year or (off is not None and y > off.year):
            return "1%"
        if y in (on.year, off.year if off is not None else None):
            return "1% / 0.5%"
        return "0.5%"

    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    neg_years = lambda r: sum(y["ret"] < 0 for y in r["yearly"])
    mb, mn = mc["brake 25%"], mc["const 1%"]
    # (label, brake, no brake, which is better: 1 brake, -1 no brake, 0 none)
    rows = [("เงินสุดท้าย (เริ่ม $100,000)", f"${bk['final']:,.0f}", f"${b1['final']:,.0f}", -1),
            ("ผลตอบแทนทบต้นต่อปี", f"{bk['cagr']:.1%}", f"{b1['cagr']:.1%}", -1),
            ("Equity DD สูงสุด", f"{bk['equity_dd']['relative_pct']:.1%}", f"{b1['equity_dd']['relative_pct']:.1%}", 1),
            ("Balance DD สูงสุด", f"{bk['balance_dd']['relative_pct']:.1%}", f"{b1['balance_dd']['relative_pct']:.1%}", 1),
            ("MAR (ต่อปี ÷ Equity DD)", f"{mar(bk):.2f}", f"{mar(b1):.2f}", 1),
            ("Profit Factor", f"{bk['pf']:.2f}", f"{b1['pf']:.2f}", 1),
            ("ปีที่แย่สุด", f"{worst(bk)['ret']:+.0%} ({worst(bk)['year']})", f"{worst(b1)['ret']:+.0%} ({worst(b1)['year']})", 1),
            ("จำนวนปีที่ขาดทุน", f"{neg_years(bk)} จาก {len(years)}", f"{neg_years(b1)} จาก {len(years)}", 0),
            ("อยู่ใต้ยอดเดิมนานสุด", f"{bk['longest_underwater_days'] / 365.25:.1f} ปี", f"{b1['longest_underwater_days'] / 365.25:.1f} ปี", 0),
            ("สุ่ม 10 ปี: โอกาส DD เกิน 50%", f"{mb['p_dd50']:.1%}", f"{mn['p_dd50']:.1%}", 1),
            ("สุ่ม 10 ปี: DD มัธยฐาน", f"{mb['dd_median']:.0%}", f"{mn['dd_median']:.0%}", 1),
            ("สุ่ม 10 ปี: ผลตอบแทนมัธยฐาน", f"{mb['cagr_median']:.1%}", f"{mn['cagr_median']:.1%}", -1),
            *dca_rows]
    td = lambda v, w: f'<td class="n{" win" if w else ""}">{v}</td>'
    table = ('<table class="cmp"><thead><tr><th></th><th class="n"><span class="sw" style="background:var(--s-bk)"></span>เบรก 25%</th>'
             '<th class="n"><span class="sw" style="background:var(--s-nb)"></span>ไม่มีเบรก</th></tr></thead><tbody>'
             + "".join(f"<tr><td style='white-space:normal'>{l}</td>{td(a, w == 1 and a != b)}{td(b, w == -1 and a != b)}</tr>" for l, a, b, w in rows)
             + "</tbody></table><p class='muted small' style='margin:8px 0 0'>ตัวหนา = ฝั่งที่ดีกว่าในข้อนั้น · พอร์ต 3 ตลาด · “สุ่ม 10 ปี” = Monte Carlo 10,000 รอบจากผลรายเดือนของประวัติ 17 ปีทั้งหมด</p>")
    yt = ('<table class="cmp"><thead><tr><th>ปี</th><th class="n">ความเสี่ยง</th><th class="n">เบรก 25%</th><th class="n">ไม่มีเบรก</th>'
          '<th class="n">ต่าง (จุด)</th></tr></thead><tbody>'
          + "".join(f"<tr><td>{y}</td><td class='n'>{state(y)}</td>"
                    f"<td class='n {'pos' if yrs_bk[y]['ret'] >= 0 else 'neg'}'>{yrs_bk[y]['ret']:+.0%}</td>"
                    f"<td class='n {'pos' if yrs_nb[y]['ret'] >= 0 else 'neg'}'>{yrs_nb[y]['ret']:+.0%}</td>"
                    f"<td class='n'>{(yrs_bk[y]['ret'] - yrs_nb[y]['ret']) * 100:+.0f}</td></tr>" for y in years)
          + "</tbody></table>")
    gap = 1 - bk["final"] / b1["final"]
    summary = (f"<p class='cmp-sum'>เบรกทำงาน <b>{on:%d/%m/%Y}</b> และปลด <b>{off:%d/%m/%Y}</b> "
               f"(ใช้ 0.5% อยู่ราว {(off - on).days / 365.25:.0f} ปี) · ผลรวม {nyears} ปี: เงินสุดท้ายน้อยกว่าไม่มีเบรก {gap:.0%} "
               f"แต่ Equity DD ลดจาก {b1['equity_dd']['relative_pct']:.0%} เหลือ {bk['equity_dd']['relative_pct']:.0%} "
               f"และโอกาสพอร์ตร่วงเกินครึ่งลดจาก {mn['p_dd50']:.1%} เหลือ {mb['p_dd50']:.1%}</p>") if off is not None else (
        f"<p class='cmp-sum'><b>ช่วง {nyears} ปีนี้เบรกไม่ทำงานเลย</b> เพราะพอร์ตไม่เคยต่ำกว่ายอดสูงสุดถึง 25% "
        f"(Balance DD สูงสุด {bk['balance_dd']['relative_pct']:.1%}) ผลจึงเหมือนไม่มีเบรกทุกไม้ · "
        f"เบรกคือประกันสำหรับช่วงแบบปี 2013–2015 ซึ่งช่วงนี้ไม่เกิด · ตัวเลข “สุ่ม 10 ปี” ด้านล่างคือสิ่งที่เบรกป้องกัน</p>")
    data = json.dumps(dict(pts=pts, on=log[0]["t"] if log else None, off=log[1]["t"] if len(log) > 1 else None))
    script = """<script>
(function(){
const C = __DATA__, el = document.getElementById("cmpChart"), tip = document.getElementById("cmpTip");
const ts = s => Date.parse(s + "T00:00:00Z"), nf = new Intl.NumberFormat("en-US", {maximumFractionDigits: 0});
const short = v => v >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : "$" + Math.round(v / 1e3) + "k";
const tick = v => v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";
function draw(){
  const W = el.clientWidth, narrow = W < 520, H = narrow ? 240 : 300, L = 48, R = narrow ? 14 : 92, T = 12, B = 26;
  const x0 = ts(C.pts[0].x), x1 = ts(C.pts[C.pts.length - 1].x);
  const all = C.pts.flatMap(p => [p.bk, p.nb]), lo = Math.log(Math.min(...all) * 0.9), hi = Math.log(Math.max(...all) * 1.08);
  const X = t => L + (t - x0) / (x1 - x0) * (W - L - R), Y = v => T + (hi - Math.log(v)) / (hi - lo) * (H - T - B);
  const ticks = [1e5, 2e5, 5e5, 1e6, 2e6].filter(v => Math.log(v) > lo && Math.log(v) < hi);
  const ya = new Date(x0).getUTCFullYear() + 1, yb = new Date(x1).getUTCFullYear(), stp = Math.max(1, Math.ceil((yb - ya + 1) / (W < 520 ? 5 : 7)));
  const yearsT = []; for (let y = ya; y <= yb; y += stp) yearsT.push(y);
  const line = k => C.pts.map((p, i) => (i ? "L" : "M") + X(ts(p.x)).toFixed(1) + "," + Y(p[k]).toFixed(1)).join("");
  const last = C.pts[C.pts.length - 1];
  let s = `<svg class="svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Balance เบรก 25% เทียบกับไม่มีเบรก สเกล log">`;
  if (C.on) s += `<rect x="${X(ts(C.on))}" y="${T}" width="${X(ts(C.off || last.x)) - X(ts(C.on))}" height="${H - T - B}" fill="var(--band)"/>` +
    `<text x="${(X(ts(C.on)) + X(ts(C.off || last.x))) / 2}" y="${T + 14}" text-anchor="middle" font-size="12" fill="var(--muted)">ช่วงเบรก (0.5%)</text>`;
  ticks.forEach(v => s += `<line class="gl" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="11.5" fill="var(--faint)">${tick(v)}</text>`);
  yearsT.forEach(y => { const x = X(ts(y + "-01-01")); s += `<text x="${x}" y="${H - 8}" text-anchor="middle" font-size="11.5" fill="var(--faint)">${y}</text>`; });
  s += `<path d="${line("nb")}" fill="none" stroke="var(--s-nb)" stroke-width="2" stroke-linejoin="round"/>`;
  s += `<path d="${line("bk")}" fill="none" stroke="var(--s-bk)" stroke-width="2" stroke-linejoin="round"/>`;
  const ly = [[last.nb, "ไม่มีเบรก", "nb"], [last.bk, "เบรก", "bk"]].map(([v, t, k]) => [Y(v), t, k, v]).sort((a, b) => a[0] - b[0]);
  if (ly[1][0] - ly[0][0] < 34) { const m = (ly[0][0] + ly[1][0]) / 2; ly[0][0] = m - 17; ly[1][0] = m + 17; }
  ly.forEach(l => { l[0] = Math.max(l[0], T + 26); });
  if (ly[1][0] - ly[0][0] < 34) ly[1][0] = ly[0][0] + 34;
  if (!narrow) ly.forEach(([y, t, k, v]) => s += `<circle cx="${X(ts(last.x))}" cy="${Y(v)}" r="4" fill="var(--s-${k})" stroke="var(--panel)" stroke-width="2"/><text x="${X(ts(last.x)) + 8}" y="${y - 2}" font-size="12" fill="var(--ink)" font-weight="600">${t}</text><text x="${X(ts(last.x)) + 8}" y="${y + 12}" font-size="11.5" fill="var(--muted)">${short(v)}</text>`);
  s += `<line id="cmpX" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--faint)" stroke-width="1" style="display:none"/>`;
  s += `<circle id="cmpDb" r="4" fill="var(--s-bk)" stroke="var(--panel)" stroke-width="2" style="display:none"/><circle id="cmpDn" r="4" fill="var(--s-nb)" stroke="var(--panel)" stroke-width="2" style="display:none"/>`;
  s += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" id="cmpHit"/></svg>`;
  el.innerHTML = s + `<div id="cmpTip"></div>`;
  const tp = document.getElementById("cmpTip"), cx = document.getElementById("cmpX"), db = document.getElementById("cmpDb"), dn = document.getElementById("cmpDn");
  const move = e => {
    const r = el.getBoundingClientRect(), px = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
    let best = C.pts[0], bd = 1e9; C.pts.forEach(p => { const d = Math.abs(X(ts(p.x)) - px); if (d < bd) { bd = d; best = p; } });
    const x = X(ts(best.x));
    [cx, db, dn].forEach(n => n.style.display = "");
    cx.setAttribute("x1", x); cx.setAttribute("x2", x);
    db.setAttribute("cx", x); db.setAttribute("cy", Y(best.bk)); dn.setAttribute("cx", x); dn.setAttribute("cy", Y(best.nb));
    tp.style.display = "block";
    tp.innerHTML = `<b>${best.lab}</b><br><span class="sw" style="background:var(--s-bk)"></span>เบรก $${nf.format(best.bk)}<br><span class="sw" style="background:var(--s-nb)"></span>ไม่มีเบรก $${nf.format(best.nb)}`;
    const tw = tp.offsetWidth; tp.style.left = Math.min(Math.max(x + 10, 0), W - tw) + "px"; tp.style.top = "8px";
  };
  const hide = () => { [cx, db, dn, tp].forEach(n => n.style.display = "none"); };
  const hit = document.getElementById("cmpHit");
  hit.addEventListener("mousemove", move); hit.addEventListener("touchstart", move, {passive: true}); hit.addEventListener("touchmove", move, {passive: true});
  hit.addEventListener("mouseleave", hide);
}
let w0 = 0; draw(); w0 = el.clientWidth;
window.addEventListener("resize", () => { if (el.clientWidth !== w0) { w0 = el.clientWidth; draw(); } });
})();
</script>""".replace("__DATA__", data)
    html = (CMP_CSS + '<section class="card"><h2>เทียบกับไม่มีเบรก · พอร์ต 3 ตลาด 1% ต่อไม้</h2>' + summary +
            '<div class="legend" style="margin-bottom:6px"><span><i style="background:var(--s-bk)"></i>เบรก 25%</span>'
            '<span><i style="background:var(--s-nb)"></i>ไม่มีเบรก</span><span class="muted">Balance สิ้นเดือน · สเกล log</span></div>'
            '<div id="cmpChart" class="chart"></div></section>'
            '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
            '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>')
    return html, script


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    S, E = pd.Timestamp(a.start, tz="UTC"), pd.Timestamp(a.end, tz="UTC")
    ny = round((E - S).days / 365.25)
    G.START = K.START = int(S.timestamp())
    ext = K.externals()
    rows = []
    for m in ("XAUUSD", "XAGUSD", "BTCUSD"):
        h1 = P._M["h1"][m]
        Mk = K.prepare(m, h1, ext)
        X = G.features(G.frames(h1), m, "H4")
        X["sec"] = 14400
        P.FRAMES[(m, "H4")] = X
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        rows += [dict(tr, X=X) for tr in RP.sim_paths(X, m, idx, d[idx], "I1")]
    rows = [r for r in rows if S.timestamp() <= r["t"] < E.timestamp()]
    log = brake_fracs(rows)

    out = {}
    for uni in RWF.UNIS:
        for key, fixed in (("BK", None), ("B1", 0.01), ("B05", 0.005)):
            ent = RWF.build_entry(key, uni, rows, fixed or 0.01, fixed, RP, G)
            if ent:
                out[f"{key}_{uni}"] = ent
    bk, b1, b05 = out["BK_MET3"], out["B1_MET3"], out["B05_MET3"]
    braked = float(np.mean([r["risk_frac"] < 0.01 for r in rows]))
    bj = json.loads((HERE / "brake.json").read_text())
    mc, dca = bj["monte_carlo"], bj["dca"]
    line = lambda r: f"{r['cagr'] * 100:.1f}% ต่อปี, Equity DD {r['equity_dd']['relative_pct'] * 100:.0f}%"
    base_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
                  "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
                  "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง (ไม่มี TP)",
                  "ตลาดละ 1 ไม้ · ทอง เงิน และบิตคอยน์ (บิตคอยน์เริ่มปี 2021)"]
    TH_M = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    last = E - pd.Timedelta(days=1)
    period_th = f"{ny} ปี {S.day} {TH_M[S.month - 1]} {S.year} – {last.day} {TH_M[last.month - 1]} {last.year}"
    info = {
        "BK": dict(label="ระบบ B 1% + เบรก 25%", tab="B 1% + เบรก", combo="G27K #1 · เบรก DD 25%", risk=0.01, adds=False, tf="H4",
                   risk_note=f"ปกติ 1% · Balance DD ถึง 25% → 0.5% · กลับ 1% เมื่อ DD ไม่เกิน 12.5% · {braked:.0%} ของไม้ทั้งหมดเข้าตอนเบรกทำงาน",
                   rules=base_rules + ["ความเสี่ยง 1% ต่อไม้ ทบต้นจาก balance",
                                       "เบรก: เมื่อ balance ต่ำกว่ายอดสูงสุด 25% ลดเหลือ 0.5% ต่อไม้ กลับเป็น 1% เมื่อห่างจากยอดสูงสุดไม่เกิน 12.5%"],
                   notes=[f"<b>ระบบที่คุณเลือก</b> ได้ {line(bk)} เทียบกับ 1% ไม่มีเบรก {line(b1)} และ 0.5% {line(b05)}",
                          "<b>เบรกลงทะเบียนไว้ก่อนรัน (ledger g27k_b_1pct_brake) ผ่าน 3 จาก 4 เกณฑ์</b> ช่วง 2017–2026 MAR ต่ำกว่าการใช้ความเสี่ยงคงที่เท่ากัน (0.94 เทียบกับ 1.01) จึงถือเป็นนโยบายคุมความเสี่ยง ไม่ใช่ความได้เปรียบที่พิสูจน์แล้ว",
                          f"<b>Monte Carlo 10 ปี 10,000 รอบ:</b> โอกาส DD เกิน 50% = {mc['brake 25%']['p_dd50']:.1%} (ไม่มีเบรก {mc['const 1%']['p_dd50']:.1%}) · DD มัธยฐาน {mc['brake 25%']['dd_median']:.0%} · ผลตอบแทนมัธยฐาน {mc['brake 25%']['cagr_median']:.1%} ต่อปี",
                          *([f"<b>เติมเงิน $100 ทุกเดือนตั้งแต่ ต.ค. 2009:</b> ใส่ ${dca['2009-10-01 brake 25%']['deposited']:,.0f} ได้ ${dca['2009-10-01 brake 25%']['final']:,.0f} (IRR {dca['2009-10-01 brake 25%']['irr']:.1%}) · ไม่มีเบรกได้ ${dca['2009-10-01 const 1%']['final']:,.0f}"] if S.year < 2010 else []),
                          "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ต 3 ตลาด (เบรกดู DD ของทั้งพอร์ต) · ตาราง “ถ้าเปลี่ยนความเสี่ยง” ย่อ/ขยายทุกไม้ตามสัดส่วน โดยจังหวะเบรกคงเดิม"]),
        "B1": dict(label="ระบบ B 1% ไม่มีเบรก", tab="B 1%", combo="G27K #1", risk=0.01, adds=False, tf="H4", risk_note="ต่อไม้ คงที่",
                   rules=base_rules + ["ความเสี่ยง 1% ต่อไม้ ทบต้นจาก balance ไม่มีเบรก"],
                   notes=[f"ได้ {line(b1)} · แท็บทองตลาดเดียวของหน้านี้คือระบบ A (ทองอย่างเดียว 1%)"]),
        "B05": dict(label="ระบบ B 0.5%", tab="B 0.5%", combo="G27K #1", risk=0.005, adds=False, tf="H4", risk_note="ต่อไม้ คงที่",
                    rules=base_rules + ["ความเสี่ยง 0.5% ต่อไม้ ทบต้นจาก balance ไม่มีเบรก"],
                    notes=[f"ได้ {line(b05)} · ตัวเลือกที่ปลอดภัยที่สุด แต่ผลตอบแทนประมาณครึ่งหนึ่ง"]),
    }
    empty = "ระบบนี้เป็นกฎตายตัว G27K #1 กฎเดียว ไม่มีการค้นหรือเปลี่ยนรูปแบบระหว่างทาง"
    wf = {"BK": dict(patterns=[], pat_note="", pat_empty=empty, log=log,
                     log_note=f"ทุกครั้งที่เบรกทำงานหรือปลดเบรก ({len(log)} ครั้งใน {ny} ปี)", log_empty=f"เบรกไม่ทำงานเลยใน {ny} ปีนี้ (Balance DD ไม่ถึง 25%)"),
          "B1": dict(patterns=[], pat_note="", pat_empty=empty, log=[], log_note="", log_empty="ไม่มีเบรก ไม่มีการตัดสินใจระหว่างทาง"),
          "B05": dict(patterns=[], pat_note="", pat_empty=empty, log=[], log_note="", log_empty="ไม่มีเบรก ไม่มีการตัดสินใจระหว่างทาง")}
    out["META"] = dict(
        systems_info=info, wf=wf, period_th=period_th,
        data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 H1 · BTC: MT5 H1 ตั้งแต่ปี 2021 · SL ตรวจทีละแท่ง H1",
        notes_common=[f"<b>ตัวเลขทั้งหน้านี้คือ {period_th} บัญชีเดียวต่อเนื่อง เริ่ม $100,000</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง และไม่ได้บอกอนาคต · ทุกตัวเลขย่อขยายตามเงินต้นได้ ($100 = 10,000 USC)",
                      "<b>ต้นทุนเหมือนรายงาน G27K:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap จริงของโบรกเกอร์",
                      *(["<b>กฎ G27K #1 ถูกเลือกจาก 27,648 แบบโดยเห็นผลปี 2021–2026 แล้ว</b> ช่วงนั้นจึงดีเกินจริง · ช่วง 2009–2020 ไม่ได้ใช้เลือก และได้ผลอ่อนกว่ามาก (ตลาดโลหะขาลงปี 2011–2015)",
                         "<b>BTC มีข้อมูลตั้งแต่ปี 2021 เท่านั้น</b> ก่อนหน้านั้นระบบ B เทรดแค่ทองกับเงิน และ 5 ปีของ BTC ยังไม่ครอบคลุมการร่วงแบบ 75–80% ทุกแบบที่เคยเกิด"]
                        if S.year < 2021 else
                        ["<b>ทั้งช่วงนี้อยู่ในช่วงที่ใช้เลือกกฎ G27K #1 (เห็นผลปี 2021–2026 แล้วจึงเลือกจาก 27,648 แบบ)</b> ตัวเลขจึงดีเกินจริงมาก และเป็นช่วงที่ทอง เงิน และ BTC ขึ้นแรง ห้ามใช้เป็นภาพของอนาคต · ภาพที่สมจริงกว่าคือรายงาน 17 ปี"])],
        footer="สร้างจาก research/g27k_dev/report_brake.py · ledger: g27k_two_systems_phase1 / g27k_b_1pct_brake · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · คำนวณ 2 ต.ค. 2026")
    data = RWF.clean(out)
    (HERE / f"report_brake_{ny}y.json").write_text(json.dumps(data, ensure_ascii=False))
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    tpl = (tpl.replace("<title>รายงาน Walk-forward 10 ปี</title>", "<title>ระบบ B 1% + เบรก</title>" if ny == 17 else f"<title>ระบบ B + เบรก {ny} ปี</title>")
              .replace("Strategy Tester · Walk-forward report", "Strategy Tester · G27K ระบบ B")
              .replace("รายงานผลทดสอบ Walk-forward · 10 ปี", f"รายงานผลทดสอบระบบ B 1% + เบรก · {ny} ปี")
              .replace("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "เบรกใช้แค่ balance ณ เวลาเข้าไม้")
              .replace('<h2>บันทึกการตัดสินใจ</h2>', '<h2>บันทึกเบรก</h2>'))
    Tdf = pd.DataFrame(dict(t=[r["t"] for r in rows], tx=[r["t_exit"] for r in rows], R=[r["R"] for r in rows]))
    dca_rows = []
    d0 = (S + pd.offsets.MonthBegin(0)).strftime("%Y-%m-%d")
    for ds in [d0] + (["2016-10-01"] if S.year < 2016 else []):
        db, dn = (BR.dca_brake(Tdf[Tdf.t >= W.ts(ds)], X, ds, a.end) for X in (X_BRAKE, None))
        dca_rows.append((f"เติม $100/เดือน ตั้งแต่ {ds[:7]} (ใส่ ${db['deposited']:,.0f})",
                         f"${db['final']:,.0f} · {db['irr']:.1%}/ปี", f"${dn['final']:,.0f} · {dn['irr']:.1%}/ปี",
                         0 if abs(db['final'] - dn['final']) < 1 else (1 if db['final'] > dn['final'] else -1)))
    me = pd.date_range(S, E, freq="ME")
    def monthly(acc):
        tx = np.array([r["t_exit"] for r in acc]); ba = np.array([r["bal_after"] for r in acc])
        j = np.searchsorted(tx, me.values.astype("datetime64[s]").astype(np.int64) + 86399, side="right") - 1
        return np.where(j >= 0, ba[np.maximum(j, 0)], W.DEPOSIT)
    cb = monthly(RWF.account_var(rows))
    cn = monthly(RWF.account_var([dict(r, risk_frac=0.01) for r in rows]))
    curves = [(d, float(x), float(y)) for d, x, y in zip(me, cb, cn)]
    cmp_html, cmp_js = compare_section(bk, b1, log, mc, dca_rows, str(S.date()), ny, curves)
    tpl = (tpl.replace('<section class="kpis" id="kpis"></section>',
                       cmp_html + '<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>', 1)
              + "\n" + cmp_js)
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for k in ("BK", "B1", "B05"):
        m = out[f"{k}_MET3"]
        print(f"  {k}: trades {m['trades']} net {m['net']:+,.0f} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} "
              f"balDD {m['balance_dd']['relative_pct']:.1%} PF {m['pf']:.2f}")
    print(f"  brake switches {len(log)}, share of trades braked {braked:.0%}")
    for l in log:
        print("   ", l["t"], l["text"])


if __name__ == "__main__":
    main()
