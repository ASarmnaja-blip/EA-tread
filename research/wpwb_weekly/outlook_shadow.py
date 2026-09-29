"""WPWB Outlook shadow log (docs/WPWB_OUTLOOK_SHADOW_PREREG.md v1 + Amendment 1). Model OUTLOOK-V2.0.
Records next-week volatility forecasts BEFORE the target week opens; changes nothing
in the risk report, sizing or orders. Downloads the Cboe GVZ file once per run
(operator permission 2026-09-29). Usage:
  python research/wpwb_weekly/outlook_shadow.py                    archive inputs, log the latest cut, score
  python research/wpwb_weekly/outlook_shadow.py --score            only rescore
  python research/wpwb_weekly/outlook_shadow.py --freeze-dukascopy one-time: write the frozen Dukascopy RV file
"""
from __future__ import annotations

import csv
import hashlib
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
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))     # first forward cut
REOPEN = 47 * 3600 + 45 * 60      # cut (Fri 22:15) + 47 h 45 m = Sunday 22:00 UTC, before any target-week bar
SLACK = 6 * 3600
POOL = 104
GVZ_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv"
DEV_GVZ = ROOT / "data" / "external" / "GVZ_History.csv"
DIR = ROOT / "data" / "wpwb_weekly"
GVZ_DIR = DIR / "gvz"
ENS_DIR = DIR / "outlook_shadow_ens"
DUK_FROZEN = DIR / "outlook_rv_dukascopy_frozen.csv"
RV_ARCH = DIR / "outlook_rv_archive.csv"
G_ARCH = DIR / "outlook_g_archive.csv"
LOG = DIR / "outlook_shadow_log.csv"
DRY = DIR / "outlook_shadow_dryrun.csv"
SCORES = DIR / "outlook_shadow_scores.csv"
LATEST = DIR / "outlook_shadow_latest.md"
LOCK = DIR / ".outlook_shadow.lock"
MODELS = ("B0", "HAR", "MVOL")
LABELS_TH = ("สงบ", "ปกติ", "ผันผวนสูง", "ผันผวนรุนแรง")
# frozen input hashes (Amendment 1); a mismatch refuses the run
DUK_FROZEN_SHA = "9c1722e6a2e7506440dc878466b39457151c85e611a0c1999c302533160f471a"
DEV_GVZ_SHA = "670e620d4d780185737478593ee3d787076cefaf3de647b9abd175e98adbca13"

MODEL_FIELDS = []
for _m in MODELS:
    MODEL_FIELDS += [f"{_m}_status", f"{_m}_var", f"{_m}_rv_q10", f"{_m}_rv_q50", f"{_m}_rv_q90",
                     f"{_m}_p_calm", f"{_m}_p_normal", f"{_m}_p_high", f"{_m}_p_extreme", f"{_m}_p_high_or_extreme"]
FIELDS = ["cut_utc", "cut_epoch", "generated_utc", "generated_epoch", "hours_after_cut", "version", "run", "status",
          "feed_end_utc", "rv_hash", "g_hash", "m_k", "current_class", "pool_first_cut", "pool_last_cut",
          "gvz_status", "gvz_file", "gvz_retrieved_utc", "gvz_bytes", "gvz_sha256", "gvz_row_date", "gvz_value",
          "gvz_thu_prev_value", "gvz_thu_revised", "ens_file", "ens_sha256", "error"] + MODEL_FIELDS


def utc(ep):
    return datetime.fromtimestamp(int(ep), timezone.utc).strftime("%Y-%m-%d %H:%M")


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ------------------------------------------------------------------ CSV with a fixed schema
def read_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def append_row(path, row, fields):
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            head = fh.readline().strip().split(",")
        if head != list(fields):
            raise RuntimeError(f"{path.name}: header differs from the frozen schema; refusing to append")
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), restval="", extrasaction="raise")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})
        fh.flush(); os.fsync(fh.fileno())


# ------------------------------------------------------------------ frozen / archived inputs
def freeze_dukascopy():
    """One-time: weekly RV and bar counts of every Dukascopy week starting <= SPLICE."""
    if DUK_FROZEN.exists():
        print(f"{DUK_FROZEN.name} exists (sha256 {sha_file(DUK_FROZEN)}); not rewritten")
        return 0
    h, t, cuts, *_ = O.load()
    cuts = cuts[cuts <= SPLICE]
    rv_raw, _, _, nb = V.weekly_rv(t, *(h[k].to_numpy(float) for k in ("c", "h", "l")), cuts)
    rv = V.mask_invalid(rv_raw, nb)
    pd.DataFrame(dict(cut_epoch=cuts, cut_utc=[utc(c) for c in cuts], rv=rv, nbar=nb)).to_csv(DUK_FROZEN, index=False)
    print(f"wrote {DUK_FROZEN.name}: {len(cuts)} weeks, sha256 {sha_file(DUK_FROZEN)}; dev GVZ sha256 {sha_file(DEV_GVZ)}")
    return 0


