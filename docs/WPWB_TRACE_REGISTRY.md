# WPWB trace registry (v1, 2026-09-29)

Every trace used by any WPWB forecast is listed here **before** it is fitted.
Status: `core` (in the model), `shadow` (logged forward, never promoted
retrospectively), `retired`. A new core trace creates a new model version and
starts a new prospective record (Codex Round 6, objection 15).

| id | trace | exact timing at the Friday 22:15 UTC cut | transform | from | target family | status | rationale |
|---|---|---|---|---|---|---|---|
| R1 | XAU H1 realised variance, last week | weeks closed by the cut (close-time rule, spec v2) | log | 2003-05 Dukascopy / 2021-07 Exness | magnitude | core | volatility persists (rho ≈ 0.81) |
| R4 | mean log RV of last 4 weeks | same | mean of logs | same | magnitude | core | HAR medium memory |
| R26 | mean log RV of last 26 weeks | same | mean of logs | same | magnitude | core | HAR long memory |
| G1 | GVZ level | latest Cboe row dated <= Thursday; publication time **not verified** from the stored file | log GVZ² | 2009-09 | magnitude | core | forward-looking implied volatility; onset AUC 0.68 on mined data |
| S1 | price vs 52-week high | last close before the cut ÷ max H1 high of prior 52 weeks | ratio | 2003-05 | magnitude (onset) | shadow | onset AUC 0.67 on mined data; no economic sign imposed |
| S2 | scheduled FOMC / NFP / CPI / PCE next week | MT5 calendar as dumped before the cut | unsigned count | 2022-01 | magnitude | shadow (forward only) | known in advance; no pre-2022 point-in-time schedule held |
| S3 | DXY, US500, XAG realised variance last week | M5 closed by the cut | log ratio to own 52-week median | 2023-09 | magnitude | shadow | too short for development |
| S4 | CFTC managed-money percentile | release timestamp from calendar, else Saturday | percentile | 2021 | magnitude | shadow | failed for direction (Part 37), untested for magnitude |
| S5 | 2-year yield 13-week change | Treasury row dated <= Thursday | absolute value | 2016 | magnitude | shadow | unsigned: magnitude only |
| S6 | intraweek RV since Sunday reopen vs forecast pace | inside the week (after Monday close) | ratio | 2003-05 / 2021-07 | intraweek breaker | shadow until H2 rule frozen | AUC 0.74 for a volatile week on mined data |
| X1 | any signed direction trace (TSM, news surprise sign, CFTC sign, yields sign) | — | — | — | direction | retired for the risk report | 0/40, 0/10 failed; needs its own pre-registration |
