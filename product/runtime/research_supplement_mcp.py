"""冻结研究补充 sidecar 的只读查询工具；不暴露采集、Bootstrap 或秘密。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from product.mcp.live.research_supplement import (
    BACKGROUND_GROUPS,
    validate_company_background_snapshot,
    validate_research_supplement_package,
)
from product.mcp.provenance import content_hash, parse_timestamp
from product.runtime.fixture_mcp import ToolAccessError
from product.runtime.hashing import canonical_hash


ADAPTER_VERSION = "research-supplement-gate-scoped/1.0.0"


class GateScopedResearchSupplementTools:
    """只按已冻结 security/dataset/cutoff/batch 返回 Gate 已准入 Evidence。"""

    adapter_version = ADAPTER_VERSION

    def __init__(
        self, *, background: Mapping[str, Any], gate: Mapping[str, Any],
        run_id: str, agent: str, invocation_id: str,
        package: Mapping[str, Any] | None = None, batch: Mapping[str, Any] | None = None,
    ) -> None:
        validate_company_background_snapshot(background)
        if gate.get("run_id") not in (None, run_id):
            raise ToolAccessError("CROSS_RUN_GATE")
        if not run_id or not agent or not invocation_id:
            raise ToolAccessError("MISSING_INVOCATION_IDENTITY")
        expected_gate_hash = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        if gate.get("bundle_hash") != expected_gate_hash:
            raise ToolAccessError("INVALID_GATE_ARTIFACT")
        allowed = {
            item["evidence_id"]: deepcopy(dict(item))
            for item in gate.get("allowed_evidence", [])
        }
        supplement_facts = list(background["evidence"])
        if package is not None:
            if batch is None:
                raise ToolAccessError("SUPPLEMENT_BATCH_REQUIRED")
            try:
                validate_research_supplement_package(package, batch=batch, background=background)
            except (KeyError, TypeError, ValueError) as exc:
                raise ToolAccessError("SUPPLEMENT_PACKAGE_INVALID") from exc
            supplement_facts.extend(package["extra_evidence"])
        supplement_ids = {item["evidence_id"] for item in supplement_facts}
        if not supplement_ids <= set(allowed):
            raise ToolAccessError("SUPPLEMENT_NOT_ADMITTED_BY_GATE")
        self.background = deepcopy(dict(background))
        self._facts = {key: allowed[key] for key in supplement_ids}
        self._dataset_ids: dict[str, set[str]] = {}
        for fact in supplement_facts:
            self._dataset_ids.setdefault(fact["dataset"], set()).add(fact["evidence_id"])
        self.run_id = run_id
        self.agent = agent
        self.invocation_id = invocation_id
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        return ({
            "name": "research_supplement.query",
            "description": "按冻结证券、数据集、cutoff 和批次查询补充研究 Evidence。",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "run_id", "agent", "invocation_id", "security_id",
                    "datasets", "decision_cutoff", "batch_id",
                ],
                "properties": {
                    "run_id": {"type": "string"},
                    "agent": {"type": "string"},
                    "invocation_id": {"type": "string"},
                    "security_id": {"type": "string"},
                    "datasets": {
                        "type": "array", "items": {"type": "string"}, "minItems": 1,
                    },
                    "decision_cutoff": {"type": "string"},
                    "batch_id": {"type": "string"},
                },
            },
        },)

    def query(
        self, *, run_id: str, agent: str, invocation_id: str,
        security_id: str, datasets: Sequence[str], decision_cutoff: str,
        batch_id: str,
    ) -> dict[str, Any]:
        if (run_id, agent, invocation_id) != (self.run_id, self.agent, self.invocation_id):
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")
        if security_id != self.background["security_id"]:
            raise ToolAccessError("SUPPLEMENT_SECURITY_SCOPE_MISMATCH")
        if batch_id != self.background["batch_id"]:
            raise ToolAccessError("SUPPLEMENT_BATCH_SCOPE_MISMATCH")
        requested = list(datasets)
        allowed_datasets = set(BACKGROUND_GROUPS) | set(self._dataset_ids)
        if not requested or len(requested) != len(set(requested)) or not set(requested) <= allowed_datasets:
            raise ToolAccessError("SUPPLEMENT_DATASET_SCOPE_INVALID")
        cutoff = parse_timestamp(decision_cutoff)
        if cutoff > parse_timestamp(self.background["decision_cutoff"]):
            raise ToolAccessError("SUPPLEMENT_CUTOFF_AFTER_FREEZE")
        identifiers = {
            evidence_id for dataset in requested
            for evidence_id in (
                self.background["groups"][dataset]["evidence_ids"]
                if dataset in self.background["groups"] else self._dataset_ids.get(dataset, set())
            )
        }
        evidence = sorted((
            deepcopy(self._facts[evidence_id]) for evidence_id in identifiers
            if max(
                parse_timestamp(self._facts[evidence_id]["as_of"]),
                parse_timestamp(self._facts[evidence_id]["published_at"]),
                parse_timestamp(self._facts[evidence_id]["retrieved_at"]),
            ) <= cutoff
        ), key=lambda item: item["evidence_id"])
        inputs = {
            "run_id": run_id, "agent": agent, "invocation_id": invocation_id,
            "security_id": security_id, "datasets": requested,
            "decision_cutoff": decision_cutoff, "batch_id": batch_id,
        }
        output = {
            "adapter_version": ADAPTER_VERSION,
            "run_id": run_id,
            "security_id": security_id,
            "batch_id": batch_id,
            "decision_cutoff": decision_cutoff,
            "evidence": evidence,
            "group_statuses": {
                name: (
                    self.background["groups"][name]["status"]
                    if name in self.background["groups"] else "AVAILABLE"
                ) for name in requested
            },
            "result_hash": content_hash(evidence),
        }
        self.events.append({
            "event_type": "mcp_tool_result",
            "adapter_version": ADAPTER_VERSION,
            "run_id": run_id,
            "agent": agent,
            "invocation_id": invocation_id,
            "tool": "research_supplement.query",
            "input_hash": content_hash(inputs),
            "output_hash": content_hash(output),
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "access_mode": "read",
        })
        return output
