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
from .smoke_prompt import build_smoke_prompt


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

    rerun = subparsers.add_parser("prepare-rerun")
    rerun.add_argument("--repo", type=Path, required=True)
    rerun.add_argument("--source-run-dir", type=Path, required=True)
    rerun.add_argument("--run-dir", type=Path, required=True)
    rerun.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare_run(
            args.repo,
            fixture_path=args.fixture,
            run_dir=args.run_dir,
            run_id=args.run_id,
            model=args.model,
            research_question=args.question,
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
                trace=trace,
            )
    elif args.command == "replay":
        result = replay_run(args.repo, run_dir=args.run_dir)
        write_replay_result(result, output_path=args.output)
    elif args.command == "eval":
        result = evaluate_run(args.repo, run_dir=args.run_dir)
        persist_eval_result(result, run_dir=args.run_dir)
    else:
        result = prepare_native_rerun(
            args.repo,
            source_run_dir=args.source_run_dir,
            new_run_dir=args.run_dir,
            new_run_id=args.run_id,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    failed = "FAILED_VALIDATION" in {
        result.get("next_state"),
        result.get("terminal_state"),
    }
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
