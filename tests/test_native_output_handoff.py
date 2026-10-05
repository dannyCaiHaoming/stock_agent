import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.codex_hook_recorder import _capture_specialist_report
from product.runtime.eval_execution_proof import (
    _native_manifest_read,
    normalize_native_grade,
    collect_native_eval_output,
    persist_eval_execution_proof,
)
from product.runtime.hashing import canonical_hash
from product.runtime.runtime_eval import SEMANTIC_DIMENSIONS, validate_semantic_result


class NativeOutputHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "invocations").mkdir()
        self.agent = "runtime_company_analyst"
        self.binding = {"agent": self.agent, "run_id": "run", "invocation_id": "inv"}
        (self.root / "run_manifest.json").write_text(json.dumps({"source_mode": "live", "specialist_output_delivery": "native-final-json/1.0.0"}))
        (self.root / "invocations" / f"{self.agent}.json").write_text(json.dumps(dict(self.binding, agent={"name": self.agent}, model="gpt-6-luna")))
        self.report = dict(self.binding, evidence_refs=["ev-exact-id"], thesis="中文原文，不改写")
        self.payload = {"agent_type": self.agent, "model": "gpt-6-luna", "last_assistant_message": json.dumps(self.report, ensure_ascii=False)}
        self.env = {"STOCK_AGENT_RUN_DIR": str(self.root)}

    def test_legacy_capture_is_explicitly_retired(self):
        with self.assertRaisesRegex(ValueError, "SPECIALIST_LEGACY_OUTPUT_WRITE_RETIRED"):
            _capture_specialist_report(self.payload, {}, self.env)
        self.assertFalse((self.root / "agents").exists())

    def test_no_reference_repair(self):
        self.report["evidence_refs"] = ["ev-exact-id|source", "unknown"]
        self.payload["last_assistant_message"] = json.dumps(self.report)
        before = copy.deepcopy(self.report)
        with self.assertRaisesRegex(ValueError, "SPECIALIST_LEGACY_OUTPUT_WRITE_RETIRED"):
            _capture_specialist_report(self.payload, {}, self.env)
        self.assertEqual(before, self.report)
        self.assertFalse((self.root / "agents").exists())

    def test_conflicting_output_not_overwritten(self):
        (self.root / "agents").mkdir()
        path = self.root / "agents" / f"{self.agent}.json"
        path.write_text(json.dumps(self.report))
        before = path.read_bytes()
        self.payload["last_assistant_message"] = json.dumps(dict(self.report, thesis="different"))
        with self.assertRaisesRegex(ValueError, "SPECIALIST_LEGACY_OUTPUT_WRITE_RETIRED"):
            _capture_specialist_report(self.payload, {}, self.env)
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_json_identity_model_and_path(self):
        for payload in [dict(self.payload, last_assistant_message="not json"),
                        dict(self.payload, last_assistant_message=json.dumps(dict(self.report, run_id="other"))),
                        dict(self.payload, model="wrong")]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                _capture_specialist_report(payload, {}, self.env)
        (self.root / "agents").symlink_to(self.root / "invocations", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "SPECIALIST_LEGACY_OUTPUT_WRITE_RETIRED"):
            _capture_specialist_report(self.payload, {}, self.env)


