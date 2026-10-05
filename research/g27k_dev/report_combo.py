#!/usr/bin/env python3
"""Every combination of the three books, in the G27K Strategy-Tester layout,
plus the hand-off data set.

Books (2011-09-01..2026-09-30, same trades, costs and Fed rule as
report_g27kf_m30.py):
  F    G27K-F: G27K #1 (C8/D3/E1/F1/G2/H2/I1/J1) on H4 + the Fed-shock rule
  M30  the M30 sleeve (ledger m30_sleeve_new_markets, adopted)
  H1   the H1 sleeve (ledger h1_search_mirror_m30, NOT adopted: fails the
       0.10R cost-stress condition at account level)
Combos: F, M30, H1, F+M30, F+H1, M30+H1, F+M30+H1. Each on Cent (XAU, XAG,
BTC, ETH, USDJPY) and Standard (+ JP225 for F; the sleeves never trade
JP225), at 0.75% / 1% / 1% + brake 25%. With F in the combo the level is
F's risk per trade and every sleeve trade risks 0.5%; without F the
sleeves themselves trade at the level.

Each combo also gets the monthly top-up case (100,000 on the first of every
month from 1 Sep 2011, 181 deposits): IRR, unit-value drawdown, worst gap
below the money put in.

Writes <outdir>/combo_<name>.html, and research/g27k_dev/handoff/:
  trades_F.csv.gz, trades_M30.csv.gz, trades_H1.csv.gz  every trade
  matrix.csv.gz      one row per combo x account x level x (no DCA | DCA)
  monthly.csv.gz     month-end balance (no DCA) and value (DCA) per run

Usage: python3 research/g27k_dev/report_combo.py --root <snap> --outdir <dir> [--only F_M30,...]
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
import dca as DC
import fresh_markets as FM
import fresh_search_l3 as L3
import h1_sleeve as HS
import h4d1_pattern_search as P
import multi_market_search as MMS
import news_shock as NS
import report_dca as RD
import report_five as R5
import report_g27kf_m30 as RG
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, MID, END = RG.START, RG.MID, RG.END
CENT, STD = RG.CENT, RG.STD
MK5 = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")
VCONF, VERS = RG.VCONF, RG.VERS
NAME = {"F": "G27K-F", "M30": "M30", "H1": "H1"}
COMBOS = {"F": ("F",), "M30": ("M30",), "H1": ("H1",), "F_M30": ("F", "M30"), "F_H1": ("F", "H1"), "M30_H1": ("M30", "H1"), "F_M30_H1": ("F", "M30", "H1")}
STATUS = {"F": "รับใช้", "M30": "รับใช้ (ผ่านการทดสอบที่ลงทะเบียนไว้)", "H1": "ยังไม่รับใช้ (ระดับบัญชีแย่ลงเมื่อต้นทุนแย่ลง 0.10R)"}
HANDOFF = HERE / "handoff"
G_RULES = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
           "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
           "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้",
           "กฎข่าว Fed: ถ้าผลตอบแทนพันธบัตรสหรัฐ 2 ปี (DGS2) วันใดขึ้นเกิน 2 เท่าของ SD การเปลี่ยนรายวันย้อนหลัง 250 วัน ให้ปิดไม้ทอง เงิน BTC ETH "
           "ที่ราคาเปิดชั่วโมงถัดไปหลัง 22:00 UTC ของวันทำการถัดไป (ข้ามวันหยุดราชการสหรัฐ) และไม่เข้าไม้ใหม่ในตลาดเหล่านี้ 5 วัน"]
M30_RULE = ("ไม้ M30: แท่ง M30 ปิดไม่เกิน 1 ATR จาก High/Low 55 แท่งในทิศที่เทรด + ATR14/ATR100 ≥ 1.5 + D1 ไปทางเดียวกัน · ซื้อหรือขายตามทิศนั้น · "
            "SL 2 × ATR20 (M30) · TP 2R · ครบ 30 แท่งยังไม่ชน ปิดที่ราคาเปิดแท่งถัดไป · ทอง เงิน BTC ETH USDJPY")
H1_RULE = ("ไม้ H1: แท่ง H1 ราคาอยู่ในช่วงบน 10% ของ 250 แท่งในทิศที่เทรด + ATR14/ATR100 ≥ 1.25 + D1 ไปทางเดียวกัน · ซื้อหรือขายตามทิศนั้น · "
           "SL 2 × ATR20 (H1) · TP 2R · ครบ 30 แท่งยังไม่ชน ปิดที่ราคาเปิดแท่งถัดไป · ทอง เงิน BTC ETH USDJPY")


def load(a):
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    m30 = [r for r in RG.sleeve_rows(C, MK5) if W.ts(START) <= r["t"] < W.ts(END)]
    h1 = [r for r in RG.sleeve_rows(C, MK5, HS.spec_of(HS.pick())) if W.ts(START) <= r["t"] < W.ts(END)]
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in STD}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    raw = [r for r in RSD.g27k_rows(STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    shocks = NS.fed_shocks(a.root)
    shocks = shocks[(shocks >= W.ts(START)) & (shocks < W.ts(END))]
    orig = {(r["mkt"], r["t"]): r["t_exit"] for r in raw}
    rows = []
    for r in NS.apply(raw, shocks, H1, True):
        r = dict(r)
        if r["t_exit"] != orig[(r["mkt"], r["t"])]:
            X, b = r["X"], H1[r["mkt"]]
            sec = X.get("sec", 14400)
            r["x"] = max(int(np.searchsorted(X["t"] + sec, r["t_exit"], "left")), r["e"])
            r["px"] = float(b["o"][np.searchsorted(b["t"], r["t_exit"])])
            r["fed_exit"] = True
        rows.append(r)
    print(f"  loaded: F {len(rows)} trades, M30 {len(m30)}, H1 {len(h1)}", flush=True)
    return dict(G=G, K=K, C=C, RP=RP, news=news, F=rows, raw=raw, M30=m30, H1=h1)


def export_trades(D):
    HANDOFF.mkdir(exist_ok=True)
    ts = lambda t: pd.to_datetime(t, unit="s", utc=True).strftime("%Y-%m-%d %H:%M")
    for book in ("F", "M30", "H1"):
        rr = D[book]
        df = pd.DataFrame(dict(book=book, market=[r["mkt"].split("_")[0] for r in rr], direction=[int(r["d"]) for r in rr],
                               entry_time_utc=[ts(r["t"]) for r in rr], exit_time_utc=[ts(r["t_exit"]) for r in rr],
                               entry_price=[float(r["ep"]) for r in rr], exit_price=[float(r["px"]) for r in rr],
                               stop_distance=[float(r["risk"]) for r in rr], stop_pct=[float(r["stop_pct"]) for r in rr],
                               R=[float(r["R"]) for r in rr], R_gross=[float(r.get("R_gross", np.nan)) for r in rr],
                               R_spread=[float(r.get("R_spread", np.nan)) for r in rr], R_swap=[float(r.get("R_swap", np.nan)) for r in rr],
                               fed_exit=[bool(r.get("fed_exit", False)) for r in rr]))
        df.sort_values("entry_time_utc").to_csv(HANDOFF / f"trades_{book}.csv.gz", index=False, compression="gzip")
        print(f"  trades_{book}.csv.gz: {len(df)} trades, mean R {df.R.mean():+.3f}", flush=True)


def run_combo(name, D, a, matrix, monthly):
    t0 = time.time()
    combo = COMBOS[name]
    lab = " + ".join(NAME[b] for b in combo)
    has_f = "F" in combo
    G, RP, news = D["G"], D["RP"], D["news"]
    sleeve = [r for b in ("M30", "H1") if b in combo for r in D[b]]
    units = sorted({r["mkt"] for r in sleeve}, key=lambda u: (RG.BOOK(u), MK5.index(RG.BASE(u))))
    SYS = {"A": (f"Cent · {lab}", CENT), "B": (f"Standard · {lab}", STD)}
    port = {s: "P" + s for s in SYS}
    gms = {s: (list(ms) if has_f else []) for s, (_, ms) in SYS.items()}
    slv = {s: [u for u in units if RG.BASE(u) in ms] for s, (_, ms) in SYS.items()}
    RWF.UNIS.clear()
    RWF.UNIS.update({port[s]: gms[s] + slv[s] for s in SYS}, **{m: [m] for m in list(STD) + units})
    RG.START = START
    out, sized_rows, stress, mc, halves, dca = {}, {}, {}, {}, {}, {}
    for s, (label, ms) in SYS.items():
        rr = [r for r in D["F"] if r["mkt"] in gms[s]] + [r for r in sleeve if r["mkt"] in slv[s]]
        rr.sort(key=lambda r: (r["t"], r["mkt"]))
        for v, (k, ver) in VCONF.items():
            scale = dict({m: k for m in gms[s]}, **{u: (RG.K_SLEEVE if has_f else k) for u in slv[s]})
            vr = RG.sized(rr, ver, news, scale)
            sized_rows[(s, v)] = vr
            for u in [port[s], *gms[s], *slv[s]]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, k / 100, None, RP, G)
                if ent:
                    for c_ in ("corr_p_mfe", "corr_p_mae", "corr_mfe_mae"):       # sleeves keep no MFE/MAE: show 0, not a broken tile
                        if c_ in ent and not np.isfinite(ent[c_] if ent[c_] is not None else np.nan):
                            ent[c_] = 0.0
                    out[f"{s}~{v}_{u}"] = ent
            for extra in (0.0, 0.10):
                st, eq, _ = SU.simulate(RG.frame(rr, scale, extra), ver, START, END, news=news)
                a1, _, _ = SU.simulate(RG.frame(rr, scale, extra), ver, START, MID, news=news)
                a2, _, _ = SU.simulate(RG.frame(rr, scale, extra), ver, MID, END, news=news)
                m_ = SU.monte_carlo(eq)
                stress[(s + v, extra)] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], h1=a1["mar"], h2=a2["mar"], p50=m_["p_dd50"])
                if extra == 0.0:
                    mc[s + v], halves[s + v] = m_, (a1["mar"], a2["mar"])
            DC.INITIAL, DC.MONTHLY = 0.0, RD.MONTHLY
            st, eq, _ = SU.simulate(RG.frame(rr, scale), ver, START, END, news=news, deposits=True)
            mv = RD.monthly_value(eq)
            gap, gap_at = RD.worst_gap(mv)
            dca[s + v] = dict(deposited=st["deposited"], final=float(mv.iloc[-1]), irr=st["irr"], dd_unit=st["dd"], gap=gap, gap_at=gap_at, mv=mv)
        print(f"  [{name}] {label} done {time.time() - t0:.0f}s", flush=True)
    S_, E_ = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    keys = [s + v for v in VCONF for s in SYS]
    E = {s + v: out[f"{s}~{v}_{port[s]}"] for s in SYS for v in VCONF}
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    acct_of = {"A": "Cent", "B": "Standard"}
    lvl_txt = (lambda v: f"G27K-F {VERS[v]} · ไม้แยก 0.5%") if has_f else (lambda v: f"ไม้ละ {VERS[v]}")
    for s in SYS:
        for v in VCONF:
            k_ = s + v
            cur_m, cur_v = RJ.monthly(RWF.account_var(sized_rows[(s, v)]), S_, E_)
            for d, val in zip(cur_m, cur_v):
                monthly.append(dict(combo=name, account=acct_of[s], level=VERS[v], dca="no", month=str(d.date()), value=float(val)))
            for d, val in dca[k_]["mv"].items():
                monthly.append(dict(combo=name, account=acct_of[s], level=VERS[v], dca="yes", month=str(d.date()), value=float(val)))
            m, st = E[k_], stress[(k_, 0.0)]
            base = dict(combo=name, books=lab, account=acct_of[s], level=VERS[v], f_risk=VERS[v] if has_f else "-",
                        sleeve_risk=("0.5%" if has_f else VERS[v]) if units else "-")
            matrix.append(dict(base, dca="no", start_balance=W.DEPOSIT, deposited=W.DEPOSIT, final=m["final"], cagr=m["cagr"], irr=None,
                               equity_dd=m["equity_dd"]["relative_pct"], balance_dd=st["dd"], mar=mar(m), mar_2011_17=halves[k_][0], mar_2018_26=halves[k_][1],
                               worst_year=worst(m)["ret"], trades=m["trades"], p_dd50=mc[k_]["p_dd50"], stress_cagr=stress[(k_, 0.1)]["cagr"],
                               stress_mar=stress[(k_, 0.1)]["mar"], stress_p_dd50=stress[(k_, 0.1)]["p50"], unit_dd=None, gap_below_deposits=None, gap_at=None))
            dd_ = dca[k_]
            matrix.append(dict(base, dca="yes", start_balance=0.0, deposited=dd_["deposited"], final=dd_["final"], cagr=None, irr=dd_["irr"],
                               equity_dd=None, balance_dd=None, mar=None, mar_2011_17=None, mar_2018_26=None, worst_year=None, trades=m["trades"],
                               p_dd50=None, stress_cagr=None, stress_mar=None, stress_p_dd50=None, unit_dd=dd_["dd_unit"], gap_below_deposits=dd_["gap"],
                               gap_at=dd_["gap_at"]))
    # ---- comparison section ----
    rws = [("เงินสุดท้าย (เริ่ม $100,000)", lambda k: E[k]["final"], lambda x: RD.money(x)),
           ("ต่อปี", lambda k: E[k]["cagr"], lambda x: f"{x:.1%}"),
           ("Equity DD", lambda k: E[k]["equity_dd"]["relative_pct"], lambda x: f"{x:.1%}"),
           ("MAR", lambda k: mar(E[k]), lambda x: f"{x:.2f}"),
           ("MAR 2011–17", lambda k: halves[k][0], lambda x: f"{x:+.2f}"),
           ("MAR 2018–26", lambda k: halves[k][1], lambda x: f"{x:+.2f}"),
           ("ปีแย่สุด", lambda k: worst(E[k])["ret"], lambda x: f"{x:+.0%}"),
           ("ไม้", lambda k: E[k]["trades"], lambda x: f"{x:,}"),
           ("DD>50%", lambda k: mc[k]["p_dd50"], lambda x: f"{x:.1%}"),
           ("ต่อปี ถ้าแย่ลง 0.10R", lambda k: stress[(k, 0.10)]["cagr"], lambda x: f"{x:+.1%}"),
           ("MAR ถ้าแย่ลง 0.10R", lambda k: stress[(k, 0.10)]["mar"], lambda x: f"{x:.2f}"),
           ("DD>50% ถ้าแย่ลง 0.10R", lambda k: stress[(k, 0.10)]["p50"], lambda x: f"{x:.1%}")]
    head = "<th>บัญชี</th>" + "".join(f"<th class='n'>{l_}</th>" for l_, *_ in rws)
    body = ""
    for v in VCONF:
        body += f"<tr><td colspan='{len(rws) + 1}' style='font-weight:600;padding-top:14px'>{lvl_txt(v)}</td></tr>"
        for s in SYS:
            body += f"<tr><td>{acct_of[s]}</td>" + "".join(f"<td class='n'>{f(g(s + v))}</td>" for _, g, f in rws) + "</tr>"
    table = f"<table class='cmp'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    dh = ("<th>บัญชี</th><th class='n'>เงินที่ใส่</th><th class='n'>มูลค่าสุดท้าย</th><th class='n'>กำไร</th><th class='n'>IRR ต่อปี</th>"
          "<th class='n'>DD หน่วยลงทุน</th><th class='n'>ต่ำกว่าเงินที่ใส่มากสุด</th><th>เมื่อ</th>")
    db = ""
    for v in VCONF:
        db += f"<tr><td colspan='8' style='font-weight:600;padding-top:14px'>{lvl_txt(v)}</td></tr>"
        for s in SYS:
            x = dca[s + v]
            db += (f"<tr><td>{acct_of[s]}</td><td class='n'>{RD.money(x['deposited'])}</td><td class='n'><b>{RD.money(x['final'])}</b></td>"
                   f"<td class='n {'pos' if x['final'] >= x['deposited'] else 'neg'}'>{RD.money(x['final'] - x['deposited'])}</td><td class='n'>{x['irr']:.1%}</td>"
                   f"<td class='n'>{x['dd_unit']:.0%}</td><td class='n'>{x['gap']:.0%}</td><td>{x['gap_at'][:7] if x['gap'] > 0 else '–'}</td></tr>")
    dtable = f"<table class='cmp'><thead><tr>{dh}</tr></thead><tbody>{db}</tbody></table>"
    years = sorted(set.intersection(*(set(y["year"] for y in E[k]["yearly"]) for k in keys)))
    Y = {k: {y["year"]: y["ret"] for y in E[k]["yearly"]} for k in keys}
    yhead = "<th>ปี</th>" + "".join(f"<th class='n'>{acct_of[k[0]]}<br>{VERS[k[1:]]}</th>" for k in keys)
    yt = (f"<table class='cmp'><thead><tr>{yhead}</tr></thead><tbody>"
          + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {'pos' if Y[k][y] >= 0 else 'neg'}'>{Y[k][y]:+.0%}</td>" for k in keys) + "</tr>" for y in years)
          + "</tbody></table>")
    # per-market quality
    cl = lambda x: "pos" if x > 0 else "neg"
    tstat = lambda R: float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")
    mid = W.ts("2019-01-01")
    perm = []
    qual = [(m, [r for r in D["F"] if r["mkt"] == m]) for m in STD] if has_f else []
    qual += [(u, [r for r in sleeve if r["mkt"] == u]) for u in units]
    for u, x in qual:
        R, t = np.array([r["R"] for r in x]), np.array([r["t"] for r in x])
        h1_ = R[t < mid].mean() if (t < mid).any() else np.nan
        h2_ = R[t >= mid].mean()
        c1 = f"<td class='n {cl(h1_)}'>{h1_:+.2f}</td>" if np.isfinite(h1_) else "<td class='n'>–</td>"
        acct = RG.ACCT.get(RG.BASE(u) if "_" in u else u, "Cent + Standard")
        perm.append(f"<tr><td>{RG.TH.get(u, u)}</td><td class='n'>{len(R)}</td><td class='n {cl(R.mean())}'>{R.mean():+.3f}</td><td class='n'>{tstat(R):.1f}</td>"
                    f"{c1}<td class='n {cl(h2_)}'>{h2_:+.2f}</td><td>{acct}</td></tr>")
    perm_t = ("<table class='cmp'><thead><tr><th>ตลาด</th><th class='n'>ไม้</th><th class='n'>R ต่อไม้</th><th class='n'>t</th><th class='n'>2011–18</th>"
              "<th class='n'>2019–26</th><th>บัญชี</th></tr></thead><tbody>" + "".join(perm) + "</tbody></table>"
              "<p class='muted' style='margin:8px 0 0;font-size:13px'>R = R ต่อไม้หลังต้นทุน · กฎ Fed ใช้กับไม้ G27K-F ของทอง เงิน BTC ETH เท่านั้น</p>")
    # charts: no-DCA balance and DCA value at 1% + brake
    cur = {s: RJ.monthly(RWF.account_var(sized_rows[(s, "r1b")]), S_, E_) for s in SYS}
    me = cur["A"][0]
    pts = [dict(x=START, lab="เริ่ม " + START, A=float(W.DEPOSIT), B=float(W.DEPOSIT))]
    pts += [dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", A=float(cur["A"][1][i]), B=float(cur["B"][1][i])) for i, d in enumerate(me)]
    js1 = R5.SCRIPT.replace("__DATA__", json.dumps(dict(pts=pts, keys=["A", "B"], names=["Cent", "Standard"]), ensure_ascii=False))
    mvA, mvB = dca["Ar1b"]["mv"], dca["Br1b"]["mv"]
    dep = RD.MONTHLY * np.arange(1, len(mvA) + 1)
    pts2 = [dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", dep=float(dep[i]), A=float(mvA.iloc[i]), B=float(mvB.iloc[i])) for i, d in enumerate(mvA.index)]
    js2 = (R5.SCRIPT.replace("__DATA__", json.dumps(dict(pts=pts2, keys=["dep", "A", "B"], names=["เงินที่ใส่", "Cent", "Standard"]), ensure_ascii=False))
           .replace('"cmpChart"', '"dcaChart"').replace("cmpTip", "dcaTip").replace("cmpX", "dcaX")
           .replace("[5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7]", "[1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11]"))
    fix_fmt = lambda js: (js.replace('const short = v => v >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : "$" + Math.round(v / 1e3) + "k";',
                                     'const short = v => v >= 1e9 ? "$" + (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? "$" + (v / 1e6).toFixed(1) + "M" : "$" + Math.round(v / 1e3) + "k";')
                            .replace('const tick = v => v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";',
                                     'const tick = v => v >= 1e9 ? "$" + (v / 1e9) + "B" : v >= 1e6 ? "$" + (v / 1e6) + "M" : "$" + Math.round(v / 1e3) + "k";'))
    js1 = fix_fmt(js1).replace("[5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7]", "[5e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10]")
    js2 = fix_fmt(js2)
    books_li = "".join(f"<li><b>{NAME[b]}</b>: {STATUS[b]}</li>" for b in combo)
    rules_li = ((f"<li>{'<br>'.join(G_RULES)}</li>" if has_f else "") + (f"<li>{M30_RULE}</li>" if "M30" in combo else "")
                + (f"<li>{H1_RULE}</li>" if "H1" in combo else ""))
    risk_li = ("<li><b>ความเสี่ยง</b>: ระดับ 0.75% / 1% / 1% + เบรก 25% คือความเสี่ยงต่อไม้ของ G27K-F · ไม้ M30/H1 เสี่ยง 0.5% ต่อไม้ทุกระดับ</li>" if has_f and len(combo) > 1 else
               "<li><b>ความเสี่ยง</b>: ระดับ 0.75% / 1% / 1% + เบรก 25% คือความเสี่ยงต่อไม้ของทุกไม้ในชุด</li>")
    nums = "".join(f"<li><b>{lvl_txt(v)}</b>: " + " · ".join(f"{acct_of[s]} {E[s + v]['cagr']:.1%} ต่อปี DD {E[s + v]['equity_dd']['relative_pct']:.0%} · DCA {RD.money(dca[s + v]['final'])} (IRR {dca[s + v]['irr']:.1%})"
                                                         for s in SYS) + "</li>" for v in VCONF)
    summary = (f"<ul class='cmp-sum'>{books_li}{risk_li}{nums}"
               "<li><b>บัญชี</b>: Cent = ทอง เงิน BTC ETH USDJPY · Standard = + JP225 (เฉพาะ G27K-F) · เริ่ม $100,000 ก.ย. 2011 · DCA = เริ่ม 0 เติม $100,000 ทุกต้นเดือน 181 ครั้ง</li>"
               "<li><b>ข้อจำกัด</b>: กฎถูกเลือกจากข้อมูลชุดเดียวกัน ตัวเลขดีเกินจริงบางส่วน · ไม้ M30/H1 ได้เปรียบราว 0.16R ต่อไม้ ต้นทุนจริงตัดสินผล · มูลค่าระดับพันล้านเป็นตัวเลขของโมเดล</li></ul>"
               "<details style='margin-top:6px'><summary style='cursor:pointer'>กฎของแต่ละชุดไม้</summary><ul class='cmp-sum'>" + rules_li + "</ul></details>")
    css = ("<style>#dcaChart{position:relative}#dcaTip" + R5.CSS[R5.CSS.index("#cmpTip{") + 7:].split("}")[0] + "}" + "</style>")
    rob = (RG.robust_card(str(HERE / "m30_robust.json")) if "M30" in combo else "") + (RG.robust_card(str(HERE / "h1_robust.json"), "H1") if "H1" in combo else "")
    leg = lambda names: "".join(f'<span><i style="background:var(--c{i + 1})"></i>{n}</span>' for i, n in enumerate(names))
    cmp_html = (R5.CSS + css + f'<section class="card"><h2>{lab} · Cent และ Standard · 0.75% / 1% / 1% + เบรก 25% · ไม่ DCA และ DCA</h2>' + summary +
                f'<div class="legend" style="margin-bottom:6px">{leg(["Cent", "Standard"])}<span class="muted">Balance สิ้นเดือน ไม่เติมเงิน · สเกล log · ระดับ 1% + เบรก 25%</span></div>'
                '<div id="cmpChart" class="chart"></div></section>'
                f'<section class="card"><h2>DCA: เติม $100,000 ทุกต้นเดือน</h2><div class="legend" style="margin-bottom:6px">{leg(["เงินที่ใส่", "Cent", "Standard"])}'
                '<span class="muted">มูลค่าสิ้นเดือน · สเกล log · ระดับ 1% + เบรก 25%</span></div><div id="dcaChart" class="chart"></div>'
                f'<div class="tbl" style="margin-top:10px">{dtable}</div></section>'
                '<section class="card"><h2>ตัวเลขเทียบกัน (ไม่ DCA)</h2><div class="tbl">' + table + '</div></section>'
                '<section class="card"><h2>รายปี (ไม่ DCA)</h2><div class="tbl">' + yt + '</div></section>'
                '<section class="card"><h2>คุณภาพรายตลาด (ต่อไม้ 2011–2026)</h2><div class="tbl">' + perm_t + '</div></section>' + rob)
    # ---- template ----
    info, wf = {}, {}
    for s, (label, ms) in SYS.items():
        rn = {v: (f"G27K-F {k:g}% ต่อไม้" + (" · ไม้แยก 0.5%" if len(combo) > 1 else "") if has_f else f"ไม้ละ {k:g}%")
              + (" · เบรก: ลดครึ่งเมื่อ DD ถึง 25% จนกลับมาไม่เกิน 12.5%" if ver == "brake" else " · ไม่มีเบรก") for v, (k, ver) in VCONF.items()}
        rules = (G_RULES if has_f else []) + ([M30_RULE] if "M30" in combo else []) + ([H1_RULE] if "H1" in combo else [])
        acct = "บัญชี Standard: G27K-F มี JP225 · ไม้แยกไม่เทรด JP225" if "JP225" in ms else "บัญชี Cent: ทอง เงิน BTC ETH USDJPY"
        info[s] = dict(label=label, tab=label, rules=rules + [f"ตลาด: {', '.join(gms[s] + slv[s])}"], notes=[f"<b>{acct}</b>", rn["r1b"]],
                       combo=lab, risk=0.01, adds=False, tf="H4" if has_f else "M30/H1", risk_note=rn["r1b"], risk_notes=rn)
        wf[s] = dict(patterns=[], pat_note="", pat_empty="กฎตายตัว", log=[], log_note="", log_empty="ขนาดไม้ของแต่ละเวอร์ชันคำนวณที่เวลาเข้าไม้ ดูกฎในช่อง ตั้งค่า")
    last = E_ - pd.Timedelta(days=1)
    out["META"] = dict(systems_info=info, wf=wf, versions=VERS,
                       period_th=f"15 ปี {S_.day} {RJ.TH_M[S_.month - 1]} {S_.year} – {last.day} {RJ.TH_M[last.month - 1]} {last.year}",
                       data_note="G27K-F: ทอง/เงิน Candle Lab H1 ก่อนปี 2021 ต่อด้วย MT5 · ตลาดอื่น Dukascopy H1 · BTC/ETH Binance · ไม้ M30/H1: Dukascopy M1 (ทอง เงิน), Binance 1m (BTC ETH), histdata M1 (USDJPY)",
                       notes_common=["<b>บัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง (ผล DCA อยู่ในการ์ดด้านบน)",
                                     "<b>ต้นทุน:</b> spread + 1 bp (ขั้นต่ำ 2 bp ต่อรอบ) และ swap",
                                     "<b>กฎถูกเลือกจากข้อมูลชุดเดียวกัน</b> ตัวเลขจึงดีเกินจริงบางส่วน",
                                     "<b>แท็บตลาดเดียว</b> ใช้ขนาดไม้เดียวกับพอร์ตของระบบนั้น"],
                       footer="สร้างจาก research/g27k_dev/report_combo.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    allu = (list(STD) if has_f else []) + units
    ulist = [port[s] for s in SYS] + allu
    uni_th = {port[s]: f"พอร์ต {SYS[s][0]}" for s in SYS}
    uni_th.update({m: f"{RG.TH.get(m, m)} ({m}) ตลาดเดียว" for m in allu})
    pbtn = "\n        ".join(f'<button role="tab" data-u="{port[s]}">พอร์ต {SYS[s][0]}</button>' for s in SYS)
    mbtn = "\n        ".join(f'<button role="tab" data-u="{m}">{RG.TH.get(m, m)}</button>' for m in allu if m not in ("XAUUSD", "XAGUSD", "BTCUSD"))
    tl = f"{lab} · รายงาน"
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", f"<title>{lab}</title>"),
        ("Strategy Tester · Walk-forward report", f"Strategy Tester · {lab}"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", f"{lab} · Cent และ Standard · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>', pbtn),
        ('<button role="tab" data-u="BTCUSD">BTC</button>', '<button role="tab" data-u="BTCUSD">BTC</button>\n        ' + mbtn),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="เวอร์ชัน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "r1b";\nconst PORTS = ' + json.dumps(port) + ';\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์", XAUUSD: "ทอง (XAUUSD) ตลาดเดียว", XAGUSD: "เงิน (XAGUSD) ตลาดเดียว", BTCUSD: "บิตคอยน์ (BTCUSD) ตลาดเดียว"};',
         "const UNI_TH = " + json.dumps(uni_th, ensure_ascii=False) + ";"),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "PA"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         f'const fixUni = () => {{ if (!D[keyOf(SYS, UNI)]) UNI = {json.dumps(ulist)}.find(u => D[keyOf(SYS, u)]); }};\n'
         'try { const vv = localStorage.getItem("combover"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("combosys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("combosys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("combover", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ (ไม่ DCA)</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + js1 + "\n" + js2
    path = pathlib.Path(a.outdir) / f"combo_{name}.html"
    path.write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for k_ in keys:
        m = E[k_]
        print(f"  [{name}] {acct_of[k_[0]]:8s} {VERS[k_[1:]]:14s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} MAR {mar(m):.2f} trades {m['trades']} | "
              f"stress MAR {stress[(k_, 0.1)]['mar']:.2f} | DCA {RD.money(dca[k_]['final'])} IRR {dca[k_]['irr']:.1%}", flush=True)
    print(f"  written {path} ({path.stat().st_size / 1e6:.1f} MB) {time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    D = load(a)
    export_trades(D)
    names = a.only.split(",") if a.only else list(COMBOS)
    matrix, monthly = [], []
    for nm in names:
        run_combo(nm, D, a, matrix, monthly)
    HANDOFF.mkdir(exist_ok=True)
    suffix = "" if not a.only else "_partial"
    pd.DataFrame(matrix).to_csv(HANDOFF / f"matrix{suffix}.csv.gz", index=False, compression="gzip")
    pd.DataFrame(monthly).to_csv(HANDOFF / f"monthly{suffix}.csv.gz", index=False, compression="gzip")
    print(f"  handoff: {len(matrix)} matrix rows, {len(monthly)} monthly rows")


if __name__ == "__main__":
    main()
