#!/usr/bin/env python3
"""Adding weakly profitable markets to the five-market G27K #1 system, in the
G27K Strategy-Tester layout. Systems: S5; S5 + USDZAR, USTEC (1%); S5 + five
weak markets (USDZAR, USTEC, GBPJPY, CHFJPY, EURJPY) at 1%; the same at 0.5%.
A comparison section on top (balance, numbers, years, and the same four with
every trade 0.10R worse), then version and market tabs. 2011-09..2026-09.

Usage: python3 research/g27k_dev/report_weak.py --root <snap> --out <html>
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
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_five as R5
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, MID, END = "2011-09-01", "2018-01-01", "2026-10-01"
S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
W2 = ("USDZAR", "USTEC")
W5 = W2 + ("GBPJPY", "CHFJPY", "EURJPY")
SYS = {"A": ("5 ตลาด", S5, 1.0), "B": ("+USDZAR, USTEC", S5 + W2, 1.0), "C": ("+กำไรน้อย 5 ตัว 1%", S5 + W5, 1.0),
       "D": ("+กำไรน้อย 5 ตัว 0.5%", S5 + W5, 0.5)}
VERS = {"brake": "เบรก 25%", "normal": "ปกติ 1%", "monitor": "AI monitor"}
TH = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC"}


def frame(rows, scale, extra=0.0):
    return pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[r["t"] for r in rows], tx=[r["t_exit"] for r in rows],
                             R=[(r["R"] - extra) * scale.get(r["mkt"], 1.0) for r in rows], vp=[r.get("vp", 0.0) for r in rows],
                             sc=[r.get("sc", r["t"]) for r in rows]))


def sized(rows, version, news, scale):
    """Like report_suite_detail.sized, with the weak markets traded at a fraction of the risk: the account path is
    simulated with their R scaled, and each row keeps its own R with the scaled risk fraction."""
    _, _, risk = SU.simulate(frame(rows, scale), version, START, news=news)
    return [dict(r, risk_frac=float(risk.get(j, 0.0)) * scale.get(r["mkt"], 1.0)) for j, r in enumerate(rows) if risk.get(j, 0.0) > 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    allm = S5 + W5
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in allm}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(allm, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    port = {s: "P" + s for s in SYS}
    RWF.UNIS.update({port[s]: list(ms) for s, (_, ms, _) in SYS.items()}, **{m: [m] for m in allm})
    out, sized_rows, stress, mc, halves = {}, {}, {}, {}, {}
    for s, (label, ms, w) in SYS.items():
        rr = [r for r in rows if r["mkt"] in ms]
        scale = {m: (w if m not in S5 else 1.0) for m in ms}
        for v in VERS:
            vr = sized(rr, v, news, scale)
            sized_rows[(s, v)] = vr
            for u in [port[s], *ms]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, 0.01, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
        for extra in (0.0, 0.10):
            st, eq, _ = SU.simulate(frame(rr, scale, extra), "brake", START, END, news=news)
            a1, _, _ = SU.simulate(frame(rr, scale, extra), "brake", START, MID, news=news)
            a2, _, _ = SU.simulate(frame(rr, scale, extra), "brake", MID, END, news=news)
            m_ = SU.monte_carlo(eq)
            stress[(s, extra)] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], h1=a1["mar"], h2=a2["mar"], p50=m_["p_dd50"])
            if extra == 0.0:
                mc[s], halves[s] = m_, (a1["mar"], a2["mar"])
        print(f"  {s} {label} done  {time.time() - t0:.0f}s", flush=True)

    S_, E_ = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    cur = {}
    for s in SYS:
        me, cur[s] = RJ.monthly(RWF.account_var(sized_rows[(s, "brake")]), S_, E_)
    curves = [(d, [cur[s][i] for s in SYS]) for i, d in enumerate(me)]
    E = {s: out[f"{s}~brake_{port[s]}"] for s in SYS}
    keys = list(SYS)
    name = {s: SYS[s][0] for s in SYS}
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    rws = [("เงินสุดท้าย (เริ่ม $100,000)", lambda s: E[s]["final"], 1, lambda v: f"${v:,.0f}"),
           ("ผลตอบแทนทบต้นต่อปี", lambda s: E[s]["cagr"], 1, lambda v: f"{v:.1%}"),
           ("Equity DD สูงสุด", lambda s: E[s]["equity_dd"]["relative_pct"], -1, lambda v: f"{v:.1%}"),
           ("MAR (ต่อปี ÷ Equity DD)", lambda s: mar(E[s]), 1, lambda v: f"{v:.2f}"),
           ("MAR ปี 2011–2017 (balance)", lambda s: halves[s][0], 1, lambda v: f"{v:+.2f}"),
           ("MAR ปี 2018–2026 (balance)", lambda s: halves[s][1], 1, lambda v: f"{v:+.2f}"),
           ("ปีที่แย่สุด", lambda s: worst(E[s])["ret"], 1, lambda v: f"{v:+.0%}"),
           ("จำนวนไม้", lambda s: E[s]["trades"], 0, lambda v: f"{v:,}"),
           ("สุ่ม 10 ปี: โอกาส DD เกิน 50%", lambda s: mc[s]["p_dd50"], -1, lambda v: f"{v:.1%}")]

    def tr(label, get, w, f):
        vals = {s: get(s) for s in keys}
        best = (max if w > 0 else min)(vals.values()) if w else None
        return f"<tr><td>{label}</td>" + "".join(f'<td class="n{" win" if w and f(v) == f(best) else ""}">{f(v)}</td>' for v in vals.values()) + "</tr>"
    head = "".join(f'<th class="n"><span class="sw" style="background:var(--c{i + 1})"></span>{name[s]}</th>' for i, s in enumerate(keys))
    table = f'<table class="cmp"><thead><tr><th></th>{head}</tr></thead><tbody>' + "".join(tr(*r) for r in rws) + "</tbody></table>"
    st_rows = [("ต่อปี", "cagr", 1, lambda v: f"{v:+.1%}"), ("DD (balance)", "dd", -1, lambda v: f"{v:.1%}"), ("MAR", "mar", 1, lambda v: f"{v:.2f}"),
               ("MAR ปี 2011–2017", "h1", 1, lambda v: f"{v:+.2f}"), ("MAR ปี 2018–2026", "h2", 1, lambda v: f"{v:+.2f}"),
               ("โอกาส DD เกิน 50%", "p50", -1, lambda v: f"{v:.1%}")]
    stress_html = ""
    for extra, lab in ((0.0, "ต้นทุนตามโมเดล"), (0.10, "ต้นทุนจริงแย่ลง 0.10R ทุกไม้ (ทุกตลาด)")):
        body = ""
        for l, k_, w, f in st_rows:
            vals = {s: stress[(s, extra)][k_] for s in keys}
            best = (max if w > 0 else min)(vals.values())
            body += f"<tr><td>{l}</td>" + "".join(f'<td class="n{" win" if f(v) == f(best) else ""}">{f(v)}</td>' for v in vals.values()) + "</tr>"
        stress_html += f"<h3 style='margin:12px 0 6px;font-size:15px'>{lab}</h3><table class='cmp'><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>"
    Y = {s: {y["year"]: y["ret"] for y in E[s]["yearly"]} for s in keys}
    years = sorted(set.intersection(*(set(Y[s]) for s in keys)))
    yt = (f'<table class="cmp"><thead><tr><th>ปี</th>{"".join(f"<th class=n>{name[s]}</th>" for s in keys)}</tr></thead><tbody>'
          + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {'pos' if Y[s][y] >= 0 else 'neg'}'>{Y[s][y]:+.0%}</td>" for s in keys) + "</tr>" for y in years)
          + "</tbody></table>")
    perm = []
    for m in W5:
        x = [r for r in rows if r["mkt"] == m]
        R = np.array([r["R"] for r in x])
        perm.append(f"<tr><td>{m}</td><td class='n'>{len(R)}</td><td class='n {'pos' if R.mean() > 0 else 'neg'}'>{R.mean():+.3f}</td>"
                    f"<td class='n {'pos' if R.mean() - 0.1 > 0 else 'neg'}'>{R.mean() - 0.1:+.3f}</td><td class='n'>{'Cent + Standard' if m in ('USTEC',) or m.endswith('JPY') else 'Standard'}</td></tr>")
    perm_t = ("<table class='cmp'><thead><tr><th>ตลาด</th><th class='n'>ไม้</th><th class='n'>R/ไม้</th><th class='n'>แย่ลง 0.10R</th><th class='n'>บัญชี</th></tr></thead><tbody>"
              + "".join(perm) + "</tbody></table>")
    s0, s1, s2 = stress[("A", 0.10)], stress[("B", 0.10)], stress[("C", 0.10)]
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>เพิ่ม USDZAR และ USTEC</b>: MAR {mar(E['A']):.2f} → {mar(E['B']):.2f} และ Equity DD {E['A']['equity_dd']['relative_pct']:.0%} → {E['B']['equity_dd']['relative_pct']:.0%} · "
               f"ถ้าต้นทุนแย่ลง 0.10R ยังดีกว่า 5 ตลาดเดิมเล็กน้อย (MAR {s0['mar']:.2f} → {s1['mar']:.2f}) แต่โอกาส DD เกิน 50% เป็น {s1['p50']:.1%}</li>"
               f"<li><b>เพิ่มตลาดกำไรน้อยทั้ง 5 ตัว</b>: แย่ลงแม้ต้นทุนปกติ และพังเมื่อต้นทุนแย่ลง (MAR {s2['mar']:.2f}, โอกาส DD เกิน 50% {s2['p50']:.0%})</li>"
               "<li><b>หลัก</b>: ตลาดที่จะเพิ่มควรกำไรเกินต้นทุนจริงชัดเจน (ราว 0.15–0.2R ต่อไม้ขึ้นไปหลังต้นทุน) ตัวที่บางกว่านี้เพิ่มไม้และความเสี่ยงโดยไม่คุ้ม</li>"
               "<li><b>USDZAR และ USTEC ถูกเลือกหลังเห็นผล</b> (hindsight บางส่วน) หลักฐานรายตลาดยังอ่อน (t ประมาณ 1.1) ควรเริ่มที่ forward test หรือความเสี่ยงต่ำ</li></ul>")
    pts = [dict(x=START, lab="เริ่ม " + START, **{s: float(W.DEPOSIT) for s in keys})]
    for d, vals in curves:
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", **{s: float(v) for s, v in zip(keys, vals)}))
    short = {"A": "5 ตลาด", "B": "+ZAR,TEC", "C": "+5 ตัว 1%", "D": "+5 ตัว 0.5%"}
    data = json.dumps(dict(pts=pts, keys=keys, names=[short[s] for s in keys]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{name[s]}</span>' for i, s in enumerate(keys))
    cmp_html = (R5.CSS + '<section class="card"><h2>เพิ่มตลาดที่กำไรน้อยแต่ยังบวก · เบรก 25%</h2>' + summary +
                f'<div class="legend" style="margin-bottom:6px">{legend}<span class="muted">Balance สิ้นเดือน · สเกล log</span></div><div id="cmpChart" class="chart"></div></section>'
                '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
                '<section class="card"><h2>ตลาดที่เพิ่ม (G27K #1 ต่อไม้ ปี 2011–2026)</h2><div class="tbl">' + perm_t + '</div></section></div>'
                '<div class="cmp-grid"><section class="card"><h2>ถ้าต้นทุนจริงแย่กว่าโมเดล</h2><div class="tbl">' + stress_html + '</div></section>'
                '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>')
    cmp_js = R5.SCRIPT.replace("__DATA__", data)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้"]
    info = {}
    for s, (label, ms, w) in SYS.items():
        extra_note = [] if s == "A" else [f"<b>ตลาดที่เพิ่ม:</b> {', '.join(m for m in ms if m not in S5)} · ความเสี่ยง {w:.1%} ต่อไม้ (5 ตลาดเดิม 1%)",
                                          "swap ของ GBPJPY, CHFJPY, EURJPY เป็นค่าสมมติ (1 bp/คืน) · USDZAR และ USTEC ใช้สเปกจริงของโบรก"]
        info[s] = dict(label=f"G27K #1 · {label}", tab=label, rules=g_rules + [f"ตลาด: {', '.join(ms)}"], notes=extra_note or ["ระบบหลักปัจจุบัน 5 ตลาด"],
                       combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01, adds=False, tf="H4", risk_note=RSD.RISK_NOTE["brake"], risk_notes=RSD.RISK_NOTE)
    wf = {s: dict(patterns=[], pat_note="", pat_empty="กฎตายตัว G27K #1 กฎเดียว", log=[], log_note="",
                  log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า") for s in SYS}
    last = E_ - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S_.day} {RJ.TH_M[S_.month - 1]} {S_.year} – {last.day} {RJ.TH_M[last.month - 1]} {last.year}",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · ตลาดอื่น: Dukascopy H1 · BTC: Binance · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>บัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap",
                                     "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> และตลาดที่เพิ่มถูกเลือกหลังเห็นผล ตัวเลขจึงดีเกินจริงบางส่วน",
                                     "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ตของระบบนั้น"],
                       footer="สร้างจาก research/g27k_dev/report_weak.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    ulist = [port[s] for s in SYS] + list(allm)
    uni_th = {port[s]: f"พอร์ต {SYS[s][0]}" for s in SYS}
    uni_th.update({m: f"{TH.get(m, m)} ({m}) ตลาดเดียว" for m in allm})
    pbtn = "\n        ".join(f'<button role="tab" data-u="{port[s]}">พอร์ต {SYS[s][0]}</button>' for s in SYS)
    mbtn = "\n        ".join(f'<button role="tab" data-u="{m}">{TH.get(m, m)}</button>' for m in allm if m not in ("XAUUSD", "XAGUSD", "BTCUSD"))
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>G27K เพิ่มตลาดกำไรน้อย</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K เพิ่มตลาด"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "เพิ่มตลาดที่กำไรน้อยแต่ยังบวก · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>', pbtn),
        ('<button role="tab" data-u="BTCUSD">BTC</button>', '<button role="tab" data-u="BTCUSD">BTC</button>\n        ' + mbtn),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "brake";\nconst PORTS = ' + json.dumps(port) + ';\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์", XAUUSD: "ทอง (XAUUSD) ตลาดเดียว", XAGUSD: "เงิน (XAGUSD) ตลาดเดียว", BTCUSD: "บิตคอยน์ (BTCUSD) ตลาดเดียว"};',
         "const UNI_TH = " + json.dumps(uni_th, ensure_ascii=False) + ";"),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "PA"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         f'const fixUni = () => {{ if (!D[keyOf(SYS, UNI)]) UNI = {json.dumps(ulist)}.find(u => D[keyOf(SYS, u)]); }};\n'
         'try { const vv = localStorage.getItem("weakver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("weakver", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for s in SYS:
        m = E[s]
        print(f"  {s} {SYS[s][0]:22s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} MAR {mar(m):.2f} trades {m['trades']} | "
              f"stress MAR {stress[(s, 0.1)]['mar']:.2f} p50 {stress[(s, 0.1)]['p50']:.1%}")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
