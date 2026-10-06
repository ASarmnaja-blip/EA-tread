#!/usr/bin/env python3
"""A dollar index built from the FX majors, tested as a PREDICTOR of gold.

WHY THIS IS DIFFERENT FROM EVERYTHING TRIED SO FAR

  Every test in this repo has asked gold's own price history to predict
  gold's future. That is the most competed-over information in the market:
  thousands of funds run the same regressions on the same bars with better
  data and a tenth of the cost. Repeated failure there is the expected
  result, not a surprise.

  A dollar index is DIFFERENT INFORMATION. Gold is quoted in dollars, so a
  large part of what looks like "gold moving" is the denominator moving. The
  six currencies in the DXY basket are separate markets with separate
  participants, and what happens in them is not contained in XAUUSD's own
  bars. That makes this the first genuinely new input this project has had.

  It is also the honest reading of why gold rallied 2004-2026: a good part of
  that is the dollar, not the metal.

THE INDEX

  ICE's DXY formula, weights and all:

      DXY = 50.14348112
            x EURUSD^-0.576  x USDJPY^+0.136  x GBPUSD^-0.119
            x USDCAD^+0.091  x USDSEK^+0.042  x USDCHF^+0.036

  Built from this repo's own Dukascopy bars rather than downloaded, so it is
  on exactly the same clock as the gold series and needs no alignment
  guesswork. The constant is chosen so the index reads 100 at its 1973 base;
  it is irrelevant to anything measured here, since only RETURNS are used,
  but it is kept so the numbers are recognisable.

THE ONE DISTINCTION THAT DECIDES WHETHER ANY OF THIS IS TRADEABLE

  Gold and the dollar move together CONTEMPORANEOUSLY - that correlation is
  large, well known, and worth nothing. You cannot trade on information that
  arrives at the same instant as the move it explains.

  The only question that pays is LEAD-LAG: does the dollar at time t tell you
  anything about gold from t to t+h? Both are measured below and reported
  side by side, because the contemporaneous number is the one that looks
  impressive and the forward one is the one that matters. Confusing them is
  the single most common way a cross-asset "signal" turns out to be nothing.

THE HYPOTHESES, DECLARED BEFORE THE RUN

    1  dollar momentum      DXY return over the past k bars -> gold forward
    2  dollar stretch       DXY distance from its own moving average -> gold
                            forward
    3  divergence           gold and the dollar moving the SAME way, which is
                            unusual, as a signal that one of them corrects

  Each at k in {4, 24} lookback and h in {1, 4, 12} forward, on discovery
  data only:

      k = 3 hypotheses x 2 lookbacks x 3 horizons = 18
      noise floor = sqrt(2 ln 18) = 2.40

  Detection needs the block-bootstrap CI clear of zero AND |t| above that
  floor. Tradeability needs the effect to also exceed the round-trip cost in
  the same units, which detection alone does not imply.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import mega_search as M

DISCOVERY_END = "2017-01-01"
LOOKBACKS = (4, 24)
HORIZONS = (1, 4, 12)

# ICE DXY: symbol -> exponent. A negative exponent means the pair is quoted
# XXX/USD, so the dollar strengthening pushes it DOWN.
DXY_LEGS = {"EURUSD": -0.576, "USDJPY": +0.136, "GBPUSD": -0.119,
            "USDCAD": +0.091, "USDSEK": +0.042, "USDCHF": +0.036}
DXY_CONST = 50.14348112

def load_leg(sym):
    return D.clean(D.mid(D.load_h1(2003, 2026, symbol=sym)))

def build_dxy(verbose=True):
    """The index on the gold series' own clock. Bars present in every leg are
    the only ones used - a synthetic index with a missing leg is not an index,
    it is a different index on that bar."""
    legs = {}
    for sym in DXY_LEGS:
        try:
            legs[sym] = load_leg(sym).close
        except Exception as e:
            if verbose:
                print(f"  {sym}: unavailable ({type(e).__name__}) - cannot "
                      f"build the index without it")
            return None
    df = pd.DataFrame(legs).dropna()
    dxy = DXY_CONST * np.prod(
        [df[s].to_numpy() ** w for s, w in DXY_LEGS.items()], axis=0)
    out = pd.Series(dxy, index=df.index, name="dxy")
    if verbose:
        print(f"  DXY built from {len(DXY_LEGS)} legs, {len(out):,} bars "
              f"{out.index[0].date()} -> {out.index[-1].date()}")
        print(f"  level: min {out.min():.1f}  median {out.median():.1f}  "
              f"max {out.max():.1f}  (a sane DXY sits roughly 70-115)")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("DOLLAR INDEX AS A PREDICTOR OF GOLD")
    print("=" * 84)
    print(__doc__.split("THE ONE DISTINCTION")[1].split("THE HYPOTHESES")[0])

    dxy = build_dxy()
    if dxy is None:
        print("\n  cannot proceed without the full basket")
        return

    gold = M.load_tf("1h")
    P = M.prep(gold)
    both = gold.index.intersection(dxy.index)
    g = gold.close.reindex(both).to_numpy()
    A = pd.Series(P["A"], index=gold.index).reindex(both).to_numpy()
    x = dxy.reindex(both).to_numpy()
    n_disc = int((both < pd.Timestamp(DISCOVERY_END, tz="UTC")).sum())
    print(f"\n  aligned bars {len(both):,}, discovery {n_disc:,} "
          f"({both[0].date()} -> {both[n_disc-1].date()})")

    g, A, x = g[:n_disc], A[:n_disc], x[:n_disc]
    n = len(g)
    k_total = 3 * len(LOOKBACKS) * len(HORIZONS)
    bar = math.sqrt(2 * math.log(k_total))
    print(f"  hypotheses {k_total}, noise floor |t| > {bar:.2f}")

    # -- the contemporaneous relationship, for contrast only ---------------
    print(f"\nCONTEMPORANEOUS (impressive, and worth nothing)")
    for k in LOOKBACKS:
        gr = np.full(n, np.nan); gr[k:] = (g[k:] - g[:-k]) / np.maximum(A[k:], 1e-9)
        dr = np.full(n, np.nan); dr[k:] = (x[k:] - x[:-k]) / x[:-k]
        ok = np.isfinite(gr) & np.isfinite(dr)
        c = np.corrcoef(gr[ok], dr[ok])[0, 1]
        print(f"  {k:>3}-bar gold return vs same-window dollar return: "
              f"corr {c:+.3f}")
    print("  -> a strong negative number here is the dollar being the "
          "denominator,\n     not a forecast. It arrives at the same instant "
          "as the move.")

    # -- the forward relationship, which is the only one that pays ---------
    print(f"\nFORWARD (the only one that can be traded)")
    print(f"  {'hypothesis':<22}{'k':>3}{'h':>4}{'n':>8}{'effect':>11}"
          f"{'t':>8}{'t_indep':>9}{'CI low':>10}  verdict")
    rows = []
    for k in LOOKBACKS:
        dr = np.full(n, np.nan); dr[k:] = (x[k:] - x[:-k]) / x[:-k]
        ma = pd.Series(x).rolling(k * 5).mean().to_numpy()
        stretch = (x - ma) / np.maximum(ma, 1e-9)
        gr_back = np.full(n, np.nan)
        gr_back[k:] = (g[k:] - g[:-k]) / np.maximum(A[k:], 1e-9)
        for h in HORIZONS:
            fwd = np.full(n, np.nan)
            fwd[:n - h] = (g[h:] - g[:n - h]) / np.maximum(A[:n - h], 1e-9)
            # 1 dollar momentum: short the dollar's direction into gold
            sig1 = -np.sign(dr)
            # 2 dollar stretch: fade a stretched dollar
            sig2 = -np.sign(stretch)
            # 3 divergence: gold and the dollar moving the same way
            sig3 = np.where(np.sign(gr_back) == np.sign(dr), -np.sign(dr), 0.0)
            for nm, sig in (("dollar_momentum", sig1), ("dollar_stretch", sig2),
                            ("divergence", sig3)):
                ok = np.isfinite(fwd) & np.isfinite(sig) & (sig != 0)
                if ok.sum() < 500:
                    continue
                r = fwd[ok] * sig[ok]
                where = np.where(ok)[0].astype(float)
                held = np.full(len(r), float(h))
                t = M.block_bootstrap_t(r, where, held, 1)
                ci = M.block_bootstrap_ci(r, where, held)
                lo, hi = ci if ci is not None else (np.nan, np.nan)
                det = (ci is not None and (lo > 0 or hi < 0)
                       and np.isfinite(t) and abs(t) > bar)
                cost_atr = 0.260 / float(np.nanmedian(A))
                trade = det and abs(r.mean()) > cost_atr
                # THE OVERLAP TRAP, CHECKED AUTOMATICALLY.
                # Consecutive bars share almost all of their forward window,
                # so n is not the number of independent observations. Every
                # candidate in this project that looked significant and then
                # died - the M15 calendar effects, the Friday effect on M15 -
                # died exactly here. The block bootstrap already widens the
                # interval for overlap and it is still not enough, so the
                # decisive test is re-run on a thinned sample taking every
                # h-th bar, which is genuinely non-overlapping.
                t_min = float("nan")
                t_ind = []
                for off in range(min(3, h)):
                    thin = np.zeros(n, bool); thin[off::h] = True
                    s = thin & ok
                    if s.sum() < 200: continue
                    rr = fwd[s] * sig[s]
                    ww = np.where(s)[0].astype(float)
                    t_ind.append(M.block_bootstrap_t(
                        rr, ww, np.full(len(rr), float(h)), 1))
                t_min = min(t_ind) if t_ind else float("nan")
                survives = det and np.isfinite(t_min) and abs(t_min) > bar
                rows.append(dict(hypothesis=nm, k=k, h=h, n=int(ok.sum()),
                                 effect=float(r.mean()), t=float(t),
                                 ci_lo=float(lo), ci_hi=float(hi),
                                 t_independent=float(t_min),
                                 detected=bool(det),
                                 tradeable=bool(trade and survives)))
                v = ("TRADEABLE" if (trade and survives) else
                     "dies on independent samples" if det and not survives else
                     "detected, too small" if det else "-")
                print(f"  {nm:<22}{k:>3}{h:>4}{ok.sum():>8,}{r.mean():>+11.4f}"
                      f"{t:>+8.2f}{t_min:>+9.2f}{lo:>+10.4f}  {v}")

    df = pd.DataFrame(rows)
    print("\n" + "=" * 84)
    print(f"detected: {int(df.detected.sum())} of {len(df)}     "
          f"tradeable: {int(df.tradeable.sum())} of {len(df)}")
    if df.tradeable.sum():
        print("\n  tradeable:")
        for _, r in df[df.tradeable].iterrows():
            print(f"    {r['hypothesis']} k={r['k']} h={r['h']}  "
                  f"{r['effect']:+.4f} ATR  t={r['t']:+.2f}")
    else:
        print("\n  Nothing clears both bars. The dollar explains where gold HAS")
        print("  been, not where it is going - which is what the contemporaneous")
        print("  correlation above was always measuring.")
    if a.out:
        pathlib.Path(a.out).write_text(df.to_json(orient="records", indent=1))
    print(f"\n  elapsed {time.time()-t0:.0f}s")
    return df

if __name__ == "__main__":
    main()
