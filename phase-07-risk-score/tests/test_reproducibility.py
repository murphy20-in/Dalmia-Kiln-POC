"""Reproducibility: repeated scoring / fitting / bootstrap identical, byte-stable serialisation, stable config key, no
hidden current-time or unseeded randomness. (Two full clean runs are compared byte-for-byte by run_phase7.py, G8.)"""
from __future__ import annotations

import io
import json
import re
import unittest

import synthetic
from risk_core import block_ids, boot_quantiles
from common import PRIMARY, SCRIPTS, round_frame
from reference_builder import fit_reference
from risk_core import components_long, score_frame


class TestReproducibility(unittest.TestCase):
    def test_two_runs_identical(self):
        ctx = synthetic.make_context(synthetic.make_grid())
        refs1, refs2 = synthetic.fit_refs(ctx), synthetic.fit_refs(ctx)
        self.assertEqual(json.dumps(refs1, sort_keys=True, default=str), json.dumps(refs2, sort_keys=True, default=str))
        a, ca = score_frame(ctx["grid"], refs1, ctx)
        b, cb = score_frame(ctx["grid"], refs2, ctx)
        self.assertTrue(a.equals(b))
        self.assertTrue(components_long(a, ca).equals(components_long(b, cb)))
        self.assertTrue(ca["reasons_long"].equals(cb["reasons_long"]))

    def test_serialisation_is_byte_stable(self):
        g, ctx, refs = synthetic.fixture()
        f, _ = score_frame(g, refs, ctx)
        out = []
        for _ in range(2):
            buf = io.BytesIO()
            round_frame(f.reset_index()).to_parquet(buf, index=False)
            out.append(buf.getvalue())
        self.assertEqual(out[0], out[1])

    def test_bootstrap_and_reference_seeded(self):
        g, ctx, _ = synthetic.fixture()
        r1 = fit_reference(g, PRIMARY, ctx["episodes"], ctx)["bands"]
        r2 = fit_reference(g, PRIMARY, ctx["episodes"], ctx)["bands"]
        self.assertEqual(r1, r2)
        import numpy as np
        v = np.arange(3000, dtype=float)
        blk = block_ids(g.index[:3000], PRIMARY.ref_start, 3)
        np.testing.assert_array_equal(boot_quantiles(v, blk, (0.5,), 30, 1), boot_quantiles(v, blk, (0.5,), 30, 1))

    def test_config_key_stable(self):
        self.assertEqual(PRIMARY.key(), PRIMARY.key())
        self.assertEqual(len(PRIMARY.key()), 12)

    def test_no_hidden_current_time_or_unseeded_randomness(self):
        bad = re.compile(r"datetime\.now|date\.today|Timestamp\.now|Timestamp\(\s*[\"']now|default_rng\(\s*\)|"
                         r"np\.random\.(rand|randn|random|choice|seed)\(")
        hits = []
        for p in sorted(SCRIPTS.glob("*.py")):
            if p.name == "run_phase7.py":             # uses time.time() for durations in the log only
                continue
            hits += [f"{p.name}:{i + 1}" for i, ln in enumerate(p.read_text().splitlines()) if bad.search(ln)]
        self.assertEqual(hits, [])


class TestSafety(unittest.TestCase):
    def test_clean_refuses_paths_outside_phase7(self):
        from pathlib import Path
        import run_phase7
        saved = run_phase7.OWNED
        try:
            run_phase7.OWNED = (Path("/tmp") / "not-phase-7",)
            with self.assertRaises(RuntimeError):
                run_phase7.clean()
        finally:
            run_phase7.OWNED = saved

    def test_wording_scanner(self):
        from common import forbidden_hits
        self.assertTrue(forbidden_hits("The score is a deposit probability."))
        self.assertTrue(forbidden_hits("This detects deposits confirmed by the model."))
        self.assertFalse(forbidden_hits("It is not a deposit probability."))
        self.assertFalse(forbidden_hits("EMPIRICAL_ALERT_RATE is reported instead."))


if __name__ == "__main__":
    unittest.main()
