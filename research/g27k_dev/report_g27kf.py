#!/usr/bin/env python3
"""G27K-F: G27K #1 plus the Fed-shock exit (ledger g27k_fast_news_shock), in
the G27K Strategy-Tester layout. Locked risk: 0.75% per trade with no brake,
and 1% per trade with the 25% brake; BTC and ETH always at half. Cent 5 and
Standard 6 markets. Comparison on top (also without the Fed rule), then
system and market tabs. 2011-09..2026-09.

Usage: python3 research/g27k_dev/report_g27kf.py --root <snap> --out <html>
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
import news_shock as NS
import report_five as R5
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, MID, END = "2011-09-01", "2018-01-01", "2026-10-01"
CENT = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")
STD = CENT + ("JP225",)
S5 = STD
# (label, markets, risk per trade, version); BTC and ETH always at half that risk
SYS = {"A": ("Cent 0.75%", CENT, 0.75, "normal"), "B": ("Cent 1% + เบรก 25%", CENT, 1.0, "brake"),
       "C": ("Standard 0.75%", STD, 0.75, "normal"), "D": ("Standard 1% + เบรก 25%", STD, 1.0, "brake")}
VERS = {"lock": "ความเสี่ยงที่ล็อก"}
HALF_OF = lambda ms, k: {m: k * (0.5 if m in ("BTCUSD", "ETHUSD") else 1.0) for m in ms}
TH = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC", "ETHUSD": "ETH"}
ACCT = {"JP225": "Standard เท่านั้น", "BTCUSD": "Cent (MT5) + Standard", "ETHUSD": "Cent (MT5) + Standard"}


def frame(rows, scale, extra=0.0):
    return pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[r["t"] for r in rows], tx=[r["t_exit"] for r in rows],
                             R=[(r["R"] - extra) * scale.get(r["mkt"], 1.0) for r in rows], vp=[r.get("vp", 0.0) for r in rows],
                             sc=[r.get("sc", r["t"]) for r in rows]))


def sized(rows, version, news, scale):
    """Like report_suite_detail.sized, with some markets traded at a fraction of the risk: the account path is
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
    allm = STD
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in allm}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    raw = [r for r in RSD.g27k_rows(allm, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    shocks = NS.fed_shocks(a.root)
    shocks = shocks[(shocks >= W.ts(START)) & (shocks < W.ts(END))]
    orig = {(r["mkt"], r["t"]): r["t_exit"] for r in raw}
    rows = []
    for r in NS.apply(raw, shocks, H1, True):
        r = dict(r)
        if r["t_exit"] != orig[(r["mkt"], r["t"])]:           # closed early by the Fed rule
            X, b = r["X"], H1[r["mkt"]]
            sec = X.get("sec", 14400)
            r["x"] = max(int(np.searchsorted(X["t"] + sec, r["t_exit"], "left")), r["e"])
            r["px"] = float(b["o"][np.searchsorted(b["t"], r["t_exit"])])
            r["fed_exit"] = True
        rows.append(r)
    n_fed = sum(1 for r in rows if r.get("fed_exit"))
    print(f"  Fed shocks {len(shocks)}, trades {len(raw)} -> {len(rows)} (blocked {len(raw) - len(rows)}, closed early {n_fed})", flush=True)
    port = {s: "P" + s for s in SYS}
    RWF.UNIS.update({port[s]: list(ms) for s, (_, ms, _, _) in SYS.items()}, **{m: [m] for m in allm})
    out, sized_rows, stress, mc, halves = {}, {}, {}, {}, {}
    nofed = {}
    for s, (label, ms, k, ver) in SYS.items():
        rr = [r for r in rows if r["mkt"] in ms]
        scale = HALF_OF(ms, k)
        for v in VERS:
            vr = sized(rr, ver, news, scale)
            sized_rows[(s, v)] = vr
            for u in [port[s], *ms]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, k / 100, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
        for extra in (0.0, 0.10):
            st, eq, _ = SU.simulate(frame(rr, scale, extra), ver, START, END, news=news)
            a1, _, _ = SU.simulate(frame(rr, scale, extra), ver, START, MID, news=news)
            a2, _, _ = SU.simulate(frame(rr, scale, extra), ver, MID, END, news=news)
            m_ = SU.monte_carlo(eq)
            stress[(s, extra)] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], h1=a1["mar"], h2=a2["mar"], p50=m_["p_dd50"])
            if extra == 0.0:
                mc[s], halves[s] = m_, (a1["mar"], a2["mar"])
        rb = [r for r in raw if r["mkt"] in ms]
        st0, eq0, _ = SU.simulate(frame(rb, scale), ver, START, END, news=news)
        s10, _, _ = SU.simulate(frame(rb, scale, 0.10), ver, START, END, news=news)
        nofed[s] = dict(cagr=st0["cagr"], dd=st0["dd"], mar=st0["mar"], p50=SU.monte_carlo(eq0)["p_dd50"], st_cagr=s10["cagr"], st_dd=s10["dd"])
        print(f"  {s} {label} done  {time.time() - t0:.0f}s", flush=True)

    S_, E_ = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    cur = {}
    for s in SYS:
        me, cur[s] = RJ.monthly(RWF.account_var(sized_rows[(s, "lock")]), S_, E_)
    curves = [(d, [cur[s][i] for s in SYS]) for i, d in enumerate(me)]
    E = {s: out[f"{s}~lock_{port[s]}"] for s in SYS}
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
    def tstat(R):
        return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")
    cl = lambda v: "pos" if v > 0 else "neg"
    perm, mid = [], W.ts("2019-01-01")
    for m in STD:
        x = [r for r in rows if r["mkt"] == m]
        x0 = [r for r in raw if r["mkt"] == m]
        R, R0 = np.array([r["R"] for r in x]), np.array([r["R"] for r in x0])
        t = np.array([r["t"] for r in x])
        h1, h2 = R[t < mid].mean(), R[t >= mid].mean()
        nfx = sum(1 for r in x if r.get("fed_exit"))
        perm.append(f"<tr><td>{TH.get(m, m)}</td><td class='n'>{len(R0)}</td><td class='n'>{len(R)}</td><td class='n'>{nfx}</td><td class='n {cl(R0.mean())}'>{R0.mean():+.3f}</td>"
                    f"<td class='n {cl(R.mean())}'>{R.mean():+.3f}</td><td class='n'>{tstat(R):.1f}</td>"
                    f"<td class='n {cl(h1)}'>{h1:+.2f}</td><td class='n {cl(h2)}'>{h2:+.2f}</td><td>{ACCT.get(m, 'Cent + Standard')}</td></tr>")
    perm_t = ("<table class='cmp'><thead><tr><th>ตลาด</th><th class='n'>ไม้เดิม</th><th class='n'>ไม้ F</th><th class='n'>ปิดเพราะข่าว</th><th class='n'>R เดิม</th>"
              "<th class='n'>R F</th><th class='n'>t</th><th class='n'>2011–18</th><th class='n'>2019–26</th><th>บัญชี</th></tr></thead><tbody>" + "".join(perm) + "</tbody></table>"
              "<p class='muted' style='margin:8px 0 0;font-size:13px'>R = R ต่อไม้หลังต้นทุน · F = G27K-F · กฎ Fed ใช้กับทอง เงิน BTC ETH เท่านั้น</p>")
    fed_rows = "".join(f"<tr><td>{name[s]}</td><td class='n'>{nofed[s]['cagr']:+.1%} → <b>{stress[(s, 0.0)]['cagr']:+.1%}</b></td>"
                       f"<td class='n'>{nofed[s]['dd']:.1%} → <b>{stress[(s, 0.0)]['dd']:.1%}</b></td><td class='n'>{nofed[s]['mar']:.2f} → <b>{stress[(s, 0.0)]['mar']:.2f}</b></td>"
                       f"<td class='n'>{nofed[s]['st_cagr']:+.1%} → <b>{stress[(s, 0.10)]['cagr']:+.1%}</b></td></tr>" for s in keys)
    fed_t = ("<table class='cmp'><thead><tr><th>ระบบ</th><th class='n'>ต่อปี</th><th class='n'>DD (balance)</th><th class='n'>MAR</th><th class='n'>ต่อปี ถ้าแย่ลง 0.10R</th></tr></thead><tbody>"
             + fed_rows + "</tbody></table><p class='muted' style='margin:8px 0 0;font-size:13px'>ซ้าย = G27K #1 เดิม · ขวา = G27K-F (เพิ่มกฎข่าว Fed)</p>")
    eq = lambda s: E[s]["equity_dd"]["relative_pct"]
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>G27K-F</b> = G27K #1 + กฎข่าว Fed: เมื่อผลตอบแทนพันธบัตรสหรัฐ 2 ปีขึ้นแรงผิดปกติในวันเดียว (เกิน 2 เท่าของความผันผวนปกติ) "
               f"ปิดไม้ทอง เงิน BTC ETH ที่เปิดอยู่ และหยุดเข้าไม้ใหม่ 5 วัน · เกิด {len(shocks)} ครั้งในข้อมูล (ราว 9 ครั้งต่อปี) · ปิดก่อนกำหนด {n_fed} ไม้ · ไม่ได้เข้า {len(raw) - len(rows)} ไม้</li>"
               f"<li><b>Cent 0.75%</b>: {E['A']['cagr']:.1%} ต่อปี · Equity DD {eq('A'):.0%} · <b>Cent 1% + เบรก 25%</b>: {E['B']['cagr']:.1%} ต่อปี · Equity DD {eq('B'):.0%}</li>"
               f"<li><b>Standard 0.75%</b>: {E['C']['cagr']:.1%} ต่อปี · Equity DD {eq('C'):.0%} · <b>Standard 1% + เบรก 25%</b>: {E['D']['cagr']:.1%} ต่อปี · Equity DD {eq('D'):.0%}</li>"
               "<li><b>BTC และ ETH เสี่ยงครึ่งหนึ่งเสมอ</b> (0.375% หรือ 0.5% ตัวละ) เพราะขยับตามกัน</li>"
               "<li><b>หลักฐานกฎ Fed ระดับปานกลาง</b>: ผ่านเกณฑ์ที่ลงทะเบียนไว้ทั้ง Cent, Standard, สองช่วงเวลา และต้นทุนแย่ลง · วันสุ่มแทนวันข่าว 200 ชุด ดีเท่าหรือดีกว่าแค่ 7% · "
               "ปรับค่าตั้ง 9 แบบดีกว่าไม่มีกฎทุกแบบ · แต่ไอเดียมาจากการดูช่วง DD ในข้อมูลชุดเดียวกัน</li></ul>")
    pts = [dict(x=START, lab="เริ่ม " + START, **{s: float(W.DEPOSIT) for s in keys})]
    for d, vals in curves:
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", **{s: float(v) for s, v in zip(keys, vals)}))
    short = {"A": "Cent 0.75", "B": "Cent 1%+B", "C": "Std 0.75", "D": "Std 1%+B"}
    data = json.dumps(dict(pts=pts, keys=keys, names=[short[s] for s in keys]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{name[s]}</span>' for i, s in enumerate(keys))
    cmp_html = (R5.CSS + '<section class="card"><h2>G27K-F · G27K #1 + กฎข่าว Fed · ความเสี่ยงที่ล็อก</h2>' + summary +
                f'<div class="legend" style="margin-bottom:6px">{legend}<span class="muted">Balance สิ้นเดือน · สเกล log</span></div><div id="cmpChart" class="chart"></div></section>'
                '<div class="cmp-grid"><section class="card"><h2>กฎข่าว Fed ช่วยแค่ไหน</h2><div class="tbl">' + fed_t + '</div></section>'
                '<section class="card"><h2>คุณภาพรายตลาด (ต่อไม้ 2011–2026)</h2><div class="tbl">' + perm_t + '</div></section></div>'
                '<div class="cmp-grid"><section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
                '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section></div>'
                '<section class="card"><h2>ถ้าต้นทุนจริงแย่กว่าโมเดล</h2><div class="tbl">' + stress_html + '</div></section>')
    cmp_js = R5.SCRIPT.replace("__DATA__", data)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้",
               "กฎข่าว Fed: ถ้าผลตอบแทนพันธบัตรสหรัฐ 2 ปี (DGS2) วันใดขึ้นเกิน 2 เท่าของ SD การเปลี่ยนรายวันย้อนหลัง 250 วัน "
               "ให้ปิดไม้ทอง เงิน BTC ETH ที่ราคาเปิดชั่วโมงถัดไปหลัง 22:00 UTC ของวันทำการถัดไป และไม่เข้าไม้ใหม่ในตลาดเหล่านี้ 5 วัน"]
    info = {}
    for s, (label, ms, k, ver) in SYS.items():
        acct = "บัญชี Cent: ไม่มี JP225 · BTCUSDc/ETHUSDc บน MT5 เท่านั้น" if "JP225" not in ms else "บัญชี Standard: มี JP225 ครบ 6 ตลาด"
        risk = (f"ความเสี่ยง {k:g}% ต่อไม้ · BTC และ ETH ตัวละ {k / 2:g}%" + (" · เบรก: ลดครึ่งเมื่อ DD ถึง 25% จนกลับมาไม่เกิน 12.5%" if ver == "brake" else " · ไม่มีเบรก"))
        info[s] = dict(label=f"G27K-F · {label}", tab=label, rules=g_rules + [f"ตลาด: {', '.join(ms)}"], notes=[f"<b>{acct}</b>", risk],
                       combo="C8/D3/E1/F1/G2/H2/I1/J1 + Fed", risk=k / 100, adds=False, tf="H4", risk_note=risk, risk_notes={"lock": risk})
    wf = {s: dict(patterns=[], pat_note="", pat_empty="กฎตายตัว G27K #1 กฎเดียว", log=[], log_note="",
                  log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า") for s in SYS}
    last = E_ - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S_.day} {RJ.TH_M[S_.month - 1]} {S_.year} – {last.day} {RJ.TH_M[last.month - 1]} {last.year}",
                       data_note="ทอง/เงิน: Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · ตลาดอื่น: Dukascopy H1 · BTC/ETH: Binance · SL ตรวจทีละแท่ง H1",
                       notes_common=["<b>บัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap",
                                     "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> ETH ถูกเพิ่มหลังเห็นผล และกฎข่าว Fed มาจากการดูช่วง DD ในข้อมูลชุดเดียวกัน ตัวเลขจึงดีเกินจริงบางส่วน",
                                     "<b>ETH มีข้อมูลตั้งแต่ ส.ค. 2017</b> ก่อนหน้านั้นเทรดตลาดที่เหลือ",
                                     "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ตของระบบนั้น"],
                       footer="สร้างจาก research/g27k_dev/report_g27kf.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    ulist = [port[s] for s in SYS] + list(allm)
    uni_th = {port[s]: f"พอร์ต {SYS[s][0]}" for s in SYS}
    uni_th.update({m: f"{TH.get(m, m)} ({m}) ตลาดเดียว" for m in allm})
    pbtn = "\n        ".join(f'<button role="tab" data-u="{port[s]}">พอร์ต {SYS[s][0]}</button>' for s in SYS)
    mbtn = "\n        ".join(f'<button role="tab" data-u="{m}">{TH.get(m, m)}</button>' for m in allm if m not in ("XAUUSD", "XAGUSD", "BTCUSD"))
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", "<title>G27K-F</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K-F"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "G27K-F · G27K #1 + กฎข่าว Fed · Cent และ Standard · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>', pbtn),
        ('<button role="tab" data-u="BTCUSD">BTC</button>', '<button role="tab" data-u="BTCUSD">BTC</button>\n        ' + mbtn),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "lock";\nconst PORTS = ' + json.dumps(port) + ';\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์", XAUUSD: "ทอง (XAUUSD) ตลาดเดียว", XAGUSD: "เงิน (XAGUSD) ตลาดเดียว", BTCUSD: "บิตคอยน์ (BTCUSD) ตลาดเดียว"};',
         "const UNI_TH = " + json.dumps(uni_th, ensure_ascii=False) + ";"),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "PA"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         f'const fixUni = () => {{ if (!D[keyOf(SYS, UNI)]) UNI = {json.dumps(ulist)}.find(u => D[keyOf(SYS, u)]); }};\n'
         'try { const vv = localStorage.getItem("g27kfver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("g27kfver", VER); } catch (x) {} render(); });'),
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
