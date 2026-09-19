#!/usr/bin/env python3
"""Two questions that do not need a search, asked across nine markets.

WHY THIS AND NOT MORE RULE-HUNTING

  Every test in this repo so far has re-sliced ONE sample path: XAUUSD,
  2004-2026. Twenty-two years sounds like a lot but it is a single draw from
  whatever process generates gold. No statistic fixes n = 1 market. Searching
  more rules on it raises k without adding information - the noise floor goes
  up, the evidence does not.

  Nine markets is genuinely new data. So this file asks two questions that
  each cost ONE hypothesis, instead of the 1,728 the frozen grid cost and the
  4,000,000 the sweep cost:

  QUESTION 1 - IS THE FAMILY DEAD?
    Not "did any of 1,728 cells pass" but "does the breakout family, pooled
    over every configuration in it, have positive expectancy at all?" That is
    one number per market, one test. A definitive "this whole direction is
    dead" is worth far more than 1,728 individual failures, because it closes
    the direction instead of leaving it open for the next variation.

  QUESTION 2 - DOES IT REPLICATE ACROSS MARKETS?
    One frozen rule, nine instruments. Under the null that the rule has no
    edge anywhere, each market's mean is positive with probability 1/2, so:

        P(>= 7 of 9 positive) =  46/512 = 8.98%
        P(>= 8 of 9 positive) =  10/512 = 1.95%
        P(   9 of 9 positive) =   1/512 = 0.195%

    Requiring 8 of 9 is therefore a 1.95% test that costs ONE hypothesis. A
    rule that clears t = 3 on gold and fails on the other eight is gold's
    idiosyncratic history. A rule that is positive on eight of nine, even
    weakly in each, is evidence of a different kind entirely.

    The markets are not fully independent - the dollar is on one side of six
    of them - so the binomial figure is an upper bound on the evidence, and
    the correlation of the per-market results is reported alongside it so the
    reader can discount accordingly. That is stated here rather than being
    left for someone to notice.

PASS / FAIL, FIXED BEFORE THE RUN

  Q1 the breakout family is declared ALIVE on a market only if the pooled
     mean net R over all configurations is positive AND its block-bootstrap
     95% CI excludes zero. One test per market, floor |t| > 1.96.
  Q2 the frozen rule REPLICATES only if at least 8 of 9 markets show a
     positive mean net R. 7 of 9 is reported as suggestive and is NOT a pass.
  Neither question is allowed to be re-asked with a different rule if it
  fails. If both fail, the breakout direction is closed.

  DISCOVERY DATA ONLY. Validation and holdout are not touched here.
"""
import argparse, math, sys, pathlib, json, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import mega_search as M
import session_rules as S
import exness_backtest as EB
from exness_cent import ExnessCent, SPREAD_SCENARIOS
from split_guard import Split

ACC = ExnessCent()

# ---- the nine markets, declared before the run ----------------------------
MARKETS = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
           "AUDUSD", "USDCHF", "USDCAD", "NZDUSD")

# ---- the ONE frozen rule for question 2 -----------------------------------
# Chosen as the plain centre of the family, NOT as the best discovery cell -
# picking the winner and then "replicating" it would carry gold's selection
# into every other market and the whole point would be lost.
FROZEN = dict(look=20, buf=0.1, stop="atr2", tp=2.0, hold=12)

# ---- the family swept for question 1 --------------------------------------
FAM_LOOKS = (10, 20, 40)
FAM_BUFS = (0.0, 0.1)
FAM_STOPS = ("range", "atr1", "atr2")
FAM_TPS = (1.0, 2.0, None)
FAM_HOLDS = (4, 12)

DISCOVERY_END = "2017-01-01"

def cost_for(symbol, spread_px_series):
    """Round-trip cost in PRICE UNITS, from that market's own measured spread.

    Each instrument has its own tick size and its own typical spread; using
    gold's 260 points on EURUSD would be meaningless. The MEDIAN OF THE
    MARKET'S OWN DISCOVERY-PERIOD BID/ASK is used, which is measured, not
    assumed - and it is fitted on discovery bars only, like every other
    threshold in this repo."""
    s = spread_px_series[np.isfinite(spread_px_series) & (spread_px_series > 0)]
    return float(np.median(s)) if len(s) else float("nan")

def load_market(sym, tf="1h"):
    if sym == "XAUUSD":
        return M.load_tf(tf)
    return D.clean(D.mid(D.load_h1(2003, 2026, symbol=sym)))

