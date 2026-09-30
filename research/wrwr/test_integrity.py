"""C5 integrity and data-definition tests for the WRWR potential-signal tables (contract v5). Run directly."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402


def test_h4_d1_entry_spread_is_first_constituent():
    H, _, cuts, _ = E.load()
    base = SG.mk(H.t, H.o, H.h, H.l, H.c, H.v, H.spread_bp, 3600)
    by_t = dict(zip(base.t.tolist(), base.spread_bp))
    for tf in ("H4", "D1"):
        B, _, _ = SG.load_xau(tf)
        exp = np.array([by_t[int(t)] for t in B.t])
        assert np.array_equal(exp, B.spread_bp), f"{tf}: spread is not the first constituent H1 spread"
    print("PASS C4 H4 / D1 entry spread = first constituent H1 bar's recorded spread (not a bar median)")


def _tampered(edit):
    meta, cands, arr = SG.load("XAUUSD", "D1", verify=False)
    tmp = Path(tempfile.mkdtemp()) / "t.npz"
    m2 = dict(meta); a2 = {k: v.copy() for k, v in arr.items()}
    edit(m2, a2)
    np.savez_compressed(tmp, meta=json.dumps(m2), cands=json.dumps(cands), **a2)
    return tmp


def test_loader_rejects_tampering():
    SG.load("XAUUSD", "D1", verify=True)                                      # the genuine table loads
    cases = {
        "flipped gross_bp value": lambda m, a: a["gross_bp"].__setitem__(5, a["gross_bp"][5] + 1.0),
        "non-monotonic bar times": lambda m, a: a["bar_t"].__setitem__(10, a["bar_t"][9]),
        "wrong schema": lambda m, a: m.__setitem__("schema", "old"),
        "stale code digest": lambda m, a: m.__setitem__("code_sha", "0" * 64),
        "different raw manifest": lambda m, a: m.__setitem__("raw_manifest_sha", "0" * 64),
        "different data digest": lambda m, a: m.__setitem__("data_sha", "0" * 64),
        "row count mismatch": lambda m, a: m.__setitem__("n_rows", m["n_rows"] + 1),
    }
    for name, edit in cases.items():
        tmp = _tampered(edit)
        try:
            SG.load("XAUUSD", "D1", verify=True, path=tmp)
        except ValueError:
            continue
        finally:
            shutil.rmtree(tmp.parent, ignore_errors=True)
        raise AssertionError(f"tampered table accepted: {name}")
    print(f"PASS C5 loader fails closed on {len(cases)} kinds of tampering (array, time order, schema, code, raw manifest, data, counts)")


def test_table_columns_and_reconstruction():
    meta, cands, a = SG.load("XAUUSD", "D1", verify=True)
    for col in ("dir", "gross_bp", "cost_bp", "swap_bp", "stop_px", "entry_px"):
        assert col in a, col
    assert meta["rejected_at_cut"] == 0 and len(a["rej_cand"]) == 0
    stop_bp = a["stop_px"].astype(float) / a["entry_px"].astype(float) * 1e4
    R = (a["gross_bp"].astype(float) - a["cost_bp"] - a["swap_bp"]) / stop_bp
    assert np.isfinite(R).all() and (R > -3).all(), (R.min(), R.max())         # a stop loss is about -1 R plus costs
    assert ((a["dir"] == 1) | (a["dir"] == -1)).all()
    shorts = a["dir"] == -1
    assert (a["swap_bp"][shorts] == 0).all(), "shorts must pay no swap (C4)"
    print(f"PASS tables: separate gross / cost / swap columns, shorts no swap, R in [{R.min():.2f}, {R.max():.2f}]")


if __name__ == "__main__":
    for t in (test_h4_d1_entry_spread_is_first_constituent, test_loader_rejects_tampering, test_table_columns_and_reconstruction):
        t()
    print("ALL INTEGRITY TESTS PASS")
