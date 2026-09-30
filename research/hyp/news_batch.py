"""News batch (docs/HYPOTHESIS_BATCH_NEWS_PREREG.md): GPR spike / regime, EPU-TPU spike, Trump keyword posts, weekend risk read-outs.
NOTHING here downloads anything unless `fetch` is called, and `fetch` is run only after the operator explicitly allows the downloads.
Usage:
  python research/hyp/news_batch.py fetch     (operator permission required; writes data/news/ + data/news/manifest.json with sha256)
  python research/hyp/news_batch.py run       (N2, N3, N4, N6 primaries + N1 / N5 read-outs; stats as batches 1-3)"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import batch2 as B2  # noqa: E402
import batch3 as B3  # noqa: E402

ROOT = B1.ROOT
NEWS = ROOT / "data" / "news"
SOURCES = {   # name: url (public, first-party or the maintained public archive named in the pre-registration)
    "gpr_daily.xls": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
    "epu_daily.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=USEPUINDXD",
    "tpu_daily.xlsx": "https://www.policyuncertainty.com/media/Trade_Uncertainty_Daily.xlsx",
    "truth_archive.csv": "https://ix.cnn.io/data/truth-social/truth_archive.csv",
}
KEYWORDS = ("tariff", "china", "fed", "powell", "war", "iran", "russia", "israel")


def fetch():
    NEWS.mkdir(parents=True, exist_ok=True)
    man = {}
    for name, url in SOURCES.items():
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; EA-tread)"})
        data = urllib.request.urlopen(req, timeout=120).read()
        (NEWS / name).write_bytes(data)
        man[name] = dict(url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), fetched=pd.Timestamp.now(tz="UTC").isoformat())
        print(f"{name}: {len(data):,} bytes ({time.time() - t0:.0f}s)")
    (NEWS / "manifest.json").write_text(json.dumps(man, indent=1))


def daily_index(name):
    """-> DataFrame(date, value) for gpr / epu / tpu; the value of date d is usable from 24:00 UTC of d."""
    if name == "gpr":
        x = pd.read_excel(NEWS / "gpr_daily.xls")
        dcol = [c for c in x.columns if str(c).lower() in ("date", "day")][0]
        return pd.DataFrame(dict(date=pd.to_datetime(x[dcol]), value=pd.to_numeric(x["GPRD"], errors="coerce"))).dropna()
    if name == "epu":
        x = pd.read_csv(NEWS / "epu_daily.csv")
        return pd.DataFrame(dict(date=pd.to_datetime(x.iloc[:, 0]), value=pd.to_numeric(x.iloc[:, 1], errors="coerce"))).dropna()
    x = pd.read_excel(NEWS / "tpu_daily.xlsx")
    dcol = [c for c in x.columns if "date" in str(c).lower() or "day" in str(c).lower()][0]
    vcol = [c for c in x.columns if c != dcol][-1]
    return pd.DataFrame(dict(date=pd.to_datetime(x[dcol]), value=pd.to_numeric(x[vcol], errors="coerce"))).dropna()


def spike_signal(name, q, n=750, minn=250):
    X = daily_index(name).sort_values("date").reset_index(drop=True)
    thr = B2.causal_q(X.value.to_numpy(), q, n=n, minn=minn)
    m = np.isfinite(thr) & (X.value.to_numpy() >= thr)
    end = X.date.values.astype("datetime64[s]").astype(np.int64)[m] + 86400
    return end


def rule_N3(M):
    """21-bar blocks: long when the 30-day mean GPRD is above its trailing 250-day median at the block start (value known by then)."""
    D = M["D1"]; X = daily_index("gpr").sort_values("date").reset_index(drop=True)
    end = X.date.values.astype("datetime64[s]").astype(np.int64) + 86400
    m30 = X.value.rolling(30, min_periods=30).mean(); med = m30.rolling(250, min_periods=250).median()
    e_list = []
    for e in range(0, len(D.t) - 22, 21):
        j = int(np.searchsorted(end, D.t[e], side="right")) - 1
        if j >= 0 and np.isfinite(med.iloc[j]) and m30.iloc[j] > med.iloc[j]:
            e_list.append(e)
    e = np.array(e_list, int)
    return D, dict(e=e, d=np.ones(len(e)), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 20)


def trump_posts():
    x = pd.read_csv(NEWS / "truth_archive.csv")
    tcol = [c for c in x.columns if "created" in c.lower() or c.lower() in ("date", "timestamp")][0]
    ccol = [c for c in x.columns if c.lower() in ("content", "text", "body")][0]
    t = pd.to_datetime(x[tcol], utc=True, errors="coerce").dt.tz_convert(None)
    txt = x[ccol].astype(str).str.lower()
    hit = txt.apply(lambda s: any(k in s for k in KEYWORDS))
    return pd.DataFrame(dict(t=t.values.astype("datetime64[s]").astype(np.int64), hit=hit.values)).dropna()


def rule_N6(M, sign, posts):
    H = M["H1"]; p = posts[posts.hit]
    e = np.searchsorted(H.t, p.t.to_numpy() + 1, side="left")
    ok = (e < len(H.t) - 13) & ((H.t[np.minimum(e, len(H.t) - 1)] - p.t.to_numpy()) <= 3 * 3600)     # market open within 3 h of the post
    e = np.unique(e[ok])
    return H, dict(e=e, d=float(sign) * np.ones(len(e)), stop=1.5 * H.atr[e], tgt=np.full(len(e), np.nan), last=e + 11)


def run():
    import batch5 as B5
    Gd = B5.light_gold(); Sv = B5.light_silver()
    res = {}
    e2 = spike_signal("gpr", 0.99)
    res["N2"] = B3.evaluate(Gd, Sv, lambda M: B2.daily_rule(M, e2, -np.ones(len(e2)), 20, 3), 20, 3)
    res["N3"] = B3.evaluate(Gd, Sv, rule_N3, 21, 3)
    e4 = np.unique(np.r_[spike_signal("epu", 0.975), spike_signal("tpu", 0.975)])
    res["N4"] = B3.evaluate(Gd, Sv, lambda M: B2.daily_rule(M, e4, np.ones(len(e4)), 5, 2), 5, 2)
    posts = trump_posts()
    dev_end, chk_start = int(pd.Timestamp("2021-01-09").timestamp()), int(pd.Timestamp("2025-01-20").timestamp())
    print(f"Trump archive: {len(posts):,} posts, {int(posts.hit.sum()):,} with keywords, {pd.to_datetime(posts.t.min(), unit='s')} .. {pd.to_datetime(posts.t.max(), unit='s')}")
    print("NOTE: the Truth Social archive starts in 2022; the DEV period (first presidency, Twitter 2017-2021) needs the Twitter archive,")
    print("      which the pre-registration names but which has no stable first-party CSV: N6 is reported descriptively until it is added.")
    (B1.OUT / "news_batch.json").write_text(json.dumps(res, indent=1, default=float))
    for h, r in res.items():
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            print(f"{h} {p:<6s} n {x['n']:4d} mean R {x['mean_R']:+.3f} p {x['p']:.3f} control {x['control_R']:+.3f} excess {x['excess']:+.3f}")


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch()
    else:
        run()
