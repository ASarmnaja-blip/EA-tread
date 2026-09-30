# WRWR out-of-sample tests on historical data — pre-registration (2026-09-30, committed before any number below is computed)

Operator: "shadow เราเก็บผ่านข้อมูลในอดีตเลยสิ ยังไงเราก็มีข้อมูลมากพออยู่แล้ว" and "ถ้างั้นก็ทำในเงินด้วยเลยสิ จะได้ไม่ต้องรอ 26 สัปดาห์".
The weekly champions over 2004-2026 already exist (data/wrwr/wrwr_champions_history.xlsx) but they are not evidence: the four
SHADOW configurations were chosen AFTER the Reality Check had seen all of 2004-2026. Two historical tests remove that researcher
look-ahead. Both are descriptive for the alpha ledger (no alpha is spent). The forward SHADOW record keeps running unchanged: no
file in forward_shadow.SHADOW_FILES is modified (the silver code lives in new files), and its digest is re-checked afterwards.

## Test A — the research procedure replayed through time (gold, results already computed)
Inputs (frozen, nothing is re-simulated): the weekly net R matrices at f = 1 % (`R_0.01`, 144 configurations) and the Stage F
random-router benchmarks B (2,000 paths) of both families: data/wrwr/family_XAUUSD.npz + bench_F.npz (zoo) and
data/wrwr/family_XAUUSD_f2.npz + bench_F_f2.npz (Family 2); d = R - B; active weeks only (the family file's `active` mask).
Timing: R_{j,k} is realised on exits in (cut_k, cut_{k+1}], so it is known at cut_{k+1}; champions and random draws use only
information at cut k. Decision date for year Y: c*(Y) = the first cut on or after 1 January Y 00:00 UTC, index k*(Y). The
decision uses active weeks k < k*(Y); year Y is the active weeks k*(Y) <= k < k*(Y+1). Y = 2010 .. 2026 (2026 partial).
Procedures, each family separately:
- **P1 (primary):** studentized White Reality Check on d over the history (gates.reality_check: stationary bootstrap, mean block
  10, K = 999, seed 12345 + Y). If the family p <= 0.05, ADOPT the configuration with the largest t (ties: lower index) for
  year Y; otherwise STAND ASIDE (zero R for the year).
- P4: same gate, adopt the 4 configurations with the largest t, equal weight (mean of their weekly R and d).
- F1 / F4 (descriptive, no gate): top-1 / top-4 by t every year.
The adopted configuration's own continuous path is sliced by year (handover between configurations is approximated by slicing).
Read-out per family and procedure: years adopted, adopted weeks, total R, mean weekly R and mean weekly d over the adopted weeks
with one-sided 95% stationary-bootstrap lower bounds (gates.lower_bound_mean: block 10, K = 999, seed 777), share of positive
adopted years, the year-by-year table (Y, p, chosen configuration, R, d).
- **PASS:** P1 lower bound of mean weekly d > 0 AND mean weekly R > 0.
- **WEAK:** lower bound of d > 0 but mean R <= 0 (beats random picks, still loses after cost).
- **FAIL:** lower bound of d <= 0.
- **INSUFFICIENT:** P1 adopts fewer than 104 weeks; F1 is then the descriptive answer to "does the configuration that looks best
  on the past carry forward".
Caveat recorded now: the contract, the families and their definitions were written after earlier full-sample gold research, so
Test A is out of sample for the SELECTION of configurations, not a fully virgin test.

## Test B — silver (XAGUSD), prices never read before this commit
Supersedes the primary of contract C7 before XAG is opened: C7 as frozen tests only the zoo BASE, whose gold Reality Check failed
(p = 0.111), and its secondary is empty (no configuration passed the gold cost gate). The question that matters is whether the
Family 2 selection skill found on gold (Reality Check p = 0.003) exists on silver. C7 as frozen is still run and reported (B3).

### Data (docs/WRWR_XAG_MANIFEST.md, committed with this file)
- HistData XAGUSD M1 ASCII 2009-05 .. 2026-09 (26 zips). Timestamps are New York local time with DST, converted to UTC exactly as
  research/history/build_histdata.py does for gold (ambiguous / nonexistent local times dropped).
- H1 bar = the M1 bars opening in that UTC hour: open first, high max, low min, close last; every hour with >= 1 M1 bar is kept.
  Volume proxy v = number of M1 bars in the hour (HistData has no volume; only the zoo VWAP and OBV indicators read v).
- Prices as quoted (HistData ~ bid); no outlier filter; the number of M1 bars with |log return| > 5 % is reported.
- H4 / D1 from H1 with signals.resample (H4 >= 2 H1 bars; D1 22:00 UTC anchor, >= 18 H1 bars; spread of the first H1 bar).
- Spread per H1 bar: Exness XAGUSD M5 (data/fresh/XAGUSD_M5.npz, 2023-09-01 .. 2026-09-28; previously opened only to freeze the C4
  constant, no strategy statistic ever computed on it): the first M5 bar of the hour, ask-bid / close x 1e4; none elsewhere.
- Timezone checks; Test B stops if any fails:
  (i) hours present in both HistData H1 and Exness H1 (bid closes): for shifts s in {-2, -1, 0, +1, +2} h, the MAD of the close
  difference in bp; separately in US summer time and winter time, s = 0 has the smallest MAD and MAD(0) <= 0.5 x min(MAD(-1), MAD(+1)).
  (ii) every calendar year 2009 .. 2026: the correlation of silver and gold (Dukascopy mid) H1 log returns at lag 0 exceeds those at
  lags -1 h and +1 h, separately in summer and winter time.
  The C5 offset thresholds (|median| <= 2 bp, MAD <= 1 bp) are reported for information only (two different feeds).

### Rules (frozen from gold; no tuning on silver)
- Costs C4 XAG: entries before 2023: the frozen constant 11.615 bp; entries from 2023 with a recorded Exness spread for the entry
  bar: max(4.0, spread + 1.0) bp; entries from 2023 without one: the constant (conservative). Stress +2 bp. Swap: contracts.swap_bp
  ("XAGUSD": US 2y + markup -0.20 pp, longs only). Contract size, lot step, margin: data/foundry/mt5_symbols_20260930.json (C2).
- Regime cells: engine.build on silver H1 (same code as gold); vol_scale: contracts.causal_vol_scale, historical mode, silver H1
  (B_REF from silver's own weekly RV). Cut grid: the gold grid (Fridays 22:15 UTC from 2003-05-09) to the week after the last bar.
- Candidates: Family 2 (docs/WRWR_FAMILY2_PREREG.md) and the zoo on silver bars, same exits, stops, holds, sessions, clock times.
  One definitional transfer: round-number levels are silver's own quote grid, $0.50 and $1.00 (gold's $50 / $100 divided by 100);
  candidate names are unchanged (round50_x = $0.50, round100_x = $1.00 on silver).
- Selector: the same 144 configurations (window x LCB z x pool x m x equity filter, min 10 trades), C2 portfolio, f = 1 %, $10,000.
- Engineering check before silver: the new table builder must reproduce the frozen gold H4 tables (zoo and Family 2) bit for bit
  from gold bars and gold costs; otherwise stop and fix.

### Endpoints
- **B1 (primary): Family 2 Reality Check on silver, p <= 0.05** (d vs the same-exit-configuration random router; Stage S 500 paths
  per configuration; if p < 0.20, Stage F 2,000 paths decides; block 10, K = 999, seed 12345). d nets the same costs on both sides,
  so B1 measures selection skill, not whether silver pays its costs.
- **B2 (secondary):** F2-66, F2-78, F2-134, F2-86 (indices 66, 78, 134, 86): one-sided studentized p of mean d from the same
  bootstrap, Holm step-down over the four at familywise 0.05; plus the cost gate of each (lower bound of mean weekly R > 0, +2 bp
  stress mean > 0, stressed drawdown <= 1.25 x base).
- **B3 (C7 as frozen, reported):** zoo BASE (52w, z 1, H1, m 2, no filter) on silver: one-sided 95% lower bound of mean d > 0 vs its
  10,000-path random-router benchmark.
- Reported alongside, never as a pass: PBO (16 blocks, embargo 5), eras 2010-14 / 2015-20 / 2021-26, long / short split, total R.
Reading: B1 PASS with a Holm-significant B2 configuration = the gold selection skill replicates on silver (still no alpha; the next
step would be asking the operator about a forward allocation). B1 FAIL = it does not replicate; Family 2 stays SHADOW only.
