#!/usr/bin/env python3
"""Many rare strict setups pooled into one book - the frequency argument, tested.

THE PROPOSAL, STATED FAIRLY

  "One strict setup fires once a month, which is too rare to measure. Fine -
  don't loosen it. Build a HUNDRED equally strict setups. Each is still rare,
  but a hundred of them is seventy signals a month, and that is tradeable. It
  will be overfit, obviously. But the result might still be positive."

  The frequency half of this is simply CORRECT, and `setup_power.py` answered
  the wrong question by treating one setup in isolation. Breadth genuinely
  does solve frequency: n is additive across setups, so a hundred rare rules
  reach a measurable sample where one never could. Every real systematic book
  is built this way - many weak, weakly-correlated signals - and dismissing it
  would be dismissing the one structure that is known to work.

  The trap is not in the breadth. It is in the word SURVIVE.

WHAT "THE HUNDRED THAT SURVIVED" ACTUALLY SELECTS

  To end up with a hundred survivors you must test many more than a hundred
  and keep the ones that looked good. With a dozen trades a year per setup the
  standard error on each is enormous, so "looked good" is very nearly a coin
  flip. Selecting the positive half of a pile of coin flips produces a pile of
  positive-looking coin flips, and pooling them produces a portfolio whose
  BACKTEST is strongly positive and whose TRUE edge is exactly zero.

  That is not a caveat about the method, it is a description of the method.
  Part 1 puts a number on it by running the exact procedure on data that is
  KNOWN to contain no edge whatsoever, so the entire measured result is the
  selection and nothing else.

  Part 2 then runs the real thing on real gold, and the two parts are meant to
  be read together: Part 1 says what a null result looks like under this
  procedure, and Part 2 says whether gold does anything more than that.

THE TEST THAT SEPARATES THEM

  Selection on one period, measurement on another. A portfolio whose edge is
  selection collapses to zero on data it was not selected on; a portfolio with
  an edge keeps it. Nothing else distinguishes the two cases, and no amount of
  in-sample evidence can - which is why the in-sample number is reported here
  only next to its out-of-sample twin, never alone.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
import exness_backtest as EB
import multi_tf_setup_grid as G

SEED = 17


# --------------------------------------------------------------- part 1 ---
def selection_null(k_tested, n_per_setup, sigma, keep_rule, rng):
    """Run the proposed procedure on data with NO edge, twice.

    Every setup here has a true expectancy of exactly zero. The first draw is
    the selection period, the second is fresh data for the same setups. Any
    difference between the two is the selection and nothing else, because
    there is nothing else in the data to find."""
    sel = rng.normal(0.0, sigma, size=(k_tested, n_per_setup))
    fresh = rng.normal(0.0, sigma, size=(k_tested, n_per_setup))
    m_sel = sel.mean(axis=1)
    se = sigma / math.sqrt(n_per_setup)
    t_sel = m_sel / se
    keep = keep_rule(m_sel, t_sel)
    if keep.sum() == 0:
        return None
    return dict(
        tested=k_tested, kept=int(keep.sum()),
        e_selection=float(sel[keep].mean()),
        e_fresh=float(fresh[keep].mean()),
        t_fresh=float(fresh[keep].mean() /
                      (fresh[keep].std(ddof=1) / math.sqrt(fresh[keep].size))),
    )


def part1(sigma, n_per_setup, trials=200):
    print("=" * 84)
    print("PART 1 - THE SAME PROCEDURE ON DATA WITH NO EDGE AT ALL")
    print("=" * 84)
    print(f"  Every setup below has a TRUE expectancy of exactly 0.000R by")
    print(f"  construction. sigma = {sigma:.2f}R per trade, "
          f"{n_per_setup} trades per setup.")
    print(f"  Whatever the table shows is therefore the selection, because")
    print(f"  there is nothing else in the numbers to find.\n")
    rules = (
        ("keep E(R) > 0", lambda m, t: m > 0),
        ("keep t > 1", lambda m, t: t > 1),
        ("keep t > 2", lambda m, t: t > 2),
    )
    print(f"  {'selection rule':<18}{'tested':>8}{'kept':>7}"
          f"{'E on selection':>16}{'E on fresh data':>17}{'t fresh':>9}")
    rng = np.random.default_rng(SEED)
    for name, rule in rules:
        for k_tested in (200, 1000):
            acc = [selection_null(k_tested, n_per_setup, sigma, rule, rng)
                   for _ in range(trials)]
            acc = [x for x in acc if x]
            if not acc:
                continue
            kept = np.mean([x["kept"] for x in acc])
            esel = np.mean([x["e_selection"] for x in acc])
            efre = np.mean([x["e_fresh"] for x in acc])
            tfre = np.mean([x["t_fresh"] for x in acc])
            print(f"  {name:<18}{k_tested:>8}{kept:>7.0f}{esel:>+16.4f}"
                  f"{efre:>+17.4f}{tfre:>+9.2f}")
    print(f"\n  Read the last two columns against each other. The selection")
    print(f"  column is reliably, sometimes strongly positive. The fresh-data")
    print(f"  column is zero, every time, because zero is the truth and fresh")
    print(f"  data is the only thing that reports it.")
    print(f"\n  'It will be overfit but the result might be positive' is "
          f"therefore\n  exactly right, and the positive result is the overfit. "
          f"The two are\n  not separate outcomes to weigh against each other - "
          f"they are one\n  outcome under two names.")


# --------------------------------------------------------------- part 2 ---
def build_cells(P, hold, spread, lo, hi):
    """Every entry x exit x stop in the existing grid, over bars [lo, hi).

    The grid is taken WHOLE. Nothing is dropped for looking unpromising,
    because dropping those is the selection this file exists to measure."""
    out = []
    for ename, (fn, grid) in G.ENTRIES.items():
        for gp in grid:
            try:
                sig = fn(P, **gp)
            except Exception:
                continue
            s = sig.copy()
            s[:lo] = 0
            s[hi:] = 0
            if int((s != 0).sum()) < 40:
                continue
            ps = ",".join(f"{k}={v}" for k, v in gp.items()) or "-"
            for xname, dz in G.EXITS.items():
                for rm in G.RMULTS:
                    r = G.book(P, s, dz, hold, rm, spread)
                    if len(r) < 30:
                        continue
                    a = np.asarray(r, float)
                    out.append(dict(entry=ename, params=ps, exit=xname, rm=rm,
                                    n=len(a), E=float(a.mean()),
                                    sd=float(a.std(ddof=1))))
    return pd.DataFrame(out)


def book_detail(P, sig, design, hold, rmult, spread):
    """G.book, but keeping WHEN each trade happened.

    The bar index is what makes a portfolio-level test possible. Without it
    every cell looks like an independent sample, and 28 cells trading the same
    gold on the same bars is emphatically not 28 independent samples."""
    c, A, N = P["c"], P["A"], P["N"]
    live = [i for i in range(320, N - 1)
            if sig[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
    if len(live) < 30:
        return None
    out_r, out_i, out_h = [], [], []
    busy = -1
    for i in live:
        if i <= busy:
            continue
        risk = rmult * A[i]
        if risk <= 0:
            continue
        r, kx = G.exit_run(P, i, c[i], int(sig[i]), risk, design, hold, spread)
        if r is None:
            continue
        out_r.append(r); out_i.append(i); out_h.append(max(kx - i, 1))
        busy = kx
    if len(out_r) < 30:
        return None
    return (np.asarray(out_r, float), np.asarray(out_i, float),
            np.asarray(out_h, float))


def shuffled_sig(sig, lo, hi, rng):
    """The same signals, the same directions, on randomly chosen bars.

    Direction mix is preserved exactly, so a book that earns only because gold
    rose over the period earns the same here. What is destroyed is any relation
    between the signal and WHEN it fired - which is the entire claim an entry
    rule makes."""
    s = np.zeros_like(sig)
    live = np.where(sig[lo:hi] != 0)[0] + lo
    if len(live) == 0:
        return s
    dirs = sig[live].copy()
    pool = np.arange(lo + 320, hi - 1)
    if len(pool) < len(live):
        return s
    pick = rng.choice(pool, size=len(live), replace=False)
    s[pick] = dirs
    return s


def pooled_book(P, cells, hold, spread, lo, hi, rng=None):
    """Every selected cell's trades merged into ONE book, in time order.

    This is the portfolio the proposal actually describes - all the surviving
    setups traded together - and it is the only object whose statistics mean
    what they appear to mean. With `rng` set, the same cells fire on random
    bars instead, which is the matched control."""
    R, I, HD = [], [], []
    for _, x in cells.iterrows():
        fn, _ = G.ENTRIES[x["entry_d"]]
        gp = {} if x["params_d"] == "-" else dict(
            (k, float(v) if "." in v else int(v))
            for k, v in (p.split("=") for p in x["params_d"].split(",")))
        try:
            sig = fn(P, **gp)
        except Exception:
            continue
        s = sig.copy(); s[:lo] = 0; s[hi:] = 0
        if rng is not None:
            s = shuffled_sig(s, lo, hi, rng)
        b = book_detail(P, s, G.EXITS[x["exit_d"]], hold, x["rm_d"], spread)
        if b is None:
            continue
        R.append(b[0]); I.append(b[1]); HD.append(b[2])
    if not R:
        return None
    R = np.concatenate(R); I = np.concatenate(I); HD = np.concatenate(HD)
    o = np.argsort(I)
    return R[o], I[o], HD[o]


def key(d):
    return (d["entry"], d["params"], d["exit"], d["rm"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--hold", type=int, default=48)
    ap.add_argument("--sigma", type=float, default=None)
    ap.add_argument("--skip-part1", action="store_true")
    a = ap.parse_args()
    t0 = time.time()

    print("A PORTFOLIO OF RARE SETUPS - the frequency argument, tested")
    print("=" * 84)
    print(__doc__.split("THE PROPOSAL, STATED FAIRLY")[1]
          .split("THE TEST THAT SEPARATES THEM")[0])

    m = M.load_tf(a.tf)
    P0 = M.prep(m)
    spread = float(EB.scenario_cost_px(260.0, 0.0) / np.nanmedian(P0["c"]))
    disc_end = EB.DISCOVERY_END if S.bar_minutes(m.index) >= 60 \
        else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    Pg = G.prep(pd.DataFrame(
        dict(open=P0["o"], high=P0["h"], low=P0["l"], close=P0["c"]),
        index=m.index))

    yrs_d = (m.index[n_disc - 1] - m.index[0]).days / 365.25
    yrs_h = (m.index[-1] - m.index[n_disc]).days / 365.25
    print(f"data      {a.tf}  {len(m):,} bars  {m.index[0].date()} -> "
          f"{m.index[-1].date()}")
    print(f"split     discovery {n_disc:,} bars ({yrs_d:.1f}y)   "
          f"holdout {len(m)-n_disc:,} bars ({yrs_h:.1f}y)")
    print(f"cost      260 points charged on every leg of every cell")

    print(f"\nbuilding every cell on DISCOVERY ...", flush=True)
    D = build_cells(Pg, a.hold, spread, 0, n_disc)
    print(f"  {len(D)} cells cleared the 30-trade floor")
    print(f"building the SAME cells on HOLDOUT ...", flush=True)
    H = build_cells(Pg, a.hold, spread, n_disc, len(m))
    print(f"  {len(H)} cells")

    if len(D) == 0 or len(H) == 0:
        print("\n  not enough cells to run the comparison")
        return

    D["k"] = D.apply(key, axis=1)
    H["k"] = H.apply(key, axis=1)
    J = D.merge(H, on="k", suffixes=("_d", "_h"))
    print(f"  {len(J)} cells present in both periods\n")

    sigma = a.sigma if a.sigma else float(D["sd"].median())

    if not a.skip_part1:
        n_typ = int(D["n"].median())
        part1(sigma, max(n_typ, 10))

    # ---- the real thing ---------------------------------------------------
    print("\n" + "=" * 84)
    print("PART 2 - THE SAME PROCEDURE ON REAL GOLD")
    print("=" * 84)
    print(f"  Cells are selected on DISCOVERY only, then the SAME cells are")
    print(f"  measured on HOLDOUT. The holdout column is the only one that is")
    print(f"  evidence of anything.\n")

    dsel, hsel = J["E_d"].to_numpy(), J["E_h"].to_numpy()
    td = dsel / (J["sd_d"].to_numpy() / np.sqrt(J["n_d"].to_numpy()))
    rules = (
        ("everything, no selection", np.ones(len(J), bool)),
        ("keep E(R) > 0", dsel > 0),
        ("keep t > 1", td > 1),
        ("keep t > 2", td > 2),
        ("keep the best 25%", dsel >= np.quantile(dsel, 0.75)),
        ("keep the best 10", np.isin(np.arange(len(J)),
                                     np.argsort(-dsel)[:10])),
    )
    print(f"  {'selection rule':<26}{'kept':>6}{'E disc':>10}{'E hold':>10}"
          f"{'trades/yr':>11}{'hold t':>9}")
    for name, sel in rules:
        if sel.sum() == 0:
            print(f"  {name:<26}{0:>6}")
            continue
        ed = float(dsel[sel].mean())
        eh = float(hsel[sel].mean())
        nh = J["n_h"].to_numpy()[sel]
        # Pool the holdout books by weighting each cell by its own trade count,
        # which is what actually trading all of them would produce.
        w = nh / nh.sum()
        eh_w = float((hsel[sel] * w).sum())
        sd_h = J["sd_h"].to_numpy()[sel]
        se = math.sqrt(float((w ** 2 * sd_h ** 2 / np.maximum(nh, 1)).sum()))
        th = eh_w / se if se > 0 else float("nan")
        print(f"  {name:<26}{int(sel.sum()):>6}{ed:>+10.4f}{eh_w:>+10.4f}"
              f"{nh.sum()/yrs_h:>11,.0f}{th:>+9.2f}")

    # ---- the frequency claim, measured ------------------------------------
    print(f"\nTHE FREQUENCY CLAIM, MEASURED")
    pos = dsel > 0
    if pos.sum():
        per_cell = J["n_h"].to_numpy()[pos] / yrs_h
        print(f"  cells kept by 'E(R) > 0 on discovery': {int(pos.sum())}")
        print(f"  median cell fires {np.median(per_cell):.1f} times a year "
              f"= {np.median(per_cell)/12:.1f} a month")
        print(f"  all of them together: {per_cell.sum():,.0f} a year "
              f"= {per_cell.sum()/12:,.0f} a month")
        print(f"  -> the breadth argument WORKS. {int(pos.sum())} rare cells do")
        print(f"     reach a tradeable frequency, exactly as proposed. The")
        print(f"     frequency was never the thing that fails.")

    # ---- what strict selection is actually picking ------------------------
    # The grid's own docstring warns that the EXIT carries a structural return
    # of its own, larger on random entries than any entry rule in this repo has
    # produced. So if strict selection quietly concentrates on one exit design,
    # a positive holdout is that exit's return and has nothing to do with the
    # entries - and it would be available without any selection at all.
    print(f"\nWHAT STRICT SELECTION IS ACTUALLY PICKING")
    strict = td > 2
    if strict.sum():
        print(f"  {int(strict.sum())} cells kept by t > 2. Their composition "
              f"against the whole grid:\n")
        for col, lab in (("exit_d", "exit design"), ("entry_d", "entry family")):
            a_ = J[strict][col].value_counts()
            b_ = J[col].value_counts()
            print(f"  {lab:<16}{'kept':>6}{'in grid':>9}{'kept share':>12}"
                  f"{'grid share':>12}")
            for nm in b_.index:
                kc = int(a_.get(nm, 0))
                print(f"    {nm:<14}{kc:>6}{int(b_[nm]):>9}"
                      f"{kc/strict.sum()*100:>11.1f}%"
                      f"{int(b_[nm])/len(J)*100:>11.1f}%")
            print()

    # ---- part 3: the t above is wrong, and here is the right one ----------
    # The holdout t printed above weights each cell by its trade count and adds
    # their variances as if the cells were independent samples. They are not.
    # Twenty-eight cells trading the same gold on the same bars share most of
    # their information, so that SE is far too small and its t far too large.
    # This is the exact error - overlapping samples read as independent ones -
    # that killed every previous candidate in this project, and it does not
    # stop being the error when the result is one I would like to keep.
    #
    # The fix is to build the ACTUAL portfolio: every selected cell's trades in
    # one book, in time order, block-bootstrapped over TIME so that trades on
    # nearby bars resample together and the cross-cell correlation is carried
    # rather than assumed away.
    print("\n" + "=" * 84)
    print("PART 3 - THE PORTFOLIO t, WITH CROSS-CELL OVERLAP CARRIED")
    print("=" * 84)
    print("  The holdout t in Part 2 adds 28 cells' variances as if they were")
    print("  28 independent samples. They trade the same gold on the same bars.")
    print("  This rebuilds the real pooled book and block-bootstraps over time.\n")
    print(f"  {'selection rule':<26}{'cells':>6}{'trades':>9}{'E hold':>10}"
          f"{'naive t':>9}{'block t':>9}{'95% CI':>20}")
    for name, sel in rules:
        if sel.sum() == 0 or name == "everything, no selection":
            continue
        pb = pooled_book(Pg, J[sel], a.hold, spread, n_disc, len(m))
        if pb is None:
            continue
        R, I, HD = pb
        nh = J["n_h"].to_numpy()[sel]
        w = nh / nh.sum()
        sd_h = J["sd_h"].to_numpy()[sel]
        se_naive = math.sqrt(float((w ** 2 * sd_h ** 2 / np.maximum(nh, 1)).sum()))
        t_naive = float((hsel[sel] * w).sum()) / se_naive if se_naive > 0 else float("nan")
        bt = M.block_bootstrap_t(R, I, HD, 1)
        ci = M.block_bootstrap_ci(R, I, HD)
        cis = f"[{ci[0]:+.4f}, {ci[1]:+.4f}]" if ci is not None else "-"
        print(f"  {name:<26}{int(sel.sum()):>6}{len(R):>9,}{R.mean():>+10.4f}"
              f"{t_naive:>+9.2f}{bt:>+9.2f}{cis:>20}")

    # ---- part 4: is any of it the ENTRY, or is it drift plus the exit? ----
    # Donchian breakout is 57% of the strict selection and 14% of the grid, on
    # an asset that rose for twenty-two years. "Trend-following does well in a
    # trending market" persists from discovery to holdout without any entry
    # skill being involved, and would produce exactly the pattern seen above.
    # The control fires the SAME cells with the SAME direction mix on RANDOM
    # bars: it keeps the drift and the exit design and destroys only the timing.
    print("\n" + "=" * 84)
    print("PART 4 - IS IT THE ENTRY, OR IS IT DRIFT PLUS THE EXIT?")
    print("=" * 84)
    print("  Same cells, same direction mix, random bars. Everything the entry")
    print("  does NOT claim is preserved; only its timing is destroyed.\n")
    print(f"  {'selection rule':<26}{'real':>10}{'control':>10}{'skill':>10}"
          f"{'block t':>9}")
    rng = np.random.default_rng(SEED)
    for name, sel in rules:
        if sel.sum() == 0 or name == "everything, no selection":
            continue
        pb = pooled_book(Pg, J[sel], a.hold, spread, n_disc, len(m))
        if pb is None:
            continue
        R, I, HD = pb
        cr, ci_, chd = [], [], []
        for _ in range(3):
            cb = pooled_book(Pg, J[sel], a.hold, spread, n_disc, len(m), rng)
            if cb is None:
                continue
            cr.append(cb[0]); ci_.append(cb[1]); chd.append(cb[2])
        if not cr:
            continue
        C = np.concatenate(cr)
        skill = float(R.mean() - C.mean())
        # The skill's own t, block-bootstrapped on the real book and compared
        # against the control mean as a fixed offset.
        bt = M.block_bootstrap_t(R - C.mean(), I, HD, 1)
        print(f"  {name:<26}{R.mean():>+10.4f}{C.mean():>+10.4f}"
              f"{skill:>+10.4f}{bt:>+9.2f}")
    print(f"\n  If the control column is close to the real column, the entries")
    print(f"  are contributing nothing and the book is the exit design plus")
    print(f"  twenty-two years of gold going up.")

    k_rules = len(rules)
    floor = math.sqrt(2 * math.log(k_rules))
    print(f"\n  Six selection rules were tried, so the floor a surviving rule")
    print(f"  must clear is sqrt(2 ln {k_rules}) = {floor:.2f}, not 1.96. That")
    print(f"  count is small only because the GRID was frozen beforehand - the")
    print(f"  176 cells were not chosen, they are the whole of an existing file.")
    print(f"\n  Compare the naive and block columns. The gap between them is the")
    print(f"  cross-cell overlap, and it is the single thing most likely to")
    print(f"  turn a portfolio result into an artefact.")

    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
