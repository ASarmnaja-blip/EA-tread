#!/usr/bin/env python3
"""Round 1 of a forward-only, self-managed backtest (ledger id
walkforward_controller_round1; rules registered before the first run).

Starting 2021-10-01 with no knowledge of later data, the controller
re-searches for patterns at every quarter start using only earlier data,
adopts and retires them by fixed rules, and sizes every trade through live
monitors. Two comparisons over the same window: G27K #1 (chosen with
hindsight on this window, recomputed with the G27K report's own code) and
the same adopted patterns traded with no decisions at all.

Usage: python3 walkforward_controller.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import json
import math
import pickle
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import h4d1_pattern_search as P

START = pd.Timestamp("2021-10-01", tz="UTC")
END = pd.Timestamp("2026-10-01", tz="UTC")
TWO_Y = 730 * 86400
BASE_RISK = 0.0075
MAX_ACTIVE, MAX_NEW = 5, 2
TFS = ("H4", "D1")
SEC = {"H4": 14400, "D1": 86400}
DEPOSIT = 100_000.0


def ts(x):
    return int(pd.Timestamp(x).timestamp())


# ------------------------------------------------------------------ data
def hybrid_h1(m, G):
    mt = G.load_h1(m)
    k = mt["t"] >= ts("2021-01-01")
    mt = {x: (v[k] if isinstance(v, np.ndarray) else v) for x, v in mt.items()}
    if m == "BTCUSD":
        return mt
    z = np.load(G.ROOT / "data" / "bundle" / f"bars_{m}_H1.npz")
    keep = z["t"].astype(np.int64) < mt["t"][0]
    out = {x: np.r_[z[x][keep].astype(float), mt[x].astype(float)] for x in ("o", "h", "l", "c", "v")}
    out["t"] = np.r_[z["t"][keep].astype(np.int64), mt["t"]]
    out["step"] = 3600
    return out


# ------------------------------------------------------------------ patterns
def parse(name):
    for op in (">=", "<="):
        if op in name:
            f, q = name.split(op)
            return (f, op, float(q))
    return (name, "cat", None)


def pmask(feats, cats, conds):
    m = None
    for f, op, q in conds:
        if op == ">=":
            v = feats[f] >= q
        elif op == "<=":
            v = feats[f] <= q
        else:
            v = cats[f]
        m = v if m is None else (m & v)
    return m


def nov(E, mask, ex):
    k = P.no_overlap(E, mask, ex)
    r = E[f"R_{ex}"][k]
    if len(r) < 3 or r.std(ddof=1) == 0:
        return k, r, (np.nan if len(r) == 0 else float(r.mean())), np.nan
    return k, r, float(r.mean()), float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r))))


def refit_candidates(D, B):
    """Every candidate the search offers at refit date D, with its discovery
    and validation statistics. Uses only trades entered AND exited before D."""
    disc_end = D - TWO_Y
    P._M["SPLIT"] = disc_end
    out = []
    for tf in TFS:
        E, feats, cats = B[tf]
        Rok = {ex: np.isfinite(E[f"R_{ex}"]) for ex in P.EXITS}
        disc_t = E["t"] < disc_end
        names, Bm = P.conditions(feats, cats, disc_t)
        cands, _ = P.search(tf, E, names, Bm, disc_t)
        seen = set()
        for c in sorted(cands, key=lambda c: -c["t_disc"]):
            key = (c["exit"], c["scope"], tuple(c["conds"]))
            if key in seen:
                continue
            seen.add(key)
            conds = [parse(names[q]) for q in c["conds"]]
            mask = pmask(feats, cats, conds)
            if c["scope"] == "XAUUSD":
                mask = mask & (E["mkt"] == "XAUUSD")
            ex = c["exit"]
            val = mask & Rok[ex] & (E["t"] >= disc_end) & (E[f"tx_{ex}"] < D)
            k, r, mu, t = nov(E, val, ex)
            gold = float(r[E["mkt"][k] == "XAUUSD"].sum()) if len(r) else 0.0
            recent = mask & (E["t"] >= disc_end) & (E["t"] < D)
            out.append(dict(tf=tf, exit=ex, scope=c["scope"], conds=conds,
                            names=[names[q] for q in c["conds"]],
                            disc_n=c["n_disc"], disc_R=c["R_disc"], disc_t=c["t_disc"],
                            val_n=len(r), val_R=mu, val_t=t, val_gold=gold,
                            recent=np.flatnonzero(recent)))
            if len(seen) >= 150:
                break
    return out


def eligible(c):
    return (c["disc_R"] >= 0.10 and c["disc_t"] >= 3 and c["val_n"] >= 20
            and np.isfinite(c["val_R"]) and c["val_R"] >= 0.10
            and np.isfinite(c["val_t"]) and c["val_t"] >= 1.5
            and (c["scope"] == "XAUUSD" or c["val_gold"] >= 0))


def score(c):
    return (c["disc_t"] + c["val_t"]) / math.sqrt(2)


def jaccard(a, b):
    if len(a) == 0 or len(b) == 0:
        return 0.0
    return len(np.intersect1d(a, b)) / len(np.union1d(a, b))


# ------------------------------------------------------------------ trading
class Pattern:
    def __init__(self, pid, c, t_on):
        self.id, self.c, self.t_on, self.t_off = pid, c, t_on, None
        self.live, self.why_off = [], None

    def desc(self):
        c = self.c
        return f"{c['tf']} {c['exit']} {c['scope']}: " + " & ".join(c["names"])


def news_times(root):
    cal = pd.read_csv(pathlib.Path(root) / "data" / "calendar.csv", encoding="cp1252")
    hi = cal[(cal.importance == "HIGH") & (cal.currency == "USD")]
    t = (pd.to_datetime(hi.time, format="%Y.%m.%d %H:%M", utc=True)
         - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")
    return np.sort(t.to_numpy(np.int64))


def run(B, refits, news, decide=True, fixed=None, off=()):
    """Event-driven account. decide=False trades every pattern adopted on the
    controller's schedule at flat risk, with no retirements, filters, caps or
    brakes - the 'no decisions' comparison."""
    patterns, active, log = {}, [], []
    schedule = sorted(refits)
    bal, peak = DEPOSIT, DEPOSIT
    open_heap, open_list, rows = [], [], []
    brake = 1.0
    skipped = dict(news=0, cap_market=0, cap_risk=0)

    def close_until(t):
        nonlocal bal, peak, brake
        while open_heap and open_heap[0][0] <= t:
            tx, _, tr = heapq.heappop(open_heap)
            open_list.remove(tr)
            bal += tr["pnl"]
            tr["bal_after"] = bal
            rows.append(tr)
            p = patterns[tr["pid"]]
            p.live.append(tr["R"])
            peak = max(peak, bal)
            if decide:
                dd = 1 - bal / peak
                nb = 0.25 if dd >= 0.20 else 0.5 if dd >= 0.10 else (1.0 if dd < 0.05 else brake)
                if "brake" in off:
                    nb = 1.0
                if nb != brake:
                    log.append(dict(t=tx, kind="brake", text=f"บัญชี DD {dd:.1%} → ความเสี่ยง x{nb}"))
                    brake = nb
                if p.t_off is None and "live_retire" not in off:
                    cum = sum(p.live)
                    if cum <= -8 or (len(p.live) >= 15 and np.mean(p.live) < -0.15):
                        p.t_off, p.why_off = tx, (f"ผลจริงสะสม {cum:+.1f}R" if cum <= -8
                                                  else f"{len(p.live)} ไม้ เฉลี่ย {np.mean(p.live):+.2f}R")
                        active.remove(p.id)
                        log.append(dict(t=tx, kind="retire", pid=p.id, text=f"ปลด {p.id}: {p.why_off}"))

    # all refit decisions and all entries are processed in time order
    pid_n = 0
    cand_by_D = refits

    def candidate_entries(p):
        E, feats, cats = B[p.c["tf"]]
        m = pmask(feats, cats, p.c["conds"])
        if p.c["scope"] == "XAUUSD":
            m = m & (E["mkt"] == "XAUUSD")
        ex = p.c["exit"]
        m = m & np.isfinite(E[f"R_{ex}"]) & (E["t"] + SEC[p.c["tf"]] >= p.t_on) & (E["t"] < ts(END))
        out = []
        for i in np.flatnonzero(m):
            X = P.FRAMES[(E["mkt"][i], p.c["tf"])]
            e = int(E["s"][i]) + 1
            if e >= len(X["t"]):
                continue
            out.append((int(X["t"][e]), p.id, int(i)))
        return out

    queue = []
    for D in schedule:
        heapq.heappush(queue, (D, 0, ("refit", D)))
    busy = {}
    while queue:
        t, pri, item = heapq.heappop(queue)
        close_until(t)
        if item[0] == "refit":
            D = item[1]
            cands = cand_by_D[D]
            if fixed is not None:
                for fp in fixed:
                    if fp.t_on == D:
                        p = Pattern(fp.id, fp.c, D)
                        patterns[p.id] = p
                        active.append(p.id)
                        for ent in candidate_entries(p):
                            heapq.heappush(queue, (ent[0], 1, ("entry", ent[1], ent[2])))
                continue
            if decide and "refit_retire" not in off:
                for pid in list(active):
                    p = patterns[pid]
                    E, feats, cats = B[p.c["tf"]]
                    m = pmask(feats, cats, p.c["conds"])
                    if p.c["scope"] == "XAUUSD":
                        m = m & (E["mkt"] == "XAUUSD")
                    ex = p.c["exit"]
                    val = m & np.isfinite(E[f"R_{ex}"]) & (E["t"] >= D - TWO_Y) & (E[f"tx_{ex}"] < D)
                    _, r, mu, _ = nov(E, val, ex)
                    if len(r) >= 5 and mu < 0:
                        p.t_off, p.why_off = D, f"2 ปีล่าสุดเฉลี่ย {mu:+.2f}R"
                        active.remove(pid)
                        log.append(dict(t=D, kind="retire", pid=pid, text=f"ปลด {pid}: {p.why_off}"))
            el = sorted([c for c in cands if eligible(c)], key=lambda c: -score(c))
            n_new = 0
            for c in el:
                if n_new >= MAX_NEW:
                    break
                if any(jaccard(c["recent"], patterns[a].c["recent"]) >= 0.5
                       for a in active if patterns[a].c["tf"] == c["tf"]):
                    continue
                if any(p.c["names"] == c["names"] and p.c["exit"] == c["exit"] and p.c["tf"] == c["tf"]
                       and p.c["scope"] == c["scope"] for p in patterns.values()):
                    continue
                if len(active) >= MAX_ACTIVE:
                    weakest = min(active, key=lambda a: score(patterns[a].c))
                    if score(c) < score(patterns[weakest].c) + 1.0:
                        continue
                    pw = patterns[weakest]
                    pw.t_off, pw.why_off = D, f"แทนที่ด้วยรูปแบบที่คะแนนสูงกว่า"
                    active.remove(weakest)
                    log.append(dict(t=D, kind="retire", pid=weakest, text=f"ปลด {weakest}: {pw.why_off}"))
                pid_n += 1
                pid = f"P{pid_n:02d}"
                p = Pattern(pid, c, D)
                patterns[pid] = p
                active.append(pid)
                n_new += 1
                log.append(dict(t=D, kind="adopt", pid=pid,
                                text=f"รับ {pid} ({p.desc()}) ค้น {c['disc_n']} ไม้ {c['disc_R']:+.2f}R t{c['disc_t']:.1f} · "
                                     f"ตรวจ {c['val_n']} ไม้ {c['val_R']:+.2f}R t{c['val_t']:.1f}"))
                for ent in candidate_entries(p):
                    heapq.heappush(queue, (ent[0], 1, ("entry", ent[1], ent[2])))
            log.append(dict(t=D, kind="refit", text=f"ค้นใหม่: ผ่านเกณฑ์ {len(el)} จาก {len(cands)} ตัวเลือก · ใช้งาน {len(active)}"))
            continue
        _, pid, i = item
        p = patterns[pid]
        if decide and p.t_off is not None and t >= p.t_off:
            continue
        E, feats, cats = B[p.c["tf"]]
        mkt = E["mkt"][i]
        if busy.get((pid, mkt), -1) > t:
            continue
        ex = p.c["exit"]
        risk = BASE_RISK
        if decide:
            sig_close = int(E["t"][i]) + SEC[p.c["tf"]]
            j = np.searchsorted(news, sig_close - 3600)
            if "news" not in off and j < len(news) and news[j] <= sig_close + 7200:
                skipped["news"] += 1
                continue
            if "cap_market" not in off and sum(1 for o in open_list if o["mkt"] == mkt) >= 2:
                skipped["cap_market"] += 1
                continue
            f_p = 0.5 if ("probation" not in off and len(p.live) >= 8 and np.mean(p.live[-8:]) < -0.3) else 1.0
            f_v = 0.5 if ("vol" not in off and feats["atr_pct"][i] > 0.95) else 1.0
            risk = BASE_RISK * f_p * f_v * brake
            if "cap_risk" not in off and sum(o["risk_frac"] for o in open_list) + risk > 0.04 + 1e-12:
                skipped["cap_risk"] += 1
                continue
        tx = int(E[f"tx_{ex}"][i])
        busy[(pid, mkt)] = tx
        tr = dict(pid=pid, mkt=mkt, tf=p.c["tf"], ex=ex, i=i, t=t, t_exit=tx, R=float(E[f"R_{ex}"][i]),
                  d=int(E["d"][i]), risk_frac=risk, bal_before=bal, unit_usd=risk * bal, pnl=risk * bal * float(E[f"R_{ex}"][i]))
        open_list.append(tr)
        heapq.heappush(open_heap, (tx, id(tr), tr))
    close_until(2 ** 62)
    rows.sort(key=lambda r: (r["t_exit"], r["t"]))
    b = DEPOSIT
    for r in rows:
        b += r["pnl"]
        r["bal_after"] = b
    return rows, patterns, log, skipped


# ------------------------------------------------------------------ report rows
def to_report_rows(rows, B):
    C, K = P._M["C"], P._M["K"]
    out = []
    for r in rows:
        E, _, _ = B[r["tf"]]
        i, ex = r["i"], r["ex"]
        X = P.FRAMES[(r["mkt"], r["tf"])]
        X["sec"] = SEC[r["tf"]]
        spec = C.SPECS[r["mkt"]]
        cost = spec["cost_rt_bp"] / 1e4
        d = r["d"]
        swr = (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
        ep, px, rk, nts = (float(E[f"{k}_{ex}"][i]) for k in ("ep", "px", "rk", "nts"))
        e = int(E["s"][i]) + 1
        out.append(dict(r, e=e, x=int(E[f"x_{ex}"][i]), ep=ep, px=px, risk=rk, units=[(ep, e, int(X["t"][e]))],
                        R_gross=d * (px - ep) / rk, R_spread=ep * cost / rk, R_swap=ep * swr * nts / rk,
                        stop_pct=rk / ep, cost=cost, swr=swr, triple=spec["rollover3"], X=X,
                        mfe=0.0, mae=0.0, gaps=0, same=0))
    return out


def metrics_for(rows, RP, G):
    Xs = {}
    for r in rows:
        Xs[(r["mkt"], r["tf"])] = r["X"]
    T = np.unique(np.concatenate([X["t"] + X["sec"] for X in Xs.values()] + [np.array([r["t_exit"] for r in rows])]))
    T = T[(T >= G.START) & (T <= max(r["t_exit"] for r in rows))]
    RP.prep_marks(rows, T)
    with np.errstate(all="ignore"):
        M = RP.metrics(rows, T, BASE_RISK)
    return M


def baseline_g27k(RP, G, K):
    """G27K #1 exactly as the G27K report builds it (MT5 H1, report768 fills)."""
    ext = K.externals()
    combo = "C8/D3/E1/F1/G2/H2/I1/J1"
    Cc, D, E_, F, Gs, H, I, J = combo.split("/")
    sub, Xs = [], {}
    for m in K.MKTS:
        h1 = G.load_h1(m)
        M = K.prepare(m, h1, ext)
        X = G.features(G.frames(h1), m, "H4")
        X["sec"] = 14400
        Xs[m] = X
        d = K.directions(M, Cc, D, E_, J)
        idx = np.flatnonzero(d)
        sub += [dict(tr, X=X) for tr in RP.sim_paths(X, m, idx, d[idx], "I1")]
    T = RP.timeline(sub, Xs)
    RP.prep_marks(sub, T)
    with np.errstate(all="ignore"):
        M = RP.metrics(RP.account(sub, 0.01), T, 0.01)
    return M


