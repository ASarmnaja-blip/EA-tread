"""Diagnostic (DISC only): does a variant's trailing performance predict its next-period
performance? Rank correlation across menu variants between trailing-L-week mean R and the
next-H-week mean R, averaged over cuts, with a week-block bootstrap interval."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
from selector import menu_trades  # noqa: E402

WEEK = E.WEEK


def main(menu="menu1") -> int:
    os.chdir(E.ROOT)
    T, cuts, cell, names = menu_trades(menu)
    end_disc = int(np.datetime64("2015-01-01T00:00:00", "s").astype(np.int64))
    T = T[T.xt < end_disc]
    xt, et, v, R = T.xt.to_numpy(), T.et.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    rows = []
    for L in (1, 4, 8, 13, 26, 52):
        for Hh in (1, 4, 13):
            ics = []
            for k in range(60, len(cuts)):
                c = cuts[k]
                if c + Hh * WEEK > end_disc:
                    break
                past = (xt > c - L * WEEK) & (xt <= c)
                fut = (et > c) & (et <= c + Hh * WEEK)
                a = pd.Series(R[past]).groupby(v[past]).mean()
                b = pd.Series(R[fut]).groupby(v[fut]).mean()
                j = a.index.intersection(b.index)
                if len(j) >= 10:
                    ics.append(spearmanr(a[j], b[j]).statistic)
            ics = np.asarray(ics)
            ics = ics[np.isfinite(ics)]
            # block bootstrap over cuts (block = max(L, H) weeks)
            blk = max(L, Hh, 4)
            rng = np.random.default_rng(1)
            nb = int(np.ceil(len(ics) / blk))
            bs = [ics[(rng.integers(0, len(ics), nb)[:, None] + np.arange(blk)) % len(ics)].mean() for _ in range(1000)]
            rows.append(dict(lookback_wk=L, horizon_wk=Hh, cuts=len(ics), mean_IC=ics.mean(),
                             lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5)))
    pd.set_option("display.width", 200)
    print("DISC 2003-14: rank IC between trailing mean R and next-period mean R across menu variants")
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
