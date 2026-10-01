# Bundle 2 (Y1-Y8) — pre-registration (2026-10-01, written before any of these numbers is computed)

Operator, 2026-10-01: combine rules 1, 3 and 4 of `docs/AUTOPSY_SYNTHESIS_2026-10-01_TH.md` into one system (higher-TF direction +
side switch by market direction + no chasing) and test it on the gold bear phase, silver and 16 markets; re-test the 7 old setups
without profit caps; also: small timeframes anchored to big timeframes, cutting the conditions that lose most often, M30, anchoring to
big timeframes; and "is there a fix" for the grid ruins and for WRWR's fragility. Operator rules: no caps (no take-profit, no time exit,
no clipping), martingale / grid research only. Separate experiments, each with its own read-out.

## Common
- Engine, costs, swaps, fills: `research/bundle/common.py` as in Bundle 1 (entry at the next open, stop first inside a bar, close
  exits at the next open, booked at the fill bar). Metals: Candle Lab bars, now also **M30**. Gold 2003-05..2008-12: Dukascopy H1 / H4 /
  D1 (`signals.load_xau`, W1 aggregated from D1 by the cut grid), cost 2.5 bp + swap. Other markets: MT5 cache D1 / H1, H4 aggregated
  from H1 (22:00 UTC anchor), W1 from D1, and **M30 / M15 / M5 fetched read-only from the demo MT5 terminal** (up to 100,000 bars each:
  roughly 4 / 2 / 0.7 years), broker cost and swap (`data/bundle/broker_specs.json`); USDINR is reported but excluded from pooled reads
  (130 bp spread).
- In-sample vs clean: the rules of Y1 / Y3 were found on gold 2009-2026 and silver 2010-2026 (X8 also showed the 2012-15 bear phase),
  so those are reported as IN-SAMPLE. CLEAN evidence = the 16 MT5 markets and gold 2003-05..2008-12.
- Trend systems: S1 (20 / 10), S2 (55 / 20), CH (55-bar entry, Chandelier 3 x ATR22), 2 N initial stop.

## Y1 Higher-TF-aligned trend system (rules 1 + 3 + 4)
- Anchor direction of a timeframe A at an entry bar's close: sign(close of the last completed A bar - midpoint of its 55-bar Donchian).
- Anchors (NEAR): M5 -> H1 + H4; M15 and M30 -> H4 + D1; H1 and H4 -> D1 + W1; D1 -> W1. Anchors (FAR): every entry TF -> D1 + W1
  (D1 -> W1). Regime = the common sign when both anchors agree, else 0 (no trade).
- Side switch: long breakouts only when the regime is +1, short breakouts only when it is -1.
- No chasing (on the first NEAR anchor): skip a long when that anchor's last completed bars form an up-run of >= 3 or its forming bar's
  range is already >= 1.3 x its ATR(14); mirror for shorts.
- Variants: BASE (all signals, long + short), LONG (long only), REGIME (side switch only), FULL (side switch + no chasing, NEAR),
  FULL-FAR. Every entry TF M5, M15, M30, H1, H4, D1.
- Read-outs: every-signal net R per trade and one-position (TAKEN) net R per trade per market; a portfolio of the 16 markets at 1 % per
  trade (one position per market and system).
- PASS for an entry TF (FULL, NEAR): on the 16 markets (i) one-position net R > 0 in >= 60 % of markets, (ii) pooled every-signal net R
  > 0 with market-week bootstrap p < 0.05, (iii) improvement over BASE > 0 with p < 0.05; and for H1 / H4 / D1 (iv) gold 2003-08 net R > 0.
- Y4 is the read-out of Y1 for M5 / M15 / M30: does anchoring to big timeframes make small timeframes pay after cost?

