"""WPWB Outlook shadow log (docs/WPWB_OUTLOOK_SHADOW_PREREG.md). Model OUTLOOK-V2.0.
Records next-week volatility forecasts BEFORE the week starts; changes nothing
in the risk report, sizing or orders. Downloads the Cboe GVZ file once per run
(operator permission 2026-09-29). Usage:
  python research/wpwb_weekly/outlook_shadow.py            log the latest cut, then score finished weeks
  python research/wpwb_weekly/outlook_shadow.py --score    only rescore
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import outlook_dev as O  # noqa: E402
import vol as V  # noqa: E402

VERSION = "OUTLOOK-V2.0"
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
SPLICE = int(np.datetime64("2026-08-21T22:15:00", "s").astype(np.int64))      # last Dukascopy week start
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))     # first scored cut
SLACK = 6 * 3600
GVZ_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv"
DIR = ROOT / "data" / "wpwb_weekly"
GVZ_DIR = DIR / "gvz"
ENS_DIR = DIR / "outlook_shadow_ens"
LOG = DIR / "outlook_shadow_log.csv"
DRY = DIR / "outlook_shadow_dryrun.csv"
SCORES = DIR / "outlook_shadow_scores.csv"
LATEST = DIR / "outlook_shadow_latest.md"
MODELS = ("B0", "HAR", "MVOL")
LABELS_TH = ("สงบ", "ปกติ", "ผันผวนสูง", "ผันผวนรุนแรง")


def utc(ep):
    return datetime.fromtimestamp(int(ep), timezone.utc).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ inputs
def fetch_gvz():
    """One polite download; the file is stored unchanged with its hash."""
    GVZ_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(GVZ_URL, headers={"User-Agent": "Mozilla/5.0 (EA-tread weekly research log)"})
    for attempt in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=60).read()
            break
        except Exception as e:  # noqa: BLE001
            err = repr(e)
            time.sleep(30)
    else:
        return None, dict(gvz_status=f"FETCH_FAILED {err[:80]}")
    now = datetime.now(timezone.utc)
    f = GVZ_DIR / f"GVZ_{now:%Y%m%dT%H%M%SZ}.csv"
    f.write_bytes(raw)
    meta = dict(gvz_status="OK", gvz_file=f.name, gvz_retrieved_utc=now.strftime("%Y-%m-%d %H:%M:%S"),
                gvz_bytes=len(raw), gvz_sha256=hashlib.sha256(raw).hexdigest())
    return f, meta


def gvz_arrays(path):
    g = pd.read_csv(path)
    g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
    g = g.dropna(subset=["GVZ"]).sort_values("d")
    return g.d.astype("datetime64[s]").astype(np.int64).to_numpy(), g.GVZ.astype(float).to_numpy(), g


def revisions(g_new):
    """Rows dated in the development file whose value differs in the new snapshot."""
    old = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    old["d"] = pd.to_datetime(old.DATE, format="%m/%d/%Y")
    m = old.merge(g_new[["d", "GVZ"]], on="d", suffixes=("_old", "_new"))
    return int((np.abs(m.GVZ_old - m.GVZ_new) > 1e-9).sum()), len(m)


def rv_series(cut_target):
    """Weekly RV on the grid FIRST_CUT..cut_target (last element = target week, NaN).
    Dukascopy for week starts <= SPLICE, live Exness after; an Exness week counts
    only if the feed reaches its end (minus the Friday slack)."""
    import bars as BR
    cuts = np.arange(FIRST_CUT, cut_target + 1, WEEK, dtype=np.int64)
    rv = np.full(len(cuts), np.nan)
    h, t, cuts_d, *_ = O.load()
    kd = cuts <= SPLICE
    rv[kd] = O.weekly(t, *(h[k].to_numpy(float) for k in ("c", "h", "l")), cuts[kd])
    m = BR.market(BR.load_bars(frozen=False))
    te = np.asarray(m.t, np.int64)
    end = int(te[-1]) + 3600
    ke = (cuts > SPLICE) & (cuts < cut_target)
    if ke.any():
        r = O.weekly(te, np.asarray(m.c, float), np.asarray(m.h, float), np.asarray(m.l, float), cuts[ke])
        complete = cuts[ke] + WEEK - SLACK <= end
        rv[ke] = np.where(complete, r, np.nan)
    return cuts, rv, end


def features(cuts, rv, gd, gv):
    n = len(cuts)
    lv = np.log(rv)
    F = {k: np.full(n, np.nan) for k in ("L1", "L4", "L26", "G")}
    for k in range(26, n):
        w = lv[k - 26:k]
        if np.isfinite(w).all():
            F["L1"][k], F["L4"][k], F["L26"][k] = w[-1], w[-4:].mean(), w.mean()
        cut = int(cuts[k])
        j = np.searchsorted(gd, cut - 86400, side="right") - 1
        if j >= 0 and gd[j] > cut - 7 * 86400:
            F["G"][k] = math.log((gv[j] / 100) ** 2 / 52 * 1e8)
    return F


def forecasts(cuts, rv, F):
    lv = np.log(rv)
    n = len(cuts)
    one = np.ones(n)
    har_X = np.c_[one, F["L1"], F["L4"], F["L26"]]
    f = V.ewma_forecast(rv)
    mu = {"B0": np.where(f > 0, np.log(np.where(f > 0, f, 1)), np.nan)}
    mu["HAR"], _ = O.ols_prequential(har_X, lv)
    mu["MVOL"], _ = O.ols_prequential(np.c_[har_X, F["G"]], lv)
    return O.ensembles(rv, mu)


# ------------------------------------------------------------------ log
def read_log(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def append(path, row):
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def log_cut(now=None):
    import bars as BR
    now = int(time.time()) if now is None else now
    C = BR.last_cut_before(now)
    target = LOG if C >= FORWARD else DRY
    old = read_log(target)
    if len(old) and (old.cut_epoch == C).any():
        print(f"cut {utc(C)} already logged in {target.name}; refusing to rewrite")
        return 0
    row = dict(cut_utc=utc(C), cut_epoch=C, generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
               version=VERSION, run="FORWARD" if C >= FORWARD else "DRY_RUN")
    cuts, rv, end = rv_series(C)
    K = len(cuts) - 1
    row["feed_end_utc"] = utc(end)
    row["rv_hash"] = hashlib.sha256(np.nan_to_num(rv[:K], nan=-1.0).tobytes()).hexdigest()[:16]
    gpath, gmeta = fetch_gvz()
    row.update(gmeta)
    if gpath is not None:
        gd, gv, g = gvz_arrays(gpath)
        nrev, nover = revisions(g)
        row["gvz_rows_revised_vs_dev_file"] = f"{nrev}/{nover}"
        # the same Thursday in earlier snapshots
        j = np.searchsorted(gd, C - 86400, side="right") - 1
        row["gvz_row_date"] = str(pd.to_datetime(gd[j], unit="s").date()) if j >= 0 else ""
        row["gvz_value"] = float(gv[j]) if j >= 0 else np.nan
    else:
        gd, gv = np.array([], np.int64), np.array([])
    F = features(cuts, rv, gd, gv)
    ens = forecasts(cuts, rv, F)
    mk = O.med52(rv)
    row["m_k"] = float(mk[K])
    prev_ratio = rv[K - 1] / mk[K - 1] if np.isfinite(mk[K - 1]) else np.nan
    row["current_class"] = int(O.cls(np.array([prev_ratio]))[0])
    issued = []
    ENS_DIR.mkdir(parents=True, exist_ok=True)
    draws = {}
    for mdl in MODELS:
        e = ens[mdl][K]
        if e is None or not np.isfinite(mk[K]):
            row[f"{mdl}_status"] = "NOT_ISSUED"
            continue
        issued.append(mdl)
        draws[mdl] = e
        lm = math.log(mk[K])
        cdf = [float(np.mean(e < lm + math.log(q))) for q in O.EDGES]
        probs = [cdf[0], cdf[1] - cdf[0], cdf[2] - cdf[1], 1 - cdf[2]]
        row.update({f"{mdl}_status": "ISSUED", f"{mdl}_var": float(np.mean(np.exp(e))),
                    **{f"{mdl}_rv_q{q}": float(np.exp(np.quantile(e, q / 100))) for q in (10, 50, 90)},
                    **{f"{mdl}_p_{c}": p for c, p in zip(("calm", "normal", "high", "extreme"), probs)},
                    f"{mdl}_p_high_or_extreme": probs[2] + probs[3]})
    np.savez(ENS_DIR / f"{row['run']}_{pd.Timestamp(C, unit='s'):%Y%m%dT%H%M}.npz", **draws)
    row["status"] = "OK" if len(issued) == 3 else ("PARTIAL " + ",".join(issued) if issued else "NONE_ISSUED")
    append(target, row)
    write_latest(row)
    print(f"logged {row['run']} cut {row['cut_utc']}: {row['status']} -> {target.name}")
    return 0


def write_latest(r):
    cur = r.get("current_class", -1)
    lines = [f"# WPWB Outlook (shadow) — สัปดาห์เริ่ม {r['cut_utc']} UTC", "",
             "> **shadow — ไม่ได้ใช้กำหนดขนาดไม้** ขนาดไม้ยังใช้ EWMA ตามรายงานความเสี่ยงเดิม",
             "> ไม่มีการพยากรณ์ทิศทาง", "",
             f"สัปดาห์ที่เพิ่งจบ: **{LABELS_TH[cur] if 0 <= cur <= 3 else 'ไม่ทราบ'}**  ·  สถานะ: {r['status']}  ·  รอบ: {r['run']}", "",
             "| โมเดล | ความผันผวนคาด (bp/สัปดาห์) | ช่วง 10–90% | P(สงบ) | P(ปกติ) | P(สูง) | P(รุนแรง) |",
             "|---|---|---|---|---|---|---|"]
    for mdl in MODELS:
        if r.get(f"{mdl}_status") != "ISSUED":
            lines.append(f"| {mdl} | ไม่ออก | | | | | |")
            continue
        lines.append(f"| {mdl} | {math.sqrt(r[mdl + '_var']):.0f} | {math.sqrt(r[mdl + '_rv_q10']):.0f}–{math.sqrt(r[mdl + '_rv_q90']):.0f} | "
                     + " | ".join(f"{100 * r[f'{mdl}_p_{c}']:.0f}%" for c in ("calm", "normal", "high", "extreme")) + " |")
    lines += ["", f"GVZ: {r.get('gvz_value', '')} (วันที่ {r.get('gvz_row_date', '')}, ดาวน์โหลด {r.get('gvz_retrieved_utc', '')} UTC, {r.get('gvz_status', '')})",
              "", "B0 = EWMA ที่ใช้อยู่จริง · HAR = ความผันผวนย้อนหลัง 1/4/26 สัปดาห์ · MVOL = HAR + GVZ"]
    LATEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ scoring
def score_all(now=None):
    L = read_log(LOG)
    if not len(L):
        print("no forward rows yet; nothing to score")
        return 0
    now = int(time.time()) if now is None else now
    last = int(L.cut_epoch.max())
    cuts, rv, end = rv_series(last + WEEK)
    idx = {int(c): i for i, c in enumerate(cuts)}
    rows = []
    for _, r in L.iterrows():
        C = int(r.cut_epoch)
        i = idx.get(C)
        if i is None or not np.isfinite(rv[i]):
            continue
        f = ENS_DIR / f"FORWARD_{pd.Timestamp(C, unit='s'):%Y%m%dT%H%M}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        y = math.log(rv[i])
        out = dict(cut_utc=r.cut_utc, rv=rv[i], realised_class=int(O.cls(np.array([rv[i] / r.m_k]))[0]))
        for mdl in MODELS:
            if mdl not in z:
                continue
            e = z[mdl]
            F_ = float(np.mean(np.exp(e)))
            out[f"{mdl}_crps"] = O.crps(e, y)
            out[f"{mdl}_qlike"] = rv[i] / F_ - math.log(rv[i] / F_) - 1
            out[f"{mdl}_in80"] = float(np.quantile(e, .1) <= y <= np.quantile(e, .9))
            out[f"{mdl}_p_high_or_extreme"] = r.get(f"{mdl}_p_high_or_extreme")
        rows.append(out)
    S = pd.DataFrame(rows)
    S.to_csv(SCORES, index=False)
    print(f"scored {len(S)} forward weeks -> {SCORES.name}")
    if len(S) >= 26:
        for a, b in (("MVOL", "B0"), ("MVOL", "HAR")):
            d = (S[f"{a}_crps"] - S[f"{b}_crps"]).dropna()
            lo, hi = O.block_ci(d.to_numpy(), 8)
            print(f"  running {a} - {b} CRPS {d.mean():+.4f} [{lo:+.4f}, {hi:+.4f}] over {len(d)} weeks (descriptive)")
    return 0


def main() -> int:
    os.chdir(ROOT)
    if "--score" not in sys.argv:
        log_cut()
    return score_all()


if __name__ == "__main__":
    sys.exit(main())
