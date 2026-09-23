"""Past-only macro context challenger for the K=5 diverse weekly policy.

The challenger is deliberately nested: every week's ridge model is trained
only on weekly outcomes already completed before that cutoff.  It may gate a
family but never changes that week's price-selected entry geometry.  Missing
external history is explicit and imputed from the training sample only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cftc_legacy
import data as D
import evolution_candidate_validation as valid
import evolution_portfolio_audit as audit
import treasury_real_yields


DAY = 86400
MIN_TRAIN_WEEKS = 52
RIDGE = 10.0
SETUPS = ("breakout", "pullback", "sweep", "failed", "vwap", "expansion")


def daily_close(bars: D.Bars) -> pd.Series:
    idx = pd.to_datetime(bars.t, unit="s", utc=True)
    return pd.Series(bars.c, index=idx).groupby(idx.floor("D")).last().sort_index()


def _returns(s: pd.Series, cut: pd.Timestamp, days: int) -> float:
    x = s[s.index < cut]
    if len(x) < 2:
        return float("nan")
    old = x[x.index <= cut - pd.Timedelta(days=days)]
    if not len(old):
        return float("nan")
    return float(x.iloc[-1] / old.iloc[-1] - 1.0)


def _vol(s: pd.Series, cut: pd.Timestamp, days: int) -> float:
    x = s[(s.index < cut) & (s.index >= cut - pd.Timedelta(days=days))]
    return float(x.pct_change().std()) if len(x) >= 10 else float("nan")


def features(cuts: list[int], xau: D.Bars) -> tuple[np.ndarray, list[str]]:
    xau_d = daily_close(xau)
    dxy_d = daily_close(D.load_csv("data/DXY_M5.csv"))
    tips = treasury_real_yields.load().copy()
    # Treat each Treasury close as available only on the following UTC day.
    tips["available"] = tips.time + pd.Timedelta(days=1)
    cot = cftc_legacy.load()
    names = ["xau_ret20", "xau_ret60", "xau_vol20", "dxy_ret20",
             "tips10y", "tips_change20", "cot_pct", "cot_change"]
    rows = []
    for epoch in cuts:
        cut = pd.Timestamp(epoch, unit="s", tz="UTC")
        tr = tips[tips.available < cut]
        if len(tr):
            old = tr[tr.available <= cut - pd.Timedelta(days=20)]
            tip_level = float(tr.tips10y.iloc[-1])
            tip_chg = (tip_level - float(old.tips10y.iloc[-1])
                       if len(old) else float("nan"))
        else:
            tip_level = tip_chg = float("nan")
        cp = cot[cot.available < cut]
        cot_pct = float(cp.pct_rank.iloc[-1]) / 100.0 if len(cp) else float("nan")
        cot_chg = float(cp.chg.iloc[-1]) / 100.0 if len(cp) else float("nan")
        rows.append([
            _returns(xau_d, cut, 20), _returns(xau_d, cut, 60),
            _vol(xau_d, cut, 20), _returns(dxy_d, cut, 20),
            tip_level, tip_chg, cot_pct, cot_chg,
        ])
    return np.asarray(rows, float), names


def ridge_predict(x: np.ndarray, y: np.ndarray, current: np.ndarray,
                  cols: list[int]) -> float:
    tx = x[:, cols].copy()
    cx = current[cols].copy()
    missing = ~np.isfinite(tx)
    cmissing = ~np.isfinite(cx)
    med = np.nanmedian(tx, axis=0)
    med[~np.isfinite(med)] = 0.0
    tx = np.where(missing, med, tx)
    cx = np.where(cmissing, med, cx)
    # Availability flags prevent an imputed zero from pretending data existed.
    tx = np.c_[tx, missing.astype(float)]
    cx = np.r_[cx, cmissing.astype(float)]
    mean = tx.mean(axis=0)
    std = tx.std(axis=0)
    std[std < 1e-9] = 1.0
    z = (tx - mean) / std
    cz = (cx - mean) / std
    design = np.c_[np.ones(len(z)), z]
    penalty = np.eye(design.shape[1]) * RIDGE
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return float(np.r_[1.0, cz] @ beta)


def family_week_rows(b5, uni, meta, rankings):
    out = []
    for cut, end, ranked in rankings:
        week = {}
        # Build the top candidate of every setup.  The base K5 later keeps only
        # the first five in global order; the sixth outcome remains available
        # as past training data after that week is over.
        for setup in SETUPS:
            tag = next((x for x in ranked if meta[x]["setup"] == setup), None)
            if tag is None:
                week[setup] = []
                continue
            a = uni[tag]
            mask = (a["t_in"] >= cut) & (a["t_in"] < end)
            z = []
            for j in np.flatnonzero(mask):
                bar = int(a["sigk"][j])
                sp = max(float(b5.sp[bar]), audit.wf.E.SPREAD_FALLBACK)
                execution = sp + audit.wf.E.COMMISSION_RT + 2 * audit.wf.E.SLIP_PER_FILL
                stress = float(a["net"][j] - 0.5 * execution / a["risk"][j])
                z.append(audit.Trade(int(a["t_in"][j]), int(a["t_out"][j]),
                                     float(a["net"][j]), float(a["dollars"][j]),
                                     float(a["risk"][j]), tag, stress,
                                     float(a["entry"][j]), int(a["sigk"][j]),
                                     int(a["exit_k"][j]), int(a["direction"][j])))
            week[setup] = z
        out.append(week)
    return out


def challenger(rankings, meta, week_rows, x, cols: list[int]):
    chosen_rows = []
    predictions = []
    for i, (_cut, _end, ranked) in enumerate(rankings):
        base = valid.choose_five(ranked, meta)
        base_setups = [meta[t]["setup"] for t in base]
        if i < MIN_TRAIN_WEEKS:
            keep = base_setups
            pred = {s: float("nan") for s in base_setups}
        else:
            pred = {}
            for setup in base_setups:
                y = np.array([sum(r.net_r for r in week_rows[j][setup])
                              for j in range(i)], float)
                # One crisis week must not dictate the next regime decision.
                y = np.clip(y, -20.0, 20.0)
                pred[setup] = ridge_predict(x[:i], y, x[i], cols)
            keep = [s for s in base_setups if pred[s] > 0]
            if len(keep) < 3:
                keep = sorted(base_setups, key=lambda s: pred[s], reverse=True)[:3]
        for setup in keep:
            chosen_rows.extend(week_rows[i][setup])
        predictions.append(pred)
    return chosen_rows, predictions


def main() -> int:
    b5 = audit.hist.load_history()
    first, last = int(b5.t[0]), int(b5.t[-1] + b5.step)
    uni, meta = audit.load_universe(b5)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    cuts = [x[0] for x in rankings]
    x, names = features(cuts, b5)
    weekly_rows = family_week_rows(b5, uni, meta, rankings)
    base, _ = audit.weekly_portfolio(b5, uni, meta, rankings, purged, 5, True)
    print("feature_names", names)
    print("base", audit.metrics(base))
    for label, cols in (("PRICE_ONLY", [0, 1, 2]),
                        ("PRICE_PLUS_DXY_YIELD_COT", list(range(len(names))))):
        rows, preds = challenger(rankings, meta, weekly_rows, x, cols)
        print(label, audit.metrics(rows))
        print("latest_prediction", preds[-1])
    print("latest_context", dict(zip(names, x[-1])))
    print("latest_cut", datetime.fromtimestamp(cuts[-1], timezone.utc).isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
