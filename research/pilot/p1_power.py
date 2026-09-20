"""More walks: does |skill| shrink toward zero (noise) or hold (a real bias
in the control)? Random walk only. Usage: p1_power.py <n_walks>"""
import sys, time
sys.path.insert(0, ".")
import numpy as np, core, data as D, run as R

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
b5 = D.load(D.SYMBOL, "60d", "5m")
_r = np.diff(np.log(b5.c)); SIG = float(np.std(_r[np.isfinite(_r)])) * float(np.mean(b5.c))
names = [n for n, _, _ in core.REGISTRY]
w = {n: [] for n in names}
t0 = time.time()
for sd in range(N):
    rng = np.random.default_rng(R.RNG_MASTER + 1000 + sd)
    sb5 = R.synth_walk(b5, SIG/np.sqrt(20), rng)
    sb15, _ = D.to_15m(sb5); nxt = R.map_next(sb15, sb5); c = core.Ctx(sb15, nxt)
    for name, _d, fn in core.REGISTRY:
        sg = fn(c)
        tr, _ = core.run_signals(c, sg, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        cs = core.control_signals(c, sg, nxt, R.CONTROL_DRAWS, rng)
        ct, _ = core.run_signals(c, cs, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        if len(tr) >= 2 and len(ct) >= 2:
            w[name].append(np.mean([t.net_R for t in tr]) - np.mean([t.net_R for t in ct]))
    if (sd+1) % 10 == 0:
        print(f"  {sd+1}/{N} walks  {time.time()-t0:.0f}s", flush=True)

print(f"\n{N} walks in {time.time()-t0:.0f}s")
print(f"{'id':6s} {'skill':>9s} {'se_path':>8s} {'t':>7s} {'95% CI':>20s}  verdict")
print("-"*68)
nz = 0
for n in names:
    a = np.array(w[n])
    if len(a) < 3: continue
    m, se = a.mean(), a.std(ddof=1)/np.sqrt(len(a))
    lo, hi = m-1.96*se, m+1.96*se
    real = not (lo <= 0 <= hi)
    nz += real
    print(f"{n:6s} {m:9.4f} {se:8.4f} {m/se:7.2f} [{lo:8.4f},{hi:8.4f}]  "
          f"{'BIAS' if real else 'consistent with 0'}")
print(f"\n{nz}/18 have a CI excluding zero -> that many are a real control mismatch.")