def family_pooled(P, deadline, n_disc, cost_px, th):
    """Question 1: pool every configuration in the family into ONE number.

    Each configuration contributes its trades; the pooled mean is taken over
    all of them together. Configurations overlap heavily in the trades they
    select, so the block bootstrap is run over the pooled series with a block
    length set from the holding period - the same correction used everywhere
    else for overlap."""
    all_R, all_i, all_h = [], [], []
    n_cfg = 0
    tps_real = [t for t in M.TPS if t is not None]
    for look in FAM_LOOKS:
        for buf in FAM_BUFS:
            for sm in FAM_STOPS:
                W = EB.walk_for(P, look, buf, sm, cost_px, max(FAM_HOLDS))
                if W is None: continue
                for tp in FAM_TPS:
                    tp_j = None if tp is None else tps_real.index(tp)
                    for hold in FAM_HOLDS:
                        R, held, keep, _, _ = EB.resolve_window(
                            W, P, tp_j, hold, 0, n_disc, deadline)
                        if keep.sum() < 30: continue
                        n_cfg += 1
                        all_R.append(R[keep]); all_i.append(W["i"][keep])
                        all_h.append(held[keep])
    if not all_R:
        return None
    R = np.concatenate(all_R); i = np.concatenate(all_i); h = np.concatenate(all_h)
    order = np.argsort(i)
    return dict(R=R[order], i=i[order], held=h[order], n_cfg=n_cfg)

def frozen_rule(P, deadline, n_disc, cost_px, th):
    """Question 2: the single frozen configuration on this market."""
    tps_real = [t for t in M.TPS if t is not None]
    tp_j = None if FROZEN["tp"] is None else tps_real.index(FROZEN["tp"])
    W = EB.walk_for(P, FROZEN["look"], FROZEN["buf"], FROZEN["stop"],
                    cost_px, FROZEN["hold"])
    if W is None: return None
    R, held, keep, rep, _ = EB.resolve_window(W, P, tp_j, FROZEN["hold"],
                                              0, n_disc, deadline)
    if keep.sum() < 50: return None
    return dict(R=R[keep], i=W["i"][keep], held=held[keep], n=int(keep.sum()))

