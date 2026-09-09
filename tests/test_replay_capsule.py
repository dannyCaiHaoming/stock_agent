from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from product.runtime.execution_replay import ExecutionReplayError, finalize_execution_replay, prepare_execution_replay
from product.runtime.hashing import canonical_hash
from product.runtime.replay import replay_run
from product.runtime.replay_capsule import (
    MAX_OBJECT_BYTES,
    ReplayCapsuleError,
    materialize_replay_capsule,
    validate_materialized_snapshot,
    validate_replay_capsule,
)
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from tests.test_native_run_package import FIXTURES, ROOT, cio_output, specialist_outputs, write_json


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def complete_run(run_dir: Path, run_id: str) -> None:
    prepare_run(
        ROOT,
        fixture_path=FIXTURES / "normal-research.json",
        run_dir=run_dir,
        run_id=run_id,
        model="gpt-5.6-terra",
        research_question="研究 fixture。",
        authenticity_required=False,
    )
    specialist_outputs(run_dir)
    prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
    write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
    finalize_cio(ROOT, run_dir=run_dir)


def reseal(manifest_path: Path, manifest: dict) -> None:
    root_records = [
        {"logical_path": item["logical_path"], "sha256": item["sha256"]}
        for item in manifest["objects"]
    ]
    manifest["root_hash"] = canonical_hash(sorted(root_records, key=lambda item: item["logical_path"]))
    body = dict(manifest)
    body.pop("manifest_hash", None)
    manifest["manifest_hash"] = canonical_hash(body)
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


