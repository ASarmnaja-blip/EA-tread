#!/usr/bin/env python3
"""Time-series momentum at D1 - the one direction this project never went.

THE TWO REASONS THIS RUN IS DIFFERENT FROM EVERY OTHER FILE HERE

  1. COST. Every test in this repo runs at M1 to H1. Measured on these same
     caches, the round-turn spread as a share of ATR is:

              H1      D1      W1
        mean  19.0%   4.18%   1.19%
        gold  17.2%   3.24%   0.86%
        EUR    5.0%   1.01%   0.27%

     Every candidate this project killed died on cost. The single lever that
     moves cost by an order of magnitude - holding longer - has never been
     pulled. Going DOWN to M1 was tried; going UP was not.

  2. THE HYPOTHESIS COMES FROM OUTSIDE THIS DATA. Everything tested here so
     far was found by searching the same sample it was then judged on, which
     is why the multiple-testing floor now sits at |t| > 3.66 after 815
     hypotheses. Time-series momentum is not from this sample. Moskowitz, Ooi
     and Pedersen (2012) report it positive in 58 of 58 futures markets over
     1965-2009; Hurst, Ooi and Pedersen extend it to 1880. The specification
     below - 12-month lookback, 1-month hold, volatility-scaled - is theirs,
     fixed before this run, not chosen after seeing these results.

  That second point is the whole value of this test. A prediction made
  elsewhere, on other markets, in another century, either survives contact
  with this data or it does not.

WHAT R MEANS HERE

  There is no stop, because the specification being tested has no stop.
  Position size is set so that one unit of ex-ante monthly volatility is one
  R - the same normalisation the literature uses - which keeps E(R) directly
  comparable to every other number in this project and makes the spread enter
  as a real haircut rather than a footnote. The volatility estimate uses only
  data available at the signal.

THE DECOMPOSITION

  A long/short rule that is net long on average inherits whatever the market
  did, exactly as Setup D's long side turned out to be gold's uptrend counted
  twice. So each market is split:

      raw E(R) = mean(d * x)
      drift    = mean(d) * mean(x)      <- the average net exposure alone
      skill    = cov(d, x)              <- the timing, and nothing else

  Only the third column is the claim.

WHY THE PORTFOLIO ROW IS THE HONEST ONE

  Seven of these ten markets have the dollar on one side. Ten markets is not
  ten independent tests, and a binomial count across them overstates the
  evidence - this project has already made that mistake once. So the months
  are pooled into a single equal-weight portfolio series first, and the t on
  THAT series is the one that decides, because cross-market correlation is
  inside it rather than assumed away.
"""
import argparse, math, pathlib, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M

CACHE = pathlib.Path(__file__).parent / ".cache_duka"
MARKETS = ("XAUUSD", "XAGUSD", "USDSEK", "EURUSD", "GBPUSD",
           "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD")
LOOKBACKS = (1, 3, 6, 12)          # months - the literature's own set
HEADLINE = 12                      # the specification the prediction is about
VOL_COM = 60                       # days, MOP2012's centre of mass
VOL_TARGET_MONTHLY = 1.0           # R is defined as one ex-ante monthly sigma
START = "2004-01-01"
GOLD_SWAP_POINTS = -534.9          # XAUUSDc long, from the account spec
GOLD_TICK = 0.001


def load_d1(sym):
    """H1 bid/ask -> daily bars that keep both sides of the quote."""
    f = CACHE / f"{sym}_H1_2003_2026.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f)
    d = d[d.index >= pd.Timestamp(START, tz=d.index.tz)]
    spr = d["ask_close"] - d["bid_close"]
    d = d[spr > 0]
    for k in ("open", "high", "low", "close"):
        d[k] = (d[f"bid_{k}"] + d[f"ask_{k}"]) / 2
    d = d[d.high >= d.low]
    d = d[(d.index.dayofweek < 5) |
          ((d.index.dayofweek == 5) & (d.index.hour == 0))]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last",
           "bid_open": "first", "ask_open": "first",
           "bid_close": "last", "ask_close": "last"}
    b = d.resample("1D").agg(agg).dropna(subset=["close"])
    return b[b.close > 0]


