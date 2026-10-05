"""G27K-F + M30 + H1 on the Cent account without USDJPY (gold, silver, BTC, ETH), no brake, in the G27K Strategy-Tester layout.

Same template (research/walkforward_report_template.html) and the same metric code (report768.metrics from the data snapshot) as the
research session's G27K reports, so every figure is computed the way theirs are. Differences, all forced by what this machine has:
  - trades come from the hand-off files (handoff/trades_*.csv.gz), not from re-running the research engine;
  - the version tabs are cost versions (cent4_costs.py) instead of risk levels: as published, real Cent spreads with swap case D,
    and real Cent spreads with swap case B;
  - open P&L between entry and exit is marked on H1 bars: gold and silver from the snapshot's Candle Lab + MT5 bars, BTC and ETH
    from the MT5 terminal (Exness), which has no crypto before 2018-03 (BTC) / 2018-07 (ETH); those early crypto trades show
    equity = balance while open, and their MFE/MAE are the lower bounds max(R, 0) / max(-R, 0).
Top cards add the minimum capital (cent4_capital.py) and the cost comparison.

Usage: python report_cent4.py [--out report_cent4.html]   (run cent4_capital.py first)
"""
from __future__ import annotations

import argparse
import ast
import heapq
import json
import math
import pathlib
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import cent4_capital as K
import cent4_costs as CC

sys.path.insert(0, str(CC.SNAP / "research" / "grid768"))
import report768 as RP  # noqa: E402

RESEARCH = CC.HANDOFF.parent.parent
TEMPLATE = RESEARCH / "walkforward_report_template.html"
START, END = K.START, K.END
DEPOSIT = 100_000.0
VERS = list(CC.VERSIONS)
TH = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "BTCUSD": "BTC", "ETHUSD": "ETH"}
BOOK_TH = {"F": "G27K-F", "M30": "M30", "H1": "H1"}
UNITS = [m for m in CC.M4] + [f"{m}_{b}" for b in ("M30", "H1") for m in CC.M4]
UNIS = {"PA": UNITS, **{u: [u] for u in UNITS}}
base = lambda u: u.split("_")[0]
book = lambda u: u.split("_")[1] if "_" in u else "F"
uname = lambda u: TH[base(u)] + ("" if book(u) == "F" else " " + book(u))
TH_M = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def r5_strings():
    """CSS and the month-end comparison chart of report_five.py, read from its source (importing it needs the research data)."""
    tree = ast.parse((RESEARCH / "g27k_dev" / "report_five.py").read_text(encoding="utf-8"))
    out = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
           if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("CSS", "SCRIPT")}
    script = out["SCRIPT"].replace("[5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7]", "[5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7, 2e7, 5e7, 1e8, 2e8, 5e8, 1e9]")
    script = script.replace('aria-label="Balance สิ้นเดือนของ 4 ชุดตลาด สเกล log"', 'aria-label="Balance สิ้นเดือนของ 4 แบบต้นทุน สเกล log"')
    assert "1e9]" in script
    return out["CSS"], script


def h1_frames():
    """H1 bars per market for marking open trades: gold and silver from the snapshot (Candle Lab + MT5) with the terminal's bars
    after the snapshot ends; BTC and ETH from the terminal."""
    import MetaTrader5 as mt5
    mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe") or mt5.initialize()
    F, src = {}, {}
    for m in CC.M4:
        mt5.symbol_select(m, True)
        r = mt5.copy_rates_range(m, mt5.TIMEFRAME_H1, datetime(2009, 1, 1, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc))
        x = pd.DataFrame(dict(t=r["time"].astype(np.int64), h=r["high"], l=r["low"], c=r["close"]))
        if m in CC.METALS:
            z = np.load(CC.SNAP / "data" / "bundle" / f"bars_{m}_H1.npz")
            b = pd.DataFrame(dict(t=z["t"].astype(np.int64), h=z["h"], l=z["l"], c=z["c"]))
            x = pd.concat([b, x[x.t > b.t.max()]])
        x = x.drop_duplicates("t").sort_values("t")
        F[m] = dict(t=x.t.to_numpy(np.int64), h=x.h.to_numpy(float), l=x.l.to_numpy(float), c=x.c.to_numpy(float), sec=3600)
        src[m] = str(pd.to_datetime(F[m]["t"][0], unit="s").date())
    mt5.shutdown()
    return F, src


def rows_for(D, v, F):
    """Report rows (report768 shape) for one cost version."""
    rows, nomark = [], 0
    for r in D.itertuples():
        X = F[r.market]
        has = X["t"][0] <= r.t
        e = int(np.searchsorted(X["t"], r.t, "right") - 1)
        x = int(np.searchsorted(X["t"], r.tx, "right") - 1)
        R, Rs, Rw = getattr(r, f"R_{v}"), getattr(r, f"R_spread_{v}"), getattr(r, f"R_swap_{v}")
        triple = 3 if r.market in CC.METALS else 5
        nt = int(RP.C.nights(np.array([r.t]), np.array([r.tx]), triple)[0])
        d, ep, rk = int(r.direction), float(r.entry_price), float(r.stop_distance)
        if has and x >= e:
            hi, lo = float(X["h"][e:x + 1].max()), float(X["l"][e:x + 1].min())
            mfe = max(0.0, (hi - ep) / rk if d > 0 else (ep - lo) / rk)
            mae = max(0.0, (ep - lo) / rk if d > 0 else (hi - ep) / rk)
        else:
            nomark += 1
            e = x = max(e, 0)
            mfe, mae = max(r.R_gross_eff, 0.0), max(-r.R_gross_eff, 0.0)
        rows.append(dict(mkt=r.market if r.book == "F" else f"{r.market}_{r.book}", t=int(r.t), t_exit=int(r.tx), R=float(R), R_gross=float(r.R_gross_eff),
                         R_spread=float(Rs), R_swap=float(Rw), d=d, ep=ep, px=float(r.exit_price), units=[(ep, e, int(r.t))], mfe=mfe, mae=mae,
                         gaps=0, same=0, risk=rk, stop_pct=float(r.stop_pct), cost=float(Rs) * float(r.stop_pct),
                         swr=float(Rw) * float(r.stop_pct) / nt if nt > 0 else 0.0, triple=triple, X=X, e=e, x=x, risk_frac=K.RISK[r.book]))
    return rows, nomark


