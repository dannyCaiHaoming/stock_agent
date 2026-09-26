"""Deterministic command surface consumed by the portfolio-council Skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .execution_proof import (
    ExecutionProofError,
    build_ephemeral_run_specialist_execution_proof,
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
from .nested_codex import launch_nested_codex
from .environment_preflight import reject_legacy_entry
from .common_stock_stage import (
    build_common_stock_stage_prompt,
    launch_common_stock_stage,
    persist_common_stock_report_package,
    prepare_common_stock_stage_run,
    validate_common_stock_stage_run_package,
)
from .common_stock_eval import (
    build_common_stock_eval_prompt,
    finalize_common_stock_eval_job,
    launch_common_stock_eval,
    prepare_common_stock_eval_job,
)
from .common_stock_data import (
    attach_research_supplement,
    assemble_common_stock_evidence_from_live_snapshot,
    collect_common_stock_data_from_handoff,
)
from .multidimensional_stage import (
    assemble_canonical_holding_research_package,
    build_multidimensional_stage_prompt,
    check_multidimensional_bundle_consumable,
    launch_multidimensional_stage,
    prepare_multidimensional_stage_run,
)
from .research_materials_stage import (
    build_research_materials_stage_prompt,
    launch_research_materials_stage,
    prepare_research_materials_stage,
    materialize_selected_peers,
)
from .independent_skeptic_stage import (
    prepare_skeptic_phase, launch_skeptic_phase, finalize_skeptic_phase,
    prepare_skeptic_resume,
    validate_forward_gate,
)
from .predecision_cio_stage import (
    check_predecision_cio_trace, finalize_predecision_cio_advice,
    finalize_predecision_cio_research, launch_predecision_cio_run,
    prepare_predecision_cio_run,
)
from .research_consumption_audit import build_research_consumption_audit, render_audit_summary


def build_parser() -> argparse.ArgumentParser:
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

    live = subparsers.add_parser("prepare-live", help="已退役：仅保留显式失败以防旧调用静默回退")
    live.add_argument("--repo", type=Path, required=True)
    live.add_argument("--profile", choices=("live-us-equity",), required=True)
    live.add_argument("--portfolio", type=Path, required=True)
    live.add_argument("--snapshot", type=Path, required=True)
    live.add_argument("--cache-root", type=Path, required=True)
    live.add_argument("--calendar-lock", type=Path, required=True)
    live.add_argument("--run-dir", type=Path, required=True)
    live.add_argument("--run-id", required=True)
    live.add_argument("--model", required=True)
    live.add_argument("--focus-security-id")

    collection = subparsers.add_parser("collect-live", help="宿主显式调用的 live 采集；需已批准的外置来源配置")
    collection.add_argument("--repo", type=Path, required=True)
    collection.add_argument("--portfolio", type=Path, required=True)
    collection.add_argument("--source-access", type=Path, required=True)
    collection.add_argument("--output-dir", type=Path, required=True)
    collection.add_argument("--cache-root", type=Path, required=True)

    stock_prepare = subparsers.add_parser(
        "prepare-common-stock-research",
        help="从已确认 Handoff 与冻结 Gate 准备普通股研究阶段；不启动模型",
    )
    stock_prepare.add_argument("--repo", type=Path, required=True)
    stock_prepare.add_argument("--handoff", type=Path, required=True)
    stock_prepare.add_argument("--gate", type=Path, required=True)
    stock_prepare.add_argument("--data-preparation", type=Path)
    stock_prepare.add_argument("--source-bundle", type=Path)
    stock_prepare.add_argument("--run-dir", type=Path, required=True)
    stock_prepare.add_argument("--run-id", required=True)
    stock_prepare.add_argument("--model", required=True)
    stock_prepare.add_argument("--question", default="分析已确认的普通股持仓。")
    stock_prepare.add_argument("--source-fixture", type=Path)
    stock_prepare.add_argument("--max-concurrency", type=int, default=3)
    stock_prepare.add_argument("--focus-security-id")
    stock_prepare.add_argument("--memory-root", type=Path)
    stock_prepare.add_argument(
        "--force-rerun", action="store_true",
        help="忽略严格等价的持久化报告并创建新的 Company Agent 调用",
    )
    stock_prepare.add_argument(
        "--equity-research-package", type=Path, action="append", default=[],
        help="可重复；按 security_id 绑定的冻结估值/基本面/同行附件包",
    )

    stock_data = subparsers.add_parser(
        "prepare-common-stock-data",
        help="将既有只读 live 冻结物转换为普通股研究 Gate；不启动模型或组合估值",
    )
    stock_data.add_argument("--handoff", type=Path, required=True)
    stock_data.add_argument("--portfolio", type=Path, required=True)
    stock_data.add_argument("--snapshot", type=Path, required=True)
    stock_data.add_argument("--calendar", type=Path, required=True)
    stock_data.add_argument("--output-dir", type=Path, required=True)
    stock_data.add_argument("--run-id", required=True)

    stock_collect = subparsers.add_parser(
        "collect-common-stock-data",
        help="从已确认 Handoff 经现有只读适配器自动准备普通股研究 Gate；不启动模型",
    )
    stock_collect.add_argument("--repo", type=Path, required=True)
    stock_collect.add_argument("--handoff", type=Path, required=True)
    stock_collect.add_argument("--source-access", type=Path, required=True)
    stock_collect.add_argument("--output-dir", type=Path, required=True)
    stock_collect.add_argument("--cache-root", type=Path)
    stock_collect.add_argument("--memory-root", type=Path)
    stock_collect.add_argument("--run-id", required=True)
    stock_collect.add_argument("--benchmark-id")
    stock_collect.add_argument("--benchmark-ticker")

    stock_supplement = subparsers.add_parser(
        "attach-research-supplement",
        help="把冻结的三源补充包接入既有普通股 Gate；不采集网络或启动模型",
    )
    stock_supplement.add_argument("--data-dir", type=Path, required=True)
    stock_supplement.add_argument("--background", type=Path, required=True)
    stock_supplement.add_argument("--package", type=Path, required=True)
    stock_supplement.add_argument("--batch", type=Path, required=True)

    stock_prompt = subparsers.add_parser("common-stock-research-prompt")
    stock_prompt.add_argument("--repo", type=Path, required=True)
    stock_prompt.add_argument("--run-dir", type=Path, required=True)

    stock_validate = subparsers.add_parser(
        "validate-common-stock-research",
        help="验证已准备的普通股研究运行包；不启动模型",
    )
    stock_validate.add_argument("--repo", type=Path, required=True)
    stock_validate.add_argument("--run-dir", type=Path, required=True)

    stock_persist = subparsers.add_parser(
        "persist-common-stock-report",
        help="重新验证并补存一个既有普通股研究报告；不访问 Provider 或调用模型",
    )
    stock_persist.add_argument("--repo", type=Path, required=True)
    stock_persist.add_argument("--run-dir", type=Path, required=True)
    stock_persist.add_argument("--security-id", required=True)

    stock_launch = subparsers.add_parser(
        "launch-common-stock-research", help="仅宿主入口：运行普通股 Company Analyst 子任务"
    )
    stock_launch.add_argument("--repo", type=Path, required=True)
    stock_launch.add_argument("--run-dir", type=Path, required=True)
    stock_launch.add_argument("--codex-binary", default="codex")
    stock_launch.add_argument("--timeout-seconds", type=int, default=1800)

    multi_prepare = subparsers.add_parser(
        "prepare-multidimensional-research",
        help="从确认 Handoff 与冻结 Gate 准备免费多维研究阶段；不启动模型",
    )
    multi_prepare.add_argument("--repo", type=Path, required=True)
    multi_prepare.add_argument("--handoff", type=Path, required=True)
    multi_prepare.add_argument("--gate", type=Path, required=True)
    multi_prepare.add_argument("--run-dir", type=Path, required=True)
    multi_prepare.add_argument("--run-id", required=True)
    multi_prepare.add_argument("--model", required=True)
    multi_prepare.add_argument(
        "--stage", default="MULTI_DIMENSIONAL_HOLDING_RESEARCH",
        choices=("MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH"),
    )
    multi_prepare.add_argument("--question", default="补全普通股持仓的免费多维研究资料。")
    multi_prepare.add_argument("--benchmark-id", default="US:SPY")
    multi_prepare.add_argument("--peer-candidates", type=Path)
    multi_prepare.add_argument(
        "--company-research-run", type=Path,
        help="可选：已完成且将被重新验证、冻结复制的普通股研究运行目录",
    )
    multi_prepare.add_argument(
        "--research-materials-run", type=Path,
        help="可选：已完成且将被重新验证、冻结复制的资料准备运行目录",
    )
    multi_prepare.add_argument("--max-concurrency", type=int, default=3)

    multi_prompt = subparsers.add_parser("multidimensional-research-prompt")
    multi_prompt.add_argument("--repo", type=Path, required=True)
    multi_prompt.add_argument("--run-dir", type=Path, required=True)

    multi_launch = subparsers.add_parser(
        "launch-multidimensional-research",
        help="仅宿主入口：运行多维 Company Analyst / Market Catalyst 任务",
    )
    multi_launch.add_argument("--repo", type=Path, required=True)
    multi_launch.add_argument("--run-dir", type=Path, required=True)
    multi_launch.add_argument("--codex-binary", default="codex")
    multi_launch.add_argument("--timeout-seconds", type=int, default=2400)
    multi_launch.add_argument(
        "--task-name",
        help="只执行目标任务及其最小依赖闭包并保存定点执行证明；不生成完整研究包",
    )

    multi_consume = subparsers.add_parser(
        "check-multidimensional-consumption",
        help="只读解析多维研究包并保存下游消费证明；不启动模型",
    )
    multi_consume.add_argument("--repo", type=Path, required=True)
    multi_consume.add_argument("--run-dir", type=Path, required=True)

    counter_prepare = subparsers.add_parser(
        "prepare-independent-skeptic", help="只在当前运行正向包就绪后准备逐证券独立反证；不启动模型",
    )
    counter_prepare.add_argument("--repo", type=Path, required=True)
    counter_prepare.add_argument("--run-dir", type=Path, required=True)

    counter_launch = subparsers.add_parser(
        "launch-independent-skeptic", help="仅宿主入口：逐证券派发只读独立反证",
    )
    counter_launch.add_argument("--repo", type=Path, required=True)
    counter_launch.add_argument("--run-dir", type=Path, required=True)
    counter_launch.add_argument("--codex-binary", default="codex")
    counter_launch.add_argument("--timeout-seconds", type=int, default=2400)

    counter_resume = subparsers.add_parser(
        "resume-independent-skeptic", help="仅宿主入口：冻结输入不变时只重试未完成的反证任务",
    )
    counter_resume.add_argument("--repo", type=Path, required=True)
    counter_resume.add_argument("--run-dir", type=Path, required=True)
    counter_resume.add_argument("--codex-binary", default="codex")
    counter_resume.add_argument("--timeout-seconds", type=int, default=2400)

    counter_check = subparsers.add_parser(
        "check-independent-skeptic", help="只读验证本次正向研究包的反证前置门禁",
    )
    counter_check.add_argument("--repo", type=Path, required=True)
    counter_check.add_argument("--run-dir", type=Path, required=True)

    counter_finalize = subparsers.add_parser(
        "finalize-independent-skeptic", help="确定性归集真实反证报告和执行证明；不启动模型",
    )
    counter_finalize.add_argument("--repo", type=Path, required=True)
    counter_finalize.add_argument("--run-dir", type=Path, required=True)

    cio_prepare = subparsers.add_parser(
        "prepare-predecision-cio", help="重验正反研究包并在独立目录冻结 CIO 输入；不启动模型",
    )
    cio_prepare.add_argument("--repo", type=Path, required=True)
    cio_prepare.add_argument("--source-run", type=Path, required=True)
    cio_prepare.add_argument("--run-dir", type=Path, required=True)
    cio_prepare.add_argument("--run-id", required=True)
    cio_prepare.add_argument("--target-security-id", required=True)
    cio_prepare.add_argument("--requested-level", choices=("RESEARCH_SYNTHESIS", "PORTFOLIO_ADVICE"), default="RESEARCH_SYNTHESIS")
    cio_prepare.add_argument("--time-mode", choices=("SOURCE_CUTOFF", "CURRENT"), default="SOURCE_CUTOFF")
    cio_prepare.add_argument("--max-research-age-days", type=int)
    cio_prepare.add_argument("--mandate", type=Path)
    cio_prepare.add_argument("--model")

    cio_launch = subparsers.add_parser(
        "launch-predecision-cio", help="仅宿主入口：运行一次已准备的正反研究 CIO 综合",
    )
    cio_launch.add_argument("--repo", type=Path, required=True)
    cio_launch.add_argument("--run-dir", type=Path, required=True)
    cio_launch.add_argument("--codex-binary", default="codex")
    cio_launch.add_argument("--timeout-seconds", type=int, default=2400)

    cio_finalize = subparsers.add_parser(
        "finalize-predecision-cio-research", help="验证并渲染已完成的非动作 CIO 研究综合",
    )
    cio_finalize.add_argument("--repo", type=Path, required=True)
    cio_finalize.add_argument("--run-dir", type=Path, required=True)

    cio_advice_finalize = subparsers.add_parser(
        "finalize-predecision-cio-advice", help="已退役：明确拒绝本阶段尚未验收的持仓建议",
    )
    cio_advice_finalize.add_argument("--repo", type=Path, required=True)
    cio_advice_finalize.add_argument("--run-dir", type=Path, required=True)

    cio_trace = subparsers.add_parser(
        "check-predecision-cio", help="只读核验研究级 CIO 阶段的来源、模型、Evidence 与终态血缘",
    )
    cio_trace.add_argument("--repo", type=Path, required=True)
    cio_trace.add_argument("--run-dir", type=Path, required=True)

    multi_assemble = subparsers.add_parser(
        "assemble-canonical-holding-research",
        help="只读重验既有公司与多维研究产物并形成 canonical 下游交接包；不启动模型",
    )
    multi_assemble.add_argument("--repo", type=Path, required=True)
    multi_assemble.add_argument("--base-run", type=Path, required=True)
    multi_assemble.add_argument("--company-research-run", type=Path, required=True)
    multi_assemble.add_argument("--output-dir", type=Path, required=True)
    multi_assemble.add_argument("--supplement-run", type=Path, action="append", default=[])

    materials_prepare = subparsers.add_parser(
        "prepare-research-materials",
        help="准备研报发现与同行选择任务；不启动模型或网络",
    )
    materials_prepare.add_argument("--repo", type=Path, required=True)
    materials_prepare.add_argument("--handoff", type=Path, required=True)
    materials_prepare.add_argument("--gate", type=Path, required=True)
    materials_prepare.add_argument("--peer-candidates", type=Path, required=True)
    materials_prepare.add_argument("--run-dir", type=Path, required=True)
    materials_prepare.add_argument("--run-id", required=True)
    materials_prepare.add_argument("--model", required=True)
    materials_prepare.add_argument("--max-concurrency", type=int, default=3)

    materials_prompt = subparsers.add_parser("research-materials-prompt")
    materials_prompt.add_argument("--repo", type=Path, required=True)
    materials_prompt.add_argument("--run-dir", type=Path, required=True)

    materials_launch = subparsers.add_parser(
        "launch-research-materials",
        help="仅宿主入口：运行研报发现与同行选择准备任务",
    )
    materials_launch.add_argument("--repo", type=Path, required=True)
    materials_launch.add_argument("--run-dir", type=Path, required=True)
    materials_launch.add_argument("--codex-binary", default="codex")
    materials_launch.add_argument("--timeout-seconds", type=int, default=1800)

    peer_materialize = subparsers.add_parser(
        "materialize-selected-peers",
        help="从资料准备输出核实并冻结有限同行资料；不调用模型",
    )
    peer_materialize.add_argument("--materials-run", type=Path, required=True)
    peer_materialize.add_argument("--source-access", type=Path, required=True)
    peer_materialize.add_argument("--cache-root", type=Path, required=True)
    peer_materialize.add_argument("--output-dir", type=Path, required=True)

    stock_eval_prepare = subparsers.add_parser("common-stock-eval-prepare")
    stock_eval_prepare.add_argument("--report", type=Path, required=True)
    stock_eval_prepare.add_argument("--request", type=Path, required=True)
    stock_eval_prepare.add_argument("--gate", type=Path, required=True)
    stock_eval_prepare.add_argument("--rubric", type=Path, required=True)
    stock_eval_prepare.add_argument("--mcp-events", type=Path)
    stock_eval_prepare.add_argument("--output-dir", type=Path, required=True)
    stock_eval_prepare.add_argument("--eval-id", required=True)

    stock_eval_prompt = subparsers.add_parser("common-stock-eval-prompt")
    stock_eval_prompt.add_argument("--eval-dir", type=Path, required=True)

    stock_eval_finalize = subparsers.add_parser("common-stock-eval-finalize")
    stock_eval_finalize.add_argument("--eval-dir", type=Path, required=True)
    stock_eval_finalize.add_argument("--semantic-result", type=Path, required=True)

    stock_eval_launch = subparsers.add_parser(
        "launch-common-stock-eval",
        help="仅宿主入口：使用既有 dev_eval Agent 评价一份普通股研究报告",
    )
    stock_eval_launch.add_argument("--repo", type=Path, required=True)
    stock_eval_launch.add_argument("--eval-dir", type=Path, required=True)
    stock_eval_launch.add_argument("--model", default="gpt-5.6-terra")
    stock_eval_launch.add_argument("--codex-binary", default="codex")
    stock_eval_launch.add_argument("--timeout-seconds", type=int, default=900)

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
    prompt.add_argument("--sessions-root", type=Path)

    proof = subparsers.add_parser("execution-proof")
    proof.add_argument("--repo", type=Path, required=True)
    proof.add_argument("--run-dir", type=Path, required=True)
    proof.add_argument("--parent-rollout", type=Path)
    proof.add_argument("--company-rollout", type=Path)
    proof.add_argument("--skeptic-rollout", type=Path)
    proof.add_argument("--sessions-root", type=Path)
    proof.add_argument("--codex-events", type=Path)
    proof.add_argument("--hook-events", type=Path)
    proof.add_argument("--latency-ms", type=int)

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
    eval_prompt.add_argument("--sessions-root", type=Path)

    eval_proof = subparsers.add_parser("eval-execution-proof")
    eval_proof.add_argument("--repo", type=Path, required=True)
    eval_proof.add_argument("--eval-dir", type=Path, required=True)
    eval_proof.add_argument("--semantic-result", type=Path, required=True)
    eval_proof.add_argument("--sessions-root", type=Path, required=True)
    eval_proof.add_argument("--collect-native-output", action="store_true")

    calibration = subparsers.add_parser("eval-calibration")
    calibration.add_argument("--repo", type=Path, required=True)
    calibration.add_argument("--labels", type=Path, required=True)
    calibration.add_argument("--grader-index", type=Path, required=True)
    calibration.add_argument("--output-dir", type=Path, required=True)

    calibration_proof = subparsers.add_parser("calibration-execution-proof")
    calibration_proof.add_argument("--repo", type=Path, required=True)
    calibration_proof.add_argument("--case-id", required=True)
    calibration_proof.add_argument("--repeat", type=int, required=True)
    calibration_proof.add_argument("--grader-output", type=Path, required=True)
    calibration_proof.add_argument("--parent-rollout", type=Path, required=True)
    calibration_proof.add_argument("--child-rollout", type=Path, required=True)
    calibration_proof.add_argument("--prompt", type=Path, required=True)
    calibration_proof.add_argument("--input", type=Path, required=True)
    calibration_proof.add_argument("--output", type=Path, required=True)

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

    test_evidence = subparsers.add_parser("test-evidence")
    test_evidence.add_argument("--repo", type=Path, required=True)
    test_evidence.add_argument("--output-dir", type=Path, required=True)
    test_evidence.add_argument("--tmpdir", type=Path, required=True)
    test_evidence.add_argument("--test-target", action="append", default=[])

    trace_check = subparsers.add_parser("trace-check")
    trace_check.add_argument("--run-dir", type=Path, required=True)
    trace_check.add_argument("--output", type=Path, required=True)

    research_audit = subparsers.add_parser("audit-research-consumption", help="只读核对冻结资料交付与报告引用")
    research_audit.add_argument("--run-dir", type=Path, required=True)
    research_audit.add_argument("--company-run", type=Path)
    research_audit.add_argument("--cio-run", type=Path)
    research_audit.add_argument("--output-dir", type=Path, required=True)

    nested = subparsers.add_parser("nested-codex-smoke")
    nested.add_argument("--repo", type=Path, required=True)
    nested.add_argument("--run-dir", type=Path, required=True)
    nested.add_argument("--codex-binary", default="codex")
    nested.add_argument("--timeout-seconds", type=int, default=1800)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        reject_legacy_entry(arguments)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "failure_code": str(exc), "llm_calls": 0}))
        return 2
    args = parser.parse_args(arguments)
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
    elif args.command == "collect-common-stock-data":
        try:
            import os
            result = collect_common_stock_data_from_handoff(
                args.handoff, access_path=args.source_access,
                output_dir=args.output_dir, cache_root=args.cache_root,
                sec_user_agent=os.environ.get("SEC_USER_AGENT", ""),
                run_id=args.run_id,
                benchmark_id=args.benchmark_id,
                benchmark_ticker=args.benchmark_ticker,
                collect_research_supplements=True,
                repository_root=args.repo, memory_root=args.memory_root,
            )
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            print(json.dumps({
                "status": "FAILED", "failure_code": str(exc).split(":", 1)[0],
                "command": args.command, "llm_calls": 0,
            }, ensure_ascii=False))
            return 2
    elif args.command == "attach-research-supplement":
        try:
            result = attach_research_supplement(
                args.data_dir, background_path=args.background,
                package_path=args.package, batch_path=args.batch,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({
                "status": "FAILED", "failure_code": str(exc).split(":", 1)[0],
                "command": args.command, "llm_calls": 0,
            }, ensure_ascii=False))
            return 2
    elif args.command == "prepare-common-stock-data":
        try:
            from product.mcp.live.contracts import external_path
            from product.mcp.live.market import load_locked_calendar
            output_dir = external_path(args.output_dir)
            if output_dir.exists():
                raise ValueError("COMMON_STOCK_DATA_OUTPUT_EXISTS")
            values = [
                json.loads(external_path(path).read_text(encoding="utf-8"))
                for path in (args.handoff, args.portfolio, args.snapshot, args.calendar)
            ]
            prepared = assemble_common_stock_evidence_from_live_snapshot(
                values[0], live_portfolio=values[1], snapshot=values[2],
                calendar=load_locked_calendar(values[3]), run_id=args.run_id,
            )
            output_dir.mkdir(parents=True, mode=0o700)
            for name, value in (
                ("gate.json", prepared["gate"]),
                ("data-preparation.json", prepared["preparation"]),
            ):
                (output_dir / name).write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            result = {
                "status": "FROZEN", "run_id": args.run_id,
                "gate": str(output_dir / "gate.json"),
                "data_preparation": str(output_dir / "data-preparation.json"),
            }
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            print(json.dumps({
                "status": "FAILED", "failure_code": str(exc).split(":", 1)[0],
                "command": args.command, "llm_calls": 0,
            }, ensure_ascii=False))
            return 2
    elif args.command == "prepare-common-stock-research":
        result = prepare_common_stock_stage_run(
            args.repo, handoff_path=args.handoff, gate_path=args.gate,
            run_dir=args.run_dir, run_id=args.run_id, model=args.model,
            research_question=args.question, source_fixture=args.source_fixture,
            target_concurrency=args.max_concurrency,
            data_preparation_path=args.data_preparation,
            source_bundle_path=args.source_bundle,
            focus_security_id=args.focus_security_id,
            equity_research_package_paths=args.equity_research_package,
            memory_root=args.memory_root, force_rerun=args.force_rerun,
        )
    elif args.command == "common-stock-research-prompt":
        print(build_common_stock_stage_prompt(args.repo, args.run_dir))
        return 0
    elif args.command == "validate-common-stock-research":
        result = validate_common_stock_stage_run_package(args.repo, args.run_dir)
    elif args.command == "persist-common-stock-report":
        result = persist_common_stock_report_package(
            args.repo, args.run_dir, security_id=args.security_id,
        )
    elif args.command == "launch-common-stock-research":
        result, exit_code = launch_common_stock_stage(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "prepare-multidimensional-research":
        result = prepare_multidimensional_stage_run(
            args.repo, handoff_path=args.handoff, gate_path=args.gate,
            run_dir=args.run_dir, run_id=args.run_id, model=args.model,
            research_question=args.question, benchmark_id=args.benchmark_id,
            target_concurrency=args.max_concurrency,
            peer_candidate_pool_path=args.peer_candidates,
            company_research_run_path=args.company_research_run,
            research_materials_run_path=args.research_materials_run,
            stage=args.stage,
        )
    elif args.command == "multidimensional-research-prompt":
        print(build_multidimensional_stage_prompt(args.repo, args.run_dir))
        return 0
    elif args.command == "launch-multidimensional-research":
        result, exit_code = launch_multidimensional_stage(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds, task_name=args.task_name,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "check-multidimensional-consumption":
        result = check_multidimensional_bundle_consumable(args.repo, args.run_dir)
    elif args.command == "prepare-independent-skeptic":
        result = prepare_skeptic_phase(args.repo, args.run_dir)
    elif args.command == "launch-independent-skeptic":
        result, exit_code = launch_skeptic_phase(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "resume-independent-skeptic":
        prepared = prepare_skeptic_resume(args.repo, args.run_dir)
        result, exit_code = launch_skeptic_phase(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds, index_ref=prepared["dispatch_index"],
            task_names=prepared["retry_task_names"],
        )
        print(json.dumps({"resume": prepared, "result": result}, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "check-independent-skeptic":
        result = validate_forward_gate(args.repo, args.run_dir)
    elif args.command == "finalize-independent-skeptic":
        result = finalize_skeptic_phase(args.repo, args.run_dir)
    elif args.command == "prepare-predecision-cio":
        result = prepare_predecision_cio_run(
            args.repo, source_run_dir=args.source_run, run_dir=args.run_dir,
            run_id=args.run_id, target_security_id=args.target_security_id,
            requested_level=args.requested_level, time_mode=args.time_mode,
            max_research_age_days=args.max_research_age_days,
            mandate_path=args.mandate, model=args.model,
        )
    elif args.command == "launch-predecision-cio":
        result, exit_code = launch_predecision_cio_run(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "finalize-predecision-cio-research":
        result = finalize_predecision_cio_research(args.repo, args.run_dir)
    elif args.command == "finalize-predecision-cio-advice":
        result = finalize_predecision_cio_advice(args.repo, args.run_dir)
    elif args.command == "check-predecision-cio":
        result = check_predecision_cio_trace(args.repo, args.run_dir)
    elif args.command == "assemble-canonical-holding-research":
        result = assemble_canonical_holding_research_package(
            args.repo,
            base_run_dir=args.base_run,
            company_research_run_dir=args.company_research_run,
            output_dir=args.output_dir,
            supplement_run_dirs=args.supplement_run,
        )
    elif args.command == "prepare-research-materials":
        result = prepare_research_materials_stage(
            args.repo, handoff_path=args.handoff, gate_path=args.gate,
            peer_candidate_pool_path=args.peer_candidates, run_dir=args.run_dir,
            run_id=args.run_id, model=args.model,
            target_concurrency=args.max_concurrency,
        )
    elif args.command == "research-materials-prompt":
        print(build_research_materials_stage_prompt(args.repo, args.run_dir))
        return 0
    elif args.command == "launch-research-materials":
        result, exit_code = launch_research_materials_stage(
            args.repo, run_dir=args.run_dir, codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "materialize-selected-peers":
        import os
        result = materialize_selected_peers(
            args.materials_run, source_access_path=args.source_access,
            cache_root=args.cache_root, sec_user_agent=os.environ.get("SEC_USER_AGENT", ""),
            output_dir=args.output_dir,
        )
    elif args.command == "common-stock-eval-prepare":
        result = prepare_common_stock_eval_job(
            report_path=args.report, request_path=args.request, gate_path=args.gate,
            rubric_path=args.rubric, output_dir=args.output_dir, eval_id=args.eval_id,
            mcp_events_path=args.mcp_events,
        )
    elif args.command == "common-stock-eval-prompt":
        print(build_common_stock_eval_prompt(args.eval_dir))
        return 0
    elif args.command == "common-stock-eval-finalize":
        result = finalize_common_stock_eval_job(
            eval_dir=args.eval_dir, semantic_result_path=args.semantic_result,
        )
    elif args.command == "launch-common-stock-eval":
        result, exit_code = launch_common_stock_eval(
            args.repo, eval_dir=args.eval_dir, model=args.model,
            codex_binary=args.codex_binary, timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "collect-live":
        try:
            import os
            from product.mcp.live.collection import collect_live_snapshot
            result = collect_live_snapshot(
                args.portfolio,
                access_path=args.source_access,
                output_dir=args.output_dir,
                cache_root=args.cache_root,
                sec_user_agent=os.environ.get("SEC_USER_AGENT", ""),
            )
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            import re
            token = str(exc).split(":", 1)[0]
            code = token if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", token) else "LIVE_COMMAND_FAILED"
            print(json.dumps({"status": "FAILED", "failure_type": type(exc).__name__, "command": args.command,
                              "failure_code": code}, ensure_ascii=False))
            return 2
    elif args.command == "prepare-live":
        print(json.dumps({
            "status": "FAILED",
            "failure_code": "LIVE_COUNCIL_ENTRY_RETIRED",
            "command": args.command,
            "successor": "common-stock-research",
            "data_reads": 0,
            "network_calls": 0,
            "llm_calls": 0,
        }, ensure_ascii=False))
        return 2
    elif args.command == "prepare-cio":
        result = prepare_cio(args.repo, run_dir=args.run_dir, model=args.model)
    elif args.command == "finalize-cio":
        result = finalize_cio(args.repo, run_dir=args.run_dir, revision=args.revision)
    elif args.command == "smoke-prompt":
        print(build_smoke_prompt(args.run_dir, repository_root=args.repo, sessions_root=args.sessions_root))
        return 0
    elif args.command == "execution-proof":
        try:
            ephemeral_values = (args.codex_events, args.hook_events, args.latency_ms)
            if any(value is not None for value in ephemeral_values):
                if any(value is None for value in ephemeral_values):
                    parser.error(
                        "provide --codex-events, --hook-events and --latency-ms together"
                    )
                if args.sessions_root is not None or any(
                    value is not None
                    for value in (
                        args.parent_rollout,
                        args.company_rollout,
                        args.skeptic_rollout,
                    )
                ):
                    parser.error("ephemeral events cannot be combined with rollouts")
                result = build_ephemeral_run_specialist_execution_proof(
                    args.repo,
                    run_dir=args.run_dir,
                    codex_events_path=args.codex_events,
                    hook_events_path=args.hook_events,
                    latency_ms=args.latency_ms,
                )
            elif args.sessions_root is not None:
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
    elif args.command == "audit-research-consumption":
        try:
            from product.mcp.live.contracts import external_path
            destination = external_path(args.output_dir)
            if destination.exists():
                raise ValueError("RESEARCH_AUDIT_OUTPUT_EXISTS")
            audit = build_research_consumption_audit(
                args.run_dir, company_run=args.company_run, cio_run=args.cio_run,
            )
            destination.mkdir(parents=True, mode=0o700)
            (destination / "consumption.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (destination / "consumption.md").write_text(
                render_audit_summary(audit), encoding="utf-8",
            )
            result = {
                "status": "SAVED", "run_id": audit["run_id"],
                "json": str(destination / "consumption.json"),
                "report": str(destination / "consumption.md"), "llm_calls": 0,
            }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "FAILED", "failure_code": str(exc).split(":", 1)[0], "llm_calls": 0}, ensure_ascii=False))
            return 2
    elif args.command == "check-run":
        result, exit_code = check_run(args.repo, run_dir=args.run_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    elif args.command == "nested-codex-smoke":
        result, exit_code = launch_nested_codex(
            args.repo,
            run_dir=args.run_dir,
            codex_binary=args.codex_binary,
            timeout_seconds=args.timeout_seconds,
            preflight_report=None,
        )
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
                print(build_eval_smoke_prompt(args.repo, eval_dir=args.eval_dir, sessions_root=args.sessions_root))
                return 0
            elif args.command == "eval-execution-proof":
                parent, child = discover_eval_rollouts(
                    args.sessions_root,
                    eval_dir=args.eval_dir.resolve(),
                    eval_id=str(json.loads((args.eval_dir / "input-manifest.json").read_text(encoding="utf-8"))["eval_id"]),
                )
                from .eval_execution_proof import collect_native_eval_output
                proof_builder = collect_native_eval_output if args.collect_native_output else build_eval_execution_proof
                proof = proof_builder(
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
            elif args.command == "calibration-execution-proof":
                from evals.grading.calibration import build_calibration_execution_proof

                result = build_calibration_execution_proof(
                    args.repo,
                    case_id=args.case_id,
                    repeat=args.repeat,
                    grader_output_path=args.grader_output,
                    parent_rollout=args.parent_rollout,
                    child_rollout=args.child_rollout,
                    prompt_path=args.prompt,
                    input_path=args.input,
                )
                if args.output.exists():
                    raise ValueError("CALIBRATION_EXECUTION_PROOF_OUTPUT_EXISTS")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
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
            elif args.command == "promotion":
                from evals.promotion.runtime_gate import run_promotion_gate

                result = run_promotion_gate(
                    args.repo,
                    input_manifest_path=args.input_manifest,
                    output_dir=args.output_dir,
                )
            else:
                from evals.promotion.test_evidence import run_deterministic_test_evidence

                result = run_deterministic_test_evidence(
                    args.repo,
                    output_dir=args.output_dir,
                    tmpdir=args.tmpdir,
                    test_targets=args.test_target,
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
