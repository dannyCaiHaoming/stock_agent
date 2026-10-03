"""CIO计算血缘无损共享；不启动模型，不改变研究内容。"""
from copy import deepcopy
import unittest

from product.runtime.cio_handoff import (
    REPORT_DELIVERY_VERSION, compact_cio_report_view, expand_cio_report_view,
)
from product.runtime.hashing import canonical_hash, canonical_json


class CioReportDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.invocation = {"run_id": "cio-new", "invocation_id": "cio:cio-new",
                           "report_delivery_version": REPORT_DELIVERY_VERSION}
        self.mapping = {"map_hash": "b" * 64}
        self.binding = {"run_id": "cio-new", "invocation_id": "cio:cio-new",
                        "reference_map_hash": self.mapping["map_hash"]}
        # Include repeated entries and reverse order: neither can be normalized.
        refs = [f"e.scope.{i}" for i in range(100, 0, -1)] + ["e.scope.7"] * 5
        self.value = {"reports": [{"report_id": "p.scope.1", "report": {
            "claims": [{"statement": "原作者判断，不得改写", "evidence_refs": ["e.scope.7"]}],
            "calculations": [{"calculation_id": f"calc-{i}", "value": i, "unit": "pct",
                "method": "original method", "input_evidence_refs": deepcopy(refs)} for i in range(20)],
            "unrelated": {"input_evidence_refs": deepcopy(refs)},
        }}]}

    def test_lossless_shared_order_duplicates_and_fields_without_input_mutation(self):
        original = deepcopy(self.value)
        encoded = compact_cio_report_view(self.value, self.invocation, self.mapping)
        self.assertEqual(self.value, original)
        self.assertLess(len(canonical_json(encoded).encode()), len(canonical_json(original).encode()) // 4)
        self.assertEqual(len(encoded["report_delivery"]["input_evidence_ref_sets"]), 1)
        expanded = expand_cio_report_view(encoded, binding=self.binding)
        self.assertEqual(canonical_json(expanded), canonical_json(original))
        self.assertEqual(encoded["reports"][0]["report"]["unrelated"], original["reports"][0]["report"]["unrelated"])
        expanded["reports"][0]["report"]["calculations"][0]["input_evidence_refs"].clear()
        self.assertNotEqual(expanded["reports"][0]["report"]["calculations"][1]["input_evidence_refs"], [])

    def test_legacy_small_and_nonrepeated_responses_keep_original_representation(self):
        legacy = {key: value for key, value in self.invocation.items() if key != "report_delivery_version"}
        self.assertEqual(compact_cio_report_view(self.value, legacy, self.mapping), self.value)
        small = {"reports": [{"report_id": "p.1", "report": {"calculations": [
            {"input_evidence_refs": ["e.1"]}, {"input_evidence_refs": ["e.1"]}]}}]}
        self.assertEqual(compact_cio_report_view(small, self.invocation, self.mapping), small)
        unique = deepcopy(self.value)
        unique["reports"][0]["report"]["calculations"] = unique["reports"][0]["report"]["calculations"][:1]
        self.assertEqual(compact_cio_report_view(unique, self.invocation, self.mapping), unique)
        self.assertEqual(expand_cio_report_view(unique, binding=self.binding), unique)
        with self.assertRaisesRegex(ValueError, "PROTOCOL_INVALID"):
            compact_cio_report_view(self.value, {**self.invocation, "report_delivery_version": "unknown"}, self.mapping)
        with self.assertRaisesRegex(ValueError, "PROTOCOL_INVALID"):
            compact_cio_report_view(self.value, self.invocation, None)

    def test_unknown_missing_unused_or_tampered_definitions_and_semantics_rejected(self):
        encoded = compact_cio_report_view(self.value, self.invocation, self.mapping)
        key = next(iter(encoded["report_delivery"]["input_evidence_ref_sets"]))
        changes = []
        for delivery in (None, "invalid", []):
            bad = deepcopy(encoded)
            bad["report_delivery"] = delivery
            changes.append(bad)
        bad = deepcopy(encoded)
        bad["report_delivery"]["input_evidence_ref_sets"][key][0] = "e.changed"
        changes.append(bad)
        bad = deepcopy(encoded)
        bad["report_delivery"]["input_evidence_ref_sets"] = {}
        changes.append(bad)
        bad = deepcopy(encoded)
        bad["report_delivery"]["input_evidence_ref_sets"]["refs." + canonical_hash(["e.extra"])] = ["e.extra"]
        changes.append(bad)
        for marker in ({"input_evidence_ref_set": "missing"}, {"input_evidence_ref_set": key, "extra": 1}, "missing"):
            bad = deepcopy(encoded)
            bad["reports"][0]["report"]["calculations"][0]["input_evidence_refs"] = marker
            changes.append(bad)
        bad = deepcopy(encoded)
        bad["reports"][0]["report"]["claims"][0]["statement"] = "改稿"
        changes.append(bad)
        bad = deepcopy(encoded)
        bad["report_delivery"]["version"] = "unknown"
        changes.append(bad)
        for bad in changes:
            with self.subTest(bad=canonical_hash(bad)), self.assertRaises(ValueError):
                expand_cio_report_view(bad, binding=self.binding)
        for field in ("run_id", "invocation_id", "reference_map_hash"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "BINDING_INVALID"):
                expand_cio_report_view(encoded, binding={**self.binding, field: "other"})


if __name__ == "__main__":
    unittest.main()
