"""Command-line seam for Portfolio Intake deterministic processing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from product.council.intake_planning import (
    CouncilPlanningError,
    build_council_request,
    build_research_plan,
    validate_council_request,
)

from .service import IntakeValidationError as IntakeV2ValidationError
from .service import validate_draft as validate_draft_v2
from .service import validate_handoff as validate_handoff_v2
from .v3 import (
    REPO_ROOT,
    IntakeV3ValidationError,
    apply_corrections,
    build_draft,
    build_handoff,
    build_manual_draft,
    render_draft_summary,
    validate_draft,
    validate_handoff,
)


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IntakeV3ValidationError("INTAKE_JSON_OBJECT_REQUIRED")
    return value


def _is_inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def _contains_private_source(value: Mapping[str, Any]) -> bool:
    items = value.get("source_items", [])
    return isinstance(items, list) and any(
        isinstance(item, Mapping) and item.get("synthetic") is False for item in items
    )


def _write_json(path_value: str, value: Mapping[str, Any]) -> None:
    path = Path(path_value).expanduser().resolve()
    if _contains_private_source(value) and _is_inside_repo(path):
        raise IntakeV3ValidationError("INTAKE_PRIVATE_ARTIFACT_INSIDE_REPO")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio Intake deterministic seam")
    commands = parser.add_subparsers(dest="command", required=True)

    draft = commands.add_parser("draft", help="从结构化观察创建 PortfolioDraft")
    draft.add_argument("--input", required=True)
    draft.add_argument("--output", required=True)

    manual = commands.add_parser("manual-draft", help="从简洁手工持仓创建 PortfolioDraft")
    manual.add_argument("--input", required=True)
    manual.add_argument("--output", required=True)

    correct = commands.add_parser("correct", help="应用用户明确修订")
    correct.add_argument("--draft", required=True)
    correct.add_argument("--corrections", required=True)
    correct.add_argument("--output", required=True)

    summary = commands.add_parser("summary", help="渲染中文确认摘要")
    summary.add_argument("--draft", required=True)

    confirm = commands.add_parser("confirm", help="显式确认并生成 PortfolioHandoff")
    confirm.add_argument("--draft", required=True)
    confirm.add_argument("--output", required=True)
    confirm.add_argument("--confirmed-at", required=True)
    confirm.add_argument(
        "--explicit-confirmation",
        choices=["CONFIRM_PORTFOLIO"],
        required=True,
        help="仅在用户明确确认当前 draft_hash 后传入",
    )

    validate = commands.add_parser("validate-handoff", help="独立校验 Handoff；历史 v2 必须显式选择")
    validate.add_argument("--handoff", required=True)
    validate.add_argument("--draft")
    validate.add_argument("--schema-version", choices=["v2", "v3"], default="v3")

    request = commands.add_parser("council-request", help="为已确认 Handoff 创建独立研究请求")
    request.add_argument("--handoff", required=True)
    request.add_argument("--output", required=True)
    request.add_argument("--request-id", required=True)
    request.add_argument("--research-question", required=True)
    request.add_argument("--holding-horizon", required=True)
    request.add_argument("--benchmark-id", default="SP500")
    request.add_argument("--mandate-artifact-id", default="mandate:advisory-only-v1")
    request.add_argument("--constraints")

    validate_request = commands.add_parser("validate-council-request", help="校验 CouncilRequest 绑定")
    validate_request.add_argument("--handoff", required=True)
    validate_request.add_argument("--request", required=True)

    council = commands.add_parser("council-plan", help="生成零 Agent/LLM 的全持仓规划")
    council.add_argument("--handoff", required=True)
    council.add_argument("--request", required=True)
    council.add_argument("--output", required=True)
    council.add_argument("--batch-size", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "draft":
            _write_json(args.output, build_draft(_read_json(args.input)))
        elif args.command == "manual-draft":
            _write_json(args.output, build_manual_draft(_read_json(args.input)))
        elif args.command == "correct":
            correction_package = _read_json(args.corrections)
            corrections = correction_package.get("corrections")
            if not isinstance(corrections, list):
                raise IntakeV3ValidationError("INTAKE_CORRECTIONS_REQUIRED")
            value = apply_corrections(
                _read_json(args.draft),
                correction_source=correction_package.get("source_item", {}),
                corrections=corrections,
            )
            _write_json(args.output, value)
        elif args.command == "summary":
            print(render_draft_summary(_read_json(args.draft)))
        elif args.command == "confirm":
            value = build_handoff(
                _read_json(args.draft),
                confirmed=args.explicit_confirmation == "CONFIRM_PORTFOLIO",
                confirmed_at=args.confirmed_at,
            )
            _write_json(args.output, value)
        elif args.command == "validate-handoff":
            handoff = _read_json(args.handoff)
            draft = _read_json(args.draft) if args.draft else None
            if args.schema_version == "v2":
                validate_handoff_v2(handoff, source_draft=draft)
            else:
                validate_handoff(handoff, source_draft=draft)
            print(json.dumps({"status": "PASSED", "handoff_hash": handoff["handoff_hash"]}))
        elif args.command == "council-request":
            constraints = _read_json(args.constraints) if args.constraints else {}
            value = build_council_request(
                _read_json(args.handoff), request_id=args.request_id,
                research_question=args.research_question, holding_horizon=args.holding_horizon,
                benchmark_id=args.benchmark_id, mandate_artifact_id=args.mandate_artifact_id,
                constraints=constraints,
            )
            _write_json(args.output, value)
        elif args.command == "validate-council-request":
            request = _read_json(args.request)
            validate_council_request(request, handoff=_read_json(args.handoff))
            print(json.dumps({"status": "PASSED", "request_hash": request["request_hash"]}))
        elif args.command == "council-plan":
            _write_json(
                args.output,
                build_research_plan(
                    _read_json(args.handoff), _read_json(args.request), batch_size=args.batch_size
                ),
            )
        else:  # pragma: no cover - argparse owns this branch
            raise IntakeV3ValidationError("INTAKE_COMMAND_UNKNOWN")
    except (
        IntakeV3ValidationError,
        IntakeV2ValidationError,
        CouncilPlanningError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
