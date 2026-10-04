#!/usr/bin/env python3
"""Page for dropped_markets.json: can the markets we dropped turn positive?

Usage: python3 research/g27k_dev/report_dropped.py --out <html>
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TH = {"XAUUSD": "ทอง", "XAGUSD": "เงิน", "XCUUSD": "ทองแดง", "USOIL": "น้ำมัน WTI", "UKOIL": "น้ำมัน Brent", "XNGUSD": "ก๊าซ",
      "XPTUSD": "แพลทินัม", "XPDUSD": "พัลลาเดียม"}
GROUP = {**{m: "ดัชนีหุ้น" for m in ("US500", "USTEC", "DE30", "UK100", "FRA40", "AUS200", "HK50", "STOXX50", "JP225")},
         **{m: "สินค้าโภคภัณฑ์" for m in ("XCUUSD", "USOIL", "UKOIL", "XNGUSD", "XPTUSD", "XPDUSD", "XAUUSD", "XAGUSD")},
         **{m: "คริปโต" for m in ("BTCUSD", "ETHUSD")}}


def why(p):
    if p["kept"]:
        return ("keep", "ใช้อยู่")
    if p["R"] > 0:
        return ("weak", "บวกแต่อ่อน")
    if p["cost"] > 0.055:
        return ("cost", "ต้นทุนกิน")
    if p["up_years"] == 0:
        return ("flat", "ไม่เคยขึ้นแรง")
    if p["up_R"] < 0.35:
        return ("chop", "ขึ้นแต่ไม่เป็นเทรนด์")
    return ("rare", "ได้แค่ปีขึ้นแรง")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = json.loads((HERE / "dropped_markets.json").read_text())
    mk = sorted(d["markets"], key=lambda p: (not p["kept"], -p["R"]))
    panel = {}
    for r in d["panel"]:
        panel.setdefault(r["mkt"], {})[r["year"]] = dict(s=round(r["sumR"], 1), n=r["n"], mv=round(r["move"], 3), er=round(r["er"], 3))
    rows = []
    for p in mk:
        k, lab = why(p)
        rows.append(dict(m=p["mkt"], th=TH.get(p["mkt"], ""), grp=GROUP.get(p["mkt"], "ค่าเงิน"), kept=p["kept"], n=p["n"], R=round(p["R"], 3),
                         t=round(p["t"], 1), pos=p["pos"], yrs=p["years"], up=p["up_years"], upR=None if p["up_R"] != p["up_R"] else round(p["up_R"], 2),
                         l12=round(p["last12"], 1), cost=round(p["cost"], 3), drift=round(p["drift"], 3), cat=k, catTh=lab, y=panel.get(p["mkt"], {})))
    data = dict(bins=d["bins"], reg=d["reg"], rows=rows)
    html = (HERE / "report_dropped.html").read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    pathlib.Path(a.out).write_text(html, encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    main()
