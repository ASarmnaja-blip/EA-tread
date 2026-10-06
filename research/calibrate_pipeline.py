#!/usr/bin/env python3
"""Run the ENTIRE search pipeline on data that contains nothing, many times.

WHY THE OLD CALIBRATION DID NOT COUNT

  `mega_search.py --calibrate` used to stop after stage 2 and print the best
  naive t on noise against sqrt(2 ln k). That answered the wrong question
  twice over:

    - stage 1-2 is a RANKING pass. It is supposed to surface high t values on
      noise; that is what searching a million cells does. Judging the pipeline
      on its ranking stage is like judging a sieve by what lands in it.
    - the thing that decides is the stage-3 triple gate: a percentile block
      bootstrap interval clear of zero, positive control-adjusted skill, and
      an overlap-corrected t above the search's own noise floor. None of that
      ran.

  The only question worth asking is: HOW OFTEN DOES THE WHOLE PIPELINE, END TO
  END, DECLARE A WINNER ON DATA WITH NO WINNER IN IT? That is what this
  measures, on many independent seeds, and it exits non-zero if the answer is
  anything but never.

THE GENERATOR HAS TO BE A TRUE MARTINGALE
  mega_search.synth builds price + cumsum(zero-mean steps), an ARITHMETIC
  martingale. The first version used price * exp(cumsum(...)), which is
  driftless in LOG space and drifts UP in price space because
  E[e^X] = e^(sigma^2/2). That fake drift produced E +0.2893R at t +5.29 on
  "information-free" data - an upward-drifting series throws more upside
  breakouts than downside, so the rule ends up net long and collects the
  drift. Exactly the way gold's 11x rise can masquerade as skill.

WHAT A FAILURE HERE MEANS
  Not "tune the gate until it passes". A pipeline that manufactures winners on
  noise cannot be repaired by moving its own threshold, because the threshold
  was fitted to the same noise. It means the gate is wrong and the search is
  not to be run on real data until it is fixed.

Run:  python3 research/calibrate_pipeline.py [--seeds N] [--bars N] [--jobs N]
Exit code is non-zero if ANY seed produces a survivor.
"""
import argparse, math, os, sys, pathlib, time, json
import multiprocessing as mp
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))

def wilson(k, n, z=1.96):
    """A binomial interval that stays sane at k=0, where k/n +- se gives the
    useless [0, 0]. With 0 successes in 20 trials the honest statement is
    'below about 16%', not 'exactly zero'."""
    if n == 0: return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

