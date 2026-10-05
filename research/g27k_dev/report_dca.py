#!/usr/bin/env python3
"""G27K-F, G27K-F + M30 and G27K-F + M30 + H1 with a monthly top-up of
100,000 (the first on 1 Sep 2011, the last on 1 Sep 2026: 181 deposits),
Cent and Standard, G27K-F at 0.75% / 1% / 1% + brake 25%, sleeves at 0.5%.
Same trades, costs and Fed rule as report_g27kf_m30.py; buying gold every
month as the yardstick.

  money-weighted return (IRR), drawdown of the unit value (what one unit
  invested at the start went through, deposits do not hide it), the worst
  gap of the balance below the money put in, year-end path, and a 15-year
  block bootstrap of G27K-F + M30 at 1% + brake.

The balance counts closed trades only (open positions are not marked).

Usage: python3 research/g27k_dev/report_dca.py --root <snap> --out <html>
"""
import argparse
import json
import math
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import dca as DC
import h1_sleeve as HS
import h4d1_pattern_search as P
import news_shock as NS
import per_market_search as PMS
import report_five as R5
import report_jp225 as RJ
import suite as SU

MONTHLY = 100_000.0
START, END = "2011-09-01", "2026-10-01"
MK5 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY"]
SYSTEMS = {"F": ("G27K-F", ()), "FM": ("G27K-F + M30", ("M30",)), "FMH": ("G27K-F + M30 + H1", ("M30", "H1"))}
VCONF = {"r075": (0.75, "normal", "0.75%"), "r1": (1.0, "normal", "1%"), "r1b": (1.0, "brake", "1% + เบรก 25%")}
ACCTS = {"Cent": NS.RF.CENT, "Standard": NS.RF.STD}


def months():
    return pd.date_range(START, END, freq="MS", inclusive="left")


def monthly_value(eq):
    """Balance at each month end: last closed balance plus deposits made after it."""
    ms = months()
    dep_t = np.array([int(m.timestamp()) for m in ms])
    et = np.array([int(x.timestamp()) for x in eq.index]) if len(eq) else np.array([], int)
    ev = eq.to_numpy()
    out = []
    for me in pd.date_range(START, END, freq="ME", inclusive="left"):
        t = int((me + pd.Timedelta(hours=23, minutes=59)).timestamp())
        j = np.searchsorted(et, t, side="right") - 1
        if j >= 0:
            out.append(ev[j] + MONTHLY * ((dep_t > et[j]) & (dep_t <= t)).sum())
        else:
            out.append(MONTHLY * (dep_t <= t).sum())
    return pd.Series(out, index=pd.date_range(START, END, freq="ME", inclusive="left"))


def worst_gap(mv):
    dep = MONTHLY * np.arange(1, len(mv) + 1)
    g = (dep - mv.to_numpy()) / dep
    i = int(np.argmax(g))
    return float(max(g[i], 0.0)), str(mv.index[i].date())


def bootstrap(F, news):
    _, eq, _ = SU.simulate(F, "normal", START, END, news=news)
    x = pd.concat([pd.Series([1.0], index=[pd.Timestamp(START)]), eq]).groupby(level=0).last().resample("ME").last().ffill().pct_change().dropna().to_numpy()
    rng = np.random.default_rng(7)
    runs, n, block = 10000, len(months()), 6
    fin, gap = np.empty(runs), np.empty(runs)
    for k in range(runs):
        path = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, math.ceil(n / block))])[:n]
        bal, nav, pk, mult, dep, g = 0.0, 1.0, 1.0, 1.0, 0.0, 0.0
        for r in path:
            bal += MONTHLY
            dep += MONTHLY
            now = 1 - nav / pk
            mult = 0.5 if (mult == 1.0 and now >= 0.25) else 1.0 if (mult < 1.0 and now <= 0.125) else mult
            bal *= 1 + r * mult
            nav *= 1 + r * mult
            pk = max(pk, nav)
            g = max(g, (dep - bal) / dep)
        fin[k], gap[k] = bal, g
    dep = MONTHLY * n
    return dict(deposited=dep, p5=float(np.quantile(fin, .05)), p25=float(np.quantile(fin, .25)), p50=float(np.median(fin)), p75=float(np.quantile(fin, .75)),
                p95=float(np.quantile(fin, .95)), p_below=float((fin < dep).mean()), p_gap20=float((gap > 0.2).mean()))


