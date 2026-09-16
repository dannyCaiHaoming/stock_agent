"""固定的零 LLM Agent Package Demo 数据流与产物生成。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from product.runtime.decision_contract import validate_no_investment_policy_keys
from product.runtime.evidence_gate import run_evidence_gate
from product.runtime.fixture_mcp import GateScopedFixtureTools
from product.runtime.hashing import canonical_hash
from product.runtime.risk_runtime import check_cio_draft

from .agents import (
    CioDemoAdapter,
    CompanyAnalystDemoAdapter,
    IndependentSkepticDemoAdapter,
)
from .contracts import (
    DECISION_ENVELOPE_VERSION,
    DISPATCH_VERSION,
    REQUEST_VERSION,
    RUN_VERSION,
    DemoValidationError,
    artifact_ref,
    load_demo_input,
    load_json_object,
    validate_agent_request,
    validate_agent_response,
    validate_dispatch_record,
    validate_final_decision,
    validate_role_response,
)
from .ports import DeterministicMathPort, EvidenceQueryPort
from .topology import build_agent_package_topology


LIMITATIONS = [
    "合成示例，不使用真实市场数据。",
    "未使用真实 LLM。",
    "未执行专业 Skill 推理或真实 Codex Subagent。",
    "CIO Demo Adapter 不代表当前 Codex 主线程担任 CIO。",
    "仅供装配演示，不构成投资建议或交易依据。",
]

DECISION_FIELDS = (
    "action", "security_id", "current_weight", "target_weight_range",
    "maximum_notional", "time_horizon", "thesis", "counter_thesis",
    "consensus", "conflicts", "unresolved_questions", "invalidation_conditions",
    "confidence", "confidence_rationale", "evidence_refs", "no_trade_reason",
    "no_trade_explanation", "reevaluation_conditions", "advisory_only",
)


def _write_json(path: Path, value: Mapping[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def _portfolio_summary(demo_input: Mapping[str, Any]) -> dict[str, Any]:
    portfolio = demo_input["portfolio"]
    positions = [
        {
            "security_id": item["security_id"],
            "quantity": item["quantity"],
            "input_price": item["price"],
            "industry": item.get("industry", "Unclassified"),
        }
        for item in portfolio["positions"]
    ]
    total = portfolio["cash"] + sum(
        item["quantity"] * item["price"] for item in portfolio["positions"]
    )
    return {
        "base_currency": portfolio["base_currency"],
        "cash": portfolio["cash"],
        "total_input_value": total,
        "positions": positions,
        "mandate": deepcopy(portfolio["mandate"]),
    }


def _invocation_id(run_id: str, agent: str) -> str:
    return "demo-inv-" + canonical_hash({"run_id": run_id, "agent": agent})[:20]


def _request(
    demo_input: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    agent: str,
    payload: Mapping[str, Any],
    input_refs: list[dict[str, str]],
    upstream_responses: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    value = {
        "schema_version": REQUEST_VERSION,
        "run_id": demo_input["run_id"],
        "invocation_id": _invocation_id(demo_input["run_id"], agent),
        "sender": "demo_orchestrator",
        "recipient": agent,
        "input_refs": deepcopy(input_refs),
        "portfolio_summary": _portfolio_summary(demo_input),
        "research_question": demo_input["research_question"],
        "decision_cutoff": demo_input["decision_cutoff"],
        "allowed_evidence_ids": list(gate["allowed_evidence_ids"]),
        "demo_payload": deepcopy(payload),
        "upstream_responses": deepcopy(upstream_responses or []),
    }
    return validate_agent_request(value)


def _tool_ports(
    gate: Mapping[str, Any], request: Mapping[str, Any], *, allow_math: bool
) -> tuple[EvidenceQueryPort, DeterministicMathPort | None, GateScopedFixtureTools]:
    permissions = ["fixture_evidence.query"]
    if allow_math:
        permissions.append("fixture_math.calculate")
    tools = GateScopedFixtureTools(
        gate,
        run_id=request["run_id"],
        agent=request["recipient"],
        invocation_id=request["invocation_id"],
        allowed_tools=permissions,
    )
    return (
        EvidenceQueryPort(tools),
        DeterministicMathPort(tools) if allow_math else None,
        tools,
    )


def _dispatch(
    *,
    run_id: str,
    sender: str,
    recipient: str,
    sequence: int,
    artifact: Mapping[str, Any],
    artifact_id: str,
) -> dict[str, Any]:
    value = {
        "schema_version": DISPATCH_VERSION,
        "run_id": run_id,
        "dispatch_id": f"dispatch-{sequence:02d}",
        "from": sender,
        "to": recipient,
        "artifact_ref": artifact_ref(artifact_id, artifact),
        "validation_status": "VALIDATED",
    }
    return validate_dispatch_record(
        value,
        expected_run_id=run_id,
        expected_sender=sender,
        expected_recipient=recipient,
    )


def _safe_no_trade(*, reason: str, explanation: str, reevaluate: list[str]) -> dict[str, Any]:
    return {
        "action": "NO_TRADE",
        "security_id": None,
        "current_weight": None,
        "target_weight_range": None,
        "maximum_notional": None,
        "time_horizon": "等待满足重新评估条件",
        "thesis": "",
        "counter_thesis": "",
        "consensus": [],
        "conflicts": [],
        "unresolved_questions": [],
        "invalidation_conditions": [],
        "confidence": 0.0,
        "confidence_rationale": "未形成可供研究综合的 Gate 合格 Evidence。",
        "evidence_refs": [],
        "no_trade_reason": reason,
        "no_trade_explanation": explanation,
        "reevaluation_conditions": reevaluate,
        "advisory_only": True,
    }


def _decision_after_risk(draft: Mapping[str, Any], risk: Mapping[str, Any]) -> dict[str, Any]:
    decision = {field: deepcopy(draft[field]) for field in DECISION_FIELDS}
    if risk["check"]["status"] != "APPROVED":
        decision.update(
            action="NO_TRADE",
            target_weight_range=None,
            maximum_notional=None,
            no_trade_reason="RISK_VETO",
            no_trade_explanation="deterministic Risk Engine 未批准 CIO Demo 草案。",
            reevaluation_conditions=["修正风险违规并重新经过相同 Risk Policy 校验。"],
        )
    return decision


def _decision_envelope(
    *,
    run_id: str,
    terminal_state: str,
    decision: Mapping[str, Any],
    risk: Mapping[str, Any] | None,
    allowed_evidence_ids: list[str],
) -> dict[str, Any]:
    value = {
        "schema_version": DECISION_ENVELOPE_VERSION,
        "profile": "DEMO_SCAFFOLD",
        "run_id": run_id,
        "synthetic": True,
        "advisory_only": True,
        "llm_used": False,
        "terminal_state": terminal_state,
        "decision": dict(decision),
        "risk_result_ref": artifact_ref("risk/result.json", risk) if risk else None,
        "limitations": LIMITATIONS,
    }
    validate_final_decision(decision, allowed_evidence_ids=allowed_evidence_ids)
    return value


def _render_report(
    demo_input: Mapping[str, Any],
    gate: Mapping[str, Any],
    envelope: Mapping[str, Any],
    *,
    responses: Mapping[str, Mapping[str, Any]],
    risk: Mapping[str, Any] | None,
) -> str:
    decision = envelope["decision"]
    lines = [
        "# Agent Package 合成演示报告",
        "",
        "> **合成示例｜未使用真实 LLM｜未使用真实市场数据｜不得作为投资建议或交易依据。**",
        "",
        "## Portfolio",
        "",
        f"- 基础货币：{demo_input['portfolio']['base_currency']}",
        f"- 现金：{demo_input['portfolio']['cash']}",
    ]
    for item in demo_input["portfolio"]["positions"]:
        lines.append(
            f"- 合成持仓：{item['security_id']}，数量 {item['quantity']}，输入价格 {item['price']}"
        )
    lines.extend(["", "## 角色状态", ""])
    if responses:
        for agent in ("runtime_company_analyst", "runtime_skeptic", "runtime_cio"):
            response = responses.get(agent)
            if response:
                lines.append(
                    f"- {agent}: {response['status']}（deterministic demo，Skill 推理未执行）"
                )
    else:
        lines.append("- PIT Gate 后无可用 Evidence，未调用任何 Agent，也未伪造响应。")

    lines.extend(["", "## Thesis 与反证", ""])
    if responses:
        analyst = responses["runtime_company_analyst"]["output"]
        skeptic = responses["runtime_skeptic"]["output"]
        for claim in analyst["claims"]:
            lines.append(f"- Analyst：{claim['statement']}")
        for challenge in skeptic["challenges"]:
            lines.append(f"- Skeptic：{challenge['statement']}")
        lines.extend(["", "## 共识与冲突", ""])
        lines.extend(f"- 共识：{item}" for item in decision["consensus"])
        if decision["conflicts"]:
            lines.extend(f"- 冲突：{item['summary']}" for item in decision["conflicts"])
        else:
            lines.append("- 未声明结构化证据冲突。")
    else:
        lines.append("- 未进入研究阶段。")

    lines.extend(["", "## Evidence", ""])
    allowed = {item["evidence_id"]: item for item in gate["allowed_evidence"]}
    if decision["evidence_refs"]:
        for evidence_id in decision["evidence_refs"]:
            fact = allowed[evidence_id]
            lines.append(
                f"- {evidence_id}：source_id={fact['source_id']}，as_of={fact['as_of']}，retrieved_at={fact['retrieved_at']}"
            )
    else:
        lines.append("- 无 Gate 合格 Evidence 被最终决策引用。")
    if gate["excluded"]:
        lines.extend(
            f"- Gate 排除 {item['evidence_id']}：{', '.join(item['reason_codes'])}"
            for item in gate["excluded"]
        )

    gaps: list[str] = []
    for name in ("runtime_company_analyst", "runtime_skeptic"):
        if name in responses:
            gaps.extend(responses[name]["output"]["data_gaps"])
    lines.extend(["", "## 数据缺口", ""])
    lines.extend(f"- {item}" for item in gaps) if gaps else lines.append("- 未进入 Agent 阶段。")
    lines.extend(["", "## 失效条件", ""])
    if decision["invalidation_conditions"]:
        lines.extend(f"- {item}" for item in decision["invalidation_conditions"])
    else:
        lines.append("- 等待新的合格 Evidence。")
    lines.extend(
        [
            "",
            "## 决策与置信度",
            "",
            f"- Action：{decision['action']}",
            f"- Confidence：{decision['confidence']}",
            f"- 理由：{decision['confidence_rationale']}",
            f"- 终态：{envelope['terminal_state']}",
            "",
            "## deterministic Risk Engine",
            "",
        ]
    )
    if risk:
        lines.extend(
            [
                f"- Policy：{risk['policy_version']}",
                f"- Check：{risk['check']['status']}",
                f"- Final Action：{risk['final_action']}",
                f"- Veto：{risk['veto_reason']}",
            ]
        )
    else:
        lines.append("- Agent 前安全终止，未伪造 Risk 调用。")
    lines.extend(["", "## Demo 限制", ""])
    lines.extend(f"- {item}" for item in LIMITATIONS)
    return "\n".join(lines) + "\n"


def _run_demo(
    repository_root: Path,
    demo_input: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    topology = build_agent_package_topology(repository_root)
    _write_json(output_dir / "input.json", demo_input)
    _write_json(output_dir / "package-topology.json", topology)
    gate = run_evidence_gate(demo_input, run_id=demo_input["run_id"]).artifact
    _write_json(output_dir / "evidence" / "gate.json", gate)
    base_refs = [
        artifact_ref("input.json", demo_input),
        artifact_ref("evidence/gate.json", gate),
    ]

    if not gate["allowed_evidence_ids"]:
        decision = _safe_no_trade(
            reason="INSUFFICIENT_EVIDENCE",
            explanation="PIT Gate 排除了全部合成 Evidence。",
            reevaluate=["提供 decision_cutoff 之前取得且满足 freshness policy 的 Evidence。"],
        )
        validate_final_decision(decision, allowed_evidence_ids=[])
        envelope = _decision_envelope(
            run_id=demo_input["run_id"],
            terminal_state="DEMO_SAFE_NO_TRADE",
            decision=decision,
            risk=None,
            allowed_evidence_ids=[],
        )
        _write_json(output_dir / "decision.json", envelope)
        _write_text(
            output_dir / "report.md",
            _render_report(demo_input, gate, envelope, responses={}, risk=None),
        )
        run = {
            "schema_version": RUN_VERSION,
            "run_id": demo_input["run_id"],
            "profile": "DEMO_SCAFFOLD",
            "terminal_state": "DEMO_SAFE_NO_TRADE",
            "stages": ["INPUT", "PACKAGE_TOPOLOGY", "PIT_GATE", "SAFE_NO_TRADE", "REPORT"],
            "agent_invocations": [],
            "dispatch_records": [],
            "tool_events": [],
            "artifacts": ["input.json", "package-topology.json", "evidence/gate.json", "decision.json", "report.md", "demo_run.json"],
            "llm_used": False,
            "advanced_assurance_run": False,
        }
        run["run_hash"] = canonical_hash(run)
        _write_json(output_dir / "demo_run.json", run)
        return run

    requests: dict[str, dict[str, Any]] = {}
    responses: dict[str, dict[str, Any]] = {}
    dispatches: list[dict[str, Any]] = []
    events: list[Mapping[str, Any]] = []

    analyst_request = _request(
        demo_input, gate, agent="runtime_company_analyst",
        payload=demo_input["role_samples"]["analyst"], input_refs=base_refs,
    )
    skeptic_request = _request(
        demo_input, gate, agent="runtime_skeptic",
        payload=demo_input["role_samples"]["skeptic"], input_refs=base_refs,
    )
    requests["runtime_company_analyst"] = analyst_request
    requests["runtime_skeptic"] = skeptic_request
    dispatches.extend(
        [
            _dispatch(
                run_id=demo_input["run_id"], sender="demo_orchestrator",
                recipient="runtime_company_analyst", sequence=1,
                artifact=analyst_request, artifact_id="agents/requests/runtime_company_analyst.json",
            ),
            _dispatch(
                run_id=demo_input["run_id"], sender="demo_orchestrator",
                recipient="runtime_skeptic", sequence=2,
                artifact=skeptic_request, artifact_id="agents/requests/runtime_skeptic.json",
            ),
        ]
    )
    analyst_evidence, analyst_math, analyst_tools = _tool_ports(
        gate, analyst_request, allow_math=True
    )
    assert analyst_math is not None
    analyst_response = CompanyAnalystDemoAdapter().respond(
        analyst_request, evidence=analyst_evidence, math=analyst_math, topology=topology,
    )
    validate_role_response(analyst_response, request=analyst_request)
    skeptic_evidence, _, skeptic_tools = _tool_ports(
        gate, skeptic_request, allow_math=False
    )
    skeptic_response = IndependentSkepticDemoAdapter().respond(
        skeptic_request, evidence=skeptic_evidence, topology=topology
    )
    validate_role_response(skeptic_response, request=skeptic_request)
    responses["runtime_company_analyst"] = analyst_response
    responses["runtime_skeptic"] = skeptic_response
    events.extend(analyst_tools.events)
    events.extend(skeptic_tools.events)

    analyst_ref = artifact_ref("agents/responses/runtime_company_analyst.json", analyst_response)
    skeptic_ref = artifact_ref("agents/responses/runtime_skeptic.json", skeptic_response)
    dispatches.extend(
        [
            _dispatch(
                run_id=demo_input["run_id"], sender="runtime_company_analyst",
                recipient="runtime_cio", sequence=3, artifact=analyst_response,
                artifact_id="agents/responses/runtime_company_analyst.json",
            ),
            _dispatch(
                run_id=demo_input["run_id"], sender="runtime_skeptic",
                recipient="runtime_cio", sequence=4, artifact=skeptic_response,
                artifact_id="agents/responses/runtime_skeptic.json",
            ),
        ]
    )
    cio_request = _request(
        demo_input, gate, agent="runtime_cio",
        payload=demo_input["role_samples"]["cio"],
        input_refs=[*base_refs, analyst_ref, skeptic_ref],
        upstream_responses=[analyst_response, skeptic_response],
    )
    requests["runtime_cio"] = cio_request
    cio_evidence, _, cio_tools = _tool_ports(gate, cio_request, allow_math=False)
    cio_response = CioDemoAdapter().respond(cio_request, evidence=cio_evidence, topology=topology)
    validate_role_response(cio_response, request=cio_request)
    responses["runtime_cio"] = cio_response
    events.extend(cio_tools.events)
    dispatches.append(
        _dispatch(
            run_id=demo_input["run_id"], sender="runtime_cio",
            recipient="deterministic_risk_engine", sequence=5,
            artifact=cio_response, artifact_id="agents/responses/runtime_cio.json",
        )
    )

    for agent, request in requests.items():
        _write_json(output_dir / "agents" / "requests" / f"{agent}.json", request)
    for agent, response in responses.items():
        _write_json(output_dir / "agents" / "responses" / f"{agent}.json", response)
    _write_json(output_dir / "dispatch" / "records.json", dispatches)
    _write_json(output_dir / "tools" / "events.json", list(events))

    draft = cio_response["output"]
    risk = check_cio_draft(demo_input, draft, run_id=demo_input["run_id"])
    risk["result_hash"] = canonical_hash(risk)
    _write_json(output_dir / "risk" / "result.json", risk)
    decision = _decision_after_risk(draft, risk)
    validate_no_investment_policy_keys(decision)
    validate_final_decision(decision, allowed_evidence_ids=gate["allowed_evidence_ids"])
    terminal = "DEMO_SAFE_NO_TRADE" if decision["action"] == "NO_TRADE" else "DEMO_COMPLETED"
    envelope = _decision_envelope(
        run_id=demo_input["run_id"], terminal_state=terminal, decision=decision,
        risk=risk, allowed_evidence_ids=gate["allowed_evidence_ids"],
    )
    _write_json(output_dir / "decision.json", envelope)
    _write_text(
        output_dir / "report.md",
        _render_report(demo_input, gate, envelope, responses=responses, risk=risk),
    )
    run = {
        "schema_version": RUN_VERSION,
        "run_id": demo_input["run_id"],
        "profile": "DEMO_SCAFFOLD",
        "terminal_state": terminal,
        "stages": [
            "INPUT", "PACKAGE_TOPOLOGY", "PIT_GATE", "SPECIALIST_FAN_OUT",
            "SPECIALIST_FAN_IN", "CIO", "RISK", "DECISION", "REPORT",
        ],
        "agent_invocations": [
            {
                "agent": name,
                "invocation_id": responses[name]["invocation_id"],
                "status": responses[name]["status"],
                "producer_type": "deterministic_demo",
            }
            for name in ("runtime_company_analyst", "runtime_skeptic", "runtime_cio")
        ],
        "dispatch_records": dispatches,
        "tool_events": list(events),
        "artifacts": [
            "input.json", "package-topology.json", "evidence/gate.json",
            "agents/requests/runtime_company_analyst.json",
            "agents/requests/runtime_skeptic.json", "agents/requests/runtime_cio.json",
            "agents/responses/runtime_company_analyst.json",
            "agents/responses/runtime_skeptic.json", "agents/responses/runtime_cio.json",
            "dispatch/records.json", "tools/events.json", "risk/result.json",
            "decision.json", "report.md", "demo_run.json",
        ],
        "llm_used": False,
        "skill_reasoning_executed": False,
        "real_subagents_started": False,
        "main_thread_cio_executed": False,
        "advanced_assurance_run": False,
    }
    run["run_hash"] = canonical_hash(run)
    _write_json(output_dir / "demo_run.json", run)
    return run


def run_demo(repository_root: Path, *, input_path: Path, output_dir: Path) -> dict[str, Any]:
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    try:
        demo_input = load_demo_input(input_path.resolve())
        return _run_demo(repository_root.resolve(), demo_input, destination)
    except (DemoValidationError, ValueError, KeyError, TypeError, OSError) as exc:
        failure = {
            "schema_version": RUN_VERSION,
            "profile": "DEMO_SCAFFOLD",
            "terminal_state": "DEMO_FAILED_VALIDATION",
            "failure_code": str(exc).split(":", 1)[0],
            "message": str(exc),
            "llm_used": False,
            "advanced_assurance_run": False,
        }
        try:
            _write_json(destination / "failure.json", failure)
        except OSError:
            pass
        raise DemoValidationError(str(exc)) from exc


def run_single_agent(
    repository_root: Path,
    *,
    input_path: Path,
    agent: str,
    output_path: Path,
    analyst_response_path: Path | None = None,
    skeptic_response_path: Path | None = None,
) -> dict[str, Any]:
    demo_input = load_demo_input(input_path.resolve())
    topology = build_agent_package_topology(repository_root.resolve())
    gate = run_evidence_gate(demo_input, run_id=demo_input["run_id"]).artifact
    if not gate["allowed_evidence_ids"]:
        raise DemoValidationError("NO_EVIDENCE_FOR_SINGLE_AGENT_CALL")
    refs = [artifact_ref("input", demo_input), artifact_ref("gate", gate)]
    if agent == "runtime_company_analyst":
        request = _request(
            demo_input, gate, agent=agent,
            payload=demo_input["role_samples"]["analyst"], input_refs=refs,
        )
        evidence, math, _ = _tool_ports(gate, request, allow_math=True)
        assert math is not None
        response = CompanyAnalystDemoAdapter().respond(
            request, evidence=evidence, math=math, topology=topology
        )
    elif agent == "runtime_skeptic":
        request = _request(
            demo_input, gate, agent=agent,
            payload=demo_input["role_samples"]["skeptic"], input_refs=refs,
        )
        evidence, _, _ = _tool_ports(gate, request, allow_math=False)
        response = IndependentSkepticDemoAdapter().respond(
            request, evidence=evidence, topology=topology
        )
    elif agent == "runtime_cio":
        if analyst_response_path is None or skeptic_response_path is None:
            raise DemoValidationError("CIO_SPECIALIST_RESPONSE_PATHS_REQUIRED")
        upstream = [
            load_json_object(analyst_response_path.resolve()),
            load_json_object(skeptic_response_path.resolve()),
        ]
        expected_roles = ("runtime_company_analyst", "runtime_skeptic")
        for role, item in zip(expected_roles, upstream):
            if item.get("agent_name") != role or item.get("run_id") != demo_input["run_id"]:
                raise DemoValidationError("CIO_SPECIALIST_RESPONSE_IDENTITY_INVALID")
        request = _request(
            demo_input, gate, agent=agent,
            payload=demo_input["role_samples"]["cio"],
            input_refs=[
                *refs,
                *(artifact_ref(f"response:{item['agent_name']}", item) for item in upstream),
            ],
            upstream_responses=upstream,
        )
        evidence, _, _ = _tool_ports(gate, request, allow_math=False)
        response = CioDemoAdapter().respond(
            request, evidence=evidence, topology=topology
        )
    else:
        raise DemoValidationError(f"UNKNOWN_DEMO_AGENT:{agent}")
    validate_agent_response(response, request=request)
    validate_role_response(response, request=request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, response)
    return response