def one_seed(args):
    seed, bars, sigma = args
    import mega_search as M
    t0 = time.time()
    m = M.synth(bars, seed, sigma)
    boundary = m.index[int(len(m) * 0.70)]
    try:
        r = M.run(m, "1h", f"calib seed {seed}", calib=True, boundary=boundary,
                  quiet=True, seed=seed)
    except Exception as e:
        return dict(seed=seed, error=f"{type(e).__name__}: {e}",
                    elapsed=time.time() - t0)
    r["seed"] = seed
    r["elapsed"] = time.time() - t0
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--bars", type=int, default=20000)
    ap.add_argument("--sigma", type=float, default=0.0012)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import mega_search as M
    print("FULL-PIPELINE CALIBRATION  (stage 1 -> stage 2 -> stage 3)")
    print("=" * 74)
    print(f"  driftless arithmetic random walk, {a.bars:,} bars x {a.seeds} "
          f"independent seeds")
    print(f"  per-bar sigma {a.sigma}, discovery/holdout boundary at 70%")
    print(f"  the holdout is NEVER opened here - a calibration run that spent")
    print(f"  it would be the exact thing the split exists to prevent")
    print(f"  gate: bootstrap 95% CI clear of zero AND control-adjusted skill "
          f"> 0 AND |boot t| > sqrt(2 ln k)")
    print(f"  running {a.jobs} at a time\n")

    # the generator must be driftless; check it rather than trusting the label
    drift_t = []
    for s in range(60, 70):
        mm = M.synth(4000, s, a.sigma)
        st = np.diff(mm.close.to_numpy())
        drift_t.append(st.mean() / (st.std(ddof=1) / math.sqrt(len(st))))
    dt = float(np.mean(drift_t))
    print(f"  generator check: mean step t = {dt:+.3f} over 10 seeds "
          f"(a geometric walk reads about +3 here and is NOT driftless)\n")
    if abs(dt) > 2.0:
        print("*** the generator itself has drift. Calibrating against it is")
        print("    meaningless. Stop.")
        sys.exit(2)

    t0 = time.time()
    jobs = [(101 + i, a.bars, a.sigma) for i in range(a.seeds)]
    results = []
    with mp.Pool(a.jobs) as pool:
        for r in pool.imap_unordered(one_seed, jobs):
            results.append(r)
            if "error" in r:
                print(f"  seed {r['seed']:>4}  *** ERROR {r['error']}")
            else:
                print(f"  seed {r['seed']:>4}  survivors {r['survivors']:>2}  "
                      f"cells {r['tested']:>9,}  floor {r['bar']:.2f}  "
                      f"best boot t {r['best_boot_t']:+.2f}  "
                      f"best naive t {r['best_naive_t']:+.2f}  "
                      f"reached stage 3: {r['n_final']:>2}  "
                      f"[{r['elapsed']:.0f}s]")
    results.sort(key=lambda x: x["seed"])
    errs = [r for r in results if "error" in r]
    good = [r for r in results if "error" not in r]

    print("\n" + "=" * 74)
    if errs:
        print(f"{len(errs)} seed(s) raised. A pipeline that crashes on noise is")
        print("not calibrated, it is untested.")
        for r in errs: print(f"  seed {r['seed']}: {r['error']}")
        sys.exit(1)

    hits = [r for r in good if r["survivors"] > 0]
    n = len(good)
    k = len(hits)
    lo, hi = wilson(k, n)
    tot_cells = sum(r["tested"] for r in good)
    bts = np.array([r["best_boot_t"] for r in good if np.isfinite(r["best_boot_t"])])
    nts = np.array([r["best_naive_t"] for r in good if np.isfinite(r["best_naive_t"])])

    print("RESULT")
    print(f"  seeds run                      {n}")
    print(f"  seeds producing a survivor     {k}")
    print(f"  false-positive rate            {k/n:.1%}   "
          f"95% Wilson CI [{lo:.1%}, {hi:.1%}]")
    print(f"  cells tested in total          {tot_cells:,}")
    print(f"  reached stage 3 per seed       "
          f"{np.mean([r['n_final'] for r in good]):.1f} on average")
    if len(bts):
        print(f"  best overlap-corrected t       max {bts.max():+.2f}, "
              f"median {np.median(bts):+.2f}  (floor was "
              f"~{np.mean([r['bar'] for r in good]):.2f})")
    if len(nts):
        print(f"  best NAIVE t (ranking only)    max {nts.max():+.2f}, "
              f"median {np.median(nts):+.2f}")
        print(f"    - that a ranking pass reaches {nts.max():+.2f} on pure noise")
        print(f"      is the whole reason the naive t is not the gate")
    print(f"  elapsed                        {time.time()-t0:.0f}s")

    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(
            [{kk: (vv if not isinstance(vv, (np.floating, np.integer)) else float(vv))
              for kk, vv in r.items()} for r in good], indent=1))
        print(f"  written to {a.out}")

    print()
    if k:
        print("*** CALIBRATION FAILED")
        print(f"    {k} of {n} noise seeds produced a configuration that cleared")
        print("    the final gate. Every number this pipeline produces on real")
        print("    data is suspect until that is fixed - and it is NOT fixed by")
        print("    raising the threshold, because the threshold would be fitted")
        print("    to this same noise.")
        for r in hits:
            print(f"      seed {r['seed']}: {r['survivors']} survivor(s), "
                  f"best boot t {r['best_boot_t']:+.2f} vs floor {r['bar']:.2f}")
        sys.exit(1)

    print("CALIBRATION PASSED")
    print(f"  {n} independent noise seeds, {tot_cells:,} cells searched, and")
    print("  nothing cleared the final gate on any of them.")
    print(f"  Read the interval, not the point estimate: 0 of {n} means the")
    print(f"  true rate is somewhere below {hi:.1%}, not that it is zero. To")
    print("  claim a rate below 1% would need on the order of 300 seeds.")
    sys.exit(0)

if __name__ == "__main__":
    main()
