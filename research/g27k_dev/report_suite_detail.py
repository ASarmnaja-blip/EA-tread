#!/usr/bin/env python3
"""Every suite system in the G27K Strategy-Tester layout, 17 years, with a
version switch (normal 1%, brake 25%, AI monitor, 0.5%) and a 16-market tab.

Trades come from the same engines as suite.py (report768.sim_paths for
G27K, the search engine's events for searched patterns), sizing from
suite.simulate, and every metric from report768.metrics.

Usage: python3 research/g27k_dev/report_suite_detail.py --root <data-snapshot checkout> --out <html>
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
import intraday_pattern_search as IP
import per_market_search as PMS
import multi_market_search as MMS
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START = SU.WINDOWS["17y"]
VERS = {"normal": "ปกติ 1%", "brake": "เบรก 25%", "monitor": "AI monitor"}   # 0.5% is the risk table's 0.5% row
RISK_NOTE = {"normal": "1% ทุกไม้", "half": "0.5% ทุกไม้",
             "brake": "1% · balance DD ถึง 25% → 0.5% · กลับ 1% เมื่อ DD ไม่เกิน 12.5%",
             "monitor": "1% × DD 15%→×0.5, 25%→×0.25 · แพ้ติด 8 ไม้ → ×0.5 · ATR สุดขั้ว → ×0.5 · ใกล้ข่าว → ×0.5 · รวมเปิดไม่เกิน 6%"}


def g27k_rows(mkts, H1, RP, G, K, ext):
    K.START = W.ts(START)
    rows = []
    for m in mkts:
        Mk = K.prepare(m, H1[m], ext)
        X = G.features(G.frames(H1[m]), m, "H4")
        X["sec"] = 14400
        P.FRAMES[(m, "H4")] = X
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        vp = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        for tr in RP.sim_paths(X, m, idx, d[idx], "I1"):
            rows.append(dict(tr, X=X, vp=float(vp[max(tr["e"] - 1, 0)]), sc=int(tr["t"])))
    return rows


def pattern_rows(c, H1, mkts, trade_mkts):
    """Report rows of one searched pattern over the whole history."""
    minute = c["tf"] in ("M15", "M30")
    if minute:                                  # minute patterns rebuild on M1 bars of their own market
        old = P._M.get("frames_for")
        P._M["frames_for"] = IP.frames_minute
        E, feats, cats = P.build({x: PMS.load_m1(x) for x in trade_mkts}, c["tf"])
        if old is None:
            P._M.pop("frames_for")
        else:
            P._M["frames_for"] = old
    else:
        E, feats, cats = P.build({m: H1[m] for m in mkts}, c["tf"])
    m = W.pmask(feats, cats, [W.parse(n) for n in c["names"]]) & P.scope_mask(E, c["scope"]) & np.isfinite(E[f"R_{c['exit']}"])
    m &= np.isin(E["mkt"], list(trade_mkts))
    k = P.no_overlap(E, m, c["exit"])
    sec = P.TF_SEC[c["tf"]]
    ex = c["exit"]
    raw = [dict(mkt=str(E["mkt"][i]), tf=c["tf"], ex=ex, i=int(i), t=int(E["t"][i]) + sec, t_exit=int(E[f"tx_{ex}"][i]),
                R=float(E[f"R_{ex}"][i]), d=int(E["d"][i]), vp=float(feats["atr_pct"][i]), sc=int(E["t"][i]) + sec)
           for i in k if E["t"][i] + sec >= W.ts(START)]
    rows = RWF.add_excursions(W.to_report_rows(raw, {c["tf"]: (E, feats, cats)}))
    return rows


def sized(rows, version, news):
    T = pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[r["t"] for r in rows], tx=[r["t_exit"] for r in rows],
                          R=[r["R"] for r in rows], vp=[r.get("vp", 0.0) for r in rows], sc=[r.get("sc", r["t"]) for r in rows]))
    _, _, risk = SU.simulate(T, version, START, news=news)
    out = []
    for j, r in enumerate(rows):
        rf = float(risk.get(j, 0.0))
        if rf > 0:
            out.append(dict(r, risk_frac=rf))
    return out


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
    W.SEC.update(P.TF_SEC)
    H1 = {m: MMS.load(m, G) for m in MMS.MARKETS}
    P._M["h1"] = H1
    G.START = W.ts(START)
    ext = K.externals()
    news = W.news_times(a.root)
    RWF.UNIS["ALL16"] = list(MMS.MARKETS)
    g = g27k_rows(MMS.MARKETS, H1, RP, G, K, ext)
    systems = {"A": [r for r in g if r["mkt"] == "XAUUSD"], "B": [r for r in g if r["mkt"] in SU.TARGET], "B16": g}
    pk = SU.picks()
    names = {}
    if all(m in pk for m in SU.TARGET):
        systems["PM"] = sum((pattern_rows(pk[m], H1, SU.TARGET, [m]) for m in SU.TARGET), [])
        names["PM"] = " · ".join(f"{m}: {pk[m]['tf']} {pk[m]['exit']} {' & '.join(pk[m]['names'])}" for m in SU.TARGET)
    for key, src, mk in (("POOL3", "POOL3", SU.TARGET), ("ALL16", "ALL16", MMS.MARKETS)):
        if src in pk and pk[src]["tf"] in ("H1", "H4", "D1"):
            systems[key] = pattern_rows(pk[src], H1, mk, mk)
            names[key] = f"{pk[src]['tf']} {pk[src]['exit']} {' & '.join(pk[src]['names'])}"
    print("  rows: " + ", ".join(f"{k} {len(v)}" for k, v in systems.items()) + f"  {time.time() - t0:.0f}s", flush=True)

    out = {}
    unis = {"A": ["XAUUSD"], "B": ["MET3", "XAUUSD", "XAGUSD", "BTCUSD"], "B16": ["ALL16", "MET3", "XAUUSD", "XAGUSD", "BTCUSD"],
            "PM": ["MET3", "XAUUSD", "XAGUSD", "BTCUSD"], "POOL3": ["MET3", "XAUUSD", "XAGUSD", "BTCUSD"],
            "ALL16": ["ALL16", "MET3", "XAUUSD", "XAGUSD", "BTCUSD"]}
    for s, rows in systems.items():
        for v in VERS:
            vr = sized(rows, v, news)
            for u in unis[s]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, 0.005 if v == "half" else 0.01, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
        print(f"  {s} done  {time.time() - t0:.0f}s", flush=True)

    TH = {"A": ("G27K #1 · ทอง", "G27K #1 ทอง"), "B": ("G27K #1 · ทอง เงิน BTC", "G27K #1 3 ตลาด"),
          "B16": ("G27K #1 · 16 ตลาด", "G27K #1 16 ตลาด"), "PM": ("รูปแบบดีที่สุดรายตลาด", "ดีสุดรายตลาด"),
          "POOL3": ("รูปแบบเดียว ค้นจาก 3 ตลาด", "รูปแบบ 3 ตลาด"), "ALL16": ("รูปแบบเดียว ค้นจาก 16 ตลาด", "รูปแบบ 16 ตลาด")}
    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้"]
    info, wf = {}, {}
    for s in systems:
        searched = s in ("PM", "POOL3", "ALL16")
        info[s] = dict(label=TH[s][0], tab=TH[s][1], combo=names.get(s, "C8/D3/E1/F1/G2/H2/I1/J1"), risk=0.01, adds=False,
                       tf="H1–D1" if searched else "H4", risk_note=RISK_NOTE["normal"], risk_notes=RISK_NOTE,
                       rules=(["รูปแบบจากการค้นอิสระ: " + names[s], "SL 2 × ATR20 · ออกตามวิธีออกของรูปแบบ · ตลาดละ 1 ไม้"]
                              if searched else g_rules),
                       notes=(["<b>รูปแบบนี้ค้นจากข้อมูลก่อนปี 2018 (BTC ก่อนปี 2021/2024)</b> ผลช่วงนั้นเป็นข้อมูลที่ใช้เลือก จึงดีเกินจริงแน่นอน · ดูรายปีตั้งแต่ 2018 เพื่อดูผลจริง"]
                              if searched else ["<b>G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> ช่วงนั้นจึงดีเกินจริง"]))
        wf[s] = dict(patterns=[], pat_note="", pat_empty=("กฎตายตัวกฎเดียว" if not searched else "รูปแบบที่ใช้: " + names[s]),
                     log=[], log_note="", log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า")
    TH_M = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS, period_th="17 ปี 1 ก.ย. 2009 – 30 ก.ย. 2026",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · ตลาดอื่น: Dukascopy H1 · BTC: Binance ตั้งแต่ ส.ค. 2017 · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>ตัวเลขทั้งหน้านี้คือบัญชีเดียวต่อเนื่อง เริ่ม $100,000</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap จริงของโบรกเกอร์",
                                     "<b>ตลาดเริ่มไม่พร้อมกัน:</b> ดัชนีและน้ำมันจาก ก.ย. 2011, ทองแดง มี.ค. 2012, USDCNH มิ.ย. 2012, DAX ก.ย. 2013, BTC ส.ค. 2017"],
                       footer="สร้างจาก research/g27k_dev/report_suite_detail.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · คำนวณ 2 ต.ค. 2026")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>รายละเอียดทุกระบบ G27K</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · Backtest suite"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "รายละเอียดทุกระบบ · 17 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">', '<button role="tab" data-u="ALL16">16 ตลาด</button>\n        <button role="tab" data-u="MET3">'),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "normal";\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3:', 'const UNI_TH = {ALL16: "16 ตลาด", MET3:'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         'const fixUni = () => { if (!D[keyOf(SYS, UNI)]) UNI = ["MET3", "ALL16", "XAUUSD", "XAGUSD", "BTCUSD"].find(u => D[keyOf(SYS, u)]); };\n'
         'try { const vv = localStorage.getItem("stver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("stver", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y)
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
