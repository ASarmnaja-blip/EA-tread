"""Single A7.2/A7.3 run: external pre-week traces and Fed-cycle FOMC test.

Frozen in docs/WPWB_LIVE_PREREG.md amendments 7 and 7a.  Local-file analysis
only: no MetaTrader5 import and no broker or trading API call.
"""
from __future__ import annotations

import io
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data" / "external"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
sys.path.insert(0, str(ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402
import common as C  # noqa: E402
from backtest_report import load_events  # noqa: E402
from oos_2016 import FOMC, statement_utc  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402

SEED = 20260928
DRAWS = 20_000
P_MAX = 0.05 / 10
START = C.ep(2021, 7, 2)
FINAL_CUT = C.ep(2026, 9, 18) + 22 * C.HOUR + 15 * 60
ERA_SPLIT = C.ep(2024, 1, 1)
GOLD_MARKET = "GOLD - COMMODITY EXCHANGE INC."


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def treasury_series(kind: str, field: str) -> pd.Series:
    rows = []
    for path in sorted(EXT.glob(f"treasury_{kind}_*.xml")):
        root = ET.parse(path).getroot()
        for node in root.iter():
            if local_name(node.tag) != "properties":
                continue
            values = {local_name(child.tag): child.text for child in node}
            if values.get("NEW_DATE") and values.get(field):
                rows.append((pd.Timestamp(values["NEW_DATE"]).normalize(), float(values[field])))
    out = pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date", keep="last")
    return out.sort_values("date").set_index("date").value


def gvz_series() -> pd.Series:
    d = pd.read_csv(EXT / "GVZ_History.csv")
    d["date"] = pd.to_datetime(d.DATE, format="%m/%d/%Y")
    return d.drop_duplicates("date", keep="last").sort_values("date").set_index("date").GVZ.astype(float)


def cftc_managed_money() -> pd.DataFrame:
    use = ["Market_and_Exchange_Names", "Report_Date_as_YYYY-MM-DD",
           "M_Money_Positions_Long_All", "M_Money_Positions_Short_All"]
    rows = []
    for path in sorted(EXT.glob("cftc_fut_disagg_*.zip")):
        with zipfile.ZipFile(path) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as src:
                d = pd.read_csv(src, usecols=use, skipinitialspace=True)
        d = d[d[use[0]].str.strip() == GOLD_MARKET].copy()
        rows.append(d)
    out = pd.concat(rows, ignore_index=True).drop_duplicates(use[1], keep="last")
    out["as_of"] = pd.to_datetime(out[use[1]], utc=True)
    out["net"] = pd.to_numeric(out[use[2]]) - pd.to_numeric(out[use[3]])

    # Default is deliberately after the Friday rebuild.  Exact broker-calendar
    # releases, when present, replace it and allow same-Friday use.
    out["available"] = out.as_of + pd.Timedelta(days=4)
    cal = calendar_feed.load_calendar("data/calendar.csv")
    exact = cal[(cal.event == calendar_feed.COT_GOLD) & cal.actual.notna()].sort_values("time")
    for r in exact.itertuples():
        release = pd.Timestamp(r.time, tz="UTC")
        candidates = out[(out.as_of <= release) & (release - out.as_of <= pd.Timedelta(days=10))]
        if len(candidates):
            out.loc[candidates.as_of.idxmax(), "available"] = release
    out = out.sort_values("available").reset_index(drop=True)
    out["chg4"] = out.net.diff(4)
    pct = []
    for i in range(len(out)):
        window = out.net.iloc[max(0, i - 51):i + 1]
        pct.append(float((window <= out.net.iloc[i]).mean() * 100) if len(window) >= 12 else np.nan)
    out["pct52"] = pct
    return out[["as_of", "available", "net", "chg4", "pct52"]]


def value_at(series: pd.Series, latest_date: pd.Timestamp) -> tuple[float, int]:
    dates = series.index.values.astype("datetime64[D]")
    j = int(np.searchsorted(dates, np.datetime64(latest_date.date()), side="right")) - 1
    return (float(series.iloc[j]), j) if j >= 0 else (np.nan, -1)


def daily_gold_vol(b5, cut: int) -> float:
    latest = pd.Timestamp(datetime.fromtimestamp(cut, timezone.utc).date()) - pd.Timedelta(days=1)
    dates = pd.to_datetime(b5.t, unit="s").normalize()
    d = pd.DataFrame({"date": dates, "close": b5.c}).groupby("date", sort=True).close.last()
    d = d[d.index <= latest]
    r = d.pct_change().dropna().tail(20)
    return float(r.std(ddof=1) * np.sqrt(252) * 100) if len(r) == 20 else np.nan


def weekly_frame() -> pd.DataFrame:
    m = C.Market(combined_bars())
    y2 = treasury_series("nominal", "BC_2YEAR")
    y10 = treasury_series("nominal", "BC_10YEAR")
    r10 = treasury_series("real", "TC_10YEAR")
    gvz = gvz_series()
    cot = cftc_managed_money()
    last = int(m.t[-1]) + C.HOUR
    rows = []
    for raw_cut in m.cuts:
        cut = int(raw_cut)
        if cut < START or cut > FINAL_CUT or cut + C.WEEK > last:
            continue
        lo, hi = m.week_bars(cut)
        if hi - lo < 50:
            continue
        latest = pd.Timestamp(datetime.fromtimestamp(cut, timezone.utc).date()) - pd.Timedelta(days=1)
        values = {}
        for label, series in (("y2", y2), ("y10", y10), ("r10", r10), ("gvz", gvz)):
            now, j = value_at(series, latest)
            values[label] = now
            values[label + "_chg63"] = now - float(series.iloc[j - 63]) if j >= 63 else np.nan
        gold_rv = daily_gold_vol(m.b5, cut)
        cutoff = pd.Timestamp(cut, unit="s", tz="UTC")
        q = cot[cot.available <= cutoff].tail(1)
        rows.append({
            "cut": cut,
            "week": pd.Timestamp(cut, unit="s").date(),
            "era": "A" if cut < ERA_SPLIT else "B",
            "gold_bp": float((m.c[hi - 1] / m.o[lo] - 1) * 1e4),
            "N1_y2_level": values["y2"],
            "N2_y2_chg13w": values["y2_chg63"],
            "N3_y10_level": values["y10"],
            "N4_y10_chg13w": values["y10_chg63"],
            "R1_real10_level": values["r10"],
            "R2_real10_chg13w": values["r10_chg63"],
            "G1_gvz_rv_ratio": values["gvz"] / gold_rv if np.isfinite(gold_rv) and gold_rv > 0 else np.nan,
            "G2_gvz_chg13w": values["gvz_chg63"],
            "C1_mm_pct52": float(q.pct52.iloc[0]) if len(q) else np.nan,
            "C2_mm_chg4": float(q.chg4.iloc[0]) if len(q) else np.nan,
            "fed_y2_chg63": values["y2_chg63"],
        })
    out = pd.DataFrame(rows)
    out["gold_abs_bp"] = out.gold_bp.abs()
    return out


def timing_test(x: np.ndarray, y: np.ndarray, direction: int, seed: int) -> tuple[float, float]:
    xr = stats.rankdata(x).astype(float)
    yr = stats.rankdata(y).astype(float)
    xr = (xr - xr.mean()) / xr.std()
    yr = (yr - yr.mean()) / yr.std()
    rho = float(np.mean(xr * yr))
    observed = direction * rho
    rng = np.random.default_rng(seed)
    shifts = rng.integers(1, len(y), size=DRAWS)
    by_shift = np.array([direction * float(np.mean(xr * np.roll(yr, shift)))
                         for shift in range(1, len(y))])
    controls = by_shift[shifts - 1]
    p = float((1 + (controls >= observed).sum()) / (DRAWS + 1))
    return rho, p


def run_external_tests(wk: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("N1", "N1_y2_level", "gold_bp", -1),
        ("N2", "N2_y2_chg13w", "gold_bp", -1),
        ("N3", "N3_y10_level", "gold_bp", -1),
        ("N4", "N4_y10_chg13w", "gold_bp", -1),
        ("R1", "R1_real10_level", "gold_bp", -1),
        ("R2", "R2_real10_chg13w", "gold_bp", -1),
        ("G1", "G1_gvz_rv_ratio", "gold_abs_bp", +1),
        ("G2", "G2_gvz_chg13w", "gold_abs_bp", +1),
        ("C1", "C1_mm_pct52", "gold_bp", -1),
        ("C2", "C2_mm_chg4", "gold_bp", +1),
    ]
    results = []
    print("== A7.2 EXTERNAL PRE-WEEK TRACES ==")
    for number, (name, feature, target, direction) in enumerate(specs):
        row = {"trace": name, "feature": feature, "target": target, "registered_sign": direction}
        passes = []
        pieces = []
        for era_idx, era in enumerate(("A", "B")):
            z = wk[wk.era == era][[feature, target]].dropna()
            if len(z) < 20 or z[feature].nunique() < 3:
                rho = p = np.nan
                passed = False
                status = "NOT ASSESSED"
            else:
                rho, p = timing_test(z[feature].to_numpy(), z[target].to_numpy(), direction,
                                     SEED + number * 10 + era_idx)
                passed = bool(direction * rho > 0 and p < P_MAX)
                status = "PASS" if passed else "FAIL"
            row.update({f"n_{era}": len(z), f"rho_{era}": rho, f"p_{era}": p,
                        f"status_{era}": status})
            passes.append(passed)
            pieces.append(f"{era}: n={len(z)} rho={rho:+.3f} p={p:.4f} {status}"
                          if np.isfinite(rho) else f"{era}: n={len(z)} NOT ASSESSED")
        row["PASS"] = bool(all(passes))
        results.append(row)
        print(f"{name:2s} {feature:20s} | " + " | ".join(pieces)
              + f" -> {'PASS' if row['PASS'] else 'FAIL'}")
    out = pd.DataFrame(results)
    print(f"A7.2 RESULT: {int(out.PASS.sum())} of 10 pass (threshold p<{P_MAX:.3f} in both eras)\n")
    return out


def fomc_epochs() -> list[int]:
    old = [statement_utc(s) for s in FOMC if s.startswith("2021-")]
    ev = load_events()
    new = ev.loc[ev.event == "Fed Interest Rate Decision", "ts"].astype(int).tolist()
    return sorted(set(old + new))


def binomial_power(n: int, true_hit: float) -> float:
    critical = next((k for k in range(n + 1) if stats.binom.sf(k - 1, n, 0.5) < 0.05), n + 1)
    return float(stats.binom.sf(critical - 1, n, true_hit)) if critical <= n else 0.0


def run_fomc_test(wk: pd.DataFrame) -> pd.DataFrame:
    announcements = fomc_epochs()
    wk = wk.copy()
    wk["fomc"] = [any(int(c) <= ts < int(c) + C.WEEK for ts in announcements) for c in wk.cut]
    wk["fed_direction"] = np.where(wk.fed_y2_chg63 <= 0, 1, -1)
    wk["cycle_score_bp"] = wk.fed_direction * wk.gold_bp
    rows = []
    print("== A7.3 FED-DIRECTION x FOMC WEEK ==")
    for era_idx, era in enumerate(("A", "B")):
        all_era = wk[(wk.era == era) & wk.fed_y2_chg63.notna()].reset_index(drop=True)
        z = all_era[all_era.fomc].copy()
        score = z.cycle_score_bp.to_numpy()
        observed = float(score.mean())
        rng = np.random.default_rng(SEED + 100 + era_idx)
        signs = rng.choice((-1, 1), size=(DRAWS, len(z)))
        random_direction = (signs * np.abs(z.gold_bp.to_numpy())).mean(axis=1)
        p_direction = float((1 + (random_direction >= observed).sum()) / (DRAWS + 1))
        random_week = np.empty(DRAWS)
        pool = (all_era.fed_direction * all_era.gold_bp).to_numpy()
        for i in range(DRAWS):
            random_week[i] = rng.choice(pool, size=len(z), replace=False).mean()
        p_week = float((1 + (random_week >= observed).sum()) / (DRAWS + 1))
        hit = float((score > 0).mean())
        passed = bool(observed > 0 and hit > 0.5 and p_direction < 0.05 and p_week < 0.05)
        transitions = int((z.fed_direction.to_numpy()[1:] != z.fed_direction.to_numpy()[:-1]).sum())
        row = dict(era=era, n=len(z), dovish=int((z.fed_direction == 1).sum()),
                   hawkish=int((z.fed_direction == -1).sum()), mean_score_bp=observed,
                   median_score_bp=float(np.median(score)), hit_rate=hit,
                   p_random_direction=p_direction, p_random_week=p_week,
                   signal_transitions=transitions, PASS=passed)
        rows.append(row)
        print(f"era {era}: n={len(z)} (dovish {row['dovish']}, hawkish {row['hawkish']}), "
              f"score mean {observed:+.1f} bp median {row['median_score_bp']:+.1f}, hit {hit:.1%}, "
              f"p random-direction={p_direction:.4f}, p random-week={p_week:.4f}, "
              f"transitions={transitions} -> {'PASS' if passed else 'FAIL'}")
        print("  binomial power at true hit 60/65/70%: "
              + "/".join(f"{binomial_power(len(z), p):.1%}" for p in (0.60, 0.65, 0.70)))
    out = pd.DataFrame(rows)
    print(f"A7.3 RESULT: {'PASS' if out.PASS.all() else 'FAIL'}; "
          "cycle-level generalisation: NOT ASSESSED\n")
    return out


def old_cycle_context() -> dict:
    d = np.load("data/fresh/XAUUSD_D1_2016_2020.npz")
    t, o, h, l, c = (d[k] for k in ("t", "o", "h", "l", "c"))
    wd = ((t // 86400) + 3) % 7
    yr = pd.to_datetime(t, unit="s").year.to_numpy()
    ranges = h - l
    all_days = {statement_utc(s) // 86400 for s in FOMC}
    verified = []
    for s in FOMC:
        a = statement_utc(s)
        if not (C.ep(2016, 8, 9) <= a < C.ep(2020, 12, 4)):
            continue
        k = np.flatnonzero(t // 86400 == a // 86400)
        if not len(k):
            continue
        k = int(k[0])
        ref = ranges[(wd == 2) & (yr == yr[k]) & ~np.isin(t // 86400, list(all_days))]
        if ranges[k] > np.median(ref):
            verified.append(a)

    y2 = treasury_series("nominal", "BC_2YEAR")
    rows = []
    cut = _week_boundary(C.ep(2016, 8, 9))
    end = C.ep(2020, 12, 4)
    while cut + C.WEEK <= end:
        idx = np.flatnonzero((t >= cut) & (t < cut + C.WEEK))
        if len(idx) >= 4:
            latest = pd.Timestamp(datetime.fromtimestamp(cut, timezone.utc).date()) - pd.Timedelta(days=1)
            y, j = value_at(y2, latest)
            chg = y - float(y2.iloc[j - 63]) if j >= 63 else np.nan
            if any(cut <= a < cut + C.WEEK for a in verified) and np.isfinite(chg):
                gross = (c[int(idx[-1])] / o[int(idx[0])] - 1) * 1e4
                direction = 1 if chg <= 0 else -1
                rows.append((gross * direction, direction))
        cut += C.WEEK
    score = np.array([x[0] for x in rows])
    directions = np.array([x[1] for x in rows])
    result = dict(n=len(score), dovish=int((directions == 1).sum()), hawkish=int((directions == -1).sum()),
                  mean_score_bp=float(score.mean()), median_score_bp=float(np.median(score)),
                  hit_rate=float((score > 0).mean()),
                  signal_transitions=int((directions[1:] != directions[:-1]).sum()))
    print("== NON-CONFIRMATORY 2016-08..2020-11 CONTEXT ==")
    print(f"n={result['n']} verified FOMC weeks (dovish {result['dovish']}, hawkish {result['hawkish']}), "
          f"score mean {result['mean_score_bp']:+.1f} bp, median {result['median_score_bp']:+.1f}, "
          f"hit {result['hit_rate']:.1%}, transitions={result['signal_transitions']}")
    print("This price period was examined in Part 34: context only, not confirmation.\n")
    return result


def main() -> int:
    wk = weekly_frame()
    print(f"weekly outcomes: {len(wk)} ({wk.week.iloc[0]} .. {wk.week.iloc[-1]}), "
          f"era A {(wk.era == 'A').sum()}, era B {(wk.era == 'B').sum()}\n")
    traces = run_external_tests(wk)
    fomc = run_fomc_test(wk)
    context = old_cycle_context()
    wk.to_csv("data/wpwb_external_traces_weekly.csv", index=False)
    traces.to_csv("data/wpwb_external_trace_results.csv", index=False)
    fomc.to_csv("data/wpwb_fomc_cycle_results.csv", index=False)
    pd.DataFrame([context]).to_csv("data/wpwb_fomc_cycle_old_context.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
