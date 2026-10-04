#!/usr/bin/env python3
"""G27K #1 on four markets (gold, silver, BTC + JP225) against the three-market
system, 17 years, in the G27K Strategy-Tester layout (ledger g27k_b_plus_jp225).

A comparison section on top (monthly balance of both, key numbers, years),
then the full report with system tabs (4 / 3 markets), a version switch
(brake 25%, normal 1%, AI monitor) and market tabs.

Usage: python3 research/g27k_dev/report_jp225.py --root <data-snapshot checkout> --out <html>
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
import report_brake as RB
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, END = "2011-09-01", "2026-10-01"      # JP225 history starts Sep 2011
M3 = ("XAUUSD", "XAGUSD", "BTCUSD")
M4 = M3 + ("JP225",)
VERS = {"brake": "เบรก 25%", "normal": "ปกติ 1%", "monitor": "AI monitor"}
TH_M = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def monthly(acc, S, E):
    me = pd.date_range(S, E, freq="ME")
    tx = np.array([r["t_exit"] for r in acc])
    ba = np.array([r["bal_after"] for r in acc])
    j = np.searchsorted(tx, me.values.astype("datetime64[s]").astype(np.int64) + 86399, side="right") - 1
    return me, np.where(j >= 0, ba[np.maximum(j, 0)], W.DEPOSIT)


def compare(e4, e3, mc4, mc3, curves, start, corr):
    """Four-vs-three comparison for the brake version. The balance chart is the
    brake report's own chart script with its labels changed."""
    _, script = RB.compare_section(e4, e3, [], {"brake 25%": mc4, "const 1%": mc3}, [], start, 15, curves)
    script = (script.replace('"ไม่มีเบรก", "nb"]', '"3 ตลาด", "nb"]').replace('"เบรก", "bk"]', '"4 ตลาด", "bk"]')
                    .replace(">เบรก $${nf.format(best.bk)}", ">4 ตลาด $${nf.format(best.bk)}")
                    .replace(">ไม่มีเบรก $${nf.format(best.nb)}", ">3 ตลาด $${nf.format(best.nb)}")
                    .replace("Balance เบรก 25% เทียบกับไม่มีเบรก สเกล log", "Balance 4 ตลาด เทียบ 3 ตลาด สเกล log"))
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    # (label, 4 markets, 3 markets, which is better: 1 = higher wins, -1 = lower wins, 0 = neither)
    rows = [("เงินสุดท้าย (เริ่ม $100,000)", e4["final"], e3["final"], 1, lambda v: f"${v:,.0f}"),
            ("ผลตอบแทนทบต้นต่อปี", e4["cagr"], e3["cagr"], 1, lambda v: f"{v:.1%}"),
            ("Equity DD สูงสุด", e4["equity_dd"]["relative_pct"], e3["equity_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
            ("Balance DD สูงสุด", e4["balance_dd"]["relative_pct"], e3["balance_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
            ("MAR (ต่อปี ÷ Equity DD)", mar(e4), mar(e3), 1, lambda v: f"{v:.2f}"),
            ("Profit Factor", e4["pf"], e3["pf"], 1, lambda v: f"{v:.2f}"),
            ("ปีที่แย่สุด", worst(e4)["ret"], worst(e3)["ret"], 1, lambda v: f"{v:+.0%}"),
            ("อยู่ใต้ยอดเดิมนานสุด (ปี)", e4["longest_underwater_days"] / 365.25, e3["longest_underwater_days"] / 365.25, -1, lambda v: f"{v:.1f}"),
            ("จำนวนไม้", e4["trades"], e3["trades"], 0, lambda v: f"{v:,}"),
            ("สุ่ม 10 ปี: โอกาส DD เกิน 50%", mc4["p_dd50"], mc3["p_dd50"], -1, lambda v: f"{v:.1%}"),
            ("สุ่ม 10 ปี: DD มัธยฐาน", mc4["dd_median"], mc3["dd_median"], -1, lambda v: f"{v:.0%}"),
            ("สุ่ม 10 ปี: ผลตอบแทนมัธยฐาน", mc4["cagr_median"], mc3["cagr_median"], 1, lambda v: f"{v:.1%}")]

    def cell(v, other, w, f):
        win = w != 0 and f(v) != f(other) and ((v > other) == (w > 0))
        return f'<td class="n{" win" if win else ""}">{f(v)}</td>'

    table = ('<table class="cmp"><thead><tr><th></th><th class="n"><span class="sw" style="background:var(--s-bk)"></span>4 ตลาด</th>'
             '<th class="n"><span class="sw" style="background:var(--s-nb)"></span>3 ตลาด</th></tr></thead><tbody>'
             + "".join(f"<tr><td style='white-space:normal'>{l}</td>{cell(a, b, w, f)}{cell(b, a, w, f)}</tr>" for l, a, b, w, f in rows)
             + "</tbody></table><p class='muted small' style='margin:8px 0 0'>ตัวหนา = ฝั่งที่ดีกว่าในข้อนั้น · เวอร์ชันเบรก 25% ทั้งคู่ · “สุ่ม 10 ปี” = Monte Carlo จากผลรายเดือน</p>")
    y4 = {y["year"]: y for y in e4["yearly"]}
    y3 = {y["year"]: y for y in e3["yearly"]}
    yj = {y["year"]: y for y in e4.get("jp_yearly", [])}
    yt = ('<table class="cmp"><thead><tr><th>ปี</th><th class="n">4 ตลาด</th><th class="n">3 ตลาด</th><th class="n">ต่าง (จุด)</th></tr></thead><tbody>'
          + "".join(f"<tr><td>{y}</td><td class='n {'pos' if y4[y]['ret'] >= 0 else 'neg'}'>{y4[y]['ret']:+.0%}</td>"
                    f"<td class='n {'pos' if y3[y]['ret'] >= 0 else 'neg'}'>{y3[y]['ret']:+.0%}</td>"
                    f"<td class='n'>{(y4[y]['ret'] - y3[y]['ret']) * 100:+.0f}</td></tr>" for y in sorted(y4) if y in y3)
          + "</tbody></table>")
    summary = (f"<p class='cmp-sum'>เพิ่ม JP225 แล้ว <b>ผลตอบแทน {e3['cagr']:.1%} → {e4['cagr']:.1%} ต่อปี</b> และ "
               f"<b>Equity DD สูงสุด {e3['equity_dd']['relative_pct']:.0%} → {e4['equity_dd']['relative_pct']:.0%}</b> · "
               f"JP225 แทบไม่ขยับตาม 3 ตลาดเดิม (correlation รายเดือน {corr:+.2f}) · "
               f"JP225 ถูกเลือกหลังเห็นผลแล้ว ตัวเลขนี้จึงยืนยันอนาคตไม่ได้</p>")
    html = (RB.CMP_CSS + '<section class="card"><h2>4 ตลาด (เพิ่ม JP225) เทียบ 3 ตลาด · เบรก 25%</h2>' + summary +
            '<div class="legend" style="margin-bottom:6px"><span><i style="background:var(--s-bk)"></i>4 ตลาด (+JP225)</span>'
            '<span><i style="background:var(--s-nb)"></i>3 ตลาด</span><span class="muted">Balance สิ้นเดือน · สเกล log</span></div>'
            '<div id="cmpChart" class="chart"></div></section>'
            '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
            '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>')
    return html, script


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
    H1 = {m: MMS.load(m, G) for m in M4}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(M4, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    systems = {"B4": rows, "B3": [r for r in rows if r["mkt"] in M3]}
    RWF.UNIS.update(MET4=list(M4), MET3=list(M3), JP225=["JP225"])
    unis = {"B4": ["MET4", "MET3", "XAUUSD", "XAGUSD", "BTCUSD", "JP225"], "B3": ["MET3", "XAUUSD", "XAGUSD", "BTCUSD"]}
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

    # Monte Carlo of the brake and normal versions (10-year paths from monthly returns)
    mc = {}
    for s in systems:
        for v in ("brake", "normal"):
            T = pd.DataFrame(dict(mkt=[r["mkt"] for r in systems[s]], t=[r["t"] for r in systems[s]],
                                  tx=[r["t_exit"] for r in systems[s]], R=[r["R"] for r in systems[s]],
                                  vp=[r["vp"] for r in systems[s]], sc=[r["sc"] for r in systems[s]]))
            _, eq, _ = SU.simulate(T, v, START, END, news=news)
            mc[(s, v)] = SU.monte_carlo(eq)

    S, E = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    me, c4 = monthly(RWF.account_var(sized[("B4", "brake")]), S, E)
    _, c3 = monthly(RWF.account_var(sized[("B3", "brake")]), S, E)
    curves = [(d, float(x), float(y)) for d, x, y in zip(me, c4, c3)]
    j = [r for r in systems["B4"] if r["mkt"] == "JP225"]
    b = [r for r in systems["B3"]]
    mon = lambda rs: pd.Series([r["R"] for r in rs], index=pd.to_datetime([r["t_exit"] for r in rs], unit="s")).resample("ME").sum()
    cj, cb = mon(j), mon(b)
    idx = cj.index.union(cb.index)
    corr = float(np.corrcoef(cj.reindex(idx, fill_value=0), cb.reindex(idx, fill_value=0))[0, 1])
    cmp_html, cmp_js = compare(out["B4~brake_MET4"], out["B3~brake_MET3"], mc[("B4", "brake")], mc[("B3", "brake")],
                               curves, START, corr)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้"]
    jm = out.get("B4~normal_JP225", {})
    info = {
        "B4": dict(label="G27K #1 · 4 ตลาด (ทอง เงิน BTC JP225)", tab="4 ตลาด +JP225", combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01,
                   adds=False, tf="H4", risk_note=RSD.RISK_NOTE["brake"], risk_notes=RSD.RISK_NOTE,
                   rules=g_rules + ["ตลาด: ทอง เงิน BTC และ Nikkei 225 (JP225) · เปิดพร้อมกันได้สูงสุด 4 ไม้"],
                   notes=[f"<b>JP225 ถูกเลือกหลังเห็นผลทั้ง 16 ตลาดแล้ว</b> (ดีเป็นอันดับ 3 รองจาก BTC และทอง) ตัวเลขช่วงนี้จึงยืนยันไม่ได้ว่าจะดีต่อ · ลงทะเบียนไว้เป็น forward test (ledger g27k_b_plus_jp225)",
                          f"<b>JP225 แทบไม่ขยับตาม 3 ตลาดเดิม</b> (correlation ผลรายเดือน {corr:+.2f}) จึงช่วยกระจายความเสี่ยง · ได้มากช่วงปี 2012–2013 (Abenomics) ตอนที่โลหะเป็นขาลง",
                          "<b>เช็คก่อนใช้จริง:</b> บัญชี Standard Cent อาจไม่มีดัชนีหุ้น · ค่า swap ของ JP225 ในข้อมูลโบรกเกอร์ที่ใช้คำนวณเป็นศูนย์ ควรตรวจค่าจริงใน MT5"]),
        "B3": dict(label="G27K #1 · 3 ตลาด (ทอง เงิน BTC)", tab="3 ตลาด", combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01,
                   adds=False, tf="H4", risk_note=RSD.RISK_NOTE["brake"], risk_notes=RSD.RISK_NOTE, rules=g_rules,
                   notes=["ระบบเดิมที่ใช้อยู่ · ช่วงนี้เริ่ม ก.ย. 2011 ให้ตรงกับข้อมูล JP225 จึงต่างจากรายงาน 17 ปีที่เริ่ม ก.ย. 2009"]),
    }
    wf = {s: dict(patterns=[], pat_note="", pat_empty="กฎตายตัว G27K #1 กฎเดียว", log=[], log_note="",
                  log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า") for s in systems}
    last = E - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S.day} {TH_M[S.month - 1]} {S.year} – {last.day} {TH_M[last.month - 1]} {last.year}",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · JP225: Dukascopy H1 · BTC: Binance ตั้งแต่ ส.ค. 2017 · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>ตัวเลขทั้งหน้านี้คือบัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> (เดือนแรกที่มีข้อมูล JP225) จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap จริงของโบรกเกอร์",
                                     "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> ช่วงนั้นจึงดีเกินจริงทั้ง 3 และ 4 ตลาด"],
                       footer="สร้างจาก research/g27k_dev/report_jp225.py · ledger: g27k_b_plus_jp225 · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · คำนวณ 3 ต.ค. 2026")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>G27K 4 ตลาด +JP225</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K 4 ตลาด"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "เพิ่ม JP225 เป็นตลาดที่ 4 · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>',
         '<button role="tab" data-u="MET4">4 ตลาด</button>\n        <button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>'),
        ('<button role="tab" data-u="BTCUSD">BTC</button>', '<button role="tab" data-u="BTCUSD">BTC</button>\n        <button role="tab" data-u="JP225">JP225</button>'),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "brake";\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3:', 'const UNI_TH = {MET4: "4 ตลาด: ทอง เงิน บิตคอยน์ JP225", JP225: "Nikkei 225 (JP225) ตลาดเดียว", MET3:'),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "MET4"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         'const fixUni = () => { if (!D[keyOf(SYS, UNI)]) UNI = ["MET4", "MET3", "XAUUSD", "XAGUSD", "BTCUSD", "JP225"].find(u => D[keyOf(SYS, u)]); };\n'
         'try { const vv = localStorage.getItem("jpver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("jpver", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for s in systems:
        for v in VERS:
            u = "MET4" if s == "B4" else "MET3"
            m = out[f"{s}~{v}_{u}"]
            print(f"  {s} {v:7s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} balDD {m['balance_dd']['relative_pct']:.1%} "
                  f"PF {m['pf']:.2f} trades {m['trades']}")
    print("  MC", {f"{k[0]}-{k[1]}": round(v["p_dd50"], 3) for k, v in mc.items()}, f"corr {corr:+.2f}")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
