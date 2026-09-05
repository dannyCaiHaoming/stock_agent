from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from product.evidence_store.closure import Claim, validate_claim_evidence_closure
from product.evidence_store.quality import (
    FreshnessPolicy,
    assess_freshness,
    detect_conflicts,
    detect_missing_fields,
)
from product.evidence_store.store import AppendOnlyEvidenceStore
from product.mcp.contracts import (
    AccessMode,
    TOOL_CONTRACTS,
    ToolContract,
    discover_runtime_tools,
    validate_read_only_registry,
)
from product.mcp.provenance import normalize_fact
from product.mcp.reference_adapter import ReferenceAdapter


class ToolContractTests(unittest.TestCase):
    def test_runtime_registry_contains_all_provider_neutral_read_capabilities(self) -> None:
        tools = discover_runtime_tools()
        self.assertEqual(
            {tool["capability"] for tool in tools},
            {
                "security-master",
                "market-data",
                "fundamentals",
                "filings-news",
                "evidence-query",
                "deterministic-valuation",
                "deterministic-liquidity",
            },
        )
        self.assertTrue(all(tool["access_mode"] == AccessMode.READ for tool in tools))

    def test_no_broker_order_or_account_write_tools_are_discoverable(self) -> None:
        serialized = json.dumps(discover_runtime_tools()).casefold()
        for forbidden in (
            "broker",
            "place_order",
            "submit_order",
            "cancel_order",
            "account.write",
            "account.update",
            "execution",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(all(tool.access_mode is AccessMode.READ for tool in TOOL_CONTRACTS))

    def test_registry_rejects_a_read_contract_with_execution_semantics(self) -> None:
        unsafe = ToolContract(
            name="broker.place_order",
            capability="unsafe",
            access_mode=AccessMode.READ,
            input_fields=("symbol",),
            output_type="unsafe",
            description="unsafe fixture",
        )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_read_only_registry((unsafe,))

        disguised = ToolContract(
            name="portfolio.utility",
            capability="utility",
            access_mode=AccessMode.READ,
            input_fields=("payload",),
            output_type="Result",
            description="submit_order through a hidden provider",
        )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_read_only_registry((disguised,))


class ProvenanceAndFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ReferenceAdapter()

    def test_fixture_adapter_is_stable_and_covers_required_scenarios(self) -> None:
        self.assertEqual(
            set(self.adapter.scenarios),
            {"normal", "stale", "missing", "conflict", "revision"},
        )
        for scenario in self.adapter.scenarios:
            first = self.adapter.evidence_artifact(scenario)
            second = self.adapter.evidence_artifact(scenario)
            self.assertEqual(first, second)
            self.assertEqual(first["artifact_id"], second["artifact_id"])
        self.assertEqual(
            self.adapter.evidence_artifact("missing")["missing_fields"],
            ["revenue_ttm"],
        )
        revisions = self.adapter.facts("revision")
        self.assertEqual(len(revisions), 2)
        self.assertNotEqual(revisions[0].fact_id, revisions[1].fact_id)
        self.assertNotEqual(revisions[0].content_hash, revisions[1].content_hash)

    def test_normalization_preserves_source_unit_timezone_currency_and_hash(self) -> None:
        raw = {
            "security_id": "SEC-X",
            "semantic_field": "close_price",
            "value": "42.50",
            "value_type": "number",
            "unit": "per_share",
            "currency": "USD",
            "source_timezone": "America/New_York",
            "source_id": "source-x",
            "source_type": "market-data",
            "source_locator": "fixture://source-x/close",
            "source_version": "v3",
            "as_of": "2026-01-02T16:00:00-05:00",
            "retrieved_at": "2026-01-02T21:05:00Z",
        }
        fact = normalize_fact(raw, adapter_version="test/3")
        self.assertEqual(fact.source_id, raw["source_id"])
        self.assertEqual(fact.source_locator, raw["source_locator"])
        self.assertEqual(fact.source_version, raw["source_version"])
        self.assertEqual(fact.unit, raw["unit"])
        self.assertEqual(fact.currency, raw["currency"])
        self.assertEqual(fact.source_timezone, raw["source_timezone"])
        self.assertEqual(fact.value, "42.50")
        self.assertEqual(len(fact.content_hash), 64)

    def test_missing_required_provenance_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_id"):
            normalize_fact(
                {
                    "security_id": "SEC-X",
                    "semantic_field": "close_price",
                    "value": 1,
                    "source_type": "fixture",
                    "source_locator": "fixture://x",
                    "as_of": "2026-01-01T00:00:00Z",
                    "retrieved_at": "2026-01-01T01:00:00Z",
                }
            )


class EvidenceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ReferenceAdapter()

    def test_store_is_append_only_and_queries_bitemporal_cutoffs(self) -> None:
        original, revised = self.adapter.facts("revision")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            store = AppendOnlyEvidenceStore(path)
            self.assertTrue(store.append(original))
            self.assertTrue(store.append(revised))
            self.assertFalse(store.append(original))
            self.assertEqual(len(store), 2)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

            historical = store.query(
                semantic_field="revenue_ttm",
                as_of_lte="2025-12-31T23:59:59Z",
                retrieved_at_lte="2026-01-31T23:59:59Z",
            )
            self.assertEqual([fact.fact_id for fact in historical], [original.fact_id])
            later = store.query(
                semantic_field="revenue_ttm",
                as_of_lte="2025-12-31T23:59:59Z",
                retrieved_at_lte="2026-02-02T00:00:00Z",
            )
            self.assertEqual({fact.fact_id for fact in later}, {original.fact_id, revised.fact_id})
            self.assertEqual(
                store.query(as_of_lte="2025-01-01T00:00:00Z"),
                (),
            )

            reloaded = AppendOnlyEvidenceStore(path)
            self.assertEqual(len(reloaded), 2)
            self.assertEqual(reloaded.snapshot_hash(), store.snapshot_hash())

    def test_freshness_missing_and_conflict_layers_only_emit_flags(self) -> None:
        stale_fact = self.adapter.facts("stale")[0]
        assessment = assess_freshness(
            stale_fact,
            decision_time="2026-01-03T00:00:00Z",
            policy=FreshnessPolicy(
                version="freshness/1",
                default_max_age=timedelta(days=30),
                field_max_age={"close_price": timedelta(days=2)},
            ),
        )
        self.assertEqual(assessment.status, "STALE")
        self.assertEqual(assessment.policy_version, "freshness/1")

        missing = self.adapter.facts("missing")
        self.assertEqual(
            detect_missing_fields(missing, ("close_price", "revenue_ttm")),
            ("revenue_ttm",),
        )
        conflicts = detect_conflicts(self.adapter.facts("conflict"))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].reason_code, "MATERIAL_VALUE_CONFLICT")
        self.assertFalse(hasattr(conflicts[0], "investment_impact"))
        self.assertFalse(hasattr(conflicts[0], "preferred_source"))

    def test_claim_evidence_closure_gates_unsupported_material_claims(self) -> None:
        fact = self.adapter.facts("normal")[0]
        valid = validate_claim_evidence_closure(
            [Claim("claim-1", "Price was observed", (fact.fact_id,))],
            [fact],
        )
        self.assertTrue(valid.eligible_for_cio)
        self.assertEqual(valid.resolved_source_ids, (fact.source_id,))

        unsupported = validate_claim_evidence_closure(
            [Claim("claim-2", "Unsupported conclusion")],
            [fact],
        )
        self.assertFalse(unsupported.eligible_for_cio)
        self.assertEqual(unsupported.unsupported_claim_ids, ("claim-2",))

        assumption = validate_claim_evidence_closure(
            [
                Claim(
                    "claim-3",
                    "Scenario assumption",
                    is_assumption=True,
                    assumption_rationale="Used only for sensitivity analysis",
                )
            ],
            [fact],
        )
        self.assertTrue(assumption.eligible_for_cio)

        unknown = validate_claim_evidence_closure(
            [Claim("claim-4", "Bad reference", ("fact-does-not-exist",))],
            [fact],
        )
        self.assertFalse(unknown.eligible_for_cio)
        self.assertEqual(unknown.unknown_fact_refs, ("fact-does-not-exist",))


if __name__ == "__main__":
    unittest.main()
