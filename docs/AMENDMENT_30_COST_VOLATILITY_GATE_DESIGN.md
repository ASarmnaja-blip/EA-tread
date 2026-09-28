# Amendment 30 — regime-conditioned cost-to-R gate: design and pre-registration

**Written 2026-09-28, before any Amendment 30 code or result.** Pre-
registration only, in the ownership sixth-revision Claude-leads format. This
document authorizes no run, no cache build, no Demo or real order, no
autotrader change, and no PR. Everything below is a design to be reviewed,
not a result.

**Disclosure on how this document was produced.** It was written in a
sandboxed research session whose working tree does not contain
`research/pilot/`, `docs/OWNERSHIP.md`, `docs/LOGIC_LEDGER.md`, or `data/` —
that worktree was branched from an older, unrelated line of this repository
(the MQL5/Dobby-indicator work) before the `research/pilot` program existed.
The commit that holds the current state of that program
(`76d6b58`, `claude/claude-md-project-file-qh0ier`, "Part 25 — existing news
acceptance/rejection test also fails at development") was reachable only by
its object hash from that worktree, not by branch or by file on disk, and the
canonical dataset (`data/canonical_XAUUSD_M5.npz`, gitignored) was not
reachable at all. `docs/OWNERSHIP.md`, `docs/LOGIC_LEDGER.md` Parts 18–25,
`docs/AMENDMENT_24_COST_TO_R_GATE.md`, `docs/AMENDMENT_24_RESULT.md`,
`docs/AMENDMENT_28_REGIME_STANDASIDE.md`, `docs/AMENDMENT_28_RESULT.md`,
`research/pilot/mtf_engine.py`, `research/pilot/check_fake_edge.py`,
`research/pilot/regime_standaside.py`, and `research/pilot/core.py` were read
via `git show <hash>:<path>` against that reachable commit — their content is
quoted accurately below, but this design was **not written or reviewed
inside a checkout that also has the canonical data present**, and Part B of
the exploratory diagnostic (section 2) could not be executed against real
XAUUSD history as a result. This is stated here in full rather than worked
around, because a design document that quietly skipped this would be worse
than one that says so. Section 2 states exactly what did and did not run.

**Editor's note (added when copying this design into the main working
tree, same day):** Part B was subsequently run against the real canonical
history — see the note appended at the end of section 2.

## 1. Why this, stated honestly

`docs/OWNERSHIP.md`'s "next (Claude-led)" step, written after Amendment 27
was frozen, names the open problem directly:

> a new pre-registered design attacking the actual open problem — cost
> relative to volatility/stop size at low-volatility regimes — since gating
> on cost/R alone (Amendment 24) was not enough.

Two prior amendments already touch this exact question and both are
already-published, already-audited evidence this design must be read
alongside, not in place of:

- **Amendment 24** (`docs/AMENDMENT_24_COST_TO_R_GATE.md`) added a flat
  cost-to-R ceiling — `execution_friction_price / (stop_ATR_multiple * ATR)
  <= 1/12` at base cost, `<= 1/8` at 1.5x stress — applied identically
  regardless of the surrounding volatility regime. Its own result
  (`docs/AMENDMENT_24_RESULT.md`) shows the ratio is not regime-blind by
  accident: the 44-month window (net R **−66.664** base / **−104.467** 1.5x)
  had a 60.60% gate-cancellation rate and 262.0%/364.7% cost share of gross
  edge, against the trailing 12 months' 24.11% cancellation rate and
  69.0%/101.2% cost share. Section 4 of that result reports the gate widened
  the **median accepted stop to $4.68** in the 44-month window versus **$6.00**
  in the trailing year — a ~22% smaller typical stop in the window that
  failed, i.e. lower realised volatility survived the gate but still lost.
- **Amendment 28** (`docs/AMENDMENT_28_REGIME_STANDASIDE.md`,
  `docs/AMENDMENT_28_RESULT.md`) already tested one causal, frozen response
  to this: a **whole-week stand-aside** when a trailing-year H1-ATR
  percentile fell below 0.40. It helped (+10.9 R base / +15.7 R stress in the
  44-month window, byte-for-byte no change to the already-positive trailing
  12 months) but did **not** flip the 44-month verdict (still −69.467 /
  −93.428). Its own reading states the natural next step in so many words:
  *"A cost-vs-volatility fix at the trade level (e.g., volatility-scaled
  targets) remains untried and is a candidate for a future amendment."*

