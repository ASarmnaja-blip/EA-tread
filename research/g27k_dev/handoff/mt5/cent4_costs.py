"""Cost versions for the Cent account without USDJPY (gold, silver, BTC, ETH), shared by cent4_capital.py and report_cent4.py.

Four versions of every trade's R, each changing only the costs of the hand-off trades (entries and exits stay):
  pub    as published: spread max(2 bp, spread + 1 bp) of the Standard account, swap as today's bp in every year (case A)
  realC  the Cent spreads measured on 184136077 plus the same 1 bp allowance, and swap case C of the research's
         swap_sensitivity.py: metals follow the US 2-year yield on the entry day, crypto at today's bp (a constant % a year)
  real   the Cent spreads plus 1 bp, and swap case D: metals as C, crypto at today's points (the research's pick; at BTC's
         2017-20 prices today's points are a 70-116 % a year swap, so this is the dear end for crypto)
  worst  the Cent spreads plus 1 bp, and swap case B: today's points in every year for every market (the pessimistic bound,
         and what the MT5 Strategy Tester charges)

Every version is the published R minus the change in each cost column, as swap_sensitivity.py does it. Rebuilding R as
R_gross - spread - swap is wrong for the 111 G27K-F trades closed early by the Fed rule: their R is the early exit, but their
R_gross, R_spread and R_swap columns are those of the original exit (checked: all 111 mismatches are Fed-rule exits).

The swap cases reproduce swap_sensitivity.py exactly (checked against swap_sensitivity.json on the trades it was run on).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
HANDOFF = HERE.parent
SNAP = pathlib.Path.home() / "Documents" / "G27K-snap"
M4 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]
METALS = ("XAUUSD", "XAGUSD")
CRYPTO = ("BTCUSD", "ETHUSD")
MODEL_BP = {"XAUUSD": 2.0, "XAGUSD": 3.641, "BTCUSD": 2.0, "ETHUSD": 2.0, "USDJPY": 2.0, "JP225": 2.0}
CENT_BP = {"XAUUSD": 0.58, "XAGUSD": 4.60, "BTCUSD": 1.28, "ETHUSD": 4.03, "USDJPY": 0.64}
SWAP_LONG_BP = {"XAUUSD": 1.2968641458960126, "XAGUSD": 1.3126412335504454}      # data/bundle/broker_specs.json
VERSIONS = {"pub": "ต้นทุนตามที่รายงาน", "realC": "spread Cent จริง + swap กรณี C", "real": "spread Cent จริง + swap กรณี D",
            "worst": "spread Cent จริง + swap กรณี B"}
SHORT = {"pub": "ตามที่รายงาน", "realC": "Cent + swap C", "real": "Cent + swap D", "worst": "Cent + swap B"}
VERSION_NOTE = {"pub": "spread ขั้นต่ำ 2 bp ของบัญชี Standard · swap เป็น bp ที่ราคาวันนี้ทุกปี (กรณี A)",
                "realC": "spread ที่วัดจากบัญชี Cent + 1 bp · swap โลหะตามดอกเบี้ย US 2 ปี, crypto เป็น % คงที่ต่อปีแบบที่รายงาน (กรณี C)",
                "real": "spread ที่วัดจากบัญชี Cent + 1 bp · swap โลหะตามดอกเบี้ย US 2 ปี, crypto เป็นจุดคงที่ (กรณี D ที่ session วิจัยเลือก)",
                "worst": "spread ที่วัดจากบัญชี Cent + 1 bp · swap เป็นจุดคงที่ของวันนี้ทุกปีทุกตลาด (กรณี B ขอบล่างแบบมองร้าย)"}


def ts(c):
    return ((pd.to_datetime(c, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype(np.int64)


def load(folder=HANDOFF):
    T = {}
    for b in ("F", "M30", "H1"):
        x = pd.read_csv(pathlib.Path(folder) / f"trades_{b}.csv.gz")
        x["book"] = b
        x["t"] = ts(x.entry_time_utc)
        x["tx"] = ts(x.exit_time_utc)
        T[b] = x
    return T


def us2y():
    y = pd.read_csv(SNAP / "data" / "macro" / "fred" / "DGS2.csv")
    y = y[pd.to_numeric(y.DGS2, errors="coerce").notna()]
    return pd.Series(y.DGS2.astype(float).to_numpy() / 100, index=pd.to_datetime(y.observation_date, utc=True)).sort_index()


def swap_factor(x, now, y, case):
    """Multiplier on R_swap per trade; swap_sensitivity.recost, same definitions."""
    f = np.ones(len(x))
    pts = x.market.map(now).to_numpy() / x.entry_price.to_numpy()
    if case == "A":
        return f
    if case == "B":
        return pts
    y_today = float(y[y.index >= pd.Timestamp("2026-09-01", tz="UTC")].mean())
    if case == "D":
        k = x.market.isin(CRYPTO).to_numpy()
        f[k] = pts[k]
    ys = ((y.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    j = np.searchsorted(ys, x.t.to_numpy(), side="right") - 1
    yt = np.where(j >= 0, y.to_numpy()[np.maximum(j, 0)], np.nan)
    for m in METALS:
        k = (x.market == m).to_numpy()
        if k.any():
            margin = max(SWAP_LONG_BP[m] / 1e4 * 365 - y_today, 0.0)
            f[k] = (np.maximum(np.nan_to_num(yt[k], nan=y_today), 0) + margin) / (y_today + margin)
    return f


def now_prices(T):
    """'Today's price' as swap_sensitivity defines it: the last exit price per market in the hand-off period."""
    allx = pd.concat(T.values())
    return allx.sort_values("tx").groupby("market").exit_price.last().to_dict()


