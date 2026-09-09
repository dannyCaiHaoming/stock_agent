"""Deterministic command surface consumed by the portfolio-council Skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .execution_proof import (
    ExecutionProofError,
    build_run_specialist_execution_proof,
    discover_and_build_run_specialist_execution_proof,
)
from .run_package import fail_run, finalize_cio, prepare_cio, prepare_run
from .replay import replay_run, write_replay_result
from .native_eval import evaluate_run, persist_eval_result
from .native_rerun import prepare_native_rerun
from .release_gate import check_run
from .smoke_prompt import build_smoke_prompt
from .terminal_contract import FailureStage
from .execution_replay import finalize_execution_replay, prepare_execution_replay
from .reason_codes import code_from_error
from .runtime_eval import build_eval_smoke_prompt, finalize_eval_job, prepare_eval_job
from .eval_execution_proof import (
    build_eval_execution_proof,
    discover_eval_rollouts,
    persist_eval_execution_proof,
)
from .trace_validation import trace_integrity_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portfolio Council deterministic runtime tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--repo", type=Path, required=True)
    prepare.add_argument("--fixture", type=Path, required=True)
    prepare.add_argument("--run-dir", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--question", required=True)
    prepare.add_argument("--run-mode", default="PRODUCT_COUNCIL", choices=("PRODUCT_COUNCIL", "EVAL_ABLATION"))
    prepare.add_argument("--ablation-profile", choices=("cio-only", "analyst-cio", "full-council"))
    prepare.add_argument("--trigger-reason", default="product_council")

    cio = subparsers.add_parser("prepare-cio")
    cio.add_argument("--repo", type=Path, required=True)
    cio.add_argument("--run-dir", type=Path, required=True)
    cio.add_argument("--model", required=True)

    final = subparsers.add_parser("finalize-cio")
    final.add_argument("--repo", type=Path, required=True)
    final.add_argument("--run-dir", type=Path, required=True)
    final.add_argument("--revision", action="store_true")

    prompt = subparsers.add_parser("smoke-prompt")
    prompt.add_argument("--repo", type=Path, required=True)
    prompt.add_argument("--run-dir", type=Path, required=True)

    proof = subparsers.add_parser("execution-proof")
    proof.add_argument("--repo", type=Path, required=True)
    proof.add_argument("--run-dir", type=Path, required=True)
    proof.add_argument("--parent-rollout", type=Path)
    proof.add_argument("--company-rollout", type=Path)
    proof.add_argument("--skeptic-rollout", type=Path)
    proof.add_argument("--sessions-root", type=Path)

    replay = subparsers.add_parser("replay")
    replay.add_argument("--repo", type=Path, required=True)
    replay.add_argument("--run-dir", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    evaluation = subparsers.add_parser("eval")
    evaluation.add_argument("--repo", type=Path, required=True)
    evaluation.add_argument("--run-dir", type=Path, required=True)

    check = subparsers.add_parser("check-run")
    check.add_argument("--repo", type=Path, required=True)
    check.add_argument("--run-dir", type=Path, required=True)

    rerun = subparsers.add_parser("prepare-rerun")
    rerun.add_argument("--repo", type=Path, required=True)
    rerun.add_argument("--source-run-dir", type=Path, required=True)
    rerun.add_argument("--run-dir", type=Path, required=True)
    rerun.add_argument("--run-id", required=True)

    artifact_replay = subparsers.add_parser("artifact-replay")
    artifact_replay.add_argument("--repo", type=Path, required=True)
    artifact_replay.add_argument("--run-dir", type=Path, required=True)
    artifact_replay.add_argument("--output", type=Path, required=True)

    execution_prepare = subparsers.add_parser("prepare-execution-replay")
    execution_prepare.add_argument("--source-run-dir", type=Path, required=True)
    execution_prepare.add_argument("--run-dir", type=Path, required=True)
    execution_prepare.add_argument("--run-id", required=True)
    execution_prepare.add_argument("--workspace", type=Path)

    execution_finalize = subparsers.add_parser("finalize-execution-replay")
    execution_finalize.add_argument("--source-run-dir", type=Path, required=True)
    execution_finalize.add_argument("--run-dir", type=Path, required=True)
    execution_finalize.add_argument("--output-dir", type=Path, required=True)

    eval_prepare = subparsers.add_parser("eval-prepare")
    eval_prepare.add_argument("--repo", type=Path, required=True)
    eval_prepare.add_argument("--run-dir", type=Path, required=True)
    eval_prepare.add_argument("--eval-dir", type=Path, required=True)
    eval_prepare.add_argument("--eval-id", required=True)
    eval_prepare.add_argument("--expected-terminal-state", action="append")

    eval_finalize = subparsers.add_parser("eval-finalize")
    eval_finalize.add_argument("--repo", type=Path, required=True)
    eval_finalize.add_argument("--eval-dir", type=Path, required=True)
    eval_finalize.add_argument("--semantic-result", type=Path)

    eval_prompt = subparsers.add_parser("eval-smoke-prompt")
    eval_prompt.add_argument("--repo", type=Path, required=True)
    eval_prompt.add_argument("--eval-dir", type=Path, required=True)

    eval_proof = subparsers.add_parser("eval-execution-proof")
    eval_proof.add_argument("--repo", type=Path, required=True)
    eval_proof.add_argument("--eval-dir", type=Path, required=True)
    eval_proof.add_argument("--semantic-result", type=Path, required=True)
    eval_proof.add_argument("--sessions-root", type=Path, required=True)

    calibration = subparsers.add_parser("eval-calibration")
    calibration.add_argument("--repo", type=Path, required=True)
    calibration.add_argument("--labels", type=Path, required=True)
    calibration.add_argument("--grader-index", type=Path, required=True)
    calibration.add_argument("--output-dir", type=Path, required=True)

    regression = subparsers.add_parser("regression")
    regression.add_argument("--repo", type=Path, required=True)
    regression.add_argument("--output-dir", type=Path, required=True)
    regression.add_argument("--suite-id", required=True)
    regression.add_argument("--candidate-hash", required=True)
    regression.add_argument("--run-index", type=Path, required=True)
    regression.add_argument("--cache-dir", type=Path)
    regression.add_argument("--force", action="store_true")

    ablation = subparsers.add_parser("ablation")
    ablation.add_argument("--repo", type=Path, required=True)
    ablation.add_argument("--output-dir", type=Path, required=True)
    ablation.add_argument("--ablation-id", required=True)
    ablation.add_argument("--variants", type=Path, required=True)

    promotion = subparsers.add_parser("promotion")
    promotion.add_argument("--repo", type=Path, required=True)
    promotion.add_argument("--input-manifest", type=Path, required=True)
    promotion.add_argument("--output-dir", type=Path, required=True)

    trace_check = subparsers.add_parser("trace-check")
    trace_check.add_argument("--run-dir", type=Path, required=True)
    trace_check.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare_run(
            args.repo,
            fixture_path=args.fixture,
            run_dir=args.run_dir,
            run_id=args.run_id,
            model=args.model,
            research_question=args.question,
            run_mode=args.run_mode,
            ablation_profile=args.ablation_profile,
            trigger_reason=args.trigger_reason,
        )
    elif args.command == "prepare-cio":
        result = prepare_cio(args.repo, run_dir=args.run_dir, model=args.model)
    elif args.command == "finalize-cio":
        result = finalize_cio(args.repo, run_dir=args.run_dir, revision=args.revision)
    elif args.command == "smoke-prompt":
        print(build_smoke_prompt(args.run_dir, repository_root=args.repo))
        return 0
    elif args.command == "execution-proof":
        try:
            if args.sessions_root is not None:
                if any(
                    value is not None
                    for value in (
                        args.parent_rollout,
                        args.company_rollout,
                        args.skeptic_rollout,
                    )
                ):
                    parser.error("--sessions-root cannot be combined with explicit rollouts")
                result = discover_and_build_run_specialist_execution_proof(
                    args.repo,
                    run_dir=args.run_dir,
                    sessions_root=args.sessions_root,
                )
            else:
                if any(
                    value is None
                    for value in (
                        args.parent_rollout,
                        args.company_rollout,
                        args.skeptic_rollout,
                    )
                ):
                    parser.error("provide --sessions-root or all three explicit rollouts")
                result = build_run_specialist_execution_proof(
                    args.repo,
                    run_dir=args.run_dir,
                    parent_rollout=args.parent_rollout,
                    child_rollouts={
                        "runtime_company_analyst": args.company_rollout,
                        "runtime_skeptic": args.skeptic_rollout,
                    },
                )
        except ExecutionProofError as exc:
            manifest_path = args.run_dir / "run_manifest.json"
            trace_path = args.run_dir / "decision_trace.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            result = fail_run(
                args.run_dir,
                run_id=str(manifest["run_id"]),
                code="NATIVE_EXECUTION_PROOF_FAILED",
                message=str(exc),
                failed_stage=FailureStage.EXECUTION_PROOF,
                trace=trace,
            )
    elif args.command == "replay":
        result = replay_run(args.repo, run_dir=args.run_dir)
        write_replay_result(result, output_path=args.output)
    elif args.command == "artifact-replay":
        try:
            result = replay_run(args.repo, run_dir=args.run_dir)
            write_replay_result(result, output_path=args.output)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failure = {
                "status": "FAIL",
                "reason_code": code_from_error(exc),
                "message": str(exc),
                "command": args.command,
            }
            print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
            return 6
    elif args.command == "eval":
        result = evaluate_run(args.repo, run_dir=args.run_dir)
        persist_eval_result(result, run_dir=args.run_dir)
    elif args.command == "check-run":
        result, exit_code = check_run(args.repo, run_dir=args.run_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "prepare-rerun":
        result = prepare_native_rerun(
            args.repo,
            source_run_dir=args.source_run_dir,
            new_run_dir=args.run_dir,
            new_run_id=args.run_id,
        )
    else:
        try:
            if args.command == "prepare-execution-replay":
                result = prepare_execution_replay(
                    source_run_dir=args.source_run_dir,
                    new_run_dir=args.run_dir,
                    new_run_id=args.run_id,
                    workspace_root=args.workspace,
                )
            elif args.command == "finalize-execution-replay":
                result = finalize_execution_replay(
                    source_run_dir=args.source_run_dir,
                    replay_run_dir=args.run_dir,
                    output_dir=args.output_dir,
                )
            elif args.command == "eval-prepare":
                result = prepare_eval_job(
                    args.repo,
                    run_dir=args.run_dir,
                    eval_dir=args.eval_dir,
                    eval_id=args.eval_id,
                    expected_terminal_states=tuple(args.expected_terminal_state or ("COMPLETED", "SAFE_NO_TRADE")),
                )
            elif args.command == "eval-finalize":
                result = finalize_eval_job(
                    args.repo,
                    eval_dir=args.eval_dir,
                    semantic_result_path=args.semantic_result,
                )
            elif args.command == "eval-smoke-prompt":
                print(build_eval_smoke_prompt(args.repo, eval_dir=args.eval_dir))
                return 0
            elif args.command == "eval-execution-proof":
                parent, child = discover_eval_rollouts(
                    args.sessions_root,
                    eval_dir=args.eval_dir.resolve(),
                    eval_id=str(json.loads((args.eval_dir / "input-manifest.json").read_text(encoding="utf-8"))["eval_id"]),
                )
                proof = build_eval_execution_proof(
                    args.repo,
                    eval_dir=args.eval_dir,
                    semantic_result_path=args.semantic_result,
                    parent_rollout=parent,
                    child_rollout=child,
                )
                persist_eval_execution_proof(proof, eval_dir=args.eval_dir)
                result = {
                    "eval_id": proof["eval_id"],
                    "next_state": "EVAL_EXECUTION_PROOF_VERIFIED",
                    "proof_hash": proof["proof_hash"],
                }
            elif args.command == "eval-calibration":
                from evals.grading.calibration import run_calibration

                result = run_calibration(
                    args.repo,
                    labels_path=args.labels,
                    grader_index_path=args.grader_index,
                    output_dir=args.output_dir,
                )
            elif args.command == "regression":
                from evals.regression.runner import run_regression_suite

                run_index = json.loads(args.run_index.read_text(encoding="utf-8"))
                result = run_regression_suite(
                    args.repo,
                    output_dir=args.output_dir,
                    suite_id=args.suite_id,
                    candidate_hash=args.candidate_hash,
                    run_index=run_index,
                    cache_dir=args.cache_dir,
                    force=args.force,
                )
            elif args.command == "ablation":
                from evals.ablation.runtime import compare_runtime_ablation_set, compare_runtime_variants

                variants = json.loads(args.variants.read_text(encoding="utf-8"))
                if isinstance(variants, dict) and set(variants) == {"cases"}:
                    result = compare_runtime_ablation_set(
                        args.repo,
                        ablation_id=args.ablation_id,
                        cases=variants["cases"],
                        output_dir=args.output_dir,
                    )
                else:
                    result = compare_runtime_variants(
                        args.repo,
                        ablation_id=args.ablation_id,
                        variants=variants,
                        output_dir=args.output_dir,
                    )
            elif args.command == "trace-check":
                trace = json.loads((args.run_dir / "decision_trace.json").read_text(encoding="utf-8"))
                result = trace_integrity_report(trace, run_dir=args.run_dir)
                if args.output.exists():
                    raise ValueError("TRACE_OUTPUT_EXISTS")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            else:
                from evals.promotion.runtime_gate import run_promotion_gate

                result = run_promotion_gate(
                    args.repo,
                    input_manifest_path=args.input_manifest,
                    output_dir=args.output_dir,
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failure = {
                "status": "FAIL",
                "reason_code": code_from_error(exc),
                "message": str(exc),
                "command": args.command,
            }
            print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
            return 6
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    failed = "FAILED_VALIDATION" in {
        result.get("next_state"),
        result.get("terminal_state"),
    }
    if failed:
        return 2
    if result.get("status") in {"FAIL", "FAILED"} or result.get("conclusion") == "NOT_COMPARABLE":
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
