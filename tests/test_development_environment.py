"""开发入口的零 LLM 路径与命令生成检查。"""

import contextlib
import io
import json
import os
import runpy
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from product.runtime.cli import main
from product.runtime.runtime_eval import build_eval_smoke_prompt
from product.runtime.smoke_prompt import build_smoke_prompt, sessions_root_argument
from product.runtime.model_routing import load_model_routing, select_model
from product.runtime.environment_preflight import (
    build_restricted_command,
    command_network_probe,
    network_access_probe,
    permission_probe,
    permission_profile_override,
    permission_profile_overrides,
    resolve_run_paths,
    run_permission_probe_with_child,
    run_environment_preflight,
)
from product.runtime.nested_codex import (
    CONNECTIVITY_PROBE_MARKER,
    run_nested_codex_connectivity_probe,
)


ROOT = Path(__file__).resolve().parents[1]


class EntryPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="entry paths ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.run = self.base / "run"
        self.run.mkdir()
        self.manifest = {"run_id": "entry-run", "output_dir": str(self.run), "run_mode": "PRODUCT_COUNCIL"}
        self.save_manifest()
        self.forward = runpy.run_path(str(ROOT / "scripts" / "council-dev.py"))["forwarded_command"]

    def save_manifest(self):
        (self.run / "run_manifest.json").write_text(json.dumps(self.manifest))
        if self.manifest.get("run_mode") == "EXECUTION_REPLAY":
            (self.run / "host-replay-source.json").write_text('{}')

    def test_cwd_does_not_change_product_root_or_argument_boundaries(self):
        for cwd in (ROOT, ROOT / "product", self.base):
            command, repo = self.forward(["nested-codex-smoke", "--repo", os.path.relpath(ROOT, cwd), "--run-dir", os.path.relpath(self.run, cwd)], calling_cwd=cwd)
            self.assertEqual(repo, ROOT)
            self.assertEqual(command[command.index("--run-dir") + 1], str(self.run))
            self.assertEqual(command[command.index("--repo") + 1], str(ROOT))
        paths = resolve_run_paths(ROOT, run_dir=self.run)
        self.assertEqual(paths["child_cwd"], str(ROOT / "product"))
        self.assertEqual(paths["state_dir"], str(self.run / ".codex-runtime"))

    def test_default_repo_and_equals_syntax_preserve_cli(self):
        command, repo = self.forward(["artifact-replay", f"--run-dir={self.run}", "--output=report with spaces.json"], calling_cwd=self.base)
        self.assertEqual(repo, ROOT)
        self.assertIn(f"--output={self.base / 'report with spaces.json'}", command)
        self.assertEqual(command[command.index("--repo") + 1], str(ROOT))
        self.assertNotIn("nested-codex-smoke", command)

    def test_regression_only_forwards_existing_index_consumer(self):
        command, _ = self.forward(["regression", "--output-dir", "results", "--suite-id", "suite", "--candidate-hash", "hash", "--run-index", "index.json"], calling_cwd=self.base)
        self.assertEqual(command[3], "regression")
        self.assertNotIn("nested-codex-smoke", command)
        self.assertEqual(command[command.index("--run-index") + 1], str(self.base / "index.json"))

    def test_replay_explicit_root_conflict_fails_before_execution(self):
        self.manifest.update(run_mode="EXECUTION_REPLAY", execution_replay={"workspace": str(self.base / "frozen")})
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "REPLAY_REPOSITORY_CONFLICT"):
            self.forward(["nested-codex-smoke", "--repo", str(ROOT), "--run-dir", str(self.run)], calling_cwd=self.base)
        with self.assertRaisesRegex(ValueError, "REPLAY_REPOSITORY_CONFLICT"):
            resolve_run_paths(ROOT, run_dir=self.run)

    def test_three_new_execution_sources_use_the_same_cli_launcher(self):
        for mode, trigger in (("PRODUCT_COUNCIL", "product_council"), ("PRODUCT_COUNCIL", "regression:normal"), ("EXECUTION_REPLAY", "execution_replay")):
            self.manifest.update(run_mode=mode, trigger_reason=trigger)
            if mode == "EXECUTION_REPLAY":
                self.manifest["execution_replay"] = {"workspace": str(ROOT)}
            self.save_manifest()
            command, repo = self.forward(["nested-codex-smoke", "--run-dir", str(self.run)], calling_cwd=self.base)
            with patch("product.runtime.cli.launch_nested_codex", return_value=({"status": "TEST_ONLY"}, 7)) as launcher, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(command[3:]), 7)
                launcher.assert_called_once_with(
                    repo,
                    run_dir=self.run,
                    codex_binary=str(ROOT / "scripts/replay-codex-transport.py") if mode == "EXECUTION_REPLAY" else "codex",
                    timeout_seconds=1800,
                    preflight_report=None,
                )

    def test_duplicate_invocation_state_and_identity_conflicts_fail(self):
        for name, code in (("invocation", "INVOCATION_DIRECTORY_ALREADY_EXISTS"), (".codex-runtime", "RUN_STATE_ALREADY_EXISTS")):
            path = self.run / name
            path.mkdir()
            with self.assertRaisesRegex(ValueError, code):
                resolve_run_paths(ROOT, run_dir=self.run)
            path.rmdir()
        (self.run / "decision_trace.json").write_text(json.dumps({"run_id": "different"}))
        with self.assertRaisesRegex(ValueError, "RUN_IDENTITY_CONFLICT"):
            resolve_run_paths(ROOT, run_dir=self.run)

    def test_symlink_inside_run_is_rejected(self):
        (self.run / "escaped").symlink_to(ROOT, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "RUN_DIRECTORY_SYMLINK_ESCAPE"):
            resolve_run_paths(ROOT, run_dir=self.run)

    def test_source_root_cannot_be_run_output(self):
        with self.assertRaisesRegex(ValueError, "RUN_DIRECTORY_OVERLAPS_SOURCE"):
            resolve_run_paths(ROOT, run_dir=ROOT / "product")

    def test_authorized_output_root_and_ancestor_symlink_fail_closed(self):
        (self.base / "other").mkdir()
        with self.assertRaisesRegex(ValueError, "RUN_DIRECTORY_OUTSIDE_AUTHORIZED_OUTPUT_ROOT"):
            resolve_run_paths(ROOT, run_dir=self.run, authorized_output_root=self.base / "other")
        link = self.base / "linked-run"
        link.symlink_to(self.run, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "PATH_ANCESTOR_SYMLINK_FORBIDDEN"):
            resolve_run_paths(ROOT, run_dir=link)


