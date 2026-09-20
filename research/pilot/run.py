"""
Pilot runner. Order is fixed by the pre-registration:

    P1 random-walk calibration  ->  if it fails, STOP, read no market data
    P2 look-ahead probe
    P4 cost reconciliation
    market run (18 registered configurations)
    P5 exit-resolution bias on the 1m overlap

Everything is COMEX gold futures (GC=F). None of it is XAUUSD spot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

OUT = Path(__file__).resolve().parent / "results"
RNG_MASTER = 20260919
CONTROL_DRAWS = 20
P1_SEEDS = 10


# --------------------------------------------------------------- helpers
def map_next(b15: D.Bars, ex: D.Bars) -> np.ndarray:
    """For each 15m bar, the exec-series index starting exactly at its close."""
    want = b15.t + 900
    pos = np.searchsorted(ex.t, want)
    out = np.full(len(b15), -1, dtype=np.int64)
    ok = (pos < len(ex.t))
    out[ok] = np.where(ex.t[pos[ok]] == want[ok], pos[ok], -1)
    return out


def synth_walk(b5: D.Bars, sigma_step: float, rng) -> D.Bars:
    """A driftless random walk on the REAL timestamps, so session structure,
    gaps and volume are identical and only the prices carry no information."""
    n, steps = len(b5), 20
    inc = rng.normal(0.0, sigma_step, size=(n, steps))
    path = np.cumsum(inc, axis=1)
    base = b5.c[0] + np.concatenate(([0.0], np.cumsum(path[:, -1])[:-1]))
    px = base[:, None] + path
    o = np.concatenate(([b5.c[0]], px[:-1, -1]))
    return D.Bars(b5.t, o, np.maximum(px.max(axis=1), o),
                  np.minimum(px.min(axis=1), o), px[:, -1], b5.v, 300, "SYNTH")


def evaluate(c: core.Ctx, signals, ex: D.Bars, nxt: np.ndarray, cost: float,
             max_bars: int, rng) -> dict:
    tr, skipped, accepted = core.run_signals(c, signals, ex, nxt, cost, max_bars)
    # Controls are built from the ACCEPTED signals only. Building them from the
    # raw list lets the control keep twins of signals the setup arm dropped for
    # an inverted stop or a target already passed, so the two arms would differ
    # by a feasibility filter instead of by timing alone.
    ctl_sig = core.control_signals(c, accepted, nxt, CONTROL_DRAWS, rng)
    ctl, _, _ = core.run_signals(c, ctl_sig, ex, nxt, cost, max_bars)
    s = core.summarise(tr, "net_R")
    g = core.summarise(tr, "gross_R")
    cs = core.summarise(ctl, "net_R")
    skill = s["E"] - cs["E"] if s["n"] and cs["n"] else float("nan")
    se = (np.sqrt(s["se"] ** 2 + cs["se"] ** 2)
          if s["n"] > 1 and cs["n"] > 1 else float("nan"))
    return dict(trades=tr, ctl=ctl, skipped=skipped, net=s, gross=g, ctlstat=cs,
                skill=skill, skill_se=se,
                skill_t=(skill / se if se and np.isfinite(se) and se > 0 else float("nan")))


def fmt(v, w=8, p=4):
    return f"{v:{w}.{p}f}" if isinstance(v, float) and np.isfinite(v) else f"{'--':>{w}}"


# ------------------------------------------------------------------- P1
def run_p1(b5: D.Bars) -> tuple[bool, list]:
    print("=" * 96)
    print("P1  CALIBRATION ON A DRIFTLESS RANDOM WALK")
    print("    Pre-registered pass: |skill| <= 0.02R AND |t| < 2, for all 18.")
    print("    If this fails, no market data is read.")
    print("=" * 96)

    r = np.diff(np.log(b5.c))
    sigma_bar = float(np.std(r[np.isfinite(r)])) * float(np.mean(b5.c))
    sigma_step = sigma_bar / np.sqrt(20)
    print(f"    matched 5m sd = ${sigma_bar:.3f}  ->  per-step sd = ${sigma_step:.4f}")
    print(f"    {P1_SEEDS} independent walks, pooled\n")

    # Skill is measured PER WALK. Ten walks are genuinely independent, so the
    # spread across them is an honest standard error. Pooling every trade and
    # dividing by sqrt(n) treats overlapping trades on one path as independent
    # and understates the error by 1.1x to 3.3x - which is what produced four
    # false failures on the first attempt.
    per_walk: dict[str, list] = {name: [] for name, _, _ in core.REGISTRY}
    pooled: dict[str, dict] = {name: {"tr": [], "ctl": []} for name, _, _ in core.REGISTRY}
    for seed in range(P1_SEEDS):
        rng = np.random.default_rng(RNG_MASTER + seed)
        sb5 = synth_walk(b5, sigma_step, rng)
        sb15, _ = D.to_15m(sb5)
        snxt = map_next(sb15, sb5)
        sc = core.Ctx(sb15, snxt)
        for name, _desc, fn in core.REGISTRY:
            sig = fn(sc)
            res = evaluate(sc, sig, sb5, snxt, core.COST_ROUND_TURN,
                           core.TIME_STOP_5M, rng)
            pooled[name]["tr"].extend(res["trades"])
            pooled[name]["ctl"].extend(res["ctl"])
            if len(res["trades"]) >= 2 and len(res["ctl"]) >= 2:
                per_walk[name].append(res["net"]["E"] - res["ctlstat"]["E"])
        print(f"    walk {seed + 1}/{P1_SEEDS} done", end="\r")
    print(" " * 40, end="\r")

    print(f"    {'id':6s} {'trades':>7s} {'walks':>6s} {'skill':>9s} {'se_path':>8s} "
          f"{'t_path':>7s} {'|skill|<=.02':>12s} {'|t|<2':>6s}  verdict")
    print("    " + "-" * 82)
    rows, all_ok = [], True
    mag_fail = t_fail = 0
    for name, _desc, _fn in core.REGISTRY:
        w = np.array(per_walk[name], dtype=float)
        s = core.summarise(pooled[name]["tr"], "net_R")
        if len(w) < 3:
            print(f"    {name:6s} {s['n']:7d} {len(w):6d}   too few walks to calibrate")
            rows.append(dict(id=name, n=s["n"], ok=False, why="too few walks"))
            all_ok = False
            continue
        skill = float(w.mean())
        se = float(w.std(ddof=1) / np.sqrt(len(w)))
        t = skill / se if se > 0 else float("nan")
        ok_mag = abs(skill) <= 0.02
        ok_t = abs(t) < 2
        ok = ok_mag and ok_t
        mag_fail += not ok_mag
        t_fail += not ok_t
        all_ok &= ok
        print(f"    {name:6s} {s['n']:7d} {len(w):6d} {fmt(skill,9)} {fmt(se,8)} "
              f"{fmt(t,7,2)} {('pass' if ok_mag else 'FAIL'):>12s} "
              f"{('pass' if ok_t else 'FAIL'):>6s}  {'ok' if ok else 'FAIL'}")
        rows.append(dict(id=name, n=s["n"], walks=len(w), skill=skill, se=se, t=t,
                         ok_mag=bool(ok_mag), ok_t=bool(ok_t), ok=bool(ok)))
    print("    " + "-" * 82)
    print(f"    magnitude arm |skill| <= 0.02R : {18 - mag_fail}/18 pass")
    print(f"    t arm         |t| < 2          : {18 - t_fail}/18 pass")
    print(f"    P1 {'PASS' if all_ok else 'FAIL'}\n")
    return all_ok, rows


# ------------------------------------------------------------- P2 and P4
def run_p2_p4(c: core.Ctx, b5: D.Bars, nxt: np.ndarray) -> dict:
    print("=" * 96)
    print("P2  LOOK-AHEAD PROBE   /   P4  COST RECONCILIATION")
    print("=" * 96)
    rng = np.random.default_rng(RNG_MASTER)

    # structural: entry must start at or after the signal bar's close
    bad = 0
    for name, _d, fn in core.REGISTRY:
        for (i, *_r) in fn(c):
            k = nxt[i]
            if k >= 0 and b5.t[k] < c.b.t[i] + 900:
                bad += 1
    print(f"    entries before the signal bar closed : {bad}   "
          f"{'ok' if bad == 0 else 'LEAK'}")

    delayed_nxt = np.where(nxt >= 0, nxt + 1, -1)
    delayed_nxt[delayed_nxt >= len(b5)] = -1

    print(f"\n    {'id':6s} {'E_now':>9s} {'E_delayed':>10s} {'delta':>9s}")
    print("    " + "-" * 40)
    deltas, p4_ok = [], True
    for name, _d, fn in core.REGISTRY:
        sig = fn(c)
        a = core.run_signals(c, sig, b5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)[0]
        b = core.run_signals(c, sig, b5, delayed_nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)[0]
        ea, eb = core.summarise(a)["E"], core.summarise(b)["E"]
        deltas.append(ea - eb)
        print(f"    {name:6s} {fmt(ea,9)} {fmt(eb,10)} {fmt(ea - eb,9)}")

        # P4: the same signals costed twice, independently
        zero = core.run_signals(c, sig, b5, nxt, 0.0, core.TIME_STOP_5M)[0]
        full = core.run_signals(c, sig, b5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)[0]
        if len(zero) != len(full):
            p4_ok = False
        else:
            for z, f in zip(zero, full):
                if abs(z.gross_R - f.gross_R) > 1e-9:
                    p4_ok = False
                if abs((z.gross_R - core.COST_ROUND_TURN / z.risk) - f.net_R) > 1e-9:
                    p4_ok = False
    identical = sum(1 for d in deltas if abs(d) < 1e-12)
    print("    " + "-" * 40)
    print(f"    configurations unchanged by a one-bar delay: {identical}/18 "
          f"{'(suspicious if high)' if identical > 2 else 'ok'}")
    print(f"    P4 cost reconciliation (gross - cost/risk == net, two runs): "
          f"{'PASS' if p4_ok else 'FAIL'}\n")
    return dict(entries_before_close=bad, delayed_identical=identical, p4=p4_ok)


# --------------------------------------------------------- market + P5
def stressed(trades, mult: float) -> dict:
    if not trades:
        return dict(n=0, E=float("nan"))
    x = np.array([t.gross_R - mult * core.COST_ROUND_TURN / t.risk for t in trades])
    return dict(n=len(x), E=float(x.mean()))


def run_market(c: core.Ctx, b5: D.Bars, nxt: np.ndarray) -> list[dict]:
    print("=" * 96)
    print("MARKET RUN - COMEX gold futures GC=F.  THIS IS NOT XAUUSD SPOT.")
    print(f"    cost: spread ${core.SPREAD:.2f} + 2 x slippage ${core.SLIPPAGE:.2f} "
          f"= ${core.COST_ROUND_TURN:.2f} per round turn (ASSUMED, not measured)")
    print("=" * 96)
    rng = np.random.default_rng(RNG_MASTER + 999)
    print(f"    {'id':6s} {'n':>5s} {'E_gross':>9s} {'E_net':>9s} {'net@1.5x':>9s} "
          f"{'net@2x':>8s} {'CI95(net)':>19s} {'MDE':>7s} {'skill':>8s} {'t':>6s}")
    print("    " + "-" * 104)
    rows = []
    for name, desc, fn in core.REGISTRY:
        sig = fn(c)
        res = evaluate(c, sig, b5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M, rng)
        tr = res["trades"]
        if len(tr) < 2:
            print(f"    {name:6s} {len(tr):5d}   too few trades")
            rows.append(dict(id=name, desc=desc, n=len(tr)))
            continue
        lo, hi = core.block_bootstrap_ci(res["net"]["x"], 12, 2000,
                                         np.random.default_rng(RNG_MASTER + 7))
        s15 = stressed(tr, 1.5)
        s20 = stressed(tr, 2.0)
        print(f"    {name:6s} {res['net']['n']:5d} {fmt(res['gross']['E'],9)} "
              f"{fmt(res['net']['E'],9)} {fmt(s15['E'],9)} {fmt(s20['E'],8)} "
              f"[{fmt(lo,8)},{fmt(hi,8)}] {fmt(res['net']['mde'],7,3)} "
              f"{fmt(res['skill'],8)} {fmt(res['skill_t'],6,2)}")
        rows.append(dict(id=name, desc=desc, n=res["net"]["n"],
                         E_gross=res["gross"]["E"], E_net=res["net"]["E"],
                         E_net_15x=s15["E"], E_net_2x=s20["E"],
                         ci_lo=lo, ci_hi=hi, sd=res["net"]["sd"],
                         mde=res["net"]["mde"], win=res["net"]["win"],
                         skill=res["skill"], skill_se=res["skill_se"],
                         skill_t=res["skill_t"], n_ctl=res["ctlstat"]["n"],
                         E_ctl=res["ctlstat"]["E"], skipped=res["skipped"],
                         trades=tr))
    print("    " + "-" * 104)
    return rows


def split_report(rows: list[dict]) -> None:
    print("\n    split by regime and session (net R, primaries only)")
    print(f"    {'id':6s} {'bucket':10s} {'n':>5s} {'E_net':>9s}")
    print("    " + "-" * 34)
    for r in rows:
        if "trades" not in r or r["id"].find("V") >= 0:
            continue
        for key in ("regime", "session"):
            buckets: dict[str, list] = {}
            for t in r["trades"]:
                buckets.setdefault(getattr(t, key), []).append(t.net_R)
            for b in sorted(buckets):
                x = np.array(buckets[b])
                print(f"    {r['id']:6s} {b:10s} {len(x):5d} {fmt(float(x.mean()),9)}")


def run_p5(c: core.Ctx, b5: D.Bars, nxt5: np.ndarray, b1: D.Bars) -> list[dict]:
    print("\n" + "=" * 96)
    print("P5  EXIT-RESOLUTION BIAS: 5m vs 1m on the overlap")
    print("=" * 96)
    nxt1 = map_next(c.b, b1)
    both = (nxt5 >= 0) & (nxt1 >= 0)
    print(f"    15m bars resolvable on BOTH series: {int(both.sum())} of {len(c.b)}")
    print(f"    {'id':6s} {'n':>5s} {'E_5m':>9s} {'E_1m':>9s} {'bias':>9s}")
    print("    " + "-" * 42)
    out = []
    for name, _d, fn in core.REGISTRY:
        sig = [s for s in fn(c) if both[s[0]]]
        if len(sig) < 2:
            print(f"    {name:6s} {len(sig):5d}   too few in the overlap")
            out.append(dict(id=name, n=len(sig)))
            continue
        a = core.run_signals(c, sig, b5, nxt5, core.COST_ROUND_TURN, core.TIME_STOP_5M)[0]
        b = core.run_signals(c, sig, b1, nxt1, core.COST_ROUND_TURN, core.TIME_STOP_5M * 5)[0]
        ea, eb = core.summarise(a)["E"], core.summarise(b)["E"]
        print(f"    {name:6s} {len(a):5d} {fmt(ea,9)} {fmt(eb,9)} {fmt(ea - eb,9)}")
        out.append(dict(id=name, n=len(a), E_5m=ea, E_1m=eb, bias=ea - eb))
    biases = [r["bias"] for r in out if "bias" in r and np.isfinite(r["bias"])]
    if biases:
        print("    " + "-" * 42)
        print(f"    mean bias {np.mean(biases):+.4f} R, median {np.median(biases):+.4f} R, "
              f"max |bias| {max(abs(b) for b in biases):.4f} R")
        print("    Positive bias = 5m resolution flatters the result.")
    return out


# ------------------------------------------------------------------ main
def main() -> int:
    OUT.mkdir(exist_ok=True)
    print(f"\ninstrument: {D.INSTRUMENT_LABEL}\n")
    b5 = D.load(D.SYMBOL, "60d", "5m")
    b1 = D.load(D.SYMBOL, "7d", "1m")
    b15, nxt_from_build = D.to_15m(b5)
    nxt = map_next(b15, b5)
    assert np.array_equal(nxt, nxt_from_build), "next-bar mapping disagrees"
    print("   ", D.describe(b5, "5m exec"))
    print("   ", D.describe(b1, "1m exec"))
    print("   ", D.describe(b15, "15m sig"))
    print()

    p1_ok, p1_rows = run_p1(b5)
    if not p1_ok:
        print("!" * 96)
        print("P1 FAILED. Stopping before any market data is read, as pre-registered.")
        print("!" * 96)
        (OUT / "p1.json").write_text(json.dumps(p1_rows, indent=2, default=float))
        return 1

    c = core.Ctx(b15, nxt)
    checks = run_p2_p4(c, b5, nxt)
    rows = run_market(c, b5, nxt)
    split_report(rows)
    p5 = run_p5(c, b5, nxt, b1)

    slim = [{k: v for k, v in r.items() if k != "trades"} for r in rows]
    (OUT / "pilot.json").write_text(json.dumps(
        dict(instrument=D.INSTRUMENT_LABEL, p1=p1_rows, checks=checks,
             market=slim, p5=p5), indent=2, default=float))
    print(f"\nwritten: {OUT / 'pilot.json'}")
    print("\nCeiling for every result above: RESEARCH WATCH. Not a trade signal,")
    print("not a shadow candidate, and not a statement about XAUUSD spot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
