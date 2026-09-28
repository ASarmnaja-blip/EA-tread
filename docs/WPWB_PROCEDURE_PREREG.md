# WPWB procedure test — pre-registration (DRAFT v2 — CLOSED 2026-09-28 before outcome evaluation)

> **Status:** H-WPWB-P1 abandoned before any real-data evaluation for
> inadequate prospective power (debate Round 3). The real P, B' and d were
> never computed. Alpha 0.025 returned unspent. Kept as the record of the
> design and its harness.

Written by Claude 2026-09-28. v0 → 17 Codex objections (Round 1); v1 → 9
named edits (Round 2); v2 implements all nine. Debate record:
`docs/WPWB_DEBATE_2026-09-28.md`. Code: `research/wpwb_procedure/`. Nothing
here evaluates P on real data until the draft is frozen with the hash
manifest. No order, EA change or PR is authorised.

## 1. The claim under test

> Does frozen selector P — each Friday choosing **one** tool, or flat, from a
> fixed legacy menu of 38 weekly tools using only past data — earn more next
> week than choosing one currently eligible tool uniformly at random every
> week (B'), under the same sizing and costs, while also being profitable on
> its own at 1.5x costs?

This tests a one-champion policy over this hindsight-shaped menu only. A
failure says nothing general about WPWB, about M5/M15 conditional tools not
in the menu, or about multi-sleeve portfolios. A historical success is
development evidence only; confirmation comes only from forward weeks
(section 6). Calendar eras are diagnostics, never gates.

## 2. Inputs (frozen)

- **Bars:** `run_live_hod.combined_bars()` = canonical M5 (sha256 613d5e74…)
  + fresh MT5 M5 after it (to 2026-09-28 08:00), H1 via `common.Market`.
  Canonical rows before 2021-07 are sparse (~116 bars/week), so **usable H1
  starts 2021-07-02 10:00 UTC**; first cut 2021-07-02 22:15.
- **Cuts:** Friday 22:15 UTC; week t = [cut_t, cut_t + 7 d). 273 complete
  cuts, **last outcome cut 2026-09-18 22:15** (asserted; an incomplete final
  week raises).
- **Menu (38 tools, frozen order)**, lookback Lb in weeks (worst case read by
  the code before a cut); a tool-week is lookback-valid iff cut − Lb weeks >=
  first H1 bar. Invalid weeks are masked, never run on a truncated window.

  | idx | tools | Lb | first valid cut |
  |---|---|---|---|
  | 0–3 | TSM L=4, 8, 13, 26 | L+1 | 2021-08-06 … 2022-01-07 |
  | 4–7 | HOD W=26 T=2,3; HOD W=52 T=2,3 | W | 2021-12-31; 2022-07-01 |
  | 8–9 | DOW W=52 T=1.5, 2 | 52 | 2022-07-01 |
  | 10–13 | CHOPREV (gated) z=1.5/2.5 H=2/6 | 5 (20 UTC dates + ATR14) | 2021-08-06 |
  | 14–17 | CHOPREV-ungated z=1.5/2.5 H=2/6 | 1 | 2021-07-09 |
  | 18–19 | GAP k=0.5, 1 | 53 (52 past cuts) | 2022-07-08 |
  | 20–21 | HODM W=52 T=2, 3 | 52 | 2022-07-01 |
  | 22–25 | SESSION W=52 T=1.5/2; W=104 T=1.5/2 | W | 2022-07-01; 2023-06-30 |
  | 26–29 | DAYREV z=1/1.5 N=1/2 | 32 (26 w + 40 d) | 2022-02-11 |
  | 30–31 | TSMI L=8, 13 | L+1 | 2021-09-03; 2021-10-08 |
  | 32–33 | VOLMAN hl=4, 13 | 78 (26-w sigma at 52 past cuts) | 2022-12-30 |
  | 34–37 | CHOPREV-X z=3/4 H=2/6 | 1 | 2021-07-09 |

  META hl=3/8 are excluded (a selector does not select a selector).
- **Outcome matrix** (`build_matrix.py` → `data/wpwb_procedure_matrix.npz`):
  R10 / R15 = net bp per tool-week at Demo90 base / 1.5x costs (1.5x scales
  spread, commission and slippage, **not swap**); 0 if valid and no trade.
  NTR = trade count. INNER = the tool's own past-known multiplier (VOLMAN's
  size, 1 otherwise; already inside R). Verified: every trade enters and
  exits inside its own week; no tool holds two positions at once.

## 3. The procedure P (k = 1, no inner tuning)