Amendment 30 is that trade-level design: instead of standing an entire week
aside, condition the **existing** per-trade cost-to-R ceiling itself on the
same causal regime measure, so the ceiling tightens specifically for signals
generated in an unfavourable regime, rather than blocking every signal that
week regardless of its own stop.

**The overriding risk this design must not ignore.** `docs/LOGIC_LEDGER.md`
Part 22 and Part 24 (independently, by two different methods) and Part 25
found that **all seven setup ideas tried in this project's 8,250-cell grid —
`sweep`, `expansion`, `vwap`, `failed`, `breakout`, `pullback`, and a
separate news-acceptance/rejection mechanism — fail an unconditional
real-vs-random baseline check** (`research/pilot/check_fake_edge.py`'s
method). Amendment 24's own basket is built from exactly this pool. Any
design that only reduces trade count in the worst-cost regime will look like
it "improves" mean net R for the boring reason that removing already-bad
trades raises the average of what remains — with **no connection to any real
directional edge**, since there may be none in this pool to begin with. This
design's own success criterion (section 6) is built specifically to catch
that trap, not just to report a better net R.

## 2. Exploratory diagnostic (NOT pre-registered, NOT decisive)

Script: `research/pilot/cost_volatility_diagnostic.py`. Read-only, no order
path, no MT5 connection. It has two independent parts.

### Part A — closed-form, always runs, executed in this session

Amendment 24's own gate formula (`execution_friction_price = max(spread,
0.090) + 0.140 + 2*0.0165 = $0.263` base, `$0.395` at 1.5x stress) was
evaluated across an ATR grid from $1.00 to $8.00 (chosen to straddle the two
real median-stop figures above: $4.68 and $6.00) at each of Amendment 14's
five frozen stop multiples (0.75/1.0/1.5/2.0/3.0). This ran successfully in
this session; full table is reproducible by running the script.

**Result: the premise is arithmetically true and not small.** At ATR=$2.00,
stop=0.75, base cost/R is 0.1753 — already outside Amendment 24's own 1/12
ceiling. At ATR=$6.00, the same stop multiple's ratio falls to 0.0584,
comfortably inside it. The identical fixed $0.263 friction is therefore
**3x** as large a fraction of R at ATR=$2 as at ATR=$6, for the same stop
multiple, exactly the mechanism `docs/OWNERSHIP.md` names. Applying the
proposed Amendment 30 step-gate (section 4) at an illustrative low reading
(regime_percentile = 0.20, ceiling halved to 0.0417 base / 0.0625 stress)
shows the 0.75-ATR stop multiple fails **across the entire $1–$8 grid** —
i.e. the tightest stop is functionally retired in an unfavourable regime,
while the 2.0 and 3.0 multiples still open up once ATR is high enough. At a
favourable reading (0.80, ceiling unchanged), only 7 of 15 ATR levels have
any failing multiple, matching Amendment 24's unconditioned behaviour by
construction (this is a deliberate design property, not a finding — see
section 4).

**This is arithmetic on frozen constants, not a strategy result.** It shows
the mechanism is well-defined and does what it claims. It says nothing about
whether any setup has real edge in the regime it would now admit more or
fewer trades from.

### Part B — empirical bucketing on real canonical history

The script's Part B reuses Amendment 28's already-audited causal regime
measure unchanged (`research/pilot/regime_standaside.py`:
`build_regime_series`, `regime_percentile_at` — trailing-20-trading-day
median H1 ATR ranked within the trailing-365-day H1 ATR distribution) to
bucket real M5 bars by regime percentile and report the empirical cost/R
distribution and median ATR per bucket, at a daily (not per-trade) cadence
for diagnostic speed.

**Editor's addendum, run on the main working tree, same day, against the
real canonical snapshot.** (Correction: an earlier version of this addendum
contained numbers that were written before the script had actually been
run — a mistake, caught and fixed before this document was committed. The
table below is the genuine, verified console output of
`research/pilot/cost_volatility_diagnostic.py`, reproduced exactly.)

```
loaded canonical M5: 372,614 bars, 1609632000 .. 1789979700

                      bucket    n_bars   s=0.75 base      s=1 base    s=1.5 base      s=2 base      s=3 base
                  no-history     8,880        0.2779        0.2084        0.1389        0.1042        0.0695
       < 0.40 (A30 tightens)    58,425        0.3984        0.2988        0.1992        0.1494        0.0996
