#!/usr/bin/env python3
"""Every horizon and exit resolution that free data allows, on COMEX gold.

WHY IT LOOKS LIKE THIS
  The question was "test everything you can on three months". Three months of
  MINUTE data is not obtainable free - Yahoo serves 1m eight days per request
  and stops at four weeks - so this runs the horizons that do exist and puts
  the minimum detectable effect beside every one of them.

  MDE is the expectancy a given trade count could actually resolve at 5%
  significance and 80% power. A result smaller than its own MDE is consistent
  with no edge whatever its sign. That column is the point of the table: it
  turns "we could not find anything" into "this sample could not have found
  anything, so stop reading the numbers".

  Available:  1m  ~27 days   the only honest exit resolution
              5m  ~71 days
              1h  ~875 days  but exits resolve on the signal bar, which is
                             worth roughly +0.5R of fiction - see
                             docs/RESEARCH_FINDINGS.md

  Needs gc_1m.csv, gc_5m.json and gc_1h.json in the working directory; the
  fetch code is in yahoo_gc_crosscheck.py.
"""
import json, math
import numpy as np, pandas as pd
from statistics import NormalDist

OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
SPREAD_ATR = 0.02          # cost as a fraction of ATR, comparable across horizons
Z = NormalDist().inv_cdf(.975) + NormalDist().inv_cdf(.80)


def from_json(f):
    d = json.load(open(f))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    x = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                     index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()
    return x[x.volume > 0]