def versions(T, markets=M4):
    """Every trade of every book with R under each cost version: columns R_<v>, R_spread_<v>, R_swap_<v>, and R_gross_eff, the
    gross R consistent with the published R (R + spread + swap; differs from R_gross only on Fed-rule exits)."""
    now, y = now_prices(T), us2y()
    out = []
    for b, x in T.items():
        x = x[x.market.isin(markets)].copy()
        fs = x.market.map(lambda m: (CENT_BP[m] + 1.0) / MODEL_BP[m]).to_numpy()
        x["R_pub"], x["R_spread_pub"], x["R_swap_pub"] = x.R, x.R_spread, x.R_swap
        x["R_gross_eff"] = x.R + x.R_spread + x.R_swap
        for v, case in (("realC", "C"), ("real", "D"), ("worst", "B")):
            x[f"R_spread_{v}"] = x.R_spread * fs
            x[f"R_swap_{v}"] = x.R_swap * swap_factor(x, now, y, case)
            x[f"R_{v}"] = x.R - (x[f"R_spread_{v}"] - x.R_spread) - (x[f"R_swap_{v}"] - x.R_swap)
        out.append(x)
    return pd.concat(out, ignore_index=True).sort_values(["t", "market", "book"], kind="mergesort").reset_index(drop=True)


if __name__ == "__main__":
    import json
    import sys
    # check against the research's own run (swap_sensitivity.json was computed on the trades before the gold M1 refill)
    folder = sys.argv[1] if len(sys.argv) > 1 else HANDOFF
    T = load(folder)
    now, y = now_prices(T), us2y()
    ref = json.loads((HANDOFF.parent / "swap_sensitivity.json").read_text())
    for case in "ABCD":
        got = {}
        for b, x in T.items():
            f = swap_factor(x, now, y, case)
            if case == "C":                      # C = metals rate-linked, everything else as published
                f = np.where(x.market.isin(METALS), f, 1.0)
            got[b] = float((x.R + x.R_swap - x.R_swap * f).mean())
        print(case, " ".join(f"{b} {got[b]:+.5f} (ref {ref[case]['R_per_trade'][b]:+.5f})" for b in got))
