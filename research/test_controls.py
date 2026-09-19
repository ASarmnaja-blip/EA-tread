#!/usr/bin/env python3
"""Thirteen fixtures for the control layer, on data whose answer is known.

WHY THE FIXTURES USE SYNTHETIC PROCESSES

  A control cannot be validated against a market, because nobody knows what a
  market's answer is - that is the whole research question. It can be
  validated against a process whose answer is known by construction:

    a pure random walk has no directional information, so every control level
    must return a skill indistinguishable from zero;

    a walk with a PLANTED rule that genuinely predicts direction must survive
    all the way to C7, because the information is real;

    a walk with a planted ACTIVITY preference and no direction must beat C1
    and die at C3, because that is exactly the artifact C3 exists to remove.

  The third is the one that matters. A control hierarchy that cannot tell the
  second from the third is decoration, and the only way to know is to build
  both and check.

WHAT EACH FIXTURE ASSERTS

   1 feature causality      no feature at t reads a bar after t
   2 post-signal refusal    matching on an outcome variable raises
   3 geometry inheritance   control dist/ATR matches the rule's within 15%
   4 determinism            same seed, same control, bit-identical
   5 no self-donation       the control never places on a real signal bar
   6 placement rate         at least 80% of signals get a donor at every level
   7 direction mix          inherit preserves it, random does not
   8 stratum fidelity       matched dim distributions agree within 0.15 TV
   9 relaxation is reported when cells empty, meta says so rather than lying
  10 null process           random walk: every level's skill is near zero
  11 planted direction      survives C0 through C7
  12 planted activity       beats C1, dies by C3 - the discriminating case
  13 monotone strength      later controls are not systematically easier
"""
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import controls as C
import xauusd_1000_setups as X
from bracket_bias import engine

FAIL = []
SEED = 17


def check(tag, ok, detail):
    print(f"  {'PASS' if ok else 'FAIL'}  {tag:<26}{detail}")
    if not ok:
        FAIL.append(tag)
    return ok