class ReplayCapsuleTests(unittest.TestCase):
    def test_capsule_closes_every_object_and_materializes_allowlisted_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "source"
            complete_run(run_dir, "capsule-source")
            capsule = validate_replay_capsule(run_dir / "replay_capsule", expected_run_id="capsule-source")
            self.assertEqual(capsule["root_hash"], read_json(run_dir / "run_manifest.json")["replay_capsule"]["root_hash"])
            target = Path(directory) / "materialized"
            materialize_replay_capsule(run_dir / "replay_capsule", target_root=target)
            self.assertTrue((target / "product" / "skills" / "portfolio-council" / "SKILL.md").is_file())
            self.assertTrue((target / "frozen" / "evidence" / "gate.json").is_file())
            validate_materialized_snapshot(run_dir / "replay_capsule", target_root=target)
            for path in [target, *target.rglob("*")]:
                self.assertEqual(path.stat().st_mode & 0o222, 0, path)

    def test_same_inputs_have_stable_logical_root_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            complete_run(first, "same-run")
            complete_run(second, "same-run")
            first_capsule = read_json(first / "replay_capsule" / "manifest.json")
            second_capsule = read_json(second / "replay_capsule" / "manifest.json")
            self.assertEqual(first_capsule["root_hash"], second_capsule["root_hash"])

    def test_missing_tampered_and_path_escape_objects_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            complete_run(source, "capsule-tamper")
            original = source / "replay_capsule"

            missing = Path(directory) / "missing"
            shutil.copytree(original, missing)
            missing_manifest = read_json(missing / "manifest.json")
            (missing / "objects" / missing_manifest["objects"][0]["sha256"]).unlink()
            with self.assertRaisesRegex(ReplayCapsuleError, "CAPSULE_OBJECT_MISSING"):
                validate_replay_capsule(missing)

            escaped = Path(directory) / "escaped"
            shutil.copytree(original, escaped)
            escaped_manifest = read_json(escaped / "manifest.json")
            escaped_manifest["objects"][0]["logical_path"] = "../outside"
            reseal(escaped / "manifest.json", escaped_manifest)
            with self.assertRaisesRegex(ReplayCapsuleError, "CAPSULE_PATH_FORBIDDEN"):
                validate_replay_capsule(escaped)

            sensitive = Path(directory) / "sensitive"
            shutil.copytree(original, sensitive)
            sensitive_manifest = read_json(sensitive / "manifest.json")
            record = sensitive_manifest["objects"][0]
            old = sensitive / "objects" / record["sha256"]
            payload = b"sk-abcdefghijklmnopqrstuvwxyz123456"
            digest = hashlib.sha256(payload).hexdigest()
            old.unlink()
            (sensitive / "objects" / digest).write_bytes(payload)
            record["sha256"] = digest
            record["bytes"] = len(payload)
            reseal(sensitive / "manifest.json", sensitive_manifest)
            with self.assertRaisesRegex(ReplayCapsuleError, "CAPSULE_SENSITIVE_CONTENT"):
                validate_replay_capsule(sensitive)

    def test_oversized_and_symlink_objects_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            complete_run(source, "capsule-object-policy")
            original = source / "replay_capsule"

            oversized = Path(directory) / "oversized"
            shutil.copytree(original, oversized)
            manifest = read_json(oversized / "manifest.json")
            record = manifest["objects"][0]
            old = oversized / "objects" / record["sha256"]
            payload = b"x" * (MAX_OBJECT_BYTES + 1)
            digest = hashlib.sha256(payload).hexdigest()
            old.unlink()
            (oversized / "objects" / digest).write_bytes(payload)
            record["sha256"] = digest
            record["bytes"] = len(payload)
            reseal(oversized / "manifest.json", manifest)
            with self.assertRaisesRegex(ReplayCapsuleError, "CAPSULE_OBJECT_TOO_LARGE"):
                validate_replay_capsule(oversized)

            linked = Path(directory) / "linked"
            shutil.copytree(original, linked)
            linked_manifest = read_json(linked / "manifest.json")
            object_path = linked / "objects" / linked_manifest["objects"][0]["sha256"]
            target = Path(directory) / "outside-object"
            target.write_bytes(object_path.read_bytes())
            object_path.unlink()
            object_path.symlink_to(target)
            with self.assertRaisesRegex(ReplayCapsuleError, "CAPSULE_OBJECT_MISSING"):
                validate_replay_capsule(linked)

    def test_locked_model_context_cannot_drift_from_frozen_version_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "source"
            complete_run(run_dir, "capsule-context")
            manifest_path = run_dir / "replay_capsule" / "manifest.json"
            manifest = read_json(manifest_path)
            manifest["locked_context"]["model"] = "gpt-6-astra"
            reseal(manifest_path, manifest)
            with self.assertRaisesRegex(ReplayCapsuleError, "LOCKED_CONTEXT_VERSION_MISMATCH"):
                validate_replay_capsule(run_dir / "replay_capsule")

    def test_artifact_replay_uses_capsule_without_repository_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "source"
            complete_run(run_dir, "capsule-artifact")
            result = replay_run(Path(directory) / "nonexistent-repository", run_dir=run_dir)
            self.assertEqual(result["llm_calls"], 0)
            self.assertTrue(result["execution_replay_ready"])
            self.assertEqual(result["source_tree_hash"], result["source_tree_hash"])

    def test_execution_replay_rebuilds_frozen_context_with_new_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            replay = root / "replay"
            complete_run(source, "execution-source")
            prepared = prepare_execution_replay(
                source_run_dir=source,
                new_run_dir=replay,
                new_run_id="execution-new",
            )
            self.assertEqual(prepared["source_run_id"], "execution-source")
            self.assertEqual(prepared["next_state"], "DISPATCH_REQUIRED")
            workspace = Path(prepared["workspace"])
            specialist_outputs(replay)
            prepare_cio(workspace, run_dir=replay, model="gpt-5.6-terra")
            write_json(replay / "cio" / "runtime_cio.json", cio_output(replay))
            finalize_cio(workspace, run_dir=replay)
            output = root / "comparison"
            result = finalize_execution_replay(
                source_run_dir=source,
                replay_run_dir=replay,
                output_dir=output,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["byte_identical_output_required"])
            self.assertTrue((output / "report.md").is_file())
            self.assertEqual(
                result["source_configuration_hashes"],
                result["replay_configuration_hashes"],
            )

    def test_execution_replay_rejects_writable_workspace_and_configuration_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            replay = root / "replay"
            complete_run(source, "execution-source-drift")
            prepared = prepare_execution_replay(
                source_run_dir=source,
                new_run_dir=replay,
                new_run_id="execution-new-drift",
            )
            workspace = Path(prepared["workspace"])
            os.chmod(workspace / "product", 0o755)
            specialist_outputs(replay)
            prepare_cio(workspace, run_dir=replay, model="gpt-5.6-terra")
            write_json(replay / "cio" / "runtime_cio.json", cio_output(replay))
            finalize_cio(workspace, run_dir=replay)
            with self.assertRaisesRegex(ExecutionReplayError, "MATERIALIZED_PATH_WRITABLE"):
                finalize_execution_replay(
                    source_run_dir=source,
                    replay_run_dir=replay,
                    output_dir=root / "comparison-writable",
                )

            os.chmod(workspace / "product", 0o555)
            manifest_path = replay / "run_manifest.json"
            manifest = read_json(manifest_path)
            manifest["model"] = "gpt-6-astra"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ExecutionReplayError,
                "TRACE_INVALID|SOURCE_MISMATCH|CONFIGURATION_DRIFT",
            ):
                finalize_execution_replay(
                    source_run_dir=source,
                    replay_run_dir=replay,
                    output_dir=root / "comparison-drift",
                )

    def test_old_run_without_capsule_is_not_execution_replay_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "legacy"
            complete_run(old, "legacy-source")
            manifest_path = old / "run_manifest.json"
            manifest = read_json(manifest_path)
            manifest.pop("execution_replay_supported")
            manifest.pop("replay_capsule")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            shutil.rmtree(old / "replay_capsule")
            trace_path = old / "decision_trace.json"
            trace = read_json(trace_path)
            trace["runtime"]["replay_capsule"] = None
            trace["artifacts"] = {
                path: digest
                for path, digest in trace["artifacts"].items()
                if not path.startswith("replay_capsule/")
            }
            trace["artifacts"]["run_manifest.json"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            result = replay_run(ROOT, run_dir=old)
            self.assertFalse(result["execution_replay_ready"])
            with self.assertRaisesRegex(ValueError, "EXECUTION_REPLAY_UNSUPPORTED"):
                prepare_execution_replay(
                    source_run_dir=old,
                    new_run_dir=Path(directory) / "new",
                    new_run_id="legacy-new",
                )

    def test_pre_agent_safe_termination_execution_replay_calls_no_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            prepared = prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=source,
                run_id="stale-source",
                model="gpt-5.6-terra",
                research_question="验证无可用 Evidence。",
                authenticity_required=True,
            )
            self.assertEqual(prepared["next_state"], "SAFE_NO_TRADE")
            replay = root / "replay"
            result = prepare_execution_replay(
                source_run_dir=source,
                new_run_dir=replay,
                new_run_id="stale-replay",
            )
            self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
            trace = read_json(replay / "decision_trace.json")
            self.assertEqual(trace["agents"], [])
            self.assertEqual(trace["risk_lineage"], [])

    def test_ablation_run_cannot_be_replayed_as_product_topology(self):
        from tests.test_runtime_ablation import build_variant

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variant = build_variant(root, "cio-only")
            with self.assertRaisesRegex(ExecutionReplayError, "SOURCE_PROFILE_UNSUPPORTED"):
                prepare_execution_replay(
                    source_run_dir=Path(variant["run_dir"]),
                    new_run_dir=root / "replay",
                    new_run_id="ablation-replay",
                )


if __name__ == "__main__":
    unittest.main()
