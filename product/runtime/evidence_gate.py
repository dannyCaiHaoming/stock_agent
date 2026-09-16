"""Deterministic point-in-time gate for versioned fixture evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.mcp.provenance import canonical_json, content_hash, parse_timestamp


GATE_SCHEMA_VERSION = "evidence-gate/2.0.0"
REQUIRED_FACT_FIELDS = (
    "evidence_id",
    "security_id",
    "semantic_field",
    "value",
    "unit",
    "source_id",
    "source_type",
    "source_locator",
    "source_version",
    "as_of",
    "retrieved_at",
)


class FixtureValidationError(ValueError):
    """The fixture cannot safely enter the product runtime."""


@dataclass(frozen=True, slots=True)
class GateResult:
    artifact: dict[str, Any]

    @property
    def allowed_ids(self) -> tuple[str, ...]:
        return tuple(self.artifact["allowed_evidence_ids"])

    @property
    def excluded_ids(self) -> tuple[str, ...]:
        return tuple(item["evidence_id"] for item in self.artifact["excluded"])


def load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise FixtureValidationError("fixture must be a JSON object")
    fixture = dict(value)
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    required = {
        "fixture_version",
        "fixture_id",
        "scenario_type",
        "decision_cutoff",
        "freshness_policy",
        "conflict_policy_version",
        "portfolio",
        "evidence",
    }
    missing = sorted(required - fixture.keys())
    if missing:
        raise FixtureValidationError(f"fixture missing fields: {','.join(missing)}")
    parse_timestamp(str(fixture["decision_cutoff"]))

    portfolio = fixture["portfolio"]
    if not isinstance(portfolio, Mapping):
        raise FixtureValidationError("portfolio must be an object")
    if not isinstance(portfolio.get("cash"), (int, float)) or portfolio["cash"] < 0:
        raise FixtureValidationError("portfolio cash must be non-negative")
    positions = portfolio.get("positions")
    if not isinstance(positions, list) or not positions:
        raise FixtureValidationError("portfolio positions must be non-empty")
    for position in positions:
        if not isinstance(position, Mapping):
            raise FixtureValidationError("portfolio position must be an object")
        if not position.get("security_id"):
            raise FixtureValidationError("portfolio position requires security_id")
        if not isinstance(position.get("quantity"), (int, float)) or position["quantity"] <= 0:
            raise FixtureValidationError("portfolio position quantity must be positive")

    policy = fixture["freshness_policy"]
    if not isinstance(policy, Mapping) or not policy.get("version"):
        raise FixtureValidationError("freshness_policy requires version")
    default_days = policy.get("default_max_age_days")
    if not isinstance(default_days, int) or default_days < 0:
        raise FixtureValidationError("default_max_age_days must be non-negative integer")
    field_days = policy.get("field_max_age_days", {})
    if not isinstance(field_days, Mapping) or any(
        not isinstance(value, int) or value < 0 for value in field_days.values()
    ):
        raise FixtureValidationError("field_max_age_days values must be non-negative integers")

    evidence = fixture["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise FixtureValidationError("fixture evidence must be non-empty")
    identifiers: set[str] = set()
    for index, fact in enumerate(evidence):
        if not isinstance(fact, Mapping):
            raise FixtureValidationError(f"evidence[{index}] must be an object")
        absent = [field for field in REQUIRED_FACT_FIELDS if fact.get(field) is None]
        if absent:
            raise FixtureValidationError(
                f"evidence[{index}] missing provenance: {','.join(absent)}"
            )
        evidence_id = str(fact["evidence_id"])
        if evidence_id in identifiers:
            raise FixtureValidationError(f"duplicate evidence_id: {evidence_id}")
        identifiers.add(evidence_id)
        as_of = parse_timestamp(str(fact["as_of"]))
        retrieved_at = parse_timestamp(str(fact["retrieved_at"]))
        if retrieved_at < as_of:
            raise FixtureValidationError(
                f"retrieved_at precedes as_of for {evidence_id}"
            )


def _conflict_key(fact: Mapping[str, Any]) -> str:
    components = (
        str(fact["security_id"]).strip().casefold(),
        str(fact["semantic_field"]).strip().casefold(),
        parse_timestamp(str(fact["as_of"])).isoformat(),
    )
    return "|".join(components)


def _fact_signature(fact: Mapping[str, Any]) -> str:
    return canonical_json(
        {
            "value": fact["value"],
            "unit": fact["unit"],
            "currency": fact.get("currency"),
        }
    )


def _detect_conflicts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(_conflict_key(fact), []).append(fact)
    conflicts: list[dict[str, Any]] = []
    for key, candidates in sorted(grouped.items()):
        if len({_fact_signature(fact) for fact in candidates}) <= 1:
            continue
        conflicts.append(
            {
                "conflict_key": key,
                "reason_code": "INCOMPATIBLE_NORMALIZED_VALUES",
                "evidence_ids": sorted(str(fact["evidence_id"]) for fact in candidates),
                "source_ids": sorted(str(fact["source_id"]) for fact in candidates),
                "observations": sorted(
                    (
                        {
                            "evidence_id": str(fact["evidence_id"]),
                            "source_id": str(fact["source_id"]),
                            "value": fact["value"],
                            "unit": fact["unit"],
                            "currency": fact.get("currency"),
                        }
                        for fact in candidates
                    ),
                    key=lambda item: item["evidence_id"],
                ),
            }
        )
    return conflicts


def run_evidence_gate(fixture: Mapping[str, Any], *, run_id: str) -> GateResult:
    validate_fixture(fixture)
    cutoff = parse_timestamp(str(fixture["decision_cutoff"]))
    policy = fixture["freshness_policy"]
    default_days = int(policy["default_max_age_days"])
    field_days = policy.get("field_max_age_days", {})

    allowed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw_fact in fixture["evidence"]:
        fact = dict(raw_fact)
        reasons: list[str] = []
        as_of = parse_timestamp(str(fact["as_of"]))
        retrieved_at = parse_timestamp(str(fact["retrieved_at"]))
        if as_of > cutoff:
            reasons.append("FUTURE_AS_OF")
        if retrieved_at > cutoff:
            reasons.append("FUTURE_RETRIEVAL")
        threshold_days = int(field_days.get(str(fact["semantic_field"]), default_days))
        age = cutoff - as_of
        if age >= timedelta(0) and age > timedelta(days=threshold_days):
            reasons.append("STALE")
        if reasons:
            excluded.append(
                {
                    "evidence_id": fact["evidence_id"],
                    "reason_codes": reasons,
                    "as_of": fact["as_of"],
                    "retrieved_at": fact["retrieved_at"],
                    "threshold_days": threshold_days,
                }
            )
        else:
            fact["freshness_status"] = "FRESH"
            fact["freshness_policy_version"] = policy["version"]
            allowed.append(fact)

    allowed.sort(key=lambda item: str(item["evidence_id"]))
    excluded.sort(key=lambda item: str(item["evidence_id"]))
    input_ids = sorted(str(item["evidence_id"]) for item in fixture["evidence"])
    body: dict[str, Any] = {
        "schema_version": GATE_SCHEMA_VERSION,
        "run_id": run_id,
        "fixture_id": fixture["fixture_id"],
        "decision_cutoff": fixture["decision_cutoff"],
        "freshness_policy_version": policy["version"],
        "conflict_policy_version": fixture["conflict_policy_version"],
        "input_evidence_ids": input_ids,
        "allowed_evidence_ids": [item["evidence_id"] for item in allowed],
        "excluded_evidence_ids": [item["evidence_id"] for item in excluded],
        "excluded": excluded,
        "conflicts": _detect_conflicts(allowed),
        "allowed_evidence": allowed,
        "input_hash": content_hash(fixture),
    }
    body["bundle_hash"] = content_hash(body)
    return GateResult(body)


def run_live_evidence_gate(snapshot: Mapping[str, Any], *, run_id: str, calendar=None) -> GateResult:
    """显式 live Gate；不伪造 fixture 字段，不改变旧 fixture 规则。

    calendar 由采集适配提供版本化交易日历，completed_sessions(cutoff) 返回
    已结束时段的 UTC close 列表。没有日历时行情 fail-closed，不猜周末/假日。
    """
    from product.mcp.live.contracts import validate_contract

    validate_contract("snapshot", dict(snapshot))
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("LIVE_RUN_ID_REQUIRED")
    cutoff = parse_timestamp(snapshot["decision_cutoff"])
    facts = {f["evidence_id"]: dict(f) for f in snapshot["facts"]}
    from product.mcp.live.contracts import source_is_admitted
    authorized = {a["provider"] for a in snapshot["source_access"]
                  if source_is_admitted(a, at=snapshot["request_started_at"])}
    rejected, allowed = {}, {}
    sessions = None
    if calendar is not None:
        if not calendar.version or not calendar.content_hash:
            raise ValueError("LIVE_CALENDAR_VERSION_REQUIRED")
        sessions = sorted(parse_timestamp(t) for t in calendar.completed_sessions(cutoff))
        if len(sessions) < 2 or len(set(sessions)) != len(sessions) or sessions[-1] > cutoff:
            raise ValueError("LIVE_CALENDAR_SESSIONS_INVALID")
    pending = dict(facts)
    while pending:
        advanced = False
        for identifier, fact in list(pending.items()):
            parents = fact["parent_ids"]
            if any(parent not in facts for parent in parents):
                raise ValueError("LIVE_EVIDENCE_CLOSURE_FAILED")
            if any(parent in pending for parent in parents):
                continue
            reasons = []
            times = {field: parse_timestamp(fact[field]) for field in ("as_of", "published_at", "retrieved_at")}
            for field, code in (("as_of", "FUTURE_AS_OF"), ("published_at", "FUTURE_PUBLICATION"),
                                ("retrieved_at", "FUTURE_RETRIEVAL")):
                if times[field] > cutoff:
                    reasons.append(code)
            if times["as_of"] > times["retrieved_at"] or times["published_at"] > times["retrieved_at"]:
                reasons.append("INVALID_FACT_TIME_ORDER")
            if fact["source_type"] != "derived" and fact["source_type"] not in authorized:
                reasons.append("SOURCE_NOT_AUTHORIZED")
            if parents:
                if fact["parent_hashes"] != [content_hash(facts[p]) for p in parents]:
                    raise ValueError("LIVE_PARENT_HASH_MISMATCH")
                if any(p in rejected for p in parents):
                    reasons.append("PARENT_EXCLUDED")
                for field in times:
                    if times[field] < max(parse_timestamp(facts[p][field]) for p in parents):
                        reasons.append("DERIVED_TIME_PRECEDES_PARENT")
            elif fact["kind"] == "price":
                if sessions is None:
                    reasons.append("PRICE_CALENDAR_REQUIRED")
                elif times["as_of"] not in sessions[-2:]:
                    reasons.append("PRICE_NOT_RECENT_COMPLETED_SESSION")
                if calendar is not None and (
                    fact["metadata"].get("calendar_version") != calendar.version
                    or fact["metadata"].get("calendar_hash") != calendar.content_hash
                ):
                    reasons.append("PRICE_CALENDAR_LOCK_MISMATCH")
                if fact["semantic_field"] != "close_price" or fact["metadata"].get("price_basis") != "provider_close":
                    reasons.append("PRICE_BASIS_INVALID")
            else:
                form = fact["metadata"].get("form", "")
                threshold = 800 if fact["usage"] == "comparison" else (
                    450 if form in ("10-K", "10-K/A")
                    else 200 if form in ("10-Q", "10-Q/A")
                    else 90 if form in ("8-K", "8-K/A")
                    else 90 if fact["kind"] == "ownership" and form in (
                        "3", "3/A", "4", "4/A", "5", "5/A"
                    )
                    else None
                )
                if threshold is None:
                    reasons.append("FRESHNESS_CONTEXT_UNKNOWN")
                elif cutoff - times["as_of"] > timedelta(days=threshold):
                    reasons.append("STALE")
                if fact["kind"] == "financial" and fact["metadata"].get("period_end") != times["as_of"].date().isoformat():
                    reasons.append("FINANCIAL_PERIOD_AS_OF_MISMATCH")
            if reasons:
                rejected[identifier] = {"evidence_id": identifier, "reason_codes": sorted(set(reasons)),
                                        **{field: fact[field] for field in times}}
            else:
                allowed[identifier] = dict(fact, freshness_status="FRESH",
                                           freshness_policy_version=snapshot["freshness_policy_version"])
            del pending[identifier]
            advanced = True
        if not advanced:
            raise ValueError("LIVE_PARENT_CYCLE")
    groups = {}
    for fact in allowed.values():
        meta = fact["metadata"]
        key = content_hash([fact["security_id"], fact["semantic_field"], fact["as_of"], fact["unit"], fact["currency"],
                            *[meta.get(k) for k in ("period_start", "period_end", "context_type")]])
        groups.setdefault(key, []).append(fact)
    conflicts = [{"conflict_key": key, "evidence_ids": sorted(f["evidence_id"] for f in group),
                  "reason_code": "INCOMPATIBLE_NORMALIZED_VALUES"}
                 for key, group in sorted(groups.items()) if len({content_hash(f["value"]) for f in group}) > 1]
    body = {"schema_version": "live-evidence-gate/1.0.0", "source_mode": "live", "run_id": run_id,
            "snapshot_id": snapshot["snapshot_id"], "decision_cutoff": snapshot["decision_cutoff"],
            "freshness_policy_version": snapshot["freshness_policy_version"],
            "conflict_policy_version": "live-context-conflict/1.0.0",
            "input_hash": content_hash(snapshot), "input_evidence_ids": sorted(facts),
            "allowed_evidence_ids": sorted(allowed), "excluded_evidence_ids": sorted(rejected),
            "allowed_evidence": [allowed[k] for k in sorted(allowed)],
            "excluded": [rejected[k] for k in sorted(rejected)], "conflicts": conflicts,
            "calendar_lock": {"version": calendar.version, "hash": calendar.content_hash} if calendar else None}
    body["bundle_hash"] = content_hash(body)
    return GateResult(body)
