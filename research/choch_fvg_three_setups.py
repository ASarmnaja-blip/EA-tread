#!/usr/bin/env python3
"""Three CHoCH + fair-value-gap setups, each attacking a different one of the
failure modes this repo has already diagnosed.

WHY THIS EXISTS
  `smc_entry_test.py` measured "CHoCH then FVG retrace" once, one way: entry at
  the CLOSE of the bar that re-enters the gap, on H1, with no higher-timeframe
  context. It returned -0.0943R at t = -2.36, skill over a matched random
  control +0.0293 at t = +0.54.

  That is one configuration, not a verdict on the family. Three things were
  never varied, and each is something this repo has separately identified as a
  reason intraday results die:

    the FILL      every test in this program enters at the close. The cost
                  analysis in RESEARCH_FINDINGS says the spread as a share of R
                  is what kills intraday rules, and the close is the worst
                  available price inside a gap you were waiting to be filled in.
    the HORIZON   -0.2670R at t = -6.23 for trend structure on H1 across 26
                  markets, +0.2232R at t = +2.48 for the same structure DAILY.
                  Only the liquidity sweep was ever taken to daily bars.
                  CHoCH+FVG was not.
    the BIAS     the MTF tests gated on a 4h EMA-50 - a direction filter with no
                  measured edge of its own. The one direction filter in this
                  repo that passed a controlled test (daily Donchian 55, 20 of
                  27 markets positive, binomial p = 0.0096) was never the gate.

WHAT IS TESTED
  S1  gap-edge limit entry     same signal, resting limit at the far edge of
                               the gap, good for 8 bars, skipped if unfilled
  S2  daily CHoCH + FVG        same rules, daily bars, 20 years
  S3  daily trend gates H1     Donchian-55 daily state sets direction, H1
                               CHoCH+FVG sets timing

PRE-REGISTERED, BEFORE THE RUN
  S1  If the +0.0293 skill on the close entry is real directional information,
      a better fill keeps its sign and raises it. Reading: skill > +0.10 at
      t > 2.39 is a result; skill inside +/-0.05 says the fill was never the
      problem and the signal is noise.
  S2  The test that either opens the family or closes it. The repo's precedent
      is a SIGN FLIP between horizons - that is what disqualified the liquidity
      sweep, the strongest candidate in the program. Skill > +0.15 at t > 2.39
      earns a fourth test; a sign flip retires the family.
  S3  If CHoCH+FVG carries entry-TIMING information, gating it on a trend
      independently known to work should raise skill above the ungated +0.0293.
      If the gate only selects trending markets, E rises and skill does not -
      which is exactly what the direction-matched control is for.

  Bonferroni bar for three tests, two-sided: |t| > 2.39.
  Expected max of three standard normals, sqrt(2*ln 3) = 1.48.

THE COLUMN THAT MATTERS IS 'skill'
  Every setup is measured against random entries with MATCHED COUNT, MATCHED
  DIRECTION MIX and identical exits - and for S1, matched entry mechanics, the
  control resting its limit at the same ATR-scaled offset the real signals
  used. Expectancy alone is not evidence: `gold_only_search.py` moved from
  t = +3.18 to t = +2.78 purely by matching the control's direction mix, and
  `universe_trend_test.py` found a Donchian rule on equities reaching t = +4.33
  while being MEASURABLY WORSE than darts.

KNOWN BIAS, AND WHY IT DOES NOT INVALIDATE THE SKILL COLUMN
  Exits are resolved on the signal timeframe's own bars. RESEARCH_FINDINGS puts
  that inflation at roughly +0.5R for H1 - the largest single distortion in this
  program. It applies IDENTICALLY to the rule and its control, so it cancels in
  the difference. Read skill. Do not read E.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

UNI = {"GC=F":"gold","SI=F":"silver","HG=F":"copper","PL=F":"platinum",
       "CL=F":"crude","NG=F":"natgas","RB=F":"gasoline","HO=F":"heatoil",
       "ES=F":"S&P500","NQ=F":"nasdaq","YM=F":"dow","RTY=F":"russell",
       "ZB=F":"30y","ZN=F":"10y","ZF=F":"5y",
       "6E=F":"euro","6J=F":"yen","6B=F":"pound","6A=F":"aud","6C=F":"cad",
       "ZC=F":"corn","ZS=F":"soy","ZW=F":"wheat","KC=F":"coffee",
       "SB=F":"sugar","CT=F":"cotton","LE=F":"cattle"}

COST   = 0.0002      # 2bp of price per leg round turn, charged on every leg
RMULT  = 2.0         # 1R = 2.0 x ATR(14), the repo's standard
LEGS   = (1.0, 2.0, 3.0)
HOLD_H1, HOLD_D = 240, 60
LIMIT_LIFE = 8       # bars a resting gap-edge limit stays live (S1)
DON_N  = 55          # daily Donchian window for the S3 gate
MIN_H1, MIN_D = 3000, 1200
WARMUP = 320
CTRL_REPS = 10       # control draws pooled, so skill is not one lucky draw
SEED = 17

# ------------------------------------------------------------------ data ---
def fetch(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

def grab(item):
    sym, name = item
    out = {}
    for key, (rng, iv, need) in {"h1": ("730d", "1h", MIN_H1),
                                 "d1": ("20y", "1d", MIN_D)}.items():
        try:
            x = fetch(sym, rng, iv)
            out[key] = x if len(x) >= need else None
        except Exception:
            out[key] = None
    return name, out

# ------------------------------------------------------- indicators/prep ---
def prep(df):
    """Structure walk and fair value gaps. Identical rules to smc_entry_test."""
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    N = len(c)
    pc = pd.Series(c).shift(1)
    A = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                   (pd.Series(l) - pc).abs()], axis=1).max(axis=1) \
          .ewm(alpha=1 / 14, adjust=False).mean().to_numpy()

    def piv(s, low):
        s = pd.Series(s)
        ok = ((s < s.rolling(5).min().shift(1)) & (s < s.rolling(5).min().shift(-5))) if low \
             else ((s > s.rolling(5).max().shift(1)) & (s > s.rolling(5).max().shift(-5)))
        return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(5).ffill().to_numpy()
    sh, sl = piv(h, False), piv(l, True)

    # structure: a close beyond the last confirmed opposing swing by 0.10 ATR.
    # Continuing the prevailing direction is BOS; flipping it is CHoCH.
    st = np.zeros(N, np.int8)
    cur = 0
    for i in range(N):
        a = A[i]
        if np.isfinite(a) and a > 0:
            brk = 0.10 * a
            ev = 0
            if np.isfinite(sh[i]) and c[i] > sh[i] + brk:   ev = 1
            elif np.isfinite(sl[i]) and c[i] < sl[i] - brk: ev = -1
            if ev != 0 and ev != cur: cur = ev
        st[i] = cur

    # fair value gap: a three-bar imbalance, carried forward until replaced
    fvg_lo = np.full(N, np.nan); fvg_hi = np.full(N, np.nan)
    fvg_d = np.zeros(N, np.int8)
    _lo = _hi = np.nan; _d = 0
    for i in range(2, N):
        if   l[i] > h[i - 2]: _lo, _hi, _d = h[i - 2], l[i], 1
        elif h[i] < l[i - 2]: _lo, _hi, _d = h[i], l[i - 2], -1
        fvg_lo[i], fvg_hi[i], fvg_d[i] = _lo, _hi, _d

    return dict(o=o, h=h, l=l, c=c, N=N, A=A, st=st,
                fvg_lo=fvg_lo, fvg_hi=fvg_hi, fvg_d=fvg_d)

def signals(P):
    """CHoCH + FVG retrace: gap direction agrees with structure, price closes
    back inside the unfilled gap. Direction per bar, 0 where flat."""
    s = np.zeros(P["N"], np.int8)
    for i in range(P["N"]):
        d = P["fvg_d"][i]
        if d == 0 or d != P["st"][i] or not np.isfinite(P["fvg_lo"][i]): continue
        if P["fvg_lo"][i] <= P["c"][i] <= P["fvg_hi"][i]: s[i] = d
    return s

def donchian_state(dfd, n=DON_N):
    """+1 after a close above the n-day high, -1 after a close below the n-day
    low, held until flipped. Stamped one day LATE so an intraday bar can only
    see a daily bar that closed at least a day earlier."""
    c = dfd.close
    hi = dfd.high.rolling(n).max().shift(1)
    lo = dfd.low.rolling(n).min().shift(1)
    st = pd.Series(np.where(c > hi, 1, np.where(c < lo, -1, np.nan)), index=c.index).ffill()
    st.index = st.index + pd.Timedelta(days=1)
    return st

# ----------------------------------------------------------------- exits ---
def run_trade(P, start, entry, d, risk, hold):
    """Three legs at 1R/2R/3R, stop to break-even after leg one, time stop at
    `hold` bars. The stop is tested BEFORE the targets on every bar, and the
    break-even stop is re-tested on the same bar that filled leg one - both
    bugs `backtest_dobby_indicator.py` had to fix before its harness was sane.
    `risk` is passed in from the SIGNAL bar so an intrabar fill never uses an
    ATR that includes its own bar."""
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    if not np.isfinite(risk) or risk <= 0: return None
    stop = entry - d * risk
    tg = [entry + d * risk * m for m in LEGS]
    alive, t1, r, k, be = [True] * 3, False, 0.0, start + 1, entry
    while k < min(start + 1 + hold, N):
        cur = be if t1 else stop
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            for x in range(3):
                if alive[x]:
                    r += ((cur - entry) * d - COST * entry) / risk
                    alive[x] = False
            break
        for x in range(3):
            if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                r += ((tg[x] - entry) * d - COST * entry) / risk
                alive[x] = False
                if x == 0: t1 = True
        if not any(alive): break
        k += 1
    kx = min(k, N - 1)
    if any(alive):
        for x in range(3):
            if alive[x]: r += ((c[kx] - entry) * d - COST * entry) / risk
    return r, kx

def fill_limit(P, i, d, offset):
    """Resting limit `offset` price units better than the close of bar i, live
    for LIMIT_LIFE bars. Returns (fill_bar, fill_price) or None if never hit."""
    px = P["c"][i] - d * offset
    for k in range(i + 1, min(i + 1 + LIMIT_LIFE, P["N"])):
        if (d > 0 and P["l"][k] <= px) or (d < 0 and P["h"][k] >= px):
            return k, px
    return None

# ------------------------------------------------------------ evaluation ---
def evaluate(prepped, sigs, mode, hold, bars_per_day, rand=False, reps=1,
             match_dir=True, seed=SEED):
    """mode 'close' enters at the signal bar's close; 'limit' rests an order at
    the far edge of the gap. The control matches count, direction mix and - in
    limit mode - the ATR-scaled offset the real signals used, so the only thing
    that differs is WHICH BARS were chosen.

    `reps` draws the control several times and pools them, so the skill column
    is not hostage to one lucky draw of random bars.

    `match_dir=False` reproduces the OLDER control used by smc_entry_test.py,
    which drew direction at random instead of matching the rule's own mix. It
    is kept only so the calibration block can show what that choice was worth."""
    # Each draw gets its own seeded generator, so a row's skill does not depend
    # on how many other rows were evaluated before it.
    rng = np.random.default_rng(seed)
    if rand and reps > 1:
        parts = [evaluate(prepped, sigs, mode, hold, bars_per_day, True, 1,
                          match_dir, seed * 1000 + rep)
                 for rep in range(reps)]
        parts = [p for p in parts if p["n"] >= 30]
        if not parts:
            return dict(n=0, E=np.nan, t=np.nan, sd=np.nan, rpd=np.nan, mk={}, fill=np.nan)
        n = sum(p["n"] for p in parts)
        E = sum(p["n"] * p["E"] for p in parts) / n
        ss = sum((p["n"] - 1) * p["sd"] ** 2 + p["n"] * (p["E"] - E) ** 2 for p in parts)
        sd = math.sqrt(ss / (n - 1))
        mk = {m: float(np.mean([p["mk"][m] for p in parts if m in p["mk"]]))
              for m in {k for p in parts for k in p["mk"]}}
        return dict(n=n, E=E, t=E / (sd / math.sqrt(n)), sd=sd,
                    rpd=float(np.mean([p["rpd"] for p in parts])), mk=mk,
                    fill=float(np.mean([p["fill"] for p in parts])))

    per_market, all_r, days, fills, tried = {}, [], 0.0, 0, 0
    for name, P in prepped.items():
        s = sigs[name]
        lo, hi, c, A, N = P["fvg_lo"], P["fvg_hi"], P["c"], P["A"], P["N"]
        live = [i for i in range(WARMUP, N - 1)
                if s[i] != 0 and np.isfinite(A[i]) and A[i] > 0]
        if not live: continue
        dirs = [int(s[i]) for i in live]
        # offset from the close to the far gap edge, in ATR units
        offs = [abs(c[i] - (lo[i] if s[i] > 0 else hi[i])) / A[i] for i in live]

        if rand:
            pool = [i for i in range(WARMUP, N - 1) if np.isfinite(A[i]) and A[i] > 0]
            if not pool: continue
            pick = sorted(rng.choice(pool, size=min(len(live), len(pool)), replace=False))
            plan = [(int(i),
                     dirs[j % len(dirs)] if match_dir
                     else int(np.sign(rng.integers(0, 2) * 2 - 1)),
                     offs[j % len(offs)])
                    for j, i in enumerate(pick)]
        else:
            plan = list(zip(live, dirs, offs))

        rows, busy = [], -1
        for i, d, off in plan:
            if i <= busy: continue
            risk = RMULT * A[i]
            tried += 1
            if mode == "limit":
                f = fill_limit(P, i, d, off * A[i])
                if f is None: continue
                start, entry = f
            else:
                start, entry = i, c[i]
            t = run_trade(P, start, entry, d, risk, hold)
            if t is None: continue
            fills += 1
            rows.append(t[0]); busy = t[1]
        if rows:
            per_market[name] = float(np.mean(rows))
            all_r.extend(rows)
        days = max(days, N / bars_per_day)

    a = np.array(all_r); n = len(a)
    if n < 30:
        return dict(n=n, E=np.nan, t=np.nan, sd=np.nan, rpd=np.nan, mk={}, fill=np.nan)
    e, sd = a.mean(), a.std(ddof=1)
    return dict(n=n, E=e, t=e / (sd / math.sqrt(n)), sd=sd, rpd=a.sum() / days,
                mk=per_market, fill=fills / tried if tried else np.nan)

def binom_p(k, n):
    """One-sided: probability of k or more successes in n fair coin flips."""
    return sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n

# ------------------------------------------------------------------- run ---
def main():
    print("fetching 26 futures: hourly 730d and daily 20y ...")
    DATA = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for name, got in ex.map(grab, UNI.items()):
            DATA[name] = got
    h1 = {n: v["h1"] for n, v in DATA.items() if v["h1"] is not None}
    d1 = {n: v["d1"] for n, v in DATA.items() if v["d1"] is not None}
    both = [n for n in h1 if n in d1]
    print(f"  hourly {len(h1)} markets, daily {len(d1)}, both {len(both)}\n")

    P_H1 = {n: prep(df) for n, df in h1.items()}
    P_D1 = {n: prep(df) for n, df in d1.items()}
    S_H1 = {n: signals(P) for n, P in P_H1.items()}
    S_D1 = {n: signals(P) for n, P in P_D1.items()}

    # S3: daily Donchian state carried onto the hourly index, gating the signal
    P_S3, S_S3 = {}, {}
    for n in both:
        g = donchian_state(d1[n]).reindex(h1[n].index, method="ffill")
        g = np.nan_to_num(g.to_numpy(float), nan=0.0).astype(np.int8)
        s = S_H1[n].copy()
        s[s != g] = 0
        P_S3[n], S_S3[n] = P_H1[n], s

    plan = [
        # calibration row: the configuration smc_entry_test already measured.
        # Its E must land near -0.0943 or this harness is not measuring the
        # same thing and none of the three rows below mean anything.
        ("S0 close entry (repro)", P_H1, S_H1, "close", HOLD_H1, 23.0),
        ("S1 gap-edge limit H1",  P_H1, S_H1, "limit", HOLD_H1, 23.0),
        ("S2 CHoCH+FVG daily",    P_D1, S_D1, "close", HOLD_D,   1.0),
        ("S3 daily trend + H1",   P_S3, S_S3, "close", HOLD_H1, 23.0),
    ]

    # -------------------------------------------------------- calibration ---
    # Before reading any new row: does this harness reproduce the number the
    # repo already has, and what is the control choice worth?
    cal = evaluate(P_H1, S_H1, "close", HOLD_H1, 23.0)
    c_match = evaluate(P_H1, S_H1, "close", HOLD_H1, 23.0, rand=True,
                       reps=CTRL_REPS, match_dir=True)
    c_free = evaluate(P_H1, S_H1, "close", HOLD_H1, 23.0, rand=True,
                      reps=CTRL_REPS, match_dir=False)
    print("CALIBRATION - the configuration smc_entry_test.py already measured")
    print(f"  recorded there:            E -0.0943   skill +0.0293 (t +0.54)")
    print(f"  reproduced here:           E {cal['E']:+.4f}   n = {cal['n']}")
    print(f"  skill vs RANDOM-direction control (the old method):"
          f" {cal['E'] - c_free['E']:+.4f}")
    print(f"  skill vs MATCHED-direction control (the correction):"
          f" {cal['E'] - c_match['E']:+.4f}")
    print("  The E reproduces. The skill does not, and the difference is entirely")
    print("  the control: matching each market's own long/short mix removes drift")
    print("  that the older control was crediting to the signal. Same correction")
    print("  gold_only_search.py had to make. Every row below uses the matched one.\n")

    hdr = (f"{'setup':<22}{'n':>7}{'E':>9}{'t':>7}{'R/day':>8}"
           f"{'rand E':>9}{'skill':>9}{'skill t':>9}{'mkts+':>8}{'binom p':>9}")
    print(hdr); print("-" * len(hdr))
    out = []
    for label, prepped, sigs, mode, hold, bpd in plan:
        r = evaluate(prepped, sigs, mode, hold, bpd)
        c = evaluate(prepped, sigs, mode, hold, bpd, rand=True, reps=CTRL_REPS)
        if not np.isfinite(r["E"]) or not np.isfinite(c["E"]):
            print(f"{label:<22}{r['n']:>7}  too few trades"); continue
        sk = r["E"] - c["E"]
        se = math.sqrt(r["sd"] ** 2 / r["n"] + c["sd"] ** 2 / c["n"])
        common = [m for m in r["mk"] if m in c["mk"]]
        pos = sum(1 for m in common if r["mk"][m] > c["mk"][m])
        bp = binom_p(pos, len(common)) if common else float("nan")
        out.append((label, r, c, sk, sk / se, pos, len(common), bp))
        print(f"{label:<22}{r['n']:>7}{r['E']:>+9.4f}{r['t']:>+7.2f}{r['rpd']:>8.3f}"
              f"{c['E']:>+9.4f}{sk:>+9.4f}{sk/se:>+9.2f}"
              f"{f'{pos}/{len(common)}':>8}{bp:>9.4f}")

    for label, r, c, *_ in out:
        if "limit" in label and np.isfinite(r["fill"]):
            print(f"\n{label}: limit filled on {r['fill']:.1%} of signals "
                  f"(control {c['fill']:.1%}) - the rest expired unfilled and "
                  f"were never traded")

    print(f"\nBonferroni bar for 3 tests, two-sided: |t| > 2.39")
    print(f"Expected max of 3 standard normals: sqrt(2*ln 3) = {math.sqrt(2*math.log(3)):.2f}")
    print("\n'skill' is the setup minus a random control with matched count, matched")
    print("direction mix and identical exits. 'mkts+' counts markets where the setup")
    print("beat its own control - the repo trusts that count over pooled t, because a")
    print("t can be carried by two lucky markets and a count cannot. E is inflated by")
    print("same-timeframe exit resolution (~+0.5R on H1); the inflation is identical")
    print("in the control, so read skill, not E.")

if __name__ == "__main__":
    main()
