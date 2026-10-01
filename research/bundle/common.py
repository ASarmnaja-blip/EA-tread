"""Shared engine of the big bundle (docs/BUNDLE_2026-10-01_PREREG.md): bars, costs, swaps, an uncapped trade simulator in which every signal
is its own trade (overlaps allowed) with its full path autopsy, one-position flags, and an event-driven equity simulation that allows
stacked positions. Nothing here caps a profit, a loss or a holding time."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "bundle"; OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(ROOT / "research" / "candlelab"), str(ROOT / "research" / "wrwr")]
import lab as L  # noqa: E402
import contracts as K  # noqa: E402

TFS = ("M5", "M15", "H1", "H4", "D1", "W1")
METALS = ("XAUUSD", "XAGUSD")
ORIG8 = ("EURUSD", "USDJPY", "AUDUSD", "USDCHF", "US500", "USTEC", "USOIL", "BTCUSD")
NEW8 = ("DE30", "JP225", "XCUUSD", "XPTUSD", "USDCNH", "USDINR", "USDMXN", "USDZAR")
SYSTEMS = {"S1": (20, ("chan", 10)), "S2": (55, ("chan", 20)), "CH": (55, ("chand", 3.0))}
GOLD_DEV, GOLD_CHECK = ("2009-01-01", "2016-01-01"), ("2016-01-01", "2026-10-01")
SPECS = json.loads((OUT / "broker_specs.json").read_text()) if (OUT / "broker_specs.json").exists() else {}


def ts(s):
    return int(pd.Timestamp(s).timestamp())


# ------------------------------------------------------------------ bars
def metal_bars(sym, tf):
    """Candle Lab bars of a metal, cached in data/bundle/bars_<sym>_<tf>.npz (all timeframes are built on the first call)."""
    f = OUT / f"bars_{sym}_{tf}.npz"
    if not f.exists():
        base = L.base_gold() if sym == "XAUUSD" else L.base_silver()
        cuts = L.cut_grid(base["t"][-1])
        for t_ in TFS + ("M30",):
            B = L.resample(base, t_, cuts)
            np.savez(OUT / f"bars_{sym}_{t_}.npz", t=B.t, o=B.o, h=B.h, l=B.l, c=B.c, v=B.v, n=B.n, hi_pos=B.hi_pos, lo_pos=B.lo_pos, atr=B.atr)
        del base
    z = np.load(f)
    return L.Bars(tf=tf, **{k: z[k] for k in z.files})


def _agg(B, key, tf):
    g = pd.DataFrame(dict(k=key, t=B.t, o=B.o, h=B.h, l=B.l, c=B.c, v=B.v)).groupby("k", sort=True).agg(
        t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
    X = L.Bars(tf=tf, t=g.t.to_numpy(np.int64), o=g.o.to_numpy(), h=g.h.to_numpy(), l=g.l.to_numpy(), c=g.c.to_numpy(), v=g.v.to_numpy(),
               n=np.full(len(g), 12), hi_pos=np.full(len(g), np.nan), lo_pos=np.full(len(g), np.nan))
    X.atr = L.atr(X.h, X.l, X.c, 14)
    return X


def mt5_bars(sym, tf):
    """MT5 bars: D1 / H1 from data/mt5 (cache), M30 / M15 / M5 from data/bundle/mt5 (read-only fetch), H4 aggregated from H1 at the 22:00
    UTC anchor, W1 aggregated from D1 by the cut grid."""
    if tf == "H4":
        H = mt5_bars(sym, "H1"); return _agg(H, (H.t - L.ANCHOR) // 14400, "H4")
    if tf == "W1":
        D = mt5_bars(sym, "D1"); return _agg(D, np.searchsorted(L.cut_grid(int(D.t[-1])), D.t, side="right") - 1, "W1")
    f = ROOT / "data" / ("mt5" if tf in ("H1", "D1") else "bundle/mt5") / f"{sym}_{tf}.npz"
    z = np.load(f)
    t, o, h, l, c = z["t"].astype(np.int64), z["o"].astype(float), z["h"].astype(float), z["l"].astype(float), z["c"].astype(float)
    B = L.Bars(tf=tf, t=t, o=o, h=h, l=l, c=c, v=z["tick_volume"].astype(float), n=np.full(len(t), 12), hi_pos=np.full(len(t), np.nan),
               lo_pos=np.full(len(t), np.nan))
    B.atr = L.atr(h, l, c, 14)
    return B


def bars(sym, tf):
    return metal_bars(sym, tf) if sym in METALS else mt5_bars(sym, tf)


# ------------------------------------------------------------------ costs (round trip, bp) and swaps (bp, positive = paid)
def cost_rt_bp(sym):
    if sym == "XAUUSD":
        return 2.5
    if sym == "XAGUSD":
        return float(K.xag_pre2023_constant())
    return float(SPECS[sym]["cost_rt_bp"])


def nights(t0, t1, triple):
    """Rollovers at 22:00 UTC in (t0, t1]: Monday-Friday count 1, the triple day 3, weekends 0."""
    d0 = ((np.asarray(t0, np.int64) - 22 * 3600) // 86400 + 1).astype("datetime64[D]")
    d1 = ((np.asarray(t1, np.int64) - 22 * 3600) // 86400 + 1).astype("datetime64[D]")
    d1 = np.maximum(d1, d0)
    wk = np.busday_count(d0, d1)
    mask = ["0"] * 7; mask[(triple - 1) % 7] = "1"
    tr = np.busday_count(d0, d1, weekmask="".join(mask))
    return wk + 2 * tr


def swap_bp(sym, t_entry_open, t_exit, d):
    d = np.asarray(d, float)
    if sym in METALS:
        return K.swap_bp(sym, t_entry_open, t_exit, d)
    s = SPECS[sym]
    n = nights(t_entry_open, t_exit, s["rollover3"])
    return n * np.where(d > 0, s["swap_long_bp"], s["swap_short_bp"])


# ------------------------------------------------------------------ simulator
def chan_levels(B, n):
    lo = pd.Series(B.l).rolling(n).min().shift(1).to_numpy(); hi = pd.Series(B.h).rolling(n).max().shift(1).to_numpy()
    return lo, hi


def _next_true(mask):
    idx = np.where(mask, np.arange(len(mask)), len(mask) + 10 ** 9)
    return np.minimum.accumulate(idx[::-1])[::-1]


def simulate(B, s, d, stop_dist, exit_spec, sym):
    """Every (signal bar s, direction d) is its own trade: entry at the open of s+1, initial stop d*stop_dist away, exit by exit_spec:
    ("chan", n): a close beyond the opposite n-bar channel; ("chand", m[, A]): a close beyond best-since-entry -/+ m x A (A defaults to
    ATR22). Stop first inside a bar (gaps fill at the open); close exits fill at the next open; trades open at the data end close at the
    last close (flag open_end). Returns one row per trade with the path autopsy."""
    n = len(B.c); o, h, l, c = B.o, B.h, B.l, B.c
    s = np.asarray(s, np.int64); d = np.asarray(d, np.int64); sd = np.asarray(stop_dist, float)
    ok = (s + 1 < n) & np.isfinite(sd) & (sd > 0)
    s, d, sd = s[ok], d[ok], sd[ok]
    kind = exit_spec[0]
    if kind == "chan":
        lo, hi = chan_levels(B, exit_spec[1])
        with np.errstate(invalid="ignore"):
            nxt_l = _next_true(c < lo); nxt_s = _next_true(c > hi)
    else:
        m = exit_spec[1]; A = exit_spec[2] if len(exit_spec) > 2 else L.atr(h, l, c, 22)
    rows = np.full((len(s), 10), np.nan)
    for i in range(len(s)):
        e = s[i] + 1; di = d[i]; ep = o[e]; R = sd[i]; stop = ep - di * R
        x = None; stopped = False
        if kind == "chan":
            jc = (nxt_l if di > 0 else nxt_s)[e]
            jend = min(jc, n - 1)
            seg_hit = (l[e:jend + 1] <= stop) if di > 0 else (h[e:jend + 1] >= stop)
            if seg_hit.any():
                x = e + int(np.argmax(seg_hit)); stopped = True
            else:
                x = min(jc, n - 1)
        else:
            j0 = e; best = ep; W = 64
            while x is None:
                j1 = min(n, j0 + W)
                hh = h[j0:j1] if di > 0 else l[j0:j1]
                bst = np.maximum.accumulate(np.r_[best, hh])[1:] if di > 0 else np.minimum.accumulate(np.r_[best, hh])[1:]
                st = (l[j0:j1] <= stop) if di > 0 else (h[j0:j1] >= stop)
                with np.errstate(invalid="ignore"):
                    ce = (c[j0:j1] < bst - m * A[j0:j1]) if di > 0 else (c[j0:j1] > bst + m * A[j0:j1])
                ks = int(np.argmax(st)) if st.any() else 10 ** 9
                kc = int(np.argmax(ce)) if ce.any() else 10 ** 9
                if ks <= kc and ks < 10 ** 9:
                    x = j0 + ks; stopped = True
                elif kc < 10 ** 9:
                    x = j0 + kc
                elif j1 >= n:
                    x = n - 1
                else:
                    best = bst[-1]; j0 = j1; W *= 4
        if stopped:
            px = stop if (x == e or (o[x] - stop) * di > 0) else o[x]
            fill_bar = x
        elif x < n - 1:
            px = o[x + 1]; fill_bar = x + 1
        else:
            px = c[n - 1]; fill_bar = n - 1
        seg_h = h[e:x + 1]; seg_l = l[e:x + 1]
        fav = (seg_h - ep) if di > 0 else (ep - seg_l)
        adv = (ep - seg_l) if di > 0 else (seg_h - ep)
        if stopped:
            adv = np.minimum(adv, R)
        kb = int(np.argmax(fav))
        up1 = np.flatnonzero(fav >= R); dn1 = np.flatnonzero(adv >= R)
        rows[i] = [e, fill_bar, ep, px, fav.max() / R, adv.max() / R, kb, adv[:kb + 1].max() / R,
                   float((up1[0] if len(up1) else 10 ** 9) < (dn1[0] if len(dn1) else 10 ** 9)), float(stopped)]
    T = pd.DataFrame(rows, columns=["e", "xf", "ep", "px", "mfe_R", "mae_R", "bars_to_best", "mae_before_best_R", "plus1_first", "stopped"])
    T.insert(0, "s", s); T.insert(1, "d", d); T["risk"] = sd
    T["e"] = T.e.astype(np.int64); T["xf"] = T.xf.astype(np.int64)
    T["t"] = B.t[T.e.to_numpy()]; T["t_exit"] = B.t[T.xf.to_numpy()]
    T["open_end"] = (T.xf.to_numpy() >= n - 1) & (T.stopped.to_numpy() == 0)
    T["bars"] = T.xf - T.e
    risk_bp = T.risk / T.ep * 1e4
    T["gR"] = T.d * (T.px - T.ep) / T.risk
    sw = swap_bp(sym, T.t.to_numpy(), T.t_exit.to_numpy(), T.d.to_numpy()) if len(T) else np.zeros(0)
    T["cost_bp"] = cost_rt_bp(sym); T["swap_bp"] = sw
    T["R"] = T.gR - (T.cost_bp + T.swap_bp) / risk_bp
    return T


def trend_signals(B, entry_n, side):
    hi = pd.Series(B.h).rolling(entry_n).max().shift(1).to_numpy(); lo = pd.Series(B.l).rolling(entry_n).min().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        m = (B.c > hi) if side > 0 else (B.c < lo)
    return np.flatnonzero(m)


def trend_trades(B, sym, system, side, s=None, d=None):
    """Trades of a trend system. Default: every entry signal of `side`. With s (signal bars) and d (directions) given: those trades with
    the system's exit (used for fades: a long signal traded short with the mirrored exit)."""
    entry_n, ex = SYSTEMS[system]
    if s is None:
        s = trend_signals(B, entry_n, side); d = np.full(len(s), side)
    N = L.atr(B.h, B.l, B.c, 20)
    T = simulate(B, s, d, 2 * N[np.asarray(s, np.int64)], ex, sym)
    T["system"] = system
    return T


