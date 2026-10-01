"""MT5-Strategy-Tester-style page for G27K (operator 2026-10-01: "make it an artifact like the G768 backtest report").
Three systems from data/grid27k/g27k_real.csv, all F1 / G2 / H2 so report768.sim_paths reproduces them (stops and adds walked on H1):
  S1 C8/D3/E1/F1/G2/H2/I1/J1  best CAGR of the 27,648 (1 % per trade)
  S2 C1/D8/E1/F1/G2/H2/I2/J1  best total R (Turtle adds, 0.25 % per unit)
  S0 C2/D1/E1/F1/G2/H2/I1/J1  the system of the G768 report, for comparison (1 % per trade)
Signals come from g27k.prepare / directions, so the totals match the grid. Universes: gold + silver + BTC, each alone, and the other 14
G768 markets. Entries 2021-10-01..2026-09-30 only. Writes data/grid27k/report27k.json; `python report27k.py TEMPLATE OUT_HTML` fills
the template's /*DATA*/ placeholder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

SYSTEMS = {
    "S1": dict(combo="C8/D3/E1/F1/G2/H2/I1/J1", I="I1", risk=0.01, label="อันดับ 1 ตาม % ต่อปี", tab="อันดับ 1 % ต่อปี",
               rules=["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 10 แท่งก่อนหน้า ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
                      "ไม่เข้า ถ้ามีข่าว USD ระดับ HIGH ภายใน 8 ชั่วโมงหลังเข้า",
                      "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง (ไม่มี TP)",
                      "ไม้เดียว ความเสี่ยง 1% ต่อไม้ · ตลาดละ 1 ไม้ ถือหลายตลาดพร้อมกันได้"]),
    "S2": dict(combo="C1/D8/E1/F1/G2/H2/I2/J1", I="I4", risk=0.0025, label="อันดับ 1 ตาม R รวม", tab="อันดับ 1 R รวม",
               rules=["เข้า: แท่ง H4 ปิดเหนือ swing high ล่าสุดที่ยืนยันแล้ว (fractal 2) ซื้ออย่างเดียว เข้าที่ราคาเปิดแท่งถัดไป",
                      "ไม่มีตัวกรองบริบท",
                      "SL เริ่มต้น 2 × ATR20 · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง (ไม่มี TP)",
                      "เติมไม้ทุก +0.5 × ATR20 สูงสุด 4 หน่วย ความเสี่ยง 0.25% ต่อหน่วย · SL ทุกหน่วยย้ายเป็นราคาเติมล่าสุด − 2 × ATR20"]),
    "S0": dict(combo="C2/D1/E1/F1/G2/H2/I1/J1", I="I1", risk=0.01, label="ระบบเดิมจากรายงาน G768", tab="ระบบเดิม",
               rules=["เข้า: แท่ง H4 ปิดเหนือ High สูงสุด 20 แท่งก่อนหน้า และ D1 ปิดเหนือกึ่งกลางกรอบ 55 วัน ซื้ออย่างเดียว",
                      "SL 2 × ATR20 ไม่ขยับ · ออกเมื่อแท่ง H4 ปิดต่ำกว่า Low ต่ำสุด 20 แท่ง (ไม่มี TP)",
                      "ไม้เดียว ความเสี่ยง 1% ต่อไม้ · ตลาดละ 1 ไม้ ถือหลายตลาดพร้อมกันได้"]),
}
UNIS = {"MET3": K.MKTS, "XAUUSD": ["XAUUSD"], "XAGUSD": ["XAGUSD"], "BTCUSD": ["BTCUSD"], "OTHER14": K.OTHER}


def grid_meta():
    real = pd.read_csv(K.OUT / "g27k_real.csv"); early = pd.read_csv(K.OUT / "g27k_early.csv").set_index("combo")
    drift = [pd.read_csv(f) for f in sorted(K.OUT.glob("g27k_drift[0-9].csv"))]
    flat = [pd.read_csv(f) for f in sorted(K.OUT.glob("g27k_placebo[0-9].csv"))]
    rr = real.set_index("combo")
    rank = lambda c, col: int(real[col].rank(ascending=False, method="min")[real.combo == c].iloc[0])
    sysm = {}
    for k, s in SYSTEMS.items():
        c = s["combo"]; e = early.loc[c]
        sysm[k] = dict(combo=c, rank_cagr=rank(c, "cagr"), rank_totR=rank(c, "totR"), grid_totR=float(rr.loc[c, "totR"]),
                       early=dict(totR=float(e.totR), cagr=float(e.cagr), dd=float(e.dd), n=int(e.n),
                                  by_mkt={m: float(e[f"totR_{m}"]) for m in K.MKTS}),
                       drift_same=sorted(float(D.set_index("combo").loc[c, "totR"]) for D in drift))
    return dict(n_combos=len(real), real_best_totR=float(real.totR.max()), real_best_cagr=float(real.cagr.max()),
                real_basic=int(((real.p < 0.05) & (real.R > 0)).sum()),
                drift_best_totR=[float(D.totR.max()) for D in drift], drift_best_cagr=[float(D.cagr.max()) for D in drift],
                drift_basic=[int(((D.p < 0.05) & (D.R > 0)).sum()) for D in drift],
                flat_best_totR=[float(D.totR.max()) for D in flat], early_median=float(early.totR.median()), systems=sysm)


def main():
    ext = K.externals(); Ms, Xs = {}, {}
    for m in K.MKTS + K.OTHER:
        h1 = G.load_h1(m); Ms[m] = K.prepare(m, h1, ext); Xs[m] = G.features(G.frames(h1), m, "H4"); Xs[m]["sec"] = 14400
        assert np.array_equal(Ms[m]["t"], Xs[m]["t"]), m
    meta = grid_meta(); out = {}
    for k, s in SYSTEMS.items():
        Cc, D, E, F, Gs, H, I, J = s["combo"].split("/")
        trades = {}
        for m in Ms:
            d = K.directions(Ms[m], Cc, D, E, J); idx = np.flatnonzero(d)
            trades[m] = [dict(tr, X=Xs[m]) for tr in RP.sim_paths(Xs[m], m, idx, d[idx], s["I"])]
        tot3 = sum(r["R"] for m in K.MKTS for r in trades[m])
        print(f"{k} {s['combo']}: R total on 3 markets {tot3:.1f} (grid {meta['systems'][k]['grid_totR']:.1f})")
        for u, mk in UNIS.items():
            sub = [r for m in mk for r in trades[m]]
            T = RP.timeline(sub, {m: Xs[m] for m in mk}); RP.prep_marks(sub, T)
            M = RP.metrics(RP.account(sub, s["risk"]), T, s["risk"])
            bars = int(sum(int(((Xs[m]["t"] >= G.START) & (Xs[m]["t"] <= T[-1])).sum()) for m in mk))
            M["curve"] = {kk: v for kk, v in M["curve"].items()}
            out[f"{k}_{u}"] = dict(key=k, uni=u, mkts=mk, deposit=RP.DEPOSIT, markets=len(mk), bars=bars,
                                   risk_table=[RP.metrics(RP.account(sub, rk), T, rk, full=False) for rk in RP.RISKS], **M)
            print(f"   {u:8s} trades {M['trades']:5d} total {M['net'] / RP.DEPOSIT:+.0%} CAGR {M['cagr']:+.1%} eqDD {M['equity_dd']['relative_pct']:.1%}")
    out["META"] = dict(meta, systems_info={k: dict(label=s["label"], tab=s["tab"], rules=s["rules"], combo=s["combo"], risk=s["risk"],
                                                   adds=s["I"] == "I4") for k, s in SYSTEMS.items()})
    (K.OUT / "report27k.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    if len(sys.argv) > 2:
        tpl = Path(sys.argv[1]).read_text(encoding="utf-8")
        Path(sys.argv[2]).write_text(tpl.replace("/*DATA*/", json.dumps(out, ensure_ascii=False)), encoding="utf-8")
        print("html written", sys.argv[2])


if __name__ == "__main__":
    main()
