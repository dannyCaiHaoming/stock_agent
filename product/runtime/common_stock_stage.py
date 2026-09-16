"""普通股持仓研究阶段的运行包、派发消息和执行证明。

Codex 主线程负责派发 LLM Subagent；本模块只冻结输入、验证绑定、
归集事件和产物，不实现 Python LLM 编排。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council import (
    build_common_stock_council_request,
    prepare_common_stock_research_stage,
    validate_council_request,
    validate_equity_research_report,
    validate_holding_research_request,
    validate_research_coverage,
)
from product.intake.v3 import validate_handoff
from product.runtime.hashing import canonical_hash, file_hash
from product.council.research_output import validate_persisted_equity_research_pair


STAGE_VERSION = "common-stock-research-runtime/1.0.0"
DISPATCH_VERSION = "common-stock-research-dispatch/1.0.0"
COMPANY_AGENT_VERSION = "3.0.18"
REQUIRED_SKILLS = (
    "evidence-grounding", "company-research", "valuation", "catalyst-analysis"
)


class CommonStockStageError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommonStockStageError(f"COMMON_STOCK_STAGE_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise CommonStockStageError(f"COMMON_STOCK_STAGE_INPUT_NOT_OBJECT:{path.name}")
    return dict(value)


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise CommonStockStageError(f"COMMON_STOCK_STAGE_OUTPUT_EXISTS:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _claimed_hash(value: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _calculation_ids_for_invocation(run_dir: Path, invocation_id: str) -> list[str]:
    """只信任该 Invocation 实际留下的 MCP 计算事件。"""

    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        return []
    identifiers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CommonStockStageError("COMMON_STOCK_MCP_EVENT_INVALID") from exc
        calculation_id = event.get("calculation_id")
        if (
            event.get("event_type") == "mcp_tool_result"
            and event.get("invocation_id") == invocation_id
            and event.get("tool") == "fixture_math.calculate"
            and isinstance(calculation_id, str)
            and calculation_id
        ):
            identifiers.append(calculation_id)
    return sorted(set(identifiers))


def _skill_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise CommonStockStageError(f"COMMON_STOCK_SKILL_FRONTMATTER_INVALID:{path.parent.name}")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    matched = re.search(r'(?m)^\s{2}version:\s*["\']?([^"\'\n]+)', frontmatter)
    if not matched:
        raise CommonStockStageError(f"COMMON_STOCK_SKILL_VERSION_MISSING:{path.parent.name}")
    return matched.group(1).strip()


def current_research_bindings(repository_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    product_root = Path(repository_root).resolve() / "product"
    agent_path = product_root / ".codex/agents/runtime_company_analyst.toml"
    with agent_path.open("rb") as stream:
        agent_config = tomllib.load(stream)
    configured = tuple(Path(item["path"]).name for item in agent_config["skills"]["config"] if item.get("enabled"))
    # Agent 可为显式新模式加载额外 Skill；旧 COMMON_STOCK_RESEARCH 仅锁定
    # 并记录自己的四项必需 Skill，不能因正交能力增加而失效。
    if not set(REQUIRED_SKILLS) <= set(configured) or len(configured) != len(set(configured)):
        raise CommonStockStageError("COMMON_STOCK_AGENT_SKILL_SET_INVALID")
    agent = {
        "name": "runtime_company_analyst",
        "version": COMPANY_AGENT_VERSION,
        "content_hash": file_hash(agent_path),
    }
    skills = []
    for name in REQUIRED_SKILLS:
        path = product_root / "skills" / name / "SKILL.md"
        skills.append({"name": name, "version": _skill_version(path), "content_hash": file_hash(path)})
    return agent, skills


def _dynamic_draft_schema(
    repository_root: Path, *, run_id: str, invocation_id: str,
    allowed_evidence_ids: Sequence[str], calculation_artifact_ids: Sequence[str] = (),
) -> dict[str, Any]:
    schema = _read_object(
        Path(repository_root).resolve() / "product/schemas/runtime/equity-research-report.schema.json"
    )
    technical = {"schema_version", "report_id", "bindings", "security", "research_scope", "skill_execution"}
    for key in technical:
        schema["properties"].pop(key)
        schema["required"].remove(key)
    schema["title"] = "EquityResearchDraft"
    schema["$id"] = "equity-research-draft/1.0.0"
    schema["properties"]["run_id"] = {"const": run_id}
    schema["properties"]["invocation_id"] = {"const": invocation_id}
    schema["properties"]["agent"] = {"const": "runtime_company_analyst"}
    schema["$defs"].pop("bindings", None)
    schema["$defs"].pop("security", None)
    schema["$defs"].pop("skill", None)
    schema["$defs"]["evidence_id"] = {"type": "string", "enum": list(allowed_evidence_ids)}
    calculation_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if calculation_artifact_ids:
        calculation_schema = {"type": "string", "enum": list(calculation_artifact_ids)}
    schema["$defs"]["claim"]["properties"]["calculation_refs"]["items"] = calculation_schema
    return schema


def invocation_file_name(invocation_id: str) -> str:
    return hashlib.sha256(invocation_id.encode("utf-8")).hexdigest() + ".json"


def _build_evidence_period_index(
    evidence: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Group factual periods without deciding comparability or importance."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        semantic_field = item.get("semantic_field")
        if not isinstance(semantic_field, str) or not semantic_field:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        period_start = metadata.get("period_start")
        period_end = metadata.get("period_end")
        context_type = metadata.get("context_type")
        if context_type == "instant":
            period_kind = "INSTANT"
        elif period_start is not None or context_type == "duration":
            period_kind = "DURATION"
        else:
            period_kind = "UNKNOWN"
        groups.setdefault(semantic_field, []).append({
            "evidence_id": item.get("evidence_id"),
            "source_id": item.get("source_id"),
            "unit": item.get("unit") or metadata.get("unit"),
            "context_type": context_type,
            "period_kind": period_kind,
            "period_start": period_start,
            "period_end": period_end,
            "as_of": item.get("as_of"),
            "published_at": item.get("published_at") or metadata.get("published_at"),
            "retrieved_at": item.get("retrieved_at"),
            "form": metadata.get("form"),
        })
    result = []
    for semantic_field, items in sorted(groups.items()):
        items.sort(key=lambda value: (
            str(value.get("period_end") or ""),
            str(value.get("as_of") or ""),
            str(value.get("published_at") or ""),
            str(value.get("evidence_id") or ""),
        ))
        result.append({
            "semantic_field": semantic_field,
            "selection_rule": (
                "逐项核对指标定义、主体、单位、期间性质与会计基础；"
                "排序不代表自动可比或自动采用最后一项"
            ),
            "items": items,
        })
    return result


def _build_common_stock_dispatch_packet(
    repository_root: Path, run_dir: Path, task: Mapping[str, Any]
) -> dict[str, Any]:
    request = _read_object(run_dir / task["request_path"])
    invocation = _read_object(run_dir / task["invocation_path"])
    gate = _read_object(run_dir / "evidence/gate.json")
    evidence = [
        copy.deepcopy(item) for item in gate["allowed_evidence"]
        if item["evidence_id"] in set(request["allowed_evidence_ids"])
    ]
    evidence_catalog = []
    for item in evidence:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        evidence_catalog.append({
            "evidence_id": item["evidence_id"],
            "semantic_field": item.get("semantic_field"),
            "kind": item.get("kind"),
            "usage": item.get("usage"),
            "source_id": item.get("source_id"),
            "as_of": item.get("as_of"),
            "published_at": item.get("published_at"),
            "retrieved_at": item.get("retrieved_at"),
            "source_locator": item.get("source_locator") or metadata.get("source_locator"),
            "unit": item.get("unit") or metadata.get("unit"),
            "context_type": metadata.get("context_type"),
            "fiscal_period": metadata.get("fiscal_period"),
            "form": metadata.get("form"),
            "section": metadata.get("section"),
            "period_start": metadata.get("period_start"),
            "period_end": metadata.get("period_end"),
            "comparison_policy": metadata.get("comparison_policy"),
            "comparability_scope": metadata.get("comparability_scope"),
            "accounting_basis_status": metadata.get("accounting_basis_status"),
            "share_denominator_status": metadata.get("share_denominator_status"),
            "trend_interpretation_status": metadata.get("trend_interpretation_status"),
            "comparison_periods": metadata.get("periods"),
            "comparison_limitation": metadata.get("comparison_limitation"),
        })
    allowed_ids = set(request["allowed_evidence_ids"])
    evidence_conflicts = [
        {
            "conflict_key": item.get("conflict_key"),
            "reason_code": item.get("reason_code"),
            "evidence_ids": list(item.get("evidence_ids", [])),
        }
        for item in gate.get("conflicts", [])
        if set(item.get("evidence_ids", [])) & allowed_ids
    ]
    schema = _dynamic_draft_schema(
        repository_root, run_id=request["run_id"], invocation_id=request["invocation_id"],
        allowed_evidence_ids=request["allowed_evidence_ids"],
    )
    return {
        "dispatch_contract": DISPATCH_VERSION,
        "identity": {
            "run_id": request["run_id"], "invocation_id": request["invocation_id"],
            "agent": "runtime_company_analyst", "task_name": task["task_name"],
            "security_id": request["security"]["security_id"],
        },
        "instruction": (
            "只研究本包的一只普通股。实际应用已加载的 evidence-grounding、company-research、"
            "valuation、catalyst-analysis；本包即使包含 Yahoo/SEC 事实也已冻结为 run-scoped Gate，"
            "必须使用 fixture_runtime.query 查询 Evidence，需要比较两个数值时使用 "
            "fixture_runtime.calculate。"
            "使用确定性计算工具。evidence_refs 只能原样选择 allowed_evidence_ids，禁止拼接来源、"
            "时间或说明。只返回 output_schema 的一个 JSON，不输出交易动作、仓位或完整组合结论。"
            "提交前逐项把每个 evidence_refs 与 allowed_evidence_ids 做完整字符串核对；任何字符增删、"
            "替换或手工重写都属于非法引用，必须改为直接复制允许列表中的原值。"
            "每条 Claim 至少有一个 evidence_ref、assumption_id 或 calculation_ref；"
            "calculation_ref 只能填写本次 calculate 实际返回的 calculation_id，且同一个 ID 必须"
            "同时列入顶层 artifact_refs，未调用成功的计算不得引用。"
            "核心假设关联具体主张；counter_claim_refs 只可填写本报告已有的 claim_id；反证若挑战"
            "假设，须在文字中说明并关联承载该假设的 Claim，不得把 assumption_id 填入该字段。观察指标填写已有"
            "基线、单位、比较期间和重评方式，未知时使用 null 或明确写未知，不编造阈值。"
            "财务期间按 period_start/period_end 核对，FY/10-K 不代表全年；重组后部分期间"
            "不得写成完整年度或直接比较，来源发布时间不等于报告期末。按 company-research 的"
            "首版研究深度解释关键矛盾与缺口影响，不只摘录数字。同一 FACT Claim 引用多个 duration "
            "Evidence 且任一起止日不同时，Claim 文字必须逐项写出每个 Evidence 的真实起止日；"
            "即使只差一天也不得归并为一个统一期间。10-K/FY 标签不能证明完整财年；不足一年或"
            "重组后部分期间的 EPS 只能按真实起止日描述为非年化实际期间分母，不得称为年度、"
            "财年、全年或 TTM P/E，分母为负时说明 P/E 不适用，不强行计算。"
            "先查看 evidence_period_index 中同指标全部可用期间，再核对指标定义、主体、单位、"
            "季度/累计/时点性质和会计基础；该索引排序不代表自动可比或自动采用最后一项，"
            "不得按 retrieved_at 或单一最大日期覆盖。引用旧基线时说明用途，并呈现包内较新且"
            "适用的重要事实。输出前按每个实际采用的指标逐项自检 evidence_period_index：若存在"
            "报告期更近且定义、主体、单位、期间性质和会计基础适用的事实，必须纳入主张；若不纳入，"
            "必须明确说明不可比或不适用的具体原因，不能只写旧年度基线。检查 evidence_conflicts，"
            "无法消解的冲突必须保留，禁止静默选择 winner。"
            "任何 derived comparison 的同指标、同单位、同一披露、相同天数或算术差额都不自动"
            "证明会计基础、报告主体、每股分母或经济含义可比；先读取 comparison_limitation、"
            "accounting_basis_status 和原始父 Evidence。若冻结资料显示 fresh-start accounting、"
            "重组、前后继主体、重述或重大业务处置跨越两个期间，且没有额外 Evidence 明确确认"
            "可比基础，只能分别呈现两期原值和限制，不得称为可比趋势、改善/恶化或现实反证。"
            "大幅百分比变化必须同时写出两期原始值和绝对变化，并说明低基数、负基数或一次性因素"
            "是否影响解释；百分比不能单独承担核心判断。观察指标引用数值 Evidence 时，baseline "
            "必须保留实际数值、单位和期间，不得仅写‘流入’、‘流出’、‘上升’或‘下降’；只有数值"
            "不适用或不能可靠展示时才使用定性状态并说明原因。"
            "金额必须保留来源币种、数量级和税前/税后语义。中文主张实际呈现 Evidence 中以 "
            "billion 或 million 表示的金额时，必须先对该 Evidence 调用 fixture_runtime.calculate 的"
            "monetary_scale 操作，改写为等值的亿或万，并引用其 calculation_id；例如 $1.8 billion "
            "转为 18 亿美元。影响盈利质量的重大交易或一次性项目若在 Evidence 中有该类金额，"
            "必须在相关主张中呈现并完成换算；其他未纳入正文的金额无需调用。未成功调用时不得"
            "自行换算或复述该金额。"
            "反证必须是挑战具体主张的可观察事实并解释机制与可比性；风险清单和不可比期间金额"
            "变化不冒充现实反证。反证只能挑战本报告实际提出的 Claim 或显式假设，不得虚构需求归零、"
            "商业活动完全消失等报告未提出的极端判断后再反驳。没有可靠现实反证时说明检视范围、"
            "缺口及验证条件。对最重要的"
            "未决问题说明基准判断、向好/向坏条件、受影响主张与观察信号；无依据时不强凑情景。"
            "JSON 的 summary、narrative、statement 不重复粘贴 evidence_id、source_id、as_of 或"
            "retrieved_at；只在结构化 evidence_refs 中使用原始 ID，中文报告会生成简短引用与完整附录。"
            "data_gaps.reason_code 只可为 NOT_FETCHED、NOT_YET_DISCLOSED、SOURCE_UNSUPPORTED、UNKNOWN，"
            "无法证明原因时使用 UNKNOWN。区分公司研究资料缺口与本阶段未研究的技术图形、市场/宏观、"
            "板块、期权、资金结构、新闻情绪和 ETF 方向；不得把未研究解释为无风险。"
        ),
        "tool_context": {
            "source_mode": "frozen-gate",
            "mcp_server": "fixture_runtime",
            "query_tool": "fixture_runtime.query",
            "calculation_tool": "fixture_runtime.calculate",
            "logical_permissions": invocation["tool_permissions"],
            "required_identity_arguments": {
                "run_id": request["run_id"],
                "agent": "runtime_company_analyst",
                "invocation_id": request["invocation_id"],
            },
            "run_directory_binding": "LAUNCHER_ENVIRONMENT",
        },
        "holding_research_request": request,
        "allowed_evidence_ids": request["allowed_evidence_ids"],
        "evidence_catalog": evidence_catalog,
        "evidence_period_index": _build_evidence_period_index(evidence),
        "evidence_conflicts": evidence_conflicts,
        "output_schema": schema,
    }


def build_common_stock_dispatch_packet(repository_root: Path, run_dir: Path, task_name: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    index = _read_object(run_dir / "research/dispatch-index.json")
    tasks = {item["task_name"]: item for item in index.get("tasks", [])}
    if task_name not in tasks:
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_TASK_UNKNOWN")
    task = tasks[task_name]
    packet = _read_object(run_dir / task["packet_path"])
    if canonical_hash(packet) != task["packet_hash"]:
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_PACKET_HASH_MISMATCH")
    return packet


def build_common_stock_dispatch_message(repository_root: Path, run_dir: Path, task_name: str) -> str:
    run_dir = Path(run_dir).resolve()
    index = _read_object(run_dir / "research/dispatch-index.json")
    tasks = {item["task_name"]: item for item in index.get("tasks", [])}
    if task_name not in tasks:
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_TASK_UNKNOWN")
    task = tasks[task_name]
    return (
        f"普通股研究任务 {task_name}。等待 SubagentStart Hook 注入冻结研究包；"
        "以 Hook 上下文为唯一研究输入，忽略本消息中的其他研究内容。"
    )


def _apply_focus_to_stage(
    stage: dict[str, Any], *, handoff: Mapping[str, Any],
    council_request: Mapping[str, Any], focus_security_id: str | None,
) -> None:
    if focus_security_id is None:
        return
    selected = [
        item for item in stage["holding_requests"]
        if item["security"]["security_id"] == focus_security_id
    ]
    if len(selected) != 1:
        raise CommonStockStageError("COMMON_STOCK_FOCUS_SECURITY_NOT_READY")
    stage["holding_requests"] = selected
    coverage = stage["coverage"]
    coverage["execution_mode"] = "SERIAL"
    coverage["effective_concurrency"] = 1
    coverage["execution_mode_reason"] = "显式限定为单只普通股重跑。"
    for item in coverage["items"]:
        if (
            item["asset_type"] == "COMMON_STOCK"
            and item["security_id"] != focus_security_id
            and item["execution_status"] == "QUEUED"
        ):
            item.update({
                "execution_status": "NOT_STARTED",
                "research_status": "NOT_RESEARCHED",
                "coverage_status": "NOT_RESEARCHED",
                "failure_code": None,
            })
    coverage["coverage_hash"] = _claimed_hash(coverage, "coverage_hash")
    validate_research_coverage(
        coverage, handoff=handoff, council_request=council_request
    )
    stage.pop("stage_hash", None)
    stage["stage_hash"] = canonical_hash(stage)


def prepare_common_stock_stage_run(
    repository_root: Path, *, handoff_path: Path, gate_path: Path, run_dir: Path,
    run_id: str, model: str, research_question: str = "分析已确认的普通股持仓。",
    source_fixture: Path | None = None, target_concurrency: int = 3,
    data_preparation_path: Path | None = None,
    source_bundle_path: Path | None = None,
    focus_security_id: str | None = None,
) -> dict[str, Any]:
    """冻结已确认持仓和 Gate，生成一个可由现有宿主 launcher 执行的阶段包。"""

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    from product.runtime.model_routing import select_product_runtime_model
    analyst_model = select_product_runtime_model(
        repository_root / "product", requested_model=model
    )
    parent_model = analyst_model
    if run_dir.exists():
        raise CommonStockStageError("COMMON_STOCK_STAGE_RUN_EXISTS")
    handoff = _read_object(Path(handoff_path).resolve())
    validate_handoff(handoff)
    gate = _read_object(Path(gate_path).resolve())
    if gate.get("run_id") != run_id:
        raise CommonStockStageError("COMMON_STOCK_STAGE_GATE_RUN_MISMATCH")
    request = build_common_stock_council_request(
        handoff, request_id=f"common-stock-research:{run_id}", research_question=research_question,
    )
    agent, skills = current_research_bindings(repository_root)
    data_preparation = (
        _read_object(Path(data_preparation_path).resolve())
        if data_preparation_path is not None else None
    )
    if gate.get("source_mode") == "live-read-only":
        if data_preparation is None or source_bundle_path is None:
            raise CommonStockStageError("COMMON_STOCK_LIVE_DATA_PACKAGE_INCOMPLETE")
        from product.runtime.common_stock_data import validate_common_stock_source_bundle
        validate_common_stock_source_bundle(
            handoff, gate=gate, preparation=data_preparation,
            source_bundle_path=Path(source_bundle_path).resolve(),
        )
    stage = prepare_common_stock_research_stage(
        handoff, request, gate, run_id=run_id, batch_id=f"batch:{run_id}",
        agent_binding=agent, skill_bindings=skills, target_concurrency=target_concurrency,
        effective_concurrency=min(target_concurrency, sum(
            item["asset_type"] == "COMMON_STOCK" for item in handoff["portfolio"]["positions"]
        )), data_preparation=data_preparation,
    )
    _apply_focus_to_stage(
        stage, handoff=handoff, council_request=request,
        focus_security_id=focus_security_id,
    )
    run_dir.mkdir(parents=True)
    _write_object(run_dir / "audit/portfolio-handoff.json", handoff)
    _write_object(run_dir / "council-request.json", request)
    _write_object(run_dir / "evidence/gate.json", gate)
    if data_preparation is not None:
        _write_object(run_dir / "evidence/data-preparation.json", data_preparation)
    source_bundle_ref = None
    if source_bundle_path is not None:
        source_bundle_file = Path(source_bundle_path).resolve()
        source_bundle = _read_object(source_bundle_file)
        source_package = run_dir / "evidence/source-package"
        shutil.copytree(source_bundle_file.parent, source_package)
        source_bundle_ref = "evidence/source-package/source-bundle.json"
        _write_object(run_dir / "evidence/source-bundle.json", source_bundle)
    _write_object(run_dir / "research/stage.json", stage)
    _write_object(run_dir / "research/coverage.json", stage["coverage"])
    tasks = []
    for position, holding_request in enumerate(stage["holding_requests"]):
        task_name = f"company_research_{position + 1}"
        request_path = f"research/requests/{invocation_file_name(holding_request['invocation_id'])}"
        _write_object(run_dir / request_path, holding_request)
        invocation = {
            "schema_version": "common-stock-research-invocation/1.0.0",
            "run_id": run_id, "invocation_id": holding_request["invocation_id"],
            "agent": agent, "skill_execution": [
                {
                    "skill_name": item["name"], "version": item["version"],
                    "invocation_hash": canonical_hash({
                        "invocation_id": holding_request["invocation_id"],
                        "skill_name": item["name"], "skill_hash": item["content_hash"],
                    }),
                }
                for item in skills
            ],
            "model": analyst_model,
            "analyst_model": analyst_model,
            "tool_permissions": ["fixture_evidence.query", "fixture_math.calculate"],
            "request_path": request_path,
        }
        invocation["manifest_hash"] = canonical_hash(invocation)
        invocation_path = f"invocations/by-id/{invocation_file_name(holding_request['invocation_id'])}"
        _write_object(run_dir / invocation_path, invocation)
        task = {
            "task_name": task_name,
            "security_id": holding_request["security"]["security_id"],
            "invocation_id": holding_request["invocation_id"],
            "request_path": request_path,
            "invocation_path": invocation_path,
        }
        packet = _build_common_stock_dispatch_packet(repository_root, run_dir, task)
        packet_path = f"research/dispatch-packets/{invocation_file_name(holding_request['invocation_id'])}"
        _write_object(run_dir / packet_path, packet)
        task.update(packet_path=packet_path, packet_hash=canonical_hash(packet))
        tasks.append(task)
    index = {
        "schema_version": DISPATCH_VERSION,
        "run_id": run_id,
        "target_concurrency": target_concurrency,
        "tasks": tasks,
    }
    index["index_hash"] = canonical_hash(index)
    _write_object(run_dir / "research/dispatch-index.json", index)
    fixture = Path(source_fixture).resolve() if source_fixture else (
        repository_root / "evals/fixtures/codex-native/common-stock-two-company-v1.json"
    ).resolve()
    manifest = {
        "schema_version": STAGE_VERSION, "run_id": run_id, "stage": "COMMON_STOCK_RESEARCH",
        "source_mode": gate.get("source_mode", "fixture-research"), "model": parent_model,
        "parent_model": parent_model, "analyst_model": analyst_model,
        "output_dir": str(run_dir),
        "fixture": str(fixture),
        "discovery": {"product_root": str(repository_root / "product")},
        "agent_binding": agent, "skill_bindings": skills,
        "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
        "council_request_hash": request["request_hash"], "gate_hash": gate["bundle_hash"],
        "data_preparation_hash": (
            data_preparation.get("preparation_hash") if data_preparation is not None else None
        ),
        "source_bundle_hash": gate.get("source_bundle_hash"),
        "source_bundle_ref": source_bundle_ref,
        "stage_hash": stage["stage_hash"],
        "dispatch_index_hash": index["index_hash"], "target_concurrency": target_concurrency,
        "focus_security_id": focus_security_id,
        "prepared_at": _utc_now(), "complete_portfolio_decision": False,
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    _write_object(run_dir / "run_manifest.json", manifest)
    return {"status": "PREPARED", "run_id": run_id, "run_dir": str(run_dir), "task_count": len(tasks)}


def build_common_stock_stage_prompt(repository_root: Path, run_dir: Path) -> str:
    run_dir = Path(run_dir).resolve()
    index = _read_object(run_dir / "research/dispatch-index.json")
    messages = {
        item["task_name"]: build_common_stock_dispatch_message(repository_root, run_dir, item["task_name"])
        for item in index["tasks"]
    }
    concurrency = min(index["target_concurrency"], len(messages))
    return f"""你是普通股持仓研究阶段的 Codex 主线程，只负责有界派发和归集，不担任 CIO。
