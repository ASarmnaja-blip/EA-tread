#!/usr/bin/env python3
"""P01 under the vendor's exact fill and exit spec, on nine markets.

WHY THIS RUN EXISTS, AND WHY IT IS THE ONE THAT DECIDES

  `cross_market.py` already declared the breakout family dead on 9 of 9
  markets. P01 IS that family - a Donchian-20 close breakout. But the two
  tests are not the same experiment, and the differences are not cosmetic:

                        cross_market.py          this spec (P01)
      stop              1.5 x ATR                signal bar's own low/high
                                                 minus max(0.10A, spread, 2 ticks)
      target            2R                       1R
      hold              12 bars                  24 bars
      fill              mid minus a flat 260pt   REAL bid for sells, REAL ask
                                                 for buys, quote by quote
      pre-trade gate    none                     spread <= 0.10A and the stop
                                                 distance inside [max(0.30A,
                                                 5*spread), 3A]

  Under the second specification, on gold H1 over the full 2004-2026 history,
  it produced discovery skill +0.1094 (t +3.70) and holdout skill +0.1046
  (t +4.42), with gross E(R) positive in BOTH periods. That is the best result
  this project has produced, and it contradicts a conclusion this project has
  already published - which is precisely why it gets the harshest test
  available rather than a headline.

  A result this good, arriving this late, after this many dead ends, is more
  likely to be a defect than a discovery. The nine-market run is what tells
  the two apart: gold-only is how overfitting looks from the inside.

THE BAR, DECLARED BEFORE THE RUN (change_ledger: xauusd1000_p01_realfill_crossmarket)

  skill positive on at least 8 of 9 markets - binomial P = 1.95% - AND gross
  E(R) positive on at least 6 of 9. The second half is there because this
  project has already learned the hard way, on the compression rule, that
  skill over a random-timing control and actually making money are different
  claims, and that the first can hold while the second fails everywhere.

  Markets are not independent - the dollar is on one side of six of them - so
  the binomial figure is an upper bound on the evidence, not an exact level.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X

CACHE = pathlib.Path(__file__).parent / ".cache_duka"
MARKETS = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
           "AUDUSD", "USDCHF", "USDCAD", "NZDUSD")
# Measured from the cached quotes themselves, not assumed from convention.
TICKS = {"XAUUSD": 0.001, "XAGUSD": 0.001, "USDJPY": 0.001,
         "EURUSD": 0.00001, "GBPUSD": 0.00001, "AUDUSD": 0.00001,
         "USDCHF": 0.00001, "USDCAD": 0.00001, "NZDUSD": 0.00001}
DISC_END = "2017-01-01"
SEED = 17


def load_bidask_h1(sym):
    p = CACHE / f"{sym}_H1_2003_2026.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df[df.index.year >= 2004]
    for k in ("open", "high", "low", "close"):
        df[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    spr = df["ask_close"] - df["bid_close"]
    # Same quality gate clean() applies: a zero or negative spread means the
    # venue was not quoting, and a breakout rule would happily trade those
    # flat synthetic bars.
    df = df[(spr > 0) & (df.high >= df.low) & (df.low > 0)]
    return df


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()

    print("P01 UNDER THE VENDOR'S FILL SPEC, ON NINE MARKETS")
    print("=" * 96)
    print(__doc__.split("WHY THIS RUN EXISTS, AND WHY IT IS THE ONE THAT DECIDES")[1]
          .split("THE BAR, DECLARED BEFORE THE RUN")[0])

    rng = np.random.default_rng(SEED)
    rows = []
    print(f"  {'market':<9}{'bars':>9}{'tick':>9}{'n_disc':>8}{'skill_d':>10}"
          f"{'t_d':>8}{'n_hold':>8}{'skill_h':>10}{'t_h':>8}{'E_all':>10}")
    for sym in [s for s in a.markets.split(",") if s]:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 5000:
            print(f"  {sym:<9} no usable bid/ask cache")
            continue
        tick = TICKS.get(sym, 0.00001)
        P = X.prep(df, 60)
        tmpls = X.make_templates(P)
        dvec, Ivec = tmpls["P01"]()
        n_disc = int((P["idx"] < pd.Timestamp(DISC_END, tz="UTC")).sum())
        res = {}
        for lab, (lo, hi) in (("d", (0, n_disc)), ("h", (n_disc, P["N"]))):
            real = X.run_e01(P, dvec, Ivec, lo, hi, tick)
            if real is None:
                res[lab] = None
                continue
            R, I_, HD, RAT = real
            ctrl = X.run_e01_control(
                P, X.randomise_timing_local(dvec, lo, hi, rng), lo, hi,
                risk_ratios=RAT, rng=rng)
            if ctrl is None:
                res[lab] = None
                continue
            res[lab] = dict(n=len(R), E=float(R.mean()),
                            skill=float(R.mean() - ctrl[0].mean()),
                            t=float(M.block_bootstrap_t(
                                R - ctrl[0].mean(), I_, HD, 1)),
                            R=R, I=I_, HD=HD)
        if res["d"] is None or res["h"] is None:
            print(f"  {sym:<9}{len(df):>9,}  too few trades in one period")
            continue
        d_, h_ = res["d"], res["h"]
        allR = np.concatenate([d_["R"], h_["R"]])
        rows.append(dict(symbol=sym, n_d=d_["n"], skill_d=d_["skill"],
                         t_d=d_["t"], n_h=h_["n"], skill_h=h_["skill"],
                         t_h=h_["t"], E_all=float(allR.mean()),
                         E_d=d_["E"], E_h=h_["E"]))
        print(f"  {sym:<9}{len(df):>9,}{tick:>9.5f}{d_['n']:>8,}"
              f"{d_['skill']:>+10.4f}{d_['t']:>+8.2f}{h_['n']:>8,}"
              f"{h_['skill']:>+10.4f}{h_['t']:>+8.2f}{allR.mean():>+10.4f}")

    if len(rows) < 5:
        print("\n  too few markets to run the declared test")
        return
    T = pd.DataFrame(rows)
    n = len(T)

    print("\n" + "=" * 96)
    print("THE DECLARED TEST")
    print("=" * 96)
    # Skill on each period separately, then the both-periods reading, because
    # a rule that only works in one half is not the rule that was registered.
    pos_d = int((T["skill_d"] > 0).sum())
    pos_h = int((T["skill_h"] > 0).sum())
    pos_both = int(((T["skill_d"] > 0) & (T["skill_h"] > 0)).sum())
    pos_E = int((T["E_all"] > 0).sum())
    print(f"  skill positive on DISCOVERY:  {pos_d} of {n}   "
          f"P(>= {pos_d}) = {binom_tail(pos_d, n):.4f}")
    print(f"  skill positive on HOLDOUT:    {pos_h} of {n}   "
          f"P(>= {pos_h}) = {binom_tail(pos_h, n):.4f}")
    print(f"  skill positive on BOTH:       {pos_both} of {n}")
    print(f"  gross E(R) positive:          {pos_E} of {n}   "
          f"(the declared bar was 6 of 9)")
    print(f"\n  mean skill  discovery {T['skill_d'].mean():+.4f}   "
          f"holdout {T['skill_h'].mean():+.4f}")
    print(f"  mean gross E(R) across markets {T['E_all'].mean():+.4f}")
    print(f"  markets with holdout t > 2:   {int((T['t_h'] > 2).sum())} of {n}")

    skill_pass = pos_h >= 8 and n >= 9
    money_pass = pos_E >= 6
    print(f"\n  skill criterion (8 of 9 on holdout):  "
          f"{'MET' if skill_pass else 'NOT met'}")
    print(f"  money criterion (6 of 9 gross E>0):   "
          f"{'MET' if money_pass else 'NOT met'}")

    if skill_pass and money_pass:
        print(f"\n  -> BOTH HALVES OF THE DECLARED CRITERION ARE MET.")
        print(f"     This is the first rule in this project to replicate")
        print(f"     across markets AND make money in the majority of them.")
        print(f"     It is still a backtest. The next steps are forward")
        print(f"     testing on unseen bars and the E02-E04/C02-C05 expansion")
        print(f"     the spec defines - not a position.")
    elif skill_pass:
        print(f"\n  -> SKILL REPLICATES, MONEY DOES NOT. The same split the")
        print(f"     compression rule showed: the entry carries information")
        print(f"     and not enough of it to pay the spread. A tradeable")
        print(f"     result needs both.")
    else:
        print(f"\n  -> DOES NOT REPLICATE at the declared bar. By this repo's")
        print(f"     standing rule, an effect found on gold and absent")
        print(f"     elsewhere is gold overfit, and the gold result was found")
        print(f"     while debugging rather than as a blind test.")

    gold = T[T["symbol"] == "XAUUSD"]
    others = T[T["symbol"] != "XAUUSD"]
    if len(gold):
        g = gold.iloc[0]
        print(f"\n  gold        skill_d {g['skill_d']:+.4f}  skill_h "
              f"{g['skill_h']:+.4f}  E {g['E_all']:+.4f}")
        print(f"  other {len(others)}     mean skill_h "
              f"{others['skill_h'].mean():+.4f}   positive on "
              f"{int((others['skill_h'] > 0).sum())} of {len(others)}")
        print(f"              mean E {others['E_all'].mean():+.4f}   positive "
              f"on {int((others['E_all'] > 0).sum())} of {len(others)}")
        print(f"  The second and third lines are the out-of-sample ones in")
        print(f"  every respect: no part of those markets was used to find")
        print(f"  this rule, to fix its control bug, or to pick its spec.")

    print(f"\n  CAVEAT: the markets share the dollar on one side of most of")
    print(f"  them, so the binomial figures above are upper bounds.")
    out = pathlib.Path(__file__).parent / "p01_cross_market.csv"
    T.drop(columns=[c for c in T.columns if c in ()], errors="ignore").to_csv(
        out, index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s   detail -> {out.name}")


if __name__ == "__main__":
    main()