Constants: SCALE_W = 26, SCORE_W = 26, HALF_LIFE h = 8, MIN_ACTIVE = 13,
SD_FLOOR = 10 bp, TARGET = 100 bp/week, CAP = 3.0 (total notional multiple).
h = 8 is one of the two values META already used — a development choice,
not a neutral constant. MIN_ACTIVE is fixed, not calibrated (calibrating it
on the real matrix would add a tuned knob). All decisions use base-cost
history only.

At each cut w, using only columns < w, the metadata mask, and INNER[:, w]:

1. **Scale:** sd_{i,t} = sample SD (ddof 1) of r_{i,t−26..t−1}, zero weeks
   included; defined only when all 26 are lookback-valid.
   z_{i,t} = r_{i,t} / max(sd_{i,t}, 10) with its own contemporaneous scale.
2. **Eligible at w** iff z_{i,t} exists for all t = w−26..w−1 (so r valid
   from w−52), sd_{i,w} exists, the tool traded in >= 13 of w−26..w−1, and
   it is lookback-valid at w.
3. **Score** S_{i,w} = Σ_{j=1..26} a_j z_{i,w−j} / Σ a_j, a_j = 0.5^((j−1)/8).
4. **Action:** i* = argmax S over eligible (tie → lowest index); flat if
   none eligible or S_{i*} <= 0.
5. **Size:** s_{i,w} = min(3 / INNER_{i,w}, 100 / max(sd_{i,w}, 10)), so
   total exposure <= 3x. P_w = s_{i*,w} · r_{i*,w}; 0 if flat.

**First scored cut** (metadata only): first w with >= 10 tools lookback-valid
on w−52..w → **index 57 = 2022-08-05 22:15 UTC; 216 scored weeks** to
2026-09-18. Only 5 tools meet full (activity) eligibility that week; this is
reported, not used to move the date.

## 4. Primary series and benchmarks

- **B' (primary):** B'_w = mean over eligible i of s_{i,w} · r_{i,w} — the
  exact expectation of trading one eligible tool chosen uniformly at random,
  every week; 0 if no tool is eligible. **d_w = P_w − B'_w.**
- **B (diagnostic):** B'_w when P trades, 0 when P is flat — isolates which
  tool P picks, conditional on trading.
- Evaluated on the one base-cost decision path at base (d) and 1.5x (d^1.5).
- No historical p-value is called evidence.

## 5. Historical run — descriptive, plus a resource screen

**Pre-run harness (done before the historical P result; `harness.py`):**
complete P on (a) the exact null — per-week permutation of tool identities
among valid rows, jointly for (R10, R15, NTR), after centring each week's
traded cells, untraded cells kept 0, INNER := 1, giving E[d_w | past] = 0
exactly; (b) a drift-stress null — same permutation, no centring; (c) planted
edges of +5/+10/+20 bp per traded week on one random family: persistent,
switching (13-week regimes on w.p. 0.5), decaying (half-life 52 weeks).
Seed 20260928, 1000 replicates per scenario. Results: section 9.

**Reported for the real run:** mean d and d^1.5 with HAC-8 SE, cumulative d,
mean P (base, 1.5x), P vs B (conditional), P vs risk-matched always-long,
turnover, flat share, chosen-family shares, effective menu (tools ever
eligible, eligible weeks per tool), per-era means (2022-08..2023-12 /
2024-01..2026-09), 26-week block means, expanding past-only volatility
terciles (tercile edges at w from rebuild-week H1 realised vol of all weeks
< w, starting once 52 weeks exist). Diagnostics cannot change P; any change
is P2.

**Resource screen (not a significance test).** Start the forward shadow only
if ALL hold:
1. mean d (base) >= 2 bp/week;
2. mean d^1.5 > 0;
3. mean P^1.5 > 0 (absolute profitability at stressed cost);
4. >= 60% of 26-week blocks have mean d > 0. Blocks: non-overlapping from the
   first scored week, remainder merged into the last (216 = 7 × 26 + 34 → 8
   blocks, need 5).
Otherwise P is closed as failed and reported. Thresholds are not changed
after the historical result.

## 6. Forward confirmation

- Freeze before 2026-10-02 22:15 UTC with the `freeze_manifest.py` output
  (code, inputs, matrix, constants, versions) pasted in section 10.
- Every Friday cut from 2026-10-02 the shadow records P's choice, B', B and
  next week's outcomes from live MT5 data. **No orders.**
- **Test variable:** x_w = clip(d_w, −c, c) / c, c = max(3 · SD(historical
  d), 20 bp), fixed at freeze. Margin m = 2 bp / c <= 0.1.
