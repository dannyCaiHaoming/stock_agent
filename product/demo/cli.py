"""Agent Package Demo 的本地零 LLM 命令。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .contracts import DemoValidationError
from .runner import run_demo, run_single_agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行零 LLM Agent Package 装配演示")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="运行完整固定数据流")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)

    agent = subparsers.add_parser("agent", help="单独调用一个 Demo Agent Adapter")
    agent.add_argument("--repo", type=Path, required=True)
    agent.add_argument("--input", type=Path, required=True)
    agent.add_argument(
        "--agent",
        choices=("runtime_company_analyst", "runtime_skeptic", "runtime_cio"),
        required=True,
    )
    agent.add_argument("--output", type=Path, required=True)
    agent.add_argument("--analyst-response", type=Path)
    agent.add_argument("--skeptic-response", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            result = run_demo(
                args.repo, input_path=args.input, output_dir=args.output_dir
            )
        else:
            result = run_single_agent(
                args.repo,
                input_path=args.input,
                agent=args.agent,
                output_path=args.output,
                analyst_response_path=args.analyst_response,
                skeptic_response_path=args.skeptic_response,
            )
    except (DemoValidationError, OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "terminal_state": "DEMO_FAILED_VALIDATION",
                    "failure_code": str(exc).split(":", 1)[0],
                    "message": str(exc),
                    "llm_used": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
