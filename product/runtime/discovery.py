"""Resolve repository-owned Codex resources before any model call."""

from __future__ import annotations
import json

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .decision_contract import load_decision_contract, verify_cio_schema
from .hashing import canonical_hash, file_hash
from .versioning import load_version_manifest


@dataclass(frozen=True, slots=True)
class ResourceRecord:
    resource_id: str
    relative_path: str
    resolved_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ProductDiscovery:
    product_root: str
    plugin: ResourceRecord
    plugin_mcp: ResourceRecord
    runtime_config: ResourceRecord
    runtime_profile: ResourceRecord
    decision_contract: ResourceRecord
    council_skill: ResourceRecord
    cio_agent: ResourceRecord
    company_agent: ResourceRecord
    skeptic_agent: ResourceRecord
    version_manifest: dict[str, Any]
    discovery_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


RESOURCE_PATHS = {
    "plugin": ".codex-plugin/plugin.json",
    "plugin_mcp": ".mcp.json",
    "runtime_config": ".codex/config.toml",
    "runtime_profile": "runtime-profile.json",
    "decision_contract": "contracts/council-decision-contract.json",
    "council_skill": "skills/portfolio-council/SKILL.md",
    "cio_agent": ".codex/agents/runtime_cio.toml",
    "company_agent": ".codex/agents/runtime_company_analyst.toml",
    "skeptic_agent": ".codex/agents/runtime_skeptic.toml",
}


def _record(product_root: Path, resource_id: str, relative_path: str) -> ResourceRecord:
    candidate = (product_root / relative_path).resolve()
    try:
        candidate.relative_to(product_root)
    except ValueError as exc:
        raise ValueError(f"resource escapes product root: {relative_path}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"missing product resource: {relative_path}")
    return ResourceRecord(
        resource_id=resource_id,
        relative_path=relative_path,
        resolved_path=str(candidate),
        sha256=file_hash(candidate),
    )


def discover_product_resources(repository_root: Path, *, source_profile: str = "fixture") -> ProductDiscovery:
    """Return an auditable record of the exact repository product resources."""

    root = repository_root.resolve()
    product_root = (root / "product").resolve()
    if not product_root.is_dir() or product_root.parent != root:
        raise FileNotFoundError("repository product root is missing")
    records = {
        name: _record(product_root, name, relative_path)
        for name, relative_path in RESOURCE_PATHS.items()
    }
    version_manifest = load_version_manifest(product_root / "version-manifest.json")
    decision_contract = load_decision_contract(product_root)
    if decision_contract["schema_version"] != version_manifest["decision_contract"]:
        raise ValueError("decision contract version differs from candidate manifest")
    verify_cio_schema(product_root, decision_contract)
    actual_hashes = {name: record.sha256 for name, record in records.items()}
    if actual_hashes != version_manifest["resource_hashes"]:
        mismatches = sorted(
            name
            for name in actual_hashes
            if actual_hashes[name] != version_manifest["resource_hashes"].get(name)
        )
        raise ValueError(f"product resource hash mismatch: {','.join(mismatches)}")
    if source_profile != "fixture":
        from copy import deepcopy
        from .runtime_profiles import load_source_profile
        from .versioning import validate_version_manifest
        profile = load_source_profile(root, source_profile)
        records["runtime_profile"] = _record(product_root, "runtime_profile", "profiles/live-us-equity.json")
        # 仅派生本次运行锁，不覆盖 fixture manifest、历史包或生产版本指针。
        version_manifest = deepcopy(version_manifest)
        version_manifest["candidate_version"] += "+live-us-equity"
        version_manifest["runtime_profile"] = profile["profile_id"]
        version_manifest["data_snapshot"] = "live-snapshot/4.0.0"
        version_manifest["resource_hashes"]["runtime_profile"] = records["runtime_profile"].sha256
        version_manifest["mcp_adapters"]["live-gate-scoped"] = profile["mcp_adapter_version"]
        from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION, CALENDAR_VERSION
        from product.mcp.live.sec import ADAPTER_VERSION
        from product.mcp.live.sec_client import CLIENT_VERSION
        from product.mcp.live.security_metadata import METADATA_VERSION
        from product.mcp.live.yahoo_transport import TRANSPORT_VERSION
        from product.mcp.live.collection import COLLECTION_VERSION
        from product.mcp.live.disclosure import PARSER_VERSION
        from product.mcp.live.nasdaq import ADAPTER_VERSION as NASDAQ_ADAPTER, CLIENT_VERSION as NASDAQ_CLIENT
        from product.mcp.live.nasdaq import TRANSPORT_VERSION as NASDAQ_TRANSPORT, CERTIFI_VERSION
        from product.mcp.live.sec_client import TRANSPORT_VERSION as SEC_TRANSPORT
        from product.mcp.live.eastmoney_transport import HTTPS_VERSION as EASTMONEY_HTTPS
        from product.mcp.live.tls import TRUST_VERSION
        from product.mcp.live.eastmoney_transport import ADAPTER_VERSION as EASTMONEY_ADAPTER, AKSHARE_VERSION
        from product.mcp.live.security_metadata import EASTMONEY_METADATA_VERSION
        from product.mcp.live.source_routing import policy_lock
        version_manifest["data_adapters"] = {
            "yahoo": MARKET_VERSION, "yfinance": YFINANCE_VERSION, "calendar": CALENDAR_VERSION,
            "sec_parser": ADAPTER_VERSION, "sec_client": CLIENT_VERSION,
            "security_metadata": METADATA_VERSION, "yahoo_transport": TRANSPORT_VERSION,
            "collection": COLLECTION_VERSION, "sec_disclosure": PARSER_VERSION,
            "nasdaq": NASDAQ_ADAPTER, "nasdaq_client": NASDAQ_CLIENT,
            "nasdaq_transport": NASDAQ_TRANSPORT, "certifi": CERTIFI_VERSION,
            "sec_transport": SEC_TRANSPORT, "eastmoney_https": EASTMONEY_HTTPS, "https_trust": TRUST_VERSION,
            "eastmoney": EASTMONEY_ADAPTER, "akshare": AKSHARE_VERSION,
            "eastmoney_identity": EASTMONEY_METADATA_VERSION,
            "routing": policy_lock()["version"], "routing_hash": policy_lock()["hash"],
        }
        for kind, relative in profile["schema_files"].items():
            schema = json.loads((product_root / relative).read_text(encoding="utf-8"))
            version_manifest["schemas"][f"live-{kind}"] = schema["properties"]["schema_version"]["const"]
        validate_version_manifest(version_manifest)
    digest_payload = {
        "product_root": str(product_root),
        "resources": {name: asdict(record) for name, record in sorted(records.items())},
        "version_manifest": version_manifest,
    }
    return ProductDiscovery(
        product_root=str(product_root),
        plugin=records["plugin"],
        plugin_mcp=records["plugin_mcp"],
        runtime_config=records["runtime_config"],
        runtime_profile=records["runtime_profile"],
        decision_contract=records["decision_contract"],
        council_skill=records["council_skill"],
        cio_agent=records["cio_agent"],
        company_agent=records["company_agent"],
        skeptic_agent=records["skeptic_agent"],
        version_manifest=version_manifest,
        discovery_hash=canonical_hash(digest_payload),
    )
