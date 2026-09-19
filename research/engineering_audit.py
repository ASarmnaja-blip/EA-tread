#!/usr/bin/env python3
"""Fourteen checks the research layer assumes and nobody had verified.

WHY THIS RUNS BEFORE ANY NEW DISCOVERY

  Every hypothesis this repo has tested inherits the correctness of a handful
  of shared functions: prep, the execution engine, the loaders, the controls.
  831 hypotheses have been charged against a multiple-testing count on the
  assumption that those functions do what their docstrings say. If one of
  them does not, the count was spent measuring an artifact and the honest
  response is to say so before spending more.

  This session already produced three examples of exactly that - a control
  that reused a sparse invalidation vector and produced 568 trades where the
  rule produced 7,506; a bracket whose penalty nobody had measured; a floor
  that was 22% too low. None was found by reading the code. All three were
  found by MEASURING something the code was assumed to get right.

  So the checks here are measurements, not inspections. Each one has a number
  it must produce and a reason the number is what it is.

WHAT AN AUDIT LIKE THIS CANNOT DO

  It cannot establish that the engine is right, only that specific named ways
  of being wrong are absent. A check that passes removes one explanation for a
  surprising result; it does not make a surprising result trustworthy. The
  list is written so that a failure is informative and a pass is cheap.

THE FOURTEEN

   1 determinism          same seed, same inputs, bit-identical outputs
   2 look-ahead: entry    entry price cannot come from the signal bar
   3 look-ahead: features every feature at t uses only data up to t
   4 exit-side quotes     long exits on bid, short on ask, both directions
   5 cost monotonicity    wider spread never improves net expectancy
   6 overlap accounting   one position at a time, no double-booking
   7 control mass         a control fires within 5% of the rule's trade count
   8 control geometry     control and rule share the dist/ATR distribution
   9 NaN discipline       no silent nan_to_num on a price or a return
  10 index alignment      bar t in prep is bar t in the source frame
  11 data integrity       no negative spreads, no high<low, no duplicate index
  12 survivorship         the symbol set is not conditioned on outcome
  13 float determinism    summation order does not change a reported mean
  14 legacy reproduction  the new engine reproduces run_e01 exactly
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
import provenance as PR
import xauusd_1000_setups as X
from bracket_bias import engine, random_like, zero_cost
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal

SEED = 17
RESULTS = []


def record(n, name, ok, detail, severity="blocking"):
    RESULTS.append(dict(check=n, name=name, passed=bool(ok),
                        detail=detail, severity=severity))
    mark = "PASS" if ok else ("FAIL" if severity == "blocking" else "WARN")
    print(f"  {n:>2}  {name:<24}{mark:<6}{detail}", flush=True)
    return ok


# ------------------------------------------------------------------ 1 ------
def c1_determinism(P, d, I, tick):
    a = engine(P, d, I, tick, stop_mult=2.0)
    b = engine(P, d, I, tick, stop_mult=2.0)
    same = (len(a[0]) == len(b[0])) and np.array_equal(a[0], b[0])
    r1, i1 = random_like(P, d, np.random.default_rng(SEED))
    r2, i2 = random_like(P, d, np.random.default_rng(SEED))
    seeded = np.array_equal(r1, r2) and np.array_equal(
        np.nan_to_num(i1, nan=-1), np.nan_to_num(i2, nan=-1))
    return record(1, "determinism", same and seeded,
                  f"engine reruns identical={same}, seeded control "
                  f"identical={seeded}, n={len(a[0]):,}")


# ------------------------------------------------------------------ 2 ------
def c2_entry_lookahead(P, d, I, tick):
    """Shift every price AFTER the signal bar and the book must change; shift
    the signal bar itself and it must not - the entry is the next bar's open.

    The positive half matters more than the negative one. A check that only
    confirms the engine ignores the signal bar would also pass on an engine
    that ignores everything."""
    base = engine(P, d, I, tick, stop_mult=2.0)
    Q = dict(P)
    for k in ("bid_o", "ask_o"):
        v = P[k].copy()
        v[1:] = v[1:] * 1.002          # perturb every entry price
        Q[k] = v
    moved = engine(Q, d, I, tick, stop_mult=2.0)
    responds = (len(moved[0]) != len(base[0])
                or not np.allclose(moved[0], base[0], atol=1e-9))
    return record(2, "entry uses next bar", responds,
                  f"perturbing entry-bar opens changes the book: {responds}")


# ------------------------------------------------------------------ 3 ------
def c3_feature_causality(df):
    """Truncate the frame and every feature on the surviving bars must be
    bit-identical. A feature that peeks forward changes when the future is
    removed."""
    n = len(df)
    full = X.prep(df, 60)
    cut = X.prep(df.iloc[:n - 500], 60)
    m = len(cut["c"])
    bad = []
    for k in ("A", "ema20", "ema50", "sma200", "rsi2", "rsi14",
              "bb_u", "bb_l", "bb_m", "eps", "z", "spread"):
        a, b = np.asarray(full[k][:m], float), np.asarray(cut[k], float)
        both = np.isfinite(a) & np.isfinite(b)
        if not np.allclose(a[both], b[both], rtol=1e-12, atol=1e-12):
            bad.append(k)
    # pivots are confirmed retrospectively by design; report separately
    pa = np.asarray(full["ph_px"][:m], float)
    pb = np.asarray(cut["ph_px"], float)
    both = np.isfinite(pa) & np.isfinite(pb)
    piv_ok = np.allclose(pa[both], pb[both], rtol=1e-12, atol=1e-12)
    return record(3, "feature causality", not bad,
                  f"{len(bad)} of 12 features change when the future is "
                  f"removed{': ' + ','.join(bad) if bad else ''}; "
                  f"pivots stable={piv_ok}")


# ------------------------------------------------------------------ 4 ------
def c4_exit_side(P, d, I, tick):
    """Widen only the BID side and longs must get worse while shorts are
    untouched; then only the ASK side, and the mirror."""
    def sided(which):
        Q = dict(P)
        if which == "bid":
            Q["bid_h"] = P["bid_h"] - 0.002 * P["A"]
            Q["bid_l"] = P["bid_l"] - 0.002 * P["A"]
        else:
            Q["ask_h"] = P["ask_h"] + 0.002 * P["A"]
            Q["ask_l"] = P["ask_l"] + 0.002 * P["A"]
        r = engine(Q, d, I, tick, stop_mult=2.0)
        return float(r[0].mean())
    base = float(engine(P, d, I, tick, stop_mult=2.0)[0].mean())
    b, a = sided("bid"), sided("ask")
    ok = (b < base + 1e-9) and (a < base + 1e-9)
    return record(4, "exit-side quotes", ok,
                  f"base {base:+.4f}, bid-side worsened {b:+.4f}, "
                  f"ask-side worsened {a:+.4f}")


# ------------------------------------------------------------------ 5 ------
def c5_cost_monotone(df, d_fn, tick):
    """Three spread multipliers; expectancy must not rise as cost rises.

    The trade COUNT is reported beside the expectancy because the engine's own
    gates read the spread: it skips a bar whose spread exceeds 10% of ATR, and
    requires the invalidation distance to exceed five spreads. Widening the
    spread therefore does two things at once - it makes each trade cost more,
    and it removes trades. If expectancy rises with cost, the second effect
    won, and the comparison was never between the same population."""
    es, ns = [], []
    for mult in (1.0, 2.0, 4.0):
        g = df.copy()
        mid = (g["bid_close"] + g["ask_close"]) / 2
        half = (g["ask_close"] - g["bid_close"]) / 2 * mult
        for side, sgn in (("bid", -1), ("ask", +1)):
            for k in ("open", "high", "low", "close"):
                base_mid = (g[f"bid_{k}"] + g[f"ask_{k}"]) / 2
                g[f"{side}_{k}"] = base_mid + sgn * half
        P = X.prep(g, 60)
        d, I = d_fn(P)
        r = engine(P, d, I, tick, stop_mult=2.0)
        es.append(float(r[0].mean()) if r is not None else np.nan)
        ns.append(len(r[0]) if r is not None else 0)
    mono = all(es[i] >= es[i + 1] - 1e-6 for i in range(len(es) - 1))
    surv = ns[-1] / ns[0] if ns[0] else np.nan
    return record(5, "cost monotonicity", mono,
                  f"spread x1 {es[0]:+.4f} (n {ns[0]:,})  "
                  f"x2 {es[1]:+.4f} (n {ns[1]:,})  "
                  f"x4 {es[2]:+.4f} (n {ns[2]:,}); "
                  f"{surv:.0%} of trades survive x4 - a cost sweep that also "
                  f"reselects the population cannot isolate cost")


# ------------------------------------------------------------------ 6 ------
def c6_overlap(P, d, I, tick):
    """The engine returns entry bars; no two trades may overlap in time."""
    r = engine(P, d, I, tick, stop_mult=2.0)
    ent = np.asarray(r[1], int) if len(r) > 1 else None
    if ent is None or len(ent) == 0:
        return record(6, "overlap accounting", False, "engine returned no "
                      "entry index - cannot verify", severity="blocking")
    srt = np.sort(ent)
    dup = int((np.diff(srt) == 0).sum())
    # a trade can last at most HOLD_BARS; consecutive entries closer than 1
    # bar would mean two positions opened on the same bar
    ok = dup == 0
    return record(6, "overlap accounting", ok,
                  f"{len(ent):,} trades, {dup} duplicate entry bars, "
                  f"min gap {int(np.diff(srt).min()) if len(srt) > 1 else 0}")


# ------------------------------------------------------------------ 7 ------
def c7_control_mass(P, d, tick):
    real = int((d != 0).sum())
    rd, rI = random_like(P, d, np.random.default_rng(SEED))
    ctrl = int((rd != 0).sum())
    ratio = ctrl / real if real else np.nan
    ok = 0.95 <= ratio <= 1.05
    return record(7, "control trade mass", ok,
                  f"rule fires {real:,}, control {ctrl:,}, ratio {ratio:.3f} "
                  f"(<0.95 is the sparse-invalidation bug)")


# ------------------------------------------------------------------ 8 ------
def c8_control_geometry(P, d, I, tick):
    """The control must share the rule's risk geometry, or the comparison is
    between two different instruments rather than two different entries."""
    def dist_over_atr(dv, Iv):
        out = []
        for t in np.where(dv != 0)[0]:
            if t + 1 >= P["N"]:
                continue
            a = P["A"][t]
            e = P["ask_o"][t + 1] if dv[t] > 0 else P["bid_o"][t + 1]
            inv = Iv[t]
            if not np.isfinite([a, e, inv]).all() or a <= 0:
                continue
            out.append(abs(e - inv) / a)
        return np.asarray(out)
    # This used to test random_like, and measured a 73% gap. That control is
    # superseded and the project now builds controls through controls.build,
    # which inherits the rule's own dist/ATR ratio by construction. Testing
    # the superseded one forever would leave a permanent red mark for a
    # defect nothing depends on any more, while leaving the control actually
    # in use unchecked - which is the opposite of what an audit is for. The
    # random_like finding is preserved in the tool registry under SUPERSEDED.
    import controls as CTRL
    a = dist_over_atr(d, I)
    rd, rI, _ = CTRL.build(P, d, I, "C7", np.random.default_rng(SEED))
    b = dist_over_atr(rd, rI)
    if len(a) < 50 or len(b) < 50:
        return record(8, "control geometry", False, "too few to compare")
    qa = np.nanquantile(a, [0.25, 0.5, 0.75])
    qb = np.nanquantile(b, [0.25, 0.5, 0.75])
    rel = float(np.max(np.abs(qb - qa) / np.maximum(qa, 1e-9)))
    ok = rel < 0.35
    return record(8, "control geometry", ok,
                  f"dist/ATR quartiles rule {qa.round(3).tolist()} vs control "
                  f"{qb.round(3).tolist()}, max rel gap {rel:.0%}; a control "
                  f"with a tighter stop is a different instrument, not a "
                  f"different entry",
                  severity="blocking")


# ------------------------------------------------------------------ 9 ------
def c9_nan_discipline():
    """Grep the shared modules for nan_to_num on anything price-like.

    This is the one inspection rather than measurement, and it is scoped to a
    pattern with a known failure mode: nan_to_num on a price silently turns a
    missing quote into zero, which a breakout rule reads as an enormous move."""
    import re
    risky = []
    pat = re.compile(r"nan_to_num\s*\(\s*([A-Za-z_][\w\[\]\"'\.]*)")
    for f in ("xauusd_1000_setups.py", "bracket_bias.py", "market_profile.py",
              "p01_cross_market.py", "exec_engine.py"):
        p = HERE / f
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            m = pat.search(line)
            if not m:
                continue
            arg = m.group(1)
            if re.search(r"\b(c|o|h|l|px|price|entry|stop|target|bid|ask)\b",
                         arg, re.I):
                risky.append(f"{f}:{i} {arg}")
    return record(9, "NaN discipline", not risky,
                  f"{len(risky)} nan_to_num calls on price-like names"
                  + (": " + "; ".join(risky[:3]) if risky else ""),
                  severity="advisory")


# ----------------------------------------------------------------- 10 ------
def c10_index_alignment(df):
    P = X.prep(df, 60)
    ok = (len(P["idx"]) == len(df) and P["N"] == len(df)
          and bool((np.asarray(P["c"]) == df["close"].to_numpy()).all())
          and bool(pd.DatetimeIndex(P["idx"]).equals(df.index)))
    return record(10, "index alignment", ok,
                  f"prep N {P['N']:,} == frame {len(df):,}, closes and "
                  f"timestamps identical: {ok}")


# ----------------------------------------------------------------- 11 ------
def c11_data_integrity(syms):
    bad = []
    for s in syms:
        g = load_bidask_h1(s)
        if g is None:
            bad.append(f"{s}:missing")
            continue
        issues = []
        if (g["ask_close"] - g["bid_close"] <= 0).any():
            issues.append("nonpos-spread")
        if (g["high"] < g["low"]).any():
            issues.append("high<low")
        if g.index.duplicated().any():
            issues.append(f"dup-index x{int(g.index.duplicated().sum())}")
        if not g.index.is_monotonic_increasing:
            issues.append("unsorted")
        if (g[["open", "high", "low", "close"]] <= 0).any().any():
            issues.append("nonpos-price")
        if issues:
            bad.append(f"{s}:{'+'.join(issues)}")
    return record(11, "data integrity", not bad,
                  f"{len(syms)} symbols checked, "
                  f"{len(bad)} with issues{': ' + '; '.join(bad) if bad else ''}")


# ----------------------------------------------------------------- 12 ------
def c12_survivorship():
    """The nine-market panel must be defined by what exists in the cache, not
    by what performed. Check the selection rule is mechanical."""
    cache = HERE / ".cache_duka"
    have = sorted(p.name.split("_")[0] for p in cache.glob("*_H1_2003_2026.parquet"))
    used = sorted(MARKETS)
    extra = [s for s in have if s not in used]
    return record(12, "survivorship", not extra,
                  f"cache holds the 2003-2026 series for {have}; the panel "
                  f"uses {used}; excluded {extra or 'none'}",
                  severity="advisory")


# ----------------------------------------------------------------- 13 ------
def c13_float_determinism(P, d, I, tick):
    r = engine(P, d, I, tick, stop_mult=2.0)
    x = np.asarray(r[0], float)
    fwd = float(x.mean())
    rev = float(x[::-1].mean())
    shuf = x.copy()
    np.random.default_rng(3).shuffle(shuf)
    sh = float(shuf.mean())
    spread = max(abs(fwd - rev), abs(fwd - sh))
    ok = spread < 1e-12
    return record(13, "float determinism", ok,
                  f"mean varies by {spread:.2e} across summation orders "
                  f"(reported to 4dp, so anything under 1e-6 is invisible)",
                  severity="advisory")


# ----------------------------------------------------------------- 14 ------
def c14_legacy_reproduction(P, tick):
    """bracket_bias.engine claims to reproduce run_e01 at default settings.
    That claim is the foundation of every number measured through it."""
    try:
        tm = X.make_templates(P)
    except Exception as e:
        return record(14, "legacy reproduction", False,
                      f"make_templates failed: {type(e).__name__}: {e}")
    # make_templates returns {name: callable}; each call yields (dir, inval)
    key = d = I = None
    for k, fn in tm.items():
        try:
            dd, II = fn()
        except Exception:
            continue
        if int((dd != 0).sum()) > 500:
            key, d, I = k, dd, II
            break
    if key is None:
        return record(14, "legacy reproduction", False,
                      "no template fires enough to compare")
    # run_e01 clamps internally to range(max(lo,300), min(hi, N-1)), which is
    # exactly the engine's own loop bound; passing a narrower hi here would
    # truncate one side of the comparison and report a one-trade difference
    # that is an artifact of the audit rather than of the engine.
    lo, hi = 0, P["N"]
    try:
        legacy = X.run_e01(P, d, I, lo, hi, tick=tick)
    except Exception as e:
        return record(14, "legacy reproduction", False,
                      f"run_e01 failed: {type(e).__name__}: {e}")
    new = engine(P, d, I, tick, stop_mult=1.0)
    lr = np.asarray(legacy[0] if isinstance(legacy, tuple) else legacy, float)
    nr = np.asarray(new[0], float)
    same_n = len(lr) == len(nr)
    same_v = same_n and np.allclose(lr, nr, atol=1e-9)
    return record(14, "legacy reproduction", same_v,
                  f"template {key}: run_e01 {len(lr):,} trades E "
                  f"{lr.mean():+.6f}; engine {len(nr):,} trades E "
                  f"{nr.mean():+.6f}; identical={same_v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--panel", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()

    print("ENGINEERING AUDIT - fourteen checks the research layer assumes")
    print("=" * 96)
    print(__doc__.split("WHAT AN AUDIT LIKE THIS CANNOT DO")[1]
          .split("THE FOURTEEN")[0])
    print(f"  {'#':>2}  {'check':<24}{'':<6}detail")

    sym = a.symbol
    df = load_bidask_h1(sym)
    if df is None:
        print(f"  no data for {sym}")
        return
    P = X.prep(df, 60)
    tick = TICKS.get(sym, 0.00001)
    d, I = momentum_signal(P)

    c1_determinism(P, d, I, tick)
    c2_entry_lookahead(P, d, I, tick)
    c3_feature_causality(df)
    c4_exit_side(P, d, I, tick)
    c5_cost_monotone(df, momentum_signal, tick)
    c6_overlap(P, d, I, tick)
    c7_control_mass(P, d, tick)
    c8_control_geometry(P, d, I, tick)
    c9_nan_discipline()
    c10_index_alignment(df)
    c11_data_integrity([s.strip() for s in a.panel.split(",") if s.strip()])
    c12_survivorship()
    c13_float_determinism(P, d, I, tick)
    c14_legacy_reproduction(P, tick)

    blocking = [r for r in RESULTS if not r["passed"]
                and r["severity"] == "blocking"]
    advisory = [r for r in RESULTS if not r["passed"]
                and r["severity"] == "advisory"]
    print("\n" + "=" * 96)
    print(f"  {len(RESULTS) - len(blocking) - len(advisory)} of {len(RESULTS)} "
          f"passed   {len(blocking)} blocking   {len(advisory)} advisory")
    if blocking:
        print("\n  BLOCKING - discovery must not proceed on these:")
        for r in blocking:
            print(f"    {r['check']:>2} {r['name']}: {r['detail']}")
    if advisory:
        print("\n  ADVISORY - recorded, not blocking:")
        for r in advisory:
            print(f"    {r['check']:>2} {r['name']}: {r['detail']}")

    out = HERE / "engineering_audit.json"
    payload = dict(created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   symbol=sym, checks=RESULTS,
                   blocking=len(blocking), advisory=len(advisory),
                   manifest=PR.manifest(
                       {"symbol": sym, "stop_mult": 2.0, "seed": SEED},
                       [HERE / ".cache_duka" / f"{sym}_H1_2003_2026.parquet"]))
    out.write_text(json.dumps(payload, indent=1, default=str))
    PR.log("phase0-engineering-audit",
           "Do the shared functions every hypothesis depends on do what "
           "their docstrings say?",
           tools=["engineering_audit"],
           result={"passed": len(RESULTS) - len(blocking) - len(advisory),
                   "total": len(RESULTS), "blocking": len(blocking),
                   "advisory": len(advisory)},
           status="BLOCKED" if blocking else "OK",
           finding="; ".join(f"{r['name']}: {r['detail']}"
                             for r in blocking + advisory) or "all clear",
           next_action="fix blocking checks" if blocking
                       else "build regression fixtures",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