>= 0.40 (unchanged from A24)   305,309        0.1979        0.1484        0.0989        0.0742        0.0495

median ATR(14), $, by bucket:
                    no-history: n=     8,880  median ATR=$1.262
         < 0.40 (A30 tightens): n=    58,425  median ATR=$0.880
  >= 0.40 (unchanged from A24): n=   305,309  median ATR=$1.772
```

This confirms Part A's arithmetic against real history, though at smaller
scale than the illustrative $4.68/$6.00 figures cited in section 1 (those
were Amendment 24's median stop among its own *gate-accepted trades*, a
different, already-filtered population — not all raw M5 bars, which is what
this diagnostic buckets): **only 15.7% of bars with a computed percentile
(58,425 of 372,614) sit in the regime Amendment 30 would tighten**, not the
larger share a naive reading of section 1's figures might suggest. Within
that smaller share, the effect is real and consistent in direction: median
cost/R at stop=0.75 is 0.3984 in the low-regime bucket versus 0.1979 in the
unchanged bucket (~2.0x), and median ATR roughly doubles the other way
($0.88 vs $1.77). **Part B's premise check passes on direction and
magnitude-within-bucket, but the affected share of history (15.7%) is
smaller than section 1's Amendment-24-derived figures imply** — this is
noted here plainly rather than smoothed over, and should inform how much
improvement section 7's decisive test can plausibly show even if Amendment
30's gate works exactly as designed: at most ~16% of raw bars are directly
affected, before any setup-level signal filtering is even applied.

## 3. Hypothesis

> A cost-to-R gate whose ceiling is conditioned on the causal
> `regime_percentile` measure already validated in Amendment 28 — tighter
> when the trailing regime is unfavourable, unchanged otherwise — will reject
> a larger share of low-regime-percentile candidate trades than Amendment
> 24's flat gate does, and applying it should measurably improve realised net
> R in an honest causal walk-forward test **without merely thinning an
> edgeless population**, i.e. it must clear a real-vs-random control the flat
> gate is not currently required to clear (section 6).

## 4. Candidate functional forms considered, and which was picked

Three forms for `T(regime_percentile)` were considered before picking one, to
document that this was not searched down to the best-looking option:

1. **Step function reusing Amendment 28's frozen 0.40 cutoff, halved ceiling
   below it** (chosen): `T(p) = ceiling * 0.5` if `p < 0.40`, else `ceiling`
   unchanged. Reuses a threshold that was itself frozen *before* Amendment 28
   ran and explicitly *not* tuned to reproduce any known-good split
   (`docs/AMENDMENT_28_REGIME_STANDASIDE.md` section 3: "deliberately not
   tuned... a round, sub-median cutoff"). The 0.5 multiplier is likewise a
   round, pre-declared number, not fit to any outcome — no sweep over
   alternative multipliers or cutoffs is authorized inside this amendment,
   matching Amendment 24 section 12 and Amendment 28's own closing
   discipline.
2. **Continuous linear ramp below the cutoff**: `T(p) = ceiling * clip(p /
   0.40, 0.5, 1.0)` for `p < 0.40`. Smoother, avoids a discontinuity at
   `p=0.40`. **Rejected for this design**: it adds a second implicit
   parameter (the ramp's shape) with no more justification than the step's
   multiplier, while making the paired comparison against Amendment 24 (which
   this design needs clean, section 5) harder to attribute — a continuous
   change touches every trade near the boundary, not just the ones the
   hypothesis is about.
3. **Continuous linear function over the full percentile range**: `T(p) =
   ceiling * (0.5 + 0.5*p)`, always at least somewhat stricter than Amendment
   24, relaxing to it only at `p=1`. **Rejected**: it changes behaviour even
   in already-favourable regimes where Amendment 24's flat gate was not
   flagged as the problem, contaminating any paired comparison and reopening
   a second free parameter (the intercept) with no independent grounding.

Option 1 was picked because it changes exactly one thing relative to the
already-frozen Amendment 24/28 machinery, reuses an already-audited,
already-not-tuned-to-outcome threshold, and keeps the comparison in section 5
clean: everything at or above `p=0.40` is provably identical to Amendment 24
by construction, so any measured difference is attributable to the tightened
low-regime ceiling alone.

## 5. The exact proposed gate

Retains Amendment 24 (universe, causal fill-time chain from Amendment 26,
weekly LCB-shrinkage ranking and basket construction, Demo90 cost profile)
and Amendment 26's causal chain (`research/pilot/causal_chain.py`)
**unchanged**. The only addition:

```text
# at the first otherwise-valid fill for a candidate opportunity, signal
# timestamp t_sig (the same timestamp already used for the fill-time chain):

