"""Command-line seam for Portfolio Intake deterministic processing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .service import (
    REPO_ROOT,
    IntakeValidationError,
    apply_corrections,
    build_council_portfolio_input,
    build_draft,
    build_handoff,
    build_manual_draft,
    build_risk_input,
    render_draft_summary,
    validate_draft,
    validate_handoff,
)


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IntakeValidationError("INTAKE_JSON_OBJECT_REQUIRED")
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
        raise IntakeValidationError("INTAKE_PRIVATE_ARTIFACT_INSIDE_REPO")
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
    confirm.add_argument("--holding-horizon", required=True)
    confirm.add_argument("--research-question", required=True)
    confirm.add_argument("--benchmark-id", default="SP500")
    confirm.add_argument("--mandate-artifact-id", default="mandate:us-equity-long-only-v1")
    confirm.add_argument("--batch-size", type=int, default=5)
    confirm.add_argument(
        "--explicit-confirmation",
        choices=["CONFIRM_PORTFOLIO"],
        required=True,
        help="仅在用户明确确认当前 draft_hash 后传入",
    )

    validate = commands.add_parser("validate-handoff", help="独立校验 Handoff")
    validate.add_argument("--handoff", required=True)
    validate.add_argument("--draft")

    risk = commands.add_parser("risk-input", help="生成绑定完整组合的 Risk 前置输入")
    risk.add_argument("--handoff", required=True)
    risk.add_argument("--output", required=True)

    council = commands.add_parser("council-input", help="生成保留完整多资产组合的 Council 输入")
    council.add_argument("--handoff", required=True)
    council.add_argument("--output", required=True)
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
                raise IntakeValidationError("INTAKE_CORRECTIONS_REQUIRED")
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
                holding_horizon=args.holding_horizon,
                research_question=args.research_question,
                benchmark_id=args.benchmark_id,
                mandate_artifact_id=args.mandate_artifact_id,
                batch_size=args.batch_size,
            )
            _write_json(args.output, value)
        elif args.command == "validate-handoff":
            handoff = _read_json(args.handoff)
            draft = _read_json(args.draft) if args.draft else None
            validate_handoff(handoff, source_draft=draft)
            print(json.dumps({"status": "PASSED", "handoff_hash": handoff["handoff_hash"]}))
        elif args.command == "risk-input":
            _write_json(args.output, build_risk_input(_read_json(args.handoff)))
        elif args.command == "council-input":
            _write_json(args.output, build_council_portfolio_input(_read_json(args.handoff)))
        else:  # pragma: no cover - argparse owns this branch
            raise IntakeValidationError("INTAKE_COMMAND_UNKNOWN")
    except (IntakeValidationError, json.JSONDecodeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
