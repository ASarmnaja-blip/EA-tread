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