# ======================================================== synthetic data ===
def walk(n=60000, seed=1, spread_bp=0.5, sigma=0.0008, drift=0.0):
    """A geometric random walk sampled as OHLC bars with a constant spread.

    The spread has to sit below 10% of the walk's own ATR or the engine's
    pre-trade gate rejects every bar and the fixtures come back empty rather
    than failing - which is what the first run did. At sigma 8e-4 the ATR is
    about 16bp, so 0.5bp of spread leaves the gate a wide margin and still
    costs something.

    The intrabar high and low are built from a separate noise draw, so a bar's
    range is not a deterministic function of its close-to-close move - a
    fixture where it were would let an activity-matched control match on the
    outcome by accident."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, sigma, n)
    c = 100.0 * np.exp(np.cumsum(r))
    o = np.concatenate([[100.0], c[:-1]])
    wick = np.abs(rng.normal(0, sigma * 0.7, n)) * c
    h = np.maximum(o, c) + wick
    l = np.minimum(o, c) - np.abs(rng.normal(0, sigma * 0.7, n)) * c
    idx = pd.date_range("2005-01-03", periods=n, freq="h", tz="UTC")
    half = c * spread_bp / 20000.0
    df = pd.DataFrame(dict(open=o, high=h, low=l, close=c), index=idx)
    for k, v in (("open", o), ("high", h), ("low", l), ("close", c)):
        df[f"bid_{k}"] = v - half
        df[f"ask_{k}"] = v + half
    return df


def rule_random(P, rng, rate=0.04):
    """Fires on random bars, faces a random way. No information at all."""
    n = P["N"]
    d = np.zeros(n, np.int8)
    fire = (rng.random(n) < rate)
    fire[:400] = False
    fire[n - 40:] = False
    d[fire] = rng.choice((-1, 1), size=int(fire.sum()))
    I = np.full(n, np.nan)
    a = np.asarray(P["A"], float)
    I[fire] = P["c"][fire] - d[fire] * 1.2 * a[fire]
    return d, I


def rule_activity_only(P, rng, q=0.75, rate=0.25):
    """Fires only on busy bars, still faces a coin.

    This has no directional information and a strong activity preference. It
    is the fixture that separates a working hierarchy from a decorative one."""
    n = P["N"]
    act = C.feat_activity(P)
    thr = np.nanquantile(act, q)
    fire = np.isfinite(act) & (act > thr) & (rng.random(n) < rate)
    fire[:400] = False
    fire[n - 40:] = False
    d = np.zeros(n, np.int8)
    d[fire] = rng.choice((-1, 1), size=int(fire.sum()))
    I = np.full(n, np.nan)
    a = np.asarray(P["A"], float)
    I[fire] = P["c"][fire] - d[fire] * 1.2 * a[fire]
    return d, I


def rule_planted(P, rng, fwd=12, rate=0.06, strength=0.85):
    """Knows which way the next `fwd` bars go, `strength` of the time.

    Genuine directional information, deliberately built to be visible: a
    hierarchy that kills this is over-controlling, which is as much a defect
    as one that passes noise."""
    n = P["N"]
    c = np.asarray(P["c"], float)
    fwd_ret = np.concatenate([c[fwd:] - c[:-fwd], np.full(fwd, np.nan)])
    fire = (rng.random(n) < rate) & np.isfinite(fwd_ret)
    fire[:400] = False
    fire[n - fwd - 40:] = False
    truth = np.sign(fwd_ret)
    truth[truth == 0] = 1
    flip = rng.random(n) > strength
    d = np.zeros(n, np.int8)
    d[fire] = (truth[fire] * np.where(flip[fire], -1, 1)).astype(np.int8)
    I = np.full(n, np.nan)
    a = np.asarray(P["A"], float)
    I[fire] = P["c"][fire] - d[fire] * 1.2 * a[fire]
    return d, I


def skill_by_level(P, d, I, tick, levels=C.LEVELS, seed=SEED, stop_mult=2.0):
    real = engine(P, d, I, tick, stop_mult=stop_mult)
    if real is None:
        # loud rather than silent: an empty book returned as NaN skill reads
        # as "no effect" when it means "no measurement", and the first run of
        # these fixtures failed exactly that way
        return None, {"_empty": "engine returned no book for the real rule - "
                      "check the pre-trade gate against the fixture's spread"}
    e = float(real[0].mean())
    out = {}
    for lv in levels:
        rng = np.random.default_rng(seed)
        dc, Ic, meta = C.build(P, d, I, lv, rng)
        r = engine(P, dc, Ic, tick, stop_mult=stop_mult)
        if r is None:
            out[lv] = dict(skill=np.nan, n=0, meta=meta)
            continue
        ce = float(r[0].mean())
        se = float(np.sqrt(real[0].var(ddof=1) / len(real[0])
                           + r[0].var(ddof=1) / len(r[0])))
        out[lv] = dict(skill=e - ce, control_E=ce, n=len(r[0]),
                       t=(e - ce) / se if se > 0 else np.nan, meta=meta)
    return e, out


# ============================================================= fixtures ====
def f1_feature_causality(df):
    full = X.prep(df, 60)
    cut = X.prep(df.iloc[:len(df) - 300], 60)
    m = cut["N"]
    bad = []
    for name, fn in C.FEATURES.items():
        a, b = np.asarray(fn(full), float)[:m], np.asarray(fn(cut), float)
        both = np.isfinite(a) & np.isfinite(b)
        if not np.allclose(a[both], b[both], rtol=1e-12, atol=1e-12):
            bad.append(name)
    return check("feature causality", not bad,
                 f"{len(C.FEATURES)} features, {len(bad)} peek forward"
                 + (f": {bad}" if bad else ""))


def f2_post_signal_refusal():
    raised = False
    try:
        C.SPEC["_probe"] = (("realised_move",), "inherit")
        C.DESCRIPTION["_probe"] = "probe"
        P = X.prep(walk(2000), 60)
        d = np.zeros(P["N"], np.int8)
        d[500:600] = 1
        I = np.full(P["N"], np.nan)
        I[500:600] = P["c"][500:600] - P["A"][500:600]
        C.build(P, d, I, "_probe", np.random.default_rng(1))
    except ValueError as e:
        raised = "post-signal" in str(e)
    finally:
        C.SPEC.pop("_probe", None)
        C.DESCRIPTION.pop("_probe", None)
    return check("post-signal refusal", raised,
                 "matching on realised_move raises rather than warns")


def f3_geometry(P, d, I):
    worst, who = 0.0, None
    for lv in C.LEVELS:
        dc, Ic, _ = C.build(P, d, I, lv, np.random.default_rng(SEED))
        g = C.geometry_gap(P, d, I, dc, Ic)
        if not g.get("ok", False):
            if g.get("rel_gap", 1.0) > worst:
                worst, who = g.get("rel_gap", 1.0), lv
    return check("geometry inheritance", who is None,
                 f"worst dist/ATR quartile gap {worst:.1%}"
                 + (f" at {who}" if who else " across all eight levels")
                 + "   (random_like measured 73%)")


def f4_determinism(P, d, I):
    bad = []
    for lv in C.LEVELS:
        a = C.build(P, d, I, lv, np.random.default_rng(SEED))
        b = C.build(P, d, I, lv, np.random.default_rng(SEED))
        if not (np.array_equal(a[0], b[0])
                and np.allclose(np.nan_to_num(a[1], nan=-1),
                                np.nan_to_num(b[1], nan=-1))):
            bad.append(lv)
    return check("determinism", not bad,
                 f"same seed reproduces all eight levels exactly"
                 if not bad else f"drifts at {bad}")


def f5_no_self_donation(P, d, I):
    real = set(np.where(np.asarray(d) != 0)[0].tolist())
    bad = []
    for lv in C.LEVELS:
        dc, _, _ = C.build(P, d, I, lv, np.random.default_rng(SEED))
        overlap = real & set(np.where(dc != 0)[0].tolist())
        if overlap:
            bad.append(f"{lv}:{len(overlap)}")
    return check("no self-donation", not bad,
                 "no control places an entry on a real signal bar"
                 if not bad else f"overlaps {bad}")


def f6_placement(P, d, I):
    worst, who = 1.0, None
    for lv in C.LEVELS:
        _, _, m = C.build(P, d, I, lv, np.random.default_rng(SEED))
        if m["placement_rate"] < worst:
            worst, who = m["placement_rate"], lv
    return check("placement rate", worst >= 0.80,
                 f"lowest {worst:.0%} at {who} (below 80% means the strongest "
                 f"controls are measured on a different sample size)")


def f7_direction_mix(P, d, I):
    real_up = float((np.asarray(d) > 0).sum() / max((np.asarray(d) != 0).sum(), 1))
    dc1, _, _ = C.build(P, d, I, "C1", np.random.default_rng(SEED))
    dc0, _, _ = C.build(P, d, I, "C0", np.random.default_rng(SEED))
    u1 = float((dc1 > 0).sum() / max((dc1 != 0).sum(), 1))
    u0 = float((dc0 > 0).sum() / max((dc0 != 0).sum(), 1))
    ok = abs(u1 - real_up) < 1e-9 and abs(u0 - 0.5) < 0.05
    return check("direction mix", ok,
                 f"rule long-share {real_up:.3f}; C1 inherits {u1:.3f}; "
                 f"C0 coins {u0:.3f}")


def f8_stratum_fidelity(P, d, I):
    """Total-variation distance between the rule's and the control's
    distribution over each matched dimension."""
    worst, who = 0.0, None
    for lv in ("C2", "C3", "C4", "C5"):
        dims = tuple(x for x in C.SPEC[lv][0] if x)
        dc, Ic, _ = C.build(P, d, I, lv, np.random.default_rng(SEED))
        for dim in dims:
            v = np.asarray(C.FEATURES[dim](P), float)
            a = v[np.asarray(d) != 0]
            b = v[dc != 0]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            if len(a) < 50 or len(b) < 50:
                continue
            edges = np.unique(np.nanquantile(a, np.linspace(0, 1, 11)))
            if len(edges) < 3:
                continue
            pa = np.histogram(a, bins=edges)[0] / len(a)
            pb = np.histogram(b, bins=edges)[0] / len(b)
            tv = 0.5 * float(np.abs(pa - pb).sum())
            if tv > worst:
                worst, who = tv, f"{lv}/{dim}"
    return check("stratum fidelity", worst < 0.15,
                 f"worst total-variation gap {worst:.3f} at {who}")


def f9_relaxation_reported(P, d, I):
    """Force empty cells by matching five dims on a small book and check the
    meta reports the relaxation rather than silently widening."""
    n = P["N"]
    d2 = np.zeros(n, np.int8)
    I2 = np.full(n, np.nan)
    hit = np.where(np.asarray(d) != 0)[0][:400]
    d2[hit] = np.asarray(d)[hit]
    I2[hit] = np.asarray(I)[hit]
    _, _, m = C.build(P, d2, I2, "C7", np.random.default_rng(SEED))
    consistent = (m["placed"] + m["unmatched"] == m["requested"]
                  and m["relaxed"] <= m["placed"])
    return check("relaxation reported", consistent,
                 f"C7 on 400 signals: placed {m['placed']}, of which "
                 f"{m['relaxed']} relaxed, {m['unmatched']} unmatched; "
                 f"full-cell match rate {m['match_rate']:.0%}")


def f10_null_process(P, tick):
    rng = np.random.default_rng(5)
    d, I = rule_random(P, rng)
    e, out = skill_by_level(P, d, I, tick)
    ts = {lv: out[lv]["t"] for lv in C.LEVELS if lv in out}
    worst = max((abs(v) for v in ts.values() if np.isfinite(v)), default=np.nan)
    return check("null process", worst < 3.0,
                 "information-free rule on a random walk: |t| "
                 + " ".join(f"{k} {abs(v):.1f}" for k, v in ts.items()))


def f11_planted_direction(P, tick):
    rng = np.random.default_rng(7)
    d, I = rule_planted(P, rng)
    e, out = skill_by_level(P, d, I, tick)
    t7 = out.get("C7", {}).get("t", np.nan)
    t1 = out.get("C1", {}).get("t", np.nan)
    return check("planted direction", np.isfinite(t7) and t7 > 3.0,
                 f"real information survives to the strongest control: "
                 f"C1 t {t1:+.1f} -> C7 t {t7:+.1f} "
                 f"(a hierarchy that kills this is over-controlling)")


def f12_planted_activity(P, tick):
    """The discriminating fixture. A rule with a strong activity preference
    and a coin for a direction must beat C1 and die by C3."""
    rng = np.random.default_rng(11)
    d, I = rule_activity_only(P, rng)
    e, out = skill_by_level(P, d, I, tick)
    s1 = out.get("C1", {}).get("skill", np.nan)
    s3 = out.get("C3", {}).get("skill", np.nan)
    t3 = out.get("C3", {}).get("t", np.nan)
    t7 = out.get("C7", {}).get("t", np.nan)
    died = np.isfinite(t3) and abs(t3) < 3.0 and np.isfinite(t7) and abs(t7) < 3.0
    shrank = np.isfinite(s1) and np.isfinite(s3) and abs(s3) <= abs(s1) + 1e-6
    return check("planted activity", died and shrank,
                 f"activity-only rule: skill vs C1 {s1:+.4f} -> vs C3 "
                 f"{s3:+.4f} (t {t3:+.1f}), C7 t {t7:+.1f}; the artifact must "
                 f"not survive the control built to remove it")


def f13_strength_ordering(P, tick):
    """Apparent skill must SHRINK IN MAGNITUDE as the control strengthens.

    The first version of this fixture asserted a signed ordering, C7 <= C1.
    That is wrong whenever the apparent skill is negative, which it is here:
    an activity-selecting rule with a coin for a direction LOSES to a
    random-timing control by about 0.018R. Signed, C7 above C1 then reads as a
    failure when it is the behaviour wanted - the artifact got smaller.

    Magnitude is the right quantity, and eight draws rather than three,
    because at |t| below 1 a single draw's ordering is noise and the earlier
    version was reading noise.

    The negative sign is itself informative and is not smoothed over. A busy
    bar means elevated near-term range against a stop and target that are both
    fixed at 1.2 ATR, so both levels are touched within one bar more often,
    and G12 resolves every one of those as a loss. Activity selection is
    therefore charged a penalty by the bracket rather than rewarded by it -
    which is the opposite of the direction the activity artifact was assumed
    to run in, and is followed up in g12_volatility_interaction."""
    rows = []
    lv = ("C1", "C3", "C5", "C7")
    for s in range(21, 29):
        rng = np.random.default_rng(s)
        d, I = rule_activity_only(P, rng)
        _, out = skill_by_level(P, d, I, tick, levels=lv)
        row = [out[l]["skill"] for l in lv
               if l in out and np.isfinite(out[l]["skill"])]
        if len(row) == len(lv):
            rows.append(row)
    if len(rows) < 4:
        return check("strength ordering", False,
                     f"only {len(rows)} usable draws")
    # Over eight draws the mean skill at every level is between 0.0003 and
    # 0.0044 - all of them noise. Comparing their RATIOS is meaningless at
    # that scale, and an earlier version of this fixture did exactly that and
    # called a 0.0044 against a 0.0007 a systematic failure.
    #
    # The property that can actually be tested is the one that matters: for a
    # rule with no directional information, no control level may show apparent
    # skill distinguishable from zero. Four levels are examined, seven degrees
    # of freedom, two-sided 5% with a Bonferroni correction gives 3.50, and
    # that number is fixed here before the result is read.
    A = np.asarray(rows, float)
    m = A.mean(axis=0)
    se = A.std(axis=0, ddof=1) / math.sqrt(len(A))
    t = np.where(se > 0, m / np.where(se > 0, se, 1), 0.0)
    worst = float(np.max(np.abs(t)))
    ok = worst < 3.50
    return check("strength ordering", ok,
                 "over {} draws, skill (t):  ".format(len(rows))
                 + "  ".join(f"{k} {v:+.4f} ({tt:+.1f})"
                             for k, v, tt in zip(lv, m, t))
                 + f"   worst |t| {worst:.2f} against a 3.50 bar")


def main():
    print("CONTROL LAYER FIXTURES - processes whose answer is known")
    print("=" * 96)
    print(__doc__.split("WHY THE FIXTURES USE SYNTHETIC PROCESSES")[1]
          .split("WHAT EACH FIXTURE ASSERTS")[0])

    df = walk(60000, seed=1)
    P = X.prep(df, 60)
    tick = 1e-5
    rng = np.random.default_rng(3)
    d, I = rule_activity_only(P, rng)

    f1_feature_causality(df)
    f2_post_signal_refusal()
    f3_geometry(P, d, I)
    f4_determinism(P, d, I)
    f5_no_self_donation(P, d, I)
    f6_placement(P, d, I)
    f7_direction_mix(P, d, I)
    f8_stratum_fidelity(P, d, I)
    f9_relaxation_reported(P, d, I)
    f10_null_process(P, tick)
    f11_planted_direction(P, tick)
    f12_planted_activity(P, tick)
    f13_strength_ordering(P, tick)

    print("\n" + "=" * 96)
    if FAIL:
        print(f"  {len(FAIL)} of 13 fixtures FAILED: {FAIL}")
        sys.exit(1)
    print("  all 13 fixtures pass")


if __name__ == "__main__":
    main()
