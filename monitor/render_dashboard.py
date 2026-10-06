#!/usr/bin/env python3
"""Render the Gold Watch page from latest.json (gold_monitor.py) and an
optional external.json written by the monitoring session:

  {"assessment": "normal" | "reduce" | "pause",
   "summary": "...",                      # Thai, a few sentences
   "events": [{"time_utc": "...", "name": "...", "currency": "USD", "impact": "high"}],
   "headlines": [{"title": "...", "source": "...", "url": "..."}]}

Usage: python3 monitor/render_dashboard.py --in-dir <dir> --out <file.html>
"""
import argparse
import html
import json
import pathlib

import pandas as pd

BKK = "Asia/Bangkok"


def th(ts):
    if not ts:
        return "-"
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert(BKK).strftime("%d %b %H:%M")


def esc(x):
    return html.escape(str(x))


CSS = """
:root{
  /* layout: one column of status bands, summary first, detail after */
  --bg:#f6f6f3; --panel:#ffffff; --fg:#1d2126; --muted:#5d6670; --line:#dfe1dc;
  --brass:#8a6a1f; --ok:#2f7d4f; --warn:#a8670b; --bad:#b23a35; --chip:#eef0ea;
  --display:"IBM Plex Sans Thai",system-ui,sans-serif; --body:"IBM Plex Sans Thai",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#14171a; --panel:#1c2024; --fg:#e7e9e4; --muted:#9aa3ab; --line:#2e3439;
  --brass:#d2ad55; --ok:#5fbf86; --warn:#e2a443; --bad:#e2716b; --chip:#252a2f; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#14171a; --panel:#1c2024; --fg:#e7e9e4; --muted:#9aa3ab; --line:#2e3439;
  --brass:#d2ad55; --ok:#5fbf86; --warn:#e2a443; --bad:#e2716b; --chip:#252a2f; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px;line-height:1.55}
.wrap{max-width:860px;margin:0 auto;padding-inline:16px;padding-block:20px 40px;display:grid;gap:18px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:12px}
h1{font-family:var(--display);font-size:26px;margin:0;font-weight:600;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px}
.price{font-family:var(--mono);font-size:28px;font-weight:600;font-variant-numeric:tabular-nums}
.price small{font-size:13px;color:var(--muted);font-weight:400}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px;font-weight:600}
.state{display:flex;gap:12px;align-items:flex-start;border-left:4px solid var(--c);padding-left:12px}
.state b{font-size:17px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{background:var(--chip);border-radius:999px;padding:3px 10px;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:12px}
td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.scroll{overflow-x:auto}
.pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:600;color:var(--panel);background:var(--c)}
.gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.g{display:grid;gap:4px;min-width:0}
.g .v{font-family:var(--mono);font-size:20px;font-variant-numeric:tabular-nums}
.g .ctx{font-size:12px;color:var(--muted)}
.bar{height:6px;background:var(--chip);border-radius:3px;position:relative}
.bar i{position:absolute;top:-3px;width:3px;height:12px;background:var(--brass);border-radius:1px}
ul{margin:0;padding-left:18px}
li{margin:4px 0}
a{color:var(--brass)}
footer{color:var(--muted);font-size:12px}
"""


def gauge(label, value, unit, lo, hi, ctx):
    if value is None:
        return ""
    pos = max(0.0, min(1.0, (value - lo) / (hi - lo))) * 100
    return (f'<div class="g"><span class="sub">{esc(label)}</span>'
            f'<span class="v">{value}{unit}</span>'
            f'<div class="bar" role="img" aria-label="{esc(label)} {value}{unit} on a scale {lo}-{hi}">'
            f'<i style="left:calc({pos:.1f}% - 1px)"></i></div>'
            f'<span class="ctx">{esc(ctx)}</span></div>')


