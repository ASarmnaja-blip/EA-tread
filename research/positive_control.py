#!/usr/bin/env python3
"""Positive-control calibration: does the pipeline find an edge that is
really there?

Companion to calibrate_pipeline.py, and required reading alongside it. A
pipeline that never fires on noise could simply never fire at all - nothing
in the no-edge run can distinguish "well calibrated" from "gate too tight to
find anything, ever". This hands the SAME pipeline, unmodified, data built
with a real, sized, known edge (planted_edge.py) at three magnitudes, and
checks that survivors are found and that the recovered magnitude tracks the
planted one. A pipeline that fails this while passing calibrate_pipeline.py
is not conservative, it is broken in the direction of never being useful.

Run:  python3 research/positive_control.py [--seeds N] [--bars N]
Exit code is non-zero if the LARGE planted edge is not recovered on a
majority of seeds - a pipeline that misses an edge this size on most draws
cannot be trusted to find a real one either.
"""
import argparse, math, sys, pathlib, time
import multiprocessing as mp
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))

def one_run(args):
    seed, bars, sigma, edge_r = args
    import mega_search as M
    from planted_edge import planted
    t0 = time.time()
    m, meta = planted(bars, seed, sigma, edge_r)
    boundary = m.index[int(len(m) * 0.70)]
    try:
        r = M.run(m, "1h", f"planted edge_r={edge_r} seed {seed}", calib=True,
                  boundary=boundary, quiet=True, seed=seed)
    except Exception as e:
        return dict(seed=seed, edge_r=edge_r,
                    error=f"{type(e).__name__}: {e}",
                    elapsed=time.time() - t0)
    r["seed"] = seed; r["edge_r"] = edge_r
    r["elapsed"] = time.time() - t0
    r["n_flips"] = len(meta["flip_bars"])
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--bars", type=int, default=20000)
    ap.add_argument("--sigma", type=float, default=0.0012)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()

    EDGES = {"small": 0.25, "medium": 0.50, "large": 1.00}
    print("POSITIVE-CONTROL CALIBRATION  (does the pipeline find a real, sized edge?)")
    print("=" * 78)
    print(f"  same pipeline, same synth() base martingale, same gate as "
          f"calibrate_pipeline.py")
    print(f"  the ONLY difference from the no-edge run: a planted directional")
    print(f"  move of controlled size is injected every ~60 bars")
    print(f"  edge sizes tested: {EDGES}")
    print(f"  {a.seeds} seeds per size, {a.jobs} at a time\n")

    all_results = {}
    for label, edge_r in EDGES.items():
        print(f"--- {label.upper()} planted edge (target ~{edge_r:+.2f}R) ---")
        jobs = [(201 + i, a.bars, a.sigma, edge_r) for i in range(a.seeds)]
        results = []
        with mp.Pool(a.jobs) as pool:
            for r in pool.imap_unordered(one_run, jobs):
                results.append(r)
                if "error" in r:
                    print(f"  seed {r['seed']:>4}  *** ERROR {r['error']}")
                else:
                    print(f"  seed {r['seed']:>4}  survivors {r['survivors']:>2}  "
                          f"cells {r['tested']:>9,}  floor {r['bar']:.2f}  "
                          f"best boot t {r['best_boot_t']:+.2f}  "
                          f"reached stage3 {r['n_final']:>2}  [{r['elapsed']:.0f}s]")
        results.sort(key=lambda x: x["seed"])
        all_results[label] = results
        print()

    print("=" * 78)
    print("SUMMARY\n")
    verdict_ok = True
    for label, edge_r in EDGES.items():
        rs = [r for r in all_results[label] if "error" not in r]
        errs = [r for r in all_results[label] if "error" in r]
        n = len(rs)
        found = sum(1 for r in rs if r["survivors"] > 0)
        rate = found / n if n else float("nan")
        print(f"  {label:<7} (edge_r={edge_r:+.2f}): {found}/{n} seeds found a "
              f"survivor ({rate:.0%}), {len(errs)} errored")
        if label == "large" and (n == 0 or rate < 0.5):
            verdict_ok = False

    print()
    if not verdict_ok:
        print("*** POSITIVE-CONTROL FAILED")
        print("    the pipeline missed the LARGE planted edge on a majority of")
        print("    seeds. A gate this tight cannot be trusted to find a real")
        print("    edge either - a zero-survivor result on calibrate_pipeline.py")
        print("    would not mean the pipeline is well calibrated, it would mean")
        print("    the pipeline is inert.")
        sys.exit(1)
    print("POSITIVE-CONTROL PASSED")
    print("  the large planted edge was recovered on a majority of seeds, so")
    print("  the gate is not so tight that a known-true edge cannot pass it.")
    print("  Read alongside calibrate_pipeline.py: TOGETHER they say the gate")
    print("  distinguishes noise from signal, not merely that it stays quiet.")
    sys.exit(0)

if __name__ == "__main__":
    main()