class NativeGradeTests(unittest.TestCase):
    def test_manifest_read_proof_resolves_alias_but_rejects_other_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "input-manifest.json"
            manifest.write_text('{"eval_id":"actual"}\n', encoding="utf-8")
            alias = root / "manifest-alias.json"
            alias.symlink_to(manifest)
            other = root / "input-manifest.json.other"
            other.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")

            def read_records(source, *, output=None):
                return [
                    {"payload": {"type": "custom_tool_call", "call_id": "read-1", "input": f"cat {source}"}},
                    {"payload": {"type": "custom_tool_call_output", "call_id": "read-1",
                                 "output": [{"text": manifest.read_text(encoding="utf-8") if output is None else output}]}},
                ]

            self.assertTrue(_native_manifest_read(read_records(alias), manifest))
            self.assertFalse(_native_manifest_read(read_records(other), manifest))
            self.assertFalse(_native_manifest_read(read_records(alias, output="different"), manifest))
            wrapped = read_records(other)
            wrapped[0]["payload"]["input"] = json.dumps({
                "code": f"await tools.exec_command({{cmd: 'cat {manifest.resolve()}'}})"
            })
            self.assertTrue(_native_manifest_read(wrapped, manifest))

    def setUp(self):
        self.manifest = {"grader_model": "gpt-6-luna", "schema_version": "runtime-eval-input/1.1.0", "semantic_output_delivery": "native-draft/1.0.0", "eval_id": "eval",
                         "source_hashes": {"grader_prompt": "a"*64, "rubric": "b"*64, "semantic_input": "c"*64}}
        self.draft = {"schema_version": "semantic-rubric-draft/1.0.0", "eval_id": "eval",
                      "dimensions": {name: {"status": "FAIL", "grade": 1, "evidence_refs": ["claim-1"], "rationale": "证据不足"} for name in SEMANTIC_DIMENSIONS}}

    def test_runtime_metadata_does_not_change_grades(self):
        before = copy.deepcopy(self.draft)
        result = normalize_native_grade(self.draft, self.manifest, model="gpt-6-luna")
        self.assertEqual(before, self.draft)
        self.assertEqual(result["dimensions"], self.draft["dimensions"])
        self.assertEqual(validate_semantic_result(result, eval_id="eval", input_manifest=self.manifest), result)

    def test_runtime_eval_schema_rejects_non_string_reference(self):
        result = normalize_native_grade(self.draft, self.manifest, model="gpt-6-luna")
        result["dimensions"]["no_trade_reasoning"]["evidence_refs"] = [42]
        result["output_hash"] = canonical_hash({
            key: value for key, value in result.items() if key != "output_hash"
        })
        with self.assertRaisesRegex(ValueError, "SEMANTIC_RESULT_SCHEMA_INVALID"):
            validate_semantic_result(result, eval_id="eval", input_manifest=self.manifest)

    def test_model_binding_shape_and_bad_grades_rejected(self):
        cases = [(dict(self.draft, eval_id="other"), "gpt-6-luna"),
                 (dict(self.draft, output_hash="bad"), "gpt-6-luna"),
                 (self.draft, "other-model"), (dict(self.draft, dimensions={}), "gpt-6-luna")]
        for value, model in cases:
            with self.subTest(model=model), self.assertRaises(ValueError):
                normalize_native_grade(value, self.manifest, model=model)

    def test_legacy_invalid_hash_never_repaired(self):
        result = normalize_native_grade(self.draft, self.manifest, model="gpt-6-luna")
        result["output_hash"] = "bad"
        legacy = dict(self.manifest)
        legacy.pop("semantic_output_delivery")
        self.assertEqual(normalize_native_grade(result, legacy, model="gpt-6-luna"), result)
        with self.assertRaisesRegex(ValueError, "OUTPUT_HASH_INVALID"):
            validate_semantic_result(result, eval_id="eval", input_manifest=legacy)

    def test_native_collection_requires_real_read_and_preserves_failed_scores(self):
        from product.runtime.runtime_eval import prepare_eval_job, finalize_eval_job, semantic_output_schema, verify_runtime_eval_job
        from tests.test_replay_capsule import ROOT, complete_run
        from tests.test_eval_execution_proof import rollouts
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, job = root / "run", root / "eval"
            complete_run(run, "native-grade-test")
            prepare_eval_job(ROOT, run_dir=run, eval_dir=job, eval_id="eval")
            manifest_path = job / "input-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["semantic_output_delivery"] = "native-draft/1.0.0"
            schema = semantic_output_schema(ROOT, native_draft=True)
            manifest["source_hashes"]["semantic_output_schema"] = canonical_hash(schema)
            manifest_path.write_text(json.dumps(manifest))
            (job / "semantic-output-schema.json").write_text(json.dumps(schema))
            parent, child = rollouts(root, job, self.draft)
            records = [json.loads(line) for line in child.read_text().splitlines()]
            records[5:5] = [
                {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "read-manifest", "input": f"cat {manifest_path}"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "read-manifest", "output": [{"text": manifest_path.read_text()}]}},
            ]
            child.write_text("\n".join(json.dumps(x) for x in records) + "\n")
            output = job / "semantic-result.json"
            proof = collect_native_eval_output(ROOT, eval_dir=job, semantic_result_path=output, parent_rollout=parent, child_rollout=child)
            persist_eval_execution_proof(proof, eval_dir=job)
            result = finalize_eval_job(ROOT, eval_dir=job, semantic_result_path=output)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(json.loads((job / "semantic-native-draft.json").read_text()), self.draft)
            self.assertEqual(verify_runtime_eval_job(ROOT, eval_result_path=job / "eval/result.json")["status"], "FAIL")
            with self.assertRaisesRegex(ValueError, "EVAL_LOCAL_REVISION_NOT_AUTHORIZED"):
                collect_native_eval_output(ROOT, eval_dir=job, semantic_result_path=output, parent_rollout=parent, child_rollout=child)


