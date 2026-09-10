# Research

Two kinds of file live here.

**Research cells** are paste-and-run cells for a QuantConnect *Research*
notebook. Each is self-contained — it does not depend on helpers defined in
earlier cells — so it can be dropped into a fresh notebook.

**Algorithms** are full LEAN algorithms, pasted into `main.py` of a
QuantConnect project and run through the backtest engine.

| File | Kind | Question it answers |
|---|---|---|
| `qc_crossasset_test.py` | cell | Does the trend zone exist off gold, or was it fitted to it? |
| `qc_dobby_3leg_algo.py` | algorithm | Does the EMA 9/21 cross + 3-leg ladder have an edge on 2025-onward data, priced at the real spread? |
| `qc_dobby_tuning_cell.py` | cell | Which parameters survive out-of-sample once the multiple-testing bar is applied? |
| `qc_signal_census_cell.py` | cell | What do ALL signals do, including the ones the filters were throwing away? |
| `qc_4part_filter_test.py` | cell | Does a volume-profile filter, a CHoCH+OB filter, or the pair of them rescue the system? |
| `choch_fvg_three_setups.py` | script | Does CHoCH+FVG survive a better fill, a slower horizon, or a trend gate — and is the control it was first measured against sound? |
| `dobby_setup01_sweep_chain.py` | script | Sweep → CHoCH → displacement → FVG, as one setup: does it fire often enough to trade, and does each stage earn its place? |
| `cost_vs_exit_decomposition.py` | script | Is the spread really the barrier, or is it the exit design — or the entry? Splits expectancy into the three terms and measures each. |
| `principles_backtest_gold.py` | script | If you stop forecasting and trade the exit and the sizing instead, what does that do on gold against buy and hold on the same drawdown budget? |
| `fetch_m15_gold.py` | script | Where does six years of M15 gold come from when Yahoo caps it at 60 days, and does that source actually track gold? |
| `m15_regime_search.py` | script | On six years of M15: does a trend/range regime filter carry information, and does anything survive a holdout fixed in advance? |
| `multi_tf_setup_grid.py` | script | 11 entry families × params × 4 exits × 2 stops × M5/M15/M30/H1: is the best cell of a 631-cell search worth anything? |

**Standalone scripts** (`smc_entry_test.py`, `universe_trend_test.py`,
`gold_only_search.py`, `backtest_dobby_indicator.py`,
`choch_fvg_three_setups.py`) fetch their own data and run under plain
`python3`. They need only `numpy` and `pandas`.

## choch_fvg_three_setups.py

Three variations on the CHoCH + fair-value-gap entry, each aimed at one of the
reasons this repo has recorded for intraday results dying: the fill (a resting
limit at the far gap edge instead of the close), the horizon (daily bars
instead of H1) and the bias (a daily Donchian-55 gate instead of a 4h EMA).

It leads with a **calibration row** that re-measures the exact configuration
`smc_entry_test.py` already reported, because a new number is worth nothing
until the harness reproduces an old one. That row is where the run's most
useful finding came from — see `docs/RESEARCH_FINDINGS.md`.

## dobby_setup01_sweep_chain.py

The four-stage chain — liquidity sweep, then CHoCH/MSS, then displacement, then
a limit at the fair value gap — written out as one closed setup with the EA's
own stage parameters, and measured on gold at M15/H1/D1 plus 27 futures.

Two things it prints that a plain expectancy table would not:

- a **funnel**, counting how many candidates survive each stage, so "no edge"
  can be told apart from "no data". End to end the chain keeps 0.8% of sweeps.
- an **ablation** at each stage depth with identical stops, exits and controls,
  which asks whether each added condition contributes anything beyond cutting
  the sample. Alongside each row is its **MDE** — the smallest true effect that
  sample could detect. At full depth the measured skill is smaller than the MDE.

## qc_4part_filter_test.py

A 2x2 factorial, measured only on trades that could actually have been taken.

```
PART 1   no volume profile, no CHoCH+OB      baseline
PART 2   volume profile,    no CHoCH+OB
PART 3   no volume profile, CHoCH+OB
PART 4   volume profile,    CHoCH+OB
```

Running only "baseline" against "everything on" would say whether the pair
works, not which half did the work or whether one is cancelling the other. The
factorial separates the volume effect, the structure effect and the
interaction, and prints all three.

