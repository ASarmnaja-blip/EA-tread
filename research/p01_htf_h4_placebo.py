#!/usr/bin/env python3
"""Is M15+HTF-H4's positive result P01's skill, or the trend filter alone?

THE QUESTION THIS ANSWERS

  p01_htf_gate.py reported M15 gated by H4 trend as the one variant that
  flips net positive (sum R +20.58, +1,073.23 USC, 187 trades, 2026 only).
  That is exactly the shape every earlier good-looking result in this
  project took before being retracted, so it is tested rather than trusted.

THE PLACEBO

  Take the SAME bars P01 actually fires on (same count, same times) and
  replace the DIRECTION with a coin flip, then run those through the
  IDENTICAL H4 trend gate and the identical fixed engine. If P01's specific
  Donchian-20 timing is what earns the money, random direction should do
  much worse. If the gate alone - forcing every taken trade to align with
  a strong H4 trend, at a symmetric 1R:1R bracket - is what earns it, random
  direction should earn about the same.
"""
import pathlib, sys
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import xauusd_1000_setups as X
from p01_htf_gate import htf_trend_state, apply_htf_gate, HTF_FREQ
from p01_multi_tf_2026 import h1_source, resample_bidask, m1_source
from p01_trade_log import trade_log

N_SEEDS = 20


def main():
    m1_m15 = m1_source("2023-01-01")
    m1_m15 = m1_m15[(m1_m15.index.dayofweek < 5) |
                    ((m1_m15.index.dayofweek == 5) & (m1_m15.index.hour == 0))]
    m15 = resample_bidask(m1_m15, "15min")
    h1 = h1_source()
    h4 = resample_bidask(h1, "4h")

    P = X.prep(m15, 0)
    dvec, Ivec = X.make_templates(P)["P01"]()
    hstate = htf_trend_state(h4, HTF_FREQ["H4"])
    n_yr = int((P["idx"] < pd.Timestamp("2026-01-01", tz="UTC")).sum())

    dvec_real_g = apply_htf_gate(P["idx"], dvec, hstate)
    T_real = trade_log(P, dvec_real_g, Ivec, n_yr, P["N"], 0.001, 0.01, 5000.0)
    real_per_trade = T_real.R.sum() / len(T_real)

    print("P01 + HTF-H4, REAL DIRECTION vs RANDOM DIRECTION at the same bars")
    print("=" * 78)
    print(f"real   n={len(T_real):>4}  win {float((T_real.R>0).mean())*100:5.1f}%  "
          f"sum R {T_real.R.sum():+7.2f}  R/trade {real_per_trade:+.4f}  "
          f"P&L {T_real.pnl_USC.sum():+9.2f} USC")

    per_trade = []
    nz = np.where(dvec != 0)[0]
    for seed in range(1, N_SEEDS + 1):
        rng = np.random.default_rng(seed)
        dvec_rand = np.zeros_like(dvec)
        dvec_rand[nz] = rng.choice([-1, 1], size=len(nz)).astype(dvec.dtype)
        dvec_rand_g = apply_htf_gate(P["idx"], dvec_rand, hstate)
        T = trade_log(P, dvec_rand_g, Ivec, n_yr, P["N"], 0.001, 0.01, 5000.0)
        if len(T) == 0:
            continue
        per_trade.append(T.R.sum() / len(T))

    per_trade = np.array(per_trade)
    print(f"\nplacebo (random direction, {len(per_trade)} seeds):")
    print(f"  mean R/trade   {per_trade.mean():+.4f}")
    print(f"  sd R/trade     {per_trade.std(ddof=1):.4f}")
    print(f"  range          [{per_trade.min():+.4f}, {per_trade.max():+.4f}]")
    z = (real_per_trade - per_trade.mean()) / (per_trade.std(ddof=1) + 1e-12)
    print(f"\nreal P01's R/trade vs the placebo distribution: {z:+.2f} SD")
    rank = int((per_trade >= real_per_trade).sum())
    print(f"placebo seeds that beat or matched the real result: "
          f"{rank} of {len(per_trade)}")

    print("\n" + "=" * 78)
    if abs(z) < 1.5:
        print("VERDICT: the positive M15+HTF-H4 result is NOT P01's entry skill.")
        print("Random direction through the SAME gate earns about the same money.")
        print("The gate itself - forcing every trade to align with a strong H4")
        print("trend, at a symmetric 1R:1R bracket in a year gold trended hard -")
        print("is what earns it. P01's specific Donchian-20 timing adds nothing")
        print("measurable on top of that. This retracts the reading in the")
        print("previous message that flagged this result as worth testing")
        print("further; the test asked for has already returned the answer.")
    else:
        print("VERDICT: real P01 clears the placebo distribution by a margin")
        print("worth investigating further - not explained by trend capture")
        print("alone.")


if __name__ == "__main__":
    main()
