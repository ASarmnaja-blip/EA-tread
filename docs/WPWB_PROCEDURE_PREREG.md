# WPWB procedure test — pre-registration (DRAFT v1, under debate, NOT frozen)

Written by Claude 2026-09-28. v0 was reviewed by Codex (17 objections,
`docs/WPWB_DEBATE_2026-09-28.md`, Round 1); v1 answers them. Nothing here is
run until the draft is frozen with hashes. No order, EA change or PR is
authorised.

## 1. The claim under test (narrowed per objection 1)

> Does frozen selector P, choosing each Friday **one** tool (or flat) from a
> fixed legacy menu of 38 weekly tools using only past data, earn more next
> week than an exposure-matched random choice from the same eligible menu,
> under the same sizing and costs?

A failure says nothing general about WPWB, about M5/M15 conditional tools not
represented in the menu, or about other selectors. A historical success is
development evidence only; confirmation can come only from forward weeks
(section 6). Calendar eras are diagnostics, never gates.

## 2. Inputs (frozen)

- **Bars:** `research/wpwb_live/run_live_hod.combined_bars()` = canonical M5
  (sha256 613d5e74…, 2021-01-03..2026-09-21 08:35) + fresh MT5 M5 after it
  (to 2026-09-28 08:00), H1 via `common.Market`. Input hashes recorded at
  freeze.
- **Cuts:** `Market.cuts` (Friday 22:15 UTC). Week t = [cut_t, cut_t + 7d).
  **Last outcome cut 2026-09-18** (its week ends 2026-09-25 22:15, inside the
  data). Code asserts the final week is complete and rejects any later cut.
- **Menu (38 tools):** the closed search's round 1 (20), round 2 without META
  (10), round 3 (8), parameters and code unchanged. META hl=3/8 are removed
  (a selector does not select a selector).
- **Raw outcome r_{i,t}:** net bp of tool i in week t at Demo90 base costs
  (incl. long swap), summed over its trades; 0 if valid but no trade. Every
  tool's exits are truncated at the week's last bar (`exit_index(.., hi)`), so
  no position crosses a cut — asserted in code. Stress copy at 1.5x costs.
- **Tool validity:** each tool has a declared lookback Lb_i in weeks (from its
  parameters: TSM/TSMI L, HOD/HODM/DOW/SESSION W, VOLMAN 26+52 = 78, DAYREV
  26 + 6, CHOPREV/GAP as their code requires). r_{i,t} is **valid** only if
  cut_t − Lb_i weeks >= first bar. Tools must not silently use a truncated
  window (current `hod_tool` clamps its start to 0 — such weeks are masked
  invalid, not used). The Lb_i table and per-tool validity mask are published
  at freeze; they depend on metadata only, not on outcomes.

## 3. The procedure P (k = 1, no inner tuning)

Fixed constants: SCALE_W = 26, SCORE_W = 26, half-life h = 8 weeks,
MIN_ACTIVE = 13 of 26, SD_FLOOR = 10 bp, TARGET = 100 bp/week, CAP = 3.0.
All chosen before any P outcome was computed; h = 8 is the middle of v0's
grid, not a tuned value.

At each cut w, for each tool i, using only weeks < w:

1. **Scale** (objection 3): sd_{i,t} = sample SD (ddof = 1) of r_{i,s},
   s = t−26..t−1, zero weeks included, defined only when all 26 inputs are
   valid. The historical normalised outcome z_{i,t} = r_{i,t} /
   max(sd_{i,t}, SD_FLOOR) keeps its own contemporaneous scale (never
   rescaled at w).
2. **Eligible at w** iff z_{i,t} exists for all t = w−26..w−1 (so r valid from
   w−52), sd_{i,w} exists, and the tool traded in >= 13 of weeks w−26..w−1.
3. **Score** S_{i,w} = Σ_j a_j z_{i,w−j} / Σ_j a_j, j = 1..26,
   a_j = 0.5^((j−1)/8).
4. **Action:** i* = argmax S over eligible tools (tie: lowest menu index). If
   no tool is eligible or S_{i*,w} <= 0, **flat**.
5. **Size:** s_w = min(CAP, TARGET / max(sd_{i*,w}, SD_FLOOR)); outcome
   P_w = s_w · r_{i*,w} (bp of capital; 0 if flat).

