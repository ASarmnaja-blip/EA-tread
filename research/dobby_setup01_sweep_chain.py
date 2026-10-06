#!/usr/bin/env python3
"""Short-Term Setup 01: Liquidity Sweep -> CHoCH/MSS -> Displacement -> FVG entry.

THE RULE, STATED COMPLETELY BEFORE ANY PINE IS WRITTEN

  1 SWEEP        a wick clears the prior SWEEP_N-bar extreme and the body
                 closes back inside, with penetration between 0.08 and 1.50 ATR
                 (below 0.08 is noise, above 1.50 is a real break, not a sweep -
                 the EA's InpSweepMinPenATR / InpSweepMaxPenATR)
  2 CHoCH/MSS    within CHOCH_MAX bars of the sweep, a CLOSE beyond the last
                 confirmed opposing swing by 0.10 ATR, flipping structure into
                 the trade direction (the EA's Structure.mqh rule)
  3 DISPLACEMENT within DISP_MAX bars of the CHoCH, a candle with body >= 0.60
                 ATR closing in the top/bottom 35% of its own range, in the
                 trade direction (the EA's InpMinBodyATR / InpMinCloseLocation)
  4 FVG          the three-bar window ending on that displacement candle must
                 leave an unfilled imbalance, and that gap is the entry zone
  5 ENTRY        a resting limit at the PROXIMAL edge of the gap - the edge
                 price reaches first - live for FVG_LIFE bars, then cancelled
  6 SL           beyond the sweep extreme plus a 0.10 ATR buffer. Rejected if
                 that distance exceeds MAX_SL_ATR, rather than clipped
  7 TP           three legs at 1R / 2R / 3R, stop to break-even after leg one

WHY A FUNNEL IS PRINTED
  Four conditions in series is the point of the setup and also its statistical
  problem: every stage multiplies the sample down. `smc_entry_test.py` already
  measured the two-stage version - "Sweep then CHoCH" - at n = 1,010 across 26
  markets and two years, against n = 9,682 for the sweep alone. Two more stages
  on top of that will not leave much. The funnel says exactly how much, so a
  reading of "no edge" can be told apart from "no data".

COST
  Charged as an ABSOLUTE spread in price units, not basis points, because that
  is how a gold quote actually behaves. Gold is run at BOTH numbers this repo
  has measured: $0.26, the terminal quote, and $0.7525, the 2023-2026 OANDA
  mean. RESEARCH_FINDINGS records that gap as unresolved and it is worth about
  a 46% haircut on expectancy, so a result that only survives at $0.26 is not
  a result you can trade.

THE CONTROL
  Matched count, matched direction mix, matched SL distance and matched limit
  offset - both drawn from the real signals' own distributions - and identical
  exits. Only the CHOICE OF BAR differs. This is the direction-matched control;
  `choch_fvg_three_setups.py` showed the older random-direction control was
  worth about +0.10R of fake skill on this exact family.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

# ---- stage parameters, all from the EA's own defaults where one exists ------
SWEEP_N     = 20        # bars whose extreme the wick must clear
PEN_MIN     = 0.08      # InpSweepMinPenATR
PEN_MAX     = 1.50      # InpSweepMaxPenATR
CHOCH_MAX   = 12        # bars from sweep to structure flip
BREAK_ATR   = 0.10      # InpMinBreakATR
DISP_MAX    = 5         # InpDisplacementLookback
BODY_ATR    = 0.60      # InpMinBodyATR
CLOSE_LOC   = 0.65      # InpMinCloseLocation
FVG_LIFE    = 12        # bars the resting limit stays live
SL_BUF_ATR  = 0.10      # buffer beyond the sweep extreme
MAX_SL_ATR  = 4.00      # reject rather than clip
LEGS        = (1.0, 2.0, 3.0)
CTRL_REPS   = 10
SEED        = 17

UNI = {"GC=F":"gold","SI=F":"silver","HG=F":"copper","PL=F":"platinum",
       "CL=F":"crude","NG=F":"natgas","RB=F":"gasoline","HO=F":"heatoil",
       "ES=F":"S&P500","NQ=F":"nasdaq","YM=F":"dow","RTY=F":"russell",
       "ZB=F":"30y","ZN=F":"10y","ZF=F":"5y",
       "6E=F":"euro","6J=F":"yen","6B=F":"pound","6A=F":"aud","6C=F":"cad",
       "ZC=F":"corn","ZS=F":"soy","ZW=F":"wheat","KC=F":"coffee",
       "SB=F":"sugar","CT=F":"cotton","LE=F":"cattle"}

# ------------------------------------------------------------------ data ---
def fetch(sym, rng, iv):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={rng}&interval={iv}")
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                        index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()

# ------------------------------------------------------------------ prep ---
def prep(df):
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
    sh, sl_ = piv(h, False), piv(l, True)

    ph = pd.Series(h).rolling(SWEEP_N).max().shift(1).to_numpy()
    pl = pd.Series(l).rolling(SWEEP_N).min().shift(1).to_numpy()

    # structure direction, walked forward: a close beyond the opposing swing
    st = np.zeros(N, np.int8)
    cur = 0
    for i in range(N):
        a = A[i]
        if np.isfinite(a) and a > 0:
            b = BREAK_ATR * a
            ev = 0
            if np.isfinite(sh[i]) and c[i] > sh[i] + b:    ev = 1
            elif np.isfinite(sl_[i]) and c[i] < sl_[i] - b: ev = -1
            if ev != 0 and ev != cur: cur = ev
        st[i] = cur

    return dict(o=o, h=h, l=l, c=c, N=N, A=A, sh=sh, sl=sl_, ph=ph, pl=pl, st=st)

# ------------------------------------------------------- the chain itself ---
def is_sweep(P, i, bullish):
    """A wick clears the prior extreme, the body closes back inside, and the
    penetration is in the band that separates a sweep from a real break."""
    a = P["A"][i]
    if not np.isfinite(a) or a <= 0: return False
    if bullish:
        lvl = P["pl"][i]
        if not np.isfinite(lvl): return False
        pen = lvl - P["l"][i]
        return pen > 0 and P["c"][i] > lvl and PEN_MIN * a <= pen <= PEN_MAX * a
    lvl = P["ph"][i]
    if not np.isfinite(lvl): return False
    pen = P["h"][i] - lvl
    return pen > 0 and P["c"][i] < lvl and PEN_MIN * a <= pen <= PEN_MAX * a

def is_displacement(P, i, bullish):
    a = P["A"][i]
    if not np.isfinite(a) or a <= 0: return False
    rng = P["h"][i] - P["l"][i]
    if rng <= 0: return False
    body = abs(P["c"][i] - P["o"][i])
    if body / a < BODY_ATR: return False
    if bullish and P["c"][i] <= P["o"][i]: return False
    if not bullish and P["c"][i] >= P["o"][i]: return False
    loc = (P["c"][i] - P["l"][i]) / rng if bullish else (P["h"][i] - P["c"][i]) / rng
    return loc >= CLOSE_LOC

def fvg_at(P, i, bullish):
    """The three-bar imbalance ending on bar i, if there is one.
    Returns (lo, hi) of the gap."""
    if i < 2: return None
    if bullish and P["l"][i] > P["h"][i - 2]: return (P["h"][i - 2], P["l"][i])
    if not bullish and P["h"][i] < P["l"][i - 2]: return (P["h"][i], P["l"][i - 2])
    return None

def chain(P, warmup):
    """Walk the full sequence once, recording how far each sweep got. Returning
    the whole record rather than only the survivors is what lets the ablation
    below ask each stage to justify itself at the same exits and the same
    control, instead of only reporting the deepest version."""
    N = P["N"]
    f = dict(sweep=0, choch=0, disp=0, fvg=0)
    recs = []
    for i in range(warmup, N - 1):
        for bullish in (True, False):
            if not is_sweep(P, i, bullish): continue
            f["sweep"] += 1
            d = 1 if bullish else -1
            r = dict(d=d, sweep=i, extreme=P["l"][i] if bullish else P["h"][i],
                     choch=-1, disp=-1, fvg=None)
            recs.append(r)

            # 2. structure flip within CHOCH_MAX bars
            for k in range(i + 1, min(i + 1 + CHOCH_MAX, N)):
                if P["st"][k] == d and P["st"][k - 1] != d: r["choch"] = k; break
            if r["choch"] < 0: continue
            f["choch"] += 1

            # 3. displacement within DISP_MAX bars of the flip
            for k in range(r["choch"], min(r["choch"] + 1 + DISP_MAX, N)):
                if is_displacement(P, k, bullish): r["disp"] = k; break
            if r["disp"] < 0: continue
            f["disp"] += 1

            # 4. the displacement leg must leave a gap
            z = fvg_at(P, r["disp"], bullish)
            if z is None: continue
            r["fvg"] = z
            f["fvg"] += 1
    return recs, f

# Where each stage depth enters. 1-3 take the close of the bar that completed
# the stage; 4 rests a limit at the proximal edge of the gap. In every case the
# stop sits beyond the SWEEP extreme, so the four rows differ only in when they
# commit, not in what invalidates them.
DEPTHS = {1: "sweep", 2: "choch", 3: "disp", 4: "fvg"}

def setups_at(P, recs, depth):
    """Turn the records into tradeable setups at the requested stage depth."""
    out, rejected = [], 0
    for r in recs:
        if depth >= 2 and r["choch"] < 0: continue
        if depth >= 3 and r["disp"] < 0: continue
        if depth >= 4 and r["fvg"] is None: continue
        bar = r[DEPTHS[depth]] if depth < 4 else r["disp"]
        a = P["A"][bar]
        if not np.isfinite(a) or a <= 0: continue
        if depth < 4:
            entry = P["c"][bar]
        else:
            lo, hi = r["fvg"]
            entry = hi if r["d"] > 0 else lo          # proximal edge
        risk = abs(entry - r["extreme"]) + SL_BUF_ATR * a
        if risk <= 0 or risk > MAX_SL_ATR * a:
            rejected += 1
            continue
        out.append(dict(sig=bar, d=r["d"], entry=entry, risk=risk, atr=a,
                        off=abs(P["c"][bar] - entry) / a,
                        immediate=(depth < 4)))
    return out, rejected

# ----------------------------------------------------------------- exits ---
def run_trade(P, start, entry, d, risk, hold, spread):
    h, l, c, N = P["h"], P["l"], P["c"], P["N"]
    stop = entry - d * risk
    tg = [entry + d * risk * m for m in LEGS]
    alive, t1, r, k, be = [True] * 3, False, 0.0, start + 1, entry
    while k < min(start + 1 + hold, N):
        cur = be if t1 else stop
        if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
            for x in range(3):
                if alive[x]:
                    r += ((cur - entry) * d - spread) / risk
                    alive[x] = False
            break
        for x in range(3):
            if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                r += ((tg[x] - entry) * d - spread) / risk
                alive[x] = False
                if x == 0: t1 = True
        if not any(alive): break
        k += 1
    kx = min(k, N - 1)
    if any(alive):
        for x in range(3):
            if alive[x]: r += ((c[kx] - entry) * d - spread) / risk
    return r, kx

def take(P, setups, hold, spread, rand=False, seed=SEED, warmup=320):
    """Trade the setups, one position at a time. The control keeps the real
    signals' direction, stop distance and limit offset, and changes only the
    bar it starts from."""
    rng = np.random.default_rng(seed)
    N = P["N"]
    if rand:
        if not setups: return [], 0, 0
        pool = [i for i in range(warmup, N - 1)
                if np.isfinite(P["A"][i]) and P["A"][i] > 0]
        if not pool: return [], 0, 0
        pick = sorted(rng.choice(pool, size=min(len(setups), len(pool)), replace=False))
        plan = []
        for j, i in enumerate(pick):
            s = setups[j % len(setups)]
            a = P["A"][int(i)]
            d = s["d"]
            # The limit must rest on the SAME SIDE as the real one: a long waits
            # BELOW the close. Getting this sign wrong fills the control at a
            # worse price than it asked for and manufactures skill out of thin
            # air - it was worth a fake +2.2R here before it was caught.
            plan.append(dict(sig=int(i), d=d, entry=P["c"][int(i)] - d * s["off"] * a,
                             risk=s["risk"] / s["atr"] * a, atr=a, off=s["off"],
                             immediate=s["immediate"]))
    else:
        plan = setups

    rows, busy, filled = [], -1, 0
    for s in plan:
        i = s["sig"]
        if i <= busy: continue
        if s["immediate"]:
            k = i
        else:
            # the resting limit must actually be hit, or the setup is skipped
            k = -1
            for b in range(i + 1, min(i + 1 + FVG_LIFE, N)):
                if (s["d"] > 0 and P["l"][b] <= s["entry"]) or \
                   (s["d"] < 0 and P["h"][b] >= s["entry"]): k = b; break
            if k < 0: continue
        filled += 1
        t = run_trade(P, k, s["entry"], s["d"], s["risk"], hold, spread)
        rows.append(t[0]); busy = t[1]
    return rows, filled, len(plan)

def stats(rows):
    a = np.array(rows); n = len(a)
    if n < 2: return dict(n=n, E=np.nan, t=np.nan, sd=np.nan, mde=np.nan)
    e, sd = a.mean(), a.std(ddof=1)
    se = sd / math.sqrt(n)
    return dict(n=n, E=e, t=e / se, sd=sd, mde=2.8 * se)

# ------------------------------------------------------------------- run ---
def measure(prepped, hold, spread, depth=4, warmup=320, records=None):
    real, ctrl, funnel, fills, cands = [], [], {}, 0, 0
    for name, P in prepped.items():
        recs, f = records[name] if records else chain(P, warmup)
        for k, v in f.items(): funnel[k] = funnel.get(k, 0) + v
        setups, _ = setups_at(P, recs, depth)
        funnel["sl_ok"] = funnel.get("sl_ok", 0) + len(setups)
        r, fl, cd = take(P, setups, hold, spread, warmup=warmup)
        real.extend(r); fills += fl; cands += cd
        for rep in range(CTRL_REPS):
            cr, _, _ = take(P, setups, hold, spread, rand=True,
                            seed=SEED * 1000 + rep, warmup=warmup)
            ctrl.extend(cr)
    R, C = stats(real), stats(ctrl)
    sk = R["E"] - C["E"] if R["n"] > 1 and C["n"] > 1 else np.nan
    se = math.sqrt(R["sd"] ** 2 / R["n"] + C["sd"] ** 2 / C["n"]) \
         if R["n"] > 1 and C["n"] > 1 else np.nan
    return R, C, sk, (sk / se if se else np.nan), funnel, fills, cands

def show_funnel(f, fills, cands, label):
    print(f"\n  funnel, {label}")
    order = [("1 sweep", "sweep"), ("2 + CHoCH", "choch"),
             ("3 + displacement", "disp"), ("4 + FVG", "fvg"),
             ("5 + stop in range", "sl_ok")]
    prev = None
    for nm, k in order:
        v = f.get(k, 0)
        pct = f"{v/prev:6.1%} kept" if prev else "          "
        print(f"    {nm:<20}{v:>8,}  {pct}")
        prev = v if v else None
    if cands:
        print(f"    {'6 + limit filled':<20}{fills:>8,}  {fills/cands:6.1%} kept")

def line(label, R, C, sk, skt):
    if not np.isfinite(R["E"]):
        print(f"{label:<26}{R['n']:>6}   too few trades to measure"); return
    print(f"{label:<26}{R['n']:>6}{R['E']:>+9.3f}{R['t']:>+7.2f}"
          f"{C['E']:>+9.3f}{sk:>+9.3f}{skt:>+8.2f}{R['mde']:>8.2f}")

def main():
    print("Short-Term Setup 01: sweep -> CHoCH -> displacement -> FVG limit\n")
    print("fetching ...")
    gold = {}
    for tf, (rng, iv, hold) in {"M15": ("60d", "15m", 96),
                                "H1":  ("730d", "1h", 48),
                                "D1":  ("20y", "1d", 30)}.items():
        try:
            gold[tf] = (fetch("GC=F", rng, iv), hold)
            print(f"  gold {tf}: {len(gold[tf][0]):,} bars "
                  f"{gold[tf][0].index[0].date()} -> {gold[tf][0].index[-1].date()}")
        except Exception as e:
            print(f"  gold {tf}: FAILED {type(e).__name__}")

    hdr = (f"{'run':<26}{'n':>6}{'E':>9}{'t':>7}{'randE':>9}"
           f"{'skill':>9}{'sk t':>8}{'MDE':>8}")

    # ---------------------------------------------------------- gold alone --
    print("\n" + "=" * 82)
    print("GOLD ALONE - the instrument the setup is designed for")
    print("=" * 82)
    print(hdr); print("-" * len(hdr))
    for tf, (df, hold) in gold.items():
        P = prep(df)
        warm = min(320, max(60, P["N"] // 10))
        rec = {"gold": chain(P, warm)}
        for sp, tag in ((0.26, "spread 0.26"), (0.7525, "spread 0.7525")):
            R, C, sk, skt, f, fills, cands = measure({"gold": P}, hold, sp, 4,
                                                     warm, rec)
            line(f"gold {tf}, {tag}", R, C, sk, skt)
        show_funnel(f, fills, cands, f"gold {tf}")
        yrs = (df.index[-1] - df.index[0]).days / 365.25
        print(f"    {'trades per year':<20}{fills/yrs:>8.1f}")

    # ------------------------------------------------- the futures universe --
    print("\n" + "=" * 82)
    print("26 FUTURES, H1, 730d - run only for the sample size gold cannot give")
    print("=" * 82)
    def g(item):
        sym, name = item
        try:
            x = fetch(sym, "730d", "1h")
            return name, (x if len(x) >= 3000 else None)
        except Exception:
            return name, None
    UD = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n, x in ex.map(g, UNI.items()):
            if x is not None: UD[n] = x
    PU = {n: prep(x) for n, x in UD.items()}
    print(f"  {len(PU)} markets\n")
    REC = {n: chain(P, 320) for n, P in PU.items()}
    print(hdr); print("-" * len(hdr))
    R, C, sk, skt, f, fills, cands = measure(PU, 48, 0.0, 4, 320, REC)
    line("futures H1, zero cost", R, C, sk, skt)
    show_funnel(f, fills, cands, "26 futures H1")

    # --------------------------------------------------------- the ablation --
    print("\n" + "=" * 82)
    print("ABLATION - does each stage earn its place, or only cut the sample?")
    print("=" * 82)
    print("Same stop (beyond the sweep extreme), same 1R/2R/3R ladder, same")
    print("matched control. The rows differ only in HOW LATE they commit.\n")
    print(hdr); print("-" * len(hdr))
    names = {1: "1 sweep only", 2: "2 + CHoCH", 3: "3 + displacement",
             4: "4 + FVG limit (full)"}
    for depth in (1, 2, 3, 4):
        R, C, sk, skt, _, fl, _ = measure(PU, 48, 0.0, depth, 320, REC)
        line(names[depth], R, C, sk, skt)
    print("\nBonferroni bar for 4 nested tests, two-sided: |t| > 2.50")

    print("\nNOTES")
    print("  MDE is the smallest true effect this sample could detect at 80%")
    print("  power. A skill number smaller than its own MDE is not evidence of")
    print("  absence - it is absence of evidence, and the funnel says why.")
    print("  The futures row is run at ZERO cost deliberately: it is there to")
    print("  ask whether the SEQUENCE carries information at a sample gold")
    print("  cannot reach, not to price a tradeable system.")
    print("  Control matches count, direction, stop distance and limit offset.")

if __name__ == "__main__":
    main()