h1_t, atr_h1 = regime_standaside.build_regime_series(b5)          # unchanged
pct, _ = regime_standaside.regime_percentile_at(h1_t, atr_h1, t_sig)  # unchanged

base_ceiling   = (1/12) * (0.5 if (pct is None or pct < 0.40) else 1.0)
stress_ceiling = (1/8)  * (0.5 if (pct is None or pct < 0.40) else 1.0)

# unchanged from Amendment 24:
base_friction_R   = execution_friction_price / stop_price_distance
stress_friction_R = 1.5 * base_friction_R
admit  =  (base_friction_R <= base_ceiling) and (stress_friction_R <= stress_ceiling)
```

`pct is None` (insufficient trailing H1 history) is treated as unfavourable,
identically to Amendment 28's own convention — this is not a new judgment
call, it is the existing one, reused.

Unlike Amendment 28, `regime_percentile_at` is evaluated **at each
candidate's own signal timestamp**, not once per Weekend Rebuild cutoff. This
is the trade-level resolution `docs/AMENDMENT_28_RESULT.md`'s reading asked
for, and it is causal by the same proof Amendment 28 already carries (the
function only ever reads H1 bars strictly before its `cutoff` argument;
calling it more often does not change that proof, only its number of call
sites). Section 7 requires a fresh mutation-invariance audit at this new call
cadence rather than assuming Amendment 28's audit transfers unexamined.

Everything else — candidate universe (6 families × 5 timeframes × 5 stops × 5
targets × 11 entry modes), causal fill-time chain, three-week half-life
LCB-shrinkage ranking, 26-week/8-nonzero-week eligibility, 3–5 member basket,
one member per family, correlation ≤ 0.70, weights 10–35%, Demo90 costs — is
retained byte-for-byte from Amendment 24/26.

## 6. Data window, split, and causal-chain compliance

Same windows Amendment 24/26/28 already used, for direct paired comparison
and because this design is explicitly **NOT BLIND** to them (see section 1):

- 2022-01-01 00:00 UTC – 2025-09-21 00:00 UTC ("44-month", already seen,
  informed development window);
- 2025-09-21 00:00 UTC – canonical end ("trailing 12m", already seen);
- the combined full window.

All three replay `research/pilot/causal_chain.py`'s fill-time chain
(`causal_indices`/`causal_gated_indices`), not the legacy signal-order chain
Amendment 26 superseded — this is a hard requirement, not a preference, per
`docs/AMENDMENT_26_CAUSAL_FILL_TIME_CHAIN.md`'s own stated purpose. Genuine
out-of-sample confirmation can only come from forward weeks after this
document's freeze date (2026-09-28 onward) or a separately sealed dataset —
replaying the existing canonical history, at any window, is development
evidence and will be labelled as such every time it is reported, exactly as
Amendment 24 section 1 requires.

**Forward path, once reviewed and frozen:** run as an additional read-only
shadow arm alongside Amendment 27's existing frozen A24 forward ledger — not
a replacement for it — under the same discipline Amendment 27 already
established (inactive optional Demo mirror only, clock starts at the next
Weekend Rebuild after this document is committed and reviewed, no live
policy change until genuine forward confirmation exists).

## 7. Pre-registered success criterion

Amendment 30 is a **development success** — eligible to move toward a forward
shadow arm, nothing more — only if **all** of the following hold. Any one
failing is a plain, reported failure, not a reason to adjust the design.

1. **Unit-risk net R positive** at base **and** 1.5x cost, in **both** the
   44-month and trailing-12m windows (Amendment 24 section 11's own bar,
   unchanged).
2. **Paired improvement over Amendment 24 on the identical engine** (same
   universe, same causal chain, same basket rules — only the ceiling formula
   differs): the 44-month window's net R improves, and the trailing-12m
   window's net R does not turn negative. Reported as paired weekly
   differences in net R, gross R, cost R, trade count, and MTM DD — an
   aggregate "it got better" number alone is not sufficient.
3. **The real-vs-random control, required by this design specifically because
   of the Part 22/24/25 finding in section 1** (`research/pilot/
   check_fake_edge.py`'s method, extended to the full Amendment 24 gate
   rather than one setup): build an unconditional random-entry population of
   the same size, in the same window, using the same ATR-derived stop
   distances and the same entry/fill mechanics as the real six-family
   population, with no setup logic at all. Run **both** the Amendment 24 flat
   gate and the Amendment 30 step gate over the random population exactly as
   over the real one. Compute:

   ```text
   real_gap   = net_R(A30, real setups)   − net_R(A24, real setups)
   random_gap = net_R(A30, random entries) − net_R(A24, random entries)
   ```

   **Amendment 30 passes this check only if `real_gap` is both distinguishable
   from, and clearly larger than, `random_gap`** (reported with a block
   bootstrap CI on the difference, `research/pilot/core.py`'s
   `block_bootstrap_ci` reused unchanged, block size 12 per its existing
   convention). If `random_gap` is comparable to or larger than `real_gap`,
   Amendment 30 is a **generic low-regime trade-frequency filter with no
   demonstrated connection to any real directional edge**, and fails —
   regardless of what the real population's raw net R looks like in
   isolation. This criterion exists specifically so a mean-net-R improvement
   produced only by discarding already-edgeless trades cannot be mistaken for
   a working design.
4. All causality/mutation audits in section 8 pass.
5. At least half of forward weeks in each required window still contain a
   resolved basket trade (Amendment 24 section 11's evidence-floor
   requirement, retained so the gate cannot pass by trading almost never).

## 8. Required audits (before any result is reported)

1. Every existing Amendment 24/26 audit (section 10 of
   `docs/AMENDMENT_24_COST_TO_R_GATE.md`; causal fill-time chain tests) must
   still pass unmodified.
2. **New**: mutation-invariance of `regime_percentile_at` when called at
   per-signal cadence rather than per-week — mutating bars strictly after a
   given signal's timestamp must not change that signal's computed
   `pct`. This re-derives Amendment 28's own audit at the new call frequency
   rather than assuming it transfers.
3. **New**: a constructed boundary case at `pct` exactly on either side of
   0.40 must show the ceiling switching discretely and only there — no
   smoothing, no off-by-one in the `<` vs `<=` boundary.
4. **New**: the random-entry control (section 7 item 3) must itself pass the
   existing no-look-ahead / resampling / Bid-Ask / ambiguous-bar test suite,
   since it is new code, not a re-run of `check_fake_edge.py` as-is (that
   script tests one family/stop combination; this needs the full six-family,
   five-stop, five-target grid population).
5. Full content/code/cost hash on any new cache, per Amendment 24 section 5's
   standing rule — no silent cache reuse across a code change.

## 9. What this design does NOT test, stated plainly

- It does not test any regime measure beyond Amendment 28's H1-ATR
  percentile (no DXY/yield correlation, liquidity proxy, narrative, or
  positioning signal — CLAUDE.md gap #2 remains open beyond price/volatility,
  exactly as `research/pilot/regime_stability_score.py`'s own v1 already
  disclosed).
- It does not sweep the 0.40 threshold or the 0.5 multiplier — both are
  frozen here and any change requires a new amendment starting its own NOT
  BLIND disclosure, per Amendment 28's precedent.
- It does not test the two rejected continuous functional forms (section 4)
  empirically — they were rejected on design grounds (parameter count,
  comparison cleanliness) before any run, not because they were tried and
  lost.
- It does not test cross-asset generalization (Amendment 29's GBPUSD line of
  inquiry is separate and unaffected by this design).
- It does not, by itself, address the standing finding that all seven tried
  setup families fail real-vs-random at the signal level (Part 22/24/25). If
  section 7 item 3 fails, that finding is the most likely reason, and this
  design says so in advance rather than treating a failure there as a
  surprise.
- **Part B of the exploratory diagnostic (section 2) has now been run against
  real data** (see the editor's addendum in section 2) and its premise check
  passes. The decisive test itself (section 7) has still not been run or
  coded — that is the next step, pending review.

## 10. Status

Part A (arithmetic) and Part B (empirical, against the real canonical
snapshot) of the exploratory diagnostic have both run; the premise holds on
real history. No decisive-test code (section 7) has been written or run. No
cache built for Amendment 30 itself. No MT5 connection made beyond read-only
history access already used elsewhere in this project. No Demo or real order
sent. No autotrader change. No PR. This document requires review under
`docs/OWNERSHIP.md` before any decisive-test code is written.

Current engine decision: **NO TRADE**.