### The sequencing trap

The non-overlapping selection is **recomputed inside each part**. A filter that
rejects a signal frees the account to take the next one, and that next trade
would be invisible to a filter applied after sequencing. Sequencing the census
once and filtering the survivors understates every filter tested.

### Filter definitions

**Volume profile** (`VP_MODE="breakout"`): long only above the value area high,
short only below the value area low - price has left value in the signal's
direction, which is the trend-following reading and the one that matches an
EMA cross. `VP_MODE="reversion"` is the opposite hypothesis and counts as a
separate test if you look at it.

**CHoCH** follows the EA's `Structure.mqh`: a close beyond the last confirmed
opposing swing by at least `MIN_BREAK_ATR` x ATR, counted only when it flips
the prevailing structure. A same-direction break is a BOS and re-arms nothing.

**Order block** is the last opposite-close candle before that impulse, and the
signal must arrive with price back inside it within `OB_TOL` x ATR.
**No order block exists anywhere in the EA** - this definition was written for
this test and has never been validated against anything.

### Reading it

Watch the pass counts printed before the table. These filters are restrictive
and Part 4 is the intersection of both, so it can end up with too few trades to
say anything - a handful of trades will show a wide expectancy for reasons that
have nothing to do with skill. `OB_TOL` and `CHOCH_MAX_AGE` are the knobs if
Part 4 comes back empty.

A part counts only if E > 0 with t over the Bonferroni bar (t > 2.73 at eight
hypotheses), on the same part, in both samples. A filter that only makes a
losing system lose more slowly has not found an edge - it has found fewer
trades.

### Signal timeframe

`SIGNAL_TF` sets the timeframe the EMA cross is computed on. Exits always
resolve on 1-minute bars whatever it is, and the profile window and hold are
derived from it so 24 hours stays 24 hours across settings.

Raising it is the one lead the cost diagnostic keeps pointing at. A fixed
spread against a wider ATR-based stop is a smaller share of R: moving from
`"5min"` to `"15min"` roughly halves spread/R, from about 0.21 to 0.11 per leg.
`OB_LOOKBACK` and `CHOCH_MAX_AGE` are counted in signal bars, so they cover
proportionally more clock time as the timeframe rises - adjust them if you want
the same span.

### Cost diagnostic

Expectancy climbing toward zero as the filters tighten looks the same whether
the filter predicts direction or merely avoids trades where the fixed spread is
a large share of a small R. To separate them, every setup is replayed at zero
spread and reported as GROSS beside NET. That is a second simulation, not the
cost added back: at zero spread the break-even stop sits at the entry instead
of one spread inside profit, so adding the cost back would credit a
break-even leg with a spread it never earned.

If GROSS is near zero in every part while NET improves with filtering, the
filters are selecting wide-stop trades, not forecasting. The fix for that is a
larger stop, not a better filter.

### Monthly regime, and the two periods

A volatility break is checked, not assumed. The monthly table reports ATR and
ATR/price beside the signal count, mean spread/R, and both NET and GROSS
expectancy, so the month a regime actually changed is visible rather than
argued about.

Watch what rising volatility does to cost. A wider stop makes a fixed spread a
smaller share of R, so a more volatile period can post a better NET expectancy
with no change whatsoever in the signal's ability to predict direction. That is
why GROSS sits next to NET in every table here:

| NET | GROSS | reading |
|---|---|---|
| improves | flat | cheaper trades, not better ones - the stop got wider |
| improves | improves | something in the signal genuinely changed |
| flat | flat | nothing changed |

`RECENT_MONTHS` then splits the run into the full sample and the recent period.
Each row carries **MDE**, the minimum detectable effect: the expectancy that
many trades could resolve at 5% significance and 80% power. Three months leaves
roughly 240 baseline trades, where MDE is about 0.6R - larger than any
expectancy this system has produced in either direction, so that period returns
"inside noise" whichever way the number lands. Part 4 over three months is about
six trades, MDE above 4R.

A short window does not make a marginal result clearer. It makes it
unfalsifiable. Its legitimate use is describing the current regime - which is
what the monthly table is for.


## qc_signal_census_cell.py

Supersedes the tuning cell. That cell applied the [0.30, 3.00] x ATR risk band
**before** measuring anything and discarded 1,033 of 2,184 signals, so it could
never say whether the band was removing losers or removing winners.

