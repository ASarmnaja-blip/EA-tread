"""WPWB H1 traces (prereg amendment 5).

Part A - descriptive H1 trace library, every week 2021-07..2026-09: where
the week's move happened (day, session, biggest bars), which news, prior-
week level breaks, DXY. Hindsight, for the rule-9 guideline library.
Part B - Wednesday 00:00 UTC checkpoint features W1-W5 vs rest-of-week,
two eras, single run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import common as C  # noqa: E402
from backtest_report import load_events  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from run_round3 import sigma_at  # noqa: E402

DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
SESS = {**{hh: "เอเชีย" for hh in (22, 23, 0, 1, 2, 3, 4, 5, 6)},
        **{hh: "ลอนดอน" for hh in range(7, 13)}, **{hh: "นิวยอร์ก" for hh in range(13, 22)}}
CP_OFFSET = 4 * 86400 + 105 * 60        # Fri 22:15 + 4d 1h45m = Wed 00:00 UTC
ERA_SPLIT = C.DEV_END
DXY_SPLIT = C.ep(2025, 1, 1)


def main() -> int:
    m = C.Market(combined_bars())
    dxy = np.load("data/fresh/DXY_M5.npz")
    ev = load_events()
    last = int(m.t[-1]) + C.HOUR

    def dxy_at(ts):
        j = int(np.searchsorted(dxy["t"], ts, side="right")) - 1
        return float(dxy["c"][j]) if j >= 0 and ts - dxy["t"][j] < 6 * 3600 else np.nan

    rows = []
    for cut in m.cuts:
        cut = int(cut)
        if cut + C.WEEK > last:
            break
        lo, hi = m.week_bars(cut); plo, phi = m.week_bars(cut - C.WEEK)
        if hi - lo < 50 or phi - plo < 50:
            continue
        cp = cut + CP_OFFSET
        assert pd.to_datetime(cp, unit="s").weekday() == 2
        kcp = int(np.searchsorted(m.t, cp))
        if kcp - lo < 10 or hi - kcp < 10:
            continue
        t, o, h, l, c = m.t, m.o, m.h, m.l, m.c
        br = (c[lo:hi] - o[lo:hi]) / o[lo:hi] * 1e4            # H1 bar returns, bp
        hrs = m.hour[lo:hi]; wds = m.wday[lo:hi]
        week_bp = (c[hi - 1] / o[lo] - 1) * 1e4
        long_bp = float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0])
        # ---- Wednesday features
        w1 = (c[kcp - 1] / o[lo] - 1) * 1e4
        d0, d1 = dxy_at(int(t[lo])), dxy_at(cp - 1)
        w2 = (d1 / d0 - 1) * 1e4 if np.isfinite(d0) and np.isfinite(d1) and dxy["t"][0] < t[lo] else np.nan
        ph, pl = h[plo:phi].max(), l[plo:phi].min()
        w3 = 0
        for k in range(lo, kcp):
            if c[k] > ph:
                w3 = 1
            elif c[k] < pl:
                w3 = -1
        sig = sigma_at(m, cut, 13)
        w4 = float(np.std(br[:kcp - lo]) / 1e4 / (sig / np.sqrt(22))) if np.isfinite(sig) and sig > 0 else np.nan
        wk_ev = ev[(ev.ts >= t[lo]) & (ev.ts < t[hi - 1] + C.HOUR)]
        reacts, w5 = [], 0
        for _, e in wk_ev.iterrows():
            k = int(np.searchsorted(t, e.ts, side="right")) - 1
            if k < lo or e.ts >= t[k] + C.HOUR or k + 2 >= hi:
                continue
            r3 = (c[k + 2] / o[k] - 1) * 1e4
            reacts.append(f"{e.event.split(' ')[0] if e.event != 'Fed Interest Rate Decision' else 'FOMC'}"
                          f"@{DAYS[int(m.wday[k])]} {int(m.hour[k]):02d}:00 {r3:+.0f}bp")
            if e.ts <= cp - 3 * 3600 and k + 2 < kcp:
                w5 += int(np.sign(r3))
        rest = (c[hi - 1] / c[kcp - 1] - 1) * 1e4
        # ---- descriptive trace
        day_net = {}
        for d in np.unique(wds):
            day_net[DAYS[int(d)]] = float(br[wds == d].sum())
        sess_net = {s: float(br[np.array([SESS.get(int(x)) == s for x in hrs])].sum())
                    for s in ("เอเชีย", "ลอนดอน", "นิวยอร์ก")}
        top = np.argsort(-np.abs(br))[:3]
        ev_hours = {int(np.searchsorted(t, x, side="right")) - 1 for x in wk_ev.ts}
        tops = []
        for j in top:
            k = lo + int(j)
            tag = " (มีข่าว)" if k in ev_hours else ""
            tops.append(f"{DAYS[int(m.wday[k])]} {int(m.hour[k]):02d}:00 {br[j]:+.0f}bp{tag}")
        first_dn = next((k for k in range(lo, hi) if c[k] < pl), None)
        first_up = next((k for k in range(lo, hi) if c[k] > ph), None)
        brk = []
        if first_up is not None:
            brk.append(f"ปิดเหนือ High สัปดาห์ก่อน {DAYS[int(m.wday[first_up])]} {int(m.hour[first_up]):02d}:00")
        if first_dn is not None:
            brk.append(f"ปิดใต้ Low สัปดาห์ก่อน {DAYS[int(m.wday[first_dn])]} {int(m.hour[first_dn]):02d}:00")
        abs_all = np.abs(br).sum()
        jump = float(np.abs(br[top]).sum() / abs_all) if abs_all > 0 else np.nan
        ev_share = float(np.abs(br[[k - lo for k in ev_hours if lo <= k < hi]]).sum() / abs_all) \
            if abs_all > 0 else np.nan
        worst_day = min(day_net, key=day_net.get); best_day = max(day_net, key=day_net.get)
        dxy_wk = (dxy_at(int(t[hi - 1]) + 3599) / d0 - 1) * 100 if np.isfinite(d0) else np.nan
        main_sess = max(sess_net, key=lambda s: abs(sess_net[s]))
        story = (f"{'ขาดทุน' if long_bp < 0 else 'กำไร'} {long_bp:+.0f}bp; "
                 f"{'ร่วง' if week_bp < 0 else 'ขึ้น'}หนักสุดวัน{worst_day if week_bp < 0 else best_day}; "
                 f"session หลัก {main_sess} {sess_net[main_sess]:+.0f}bp; แท่งใหญ่ {tops[0]}; "
                 + ("; ".join(brk) if brk else "ไม่หลุดกรอบสัปดาห์ก่อน")
                 + (f"; DXY {dxy_wk:+.2f}%" if np.isfinite(dxy_wk) else ""))
        rows.append(dict(
            cut=cut, week=pd.to_datetime(cut, unit="s").date(), era="A" if cut < ERA_SPLIT else "B",
            long_bp=round(long_bp, 1), week_bp=round(week_bp, 1), rest_bp=round(rest, 1),
            W1_ret_so_far=round(w1, 1), W2_dxy_so_far=round(w2, 1) if np.isfinite(w2) else np.nan,
            W3_prior_level=w3, W4_vol_ratio=round(w4, 2) if np.isfinite(w4) else np.nan, W5_news=w5,
            share_by_wed=round(w1 / week_bp, 2) if abs(week_bp) > 1 else np.nan,
            jumpiness_top3=round(jump, 2), news_hour_share=round(ev_share, 2),
            asia_bp=round(sess_net["เอเชีย"], 1), london_bp=round(sess_net["ลอนดอน"], 1),
            ny_bp=round(sess_net["นิวยอร์ก"], 1), worst_day=worst_day, best_day=best_day,
            biggest_bars=" | ".join(tops), level_breaks="; ".join(brk), news_reactions=" | ".join(reacts),
            dxy_week_pct=round(dxy_wk, 2) if np.isfinite(dxy_wk) else np.nan, story=story))
    df = pd.DataFrame(rows)
    df.to_csv("data/wpwb_h1_traces.csv", index=False)
    print(f"weeks: A {int((df.era == 'A').sum())}, B {int((df.era == 'B').sum())}")

    # ---------------- Part A: signatures, era B
    b = df[df.era == "B"]
    lose, win = b[b.long_bp < 0], b[b.long_bp > 0]
    print("\n== PART A (hindsight) - what losing vs winning weeks looked like at H1, 2024-01..2026-09")
    for col, lab in (("share_by_wed", "ส่วนของการเคลื่อนไหวที่เกิดก่อนวันพุธ"),
                     ("jumpiness_top3", "สัดส่วนจาก 3 แท่ง H1 ใหญ่สุด"),
                     ("news_hour_share", "สัดส่วนที่เกิดในชั่วโมงข่าว"),
                     ("asia_bp", "เอเชีย bp"), ("london_bp", "ลอนดอน bp"), ("ny_bp", "นิวยอร์ก bp"),
                     ("dxy_week_pct", "DXY ทั้งสัปดาห์ %")):
        print(f"   {lab:40s} ขาดทุน median {lose[col].median():+8.2f} | กำไร median {win[col].median():+8.2f}")
    print(f"   {'หลุด Low สัปดาห์ก่อน (ปิด H1 ใต้)':40s} ขาดทุน {lose.level_breaks.str.contains('ใต้').mean():.0%} "
          f"| กำไร {win.level_breaks.str.contains('ใต้').mean():.0%}")
    print(f"   {'วันที่ร่วงหนักสุด (สัปดาห์ขาดทุน)':40s} {lose.worst_day.value_counts().to_dict()}")

    # ---------------- Part B: Wednesday checkpoint test
    print("\n== PART B (pre-registered) - Wednesday 00:00 UTC H1 trace vs rest of week")
    res = []
    for f, eras in (("W1_ret_so_far", None), ("W2_dxy_so_far", "dxy"), ("W3_prior_level", None),
                    ("W4_vol_ratio", None), ("W5_news", None)):
        if eras == "dxy":
            e1 = df[(df.cut >= C.ep(2023, 9, 22)) & (df.cut < DXY_SPLIT)]; e2 = df[df.cut >= DXY_SPLIT]
            names = ("2023-09..2024-12", "2025-01..2026-09")
        else:
            e1, e2 = df[df.era == "A"], df[df.era == "B"]
            names = ("2021-07..2023-12", "2024-01..2026-09")
        out = []
        for x in (e1, e2):
            z = x[[f, "rest_bp"]].dropna()
            r, p = stats.spearmanr(z[f], z.rest_bp)
            out.append((r, p, len(z)))
        ok = np.sign(out[0][0]) == np.sign(out[1][0]) and out[0][1] < 0.01 and out[1][1] < 0.01
        res.append(dict(feature=f, era1=names[0], rho1=out[0][0], p1=out[0][1], n1=out[0][2],
                        era2=names[1], rho2=out[1][0], p2=out[1][1], n2=out[1][2], PASS=ok))
        print(f"   {f:16s} {names[0]}: rho {out[0][0]:+.2f} (p={out[0][1]:.3f}, n={out[0][2]}) | "
              f"{names[1]}: rho {out[1][0]:+.2f} (p={out[1][1]:.3f}, n={out[1][2]}) -> "
              f"{'PASS' if ok else 'fail'}")
    for e in ("A", "B"):
        z = df[df.era == e][["W4_vol_ratio", "rest_bp"]].dropna()
        r, p = stats.spearmanr(z.W4_vol_ratio, z.rest_bp.abs())
        print(f"   W4 vs |rest| (magnitude) era {e}: rho {r:+.2f} (p={p:.3f})")
    pd.DataFrame(res).to_csv("data/wpwb_h1_wednesday_test.csv", index=False)

    # ---------------- Excel library
    th = {"week": "สัปดาห์", "long_bp": "LONG ทั้งสัปดาห์ bp", "week_bp": "ทองทั้งสัปดาห์ bp",
          "rest_bp": "พุธ→ศุกร์ bp", "W1_ret_so_far": "W1 ทองถึงพุธ bp", "W2_dxy_so_far": "W2 DXY ถึงพุธ bp",
          "W3_prior_level": "W3 กรอบสัปดาห์ก่อน (+1 ยืนเหนือ/-1 ยืนใต้)", "W4_vol_ratio": "W4 ความผันผวนจริง/คาด",
          "W5_news": "W5 ทิศปฏิกิริยาข่าว", "share_by_wed": "สัดส่วนที่เกิดก่อนพุธ",
          "jumpiness_top3": "สัดส่วนจาก 3 แท่งใหญ่", "news_hour_share": "สัดส่วนในชั่วโมงข่าว",
          "asia_bp": "เอเชีย bp", "london_bp": "ลอนดอน bp", "ny_bp": "นิวยอร์ก bp",
          "worst_day": "วันร่วงหนักสุด", "best_day": "วันขึ้นหนักสุด", "biggest_bars": "3 แท่ง H1 ใหญ่สุด",
          "level_breaks": "การหลุดกรอบสัปดาห์ก่อน", "news_reactions": "ปฏิกิริยาข่าว (3 ชม.)",
          "dxy_week_pct": "DXY ทั้งสัปดาห์ %", "story": "สรุปร่องรอย"}
    x = df.drop(columns=["cut", "era"]).rename(columns=th)
    cols_first = ["สัปดาห์", "สรุปร่องรอย"] + [v for k, v in th.items() if k not in ("week", "story")]
    x = x[cols_first]
    with pd.ExcelWriter("data/wpwb_h1_trace_library.xlsx", engine="openpyxl") as xw:
        x.sort_values("LONG ทั้งสัปดาห์ bp").head(20).to_excel(xw, sheet_name="20 สัปดาห์ขาดทุนสุด", index=False)
        x.sort_values("LONG ทั้งสัปดาห์ bp", ascending=False).head(20).to_excel(
            xw, sheet_name="20 สัปดาห์กำไรสุด", index=False)
        pd.DataFrame(res).to_excel(xw, sheet_name="ทดสอบจุดเช็ควันพุธ", index=False)
        x.to_excel(xw, sheet_name="คลังร่องรอยทุกสัปดาห์", index=False)
    print("\nworst 8 weeks (story):")
    for _, r in df.nsmallest(8, "long_bp").iterrows():
        print(f"   {r.week}: {r.story}")
        print(f"        news: {r.news_reactions or '-'}")
    print("\nbest 8 weeks (story):")
    for _, r in df.nlargest(8, "long_bp").iterrows():
        print(f"   {r.week}: {r.story}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
