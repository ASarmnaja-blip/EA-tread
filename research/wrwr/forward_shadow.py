"""WRWR SHADOW record (docs/WRWR_SHADOW_PREREG.md): weekly champions of the frozen shadow configurations, appended (hash-chained) at
each Friday 22:15 UTC cut, and the paper outcome of the frozen champion history replayed through the C2 simulator.
Paper only - nothing here can place an order. Usage:
  python research/wrwr/forward_shadow.py                run at the current data end (normal weekly use)
  python research/wrwr/forward_shadow.py --truncate <UTC ISO>   test mode: pretend the data ended then (writes to a scratch dir)
Outputs in data/wrwr/forward/: champions.csv (frozen, append-only), scores_latest.csv, weekly_scores_final.csv, summary_th.md."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import f2_signals as F2  # noqa: E402
import portfolio as PF  # noqa: E402
import signals as SG  # noqa: E402

sys.path[:0] = [str(K.ROOT / "research" / "foundry"), str(K.ROOT / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402

FIRST_FORWARD_CUT = int(pd.Timestamp("2026-10-02 22:15:00").timestamp())
CONFIGS = {"F2-66": dict(window=52, lcb_z=1.0, pool="H1", m=2), "F2-78": dict(window=52, lcb_z=1.0, pool="H1+H4+D1", m=2),
           "F2-134": dict(window=78, lcb_z=2.0, pool="H4", m=2), "F2-86": dict(window=52, lcb_z=2.0, pool="H4", m=2)}
MINN = 10
TFS = ("H1", "H4", "D1")
SESSIONS = {"ALL": (0, 24), "ASIA": (0, 7), "LONDON": (7, 12), "NY": (12, 17)}
SHADOW_FILES = [HERE / "forward_shadow.py", HERE / "contracts.py", HERE / "portfolio.py", HERE / "f2_signals.py", HERE / "signals.py",
                K.ROOT / "research" / "foundry" / "engine.py", K.ROOT / "research" / "wpwb_weekly" / "vol.py"]
DESC = {
    "fvg_form": ("การเกิดช่องว่างราคา (FVG) 3 แท่ง", "ซื้อเมื่อเกิด FVG ขาขึ้น / ขายเมื่อ FVG ขาลง"),
    "fvg_retest": ("ราคากลับมาทดสอบ FVG", "ซื้อเมื่อราคาย่อลงแตะช่อง FVG ขาขึ้นแล้วปิดเหนือขอบล่าง / กลับข้างสำหรับขาลง"),
    "bos": ("โครงสร้างตลาดทะลุ swing ตามเทรนด์ (BOS)", "ซื้อเมื่อปิดทะลุ swing high ในเทรนด์ขึ้น / ขายเมื่อทะลุ swing low ในเทรนด์ลง"),
    "choch": ("โครงสร้างกลับทิศ (CHoCH)", "ซื้อเมื่อโครงสร้างพลิกเป็นขาขึ้น / ขายเมื่อพลิกเป็นขาลง"),
    "sweep_pd": ("กวาดสภาพคล่องเหนือ/ใต้ High-Low เมื่อวานแล้วปิดกลับ", "ซื้อเมื่อไส้ทะลุ Low เมื่อวานแล้วปิดกลับเหนือ / ขายเมื่อทะลุ High เมื่อวานแล้วปิดกลับใต้"),
    "sweep20": ("กวาดสภาพคล่อง High-Low 20 แท่ง", "ซื้อ/ขายเมื่อไส้ทะลุ Low/High 20 แท่งแล้วปิดกลับ"),
    "disp": ("แท่งวิ่งแรง (displacement) > 2 ATR", "ซื้อเมื่อแท่งขึ้นแรงปิดใกล้ High / ขายเมื่อแท่งลงแรงปิดใกล้ Low"),
    "ob_retest": ("ราคากลับมาทดสอบ Order Block", "ซื้อเมื่อย้อนแตะแท่งแดงสุดท้ายก่อนแท่งขึ้นแรง / กลับข้างสำหรับขาลง"),
    "pd_break": ("ปิดทะลุ High/Low เมื่อวาน", "ซื้อเมื่อปิดเหนือ High เมื่อวาน / ขายเมื่อปิดใต้ Low เมื่อวาน"),
    "pw_break": ("ปิดทะลุ High/Low สัปดาห์ก่อน", "ซื้อเมื่อปิดเหนือ High สัปดาห์ก่อน / ขายเมื่อปิดใต้ Low สัปดาห์ก่อน"),
    "pivot_x": ("ปิดตัดจุด Pivot ของเมื่อวาน", "ซื้อเมื่อปิดตัดขึ้นเหนือ Pivot / ขายเมื่อตัดลงใต้"),
    "round50_x": ("ปิดข้ามเลขกลม $50", "ซื้อเมื่อปิดข้ามขึ้น / ขายเมื่อข้ามลง"),
    "round100_x": ("ปิดข้ามเลขกลม $100", "ซื้อเมื่อปิดข้ามขึ้น / ขายเมื่อข้ามลง"),
    "gap_day": ("ช่องว่างราคาเปิดวัน > 0.5 ATR", "ซื้อเมื่อเปิดวันขึ้นช่อง / ขายเมื่อลงช่อง"),
    "fix_am": ("เวลา London Fix 10:30", "เข้าที่แท่งที่มี 10:30 ตามเวลาลอนดอน (FADE = ขาย)"),
    "fix_pm": ("เวลา London Fix 15:00", "เข้าที่แท่งที่มี 15:00 ตามเวลาลอนดอน (FADE = ขาย)"),
    "ny_open": ("เปิดตลาดนิวยอร์ก 09:30", "เข้าที่แท่งเปิด NY (FADE = ขาย)"),
    "tom": ("วันทำการสุดท้ายของเดือน", "เข้าซื้อที่แท่งแรกของวันทำการสุดท้ายของเดือน (FADE = ขาย)"),
    "nr7_break": ("วันก่อนหน้าแคบสุดใน 7 วัน (NR7) แล้วทะลุกรอบ", "ซื้อเมื่อปิดเหนือ High เมื่อวาน / ขายเมื่อปิดใต้ Low เมื่อวาน"),
    "inside_break": ("วันก่อนหน้าเป็น Inside Day แล้วทะลุกรอบ", "ซื้อเมื่อปิดเหนือ High เมื่อวาน / ขายเมื่อปิดใต้ Low เมื่อวาน"),
    "squeeze_break": ("Bollinger บีบตัวแล้วทะลุแถบ", "ซื้อเมื่อปิดเหนือแถบบน / ขายเมื่อปิดใต้แถบล่าง"),
}
MODE_TH = {"FOLLOW": "ตามสัญญาณ", "FADE": "สวนสัญญาณ"}


def code_digest():
    """sha256 over the LF-normalised bytes of SHADOW_FILES (same on CRLF and LF checkouts)."""
    h = hashlib.sha256()
    for f in SHADOW_FILES:
        h.update(Path(f).read_bytes().replace(bytes([13, 10]), bytes([10])))
    return h.hexdigest()


def log(m):
    print(f"{pd.Timestamp.now(tz='UTC'):%H:%M:%S} {m}", flush=True)


# ------------------------------------------------------------------ data
def load_spliced(truncate_utc=None):
    """Dukascopy H1 + live Exness H1 (engine.load_spliced) as SG.mk bars; the C5 seam validator must pass when the seam is inside the
    data. truncate_utc drops bars that open at or after that time (test mode: 'the data ended then')."""
    until = int(pd.Timestamp(truncate_utc).timestamp()) if truncate_utc else None
    H, _, cuts, cell = E.load_spliced(until=until)
    base = SG.mk(H.t, H.o, H.h, H.l, H.c, np.zeros(len(H.t)), H.spread_bp, 3600)      # Family 2 uses no volume
    K.check_series(base.t, "spliced H1")
    Hd = E.load()[0]
    seam = int(Hd.t[-1]) + 3600
    if until is None or until > seam:
        import splice_check as SC
        A = dict(t=np.asarray(Hd.t, np.int64), o=np.asarray(Hd.o, float), c=np.asarray(Hd.c, float), sp=np.asarray(Hd.spread_bp, float))
        r = K.validate_seam(A, SC.exness_h1(), seam, strict=True, cost_floor_bp=K.COST_FLOOR_BP["XAUUSD"])
        log("C5 seam validation PASS " + ", ".join(f"{k} {v[1]}" for k, v in r.items() if k in ("spread_ratio", "offset_bp")))
    return base, cuts, cell


def resample_tf(base, tf):
    return base if tf == "H1" else SG.resample(base, SG.STEP[tf])


# ------------------------------------------------------------------ tables in memory (Family 2), same logic as build_f2.build
def build_tables(B, cuts, tf, symbol="XAUUSD"):
    sig = F2.f2_signals(B, cuts)
    N = len(B.t); step = B.step
    ek, at_cut = K.entry_week(B.t, cuts)
    ok_bar = np.isfinite(B.atr) & (ek >= 0)
    hours = pd.to_datetime(B.t, unit="s").hour.to_numpy()
    sessions = SESSIONS if tf == "H1" else {"ALL": (0, 24)}
    cands, cols = [], {x: [] for x in SG.COLS}
    for name, (sl, ss) in sig.items():
        il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
        ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
        o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
        if not len(ent0):
            continue
        for sname, (h0, h1) in sessions.items():
            in_sess = (hours[ent0] >= h0) & (hours[ent0] < h1)
            for mode, sgn in (("FOLLOW", 1.0), ("FADE", -1.0)):
                d = d0 * sgn
                for k in SG.KS:
                    for hold in SG.HOLDS[tf]:
                        keep = in_sess & ok_bar[ent0] & ~at_cut[ent0]
                        e, dd = ent0[keep], d[keep]
                        if not len(e):
                            continue
                        stop = k * B.atr[e]
                        c_bp = K.cost_bp(symbol, B.spread_bp[e])
                        immature = (e + hold - 1) > (N - 1)                       # hold window not over at the data end
                        for lab, mult in SG.EXITS:
                            tgt = mult * stop
                            g, ex = E.simulate(B, e, dd, stop, tgt, np.minimum(e + hold - 1, N - 1))
                            res = ~immature
                            if immature.any():                                    # resolved only if the stop / target was hit inside the data
                                lastb = N - 1
                                up = dd > 0
                                stop_hit = np.where(up, B.l[lastb] <= B.o[e] - stop, B.h[lastb] >= B.o[e] + stop)
                                tgt_hit = np.where(up, B.h[lastb] >= B.o[e] + tgt, B.l[lastb] <= B.o[e] - tgt)
                                res = res | (ex < lastb) | ((ex == lastb) & (stop_hit | tgt_hit))
                            if not res.all():
                                e_, dd_, g_, ex_, stop_, c_ = e[res], dd[res], g[res], ex[res], stop[res], c_bp[res]
                            else:
                                e_, dd_, g_, ex_, stop_, c_ = e, dd, g, ex, stop, c_bp
                            if not len(e_):
                                continue
                            sw = K.swap_bp(symbol, B.t[e_], B.t[ex_] + step, dd_)
                            ci = len(cands)
                            cands.append(dict(tf=tf, setup=f"{name}|{sname}", mode=mode, k_atr=k, exit=lab, hold=hold, n=int(len(e_))))
                            cols["cand"].append(np.full(len(e_), ci, np.int32)); cols["ent"].append(e_.astype(np.int32))
                            cols["ex"].append(ex_.astype(np.int32)); cols["dir"].append(dd_.astype(np.int8))
                            cols["gross_bp"].append(g_.astype(np.float32)); cols["cost_bp"].append(c_.astype(np.float32))
                            cols["swap_bp"].append(sw.astype(np.float32))
                            cols["stop_px"].append(stop_.astype(np.float32)); cols["entry_px"].append(B.o[e_].astype(np.float32))
    arr = {x: np.concatenate(v) for x, v in cols.items()}
    return cands, arr


def pool_from_tables(tabs, cuts, base, salt="shadow-f2"):
    """PF.Pool from in-memory tables [(tf, step, bar_t, cands, arr)] (same construction as PF.load_pool)."""
    cands, et, xt, dr, gb, cb, sb, sp, ep, R, stb = ([] for _ in range(11))
    for tf, step, bt, cl, a in tabs:
        order = np.lexsort((a["ent"], a["cand"]))
        cand = a["cand"][order]
        bounds = np.searchsorted(cand, np.arange(len(cl) + 1))
        gross, cost, swap = a["gross_bp"][order], a["cost_bp"][order], a["swap_bp"][order]
        stop_px, entry_px = a["stop_px"][order], a["entry_px"][order]
        stop_bp = stop_px.astype(np.float64) / entry_px.astype(np.float64) * 1e4
        Rall = ((gross.astype(np.float64) - cost - swap) / stop_bp)
        ent_t = bt[a["ent"][order]]; ex_t = bt[a["ex"][order]] + step
        dirs = a["dir"][order]
        for i, c in enumerate(cl):
            s, e = bounds[i], bounds[i + 1]
            cands.append(c); et.append(ent_t[s:e]); xt.append(ex_t[s:e]); dr.append(dirs[s:e]); gb.append(gross[s:e]); cb.append(cost[s:e])
            sb.append(swap[s:e]); sp.append(stop_px[s:e]); ep.append(entry_px[s:e]); R.append(Rall[s:e].astype(np.float32)); stb.append(stop_bp[s:e].astype(np.float32))
    for c in cands:
        c["hash"] = K.candidate_hash(c["tf"], c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"], salt)
    ptr = np.vstack([np.searchsorted(t, cuts, side="right") for t in et]).astype(np.int32)
    rank_key = np.argsort(np.argsort([c["hash"] for c in cands]))
    keys = [(c["tf"], c["k_atr"], c["exit"], c["hold"]) for c in cands]
    uniq = {k: i for i, k in enumerate(sorted(set(keys)))}
    return PF.Pool(cands, et, xt, dr, gb, cb, sb, sp, ep, R, stb, ptr, cuts, float(K.SYMBOLS["XAUUSD"]["trade_contract_size"]), rank_key,
                   np.array([uniq[k] for k in keys]), np.array([c["tf"] for c in cands]), base.t + base.step, base.c, {}, 0)


# ------------------------------------------------------------------ selection
def champions_all(P, cell, cuts):
    S1, S2, NN = PF.shadow_stats(P)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    masks = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, TFS)}
    scores = {}
    out = {}
    for name, c in CONFIGS.items():
        key = (c["window"], c["lcb_z"])
        if key not in scores:
            scores[key] = PF.window_scores(S1, S2, NN, c["window"], c["lcb_z"], MINN)
        sc, elig = scores[key]
        ch = PF.champions(sc, masks[c["pool"]], c["m"], P.rank_key, active)
        out[name] = (ch, sc, elig)
    return out, active


def describe(P, c):
    cd = P.cands[c]
    sig, sess = cd["setup"].split("|")
    d0 = DESC.get(sig, (sig, ""))
    return dict(hash=cd["hash"], tf=cd["tf"], signal=sig, session=sess, mode=cd["mode"], stop_atr=cd["k_atr"], exit=cd["exit"], hold=cd["hold"],
                text_th=f"{d0[0]} · {sess if sess != 'ALL' else 'ทุกเซสชัน'} · {MODE_TH[cd['mode']]} · SL {cd['k_atr']} ATR · TP:SL {cd['exit']} · ถือไม่เกิน {cd['hold']} "
                        f"{'วัน' if cd['tf'] == 'D1' else 'แท่ง ' + cd['tf']}",
                rule_th=d0[1] + (" — สวนสัญญาณ: ทำตรงข้ามกับที่ระบุ (ซื้อแทนขาย/ขายแทนซื้อ)" if cd["mode"] == "FADE" else ""))


# ------------------------------------------------------------------ frozen record
def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_chain(path):
    if not path.exists() or path.stat().st_size == 0:
        return [], "GENESIS"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    prev = "GENESIS"
    for r in df.itertuples():
        h = hashlib.sha256((prev + r.payload).encode()).hexdigest()
        if r.prev_hash != prev or r.row_hash != h:
            raise ValueError(f"champion record chain broken at seq {r.seq}")
        prev = h
    return df.to_dict("records"), prev


def append_rows(path, rows, prev):
    lines = []
    for r in rows:
        payload = canon(r["payload"])
        h = hashlib.sha256((prev + payload).encode()).hexdigest()
        lines.append(dict(seq=r["seq"], cut_utc=r["cut_utc"], config=r["config"], written_utc=r["written_utc"], payload=payload, prev_hash=prev, row_hash=h))
        prev = h
    df = pd.DataFrame(lines)
    df.to_csv(path, mode="a", header=not (path.exists() and path.stat().st_size > 0), index=False)
    return prev


def payload_for(P, out, name, k, cuts, cell, vs_fwd, data_end, digests):
    ch, sc, elig = out[name]
    rows = []
    for r, c in enumerate(ch[k]):
        d = describe(P, c)
        d["score"] = round(float(sc[c, k]), 9)
        rows.append(d)
    return dict(config=name, params=CONFIGS[name], cut_utc=str(pd.Timestamp(cuts[k], unit="s")), regime=str(cell[k]) if k < len(cell) else "",
                vol_scale_forward=round(float(vs_fwd[k]), 6), champions=rows, decision="TRADE" if rows else "NO TRADE", data_end_utc=str(pd.Timestamp(data_end, unit="s")),
                digests=digests)


# ------------------------------------------------------------------ main
def compute(truncate, t0=None, salt="shadow-f2"):
    t0 = t0 or time.time()
    base, cuts, cell = load_spliced(truncate)
    data_end = int(base.t[-1]) + 3600
    log(f"data through {pd.Timestamp(data_end, unit='s')} UTC, {len(base.t):,} H1 bars; building Family 2 tables")
    tabs = []
    for tf in TFS:
        B = resample_tf(base, tf)
        cl, a = build_tables(B, cuts, tf)
        tabs.append((tf, B.step, B.t, cl, a))
        log(f"  {tf}: {len(cl)} candidates, {len(a['cand']):,} rows ({time.time() - t0:.0f}s)")
    P = pool_from_tables(tabs, cuts, base, salt)
    out, active = champions_all(P, cell, cuts)
    vs_fwd = K.causal_vol_scale(base.t, base.c, base.h, base.l, cuts, mode="forward")
    return P, out, active, vs_fwd, cuts, cell, base, data_end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truncate", default=None)
    ap.add_argument("--scratch", action="store_true")
    args = ap.parse_args()
    global FIRST_FORWARD_CUT
    if args.scratch or args.truncate:                        # test modes may move the first cut back; the real record never can
        import os
        if os.environ.get("WRWR_SHADOW_FIRST_CUT"):
            FIRST_FORWARD_CUT = int(pd.Timestamp(os.environ["WRWR_SHADOW_FIRST_CUT"]).timestamp())
    t0 = time.time()
    out_dir = K.ROOT / "data" / "wrwr" / ("forward_scratch" if (args.truncate or args.scratch) else "forward")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = K.ROOT / "docs" / "WRWR_SHADOW_MANIFEST.md"
    code_sha = code_digest()
    if manifest.exists() and not args.truncate and not args.scratch:
        if code_sha not in manifest.read_text(encoding="utf-8"):
            log(f"code digest {code_sha[:16]} is not the one frozen in {manifest.name}: refusing to run (fail closed)")
            return 2
    P, out, active, vs_fwd, cuts, cell, base, data_end = compute(args.truncate, t0)
    NW = len(cuts)
    now = pd.Timestamp(args.truncate, tz="UTC") if args.truncate else pd.Timestamp.now(tz="UTC")
    now_s = int(now.timestamp())

    def covered(cut):
        """A cut is usable once its time has passed by 30 minutes (the weekly job runs at 23:00 UTC) and the data reaches the Friday close (gold closes 21:00-22:00 UTC, before the
        22:15 cut, so 'data_end >= cut' can never hold; the data must end within 4 hours of the cut)."""
        return now_s >= cut + 1800 and data_end >= cut - 4 * 3600

    ok_cuts = [k for k in range(NW) if covered(int(cuts[k]))]
    latest = ok_cuts[-1]
    digests = dict(code=code_sha[:16], data_end=data_end, cuts=K.sha_bytes(cuts)[:16], n_cands=len(P.cands))
    fwd_ks = [k for k in range(NW) if FIRST_FORWARD_CUT <= cuts[k] <= cuts[latest]]
    log(f"latest cut {pd.Timestamp(cuts[latest], unit='s')}; forward cuts to record: {len(fwd_ks)}")
    rec_path = out_dir / "champions.csv"
    rows_old, prev = read_chain(rec_path)
    done = {(r["cut_utc"], r["config"]) for r in rows_old}
    # integrity: every frozen row must be reproduced by the recomputed champions
    for r in rows_old:
        pl = json.loads(r["payload"])
        k = int(np.searchsorted(cuts, int(pd.Timestamp(pl["cut_utc"]).timestamp())))
        new = payload_for(P, out, pl["config"], k, cuts, cell, vs_fwd, data_end, digests)
        if [c["hash"] for c in new["champions"]] != [c["hash"] for c in pl["champions"]] or new["regime"] != pl["regime"]:
            raise ValueError(f"frozen record {pl['cut_utc']} {pl['config']} is not reproduced by the recomputation (data or code changed)")
    new_rows = []; seq = len(rows_old)
    for k in fwd_ks:
        for name in CONFIGS:
            key = (str(pd.Timestamp(cuts[k], unit="s")), name)
            if key in done:
                continue
            pl = payload_for(P, out, name, k, cuts, cell, vs_fwd, data_end, digests)
            late = (now_s - int(cuts[k])) > 3 * 86400
            pl["status"] = "LATE" if late else "OK"
            new_rows.append(dict(seq=seq, cut_utc=key[0], config=name, written_utc=str(pd.Timestamp.now(tz="UTC")), payload=pl)); seq += 1
    if new_rows:
        prev = append_rows(rec_path, new_rows, prev)
        log(f"appended {len(new_rows)} frozen champion rows")
    rows_all, _ = read_chain(rec_path)
    # ---- replay the frozen history through the C2 simulator (paper outcome)
    hash_to_idx = {c["hash"]: i for i, c in enumerate(P.cands)}
    by_cfg = {n: [[] for _ in range(NW)] for n in CONFIGS}
    for r in rows_all:
        pl = json.loads(r["payload"])
        k = int(np.searchsorted(cuts, int(pd.Timestamp(pl["cut_utc"]).timestamp())))
        by_cfg[pl["config"]][k] = [hash_to_idx[c["hash"]] for c in pl["champions"]]
    score_rows = []
    for name in CONFIGS:
        if not any(by_cfg[name]):
            continue
        wr, eq, cnt = PF.simulate(P, by_cfg[name], vs_fwd, f=0.01)
        for k in range(NW - 1):
            if cuts[k] >= FIRST_FORWARD_CUT and covered(int(cuts[k + 1])):
                final = data_end >= cuts[k + 1] + 30 * 86400
                score_rows.append(dict(config=name, cut_utc=str(pd.Timestamp(cuts[k], unit="s")), week_R=float(wr[k]), equity_at_cut=float(eq[k]),
                                       champions=len(by_cfg[name][k]), status="FINAL" if final else "PROVISIONAL"))
    S = pd.DataFrame(score_rows)
    S.to_csv(out_dir / "scores_latest.csv", index=False, float_format="%.9g")
    fin = out_dir / "weekly_scores_final.csv"
    if len(S):
        old = pd.read_csv(fin) if fin.exists() and fin.stat().st_size else pd.DataFrame(columns=S.columns)
        add = S[(S.status == "FINAL") & ~S.set_index(["config", "cut_utc"]).index.isin(old.set_index(["config", "cut_utc"]).index)]
        if len(add):
            pd.concat([old, add]).to_csv(fin, index=False, float_format="%.9g")
    # ---- Thai summary of the latest cut
    lines = ["# WRWR SHADOW — ตัวเต็งประจำสัปดาห์ (กระดาษเท่านั้น ไม่มีคำสั่งจริง)", "",
             f"ข้อมูลถึง {pd.Timestamp(data_end, unit='s'):%Y-%m-%d %H:%M} UTC · ตัดรอบล่าสุด {pd.Timestamp(cuts[latest], unit='s'):%Y-%m-%d %H:%M} UTC",
             f"สภาพตลาด WRWR: **{cell[latest] if latest < len(cell) else '-'}** · vol_scale (ค่าตรึงล่วงหน้า) {vs_fwd[latest]:.2f} (ลดขนาดไม้ได้อย่างเดียว)", ""]
    for name in CONFIGS:
        c = CONFIGS[name]
        ch = out[name][0][latest] if latest < NW else []
        lines.append(f"## {name}: {c['window']} สัปดาห์ · LCB z {c['lcb_z']} · กอง {c['pool']} · ตัวเต็งสูงสุด {c['m']} ตัว")
        if not ch:
            lines.append("- **NO TRADE** สัปดาห์นี้ (ไม่มีตัวเลือกที่คะแนนเป็นบวกหรือสภาพตลาดยังไม่พร้อม)")
        for r, cid in enumerate(ch):
            d = describe(P, cid)
            lines.append(f"- ตัวเต็ง {r + 1}: {d['text_th']}  (คะแนน {out[name][1][cid, latest]:.3f})\n  - สัญญาณ: {d['rule_th']}")
        if len(S) and (S.config == name).any():
            s = S[S.config == name]
            lines.append(f"- ผลกระดาษสะสม {len(s)} สัปดาห์: {s.week_R.sum():+.2f} R ( FINAL {int((s.status == 'FINAL').sum())} สัปดาห์ )")
        lines.append("")
    (out_dir / "summary_th.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"done in {time.time() - t0:.0f}s -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