def money(v):
    a = abs(v)
    s = f"${a / 1e9:,.2f}B" if a >= 1e9 else f"${a / 1e6:,.1f}M" if a >= 1e6 else f"${a:,.0f}"
    return ("−" if v < 0 else "") + s


def build(a):
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(NS.FM.specs(C))
    DC.INITIAL, DC.MONTHLY = 0.0, MONTHLY
    M30 = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    M30 = M30[M30.mkt.isin(MK5)]
    H1S = pickle.loads((PMS.CACHE / "h1_sleeve6.pkl").read_bytes())
    H1S = H1S[H1S.mkt.isin(MK5)]
    Hh = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    news = NS.W.news_times(a.root)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, Hh, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), Hh, True)
    res, curves, mc = {}, {}, {}
    for acct, ms in ACCTS.items():
        rows = [r for r in gf if r["mkt"] in ms]
        sl = {"M30": M30[M30.mkt.isin(ms)], "H1": H1S[H1S.mkt.isin(ms)]}
        for s, (label, books) in SYSTEMS.items():
            for v, (kg, ver, vlab) in VCONF.items():
                F = HS.frame(rows, [(sl[b], "_" + b, 0.5) for b in books], kg)
                st, eq, _ = SU.simulate(F, ver, START, END, news=news, deposits=True)
                mv = monthly_value(eq)
                gap, gap_at = worst_gap(mv)
                res[(acct, s, v)] = dict(acct=acct, system=label, ver=vlab, deposited=st["deposited"], final=float(mv.iloc[-1]), irr=st["irr"],
                                         dd_unit=st["dd"], gap=gap, gap_at=gap_at, n=st["n"])
                if v == "r1b":
                    curves[(acct, s)] = mv
                    if s == "FM":
                        mc[acct] = bootstrap(F, news)
                r_ = res[(acct, s, v)]
                print(f"  {acct:8s} {label:18s} {vlab:14s} put {r_['deposited']:>12,.0f} got {r_['final']:>16,.0f} IRR {r_['irr']:6.1%} "
                      f"unit DD {r_['dd_unit']:.0%} worst gap below deposits {gap:.0%} ({gap_at})", flush=True)
    gd = DC.gold_dca(Hh["XAUUSD"], START, END)
    px = pd.Series(np.asarray(Hh["XAUUSD"]["c"], float), index=pd.to_datetime(np.asarray(Hh["XAUUSD"]["t"], np.int64), unit="s"))
    oz = np.cumsum([MONTHLY / px[px.index >= m].iloc[0] for m in months()])
    me = pd.date_range(START, END, freq="ME", inclusive="left")
    gold_mv = pd.Series([oz[i] * px[px.index <= m + pd.Timedelta(days=1)].iloc[-1] for i, m in enumerate(me)], index=me)
    gg, gg_at = worst_gap(gold_mv)
    gd.update(final=float(gold_mv.iloc[-1]), gap=gg, gap_at=gg_at)
    print(f"  gold DCA: put {gd['deposited']:,.0f} got {gd['final']:,.0f} IRR {gd['irr']:.1%} worst gap {gg:.0%}", flush=True)
    return res, curves, mc, gd, gold_mv


