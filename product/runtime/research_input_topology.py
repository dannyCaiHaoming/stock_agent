"""当前 Company / Macro / Market 研究输入拓扑的确定性发现与锁定。"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.schema_validation import validate_schema_instance


TOPOLOGY_SCHEMA_VERSION = "holding-research-input-topology/1.0.0"
TOPOLOGY_PROFILE_ID = "holding-research-inputs/1.0.0"
TOPOLOGY_RELATIVE_PATH = "profiles/holding-research-inputs.json"
TOPOLOGY_SCHEMA_PATH = "schemas/runtime/holding-research-input-topology.schema.json"

EXPECTED_DOMAIN_CAPABILITIES = {
    "COMPANY": {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"},
    "MACRO": {"MACRO_CONTEXT"},
    "MARKET": {"MARKET_STATE"},
}
EXPECTED_CAPABILITY_BINDINGS = {
    "FUNDAMENTAL_EVENT": ("runtime_company_analyst", "company-research", "PER_SECURITY"),
    "RESEARCH_REPORT": ("runtime_company_analyst", "research-report-analysis", "PER_SECURITY"),
    "MACRO_CONTEXT": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
    "MARKET_STATE": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
}
EXPECTED_PROVIDER_PLANES = {"BASE_DISCLOSURE", "OFFICIAL_MACRO", "RESEARCH_SUPPLEMENT"}
PROVIDER_COVERAGE_VERSION = "research-provider-coverage/1.0.0"
CAPABILITY_SUCCESS_STATUSES = {"AVAILABLE", "PARTIAL"}


class ResearchInputTopologyError(ValueError):
    """研究输入拓扑或它锁定的仓库资源发生漂移。"""


def _read_json(path: Path, failure_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchInputTopologyError(failure_code) from exc
    if not isinstance(value, Mapping):
        raise ResearchInputTopologyError(failure_code)
    return dict(value)


def _product_path(product_root: Path, relative_path: str) -> Path:
    candidate = (product_root / relative_path).resolve()
    try:
        candidate.relative_to(product_root)
    except ValueError as exc:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_PATH_ESCAPE") from exc
    if not candidate.is_file():
        raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_RESOURCE_MISSING:{relative_path}")
    return candidate


def _declared_version(value: Mapping[str, Any]) -> str | None:
    for key in ("schema_version", "$id", "profile_id"):
        declared = value.get(key)
        if isinstance(declared, str) and declared:
            return declared
    return None


def _skill_name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^name:\s*([^\n]+)$", text)
    return match.group(1).strip().strip("\"'") if match else None


def load_research_input_topology(
    repository_root: Path,
    *,
    topology_path: Path | None = None,
) -> dict[str, Any]:
    """读取并验证当前拓扑、绑定和全部被锁定的来源文件。"""

    root = Path(repository_root).resolve()
    product_root = (root / "product").resolve()
    if not product_root.is_dir() or product_root.parent != root:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_PRODUCT_ROOT_MISSING")
    path = (
        Path(topology_path).resolve()
        if topology_path is not None
        else product_root / TOPOLOGY_RELATIVE_PATH
    )
    value = _read_json(path, "RESEARCH_TOPOLOGY_INVALID_JSON")
    schema = _read_json(
        product_root / TOPOLOGY_SCHEMA_PATH,
        "RESEARCH_TOPOLOGY_SCHEMA_MISSING",
    )
    try:
        validate_schema_instance(value, schema)
    except Exception as exc:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_SCHEMA_INVALID") from exc
    expected_hash = canonical_hash(
        {key: item for key, item in value.items() if key != "topology_hash"}
    )
    if value.get("topology_hash") != expected_hash:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_HASH_MISMATCH")

    domains = value["domains"]
    domain_names = [item["domain"] for item in domains]
    if len(domain_names) != len(set(domain_names)) or set(domain_names) != set(EXPECTED_DOMAIN_CAPABILITIES):
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_DOMAIN_SET_INVALID")
    seen_capabilities: set[str] = set()
    for domain in domains:
        capabilities = domain["capabilities"]
        actual = {item["capability"] for item in capabilities}
        if actual != EXPECTED_DOMAIN_CAPABILITIES[domain["domain"]] or len(actual) != len(capabilities):
            raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_DOMAIN_CAPABILITIES_INVALID:{domain['domain']}")
        for capability in capabilities:
            capability_id = capability["capability"]
            if capability_id in seen_capabilities:
                raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_CAPABILITY_DUPLICATE")
            seen_capabilities.add(capability_id)
            expected = EXPECTED_CAPABILITY_BINDINGS[capability_id]
            actual_binding = (capability["agent"], capability["skill"], capability["scope"])
            if actual_binding != expected:
                raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_BINDING_INVALID:{capability_id}")
            agent_path = _product_path(product_root, capability["agent_path"])
            with agent_path.open("rb") as stream:
                agent_config = tomllib.load(stream)
            if agent_config.get("name") != capability["agent"]:
                raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_AGENT_INVALID:{capability_id}")
            skill_path = _product_path(product_root, capability["skill_path"])
            if _skill_name(skill_path) != capability["skill"]:
                raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_SKILL_INVALID:{capability_id}")
            contract = capability["output_contract"]
            contract_path = _product_path(product_root, contract["path"])
            contract_value = _read_json(contract_path, "RESEARCH_TOPOLOGY_OUTPUT_CONTRACT_INVALID")
            if contract_value.get("$id") != contract["schema_version"]:
                raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_OUTPUT_CONTRACT_DRIFT:{capability_id}")

    planes = value["provider_planes"]
    plane_names = [item["plane"] for item in planes]
    if len(plane_names) != len(set(plane_names)) or set(plane_names) != EXPECTED_PROVIDER_PLANES:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_PROVIDER_PLANES_INVALID")
    for plane in planes:
        provider_names = [item["provider"] for item in plane["providers"]]
        if len(provider_names) != len(set(provider_names)):
            raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_PROVIDER_DUPLICATE:{plane['plane']}")
    supplement = next(item for item in planes if item["plane"] == "RESEARCH_SUPPLEMENT")
    moomoo = next((item for item in supplement["providers"] if item["provider"] == "moomoo_sg"), None)
    if not isinstance(moomoo, Mapping) or moomoo.get("region") != "SG" \
            or moomoo.get("access") != "loopback_opend_quote_only":
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_MOOMOO_BOUNDARY_INVALID")

    reference_ids: set[str] = set()
    reference_paths: set[str] = set()
    for reference in value["source_references"]:
        reference_id = reference["reference_id"]
        relative_path = reference["path"]
        if reference_id in reference_ids or relative_path in reference_paths:
            raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_REFERENCE_DUPLICATE")
        reference_ids.add(reference_id)
        reference_paths.add(relative_path)
        reference_path = _product_path(product_root, relative_path)
        if file_hash(reference_path) != reference["sha256"]:
            raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_REFERENCE_HASH_MISMATCH:{reference_id}")
        reference_value = _read_json(reference_path, f"RESEARCH_TOPOLOGY_REFERENCE_INVALID:{reference_id}")
        if _declared_version(reference_value) != reference["version"]:
            raise ResearchInputTopologyError(f"RESEARCH_TOPOLOGY_REFERENCE_VERSION_MISMATCH:{reference_id}")

    compatibility = value["compatibility_profiles"]
    if len(compatibility) != 1:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_COMPATIBILITY_SET_INVALID")
    legacy = compatibility[0]
    legacy_path = _product_path(product_root, legacy["path"])
    legacy_value = _read_json(legacy_path, "RESEARCH_TOPOLOGY_COMPATIBILITY_INVALID")
    if legacy_value.get("profile_id") != legacy["profile_id"] or file_hash(legacy_path) != legacy["sha256"]:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_COMPATIBILITY_DRIFT")
    return copy.deepcopy(value)


def research_input_topology_lock(repository_root: Path) -> dict[str, Any]:
    """生成写入新运行清单的最小、可重验拓扑快照。"""

    value = load_research_input_topology(repository_root)
    product_root = Path(repository_root).resolve() / "product"
    output_contracts = {
        capability["capability"]: {
            "schema_version": capability["output_contract"]["schema_version"],
            "path": f"product/{capability['output_contract']['path']}",
            "sha256": file_hash(
                product_root / capability["output_contract"]["path"]
            ),
        }
        for domain in value["domains"]
        for capability in domain["capabilities"]
    }
    unique_contracts = {
        canonical_hash(contract): contract for contract in output_contracts.values()
    }
    if len(unique_contracts) != 1:
        raise ResearchInputTopologyError("RESEARCH_TOPOLOGY_OUTPUT_CONTRACT_SET_INVALID")
    default_output_contract = copy.deepcopy(next(iter(unique_contracts.values())))
    lock = {
        "profile_id": value["profile_id"],
        "schema_version": value["schema_version"],
        "topology_path": f"product/{TOPOLOGY_RELATIVE_PATH}",
        "topology_hash": value["topology_hash"],
        "domains": {
            item["domain"]: [capability["capability"] for capability in item["capabilities"]]
            for item in value["domains"]
        },
        "output_contracts": output_contracts,
        "default_output_contract": default_output_contract,
        "provider_planes": {
            item["plane"]: {
                provider["provider"]: provider["status"] for provider in item["providers"]
            }
            for item in value["provider_planes"]
        },
        "source_references": [
            {
                "reference_id": item["reference_id"],
                "path": f"product/{item['path']}",
                "version": item["version"],
                "sha256": item["sha256"],
            }
            for item in value["source_references"]
        ],
    }
    lock["lock_hash"] = canonical_hash(lock)
    return lock


def _fact_provider(fact: Mapping[str, Any]) -> str | None:
    source_family = fact.get("source_family")
    if isinstance(source_family, str) and source_family:
        return source_family
    source_type = str(fact.get("source_type", "")).lower()
    source_id = str(fact.get("source_id", "")).lower()
    aliases = {
        "sec": "sec",
        "yahoo": "yahoo",
        "nasdaq": "nasdaq",
        "eastmoney": "eastmoney",
        "bls": "bls",
        "treasury": "treasury",
        "federal_reserve": "federal_reserve",
        "bea": "bea",
        "fred": "fred",
        "moomoo_sg": "moomoo_sg",
        "openalex": "openalex",
    }
    if source_type in aliases:
        return aliases[source_type]
    for needle, provider in (
        ("openalex", "openalex"),
        ("moomoo", "moomoo_sg"),
        ("treasury", "treasury"),
        ("federal-reserve", "federal_reserve"),
        ("federal_reserve", "federal_reserve"),
        ("bls", "bls"),
        ("bea", "bea"),
        ("fred", "fred"),
        ("yahoo", "yahoo"),
        ("sec", "sec"),
        ("nasdaq", "nasdaq"),
        ("eastmoney", "eastmoney"),
    ):
        if needle in source_id:
            return provider
    return None


def _observed_provider_status(
    *, capability_statuses: set[str], evidence_count: int,
) -> str:
    if capability_statuses:
        successful = capability_statuses & CAPABILITY_SUCCESS_STATUSES
        unsuccessful = capability_statuses - CAPABILITY_SUCCESS_STATUSES - {"NOT_ATTEMPTED"}
        # provider 可能同时承担 base/disclosure 与 research-supplement 职责；
        # supplement 局部失败不能抹掉同批 Gate 中已存在的合格基础 Evidence。
        if evidence_count:
            successful.add("AVAILABLE")
        if successful and (unsuccessful or "PARTIAL" in successful):
            return "PARTIAL"
        if successful:
            return "AVAILABLE"
        if capability_statuses == {"NOT_ATTEMPTED"}:
            return "NOT_ATTEMPTED"
        if "BLOCKED_CONFIGURATION" in capability_statuses:
            return "BLOCKED_CONFIGURATION"
        if capability_statuses <= {"OPEND_UNREACHABLE"}:
            return "OPEND_UNREACHABLE"
        if capability_statuses <= {"ENTITLEMENT_REQUIRED", "QUOTE_NOT_LOGGED_IN"}:
            return next(iter(capability_statuses))
        return "SOURCE_LIMITED"
    return "AVAILABLE" if evidence_count else "NOT_OBSERVED"


def build_research_provider_coverage(
    repository_root: Path,
    *,
    evidence: list[Mapping[str, Any]],
    capture_batches: list[Mapping[str, Any]],
    decision_cutoff: str,
) -> dict[str, Any]:
    """把静态 provider 职责与本批真实 Evidence/attempt 分开汇总。"""

    from product.mcp.live.research_supplement import validate_capture_batch
    from product.mcp.provenance import iso_utc, parse_timestamp

    topology = load_research_input_topology(repository_root)
    cutoff = iso_utc(decision_cutoff)
    cutoff_time = parse_timestamp(cutoff)
    evidence_counts: dict[str, int] = {}
    for fact in evidence:
        provider = _fact_provider(fact)
        if provider is not None:
            evidence_counts[provider] = evidence_counts.get(provider, 0) + 1

    observations: dict[str, list[dict[str, Any]]] = {}
    for original in capture_batches:
        batch = copy.deepcopy(dict(original))
        validate_capture_batch(batch)
        if parse_timestamp(batch["decision_cutoff"]) > cutoff_time:
            raise ResearchInputTopologyError("RESEARCH_PROVIDER_COVERAGE_CUTOFF_MISMATCH")
        for capability in batch["capabilities"]:
            source = capability["source"]
            if source not in {"sec", "yahoo", "moomoo_sg"}:
                raise ResearchInputTopologyError("RESEARCH_PROVIDER_COVERAGE_SOURCE_FORBIDDEN")
            observations.setdefault(source, []).append({
                "security_id": capability["security_id"],
                "dataset": capability["dataset"],
                "status": capability["status"],
                "failure_code": capability["failure_code"],
                "checked_at": capability["checked_at"],
                "as_of": capability["as_of"],
                "evidence_ids": list(capability["evidence_ids"]),
                "limitations": list(capability["limitations"]),
            })

    providers = []
    for plane in topology["provider_planes"]:
        for provider in plane["providers"]:
            name = provider["provider"]
            attempts = sorted(
                observations.get(name, []),
                key=lambda item: (item["security_id"], item["dataset"]),
            )
            statuses = {item["status"] for item in attempts}
            observed_status = _observed_provider_status(
                capability_statuses=statuses,
                evidence_count=evidence_counts.get(name, 0),
            )
            providers.append({
                "plane": plane["plane"],
                "provider": name,
                "region": provider["region"],
                "access": provider["access"],
                "declared_status": provider["status"],
                "observed_status": observed_status,
                "evidence_count": evidence_counts.get(name, 0),
                "dataset_observations": attempts,
                "failure_codes": sorted({
                    item["failure_code"] for item in attempts
                    if isinstance(item["failure_code"], str)
                }),
                "limitations": list(provider["limitations"]),
            })
    coverage = {
        "schema_version": PROVIDER_COVERAGE_VERSION,
        "profile_id": topology["profile_id"],
        "topology_hash": topology["topology_hash"],
        "decision_cutoff": cutoff,
        "providers": providers,
        "fallback_policy": {
            "supplement_failure_isolated": True,
            "base_sources_continue": ["sec", "yahoo"],
            "forbidden_fallbacks": ["CLIENT_COOKIE", "PRIVATE_API", "LOGIN_BYPASS"],
        },
    }
    coverage["coverage_hash"] = canonical_hash(coverage)
    return coverage


def discover_research_input_profiles(repository_root: Path) -> dict[str, Any]:
    """对外区分当前研究拓扑和历史兼容 profile。"""

    value = load_research_input_topology(repository_root)
    return {
        "current": {
            "profile_id": value["profile_id"],
            "lifecycle_status": value["lifecycle_status"],
            "path": f"product/{TOPOLOGY_RELATIVE_PATH}",
            "sha256": value["topology_hash"],
        },
        "compatibility_only": copy.deepcopy(value["compatibility_profiles"]),
    }
