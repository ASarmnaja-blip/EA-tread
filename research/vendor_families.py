#!/usr/bin/env python3
"""The four KRV families, reimplemented from their names and tested.

WHAT CAN AND CANNOT BE CLAIMED HERE

  The four EAs arrived as compiled .ex5: high entropy, no readable strings
  beyond a vendor contact, no source. Their actual logic is not recoverable,
  so NOTHING below is a test of those binaries. What is tested is the FAMILY
  each name describes, implemented from a standard definition.

  That is weaker than testing the products and it is still worth doing, in one
  direction only:

    family dead   ->  strong evidence against any implementation of it,
                      including the vendor's. A well-tuned version of a rule
                      with no edge is a well-tuned version of no edge.

    family alive  ->  says nothing about the vendor's build, but justifies
                      asking for the .mq5 and testing the real thing.

  An asymmetric test is still a test. It just has to be reported as one.

THE FOUR, AS IMPLEMENTED

  1 DIVERGENCE REVERSAL   price makes a lower low while RSI makes a higher low
                          (and the mirror). This is NOT the RSI mean reversion
                          this repo already killed - that fires on a level,
                          this fires on a disagreement between two swings.

  2 COMPRESSION BREAKOUT  realised range over N bars in the bottom quantile of
                          its own history, then a close beyond the compressed
                          range. Closest to the squeeze rule already tested and
                          killed, but the compression is measured over a window
                          and against its own distribution rather than on one
                          bar.

  3 EXHAUSTION REVERSAL   an extended directional run plus a climax bar - large
                          range, close rejecting its own extreme - faded. This
                          family has never been tested in this repo under any
                          name.

  4 VOLUME POWER ZONES    a tick-volume profile over a rolling window; the
                          point of control is the most-traded price. Signal
                          fires when price returns to it.

ON TICK VOLUME, WHICH I PREVIOUSLY DISMISSED TOO FAST

  Gold CFD has no consolidated tape, so the volume field is a TICK COUNT, not
  traded size. That is a proxy rather than the real thing - but it is a good
  one: the published correlation between tick count and true volume in FX runs
  around 0.9, and the profile only needs relative activity across price levels,
  not absolute size. So family 4 is testable with a stated caveat, and calling
  it untestable was wrong.

  The caveat that does bite: a POC built from tick counts is a POC of QUOTE
  activity. On a venue where quotes update faster in fast markets, that biases
  the profile toward volatile prices rather than heavily-traded ones.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB
import multi_tf_setup_grid as G
from strictness import randomise_timing

SEED = 17
EXITS = ("stop + time", "trail 2ATR BE")
RM = 1.5


def swings(x, w):
    """Confirmed swing highs and lows, w bars either side.

    Shifted forward by w so a swing is only visible once it is confirmed -
    without that shift the whole file is a look-ahead bug, which is how two
    earlier results in this repo had to be retracted."""
    s = pd.Series(x)
    hi = (s == s.rolling(2 * w + 1, center=True).max())
    lo = (s == s.rolling(2 * w + 1, center=True).min())
    return (hi.fillna(False).shift(w).fillna(False).to_numpy(),
            lo.fillna(False).shift(w).fillna(False).to_numpy())


def f_divergence(P, w=5, rsi_p=14, gap=40):
    """Regular divergence: price and RSI disagree between two confirmed swings."""
    c, N = P["c"], P["N"]
    s = pd.Series(c)
    d_ = s.diff()
    up = d_.clip(lower=0).ewm(alpha=1 / rsi_p, adjust=False).mean()
    dn = (-d_.clip(upper=0)).ewm(alpha=1 / rsi_p, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
    sh, sl = swings(c, w)
    out = np.zeros(N, np.int8)
    last_lo = last_hi = -1
    for i in range(N):
        if sl[i]:
            if last_lo >= 0 and 0 < i - last_lo <= gap:
                # price lower low, RSI higher low -> bullish
                if c[i] < c[last_lo] and np.isfinite(rsi[i]) and \
                        np.isfinite(rsi[last_lo]) and rsi[i] > rsi[last_lo]:
                    out[i] = 1
            last_lo = i
        if sh[i]:
            if last_hi >= 0 and 0 < i - last_hi <= gap:
                if c[i] > c[last_hi] and np.isfinite(rsi[i]) and \
                        np.isfinite(rsi[last_hi]) and rsi[i] < rsi[last_hi]:
                    out[i] = -1
            last_hi = i
    return out


def f_compression(P, n=20, q=0.25, look=250):
    """Range over n bars in the bottom q of its own history, then a break out."""
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    rng = (pd.Series(h).rolling(n).max()
           - pd.Series(l).rolling(n).min()).to_numpy()
    thr = pd.Series(rng).rolling(look).quantile(q).shift(1).to_numpy()
    hi = pd.Series(h).rolling(n).max().shift(1).to_numpy()
    lo = pd.Series(l).rolling(n).min().shift(1).to_numpy()
    out = np.zeros(N, np.int8)
    with np.errstate(invalid="ignore"):
        comp = np.isfinite(thr) & np.isfinite(rng) & (rng <= thr)
        out[comp & (c > hi)] = 1
        out[comp & (c < lo)] = -1
    return out


def f_exhaustion(P, run=5, ext=2.0, rej=0.5):
    """An extended run plus a climax bar that rejects its own extreme, faded."""
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    out = np.zeros(N, np.int8)
    rng_ = np.maximum(h - l, 1e-9)
    up_run = np.zeros(N, int); dn_run = np.zeros(N, int)
    for i in range(1, N):
        up_run[i] = up_run[i - 1] + 1 if c[i] > c[i - 1] else 0
        dn_run[i] = dn_run[i - 1] + 1 if c[i] < c[i - 1] else 0
    for i in range(run + 1, N):
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        moved = abs(c[i] - c[i - run]) / a
        if moved < ext:
            continue
        upper = (h[i] - max(o[i], c[i])) / rng_[i]
        lower = (min(o[i], c[i]) - l[i]) / rng_[i]
        if up_run[i] >= run and upper >= rej:
            out[i] = -1
        elif dn_run[i] >= run and lower >= rej:
            out[i] = 1
    return out


def f_volume_poc(P, look=240, bins=24, tol=0.25):
    """Rolling tick-volume profile; fire when price returns to the POC.

    The profile is built from bars STRICTLY BEFORE i, so the level price is
    tested against was fixed before the bar that tests it."""
    c, h, l, N = P["c"], P["h"], P["l"], P["N"]
    v = P.get("vol")
    if v is None:
        return np.zeros(N, np.int8)
    v = np.nan_to_num(np.asarray(v, float))
    A = P["A"]
    out = np.zeros(N, np.int8)
    step = max(look // 8, 1)
    poc = np.full(N, np.nan)
    for i in range(look, N, step):
        lo_, hi_ = l[i - look:i].min(), h[i - look:i].max()
        if not np.isfinite(lo_) or hi_ <= lo_:
            continue
        edges = np.linspace(lo_, hi_, bins + 1)
        idx = np.clip(np.digitize(c[i - look:i], edges) - 1, 0, bins - 1)
        w = np.bincount(idx, weights=v[i - look:i], minlength=bins)
        centre = 0.5 * (edges[:-1] + edges[1:])
        p = centre[int(np.argmax(w))]
        poc[i:min(i + step, N)] = p
    for i in range(look, N):
        a, p = A[i], poc[i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(p):
            continue
        if abs(c[i] - p) <= tol * a:
            # price has returned to the most-traded level; take the side it
            # came from, which is the standard reading of a POC retest
            out[i] = 1 if c[i] < c[i - 1] else -1
    return out


FAMILIES = {
    "divergence": (f_divergence, [dict(w=5, rsi_p=14, gap=40),
                                  dict(w=3, rsi_p=14, gap=30),
                                  dict(w=8, rsi_p=21, gap=60)]),
    "compression": (f_compression, [dict(n=20, q=0.25),
                                    dict(n=12, q=0.20),
                                    dict(n=40, q=0.33)]),
    "exhaustion": (f_exhaustion, [dict(run=5, ext=2.0, rej=0.5),
                                  dict(run=3, ext=1.5, rej=0.4),
                                  dict(run=8, ext=3.0, rej=0.6)]),
    "volume_poc": (f_volume_poc, [dict(look=240, bins=24, tol=0.25),
                                  dict(look=120, bins=16, tol=0.20),
                                  dict(look=480, bins=32, tol=0.35)]),
}


def book(Pg, sig, exit_name, hold, spread, lo, hi):
    c, A, N = Pg["c"], Pg["A"], Pg["N"]
    design = G.EXITS[exit_name]
    live = np.where((sig != 0) & np.isfinite(A) & (A > 0))[0]
    live = live[(live >= max(lo, 320)) & (live < min(hi, N - 1))]
    R, I, HD = [], [], []
    busy = -1
    for i in live:
        i = int(i)
        if i <= busy:
            continue
        risk = RM * A[i]
        if risk <= 0:
            continue
        r, kx = G.exit_run(Pg, i, c[i], int(sig[i]), risk, design, hold, spread)
        if r is None:
            continue
        R.append(r); I.append(float(i)); HD.append(float(max(kx - i, 1)))
        busy = kx
    if len(R) < 20:
        return None
    return np.asarray(R), np.asarray(I), np.asarray(HD)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--hold", type=int, default=48)
    a = ap.parse_args()
    t0 = time.time()

    print("THE FOUR KRV FAMILIES, REIMPLEMENTED AND TESTED")
    print("=" * 96)
    print(__doc__.split("WHAT CAN AND CANNOT BE CLAIMED HERE")[1]
          .split("THE FOUR, AS IMPLEMENTED")[0])

    m = M.load_tf(a.tf)
    P0 = M.prep(m)
    spread = float(EB.scenario_cost_px(260.0, 0.0) / np.nanmedian(P0["c"]))
    cost_R = float(EB.scenario_cost_px(260.0, 0.0) /
                   (RM * np.nanmedian(P0["A"])))
    disc_end = EB.DISCOVERY_END if S.bar_minutes(m.index) >= 60 \
        else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))
    Pg["vol"] = P0["vol"]

    k = sum(len(v[1]) for v in FAMILIES.values()) * len(EXITS)
    floor = math.sqrt(2 * math.log(k))
    print(f"data    {a.tf} {m.index[0].date()} -> {m.index[-1].date()}, "
          f"discovery {n_disc:,} bars")
    print(f"tests   {k} ({len(FAMILIES)} families x 3 variants x "
          f"{len(EXITS)} exits), floor |t| > {floor:.2f}")
    print(f"cost    {cost_R:.4f}R per trade at a {RM} ATR stop\n")

    rng = np.random.default_rng(SEED)
    rows = []
    print(f"  {'family':<13}{'params':<28}{'exit':<15}{'n_d':>7}{'skill_d':>9}"
          f"{'t_d':>7}{'n_h':>7}{'skill_h':>9}{'t_h':>7}")
    for fam, (fn, grid) in FAMILIES.items():
        for gp in grid:
            try:
                sig = fn(Pg, **gp)
            except Exception as e:
                print(f"  {fam:<13}{str(gp)[:27]:<28}FAILED {type(e).__name__}")
                continue
            fired = int((sig != 0).sum())
            if fired < 40:
                print(f"  {fam:<13}{str(gp)[:27]:<28}only {fired} signals")
                continue
            ps = ",".join(f"{x}={y}" for x, y in gp.items())
            for ex in EXITS:
                res = {}
                for lab, (lo, hi) in (("d", (0, n_disc)),
                                      ("h", (n_disc, len(m)))):
                    b = book(Pg, sig, ex, a.hold, spread, lo, hi)
                    cb = book(Pg, randomise_timing(sig, lo, hi, rng), ex,
                              a.hold, spread, lo, hi)
                    if b is None or cb is None:
                        res[lab] = None
                        continue
                    R, I, HD = b
                    res[lab] = dict(n=len(R), E=float(R.mean()),
                                    skill=float(R.mean() - cb[0].mean()),
                                    t=float(M.block_bootstrap_t(
                                        R - cb[0].mean(), I, HD, 1)))
                if res.get("d") is None or res.get("h") is None:
                    print(f"  {fam:<13}{ps[:27]:<28}{ex:<15}  too few trades")
                    continue
                d_, h_ = res["d"], res["h"]
                rows.append(dict(family=fam, params=ps, exit=ex,
                                 n_d=d_["n"], skill_d=d_["skill"], t_d=d_["t"],
                                 n_h=h_["n"], skill_h=h_["skill"], t_h=h_["t"]))
                print(f"  {fam:<13}{ps[:27]:<28}{ex:<15}{d_['n']:>7,}"
                      f"{d_['skill']:>+9.4f}{d_['t']:>+7.2f}{h_['n']:>7,}"
                      f"{h_['skill']:>+9.4f}{h_['t']:>+7.2f}")

    if not rows:
        print("\n  nothing produced a usable book")
        return
    T = pd.DataFrame(rows)

    print("\n" + "=" * 96)
    print("VERDICT PER FAMILY")
    print("=" * 96)
    print(f"  {'family':<14}{'variants':>9}{'best t_d':>10}{'its skill_h':>13}"
          f"{'clears floor':>14}{'beats cost':>12}   verdict")
    for fam, g in T.groupby("family"):
        b = g.loc[g["t_d"].idxmax()]
        cf = bool(b["t_d"] > floor)
        pos = bool(b["skill_h"] > 0)
        bc = bool(b["skill_h"] > cost_R)
        # The criterion was written to the ledger before this run and has
        # THREE parts: clear the floor on discovery, stay positive on holdout,
        # AND exceed the round-trip cost. An earlier version of this line
        # checked only the first two and called compression ALIVE on a holdout
        # skill of +0.0423 against a cost of 0.0518 - a rule that clears every
        # statistical bar and still loses money on every trade. The registered
        # criterion is the one that counts.
        alive = cf and pos and bc
        why = ("ALIVE - ask for the .mq5" if alive
               else "dead" if not cf
               else "clears floor, loses to cost" if pos
               else "clears floor, negative out of sample")
        print(f"  {fam:<14}{len(g):>9}{b['t_d']:>+10.2f}{b['skill_h']:>+13.4f}"
              f"{('yes' if cf else 'no'):>14}{('yes' if bc else 'no'):>12}"
              f"   {why}")

    print(f"\n  floor {floor:.2f} for {k} tests   cost {cost_R:.4f}R")
    print(f"\n  A family marked dead here is evidence against any build of it,")
    print(f"  the vendor's included - a tuned version of a rule with no edge is")
    print(f"  a tuned version of no edge. A family marked ALIVE says nothing")
    print(f"  about the vendor's build and only justifies asking for source.")
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
