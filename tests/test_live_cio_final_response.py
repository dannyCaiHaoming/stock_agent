"""CIO 原生最终响应接缝；模型返回为合成数据，不替代真实 Smoke。"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.invocation import build_live_cio_decoding_schema, build_live_cio_output_schema
from product.runtime.nested_codex import _persist_cio_final_response, launch_nested_codex
from product.runtime.run_package import prepare_cio, finalize_cio
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.smoke_prompt import build_smoke_prompt
from tests.test_live_eval_contract import synthetic_run, REFS
from tests.test_native_run_package import cio_output, read_json

ROOT = Path(__file__).resolve().parents[1]


def final_events(text):
    return [{"type": "thread.started", "thread_id": "synthetic-parent"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}]


class LiveCioFinalResponseTests(unittest.TestCase):
    def prepared(self, directory):
        run = synthetic_run(Path(directory), stop_before_cio=True)
        model = read_json(run / "run_manifest.json")["model"]
        result = prepare_cio(ROOT, run_dir=run, model=model)
        self.assertEqual(result["next_state"], "CIO_SYNTHESIS_REQUIRED")
        draft = cio_output(run)
        draft.update(action="NO_TRADE", security_id="TEST", evidence_refs=REFS,
                     target_weight_range=None, maximum_notional=None,
                     no_trade_reason="INSUFFICIENT_EVIDENCE",
                     no_trade_explanation="合成客户续约披露不足。",
                     reevaluation_conditions=["下一份续约披露"])
        return run, draft

    def test_decoder_is_projection_not_replacement_of_canonical_contract(self):
        canonical = build_live_cio_output_schema(ROOT)
        before = deepcopy(canonical)
        schema = build_live_cio_decoding_schema(ROOT, run_id="synthetic", allowed_evidence_ids=REFS)
        self.assertEqual(build_live_cio_output_schema(ROOT), before)
        self.assertEqual(schema["required"], canonical["required"])
        self.assertEqual(set(schema["properties"]), set(canonical["properties"]))
        self.assertIn("allOf", canonical)

        def check(node):
            for unsupported in ("allOf", "if", "then", "not", "uniqueItems", "const"):
                self.assertNotIn(unsupported, node)
            self.assertIn("type", node)
            if node["type"] == "object":
                self.assertFalse(node["additionalProperties"])
                self.assertEqual(set(node["required"]), set(node["properties"]))
            for child in node.get("properties", {}).values():
                check(child)
            if "array" in ([node["type"]] if isinstance(node["type"], str) else node["type"]):
                check(node["items"])
        check(schema)

    def test_reference_enum_rejects_typos_and_decorations_at_both_locations(self):
        original = "ev-yahoo-c5336d9cb5a05e53be04b0f076c6c3687d8e7712c350187f78792c127ca88e79"
        typo = "ev-yahoo-c5336d9cb5a05e53dbe04b0f076c6c3687d8e7712c350187f78792c127ca88e79"
        schema = build_live_cio_decoding_schema(ROOT, run_id="synthetic", allowed_evidence_ids=[original, "other"])
        fields = [schema["properties"]["evidence_refs"],
                  schema["properties"]["conflicts"]["items"]["properties"]["evidence_refs"]]
        for field in fields:
            validate_schema_instance([original, "other"], field)
            for invalid in (typo, original + "|source", original + "|as_of=2026-09-10", "missing"):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "SCHEMA_ENUM_INVALID"):
                    validate_schema_instance([invalid, "other"], field)

    def test_final_response_is_saved_byte_for_byte_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            text = '{"thesis": "中文原文", "evidence_refs": ["typo|source"]}\n'
            _persist_cio_final_response(run, text, final_events(text))
            self.assertEqual((run / "cio/runtime_cio.json").read_text(), text)
            with self.assertRaises(FileExistsError):
                _persist_cio_final_response(run, text, final_events(text))

    def test_large_gate_uses_the_same_exact_set_without_truncating_ids(self):
        ids = [f"ev-sec-{index:064x}" for index in range(300)]
        schema = build_live_cio_decoding_schema(ROOT, run_id="synthetic", allowed_evidence_ids=ids)
        item = schema["properties"]["evidence_refs"]["items"]
        self.assertIn("pattern", item)
        for evidence_id in ids:
            validate_schema_instance(evidence_id, item)
        with self.assertRaisesRegex(ValueError, "SCHEMA_PATTERN_INVALID"):
            validate_schema_instance(ids[-1] + "d", item)

    def test_missing_malformed_or_unbound_final_response_is_not_saved(self):
        for text, events in (("{}", []), ("{}", final_events("different")),
                             ("not json", final_events("not json")), ("[]", final_events("[]")),
                             ('{"action":"HOLD","action":"EXIT"}',
                              final_events('{"action":"HOLD","action":"EXIT"}'))):
            with self.subTest(text=text, events=events), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    _persist_cio_final_response(Path(directory), text, events)
                self.assertFalse((Path(directory) / "cio/runtime_cio.json").exists())

    def test_canonical_validation_still_rejects_illegal_no_trade_and_reference(self):
        for mutation in ({"maximum_notional": 0}, {"target_weight_range": [0, 0]},
                         {"evidence_refs": ["price|source"]}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                run, draft = self.prepared(directory)
                draft.update(mutation)
                text = json.dumps(draft)
                _persist_cio_final_response(run, text, final_events(text))
                finalize_cio(ROOT, run_dir=run)
                trace = read_json(run / "decision_trace.json")
                self.assertEqual(trace["terminal_state"], "FAILED_VALIDATION")
                self.assertEqual(trace["failed_stage"], "CIO_VALIDATION")
                self.assertEqual(trace["risk_lineage"], [])
                self.assertFalse((run / "decision.json").exists())

    def test_native_handoff_prompt_is_explicit_and_default_remains_file_based(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = self.prepared(directory)
            prompt = build_smoke_prompt(run, repository_root=ROOT,
                                        defer_deterministic_finalize=True, final_response_cio=True)
            self.assertIn("--output-schema", prompt)
            self.assertNotIn("CIO_DRAFT_READY_FOR_DETERMINISTIC_FINALIZATION", prompt)
            default = build_smoke_prompt(run, repository_root=ROOT, defer_deterministic_finalize=True)
            self.assertIn("CIO_DRAFT_READY_FOR_DETERMINISTIC_FINALIZATION", default)

    def test_launcher_passes_schema_and_valid_response_reaches_existing_risk(self):
        with tempfile.TemporaryDirectory() as directory:
            run, draft = self.prepared(directory)
            text = json.dumps(draft, ensure_ascii=False)

            def fake_process(command, **kwargs):
                schema_path = Path(command[command.index("--output-schema") + 1])
                validate_schema_instance(draft, read_json(schema_path))
                self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
                Path(command[command.index("--output-last-message") + 1]).write_text(text)
                for event in final_events(text):
                    kwargs["stdout"].write(json.dumps(event) + "\n")
                return subprocess.CompletedProcess(command, 0)

            with patch("product.runtime.nested_codex.subprocess.run", side_effect=fake_process), patch(
                "product.runtime.nested_codex.build_ephemeral_run_specialist_execution_proof",
                return_value={"status": "SYNTHETIC_TEST_ONLY"}
            ):
                result, _ = launch_nested_codex(ROOT, run_dir=run)
            self.assertIsNotNone(result["deterministic_continuation"]["risk_finalization"])
            self.assertEqual((run / "cio/runtime_cio.json").read_text(), text)
            self.assertTrue((run / "decision.json").is_file())
            self.assertTrue(read_json(run / "decision_trace.json")["risk_lineage"])
            environment = read_json(run / "invocation/environment-manifest.json")
            from product.runtime.hashing import file_hash
            self.assertEqual(environment["resource_hashes"]["cio_decoding_schema"],
                             file_hash(run / "invocation/cio-output.schema.json"))

    def test_zero_exit_with_missing_final_event_fails_before_proof_and_risk(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = self.prepared(directory)

            def fake_process(command, **kwargs):
                kwargs["stdout"].write('{"type":"turn.completed"}\n')
                return subprocess.CompletedProcess(command, 0)

            with patch("product.runtime.nested_codex.subprocess.run", side_effect=fake_process), patch(
                "product.runtime.nested_codex.build_ephemeral_run_specialist_execution_proof"
            ) as proof, patch("product.runtime.nested_codex.finalize_cio") as risk:
                result, code = launch_nested_codex(ROOT, run_dir=run)
            self.assertNotEqual(code, 0)
            self.assertIn("CIO_FINAL_EVENT_MISMATCH", result["failure_code"])
            proof.assert_not_called()
            risk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