class PermissionContractTests(unittest.TestCase):
    def test_profile_is_path_scoped_and_does_not_open_codex_home(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CODEX_HOME": str(Path(directory) / "user codex")}
        ):
            base = Path(directory).resolve()
            codex_home = Path(directory) / "user codex"
            repo, run, output, tmpdir = (
                base / "repo",
                base / "run",
                base / "evidence",
                base / "tmp",
            )
            for path in (repo, run, output, tmpdir):
                path.mkdir()
            profile = permission_profile_override(
                repository_root=repo,
                run_dir=run,
                output_dir=output,
                tmpdir=tmpdir,
            )
            self.assertIn('\":root\"=\"deny\"', profile)
            self.assertIn(f'{json.dumps(str(repo))}=\"read\"', profile)
            self.assertIn(f'{json.dumps(str(run))}=\"write\"', profile)
            self.assertIn(f'{json.dumps(str(Path(sys.base_prefix).resolve()))}=\"read\"', profile)
            self.assertIn(f'{json.dumps(str(Path("/tmp").resolve()))}=\"deny\"', profile)
            self.assertIn("auth.json", profile)
            self.assertIn("config.toml", profile)
            self.assertIn("/rules", profile)
            self.assertIn("/skills", profile)
            self.assertIn("/plugins", profile)
            self.assertIn(f'{json.dumps(str(codex_home.resolve() / "tmp"))}=\"write\"', profile)
            self.assertIn(f'{json.dumps(str(codex_home.resolve() / "installation_id"))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve()))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve() / "sessions"))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve() / "logs"))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve() / "auth.json"))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve() / "config.toml"))}=\"write\"', profile)
            self.assertNotIn(f'{json.dumps(str(codex_home.resolve()))}=\"read\"', profile)
            self.assertNotIn('sandbox_mode', profile)
            self.assertNotIn('danger-full-access', profile)
            overrides = permission_profile_overrides(
                repository_root=repo,
                run_dir=run,
                output_dir=output,
                tmpdir=tmpdir,
            )
            self.assertEqual(overrides[0], profile)
            self.assertIn("features.network_proxy=true", overrides)
            self.assertIn("permissions.council_review.network.enabled=true", overrides)
            self.assertIn(
                'permissions.council_review.network.domains={"chatgpt.com"="allow"}',
                overrides,
            )
            self.assertFalse(any('"*"="allow"' in item for item in overrides))
            command = build_restricted_command(
                ["python3", "-V"],
                repository_root=repo,
                run_dir=run,
                output_dir=output,
                tmpdir=tmpdir,
            )
            self.assertEqual(command[0:2], ["codex", "sandbox"])
            self.assertEqual(command[command.index("--permission-profile") + 1], "council_review")
            self.assertIn("features.network_proxy=true", command)
            self.assertIn(
                'permissions.council_review.network.domains={"chatgpt.com"="allow"}',
                command,
            )

    def test_network_probe_rejects_proxy_allowlist_block(self):
        error = urllib.error.HTTPError(
            "https://chatgpt.com/backend-api/codex/responses",
            403,
            "forbidden",
            {"x-proxy-error": "blocked-by-allowlist"},
            None,
        )
        with patch(
            "product.runtime.environment_preflight.urllib.request.urlopen",
            side_effect=error,
        ):
            result = network_access_probe()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "NETWORK_PROXY_ALLOWLIST_BLOCKED")
        self.assertFalse(result["credentials_sent"])
        self.assertFalse(result["response_body_read"])

    def test_network_probe_accepts_reachable_http_error(self):
        error = urllib.error.HTTPError(
            "https://chatgpt.com/backend-api/codex/responses",
            405,
            "method not allowed",
            {},
            None,
        )
        with patch(
            "product.runtime.environment_preflight.urllib.request.urlopen",
            side_effect=error,
        ):
            result = network_access_probe()
        self.assertEqual(result["status"], "REACHABLE")
        self.assertIsNone(result["failure_code"])

    def test_network_probe_classifies_connect_403(self):
        error = urllib.error.URLError(
            OSError("Tunnel connection failed: 403 Forbidden")
        )
        with patch(
            "product.runtime.environment_preflight.urllib.request.urlopen",
            side_effect=error,
        ):
            result = network_access_probe()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "NETWORK_PROXY_CONNECT_REJECTED")
        self.assertEqual(result["error_classification"], "HTTP_CONNECT_403")

    def test_command_network_block_does_not_fail_permission_probe(self):
        parent = {
            "status": "PASS",
            "profile_hash": "profile-hash",
            "path_bindings": {},
        }
        child = subprocess.CompletedProcess(
            ["child"], 0, json.dumps(parent) + "\n", ""
        )
        records = [
            {
                "role": "developer",
                "content": [
                    {
                        "text": "\n".join(
                            (
                                (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
                                (ROOT / "product" / "AGENTS.md").read_text(encoding="utf-8"),
                                "product:portfolio-council",
                            )
                        )
                    }
                ],
            }
        ]
        config = subprocess.CompletedProcess(["codex"], 0, json.dumps(records), "")
        blocked = {
            "scope": "SANDBOXED_COMMAND",
            "gating": False,
            "status": "BLOCKED",
            "failure_code": "NETWORK_PROXY_CONNECT_REJECTED",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "STOCK_AGENT_PERMISSION_PROFILE_HASH": "profile-hash",
                "STOCK_AGENT_PERMISSION_PATH_BINDINGS": "{}",
            },
        ):
            base = Path(directory)
            output = base / "permission.json"
            with patch(
                "product.runtime.environment_preflight.permission_probe",
                return_value=parent,
            ), patch(
                "product.runtime.environment_preflight._command_output",
                side_effect=(child, config),
            ), patch(
                "product.runtime.environment_preflight.command_network_probe",
                return_value=blocked,
            ):
                result, code = run_permission_probe_with_child(
                    source_canary=ROOT / "AGENTS.md",
                    output_dir=base,
                    tmpdir=base,
                    outside_canary=base / "outside",
                    output_path=output,
                )
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["COMMAND_NETWORK_STATUS"], "BLOCKED")
        self.assertEqual(result["NESTED_CODEX_STATUS"], "NOT_EXECUTED")
        self.assertIsNone(result["FIRST_DIVERGENCE"])
        self.assertFalse(result["blocks_change"])

    def test_probe_never_writes_source_or_outside_canary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output, tmpdir = base / "output", base / "tmp"
            output.mkdir()
            tmpdir.mkdir()
            source, outside = base / "source", base / "outside"
            source.write_text("source", encoding="utf-8")
            outside.write_text("outside", encoding="utf-8")
            real_open = os.open

            def restricted_open(path, flags):
                if Path(path) in {source, outside}:
                    raise PermissionError("denied")
                return real_open(path, flags)

            with patch("product.runtime.environment_preflight.os.open", side_effect=restricted_open):
                result = permission_probe(
                    source_canary=source,
                    output_dir=output,
                    tmpdir=tmpdir,
                    outside_canary=outside,
                )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(source.read_text(encoding="utf-8"), "source")
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
            self.assertEqual(result["source_bytes_written"], 0)
            self.assertEqual(result["outside_bytes_written"], 0)