def analyse(fine, sig_tf, hold_hours, label):
    """fine: the bars exits resolve on. sig_tf: the timeframe signals fire on."""
    sig = fine.resample(sig_tf).agg(OHLCV).dropna()
    if len(sig) < 400:
        return None
    c = sig.close.to_numpy(float); h = sig.high.to_numpy(float)
    l = sig.low.to_numpy(float);   v = sig.volume.to_numpy(float); N = len(sig)
    fi = fine.index.values; fh = fine.high.to_numpy(float)
    fl = fine.low.to_numpy(float); fc = fine.close.to_numpy(float); NF = len(fi)
    fine_min = max(1, int((fine.index[1] - fine.index[0]).total_seconds() // 60))
    tf_min = int(pd.Timedelta(sig_tf).total_seconds() // 60)
    hold_bars = int(hold_hours * 60 / fine_min)
    J0 = np.searchsorted(fi, (sig.index + pd.Timedelta(sig_tf)).values, side="left")

    pc = pd.Series(c).shift(1)
    tr = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                    (pd.Series(l) - pc).abs()], axis=1).max(axis=1)
    A = tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    fa = pd.Series(c).ewm(span=9, adjust=False).mean().to_numpy()
    sw = pd.Series(c).ewm(span=21, adjust=False).mean().to_numpy()

    def piv(s, low):
        s = pd.Series(s)
        ok = ((s < s.rolling(5).min().shift(1)) & (s < s.rolling(5).min().shift(-5))) if low \
            else ((s > s.rolling(5).max().shift(1)) & (s > s.rolling(5).max().shift(-5)))
        return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(5).ffill().to_numpy()

    plo, phi = piv(l, True), piv(h, False)
    LB, BINS = max(20, int(24 * 60 / tf_min)), 48

    def value_area(i):
        a = max(0, i - LB)
        if i - a < 20: return np.nan, np.nan
        lo, hi = l[a:i].min(), h[a:i].max()
        if hi <= lo: return np.nan, np.nan
        bs = (hi - lo) / BINS
        il = np.floor((l[a:i] - lo) / bs).astype(int).clip(0, BINS - 1)
        ih = np.floor((h[a:i] - lo) / bs).astype(int).clip(0, BINS - 1)
        s2 = (ih - il + 1).astype(float)
        w = np.divide(v[a:i], s2, out=np.zeros(i - a), where=s2 > 0)
        d = np.zeros(BINS + 1); np.add.at(d, il, w); np.add.at(d, ih + 1, -w)
        p = np.cumsum(d)[:BINS]; t = p.sum()
        if t <= 0: return np.nan, np.nan
        k = int(p.argmax()); a_ = b_ = k; acc = p[k]
        while acc < .70 * t and (a_ > 0 or b_ < BINS - 1):
            dn = p[a_ - 1] if a_ > 0 else -1
            up = p[b_ + 1] if b_ < BINS - 1 else -1
            if up >= dn: b_ += 1; acc += up
            else:        a_ -= 1; acc += dn
        return lo + (a_ + .5) * bs, lo + (b_ + .5) * bs

    def sim(i, d, e, risk, sp):
        stop, be = e - d * risk, e + d * sp
        tg = [e + d * risk * m for m in (1, 2, 3)]
        al, t1, r, k = [True] * 3, False, 0., J0[i]
        if k >= NF: return None
        end = min(k + hold_bars, NF)
        while k < end:
            cur = be if t1 else stop
            if (d > 0 and fl[k] <= cur) or (d < 0 and fh[k] >= cur):
                for x in range(3):
                    if al[x]: r += ((cur - e) * d - sp) / risk; al[x] = False
                break
            for x in range(3):
                if al[x] and ((d > 0 and fh[k] >= tg[x]) or (d < 0 and fl[k] <= tg[x])):
                    r += ((tg[x] - e) * d - sp) / risk; al[x] = False
                    if x == 0: t1 = True
            if not any(al): break
            k += 1
        kx = min(k, end - 1, NF - 1)
        if any(al):
            for x in range(3):
                if al[x]: r += ((fc[kx] - e) * d - sp) / risk
        return r, max(1, kx - J0[i] + 1)

    bu = np.concatenate([[False], (fa[1:] > sw[1:]) & (fa[:-1] <= sw[:-1])])
    bd = np.concatenate([[False], (fa[1:] < sw[1:]) & (fa[:-1] >= sw[:-1])])
    rows = []
    for i in range(LB + 30, N - 1):
        d = 1 if bu[i] else (-1 if bd[i] else 0)
        if d == 0 or not np.isfinite(A[i]) or A[i] <= 0: continue
        e = c[i]; raw = plo[i] if d > 0 else phi[i]
        if not np.isfinite(raw): continue
        risk = abs(e - raw)
        if risk <= 0: continue
        s = sim(i, d, e, risk, SPREAD_ATR * A[i])
        if s is None: break
        val, vah = value_area(i)
        vp = bool(np.isfinite(val) and vah > val and ((e > vah) if d > 0 else (e < val)))
        rows.append((i, s[0], int(np.ceil(s[1] * fine_min / tf_min)), vp))
    S = pd.DataFrame(rows, columns=["bar", "r", "dur", "vp"])
    days = NF * fine_min / (23 * 60)
    out = []
    for nm, mask in (("baseline", np.ones(len(S), bool)), ("+volume", S.vp.to_numpy())):
        sub = S[mask].reset_index(drop=True)
        take, busy = [], -1
        for b, du in zip(sub.bar, sub.dur):
            if b > busy: take.append(True); busy = b + du
            else:        take.append(False)
        D = sub[np.array(take)]
        n = len(D)
        if n < 3:
            out.append((nm, n, 0, float("nan"), float("nan"), 0)); continue
        e_, sd = D.r.mean(), D.r.std(ddof=1)
        out.append((nm, n, n / days, e_, e_ / (sd / math.sqrt(n)), Z * sd / math.sqrt(n)))
    return label, days, out


def main():
    m1 = pd.read_csv("gc_1m.csv", index_col=0, parse_dates=True)
    m5, h1 = from_json("gc_5m.json"), from_json("gc_1h.json")
    print(f"{'test':<34}{'days':>6}{'part':<10}{'n':>5}{'n/day':>7}"
          f"{'E':>9}{'t':>7}{'MDE':>8}  verdict")
    for fine, tf, hold, lab in (
            (m1, "5min", 10, "1m data, M5 signals, 1m exits"),
            (m1, "15min", 10, "1m data, M15 signals, 1m exits"),
            (m5, "15min", 10, "5m data, M15 signals, 5m exits"),
            (m5, "30min", 20, "5m data, M30 signals, 5m exits"),
            (h1, "1h", 30, "1h data, H1 signals, 1h exits")):
        res = analyse(fine, tf, hold, lab)
        if res is None:
            print(f"{lab:<34} not enough bars"); continue
        label, days, out = res
        first = True
        for nm, n, npd, e_, t, mde in out:
            head = label if first else ""
            dd = f"{days:.0f}" if first else ""
            if n < 3:
                print(f"{head:<34}{dd:>6}{nm:<10}{n:>5}  too few"); first = False; continue
            v = "inside noise" if abs(e_) < mde else ("POSITIVE" if e_ > 0 else "negative")
            print(f"{head:<34}{dd:>6}{nm:<10}{n:>5}{npd:>7.2f}{e_:>+9.4f}"
                  f"{t:>+7.2f}{mde:>8.3f}  {v}")
            first = False


if __name__ == "__main__":
    main()