def slim(M):
    keep = ("net", "cagr", "final", "pf", "trades", "win_n", "loss_n", "total_R", "avg_R", "largest_win", "largest_loss",
            "avg_win", "avg_loss", "expected_payoff", "recovery", "sharpe_annual", "best_month", "worst_month", "pos_months",
            "months", "longest_underwater_days", "max_positions", "avg_positions", "long_n", "short_n", "long_win",
            "hold_avg_h", "spread_R", "swap_R", "gross_R", "top5_share")
    out = {k: M.get(k) for k in keep}
    out["equity_dd"] = M["equity_dd"]["relative_pct"]
    out["balance_dd"] = M["balance_dd"]["relative_pct"]
    out["mar"] = M["cagr"] / out["equity_dd"] if out["equity_dd"] else None
    out["streaks"] = {k: M["streaks"][k] for k in ("max_wins", "max_losses", "max_losses_usd")}
    for k in ("yearly", "per_market", "curve", "dd_window", "best_trades", "worst_trades", "start", "end", "years"):
        out[k] = M.get(k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    P._M["h1"] = {m: hybrid_h1(m, G) for m in K.MKTS}
    B = {tf: P.build(P._M["h1"], tf) for tf in TFS}
    print(f"  built events: " + ", ".join(f"{tf} {len(B[tf][0]['t']):,}" for tf in TFS)
          + f"  {time.time() - t0:.0f}s", flush=True)
    dates = [ts(d) for d in pd.date_range(START, END - pd.Timedelta(days=1), freq="QS")]
    cache = HERE / ".cache_wf" / "refits.pkl"
    refits = pickle.loads(cache.read_bytes()) if cache.exists() else {}
    for D in dates:
        if D not in refits:
            refits[D] = refit_candidates(D, B)
            cache.parent.mkdir(exist_ok=True)
            cache.write_bytes(pickle.dumps(refits))
        ne = sum(eligible(c) for c in refits[D])
        print(f"  refit {pd.Timestamp(D, unit='s').date()}: {len(refits[D])} candidates, "
              f"{ne} eligible  {time.time() - t0:.0f}s", flush=True)
    news = news_times(a.root)
    res = {}
    adopted = None
    for label, decide in (("controller", True), ("no_decisions", False)):
        rows, patterns, log, skipped = run(B, refits, news, decide=decide,
                                           fixed=None if decide else adopted)
        if decide:
            adopted = list(patterns.values())
        rr = to_report_rows(rows, B)
        M = metrics_for(rr, RP, G)
        res[label] = dict(metrics=slim(M), skipped=skipped,
                          patterns=[dict(id=p.id, desc=p.desc(), adopted=str(pd.Timestamp(p.t_on, unit="s").date()),
                                         retired=str(pd.Timestamp(p.t_off, unit="s").date()) if p.t_off else None,
                                         why=p.why_off, live_n=len(p.live), live_R=float(sum(p.live)),
                                         disc=dict(n=p.c["disc_n"], R=p.c["disc_R"], t=p.c["disc_t"]),
                                         val=dict(n=p.c["val_n"], R=p.c["val_R"], t=p.c["val_t"]))
                                    for p in patterns.values()],
                          log=[dict(l, t=str(pd.Timestamp(l["t"], unit="s").date())) for l in log],
                          trades=[dict(pid=r["pid"], mkt=r["mkt"], t=int(r["t"]), t_exit=int(r["t_exit"]), d=r["d"],
                                       R=r["R"], risk=r["risk_frac"], pnl=r["pnl"]) for r in rows])
        m = res[label]["metrics"]
        print(f"  {label:13s} trades {m['trades']} net {m['net']:+,.0f} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']:.1%} "
              f"MAR {m['mar']:.2f} PF {m['pf']:.2f}", flush=True)
    Mb = baseline_g27k(RP, G, K)
    res["g27k_1"] = dict(metrics=slim(Mb))
    m = res["g27k_1"]["metrics"]
    print(f"  {'g27k #1':13s} trades {m['trades']} net {m['net']:+,.0f} CAGR {m['cagr']:+.1%} eqDD {m['equity_dd']:.1%} "
          f"MAR {m['mar']:.2f} PF {m['pf']:.2f}", flush=True)
    res["config"] = dict(start=str(START.date()), end=str(END.date()), base_risk=BASE_RISK, refits=len(dates),
                         candidates=[dict(date=str(pd.Timestamp(D, unit='s').date()), n=len(refits[D]),
                                          eligible=int(sum(eligible(c) for c in refits[D]))) for D in dates])
    (HERE / "walkforward_round1.json").write_text(json.dumps(res, ensure_ascii=False, default=str))
    print(f"  saved walkforward_round1.json  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
