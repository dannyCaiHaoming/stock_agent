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


class RetiredSandboxEntryTests(unittest.TestCase):
    def setUp(self):
        self.entry = runpy.run_path(str(ROOT / "scripts/council-dev.py"))
        self.temporary = tempfile.TemporaryDirectory(prefix="retired entry ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def assert_no_effect(self, callback, *, exception=False, code="PROJECT_SANDBOX_ENTRY_RETIRED"):
        output = io.StringIO()
        with patch("subprocess.run") as run, patch("subprocess.Popen") as popen, patch(
            "urllib.request.urlopen"
        ) as network, patch.object(Path, "read_text") as read, patch.object(
            Path, "mkdir"
        ) as mkdir, contextlib.redirect_stdout(output):
            if exception:
                with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                    callback()
            else:
                self.assertEqual(callback(), 2)
                result = json.loads(output.getvalue())
                self.assertEqual(result["status"], "BLOCKED")
                self.assertEqual(result["failure_code"], code)
                self.assertEqual(result["llm_calls"], 0)
            for operation in (run, popen, network, read, mkdir):
                operation.assert_not_called()
        self.assertEqual(list(self.base.iterdir()), [])

    def test_all_retired_commands_fail_at_both_cli_layers(self):
        for command in ("review-run", "review-probe", "environment-preflight",
                        "permission-probe", "nested-codex-probe"):
            for tail in ([], ["--repo", str(ROOT), "--run-dir", str(self.base / "run"),
                              "--output-dir", str(self.base / "output")]):
                for entry in (main, self.entry["main"]):
                    with self.subTest(command=command, tail=tail, entry=entry):
                        self.assert_no_effect(lambda: entry([command, *tail]))
                with self.subTest(command=command, direct_forward=True):
                    self.assert_no_effect(
                        lambda: self.entry["forwarded_command"]([command, *tail], calling_cwd=ROOT),
                        exception=True,
                    )

    def test_legacy_options_fail_before_missing_manifest_or_report(self):
        for flag in ("--preflight-report", "--preflight-report=missing.json",
                     "--review", "--review=true"):
            code = "LEGACY_SANDBOX_MODE_RETIRED" if flag.startswith("--preflight-report") else "PROJECT_SANDBOX_ENTRY_RETIRED"
            arguments = ["nested-codex-smoke", "--run-dir", str(self.base / "run"), flag]
            if flag == "--preflight-report":
                arguments.append(str(self.base / "missing.json"))
            for entry in (main, self.entry["main"]):
                with self.subTest(flag=flag, entry=entry):
                    self.assert_no_effect(lambda: entry(arguments), code=code)
            self.assert_no_effect(
                lambda: self.entry["forwarded_command"](arguments, calling_cwd=ROOT),
                exception=True, code=code,
            )

    def test_sys_argv_path_also_rejects_retired_entry(self):
        for entry in (main, self.entry["main"]):
            with patch.object(sys, "argv", ["entry", "environment-preflight"]):
                self.assert_no_effect(entry)

    def test_direct_retired_functions_never_start_legacy_work(self):
        callbacks = [
            lambda: self.entry["restricted_main"](["review-run"], calling_cwd=ROOT),
            lambda: run_nested_codex_connectivity_probe(
                ROOT, output_dir=self.base / "probe", model="gpt-5.6-terra",
                command_network_status="PASS",
            ),
            lambda: run_environment_preflight(
                ROOT, run_dir=self.base / "run", output_dir=self.base / "preflight",
                mode="runtime", permission_evidence=self.base / "missing.json",
            ),
        ]
        for child in (False, True):
            callbacks.append(lambda child=child: run_permission_probe_with_child(
                source_canary=ROOT / "AGENTS.md", output_dir=self.base / "probe",
                tmpdir=self.base / "tmp", outside_canary=self.base / "outside",
                output_path=self.base / "permission.json", child=child,
            ))
        for callback in callbacks:
            with self.subTest(callback=callback):
                self.assert_no_effect(callback, exception=True)

    def test_retired_routes_are_not_advertised_as_active_commands(self):
        from product.runtime.cli import build_parser
        help_text = build_parser().format_help()
        for name in ("environment-preflight", "permission-probe", "nested-codex-probe"):
            self.assertNotIn(name, help_text)


class ModelConfigurationTests(unittest.TestCase):
    def test_runtime_eval_model_matches_product_policy(self):
        policy = load_model_routing(ROOT / "product")
        evaluation = tomllib.loads((ROOT / ".codex" / "agents" / "dev_eval.toml").read_text())
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
