#!/usr/bin/env python3
"""The 7 x 3 x 3 matrix: risk level x spread scenario x slippage, on the real
account.

READ THIS BEFORE READING ANY NUMBER BELOW

  The configuration priced here DID NOT PASS THE DISCOVERY GATE. Nothing in
  the frozen grid did: 0 of 1,728 cells cleared all five criteria, the best
  reaching an overlap-corrected t of +2.99 against a noise floor of +3.86 with
  a bootstrap interval that still included zero. So the profit columns are NOT
  evidence of an edge and must not be read as a forecast. They are here
  because a second question is worth answering on its own terms:

      WHAT WOULD THIS ACCOUNT ACTUALLY DO?

  That question is mechanical, not statistical. Whether 0.01 lot is dealable
  at a given risk budget, how deep floating drawdown runs when positions
  overlap, how much of the risk budget lot rounding throws away, whether a
  run of ten losses ends the account - none of that depends on the edge being
  real. Those columns ARE informative and are the reason this file exists.

  Every table is labelled with what it is: BACKTEST (in-sample, the data that
  chose the configuration), STRESS (the same trades repriced at worse costs),
  or HOLDOUT (never used for selection). There is no holdout table here,
  because nothing earned the right to open it.
"""
import argparse, math, sys, pathlib, json, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import portfolio as PF
import session_rules as S
import exness_backtest as EB
from exness_cent import (ExnessCent, SPREAD_SCENARIOS, SLIPPAGE_MULTIPLES,
                         RISK_LEVELS, DD_LIMITS, slip_points)
from split_guard import Split

ACC = ExnessCent()

# the best DISCOVERY cell from the frozen grid - it FAILED the gate
CONFIG = dict(look=20, buf=0.0, stop="atr1", tp=None, hold=12, filt="london")

def broker_for(spread_pts, slip_mult, swap=False):
    """A portfolio.Broker carrying the real account's numbers.

    portfolio.py works in PRICE UNITS, the account quotes POINTS, so every
    figure is converted once, here, rather than at each use."""
    return PF.Broker(
        contract_size=ACC.contract_size,
        min_lot=ACC.min_lot, lot_step=ACC.lot_step, max_lot=ACC.max_lot,
        leverage=ACC.leverage,
        commission_per_lot_side=ACC.commission_per_lot_side,
        slippage_points=ACC.px(slip_points(spread_pts, slip_mult)),
        swap_long_per_lot_night=(ACC.swap_per_lot_night(+1) if swap else 0.0),
        swap_short_per_lot_night=(ACC.swap_per_lot_night(-1) if swap else 0.0),
        spread_mult=1.0, margin_call_frac=0.5)

def survival_after_losses(risk_frac, n_losses):
    """Equity left after n consecutive full-stop losses, compounding.

    This is the number that decides whether a risk level is usable on a real
    account, and it does not depend on the edge being real: losing streaks of
    10-20 happen to every system that has ever been traded."""
    return (1.0 - risk_frac) ** n_losses

