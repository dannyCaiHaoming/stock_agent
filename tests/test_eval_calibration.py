from __future__ import annotations

import copy
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from evals.grading.calibration import (
    EXPECTED_CALIBRATION_GRADER,
    build_calibration_execution_proof,
    evaluate_calibration,
    run_calibration,
    verify_calibration_result,
)
from product.runtime.hashing import canonical_hash, file_hash
from tests.test_native_execution_proof import message, write_jsonl


ROOT = Path(__file__).resolve().parents[1]


def execution_proof_record(root: Path, case_id: str, repeat: int, output_path: Path, *, session_id: str | None = None) -> dict:
    parent_id = f"calibration-parent-{case_id}-{repeat}"
    child_id = session_id or f"calibration-child-{case_id}-{repeat}"
    prompt_path = root / "inputs" / case_id / f"prompt-{repeat}.txt"
    input_path = root / "inputs" / case_id / f"input-{repeat}.json"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(f"calibration:{case_id}:{repeat}\n", encoding="utf-8")
    input_path.write_text(
        json.dumps({"input": case_id, "repeat": repeat}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt_hash = canonical_hash({"prompt": prompt_path.read_text(encoding="utf-8").rstrip("\n")})
    input_hash = canonical_hash(json.loads(input_path.read_text(encoding="utf-8")))
    with (ROOT / ".codex" / "agents" / "dev_eval.toml").open("rb") as handle:
        instructions = tomllib.load(handle)["developer_instructions"]
    output = json.loads(output_path.read_text(encoding="utf-8"))
    parent = [
        {"timestamp": f"2026-09-07T00:00:0{repeat}Z", "type": "session_meta", "payload": {"id": parent_id}},
        message("user", f"case_id={case_id} prompt={prompt_hash} input={input_hash}"),
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        {"type": "response_item", "payload": {"type": "function_call", "namespace": "collaboration", "name": "spawn_agent", "call_id": f"call-{repeat}", "arguments": json.dumps({"agent_type": "dev_eval", "task_name": "semantic_grading", "fork_turns": "none", "message": "gAAAA" + "A" * 120})}},
    ]
    child = [
        {"timestamp": f"2026-09-07T00:00:1{repeat}Z", "type": "session_meta", "payload": {"id": child_id, "parent_thread_id": parent_id, "agent_role": "dev_eval"}},
        message("developer", f"runtime\n{instructions}\nend"),
        message("user", f"case_id={case_id} prompt={prompt_hash} input={input_hash}"),
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        message("assistant", json.dumps(output, sort_keys=True)),
    ]
    rollout_dir = root / "rollouts" / case_id / str(repeat)
    rollout_dir.mkdir(parents=True, exist_ok=True)
    parent_path, child_path = rollout_dir / "parent.jsonl", rollout_dir / "child.jsonl"
    write_jsonl(parent_path, parent)
    write_jsonl(child_path, child)
    proof = build_calibration_execution_proof(
        ROOT,
        case_id=case_id,
        repeat=repeat,
        grader_output_path=output_path,
        parent_rollout=parent_path,
        child_rollout=child_path,
        prompt_path=prompt_path,
        input_path=input_path,
    )
    proof_path = root / "proofs" / case_id / f"{repeat}.json"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    return {"path": str(proof_path), "sha256": file_hash(proof_path)}


class EvalCalibrationTests(unittest.TestCase):
    def test_execution_proof_recomputes_bound_prompt_and_input_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = {
                "schema_version": "semantic-rubric-result/1.0.0",
                "eval_id": "bound-inputs",
                "grader": EXPECTED_CALIBRATION_GRADER,
                "dimensions": {},
            }
            value["output_hash"] = canonical_hash(value)
            output = root / "output.json"
            output.write_text(json.dumps(value), encoding="utf-8")
            record = execution_proof_record(root, "bound-inputs", 1, output)
            proof_path = Path(record["path"])
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            Path(proof["input_artifact"]["path"]).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "EXECUTION_SOURCE_INVALID"):
                from evals.grading.calibration import verify_calibration_execution_proof

                verify_calibration_execution_proof(
                    ROOT,
                    proof_path=proof_path,
                    case_id="bound-inputs",
                    repeat=1,
                    grader_output_path=output,
                )

    def test_repeated_grades_must_match_human_ranges_and_be_stable(self):
        labels = json.loads(
            (ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json").read_text(encoding="utf-8")
        )
        grader_runs = {}
        for case in labels["cases"]:
            dimensions = {
                name: {
                    "status": expected["status"],
                    "grade": expected["grade_min"],
                }
                for name, expected in case["human_labels"].items()
            }
            grader_runs[case["case_id"]] = [{"dimensions": dimensions}, {"dimensions": dimensions}]
        result = evaluate_calibration(labels, grader_runs=grader_runs)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["agreement"], 1.0)

    def test_unstable_repeats_fail_even_when_one_grade_matches(self):
        labels = json.loads(
            (ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json").read_text(encoding="utf-8")
        )
        grader_runs = {}
        for case in labels["cases"]:
            first = {}
            second = {}
            for name, expected in case["human_labels"].items():
                first[name] = {"status": expected["status"], "grade": expected["grade_min"]}
                second[name] = dict(first[name])
            grader_runs[case["case_id"]] = [{"dimensions": first}, {"dimensions": second}]
        grader_runs[labels["cases"][0]["case_id"]][1]["dimensions"]["analyst_thesis_grounding"] = {
            "status": "FAIL",
            "grade": 0,
        }
        result = evaluate_calibration(labels, grader_runs=grader_runs)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["unstable_dimensions"])

    def test_not_applicable_against_numeric_human_range_is_a_mismatch_not_an_exception(self):
        labels = json.loads(
            (ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json").read_text(encoding="utf-8")
        )
        grader_runs = {}
        for case in labels["cases"]:
            dimensions = {
                name: {"status": expected["status"], "grade": expected["grade_min"]}
                for name, expected in case["human_labels"].items()
            }
            grader_runs[case["case_id"]] = [{"dimensions": copy.deepcopy(dimensions)}, {"dimensions": copy.deepcopy(dimensions)}]
        grader_runs["grounded-balanced"][0]["dimensions"]["confidence_calibration"] = {
            "status": "NOT_APPLICABLE",
            "grade": None,
        }
        result = evaluate_calibration(labels, grader_runs=grader_runs)
        self.assertEqual(result["status"], "FAIL")
        self.assertLess(result["agreement"], 1.0)

    def test_calibration_runner_binds_repeated_outputs_and_writes_report(self):
        labels_path = ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {}
            for case in labels["cases"]:
                records = []
                dimensions = {
                    name: {"status": expected["status"], "grade": expected["grade_min"]}
                    for name, expected in case["human_labels"].items()
                }
                for repeat in (1, 2):
                    value = {
                        "schema_version": "semantic-rubric-result/1.0.0",
                        "eval_id": f"{case['case_id']}-{repeat}",
                        "grader": EXPECTED_CALIBRATION_GRADER,
                        "dimensions": dimensions,
                    }
                    value["output_hash"] = canonical_hash(value)
                    path = root / f"{case['case_id']}-{repeat}.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    records.append({
                        "path": str(path),
                        "sha256": file_hash(path),
                        "execution_proof": execution_proof_record(root, case["case_id"], repeat, path),
                    })
                cases[case["case_id"]] = records
            index_path = root / "index.json"
            index_path.write_text(
                json.dumps({"schema_version": "semantic-calibration-index/1.0.0", "cases": cases}),
                encoding="utf-8",
            )
            result = run_calibration(
                ROOT,
                labels_path=labels_path,
                grader_index_path=index_path,
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["session_ids"]), len(labels["cases"]) * 2)
            self.assertTrue((root / "out" / "report.md").is_file())
            self.assertEqual(verify_calibration_result(ROOT, root / "out" / "result.json"), result)

    def test_calibration_runner_rejects_unattributed_static_grader_output(self):
        labels_path = ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {}
            for case in labels["cases"]:
                dimensions = {
                    name: {"status": expected["status"], "grade": expected["grade_min"]}
                    for name, expected in case["human_labels"].items()
                }
                records = []
                for repeat in (1, 2):
                    value = {
                        "schema_version": "semantic-rubric-result/1.0.0",
                        "eval_id": f"{case['case_id']}-{repeat}",
                        "grader": {},
                        "dimensions": dimensions,
                    }
                    value["output_hash"] = canonical_hash(value)
                    path = root / f"{case['case_id']}-{repeat}.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    records.append({
                        "path": str(path),
                        "sha256": file_hash(path),
                        "execution_proof": {"path": str(path), "sha256": file_hash(path)},
                    })
                cases[case["case_id"]] = records
            index_path = root / "index.json"
            index_path.write_text(
                json.dumps({"schema_version": "semantic-calibration-index/1.0.0", "cases": cases}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "GRADER_IDENTITY_INVALID"):
                run_calibration(
                    ROOT,
                    labels_path=labels_path,
                    grader_index_path=index_path,
                    output_dir=root / "out",
                )

    def test_calibration_runner_rejects_extra_self_reported_lineage(self):
        labels_path = ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {}
            for case in labels["cases"]:
                dimensions = {
                    name: {"status": expected["status"], "grade": expected["grade_min"]}
                    for name, expected in case["human_labels"].items()
                }
                records = []
                for repeat in (1, 2):
                    value = {
                        "schema_version": "semantic-rubric-result/1.0.0",
                        "eval_id": f"{case['case_id']}-{repeat}",
                        "grader": EXPECTED_CALIBRATION_GRADER,
                        "dimensions": dimensions,
                        "prompt_hash": "0" * 64,
                    }
                    value["output_hash"] = canonical_hash(value)
                    path = root / f"{case['case_id']}-{repeat}.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    records.append({
                        "path": str(path),
                        "sha256": file_hash(path),
                        "execution_proof": {"path": str(path), "sha256": file_hash(path)},
                    })
                cases[case["case_id"]] = records
            index_path = root / "index.json"
            index_path.write_text(json.dumps({"schema_version": "semantic-calibration-index/1.0.0", "cases": cases}))
            with self.assertRaisesRegex(ValueError, "TOP_LEVEL_CONTRACT_INVALID"):
                run_calibration(ROOT, labels_path=labels_path, grader_index_path=index_path, output_dir=root / "out")

    def test_calibration_runner_rejects_reused_dev_eval_session(self):
        labels_path = ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {}
            for case in labels["cases"]:
                dimensions = {
                    name: {"status": expected["status"], "grade": expected["grade_min"]}
                    for name, expected in case["human_labels"].items()
                }
                records = []
                for repeat in (1, 2):
                    value = {
                        "schema_version": "semantic-rubric-result/1.0.0",
                        "eval_id": f"{case['case_id']}-{repeat}",
                        "grader": EXPECTED_CALIBRATION_GRADER,
                        "dimensions": dimensions,
                    }
                    value["output_hash"] = canonical_hash(value)
                    path = root / f"{case['case_id']}-{repeat}.json"
                    path.write_text(json.dumps(value), encoding="utf-8")
                    records.append({
                        "path": str(path),
                        "sha256": file_hash(path),
                        "execution_proof": execution_proof_record(
                            root, case["case_id"], repeat, path, session_id=f"shared-{case['case_id']}"
                        ),
                    })
                cases[case["case_id"]] = records
            index_path = root / "index.json"
            index_path.write_text(json.dumps({"schema_version": "semantic-calibration-index/1.0.0", "cases": cases}))
            with self.assertRaisesRegex(ValueError, "SESSION_NOT_INDEPENDENT"):
                run_calibration(ROOT, labels_path=labels_path, grader_index_path=index_path, output_dir=root / "out")


if __name__ == "__main__":
    unittest.main()
