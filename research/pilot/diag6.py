"""Is the pooled trade-level SE understating the truth?

Trades overlap in time on one price path, so they are not independent. The
research log already records this: a naive shuffle moved one p-value from
0.0075 to 0.31. Ten independent walks give a clean check - per-walk skill is
genuinely independent, so its spread is the honest SE."""
import sys; sys.path.insert(0, ".")
import numpy as np, core, data as D, run as R

b5 = D.load(D.SYMBOL, "60d", "5m")
r = np.diff(np.log(b5.c))
SIG = float(np.std(r[np.isfinite(r)])) * float(np.mean(b5.c))

NAMES = ("S1","S1V1","S2","S2V1","S2V2","S3","S4V1","S5","S6")
per_walk = {n: [] for n in NAMES}
pooled = {n: dict(s=[], c=[]) for n in NAMES}

for sd in range(10):
    rng = np.random.default_rng(R.RNG_MASTER + sd)
    sb5 = R.synth_walk(b5, SIG/np.sqrt(20), rng)
    sb15, _ = D.to_15m(sb5); nxt = R.map_next(sb15, sb5); c = core.Ctx(sb15, nxt)
    for name, _d, fn in core.REGISTRY:
        if name not in NAMES: continue
        sg = fn(c)
        tr, _ = core.run_signals(c, sg, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        cs = core.control_signals(c, sg, nxt, R.CONTROL_DRAWS, rng)
        ct, _ = core.run_signals(c, cs, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        if len(tr) < 2 or len(ct) < 2: continue
        a = np.array([t.net_R for t in tr]); b = np.array([t.net_R for t in ct])
        per_walk[name].append(a.mean() - b.mean())
        pooled[name]["s"] += list(a); pooled[name]["c"] += list(b)

print(f"{'id':6s} | {'pooled skill':>12s} {'se_naive':>9s} {'t_naive':>8s} | "
      f"{'mean/walk':>10s} {'se_walk':>8s} {'t_walk':>7s} | {'SE ratio':>9s}")
print("-"*92)
for n in NAMES:
    s = np.array(pooled[n]["s"]); c_ = np.array(pooled[n]["c"])
    sk = s.mean() - c_.mean()
    se_n = np.sqrt(s.var(ddof=1)/len(s) + c_.var(ddof=1)/len(c_))
    w = np.array(per_walk[n])
    se_w = w.std(ddof=1)/np.sqrt(len(w))
    print(f"{n:6s} | {sk:12.4f} {se_n:9.4f} {sk/se_n:8.2f} | {w.mean():10.4f} "
          f"{se_w:8.4f} {w.mean()/se_w:7.2f} | {se_w/se_n:9.2f}x")
print("\nSE ratio > 1 means the pooled trade-level SE understates the real one.")