def run_cell(W, P, msk, held, exit_px, spread_pts, slip_mult, risk_frac,
             swap=False):
    br = broker_for(spread_pts, slip_mult, swap)
    spread_arr = np.full(P["N"], ACC.px(spread_pts), float)
    return PF.from_trades(W, msk, held, P["c"], P["idx"], spread_arr,
                          exit_px=exit_px, broker=br, risk_frac=risk_frac,
                          start_equity=ACC.balance)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("EXNESS CENT ACCOUNT - RISK x SPREAD x SLIPPAGE MATRIX")
    print("=" * 88)
    print(__doc__.split("READ THIS")[1].split('"""')[0].replace(
        "  BEFORE READING ANY NUMBER BELOW\n", "READ THIS BEFORE READING ANY NUMBER BELOW\n"))

    m = M.load_tf(a.tf)
    P = M.prep(m)
    tf_min = S.bar_minutes(m.index)
    deadline, _, _ = S.intraday_deadlines(m.index, tf_min)
    n_disc = int((m.index < pd.Timestamp(EB.DISCOVERY_END, tz="UTC")).sum())
    split = Split(m.index, EB.DISCOVERY_END)
    th = M.fit_thresholds(P, split)
    tps_real = [t for t in M.TPS if t is not None]
    tp_j = None if CONFIG["tp"] is None else tps_real.index(CONFIG["tp"])

    print(f"CONFIGURATION PRICED (best discovery cell; it FAILED the gate): "
          f"look{CONFIG['look']} buf{CONFIG['buf']} {CONFIG['stop']} "
          f"tp{CONFIG['tp']} hold{CONFIG['hold']} {CONFIG['filt']}")
    print(f"PERIOD: DISCOVERY only (2004-01-01 .. {EB.DISCOVERY_END}) - this is "
          f"IN-SAMPLE, the data that chose the configuration\n")

    # ---- minimum-lot feasibility, which is pure arithmetic ---------------
    print("1. CAN THE ACCOUNT EVEN DEAL IT?  (mechanical - no edge assumed)")
    print("   0.01 lot is the smallest deal. With contract size 100, a stop D")
    print("   price units away risks D x 100 x 0.01 = D USC at minimum lot.")
    sel_cost = EB.scenario_cost_px(SPREAD_SCENARIOS["normal"], 0.0)
    W = EB.walk_for(P, CONFIG["look"], CONFIG["buf"], CONFIG["stop"],
                    sel_cost, CONFIG["hold"])
    F = M.build_filters(P, W, th)
    Rd, held, keep, rep, xpx = EB.resolve_window(W, P, tp_j, CONFIG["hold"],
                                                 0, n_disc, deadline)
    msk = keep & F[CONFIG["filt"]]
    risks_px = W["risk"][msk]
    print(f"   stop distance over {int(msk.sum()):,} discovery trades: "
          f"median {np.median(risks_px):.2f} price units, "
          f"p10 {np.percentile(risks_px,10):.2f}, p90 {np.percentile(risks_px,90):.2f}")
    print(f"   {'risk %':>8}{'budget USC':>12}{'median lots wanted':>20}"
          f"{'dealable?':>12}   note")
    for rf in RISK_LEVELS:
        budget = ACC.balance * rf
        want = budget / (np.median(risks_px) * ACC.contract_size)
        need_px = budget / (ACC.contract_size * ACC.min_lot)
        frac_dealable = float((risks_px <= need_px).mean())
        print(f"   {rf*100:>7.1f}%{budget:>12.2f}{want:>20.4f}"
              f"{frac_dealable*100:>11.0f}%   "
              f"{'below min lot on most trades' if frac_dealable < 0.5 else 'ok'}")
    print(f"   -> a trade is dealable only if its stop is under "
          f"{ACC.balance*0.01/(ACC.contract_size*ACC.min_lot):.2f} price units "
          f"at 1% risk; the median stop here is {np.median(risks_px):.2f}")

    # ---- survival under losing streaks -----------------------------------
    print("\n2. SURVIVAL UNDER A LOSING STREAK (mechanical - no edge assumed)")
    print(f"   {'risk %':>8}{'after 10 losses':>18}{'after 15':>12}{'after 20':>12}"
          f"{'verdict':>28}")
    for rf in RISK_LEVELS:
        s10, s15, s20 = (survival_after_losses(rf, n) for n in (10, 15, 20))
        dd20 = 1 - s20
        if dd20 <= 0.20: v = "survivable"
        elif dd20 <= 0.35: v = "painful but survivable"
        elif dd20 <= 0.70: v = "at the edge of the 70% limit"
        else: v = "ACCOUNT EFFECTIVELY GONE"
        print(f"   {rf*100:>7.1f}%{(1-s10)*100:>17.1f}%{(1-s15)*100:>11.1f}%"
              f"{(1-s20)*100:>11.1f}%{v:>28}")

    # ---- the matrix -------------------------------------------------------
    print("\n3. THE MATRIX - BACKTEST at 260 pts, STRESS at 400/600 and with "
          "slippage")
    print("   (profit columns are NOT evidence: this configuration failed the "
          "discovery gate)")
    rows = []
    hdr = (f"   {'spread':>7}{'slip':>6}{'risk':>7}{'trades':>8}{'net USC':>10}"
           f"{'CAGR':>8}{'netR':>8}{'avgR':>8}{'win%':>7}{'PF':>7}"
           f"{'floatDD':>9}{'closeDD':>9}{'streak':>7}{'rej':>6}{'blown':>7}")
    print(hdr)
    for sname, spts in SPREAD_SCENARIOS.items():
        cost_px = EB.scenario_cost_px(spts, 0.0)
        Wx = EB.walk_for(P, CONFIG["look"], CONFIG["buf"], CONFIG["stop"],
                         cost_px, CONFIG["hold"])
        Fx = M.build_filters(P, Wx, th)
        for smult in SLIPPAGE_MULTIPLES:
            c_full = EB.scenario_cost_px(spts, smult)
            Wc = EB.walk_for(P, CONFIG["look"], CONFIG["buf"], CONFIG["stop"],
                             c_full, CONFIG["hold"])
            Fc = M.build_filters(P, Wc, th)
            Rc, heldc, keepc, _, xpc = EB.resolve_window(Wc, P, tp_j,
                                                         CONFIG["hold"], 0,
                                                         n_disc, deadline)
            mc = keepc & Fc[CONFIG["filt"]]
            r_units = Rc[mc]
            n_bad, n_tot = EB.cost_over_third_R(Wc, mc, c_full)
            for rf in RISK_LEVELS:
                res = run_cell(Wc, P, mc, heldc, xpc, spts, smult, rf)
                st = EB.trade_stats(res, r_units)
                eps = EB.dd_episodes(res["equity"], DD_LIMITS)
                rows.append(dict(
                    spread_pts=spts, slip_mult=smult, risk=rf,
                    offered=int(mc.sum()), taken=res["n_taken"],
                    net=res["net_pl"], cagr=res["cagr"],
                    netR=st["net_R"], avgR=st["avg_net_R"],
                    win=st["win_rate"], pf=st["profit_factor"],
                    ddf=res["dd_floating"], ddc=res["dd_closed"],
                    streak=st["longest_losing_streak"],
                    up_days=st["up_days"], down_days=st["down_days"],
                    rej_minlot=res["rejected"]["min_lot"],
                    rej_margin=res["rejected"]["margin"],
                    maxconc=res["max_concurrent"],
                    maxrisk=res["max_open_risk_frac"],
                    margin_call=res["margin_call_bar"] is not None,
                    blown=bool(res["blown"]),
                    cost_over_third=n_bad,
                    **{f"dd_ep_{int(l*100)}": eps[l] for l in DD_LIMITS}))
                rr = rows[-1]
                print(f"   {spts:>7.0f}{smult:>6.1f}{rf*100:>6.1f}%"
                      f"{res['n_taken']:>8}{res['net_pl']:>10.1f}"
                      f"{(rr['cagr']*100 if np.isfinite(rr['cagr']) else float('nan')):>7.1f}%"
                      f"{st['net_R']:>8.1f}"
                      f"{(st['avg_net_R'] if np.isfinite(st['avg_net_R']) else float('nan')):>8.3f}"
                      f"{st['win_rate']*100:>6.1f}%"
                      f"{(st['profit_factor'] if np.isfinite(st['profit_factor']) else 0):>7.2f}"
                      f"{res['dd_floating']*100:>8.1f}%{res['dd_closed']*100:>8.1f}%"
                      f"{st['longest_losing_streak']:>7}"
                      f"{res['rejected']['min_lot']:>6}"
                      f"{('YES' if res['blown'] else '-'):>7}")
    df = pd.DataFrame(rows)
    if a.csv:
        df.to_csv(a.csv, index=False)
        print(f"\n   full matrix ({len(df)} cells) -> {a.csv}")
    print(f"\n   elapsed {time.time()-t0:.0f}s")
    return df

if __name__ == "__main__":
    main()
