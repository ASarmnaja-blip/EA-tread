"""Round 2 of the WPWB edge search (prereg Amendment 2). DEV only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approaches as AP  # noqa: E402
import approaches2 as AP2  # noqa: E402
import common as C  # noqa: E402
import evaluate as EV  # noqa: E402
from run_dev import dev_cuts, load_canonical  # noqa: E402

FLOOR = 0.5          # Amendment 2 declared no exemption, so section 6 default applies
META_LOOKBACK = 26
META_MIN_WEEKS = 4


def selftest_entries_pool(m, cuts):
    """RTIME via ('entries', lo, hi) must equal a brute-force average."""
    cut = int(cuts[len(cuts) // 2])
    lo, hi = m.week_bars(cut)
    trades = [(lo + 3, lo + 5, 1), (lo + 20, lo + 20, -1)]
    got = EV._rtime_expectation(m, trades, ("entries", lo, hi), 1.0)
    want = 0.0
    for i, k, d in trades:
        L = k - i + 1
        vals = [float(m.pnl_bp([e], [m.exit_index(e, L, hi)], [d])[0]) for e in range(lo, hi)]
        want += np.mean(vals)
    assert abs(got - want) < 1e-9, (got, want)
    print("self-test: entries-pool RTIME matches brute force")


def meta_choose(base_matrix, w, hl):
    """Tool index for week w from weeks < w only; -1 = stand aside."""
    lo = max(0, w - META_LOOKBACK)
    hist = base_matrix[:, lo:w]
    if hist.shape[1] < META_MIN_WEEKS:
        return -1
    age = np.arange(hist.shape[1])[::-1]              # 0 = most recent week
    wt = 0.5 ** (age / hl)
    score = (hist * wt).sum(axis=1) / wt.sum()
    j = int(np.argmax(score))
    return j if score[j] > 0 else -1


def run_meta(m, cuts, eff_cache):
    tools = AP.variants()
    base, s15 = [], []
    for fam, _, params in tools:
        base.append(EV.weekly_series(fam, params, m, cuts, 1.0, eff_cache)["strat"])
        s15.append(EV.weekly_series(fam, params, m, cuts, 1.5, eff_cache))
    base = np.vstack(base)
    strat15 = np.vstack([s["strat"] for s in s15])
    long15 = np.vstack([s["long"] for s in s15])
    rdir15 = np.vstack([s["rdir"] for s in s15])
    ntr = np.vstack([s["ntr"] for s in s15])

    # audit: choice at w must not change if weeks >= w are garbage
    rng = np.random.default_rng(5)
    for w in rng.choice(np.arange(META_MIN_WEEKS, len(cuts)), 25, replace=False):
        for hl in (3, 8):
            g = base.copy(); g[:, w:] = rng.normal(0, 1e4, g[:, w:].shape)
            assert meta_choose(base, w, hl) == meta_choose(g, w, hl)
    print("META look-ahead audit: 50/50 choices unchanged under future garbage")

    rows = []
    for hl in (3, 8):
        n = len(cuts)
        s = dict(strat=np.zeros(n), long=np.zeros(n), rdir=np.zeros(n),
                 rtool=np.zeros(n), ntr=np.zeros(n, int))
        picks = []
        for w in range(n):
            j = meta_choose(base, w, hl)
            picks.append(j)
            if j < 0:
                continue
            s["strat"][w] = strat15[j, w]; s["long"][w] = long15[j, w]
            s["rdir"][w] = rdir15[j, w]; s["rtool"][w] = strat15[:, w].mean()
            s["ntr"][w] = ntr[j, w]
        r = EV.summarize("M", s, controls=("long", "rdir", "rtool"))
        base_mean = float(np.mean([base[j, w] if j >= 0 else 0.0
                                   for w, j in enumerate(picks)]))
        changes = sum(1 for a, b in zip(picks[1:], picks[:-1]) if a != b)
        r.update(family="M", variant=f"META hl={hl}", audit_fail=0,
                 mean_week_bp_base=base_mean,
                 tool_change_rate=changes / max(len(picks) - 1, 1))
        rows.append(r)
    return rows


def main() -> int:
    m = load_canonical()
    cuts = dev_cuts(m)
    print(f"DEV weeks: {len(cuts)}")
    selftest_entries_pool(m, cuts)
    eff_cache: dict = {}
    rows = []
    for fam, name, params in AP2.variants2():
        sig = lambda f, mm, c, p: AP2.tool_signature2(f, mm, c, p)  # noqa: E731
        bad = EV.audit_lookahead(fam, params, m, cuts, sig=sig)
        s15 = EV.weekly_series(fam, params, m, cuts, 1.5, eff_cache, runner=AP2.run_week2)
        s10 = EV.weekly_series(fam, params, m, cuts, 1.0, eff_cache, runner=AP2.run_week2)
        r = EV.summarize(fam, s15)
        r.update(family=fam, variant=name, audit_fail=len(bad),
                 mean_week_bp_base=float(s10["strat"].mean()))
        rows.append(r)
    rows += run_meta(m, cuts, eff_cache)
    for r in rows:
        r["eligible"] = bool(r["audit_fail"] == 0 and r["mean_week_bp"] > 0
                             and r["max_p"] < C.DEV_P_MAX and r["active"] >= FLOOR)
        extra = f" chg={r['tool_change_rate']:.2f}" if "tool_change_rate" in r else ""
        print(f"{r['variant']:24s} audit_fail={r['audit_fail']} active={r['active']:.2f} "
              f"trades={r['trades']:5d} wk_bp(1.5x)={r['mean_week_bp']:+8.2f} "
              f"base={r['mean_week_bp_base']:+8.2f} min_t={r['min_t']:+6.2f} "
              f"max_p={r['max_p']:.4f}{extra} {'ELIGIBLE' if r['eligible'] else ''}")
    df = pd.DataFrame(rows)
    df.to_csv("data/wpwb_search_round2.csv", index=False)
    print(f"\nround 2 variants: {len(df)}; eligible: {int(df.eligible.sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
