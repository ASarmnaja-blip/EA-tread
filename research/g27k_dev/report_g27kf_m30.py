#!/usr/bin/env python3
"""G27K-F with the M30 trend-continuation sleeve (ledger m30_sleeve_with_g27kf)
in the G27K Strategy-Tester layout. Cent 5 / Standard 6 markets, G27K-F at
1% + brake 25%, the sleeve (gold, silver, BTC on M30) at 0.5% per trade as
separate positions in the same account; each account with and without it.
2011-09..2026-09.

Usage: python3 research/g27k_dev/report_g27kf_m30.py --root <snap> --out <html>
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
import intraday_pattern_search as IP
import m30_new_markets as NM
import h1_sleeve as HS
import news_shock as NS
import per_market_search as PMS
import report_five as R5
import report_jp225 as RJ
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, MID, END = "2011-09-01", "2018-01-01", "2026-10-01"
CENT = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")
STD = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY", "JP225")
S5 = STD
# (label, markets, risk per trade, version); every market at the same risk, BTC and ETH included
SLEEVE = ("XAUUSD_M30", "XAGUSD_M30", "BTCUSD_M30")
K_SLEEVE = 0.5
# (label, markets, risk per trade, version, with M30 sleeve)
def systems(cent, h1=False):
    """Without the H1 sleeve: G27K-F alone vs + M30; with it every system carries M30 and B, D add H1."""
    if h1:
        return {"A": ("Cent G27K-F + M30", cent, ("M30",)), "B": ("Cent G27K-F + M30 + H1", cent, ("M30", "H1")),
                "C": ("Standard G27K-F + M30", STD, ("M30",)), "D": ("Standard G27K-F + M30 + H1", STD, ("M30", "H1"))}
    return {"A": ("Cent G27K-F", cent, ()), "B": ("Cent G27K-F + M30", cent, ("M30",)),
            "C": ("Standard G27K-F", STD, ()), "D": ("Standard G27K-F + M30", STD, ("M30",))}


SYS = systems(CENT)
M30_SPEC = dict(tf="M30", near="brk55", thr=-1.0, vol=1.5, ctx="htf1_with", dir="both", exit="tp2", scope="pooled")
# locked G27K-F risk: (risk per trade %, suite version)
VCONF = {"r075": (0.75, "normal"), "r1": (1.0, "normal"), "r1b": (1.0, "brake")}
VERS = {"r075": "0.75%", "r1": "1%", "r1b": "1% + เบรก 25%"}
HALF_OF = lambda ms, k: {m: k for m in ms}
TH = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC", "ETHUSD": "ETH", "XAUUSD_M30": "ทอง M30", "XAGUSD_M30": "เงิน M30", "BTCUSD_M30": "BTC M30",
      "ETHUSD_M30": "ETH M30", "USDJPY_M30": "USDJPY M30", "JP225_M30": "JP225 M30"}
THS = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC", "ETHUSD": "ETH", "USDJPY": "USDJPY", "JP225": "JP225"}
BASE = lambda u: u.rsplit("_", 1)[0]        # "JP225_M30" -> "JP225"
BOOK = lambda u: u.rsplit("_", 1)[1]        # "JP225_M30" -> "M30"
for _m, _t in list(THS.items()):
    for _b in ("M30", "H1"):
        TH.setdefault(f"{_m}_{_b}", f"{_t} {_b}")
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


def sleeve_rows(C, markets, spec=M30_SPEC):
    """A registered sleeve pick as report rows (one unit, no adds; MFE/MAE not tracked)."""
    h1 = {m: NM.load_m1(m) for m in markets}
    P._M["h1"] = h1
    P._M["frames_for"] = IP.frames_minute
    tf, ex = spec["tf"], spec["exit"]
    E, feats, cats = P.build(h1, tf)
    m = HS.mask(E, feats, cats, spec)
    rows = []
    for i in P.no_overlap(E, m, ex):
        mk = str(E["mkt"][i])
        X = dict(P.FRAMES[(mk, tf)], sec=P.TF_SEC[tf])
        e, x = int(E["s"][i]) + 1, int(E[f"x_{ex}"][i])
        ep, px, rk, d = float(E[f"ep_{ex}"][i]), float(E[f"px_{ex}"][i]), float(E[f"rk_{ex}"][i]), int(E["d"][i])
        spec = C.SPECS[mk]
        cost = spec["cost_rt_bp"] / 1e4
        swr = (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
        R = float(E[f"R_{ex}"][i])
        gross = d * (px - ep) / rk
        rows.append(dict(mkt=f"{mk}_{tf}", e=e, x=x, d=d, ep=ep, px=px, risk=rk, units=[(ep, e, int(X["t"][e]))], R=R, R_gross=gross,
                         R_spread=ep * cost / rk, R_swap=gross - R - ep * cost / rk, t=int(X["t"][e]), t_exit=int(E[f"tx_{ex}"][i]),
                         mfe=0.0, mae=0.0, gaps=0, same=0, stop_pct=rk / ep, cost=cost, swr=swr, triple=spec["rollover3"], X=X, vp=0.0))
    P._M.pop("frames_for", None)
    return rows


def robust_card(path, book="M30"):
    """Robustness of a sleeve (m30_robust.json / h1_robust.json) as one card."""
    if not path:
        return ""
    Rb = json.loads(pathlib.Path(path).read_text())
    cl = lambda v: "pos" if v > 0 else "neg"
    row = lambda lab, r, note="": (f"<tr><td>{lab}</td><td class='n'>{r['n']:,}</td><td class='n {cl(r['net'])}'>{r['net']:+.3f}</td>"
                                    f"<td class='n'>{r['t']:+.1f}</td><td>{note}</td></tr>")
    b, A = Rb["base"], Rb["a"]
    nb = Rb["b"]["rows"]
    rows = [row("กฎจริง", b),
            row("ทุกไม้แย่ลง 0.05R", A["-0.05R"]), row("ทุกไม้แย่ลง 0.10R", A["-0.10R"], "เกณฑ์: ยังบวก"), row("ทุกไม้แย่ลง 0.15R", A["-0.15R"], "จุดเกือบเสมอตัว"),
            row("ต้นทุนเป็น 2 เท่า", A["cost x2"], f"ต้นทุนกลางต่อไม้ {A['median cost R']:.3f}R"),
            row(f"เข้าช้า 1 แท่ง {book}", Rb["c"], "เกณฑ์: ยังบวก")]
    rows += [row(f"ตัด {THS.get(m, m)} ออก", v) for m, v in Rb["e"].items()]
    pl = Rb["d"]
    rows.append(f"<tr><td>ราคาสุ่ม (drift placebo) 5 ชุด</td><td class='n'>~{int(np.mean([x['n'] for x in pl])):,}</td>"
                f"<td class='n neg'>{min(x['net'] for x in pl):+.3f} ถึง {max(x['net'] for x in pl):+.3f}</td>"
                f"<td class='n'>{min(x['t'] for x in pl):+.1f} ถึง {max(x['t'] for x in pl):+.1f}</td><td>เกณฑ์: t จริงสูงกว่าทุกชุด</td></tr>")
    t = ("<table class='cmp'><thead><tr><th>การทดสอบ</th><th class='n'>ไม้</th><th class='n'>R ต่อไม้</th><th class='n'>t</th><th>หมายเหตุ</th></tr></thead><tbody>"
         + "".join(rows) + "</tbody></table>")
    def nbc(x):
        if "brk" in x:                                   # m30_robust.json rows
            return f"brk55 ≥ {x['brk']:+.2f} ATR", f"≥ {x['atr']:.2f}", "ใช่" if x["htf"] else "ไม่ใช้"
        near = f"{x['near']} ≥ {x['thr']:+.2f}" + (" ATR" if x["near"].startswith("brk") else "")
        return near, ("ไม่ใช้" if x["vol"] is None else f"≥ {x['vol']:.2f}"), {"htf1_with": "ใช่", "-": "ไม่ใช้"}.get(x["ctx"], x["ctx"])
    nbt = ("<table class='cmp'><thead><tr><th>ใกล้จุดสูง</th><th>ATR14/ATR100</th><th>TF ใหญ่ทางเดียวกัน</th><th class='n'>ไม้</th><th class='n'>R ต่อไม้</th><th class='n'>t</th></tr></thead><tbody>"
           + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in nbc(x)) + f"<td class='n'>{x['n']:,}</td>"
                     f"<td class='n {cl(x['net'])}'>{x['net']:+.3f}</td><td class='n'>{x['t']:+.1f}</td></tr>" for x in nb) + "</tbody></table>")
    yrs = " · ".join(f"{y} <span class='{cl(v)}'>{v:+.2f}</span>" for y, v in Rb["f"]["years"].items())
    ok = Rb["checks"]
    head = (f"<p style='margin:0 0 10px'><b>ผล: {'ทนทาน ผ่านทุกข้อที่ลงทะเบียนไว้' if Rb['robust'] else 'ไม่ผ่าน ' + ', '.join(k for k, v in ok.items() if not v)}</b> · "
            f"ไม้ {book} {len(Rb['markets'])} ตลาด รวม {b['n']:,} ไม้ 2011–2026 · ค่าข้างเคียง {Rb['b']['n_ok']} จาก {len(nb)} ชุดบวกและ t ≥ 2 (เกณฑ์ 14) · "
            f"ปีที่เป็นบวก {Rb['f']['share_pos']:.0%}</p>")
    return (f'<section class="card"><h2>ความทนทานของไม้ {book}</h2>' + head + '<div class="cmp-grid"><div class="tbl">' + t + '</div><div class="tbl">' + nbt +
            "</div></div><p class='muted' style='margin:10px 0 0;font-size:13px'>R ต่อไม้รายปี: " + yrs + "</p></section>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleeve", default="XAUUSD,XAGUSD,BTCUSD", help="sleeve markets")
    ap.add_argument("--verdict", default="", help="html of the verdict line (default: the m30_sleeve_with_g27kf one)")
    ap.add_argument("--robust", default="", help="json from m30_robust.py to show as a card")
    ap.add_argument("--h1", default="", help="H1 sleeve markets (the h1_sleeve pick): F + M30 vs F + M30 + H1")
    ap.add_argument("--h1-robust", default="", help="json from h1_sleeve.py --part robust")
    ap.add_argument("--cent", default="", help="markets tradable on the Cent account, e.g. XAUUSD,XAGUSD,BTCUSD,USDJPY")
    a = ap.parse_args()
    global SLEEVE, SYS, CENT
    smk = a.sleeve.split(",")
    hmk = a.h1.split(",") if a.h1 else []
    if a.cent:
        CENT = tuple(a.cent.split(","))
    SYS = systems(CENT, bool(hmk))
    SLEEVE = tuple(m + "_M30" for m in smk) + tuple(m + "_H1" for m in hmk)
    t0 = time.time()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    sleeve = [r for r in sleeve_rows(C, smk) if W.ts(START) <= r["t"] < W.ts(END)]
    print(f"  M30 sleeve: {len(sleeve)} trades, R {np.mean([r['R'] for r in sleeve]):+.3f}", flush=True)
    hspec = HS.spec_of(HS.pick()) if hmk else None
    if hmk:
        hs = [r for r in sleeve_rows(C, hmk, hspec) if W.ts(START) <= r["t"] < W.ts(END)]
        print(f"  H1 sleeve: {len(hs)} trades, R {np.mean([r['R'] for r in hs]):+.3f}", flush=True)
        sleeve += hs
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
    slv = {s: [u for u in SLEEVE if BASE(u) in ms and BOOK(u) in bk] for s, (_, ms, bk) in SYS.items()}     # JP225 sleeves on Standard only
    RWF.UNIS.update({port[s]: list(ms) + slv[s] for s, (_, ms, bk) in SYS.items()}, **{m: [m] for m in allm + SLEEVE})
    out, sized_rows, stress, mc, halves = {}, {}, {}, {}, {}
    for s, (label, ms, bk) in SYS.items():
        rr = [r for r in rows if r["mkt"] in ms] + [r for r in sleeve if r["mkt"] in slv[s]]
        rr.sort(key=lambda r: (r["t"], r["mkt"]))
        for v, (k, ver) in VCONF.items():
            scale = dict(HALF_OF(ms, k), **{m: K_SLEEVE for m in slv[s]})
            vr = sized(rr, ver, news, scale)
            sized_rows[(s, v)] = vr
            for u in [port[s], *ms, *slv[s]]:
                ent = RWF.build_entry(f"{s}~{v}", u, vr, k / 100, None, RP, G)
                if ent:
                    out[f"{s}~{v}_{u}"] = ent
            for extra in (0.0, 0.10):
                st, eq, _ = SU.simulate(frame(rr, scale, extra), ver, START, END, news=news)
                a1, _, _ = SU.simulate(frame(rr, scale, extra), ver, START, MID, news=news)
                a2, _, _ = SU.simulate(frame(rr, scale, extra), ver, MID, END, news=news)
                m_ = SU.monte_carlo(eq)
                stress[(s + v, extra)] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], h1=a1["mar"], h2=a2["mar"], p50=m_["p_dd50"])
                if extra == 0.0:
                    mc[s + v], halves[s + v] = m_, (a1["mar"], a2["mar"])
        print(f"  {s} {label} done  {time.time() - t0:.0f}s", flush=True)

    S_, E_ = pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC")
    keys = [s + v for v in VCONF for s in SYS]                     # 12 combinations, grouped by risk level
    E = {s + v: out[f"{s}~{v}_{port[s]}"] for s in SYS for v in VCONF}
    name = {s + v: f"{SYS[s][0]} · {VERS[v]}" for s in SYS for v in VCONF}
    mar = lambda r: r["cagr"] / r["equity_dd"]["relative_pct"]
    worst = lambda r: min(r["yearly"], key=lambda y: y["ret"])
    rws = [("เงินสุดท้าย (เริ่ม $100,000)", lambda s: E[s]["final"], 0, lambda v: f"${v / 1e6:,.1f}M"),
           ("ต่อปี", lambda s: E[s]["cagr"], 0, lambda v: f"{v:.1%}"),
           ("Equity DD", lambda s: E[s]["equity_dd"]["relative_pct"], 0, lambda v: f"{v:.1%}"),
           ("MAR", lambda s: mar(E[s]), 0, lambda v: f"{v:.2f}"),
           ("MAR 2011–17", lambda s: halves[s][0], 0, lambda v: f"{v:+.2f}"),
           ("MAR 2018–26", lambda s: halves[s][1], 0, lambda v: f"{v:+.2f}"),
           ("ปีแย่สุด", lambda s: worst(E[s])["ret"], 0, lambda v: f"{v:+.0%}"),
           ("ไม้", lambda s: E[s]["trades"], 0, lambda v: f"{v:,}"),
           ("DD>50%", lambda s: mc[s]["p_dd50"], 0, lambda v: f"{v:.1%}"),
           ("ต่อปี ถ้าแย่ลง 0.10R", lambda s: stress[(s, 0.10)]["cagr"], 0, lambda v: f"{v:+.1%}"),
           ("MAR ถ้าแย่ลง 0.10R", lambda s: stress[(s, 0.10)]["mar"], 0, lambda v: f"{v:.2f}"),
           ("DD>50% ถ้าแย่ลง 0.10R", lambda s: stress[(s, 0.10)]["p50"], 0, lambda v: f"{v:.1%}")]
    bk_txt = "ไม้ M30 และ H1" if hmk else "ไม้ M30"
    tl = ("G27K-F + M30 + H1" if hmk else "G27K-F + M30" + (f" {len(smk)} ตลาด" if len(smk) != 3 else ""))
    # one row per system, columns are measures; grouped by risk level
    head = "<th>ระบบ</th>" + "".join(f"<th class='n'>{lab}</th>" for lab, *_ in rws)
    body = ""
    for v in VCONF:
        body += f"<tr><td colspan='{len(rws) + 1}' style='font-weight:600;padding-top:14px'>G27K-F ความเสี่ยง {VERS[v]} · {bk_txt} 0.5% ต่อไม้</td></tr>"
        for s in SYS:
            body += f"<tr><td>{SYS[s][0]}</td>" + "".join(f"<td class='n'>{f(g(s + v))}</td>" for lab, g, w, f in rws) + "</tr>"
    table = f"<table class='cmp'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    stress_html = ("<p class='muted' style='margin:0;font-size:13px'>รวมอยู่ในตารางตัวเลขเทียบกันแล้ว (3 คอลัมน์ขวาสุด) "
                   f"ทุกไม้ทั้ง G27K-F และ{bk_txt} แย่ลง 0.10R</p>")
    years = sorted(set.intersection(*(set(y["year"] for y in E[k]["yearly"]) for k in keys)))
    Y = {k: {y["year"]: y["ret"] for y in E[k]["yearly"]} for k in keys}
    yhead = "<th>ปี</th>" + "".join(f"<th class='n'>{SYS[k[0]][0].replace('G27K-F', 'F')}<br>{VERS[k[1:]]}</th>" for k in keys)
    yt = (f"<table class='cmp'><thead><tr>{yhead}</tr></thead><tbody>"
          + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {'pos' if Y[k][y] >= 0 else 'neg'}'>{Y[k][y]:+.0%}</td>" for k in keys) + "</tr>" for y in years)
          + "</tbody></table>")
    cur = {}
    for s in SYS:
        me, cur[s] = RJ.monthly(RWF.account_var(sized_rows[(s, "r1b")]), S_, E_)
    curves = [(d, [cur[s][i] for s in SYS]) for i, d in enumerate(me)]
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
    for m in SLEEVE:
        R = np.array([r["R"] for r in sleeve if r["mkt"] == m]); t = np.array([r["t"] for r in sleeve if r["mkt"] == m])
        h1, h2 = (R[t < mid].mean() if (t < mid).any() else np.nan), R[t >= mid].mean()
        c1 = f"<td class='n {cl(h1)}'>{h1:+.2f}</td>" if np.isfinite(h1) else "<td class='n'>–</td>"
        perm.append(f"<tr><td>{TH[m]}</td><td class='n'>–</td><td class='n'>{len(R)}</td><td class='n'>–</td><td class='n'>–</td>"
                    f"<td class='n {cl(R.mean())}'>{R.mean():+.3f}</td><td class='n'>{tstat(R):.1f}</td>"
                    f"{c1}<td class='n {cl(h2)}'>{h2:+.2f}</td><td>{ACCT.get(BASE(m), 'Cent + Standard')}</td></tr>")
    perm_t = ("<table class='cmp'><thead><tr><th>ตลาด</th><th class='n'>ไม้เดิม</th><th class='n'>ไม้ F</th><th class='n'>ปิดเพราะข่าว</th><th class='n'>R เดิม</th>"
              "<th class='n'>R F</th><th class='n'>t</th><th class='n'>2011–18</th><th class='n'>2019–26</th><th>บัญชี</th></tr></thead><tbody>" + "".join(perm) + "</tbody></table>"
              "<p class='muted' style='margin:8px 0 0;font-size:13px'>R = R ต่อไม้หลังต้นทุน · F = G27K-F · กฎ Fed ใช้กับทอง เงิน BTC ETH เท่านั้น</p>")
    def cmp_row(lab, x, y):
        lab = lab
        f0, f1, s0, s1 = stress[(x, 0.0)], stress[(y, 0.0)], stress[(x, 0.10)], stress[(y, 0.10)]
        return (f"<tr><td>{lab}</td><td class='n'>{f0['cagr']:+.1%} → <b>{f1['cagr']:+.1%}</b></td><td class='n'>{f0['dd']:.1%} → <b>{f1['dd']:.1%}</b></td>"
                f"<td class='n'>{f0['mar']:.2f} → <b>{f1['mar']:.2f}</b></td><td class='n'>{s0['mar']:.2f} → <b>{s1['mar']:.2f}</b></td>"
                f"<td class='n'>{f0['p50']:.1%} → <b>{f1['p50']:.1%}</b></td></tr>")
    fed_t = ("<table class='cmp'><thead><tr><th>บัญชี</th><th class='n'>ต่อปี</th><th class='n'>DD (balance)</th><th class='n'>MAR</th><th class='n'>MAR ถ้าแย่ลง 0.10R</th>"
             "<th class='n'>โอกาส DD เกิน 50%</th></tr></thead><tbody>" + "".join(cmp_row(f"{acc} · {VERS[v]}", x + v, y + v) for v in VCONF for acc, x, y in (("Cent", "A", "B"), ("Standard", "C", "D"))) + "</tbody></table>"
             + ("<p class='muted' style='margin:8px 0 0;font-size:13px'>ซ้าย = G27K-F + M30 · ขวา = รวมไม้ H1 ที่ 0.5% ต่อไม้</p>" if hmk else
                "<p class='muted' style='margin:8px 0 0;font-size:13px'>ซ้าย = G27K-F อย่างเดียว · ขวา = รวมไม้ M30 ที่ 0.5% ต่อไม้</p>"))
    eq = lambda s: E[s]["equity_dd"]["relative_pct"]
    sr = np.array([r["R"] for r in sleeve if BOOK(r["mkt"]) == "M30"])
    hr = np.array([r["R"] for r in sleeve if BOOK(r["mkt"]) == "H1"])
    NEAR_TH = {"pos250": "ราคาอยู่ในช่วงบน {:.0%} ของ 250 แท่ง", "brk55": "ปิดไม่เกิน {:.2g} ATR จาก High/Low 55 แท่ง", "brk100": "ปิดไม่เกิน {:.3g} ATR จาก High/Low 100 แท่ง"}
    h1_desc = ""
    if hmk:
        nd = NEAR_TH[hspec["near"]].format(1 - hspec["thr"] if hspec["near"] == "pos250" else -hspec["thr"])
        h1_desc = (f"แท่ง H1 {nd} ในทิศที่เทรด" + (f" + ATR14/ATR100 ≥ {hspec['vol']:g}" if hspec["vol"] is not None else "")
                   + {"htf1_with": " + TF ใหญ่ (D1) ไปทางเดียวกัน", "ema20_50>=0": " + EMA20 อยู่ฝั่งเดียวกับ EMA50", "-": ""}[hspec["ctx"]]
                   + (" · เทรดทั้งสองทาง" if hspec["dir"] == "both" else " · ซื้ออย่างเดียว") + {"tp2": " · ทำกำไรที่ 2R", "t6": " · ปิดเมื่อครบ 6 แท่ง", "ch20": " · ออกตาม channel 20"}[hspec["exit"]])
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>ไม้ M30</b> = รูปแบบที่ผ่านการค้นแบบบีบให้แคบ: แท่ง M30 ปิดใกล้จุดสูง 55 แท่ง (ไม่เกิน 1 ATR) + ความผันผวน 14 แท่งสูงกว่า 100 แท่ง 1.5 เท่า + TF ใหญ่ไปทางเดียวกัน "
               f"เทรดทั้งสองทาง ทำกำไรที่ 2R · {' '.join(THS[m] for m in smk)} · {len(sr):,} ไม้ เฉลี่ย {sr.mean():+.3f}R · เปิดเป็นไม้แยก ความเสี่ยง 0.5% ต่อไม้</li>"
               + (f"<li><b>ไม้ H1</b> = ค้นด้วยขั้นตอนเดียวกับ M30: {h1_desc} · {' '.join(THS[m] for m in hmk)} · {len(hr):,} ไม้ เฉลี่ย {hr.mean():+.3f}R · ไม้แยกอีกชุด ความเสี่ยง 0.5% ต่อไม้</li>" if hmk else "")
               + "".join(f"<li><b>G27K-F {VERS[v]}</b>: " + " · ".join(f"{SYS[s][0]} {E[s + v]['cagr']:.1%} ต่อปี DD {eq(s + v):.0%}" for s in SYS) + "</li>" for v in VCONF)
               + (a.verdict or "<li><b>ผลการทดสอบที่ลงทะเบียนไว้: ยังไม่รับเข้าใช้</b> · ดีขึ้นทั้งสองบัญชีในสภาพปกติและทั้งสองช่วงเวลา แต่ Standard แย่ลงเมื่อทุกไม้แย่ลง 0.10R "
                  "เพราะไม้ M30 ได้ราว 0.14R ต่อไม้ ต้นทุนที่แย่ลงเพียง 0.10R กินไปเกือบหมด · ควร forward test เพื่อวัดต้นทุนจริงก่อน</li>") +
               f"<li><b>G27K-F</b> = G27K #1 + กฎข่าว Fed · ทุกตลาดเสี่ยงเท่ากัน · {bk_txt} ความเสี่ยง 0.5% ต่อไม้ทุกระดับ · เบรก 25% ใช้กับทั้งบัญชี</li></ul>")
    ckeys = list(SYS)
    pts = [dict(x=START, lab="เริ่ม " + START, **{s: float(W.DEPOSIT) for s in ckeys})]
    for d, vals in curves:
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {RJ.TH_M[d.month - 1]} {d.year}", **{s: float(v) for s, v in zip(ckeys, vals)}))
    short = ({"A": "Cent F+M30", "B": "Cent +H1", "C": "Std F+M30", "D": "Std +H1"} if hmk else {"A": "Cent F", "B": "Cent F+M30", "C": "Std F", "D": "Std F+M30"})
    data = json.dumps(dict(pts=pts, keys=ckeys, names=[short[s] for s in ckeys]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{SYS[s][0]}</span>' for i, s in enumerate(ckeys))
    css6 = ("<style>:root{--c5:#e87ba4;--c6:#008300}@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--c5:#d55181;--c6:#008300}}"
            ":root[data-theme=\"dark\"]{--c5:#d55181;--c6:#008300}</style>")
    cmp_html = (R5.CSS + css6 + f'<section class="card"><h2>{tl} · ความเสี่ยง 0.75% / 1% / 1% + เบรก 25% · {bk_txt} 0.5%</h2>' + summary +
                f'<div class="legend" style="margin-bottom:6px">{legend}<span class="muted">Balance สิ้นเดือน · สเกล log · กราฟนี้คือ G27K-F 1% + เบรก 25% (ระดับอื่นดูในตารางและแท็บด้านล่าง)</span></div><div id="cmpChart" class="chart"></div></section>'
                + robust_card(a.robust) + robust_card(a.h1_robust, "H1") +
                f'<div class="cmp-grid"><section class="card"><h2>{"ไม้ H1" if hmk else "ไม้ M30"} ช่วยแค่ไหน</h2><div class="tbl">' + fed_t + '</div></section>'
                '<section class="card"><h2>คุณภาพรายตลาด (ต่อไม้ 2011–2026)</h2><div class="tbl">' + perm_t + '</div></section></div>'
                '<section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">' + table + '</div></section>'
                '<section class="card"><h2>รายปี</h2><div class="tbl">' + yt + '</div></section>'
                '<section class="card"><h2>ถ้าต้นทุนจริงแย่กว่าโมเดล</h2><div class="tbl">' + stress_html + '</div></section>')
    cmp_js = R5.SCRIPT.replace("__DATA__", data)

    g_rules = ["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
               "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า (ปฏิทินข่าวมีตั้งแต่ปี 2022)",
               "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้",
               "กฎข่าว Fed: ถ้าผลตอบแทนพันธบัตรสหรัฐ 2 ปี (DGS2) วันใดขึ้นเกิน 2 เท่าของ SD การเปลี่ยนรายวันย้อนหลัง 250 วัน "
               "ให้ปิดไม้ทอง เงิน BTC ETH ที่ราคาเปิดชั่วโมงถัดไปหลัง 22:00 UTC ของวันทำการถัดไป และไม่เข้าไม้ใหม่ในตลาดเหล่านี้ 5 วัน"]
    info = {}
    for s, (label, ms, bk) in SYS.items():
        acct = (f"บัญชี Cent: {', '.join(ms)} (ไม่มี JP225" + (" และ ETH" if "ETHUSD" not in ms else "") + ") · BTCUSDc บน MT5 เท่านั้น") if "JP225" not in ms else "บัญชี Standard: มี JP225 ครบ 6 ตลาด"
        rn = {v: f"G27K-F {k:g}% ต่อไม้ทุกตลาด รวม BTC และ ETH" + (" · เบรก: ลดครึ่งเมื่อ DD ถึง 25% จนกลับมาไม่เกิน 12.5%" if ver == "brake" else " · ไม่มีเบรก")
              + "".join(f" · ไม้ {b} 0.5%" for b in bk) for v, (k, ver) in VCONF.items()}
        risk = rn["r1b"]
        m30r = ["ไม้ M30 (แยกจาก G27K-F): แท่ง M30 ปิดไม่เกิน 1 ATR จาก High/Low 55 แท่งในทิศที่เทรด + ATR14/ATR100 ≥ 1.5 + TF ใหญ่ไปทางเดียวกัน · "
                f"ซื้อหรือขายตามทิศนั้น · SL 2 × ATR20 (M30) · TP 2R · {' '.join(THS[BASE(u)] for u in slv[s] if BOOK(u) == 'M30')} · ความเสี่ยง 0.5% ต่อไม้"] if "M30" in bk else []
        if "H1" in bk:
            m30r.append(f"ไม้ H1 (แยกจาก G27K-F และ M30): {h1_desc} · SL 2 × ATR20 (H1) · {' '.join(THS[BASE(u)] for u in slv[s] if BOOK(u) == 'H1')} · ความเสี่ยง 0.5% ต่อไม้")
        info[s] = dict(label=f"{label}", tab=label, rules=g_rules + m30r + [f"ตลาด: {', '.join(ms)}"], notes=[f"<b>{acct}</b>", risk],
                       combo="C8/D3/E1/F1/G2/H2/I1/J1 + Fed", risk=0.01, adds=False, tf="H4", risk_note=risk, risk_notes=rn)
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
                       footer="สร้างจาก research/g27k_dev/report_g27kf_m30.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K")
    data = RWF.clean(out)
    tpl = (HERE.parent / "walkforward_report_template.html").read_text(encoding="utf-8")
    ulist = [port[s] for s in SYS] + list(allm) + list(SLEEVE)
    uni_th = {port[s]: f"พอร์ต {SYS[s][0]}" for s in SYS}
    uni_th.update({m: f"{TH.get(m, m)} ({m}) ตลาดเดียว" for m in allm + SLEEVE})
    pbtn = "\n        ".join(f'<button role="tab" data-u="{port[s]}">พอร์ต {SYS[s][0]}</button>' for s in SYS)
    mbtn = "\n        ".join(f'<button role="tab" data-u="{m}">{TH.get(m, m)}</button>' for m in allm + SLEEVE if m not in ("XAUUSD", "XAGUSD", "BTCUSD"))
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", f"<title>{tl}</title>"),
        ("Strategy Tester · Walk-forward report", f"Strategy Tester · {tl}"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", ("G27K-F + ไม้ M30 + ไม้ H1" if hmk else "G27K-F + ไม้ M30") + " · Cent และ Standard · 15 ปี"),
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
         'try { const vv = localStorage.getItem("g27kfm30ver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => { b.hidden = !D[keyOf(SYS, b.dataset.u)]; b.setAttribute("aria-selected", b.dataset.u === UNI); });\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; UNI = PORTS[SYS] || UNI; fixUni(); try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; fixUni(); try { localStorage.setItem("g27kfm30ver", VER); } catch (x) {} render(); });'),
        ("const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;", "fixUni();\n  const r = D[keyOf(SYS, UNI)], SI = SINFO[SYS], GM = D.META;"),
        ('<section class="kpis" id="kpis"></section>',
         '__CMP__<h2 style="margin:6px 0 10px">รายละเอียดแต่ละระบบ</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:60]
        tpl = tpl.replace(x, y, 1)
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    pathlib.Path(a.out).write_text(tpl.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for k_ in keys:
        m = E[k_]
        print(f"  {k_:4s} {name[k_]:40s} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']['relative_pct']:.1%} MAR {mar(m):.2f} trades {m['trades']} | "
              f"stress MAR {stress[(k_, 0.1)]['mar']:.2f} p50 {stress[(k_, 0.1)]['p50']:.1%}")
    print(f"  written {a.out}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