def page(res, curves, mc, gd, gold_mv):
    dep_total = res[("Standard", "FM", "r1b")]["deposited"]
    me = curves[("Standard", "F")].index
    dep_line = MONTHLY * np.arange(1, len(me) + 1)

    def chart(acct, cid):
        keys = ["dep", "gold", "F", "FM", "FMH"]
        names = ["เงินที่ใส่", "ซื้อทองเก็บ", "G27K-F", "F + M30", "F + M30 + H1"]
        pts = [dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", dep=float(dep_line[i]), gold=float(gold_mv.iloc[i]),
                    **{s: float(curves[(acct, s)].iloc[i]) for s in SYSTEMS}) for i, d in enumerate(me)]
        js = R5.SCRIPT.replace("__DATA__", json.dumps(dict(pts=pts, keys=keys, names=names), ensure_ascii=False)).replace('"cmpChart"', f'"{cid}"').replace("cmpTip", f"{cid}Tip").replace("cmpX", f"{cid}X")
        js = js.replace("[5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7]", "[1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12]")
        js = js.replace('const short = v => v >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : "$" + Math.round(v / 1e3) + "k";',
                        'const short = v => v >= 1e9 ? "$" + (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? "$" + (v / 1e6).toFixed(1) + "M" : "$" + Math.round(v / 1e3) + "k";')
        js = js.replace('const tick = v => v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";',
                        'const tick = v => v >= 1e9 ? "$" + (v / 1e9) + "B" : v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";')
        legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{n}</span>' for i, n in enumerate(names))
        return (f'<section class="card"><h2>บัญชี {acct} · G27K-F 1% + เบรก 25%</h2><div class="legend" style="margin-bottom:6px">{legend}'
                f'<span class="muted">มูลค่าสิ้นเดือน · สเกล log</span></div><div id="{cid}" class="chart"></div></section>', js)

    c1, j1 = chart("Standard", "dcaStd")
    c2, j2 = chart("Cent", "dcaCent")
    head = ("<th>ระบบ</th><th>ความเสี่ยง G27K-F</th><th class='n'>เงินที่ใส่</th><th class='n'>มูลค่าสุดท้าย</th><th class='n'>กำไร</th><th class='n'>IRR ต่อปี</th>"
            "<th class='n'>DD หน่วยลงทุน</th><th class='n'>ต่ำกว่าเงินที่ใส่มากสุด</th><th>เมื่อ</th>")
    body = ""
    for acct in ACCTS:
        body += f"<tr><td colspan='9' style='font-weight:600;padding-top:14px'>บัญชี {acct}</td></tr>"
        for s in SYSTEMS:
            for v in VCONF:
                r = res[(acct, s, v)]
                body += (f"<tr><td>{r['system']}</td><td>{r['ver']}</td><td class='n'>{money(r['deposited'])}</td><td class='n'><b>{money(r['final'])}</b></td>"
                         f"<td class='n pos'>{money(r['final'] - r['deposited'])}</td><td class='n'>{r['irr']:.1%}</td><td class='n'>{r['dd_unit']:.0%}</td>"
                         f"<td class='n'>{r['gap']:.0%}</td><td>{r['gap_at'][:7] if r['gap'] > 0 else '–'}</td></tr>")
    body += (f"<tr><td colspan='9' style='font-weight:600;padding-top:14px'>เทียบ</td></tr><tr><td>ซื้อทองเก็บทุกเดือน</td><td>–</td><td class='n'>{money(gd['deposited'])}</td>"
             f"<td class='n'><b>{money(gd['final'])}</b></td><td class='n pos'>{money(gd['final'] - gd['deposited'])}</td><td class='n'>{gd['irr']:.1%}</td>"
             f"<td class='n'>{gd['dd_unit']:.0%}</td><td class='n'>{gd['gap']:.0%}</td><td>{gd['gap_at'][:7] if gd['gap'] > 0 else '–'}</td></tr>")
    table = f"<table class='cmp'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    # year ends
    yh = "<th>สิ้นปี</th><th class='n'>ใส่สะสม</th>" + "".join(f"<th class='n'>{acct}<br>{SYSTEMS[s][0].replace('G27K-F', 'F')}</th>" for acct in ACCTS for s in SYSTEMS) + "<th class='n'>ทอง</th>"
    yb = ""
    for d in me:
        if d.month != 12 and d != me[-1]:
            continue
        i = me.get_loc(d)
        dep = dep_line[i]
        yb += (f"<tr><td>{d.year}{'' if d.month == 12 else ' (ก.ย.)'}</td><td class='n'>{money(dep)}</td>"
               + "".join(f"<td class='n'>{money(curves[(acct, s)].iloc[i])}</td>" for acct in ACCTS for s in SYSTEMS)
               + f"<td class='n'>{money(gold_mv.iloc[i])}</td></tr>")
    ytable = f"<table class='cmp'><thead><tr>{yh}</tr></thead><tbody>{yb}</tbody></table>"
    mrows = "".join(f"<tr><td>{acct}</td><td class='n'>{money(x['p5'])}</td><td class='n'>{money(x['p25'])}</td><td class='n'><b>{money(x['p50'])}</b></td>"
                    f"<td class='n'>{money(x['p75'])}</td><td class='n'>{money(x['p95'])}</td><td class='n'>{x['p_below']:.1%}</td><td class='n'>{x['p_gap20']:.1%}</td></tr>"
                    for acct, x in mc.items())
    mtable = ("<table class='cmp'><thead><tr><th>บัญชี</th><th class='n'>แย่ 5%</th><th class='n'>แย่ 25%</th><th class='n'>กลาง</th><th class='n'>ดี 25%</th>"
              "<th class='n'>ดี 5%</th><th class='n'>จบต่ำกว่าเงินที่ใส่</th><th class='n'>เคยต่ำกว่าเงินที่ใส่เกิน 20%</th></tr></thead><tbody>" + mrows + "</tbody></table>")
    fm_s, fm_c = res[("Standard", "FM", "r1b")], res[("Cent", "FM", "r1b")]
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>เติม $100,000 ทุกต้นเดือน</b> 1 ก.ย. 2011 – 1 ก.ย. 2026 รวม {len(me)} ครั้ง = <b>{money(dep_total)}</b> · เทรดด้วยไม้ ต้นทุน และกฎชุดเดียวกับรายงาน G27K-F + M30</li>"
               f"<li><b>ระบบที่แนะนำ (G27K-F + M30 · 1% + เบรก 25%)</b>: Standard ได้ {money(fm_s['final'])} (IRR {fm_s['irr']:.1%}) · Cent ได้ {money(fm_c['final'])} (IRR {fm_c['irr']:.1%}) · "
               f"ซื้อทองเก็บได้ {money(gd['final'])} (IRR {gd['irr']:.1%})</li>"
               "<li><b>IRR</b> = ผลตอบแทนต่อปีที่คิดตามจังหวะเงินที่ใส่ เงินที่ใส่ปลายทางมีเวลาเติบโตน้อย IRR จึงต่ำกว่าผลต่อปีของรายงานหลักที่ลงเงินก้อนเดียวตั้งแต่ต้น</li>"
               "<li><b>DD หน่วยลงทุน</b> = การลดลงที่เงิน 1 หน่วยที่ลงตั้งแต่ต้นเจอ การเติมเงินไม่ช่วยปิด · <b>ต่ำกว่าเงินที่ใส่มากสุด</b> = ช่วงที่มูลค่าพอร์ตต่ำกว่าเงินสะสมที่ใส่ไปมากที่สุดกี่ %</li>"
               "<li><b>ไม้ H1 ผ่านการทดสอบที่ลงทะเบียนไว้แบบเฉียด</b> (หลังเติมข้อมูลทอง ข้อต้นทุนแย่ลง 0.10R ชนะ F+M30 แค่ 0.776 ต่อ 0.773 บน Cent) · ตัวเลขทั้งหมดเป็นผลย้อนหลังที่เลือกกฎจากข้อมูลชุดเดียวกัน จึงดีเกินจริงบางส่วน</li>"
               "<li><b>มูลค่ารายเดือน</b> นับเฉพาะไม้ที่ปิดแล้ว ไม่นับกำไรขาดทุนของไม้ที่ยังเปิด · มูลค่าหลายพันล้านเป็นตัวเลขของโมเดล ขนาดไม้จริงจะชนเพดาน lot และสภาพคล่องก่อน</li></ul>")
    css = ("<style>:root{--c5:#8e6bd8}@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--c5:#a487e6}}:root[data-theme=\"dark\"]{--c5:#a487e6}"
           ".wrapd{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:22px 40px}"
           ".wrapd h1{font-size:clamp(22px,3.5vw,30px);margin:4px 0 6px;text-wrap:balance}.eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;opacity:.75}</style>")
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    base = tpl[tpl.index("<style>"):tpl.index("</style>") + 8]
    fonts = "".join(l for l in tpl.splitlines(True) if "fonts.googleapis" in l or "fonts.gstatic" in l)
    tipcss = R5.CSS[R5.CSS.index("#cmpTip{") + 7:].split("}")[0] + "}"
    css += f"<style>#dcaStd,#dcaCent{{position:relative}}#dcaStdTip,#dcaCentTip{tipcss}</style>"
    return (f"<title>G27K-F DCA</title>{fonts}{base}{R5.CSS}{css}<main class='wrapd'><div class='eyebrow'>Strategy Tester · DCA เดือนละ $100,000</div>"
            f"<h1>G27K-F · M30 · H1 เติมเงินทุกเดือน · Cent และ Standard · 15 ปี</h1>"
            f"<section class='card'><h2>สรุป</h2>{summary}</section>{c1}{c2}"
            f"<section class='card'><h2>ผลทุกระบบ ทุกระดับความเสี่ยง</h2><div class='tbl'>{table}</div></section>"
            f"<section class='card'><h2>มูลค่าสิ้นปี · G27K-F 1% + เบรก 25%</h2><div class='tbl'>{ytable}</div></section>"
            f"<section class='card'><h2>ช่วงผลลัพธ์ที่เป็นไปได้ · G27K-F + M30 · 1% + เบรก 25%</h2>"
            f"<p class='muted' style='margin:0 0 8px;font-size:13px'>สุ่มลำดับผลตอบแทนรายเดือนจริงเป็นช่วงละ 6 เดือน 10,000 รอบ ระยะ {len(me)} เดือน เติมเดือนละ $100,000 เบรกคิดใหม่ทุกเส้นทาง</p>"
            f"<div class='tbl'>{mtable}</div></section>"
            f"<p class='muted' style='font-size:12.5px'>สร้างจาก research/g27k_dev/report_dca.py · ราคาจำลองบนข้อมูลจริง ไม่ใช่ผลเทรดจริง · ไม่ใช่คำแนะนำการลงทุน</p></main>"
            f"{j1}{j2}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse", action="store_true", help="reuse the simulations of the last run")
    a = ap.parse_args()
    cache = PMS.CACHE / "report_dca.pkl"
    if a.reuse and cache.exists():
        res, curves, mc, gd, gold_mv = pickle.loads(cache.read_bytes())
    else:
        res, curves, mc, gd, gold_mv = build(a)
        cache.write_bytes(pickle.dumps((res, curves, mc, gd, gold_mv)))
    pathlib.Path(a.out).write_text(page(res, curves, mc, gd, gold_mv), encoding="utf-8")
    js = {f"{k[0]} {k[1]} {k[2]}": v for k, v in res.items()}
    (HERE / "report_dca.json").write_text(json.dumps(dict(results=js, monte_carlo=mc, gold=gd), indent=1, ensure_ascii=False, default=float))
    print("written", a.out)


if __name__ == "__main__":
    main()