读取产品 AGENTS.md 与 portfolio-council Skill 中的普通股研究阶段说明。使用 Agent 工具，agent_type 必须为 runtime_company_analyst，fork_turns=none。
最多同时保持 {concurrency} 个活跃 Subagent。在等待任何一个结果前，先按映射顺序发起最初 {concurrency} 个独立任务；任一任务结束后立即用下一个未派发任务补位，直到全部任务结束。不得一次派发超过并发上限：
{json.dumps(messages, ensure_ascii=False, sort_keys=True)}
每个 task_name 必须使用映射中的键；message 仅为非权威启动提示，完整冻结输入由 SubagentStart Hook 按已校验 task_name 注入。不得把研究数据复制进 message。不得启动 runtime_skeptic、runtime_cio、Risk 或完整 Council；不得自行改写 Specialist 输出。
等待全部任务结束后，只返回：{{"stage":"COMMON_STOCK_RESEARCH","run_id":"{index['run_id']}","dispatched":{len(messages)}}}。
"""


def finalize_common_stock_stage_run(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """从底层 Hook 和报告重算覆盖状态及并行证明。"""

    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    handoff = _read_object(run_dir / "audit/portfolio-handoff.json")
    council_request = _read_object(run_dir / "council-request.json")
    gate = _read_object(run_dir / "evidence/gate.json")
    coverage = _read_object(run_dir / "research/coverage.json")
    index = _read_object(run_dir / "research/dispatch-index.json")
    events_path = run_dir / "invocation/subagent-events.jsonl"
    dispatch_path = run_dir / "invocation/subagent-dispatches.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dispatches = [json.loads(line) for line in dispatch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    allowed = {item.get("task_name") for item in dispatches if item.get("decision") == "ALLOW"}
    expected = {item["task_name"] for item in index["tasks"]}
    if allowed != expected:
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_PROOF_INCOMPLETE")
    starts = {item["child_session_id"]: item for item in events if item.get("hook_event_name") == "SubagentStart"}
    stops = [item for item in events if item.get("hook_event_name") == "SubagentStop"]
    by_invocation = {item["invocation_id"]: item for item in index["tasks"]}
    targeted_security_ids = {item["security_id"] for item in index["tasks"]}
    intervals = []
    completed = set()
    for stop in stops:
        binding = stop.get("output_binding") or {}
        invocation_id = binding.get("invocation_id")
        if invocation_id not in by_invocation or stop.get("child_session_id") not in starts:
            continue
        task = by_invocation[invocation_id]
        request = _read_object(run_dir / task["request_path"])
        report_path = run_dir / "research/reports" / task["security_id"].replace(":", "_") / "equity-research.json"
        markdown_path = report_path.with_suffix(".md")
        report = _read_object(report_path)
        calculation_ids = _calculation_ids_for_invocation(run_dir, invocation_id)
        validate_equity_research_report(
            report,
            request=request,
            calculation_artifact_ids=calculation_ids,
        )
        validate_persisted_equity_research_pair(
            json_path=report_path, markdown_path=markdown_path, request=request,
            evidence=[
                fact for fact in gate["allowed_evidence"]
                if fact["evidence_id"] in set(request["allowed_evidence_ids"])
            ],
            calculation_artifact_ids=calculation_ids,
        )
        completed.add(task["security_id"])
        intervals.append({
            "security_id": task["security_id"], "invocation_id": invocation_id,
            "child_session_id": stop["child_session_id"],
            "started_at": starts[stop["child_session_id"]]["observed_at"],
            "completed_at": stop["observed_at"],
        })
    for item in coverage["items"]:
        if item["security_id"] in completed:
            task = next(row for row in index["tasks"] if row["security_id"] == item["security_id"])
            report_path = run_dir / "research/reports" / task["security_id"].replace(":", "_") / "equity-research.json"
            report = _read_object(report_path)
            report_status = report["status"]
            research_status = {
                "COMPLETE": "VALID_RESEARCH",
                "LOW_CONFIDENCE": "LOW_CONFIDENCE",
                "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
                "TIMEOUT": "FAILED",
            }[report_status]
            item.update({
                "execution_status": "TIMEOUT" if report_status == "TIMEOUT" else "COMPLETED",
                "research_status": research_status,
                "coverage_status": "FAILED" if report_status == "TIMEOUT" else "RESEARCHED",
                "invocation_id": task["invocation_id"],
                "report_ref": f"research/reports/{task['security_id'].replace(':', '_')}/equity-research.json",
                "report_hash": canonical_hash(report),
                "failure_code": "RESEARCH_TIMEOUT" if report_status == "TIMEOUT" else None,
            })
        elif (
            item["asset_type"] == "COMMON_STOCK"
            and item["security_id"] in targeted_security_ids
        ):
            item.update({"execution_status": "FAILED", "research_status": "FAILED", "coverage_status": "FAILED", "failure_code": "REPORT_MISSING"})
    has_gaps = any(item["coverage_status"] != "RESEARCHED" for item in coverage["items"])
    coverage["stage_status"] = "PARTIAL_RESEARCH" if has_gaps else "RESEARCH_COMPLETE"
    coverage["coverage_hash"] = canonical_hash({key: value for key, value in coverage.items() if key != "coverage_hash"})
    validate_research_coverage(coverage, handoff=handoff, council_request=council_request)
    (run_dir / "research/coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    overlap = False
    if len(intervals) >= 2:
        ordered = sorted(intervals, key=lambda item: item["started_at"])
        overlap = any(left["completed_at"] > right["started_at"] for left, right in zip(ordered, ordered[1:]))
    proof = {
        "schema_version": "common-stock-research-execution-proof/1.0.0",
        "run_id": manifest["run_id"], "expected_tasks": sorted(expected),
        "completed_security_ids": sorted(completed), "intervals": intervals,
        "parallel_overlap": overlap, "all_reports_valid": len(completed) == len(expected),
        "agent": manifest["agent_binding"], "skills": manifest["skill_bindings"],
        "gate_hash": gate["bundle_hash"], "complete_portfolio_decision": False,
    }
    proof["proof_hash"] = canonical_hash(proof)
    _write_object(run_dir / "research/execution-proof.json", proof)
    return {
        "status": "PASSED" if proof["all_reports_valid"] else "FAILED",
        "run_id": manifest["run_id"], "stage_status": coverage["stage_status"],
        "parallel_overlap": overlap, "completed": len(completed), "expected": len(expected),
    }


def _validate_common_stock_stage_run_package(
    repository_root: Path, run_dir: Path,
) -> dict[str, Any]:
    """在创建 Codex 进程前，从运行目录底层产物重算启动绑定。"""

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    if manifest.get("manifest_hash") != _claimed_hash(manifest, "manifest_hash"):
        raise CommonStockStageError("COMMON_STOCK_STAGE_MANIFEST_HASH_MISMATCH")
    if (
        manifest.get("schema_version") != STAGE_VERSION
        or manifest.get("stage") != "COMMON_STOCK_RESEARCH"
        or Path(manifest.get("output_dir", "")).resolve() != run_dir
    ):
        raise CommonStockStageError("COMMON_STOCK_STAGE_MANIFEST_INVALID")

    handoff = _read_object(run_dir / "audit/portfolio-handoff.json")
    request = _read_object(run_dir / "council-request.json")
    gate = _read_object(run_dir / "evidence/gate.json")
    stage = _read_object(run_dir / "research/stage.json")
    coverage = _read_object(run_dir / "research/coverage.json")
    index = _read_object(run_dir / "research/dispatch-index.json")
    validate_handoff(handoff)
    validate_council_request(request, handoff=handoff)
    if gate.get("bundle_hash") != _claimed_hash(gate, "bundle_hash"):
        raise CommonStockStageError("COMMON_STOCK_GATE_HASH_MISMATCH")
    if stage.get("stage_hash") != _claimed_hash(stage, "stage_hash"):
        raise CommonStockStageError("COMMON_STOCK_RESEARCH_STAGE_HASH_MISMATCH")
    if coverage.get("coverage_hash") != _claimed_hash(coverage, "coverage_hash"):
        raise CommonStockStageError("COMMON_STOCK_RESEARCH_COVERAGE_HASH_MISMATCH")
    if index.get("index_hash") != _claimed_hash(index, "index_hash"):
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_INDEX_HASH_MISMATCH")
    if stage.get("coverage") != coverage:
        raise CommonStockStageError("COMMON_STOCK_STAGE_COVERAGE_BINDING_INVALID")

    expected = {
        "run_id": manifest["run_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_request_hash": request["request_hash"],
        "gate_hash": gate["bundle_hash"],
        "stage_hash": stage["stage_hash"],
        "dispatch_index_hash": index["index_hash"],
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise CommonStockStageError("COMMON_STOCK_STAGE_MANIFEST_BINDING_INVALID")
    if (
        gate.get("run_id") != manifest["run_id"]
        or stage.get("run_id") != manifest["run_id"]
        or index.get("run_id") != manifest["run_id"]
        or index.get("target_concurrency") != manifest.get("target_concurrency")
    ):
        raise CommonStockStageError("COMMON_STOCK_STAGE_RUN_BINDING_INVALID")

    agent, skills = current_research_bindings(repository_root)
    if manifest.get("agent_binding") != agent or manifest.get("skill_bindings") != skills:
        raise CommonStockStageError("COMMON_STOCK_STAGE_RUNTIME_BINDING_DRIFT")

    from product.runtime.model_routing import select_product_runtime_model
    expected_model = select_product_runtime_model(
        repository_root / "product", requested_model=manifest.get("analyst_model")
    )
    if any(manifest.get(key) != expected_model for key in (
        "model", "parent_model", "analyst_model"
    )):
        raise CommonStockStageError("COMMON_STOCK_STAGE_MODEL_BINDING_INVALID")

    preparation = None
    preparation_path = run_dir / "evidence/data-preparation.json"
    if preparation_path.is_file():
        preparation = _read_object(preparation_path)
        if preparation.get("preparation_hash") != _claimed_hash(preparation, "preparation_hash"):
            raise CommonStockStageError("COMMON_STOCK_PREPARATION_HASH_MISMATCH")
    if manifest.get("data_preparation_hash") != (
        preparation.get("preparation_hash") if preparation is not None else None
    ):
        raise CommonStockStageError("COMMON_STOCK_STAGE_PREPARATION_BINDING_INVALID")

    expected_stage = prepare_common_stock_research_stage(
        handoff, request, gate, run_id=manifest["run_id"],
        batch_id=f"batch:{manifest['run_id']}", agent_binding=agent,
        skill_bindings=skills, target_concurrency=manifest["target_concurrency"],
        effective_concurrency=min(
            manifest["target_concurrency"],
            sum(item["asset_type"] == "COMMON_STOCK" for item in handoff["portfolio"]["positions"]),
        ),
        data_preparation=preparation,
    )
    _apply_focus_to_stage(
        expected_stage, handoff=handoff, council_request=request,
        focus_security_id=manifest.get("focus_security_id"),
    )
    if stage != expected_stage:
        raise CommonStockStageError("COMMON_STOCK_RESEARCH_STAGE_RECONSTRUCTION_MISMATCH")
    validate_research_coverage(coverage, handoff=handoff, council_request=request)
    for holding_request in stage["holding_requests"]:
        validate_holding_research_request(
            holding_request, handoff=handoff, council_request=request, gate=gate
        )

    tasks = index.get("tasks")
    holding_requests = stage.get("holding_requests")
    if not isinstance(tasks, list) or not isinstance(holding_requests, list):
        raise CommonStockStageError("COMMON_STOCK_STAGE_TASK_SET_INVALID")
    requests_by_invocation = {
        item.get("invocation_id"): item for item in holding_requests if isinstance(item, Mapping)
    }
    if len(requests_by_invocation) != len(tasks):
        raise CommonStockStageError("COMMON_STOCK_STAGE_TASK_SET_INVALID")

    def package_path(reference: Any) -> Path:
        if not isinstance(reference, str):
            raise CommonStockStageError("COMMON_STOCK_STAGE_REFERENCE_INVALID")
        path = (run_dir / reference).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise CommonStockStageError("COMMON_STOCK_STAGE_REFERENCE_INVALID")
        return path

    expected_tasks = []
    for position, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            raise CommonStockStageError("COMMON_STOCK_STAGE_TASK_INVALID")
        holding_request = _read_object(package_path(task.get("request_path")))
        invocation = _read_object(package_path(task.get("invocation_path")))
        packet = _read_object(package_path(task.get("packet_path")))
        expected_request = requests_by_invocation.get(task.get("invocation_id"))
        if holding_request != expected_request:
            raise CommonStockStageError("COMMON_STOCK_STAGE_REQUEST_BINDING_INVALID")
        if (
            task.get("security_id") != holding_request.get("security", {}).get("security_id")
            or invocation.get("run_id") != manifest["run_id"]
            or invocation.get("invocation_id") != task.get("invocation_id")
            or invocation.get("request_path") != task.get("request_path")
            or invocation.get("manifest_hash") != _claimed_hash(invocation, "manifest_hash")
            or task.get("packet_hash") != canonical_hash(packet)
        ):
            raise CommonStockStageError("COMMON_STOCK_STAGE_TASK_BINDING_INVALID")
        rebuilt_packet = _build_common_stock_dispatch_packet(repository_root, run_dir, task)
        if packet != rebuilt_packet:
            raise CommonStockStageError("COMMON_STOCK_DISPATCH_PACKET_BINDING_INVALID")
        expected_task = {
            "task_name": f"company_research_{position + 1}",
            "security_id": holding_request["security"]["security_id"],
            "invocation_id": holding_request["invocation_id"],
            "request_path": (
                f"research/requests/{invocation_file_name(holding_request['invocation_id'])}"
            ),
            "invocation_path": (
                f"invocations/by-id/{invocation_file_name(holding_request['invocation_id'])}"
            ),
            "packet_path": (
                f"research/dispatch-packets/{invocation_file_name(holding_request['invocation_id'])}"
            ),
            "packet_hash": canonical_hash(rebuilt_packet),
        }
        expected_invocation = {
            "schema_version": "common-stock-research-invocation/1.0.0",
            "run_id": manifest["run_id"],
            "invocation_id": holding_request["invocation_id"],
            "agent": agent,
            "skill_execution": [
                {
                    "skill_name": item["name"], "version": item["version"],
                    "invocation_hash": canonical_hash({
                        "invocation_id": holding_request["invocation_id"],
                        "skill_name": item["name"], "skill_hash": item["content_hash"],
                    }),
                }
                for item in skills
            ],
            "model": expected_model, "analyst_model": expected_model,
            "tool_permissions": ["fixture_evidence.query", "fixture_math.calculate"],
            "request_path": expected_task["request_path"],
        }
        expected_invocation["manifest_hash"] = canonical_hash(expected_invocation)
        if task != expected_task or invocation != expected_invocation:
            raise CommonStockStageError("COMMON_STOCK_DISPATCH_RECONSTRUCTION_MISMATCH")
        expected_tasks.append(expected_task)
    expected_index = {
        "schema_version": DISPATCH_VERSION,
        "run_id": manifest["run_id"],
        "target_concurrency": manifest["target_concurrency"],
        "tasks": expected_tasks,
    }
    expected_index["index_hash"] = canonical_hash(expected_index)
    if index != expected_index:
        raise CommonStockStageError("COMMON_STOCK_DISPATCH_INDEX_RECONSTRUCTION_MISMATCH")

    if manifest.get("source_mode") == "live-read-only":
        source_bundle_path = package_path(manifest.get("source_bundle_ref"))
        source_bundle = _read_object(source_bundle_path)
        compatibility_bundle = _read_object(run_dir / "evidence/source-bundle.json")
        if compatibility_bundle != source_bundle:
            raise CommonStockStageError("COMMON_STOCK_STAGE_SOURCE_BUNDLE_COPY_MISMATCH")
        if manifest.get("source_bundle_hash") != source_bundle.get("bundle_hash"):
            raise CommonStockStageError("COMMON_STOCK_STAGE_SOURCE_BUNDLE_BINDING_INVALID")
        if preparation is None:
            raise CommonStockStageError("COMMON_STOCK_LIVE_DATA_PACKAGE_INCOMPLETE")
        from product.runtime.common_stock_data import validate_common_stock_source_bundle
        validate_common_stock_source_bundle(
            handoff, gate=gate, preparation=preparation,
            source_bundle_path=source_bundle_path,
        )
    elif manifest.get("source_bundle_ref") is not None:
        raise CommonStockStageError("COMMON_STOCK_STAGE_SOURCE_BUNDLE_UNEXPECTED")
    return manifest


def launch_common_stock_stage(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 1800,
) -> tuple[dict[str, Any], int]:
    """通过现有 nested Codex 命令构造器运行显式普通股研究阶段。"""

    from product.runtime.nested_codex import (
        build_nested_codex_command,
        fixture_mcp_runtime_environment,
        integrity_snapshot,
    )

    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    run_dir = Path(run_dir).resolve()
    manifest = _validate_common_stock_stage_run_package(repository_root, run_dir)
    invocation_dir = run_dir / "invocation"
    if invocation_dir.exists():
        raise CommonStockStageError("COMMON_STOCK_STAGE_ALREADY_LAUNCHED")
    invocation_dir.mkdir()
    runtime_root = run_dir / ".codex-runtime"
    sqlite_home, log_dir, tmp_dir = (
        runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    )
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    prompt = build_common_stock_stage_prompt(repository_root, run_dir)
    prompt_path = invocation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    parent_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": ["stage", "run_id", "dispatched"],
        "properties": {
            "stage": {"type": "string", "const": "COMMON_STOCK_RESEARCH"},
            "run_id": {"type": "string", "const": manifest["run_id"]},
            "dispatched": {
                "type": "integer",
                "const": len(_read_object(run_dir / "research/dispatch-index.json")["tasks"]),
            },
        },
    }
    schema_path = invocation_dir / "parent-output.schema.json"
    _write_object(schema_path, parent_schema)
    events_path = invocation_dir / "codex-events.jsonl"
    hook_events_path = invocation_dir / "subagent-events.jsonl"
    dispatch_events_path = invocation_dir / "subagent-dispatches.jsonl"
    stderr_path = invocation_dir / "codex-stderr.log"
    raw_final_path = tmp_dir / "final-message.json"
    command = build_nested_codex_command(
        codex_binary=codex_binary, product_root=product_root, run_dir=run_dir,
        model=manifest["parent_model"], sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=raw_final_path,
        hook_recorder_path=product_root / "runtime/codex_hook_recorder.py",
        output_schema_path=schema_path,
        fixture_mcp_run_dir=run_dir,
    )
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(run_dir),
        "STOCK_AGENT_FIXTURE_MCP_RUN_DIR": str(run_dir),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(hook_events_path),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_events_path),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst",
        "STOCK_AGENT_COMMON_STOCK_STAGE": STAGE_VERSION,
        **fixture_mcp_runtime_environment(),
    })
    environment.pop("STOCK_AGENT_START_CONTEXT", None)
    environment.pop("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT", None)
    before = integrity_snapshot(repository_root)
    environment_manifest = {
        "schema_version": "common-stock-stage-environment/1.0.0",
        "run_id": manifest["run_id"], "cwd": str(product_root),
        "repo_root": str(repository_root), "product_root": str(product_root),
        "run_dir": str(run_dir), "command": command,
        "model": manifest["parent_model"],
        "parent_model": manifest["parent_model"],
        "analyst_model": manifest["analyst_model"],
        "sandbox": "workspace-write", "approval_policy": "never", "ephemeral": True,
        "sqlite_home": str(sqlite_home), "log_dir": str(log_dir), "tmpdir": str(tmp_dir),
        "prompt_hash": file_hash(prompt_path), "source_integrity_before": before,
    }
    _write_object(invocation_dir / "environment-manifest.json", environment_manifest)
    started = _utc_now()
    try:
        process = subprocess.run(
            command, input=prompt, text=True, cwd=product_root, env=environment,
            capture_output=True, timeout=timeout_seconds, check=False,
        )
        timed_out = False
        stdout, stderr, process_code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        process_code = 124
    events_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    result: dict[str, Any]
    failure_code = None
    try:
        if timed_out:
            raise CommonStockStageError("COMMON_STOCK_STAGE_TIMEOUT")
        if process_code != 0:
            raise CommonStockStageError("COMMON_STOCK_CODEX_PROCESS_FAILED")
        if not raw_final_path.is_file():
            raise CommonStockStageError("COMMON_STOCK_FINAL_MESSAGE_MISSING")
        final_message = _read_object(raw_final_path)
        _write_object(invocation_dir / "final-message.json", final_message)
        if (
            final_message.get("stage") != "COMMON_STOCK_RESEARCH"
            or final_message.get("run_id") != manifest["run_id"]
        ):
            raise CommonStockStageError("COMMON_STOCK_FINAL_MESSAGE_INVALID")
        result = finalize_common_stock_stage_run(repository_root, run_dir)
        if result["status"] != "PASSED":
            raise CommonStockStageError("COMMON_STOCK_REPORT_SET_INCOMPLETE")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, CommonStockStageError) as exc:
        failure_code = str(exc).split(":", 1)[0]
        result = {
            "status": "FAILED", "run_id": manifest["run_id"],
            "failure_code": failure_code,
        }
    after = integrity_snapshot(repository_root)
    process_result = {
        "schema_version": "common-stock-stage-process/1.0.0",
        "run_id": manifest["run_id"], "started_at": started, "completed_at": _utc_now(),
        "process_exit_code": process_code, "timed_out": timed_out,
        "stage_status": result["status"], "failure_code": failure_code,
        "source_integrity_unchanged": before == after,
    }
    _write_object(invocation_dir / "process-result.json", process_result)
    return result, 0 if result["status"] == "PASSED" and before == after else 7
