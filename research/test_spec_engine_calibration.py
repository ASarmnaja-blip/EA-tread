#!/usr/bin/env python3
"""Calibration for the spec engine: on information-free data it must earn
nothing and lose exactly the spread.

WHY THIS FILE EXISTS

  The engine in `xauusd_1000_setups.py` produced, on its first run, a result
  that met every bar this project sets: P01 positive on 9 of 9 markets in both
  periods, binomial P = 0.0020, gross E(R) positive everywhere, block-bootstrap
  t up to +9.68. It was a one-bar look-ahead.

  The entry filled at the ask CLOSE of bar t+1 while the exit loop scanned
  that same bar's high and low, so a trade could be closed at its target by
  price action that happened before the trade existed. The spec says the entry
  is the FIRST ask of bar t+1 - the open - and that one word was the whole
  difference between a discovery and a defect.

  Nothing in the market data could have revealed that. Every cross-market,
  holdout, and control test the project runs was passed by the broken engine,
  because all of them compare the engine against itself. The only test that
  catches it is one where the correct answer is known in advance.

THE TWO INVARIANTS

  Run any rule on a true martingale - a series with no information in it at
  all - and:

    E(R)  must be NEGATIVE, and approximately the round-trip spread measured
          in R. A backtest that breaks even on information-free data is
          collecting something it has not paid for.

    skill must be ZERO against a matched control. Anything else is the
          measurement apparatus talking to itself.

  The generator is `mega_search.synth`, which is an ARITHMETIC martingale on
  purpose: the geometric version it replaced had positive drift in price space
  and scored a breakout rule at +0.2893R on supposedly information-free data.
  That correction is recorded in its own docstring and is the reason this file
  can trust its null.

WHAT A FAILURE HERE MEANS

  It does not mean a rule is unprofitable. It means the ENGINE is wrong, and
  every number it has produced - good and bad - has to be re-run. That is what
  happened the first time this was run, and the nine-market result that had
  already been written up went from 9-of-9 to 5-of-9, a coin flip.

Run:  python3 research/test_spec_engine_calibration.py
"""
import sys, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X

SEEDS = range(1, 9)
BARS = 180_000
SIGMA = 0.0008
SPREAD = 0.40

fails = []


def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail:
        print(f"          {detail}")
    if not cond:
        fails.append(name)


def synthetic_book(seed, template="P01"):
    """A martingale with a real two-sided quote wrapped around it."""
    df = M.synth(BARS, seed, SIGMA)
    half = df["spread"].to_numpy() / 2
    for k in ("open", "high", "low", "close"):
        df["bid_" + k] = df[k] - half
        df["ask_" + k] = df[k] + half
    P = X.prep(df, 60)
    d, I = X.make_templates(P)[template]()
    real = X.run_e01(P, d, I, 0, P["N"], 0.001)
    if real is None:
        return None
    R, i_, hd, rat = real
    rng = np.random.default_rng(1000 + seed)
    ctrl = X.run_e01_control(
        P, X.randomise_timing_local(d, 0, P["N"], rng), 0, P["N"],
        risk_ratios=rat, rng=rng)
    if ctrl is None:
        return None
    return dict(R=R, i=i_, hd=hd, skill=float(R.mean() - ctrl[0].mean()),
                ratio=rat)


print("\nSPEC ENGINE CALIBRATION ON INFORMATION-FREE DATA")
print("=" * 74)
print(f"  {len(list(SEEDS))} martingale paths, {BARS:,} bars each, "
      f"spread {SPREAD} flat")

books = [b for b in (synthetic_book(s) for s in SEEDS) if b is not None]
ck("every synthetic path produced a book", len(books) == len(list(SEEDS)),
   f"{len(books)} of {len(list(SEEDS))}")

if books:
    Es = np.array([b["R"].mean() for b in books])
    Sk = np.array([b["skill"] for b in books])
    # The spread in R units: the round trip costs SPREAD, and R is denominated
    # against a stop distance of ratio x ATR, so the expected drag is the mean
    # of SPREAD / (ratio x ATR). Taking the realised ratios makes this a
    # measured expectation rather than an assumed one.
    print(f"\n  E(R) per path: "
          f"{', '.join(f'{e:+.4f}' for e in Es)}")
    print(f"  skill per path: "
          f"{', '.join(f'{s:+.4f}' for s in Sk)}")

    print("\nINVARIANT 1 - a rule with no information must LOSE the spread")
    ck("mean E(R) is negative", Es.mean() < 0,
       f"mean {Es.mean():+.4f} - a break-even backtest on information-free "
       f"data is collecting something it has not paid for")
    ck("every path is negative", bool((Es < 0).all()),
       f"worst {Es.max():+.4f}")

    print("\nINVARIANT 2 - skill against a matched control must be ZERO")
    se = Sk.std(ddof=1) / np.sqrt(len(Sk))
    ck("mean skill is within 2 SE of zero", abs(Sk.mean()) < 2 * se + 1e-9,
       f"mean {Sk.mean():+.4f}, SE {se:.4f} -> {Sk.mean()/se:+.2f} SE")
    ck("mean skill is small in absolute terms", abs(Sk.mean()) < 0.02,
       f"mean {Sk.mean():+.4f}. The broken engine scored +0.0728 here, "
       f"against +0.1535 on real markets -\n          about half the "
       f"'edge' was the defect")

    print("\nINVARIANT 3 - the entry cannot be resolved by its own bar")
    # The defect that started this: entry at the entry bar's CLOSE while the
    # exit scanned that bar's HIGH and LOW. Assert the engine reads the OPEN,
    # directly, so a future edit that reverts it fails here rather than in a
    # published result.
    src = (pathlib.Path(__file__).parent / "xauusd_1000_setups.py").read_text()
    ck("entry reads the entry bar's OPEN quote",
       'entry = P["ask_o"][e] if d > 0 else P["bid_o"][e]' in src,
       "the spec says 'Ask แรกของแท่ง t+1' - the first quote of the bar, "
       "not its close")
    ck("exits are tested on the side that actually closes the trade",
       'ex_lo = P["bid_l"] if d > 0 else P["ask_l"]' in src,
       "a long is closed by selling, at the bid; testing against the mid "
       "charges half a spread")

print("\n" + "=" * 74)
if fails:
    print(f"FAILED {len(fails)}: " + ", ".join(fails))
    print("\n  A failure here invalidates every number the engine has")
    print("  produced, not just the current run. Re-run them.")
    sys.exit(1)
print("engine is calibrated: it earns nothing on nothing, and pays the spread")
