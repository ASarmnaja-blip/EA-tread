"""Run this the moment the MT5 terminal is logged into the Exness Standard Cent account.

Answers the three questions HANDOFF_G27K_FINAL.md section 3.1 leaves open for a cent account, read-only, no orders:
  1. does the account carry JP225 in any spelling, or is the live system really only gold, silver and BTC
  2. are the cent contracts exactly 1/100 of the Standard ones, which is what makes the 10,000 USD demo a valid model of 10,000 USC
  3. what percentage of a 10,000-unit balance the minimum lot risks at the research SL distances, at full risk and inside the 25 % brake
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SL_PCT = {"XAUUSD": 0.010, "XAGUSD": 0.019, "BTCUSD": 0.031, "JP225": 0.014}
STANDARD = {"XAUUSD": 100.0, "XAGUSD": 5000.0, "BTCUSD": 1.0, "JP225": 1.0}      # contract sizes read on the Standard demo
TRADE_MODE = {0: "DEMO", 1: "CONTEST", 2: "REAL"}


def variants(base):
    out = [base + s for s in ("c", "", "m", ".c", "_c", "C")]
    if base == "JP225":
        out += ["JP225c", "JPN225c", "JPN225", "JP225Cash", "JP225cash", "Nikkei225", "NIKKEIc", "NIKKEI", "JPN225Cash", "J225c", "J225"]
    if base == "BTCUSD":
        out += ["BTCUSDm", "BTCUSDT", "BTCUSDTc"]
    return list(dict.fromkeys(out))


def main():
    if not mt5.initialize(path=TERMINAL) and not mt5.initialize():
        print("initialize failed:", mt5.last_error()); return
    a = mt5.account_info()
    print(f"account {a.login} | {TRADE_MODE.get(a.trade_mode, a.trade_mode)} | server {a.server} | currency {a.currency} | "
          f"balance {a.balance:,.2f} | leverage 1:{a.leverage}")
    cent = a.currency.upper().endswith("C") or "cent" in (a.server or "").lower()
    print(f"looks like a cent account: {cent}  (currency {a.currency}) -- if this still says USD and Exness-MT5Trial7, the terminal is "
          f"still on the Standard demo and nothing below answers the cent question\n")

    names = {s.name for s in mt5.symbols_get()}
    print(f"{len(names)} symbols on this account")
    idx = sorted(n for n in names if any(k in n.upper() for k in ("225", "JPN", "NIK", "US500", "US30", "USTEC", "DE30", "DE40")))
    print(f"every index-like symbol here: {idx or 'none'}\n")

    out = []
    for base in SL_PCT:
        name = next((v for v in variants(base) if v in names), None)
        if name is None:
            print(f"{base:7s} NOT FOUND (tried {', '.join(variants(base))})")
            out.append(dict(base=base, found=False)); continue
        if not mt5.symbol_info(name).visible:
            mt5.symbol_select(name, True)
        s = mt5.symbol_info(name); t = mt5.symbol_info_tick(name)
        price = (t.ask if t and t.ask else 0) or s.ask or s.bid
        ratio = s.trade_contract_size / STANDARD[base]
        sl = price * SL_PCT[base]
        per_lot = (sl / s.trade_tick_size) * s.trade_tick_value if s.trade_tick_size else float("nan")
        risk = per_lot * s.volume_min
        pct = risk / a.balance if a.balance else float("nan")
        swap_money = s.swap_long * s.point * s.trade_contract_size if s.swap_mode == 1 else float("nan")
        bp = -swap_money / (price * s.trade_contract_size) * 1e4 if price else float("nan")
        print(f"{base:7s} -> {name}")
        print(f"   contract {s.trade_contract_size:g} = {ratio:.4g} x Standard  -> {'1/100 as assumed' if abs(ratio - 0.01) < 1e-9 else 'NOT 1/100: the 10,000 USD demo is NOT a valid model for this market'}")
        print(f"   lot min {s.volume_min:g} step {s.volume_step:g} | tick {s.trade_tick_size:g}/{s.trade_tick_value:g} | spread {s.spread} pts | swap long {s.swap_long:g} ({bp:.2f} bp/night)")
        print(f"   min lot risks {risk:,.2f} {a.currency} = {pct:.2%} of balance | at 1 % rule: {'OK' if pct <= 0.01 else 'OVER'}"
              f" | inside the 25 % brake (0.5 %): {'OK' if pct <= 0.005 else 'OVER - cannot size down this far'}")
        out.append(dict(base=base, name=name, found=True, contract=s.trade_contract_size, ratio_vs_standard=ratio, vol_min=s.volume_min,
                        vol_step=s.volume_step, tick_size=s.trade_tick_size, tick_value=s.trade_tick_value, spread_points=s.spread,
                        swap_long=s.swap_long, swap_bp_night=bp, price=price, risk_min_lot=risk, pct_of_balance=pct))
    have = [r["base"] for r in out if r.get("found")]
    print(f"\nVERDICT: this account can trade {len(have)} of the four: {have}")
    if "JP225" not in have:
        print("   JP225 is absent, so the live system is the three-market version (gold, silver, BTC): "
              "19.7 %/yr with equity DD 46.4 % in the handoff, against 25.4 % / 37.8 % for four markets")
    with open("data/g27k_cent_check.json", "w", encoding="utf-8") as f:
        json.dump(dict(checked_utc=datetime.now(timezone.utc).isoformat(), login=a.login, server=a.server,
                       account_type=TRADE_MODE.get(a.trade_mode, a.trade_mode), currency=a.currency, balance=a.balance,
                       all_index_symbols=idx, symbols=out), f, indent=1, default=str)
    print("written data/g27k_cent_check.json")
    mt5.shutdown()


if __name__ == "__main__":
    main()