k = 1 removes cross-tool netting, duplicate positions and partial-k ambiguity
(objections 2, 4, 15). With no inner hyper-parameter search there is no
nested warm-up (objection 5): a tool is usable 52 weeks after its first valid
raw week. **First scored cut** = first cut with >= 10 tools eligible by
validity; its exact date is computed from the validity mask (metadata only)
and written here at freeze.

## 4. Primary series and benchmark (objections 7–10)

- **Benchmark B (exposure-matched random choice):** at every cut where P
  trades, B_w = mean over eligible i of s_{i,w} · r_{i,w}, with s_{i,w} from
  the same sizing rule; B_w = 0 when P is flat. B is the exact expectation of
  picking an eligible tool uniformly at random, trading exactly when P does.
  It isolates the value of *which* tool P picks. The always-trading version
  B' is a diagnostic: P vs B' also credits flat timing, but would reward the
  static fact that the menu loses on average.
- **Primary series** d_w = P_w − B_w at base cost; d^{1.5}_w at 1.5x costs.
- v0's circular-shift placebo is **dropped**. No historical p-value is called
  evidence (objection 11).

## 5. Historical run — descriptive, plus one resource screen

Reported: mean d (base, 1.5x) with HAC-8 SE, cumulative d, P vs B', P vs
risk-matched always-long, turnover, flat share, chosen-family shares, per-era
means (2021–2023 / 2024–2026), leave-one-26-week-block-out means, and a causal
(expanding past-only) volatility-tercile breakdown. Diagnostics cannot change
P; any change is a new procedure P2 (objection 17).

**Resource screen (not a significance test):** start the forward shadow only
if mean d > 0 at base **and** at 1.5x, and mean d > 0 in >= 60% of
leave-one-26-week-block-out recomputations. Otherwise P is closed as failed
and reported.

**Before the historical run** (objection 16): a simulation harness runs the
complete P on (a) nulls — each tool's r demeaned to the per-week menu mean so
no tool has an edge over B, then common circular-block resampling (block 8)
of whole weeks across all tools to keep cross-tool dependence, volatility
clustering and fat tails, plus a drift-break variant; (b) planted edges — one
tool family gets +5/+10/+20 bp per week in random 13-week regimes (switching),
and a decaying variant. Reported: false-screen rate, screen power, forward
e-process power and median time-to-detection at 52/104/156 weeks. The screen
is not tightened after seeing the data.

## 6. Forward confirmation (objections 12–13)

- Freeze: code, config, tool manifest, input snapshot and dependency hashes
  recorded here before 2026-10-02 22:15 UTC.
- Every Friday cut from 2026-10-02 the shadow records P's choice, B, and next
  week's outcomes from live MT5 data (no orders).
- **Test variable:** x_w = clip(d_w, −c, c) / c, c = 3 × SD of historical d
  (base), fixed at freeze. Margin m = 2 bp / c.
- **H0:** E[x_w | past] <= m for every w.
- **E-process:** E_t = (1/5) Σ over λ in {0.05, 0.1, 0.2, 0.3, 0.5} of
  Π_{w<=t} (1 + λ (x_w − m)). Every factor is > 0 since x >= −1. Reject H0
  when E_t >= 1/alpha_P = 40. Uncapped economic P&L is reported alongside.
- **Promotion also requires** forward mean d^{1.5} > 0. Promotion means
  "candidate for Demo execution testing", never real money without the
  operator's explicit per-order confirmation.
- Safety stops (e.g. forward drawdown) may end the shadow but never restart
  the same test; any changed P is P2 with its own ledger allocation and no
  reuse of P's forward weeks.
- Alpha budget: `docs/ALPHA_LEDGER.md` (created with this freeze).

## 7. Look-ahead defences (objection 14)

- Scale and score come from an explicit lagged function f(r[:, :w]); full
  per-cut state (eligible set, scores, sizes, choice) is cached.
- Future-garbage test on the **complete** P: for 50 random w, replace every
  r_{·, t>=w} and all bars after cut_w with garbage; choice and s_w at w must
  be identical.
- Final-week completeness assertion; validity-mask assertion; no full-sample
  quantile anywhere in P.

## 8. Known weaknesses (Claude)

- All 38 menu tools failed individually and the menu was shaped by 2021–2023
  DEV. P over weak tools may be noise — then P should fail.
- Tool-performance persistence is the whole bet; Part 31 found direction
  persistence ~0.
- The forward e-process will likely need years to reach 40 for a modest
  edge; the harness reports how many.
