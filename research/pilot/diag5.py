"""Direct harness null. On a driftless walk, first-passage probability depends
ONLY on the ratio of barrier distances: P(target first) = 1/(1+R).
Any deviation here is the instrument, not the rule."""
import sys; sys.path.insert(0, ".")
import numpy as np, core, data as D, run as R
from collections import Counter

b5 = D.load(D.SYMBOL, "60d", "5m")
r = np.diff(np.log(b5.c))
SIG = float(np.std(r[np.isfinite(r)])) * float(np.mean(b5.c))

def walk(rng, steps):
    n = len(b5)
    inc = rng.normal(0.0, SIG/np.sqrt(steps), size=(n, steps))
    path = np.cumsum(inc, axis=1)
    base = b5.c[0] + np.concatenate(([0.0], np.cumsum(path[:, -1])[:-1]))
    px = base[:, None] + path
    o = np.concatenate(([b5.c[0]], px[:-1, -1]))
    return D.Bars(b5.t, o, np.maximum(px.max(1), o), np.minimum(px.min(1), o),
                  px[:, -1], b5.v, 300, "SYNTH")

print(f"{'stop':>8s} {'R':>4s} {'maxbars':>8s} {'n':>7s} {'tgt%':>7s} {'theory%':>8s} "
      f"{'dev_pp':>7s} {'E_gross':>9s} {'t':>7s}")
print("-"*74)
for stop_mode, stop_val in [("ATR", 1.5), ("FIXED$", 10.0)]:
    for Rmult in (2.0, 3.0):
        for maxb in (core.TIME_STOP_5M, 100000):
            allR, whys = [], []
            for sd in range(6):
                rng = np.random.default_rng(R.RNG_MASTER + sd)
                sb5 = walk(rng, 20)
                sb15, _ = D.to_15m(sb5); nxt = R.map_next(sb15, sb5)
                c = core.Ctx(sb15, nxt)
                # a pure null "setup": every 7th eligible bar, direction alternating
                sig = []
                for k, i in enumerate(range(c.warm, len(sb15), 7)):
                    if nxt[i] < 0 or c.atr[i] <= 0: continue
                    d = 1 if k % 2 == 0 else -1
                    dist = stop_val*c.atr[i] if stop_mode == "ATR" else stop_val
                    sig.append((i, d, sb15.c[i] - d*dist, "R", Rmult))
                tr, _ = core.run_signals(c, sig, sb5, nxt, 0.0, maxb)
                allR += [t.gross_R for t in tr]; whys += [t.why for t in tr]
            x = np.array(allR); w = Counter(whys)
            tgt = 100.0*w["target"]/len(x)
            th = 100.0/(1.0+Rmult)
            se = x.std(ddof=1)/np.sqrt(len(x))
            print(f"{stop_mode:>8s} {Rmult:4.1f} {maxb:8d} {len(x):7d} {tgt:7.2f} {th:8.2f} "
                  f"{tgt-th:+7.2f} {x.mean():9.4f} {x.mean()/se:7.2f}")