## Y2 The 7 old setups without profit caps
- Signals exactly as `research/pilot/core.py` s1_breakout, s2_pullback, s3_sweep, s4_failed, s5_vwap, s6_expansion (their NO TRADE rules
  and their own structural initial stop kept; their targets and time stops discarded). Exits (each reported): close beyond the
  opposite 10-bar channel (CHAN10), 20-bar channel (CHAN20), Chandelier 3 x ATR22 (CH3). Entry TFs M15, M30, H1, H4.
- Control: same signals' directions on random bars (stop in the same ATR multiple, same exits), 20 draws -> excess = real - control.
- PASS: gold CHECK net R > 0 and excess > 0 with weekly-cluster bootstrap p < 0.05 after Holm over every setup x exit x TF, AND silver
  net R > 0, AND net R > 0 in >= 60 % of the markets for that TF (H1 / H4 / M30 / M15 where fetched).
- News acceptance / rejection (7th): `research/pilot/results/news_assessments.csv` (2023-11..2026-09, 468 events), the same
  classification from the stored first-minute XAU / DXY moves (|surprise z| >= 0.5, first XAU minute >= 0.5 ATR, DXY moving the other
  way), entry at the next gold M5 open, stop max(1.35 x ATR14(M5), 0.75 x |first minute|, $1), the three uncapped exits on M5.
  Descriptive (small n); 70 / 30 dev / holdout split by time as the original.

## Y3 Cut the conditions that lose most often (exclusion list fixed now, from X8)
Applied to BASE (both sides), each TF, all markets: (E1) entry hour 20-24 UTC (entry TF <= H1); (E2) 1-year ATR percentile < 0.10
(entry TF <= M30); (E3) counter-HTF: a long after the last W1 body <= -0.75 W1 ATR or a W1 down-run >= 3 or a D1 down-run >= 3, mirror for
shorts; (E4) chasing as in Y1. Read-outs: kept share, net R per trade kept vs BASE, ablation (each exclusion alone), portfolio. PASS as Y1
(i)-(iii) with "Y3 kept" in place of FULL.

## Y5 Grid fixes (research only; grids stay forbidden for orders)
Gold and silver H1 grid as X2 (S = 1 x ATR22(D1), m = 1.5 and 2.0) plus: (a) basket stop at the k-th add level (k = 3, 5, 8: all orders
close when price reaches the next level after the k-th add); (b) equity stop: close all when the floating loss reaches 10 % or 20 % of
the cycle-start equity; (c) direction = the Y1 regime (D1 + W1 agree) with the k = 5 basket stop; (d) reference: one order of the same
first size with the same stop distance and the same take-profit. Directions LONG, SHORT, RANDOM (50 seeds), REGIME. Read-outs: ruins,
CAGR net of injected capital, max drawdown, expectancy per cycle in % of equity. No pass rule; the question is whether removing ruin keeps
any positive expectancy beyond the reference.

## Y6 WRWR fragility fixes (on the corrected X7 weekly R matrices)
(a) equal weight of all 144 configurations; (b) equal weight of the top 10 by trailing t at each year's first cut; (c) the single pick
(X7 as is). Perturbations: X7 rebuilt with cost + 1 bp and with every exit fill one bar later. PASS: an ensemble rule with out-of-sample
R > 0 on both metals AND a narrower range across the three versions (base, cost + 1 bp, exit + 1 bar) than the single pick.

## Y7 Invalidation exit (added by Claude; descriptive)
Exit at the next open if, within the first 5 bars after entry, a close falls back below the breakout level (long; mirror for short).
Applied to BASE and FULL; reported next to the uncapped exits. A loss rule, not a profit cap.

## Y8 Volatility router (added by Claude; descriptive)
Per market, each signal's TF is allowed by the D1 1-year ATR percentile at the signal: < 0.33 -> D1 only; 0.33-0.67 -> H4; > 0.67 -> H1.
Portfolio of the router vs fixed D1 / H4 / H1.

## Reporting
Every test of every experiment goes to `data/bundle2/` and the Thai report; failures included.
