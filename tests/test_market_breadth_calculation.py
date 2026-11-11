from __future__ import annotations

import copy
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.deterministic.market_analysis import calculate_market_breadth
from product.runtime.hashing import canonical_hash
from product.runtime.monetary import MONETARY_SCALE_FACTORS, convert_monetary_value


def breadth_fact():
    # Captured provider layout; counts are a synthetic controlled sample.
    rows = [("NEGATIVE_INFINITY", 0, -7), ("NORMAL_RANGE", -7, -5),
            ("NORMAL_RANGE", -5, -3), ("NORMAL_RANGE", -3, 0),
            ("NORMAL_RANGE", 0, 0), ("NORMAL_RANGE", 0, 3),
            ("NORMAL_RANGE", 3, 5), ("NORMAL_RANGE", 5, 7),
            ("POSITIVE_INFINITY", 7, 0)]
    return {"evidence_id": "breadth-test", "security_id": "US:MARKET",
            "semantic_field": "moomoo_us_rise_fall_distribution", "source_id": "test-provider",
            "as_of": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-01T00:00:00Z",
            "value": {"plate": "US.USAALL", "ranges": [
                dict(type=t, left_border=l, right_border=r, stock_count=i)
                for i, (t, l, r) in enumerate(rows, 1)]}}


class BreadthTests(unittest.TestCase):

    def _invalid_breadth_draft(self, unknown_document=False):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            helper = fixtures.MultidimensionalStageTests()
            handoff, gate = helper.mrvl_daily_inputs(include_spy=False)
            fact = breadth_fact()
            fact.update(source_family="moomoo_sg", source_type="SECONDARY_VENDOR", dataset="market_breadth")
            gate["allowed_evidence"].append(fact)
            gate["allowed_evidence_ids"] = sorted(f["evidence_id"] for f in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({k:v for k,v in gate.items() if k != "bundle_hash"})
            (root / "handoff.json").write_text(json.dumps(handoff))
            (root / "gate.json").write_text(json.dumps(gate))
            run = root / "run"
            prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json", run_dir=run, run_id="exhaustion", model="gpt-5.6-terra")
            task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"] if t["capability"] == "MARKET_STATE")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            calc = copy.deepcopy(packet["prepared_analysis"]["breadth_report_calculation"])
            calc["unit"] = "stocks"
            formal = {"calculations": [calc], "artifact_refs": [calc["artifact_ref"]]}
            with self.assertRaisesRegex(ValueError, "MARKET_BREADTH_VALUE_INVALID"):
                validate_breadth_calculation_references(run, formal)
            native = helper.dimension_draft(task)
            if unknown_document:
                native["document_selections"] = ["d.not-authorized.1"]
                failure = "SCHEMA_ENUM_INVALID"
            else:
                native["calculations"] = [calc]
                failure = "SCHEMA_EXTRA_PROPERTY"
            original = copy.deepcopy(native)
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, failure):
                    helper.read_dimension_draft(run, task, native)
                self.assertEqual(native, original)
            outside = {"calculations": [], "artifact_refs": ["../outside/market-breadth-calculation.json"]}
            with self.assertRaisesRegex(ValueError, "MARKET_BREADTH_ARTIFACT_INVALID"):
                validate_breadth_calculation_references(run, outside)
            self.assertFalse((run / "research/reports").exists())
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_sum_and_order_and_input_unchanged(self):
        fact = breadth_fact()
        original = copy.deepcopy(fact)
        result = calculate_market_breadth(fact)
        self.assertEqual(result["counts"], {"fall": 10, "flat": 5, "rise": 30})
        self.assertEqual(fact, original)
        fact["value"]["ranges"].reverse()
        self.assertEqual(calculate_market_breadth(fact)["counts"], result["counts"])
        self.assertEqual(result["artifact_hash"], canonical_hash({k: v for k, v in result.items() if k != "artifact_hash"}))

    def test_invalid_partitions_do_not_create_totals(self):
        variants = []
        fact = breadth_fact()
        fact["value"]["ranges"].pop()
        variants.append(fact)
        fact = breadth_fact()
        fact["value"]["ranges"][0] = fact["value"]["ranges"][1]
        variants.append(fact)
        for field, value in [("type", "UNKNOWN"), ("left_border", -1),
                             ("stock_count", -1), ("stock_count", 1.5),
                             ("stock_count", True), ("stock_count", float("nan")),
                             ("stock_count", "2")]:
            fact = breadth_fact()
            fact["value"]["ranges"][5][field] = value
            variants.append(fact)
        for fact in variants:
            with self.subTest(fact=fact), self.assertRaises(ValueError):
                calculate_market_breadth(fact)

    def test_monetary_allowed_values_and_bounded_error(self):
        for scale, factor in MONETARY_SCALE_FACTORS.items():
            self.assertEqual(convert_monetary_value(value=str(factor), source_scale="one", target_scale=scale), "1")
        with self.assertRaises(ValueError) as error:
            convert_monetary_value(value=1, source_scale="one", target_scale="secret" * 1000)
        self.assertNotIn("secret", str(error.exception))
        self.assertIn("allowed=" + ",".join(MONETARY_SCALE_FACTORS), str(error.exception))