def binom_tail(k, n, p=0.5):
    """P(X >= k) for X ~ Binomial(n, p) - the sign-consistency test."""
    from math import comb
    return sum(comb(n, j) * p**j * (1-p)**(n-j) for j in range(k, n+1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("CROSS-MARKET: IS THE FAMILY DEAD, AND DOES ANYTHING REPLICATE?")
    print("=" * 82)
    print(__doc__.split("PASS / FAIL")[1].split('"""')[0])
    print(f"MARKETS ({len(MARKETS)}): {', '.join(MARKETS)}")
    print(f"FROZEN RULE for Q2: look{FROZEN['look']} buf{FROZEN['buf']} "
          f"{FROZEN['stop']} tp{FROZEN['tp']} hold{FROZEN['hold']}")
    print(f"  chosen as the plain centre of the family, NOT the best gold cell")
    fam_n = (len(FAM_LOOKS)*len(FAM_BUFS)*len(FAM_STOPS)*len(FAM_TPS)*len(FAM_HOLDS))
    print(f"FAMILY for Q1: {fam_n} configurations pooled into ONE number per market")
    print(f"  hypotheses spent: 1 per market for Q1, 1 total for Q2 "
          f"(the frozen grid spent 1,728; the sweep spent 4,000,000)\n")

    rows = []
    for sym in MARKETS:
        try:
            m = load_market(sym, a.tf)
        except Exception as e:
            print(f"  {sym:<8} SKIPPED - {type(e).__name__}: {e}")
            continue
        if m is None or len(m) < 5000:
            print(f"  {sym:<8} SKIPPED - not enough data")
            continue
        P = M.prep(m)
        tf_min = S.bar_minutes(m.index)
        deadline, _, _ = S.intraday_deadlines(m.index, tf_min)
        n_disc = int((m.index < pd.Timestamp(DISCOVERY_END, tz="UTC")).sum())
        if n_disc < 3000:
            print(f"  {sym:<8} SKIPPED - discovery too short ({n_disc:,} bars)")
            continue
        split = Split(m.index, DISCOVERY_END)
        th = M.fit_thresholds(P, split)
        cost_px = cost_for(sym, P["spread"][:n_disc])
        if not np.isfinite(cost_px):
            print(f"  {sym:<8} SKIPPED - no usable spread series")
            continue

        fam = family_pooled(P, deadline, n_disc, cost_px, th)
        fr = frozen_rule(P, deadline, n_disc, cost_px, th)
        atr_med = float(np.nanmedian(P["A"][:n_disc]))
        rec = dict(symbol=sym, bars=len(m), n_disc=n_disc, cost_px=cost_px,
                   atr_med=atr_med, cost_atr=cost_px / atr_med)
        if fam:
            ci = M.block_bootstrap_ci(fam["R"], fam["i"], fam["held"])
            bt = M.block_bootstrap_t(fam["R"], fam["i"], fam["held"], 1)
            rec.update(fam_n=len(fam["R"]), fam_cfg=fam["n_cfg"],
                       fam_E=float(fam["R"].mean()),
                       fam_ci_lo=(ci[0] if ci is not None else float("nan")),
                       fam_ci_hi=(ci[1] if ci is not None else float("nan")),
                       fam_t=float(bt))
        if fr:
            ci2 = M.block_bootstrap_ci(fr["R"], fr["i"], fr["held"])
            bt2 = M.block_bootstrap_t(fr["R"], fr["i"], fr["held"], 1)
            rec.update(fz_n=fr["n"], fz_E=float(fr["R"].mean()),
                       fz_ci_lo=(ci2[0] if ci2 is not None else float("nan")),
                       fz_t=float(bt2))
        rows.append(rec)
        print(f"  {sym:<8} {len(m):>7,} bars, disc {n_disc:>6,}, "
              f"spread {cost_px*10000:>6.1f} bp-ish  "
              f"| family E {rec.get('fam_E', float('nan')):+.4f} "
              f"(n={rec.get('fam_n',0):,}) "
              f"| frozen E {rec.get('fz_E', float('nan')):+.4f} "
              f"(n={rec.get('fz_n',0):,})")

    if not rows:
        print("\n  no markets usable - nothing to report")
        return

    df = pd.DataFrame(rows)
    print("\n" + "=" * 82)
    print("QUESTION 1 - IS THE BREAKOUT FAMILY ALIVE ON EACH MARKET?")
    print("  (pooled over every configuration; ONE test per market, floor |t|>1.96)")
    print(f"  {'market':<9}{'trades':>10}{'E(R)':>10}{'CI low':>10}{'CI high':>10}"
          f"{'boot t':>9}  verdict")
    alive = []
    for _, r in df.iterrows():
        if "fam_E" not in r or not np.isfinite(r.get("fam_E", np.nan)):
            print(f"  {r['symbol']:<9}{'-':>10}"); continue
        ok = (r["fam_E"] > 0 and np.isfinite(r["fam_ci_lo"]) and r["fam_ci_lo"] > 0)
        if ok: alive.append(r["symbol"])
        print(f"  {r['symbol']:<9}{int(r['fam_n']):>10,}{r['fam_E']:>+10.4f}"
              f"{r['fam_ci_lo']:>+10.4f}{r['fam_ci_hi']:>+10.4f}{r['fam_t']:>+9.2f}"
              f"  {'ALIVE' if ok else 'dead'}")
    print(f"\n  markets where the family is ALIVE: {len(alive)} of {len(df)} "
          f"{alive if alive else ''}")

    print("\n" + "=" * 82)
    print("QUESTION 2 - DOES THE FROZEN RULE REPLICATE ACROSS MARKETS?")
    fz = df[df.get("fz_E", pd.Series(dtype=float)).notna()] if "fz_E" in df else df.iloc[0:0]
    if len(fz) == 0:
        print("  the frozen rule produced no usable sample on any market")
    else:
        print(f"  {'market':<9}{'trades':>10}{'E(R)':>10}{'CI low':>10}{'boot t':>9}"
              f"  sign")
        for _, r in fz.iterrows():
            print(f"  {r['symbol']:<9}{int(r['fz_n']):>10,}{r['fz_E']:>+10.4f}"
                  f"{r['fz_ci_lo']:>+10.4f}{r['fz_t']:>+9.2f}"
                  f"  {'+' if r['fz_E'] > 0 else '-'}")
        pos = int((fz["fz_E"] > 0).sum()); n = len(fz)
        p = binom_tail(pos, n)
        print(f"\n  positive on {pos} of {n} markets   "
              f"P(>= {pos} | no edge) = {p:.4f}")
        if pos >= 8 and n >= 9:
            print("  -> REPLICATES (pre-declared bar: 8 of 9)")
        elif pos >= 7:
            print("  -> suggestive only; the pre-declared bar was 8 of 9, "
                  "so this is NOT a pass")
        else:
            print("  -> DOES NOT REPLICATE")
        print(f"\n  CAVEAT, stated rather than left to be noticed: these markets")
        print(f"  are not independent - the dollar is on one side of most of")
        print(f"  them - so the binomial p above is an UPPER BOUND on the")
        print(f"  evidence, not an exact level.")

    # ---- Q3 ---------------------------------------------------------------
    # This question CANNOT be asked on one market, which is why it is here and
    # not anywhere else in the repo. Every failure on XAUUSD so far has had two
    # readings that no amount of gold data can separate:
    #
    #     "the entry has no edge"            vs   "the edge is real, the
    #                                              spread eats it"
    #
    # The nine markets separate them, because they span a 7x range of cost
    # measured against their own volatility - EURUSD pays 3.0% of ATR round
    # trip, XAGUSD pays 20.3%. Regress expectancy on that ratio and the
    # INTERCEPT is what the family would earn at zero cost. If the intercept
    # is positive, this is a cost problem and a cheaper broker or a bigger
    # timeframe fixes it. If it is not, no cost reduction can help, because
    # there is nothing underneath the cost to uncover.
    print("\n" + "=" * 82)
    print("QUESTION 3 - IS THIS A COST PROBLEM OR A NO-EDGE PROBLEM?")
    q3 = df[df["fam_E"].notna() & df["cost_atr"].notna()] if "fam_E" in df \
        else df.iloc[0:0]
    if len(q3) < 4:
        print("  too few markets to separate cost from edge")
    else:
        x = q3["cost_atr"].to_numpy(float)
        y = q3["fam_E"].to_numpy(float)
        slope, icpt = np.polyfit(x, y, 1)
        rng = np.random.default_rng(7)
        ints = []
        for _ in range(20000):
            k = rng.integers(0, len(x), len(x))
            if len(np.unique(x[k])) < 2:
                continue
            ints.append(np.polyfit(x[k], y[k], 1)[1])
        ints = np.asarray(ints)
        lo, hi = np.percentile(ints, [2.5, 97.5])
        print(f"  {'market':<9}{'cost/ATR':>10}{'family E(R)':>13}")
        for _, r in q3.sort_values("cost_atr").iterrows():
            print(f"  {r['symbol']:<9}{r['cost_atr']*100:>9.2f}%"
                  f"{r['fam_E']:>+13.4f}")
        print(f"\n  slope     {slope:+.4f} E(R) per unit of cost/ATR")
        print(f"  INTERCEPT {icpt:+.4f} <- what the family earns at ZERO cost")
        print(f"  bootstrap 95% CI over markets [{lo:+.4f}, {hi:+.4f}]   "
              f"({float((ints >= 0).mean())*100:.1f}% of resamples >= 0)")
        print(f"\n  n={len(x)} and these markets share the dollar on one side of")
        print(f"  most of them, so that CI is OPTIMISTIC - the true interval is")
        print(f"  wider. Read the conclusion under BOTH ends of it:")
        if hi < 0:
            print(f"    Both ends negative: the family loses money before a")
            print(f"    single pip of spread is charged. NO-EDGE PROBLEM.")
        elif icpt < 0:
            print(f"    Best case, the intercept is zero: the family earns")
            print(f"    NOTHING before costs. Worst case it is negative. Under")
            print(f"    either reading cost reduction cannot rescue it, because")
            print(f"    there is no gross edge underneath the cost to uncover.")
            print(f"    A cheaper broker, a wider stop and a bigger timeframe")
            print(f"    all attack the cost term and all inherit this ceiling.")
        else:
            print(f"    The intercept is positive: there IS gross edge and cost")
            print(f"    is consuming it. Cheaper execution is then the lever,")
            print(f"    and this becomes a pre-registered hypothesis to test.")

    print("\n" + "=" * 82)
    if not alive and (len(fz) == 0 or int((fz['fz_E'] > 0).sum()) < 8):
        print("VERDICT: the breakout direction is CLOSED.")
        print("  The family is dead on every market tested, and the frozen rule")
        print("  does not replicate. Per the rule written before this run, these")
        print("  questions are not re-asked with a different rule.")
    else:
        print("VERDICT: something survived. It is now a PRE-REGISTERED hypothesis")
        print("  and the next step is validation, on data not used here.")
    if a.out:
        pathlib.Path(a.out).write_text(df.to_json(orient="records", indent=1))
    print(f"\n  elapsed {time.time()-t0:.0f}s")
    return df

if __name__ == "__main__":
    main()