class SpecialistDraftTests(NativeOutputHandoffTests):
    def setUp(self):
        super().setUp()
        from product.runtime.invocation import SPECIALIST_DRAFT_DELIVERY
        (self.root / "run_manifest.json").write_text(json.dumps({"source_mode": "live", "specialist_output_delivery": SPECIALIST_DRAFT_DELIVERY}))
        self.invocation = dict(self.binding, agent={"name": self.agent}, model="gpt-6-luna",
                               skill_execution=[{"skill_name": "valuation", "version": "1", "invocation_hash": "a"*64}])
        (self.root / "invocations" / f"{self.agent}.json").write_text(json.dumps(self.invocation))

    def test_historical_envelope_reader_preserves_exact_semantics(self):
        from product.runtime.invocation import envelope_specialist_draft
        original = copy.deepcopy(self.report)
        saved = envelope_specialist_draft(self.report, self.invocation, model="gpt-6-luna")
        self.assertEqual(saved.pop("skill_execution"), self.invocation["skill_execution"])
        self.assertEqual(saved, original)
        self.assertEqual(self.report, original)
        # 历史 envelope 的读取不自动修复旧引用；原业务 validator 仍负责拒绝。
        self.report["evidence_refs"] = ["ev-exact-id|source", "unknown"]
        self.assertEqual(envelope_specialist_draft(self.report, self.invocation, model="gpt-6-luna")["evidence_refs"],
                         self.report["evidence_refs"])

    def test_model_supplied_metadata_rejected(self):
        from product.runtime.invocation import envelope_specialist_draft
        for draft in [dict(self.report, skill_execution=[]), dict(self.report, agent="runtime_cio"), dict(self.report, invocation_id="other")]:
            with self.subTest(draft=draft), self.assertRaisesRegex(ValueError, "DRAFT_BINDING_INVALID"):
                envelope_specialist_draft(draft, self.invocation, model="gpt-6-luna")

    def test_standalone_hook_from_external_cwd(self):
        import os
        import subprocess
        import sys
        log = self.root / "invocation" / "subagent-events.jsonl"
        log.parent.mkdir()
        env = dict(os.environ, **self.env, STOCK_AGENT_SUBAGENT_EVENT_LOG=str(log),
                   STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT="native-research-draft/1.0.0")
        env.pop("PYTHONPATH", None)
        env.pop("STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS", None)
        payload = dict(self.payload, hook_event_name="SubagentStop", session_id="parent", turn_id="turn",
                       agent_id="child", cwd=str(self.root))
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "product/runtime/codex_hook_recorder.py")],
                                input=json.dumps(payload), text=True, capture_output=True, env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(log.read_text().splitlines()[-1])
        self.assertEqual(event["output_capture"]["status"], "FAILED")
        self.assertEqual(event["output_capture"]["failure_code"], "SPECIALIST_LEGACY_OUTPUT_WRITE_RETIRED")
        self.assertFalse((self.root / "agents").exists())
