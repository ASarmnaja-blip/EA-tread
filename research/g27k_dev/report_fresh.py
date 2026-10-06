#!/usr/bin/env python3
"""G27K #1 on fresh markets, in the G27K Strategy-Tester layout (ledger
g27k_fresh_markets). Reads fresh_markets.json for the admitted markets.

Systems (2011-09..2026-10, version switch brake 25% / normal 1% / AI monitor):
  C0  Cent base: gold, silver, BTC, USDJPY
  C1  C0 + the admitted markets that exist on Exness Standard Cent
  S0  Standard base: the five markets (+JP225)
  S1  S0 + every admitted market
A comparison section on top: all 28 markets in two groups (Cent / Standard
only) with the registered checks, then the portfolios side by side.

Usage: python3 research/g27k_dev/report_fresh.py --root <data-snapshot checkout> --out <html>
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
import fresh_markets as FM
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_five as R5
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, MID, END = "2011-09-01", "2018-01-01", "2026-10-01"
VERS = {"brake": "เบรก 25%", "normal": "ปกติ 1%", "monitor": "AI monitor"}
TH_M = RJ.TH_M
TH_NAME = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC", "XPTUSD": "แพลทินัม", "XPDUSD": "พาลาเดียม", "XNGUSD": "ก๊าซธรรมชาติ",
           "UKOIL": "น้ำมันเบรนท์"}


def systems_def(fr):
    S = {"C0": ("Cent: 4 ตลาด", list(FM.S4U)), "S0": ("Standard: 5 ตลาด", list(FM.S5))}
    if fr["admitted_cent"]:
        S["C1"] = (f"Cent: 4 +{len(fr['admitted_cent'])} ตลาดใหม่", list(FM.S4U) + fr["admitted_cent"])
    if fr["admitted"]:
        S["S1"] = (f"Standard: 5 +{len(fr['admitted'])} ตลาดใหม่", list(FM.S5) + fr["admitted"])
    order = [k for k in ("C0", "C1", "S0", "S1") if k in S]
    return {k: S[k] for k in order}


def market_table(fr):
    def rows(grp):
        out = ""
        for m, r in sorted(((k, v) for k, v in fr["markets"].items() if v["account"] == grp), key=lambda kv: -kv[1]["mean"]):
            ok = lambda b: "✓" if b else "✗"
            out += (f"<tr><td><b>{m}</b></td><td class='n'>{r['first'][:4]}</td><td class='n'>{r['n']}</td>"
                    f"<td class='n {'pos' if r['mean'] > 0 else 'neg'}'>{r['mean']:+.3f}</td><td class='n'>{r['t']:+.2f}</td>"
                    f"<td class='n {'pos' if r['mean_h1'] > 0 else 'neg'}'>{r['mean_h1']:+.3f}</td>"
                    f"<td class='n {'pos' if r['mean_h2'] > 0 else 'neg'}'>{r['mean_h2']:+.3f}</td>"
                    f"<td class='n {'pos' if r['mean_swap2'] > 0 else 'neg'}'>{r['mean_swap2']:+.3f}</td>"
                    f"<td class='n'>{r['cost_rt_bp']:.1f}</td><td class='n'>{r.get('corr_S5', float('nan')):+.2f}</td>"
                    f"<td class='n'>{'<b>รับ</b>' if r['admit'] else ok(False)}</td></tr>")
        return out
    head = ("<thead><tr><th>ตลาด</th><th class='n'>เริ่ม</th><th class='n'>ไม้</th><th class='n'>R/ไม้</th><th class='n'>t</th>"
            "<th class='n'>ครึ่งแรก</th><th class='n'>ครึ่งหลัง</th><th class='n'>swap ×2</th><th class='n'>ต้นทุน bp</th>"
            "<th class='n'>corr 5 ตลาด</th><th class='n'>ผล</th></tr></thead>")
    return ("<div class='cmp-grid' style='grid-template-columns:minmax(0,1fr)'>"
            "<section class='card'><h2>กลุ่ม Cent · เทรดได้ทั้งบัญชี Cent และ Standard</h2><div class='tbl'><table class='cmp'>" + head +
            "<tbody>" + rows("cent") + "</tbody></table></div></section>"
            "<section class='card'><h2>กลุ่ม Standard เท่านั้น</h2><div class='tbl'><table class='cmp'>" + head +
            "<tbody>" + rows("standard") + "</tbody></table></div>"
            "<p class='muted small' style='margin:8px 0 0'>รับเข้า = R/ไม้ > 0 และ t > 2 · บวกทั้งสองครึ่งของช่วงข้อมูลตลาดนั้น · ยังบวกเมื่อ swap แพงขึ้น 2 เท่า (เกณฑ์ลงทะเบียนก่อนรัน) · "
            "corr = correlation ผลรายเดือนกับพอร์ต 5 ตลาด</p></section></div>")


def compare(defs, E, MC, halves, curves, fr):
    keys = list(defs)
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    rows = [("เงินสุดท้าย (เริ่ม $100,000)", lambda s: E[s]["final"], 1, lambda v: f"${v:,.0f}"),
            ("ผลตอบแทนทบต้นต่อปี", lambda s: E[s]["cagr"], 1, lambda v: f"{v:.1%}"),
            ("Equity DD สูงสุด", lambda s: E[s]["equity_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
            ("MAR (ต่อปี ÷ Equity DD)", lambda s: mar(E[s]), 1, lambda v: f"{v:.2f}"),
            ("MAR ปี 2011–2017 (balance)", lambda s: halves[s][0], 1, lambda v: f"{v:+.2f}"),
            ("MAR ปี 2018–2026 (balance)", lambda s: halves[s][1], 1, lambda v: f"{v:+.2f}"),
            ("Profit Factor", lambda s: E[s]["pf"], 1, lambda v: f"{v:.2f}"),
            ("ปีที่แย่สุด", lambda s: worst(E[s])["ret"], 1, lambda v: f"{v:+.0%}"),
            ("อยู่ใต้ยอดเดิมนานสุด (ปี)", lambda s: E[s]["longest_underwater_days"] / 365.25, -1, lambda v: f"{v:.1f}"),
            ("จำนวนตลาด", lambda s: len(defs[s][1]), 0, lambda v: f"{v}"),
            ("จำนวนไม้", lambda s: E[s]["trades"], 0, lambda v: f"{v:,}"),
            ("สุ่ม 10 ปี: โอกาส DD เกิน 50%", lambda s: MC[s]["p_dd50"], -1, lambda v: f"{v:.1%}"),
            ("สุ่ม 10 ปี: ผลตอบแทนมัธยฐาน", lambda s: MC[s]["cagr_median"], 1, lambda v: f"{v:.1%}")]

    def tr(label, get, w, f):
        vals = {s: get(s) for s in keys}
        best = (max if w > 0 else min)(vals.values()) if w else None
        return f"<tr><td>{label}</td>" + "".join(f'<td class="n{" win" if w and f(v) == f(best) else ""}">{f(v)}</td>' for v in vals.values()) + "</tr>"

    head = "".join(f'<th class="n"><span class="sw" style="background:var(--c{i + 1})"></span>{defs[s][0]}</th>' for i, s in enumerate(keys))
    table = (f'<table class="cmp"><thead><tr><th></th>{head}</tr></thead><tbody>' + "".join(tr(*r) for r in rows) + "</tbody></table>"
             "<p class='muted small' style='margin:8px 0 0'>ตัวหนา = ดีที่สุดในข้อนั้น · เวอร์ชันเบรก 25% ทุกชุด · “สุ่ม 10 ปี” = Monte Carlo 4,000 รอบจากผลรายเดือน</p>")
    Y = {s: {y["year"]: y["ret"] for y in E[s]["yearly"]} for s in keys}
    years = sorted(set.intersection(*(set(Y[s]) for s in keys)))
    yt = (f'<table class="cmp"><thead><tr><th>ปี</th>{"".join(f"<th class=n>{defs[s][0]}</th>" for s in keys)}</tr></thead><tbody>'
          + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {'pos' if Y[s][y] >= 0 else 'neg'}'>{Y[s][y]:+.0%}</td>" for s in keys) + "</tr>"
                    for y in years) + "</tbody></table>")
    nm = len(fr["markets"])
    adm = fr["admitted"]
    pc, ps = fr.get("portfolio_pass_cent"), fr.get("portfolio_pass")
    verdict = lambda x: "ผ่าน" if x else "ไม่ผ่าน"
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>G27K #1 แบบไม่แก้กฎ</b> บน {nm} ตลาดที่ไม่เคยรันมาก่อน: บวก {fr['positive']} ตลาด (16 ตลาดเดิมบวก 7) · "
               f"<b>ผ่านเกณฑ์รับเข้า {len(adm)} ตลาด</b>{(': ' + ', '.join(adm)) if adm else ''}</li>"
               + (f"<li>กลุ่ม Cent รับเข้า {len(fr['admitted_cent'])} ตลาด · เพิ่มเข้าพอร์ต Cent แล้ว MAR ดีขึ้นทั้งสองช่วง: <b>{verdict(pc)}</b></li>" if pc is not None else "")
               + (f"<li>พอร์ต Standard + ตลาดที่รับเข้าทั้งหมด · MAR ดีขึ้นทั้งสองช่วง: <b>{verdict(ps)}</b></li>" if ps is not None else "")
               + ("<li><b>ETHUSD ผ่านเกณฑ์รายตลาด แต่ไม่ผ่านการตรวจพอร์ต</b> เพราะ ETH มีข้อมูลตั้งแต่ ส.ค. 2017 จึงแทบไม่อยู่ในช่วงแรก (2011–2017) ทำให้ MAR ช่วงแรกไม่ดีขึ้น · "
                  "ช่วงหลังดีขึ้นมาก แต่ <b>ETH ขยับตาม BTC</b> (correlation ผลรายเดือน +0.65 · 92% ของไม้ ETH เปิดซ้อนกับไม้ BTC) จึงเท่ากับเพิ่มความเสี่ยงคริปโตเป็น 2 เท่า</li>"
                  if "ETHUSD" in adm else "")
               + "<li>ต้นทุน: spread วัดจาก Dukascopy · <b>swap เป็นค่าสมมติ</b> (ค่าเงิน 1 bp/คืน, ดัชนีและสินค้า 2 bp/คืนฝั่ง Buy) ต้องยืนยันค่าจริงใน MT5 · "
                 f"แพลทินัมที่สเปกจริงของ Exness (spread 18.6 bp): {fr['xptusd_real_spec']['mean']:+.3f}R ต่อไม้</li>"
               + "<li>ตลาดที่ผ่านคือหลักฐานใหม่จริง (กฎไม่เคยเห็นตลาดนี้) แต่ยังควรเริ่มที่ forward test ก่อนเทรดจริง</li></ul>")
    pts = [dict(x=START, lab="เริ่ม " + START, **{s: float(W.DEPOSIT) for s in keys})]
    for d, vals in curves:
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {TH_M[d.month - 1]} {d.year}", **{s: float(v) for s, v in zip(keys, vals)}))
    short = {"C0": "Cent 4", "C1": "Cent 4+ใหม่", "S0": "Std 5", "S1": "Std 5+ใหม่"}
    data = json.dumps(dict(pts=pts, keys=keys, names=[short.get(s, defs[s][0]) for s in keys]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{defs[s][0]}</span>' for i, s in enumerate(keys))
    html = (R5.CSS + '<section class="card"><h2>ตลาดใหม่ 28 ตลาด · กฎ G27K #1 เดิม</h2>' + summary + '</section>' + market_table(fr) +
            f'<section class="card"><h2>พอร์ตตามประเภทบัญชี · เบรก 25%</h2><div class="legend" style="margin-bottom:6px">{legend}'
            '<span class="muted">Balance สิ้นเดือน · สเกล log</span></div><div id="cmpChart" class="chart"></div></section>'
            '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
            '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>')
    return html, R5.SCRIPT.replace("__DATA__", data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    fr = json.loads((HERE / "fresh_markets.json").read_text())
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    defs = systems_def(fr)
    allm = sorted({m for _, ms in defs.values() for m in ms})
    H1 = {m: MMS.load(m, G) for m in allm}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(allm, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    port = {s: "P" + s for s in defs}
    RWF.UNIS.update({port[s]: ms for s, (_, ms) in defs.items()}, **{m: [m] for m in allm})
    out, sized, MC, halves = {}, {}, {}, {}
    frame = lambda rr: pd.DataFrame(dict(mkt=[r["mkt"] for r in rr], t=[r["t"] for r in rr], tx=[r["t_exit"] for r in rr],
                                         R=[r["R"] for r in rr], vp=[r["vp"] for r in rr], sc=[r["sc"] for r in rr]))
    for s, (_, ms) in defs.items():
        rr = [r for r in rows if r["mkt"] in ms]
        for v in VERS:
            vr = RSD.sized(rr, v, news)
            sized[(s, v)] = vr
            for u in [port[s], *ms]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, 0.01, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
        T = frame(rr)
        _, eq, _ = SU.simulate(T, "brake", START, END, news=news)
        MC[s] = SU.monte_carlo(eq)
        halves[s] = (SU.simulate(T, "brake", START, MID, news=news)[0]["mar"], SU.simulate(T, "brake", MID, END, news=news)[0]["mar"])
        print(f"  {s} done  {time.time() - t0:.0f}s", flush=True)
    S_, E_ = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    cur = {}
    for s in defs:
        me, cur[s] = RJ.monthly(RWF.account_var(sized[(s, "brake")]), S_, E_)
    curves = [(d, [cur[s][i] for s in defs]) for i, d in enumerate(me)]
    E = {s: out[f"{s}~brake_{port[s]}"] for s in defs}
    cmp_html, cmp_js = compare(defs, E, MC, halves, curves, fr)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้"]
    info = {}
    for s, (label, ms) in defs.items():
        new = [m for m in ms if m in fr["markets"]]
        notes = [f"<b>ตลาด:</b> {', '.join(ms)} · เปิดพร้อมกันได้สูงสุด {len(ms)} ไม้ (ความเสี่ยงรวมสูงสุด {len(ms)}%)"]
        if s.startswith("C"):
            notes.append("<b>ทุกตลาดมีในบัญชี Exness Standard Cent</b> · BTCUSDc และ ETHUSDc มีเฉพาะ MT5")
        else:
            notes.append("<b>ต้องใช้บัญชี Exness Standard (USD)</b> · ทุกตลาดอยู่บัญชีเดียวกัน เบรก 25% จึงคิดจากยอดรวมได้ถูก")
        if new:
            notes.append(f"<b>ตลาดใหม่ที่ผ่านเกณฑ์:</b> {', '.join(new)} · กฎไม่เคยเห็นตลาดเหล่านี้มาก่อน แต่ swap เป็นค่าสมมติ ต้องเช็คใน MT5")
        info[s] = dict(label=f"G27K #1 · {label}", tab=label, rules=g_rules + [f"ตลาด: {', '.join(ms)}"], notes=notes,
                       combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01, adds=False, tf="H4", risk_note=RSD.RISK_NOTE["brake"], risk_notes=RSD.RISK_NOTE)
    wf = {s: dict(patterns=[], pat_note="", pat_empty="กฎตายตัว G27K #1 กฎเดียว", log=[], log_note="",
                  log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า") for s in defs}
    last = E_ - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S_.day} {TH_M[S_.month - 1]} {S_.year} – {last.day} {TH_M[last.month - 1]} {last.year}",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · ตลาดอื่น: Dukascopy H1 · BTC/ETH: Binance · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>บัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) · swap ของตลาดเดิมเป็นค่าจริงของโบรก ของตลาดใหม่เป็นค่าสมมติ",
                                     "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026 บนทอง</b> ส่วนตลาดใหม่ไม่เคยถูกใช้เลือกกฎ",
                                     "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ตของระบบนั้น (เบรกดู DD ของทั้งพอร์ต)"],
                       footer="สร้างจาก research/g27k_dev/report_fresh.py · ledger: g27k_fresh_markets · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    ulist = [port[s] for s in defs] + allm
    uni_th = {port[s]: f"พอร์ต {defs[s][0]}" for s in defs}
    uni_th.update({m: f"{TH_NAME.get(m, m)} ({m}) ตลาดเดียว" for m in allm})
    pbtn = "\n        ".join(f'<button role="tab" data-u="{port[s]}">พอร์ต {defs[s][0]}</button>' for s in defs)
    mbtn = "\n        ".join(f'<button role="tab" data-u="{m}">{TH_NAME.get(m, m)}</button>' for m in allm if m not in ("XAUUSD", "XAGUSD", "BTCUSD"))
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>G27K ตลาดใหม่</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K ตลาดใหม่"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "G27K #1 บน 28 ตลาดใหม่ · Cent และ Standard"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>', pbtn),
        ('<button role="tab" data-u="BTCUSD">BTC</button>', '<button role="tab" data-u="BTCUSD">BTC</button>\n        ' + mbtn),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "brake";\nconst PORTS = ' + json.dumps(port) + ';\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์", XAUUSD: "ทอง (XAUUSD) ตลาดเดียว", XAGUSD: "เงิน (XAGUSD) ตลาดเดียว", BTCUSD: "บิตคอยน์ (BTCUSD) ตลาดเดียว"};',
         "const UNI_TH = " + json.dumps(uni_th, ensure_ascii=False) + ";"),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', f'let SYS = Object.keys(SINFO)[0], UNI = "{port[next(iter(defs))]}"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         f'const fixUni = () => {{ if (!D[keyOf(SYS, UNI)]) UNI = {json.dumps(ulist)}.find(u => D[keyOf(SYS, u)]); }};\n'
         'try { const vv = localStorage.getItem("freshver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("freshver", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for s in defs:
        m = E[s]
        print(f"  {s} {defs[s][0]:28s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} MAR {m['cagr'] / m['equity_dd']['relative_pct']:.2f} "
              f"halves {halves[s][0]:+.2f}/{halves[s][1]:+.2f} trades {m['trades']}")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
