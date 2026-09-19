#!/usr/bin/env python3
"""Three targets, because a bracket does not pay the expected move.

THE ARITHMETIC THAT MAKES THIS A DIFFERENT QUESTION

  Direction at a fixed horizon has been measured to exhaustion here and fails
  structurally: the payoff is the expected MOVE, which is small, and the cost
  is the spread, which is fixed. Every conditioning state raised the move by
  less than the factor needed, and the best collapsed on a fresh market.

  A bracket pays something else. Enter with a symmetric bracket at plus or
  minus D and ask only which side is touched first. The expectancy is

      (2p - 1) * D  -  one spread

  and D is a choice rather than a property of the market. At D = 1.5 ATR with
  the spread near 12% of ATR, D is about twelve spreads, so breakeven sits at

      p = 0.5 + 1/(2 * 12.5) = 0.540

  A four point lift in which side is touched first pays. A four point lift in
  sign accuracy at a fixed horizon does not, because there the payoff is the
  move and not the bracket. Same information content, completely different
  economics, and this project has never asked the question in the form that
  has the better arithmetic.

  The third target is not directional at all: whether the next window's range
  is large. That has the economics of a straddle, and the only family in the
  pilot carrying anything was the one conditioning on range states - which is
  a reason to ask, not a result.

WHAT IS DIFFERENT ABOUT THE DESIGN

  The out-of-sample split is inside the funnel rather than bolted on. Every
  hypothesis is fitted on 2004-2016 and reported on 2017-2026, BOTH printed
  for all of them, and only what passes both goes to USDSEK. This run has
  twice now seen a set that was strong on the discovery data and scattered
  off it; building the second period into the same table makes that visible
  at a glance instead of two commits later.

WHAT THE UNCONDITIONAL PATH RATE IS NOT

  50%. A symmetric bracket measured on this engine has a stop-first bias from
  three sources that are all real: the entry pays half a spread before the
  levels are measured, G12 resolves a bar touching both as a stop, and gold
  minute data measured the true stop-first rate at 73% on ambiguous bars. So
  the number that matters is the LIFT over the same bracket placed on matched
  control entries, never the raw rate.
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import controls as C
import discovery as DIS
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
SPLIT = pd.Timestamp("2017-01-01", tz="UTC")
HORIZON = 3          # hours, for direction and expansion
PATH_BARS = 12       # bars a bracket is given to resolve
PATH_K = (1.0, 1.5, 2.0)
FLOOR = 4.90


# ============================================================== targets ====
def target_direction(P, t, d, h=HORIZON):
    return DIS.score(P, t, d, h, idx=P["idx"])


def target_path(P, t, d, k, bars=PATH_BARS):
    """Which side of a symmetric k-ATR bracket is touched first.

    Vectorised the same way engine_fast is, and for the same reason: the first
    touch is a dense window of fixed length, so it is a matrix operation. The
    stop test is evaluated before the target test at equal indices, which is
    G12 - a bar touching both is a stop. An argmax over the combined mask
    would hand half the ambiguous bars to the target."""
    N = P["N"]
    A = np.asarray(P["A"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    hi, lo = np.asarray(P["h"], float), np.asarray(P["l"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    keep = (t >= 300) & (t + bars + 1 < N)
    t, d = t[keep], d[keep]
    if len(t) < 100:
        return None
    e = t + 1
    entry = o[e]
    D = k * A[t]
    sp = ask_o[e] - bid_o[e]
    ok = np.isfinite(entry) & np.isfinite(D) & (D > 0) & np.isfinite(sp) & (sp > 0)
    t, d, e, entry, D, sp = t[ok], d[ok], e[ok], entry[ok], D[ok], sp[ok]
    if len(t) < 100:
        return None
    up = entry + D
    dn = entry - D
    tgt = np.where(d > 0, up, dn)
    stp = np.where(d > 0, dn, up)

    K = e[:, None] + np.arange(bars)[None, :]
    valid = K < N
    Kc = np.clip(K, 0, N - 1)
    H, L = hi[Kc], lo[Kc]
    with np.errstate(invalid="ignore"):
        hit_t = np.where(d[:, None] > 0, H >= tgt[:, None], L <= tgt[:, None]) & valid
        hit_s = np.where(d[:, None] > 0, L <= stp[:, None], H >= stp[:, None]) & valid
    BIG = bars + 1
    ft = np.where(hit_t.any(1), hit_t.argmax(1), BIG)
    fs = np.where(hit_s.any(1), hit_s.argmax(1), BIG)
    resolved = (ft < BIG) | (fs < BIG)
    # G12: equal index is a stop
    target_first = (ft < fs) & resolved
    n_res = int(resolved.sum())
    if n_res < 100:
        return None
    p = float(target_first[resolved].sum() / n_res)
    # expectancy of the bracket in spread units, mid-to-mid less one round trip
    d_over_s = float(np.mean(D[resolved] / sp[resolved]))
    edge = (2 * p - 1) * d_over_s - 1.0
    breakeven_p = 0.5 + 1.0 / (2 * d_over_s) if d_over_s > 0 else np.nan
    se = math.sqrt(max(p * (1 - p), 1e-9) / n_res)
    return dict(n=int(len(t)), n_resolved=n_res, resolve_rate=n_res / len(t),
                p_target_first=p, d_over_spread=d_over_s,
                edge=edge, breakeven_p=breakeven_p,
                t_p=(p - 0.5) / se if se > 0 else np.nan)


def target_expansion(P, t, d, h=HORIZON, k=0.5):
    """A breakout straddle: is the next window's move large enough to pay for
    catching it late?

    THE FIRST VERSION OF THIS WAS NOT AN EXPECTANCY

      It scored the next window's true range over the spread, minus two, and
      returned numbers like +73 "round trips". A range is not a profit. Price
      covering fifty-five spreads of ground says nothing about whether a
      straddle would have captured any of it - the whipsaw case, where both
      sides trigger and neither runs, has exactly the same range as the clean
      case. Reporting that as an edge would have been the largest number in
      this project and meant nothing at all.

    WHAT IT MEASURES NOW

      Stops placed k ATR either side of the entry bar's open. Whichever
      triggers FIRST is taken, in its own direction, and held to the close of
      the window. Expectancy is the move from the trigger to that close, less
      one round trip, in spread units. Windows where neither side triggers
      contribute zero rather than being dropped, because not trading is the
      outcome on those and excluding them would price a strategy nobody could
      run.

      This is non-directional by construction: the signal chooses WHEN to arm
      the straddle and the market chooses which way."""
    N = P["N"]
    A = np.asarray(P["A"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    hi, lo = np.asarray(P["h"], float), np.asarray(P["l"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    keep = (t >= 300) & (t + h + 1 < N)
    t = t[keep]
    if len(t) < 100:
        return None
    e = t + 1
    entry = o[e]
    X = k * A[t]
    sp = ask_o[e] - bid_o[e]
    ok = np.isfinite(entry) & np.isfinite(X) & (X > 0) & np.isfinite(sp) & (sp > 0)
    t, e, entry, X, sp = t[ok], e[ok], entry[ok], X[ok], sp[ok]
    if len(t) < 100:
        return None
    up, dn = entry + X, entry - X
    K = e[:, None] + np.arange(h)[None, :]
    valid = K < N
    Kc = np.clip(K, 0, N - 1)
    H, L = hi[Kc], lo[Kc]
    with np.errstate(invalid="ignore"):
        hit_u = (H >= up[:, None]) & valid
        hit_d = (L <= dn[:, None]) & valid
    BIG = h + 1
    fu = np.where(hit_u.any(1), hit_u.argmax(1), BIG)
    fd = np.where(hit_d.any(1), hit_d.argmax(1), BIG)
    # a bar touching both is resolved the conservative way: the side that
    # would have been entered is unknowable at this resolution, so the window
    # is scored as no trade rather than as the favourable side
    both_same_bar = (fu == fd) & (fu < BIG)
    took_up = (fu < fd) & (fu < BIG)
    took_dn = (fd < fu) & (fd < BIG)
    exit_px = c[np.clip(e + h - 1, 0, N - 1)]
    pnl = np.zeros(len(t))
    pnl[took_up] = (exit_px[took_up] - up[took_up]) - sp[took_up]
    pnl[took_dn] = (dn[took_dn] - exit_px[took_dn]) - sp[took_dn]
    traded = took_up | took_dn
    if traded.sum() < 50:
        return None
    edge = float(pnl.sum() / sp.sum())
    return dict(n=int(len(t)), n_traded=int(traded.sum()),
                trigger_rate=float(traded.mean()),
                ambiguous=float(both_same_bar.mean()),
                edge=edge,
                edge_per_trade=float(pnl[traded].sum() / sp[traded].sum()))


# ============================================================ candidates ===
def candidates(P, V, ref=None):
    out = []
    for _, fn in DIS.FAMILIES:
        try:
            out.extend(fn(P, V))
        except Exception:
            pass
    if ref is not None:
        try:
            out.extend(DIS.fam_cross(P, V, ref))
        except Exception:
            pass
    return out


def cross_t(v):
    v = np.asarray([y for y in v if np.isfinite(y)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("EXPANDED DISCOVERY - direction, path asymmetry, expansion")
    print("=" * 108)
    print(__doc__.split("THE ARITHMETIC THAT MAKES THIS A DIFFERENT "
                        "QUESTION")[1].split("WHAT IS DIFFERENT ABOUT")[0])

    ref_df = load_bidask_h1("EURUSD")
    ref_s = None
    if ref_df is not None:
        Pr = X.prep(ref_df, 60)
        ref_s = pd.Series(DIS.state_vars(Pr)["ret_atr"],
                          index=pd.DatetimeIndex(Pr["idx"]))

    book = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        V = DIS.state_vars(P)
        idx = pd.DatetimeIndex(P["idx"])
        early_bar = idx < SPLIT
        ref = None
        if ref_s is not None and sym != "EURUSD":
            ref = ref_s.reindex(idx).to_numpy(float)
        for name, t, d in candidates(P, V, ref):
            for per, mask in (("2004-2016", early_bar[t]),
                              ("2017-2026", ~early_bar[t])):
                tt, dd = t[mask], d[mask]
                if len(tt) < 150:
                    continue
                row = dict(symbol=sym, period=per, n=int(len(tt)))
                s = target_direction(P, tt, dd)
                row["direction"] = s["edge"] if s else np.nan
                for k in PATH_K:
                    pr = target_path(P, tt, dd, k)
                    row[f"path{k}"] = pr["edge"] if pr else np.nan
                    row[f"p{k}"] = pr["p_target_first"] if pr else np.nan
                    row[f"be{k}"] = pr["breakeven_p"] if pr else np.nan
                ex = target_expansion(P, tt, dd)
                row["expansion"] = ex["edge"] if ex else np.nan
                book.setdefault(name, []).append(row)
        print(f"  {sym:<9}{time.time()-t0:>7.0f}s", flush=True)

    if not book:
        print("  nothing measured")
        return

    # unconditional reference, per period, for the path target
    print("\n" + "=" * 108)
    print("THE UNCONDITIONAL PATH RATE - which the lift is measured against")
    print("=" * 108)
    base = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        V = DIS.state_vars(P)
        r = V["ret_atr"]
        s = np.sign(np.nan_to_num(r, nan=0.0))
        m = np.isfinite(r) & (s != 0)
        m[:300] = False
        t = np.where(m)[0]
        for k in PATH_K:
            pr = target_path(P, t, -s[m].astype(float), k)
            if pr:
                base.setdefault(k, []).append(pr)
    print(f"  {'bracket':<10}{'p(target first)':>18}{'breakeven p':>14}"
          f"{'D/spread':>11}{'resolve rate':>15}{'edge':>9}")
    base_summary = []
    for k in PATH_K:
        gs = base.get(k, [])
        if not gs:
            continue
        p = float(np.mean([g["p_target_first"] for g in gs]))
        be = float(np.mean([g["breakeven_p"] for g in gs]))
        ds = float(np.mean([g["d_over_spread"] for g in gs]))
        rr = float(np.mean([g["resolve_rate"] for g in gs]))
        ed = float(np.mean([g["edge"] for g in gs]))
        base_summary.append(dict(k=k, p=p, breakeven=be, d_over_spread=ds,
                                 resolve_rate=rr, edge=ed))
        print(f"  {k:<10.1f}{p*100:>17.2f}%{be*100:>13.2f}%{ds:>11.1f}"
              f"{rr*100:>14.1f}%{ed:>+9.3f}")
    print(f"\n  The gap between p and breakeven is what a state would have to "
          f"supply.")

    rows = []
    for name, gs in book.items():
        D = pd.DataFrame(gs)
        rec = dict(hypothesis=name, family=name.split("/")[0])
        okp = True
        for per in ("2004-2016", "2017-2026"):
            g = D[D.period == per]
            if len(g) < 3:
                okp = False
                continue
            rec[f"n_{per}"] = int(g.n.mean())
            for col in ["direction", "expansion"] + [f"path{k}" for k in PATH_K]:
                v = g[col].to_numpy(float)
                t_, pos, nn = cross_t(v)
                rec[f"{col}_{per}"] = float(np.nanmean(v))
                rec[f"{col}_t_{per}"] = t_
                rec[f"{col}_pos_{per}"] = pos
                rec[f"{col}_mkts_{per}"] = nn
        if okp:
            rows.append(rec)
    R = pd.DataFrame(rows)

    print("\n" + "=" * 108)
    print("BEST BY TARGET, WITH BOTH PERIODS SHOWN FOR EVERY ROW")
    print("=" * 108)
    # direction's edge is GROSS - it is the move over the spread and has
    # to clear one round trip. The path and expansion targets already
    # subtract the round trip, so their bar is zero. Mixing the two in one
    # table without saying so is how a gross number gets read as a net one.
    targets = [("direction", 1.0)] + [(f"path{k}", 0.0) for k in PATH_K] \
        + [("expansion", 0.0)]
    promoted = []
    for col, bar in targets:
        c1, c2 = f"{col}_2004-2016", f"{col}_2017-2026"
        if c1 not in R or c2 not in R:
            continue
        g = R.dropna(subset=[c1, c2]).sort_values(c1, ascending=False)
        print(f"\n  {col}   (expectancy in round trips; positive means it "
              f"pays)")
        print(f"    {'hypothesis':<42}{'2004-2016':>12}{'t':>7}{'pos':>7}"
              f"{'2017-2026':>12}{'t':>7}{'pos':>7}")
        for _, r in g.head(6).iterrows():
            print(f"    {r.hypothesis:<42}{r[c1]:>+12.3f}"
                  f"{r[f'{col}_t_2004-2016']:>+7.2f}"
                  f"{int(r[f'{col}_pos_2004-2016']):>4}/"
                  f"{int(r[f'{col}_mkts_2004-2016'])}"
                  f"{r[c2]:>+12.3f}{r[f'{col}_t_2017-2026']:>+7.2f}"
                  f"{int(r[f'{col}_pos_2017-2026']):>4}/"
                  f"{int(r[f'{col}_mkts_2017-2026'])}")
        pas = g[(g[c1] > bar) & (g[c2] > bar)
                & (g[f"{col}_pos_2004-2016"] >= 6)
                & (g[f"{col}_pos_2017-2026"] >= 6)]
        print(f"    {len(pas)} of {len(g)} positive in BOTH periods on at "
              f"least 6 of 9 markets in each")
        for _, r in pas.head(5).iterrows():
            promoted.append(dict(hypothesis=r.hypothesis, target=col,
                                 p1=float(r[c1]), p2=float(r[c2]),
                                 t1=float(r[f"{col}_t_2004-2016"]),
                                 t2=float(r[f"{col}_t_2017-2026"])))

    print("\n" + "=" * 108)
    print("PROMOTED TO THE FRESH MARKET")
    print("=" * 108)
    if not promoted:
        print("  nothing passes both periods on any of the three targets")
    for p in promoted[:20]:
        print(f"  {p['target']:<10}{p['hypothesis']:<44}"
              f"{p['p1']:>+9.3f} (t {p['t1']:+.2f})  ->  "
              f"{p['p2']:>+9.3f} (t {p['t2']:+.2f})")

    out = HERE / "expanded_discovery.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        split=str(SPLIT.date()), horizon=HORIZON, path_bars=PATH_BARS,
        path_k=list(PATH_K), floor=FLOOR,
        unconditional_path=base_summary,
        hypotheses=len(R), results=R.to_dict("records"),
        promoted=promoted,
        manifest=PR.manifest(dict(split=str(SPLIT.date()), seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase4-expanded",
           "Does any state pay through a bracket's own width, or through a "
           "non-directional range target, in both halves of the sample?",
           hypothesis="expanded_three_targets",
           tools=["expanded_discovery", "discovery", "controls"],
           result=dict(hypotheses=len(R), promoted=len(promoted),
                       unconditional_path=base_summary),
           status="MEASURED",
           finding=f"{len(promoted)} hypothesis-target pairs positive in both "
                   f"periods",
           next_action="take anything promoted to USDSEK",
           started=t0)
    print(f"\n  saved -> {out.name}   {len(R)} hypotheses x 5 targets   "
          f"elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
