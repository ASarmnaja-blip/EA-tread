#!/usr/bin/env python3
"""Ten-year walk-forward results in the G27K Strategy-Tester layout.

Four systems on 2016-10-01..2026-09-30, the same hybrid data and cost model:
  W2  the round-2 controller (forward-only, decides as it goes)
  W1  round-1 rules
  ND  every pattern round 2 adopted, traded with no decisions
  G1  G27K #1 (C8/D3/E1/F1/G2/H2/I1/J1, 1%), for comparison
Each in four universes (three markets, gold, silver, BTC), with every
metric computed by the G27K report's own report768.metrics.

Usage: python3 report_walkforward10y.py --root <data-snapshot checkout> --out <html>
"""
import argparse
import heapq
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import h4d1_pattern_search as P
import walkforward_controller as W
import walkforward_round2 as W2
import walkforward_10y as W10

UNIS = {"MET3": ["XAUUSD", "XAGUSD", "BTCUSD"], "XAUUSD": ["XAUUSD"], "XAGUSD": ["XAGUSD"], "BTCUSD": ["BTCUSD"]}


def add_excursions(rows):
    for r in rows:
        X, d, ep, rk = r["X"], r["d"], r["ep"], r["risk"]
        b = X["b"]
        q0 = int(X["k0"][r["e"]])
        q1 = int(np.searchsorted(b["t"], r["t_exit"], side="right"))
        if q1 <= q0:
            q1 = q0 + 1
        hi, lo = float(np.max(b["h"][q0:q1])), float(np.min(b["l"][q0:q1]))
        r["mfe"] = max(0.0, (hi - ep) / rk if d > 0 else (ep - lo) / rk)
        r["mae"] = max(0.0, (ep - lo) / rk if d > 0 else (hi - ep) / rk)
    return rows


