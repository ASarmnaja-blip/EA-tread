# WRWR manifest (frozen 2026-09-30, committed BEFORE any gate statistic is computed and BEFORE XAGUSD is opened)
Pre-registration: docs/WRWR_CONTRACT_PREREG.md v6 (C1-C11 + v5/v6 clarifications). Plan: docs/MASTER_PLAN_2026-09-30.md.

## Family (C6)
- 144 deployable configurations, dedup key = (window, lcb_z, pool, m, equity_filter, min_trades), family sha256
  `fb28ac097eee30b5904185dec3e5771b5d620eae616955722707c6b055b6bf59`; windows 26/52/78 weeks, LCB z 0.5/1.0/2.0, pools H1 / H4 / D1 / H1+H4+D1, m in {1, 2},
  equity filter {none, 26 weeks realised by cut}, min trades 10, NO TRADE when the best score <= 0.
- BASE = (52, 1.0, H1, 2, none). Ranking: score = mean - z x se of shadow net R over the window; ties by candidate hash order
  (sha256 of [tf, setup, mode, k_atr, exit, hold, code sha]).
- Candidate universe: 6,696 candidates (H1 + H4 + D1 x 2,232), ordered candidate-hash digest sha256 `2addef5e7d014bf77b78a78c3218c218ddbd225caa3d9a415dd251692d3cd3f9`.
- Input tables (array sha256): H1 `30aa8a1dc4acb3cf...`, H4 `37123700794b8e69...`, D1 `8f42fad5a4df9a94...`;
  raw Dukascopy manifest sha256 `fda2d483b8fb3bdff8fd137267054af7687aed35f9cc8d03968043667f768e19`; symbols sha `4627adb587949264f4cd3ae8921f5df4b5ab7265f20d04e00298a5b70c4161bf`;
  Treasury sha `ced897410400c41167d2711e942a3fceac2d76f812720c9ea9ace3097560751b`; holiday sha `35a2d982c06c84faa9809c2a9b6073fcff4a2de70b79d7430e0c506854464e8f`; XAG freeze file in data/foundry/xag_cost_freeze.json.
- Code sha256 (LF-normalised): run_family.py `cf82309ec252a080...`; run_bench.py `842eb6220dc57129...`; gates.py `9b87abe4b94903e8...`; portfolio.py `7dff77de961c7c0f...`; contracts.py `6b0261c29621b9b6...`; signals.py `1000a0e36291f8cb...`.

## Endpoints (all after cost and swap, f = 1 %, $10,000, causal historical vol_scale)
1. BASE alone vs its random-router benchmark (10,000 seeded paths): one-sided stationary-bootstrap p <= 0.05 (block 10, K = 999)
   and a positive 95% lower bound of mean weekly d.
2. Family claim: studentized White Reality Check over the 144 configurations on d, p <= 0.05; Stage S (500 paths) screen:
   p >= 0.20 -> not passed, Stage F not run (v6).
3. PBO: upper 95% bound <= 0.20 (CSCV, 16 blocks, 5-week embargo, 999-replicate outer bootstrap).
4. Cost gate for any configuration proposed for the forward record: one-sided 95% lower bound of mean weekly net R > 0 at base cost;
   at +2 bp positive point estimate and max DD <= 1.25 x base DD.
5. XAGUSD (C7) is opened only after endpoints 1-3 are read and the C7 primary / secondary hypotheses are fixed by the rules in C7.
Random seeds: benchmark paths `numpy.random.default_rng([config_index, path_index])` with config_index the position in the frozen
family order (docs family json in data/wrwr/family_XAUUSD.npz); bootstrap seeds: Reality Check 12345, lower bounds 777, PBO outer 2024.

## Sieve (C11) - recorded when the sieve is run, before any real statistic: test-family digest and placebo seeds (pending).

## Amendment (Family 2, 2026-09-30)
`portfolio.load_pool` gained an optional `loader` argument so Family-2 tables can be stacked; behaviour for the zoo family is unchanged (identical weekly R matrices were verified after the earlier optimisation; the Family-1 benchmark and gates use the frozen code as committed before this line). Family 2 is judged by the same endpoints; see docs/WRWR_FAMILY2_PREREG.md.