def account_var(rows, scale=1.0, deposit=DEPOSIT):
    """report_walkforward10y.account_var: every trade keeps its own risk fraction, optionally scaled."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["t"], rows[i]["mkt"]))
    bal, heap, live, out = deposit, [], {}, []
    for i in order:
        tr = rows[i]
        while heap and heap[0][0] <= tr["t"]:
            _, k = heapq.heappop(heap)
            r = live.pop(k); bal += r["pnl"]; out.append(r)
        rf = tr["risk_frac"] * scale
        live[i] = dict(tr, unit_usd=rf * bal, pnl=rf * bal * tr["R"], bal_before=bal)
        heapq.heappush(heap, (tr["t_exit"], i))
    while heap:
        _, k = heapq.heappop(heap)
        out.append(live.pop(k))
    out.sort(key=lambda r: (r["t_exit"], r["t"]))
    b = deposit
    for r in out:
        b += r["pnl"]; r["bal_after"] = b
    return out


def build_entry(key, uni, rows, H4):
    mk = UNIS[uni]
    sub = [r for r in rows if r["mkt"] in mk]
    br = 0.005 if all(book(u) != "F" for u in mk) else 0.01
    acc = account_var(sub)
    bases = sorted({base(u) for u in mk})
    T = RP.timeline(acc, {m: H4[m] for m in bases})
    RP.prep_marks(acc, T)
    with np.errstate(all="ignore"):
        M = RP.metrics(acc, T, br)
        table = []
        for rk in RP.RISKS:
            a2 = account_var(sub, rk / br)
            RP.prep_marks(a2, T)
            table.append(RP.metrics(a2, T, rk, full=False))
    sh = [r for r in acc if r["d"] < 0]
    M["short_win"] = float(np.mean([r["pnl"] > 0 for r in sh])) if sh else 0.0
    bars = int(sum(int((H4[m]["t"] >= RP.G.START).sum()) for m in bases))
    return dict(key=key, uni=uni, mkts=mk, deposit=DEPOSIT, markets=len(bases), bars=bars, risk_table=table, **M), acc


def clean(o):
    if isinstance(o, float):
        return None if not np.isfinite(o) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.floating):
        return clean(float(o))
    if isinstance(o, np.integer):
        return int(o)
    return o


def monte_carlo(eq, runs=4000, years=10, block=6, seed=7):
    """suite.monte_carlo: block bootstrap of month-end returns, share of 10-year paths with a drawdown above 50 %."""
    me = eq.resample("ME").last().ffill()
    x = me.pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    nb = math.ceil(years * 12 / block)
    dds = np.empty(runs)
    for k in range(runs):
        path = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, nb)])[: years * 12]
        v = np.cumprod(1 + path)
        dds[k] = np.max(1 - v / np.maximum.accumulate(np.r_[1.0, v])[1:])
    return float((dds > 0.5).mean())


def dca(D, rcol, monthly=100.0):
    """The operator's plan on the Cent account: $100 on the first of every month from Sep 2011 (the first deposit opens the
    account), exact sizing, no brake. IRR on the deposit dates; unit drawdown = drawdown of the NAV that deposits do not mask."""
    s0, s1 = CC.ts(pd.Series([START])).iat[0], CC.ts(pd.Series([END])).iat[0]
    months = [int(pd.Timestamp(d, tz="UTC").timestamp()) for d in pd.date_range(START, END, freq="MS", inclusive="left")]
    ev = sorted([(m, 0, -1) for m in months] + [(int(t), 1, i) for i, t in enumerate(D.t)])
    bal, nav, pk_nav, dd_nav = 0.0, 1.0, 1.0, 0.0
    heap, flows, below, below_at, dep = [], [], 0.0, None, 0.0
    tx, Rv, bk = D.tx.to_numpy(), D[rcol].to_numpy(), D.book.to_numpy()
    for t, kind, i in ev:
        while heap and heap[0][0] <= t:
            x, pnl = heapq.heappop(heap)
            nav *= (bal + pnl) / bal if bal > 0 else 1.0
            bal += pnl
            pk_nav = max(pk_nav, nav); dd_nav = max(dd_nav, 1 - nav / pk_nav)
            if dep > 0 and 1 - bal / dep > below:
                below, below_at = 1 - bal / dep, x
        if kind == 0:
            bal += monthly; dep += monthly; flows.append((t, monthly))
            continue
        if bal <= 0:
            continue
        heapq.heappush(heap, (int(tx[i]), K.RISK[bk[i]] * bal * Rv[i]))
    while heap:
        x, pnl = heapq.heappop(heap)
        bal += pnl
    yr = 365.25 * 86400
    f = lambda r: sum(a * (1 + r) ** ((s1 - t) / yr) for t, a in flows) - bal
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return dict(deposited=dep, final=bal, irr=(lo + hi) / 2, unit_dd=dd_nav, below=below,
                below_at=str(pd.to_datetime(below_at, unit="s").strftime("%Y-%m")) if below_at else "-")


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(CC.HERE / "report_cent4.html"))
    a = ap.parse_args()
    t0 = time.time()
    RP.G.START = int(CC.ts(pd.Series([START])).iat[0])
    cap = json.loads((CC.HERE / "cent4_capital.json").read_text(encoding="utf-8"))
    T = CC.load()
    D = CC.versions(T)
    F, src = h1_frames()
    H4 = {m: dict(t=np.unique(F[m]["t"] // 14400 * 14400), sec=14400) for m in CC.M4}
    print(f"  {len(D)} trades, H1 bars from " + ", ".join(f"{m} {s}" for m, s in src.items()), flush=True)

    out, acc_pa = {}, {}
    for v in VERS:
        rows, nomark = rows_for(D, v, F)
        for u in UNIS:
            ent, acc = build_entry(f"A~{v}", u, rows, H4)
            out[f"A~{v}_{u}"] = ent
            if u == "PA":
                acc_pa[v] = acc
        e = out[f"A~{v}_PA"]
        print(f"  {v:6s} CAGR {e['cagr']:+.1%} equity DD {e['equity_dd']['relative_pct']:.1%} balance DD {e['balance_dd']['relative_pct']:.1%} "
              f"trades {e['trades']} final ${e['final']:,.0f} | {nomark} crypto trades before the terminal's data, no marks | {time.time() - t0:.0f}s", flush=True)

    # ------------------------------------------------ comparison rows: version x brake, plus 0.10R worse
    cmp = {}
    for v in VERS:
        for brake in (False, True):
            st, _, eq = K.account(D, f"R_{v}", brake=brake)
            h1, _, _ = K.account(D, f"R_{v}", brake=brake, t1="2019-01-01")
            h2, _, _ = K.account(D, f"R_{v}", brake=brake, t0="2019-01-01")
            Ds = D.assign(R_s=D[f"R_{v}"] - 0.10)
            ss, _, eqs = K.account(Ds, "R_s", brake=brake)
            yr = eq.resample("YE").last()
            yr = yr / yr.shift(1).fillna(DEPOSIT) - 1
            cmp[(v, brake)] = dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar1=h1["mar"], mar2=h2["mar"],
                                   worst=float(yr.min()), worst_at=int(yr.idxmin().year), n=st["n"], p50=monte_carlo(eq),
                                   s_cagr=ss["cagr"], s_mar=ss["mar"], s_p50=monte_carlo(eqs),
                                   eqdd=out[f"A~{v}_PA"]["equity_dd"]["relative_pct"] if not brake else None)
    print(f"  comparison done {time.time() - t0:.0f}s", flush=True)
    dc = {v: dca(D, f"R_{v}") for v in VERS}
    print("  DCA " + " | ".join(f"{v} ${x['final']:,.0f} IRR {x['irr']:.1%}" for v, x in dc.items()), flush=True)

    html = render(out, cmp, dc, cap, D, src, acc_pa)
    pathlib.Path(a.out).write_text(html, encoding="utf-8")
    summ = dict(cmp={f"{v}{'_brake' if b else ''}": x for (v, b), x in cmp.items()}, dca=dc,
                pa={v: dict(cagr=out[f"A~{v}_PA"]["cagr"], eqdd=out[f"A~{v}_PA"]["equity_dd"]["relative_pct"],
                            bdd=out[f"A~{v}_PA"]["balance_dd"]["relative_pct"], final=out[f"A~{v}_PA"]["final"], trades=out[f"A~{v}_PA"]["trades"])
                    for v in VERS})
    (CC.HERE / "report_cent4_summary.json").write_text(json.dumps(clean(summ), indent=1, default=float), encoding="utf-8")
    print(f"  written {a.out} ({pathlib.Path(a.out).stat().st_size / 1e6:.1f} MB)  {time.time() - t0:.0f}s")


# ======================================================================================================== html
def render(out, cmp, dc, cap, D, src, acc_pa):
    css5, script5 = r5_strings()
    cl = lambda v: "pos" if v > 0 else "neg"
    pc = lambda v, d=1: f"{v:.{d}%}"
    usd = lambda v: f"${v / 1e9:,.2f}B" if v >= 1e9 else f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v:,.0f}"
    V = CC.VERSIONS
    need = pd.DataFrame(cap["need"])
    bm = need.loc[need.need_med.idxmax()]
    st = {x["start"]: x for x in cap["static"]}
    rp12 = [x for x in cap["replay"] if x["window"] == "12m"]
    rp3 = {x["start"]: x for x in cap["replay"] if x["window"] == "3y"}
    wname = lambda s: f"{BOOK_TH[s.split()[0]]} {TH[s.split()[1]]}"
    wb, wm = st[100]["worst"].split()
    wrow = need[(need.book == wb) & (need.market == wm)].iloc[0]
    others = math.ceil(need[need.market != "XAGUSD"].need_med.max() / 10) * 10
    px = cap["prices"]

    # ---------------- summary
    e = {v: out[f"A~{v}_PA"] for v in V}
    c = {k: x for k, x in cmp.items()}
    summary = ("<ul class='cmp-sum'>"
               f"<li><b>ชุดนี้</b>: G27K-F 1% ต่อไม้ (ไม่มีเบรก) + ไม้ M30 0.5% + ไม้ H1 0.5% · บัญชี Cent 4 ตลาด ทอง เงิน BTC ETH (ตัด USDJPY) · "
               f"{len(D):,} ไม้ ก.ย. 2011 – ก.ย. 2026 · เริ่ม $100,000 แบบรายงาน G27K ทุกฉบับ</li>"
               f"<li><b>ทุนขั้นต่ำ: ${math.ceil(bm.need_med / 10) * 10:,.0f} (≈{math.ceil(bm.need_med / 10) * 1000:,.0f} USC)</b> · ตัวกำหนดคือ{uname(bm.market + ('_' + bm.book if bm.book != 'F' else ''))} "
               f"· ที่ทุนนี้ lot ขั้นต่ำเสี่ยงไม่เกินที่ตั้งสำหรับไม้ขนาด SL กลางของทุกชุดทุกตลาด · <b>แนะนำ $200–300</b> ให้ไม้ SL กว้างไม่เสี่ยงเกินมาก · "
               f"ตั้งแต่ $500 ผลเท่ากับขนาดไม้ที่ออกแบบ (รายละเอียดการ์ดถัดไป)</li>"
               + "".join(f"<li><b>{V[v]}</b>: {pc(c[(v, False)]['cagr'])} ต่อปี · Equity DD {pc(e[v]['equity_dd']['relative_pct'], 0)} · "
                         f"MAR {c[(v, False)]['mar']:.2f} · ถ้ามีเบรก 25% {pc(c[(v, True)]['cagr'])} DD {pc(c[(v, True)]['dd'], 0)}</li>" for v in V)
               + "<li><b>ตัวเลขที่ควรใช้คิด</b>: ช่วงระหว่าง Cent + swap C กับ Cent + swap D ซึ่งต่างกันแค่ swap ของ BTC/ETH · "
                 "D ใช้จุด swap ของวันนี้ย้อนหลังทุกปี เท่ากับ swap ราว 70–116% ต่อปีของมูลค่าในปี 2017–20 ที่ BTC ถูกกว่าวันนี้ 7–20 เท่า จึงน่าจะแพงเกินจริง · "
                 "C ใช้ % ต่อปีเท่าวันนี้ · รายงานนี้ตั้งต้นที่ D เพื่อไม่มองดีเกินไป · กรณี B เป็นขอบล่างแบบมองร้าย (คิด swap โลหะแพงเกินจริงในปีดอกเบี้ยต่ำ) · "
                 "ตัวเลขทั้งหมดเป็นเพดานบน เพราะกฎเลือกจากข้อมูลชุดเดียวกัน</li>"
               "<li><b>ไม่มีเบรกต่างจากมีเบรกอย่างไร</b>: กำไรต่อปีสูงกว่า แต่ DD ลึกกว่าและไม้ช่วงขาดทุนหนักไม่ถูกลดขนาด "
               "(เบรกลดความเสี่ยงครึ่งหนึ่งเมื่อ DD ถึง 25% จนกลับมาไม่เกิน 12.5%)</li></ul>")
    me = pd.date_range(START, END, freq="ME")
    chart_rows = [month_end_balance(acc_pa[v], me) for v in V]
    pts = [dict(x=START, lab="เริ่ม " + START, **{v: DEPOSIT for v in V})]
    for i, d in enumerate(me):
        pts.append(dict(x=str(d.date()), lab=f"สิ้น {TH_M[d.month - 1]} {d.year}", **{v: float(chart_rows[k][i]) for k, v in enumerate(V)}))
    data = json.dumps(dict(pts=pts, keys=list(V), names=[CC.SHORT[v] for v in V]), ensure_ascii=False)
    legend = "".join(f'<span><i style="background:var(--c{i + 1})"></i>{V[v]}</span>' for i, v in enumerate(V))
    top = (f'<section class="card"><h2>G27K-F + M30 + H1 · Cent ทอง เงิน BTC ETH · ไม่มีเบรก · 4 แบบต้นทุน</h2>{summary}'
           f'<div class="legend" style="margin-bottom:6px">{legend}<span class="muted">Balance สิ้นเดือน · สเกล log · เริ่ม $100,000 · ขนาดไม้ตามสัดส่วน · ไม่มีเบรก</span></div>'
           '<div id="cmpChart" class="chart"></div></section>')

    # ---------------- minimum capital
    rows_n = ""
    for b in ("F", "M30", "H1"):
        for r in need[need.book == b].itertuples():
            hl = " style='background:var(--hl);font-weight:600'" if (r.book == bm.book and r.market == bm.market) else ""
            rows_n += (f"<tr{hl}><td>{BOOK_TH[b]} {TH[r.market]}</td><td class='n'>{K.RISK[b]:.1%}</td><td class='n'>{r.n}</td><td class='n'>{r.min_lot:.2f}</td>"
                       f"<td class='n'>{r.stop_med:.2%}</td><td class='n'>${r.minlot_risk_med:.2f}</td><td class='n'><b>${r.need_med:,.0f}</b></td>"
                       f"<td class='n'>{r.stop_p90:.2%}</td><td class='n'>${r.need_p90:,.0f}</td><td class='n'>${r.need_max:,.0f}</td></tr>")
    t_need = ("<table class='cmp'><thead><tr><th>ชุด · ตลาด</th><th class='n'>เสี่ยงต่อไม้</th><th class='n'>ไม้ 12 เดือน</th><th class='n'>lot ต่ำสุด</th>"
              "<th class='n'>SL กลาง</th><th class='n'>lot ต่ำสุดเสี่ยง</th><th class='n'>ทุนที่ต้องมี (SL กลาง)</th><th class='n'>SL p90</th>"
              "<th class='n'>ทุน (SL p90)</th><th class='n'>ทุน (SL กว้างสุด)</th></tr></thead><tbody>" + rows_n + "</tbody></table>"
              f"<p class='muted' style='margin:8px 0 0;font-size:13px'>SL เป็น % ของราคา จากไม้ที่เข้า ต.ค. 2025 – ก.ย. 2026 · ราคาวันนี้ ({cap['prices_at'][:16]} UTC): "
              + " · ".join(f"{TH[m]} {p:,.2f}" for m, p in px.items()) +
              " · ทุนที่ต้องมี = เงินที่ lot ต่ำสุดเสียเมื่อโดน SL ÷ ความเสี่ยงที่ตั้ง · สัญญา Cent: ทอง 1 oz, เงิน 50 oz, BTC 0.01, ETH 0.01 ต่อ lot</p>")
    srow = lambda x, hl=False: (f"<tr{' class=\"sel\"' if hl else ''}><td>${x['start']:,}</td><td class='n'>{pc(x['over125'])}</td><td class='n'>{pc(x['over15'])}</td>"
                                f"<td class='n'>{pc(x['over2'])}</td><td class='n'>{x['max_ratio']:.1f} เท่า</td><td>{wname(x['worst'])}</td></tr>")
    pick = [100, 130, 150, 200, 300, 500, 1000]
    t_static = ("<table class='cmp'><thead><tr><th>ทุน</th><th class='n'>ไม้ที่เสี่ยงเกิน 1.25 เท่า</th><th class='n'>เกิน 1.5 เท่า</th><th class='n'>เกิน 2 เท่า</th>"
                "<th class='n'>มากสุด</th><th>ไม้ที่เกินมากสุด</th></tr></thead><tbody>" + "".join(srow(st[s], s == 130) for s in pick if s in st) + "</tbody></table>"
                "<p class='muted' style='margin:8px 0 0;font-size:13px'>ทุนคงที่เทียบกับไม้ทุกไม้ 12 เดือนล่าสุด (576 ไม้) ที่ราคาวันนี้ หลังปัด lot ใกล้สุดและไม่ต่ำกว่า lot ต่ำสุด · "
                "ราวครึ่งหนึ่งของไม้เสี่ยงเกินที่ตั้งเล็กน้อยทุกระดับทุน เพราะการปัดขึ้นหรือลง ไม่ใช่ผลของทุนน้อย</p>")
    rrow = lambda x: (f"<tr><td>${x['start']:,}</td><td class='n {cl(x['final'] / x['start'] - 1)}'>{x['final'] / x['start'] - 1:+.0%}</td>"
                      f"<td class='n'>{x['exact_final'] / x['start'] - 1:+.0%}</td><td class='n'>{pc(x['dd'])}</td><td class='n'>{pc(x['exact_dd'])}</td>"
                      f"<td class='n'>{pc(x['over15_share'])}</td><td class='n'>{pc(x['max_actual'], 2)}</td><td class='n'>{pc(x['peak_margin'], 2)}</td></tr>")
    t_replay = ("<table class='cmp'><thead><tr><th>เริ่มด้วย</th><th class='n'>ผล 12 เดือน (lot จริง)</th><th class='n'>ถ้าขนาดไม้พอดี</th><th class='n'>DD (lot จริง)</th>"
                "<th class='n'>DD ถ้าพอดี</th><th class='n'>ไม้ที่เสี่ยงเกิน 1.5 เท่า</th><th class='n'>เสี่ยงต่อไม้มากสุด</th><th class='n'>margin สูงสุด</th></tr></thead><tbody>"
                + "".join(rrow(x) for x in rp12) + "</tbody></table>"
                "<p class='muted' style='margin:8px 0 0;font-size:13px'>จำลอง 12 เดือนล่าสุด (ต.ค. 2025 – ก.ย. 2026) ที่ระดับราคาวันนี้ ด้วยต้นทุนแบบ spread Cent จริง + swap กรณี D ทบต้น ไม่มีเบรก · "
                f"ถ้าจำลอง 3 ปี (ต.ค. 2023 –) ทุกระดับทุนตั้งแต่ $100 ให้ผลเกือบเท่าขนาดไม้พอดี (DD {pc(rp3[100]['dd'])} เทียบ {pc(rp3[100]['exact_dd'])}) "
                "เพราะช่วงแรกตลาดนิ่งกว่าและบัญชีโตทันก่อนเงินผันผวนหนัก</p>")
    mincap = (f'<section class="card"><h2>ทุนขั้นต่ำ ถ้าเทรดทั้งชุดบนบัญชี Cent โดยไม่มี USDJPY</h2>'
              f"<p style='margin:0 0 10px'><b>ขั้นต่ำ ${math.ceil(bm.need_med / 10) * 10:,.0f}</b> (≈{math.ceil(bm.need_med / 10) * 1000:,.0f} USC) · "
              f"ตัวกำหนดคือไม้ {BOOK_TH[bm.book]} ของ{TH[bm.market]} ซึ่ง SL กลางกว้าง {bm.stop_med:.2%} ของราคา lot ต่ำสุด {bm.min_lot:.2f} "
              f"({bm.min_lot * K.SPEC[bm.market]['contract']:g} {'oz' if bm.market in CC.METALS else bm.market[:3]}) จึงเสีย ${bm.minlot_risk_med:.2f} ต่อไม้ "
              f"เท่ากับ 0.5% ของ ${bm.need_med:,.0f} · <b>แนะนำ $200–300</b>: ไม้ที่เสี่ยงเกิน 1.5 เท่าเหลือ {pc(st[300]['over15'])}–{pc(st[200]['over15'])} "
              f"และ DD 12 เดือนห่างจากขนาดไม้พอดีไม่ถึง 2 จุด · <b>ตั้งแต่ $500</b> แทบไม่ต่างจากขนาดไม้พอดี</p>"
              f"<p style='margin:0 0 10px'>ถ้าเริ่มที่ $100 ตามแผนเดิม: ไม้ {pc(st[100]['over15'])} เสี่ยงเกิน 1.5 เท่า ไม้ที่แย่สุด ({wname(st[100]['worst'])} SL กว้าง {wrow.stop_max:.1%} ของราคา) "
              f"เสี่ยง {st[100]['max_ratio']:.1f} เท่าของที่ตั้ง · จำลอง 12 เดือน DD {pc(rp12[0]['dd'])} เทียบ {pc(rp12[0]['exact_dd'])} ถ้าขนาดไม้พอดี · "
              f"ทอง BTC ETH ไม่เป็นปัญหาตั้งแต่ ${others:,.0f} ขึ้นไป ตัวที่ต้องการทุนมากสุดคือเงิน</p>"
              f"<div class='tbl'>{t_need}</div>"
              f"<div class='cmp-grid' style='margin-top:14px'><div class='tbl'>{t_static}</div><div class='tbl'>{t_replay}</div></div>"
              "<p class='muted' style='margin:10px 0 0;font-size:13px'>margin ไม่เป็นข้อจำกัด: เลเวอเรจ 1:2000 (ทอง เงิน) และ 1:400 (BTC ETH) ใช้ margin สูงสุดราว 1.1% ของทุน · "
              "ความผันผวนของเงินช่วงนี้สูงผิดปกติ (ต้น 2026 เงินขึ้นไป $121 แล้วร่วง 37% ในวันเดียว) ถ้าเงินกลับไปนิ่งเหมือนปี 2023–24 ทุนขั้นต่ำจะลดลงเกือบครึ่ง</p></section>")

    # ---------------- comparison table
    ver_rows = ""
    for v in V:
        for brake in (False, True):
            x = cmp[(v, brake)]
            ver_rows += (f"<tr{' class=\"sel\"' if (v == 'real' and not brake) else ''}><td>{V[v]}{' · <b>มีเบรก</b>' if brake else ''}</td><td class='n'>{usd(x['final'])}</td>"
                         f"<td class='n'>{pc(x['cagr'])}</td><td class='n'>{pc(x['eqdd']) if x['eqdd'] is not None else '–'}</td><td class='n'>{pc(x['dd'])}</td>"
                         f"<td class='n'>{x['mar']:.2f}</td><td class='n'>{x['mar1']:+.2f}</td><td class='n'>{x['mar2']:+.2f}</td>"
                         f"<td class='n {cl(x['worst'])}'>{x['worst']:+.0%} ({x['worst_at']})</td><td class='n'>{pc(x['p50'])}</td>"
                         f"<td class='n'>{x['s_cagr']:+.1%}</td><td class='n'>{x['s_mar']:.2f}</td><td class='n'>{pc(x['s_p50'])}</td></tr>")
    t_cmp = ("<table class='cmp'><thead><tr><th>ต้นทุน</th><th class='n'>เงินสุดท้าย</th><th class='n'>ต่อปี</th><th class='n'>Equity DD</th><th class='n'>Balance DD</th>"
             "<th class='n'>MAR</th><th class='n'>MAR 2011–18</th><th class='n'>MAR 2019–26</th><th class='n'>ปีแย่สุด</th><th class='n'>DD&gt;50%</th>"
             "<th class='n'>ต่อปี ถ้าแย่ลง 0.10R</th><th class='n'>MAR ถ้าแย่ลง 0.10R</th><th class='n'>DD&gt;50% ถ้าแย่ลง 0.10R</th></tr></thead><tbody>" + ver_rows + "</tbody></table>"
             "<p class='muted' style='margin:8px 0 0;font-size:13px'>เริ่ม $100,000 ก.ย. 2011 · MAR = ต่อปี ÷ Balance DD · DD&gt;50% = โอกาสที่ 10 ปีข้างหน้าจะมี DD เกิน 50% "
             "จากการสุ่มผลรายเดือนเป็นช่วงละ 6 เดือน · แถวที่เน้นคือชุดที่ขอ (ไม่มีเบรก) กับต้นทุนที่น่าเชื่อที่สุด</p>")
    t_cost = ("<table class='cmp'><thead><tr><th>แบบ</th><th>spread</th><th>swap</th></tr></thead><tbody>"
              "<tr><td>ตามที่รายงาน</td><td>max(2 bp, spread Standard + 1 bp)</td><td>bp ต่อคืนที่ราคาวันนี้ ใช้ทุกปี (กรณี A)</td></tr>"
              "<tr><td>Cent + swap C</td><td>spread ที่วัดจากบัญชี Cent 60 วัน + 1 bp: ทอง 1.58 · เงิน 5.60 · BTC 2.28 · ETH 5.03 bp</td>"
              "<td>ทอง เงิน: ตามดอกเบี้ย US 2 ปีของวันเข้าไม้ · BTC ETH: % ต่อปีเท่าวันนี้ (แบบที่รายงาน)</td></tr>"
              "<tr><td>Cent + swap D</td><td>เหมือนแถวบน</td><td>ทอง เงิน: เหมือนแถวบน · BTC ETH: จุด swap ของวันนี้คงที่ทุกปี</td></tr>"
              "<tr><td>Cent + swap B</td><td>เหมือนแถวบน</td><td>จุด swap ของวันนี้คงที่ทุกปีทุกตลาด (แบบที่ Strategy Tester คิด)</td></tr></tbody></table>"
              "<p class='muted' style='margin:8px 0 0;font-size:13px'>ทุกแบบปรับจาก R ที่รายงานด้วยส่วนต่างของต้นทุน (วิธีเดียวกับ swap_sensitivity.py ของ session วิจัย) "
              "ไม้ G27K-F ที่ปิดก่อนด้วยกฎ Fed 111 ไม้จึงได้ผลของกฎ Fed ครบ</p>")
    cmp_card = (f'<section class="card"><h2>ตัวเลขเทียบกัน</h2><div class="tbl">{t_cmp}</div>'
                f'<h3 style="margin:14px 0 6px">ต้นทุนสี่แบบ</h3><div class="tbl">{t_cost}</div></section>')

    # ---------------- DCA (operator's plan)
    drow = lambda v, x: (f"<tr{' class=\"sel\"' if v == 'real' else ''}><td>{V[v]}</td><td class='n'>${x['deposited']:,.0f}</td><td class='n'><b>{usd(x['final'])}</b></td>"
                         f"<td class='n'>{pc(x['irr'])}</td><td class='n'>{pc(x['unit_dd'], 0)}</td><td class='n'>{pc(x['below'], 0)}</td><td>{x['below_at']}</td></tr>")
    t_dca = ("<table class='cmp'><thead><tr><th>ต้นทุน</th><th class='n'>เงินที่ใส่</th><th class='n'>มูลค่าสุดท้าย</th><th class='n'>IRR ต่อปี</th>"
             "<th class='n'>DD หน่วยลงทุน</th><th class='n'>ต่ำกว่าเงินที่ใส่มากสุด</th><th>เมื่อ</th></tr></thead><tbody>" + "".join(drow(v, dc[v]) for v in V) + "</tbody></table>")
    dca_card = ('<section class="card"><h2>DCA ตามแผนบัญชี Cent: เริ่ม $100 แล้วเติม $100 ทุกต้นเดือน</h2>'
                f'<div class="tbl">{t_dca}</div><p class="muted" style="margin:8px 0 0;font-size:13px">ก.ย. 2011 – ก.ย. 2026 181 ครั้ง · ขนาดไม้ตามสัดส่วน ไม่มีเบรก · '
                'เดือนแรกๆ ทุนต่ำกว่าขั้นต่ำ ไม้เงินจะเสี่ยงเกินที่ตั้งจนกว่าบัญชีจะเกิน $130–200 · มูลค่าหลักล้านเป็นตัวเลขของโมเดล 15 ปี</p></section>')

    # ---------------- yearly and per market
    Y = {v: {y["year"]: y["ret"] for y in e[v]["yearly"]} for v in V}
    years = sorted(set.intersection(*(set(Y[v]) for v in V)))
    t_year = ("<table class='cmp'><thead><tr><th>ปี</th>" + "".join(f"<th class='n'>{V[v]}</th>" for v in V) + "</tr></thead><tbody>"
              + "".join(f"<tr><td>{y}</td>" + "".join(f"<td class='n {cl(Y[v][y])}'>{Y[v][y]:+.0%}</td>" for v in V) + "</tr>" for y in years) + "</tbody></table>")
    mid = CC.ts(pd.Series(["2019-01-01"])).iat[0]
    prow = []
    for u in UNITS:
        g = D[(D.market == base(u)) & (D.book == book(u))]
        R = g.R_real.to_numpy()
        h1, h2 = (R[g.t < mid].mean() if (g.t < mid).any() else np.nan), R[g.t >= mid].mean()
        c1 = f"<td class='n {cl(h1)}'>{h1:+.2f}</td>" if np.isfinite(h1) else "<td class='n'>–</td>"
        prow.append(f"<tr><td>{uname(u)}</td><td class='n'>{len(g):,}</td><td class='n'>{g.R_gross_eff.mean():+.3f}</td>"
                    + "".join(f"<td class='n {cl(g[f'R_{v}'].mean())}'>{g[f'R_{v}'].mean():+.3f}</td>" for v in V)
                    + f"<td class='n'>{tstat(R):.1f}</td>{c1}<td class='n {cl(h2)}'>{h2:+.2f}</td></tr>")
    t_mk = ("<table class='cmp'><thead><tr><th>ตลาด</th><th class='n'>ไม้</th><th class='n'>ก่อนต้นทุน</th>" + "".join(f"<th class='n'>{V[v]}</th>" for v in V)
            + "<th class='n'>t (Cent+D)</th><th class='n'>2011–18</th><th class='n'>2019–26</th></tr></thead><tbody>" + "".join(prow) + "</tbody></table>"
            "<p class='muted' style='margin:8px 0 0;font-size:13px'>R ต่อไม้หลังต้นทุน · สองคอลัมน์ขวาใช้ต้นทุน Cent + swap D · BTC M30/H1 มีข้อมูลตั้งแต่ 2021 · "
            "G27K-F ของทองและเงินได้ประโยชน์จาก swap กรณี D เพราะปี 2011–21 ดอกเบี้ยต่ำ swap จริงจึงถูกกว่าที่รายงาน</p>")
    lim = ("<ul class='cmp-sum'>"
           "<li><b>เงิน M30 ดีเกินจริงราว 0.04R ต่อไม้</b>: งานวิจัยเดิน SL/TP บนราคากลาง แต่ MT5 ชน SL/TP ด้วย bid/ask ทำให้ SL ใกล้ขึ้นเท่ากับ spread · "
           "วัดบนข้อมูล M1 ของโบรก ไม้เงิน M30 ที่ตรงกับ EA 105 ไม้ ปี 2023–26 ที่ spread Cent 4.6 bp: เสียจริง 0.096R ต่อไม้ (2 เท่าของ spread) "
           "แต่ต้นทุนแบบ Cent + 1 bp คิดไว้ 0.059R จึงขาดอยู่ราว 0.037R ต่อไม้ · ทองกลับกัน: เสียจริง 0.008R แต่คิดไว้ 0.034R (คิดเกินราว 0.025R) "
           "· สองตลาดหักกันเกือบหมดในระดับพอร์ต · เงิน H1 ยังไม่ได้วัด (SL กว้างกว่า ผลน่าจะเล็กกว่า) · BTC ETH ยังไม่ได้วัด</li>"
           "<li><b>กฎเลือกจากข้อมูลชุดเดียวกัน</b>: G27K #1 เลือกโดยเห็นผลปี 2021–26 · กฎ Fed มาจากการดูช่วง DD · ETH เพิ่มหลังเห็นผล · ทั้งโครงการทดสอบราว 32 ล้านสมมติฐาน</li>"
           "<li><b>ไม่มีข้อมูล swap ย้อนหลังจริง</b>: กรณี D เป็นค่ากลางที่ session วิจัยเห็นว่าน่าเชื่อที่สุด กรณี B เป็นขอบล่าง</li>"
           "<li><b>ไม่ใช่ผลเทรดจริง</b>: จำลองบนราคาย้อนหลัง ยังไม่ผ่าน forward test บนบัญชีจริง</li></ul>")
    tail = (f'<div class="cmp-grid"><section class="card"><h2>รายปี (ไม่มีเบรก)</h2><div class="tbl">{t_year}</div></section>'
            f'<section class="card"><h2>คุณภาพรายตลาด (R ต่อไม้ 2011–2026)</h2><div class="tbl">{t_mk}</div></section></div>'
            f'<section class="card"><h2>ข้อจำกัดที่ต้องรู้</h2>{lim}</section>')
    css6 = ("<style>:root{--c5:#e87ba4;--c6:#008300}@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--c5:#d55181;--c6:#008300}}"
            ":root[data-theme=\"dark\"]{--c5:#d55181;--c6:#008300}</style>")
    cmp_html = css5 + css6 + top + mincap + cmp_card + dca_card + tail
    cmp_js = script5.replace("__DATA__", data)

    # ---------------- META and template
    rules = ["G27K-F: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป · ไม่เข้าถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า · "
             "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง · ตลาดละ 1 ไม้",
             "กฎข่าว Fed: ถ้าผลตอบแทนพันธบัตรสหรัฐ 2 ปีวันใดเปลี่ยนเกิน 2 เท่าของ SD ย้อนหลัง 250 วัน ปิดไม้ G27K-F ที่ราคาเปิดชั่วโมงถัดไปหลัง 22:00 UTC ของวันทำการถัดไป "
             "และไม่เข้าไม้ใหม่ 5 วัน",
             "ไม้ M30: แท่ง M30 ปิดไม่เกิน 1 ATR จาก High/Low 55 แท่งในทิศที่เทรด + ATR14/ATR100 ≥ 1.5 + D1 ไปทางเดียวกัน · ซื้อหรือขาย · SL 2 × ATR20 · TP 2R · "
             "ครบ 30 แท่งยังไม่ชน ปิดที่ราคาเปิดแท่งถัดไป · 0.5% ต่อไม้",
             "ไม้ H1: แท่ง H1 ราคาอยู่ในช่วงบน 10% ของ 250 แท่งในทิศที่เทรด + ATR14/ATR100 ≥ 1.25 + D1 ไปทางเดียวกัน · SL 2 × ATR20 · TP 2R หรือครบ 30 แท่ง · 0.5% ต่อไม้",
             "ตลาด: XAUUSD XAGUSD BTCUSD ETHUSD (บัญชี Cent ไม่มี JP225 และชุดนี้ตัด USDJPY ออก) · ไม่มีเบรก"]
    rn = {v: "G27K-F 1% ต่อไม้ · ไม้ M30 และ H1 0.5% ต่อไม้ · ไม่มีเบรก · " + CC.VERSION_NOTE[v] for v in V}
    info = {"A": dict(label="G27K-F + M30 + H1 · Cent 4 ตลาด", tab="Cent ทอง เงิน BTC ETH · ไม่มีเบรก", rules=rules,
                      notes=["<b>บัญชี Cent: ทอง เงิน BTC ETH</b> · ETHUSDc lot ต่ำสุด 0.10 · BTC และ ETH เลเวอเรจ 1:400",
                             "<b>ไม่มีเบรก</b>: G27K-F เสี่ยง 1% และไม้ M30/H1 เสี่ยง 0.5% ทุกไม้ตลอดเวลา"],
                      combo="C8/D3/E1/F1/G2/H2/I1/J1 + Fed · M30 · H1", risk=0.01, adds=False, tf="H4 + M30 + H1", risk_note=rn["real"], risk_notes=rn)}
    wf = {"A": dict(patterns=[], pat_note="", pat_empty="กฎตายตัว 3 ชุด (G27K-F, ไม้ M30, ไม้ H1) ไม่มีการเลือกหรือปลดรูปแบบระหว่างทาง", log=[], log_note="",
                    log_empty="ขนาดไม้คำนวณที่เวลาเข้าไม้จาก balance ขณะนั้น แบบสัดส่วน (ไม่ปัด lot) · ผลของ lot ขั้นต่ำและการปัด lot บนบัญชี Cent อยู่ในการ์ดทุนขั้นต่ำด้านบน")}
    S_, last = pd.Timestamp(START), pd.Timestamp(END) - pd.Timedelta(days=1)
    nom = {m: src[m] for m in ("BTCUSD", "ETHUSD")}
    meta = dict(systems_info=info, wf=wf, versions=CC.VERSIONS,
                cost_short=CC.SHORT,
                cost_notes=CC.VERSION_NOTE,
                period_th=f"15 ปี {S_.day} {TH_M[S_.month - 1]} {S_.year} – {last.day} {TH_M[last.month - 1]} {last.year}",
                data_note=("ไม้ทุกไม้จากไฟล์ส่งต่อของ session วิจัย (ทองเติมวันที่ขาดแล้ว) · equity ระหว่างถือคิดจากแท่ง H1: ทอง/เงิน Candle Lab + MT5, BTC/ETH จาก MT5 Exness "
                           f"ซึ่งมีตั้งแต่ {nom['BTCUSD']} / {nom['ETHUSD']} ไม้ crypto ก่อนหน้านั้นแสดง equity = balance · MFE/MAE จากแท่ง H1"),
                notes_common=["<b>บัญชีเดียวต่อเนื่อง เริ่ม $100,000 เมื่อ ก.ย. 2011</b> แบบรายงาน G27K ทุกฉบับ จำลองบนราคาจริง ไม่ใช่ผลเทรดจริง",
                              "<b>ต้นทุนเลือกได้ 4 แบบ</b> ที่ปุ่มด้านบน: ตามที่รายงาน · spread Cent จริง + swap กรณี C, D หรือ B (รายละเอียดในการ์ดตัวเลขเทียบกัน)",
                              "<b>กฎ G27K #1 ถูกเลือกโดยเห็นผลปี 2021–2026</b> ETH ถูกเพิ่มหลังเห็นผล และกฎข่าว Fed มาจากการดูช่วง DD ในข้อมูลชุดเดียวกัน ตัวเลขจึงดีเกินจริงบางส่วน",
                              "<b>ETH มีข้อมูลตั้งแต่ ส.ค. 2017 · BTC M30/H1 ตั้งแต่ 2021</b> ก่อนหน้านั้นเทรดตลาดที่เหลือ",
                              "<b>แท็บตลาดเดียว</b> เป็นบัญชีแยกเริ่ม $100,000 ที่ความเสี่ยงเดียวกับในพอร์ต (G27K-F 1%, ไม้ M30/H1 0.5%)"],
                footer=("สร้างจาก research/g27k_dev/handoff/mt5/report_cent4.py · ตัวเลขคำนวณด้วย report768.metrics ชุดเดียวกับรายงาน G27K · "
                        "ทุนขั้นต่ำจาก cent4_capital.py · session MT5 5 ต.ค. 2026"))
    out["META"] = meta
    data_all = clean(out)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    title = "G27K-F + M30 + H1 Cent 4 ตลาด"
    ubtn = "\n        ".join(f'<button role="tab" data-u="{u}">{uname(u)}</button>' for u in UNITS)
    uni_th = {"PA": "พอร์ต Cent 4 ตลาด · G27K-F + M30 + H1", **{u: f"{uname(u)} ({base(u)}) ตลาดเดียว" for u in UNITS}}
    mkt_th = ('const MKT_TH = {XAUUSD:"ทอง",XAGUSD:"เงิน",BTCUSD:"บิตคอยน์",ETHUSD:"อีเธอเรียม",'
              + ",".join(f'{u}:"{uname(u)}"' for u in UNITS if "_" in u) + "};")
    rep = [
        ("<title>รายงาน Walk-forward 10 ปี</title>", f"<title>{title}</title>"),
        ("Strategy Tester · Walk-forward report", "Strategy Tester · G27K-F + M30 + H1"),
        ("รายงานผลทดสอบ Walk-forward · 10 ปี", "G27K-F + M30 + H1 · Cent ทอง เงิน BTC ETH · ไม่มีเบรก · 15 ปี"),
        ("การตัดสินใจทุกครั้งใช้ข้อมูลก่อนเวลานั้นเท่านั้น", "ขนาดไม้คำนวณ ณ เวลาเข้าไม้"),
        ('<h2>บันทึกการตัดสินใจ</h2>', '<h2>หมายเหตุขนาดไม้</h2>'),
        ('<button role="tab" data-u="MET3">ทอง + เงิน + BTC</button>\n        <button role="tab" data-u="XAUUSD">ทอง</button>\n        '
         '<button role="tab" data-u="XAGUSD">เงิน</button>\n        <button role="tab" data-u="BTCUSD">BTC</button>',
         '<button role="tab" data-u="PA">พอร์ต Cent 4 ตลาด</button>\n        ' + ubtn),
        ('<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>',
         '<div class="seg wrap" role="tablist" id="sysTabs" aria-label="ระบบ"></div>\n      <div class="seg wrap" role="tablist" id="verTabs" aria-label="ต้นทุน"></div>'),
        ('const keyOf = (s, u) => s + "_" + u;', 'let VER = "real";\nconst keyOf = (s, u) => s + "~" + VER + "_" + u;'),
        ('const UNI_TH = {MET3: "3 ตลาด: ทอง เงิน บิตคอยน์", XAUUSD: "ทอง (XAUUSD) ตลาดเดียว", XAGUSD: "เงิน (XAGUSD) ตลาดเดียว", BTCUSD: "บิตคอยน์ (BTCUSD) ตลาดเดียว"};',
         "const UNI_TH = " + json.dumps(uni_th, ensure_ascii=False) + ";"),
        ('let SYS = Object.keys(SINFO)[0], UNI = "MET3"', 'let SYS = Object.keys(SINFO)[0], UNI = "PA"'),
        ('try { const s = localStorage.getItem("wfsys");',
         'document.getElementById("verTabs").innerHTML = Object.entries(D.META.versions).map(([k, t]) => `<button role="tab" data-v="${k}">${t}</button>`).join("");\n'
         'try { const vv = localStorage.getItem("c4ver"); if (vv && D.META.versions[vv]) VER = vv; } catch (e) {}\n'
         'try { const s = localStorage.getItem("wfsys");'),
        ('  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));',
         '  document.querySelectorAll("#uniTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.u === UNI));\n'
         '  document.querySelectorAll("#verTabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.v === VER));'),
        ('pct(r.risk, 2), SI.risk_note)', 'pct(r.risk, 2), (SI.risk_notes ? SI.risk_notes[VER] : SI.risk_note))'),
        ('kv("ต้นทุน", "Costs", "spread + 1 bp", "ขั้นต่ำ 2 bp ต่อรอบ + swap จริงของโบรกเกอร์ (รวมวัน triple)")',
         'kv("ต้นทุน", "Costs", GM.cost_short[VER], GM.cost_notes[VER])'),
        ('SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });',
         'SYS = b.dataset.k; try { localStorage.setItem("wfsys", SYS); } catch (x) {} render(); });\n'
         'document.getElementById("verTabs").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; VER = b.dataset.v; '
         'try { localStorage.setItem("c4ver", VER); } catch (x) {} render(); });'),
        ('<li><b>สิ่งที่ยังไม่ได้จำลอง:</b> margin และ stop-out · lot ขั้นต่ำ 0.01 · slippage ที่เกิน spread + 1 bp · ลำดับราคาภายในแท่ง H1 เดียวกัน (ถ้าแท่งเดียวชนทั้งราคาเข้าและ SL จะถือว่าโดน SL)</li>',
         '<li><b>สิ่งที่ส่วนนี้ยังไม่ได้จำลอง:</b> lot ขั้นต่ำและการปัด lot ของบัญชี Cent (ดูการ์ดทุนขั้นต่ำด้านบน) · slippage ที่เกิน 1 bp · '
         'SL/TP ที่ MT5 ชนด้วย bid/ask (เงิน M30 ดีเกินจริงราว 0.04R ต่อไม้ ทองคิดเกิน ดูข้อจำกัดด้านบน) · margin ใช้ไม่ถึง 1.2% ของทุนจึงไม่มีผล</li>'),
        ('<section class="kpis" id="kpis"></section>', '__CMP__<h2 style="margin:6px 0 10px">รายละเอียด (เลือกตลาดและต้นทุนที่ปุ่มด้านบน)</h2>\n  <section class="kpis" id="kpis"></section>'),
    ]
    for x, y in rep:
        assert x in tpl, x[:70]
        tpl = tpl.replace(x, y, 1)
    import re
    tpl, nmk = re.subn(r"const MKT_TH = \{[^\n]*\};", lambda _: mkt_th, tpl, count=1)
    assert nmk == 1
    tpl = tpl.replace("__CMP__", cmp_html) + "\n" + cmp_js
    return tpl.replace("/*DATA*/", json.dumps(data_all, ensure_ascii=False))


def month_end_balance(acc, months):
    """Balance at each month end from the account rows (closed trades only)."""
    tx = np.array([r["t_exit"] for r in acc]); bal = np.array([r["bal_after"] for r in acc])
    cut = ((months + pd.Timedelta(days=1)) - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")      # unit-safe seconds (pandas may store us)
    k = np.searchsorted(tx, np.asarray(cut, np.int64), "left") - 1
    return np.where(k >= 0, bal[np.maximum(k, 0)], DEPOSIT)


if __name__ == "__main__":
    main()
