"""MT5-Strategy-Tester-style report for the best five-year G768 combination (operator 2026-10-01: "I want to see something like this window").
System A = H4/C2/D1/E1/F1/G3/H7/I4/J1 (H4 20-bar breakout, long only, D1 trend agrees, stop 2 x ATR20, exit on the opposite 20-bar channel,
Turtle adds every +0.5 ATR20 up to 4 units); system B = the same with one unit. 17 MT5 markets, entries 2021-10-01 onward.
Differences from g768.simulate, made so the numbers behave like an MT5 tester run:
  - an add whose level was gapped through fills at the bar open (g768 filled it at the level);
  - swap is charged per unit from the bar it was added (g768 charged every unit from the first entry);
  - stops and adds walk the H1 bars inside each H4 bar, so the order inside an H4 bar is known; inside one H1 bar that both adds and
    trades through the raised stop the stop is assumed hit (worst case). g768.py with G768_FIX=h1 applies the same changes.
Each trade risks a fixed fraction of the realised balance per unit at its 2N stop; equity is marked at every H4 close of the union of all
markets (open P&L carried forward while a market is closed), spread charged at entry and swap accrued nightly.
Also reports the same signals on smaller universes (operator 2026-10-01: gold, silver and BTC together, and each alone), at the same risk,
with a choose/check line for the three-market set (the top three picked on 2021-10..2024-09, measured on 2024-10..2026-09).
Writes data/grid768/report768.json; `python report768.py TEMPLATE OUT_HTML` also fills the template's /*DATA*/ placeholder."""
from __future__ import annotations

import heapq
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g768 as G  # noqa: E402

C = G.C
DEPOSIT = 100_000.0
SYSTEMS = {"A": dict(name="H4 breakout, D1 trend, Turtle adds up to 4 units", I="I4", risk=0.0025),
           "B": dict(name="H4 breakout, D1 trend, one unit", I="I1", risk=None)}       # B's risk is set to match A's equity drawdown
