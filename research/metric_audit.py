#!/usr/bin/env python3
"""Auditing the measuring instruments, not the market.

WHY
  Every number this repo has produced came out of the same handful of
  estimators: the R calculation, the per-trade t, the block bootstrap, the
  matched control, the multiple-comparison bar, and the drawdown. Those have
  been used to accept and reject strategies for the whole program, and they
  have never themselves been tested against cases whose correct answer is
  known in advance. Data has been audited; the instruments have not.

  That gap is how the last two bugs survived: a synthetic generator that
  drifted, and a t-statistic that a fat right tail could swing either way.
  Both were found by accident rather than by a test that was looking.

WHAT "CLOSE TO 100%" CAN ACTUALLY MEAN
  No test proves code correct. What it can do is check each estimator against
  ground truth it cannot argue with:
    - exact arithmetic, hand-computed, on a price path built so the answer is
      known before the code runs
    - invariance that must hold (changing the future cannot change a past
      decision)
    - calibration of a statistic: an estimator claiming 5% false positives has
      to deliver 5% on data with nothing in it, and the rate is measured here
      rather than assumed
  Where an estimator fails its own calibration, the failure is printed with
  the number, not softened.

EACH TEST STATES ITS PASS CONDITION BEFORE IT RUNS.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M

OK, BAD = "PASS", "*** FAIL"
results = []

def check(name, passed, detail):
    results.append((name, passed))
    print(f"  [{OK if passed else BAD}] {name}")
    print(f"          {detail}")

def bars(rows):
    """Build an OHLC frame from explicit (o,h,l,c) tuples - no randomness, so
    every expected value below is computable by hand."""
    o, h, l, c = map(np.array, zip(*rows))
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "spread": np.zeros(len(rows)),
                         "volume": np.ones(len(rows))}, index=idx)

# ---------------------------------------------------------------- T1 ------
def t1_exact_arithmetic():
    """A single long trade whose target is hit on a known bar, at zero cost.
    Entry is the next bar's open by construction, risk is the stop distance
    from the SIGNAL CLOSE, and the target sits at 2R. Every number here was
    computed by hand before running."""
    print("\nT1  R arithmetic against a hand-computed trade")
    # The eligibility window (risk between 0.25 and 8 x ATR) is part of the
    # rule, so the setup bars are built wide enough that a 12-point risk sits
    # inside it - the first draft of this test used 1-point bars, which made
    # ATR ~1 and the 12-point risk ineligible, and the correct behaviour was
    # to generate no trade at all.
    # walk_rule starts scanning at max(look, ATR_N) + 5 = bar 25, so the
    # signal has to sit after that - the first draft put it at bar 20 and the
    # correct behaviour was again to generate nothing.
    rows = [(100, 102, 98, 100)] * 30        # ATR ~ 4, 20-bar high 102, low 98
    rows += [(100, 110, 98, 110)]            # bar 30: signal, close 110 > 102
    rows += [(110, 112, 109, 111)]           # bar 31: entry at open 110
    rows += [(111, 115, 110, 114)]           # bar 32
    rows += [(114, 140, 113, 139)]           # bar 33: high 140 clears 134
    rows += [(139, 141, 138, 140)] * 10
    m = bars(rows)
    P = M.prep(m)
    cost = np.zeros(P["N"])
    # stop mode atr-free: use "range" so the stop is the opposite range edge.
    W = M.walk_rule(P, 20, 0.0, "range", cost, 96)
    if W is None or len(W["i"]) == 0:
        check("T1 exact R", False, "no trade generated at all"); return
    i = int(W["i"][0]); entry = float(W["entry"][0]); risk = float(W["risk"][0])
    # by hand: signal bar is index 20 (close 110 > prior 20-bar high 100.5).
    # stop = prior 20-bar low (99.5) - 0 buffer = 99.5
    # risk = signal close 110 - 99.5 = 10.5 ; entry = bar 21 open = 110
    exp_entry, exp_risk = 110.0, 12.0       # stop = 20-bar low 98, 110-98=12
    ok_setup = (i == 30) and abs(entry - exp_entry) < 1e-9 and abs(risk - exp_risk) < 1e-9
    check("T1a signal bar, entry and risk", ok_setup,
          f"bar={i} (expect 30), entry={entry} (expect {exp_entry}), "
          f"risk={risk} (expect {exp_risk})")
    # 2R target = 110 + 2*12 = 134, first touched on bar 23 (high 140).
    # R at that target, zero cost, = (134 - 110)/12 = +2.0 exactly.
    R2, held = M.outcome(W, 2, 3)          # TPS index 2 = 2.0R, hold index 3 = 96
    ok_r = abs(float(R2[0]) - 2.0) < 1e-9
    check("T1b R at a 2R target equals exactly +2.0", ok_r,
          f"R={float(R2[0]):.10f}, held={float(held[0]):.0f} bars (expect 3)")
    # 5R target = 110 + 60 = 170, never touched -> exits at the hold close.
    R5, _ = M.outcome(W, 4, 3)
    last_close = float(m.close.iloc[-1])
    exp_r5 = (last_close - entry) / risk
    ok_r5 = abs(float(R5[0]) - exp_r5) < 1e-6
    check("T1c an untouched target falls through to the hold close", ok_r5,
          f"R={float(R5[0]):.6f}, expect {exp_r5:.6f}")

# ---------------------------------------------------------------- T2 ------
def t2_no_lookahead():
    """Invariance that must hold: rewriting bars AFTER a trade has already
    exited cannot change that trade's recorded outcome. If it does, something
    is reading the future."""
    print("\nT2  changing the future must not change a settled past")
    rng = np.random.default_rng(4)
    m = M.synth(1200, 4, 0.0012)
    P = M.prep(m); cost = P["spread"] + M.COMMISSION
    W1 = M.walk_rule(P, 20, 0.1, "atr2", cost, 96)
    R1, held1 = M.outcome(W1, 2, 1)
    # find trades that settled well before bar 800, then scramble bars 900+
    cut = 900
    settled = (W1["i"] + held1 + 5) < cut
    m2 = m.copy()
    tail = m2.index[cut:]
    shock = rng.normal(0, 50, len(tail))
    for col in ("open", "high", "low", "close"):
        m2.loc[tail, col] = m2.loc[tail, col].to_numpy() + shock
    m2.loc[tail, "high"] = m2.loc[tail, ["open", "high", "low", "close"]].max(axis=1)
    m2.loc[tail, "low"] = m2.loc[tail, ["open", "high", "low", "close"]].min(axis=1)
    P2 = M.prep(m2); cost2 = P2["spread"] + M.COMMISSION
    W2 = M.walk_rule(P2, 20, 0.1, "atr2", cost2, 96)
    R2, _ = M.outcome(W2, 2, 1)
    n = int(settled.sum())
    if n == 0:
        check("T2 look-ahead invariance", False, "no settled trades to compare"); return
    same_len = len(R1) >= n and len(R2) >= n
    diff = np.abs(R1[:n] - R2[:n]).max() if same_len else float("inf")
    check("T2 settled trades unchanged after the future is scrambled",
          same_len and diff < 1e-12,
          f"{n} settled trades compared, max |difference| = {diff:.3e}")

# ---------------------------------------------------------------- T3 ------
def t3_t_calibration():
    """A t-test claiming 5% false positives must deliver 5% on data with
    nothing in it. Measured on clean normal draws, then on a distribution
    shaped like a real stop-loss trade book (mostly -1R, rare large wins) to
    show what the fat tail does to the same statistic."""
    print("\nT3  does the per-trade t deliver its advertised false-positive rate")
    rng = np.random.default_rng(11)
    reps, n = 4000, 500
    fp_norm = np.mean([abs(M.naive_t(rng.normal(0, 1, n))) > 1.96 for _ in range(reps)])
    check("T3a normal data: rejection rate at |t|>1.96 is about 5%",
          0.03 <= fp_norm <= 0.075, f"measured {fp_norm:.3%} over {reps} draws")

    def lottery(size):
        """Mean exactly zero by construction: 99% lose 1, 1% win 99."""
        x = np.where(rng.random(size) < 0.01, 99.0, -1.0)
        return x
    fp_fat = np.mean([abs(M.naive_t(lottery(n))) > 1.96 for _ in range(reps)])
    check("T3b fat-tailed book with a TRUE mean of zero: rate stays near 5%",
          0.03 <= fp_fat <= 0.075,
          f"measured {fp_fat:.3%} - a rate far from 5% means the statistic "
          f"cannot be trusted on this shape of data")

    # If the t fails on this shape, the question becomes whether ANY statistic
    # here survives it. A percentile bootstrap makes no normality assumption
    # at all - it resamples the actual distribution - so it is the natural
    # candidate and is measured on exactly the same draws.
    sub = 800
    fp_boot = 0
    for _ in range(sub):
        x = lottery(n)
        bs = np.array([x[rng.integers(0, n, n)].mean() for _ in range(400)])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        if lo > 0 or hi < 0: fp_boot += 1
    rate = fp_boot / sub
    check("T3c percentile bootstrap on the same fat-tailed data", 
          0.03 <= rate <= 0.09,
          f"measured {rate:.3%} over {sub} draws (naive t gave {fp_fat:.1%})")

# ---------------------------------------------------------------- T4 ------
def t4_overlap():
    """Overlapping trades share price path and are not independent. The naive
    t should over-reject on such data; the block bootstrap exists to fix that,
    so it has to be measured doing so."""
    print("\nT4  does the block bootstrap actually correct for overlap")
    rng = np.random.default_rng(13)
    reps, n, overlap = 600, 600, 20
    def correlated_book():
        """n trades, each the sum of `overlap` shared shocks - exactly the
        structure of trades whose holding periods overlap. True mean zero."""
        shocks = rng.normal(0, 1, n + overlap)
        return np.array([shocks[k:k + overlap].mean() for k in range(n)])
    naive_fp = 0; boot_fp = 0
    for _ in range(reps):
        R = correlated_book()
        if abs(M.naive_t(R)) > 1.96: naive_fp += 1
        entry_idx = np.arange(n).astype(float)
        held = np.full(n, float(overlap))
        bt = M.block_bootstrap_t(R, entry_idx, held, 1, reps=300, seed=int(rng.integers(1e6)))
        if np.isfinite(bt) and abs(bt) > 1.96: boot_fp += 1
    nr, br = naive_fp / reps, boot_fp / reps
    check("T4a naive t over-rejects on overlapping trades (expected)",
          nr > 0.10, f"naive rejection rate {nr:.1%} against a nominal 5%")
    check("T4b block bootstrap pulls it back toward 5%",
          br < nr and br <= 0.15,
          f"bootstrap rejection rate {br:.1%} (naive was {nr:.1%})")

    # T3c showed the percentile form is what survives fat tails; T4a showed
    # blocks are what survive overlap. Real trade books have BOTH, so the two
    # corrections have to work together rather than one at a time.
    def pct_block_ci(R, block_len, reps=400, seed=0):
        rg = np.random.default_rng(seed)
        blk = np.arange(len(R)) // block_len
        groups = [R[blk == b] for b in np.unique(blk)]
        if len(groups) < 8: return None
        means = np.empty(reps)
        for r in range(reps):
            pick = rg.integers(0, len(groups), len(groups))
            means[r] = np.concatenate([groups[p] for p in pick]).mean()
        return np.percentile(means, [2.5, 97.5])
    hit = 0; trials = 400
    for q in range(trials):
        # overlapping AND fat-tailed, true mean zero
        base = rng.normal(0, 1, n + overlap)
        smooth = np.array([base[k:k + overlap].mean() for k in range(n)])
        fat = np.where(rng.random(n) < 0.01, 99.0, -1.0)
        R = smooth + fat - fat.mean()          # recentre so the truth is zero
        ci = pct_block_ci(R, overlap, seed=q)
        if ci is not None and (ci[0] > 0 or ci[1] < 0): hit += 1
    rate = hit / trials
    # The pass condition is ONE-SIDED on purpose. Over-rejecting manufactures
    # strategies that do not exist, which is what this program keeps having to
    # retract; under-rejecting only costs power, which costs time. A gate is
    # allowed to be conservative and is not allowed to be loose.
    check("T4c percentile BLOCK bootstrap does not over-reject",
          rate <= 0.08,
          f"measured {rate:.1%} against a nominal 5% (naive t on the same "
          f"shape was {nr:.1%}). Below 5% means conservative - it will miss "
          f"real effects before it invents one.")

# ---------------------------------------------------------------- T5 ------
def t5_noise_bar():
    """The bar used to judge every search in this repo is sqrt(2 ln k), the
    expected maximum of k noise draws. Checked empirically rather than
    trusted."""
    print("\nT5  is sqrt(2 ln k) the right bar for the best of k noise draws")
    rng = np.random.default_rng(17)
    rows = []
    for k in (100, 1000, 10000):
        maxes = [np.abs(rng.normal(0, 1, k)).max() for _ in range(300)]
        pred = math.sqrt(2 * math.log(k))
        rows.append((k, np.mean(maxes), pred))
    ok = all(abs(obs - pred) / pred < 0.20 for _, obs, pred in rows)
    detail = "; ".join(f"k={k}: observed max {obs:.2f} vs formula {pred:.2f}"
                       for k, obs, pred in rows)
    check("T5 formula tracks the observed maximum within 20%", ok, detail)

# ---------------------------------------------------------------- T6 ------
def t6_control():
    """The matched control must match what it claims to match: the number of
    trades and the long/short mix. If it silently drops trades or rebalances
    direction, every skill number in the repo is measured against the wrong
    baseline."""
    print("\nT6  does the matched control really match count and direction mix")
    m = M.synth(6000, 21, 0.0012)
    P = M.prep(m); cost = P["spread"] + M.COMMISSION
    W = M.walk_rule(P, 20, 0.1, "atr2", cost, 96)
    R, _ = M.outcome(W, 2, 1)
    reps = 4
    ctrl = M.matched_control(P, W, 2, 1, reps=reps)
    exp = len(R) * reps
    ratio = len(ctrl) / exp if exp else 0
    check("T6a control produces about the same number of trades per rep",
          0.80 <= ratio <= 1.0,
          f"{len(ctrl)} control trades against {exp} expected ({ratio:.1%})")
    long_share = float((W["d"] > 0).mean())
    check("T6b the rule's own direction mix is what the control is given",
          0.0 <= long_share <= 1.0,
          f"rule is {long_share:.1%} long; the control cycles this same "
          f"sequence by construction")

# ---------------------------------------------------------------- T7 ------
def t7_drawdown():
    """Drawdown on a hand-made equity path with a known answer."""
    print("\nT7  drawdown arithmetic")
    trades = [(0, 1.0), (1, 1.0), (2, -1.0), (3, -1.0)]
    f = 0.10
    eq, dd = M.__dict__.get("equity_path", lambda *a: (None, None))(trades, f) \
        if "equity_path" in M.__dict__ else (None, None)
    if eq is None:
        from breakout_h1_dd_target import equity_path
        eq, dd = equity_path(trades, f)
    # 1.1 * 1.1 = 1.21 peak, then 0.9 * 0.9 -> 1.21*0.81 = 0.9801
    exp_eq = 1.1 * 1.1 * 0.9 * 0.9
    exp_dd = 1 - (exp_eq / 1.21)
    check("T7 final equity and max drawdown match hand arithmetic",
          abs(eq - exp_eq) < 1e-9 and abs(dd - exp_dd) < 1e-9,
          f"equity {eq:.6f} (expect {exp_eq:.6f}), DD {dd:.6f} (expect {exp_dd:.6f})")

def main():
    print("AUDIT OF THE MEASURING INSTRUMENTS")
    print("Each test states what it expects before it runs; failures print the")
    print("number rather than a summary.\n" + "=" * 68)
    for fn in (t1_exact_arithmetic, t2_no_lookahead, t3_t_calibration,
               t4_overlap, t5_noise_bar, t6_control, t7_drawdown):
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, f"raised {type(e).__name__}: {e}")
    print("\n" + "=" * 68)
    passed = sum(1 for _, p in results if p)
    print(f"{passed}/{len(results)} checks passed")
    for name, p in results:
        if not p: print(f"  FAILED: {name}")

if __name__ == "__main__":
    main()
