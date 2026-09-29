# Regime trace dictionary (21 traces) — frozen with REGIME_MAP_PREREG v2

All traces are computed at the Friday cut C_t from information available then.
H1 bars are used only if their close time is ≤ C_t. "Valid" = week with ≥ 80 H1
bars. Units: bp unless stated. GVZ traces start 2009-09.

| trace | equation | source / as-of | missing rule |
|---|---|---|---|
| sig_ratio | σ_t / median(σ over W_{t-52}..W_{t-1}) | H1 | NaN if σ_t invalid or < 40 valid in the 52 |
| sig4_26 | mean σ (W_{t-3}..W_t) / mean σ (W_{t-25}..W_t) | H1 | ≥ 3 of 4 and ≥ 20 of 26 valid |
| ewma_ratio | √(EWMA-0.75 forecast for W_{t+1}) / median52 | H1, spec-v2 EWMA | invalid weeks carried, never used |
| range_exp | range(W_t) / σ_t | H1 | σ_t valid |
| accel | [RV of W_t over its last 48 h] / RV(W_t) ÷ 0.4 | H1 | σ_t valid |
| gvz_lvl | GVZ_Thu / median(GVZ over the prior 260 trading days) | Cboe, latest row dated ≤ Thursday before C_t; vintage not verified | NaN before 2009-09 or if no row within 6 days |
| gvz_chg | GVZ_Thu / GVZ of the previous admissible Thursday − 1 | Cboe | as above |
| gvz_prem | (GVZ_Thu/100)² / 52 × 1e8 / RV(W_t) | Cboe + H1 | as above |
| r4z, r13z, r26z | Σ weekly log returns over the last L weeks / (mean σ over them / 1e4 × √L) | H1 | L consecutive valid weeks |
| dist_ma50, dist_ma200 | ln(close at C_t / mean of the last 50 / 200 daily closes) / (mean σ13 / 1e4) | daily bars from H1 (22:00 UTC day), days ending ≤ C_t | ≥ L days |
| dist_hi52, dist_lo52 | ln(close / max high or min low of H1 bars closing in (C_t − 52 w, C_t]) / (mean σ13 / 1e4) | H1 | ≥ 1,000 bars in the window |
| streak | signed count of consecutive same-sign weekly returns ending W_t | H1 | an invalid week breaks it |
| up_share8 | share of up weeks among W_{t-7}..W_t | H1 | ≥ 6 valid |
| month | calendar month of C_t (categorical, 12) | calendar | — |
| week_of_month | (day of C_t − 1) // 7 + 1 (categorical, 5) | calendar | — |
| qend_flag | month ∈ {3,6,9,12} and day ≥ 22 (binary) | calendar | — |
| lag_short | W_t had < 100 H1 bars (binary) | H1 | σ_t valid |