def monthly_trades(b, k_months):
    """One non-overlapping trade per month, signal strictly before entry.

    The signal is the sign of the trailing k-month return measured at the
    CLOSE of the last trading day of month m-1. The fill is the OPEN of the
    first trading day of month m. Those are different bars, which is the
    whole point - the one-bar look-ahead that had to be retracted from the
    P01 nine-market result came from reading a bar the trade was already
    inside of."""
    ret = np.log(b.close / b.close.shift())
    # ex-ante vol from data up to and including the signal day only
    vol_d = ret.ewm(com=VOL_COM, min_periods=VOL_COM).std()
    vol_m = vol_d * math.sqrt(21.0)

    per = b.index.tz_localize(None).to_period("M")
    first = b.groupby(per).head(1).index      # first trading day of each month
    last = b.groupby(per).tail(1).index       # last trading day of each month
    lastp = pd.Series(last, index=pd.PeriodIndex(last, freq="M"))

    rows = []
    for i in range(len(first)):
        m = pd.Period(first[i], freq="M")
        sig_m = m - 1
        look_m = m - k_months
        if sig_m not in lastp.index or look_m not in lastp.index:
            continue
        t_sig, t_look = lastp[sig_m], lastp[look_m]
        c_sig, c_look = b.close[t_sig], b.close[t_look]
        sigma = vol_m[t_sig]
        if not np.isfinite(sigma) or sigma <= 0 or c_look <= 0:
            continue
        d = 1 if c_sig > c_look else -1

        t_in, t_out = first[i], last[i]
        if t_out <= t_in:
            continue
        entry = b.ask_open[t_in] if d > 0 else b.bid_open[t_in]
        exit_ = b.bid_close[t_out] if d > 0 else b.ask_close[t_out]
        mid_in, mid_out = b.open[t_in], b.close[t_out]
        if not all(np.isfinite([entry, exit_, mid_in, mid_out])) or entry <= 0:
            continue

        # R = realised return, signed, divided by the ex-ante monthly sigma
        r_net = d * math.log(exit_ / entry) / sigma
        r_gross = d * math.log(mid_out / mid_in) / sigma
        x = math.log(mid_out / mid_in) / sigma      # the market's own move
        rows.append(dict(month=m, d=d, R=r_net, R_gross=r_gross, x=x,
                         sigma=float(sigma), entry=float(entry),
                         days=int((t_out - t_in).days),
                         t_in=t_in, t_out=t_out))
    return pd.DataFrame(rows)