This cell filters nothing. Every EMA cross is simulated and recorded with its
features attached, and the filters are judged afterwards on measured evidence.
Eleven features per signal: `risk_atr`, `trend_ok`, `zone`, `poc_dist`,
`va_pos`, `vpoc_dist`, `liq_up`, `liq_dn`, `swept`, `atr_pct`, `hour`,
`spread_r`. Results are written to `signal_census.csv` so further slicing does
not need a re-run.

### Volume, honestly

XAU/USD spot is OTC, and QuantConnect's OANDA CFD feed carries no volume at
all - the EA's own `VolumeProfile.mqh` makes the same disclosure about MT5,
where the default source is one broker's tick count rather than gold's volume.

So the default profile here is a **time (TPO) profile**: how long price spent
in each bin, not how much traded there. With `USE_GC_VOLUME=True` the cell
additionally builds a real **volume** profile from COMEX gold futures, which
do carry genuine volume on QuantConnect, and reports it as `vpoc_dist`
alongside. Where the two disagree, the volume one is the better evidence.

### The dredging problem, and the three guards

Slicing eleven features into buckets is ~56 hypotheses. Fifty-six tests
against a signal with no edge **will** produce something that looks tradable.
So the cell prints, for every bucket:

1. in-sample **and** out-of-sample side by side - a bucket that works in one
   only is noise;
2. the Bonferroni family-wise 5% bar recomputed for the real test count -
   **t > 3.32** at 56 tests, not 2.00;
3. a **monotonicity** flag - a real effect gradients across buckets, while a
   single spiky bucket beside flat neighbours is almost always luck.

### Two correctness details worth knowing

Sweep detection reads bars *after* the sweep bar to confirm the reclaim, so a
sweep is not knowable until `SWEEP_RECLAIM` bars later; the lookup window is
shifted by that much or the feature would be reading the future. Sweeps here
use the prior 20-bar extreme rather than `Sweep.mqh`'s named levels (PDH/PDL,
Asian high/low), which is a deliberate simplification for vectorisation.

Untested-level lookup uses suffix max/min over the window, making the test O(1)
per pivot. The naive slice scan made the cell take about an hour.

### Negative control

Run against a synthetic random walk with the same spread charged, every bucket
comes back negative and none turns spuriously positive - which is what a
harness free of look-ahead should do on data with no edge.


## qc_dobby_tuning_cell.py

The tuning bench. Loads 2025-onward minute gold once, then replays every
configuration over it in seconds rather than one LEAN backtest at a time.

The sample is split before anything is measured, and the split is not
negotiable after the fact:

```
IN SAMPLE   2025-01-01 .. 2025-12-31   tune here, look freely
OUT SAMPLE  2026-01-01 .. 2026-09-10   verify ONCE, never tune
```

Both columns print side by side for all 17 configurations, plus a
drift-adjusted out-of-sample t, because gold rose hard across this window and
a long-only rule inherits that.

**The bar rises with the number of configurations tested.** The best of 17
draws is not a single test, so the cell prints the Bonferroni family-wise 5%
threshold — **t > 2.97** at 17 tests, not 2.0. Reading the out-of-sample
column before committing to a configuration turns it into a test too, and the
bar rises again.

R is scale-free here: quantity is not modelled at all, every leg risks exactly
1R by definition. No account size, lot size or cent conversion can distort the
numbers, which is the point of tuning here rather than on the Pine dashboard.

Runtime is a few minutes for the full sweep. Watch the spread-sensitivity
block at the end — at a 1.8xATR stop the spread assumption alone moved gold's
expectancy from +0.2312R to +0.1253R in earlier work, and the Pine build was
running 0.26 against a measured 0.7525.


## qc_dobby_3leg_algo.py

The TradingView build of this system reported +18% on a 1000-cent account in
September 2026. Decomposing its own dashboard shows why that number cannot be
taken at face value: **+5R across 24 signals, expectancy +0.21R, t = 0.28.**
At that effect size roughly 1,240 signals are needed to reach t = 2.0.

Four things this run fixes, all of which flattered the Pine result:

| Pine build | Here |
|---|---|
| Exits resolve on the 5-minute signal bar | Real LEAN orders against **minute** data |
| Fixed lot, stop ranging over 10x → money risk varied 10x | Quantity derived from stop distance, so **1R is constant money** |
| TP1 judged on the bar's high | TP1 is **leg 1's limit order actually filling** |
| Spread assumed 0.26 | **0.7525**, OANDA's measured 2023-2026 gold mean |

