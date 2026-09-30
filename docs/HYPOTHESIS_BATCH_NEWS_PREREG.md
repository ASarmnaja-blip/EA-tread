# Hypothesis batch N — news, geopolitics, Trump posts — pre-registration (2026-10-01; written BEFORE any of these data sets is downloaded)

Operator (2026-10-01): external news moves gold a lot while it rises (Trump, wars, turmoil); Trump likes to move markets at weekends when
the market is closed and Monday opens strongly. Downloads still need the operator's explicit permission; nothing below is run before that.
Research only, paper only.

## Data to download (first-party or public archives; sizes approximate)
- Caldara & Iacoviello daily Geopolitical Risk index (GPRD, GPRD_ACT, GPRD_THREAT), matteoiacoviello.com/gpr.htm, < 5 MB.
- Baker, Bloom & Davis daily US Economic Policy Uncertainty (FRED USEPUINDXD) and daily Trade Policy Uncertainty (policyuncertainty.com), < 2 MB.
- Trump posts with timestamps: Truth Social archive (CNN auto-updated CSV, github.com/stiles/trump-truth-social-archive, 2022-2026) and the
  Twitter archive 2009-2021 (thetrumparchive.com export), < 30 MB.
Causality: a daily index value for date d is used only from the first gold bar opening after 24:00 UTC of d (publication lag ignored in
favour of the stricter rule: never before the day ends); a post is used only after its own timestamp.

## Primaries (gold trades on Dukascopy D1 / H1; costs, stops-first, statistics and drift control exactly as batches 1-3)
| ID | rule | direction |
|---|---|---|
| N2 | GPR spike: GPRD >= its causal 99th percentile (previous 750 days, >= 250) -> gold for 20 D1 bars, stop 3 ATR(D1) | short (fear premium unwinds) |
| N3 | GPR regime: 30-day mean GPRD above its trailing 250-day median at a 21-bar block start -> long gold for the block, else flat | long |
| N4 | policy / trade uncertainty spike: EPU or TPU >= its causal 97.5th percentile -> long gold for 5 D1 bars, stop 2 ATR(D1) | long |
| N6 | Trump market-hours posts containing tariff(s) / China / Fed / Powell / war / Iran / Russia / Israel: gold for the next 12 H1 bars from the first H1 open after the post, stop 1.5 ATR(H1) | two-sided: DEV fixes the sign |
Periods: GPR / EPU / TPU rules: DEV 2004-2015, CHECK 2016-2026, SILVER 2010-2026. Trump rule: DEV = first presidency (2017-01-20 .. 2021-01-08),
CHECK = second presidency (2025-01-20 ..), SILVER = both on silver. PASS as batch 3 (DEV Holm over the four; CHECK p <= 0.05 with excess
over the drift control > 0; SILVER p <= 0.10; net > 0).

## Risk read-outs (not trading rules; reported, never a pass)
- N1: correlation of the weekend GPR change (mean of Saturday-Sunday GPRD minus the Monday-Friday mean, z vs 52 weeks) with the Monday gap
  and with |gap|; N5: the same with the number of Trump posts on Saturday-Sunday (UTC).
- Weekend risk rule: halve the risk of positions held into a weekend when Friday GPRD z > 1 or the week's post count z > 2; report the
  change in the worst 1 % of weekly R and in mean weekly R for the SHADOW configurations.