def account_var(rows, scale=1.0, deposit=W.DEPOSIT):
    """Like report768.account, but every trade keeps its own risk fraction
    (the controller sized each one), optionally scaled."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["t"], rows[i]["mkt"]))
    bal, heap, live, out = deposit, [], {}, []
    for i in order:
        tr = rows[i]
        while heap and heap[0][0] <= tr["t"]:
            _, k = heapq.heappop(heap)
            r = live.pop(k)
            bal += r["pnl"]
            out.append(r)
        rf = tr["risk_frac"] * scale
        live[i] = dict(tr, unit_usd=rf * bal, pnl=rf * bal * tr["R"], bal_before=bal)
        heapq.heappush(heap, (tr["t_exit"], i))
    while heap:
        _, k = heapq.heappop(heap)
        out.append(live.pop(k))
    out.sort(key=lambda r: (r["t_exit"], r["t"]))
    b = deposit
    for r in out:
        b += r["pnl"]
        r["bal_after"] = b
    return out


def timeline(rows, mkts, G):
    Xs = [P.FRAMES[(m, "H4")] for m in mkts if (m, "H4") in P.FRAMES]
    for X in Xs:
        X["sec"] = 14400
    T = np.unique(np.concatenate([X["t"] + 14400 for X in Xs] + [np.array([r["t_exit"] for r in rows])]))
    return T[(T >= G.START) & (T <= max(r["t_exit"] for r in rows))]


def clean(o):
    if isinstance(o, float):
        return None if not np.isfinite(o) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return clean(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def build_entry(key, uni, rows, base_risk, fixed_risk, RP, G):
    mk = UNIS[uni]
    sub = [r for r in rows if r["mkt"] in mk]
    if len(sub) < 5:
        return None
    acc = RP.account(sub, fixed_risk) if fixed_risk else account_var(sub)
    T = timeline(sub, mk, G)
    RP.prep_marks(acc, T)
    with np.errstate(all="ignore"):
        M = RP.metrics(acc, T, base_risk)
        table = []
        for rk in RP.RISKS:
            a2 = RP.account(sub, rk) if fixed_risk else account_var(sub, rk / base_risk)
            RP.prep_marks(a2, T)
            table.append(RP.metrics(a2, T, rk, full=False))
    sh = [r for r in acc if r["d"] < 0]
    M["short_win"] = float(np.mean([r["pnl"] > 0 for r in sh])) if sh else 0.0
    bars = int(sum(int(((P.FRAMES[(m, "H4")]["t"] >= G.START)).sum()) for m in mk if (m, "H4") in P.FRAMES))
    return dict(key=key, uni=uni, mkts=mk, deposit=W.DEPOSIT, markets=len(mk), bars=bars, risk_table=table, **M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2016-10-01")
    ap.add_argument("--end", default="2026-10-01")
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in W.TFS}
    allref = pickle.loads((HERE / ".cache_wf" / "refits.pkl").read_bytes())
    S, E = pd.Timestamp(a.start, tz="UTC"), pd.Timestamp(a.end, tz="UTC")
    years = round((E - S).days / 365.25)
    TH_M = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    last = E - pd.Timedelta(days=1)
    period_th = f"{years} ปี {S.day} {TH_M[S.month - 1]} {S.year} – {last.day} {TH_M[last.month - 1]} {last.year}"
    dates = [W.ts(d) for d in pd.date_range(S, E - pd.Timedelta(days=1), freq="QS")]
    refits = {D: allref[D] for D in dates}
    news = W.news_times(a.root)
    G.START = int(S.timestamp())
    W.START, W.END = S, E
    W.BASE_RISK = 0.0075

    r2, p2, l2, s2 = W2.run2(B, refits, news, int(E.timestamp()))
    r1, p1, l1, s1 = W.run(B, refits, news, decide=True)
    rn, pn, ln, sn = W.run(B, refits, news, decide=False, fixed=list(p2.values()))
    systems = {"W2": (r2, p2, l2, W2.BASE), "W1": (r1, p1, l1, 0.0075), "ND": (rn, pn, ln, 0.0075)}
    print(f"  simulated  {time.time() - t0:.0f}s", flush=True)

    # G27K #1 on the same data and window
    ext = K.externals()
    K.START = int(S.timestamp())
    g_rows = []
    for m in K.MKTS:
        h1 = P._M["h1"][m]
        Mk = K.prepare(m, h1, ext)
        X = G.features(G.frames(h1), m, "H4")
        X["sec"] = 14400
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        g_rows += [dict(tr, X=X) for tr in RP.sim_paths(X, m, idx, d[idx], "I1")]

    out = {}
    for key, (rows, pats, log, base) in systems.items():
        rr = add_excursions(W.to_report_rows(rows, B))
        for uni in UNIS:
            ent = build_entry(key, uni, rr, base, None, RP, G)
            if ent:
                out[f"{key}_{uni}"] = ent
        print(f"  {key} done  {time.time() - t0:.0f}s", flush=True)
    for uni in UNIS:
        ent = build_entry("G1", uni, g_rows, 0.01, 0.01, RP, G)
        if ent:
            out[f"G1_{uni}"] = ent
    print(f"  G1 done  {time.time() - t0:.0f}s", flush=True)

    def pat_list(pats):
        return [dict(id=p.id, desc=p.desc(), adopted=str(pd.Timestamp(p.t_on, unit="s").date()),
                     retired=str(pd.Timestamp(p.t_off, unit="s").date()) if p.t_off else None,
                     why=p.why_off, live_n=len(p.live), live_R=float(sum(p.live)),
                     disc=dict(n=p.c["disc_n"], R=p.c["disc_R"]), val=dict(n=p.c["val_n"], R=p.c["val_R"]))
                for p in pats.values()]

    def log_list(log):
        return [dict(t=str(pd.Timestamp(l["t"], unit="s").date()), kind=l["kind"], text=l["text"]) for l in log]

    M3 = {k: out[f"{k}_MET3"] for k in ("W2", "W1", "ND", "G1")}
    line = lambda k: (f"{M3[k]['cagr'] * 100:.1f}% ต่อปี, Equity DD {M3[k]['equity_dd']['relative_pct'] * 100:.0f}%")
    common_rules = [f"ทุกต้นไตรมาสค้นรูปแบบใหม่บน H4 และ D1 จากข้อมูลก่อนวันนั้นเท่านั้น ({len(dates)} ครั้งใน {years} ปี)",
                    "รับรูปแบบที่ผ่านทั้งช่วงค้นและช่วงตรวจ 2 ปีล่าสุด ไตรมาสละไม่เกิน 2 รูปแบบ",
                    "SL 2 × ATR20 ไม่ขยับ · ออกตามกติกาของแต่ละรูปแบบ (ช่อง 10/20 แท่ง, Chandelier, ครบ 6 แท่ง หรือ TP 2R)"]
    info = {
        "W2": dict(label="ผมคุมเอง รอบ 2 (เดินหน้า ไม่รู้อนาคต)", tab="ผมคุมเอง รอบ 2", combo="walk-forward round 2", risk=W2.BASE,
                   adds=False, tf="H4 + D1", risk_note="ฐาน 0.5% × จำนวนรูปแบบที่ยืนยัน (สูงสุด 2 เท่า) ลดครึ่งเมื่อใกล้ข่าว/ผันผวนสุดขั้ว/รูปแบบแพ้ติด และตามเบรก DD",
                   rules=common_rules + ["สัญญาณที่หลายรูปแบบตรงกันรวมเป็นไม้เดียว ขนาดเพิ่มตามจำนวนที่ยืนยัน",
                                         "ใกล้ข่าว USD ระดับสูง: ลดขนาดครึ่งหนึ่ง (ไม่ข้าม)",
                                         "ปลดรูปแบบเมื่อเทรดจริง ≥ 20 ไม้ และต่ำกว่าที่คาดเกิน 2.5 SE หรือขาดทุนสะสม −15R",
                                         "เบรก: บัญชี DD 15% → ครึ่งขนาด, 25% → หนึ่งในสี่ กลับเต็มเมื่อ DD ต่ำกว่า 7.5%"],
                   notes=[f"<b>ระบบนี้คือสิ่งที่ผมตัดสินใจเองแบบไม่รู้อนาคต</b> ได้ {line('W2')} เทียบกับ G27K อันดับ 1 ที่ {line('G1')}",
                          "<b>เบรก DD:</b> " + (" · ".join(f"{pd.Timestamp(l['t'], unit='s').date()} {l['text']}" for l in l2 if l['kind'] == 'brake') or "ไม่ทำงานในช่วงนี้")]),
        "W1": dict(label="กฎรอบ 1", tab="กฎรอบ 1", combo="walk-forward round 1", risk=0.0075, adds=False, tf="H4 + D1",
                   risk_note="0.75% ต่อไม้ ลดตามเบรก DD (10% → ครึ่ง, 20% → หนึ่งในสี่) และรูปแบบที่แพ้ติด",
                   rules=common_rules + ["ไม่เกิน 2 ไม้ต่อตลาด ความเสี่ยงรวมไม่เกิน 4%",
                                         "ข้ามไม้ที่ใกล้ข่าว USD ระดับสูง",
                                         "ปลดรูปแบบเมื่อขาดทุนสะสม −8R หรือ 15 ไม้แรกเฉลี่ยต่ำกว่า −0.15R"],
                   notes=[f"<b>กฎชุดแรกที่ผมล็อกไว้ก่อนรัน</b> ได้ {line('W1')} · ปลดรูปแบบเร็วเกินไปจนตัดรูปแบบที่ภายหลังทำกำไร"]),
        "ND": dict(label="รูปแบบชุดเดียวกัน ไม่ตัดสินใจ", tab="ไม่ตัดสินใจ", combo="no decisions", risk=0.0075, adds=False, tf="H4 + D1",
                   risk_note="0.75% ต่อไม้ทุกไม้ ไม่จำกัดจำนวนไม้ ไม่มีเบรก",
                   rules=["ใช้รูปแบบทุกตัวที่รอบ 2 รับเข้ามา ตั้งแต่วันที่รับ และไม่ปลดเลย",
                          "เปิดทุกสัญญาณของทุกรูปแบบ (รูปแบบละ 1 ไม้ต่อตลาด) ไม่ข้ามข่าว ไม่จำกัดความเสี่ยงรวม",
                          "SL 2 × ATR20 ไม่ขยับ · ออกตามกติกาของแต่ละรูปแบบ"],
                   notes=[f"<b>ใช้วัดว่าการตัดสินใจช่วยหรือถ่วง</b> ได้ {line('ND')} · กำไรสูงมาจากการถือหลายไม้ทับกันบนการเคลื่อนไหวเดียวกัน (สูงสุด {M3['ND']['max_positions']} ไม้พร้อมกัน) และติดลบต่อเนื่องปี 2017–2019"]),
        "G1": dict(label="G27K อันดับ 1 ตาม % ต่อปี (เลือกหลังเห็นผล 2021–2026)", tab="G27K อันดับ 1", combo="C8/D3/E1/F1/G2/H2/I1/J1", risk=0.01,
                   adds=False, tf="H4", risk_note="ต่อไม้",
                   rules=["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
                          "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
                          "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง (ไม่มี TP)",
                          "ไม้เดียว ความเสี่ยง 1% ต่อไม้ · ตลาดละ 1 ไม้"],
                   notes=[f"<b>ระบบนี้ถูกเลือกจาก 27,648 แบบโดยเห็นผลปี 2021–2026 แล้ว</b> ช่วงนั้นจึงดีเกินจริง" + (" · ช่วงก่อนปี 2021 ไม่ได้ใช้เลือก" if S.year < 2021 else "") + f" · ช่วงนี้ได้ {line('G1')}"]),
    }
    wf = {}
    for k, (rows, pats, log, base) in systems.items():
        pl = pat_list(pats) if k != "ND" else pat_list(p2)
        wf[k] = dict(patterns=pl, log=log_list(log) if k != "ND" else [],
                     pat_note=(f"{len(pl)} รูปแบบที่ระบบนี้รับเข้ามาระหว่าง {years} ปี · ช่วงค้น/ช่วงตรวจ = สถิติตอนตัดสินใจรับ (ไม้ / R เฉลี่ย) · "
                               "เทรดจริง = ไม้ที่รูปแบบนั้นเกิดสัญญาณหลังรับเข้ามา"),
                     pat_empty="", log_note="ทุกครั้งที่ระบบรับรูปแบบ ปลดรูปแบบ หรือเปลี่ยนขนาดจากเบรก DD เรียงตามเวลา",
                     log_empty="แบบนี้ไม่มีการตัดสินใจระหว่างทาง")
    wf["G1"] = dict(patterns=[], log=[], pat_note="", pat_empty="ระบบนี้เป็นกฎตายตัวกฎเดียว ไม่มีการค้นหรือเปลี่ยนรูปแบบระหว่างทาง",
                    log_note="", log_empty="ไม่มีการตัดสินใจระหว่างทาง")
    out["META"] = dict(systems_info=info, wf=wf, period_th=period_th,
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 H1 · BTC: MT5 H1 ตั้งแต่ปี 2021 · SL ตรวจทีละแท่ง H1",
                       notes_common=[f"<b>ตัวเลขทั้งหน้านี้คือ {period_th} บัญชีเดียวต่อเนื่อง เริ่ม $100,000</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง และไม่ได้บอกอนาคต",
                                     "<b>ต้นทุนเหมือนรายงาน G27K:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap จริงของโบรกเกอร์",
                                     *(["<b>BTC มีข้อมูลครบตั้งแต่ปี 2021 เท่านั้น</b> ช่วงก่อนปี 2021 จึงเทรดแค่ทองกับเงิน"] if S.year < 2021 else []),
                                     "<b>ผมรู้อยู่แล้วว่าตลาดช่วงนี้เป็นอย่างไร</b> จึงล็อกกฎทุกรอบลง ledger ก่อนรัน แต่การออกแบบกฎก็ยังทำโดยคนที่รู้อนาคต ข้อนี้กำจัดไม่ได้ 100%"],
                       footer="สร้างจาก research/report_walkforward10y.py · ledger: walkforward_controller_round1 / round2 · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · คำนวณ 2 ต.ค. 2026")
    G.START = W.ts("2021-10-01")
    data = clean(out)
    (HERE / f"walkforward_report{years}y.json").write_text(json.dumps(data, ensure_ascii=False))
    tpl = (HERE / "walkforward_report_template.html").read_text(encoding="utf-8")
    tpl = tpl.replace("Walk-forward 10 ปี", f"Walk-forward {years} ปี").replace("Walk-forward · 10 ปี", f"Walk-forward · {years} ปี")
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for k in ("W2", "W1", "ND", "G1"):
        m = out[f"{k}_MET3"]
        print(f"  {k}: net {m['net']:+,.0f} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} trades {m['trades']}")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
