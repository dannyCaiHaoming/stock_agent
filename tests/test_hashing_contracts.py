"""Versioned hash contracts and historical compatibility vectors."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from product.mcp.provenance import content_hash
from product.runtime.hashing import (
    CANONICAL_HASH_V2, HashContractError, canonical_hash, canonical_json_v2,
    envelope_hash, file_hash, legacy_envelope_hash, typed_hash, verify_typed_hash,
    verify_legacy_envelope_hash,
    legacy_provenance_json, legacy_provenance_hash,
    verify_legacy_object_hash, verify_file_hash, LEGACY_PROVENANCE_HASH,
)


class HashContractTests(unittest.TestCase):
    def test_legacy_object_and_byte_verifiers_require_declared_scope_and_algorithm(self) -> None:
        value = {"word": "证据", "value": Decimal("1.20")}
        digest = legacy_provenance_hash(value)
        verify_legacy_object_hash(value, digest, kind="fact-content", location="fact:one",
                                  algorithm=LEGACY_PROVENANCE_HASH)
        with self.assertRaisesRegex(HashContractError, "HASH_ALGORITHM_UNSUPPORTED:guessed:fact:one"):
            verify_legacy_object_hash(value, digest, kind="fact-content", location="fact:one", algorithm="guessed")
        with self.assertRaisesRegex(HashContractError, "HASH_KIND_UNSUPPORTED:file-bytes"):
            verify_legacy_object_hash({}, digest, kind="file-bytes", location="one.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.json"
            path.write_text('{"value": 1}\n', encoding="utf-8")
            original = path.read_bytes()
            verify_file_hash(path, file_hash(path), location="one.json")
            with self.assertRaisesRegex(HashContractError, "HASH_MISMATCH:file-bytes:sha256/1.0.0:one.json"):
                verify_file_hash(path, canonical_hash(json.loads(path.read_text())), location="one.json")
            self.assertEqual(original, path.read_bytes())
        with self.assertRaisesRegex(HashContractError, "HASH_MISMATCH:delivered-view:canonical-json/1.0.0:packet.json"):
            verify_legacy_object_hash({"value": 2}, canonical_hash({"value": 1}),
                                      kind="delivered-view", location="packet.json")

    def test_provenance_serializer_is_shared_and_old_scalar_vectors_are_unchanged(self) -> None:
        from product.mcp import provenance
        self.assertIs(provenance.canonical_json, legacy_provenance_json)
        self.assertIs(provenance.content_hash, legacy_provenance_hash)
        vectors = (
            (Decimal("1.20"), '"1.20"'),
            (date(2026, 9, 30), '"2026-09-30T00:00:00Z"'),
            (datetime(2026, 9, 30, 16, tzinfo=timezone(timedelta(hours=8))), '"2026-09-30T08:00:00Z"'),
            ({"否定": False, "值": 1.0}, '{"值":1.0,"否定":false}'),
        )
        for value, original_bytes in vectors:
            with self.subTest(value=value):
                self.assertEqual(provenance.canonical_json(value), original_bytes)
                self.assertEqual(provenance.content_hash(value), hashlib.sha256(original_bytes.encode()).hexdigest())
        with self.assertRaisesRegex(ValueError, "timestamps must include a timezone"):
            provenance.content_hash(datetime(2026, 9, 30))
        with self.assertRaises(TypeError):
            canonical_hash(Decimal("1.20"))

    def test_reference_map_hash_is_not_packet_object_hash_or_a_cross_version_guess(self) -> None:
        from product.runtime.multidimensional_references import build_reference_map, validate_reference_map
        packet = {"identity": {"run_id": "hash-seam-run", "invocation_id": "one"},
                  "allowed_evidence_ids": ["ev-中文"], "task": {"allowed_documents": []}}
        mapping = build_reference_map(packet, "a" * 64, "/tmp/frozen-hash-seam")
        original = json.loads(json.dumps(mapping))
        validate_reference_map(mapping)
        self.assertEqual(mapping["map_hash"], canonical_hash({k: v for k, v in mapping.items() if k != "map_hash"}))
        self.assertEqual(mapping["binding"]["packet_hash"], canonical_hash(packet))
        mapping["map_hash"] = canonical_hash(mapping)
        with self.assertRaisesRegex(ValueError,
                "MULTIDIMENSIONAL_REFERENCE_MAP_INVALID:HASH_MISMATCH:self-excluding-envelope:canonical-json/1.0.0:task/reference-map"):
            validate_reference_map(mapping)
        self.assertEqual(original["map_hash"], legacy_envelope_hash(original, hash_field="map_hash"))
        original["binding"]["version"] = "unregistered/1"
        with self.assertRaisesRegex(ValueError, "MULTIDIMENSIONAL_REFERENCE_MAP_INVALID"):
            validate_reference_map(original)

    def test_retained_eval_dispatch_record_uses_shared_envelope_not_whole_digest(self) -> None:
        from product.runtime.codex_hook_recorder import _dispatch_record
        payload = {"session_id": "parent", "turn_id": "turn", "tool_name": "spawn_agent",
                   "tool_use_id": "spawn-one", "cwd": "/tmp/frozen-hash-seam",
                   "tool_input": {"agent_type": "dev_eval"}}
        record = _dispatch_record(payload, decision="ALLOW")
        verify_legacy_envelope_hash(record, hash_field="event_hash", location="dispatch.jsonl")
        self.assertEqual(record["event_hash"], canonical_hash({k: v for k, v in record.items() if k != "event_hash"}))
        self.assertNotEqual(record["event_hash"], canonical_hash(record))
        with self.assertRaisesRegex(HashContractError, "dispatch.jsonl:field=event_hash"):
            verify_legacy_envelope_hash({**record, "decision": "DENY"}, hash_field="event_hash", location="dispatch.jsonl")

    def test_standalone_hook_loads_shared_hash_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-B", str(root / "product/runtime/codex_hook_recorder.py")],
            input="[]", text=True, capture_output=True, cwd=root / "product",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("HOOK_INPUT_NOT_OBJECT", result.stderr)

    def test_file_bytes_and_canonical_object_have_distinct_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item.json"
            path.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
            first_file_hash = file_hash(path)
            first_object_hash = typed_hash(json.loads(path.read_text()), kind="canonical-object")
            path.write_text('{"b":2,"a":1}', encoding="utf-8")
            self.assertNotEqual(first_file_hash, file_hash(path))
            self.assertEqual(first_object_hash, typed_hash(json.loads(path.read_text()), kind="canonical-object"))

    def test_kind_and_self_exclusion_do_not_collapse(self) -> None:
        body = {"payload": {"x": 1, "envelope_hash": "nested"}, "other_hash": "kept"}
        digest = envelope_hash(body, hash_field="envelope_hash")
        self.assertEqual(digest, envelope_hash({**body, "envelope_hash": "ignored"}, hash_field="envelope_hash"))
        self.assertNotEqual(digest, typed_hash(body, kind="canonical-object"))
        self.assertNotEqual(digest, envelope_hash(body, hash_field="other_hash"))
        self.assertNotEqual(digest, envelope_hash({**body, "other_hash": "changed"}, hash_field="envelope_hash"))
        self.assertNotEqual(digest, envelope_hash({"payload": {"x": 2}}, hash_field="envelope_hash"))
        with self.assertRaisesRegex(HashContractError, "HASH_KIND_UNSUPPORTED"):
            typed_hash(body, kind="file-bytes")

    def test_decimal_time_numeric_and_unicode_are_explicit(self) -> None:
        instant = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
        same_instant = datetime(2026, 9, 30, 16, 0, tzinfo=timezone(timedelta(hours=8)))
        first = {"d": Decimal("1.20"), "at": instant, "day": date(2026, 9, 30), "word": "é"}
        second = {"word": "é", "day": date(2026, 9, 30), "at": same_instant, "d": Decimal("1.20")}
        self.assertEqual(canonical_json_v2(first), canonical_json_v2(second))
        self.assertNotEqual(typed_hash(first, kind="canonical-object"), typed_hash({**first, "d": "1.20"}, kind="canonical-object"))
        self.assertNotEqual(typed_hash(first, kind="canonical-object"), typed_hash({**first, "word": "e\u0301"}, kind="canonical-object"))
        self.assertNotEqual(typed_hash(1, kind="canonical-object"), typed_hash(True, kind="canonical-object"))
        self.assertNotEqual(typed_hash(1, kind="canonical-object"), typed_hash(1.0, kind="canonical-object"))

    def test_invalid_value_is_located_and_nonfinite_is_rejected(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf, Decimal("NaN"), Decimal("Infinity")):
            with self.assertRaisesRegex(HashContractError, r"HASH_VALUE_NONFINITE:\$\.claim\[0\]"):
                typed_hash({"claim": [invalid]}, kind="canonical-object")
        with self.assertRaisesRegex(HashContractError, r"HASH_TIMEZONE_REQUIRED:\$\.at"):
            typed_hash({"at": datetime(2026, 9, 30)}, kind="canonical-object")
        with self.assertRaisesRegex(HashContractError, r"HASH_OBJECT_KEY_INVALID:\$"):
            typed_hash({1: "value"}, kind="canonical-object")
        with self.assertRaisesRegex(HashContractError, r"HASH_UNICODE_INVALID:\$\.claim"):
            typed_hash({"claim": "\ud800"}, kind="canonical-object")
        with self.assertRaisesRegex(HashContractError, r"HASH_UNICODE_INVALID:\$"):
            typed_hash({"\ud800": "value"}, kind="canonical-object")

    def test_verifier_names_type_version_and_location(self) -> None:
        value = {"x": 1}
        digest = typed_hash(value, kind="delivered-view")
        verify_typed_hash(value, digest, kind="delivered-view", location="research/view.json")
        with self.assertRaisesRegex(
            HashContractError,
            f"HASH_MISMATCH:fact-content:{CANONICAL_HASH_V2}:research/view.json",
        ):
            verify_typed_hash(value, digest, kind="fact-content", location="research/view.json")

    def test_historical_hash_vectors_stay_byte_compatible(self) -> None:
        legacy_bytes = '{"name":"价格","value":1}'
        expected = hashlib.sha256(legacy_bytes.encode("utf-8")).hexdigest()
        value = {"value": 1, "name": "价格"}
        self.assertEqual(expected, canonical_hash(value))
        self.assertEqual(expected, content_hash(value))
        self.assertNotEqual(expected, typed_hash(value, kind="canonical-object"))
        self.assertEqual(
            "5c01d9c7c03128efa96401e6652b48f1baa7c5ae5829f439e1537aef2f8b759e",
            typed_hash(value, kind="canonical-object"),
        )
        self.assertEqual(
            expected, legacy_envelope_hash({**value, "content_hash": "ignored"}, hash_field="content_hash"),
        )

    def test_legacy_envelope_diagnostic_names_actual_scope_without_rewriting(self) -> None:
        body = {"value": {"input_hash": "nested-kept"}, "other_hash": "also-kept"}
        digest = legacy_envelope_hash(body, hash_field="input_hash")
        value = {**body, "input_hash": digest}
        verify_legacy_envelope_hash(value, hash_field="input_hash", location="input-manifest.json")
        with self.assertRaisesRegex(
            HashContractError,
            "HASH_MISMATCH:self-excluding-envelope:canonical-json/1.0.0:input-manifest.json:field=input_hash",
        ):
            verify_legacy_envelope_hash({**value, "other_hash": "changed"}, hash_field="input_hash",
                                        location="input-manifest.json")
        self.assertEqual(value["input_hash"], digest)

    def test_actual_report_and_bundle_producers_keep_legacy_digest_and_consumer_scope(self) -> None:
        from tests import test_multidimensional_research_contracts as fixtures
        from product.council.multidimensional_research import (
            finalize_research_dimension_report, finalize_holding_research_bundle,
            validate_research_dimension_report, MultiDimensionalResearchError,
        )
        report = fixtures._report()
        original = json.dumps(report, ensure_ascii=False, sort_keys=True)
        produced = finalize_research_dimension_report(report)
        expected = canonical_hash({k: v for k, v in report.items() if k != "report_hash"})
        self.assertEqual(produced["report_hash"], expected)
        self.assertEqual(json.dumps(report, ensure_ascii=False, sort_keys=True), original)
        validate_research_dimension_report(produced, expected_bindings=fixtures.BINDINGS,
            allowed_security_ids=fixtures.SECURITIES, allowed_evidence_ids=["ev-price-1"])
        bundle = fixtures._bundle(produced)
        self.assertEqual(finalize_holding_research_bundle(bundle)["bundle_hash"],
                         canonical_hash({k: v for k, v in bundle.items() if k != "bundle_hash"}))
        # 完整报告摘要（包含其 report_hash）不能代替顶层排除自身字段的摘要。
        produced["report_hash"] = canonical_hash(produced)
        with self.assertRaisesRegex(MultiDimensionalResearchError,
                "DIMENSION_REPORT_HASH_MISMATCH:HASH_MISMATCH:self-excluding-envelope:canonical-json/1.0.0:research-dimension-report:"):
            validate_research_dimension_report(produced, expected_bindings=fixtures.BINDINGS,
                allowed_security_ids=fixtures.SECURITIES, allowed_evidence_ids=["ev-price-1"])


if __name__ == "__main__":
    unittest.main()
