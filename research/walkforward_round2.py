#!/usr/bin/env python3
"""Round 2 of the forward-only controller (ledger id walkforward_controller_round2).

Changes from round 1, each from a round-1 observation: confluence
aggregation instead of a per-market cap, news halves size instead of
skipping, retirement only on statistical evidence, a looser drawdown brake.
Run on the main window (2021-10..2026-09) and on an independent forward
window (2016-10..2021-09) that round 1 never touched.

Usage: python3 walkforward_round2.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import json
import math
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

BASE = 0.005
WINDOWS = {"main": ("2021-10-01", "2026-10-01"), "independent": ("2016-10-01", "2021-10-01")}


def entries_of(p, B, end):
    E, feats, cats = B[p.c["tf"]]
    m = W.pmask(feats, cats, p.c["conds"])
    if p.c["scope"] == "XAUUSD":
        m = m & (E["mkt"] == "XAUUSD")
    ex = p.c["exit"]
    m = m & np.isfinite(E[f"R_{ex}"]) & (E["t"] + W.SEC[p.c["tf"]] >= p.t_on) & (E["t"] < end)
    out = []
    for i in np.flatnonzero(m):
        X = P.FRAMES[(E["mkt"][i], p.c["tf"])]
        e = int(E["s"][i]) + 1
        if e < len(X["t"]):
            out.append((int(X["t"][e]), E["mkt"][i], int(E["d"][i]), p.c["tf"], int(i)))
    return out


def run2(B, refits, news, end):
    patterns, active, log = {}, [], []
    bal, peak, brake = W.DEPOSIT, W.DEPOSIT, 1.0
    heap, open_list, rows = [], [], []
    agg = {}
    queue = []
    for D in sorted(refits):
        heapq.heappush(queue, (D, 0, ("refit", D)))
    pid_n = 0
    stats = dict(signals=0, k_hist={}, news_half=0, cap_risk=0, busy=0)

    def close_until(t):
        nonlocal bal, peak, brake
        while heap and heap[0][0] <= t:
            tx, _, tr = heapq.heappop(heap)
            open_list.remove(tr)
            bal += tr["pnl"]
            tr["bal_after"] = bal
            rows.append(tr)
            peak = max(peak, bal)
            dd = 1 - bal / peak
            nb = 0.25 if dd >= 0.25 else 0.5 if dd >= 0.15 else (1.0 if dd < 0.075 else brake)
            if nb != brake:
                log.append(dict(t=tx, kind="brake", text=f"บัญชี DD {dd:.1%} → ความเสี่ยง x{nb}"))
                brake = nb
            for pid in tr["firing"]:
                p = patterns[pid]
                p.live.append(tr["R"])
                if p.t_off is not None:
                    continue
                n = len(p.live)
                cum = sum(p.live)
                bad = False
                if cum <= -15:
                    bad, why = True, f"ผลจริงสะสม {cum:+.1f}R"
                elif n >= 20:
                    se = np.std(p.live, ddof=1) / math.sqrt(n)
                    if np.mean(p.live) < p.c["val_R"] - 2.5 * se:
                        bad, why = True, (f"{n} ไม้ เฉลี่ย {np.mean(p.live):+.2f}R ต่ำกว่าที่คาด "
                                          f"{p.c['val_R']:+.2f}R เกิน 2.5 SE")
                if bad:
                    p.t_off, p.why_off = tx, why
                    active.remove(pid)
                    log.append(dict(t=tx, kind="retire", pid=pid, text=f"ปลด {pid}: {why}"))

    while queue:
        t, pri, item = heapq.heappop(queue)
        close_until(t)
        if item[0] == "refit":
            D = item[1]
            for pid in list(active):
                p = patterns[pid]
                E, feats, cats = B[p.c["tf"]]
                m = W.pmask(feats, cats, p.c["conds"])
                if p.c["scope"] == "XAUUSD":
                    m = m & (E["mkt"] == "XAUUSD")
                ex = p.c["exit"]
                val = m & np.isfinite(E[f"R_{ex}"]) & (E["t"] >= D - W.TWO_Y) & (E[f"tx_{ex}"] < D)
                _, r, mu, _ = W.nov(E, val, ex)
                if len(r) >= 5 and mu < 0:
                    p.t_off, p.why_off = D, f"2 ปีล่าสุดเฉลี่ย {mu:+.2f}R"
                    active.remove(pid)
                    log.append(dict(t=D, kind="retire", pid=pid, text=f"ปลด {pid}: {p.why_off}"))
            cands = refits[D]
            el = sorted([c for c in cands if W.eligible(c)], key=lambda c: -W.score(c))
            n_new = 0
            for c in el:
                if n_new >= W.MAX_NEW:
                    break
                if any(W.jaccard(c["recent"], patterns[a].c["recent"]) >= 0.6
                       for a in active if patterns[a].c["tf"] == c["tf"]):
                    continue
                if any(p.c["names"] == c["names"] and p.c["exit"] == c["exit"] and p.c["tf"] == c["tf"]
                       and p.c["scope"] == c["scope"] for p in patterns.values()):
                    continue
                if len(active) >= 6:
                    weakest = min(active, key=lambda a: W.score(patterns[a].c))
                    if W.score(c) < W.score(patterns[weakest].c) + 1.0:
                        continue
                    pw = patterns[weakest]
                    pw.t_off, pw.why_off = D, "แทนที่ด้วยรูปแบบที่คะแนนสูงกว่า"
                    active.remove(weakest)
                    log.append(dict(t=D, kind="retire", pid=weakest, text=f"ปลด {weakest}: {pw.why_off}"))
                pid_n += 1
                pid = f"P{pid_n:02d}"
                p = W.Pattern(pid, c, D)
                patterns[pid] = p
                active.append(pid)
                n_new += 1
                log.append(dict(t=D, kind="adopt", pid=pid,
                                text=f"รับ {pid} ({p.desc()}) ค้น {c['disc_n']} ไม้ {c['disc_R']:+.2f}R t{c['disc_t']:.1f} · "
                                     f"ตรวจ {c['val_n']} ไม้ {c['val_R']:+.2f}R t{c['val_t']:.1f}"))
                for te, mkt, d, tf, i in entries_of(p, B, end):
                    key = (te, mkt, d, tf)
                    if key not in agg:
                        agg[key] = []
                        heapq.heappush(queue, (te, 1, ("entry", key)))
                    agg[key].append((pid, i))
            log.append(dict(t=D, kind="refit", text=f"ค้นใหม่: ผ่านเกณฑ์ {len(el)} จาก {len(cands)} ตัวเลือก · ใช้งาน {len(active)}"))
            continue
        key = item[1]
        te, mkt, d, tf = key
        firing = [(pid, i) for pid, i in agg[key]
                  if patterns[pid].t_off is None or te < patterns[pid].t_off]
        if not firing:
            continue
        stats["signals"] += 1
        if any(o["mkt"] == mkt and o["d"] == d for o in open_list):
            stats["busy"] += 1
            continue
        k = len(firing)
        stats["k_hist"][k] = stats["k_hist"].get(k, 0) + 1
        lead_pid, i = max(firing, key=lambda x: W.score(patterns[x[0]].c))
        lead = patterns[lead_pid]
        E, feats, cats = B[tf]
        ex = lead.c["exit"]
        risk = BASE * min(1 + 0.25 * (k - 1), 2.0) * brake
        if len(lead.live) >= 8 and np.mean(lead.live[-8:]) < -0.3:
            risk *= 0.5
        if feats["atr_pct"][i] > 0.95:
            risk *= 0.5
        sig_close = int(E["t"][i]) + W.SEC[tf]
        j = np.searchsorted(news, sig_close - 3600)
        if j < len(news) and news[j] <= sig_close + 7200:
            risk *= 0.5
            stats["news_half"] += 1
        if sum(o["risk_frac"] for o in open_list) + risk > 0.06 + 1e-12:
            stats["cap_risk"] += 1
            continue
        R = float(E[f"R_{ex}"][i])
        tr = dict(pid=lead_pid, firing=[f for f, _ in firing], k=k, mkt=mkt, tf=tf, ex=ex, i=i, t=te,
                  t_exit=int(E[f"tx_{ex}"][i]), R=R, d=d, risk_frac=risk, bal_before=bal,
                  unit_usd=risk * bal, pnl=risk * bal * R)
        open_list.append(tr)
        heapq.heappush(heap, (tr["t_exit"], id(tr), tr))
    close_until(2 ** 62)
    rows.sort(key=lambda r: (r["t_exit"], r["t"]))
    b = W.DEPOSIT
    for r in rows:
        b += r["pnl"]
        r["bal_after"] = b
    return rows, patterns, log, stats


def pack(rows, patterns, log, extra, RP, G, B):
    M = W.slim(W.metrics_for(W.to_report_rows(rows, B), RP, G))
    return dict(metrics=M, skipped=extra,
                patterns=[dict(id=p.id, desc=p.desc(), adopted=str(pd.Timestamp(p.t_on, unit="s").date()),
                               retired=str(pd.Timestamp(p.t_off, unit="s").date()) if p.t_off else None,
                               why=p.why_off, live_n=len(p.live), live_R=float(sum(p.live)),
                               disc=dict(n=p.c["disc_n"], R=p.c["disc_R"], t=p.c["disc_t"]),
                               val=dict(n=p.c["val_n"], R=p.c["val_R"], t=p.c["val_t"]))
                          for p in patterns.values()],
                log=[dict(l, t=str(pd.Timestamp(l["t"], unit="s").date())) for l in log],
                trades=[dict(pid=r["pid"], mkt=r["mkt"], t=int(r["t"]), t_exit=int(r["t_exit"]), d=r["d"],
                             R=r["R"], risk=r["risk_frac"], pnl=r["pnl"], k=r.get("k", 1)) for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in W.TFS}
    cache = HERE / ".cache_wf" / "refits.pkl"
    allref = pickle.loads(cache.read_bytes()) if cache.exists() else {}
    news = W.news_times(a.root)
    out = {}
    for wname, (s, e) in WINDOWS.items():
        start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
        dates = [W.ts(d) for d in pd.date_range(start, end - pd.Timedelta(days=1), freq="QS")]
        for D in dates:
            if D not in allref:
                allref[D] = W.refit_candidates(D, B)
                cache.write_bytes(pickle.dumps(allref))
                print(f"  refit {pd.Timestamp(D, unit='s').date()} done  {time.time() - t0:.0f}s", flush=True)
        refits = {D: allref[D] for D in dates}
        G.START = int(start.timestamp())
        W.START, W.END = start, end
        res = {}
        rows, pats, log, st = run2(B, refits, news, int(end.timestamp()))
        res["round2"] = pack(rows, pats, log, st, RP, G, B)
        W.BASE_RISK = 0.0075
        rows1, pats1, log1, sk1 = W.run(B, refits, news, decide=True)
        res["round1_rules"] = pack(rows1, pats1, log1, sk1, RP, G, B)
        rowsn, patsn, logn, skn = W.run(B, refits, news, decide=False, fixed=list(pats.values()))
        res["no_decisions"] = pack(rowsn, patsn, logn, skn, RP, G, B)
        for k in res:
            m = res[k]["metrics"]
            print(f"  [{wname}] {k:13s} trades {m['trades']:5d} net {m['net']:+12,.0f} CAGR {m['cagr']:+6.1%} "
                  f"eqDD {m['equity_dd']:5.1%} MAR {m['mar']:5.2f} PF {m['pf']:.2f}", flush=True)
        res["config"] = dict(start=s, end=str((end - pd.Timedelta(days=1)).date()), base_risk=BASE, refits=len(dates),
                             candidates=[dict(date=str(pd.Timestamp(D, unit='s').date()), n=len(refits[D]),
                                              eligible=int(sum(W.eligible(c) for c in refits[D]))) for D in dates])
        out[wname] = res
    G.START = W.ts("2021-10-01")
    out["main"]["g27k_1"] = json.load(open(HERE / "walkforward_round1.json"))["g27k_1"]
    (HERE / "walkforward_round2.json").write_text(json.dumps(out, ensure_ascii=False, default=str))
    print(f"  saved walkforward_round2.json  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