- **H0 (clipped excess):** E[clip(d_w, −c, c) | past] <= 2 bp for all w.
- **E-process:** E_t = (1/5) Σ_{λ ∈ {0.05, 0.1, 0.2, 0.3, 0.5}}
  Π_{w<=t} (1 + λ (x_w − m)); every factor >= 0.45. Flat and no-eligible
  weeks update with their d; a missing week stops the test (no silent skip).
  Reject H0 when E_t >= 1/alpha_P = 40.
- **Promotion** additionally requires forward mean P^1.5 > 0 and forward mean
  d^1.5 > 0. Promotion = candidate for Demo execution testing only; never real
  money without the operator's explicit per-order confirmation.
- Safety stops may end the shadow but never restart the same test; any
  changed P is P2 with its own ledger allocation and no reuse of P's forward
  weeks. Budget: `docs/ALPHA_LEDGER.md` (H-WPWB-P1, alpha 0.025).

## 7. Look-ahead defences (all passing)

- `test_future_garbage_synthetic` and `test_future_garbage_real_matrix` (50
  real cuts): mutating R, NTR (columns >= w), VALID and INNER (columns > w)
  leaves eligibility, scores, choice and size at w identical.
- `audit_builder.py`: for 12 random cuts, a random walk replaces every bar
  after the week's end; all 38 tools' r, NTR and INNER at that week are
  unchanged (12/12).
- `test_fast_equals_reference`: the vectorised simulator equals the reference
  implementation.
- Final-week completeness and validity-mask assertions; no full-sample
  quantile anywhere in P.

## 8. Known weaknesses (Claude)

- All 38 menu tools failed individually and the menu was shaped by 2021–2023
  DEV. P over weak tools may be noise — then P should fail.
- Several tools are rarely or never eligible (MIN_ACTIVE); the effective
  competition is smaller than 38.
- The null keeps each week's cross-tool distribution but not tool-specific
  scale persistence (a permuted row mixes tools of different scale); this
  makes sizing noisier under the null than for real tools.
- Harness e-process power uses the first 52/104/156 scored weeks of each
  replicate as a stand-in for forward weeks and c from the same replicate.

## 9. Harness results

Run 2026-09-28, `harness.py` (seed 20260928, 1000 replicates/scenario) and
`harness_mde.py` (seed 5, 200 replicates). Scrambled data only; P was not
evaluated on the real matrix.

| scenario | screen pass | mean d (bp) | e-process >= 40 within 156 w |
|---|---|---|---|
| exact null (centred) | 0.281 ± 0.014 | −0.05 ± 0.24 | 0.000 |
| drift-stress null | 0.271 | +0.38 | 0.000 |
| persistent +5 / +10 / +20 | 0.281 / 0.292 / 0.348 | −0.06 / +0.39 / +1.73 | 0.000 |
| switching +5 / +10 / +20 | 0.288 / 0.288 / 0.289 | +0.15 / +0.31 / +0.48 | 0.000 |
| decaying +20 | 0.311 | +0.47 | 0.001 |
| persistent +50 (MDE run) | 0.70 | +10.2 | 0.03 |
| persistent +100 | 0.98 | +34.3 | 0.72 |
| persistent +200 | 1.00 | +64.6 | 0.99 |

Planted-family pick rate: 0.20 at +20, 0.40 at +50, 0.67 at +100, 0.81 at
+200. Tool weekly SD: median 84 bp (14..239), median activity 0.49.

**Correction (Round 3, Codex).** The rows above plant e per *traded* cell,
i.e. roughly e × activity (0.4–0.5) per calendar week; the null mixes tool
scales and set INNER := 1 while R kept VOLMAN's sizing; and c came from the
same realisation used as "forward". These bias power down. Codex's
identity-preserving sign-randomised harness with an independent 156-week
forward and +e per *calendar* week gives: null screen 24.2%, +10 bp screen
39.2% / forward 1.8%, +20 bp screen 57.4% / forward 12.2%
(`codex_checks/round3_power.py`). The conclusion survives in narrower form:
**this P1 is inadequately powered for 10–20 bp/week**, not "all weekly P&L
ranking is incapable".

**Original reading (superseded wording):** the null is correctly centred (mean d −0.05 ± 0.24) and the
e-process never falsely confirms, so the machinery is valid. But the design
is **powerless for plausible edges**: the screen passes 28% of exact nulls
and only 35% with a persistent +20 bp/traded-week edge; forward confirmation
within three years needs roughly +100 bp per traded week (~1.2 tool-SD per
week). Reason: 26 weekly P&L points per tool cannot rank ~20 eligible tools
when a plausible edge is a fraction of the weekly SD — the maximum of the
noise wins. See Round 3 of the debate for what follows from this.

## 10. Freeze manifest

(to be filled from `freeze_manifest.py` at freeze)
