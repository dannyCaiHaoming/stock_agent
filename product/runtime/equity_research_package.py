"""估值/基本面/同行/图表附件的冻结包与 Gate-scoped 只读查询。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from product.deterministic.equity_valuation import (
    validate_fundamental_supplement,
    validate_peer_comparison,
    validate_valuation_history,
    validate_valuation_snapshot,
)
from product.mcp.provenance import parse_timestamp
from product.runtime.fixture_mcp import ToolAccessError
from product.runtime.hashing import canonical_hash


PACKAGE_VERSION = "equity-research-attachments/1.0.0"
ADAPTER_VERSION = "equity-research-attachments-gate-scoped/1.0.0"
ARTIFACT_KINDS = {
    "valuation_snapshot", "valuation_history", "fundamental_supplement",
    "peer_comparison", "visual_bundle",
}
MODEL_QUERY_ARTIFACT_KINDS = {
    "valuation_snapshot", "valuation_history", "fundamental_supplement",
    "peer_comparison",
}


class EquityResearchPackageError(ValueError):
    pass


def _hash_without(value: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _evidence_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "evidence_refs" and isinstance(item, list):
                refs.update(ref for ref in item if isinstance(ref, str))
            else:
                refs.update(_evidence_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_evidence_refs(item))
    return refs


def _calculation_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "calculation_ref" and isinstance(item, str) and item:
                refs.add(item)
            elif key == "calculation_refs" and isinstance(item, list):
                refs.update(ref for ref in item if isinstance(ref, str) and ref)
            else:
                refs.update(_calculation_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_calculation_refs(item))
    return refs


def _validate_artifact(kind: str, artifact: Mapping[str, Any]) -> None:
    if kind == "valuation_snapshot":
        validate_valuation_snapshot(artifact)
    elif kind == "valuation_history":
        validate_valuation_history(artifact)
    elif kind == "fundamental_supplement":
        validate_fundamental_supplement(artifact)
    elif kind == "peer_comparison":
        validate_peer_comparison(artifact)
    elif kind == "visual_bundle":
        from product.council.research_visuals import validate_visual_bundle
        validate_visual_bundle(artifact)
    else:
        raise EquityResearchPackageError("EQUITY_ATTACHMENT_KIND_INVALID")


def build_equity_research_package(
    *, package_id: str, run_id: str, security_id: str, decision_cutoff: str,
    gate_bundle_hash: str, artifacts: Mapping[str, Mapping[str, Any]],
    raw_input_refs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    if not artifacts or not set(artifacts) <= ARTIFACT_KINDS:
        raise EquityResearchPackageError("EQUITY_ATTACHMENT_SET_INVALID")
    entries = []
    for kind, artifact in sorted(artifacts.items()):
        _validate_artifact(kind, artifact)
        entries.append({
            "kind": kind, "artifact": deepcopy(dict(artifact)),
            "artifact_hash": artifact.get("artifact_hash") or artifact.get("bundle_hash"),
        })
    value = {
        "schema_version": PACKAGE_VERSION, "package_id": package_id,
        "run_id": run_id, "security_id": security_id,
        "decision_cutoff": decision_cutoff, "gate_bundle_hash": gate_bundle_hash,
        "raw_input_refs": sorted((deepcopy(dict(item)) for item in raw_input_refs), key=lambda item: item["ref"]),
        "artifacts": entries,
    }
    value["package_hash"] = canonical_hash(value)
    validate_equity_research_package(value)
    return value


def validate_equity_research_package(
    value: Mapping[str, Any], *, gate: Mapping[str, Any] | None = None,
) -> None:
    expected = {"schema_version", "package_id", "run_id", "security_id", "decision_cutoff", "gate_bundle_hash", "raw_input_refs", "artifacts", "package_hash"}
    if set(value) != expected or value.get("schema_version") != PACKAGE_VERSION:
        raise EquityResearchPackageError("EQUITY_ATTACHMENT_PACKAGE_SHAPE_INVALID")
    if value.get("package_hash") != _hash_without(value, "package_hash"):
        raise EquityResearchPackageError("EQUITY_ATTACHMENT_PACKAGE_HASH_MISMATCH")
    cutoff = parse_timestamp(value["decision_cutoff"])
    raw_refs: dict[str, Mapping[str, Any]] = {}
    for item in value["raw_input_refs"]:
        if set(item) != {"ref", "source_id", "retrieved_at", "raw_content_hash"}:
            raise EquityResearchPackageError("EQUITY_RAW_INPUT_SHAPE_INVALID")
        if not str(item["ref"]).startswith("raw:") or item["ref"] in raw_refs:
            raise EquityResearchPackageError("EQUITY_RAW_INPUT_REF_INVALID")
        if parse_timestamp(item["retrieved_at"]) > cutoff:
            raise EquityResearchPackageError("EQUITY_RAW_INPUT_AFTER_CUTOFF")
        if len(str(item["raw_content_hash"])) != 64:
            raise EquityResearchPackageError("EQUITY_RAW_INPUT_HASH_INVALID")
        raw_refs[item["ref"]] = item
    kinds: set[str] = set()
    refs: set[str] = set()
    for entry in value["artifacts"]:
        if set(entry) != {"kind", "artifact", "artifact_hash"} or entry["kind"] in kinds:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_ENTRY_INVALID")
        kinds.add(entry["kind"])
        artifact = entry["artifact"]
        try:
            _validate_artifact(entry["kind"], artifact)
        except (KeyError, TypeError, ValueError) as exc:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_ARTIFACT_INVALID") from exc
        expected_hash = artifact.get("artifact_hash") or artifact.get("bundle_hash")
        if entry["artifact_hash"] != expected_hash:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_HASH_MISMATCH")
        if artifact.get("security_id", value["security_id"]) != value["security_id"]:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_SECURITY_MISMATCH")
        artifact_cutoff = artifact.get("decision_cutoff")
        if artifact_cutoff is not None and artifact_cutoff != value["decision_cutoff"]:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_CUTOFF_MISMATCH")
        refs.update(_evidence_refs(artifact))
    raw_used = {ref for ref in refs if ref.startswith("raw:")}
    if raw_used - set(raw_refs):
        raise EquityResearchPackageError("EQUITY_RAW_INPUT_REFERENCE_DANGLING")
    if gate is not None:
        gate_hash = _hash_without(gate, "bundle_hash")
        if gate.get("bundle_hash") != gate_hash or value["gate_bundle_hash"] != gate["bundle_hash"]:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_GATE_BINDING_INVALID")
        if gate.get("run_id") not in {None, value["run_id"]}:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_RUN_MISMATCH")
        if gate.get("decision_cutoff") not in {None, value["decision_cutoff"]}:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_CUTOFF_MISMATCH")
        allowed = set(gate.get("allowed_evidence_ids", []))
        evidence_used = {ref for ref in refs if not ref.startswith("raw:")}
        if evidence_used - allowed:
            raise EquityResearchPackageError("EQUITY_ATTACHMENT_EVIDENCE_NOT_ADMITTED")


class GateScopedEquityResearchTools:
    """只查询构造时冻结且已绑定 Gate 的附件；不联网、不采集。"""

    adapter_version = ADAPTER_VERSION

    def __init__(
        self, *, package: Mapping[str, Any], gate: Mapping[str, Any],
        run_id: str, agent: str, invocation_id: str,
    ) -> None:
        try:
            validate_equity_research_package(package, gate=gate)
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolAccessError("EQUITY_ATTACHMENT_PACKAGE_INVALID") from exc
        if package["run_id"] != run_id or not agent or not invocation_id:
            raise ToolAccessError("EQUITY_ATTACHMENT_INVOCATION_INVALID")
        self.package = deepcopy(dict(package))
        self.run_id, self.agent, self.invocation_id = run_id, agent, invocation_id
        self._artifacts = {item["kind"]: item["artifact"] for item in package["artifacts"]}
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        return ({
            "name": "equity_research_attachments.query",
            "description": "按冻结证券与 cutoff 查询估值、基本面或同行附件；图表只由确定性报告层消费。",
            "inputSchema": {
                "type": "object", "additionalProperties": False,
                "required": ["run_id", "agent", "invocation_id", "security_id", "decision_cutoff", "kinds"],
                "properties": {
                    "run_id": {"type": "string"}, "agent": {"type": "string"},
                    "invocation_id": {"type": "string"}, "security_id": {"type": "string"},
                    "decision_cutoff": {"type": "string"},
                    "kinds": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                },
            },
        },)

    def query(
        self, *, run_id: str, agent: str, invocation_id: str,
        security_id: str, decision_cutoff: str, kinds: Sequence[str],
    ) -> dict[str, Any]:
        if (run_id, agent, invocation_id) != (self.run_id, self.agent, self.invocation_id):
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")
        if security_id != self.package["security_id"]:
            raise ToolAccessError("EQUITY_ATTACHMENT_SECURITY_SCOPE_MISMATCH")
        if decision_cutoff != self.package["decision_cutoff"]:
            raise ToolAccessError("EQUITY_ATTACHMENT_CUTOFF_SCOPE_MISMATCH")
        requested = list(kinds)
        if (
            not requested
            or requested != list(dict.fromkeys(requested))
            or not set(requested) <= MODEL_QUERY_ARTIFACT_KINDS
            or not set(requested) <= set(self._artifacts)
        ):
            raise ToolAccessError("EQUITY_ATTACHMENT_KIND_SCOPE_INVALID")
        artifacts = {kind: deepcopy(self._artifacts[kind]) for kind in requested}
        output = {
            "adapter_version": ADAPTER_VERSION, "run_id": run_id,
            "security_id": security_id, "decision_cutoff": decision_cutoff,
            "artifacts": artifacts, "result_hash": canonical_hash(artifacts),
        }
        self.events.append({
            "event_type": "mcp_tool_result", "adapter_version": ADAPTER_VERSION,
            "run_id": run_id, "agent": agent, "invocation_id": invocation_id,
            "tool": "equity_research_attachments.query", "access_mode": "read",
            "input_hash": canonical_hash({"security_id": security_id, "decision_cutoff": decision_cutoff, "kinds": requested}),
            "output_hash": canonical_hash(output),
            "artifact_kinds": sorted(requested),
            "artifact_hashes": sorted(
                str(entry.get("artifact_hash") or entry.get("bundle_hash"))
                for entry in artifacts.values()
            ),
            "evidence_ids": sorted({
                ref for artifact in artifacts.values() for ref in _evidence_refs(artifact)
                if not ref.startswith("raw:")
            }),
            "calculation_ids": sorted(
                {ref for artifact in artifacts.values() for ref in _calculation_refs(artifact)}
            ),
        })
        return output