def one_position(T):
    """TAKEN flag: in entry order, a trade is taken when its signal bar comes at or after the exit bar of the last taken trade."""
    take = np.zeros(len(T), bool); busy = -1
    s = T.s.to_numpy(); xf = T.xf.to_numpy()
    for i in np.argsort(s, kind="stable"):
        if s[i] >= busy:
            take[i] = True; busy = xf[i]
    return take


# ------------------------------------------------------------------ equity with stacked positions
def equity(T, risk, a=None, b=None, mode="all", close=None):
    """Event-driven equity on $10,000: every row of T is a position sized at risk x realised equity at its entry; P&L booked at exit.
    mode "all" takes every row; "winners" takes a row only if every open same-direction position is in profit at the signal close
    (needs close = the bar closes). Returns CAGR, max drawdown of realised equity, max concurrent positions, n, positive years."""
    import heapq
    x = T if a is None else T[(T.t >= ts(a)) & (T.t < ts(b))]
    x = x.sort_values(["t", "s"], kind="stable")
    if not len(x):
        return dict(n=0)
    te, tx, R, d, ep, s = x.t.to_numpy(), x.t_exit.to_numpy(), x.R.to_numpy(), x.d.to_numpy(), x.ep.to_numpy(), x.s.to_numpy()
    eq = 10_000.0; peak = eq; dd = 0.0; heap = []; live = {}
    maxc = 0; n = 0; yearly = {}

    def book(p):
        nonlocal eq, peak, dd
        eq += p[1] * p[2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak); yearly[pd.Timestamp(int(p[0]), unit="s").year] = eq

    for i in range(len(x)):
        while heap and heap[0][0] <= te[i]:
            _, k = heapq.heappop(heap); book(live.pop(k))
        if eq <= 0:
            break
        if mode == "winners" and live:
            px = close[s[i]]
            if any(p[3] == d[i] and (px - p[4]) * p[3] <= 0 for p in live.values()):
                continue
        live[i] = (tx[i], risk * eq, R[i], d[i], ep[i]); heapq.heappush(heap, (tx[i], i)); n += 1
        maxc = max(maxc, len(live))
    while heap:
        _, k = heapq.heappop(heap); book(live.pop(k))
    t0 = ts(a) if a else int(te[0]); t1 = ts(b) if b else int(max(tx.max(), te.max()))
    yrs = max((t1 - t0) / (365.25 * 86400), 0.1)
    prev = 10_000.0; pos = 0; ny = 0
    for y in sorted(yearly):
        pos += yearly[y] > prev; ny += 1; prev = yearly[y]
    return dict(n=n, end=eq, cagr=(max(eq, 0) / 10_000) ** (1 / yrs) - 1, dd=dd, max_open=maxc, pos_years=f"{pos}/{ny}")


def save(obj, name):
    with open(OUT / name, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(name):
    with open(OUT / name, "rb") as f:
        return pickle.load(f)