RISKS = (0.001, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02)
R_BINS = [-np.inf, -2, -1.5, -1, -0.5, 0, 0.5, 1, 2, 3, 5, 10, 20, np.inf]
WEEKDAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
UNIVERSES = {"MET3": ["XAUUSD", "XAGUSD", "BTCUSD"], "XAUUSD": ["XAUUSD"], "XAGUSD": ["XAGUSD"], "BTCUSD": ["BTCUSD"]}
SPLIT = G.C.ts("2024-10-01")
MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def sim_paths(X, m, s_idx, d_arr, I):
    """Mirror of g768.simulate_h1 for G3/H7: stops and adds walk the H1 bars inside each H4 bar, the channel exit stays on the H4 close.
    Returns each trade with the path details the report needs (units with their add bar and time, MFE/MAE, costs)."""
    o, h, l, c, a20, dhi, dlo, t = X["o"], X["h"], X["l"], X["c"], X["a20"], X["dhi"], X["dlo"], X["t"]; n = len(c)
    B = X["b"]; bo, bh, bl, bt = B["o"], B["h"], B["l"], B["t"]; k0, k1 = X["k0"], X["k1"]
    spec = C.SPECS[m]; cost = spec["cost_rt_bp"] / 1e4
    out = []; busy = -1
    for s, d in zip(s_idx, d_arr):
        if s <= busy or s + 1 >= n or not np.isfinite(a20[s]) or not np.isfinite(X["a14"][s]):
            continue
        e = s + 1; ep = o[e]; N = a20[s]; risk = 2 * N; stop = ep - d * risk
        units = [(ep, e, int(bt[k0[e]]))]; j = e; px = None; tx = None; fav = adv = 0.0; gaps = 0; same = 0
        while j < n:
            for q in range(k0[j], k1[j]):
                oq, hq, lq = bo[q], bh[q], bl[q]
                if (d > 0 and lq <= stop) or (d < 0 and hq >= stop):
                    px = stop if d * (oq - stop) > 0 else oq; tx = int(bt[q]); break
                if I == "I4":
                    n0 = len(units)
                    while len(units) < 4:
                        lvl = units[-1][0] + d * 0.5 * N
                        if not ((d > 0 and hq >= lvl) or (d < 0 and lq <= lvl)):
                            break
                        fill = max(lvl, oq) if d > 0 else min(lvl, oq); gaps += fill != lvl
                        units.append((fill, j, int(bt[q])))
                        stop = max(stop, fill - 2 * N) if d > 0 else min(stop, fill + 2 * N)
                    if len(units) > n0 and ((d > 0 and lq <= stop) or (d < 0 and hq >= stop)):
                        fav = max(fav, d * ((hq if d > 0 else lq) - ep)); px = stop; tx = int(bt[q]); same = 1; break
                fav = max(fav, d * ((hq if d > 0 else lq) - ep)); adv = max(adv, -d * ((lq if d > 0 else hq) - ep))
            if px is not None:
                break
            hit = (c[j] < dlo[j]) if d > 0 else (c[j] > dhi[j])
            if hit and j + 1 < n:
                px = o[j + 1]; j += 1; tx = int(t[j]); break
            j += 1
        if px is None:
            px = c[n - 1]; j = n - 1; tx = int(t[j])
        fav = max(fav, d * (px - ep)); adv = max(adv, -d * (px - ep))
        swr = (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
        nts = C.nights(np.array([u[2] for u in units], np.int64), np.full(len(units), tx, np.int64), spec["rollover3"])
        gross = sum(d * (px - u[0]) for u in units)
        swap = sum(u[0] * swr * k for u, k in zip(units, nts)); spread = sum(u[0] * cost for u in units)
        out.append(dict(mkt=m, e=e, x=j, d=int(d), ep=ep, px=px, risk=risk, units=units, R=(gross - swap - spread) / risk, R_gross=gross / risk,
                        R_swap=swap / risk, R_spread=spread / risk, t=int(t[e]), t_exit=tx, mfe=fav / risk, mae=adv / risk, gaps=gaps, same=same,
                        stop_pct=risk / ep, cost=cost, swr=swr, triple=spec["rollover3"]))
        busy = j
    return out


def build(I):
    Xs = {}
    for m in G.MKTS:
        F = G.frames(G.load_h1(m)); Xs[m] = G.features(F, m, "H4")
    trades = []; grid_R = 0.0
    for m in G.MKTS:
        X = Xs[m]; d = G.signals(X, "D1", None)
        s = np.flatnonzero((d > 0) & (X["t"] >= G.START) & (X["htf"] == d))
        trades += [dict(tr, X=X) for tr in sim_paths(X, m, s, d[s], I)]
        grid_R += sum(r[2] for r in G.simulate(X, m, s, d[s], "G3", "H7", I))
    return trades, Xs, grid_R


def timeline(trades, Xs):
    last = max(r["t_exit"] for r in trades)
    T = np.unique(np.concatenate([X["t"] + 14400 for X in Xs.values()] + [np.array([r["t_exit"] for r in trades])]))
    return T[(T >= G.START) & (T <= last)]


def prep_marks(trades, T):
    """Open P&L per unit of risk (R of one unit) at every timeline point strictly inside each trade, carried forward between own closes."""
    for r in trades:
        X = r["X"]; e, x, d = r["e"], r["x"], r["d"]
        lo = np.searchsorted(T, r["t"], "right"); hi = np.searchsorted(T, r["t_exit"], "left")
        r["mk"] = None
        if x <= e or hi <= lo:
            continue
        js = np.arange(e, x); tc = X["t"][js] + 14400; cj = X["c"][js]
        val = np.zeros(len(js)); nu = np.zeros(len(js))
        for u, jb, ta in r["units"]:
            on = js >= jb
            nts = C.nights(np.full(int(on.sum()), ta), tc[on], r["triple"])
            val[on] += d * (cj[on] - u) - u * (r["cost"] + r["swr"] * nts); nu[on] += 1
        k = np.searchsorted(tc, T[lo:hi], "right") - 1
        kk = np.maximum(k, 0)
        r["mk"] = (lo, hi, np.where(k >= 0, val[kk] / r["risk"], -r["cost"] * r["ep"] / r["risk"]), np.where(k >= 0, nu[kk], 1.0))


def account(trades, risk):
    order = sorted(range(len(trades)), key=lambda i: (trades[i]["t"], trades[i]["mkt"]))
    bal = DEPOSIT; heap = []; live = {}; rows = []
    for i in order:
        tr = trades[i]
        while heap and heap[0][0] <= tr["t"]:
            _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; r["bal_after"] = bal; rows.append(r)
        live[i] = dict(tr, unit_usd=risk * bal, pnl=risk * bal * tr["R"], bal_before=bal); heapq.heappush(heap, (tr["t_exit"], i))
    while heap:
        _, k = heapq.heappop(heap); r = live.pop(k); bal += r["pnl"]; r["bal_after"] = bal; rows.append(r)
    rows.sort(key=lambda r: (r["t_exit"], r["t"]))
    return rows


def half(trades, risk, lo, hi):
    """Balance-only account on the trades entered in [lo, hi): return, max balance drawdown, R, trades."""
    sub = [r for r in trades if lo <= r["t"] < hi]
    if not sub:
        return dict(n=0, ret=0.0, dd=0.0, R=0.0)
    rows = account(sub, risk); bal = np.array([r["bal_after"] for r in rows])
    return dict(n=len(sub), ret=float(bal[-1] / DEPOSIT - 1), dd=dd(bal, DEPOSIT)["relative_pct"], R=float(sum(r["R"] for r in sub)))


def curve(rows, T):
    opn = np.zeros(len(T)); npos = np.zeros(len(T)); notional = np.zeros(len(T))
    for r in rows:
        if r["mk"] is None:
            continue
        lo, hi, vR, nu = r["mk"]
        opn[lo:hi] += r["unit_usd"] * vR; npos[lo:hi] += 1; notional[lo:hi] += nu * r["unit_usd"] / r["stop_pct"]
    bt = np.array([r["t_exit"] for r in rows]); bv = np.array([r["bal_after"] for r in rows])
    k = np.searchsorted(bt, T, "right") - 1
    balT = np.where(k >= 0, bv[np.maximum(k, 0)], DEPOSIT)
    eq = balT + opn
    return balT, eq, npos, notional / eq


def dd(series, start):
    s = np.asarray(series, float)
    peak = np.maximum.accumulate(np.r_[start, s])[1:]
    money = peak - s; pct = money / peak
    i, k = int(np.argmax(money)), int(np.argmax(pct))
    return dict(absolute=float(max(0.0, start - s.min())), maximal=float(money[i]), maximal_pct=float(pct[i]), relative_pct=float(pct[k]),
                relative=float(money[k]))


def streaks(p):
    runs = []
    for v in p:
        sg = 1 if v > 0 else -1
        if runs and runs[-1][0] == sg:
            runs[-1][1] += 1; runs[-1][2] += v
        else:
            runs.append([sg, 1, v])
    W = [r for r in runs if r[0] > 0]; L = [r for r in runs if r[0] < 0]
    mw = max(W, key=lambda r: (r[1], r[2])); ml = max(L, key=lambda r: (r[1], -r[2]))
    pw = max(W, key=lambda r: r[2]); pl = min(L, key=lambda r: r[2])
    return dict(max_wins=mw[1], max_wins_usd=mw[2], max_losses=ml[1], max_losses_usd=ml[2], max_profit_usd=pw[2], max_profit_n=pw[1],
                max_loss_usd=pl[2], max_loss_n=pl[1], avg_wins=float(np.mean([r[1] for r in W])), avg_losses=float(np.mean([r[1] for r in L])),
                runs=len(runs))


def decimate(T, *ys, buckets=700):
    """Keep the first, last, min and max point of each bucket so drawdowns stay visible."""
    n = len(T); edges = np.linspace(0, n, min(buckets, n) + 1).astype(int); keep = set()
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        keep.update((a, b - 1))
        for y in ys:
            keep.update((a + int(np.argmin(y[a:b])), a + int(np.argmax(y[a:b]))))
    return np.array(sorted(keep))


def metrics(rows, T, risk, full=True):
    balT, eq, npos, lev = curve(rows, T)
    pnl = np.array([r["pnl"] for r in rows]); bal = np.array([r["bal_after"] for r in rows]); R = np.array([r["R"] for r in rows])
    yrs = (T[-1] - G.START) / (365.25 * 86400)
    bdd, edd = dd(bal, DEPOSIT), dd(eq, DEPOSIT)
    out = dict(risk=risk, net=float(pnl.sum()), cagr=float((bal[-1] / DEPOSIT) ** (1 / yrs) - 1), balance_dd=bdd, equity_dd=edd, final=float(bal[-1]))
    if not full:
        return out
    hpr = bal / (bal - pnl)
    gp, gl = float(pnl[pnl > 0].sum()), float(pnl[pnl <= 0].sum())
    idx = np.arange(len(bal)); fit = np.polyval(np.polyfit(idx, bal, 1), idx)
    me = pd.Series(eq, index=pd.to_datetime(T, unit="s")).resample("ME").last().ffill()
    mret = pd.concat([pd.Series([DEPOSIT], index=[me.index[0] - pd.offsets.MonthEnd(1)]), me]).pct_change().dropna()
    st = streaks(pnl); N = len(pnl); Wn = int((pnl > 0).sum()); Ln = N - Wn; P = 2 * Wn * Ln
    z = (N * (st["runs"] - 0.5) - P) / np.sqrt(P * (P - N) / (N - 1)) if P > N else None
    hold_h = np.array([(r["t_exit"] - r["t"]) / 3600 for r in rows])
    mfe = np.array([r["mfe"] for r in rows]); mae = np.array([r["mae"] for r in rows])
    pk = -np.inf; peak_t = T[0]; under = 0.0
    for tt, v in zip(T, eq):
        if v >= pk:
            pk, peak_t = v, tt
        else:
            under = max(under, (tt - peak_t) / 86400)
    srt = np.sort(R)[::-1]
    out.update(gross_profit=gp, gross_loss=gl, pf=gp / -gl, expected_payoff=float(pnl.mean()), recovery=float(pnl.sum() / edd["maximal"]),
               ahpr=float(hpr.mean()), ghpr=float((bal[-1] / DEPOSIT) ** (1 / N)), sharpe_trade=float((hpr.mean() - 1) / hpr.std(ddof=1)),
               sharpe_annual=float(mret.mean() / mret.std(ddof=1) * np.sqrt(12)), z_score=float(z) if z is not None else None,
               lr_corr=float(np.corrcoef(idx, bal)[0, 1]), lr_se=float(np.sqrt(((bal - fit) ** 2).sum() / (N - 2))),
               trades=N, deals=int(sum(len(r["units"]) + 1 for r in rows)), units=int(sum(len(r["units"]) for r in rows)),
               long_n=int(sum(r["d"] > 0 for r in rows)), long_win=float(np.mean([p > 0 for p, r in zip(pnl, rows) if r["d"] > 0])),
               short_n=int(sum(r["d"] < 0 for r in rows)), win_n=Wn, loss_n=Ln, largest_win=float(pnl.max()), largest_loss=float(pnl.min()),
               avg_win=float(pnl[pnl > 0].mean()), avg_loss=float(pnl[pnl <= 0].mean()), streaks=st,
               hold_min_h=float(hold_h.min()), hold_max_h=float(hold_h.max()), hold_avg_h=float(hold_h.mean()),
               corr_p_mfe=float(np.corrcoef(R, mfe)[0, 1]), corr_p_mae=float(np.corrcoef(R, mae)[0, 1]), corr_mfe_mae=float(np.corrcoef(mfe, mae)[0, 1]),
               total_R=float(R.sum()), avg_R=float(R.mean()), gross_R=float(sum(r["R_gross"] for r in rows)),
               spread_R=float(sum(r["R_spread"] for r in rows)), swap_R=float(sum(r["R_swap"] for r in rows)),
               top1_share=float(srt[:max(1, N // 100)].sum() / R.sum()), top5_share=float(srt[:max(1, N // 20)].sum() / R.sum()),
               avg_units=float(np.mean([len(r["units"]) for r in rows])), gap_adds=int(sum(r["gaps"] for r in rows)), same_bar=int(sum(r["same"] for r in rows)),
               max_positions=int(npos.max()), avg_positions=float(npos.mean()), max_leverage=float(lev.max()), avg_leverage=float(lev.mean()),
               longest_underwater_days=float(under), best_month=float(mret.max()), worst_month=float(mret.min()),
               pos_months=float((mret > 0).mean()), months=int(len(mret)))
    tt = pd.to_datetime([r["t"] for r in rows], unit="s")

    def by(keys, labels):
        return [dict(k=lab, n=int((keys == i).sum()), pnl=float(pnl[keys == i].sum()), R=float(R[keys == i].sum()),
                     win=float((pnl[keys == i] > 0).mean()) if (keys == i).any() else 0.0) for i, lab in labels]
    out["hours"] = by(tt.hour.to_numpy(), [(h, f"{h:02d}") for h in range(24)])
    out["weekdays"] = by(tt.weekday.to_numpy(), list(enumerate(WEEKDAYS)))
    out["months"] = by(tt.month.to_numpy(), [(i + 1, nm) for i, nm in enumerate(MONTHS)])
    cats = np.digitize(R, R_BINS[1:-1])

    def lab(a, b):
        return f"< {b:g}" if not np.isfinite(a) else (f"> {a:g}" if not np.isfinite(b) else f"{a:g} ถึง {b:g}")
    out["r_hist"] = [dict(k=lab(R_BINS[i], R_BINS[i + 1]), n=int((cats == i).sum()), R=float(R[cats == i].sum())) for i in range(len(R_BINS) - 1)]
    D = pd.DataFrame(dict(m=[r["mkt"] for r in rows], pnl=pnl, R=R, u=[len(r["units"]) for r in rows]))
    out["per_market"] = sorted([dict(mkt=m, n=len(g), win=float((g.pnl > 0).mean()), net=float(g.pnl.sum()), R=float(g.R.sum()), avgR=float(g.R.mean()),
                                     pf=float(g.pnl[g.pnl > 0].sum() / -g.pnl[g.pnl <= 0].sum()) if (g.pnl <= 0).any() else None, units=float(g.u.mean()))
                                for m, g in D.groupby("m")], key=lambda x: -x["net"])
    yT = pd.to_datetime(T, unit="s").year.to_numpy(); ty = pd.to_datetime([r["t_exit"] for r in rows], unit="s").year.to_numpy()
    yearly = []; prev = DEPOSIT; pk_run = DEPOSIT
    for y in np.unique(yT):
        sel = yT == y; endv = float(balT[sel][-1]); e_y = eq[sel]
        peak = np.maximum.accumulate(np.r_[pk_run, e_y])[1:]; pk_run = float(peak[-1])
        yearly.append(dict(year=int(y), ret=endv / prev - 1, R=float(R[ty == y].sum()), trades=int((ty == y).sum()),
                           dd=float(((peak - e_y) / peak).max()), win=float((pnl[ty == y] > 0).mean()) if (ty == y).any() else 0.0))
        prev = endv
    out["yearly"] = yearly
    day1 = lambda x: str(pd.Timestamp(int(x), unit="s").date())
    pick = lambda r: dict(mkt=r["mkt"], t=day1(r["t"]), t_exit=day1(r["t_exit"]), units=len(r["units"]), R=float(r["R"]), pnl=float(r["pnl"]),
                          ep=float(r["ep"]), px=float(r["px"]))
    srt_rows = sorted(rows, key=lambda r: -r["R"])
    out["best_trades"] = [pick(r) for r in srt_rows[:10]]; out["worst_trades"] = [pick(r) for r in srt_rows[-10:][::-1]]
    pk = np.maximum.accumulate(np.r_[DEPOSIT, eq])[1:]; ddp = (pk - eq) / pk; i1 = int(np.argmax(ddp)); i0 = int(np.argmax(eq[:i1 + 1]))
    rec = np.flatnonzero(eq[i1:] >= eq[i0]); i2 = i1 + int(rec[0]) if len(rec) else None

    def contrib(i):
        v = {}
        for r in rows:
            if r["t_exit"] <= T[i]:
                v[r["mkt"]] = v.get(r["mkt"], 0.0) + r["pnl"]
            elif r["mk"] is not None and r["mk"][0] <= i < r["mk"][1]:
                v[r["mkt"]] = v.get(r["mkt"], 0.0) + r["unit_usd"] * r["mk"][2][i - r["mk"][0]]
        return v
    c0, c1 = contrib(i0), contrib(i1)
    chg = sorted(((m, c1.get(m, 0.0) - c0.get(m, 0.0)) for m in set(c0) | set(c1)), key=lambda x: x[1])
    day = lambda i: str(pd.Timestamp(int(T[i]), unit="s").date())
    out["dd_window"] = dict(peak=day(i0), trough=day(i1), recovered=day(i2) if i2 is not None else None, depth=float(ddp[i1]), now=float(ddp[-1]),
                            peak_eq=float(eq[i0]), trough_eq=float(eq[i1]), by_market=[dict(mkt=m, chg=float(v)) for m, v in chg])
    keep = decimate(T, eq, balT)
    pk = np.maximum.accumulate(np.r_[DEPOSIT, eq])[1:]
    out["curve"] = dict(t=[int(x) for x in T[keep]], bal=[round(float(x), 2) for x in balT[keep]], eq=[round(float(x), 2) for x in eq[keep]],
                        dd=[round(float(x), 4) for x in ((pk - eq) / pk)[keep]], pos=[int(x) for x in npos[keep]])
    out["start"] = str(pd.Timestamp(G.START, unit="s").date()); out["end"] = str(pd.Timestamp(int(T[-1]), unit="s").date()); out["years"] = float(yrs)
    return out


def grid_check(suffix="_h1", combo="H4/C2/D1/E1/F1/G3/H7/I4/J1"):
    """Pass counts and best-of-768 total R for the real grid and the 20 placebo runs re-simulated with the same fills (g768 G768_FIX=h1)."""
    f = G.OUT / f"g768_real{suffix}.csv"
    if not f.exists():
        return None

    def best(D):
        D = D.assign(totR=D.R * D.n).sort_values("totR", ascending=False)
        return dict(combo=D.combo.iloc[0], totR=float(D.totR.iloc[0]), R=float(D.R.iloc[0]), n=int(D.n.iloc[0]))
    real = pd.read_csv(f); rr = real.assign(totR=real.R * real.n)
    out = dict(real_basic=int(real.pass_basic.sum()), real_strict=int(real.pass_strict.sum()), real_best=best(real),
               rank_A=int(rr.totR.rank(ascending=False, method="min")[rr.combo == combo].iloc[0]), totR_A=float(rr.totR[rr.combo == combo].iloc[0]),
               top5=[dict(combo=r.combo, totR=float(r.totR), R=float(r.R), n=int(r.n), p=float(r.p)) for r in rr.sort_values("totR", ascending=False).head(5).itertuples()])
    for kind in ("placebo", "drift"):
        Ds = [pd.read_csv(q) for q in sorted(G.OUT.glob(f"g768_{kind}[0-9]{suffix}.csv"))]
        if len(Ds) < 10:                                      # placebo runs still going: leave the check out rather than show part of it
            return None
        out[kind] = dict(runs=len(Ds), basic=[int(D.pass_basic.sum()) for D in Ds], strict=[int(D.pass_strict.sum()) for D in Ds],
                         best=[best(D)["totR"] for D in Ds], same_combo=[float((D.R * D.n)[D.combo == combo].iloc[0]) for D in Ds])
    return out


def main():
    res = {}
    for k, cfg in SYSTEMS.items():
        trades, Xs, grid_R = build(cfg["I"])
        T = timeline(trades, Xs); prep_marks(trades, T)
        res[k] = dict(trades=trades, Xs=Xs, T=T, grid_R=grid_R, table=[metrics(account(trades, rk), T, rk, full=False) for rk in RISKS])
    target = None
    for k, cfg in SYSTEMS.items():
        trades, Xs, T = res[k]["trades"], res[k]["Xs"], res[k]["T"]
        risk = cfg["risk"]
        if risk is None:                                      # match A's equity drawdown on a 0.05% grid
            grid = np.round(np.arange(0.001, 0.0301, 0.0005), 4)
            dds = np.array([metrics(account(trades, rk), T, rk, full=False)["equity_dd"]["relative_pct"] for rk in grid])
            risk = float(grid[int(np.argmin(np.abs(dds - target)))])
        M = metrics(account(trades, risk), T, risk)
        if k == "A":
            target = M["equity_dd"]["relative_pct"]
        bars = int(sum(int(((X["t"] >= G.START) & (X["t"] <= T[-1])).sum()) for X in Xs.values()))
        res[k]["out"] = dict(key=k, uni="ALL", mkts=list(G.MKTS), name=cfg["name"], deposit=DEPOSIT, markets=len(G.MKTS), bars=bars,
                             grid_R=res[k]["grid_R"], risk_table=res[k]["table"], **M)
    out = {k: v["out"] for k, v in res.items()}
    for k in SYSTEMS:
        trades, Xs, T = res[k]["trades"], res[k]["Xs"], res[k]["T"]; risk = out[k]["risk"]
        for u, mk in UNIVERSES.items():
            sel = [r for r in trades if r["mkt"] in mk]
            M = metrics(account(sel, risk), T, risk)
            bars = int(sum(int(((Xs[m]["t"] >= G.START) & (Xs[m]["t"] <= T[-1])).sum()) for m in mk))
            o = dict(key=k, uni=u, mkts=mk, name=SYSTEMS[k]["name"], deposit=DEPOSIT, markets=len(mk), bars=bars, grid_R=res[k]["grid_R"],
                     risk_table=[metrics(account(sel, rk), T, rk, full=False) for rk in RISKS], **M)
            if len(mk) > 1:
                R1 = {}
                for r in trades:
                    if r["t"] < SPLIT:
                        R1[r["mkt"]] = R1.get(r["mkt"], 0.0) + r["R"]
                pick = sorted(R1, key=lambda m: -R1[m])[:len(mk)]
                o["choose"] = dict(pick=pick, split=str(pd.Timestamp(SPLIT, unit="s").date()),
                                   pick_second=half([r for r in trades if r["mkt"] in pick], risk, SPLIT, 2 ** 62),
                                   this_second=half(sel, risk, SPLIT, 2 ** 62), this_first=half(sel, risk, G.START, SPLIT))
            out[f"{k}_{u}"] = o
    gc = grid_check()
    for k in out:
        out[k]["grid_check"] = gc
    if gc:
        print("grid check:", json.dumps(gc)[:1500])
    (G.OUT / "report768.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    for k, r in out.items():
        if r["uni"] != "ALL":
            ch = r.get("choose")
            print(f"{k} {r['mkts']}: total {r['net'] / DEPOSIT:+.0%} CAGR {r['cagr']:.1%} eqDD {r['equity_dd']['relative_pct']:.1%} "
                  f"balDD {r['balance_dd']['relative_pct']:.1%} trades {r['trades']} win {r['win_n'] / r['trades']:.0%} PF {r['pf']:.2f}"
                  + (f" | chosen on 3y {ch['pick']}: next 2y {ch['pick_second']['ret']:+.0%} vs this set {ch['this_second']['ret']:+.0%}" if ch else ""))
            continue
        print(f"{k} risk {r['risk']:.4f} | net {r['net']:,.0f} PF {r['pf']:.2f} trades {r['trades']} win {r['win_n'] / r['trades']:.1%} CAGR {r['cagr']:.1%} "
              f"balDD {r['balance_dd']['relative_pct']:.1%} eqDD {r['equity_dd']['relative_pct']:.1%} recovery {r['recovery']:.2f} "
              f"Sharpe/yr {r['sharpe_annual']:.2f} AHPR {r['ahpr']:.5f} GHPR {r['ghpr']:.5f} LRcorr {r['lr_corr']:.3f} Z {r['z_score']:.2f}")
        print(f"   R total {r['total_R']:.1f} (grid {r['grid_R']:.1f}) gross {r['gross_R']:.1f} spread {r['spread_R']:.1f} swap {r['swap_R']:.1f} "
              f"gap adds {r['gap_adds']} same-bar stops {r['same_bar']} top1% {r['top1_share']:.0%} top5% {r['top5_share']:.0%} maxpos {r['max_positions']} maxlev {r['max_leverage']:.1f} "
              f"underwater {r['longest_underwater_days']:.0f}d months+ {r['pos_months']:.0%}")
        print("   risk table:", "  ".join(f"{x['risk']:.2%}: CAGR {x['cagr']:.0%} bDD {x['balance_dd']['relative_pct']:.0%} eDD {x['equity_dd']['relative_pct']:.0%}"
                                          for x in r["risk_table"]))
        print("   yearly:", "  ".join(f"{y['year']} {y['ret']:+.0%} {y['R']:+.0f}R dd{y['dd']:.0%}" for y in r["yearly"]))
    if len(sys.argv) > 2:
        tpl = Path(sys.argv[1]).read_text(encoding="utf-8")
        Path(sys.argv[2]).write_text(tpl.replace("/*DATA*/", json.dumps(out, ensure_ascii=False)), encoding="utf-8")
        print("html written", sys.argv[2])


if __name__ == "__main__":
    main()
