"""Candle Lab trade autopsy: WHY trades win or lose. For uncapped trend rules (Turtle S1 20/10, Turtle S2 55/20, Chandelier 55 / 3 ATR; long and
short) on gold H1 / H4 / D1 (Candle Lab bars, 2009-2026): the candle anatomy and higher-timeframe context of the signal bar, the path after entry
(MFE, MAE, bars to the best point, whether +1 R came before -1 R), and a depth-3 decision tree trained on DEV (2009-15) and judged on CHECK
(2016-26). Costs: 2.5 bp round trip + gold swap for longs (contracts.swap_bp). Usage: python research/candlelab/autopsy.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L  # noqa: E402
import analyze as AN  # noqa: E402

sys.path.insert(0, str(L.ROOT / "research" / "hyp"))
import turtle as TU  # noqa: E402

K = TU.K
OUT = L.ROOT / "data" / "candlelab"
SYSTEMS = {"S1 20/10": (20, 10, None), "S2 55/20": (55, 20, None), "CHAND 55/3": (55, None, 3.0)}


def trades_with_path(X, en, ex, ch, long_only):
    cost = lambda e, j, sig: (2.5, float(K.swap_bp("XAUUSD", X.t[[e]], X.t[[j]] + L.TF_SECONDS[X.tf], np.array([float(sig)]))[0]))
    tr = TU.run(X.t, X.o, X.h, X.l, X.c, en, ex, ch, long_only, cost)
    if not len(tr):
        return tr
    e = np.searchsorted(X.t, tr.t.to_numpy(np.int64)); j = np.searchsorted(X.t, tr.t_exit.to_numpy(np.int64))
    N = TU.atr(X.h, X.l, X.c, 20)
    rows = []
    for ei, ji, d in zip(e, j, tr.d.to_numpy()):
        risk = 2 * N[ei - 1]; ep = X.o[ei]
        hi = X.h[ei:ji + 1]; lo = X.l[ei:ji + 1]
        fav = (hi - ep) if d > 0 else (ep - lo); adv = (ep - lo) if d > 0 else (hi - ep)
        mfe = np.maximum.accumulate(fav) / risk; mae = np.maximum.accumulate(adv) / risk
        k_best = int(np.argmax(fav))
        up1 = np.argmax(mfe >= 1) if (mfe >= 1).any() else 10 ** 6; dn1 = np.argmax(mae >= 1) if (mae >= 1).any() else 10 ** 6
        rows.append(dict(sig_bar=ei - 1, mfe_R=float(mfe[-1]), mae_R=float(mae[-1]), bars_to_best=k_best, plus1_first=float(up1 < dn1),
                         mae_before_best_R=float(mae[k_best]) if k_best < len(mae) else np.nan))
    return pd.concat([tr.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def explain(tr, F, name):
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.metrics import roc_auc_score
    X = F.iloc[tr.sig_bar.to_numpy()].reset_index(drop=True)
    X["dir"] = tr.d.to_numpy()
    y = (tr.R > 0).astype(int).to_numpy()
    yr = pd.to_datetime(tr.t, unit="s").dt.year.to_numpy()
    dev, chk = yr < 2016, yr >= 2016
    cols = [c for c in X.columns if X[c].notna().mean() > 0.9]
    Xf = X[cols].fillna(X[cols].median())
    out = [f"\n=== {name}: {len(tr)} trades, win rate {y.mean():.0%}, mean R {tr.R.mean():+.3f} (DEV {tr.R[dev].mean():+.3f} n {dev.sum()}, "
           f"CHECK {tr.R[chk].mean():+.3f} n {chk.sum()}) ==="]
    w, lz = tr.R > 0, tr.R <= 0
    out.append(f"  path: winners MFE {tr.mfe_R[w].mean():.2f} R, bars to best {tr.bars_to_best[w].mean():.1f}, MAE before best {tr.mae_before_best_R[w].mean():.2f} R; "
               f"losers MFE {tr.mfe_R[lz].mean():.2f} R (share of losers that never reached +0.5 R: {(tr.mfe_R[lz] < 0.5).mean():.0%}), "
               f"+1 R before -1 R: winners {tr.plus1_first[w].mean():.0%}, losers {tr.plus1_first[lz].mean():.0%}")
    big = tr.R >= 3
    out.append(f"  where the money is: trades >= +3 R are {big.mean():.0%} of trades and {tr.R[big].sum():+.1f} R of the total {tr.R.sum():+.1f} R")
    smd = []
    for c in cols:
        a, b = Xf.loc[w, c], Xf.loc[lz, c]
        sd = Xf[c].std()
        if sd > 0 and dev.sum() > 20:
            try:
                auc = roc_auc_score(y[dev], Xf.loc[dev, c]) if len(set(y[dev])) > 1 else np.nan
                auc_c = roc_auc_score(y[chk], Xf.loc[chk, c]) if len(set(y[chk])) > 1 else np.nan
            except ValueError:
                auc = auc_c = np.nan
            smd.append((c, (a.mean() - b.mean()) / sd, auc, auc_c))
    S = pd.DataFrame(smd, columns=["feature", "smd_win_minus_loss", "auc_dev", "auc_check"])
    S["stable"] = (S.auc_dev - 0.5) * (S.auc_check - 0.5) > 0
    S = S.assign(strength=(S.auc_dev - 0.5).abs()).sort_values("strength", ascending=False)
    out.append("  features that separate winners from losers at entry (AUC on DEV and on CHECK; stable = same side of 0.5 in both):")
    for _, r in S.head(8).iterrows():
        out.append(f"    {r.feature:<24s} win-minus-loss {r.smd_win_minus_loss:+.2f} sd, AUC DEV {r.auc_dev:.2f}, CHECK {r.auc_check:.2f}{'  stable' if r.stable else ''}")
    if dev.sum() >= 40 and chk.sum() >= 20 and len(set(y[dev])) > 1:
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=max(10, int(0.08 * dev.sum())), random_state=0).fit(Xf[dev], y[dev])
        try:
            auc_tr = roc_auc_score(y[dev], tree.predict_proba(Xf[dev])[:, 1]); auc_te = roc_auc_score(y[chk], tree.predict_proba(Xf[chk])[:, 1])
        except ValueError:
            auc_tr = auc_te = np.nan
        out.append(f"  decision tree (depth 3, trained on DEV): AUC DEV {auc_tr:.2f}, CHECK {auc_te:.2f}")
        out.append("    " + export_text(tree, feature_names=list(Xf.columns), decimals=2).replace("\n", "\n    "))
    return "\n".join(out), S


def main():
    t0 = time.time()
    base = L.base_gold(); cuts = L.cut_grid(base["t"][-1])
    bars = {tf: L.resample(base, tf, cuts) for tf in ("H1", "H4", "D1", "W1")}
    fr = {}
    for tf in ("H1", "H4", "D1"):
        Xb = bars[tf]; Fb = L.anatomy(Xb)
        for y in AN.HTF[tf]:
            Fb = pd.concat([Fb, L.htf_context(Xb, bars[y], y.lower())], axis=1)
        fr[tf] = (Xb, Fb, None, None)
    text = []
    allS = []
    for tf in ("D1", "H4", "H1"):
        X, F, O, wk = fr[tf]
        F = F.copy()
        F["atr_pct_1y"] = pd.Series(X.atr).rolling(250 if tf == "D1" else 1500, min_periods=100).rank(pct=True).to_numpy()
        F["ret20_atr"] = (X.c - np.r_[np.full(20, np.nan), X.c[:-20]]) / X.atr
        for name, (en, ex, ch) in SYSTEMS.items():
            for lo in (True, False):
                tr = trades_with_path(X, en, ex, ch, lo)
                if len(tr) < 30:
                    continue
                lab = f"{tf} {name} {'long-only' if lo else 'long+short'}"
                s, S = explain(tr, F, lab)
                text.append(s); S["rule"] = lab; allS.append(S)
                print(s, flush=True)
    (OUT / "autopsy.txt").write_text("\n".join(text), encoding="utf-8")
    pd.concat(allS).to_csv(OUT / "autopsy_features.csv", index=False)
    print(f"\n-> {OUT / 'autopsy.txt'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
