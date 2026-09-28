"""Compounding version of the WPWB risk backtest, with stop-out, DD in %,
sizing for a target max drawdown, and side kill-switches.

Exposure: hold gold the whole week, LONG or SHORT (the report never chooses
direction). Lots each week = BASE_LOT_PER_10K x (equity / 10,000) x vol_scale
(or x 1 for "fixed"), rounded DOWN to 0.01; below 0.01 lot the account stops
trading. Stop-out: if equity at the week's worst H1 price (adverse excursion)
would be <= 0, the account is wiped (Exness stop-out ~0%).

Three questions (operator 2026-09-28):
A. DD% of the current setting (0.10 lot per $10,000), compounding.
B. Which base size gives max DD 30% / 40% / never above 45% — on the actual
   long and short paths, and on 2,000 random-direction paths (we do not know
   direction in advance, so sizing must survive either side).
C. Could a pre-set rule have stopped the short side? Kill-switch at a side
   drawdown of 10/20/30% — applied to BOTH sides, because the rule cannot know
   which side is the wrong one.
In-sample and descriptive: the gold path 2022-2026 is one history.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402

ACCOUNT = 10_000.0
OZ = 100.0
STEP = 0.01
FIRST = int(np.datetime64("2022-07-01T22:15:00", "s").astype(np.int64))
OUT_X = BR.WEEKLY_DIR / "backtest_compound.xlsx"
N_SIM = 2000
SEED = 20260928


def weeks():
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    rows = []
    for k, cut in enumerate(cuts):
        if cut < FIRST or not np.isfinite(f[k]):
            continue
        lo, hi = m.week_bars(int(cut))
        e = float(m.o[lo])
        rows.append(dict(
            week=pd.to_datetime(int(cut) + 7 * 3600, unit="s"), entry=e,
            s=V.vol_scale(f[k]), hi=V.label(rv[k] / med[k])[1] in ("HIGH", "EXTREME"),
            bp_l=float(m.pnl_bp([lo], [hi - 1], [1])[0]),
            bp_s=float(m.pnl_bp([lo], [hi - 1], [-1])[0]),
            mae_l=float((m.l[lo:hi].min() - e) / e * 1e4),      # worst for a long (<= 0)
            mae_s=float((e - m.h[lo:hi].max()) / e * 1e4),      # worst for a short (<= 0)
        ))
    return pd.DataFrame(rows)


def simulate(bp, mae, entry, scale, base, kill=None):
    """Vectorised over paths. bp/mae: (n_paths, n_weeks). Returns equity
    (n_paths, n_weeks), stopped flags, wiped flags."""
    n_p, n_w = bp.shape
    eq = np.full(n_p, ACCOUNT)
    peak = eq.copy()
    alive = np.ones(n_p, bool)
    wiped = np.zeros(n_p, bool)
    killed = np.full(n_p, -1)
    out = np.empty((n_p, n_w))
    for w in range(n_w):
        lots = np.floor(base * eq / ACCOUNT * scale[w] / STEP + 1e-9) * STEP
        trade = alive & (lots >= STEP) & (killed < 0)
        usd_bp = entry[w] * OZ / 1e4
        worst = eq + lots * usd_bp * mae[:, w]
        blow = trade & (worst <= 0)
        pnl = np.where(trade, lots * usd_bp * bp[:, w], 0.0)
        eq = np.where(blow, 0.0, eq + pnl)
        wiped |= blow
        alive &= ~blow & (eq > 0)
        peak = np.maximum(peak, eq)
        if kill is not None:
            hit = (killed < 0) & alive & (eq <= peak * (1 - kill))
            killed[hit] = w
        out[:, w] = eq
    return out, killed, wiped


def dd_pct(eq):
    e = np.c_[np.full(len(eq), ACCOUNT), eq]
    peak = np.maximum.accumulate(e, axis=1)
    return ((e - peak) / peak).min(axis=1) * 100


def main() -> int:
    df = weeks()
    n = len(df)
    entry = df.entry.to_numpy()
    s_scaled = df.s.to_numpy()
    s_fixed = np.ones(n)
    L = df[["bp_l", "mae_l"]].to_numpy().T
    S = df[["bp_s", "mae_s"]].to_numpy().T
    print(f"weeks {n}: {df.week.iloc[0]:%Y-%m-%d} .. {df.week.iloc[-1]:%Y-%m-%d}")

    # A. current setting, compounding
    A = []
    for side, (bp, mae) in (("ซื้อ", L), ("ขาย", S)):
        for mode, sc in (("ไม้คงที่", s_fixed), ("× vol_scale", s_scaled)):
            eq, _, wiped = simulate(bp[None], mae[None], entry, sc, 0.10)
            A.append({"แบบ (ทบต้น, 0.10 lot ต่อ $10,000)": f"{side} {mode}",
                      "ทุนสุดท้าย ($)": round(eq[0, -1]), "max DD (%)": round(dd_pct(eq)[0], 1),
                      "บัญชีแตก": "ใช่" if wiped[0] else "ไม่"})
    A = pd.DataFrame(A)

    # B. base size vs max DD
    rng = np.random.default_rng(SEED)
    d = rng.choice([1, -1], size=(N_SIM, n))
    bp_r = np.where(d > 0, L[0], S[0])
    mae_r = np.where(d > 0, L[1], S[1])
    B = []
    for base in (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20):
        row = {"ไม้ตั้งต้นต่อ $10,000": base,
               "notional ตอนทอง $4,300 (เท่าของทุน)": round(base * OZ * 4300 / ACCOUNT, 2)}
        for mode, sc in (("คงที่", s_fixed), ("vol", s_scaled)):
            eL, _, _ = simulate(L[0][None], L[1][None], entry, sc, base)
            eS, _, wS = simulate(S[0][None], S[1][None], entry, sc, base)
            eR, _, wR = simulate(bp_r, mae_r, entry, sc, base)
            ddR = dd_pct(eR)
            row[f"DD ซื้อ ({mode}) %"] = round(dd_pct(eL)[0], 1)
            row[f"DD ขาย ({mode}) %"] = round(dd_pct(eS)[0], 1)
            row[f"สุ่มทิศ ({mode}) DD กลาง %"] = round(np.median(ddR), 1)
            row[f"สุ่มทิศ ({mode}) DD แย่ 5% %"] = round(np.percentile(ddR, 5), 1)
            row[f"สุ่มทิศ ({mode}) โอกาส DD เกิน 45%"] = round(float((ddR <= -45).mean()), 3)
        B.append(row)
    B = pd.DataFrame(B)

    # C. side kill-switch
    C = []
    for kill in (None, 0.10, 0.20, 0.30):
        for side, (bp, mae) in (("ซื้อ", L), ("ขาย", S)):
            eq, killed, _ = simulate(bp[None], mae[None], entry, s_scaled, 0.10, kill)
            k = int(killed[0])
            C.append({"กฎหยุดฝั่ง (DD จากยอด)": "ไม่มี" if kill is None else f"{kill:.0%}",
                      "ฝั่ง": side, "หยุดเมื่อ": "-" if k < 0 else f"{df.week.iloc[k]:%Y-%m-%d} (สัปดาห์ที่ {k + 1})",
                      "ทุนสุดท้าย ($)": round(eq[0, -1]), "max DD (%)": round(dd_pct(eq)[0], 1)})
        eR, killedR, _ = simulate(bp_r, mae_r, entry, s_scaled, 0.10, kill)
        C.append({"กฎหยุดฝั่ง (DD จากยอด)": "ไม่มี" if kill is None else f"{kill:.0%}",
                  "ฝั่ง": "สุ่มทิศ 2,000 รอบ (ค่ากลาง)",
                  "หยุดเมื่อ": "-" if kill is None else f"ถูกหยุด {(killedR >= 0).mean():.0%} ของรอบ",
                  "ทุนสุดท้าย ($)": round(float(np.median(eR[:, -1]))),
                  "max DD (%)": round(float(np.median(dd_pct(eR))), 1)})
    C = pd.DataFrame(C)

    with pd.ExcelWriter(OUT_X) as xw:
        A.to_excel(xw, sheet_name="A ค่าปัจจุบัน ทบต้น", index=False)
        B.to_excel(xw, sheet_name="B ขนาดไม้ vs DD", index=False)
        C.to_excel(xw, sheet_name="C กฎหยุดฝั่ง", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30)
    print("\nA\n" + A.to_string(index=False))
    print("\nB\n" + B.to_string(index=False))
    print("\nC\n" + C.to_string(index=False))
    print(f"\nsaved {OUT_X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
