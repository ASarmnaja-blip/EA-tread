"""Round 3 (final) of the WPWB edge search (prereg Amendment 3). DEV only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approaches as AP  # noqa: E402
import common as C  # noqa: E402
import evaluate as EV  # noqa: E402
from approaches import _date_spans, tsm_tool  # noqa: E402
from run_dev import dev_cuts, load_canonical  # noqa: E402


# ------------------------------------------------------------------ K
def tsmi_week(fam, m, cut, params):
    d = tsm_tool(m, cut, params["L"])
    lo, hi = m.week_bars(cut)
    if d == 0 or hi <= lo:
        return [], []
    trades = []
    for f, e in _date_spans(m, lo, hi):
        idx = [i for i in range(f, e + 1) if 7 <= int(m.hour[i]) <= 20]
        if idx:
            trades.append((idx[0], idx[-1], d))
    return trades, []


# ------------------------------------------------------------------ I
def sigma_at(m, cut, hl):
    a = int(np.searchsorted(m.t, cut - 26 * C.WEEK))
    b = m.last_bar_before(cut) + 1
    spans = _date_spans(m, a, b)
    if len(spans) < 40:
        return np.nan
    f = np.array([s for s, _ in spans]); e = np.array([x for _, x in spans])
    r = (m.c[e] - m.o[f]) / m.o[f]
    w = 0.5 ** (((cut - m.t[f]) / C.WEEK) / hl)
    mu = (w * r).sum() / w.sum()
    return float(np.sqrt((w * (r - mu) ** 2).sum() / w.sum()))


def volman_size(m, cut, hl, sig_cache):
    def sig(c):
        key = (c, hl)
        if key not in sig_cache:
            sig_cache[key] = sigma_at(m, c, hl)
        return sig_cache[key]
    s_now = sig(cut)
    ref = [sig(cut - j * C.WEEK) for j in range(1, 53)]
    ref = [x for x in ref if np.isfinite(x)]
    if not np.isfinite(s_now) or s_now <= 0 or len(ref) < 8:
        return 1.0
    return float(min(2.0, np.median(ref) / s_now))


def volman_series(m, cuts, hl, stress, sig_cache):
    n = len(cuts)
    strat = np.zeros(n); lng = np.zeros(n); rdir = np.zeros(n)
    size = np.zeros(n); ntr = np.zeros(n, int)
    for w, cut in enumerate(cuts):
        lo, hi = m.week_bars(int(cut))
        if hi <= lo:
            continue
        s = volman_size(m, int(cut), hl, sig_cache)
        pl = float(m.pnl_bp([lo], [hi - 1], [1], stress)[0])
        ps = float(m.pnl_bp([lo], [hi - 1], [-1], stress)[0])
        strat[w] = s * pl; lng[w] = pl; rdir[w] = s * 0.5 * (pl + ps)
        size[w] = s; ntr[w] = 1
    act = size[ntr > 0]
    s_bar = act.mean() if len(act) else 1.0
    return dict(strat=strat, longmatch=s_bar * lng, rdir=rdir, ntr=ntr), s_bar


def main() -> int:
    m = load_canonical()
    cuts = dev_cuts(m)
    print(f"DEV weeks: {len(cuts)}")
    rows = []

    for L in (8, 13):
        name = f"TSMI L={L}"
        sig = lambda f, mm, c, p: tsm_tool(mm, c, p["L"])  # noqa: E731
        bad = EV.audit_lookahead("K", dict(L=L), m, cuts, sig=sig)
        s15 = EV.weekly_series("K", dict(L=L), m, cuts, 1.5, {}, runner=tsmi_week)
        s10 = EV.weekly_series("K", dict(L=L), m, cuts, 1.0, {}, runner=tsmi_week)
        r = EV.summarize("K", s15, controls=("long", "rdir"))
        r.update(family="K", variant=name, audit_fail=len(bad), floor=0.5,
                 mean_week_bp_base=float(s10["strat"].mean()))
        rows.append(r)

    sig_cache: dict = {}
    for hl in (4, 13):
        name = f"VOLMAN hl={hl}"
        sig = lambda f, mm, c, p: round(volman_size(mm, c, p["hl"], {}), 10)  # noqa: E731
        bad = EV.audit_lookahead("I", dict(hl=hl), m, cuts, n_checks=10, sig=sig)
        s15, sbar = volman_series(m, cuts, hl, 1.5, sig_cache)
        s10, _ = volman_series(m, cuts, hl, 1.0, sig_cache)
        r = EV.summarize("I", s15, controls=("longmatch", "rdir"))
        r.update(family="I", variant=f"{name} (mean size {sbar:.2f})",
                 audit_fail=len(bad), floor=0.5,
                 mean_week_bp_base=float(s10["strat"].mean()))
        rows.append(r)

    eff: dict = {}
    for z in (3.0, 4.0):
        for H in (2, 6):
            p = dict(z=z, H=H, gated=False)
            bad = EV.audit_lookahead("D-ungated", p, m, cuts)
            s15 = EV.weekly_series("D-ungated", p, m, cuts, 1.5, eff)
            s10 = EV.weekly_series("D-ungated", p, m, cuts, 1.0, eff)
            r = EV.summarize("D-ungated", s15)
            r.update(family="L", variant=f"CHOPREV-X z={z} H={H}", audit_fail=len(bad),
                     floor=0.25, mean_week_bp_base=float(s10["strat"].mean()))
            rows.append(r)

    for r in rows:
        r["eligible"] = bool(r["audit_fail"] == 0 and r["mean_week_bp"] > 0
                             and r["max_p"] < C.DEV_P_MAX and r["active"] >= r["floor"])
        print(f"{r['variant']:28s} audit_fail={r['audit_fail']} active={r['active']:.2f} "
              f"trades={r['trades']:5d} wk_bp(1.5x)={r['mean_week_bp']:+8.2f} "
              f"base={r['mean_week_bp_base']:+8.2f} min_t={r['min_t']:+6.2f} "
              f"max_p={r['max_p']:.4f} {'ELIGIBLE' if r['eligible'] else ''}")
    df = pd.DataFrame(rows)
    df.to_csv("data/wpwb_search_round3.csv", index=False)
    print(f"\nround 3 variants: {len(df)}; eligible: {int(df.eligible.sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