def render(L, X):
    g = L["gauges"]
    d = g["distance"]
    assess = (X or {}).get("assessment", "normal")
    col = {"normal": "var(--ok)", "reduce": "var(--warn)", "pause": "var(--bad)"}.get(assess, "var(--muted)")
    word = {"normal": "เทรดตามระบบได้ตามปกติ", "reduce": "ลดขนาดไม้ใหม่ลงครึ่งหนึ่ง",
            "pause": "พักการเปิดไม้ใหม่ชั่วคราว"}.get(assess, assess)
    flags = L.get("flags") or []
    chips = "".join(f'<span class="chip">{esc(f)}</span>' for f in flags) or \
        '<span class="chip">ไม่มีสัญญาณหรือเรื่องที่ต้องจับตา</span>'

    def sysrow(name, desc, near, ok_txt):
        return f"<tr><td><b>{name}</b><br><span class='sub'>{esc(desc)}</span></td><td class='n'>{near}</td><td>{ok_txt}</td></tr>"

    yes = lambda b: '<span class="pill" style="--c:var(--ok)">ผ่าน</span>' if b else '<span class="pill" style="--c:var(--muted)">ไม่ผ่าน</span>'
    rows = [
        sysrow("H4-55", "ซื้อเมื่อปิดเหนือ High 55 แท่ง, ATR ≥ ค่ากลางปี",
               f"{d['H4-55 long']['to_trigger_atr']} ATR", "ตัวกรองความผันผวน " + yes(d['H4-55 long']['filter_ok'])),
        sysrow("D1-1", "ซื้อเมื่อปิดเหนือ High 20 วัน, W1 อยู่ครึ่งบน",
               f"{d['D1-1 long']['to_trigger_atr']} ATR", "ตัวกรอง W1 " + yes(d['D1-1 long']['w1_filter_ok'])),
    ]
    for k, lab in (("QB long", "QB ซื้อ"), ("QB short", "QB ขาย")):
        q = d[k]
        gap = max(0.0, round(q["gap_atr"] - q["need_gap_atr"], 2))
        rows.append(sysrow(lab, "เบรคแรกหลังเงียบ (ผู้สมัครจากการค้น)", f"{gap} ATR",
                           f"ตลาดเงียบ {yes(q['quiet_ok'])} · ไม่เบรคมา {q['bars_since_55_break']}/{q['need']} แท่ง "
                           + yes(q['bars_since_55_break'] >= q['need'])))
    trades = []
    for name, tr in L["paper"].items():
        for t in tr:
            side = "ซื้อ" if t["dir"] > 0 else "ขาย"
            if t["status"] == "CLOSED":
                res = f"ปิด {th(t['exit_time'])} @ {t['exit']} ({t['reason']}) <b>{t['R']:+.2f}R</b>"
            elif t["status"] == "OPEN":
                res = f"เปิดอยู่ ราคา {t['last']} = {t['open_R']:+.2f}R · ห่าง SL {t['to_stop_atr']} ATR"
            else:
                res = "สัญญาณเกิดแล้ว เข้าที่ราคาเปิดแท่งถัดไป"
            ent = f"{th(t.get('entry_time'))} @ {t.get('entry', '-')} SL {t.get('stop', '-')}" if "entry" in t else th(t["signal_close"])
            trades.append(f"<tr><td><b>{name}</b> {side}</td><td class='n'>{ent}</td><td>{res}</td></tr>")
    trade_html = ("<div class='scroll'><table><tr><th>ระบบ</th><th>เข้า</th><th>สถานะ</th></tr>"
                  + "".join(trades) + "</table></div>") if trades else \
        f"<p class='sub'>ยังไม่มีไม้ในบันทึกกระดาษ (เริ่มบันทึก {th(L['forward_start'])})</p>"
    ev = (X or {}).get("events") or []
    ev_html = "<div class='scroll'><table><tr><th>เวลาไทย</th><th>ข่าว</th><th>ระดับ</th></tr>" + "".join(
        f"<tr><td class='n'>{th(e.get('time_utc'))}</td><td>{esc(e.get('name'))} <span class='sub'>{esc(e.get('currency', ''))}</span></td>"
        f"<td>{esc(e.get('impact', ''))}</td></tr>" for e in ev) + "</table></div>" if ev else \
        "<p class='sub'>ไม่มีข่าวระดับสูงใน 48 ชม. ข้างหน้า (หรือยังไม่ได้ตรวจในรอบนี้)</p>"
    hl = (X or {}).get("headlines") or []
    hl_html = "<ul>" + "".join(
        f"<li><a href='{esc(h.get('url', '#'))}'>{esc(h.get('title'))}</a> <span class='sub'>{esc(h.get('source', ''))}</span></li>"
        for h in hl) + "</ul>" if hl else ""
    gg = "".join([
        gauge("ความผันผวน 20 วัน (ต่อปี)", g["vol20_annual_pct"], "%", 5, 35, g["vol_context"]),
        gauge("ATR H4 เทียบรอบปี", round(g["h4_atr_pct_of_year"] * 100), "%", 0, 100, f"ATR H4 = ${g['h4_atr_usd']}"),
        gauge("อัตราเบรคหลอก 12 เดือน", round(g["false_breakout_rate_12m"] * 100) if g["false_breakout_rate_12m"] is not None else None,
              "%", 20, 60, g["false_breakout_context"]),
        gauge("spread แย่สุด 0.1% (24 ชม.)", g["spread_24h_p999_bp"], "bp", 0, 20,
              f"ค่ากลาง {g['spread_24h_median_bp']}bp · {g['spread_context']}"),
    ])
    return f"""<title>Gold Watch</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header><div><h1>Gold Watch</h1><div class="sub">XAUUSD · อัปเดต {th(L['run_utc'])} (เวลาไทย) · ข้อมูลถึงแท่ง H1 {th(g['last_h1'])}</div></div>
<div class="price">{g['price']:,.2f} <small>USD/oz</small></div></header>
<section><h2>สรุปรอบนี้</h2>
<div class="state" style="--c:{col}"><div><b>{esc(word)}</b><div>{esc((X or {}).get('summary', 'ยังไม่มีสรุปปัจจัยภายนอกในรอบนี้'))}</div></div></div>
<div class="chips">{chips}</div></section>
<section><h2>ระบบและระยะถึงสัญญาณ</h2><div class="scroll"><table><tr><th>ระบบ</th><th>ห่างสัญญาณ</th><th>เงื่อนไข</th></tr>{''.join(rows)}</table></div></section>
<section><h2>บันทึกกระดาษ (ไม่มีการส่งคำสั่งจริง)</h2>{trade_html}</section>
<section><h2>สภาพตลาด</h2><div class="gauges">{gg}</div></section>
<section><h2>ข่าวและปฏิทินเศรษฐกิจ</h2>{ev_html}{hl_html}</section>
<footer>คำนวณใหม่จากข้อมูล Dukascopy ทุกรอบด้วยกฎเดียวกับ backtest · ต้นทุนบันทึกกระดาษ: spread $0.26 + 1bp + swap ฝั่งซื้อ · ข่าวใช้เพื่อลดหรือพักเท่านั้น ไม่ใช้เพิ่มความเสี่ยง</footer>
</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = pathlib.Path(a.in_dir)
    L = json.loads((d / "latest.json").read_text())
    X = json.loads((d / "external.json").read_text()) if (d / "external.json").exists() else None
    pathlib.Path(a.out).write_text(render(L, X))


if __name__ == "__main__":
    main()
