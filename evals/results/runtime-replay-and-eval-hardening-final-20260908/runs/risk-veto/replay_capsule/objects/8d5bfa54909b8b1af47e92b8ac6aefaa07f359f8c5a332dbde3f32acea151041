"""MCP-facing contracts.

The contracts deliberately describe capabilities rather than a data vendor.  They
contain no credentials, transport details, account mutation, or execution tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final


class AccessMode(StrEnum):
    READ = "read"


@dataclass(frozen=True, slots=True)
class ToolContract:
    name: str
    capability: str
    access_mode: AccessMode
    input_fields: tuple[str, ...]
    output_type: str
    description: str
    version: str = "1.0.0"


TOOL_CONTRACTS: Final[tuple[ToolContract, ...]] = (
    ToolContract(
        name="security_master.resolve",
        capability="security-master",
        access_mode=AccessMode.READ,
        input_fields=("identifier", "as_of"),
        output_type="SecurityResolution",
        description="Resolve a market identifier without guessing ambiguous matches.",
    ),
    ToolContract(
        name="market_data.query",
        capability="market-data",
        access_mode=AccessMode.READ,
        input_fields=("security_id", "fields", "as_of", "retrieved_at_cutoff"),
        output_type="EvidenceArtifact",
        description="Query point-in-time prices, volume, and liquidity observations.",
    ),
    ToolContract(
        name="fundamentals.query",
        capability="fundamentals",
        access_mode=AccessMode.READ,
        input_fields=("security_id", "fields", "as_of", "retrieved_at_cutoff"),
        output_type="EvidenceArtifact",
        description="Query point-in-time fundamental facts and their revisions.",
    ),
    ToolContract(
        name="filings_news.query",
        capability="filings-news",
        access_mode=AccessMode.READ,
        input_fields=("security_id", "start_at", "end_at", "retrieved_at_cutoff"),
        output_type="EvidenceArtifact",
        description="Query filings, disclosures, and news evidence.",
    ),
    ToolContract(
        name="evidence.query",
        capability="evidence-query",
        access_mode=AccessMode.READ,
        input_fields=("security_id", "semantic_field", "as_of", "retrieved_at_cutoff"),
        output_type="EvidenceArtifact",
        description="Read normalized evidence using bitemporal boundaries.",
    ),
    ToolContract(
        name="valuation.calculate",
        capability="deterministic-valuation",
        access_mode=AccessMode.READ,
        input_fields=("method", "facts", "assumptions", "as_of"),
        output_type="CalculationArtifact",
        description="Calculate a declared valuation method without selecting a security or action.",
    ),
    ToolContract(
        name="liquidity.calculate",
        capability="deterministic-liquidity",
        access_mode=AccessMode.READ,
        input_fields=("market_facts", "position", "as_of"),
        output_type="CalculationArtifact",
        description="Calculate liquidity and participation metrics from supplied facts.",
    ),
)


_FORBIDDEN_TOOL_TERMS: Final[tuple[str, ...]] = (
    "broker",
    "place_order",
    "submit_order",
    "cancel_order",
    "account.write",
    "account.update",
    "execution",
)


def validate_read_only_registry(
    contracts: tuple[ToolContract, ...] = TOOL_CONTRACTS,
) -> None:
    """Reject any runtime registry that exposes mutation or execution semantics."""

    names: set[str] = set()
    for contract in contracts:
        if contract.access_mode is not AccessMode.READ:
            raise ValueError(f"runtime tool is not read-only: {contract.name}")
        searchable_metadata = " ".join(
            (
                contract.name,
                contract.capability,
                contract.output_type,
                contract.description,
                *contract.input_fields,
            )
        ).casefold()
        if any(term in searchable_metadata for term in _FORBIDDEN_TOOL_TERMS):
            raise ValueError(f"forbidden runtime capability: {contract.name}")
        if contract.name in names:
            raise ValueError(f"duplicate runtime tool: {contract.name}")
        names.add(contract.name)


def discover_runtime_tools() -> tuple[dict[str, object], ...]:
    """Return the safe tool manifest presented to runtime agents."""

    validate_read_only_registry()
    return tuple(asdict(contract) for contract in TOOL_CONTRACTS)