def decompose(T, col="R"):
    """raw = mean(d*x_realised); drift = mean(d)*mean(x); skill = cov(d, x).

    The cost sits in `raw` because raw uses the net R, while drift and skill
    are computed on the mid-to-mid move - so `skill` answers 'is the timing
    informative' and `raw` answers 'does it survive the spread', which are
    the two questions this project keeps having to separate."""
    d = T["d"].to_numpy(float)
    x = T["x"].to_numpy(float)
    R = T[col].to_numpy(float)
    drift = d.mean() * x.mean()
    skill = float(np.mean(d * x) - drift)
    where = np.arange(len(T), dtype=float)
    held = np.ones(len(T))
    return dict(n=len(T), E=float(R.mean()),
                t_E=float(M.block_bootstrap_t(R, where, held, 1)),
                gross=float(T["R_gross"].mean()),
                drift=float(drift), skill=skill,
                t_skill=float(M.block_bootstrap_t(d * x - drift, where,
                                                  held, 1)),
                net_long=float((d > 0).mean()) * 100,
                win=float((R > 0).mean()) * 100)


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--swap-report", action="store_true", default=True)
    ap.parse_args()
    t0 = time.time()

    print("TIME-SERIES MOMENTUM AT D1 - MONTHLY HOLD - 10 MARKETS")
    print("=" * 96)
    print(__doc__.split("THE TWO REASONS")[1].split("WHAT R MEANS HERE")[0])
    print(f"  ledger id: tsmom_d1_monthly_10market   lookbacks {LOOKBACKS} "
          f"months, hold 1 month, headline k={HEADLINE}\n")

    bars = {}
    for s in MARKETS:
        b = load_d1(s)
        if b is not None and len(b) > 1500:
            bars[s] = b
    print(f"  loaded {len(bars)} markets, "
          f"{min(len(b) for b in bars.values()):,}-"
          f"{max(len(b) for b in bars.values()):,} daily bars each\n")

    books, table = {}, []
    for k in LOOKBACKS:
        per_mkt = {}
        for s, b in bars.items():
            T = monthly_trades(b, k)
            if len(T) >= 60:
                per_mkt[s] = T
        books[k] = per_mkt

        # equal-weight portfolio, month by month - cross-market correlation
        # is inside this series rather than assumed away
        wide = pd.DataFrame({s: T.set_index("month")["R"]
                             for s, T in per_mkt.items()})
        port = wide.mean(axis=1).dropna()
        widex = pd.DataFrame({s: T.set_index("month")["x"]
                              for s, T in per_mkt.items()})
        wided = pd.DataFrame({s: T.set_index("month")["d"]
                              for s, T in per_mkt.items()})
        pdrift = float((wided.mean(axis=1) * widex.mean(axis=1))
                       .reindex(port.index).mean())
        pv = port.to_numpy()
        where = np.arange(len(pv), dtype=float)
        t_port = float(M.block_bootstrap_t(pv, where, np.ones(len(pv)), 1))
        pos_skill = sum(1 for s in per_mkt
                        if decompose(per_mkt[s])["skill"] > 0)
        table.append(dict(k=k, n_mkt=len(per_mkt), months=len(port),
                          E=float(pv.mean()), t=t_port, drift=pdrift,
                          pos_skill=pos_skill,
                          sharpe=float(pv.mean() / pv.std(ddof=1)
                                       * math.sqrt(12))))

    print("=" * 96)
    print("1. THE SWEEP - equal-weight portfolio, net of real bid/ask, swap 0")
    print("=" * 96)
    print(f"  {'lookback':<10}{'months':>8}{'mkts':>6}{'E(R)/mo':>10}"
          f"{'t':>8}{'ann.Sharpe':>12}{'skill>0':>10}")
    for r in table:
        mark = "   <- headline" if r["k"] == HEADLINE else ""
        print(f"  {str(r['k'])+'m':<10}{r['months']:>8}{r['n_mkt']:>6}"
              f"{r['E']:>+10.4f}{r['t']:>+8.2f}{r['sharpe']:>+12.2f}"
              f"{r['pos_skill']:>7} /{r['n_mkt']:<2}{mark}")

    print("\n" + "=" * 96)
    print(f"2. PER MARKET at the headline k={HEADLINE} - raw vs drift vs skill")
    print("=" * 96)
    per = books[HEADLINE]
    print(f"  {'market':<9}{'n':>5}{'long%':>7}{'win%':>7}{'gross':>9}"
          f"{'net E':>9}{'t_E':>7}{'drift':>9}{'skill':>9}{'t_skill':>9}")
    dec = {}
    for s in MARKETS:
        if s not in per:
            continue
        z = decompose(per[s])
        dec[s] = z
        print(f"  {s:<9}{z['n']:>5}{z['net_long']:>6.0f}%{z['win']:>6.1f}%"
              f"{z['gross']:>+9.4f}{z['E']:>+9.4f}{z['t_E']:>+7.2f}"
              f"{z['drift']:>+9.4f}{z['skill']:>+9.4f}{z['t_skill']:>+9.2f}")

    pos = sum(1 for z in dec.values() if z["skill"] > 0)
    n = len(dec)
    hd = [r for r in table if r["k"] == HEADLINE][0]
    print(f"\n  drift-adjusted skill positive on {pos} of {n}   "
          f"(binomial P >= {pos}: {binom_tail(pos, n):.4f}, an UPPER bound -")
    print(f"  seven of these have the dollar on one side, so they are not "
          f"{n} independent tests)")
    print(f"  cost drag, gross minus net: "
          f"{np.mean([z['gross'] - z['E'] for z in dec.values()]):+.4f}R/month")

    print("\n" + "=" * 96)
    print("3. THE DECLARED BAR")
    print("=" * 96)
    floor = math.sqrt(2 * math.log(815))
    c1 = pos >= 8
    c2 = abs(hd["t"]) > floor and hd["t"] > 0
    print(f"  skill positive on >= 8 of 10 markets          "
          f"{pos} of {n}    {'PASS' if c1 else 'FAIL'}")
    print(f"  portfolio net t clears the floor {floor:.2f}       "
          f"t {hd['t']:+.2f}    {'PASS' if c2 else 'FAIL'}")
    print(f"\n  VERDICT: {'BOTH CRITERIA MET' if c1 and c2 else 'DOES NOT CLEAR THE DECLARED BAR'}")

    # ---- 4. the overnight report the cost rules require ---------------------
    print("\n" + "=" * 96)
    print("4. OVERNIGHT COST - the rule this whole design breaks")
    print("=" * 96)
    print("  This project's cost rules say no rollover holding and force a")
    print("  close 30 minutes before rollover. A one-month hold is ~21")
    print("  rollovers, so those rules cannot both be kept and this tested.")
    print("  The main table above sets swap to 0, as the rules require for the")
    print("  main test; the real swap is reported separately here, which is")
    print("  the only known one (XAUUSDc long, -534.9 points).")
    if "XAUUSD" in per:
        T = per["XAUUSD"].copy()
        swap_px = abs(GOLD_SWAP_POINTS) * GOLD_TICK          # USD per night
        nights = T["days"].to_numpy(float)
        # a long pays it; the short side of a spot pair typically receives,
        # but that rate is not in the account spec, so it is charged at zero
        # rather than assumed favourable
        charge = np.where(T["d"].to_numpy() > 0, swap_px * nights, 0.0)
        denom = T["sigma"].to_numpy() * T["entry"].to_numpy()
        r_swap = T["R"].to_numpy() - charge / denom
        z = dec["XAUUSD"]
        spread_R = z["gross"] - z["E"]
        swap_R = float(T.R.mean() - r_swap.mean())
        print(f"\n  XAUUSD, k={HEADLINE}:  swap 0  E {T.R.mean():+.4f}R"
              f"   ->  with real long swap  E {r_swap.mean():+.4f}R")
        print(f"  ({swap_px:.4f} USD/night, median {np.median(nights):.0f} "
              f"nights/trade, charged on longs only)")
        print(f"\n  The two costs side by side, same units, same trades:")
        print(f"      spread  {spread_R:+.4f}R/trade")
        print(f"      swap    {swap_R:+.4f}R/trade   "
              f"= {swap_R/spread_R:.0f}x the spread")
        print(f"  Going up the timeframe did not remove the cost problem, it")
        print(f"  swapped a small one for a larger one. The spread this whole")
        print(f"  project has been fighting is, at a monthly hold, a rounding")
        print(f"  error next to the financing.")

    # ---- 5. the cost-optimal holding period, which settles the premise -----
    print("\n" + "=" * 96)
    print("5. HOW LONG SHOULD ANYTHING BE HELD - a result that outlives this test")
    print("=" * 96)
    print("  Spread is paid ONCE per trade; swap is paid EVERY night. The")
    print("  typical move available to be captured grows like sqrt(time). So")
    print("  for a hold of h nights, cost as a share of the move is")
    print("\n      (S + w*h) / (sigma * sqrt(h))")
    print("\n  which is minimised, by setting the derivative to zero, at")
    print("\n      h* = S / w          (spread divided by swap per night)")
    print("\n  sigma cancels - the answer does not depend on volatility at all,")
    print("  only on the ratio of the two costs the broker charges.")
    if "XAUUSD" in bars:
        b = bars["XAUUSD"]
        S = float((b["ask_close"] - b["bid_close"]).median())
        w = abs(GOLD_SWAP_POINTS) * GOLD_TICK
        print(f"\n  XAUUSDc long:  S = {S:.4f} USD (measured round-turn), "
              f"w = {w:.4f} USD/night")
        print(f"                 h* = {S/w:.2f} nights")
        print(f"\n  The cost-optimal hold for a gold LONG on this account is")
        print(f"  under a single night. That is not a statement about momentum")
        print(f"  or about any entry rule - it is arithmetic on the broker's")
        print(f"  own two numbers, and it says the premise of this file was")
        print(f"  wrong before the first trade was simulated. The H1 and H4")
        print(f"  horizons this project has always worked at are not a habit;")
        print(f"  they are near the only place a swap-paying gold long can be")
        print(f"  held without the financing dominating.")
        print(f"\n  The asymmetry matters: a gold SHORT receives financing on")
        print(f"  most brokers, so w is negative and h* does not exist - there")
        print(f"  is no horizon penalty on that side. This repo has spent its")
        print(f"  effort on the long side throughout, including Setup D, whose")
        print(f"  config disables shorts outright.")

    out = pathlib.Path(__file__).parent / "tsmom_d1.csv"
    pd.concat([T.assign(symbol=s) for s, T in per.items()]).to_csv(out,
                                                                  index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s   detail -> {out.name}")


if __name__ == "__main__":
    main()
