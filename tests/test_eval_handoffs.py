"""两类 Eval 的语义草稿/可信装配接缝，不执行评分模型。"""

from __future__ import annotations

import copy
import json
import tempfile
import shlex
import sys
import unittest
from pathlib import Path

from product.runtime import common_stock_eval as common
from product.runtime.eval_execution_proof import (
    EvalExecutionProofError, collect_native_eval_output, normalize_native_grade, _native_manifest_read,
)
from product.runtime.hashing import canonical_hash
from product.runtime.hashing import legacy_envelope_hash
from product.runtime.runtime_eval import prepare_eval_job, build_eval_smoke_prompt
from tests import test_common_stock_research_contracts as stock_fixtures
from tests import test_eval_execution_proof as eval_fixtures
from tests import test_runtime_eval_job as runtime_fixtures
from tests.test_replay_capsule import complete_run, ROOT


class EvalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def stock_job(self):
        return stock_fixtures.CommonStockFocusedEvalTests().prepare_job(self.temp.name)

    def test_common_envelope_keeps_grade_rationale_refs_and_historical_reader(self):
        _, _, directory, manifest = self.stock_job()
        draft = stock_fixtures.CommonStockFocusedEvalTests.semantic_draft(manifest, failing={"valuation_grounding"})
        path = self.root / "draft.json"
        path.write_text(json.dumps(draft))
        result = common.finalize_common_stock_eval_job(
            eval_dir=directory, semantic_result_path=path,
            actual_model="test-adapter-model", input_binding_hash=manifest["input_hash"])
        self.assertEqual(result["dimensions"], draft["dimensions"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["input_hash"], manifest["input_hash"])
        self.assertEqual(result["model"], "test-adapter-model")
        common.validate_common_stock_eval_result(result, manifest=manifest)
        self.assertEqual(json.loads(path.read_text()), draft)

    def test_common_rejects_wrong_input_and_missing_model_without_publishing(self):
        _, _, directory, manifest = self.stock_job()
        path = self.root / "draft.json"
        path.write_text(json.dumps(stock_fixtures.CommonStockFocusedEvalTests.semantic_draft(manifest)))
        for model, digest, error in ((None, manifest["input_hash"], "MODEL_PROOF_MISSING"),
                                      ("test-model", "0" * 64, "INPUT_BINDING_INVALID")):
            with self.subTest(error=error), self.assertRaisesRegex(common.CommonStockEvalError, error):
                common.finalize_common_stock_eval_job(eval_dir=directory, semantic_result_path=path,
                                                      actual_model=model, input_binding_hash=digest)
        manifest["rubric_id"] = "different-rubric"
        (directory / "input-manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(common.CommonStockEvalError, "INPUT_HASH_INVALID"):
            common.finalize_common_stock_eval_job(eval_dir=directory, semantic_result_path=path,
                                                  actual_model="test-model", input_binding_hash=manifest["input_hash"])
        self.assertFalse((directory / "eval/result.json").exists())

    def test_common_legacy_full_output_is_readable_but_rejected_for_new_write(self):
        _, _, directory, manifest = self.stock_job()
        formal = stock_fixtures.CommonStockFocusedEvalTests.semantic_result(manifest)
        common.validate_common_stock_eval_result(formal, manifest=manifest)
        path = self.root / "legacy-result.json"
        path.write_text(json.dumps(formal))
        with self.assertRaisesRegex(common.CommonStockEvalError, "RESULT_SCHEMA_INVALID"):
            common.finalize_common_stock_eval_job(eval_dir=directory, semantic_result_path=path,
                                                  actual_model=formal["model"], input_binding_hash=manifest["input_hash"])
        self.assertFalse((directory / "eval/result.json").exists())

    def test_common_hash_diagnostic_names_contract_and_path_without_repair(self):
        _, _, directory, manifest = self.stock_job()
        draft = stock_fixtures.CommonStockFocusedEvalTests.semantic_draft(manifest)
        result = common.envelope_common_stock_eval_draft(
            draft, manifest=manifest, actual_model="test-model", input_binding_hash=manifest["input_hash"])
        self.assertEqual(result["result_hash"], legacy_envelope_hash(result, hash_field="result_hash"))
        original = result["result_hash"]
        result["dimensions"][common.DIMENSIONS[0]]["rationale"] += "改动原稿"
        with self.assertRaisesRegex(common.CommonStockEvalError,
                                   "RESULT_HASH_INVALID:HASH_MISMATCH:self-excluding-envelope:canonical-json/1.0.0:eval/result.json"):
            common.validate_common_stock_eval_result(result, manifest=manifest)
        self.assertEqual(result["result_hash"], original)

    def runtime_job(self):
        run, evaluation = self.root / "run", self.root / "eval"
        complete_run(run, "native-eval-input")
        prepare_eval_job(ROOT, run_dir=run, eval_dir=evaluation, eval_id="native-eval")
        manifest = json.loads((evaluation / "input-manifest.json").read_text())
        result = runtime_fixtures.semantic_result(evaluation)
        result["grader"]["model"] = "gpt-5.6-terra"
        result["output_hash"] = canonical_hash({k: v for k, v in result.items() if k != "output_hash"})
        return evaluation, manifest, result

    def test_fixture_runtime_also_uses_native_draft_and_real_input_read(self):
        directory, manifest, result = self.runtime_job()
        self.assertEqual(manifest["semantic_output_delivery"], "native-draft/1.0.0")
        schema = json.loads((directory / "semantic-output-schema.json").read_text())
        self.assertEqual(set(schema["properties"]), {"schema_version", "eval_id", "dimensions"})
        parent, child = eval_fixtures.rollouts(self.root, directory, result, plaintext_bindings=False)
        proof = collect_native_eval_output(ROOT, eval_dir=directory,
                                          semantic_result_path=directory / "semantic-result.json",
                                          parent_rollout=parent, child_rollout=child)
        saved = json.loads((directory / "semantic-result.json").read_text())
        raw = json.loads((directory / "semantic-native-draft.json").read_text())
        self.assertEqual(saved, result)
        self.assertEqual(raw["dimensions"], result["dimensions"])
        self.assertEqual(proof["task_binding_method"], "native_manifest_read")
        prompt = build_eval_smoke_prompt(ROOT, eval_dir=directory)
        self.assertNotIn(manifest["source_hashes"]["grader_prompt"], prompt)
        self.assertNotIn(manifest["source_hashes"]["rubric"], prompt)
        self.assertIn(f"{shlex.quote(sys.executable)} -B -m product.runtime.cli eval-execution-proof", prompt)
        self.assertIn(f"{shlex.quote(sys.executable)} -B -m product.runtime.cli eval-finalize", prompt)

    def test_manifest_read_from_real_js_wrapper_requires_exact_path_and_full_output(self):
        path = self.root / "Application Support" / "input-manifest.json"
        path.parent.mkdir()
        path.write_text('{"eval_id":"bound-input","source_hashes":{"input":"abc"}}\n')
        def records(command, output):
            wrapped = "const r = await tools.exec_command(" + json.dumps({"cmd": command}) + "); text(r.output);"
            return [{"payload": {"type": "custom_tool_call", "call_id": "read", "input": wrapped}},
                    {"payload": {"type": "custom_tool_call_output", "call_id": "read",
                                 "output": [{"type": "input_text", "text": output}]}}]
        # 与真实宿主包一致：JSON/JS 包裹、shell 转义空格、多块工具输出。
        command = "cat " + str(path).replace(" ", "\\ ")
        self.assertTrue(_native_manifest_read(records(command, path.read_text()), path))
        self.assertTrue(_native_manifest_read(records("cat " + shlex.quote(str(path)), path.read_text()), path))
        self.assertFalse(_native_manifest_read(records(command + ".backup", path.read_text()), path))
        self.assertFalse(_native_manifest_read(records(command, '{"eval_id":"bound-input"}'), path))
        self.assertFalse(_native_manifest_read(records("cat " + shlex.quote(str(self.root / "other.json")), path.read_text()), path))

    def test_runtime_wrong_model_and_metadata_in_draft_are_rejected(self):
        _, manifest, result = self.runtime_job()
        draft = {"schema_version": "semantic-rubric-draft/1.0.0", "eval_id": manifest["eval_id"],
                 "dimensions": copy.deepcopy(result["dimensions"])}
        for candidate, model in ((draft, "gpt-5.6-sol"), ({**draft, "output_hash": "0" * 64}, "gpt-5.6-terra"),
                                  ({**draft, "eval_id": "another-job"}, "gpt-5.6-terra")):
            with self.subTest(model=model, fields=list(candidate)), self.assertRaises(EvalExecutionProofError):
                normalize_native_grade(candidate, manifest, model=model)

    def test_runtime_historical_result_stays_readable_but_native_execution_is_retired(self):
        from product.runtime.runtime_eval import validate_semantic_result, RuntimeEvalError
        directory, manifest, result = self.runtime_job()
        manifest.pop("semantic_output_delivery")
        source = directory / "input-manifest.json"
        source.write_text(json.dumps(manifest))
        original = source.read_bytes()
        # 历史完整结果只读验证；不能把它当当前模型输出或新执行许可。
        self.assertEqual(validate_semantic_result(result, eval_id=manifest["eval_id"],
                                                  input_manifest=manifest), result)
        with self.assertRaisesRegex(RuntimeEvalError, "EVAL_LEGACY_WRITE_RETIRED"):
            build_eval_smoke_prompt(ROOT, eval_dir=directory)
        # 旧 normalizer 是纯读取兼容函数；执行拒绝由实际提示/收集入口负责。
        self.assertEqual(normalize_native_grade(result, manifest, model="gpt-5.6-terra"), result)
        with self.assertRaisesRegex(EvalExecutionProofError, "EVAL_NATIVE_COLLECTION_NOT_ENABLED"):
            collect_native_eval_output(ROOT, eval_dir=directory,
                semantic_result_path=directory / "semantic-result.json",
                parent_rollout=self.root / "not-executed-parent.jsonl",
                child_rollout=self.root / "not-executed-child.jsonl")
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((directory / "semantic-native-draft.json").exists())
        self.assertFalse((directory / "semantic-result.json").exists())
