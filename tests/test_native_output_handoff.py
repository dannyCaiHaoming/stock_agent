import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.codex_hook_recorder import _capture_specialist_report
from product.runtime.eval_execution_proof import normalize_native_grade, collect_native_eval_output, persist_eval_execution_proof
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
        (self.root / "invocations" / f"{self.agent}.json").write_text(json.dumps(dict(self.binding, agent={"name": self.agent}, model="gpt-5.6-terra")))
        self.report = dict(self.binding, evidence_refs=["ev-exact-id"], thesis="中文原文，不改写")
        self.payload = {"agent_type": self.agent, "model": "gpt-5.6-terra", "last_assistant_message": json.dumps(self.report, ensure_ascii=False)}
        self.env = {"STOCK_AGENT_RUN_DIR": str(self.root)}

    def test_capture_exact_json_and_repeat(self):
        record = {}
        for _ in range(2):
            _capture_specialist_report(self.payload, record, self.env)
        saved = json.loads((self.root / "agents" / f"{self.agent}.json").read_text())
        self.assertEqual(saved, self.report)
        self.assertEqual(record["output_capture"]["output_hash"], canonical_hash(self.report))

    def test_no_reference_repair(self):
        self.report["evidence_refs"] = ["ev-exact-id|source", "unknown"]
        self.payload["last_assistant_message"] = json.dumps(self.report)
        _capture_specialist_report(self.payload, {}, self.env)
        self.assertEqual(json.loads((self.root / "agents" / f"{self.agent}.json").read_text()), self.report)

    def test_conflicting_output_not_overwritten(self):
        _capture_specialist_report(self.payload, {}, self.env)
        self.payload["last_assistant_message"] = json.dumps(dict(self.report, thesis="different"))
        with self.assertRaisesRegex(ValueError, "OUTPUT_EXISTS"):
            _capture_specialist_report(self.payload, {}, self.env)

    def test_invalid_json_identity_model_and_path(self):
        for payload in [dict(self.payload, last_assistant_message="not json"),
                        dict(self.payload, last_assistant_message=json.dumps(dict(self.report, run_id="other"))),
                        dict(self.payload, model="wrong")]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                _capture_specialist_report(payload, {}, self.env)
        (self.root / "agents").symlink_to(self.root / "invocations", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "PATH_INVALID"):
            _capture_specialist_report(self.payload, {}, self.env)


class NativeGradeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"semantic_output_delivery": "native-draft/1.0.0", "eval_id": "eval",
                         "source_hashes": {"grader_prompt": "a"*64, "rubric": "b"*64, "semantic_input": "c"*64}}
        self.draft = {"schema_version": "semantic-rubric-draft/1.0.0", "eval_id": "eval",
                      "dimensions": {name: {"status": "FAIL", "grade": 1, "evidence_refs": ["claim-1"], "rationale": "证据不足"} for name in SEMANTIC_DIMENSIONS}}

    def test_runtime_metadata_does_not_change_grades(self):
        before = copy.deepcopy(self.draft)
        result = normalize_native_grade(self.draft, self.manifest, model="gpt-5.6-terra")
        self.assertEqual(before, self.draft)
        self.assertEqual(result["dimensions"], self.draft["dimensions"])
        self.assertEqual(validate_semantic_result(result, eval_id="eval", input_manifest=self.manifest), result)

    def test_model_binding_shape_and_bad_grades_rejected(self):
        cases = [(dict(self.draft, eval_id="other"), "gpt-5.6-terra"),
                 (dict(self.draft, output_hash="bad"), "gpt-5.6-terra"),
                 (self.draft, "other-model"), (dict(self.draft, dimensions={}), "gpt-5.6-terra")]
        for value, model in cases:
            with self.subTest(model=model), self.assertRaises(ValueError):
                normalize_native_grade(value, self.manifest, model=model)

    def test_legacy_invalid_hash_never_repaired(self):
        result = normalize_native_grade(self.draft, self.manifest, model="gpt-5.6-terra")
        result["output_hash"] = "bad"
        legacy = dict(self.manifest)
        legacy.pop("semantic_output_delivery")
        self.assertEqual(normalize_native_grade(result, legacy, model="gpt-5.6-terra"), result)
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
            with self.assertRaises(FileExistsError):
                collect_native_eval_output(ROOT, eval_dir=job, semantic_result_path=output, parent_rollout=parent, child_rollout=child)


class SpecialistDraftTests(NativeOutputHandoffTests):
    def setUp(self):
        super().setUp()
        from product.runtime.invocation import SPECIALIST_DRAFT_DELIVERY
        (self.root / "run_manifest.json").write_text(json.dumps({"source_mode": "live", "specialist_output_delivery": SPECIALIST_DRAFT_DELIVERY}))
        self.invocation = dict(self.binding, agent={"name": self.agent}, model="gpt-5.6-terra",
                               skill_execution=[{"skill_name": "valuation", "version": "1", "invocation_hash": "a"*64}])
        (self.root / "invocations" / f"{self.agent}.json").write_text(json.dumps(self.invocation))

    def test_capture_exact_json_and_repeat(self):
        record = {}
        for _ in range(2):
            _capture_specialist_report(self.payload, record, self.env)
        raw = json.loads((self.root / "agents" / f"{self.agent}.native.json").read_text())
        saved = json.loads((self.root / "agents" / f"{self.agent}.json").read_text())
        self.assertEqual(raw, self.report)
        self.assertEqual(saved.pop("skill_execution"), self.invocation["skill_execution"])
        self.assertEqual(saved, raw)
        self.assertEqual(record["output_capture"]["raw_output_hash"], canonical_hash(raw))

    def test_no_reference_repair(self):
        self.report["evidence_refs"] = ["ev-exact-id|source", "unknown"]
        self.payload["last_assistant_message"] = json.dumps(self.report)
        _capture_specialist_report(self.payload, {}, self.env)
        saved = json.loads((self.root / "agents" / f"{self.agent}.json").read_text())
        self.assertEqual(saved["evidence_refs"], self.report["evidence_refs"])

    def test_model_supplied_metadata_rejected(self):
        from product.runtime.invocation import envelope_specialist_draft
        for draft in [dict(self.report, skill_execution=[]), dict(self.report, agent="runtime_cio"), dict(self.report, invocation_id="other")]:
            with self.subTest(draft=draft), self.assertRaisesRegex(ValueError, "DRAFT_BINDING_INVALID"):
                envelope_specialist_draft(draft, self.invocation, model="gpt-5.6-terra")

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
        self.assertEqual(event["output_capture"]["status"], "SAVED")