class NestedCodexConnectivityProbeTests(unittest.TestCase):
    def _fake_run(self, *, blocked: bool):
        def run(command, **kwargs):
            kwargs["stdout"].write(json.dumps({"type": "thread.started"}) + "\n")
            if blocked:
                kwargs["stderr"].write(
                    "HTTP CONNECT 403: blocked-by-allowlist\n"
                )
                return subprocess.CompletedProcess(command, 1)
            final_path = Path(command[command.index("--output-last-message") + 1])
            final_path.write_text(CONNECTIVITY_PROBE_MARKER, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        return run

    def test_nested_codex_probe_passes_only_with_event_and_marker(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.runtime.nested_codex.subprocess.run",
            side_effect=self._fake_run(blocked=False),
        ):
            result, code = run_nested_codex_connectivity_probe(
                ROOT,
                output_dir=Path(directory) / "probe",
                model="gpt-5.6-terra",
                command_network_status="BLOCKED",
            )
        self.assertEqual(code, 0)
        self.assertEqual(result["NESTED_CODEX_STATUS"], "PASS")
        self.assertEqual(result["COMMAND_NETWORK_STATUS"], "BLOCKED")
        self.assertIsNone(result["FIRST_DIVERGENCE"])
        self.assertFalse(result["blocks_change"])

    def test_nested_codex_probe_403_is_the_network_blocker(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.runtime.nested_codex.subprocess.run",
            side_effect=self._fake_run(blocked=True),
        ):
            result, code = run_nested_codex_connectivity_probe(
                ROOT,
                output_dir=Path(directory) / "probe",
                model="gpt-5.6-terra",
                command_network_status="BLOCKED",
            )
        self.assertEqual(code, 9)
        self.assertEqual(result["NESTED_CODEX_STATUS"], "BLOCKED")
        self.assertEqual(
            result["failure_code"], "NESTED_CODEX_PROXY_CONNECT_REJECTED"
        )
        self.assertEqual(result["FIRST_DIVERGENCE"], "NESTED_CODEX_MODEL_TRANSPORT")
        self.assertTrue(result["blocks_change"])

    def test_nested_codex_probe_preserves_403_as_first_cause_after_timeout(self):
        def timed_out_after_403(command, **kwargs):
            kwargs["stdout"].write(json.dumps({"type": "thread.started"}) + "\n")
            kwargs["stderr"].write(
                "Proxy connection failed: HTTP CONNECT failed with status 403; "
                "blocked-by-allowlist\n"
            )
            raise subprocess.TimeoutExpired(command, 180)

        with tempfile.TemporaryDirectory() as directory, patch(
            "product.runtime.nested_codex.subprocess.run",
            side_effect=timed_out_after_403,
        ):
            result, code = run_nested_codex_connectivity_probe(
                ROOT,
                output_dir=Path(directory) / "probe",
                model="gpt-5.6-terra",
                command_network_status="BLOCKED",
            )
        self.assertEqual(code, 9)
        self.assertTrue(result["timed_out"])
        self.assertEqual(
            result["failure_code"], "NESTED_CODEX_PROXY_CONNECT_REJECTED"
        )


class EnvironmentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="environment preflight ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.run = self.base / "run"
        self.run.mkdir()
        (self.run / "run_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "preflight-run",
                    "output_dir": str(self.run),
                    "run_mode": "PRODUCT_COUNCIL",
                    "model": "gpt-5.6-terra",
                }
            ),
            encoding="utf-8",
        )
        self.permission = self.base / "permission.json"
        self.permission.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "child_inheritance": True,
                    "profile_hash": "profile-hash",
                    "path_bindings": {
                        "repo_root": str(ROOT),
                        "run_dir": str(self.run),
                    },
                }
            ),
            encoding="utf-8",
        )

    def command_result(self, command, *, cwd):
        if command[-2:] == ["doctor", "--json"]:
            stdout = json.dumps(
                {
                    "codexVersion": "0.153.4",
                    "checks": {
                        "config.load": {
                            "status": "pass",
                            "summary": "loaded",
                            "details": {"model": "gpt-5.6-sol"},
                        }
                    },
                }
            )
            return subprocess.CompletedProcess(command, 1, stdout, "")
        if "prompt-input" in command:
            developer = "\n".join(
                (
                    (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
                    (ROOT / "product" / "AGENTS.md").read_text(encoding="utf-8"),
                    "product:portfolio-council",
                )
            )
            stdout = json.dumps(
                [
                    {"role": "developer", "content": [{"text": "product:portfolio-council"}]},
                    {"role": "user", "content": [{"text": developer}]},
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        if command[-2:] == ["exec", "--help"]:
            return subprocess.CompletedProcess(command, 0, " ".join(("--ephemeral", "--json", "--sandbox", "--add-dir", "--strict-config")), "")
        if command[-2:] == ["sandbox", "--help"]:
            return subprocess.CompletedProcess(command, 0, "--permission-profile --sandbox-state-json --cd", "")
        return subprocess.CompletedProcess(command, 0, "codex-cli 0.153.4", "")

    def run_preflight(self, name="preflight", **overrides):
        arguments = {
            "run_dir": self.run,
            "output_dir": self.base / name,
            "mode": "runtime",
            "requested_model": "gpt-5.6-terra",
            "permission_evidence": self.permission,
        }
        arguments.update(overrides)
        with patch(
            "product.runtime.environment_preflight._command_output",
            side_effect=self.command_result,
        ):
            return run_environment_preflight(ROOT, **arguments)

    def test_ready_report_is_zero_llm_and_does_not_claim_runtime_load(self):
        report, exit_code = self.run_preflight()
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["llm_calls"], 0)
        self.assertEqual(report["run_stage"], "PREPARE_ONLY")
        self.assertEqual(report["runtime_load_status"], "UNKNOWN")
        self.assertEqual(report["models"]["actual_model"], None)
        self.assertEqual(report["models"]["availability"], "PENDING_RUNTIME_CONFIRMATION")
        self.assertEqual(report["resources"]["root_agents"]["load_status"], "LOAD_VERIFIED")
        self.assertEqual(report["resources"]["portfolio_council_skill"]["load_status"], "CONFIG_VALIDATED")

    def test_permission_model_cli_and_missing_run_are_classified(self):
        report, code = self.run_preflight("permission", permission_evidence=None)
        self.assertEqual((code, report["failure_code"]), (8, "PERMISSION_EVIDENCE_MISSING_OR_FAILED"))
        report, code = self.run_preflight("model", requested_model="gpt-unknown")
        self.assertEqual((code, report["failure_code"]), (8, "MODEL_CONFIGURATION_MISMATCH"))
        with patch(
            "product.runtime.environment_preflight._command_output",
            side_effect=lambda command, cwd: subprocess.CompletedProcess(
                command,
                0,
                "missing required options" if command[-2:] == ["sandbox", "--help"] else self.command_result(command, cwd=cwd).stdout,
                "",
            ),
        ):
            report, code = run_environment_preflight(
                ROOT,
                run_dir=self.run,
                output_dir=self.base / "unsupported",
                mode="development",
            )
        self.assertEqual((code, report["failure_code"]), (8, "CODEX_CLI_CONTRACT_UNSUPPORTED"))
        report, code = self.run_preflight("missing", run_dir=self.base / "missing")
        self.assertEqual(code, 8)
        self.assertEqual(report["first_divergence"], "PATH_RESOLUTION")


class ModelConfigurationTests(unittest.TestCase):
    def test_effective_development_defaults_match_canonical_policy(self):
        policy = load_model_routing(ROOT / "product")
        config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text())
        evaluation = tomllib.loads((ROOT / ".codex" / "agents" / "dev_eval.toml").read_text())
        self.assertEqual(config["model"], policy["development_default"])
        self.assertEqual(evaluation["model"], policy["runtime_repeated"])

    def test_dispute_model_cannot_be_selected_without_authorization(self):
        with self.assertRaises(ValueError):
            select_model(ROOT / "product", route="architecture_dispute")


class SessionPathTests(unittest.TestCase):
    def test_explicit_sessions_precedes_codex_home_without_reading_it(self):
        with patch.dict(os.environ, {"CODEX_HOME": "/unread/config"}):
            explicit = Path("sessions with spaces;literal")
            self.assertEqual(shlex.split(sessions_root_argument(explicit)), [str(explicit.resolve())])

    def test_default_uses_codex_home(self):
        with patch.dict(os.environ, {"CODEX_HOME": "/configured/codex home"}):
            self.assertEqual(shlex.split(sessions_root_argument()), ["/configured/codex home/sessions"])

    def test_unset_codex_home_uses_home(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=Path("/isolated/home")):
            self.assertEqual(shlex.split(sessions_root_argument()), ["/isolated/home/.codex/sessions"])

    def test_smoke_modes_quote_paths_and_keep_deferred_proof_run_scoped(self):
        with tempfile.TemporaryDirectory(prefix="council paths ") as directory:
            run = Path(directory).resolve()
            repo = run / "repo with spaces"
            sessions = run / "selected sessions"
            for mode, profile in (("PRODUCT_COUNCIL", None), ("EVAL_ABLATION", "full-council")):
                manifest = {"run_id": "path-check", "output_dir": str(run), "model": "gpt-5.6-terra", "run_mode": mode, "ablation_profile": profile}
                (run / "run_manifest.json").write_text(json.dumps(manifest))
                prompt = build_smoke_prompt(run, repository_root=repo, sessions_root=sessions)
                command = next(part for part in prompt.split("`") if "cli execution-proof " in part)
                argv = shlex.split(command)
                self.assertEqual(argv[1], str(repo))
                for flag, expected in (("--repo", repo), ("--run-dir", run), ("--sessions-root", sessions)):
                    self.assertEqual(argv[argv.index(flag) + 1], str(expected))
                if mode == "PRODUCT_COUNCIL":
                    deferred = build_smoke_prompt(run, repository_root=repo, defer_deterministic_finalize=True)
                    self.assertNotIn("--sessions-root", deferred)
                    self.assertIn("Subagent lifecycle events", deferred)

    def test_eval_prompt_cli_forwards_explicit_sessions(self):
        with tempfile.TemporaryDirectory(prefix="eval paths ") as directory:
            eval_dir = Path(directory).resolve()
            sessions = eval_dir / "selected sessions"
            (eval_dir / "input-manifest.json").write_text(json.dumps({"eval_id": "path-eval", "source_hashes": dict.fromkeys(("grader_prompt", "rubric", "semantic_input", "semantic_output_schema"), "test-hash")}))
            expected = build_eval_smoke_prompt(ROOT, eval_dir=eval_dir, sessions_root=sessions)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["eval-smoke-prompt", "--repo", str(ROOT), "--eval-dir", str(eval_dir), "--sessions-root", str(sessions)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue().strip(), expected.strip())
            command = next(part for part in expected.split("`") if "cli eval-execution-proof " in part)
            argv = shlex.split(command)
            self.assertEqual(argv[argv.index("--sessions-root") + 1], str(sessions))
            self.assertEqual(argv[argv.index("--semantic-result") + 1], str(eval_dir / "semantic-result.json"))

    def test_active_templates_have_no_personal_sessions_path_or_credential_copy(self):
        for filename in ("smoke_prompt.py", "runtime_eval.py"):
            source = (ROOT / "product" / "runtime" / filename).read_text()
            self.assertNotIn("/Users/", source)
            self.assertNotIn("auth.json", source)


if __name__ == "__main__":
    unittest.main()