The sizing fix matters more than it sounds. Because the Pine build sized every
leg identically while its stop distance varied, its winners happened to carry
about 25% more money-risk than its losers — which is the entire reason +5R
printed as +182 cent. Constant-R sizing removes that, so the R column and the
money column can no longer disagree.

Risk is also cut from the ~3.8% per signal the Pine build was running (1.2%
per leg x 3) to 1.0% per signal. At a 50% signal loss rate, six full stop-outs
in a row is an ordinary event, and at 3.8% that run costs 22%.

### Running it

1. New QuantConnect project, Python, paste the file into `main.py`.
2. The window is locked in the class body: `START = (2025, 1, 1)`.
3. Free-tier CFD minute data over ~20 months is a slow backtest. Expect it to
   take a while, and check the **Logs** tab, not the summary panel, for the
   verdict block.

### Reading the output

Ignore the equity curve first. Go to the log block:

```
ALL    n=...  E=+0.____R  sd=...R  t=+_.__  win=__._%  n for t=2.0: ____
LONG   ...
SHORT  ...
buy and hold over the same window: +__._%
```

`PASS = t > 2.0 on the side you intend to trade.` Anything else is noise,
however good the equity curve looks. The buy-and-hold line is printed beside
it because gold rose hard across 2025-2026, and a long-only rule inherits that
drift — inheriting drift is not timing skill. If LONG looks strong and SHORT
does not, suspect drift before suspecting edge.

Watch three diagnostics as well:

- `skipped: risk-band N` — how many crossovers the [0.30, 3.00] x ATR band
  threw away. The Pine build was rejecting a third of them.
- `WARNING stop and limit both filled` — a stop and its target both filled
  inside one minute before the cancel landed. A handful is tolerable; many
  means the R figures are contaminated.
- `L1 TP/SL` — leg 1 is the base 1R hit rate with nothing else layered on it.
  The whole ladder rests on it.

## qc_crossasset_test.py

The outstanding test. Everything measured so far — permutation p = 0.0005,
in-zone vs out-of-zone t = +9.33, drift-adjusted t = +5.08 — was measured on
**gold only**, and the zone edges were found on the *full* sample rather than
a held-out half. If `(Close − SMA200)/ATR ∈ [1.08, 7.21]` is a real effect it
has to show up elsewhere. If it does not, it is gold overfit.

**Nothing is refitted per instrument.** The zone edges, stop multiple, target
and hold are fixed at gold's values. Retuning them per market would turn one
overfit into three.

Pre-registered pass criteria, stated before the output is seen:

```
PASS = net E > 0 AND t > 2.0 on BOTH XAGUSD and EURUSD (long side, 8R target)
FAIL = anything else
```

The drift-adjusted column is reported alongside and is the honest one: gold
rose across the whole sample, so a long-only rule inherits that. On gold,
removing drift takes longs in the zone from +0.0569R (t +4.45) to **−0.0494R
(t −4.14)**, while shorts go to +0.1092R (t +7.56). Watch whether the same
happens on the new instruments.

### Two implementation details that changed earlier results

**Exits resolve on minute bars.** Resolving on the 15-minute signal bar
misses stops that were actually hit and inflated the earlier work by +0.06R
at 1.5R and +0.20R at 3R.

**The 15-minute → minute mapping uses the LAST minute of each bin.** pandas
labels a resampled bin by its left edge; searching that label into the minute
index lands on the *first* minute of the bar, a 15-minute look-ahead. That
bug once lifted a win rate from 66.7% to 79.8% on driftless data.

### Running it

Free-tier memory is the constraint, so it loads one instrument at a time in
quarterly chunks and frees each before the next. Expect several minutes.

Output is deliberately compact — one line per instrument per side, then a
verdict block — because long cell output gets truncated in the browser.

### Spreads

`SPREAD` is in price units per instrument and is a **cost assumption**, not a
measurement. The gold figure is OANDA's measured 2023–2026 mean ($0.7525),
which is 2.9× the $0.26 the original work costed with. Replace the FX values
with your broker's real numbers before trusting the verdict — at a 1.8×ATR
stop this input alone moves gold's net expectancy from +0.2312R to +0.1253R.
