#!/usr/bin/env python3
"""A search with a number to beat, for the first time in this project.

WHAT CHANGED ABOUT SEARCHING

  Every previous search here looked for a rule with a positive expectancy and
  had no idea how large an effect would have to be to matter. The economics
  are now pinned: the net of edge minus cost has a single maximum at 2.68
  hours, where the round trip plus financing costs 1.105 spreads and the
  unconditional reversal delivers about 0.23.

  So the target is a factor of roughly five, and there are exactly two ways to
  get it:

    AMPLITUDE   find states where the predictable move is much larger than
                usual. This is the numerator.

    CHEAPNESS   trade only where the spread is much smaller than usual. This
                is the denominator, and it is not a second-order concern -
                gold's cheapest hour costs 6.3% of that hour's range against a
                12.5% median and a 36.5% worst, so it is worth about a factor
                of two before any search happens at all.

  A search that only looks at the numerator is ignoring half the available
  gain, and it is the half that can be measured in advance.

WHY THE HYPOTHESES ARE ORGANISED RATHER THAN LISTED

  A flat list of rules cannot tell you why it failed. Organised as family,
  mechanism, variant and parameters, a failure distribution becomes a
  statement about which LAYER is wrong: if amplitude conditioning dies
  everywhere and cheapness conditioning works, the measurement to improve is
  tradability, not structure.

  Seven families, each a different mechanism rather than a different
  threshold:

    STATE       the unconditional fade, conditioned on one measured state
                variable at its extreme. Tests whether amplitude concentrates
                anywhere at all.
    SEQUENCE    two and three bar patterns. Tests whether the information is
                in the path rather than the level.
    MULTISCALE  an hourly decision conditioned on the four-hour context.
                Tests whether the scale of the conditioner matters.
    DISLOCATION rare moves at 2, 3, 4 and 5 ATR. Tests the oldest idea in
                mean reversion - that big dislocations revert harder - with
                the sample sizes that idea actually has.
    CLOCK       session boundaries and the rollover. Tests whether the effect
                is a time-of-day phenomenon wearing a price costume.
    CROSS       another market's move as the conditioner. Tests whether the
                information is in this instrument or in the dollar.
    CHEAP       spread percentile. Attacks the denominator.

THE BAR, AND WHY IT IS NOT A P-VALUE

  1.105 spreads of gross edge. An effect that is significant and smaller than
  its own cost is an information finding, and this project already has one of
  those; a second would not change anything. Significance is still required -
  a large edge on forty trades is not a finding either - but it is the second
  test, not the first.
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
import failure_codes as FC
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
HORIZONS = (1, 2, 3)
COST_SPREADS = 1.105          # round trip plus financing at the 2.68h maximum
UNCONDITIONAL = 0.23          # what the plain fade delivers at that horizon
MIN_SIGNALS = 300


# ====================================================== state variables ====
def state_vars(P):
    """Everything a hypothesis may condition on. All strictly pre-signal."""
    c = np.asarray(P["c"], float)
    o = np.asarray(P["o"], float)
    h = np.asarray(P["h"], float)
    l = np.asarray(P["l"], float)
    A = np.asarray(P["A"], float)
    sp = np.asarray(P["spread"], float)
    idx = pd.DatetimeIndex(P["idx"])
    ret = np.concatenate([[np.nan], np.diff(c)])
    with np.errstate(invalid="ignore", divide="ignore"):
        v = {}
        v["ret_atr"] = ret / A
        v["range_atr"] = (h - l) / A
        v["body_frac"] = np.abs(c - o) / np.maximum(h - l, 1e-12)
        v["upper_wick"] = (h - np.maximum(o, c)) / np.maximum(h - l, 1e-12)
        v["lower_wick"] = (np.minimum(o, c) - l) / np.maximum(h - l, 1e-12)
        v["gap_atr"] = (o - np.concatenate([[np.nan], c[:-1]])) / A
        v["atr_price"] = A / c
        v["spread_atr"] = sp / A
        v["spread_pct"] = _pct_rank(sp)
        hi = pd.Series(h).rolling(50).max().to_numpy()
        lo = pd.Series(l).rolling(50).min().to_numpy()
        v["range_pos"] = (c - lo) / np.maximum(hi - lo, 1e-12)
        net = np.abs(c - np.concatenate([np.full(20, np.nan), c[:-20]]))
        path = pd.Series(np.abs(np.diff(c, prepend=np.nan))).rolling(20).sum()
        v["eff_ratio"] = net / np.maximum(path.to_numpy(), 1e-12)
        v["ext_atr"] = (c - pd.Series(c).rolling(20).mean().to_numpy()) / A
        run = np.zeros(len(c))
        s = np.sign(ret)
        for i in range(1, len(c)):
            run[i] = run[i - 1] + s[i] if s[i] == s[i - 1] and s[i] != 0 else s[i]
        v["run_len"] = run
    v["hour"] = idx.hour.to_numpy().astype(float)
    v["dow"] = idx.dayofweek.to_numpy().astype(float)
    for k in v:
        v[k] = np.where(np.isfinite(v[k]), v[k], np.nan)
    return v


def _pct_rank(x, win=2000):
    """Rolling percentile rank - strictly backward looking."""
    s = pd.Series(np.asarray(x, float))
    return s.rolling(win, min_periods=200).rank(pct=True).to_numpy()


# =========================================================== measurement ===
def score(P, t, d, h, cost=COST_SPREADS):
    """Signed move in spread units, from the next open to the close h on."""
    N = P["N"]
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    keep = (t >= 300) & (t + h < N - 1)
    t, d = t[keep], d[keep]
    if len(t) < 30:
        return None
    sp = ask_o[t + 1] - bid_o[t + 1]
    move = d * (c[t + h] - o[t + 1])
    ok = np.isfinite(move) & np.isfinite(sp) & (sp > 0)
    if ok.sum() < 30:
        return None
    x = move[ok] / sp[ok]
    n_eff = max(len(x) / h, 2.0)
    se = float(x.std(ddof=1) / math.sqrt(n_eff))
    return dict(n=int(ok.sum()), edge=float(x.mean()),
                t=float(x.mean() / se) if se > 0 else np.nan,
                sign_rate=float((move[ok] > 0).mean()),
                net=float(x.mean()) - cost,
                median_spread_atr=float(np.nanmedian(
                    sp[ok] / np.asarray(P["A"], float)[t[ok]])))


# ============================================================= families ====
def fam_state(P, V):
    """The plain fade, conditioned on one variable at one extreme."""
    out = []
    ret = V["ret_atr"]
    base_d = -np.sign(np.nan_to_num(ret, nan=0.0))
    for name in ("range_atr", "body_frac", "upper_wick", "lower_wick",
                 "gap_atr", "atr_price", "spread_atr", "range_pos",
                 "eff_ratio", "ext_atr", "run_len", "ret_atr"):
        v = V[name]
        fin = np.isfinite(v)
        if fin.sum() < 5000:
            continue
        q = np.nanquantile(v[fin], [0.10, 0.25, 0.75, 0.90])
        for lab, mask in (("bottom10", v <= q[0]), ("bottom25", v <= q[1]),
                          ("top25", v >= q[2]), ("top10", v >= q[3])):
            m = fin & mask & (base_d != 0)
            if m.sum() < MIN_SIGNALS:
                continue
            out.append((f"STATE/{name}/{lab}", np.where(m)[0],
                        base_d[m].astype(float)))
    return out


def fam_sequence(P, V):
    """Two and three bar shapes - is the information in the path?"""
    out = []
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    rng = V["range_atr"]
    r1, r2 = np.roll(r, 1), np.roll(r, 2)
    s1, s2 = np.roll(s, 1), np.roll(s, 2)
    g1 = np.roll(rng, 1)
    pats = {
        "two-same-fade": (s != 0) & (s == s1),
        "two-opposite-fade": (s != 0) & (s1 != 0) & (s != s1),
        "three-same-fade": (s != 0) & (s == s1) & (s == s2),
        "expand-after-quiet": (rng > 1.5) & (g1 < 0.7),
        "contract-after-wide": (rng < 0.7) & (g1 > 1.5),
        "outside-bar": (rng > 1.3) & (np.abs(r) > 0.8),
        "reversal-bar": (s != 0) & (s1 != 0) & (s != s1) & (np.abs(r) > 1.0),
        "exhaustion": (np.abs(r) > 1.2) & (np.abs(r1) > 1.2) & (s == s1),
    }
    for lab, m in pats.items():
        m = np.nan_to_num(m, nan=False) & np.isfinite(r)
        m[:300] = False
        if m.sum() < MIN_SIGNALS:
            continue
        d = -s[m]
        keep = d != 0
        out.append((f"SEQUENCE/{lab}/fade", np.where(m)[0][keep],
                    d[keep].astype(float)))
        out.append((f"SEQUENCE/{lab}/follow", np.where(m)[0][keep],
                    -d[keep].astype(float)))
    return out


def fam_multiscale(P, V):
    """An hourly decision conditioned on the four-hour context."""
    out = []
    c = pd.Series(np.asarray(P["c"], float))
    idx = pd.DatetimeIndex(P["idx"])
    h4 = c.groupby(idx.floor("4h")).transform("first").to_numpy()
    h4_prev = pd.Series(h4).shift(4).to_numpy()
    h4_dir = np.sign(np.nan_to_num(h4 - h4_prev, nan=0.0))
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    pos = V["range_pos"]
    for lab, m in (("with-h4", (s != 0) & (s == h4_dir)),
                   ("against-h4", (s != 0) & (h4_dir != 0) & (s != h4_dir)),
                   ("h4-up-low-in-range", (h4_dir > 0) & (pos < 0.3)),
                   ("h4-down-high-in-range", (h4_dir < 0) & (pos > 0.7))):
        m = np.nan_to_num(m, nan=False)
        m[:300] = False
        if m.sum() < MIN_SIGNALS:
            continue
        for tag, d in (("fade", -s[m]), ("follow", s[m])):
            keep = d != 0
            if keep.sum() < MIN_SIGNALS:
                continue
            out.append((f"MULTISCALE/{lab}/{tag}",
                        np.where(m)[0][keep], d[keep].astype(float)))
    return out


def fam_dislocation(P, V):
    """Rare moves. The oldest idea in mean reversion, at its real sample size."""
    out = []
    r = V["ret_atr"]
    g = V["gap_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    sg = np.sign(np.nan_to_num(g, nan=0.0))
    for k in (1.5, 2.0, 3.0, 4.0, 5.0):
        m = np.isfinite(r) & (np.abs(r) > k)
        m[:300] = False
        if m.sum() >= 100:
            out.append((f"DISLOCATION/move/{k}atr-fade",
                        np.where(m)[0], -s[m].astype(float)))
        mg = np.isfinite(g) & (np.abs(g) > k / 2)
        mg[:300] = False
        if mg.sum() >= 100:
            out.append((f"DISLOCATION/gap/{k/2}atr-fade",
                        np.where(mg)[0], -sg[mg].astype(float)))
    return out


def fam_clock(P, V):
    """Is the effect a time-of-day phenomenon in a price costume?"""
    out = []
    hr = V["hour"]
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    windows = {"london-open": (7, 9), "ny-open": (13, 15),
               "london-close": (16, 18), "rollover": (20, 23),
               "asia": (0, 6), "overlap": (13, 17)}
    for lab, (a, b) in windows.items():
        m = np.isfinite(hr) & (hr >= a) & (hr < b) & (s != 0)
        m[:300] = False
        if m.sum() < MIN_SIGNALS:
            continue
        out.append((f"CLOCK/{lab}/fade", np.where(m)[0], -s[m].astype(float)))
        out.append((f"CLOCK/{lab}/follow", np.where(m)[0], s[m].astype(float)))
    return out


def fam_cheap(P, V):
    """Attack the denominator. Trade only where the quote is cheap."""
    out = []
    pr = V["spread_pct"]
    sa = V["spread_atr"]
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    for lab, m in (("spread-pct-bottom10", pr <= 0.10),
                   ("spread-pct-bottom25", pr <= 0.25),
                   ("spread-atr-bottom10", sa <= np.nanquantile(
                       sa[np.isfinite(sa)], 0.10) if np.isfinite(sa).any()
                       else np.zeros(len(sa), bool)),
                   ("spread-atr-bottom25", sa <= np.nanquantile(
                       sa[np.isfinite(sa)], 0.25) if np.isfinite(sa).any()
                       else np.zeros(len(sa), bool))):
        m = np.nan_to_num(m, nan=False) & (s != 0)
        m[:300] = False
        if m.sum() < MIN_SIGNALS:
            continue
        out.append((f"CHEAP/{lab}/fade", np.where(m)[0], -s[m].astype(float)))
        # the two levers together: cheap quote AND a large move to fade
        big = np.abs(r) > 1.5
        m2 = m & np.nan_to_num(big, nan=False)
        if m2.sum() >= 100:
            out.append((f"CHEAP/{lab}+dislocation/fade",
                        np.where(m2)[0], -s[m2].astype(float)))
    return out


def fam_cross(P, V, ref=None):
    """Another market's move as the conditioner.

    The question is whether the information is in this instrument or in the
    dollar. `ref` is a series of the reference market's own returns over ATR,
    already aligned to this market's index by timestamp - never by position,
    because the two series do not have the same bars once flat hours are
    removed, and aligning by position would silently shift one against the
    other by a growing offset."""
    if ref is None:
        return []
    out = []
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    sr = np.sign(np.nan_to_num(ref, nan=0.0))
    big_ref = np.isfinite(ref) & (np.abs(ref) > 1.0)
    for lab, m in (("agrees", (s != 0) & (s == sr)),
                   ("disagrees", (s != 0) & (sr != 0) & (s != sr)),
                   ("ref-quiet", np.isfinite(ref) & (np.abs(ref) < 0.3)
                    & (s != 0)),
                   ("ref-dislocated", big_ref & (s != 0))):
        m = np.nan_to_num(m, nan=False)
        m[:300] = False
        if m.sum() < MIN_SIGNALS:
            continue
        out.append((f"CROSS/{lab}/fade", np.where(m)[0], -s[m].astype(float)))
        out.append((f"CROSS/{lab}/follow", np.where(m)[0], s[m].astype(float)))
    return out


def fam_amplitude(P, V):
    """The winning shape's own family, swept - so the pilot reports a surface
    rather than a point, and a spike cannot be mistaken for a plateau."""
    out = []
    r = V["ret_atr"]
    rng = V["range_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    g1 = np.roll(rng, 1)
    for rt in (1.2, 1.5, 1.8, 2.2):
        for pt in (0.4, 0.5, 0.6, 0.7, 0.9):
            m = np.nan_to_num((rng > rt) & (g1 < pt), nan=False)
            m &= np.isfinite(r) & (s != 0)
            m[:300] = False
            if m.sum() < 150:
                continue
            out.append((f"AMPLITUDE/expand-after-quiet/{rt}-{pt}",
                        np.where(m)[0], -s[m].astype(float)))
    # the same shape with the cheap-quote filter stacked on top: the two
    # levers the economics says are the only ones available
    sa = V["spread_atr"]
    fin = np.isfinite(sa)
    if fin.sum() > 5000:
        cut = np.nanquantile(sa[fin], 0.33)
        for rt in (1.2, 1.5, 1.8):
            m = np.nan_to_num((rng > rt) & (g1 < 0.6) & (sa <= cut), nan=False)
            m &= np.isfinite(r) & (s != 0)
            m[:300] = False
            if m.sum() < 150:
                continue
            out.append((f"AMPLITUDE/expand-quiet-cheap/{rt}",
                        np.where(m)[0], -s[m].astype(float)))
    return out


FAMILIES = (("STATE", fam_state), ("SEQUENCE", fam_sequence),
            ("MULTISCALE", fam_multiscale), ("DISLOCATION", fam_dislocation),
            ("CLOCK", fam_clock), ("CHEAP", fam_cheap),
            ("AMPLITUDE", fam_amplitude))


def cross_t(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--controls", default="C1,C7")
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]
    H = a.horizon
    levels = [s.strip() for s in a.controls.split(",") if s.strip()]

    print("PILOT - a search with a number to beat")
    print("=" * 104)
    print(__doc__.split("WHAT CHANGED ABOUT SEARCHING")[1]
          .split("WHY THE HYPOTHESES ARE ORGANISED")[0])
    print(f"  bar to clear: {COST_SPREADS} spreads gross, against an "
          f"unconditional {UNCONDITIONAL}\n")

    # the reference series for the cross-market family: EURUSD's own move
    # over its ATR, carried as a timestamp-indexed Series so it can be
    # aligned to each market by time rather than by bar position
    ref_df = load_bidask_h1("EURUSD")
    ref_s = None
    if ref_df is not None:
        Pr = X.prep(ref_df, 60)
        Vr = state_vars(Pr)
        ref_s = pd.Series(Vr["ret_atr"], index=pd.DatetimeIndex(Pr["idx"]))

    per = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        V = state_vars(P)
        cands = []
        ref = None
        if ref_s is not None and sym != "EURUSD":
            ref = ref_s.reindex(pd.DatetimeIndex(P["idx"])).to_numpy(float)
        if ref is not None:
            try:
                cands.extend(fam_cross(P, V, ref))
            except Exception as e:
                print(f"    {sym} CROSS error {type(e).__name__}: {e}")
        for _, fn in FAMILIES:
            try:
                cands.extend(fn(P, V))
            except Exception as e:
                print(f"    {sym} family error {type(e).__name__}: {e}")
        for name, t, d in cands:
            s = score(P, t, d, H)
            if s is None:
                continue
            per.setdefault(name, []).append(dict(symbol=sym, **s))
        print(f"  {sym:<9}{len(cands):>5} hypotheses  {time.time()-t0:>6.0f}s",
              flush=True)

    if not per:
        print("  nothing measured")
        return

    rows = []
    for name, gs in per.items():
        if len(gs) < 3:
            continue
        e = np.array([g["edge"] for g in gs], float)
        t, pos, n = cross_t(e)
        rows.append(dict(
            hypothesis=name, family=name.split("/")[0], markets=n,
            edge=float(np.nanmean(e)), t=t, positive=pos,
            n_total=int(sum(g["n"] for g in gs)),
            n_per_market=int(np.mean([g["n"] for g in gs])),
            sign_rate=float(np.nanmean([g["sign_rate"] for g in gs])),
            spread_atr=float(np.nanmean([g["median_spread_atr"] for g in gs])),
            net=float(np.nanmean(e)) - COST_SPREADS))
    R = pd.DataFrame(rows).sort_values("edge", ascending=False)

    print("\n" + "=" * 104)
    print(f"TOP 20 BY GROSS EDGE, horizon {H}h, bar {COST_SPREADS} spreads")
    print("=" * 104)
    print(f"  {'hypothesis':<44}{'mkts':>5}{'n/mkt':>8}{'edge':>9}"
          f"{'t':>8}{'pos':>7}{'sprd/ATR':>10}{'net':>9}")
    for _, r in R.head(20).iterrows():
        print(f"  {r.hypothesis:<44}{r.markets:>5}{r.n_per_market:>8,}"
              f"{r.edge:>+9.3f}{r.t:>+8.2f}{r.positive:>4}/{r.markets}"
              f"{r.spread_atr:>10.3f}{r.net:>+9.3f}")

    print("\n" + "=" * 104)
    print("BY FAMILY - where amplitude concentrates")
    print("=" * 104)
    print(f"  {'family':<14}{'hyps':>6}{'mean edge':>12}{'best':>10}"
          f"{'best t':>9}{'mean spread/ATR':>18}")
    for fam in R.family.unique():
        g = R[R.family == fam]
        b = g.loc[g.edge.idxmax()]
        print(f"  {fam:<14}{len(g):>6}{g.edge.mean():>+12.3f}"
              f"{b.edge:>+10.3f}{b.t:>+9.2f}{g.spread_atr.mean():>18.3f}")

    clear = R[(R.edge > COST_SPREADS) & (R.positive >= 6) & (R.t > 3.0)]
    print(f"\n  {len(clear)} of {len(R)} hypotheses exceed the "
          f"{COST_SPREADS}-spread bar with t>3 on at least 6 of 9")
    if len(clear):
        for _, r in clear.iterrows():
            print(f"    {r.hypothesis:<44}{r.edge:+.3f}  t {r.t:+.2f}  "
                  f"{r.positive}/{r.markets}  n/mkt {r.n_per_market:,}")

    out = HERE / "discovery_pilot.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        horizon=H, cost_spreads=COST_SPREADS, hypotheses=len(R),
        results=R.to_dict("records"), per_market={k: v for k, v in per.items()},
        cleared=clear.hypothesis.tolist(),
        manifest=PR.manifest(dict(horizon=H, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase2-pilot",
           "Does any conditioning state lift the predictable move to a "
           "multiple of its own cost?",
           hypothesis="pilot_conditional_amplitude",
           tools=["discovery", "failure_codes"],
           result=dict(hypotheses=len(R), cleared=len(clear),
                       best=R.iloc[0].to_dict() if len(R) else None),
           status="MEASURED",
           finding=f"{len(clear)} of {len(R)} clear {COST_SPREADS} spreads",
           next_action="classify failures and aggregate the distribution",
           started=t0)
    print(f"\n  saved -> {out.name}   {len(R)} hypotheses   "
          f"elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