def check_frozen():
    if DUK_FROZEN_SHA and sha_file(DUK_FROZEN) != DUK_FROZEN_SHA:
        raise RuntimeError("frozen Dukascopy RV file changed")
    if DEV_GVZ_SHA and sha_file(DEV_GVZ) != DEV_GVZ_SHA:
        raise RuntimeError("development GVZ file changed")


def archive_exness(now):
    """Append RV of every Exness week (start > SPLICE) that is complete by the wall clock
    and by the feed, and not yet archived. Archived rows are never changed."""
    import bars as BR
    m = BR.market(BR.load_bars(frozen=False))
    te = np.asarray(m.t, np.int64)
    end = int(te[-1]) + 3600
    have = set(read_csv(RV_ARCH).cut_epoch.astype(int)) if RV_ARCH.exists() else set()
    fields = ["cut_epoch", "cut_utc", "rv", "nbar", "first_bar_utc", "last_bar_utc", "max_gap_h", "status", "archived_utc"]
    k = SPLICE + WEEK
    while k + WEEK <= now:
        if k not in have and k + WEEK - SLACK <= end:
            rv_raw, _, _, nb = V.weekly_rv(te, np.asarray(m.c, float), np.asarray(m.h, float), np.asarray(m.l, float),
                                           np.array([k], np.int64))
            inw = te[((te + 3600) > k) & ((te + 3600) <= k + WEEK)]
            gap = float(np.diff(inw).max() / 3600) if len(inw) > 1 else np.nan
            ok = nb[0] >= V.MIN_BARS
            append_row(RV_ARCH, dict(cut_epoch=k, cut_utc=utc(k), rv=float(rv_raw[0]) if ok else "", nbar=int(nb[0]),
                                     first_bar_utc=utc(inw[0]) if len(inw) else "", last_bar_utc=utc(inw[-1]) if len(inw) else "",
                                     max_gap_h=gap, status="VALID" if ok else "INVALID",
                                     archived_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")), fields)
        k += WEEK
    return end


def rv_series(cut_target):
    """Weekly RV on FIRST_CUT..cut_target (last element = target, NaN): frozen Dukascopy
    file for starts <= SPLICE, the Exness archive after. A missing archive week is NaN."""
    cuts = np.arange(FIRST_CUT, cut_target + 1, WEEK, dtype=np.int64)
    rv = np.full(len(cuts), np.nan)
    idx = {int(c): i for i, c in enumerate(cuts)}
    for path in (DUK_FROZEN, RV_ARCH):
        if path.exists():
            for c, v in zip(read_csv(path).cut_epoch.astype(int), read_csv(path).rv):
                if c in idx and idx[c] < len(cuts) - 1 and pd.notna(v) and v != "":
                    rv[idx[c]] = float(v)
    return cuts, rv


def g_value(gd, gv, cut):
    j = np.searchsorted(gd, cut - 86400, side="right") - 1
    if j >= 0 and gd[j] > cut - 7 * 86400:
        return j, math.log((gv[j] / 100) ** 2 / 52 * 1e8)
    return None, np.nan


def g_series(cuts, gd_new=None, gv_new=None):
    """G at each cut: from the frozen development file for cuts <= SPLICE; for later cuts
    the value archived when first computed; a not-yet-archived cut is computed from the
    newest snapshot and archived now (so later revisions never rewrite past inputs)."""
    gd, gv = O.gvz_series()
    G = np.full(len(cuts), np.nan)
    arch = read_csv(G_ARCH)
    have = dict(zip(arch.cut_epoch.astype(int), arch.G)) if len(arch) else {}
    fields = ["cut_epoch", "cut_utc", "G", "gvz_row_date", "gvz_value", "source", "archived_utc"]
    for i, c in enumerate(cuts.astype(int)):
        if c <= SPLICE:
            G[i] = g_value(gd, gv, c)[1]
        elif c in have:
            G[i] = float(have[c]) if pd.notna(have[c]) else np.nan
        elif gd_new is not None:
            j, val = g_value(gd_new, gv_new, c)
            G[i] = val
            append_row(G_ARCH, dict(cut_epoch=c, cut_utc=utc(c), G=val if np.isfinite(val) else "",
                                    gvz_row_date=str(pd.to_datetime(gd_new[j], unit="s").date()) if j is not None else "",
                                    gvz_value=float(gv_new[j]) if j is not None else "", source="cboe download",
                                    archived_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")), fields)
    return G


# ------------------------------------------------------------------ GVZ download
def fetch_gvz(cut):
    GVZ_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(GVZ_URL, headers={"User-Agent": "Mozilla/5.0 (EA-tread weekly research log)"})
    err = ""
    for _ in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=60).read()
            break
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:80]
            time.sleep(30)
    else:
        return None, None, dict(gvz_status=f"FETCH_FAILED {err}")
    now = datetime.now(timezone.utc)
    f = GVZ_DIR / f"GVZ_{now:%Y%m%dT%H%M%SZ}.csv"
    f.write_bytes(raw)
    meta = dict(gvz_file=f.name, gvz_retrieved_utc=now.strftime("%Y-%m-%d %H:%M:%S"), gvz_bytes=len(raw),
                gvz_sha256=hashlib.sha256(raw).hexdigest())
    try:  # validate before use (R11-10)
        g = pd.read_csv(f)
        assert list(g.columns[:2]) == ["DATE", "GVZ"]
        g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
        g = g.dropna(subset=["GVZ"]).sort_values("d")
        assert len(g) >= 4000 and g.GVZ.between(5, 200).all()
        assert g.d.iloc[-1] >= pd.Timestamp(cut - 10 * 86400, unit="s")
    except Exception as e:  # noqa: BLE001
        meta["gvz_status"] = f"INVALID_DOWNLOAD {repr(e)[:60]}"
        return None, None, meta
    meta["gvz_status"] = "OK"
    return g.d.astype("datetime64[s]").astype(np.int64).to_numpy(), g.GVZ.astype(float).to_numpy(), meta


def thursday_revision(gd, gv, cut, this_file):
    """Value of the used Thursday row in every earlier snapshot; flag any difference."""
    j = np.searchsorted(gd, cut - 86400, side="right") - 1
    if j < 0:
        return "", ""
    day = pd.to_datetime(gd[j], unit="s")
    vals = []
    for f in sorted(GVZ_DIR.glob("GVZ_*.csv")):
        if f.name == this_file:
            continue
        try:
            g = pd.read_csv(f)
            g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
            v = g.loc[g.d == day, "GVZ"]
            if len(v):
                vals.append(float(v.iloc[0]))
        except Exception:  # noqa: BLE001
            pass
    if not vals:
        return "", "no earlier snapshot"
    return vals[-1], str(any(abs(v - gv[j]) > 1e-9 for v in vals))


# ------------------------------------------------------------------ models
def common_ensembles(rv, mu, K):
    """Residual pool = the last POOL weeks before K in which ALL models issued a point
    forecast and the target was valid (calendar parity, R11-8)."""
    lv = np.log(rv)
    ok = np.isfinite(lv[:K]) & np.all([np.isfinite(mu[m][:K]) for m in MODELS], axis=0)
    wk = np.flatnonzero(ok)[-POOL:]
    if len(wk) < POOL:
        return None, None
    return {m: mu[m][K] + (lv[wk] - mu[m][wk]) for m in MODELS if np.isfinite(mu[m][K])}, wk


def point_forecasts(cuts, rv, G):
    n = len(cuts)
    lv = np.log(rv)
    L1, L4, L26 = (np.full(n, np.nan) for _ in range(3))
    for k in range(26, n):
        w = lv[k - 26:k]
        if np.isfinite(w).all():
            L1[k], L4[k], L26[k] = w[-1], w[-4:].mean(), w.mean()
    har_X = np.c_[np.ones(n), L1, L4, L26]
    f = V.ewma_forecast(rv)
    mu = {"B0": np.where(f > 0, np.log(np.where(f > 0, f, 1)), np.nan)}
    mu["HAR"], _ = O.ols_prequential(har_X, lv)
    mu["MVOL"], _ = O.ols_prequential(np.c_[har_X, G], lv)
    return mu


def class_probs(e, mk):
    lm = math.log(mk)
    cdf = [float(np.mean(e < lm + math.log(q))) for q in O.EDGES]
    return [cdf[0], cdf[1] - cdf[0], cdf[2] - cdf[1], 1 - cdf[2]], cdf


# ------------------------------------------------------------------ one cut
def log_cut(now):
    import bars as BR
    C = BR.last_cut_before(now)
    prospective = now < C + REOPEN
    run = ("FORWARD" if prospective else "LATE") if C >= FORWARD else "DRY_RUN"
    target = DRY if run == "DRY_RUN" else LOG
    old = read_csv(target)
    if len(old) and (old.cut_epoch.astype(int) == C).any():
        print(f"cut {utc(C)} already logged in {target.name}; refusing to rewrite")
        return
    # cuts skipped since the last forward row are recorded as MISSED (never backfilled)
    if target == LOG and len(old):
        k = int(old.cut_epoch.max()) + WEEK
        while k < C:
            append_row(LOG, dict(cut_utc=utc(k), cut_epoch=k, version=VERSION, run="MISSED", status="MISSED",
                                 generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")), FIELDS)
            k += WEEK
    row = dict(cut_utc=utc(C), cut_epoch=C, generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
               generated_epoch=now, hours_after_cut=round((now - C) / 3600, 2), version=VERSION, run=run)
    try:
        check_frozen()
        end = archive_exness(now)
        row["feed_end_utc"] = utc(end)
        cuts, rv = rv_series(C)
        K = len(cuts) - 1
        row["rv_hash"] = hashlib.sha256(np.nan_to_num(rv[:K], nan=-1.0).tobytes()).hexdigest()[:16]
        gd, gv, gmeta = fetch_gvz(C)
        row.update(gmeta)
        if gd is not None:
            j = np.searchsorted(gd, C - 86400, side="right") - 1
            row["gvz_row_date"] = str(pd.to_datetime(gd[j], unit="s").date()) if j >= 0 else ""
            row["gvz_value"] = float(gv[j]) if j >= 0 else ""
            row["gvz_thu_prev_value"], row["gvz_thu_revised"] = thursday_revision(gd, gv, C, gmeta["gvz_file"])
        G = g_series(cuts, gd, gv)
        row["g_hash"] = hashlib.sha256(np.nan_to_num(G, nan=-1.0).tobytes()).hexdigest()[:16]
        mu = point_forecasts(cuts, rv, G)
        mk = O.med52(rv)
        row["m_k"] = float(mk[K])
        prev = rv[K - 1] / mk[K - 1] if np.isfinite(mk[K - 1]) and np.isfinite(rv[K - 1]) else np.nan
        row["current_class"] = int(O.cls(np.array([prev]))[0])
        ens, wk = common_ensembles(rv, mu, K)
        issued = []
        if ens is not None and np.isfinite(mk[K]):
            row["pool_first_cut"], row["pool_last_cut"] = utc(cuts[wk[0]]), utc(cuts[wk[-1]])
            for mdl in MODELS:
                if mdl not in ens:
                    row[f"{mdl}_status"] = "NOT_ISSUED"
                    continue
                e = ens[mdl]
                probs, _ = class_probs(e, mk[K])
                issued.append(mdl)
                row.update({f"{mdl}_status": "ISSUED", f"{mdl}_var": float(np.mean(np.exp(e))),
                            **{f"{mdl}_rv_q{q}": float(np.exp(np.quantile(e, q / 100))) for q in (10, 50, 90)},
                            **{f"{mdl}_p_{c}": p for c, p in zip(("calm", "normal", "high", "extreme"), probs)},
                            f"{mdl}_p_high_or_extreme": probs[2] + probs[3]})
            ENS_DIR.mkdir(parents=True, exist_ok=True)
            fin = ENS_DIR / f"{run}_{pd.Timestamp(C, unit='s'):%Y%m%dT%H%M}.npz"
            if fin.exists():   # orphan of a crashed run: keep it, write alongside
                fin = fin.with_name(fin.stem + f"_{now}.npz")
            tmp = fin.with_suffix(".tmp.npz")
            np.savez(tmp, **{m: ens[m] for m in issued})
            os.replace(tmp, fin)
            row["ens_file"], row["ens_sha256"] = fin.name, sha_file(fin)
        else:
            for mdl in MODELS:
                row[f"{mdl}_status"] = "NOT_ISSUED"
        row["status"] = "OK" if len(issued) == 3 else ("PARTIAL " + " ".join(issued) if issued else "NONE_ISSUED")
    except Exception as e:  # noqa: BLE001  a row is always written
        row["status"] = "ERROR"
        row["error"] = repr(e)[:200]
    append_row(target, row, FIELDS)
    print(f"logged {run} cut {row['cut_utc']}: {row['status']} -> {target.name}")


def write_latest():
    rows = [read_csv(p) for p in (LOG, DRY) if p.exists()]
    rows = [r for r in rows if len(r)]
    if not rows:
        return
    r = pd.concat(rows).sort_values("cut_epoch").iloc[-1].to_dict()
    cur = int(r["current_class"]) if pd.notna(r.get("current_class")) else -1
    lines = [f"# WPWB Outlook (shadow) — สัปดาห์เริ่ม {r['cut_utc']} UTC", "",
             "> **shadow — ห้ามใช้ตัดสินขนาดไม้หรือทิศทาง** ขนาดไม้ยังใช้ EWMA ตามรายงานความเสี่ยงเดิมเท่านั้น",
             "> ตัวเลขนี้เก็บไว้เพื่อพิสูจน์ในอนาคตว่าแม่นหรือไม่ (ต้องใช้หลายปี)", "",
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


# ------------------------------------------------------------------ scoring (full contract, R11-2)
def score_all():
    L = read_csv(LOG)
    if not len(L):
        print("no forward rows yet; nothing to score")
        return
    L = L[(L.run == "FORWARD") & (L.status == "OK")]
    arch = read_csv(RV_ARCH)
    real = dict(zip(arch.cut_epoch.astype(int), arch.rv)) if len(arch) else {}
    rows = []
    for _, r in L.iterrows():
        C = int(r.cut_epoch)
        y_rv = real.get(C)
        if y_rv is None or pd.isna(y_rv) or y_rv == "":
            continue
        f = ENS_DIR / str(r.ens_file)
        if not f.exists() or sha_file(f) != r.ens_sha256:
            rows.append(dict(cut_utc=r.cut_utc, pos=(C - FORWARD) // WEEK, note="ENSEMBLE MISSING OR HASH MISMATCH"))
            continue
        z = np.load(f)
        y_rv = float(y_rv); y = math.log(y_rv)
        rc = int(O.cls(np.array([y_rv / r.m_k]))[0])
        out = dict(cut_utc=r.cut_utc, pos=(C - FORWARD) // WEEK, rv=y_rv, realised_class=rc, current_class=r.current_class)
        for mdl in MODELS:
            e = z[mdl]
            F_ = float(np.mean(np.exp(e)))
            probs, cdf = class_probs(e, r.m_k)
            p_hi = probs[2] + probs[3]
            out.update({f"{mdl}_crps": O.crps(e, y), f"{mdl}_qlike": y_rv / F_ - math.log(y_rv / F_) - 1,
                        f"{mdl}_rps": sum((a - float(rc <= j)) ** 2 for j, a in enumerate(cdf)) / 3,
                        f"{mdl}_in80": float(np.quantile(e, .1) <= y <= np.quantile(e, .9)),
                        f"{mdl}_in95": float(np.quantile(e, .025) <= y <= np.quantile(e, .975))})
            if r.current_class in (0, 1):
                out[f"{mdl}_onset_brier"] = (p_hi - float(rc >= 2)) ** 2
            elif r.current_class in (2, 3):
                out[f"{mdl}_exit_brier"] = ((1 - p_hi) - float(rc < 2)) ** 2
        rows.append(out)
    S = pd.DataFrame(rows)
    S.to_csv(SCORES, index=False)
    print(f"scored {len(S)} forward weeks -> {SCORES.name} (descriptive; no gate)")
    if len(S) >= 26:
        for a, b in (("MVOL", "B0"), ("MVOL", "HAR")):
            for mt in ("crps", "qlike", "rps", "onset_brier", "exit_brier"):
                ca, cb = f"{a}_{mt}", f"{b}_{mt}"
                if ca not in S or cb not in S:
                    continue
                m = S[ca].notna() & S[cb].notna()
                if m.sum() < 20:
                    continue
                d = (S.loc[m, ca] - S.loc[m, cb]).to_numpy()
                lo, hi = O.block_ci(d, 8, S.loc[m, "pos"].to_numpy())
                print(f"  {a} - {b} {mt}: {d.mean():+.4f} [{lo:+.4f}, {hi:+.4f}] over {m.sum()} weeks")


def main() -> int:
    os.chdir(ROOT)
    if "--freeze-dukascopy" in sys.argv:
        return freeze_dukascopy()
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime > 2 * 3600:
            LOCK.unlink(); fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            print("another outlook_shadow run holds the lock; exiting")
            return 0
    try:
        if "--score" not in sys.argv:
            log_cut(int(time.time()))
        write_latest()
        score_all()
    finally:
        os.close(fd); LOCK.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
