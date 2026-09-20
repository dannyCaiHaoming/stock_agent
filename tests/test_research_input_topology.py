from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.research_input_topology import (
    ResearchInputTopologyError,
    build_research_provider_coverage,
    discover_research_input_profiles,
    load_research_input_topology,
    research_input_topology_lock,
)
from product.mcp.live.research_supplement import build_capability, build_capture_batch
from product.runtime.runtime_profiles import load_source_profile
from product.runtime.multidimensional_stage import (
    MultidimensionalStageError,
    _load_research_capture_batches,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "product/profiles/holding-research-inputs.json"


def _rehash(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["topology_hash"] = canonical_hash(
        {key: item for key, item in result.items() if key != "topology_hash"}
    )
    return result


class ResearchInputTopologyTests(unittest.TestCase):
    def test_current_topology_maps_three_domains_and_provider_planes(self) -> None:
        topology = load_research_input_topology(ROOT)
        self.assertEqual(topology["lifecycle_status"], "CURRENT")
        self.assertEqual(
            {item["domain"] for item in topology["domains"]},
            {"COMPANY", "MACRO", "MARKET"},
        )
        capabilities = {
            capability["capability"]
            for domain in topology["domains"]
            for capability in domain["capabilities"]
        }
        self.assertEqual(
            capabilities,
            {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "MACRO_CONTEXT", "MARKET_STATE"},
        )
        supplement = next(
            item for item in topology["provider_planes"]
            if item["plane"] == "RESEARCH_SUPPLEMENT"
        )
        moomoo = next(item for item in supplement["providers"] if item["provider"] == "moomoo_sg")
        self.assertEqual(moomoo["region"], "SG")
        self.assertEqual(moomoo["access"], "loopback_opend_quote_only")
        self.assertTrue(any("Cookie" in item for item in moomoo["limitations"]))

    def test_lock_carries_topology_and_source_hashes(self) -> None:
        lock = research_input_topology_lock(ROOT)
        self.assertEqual(lock["domains"]["MACRO"], ["MACRO_CONTEXT"])
        self.assertEqual(lock["domains"]["MARKET"], ["MARKET_STATE"])
        self.assertEqual(lock["lock_hash"], canonical_hash({
            key: item for key, item in lock.items() if key != "lock_hash"
        }))
        for reference in lock["source_references"]:
            self.assertEqual(file_hash(ROOT / reference["path"]), reference["sha256"])
        self.assertEqual(
            lock["default_output_contract"]["schema_version"],
            "research-dimension-report/2.0.0",
        )
        self.assertEqual(
            file_hash(ROOT / lock["default_output_contract"]["path"]),
            lock["default_output_contract"]["sha256"],
        )
        self.assertEqual(
            set(lock["output_contracts"]),
            {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "MACRO_CONTEXT", "MARKET_STATE"},
        )

    def test_unknown_binding_and_reference_drift_fail_closed(self) -> None:
        original = json.loads(PROFILE.read_text(encoding="utf-8"))
        variants = []
        unknown_agent = copy.deepcopy(original)
        unknown_agent["domains"][0]["capabilities"][0]["agent"] = "runtime_unknown"
        variants.append((_rehash(unknown_agent), "SCHEMA_INVALID"))
        drift = copy.deepcopy(original)
        drift["source_references"][0]["sha256"] = "0" * 64
        variants.append((_rehash(drift), "REFERENCE_HASH_MISMATCH"))
        missing = copy.deepcopy(original)
        missing["source_references"][0]["path"] = "mcp/live/missing-source-policy.json"
        variants.append((_rehash(missing), "RESOURCE_MISSING"))
        with tempfile.TemporaryDirectory() as temp:
            for index, (value, code) in enumerate(variants):
                path = Path(temp) / f"topology-{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(code=code), self.assertRaisesRegex(
                    ResearchInputTopologyError, code
                ):
                    load_research_input_topology(ROOT, topology_path=path)

    def test_retired_live_profile_remains_hash_stable_and_readable(self) -> None:
        before = file_hash(ROOT / "product/profiles/live-us-equity.json")
        discovered = discover_research_input_profiles(ROOT)
        self.assertEqual(discovered["current"]["lifecycle_status"], "CURRENT")
        retired = discovered["compatibility_only"][0]
        self.assertEqual(retired["lifecycle_status"], "RETIRED")
        self.assertEqual(retired["compatibility_mode"], "COMPATIBILITY_ONLY")
        self.assertEqual(retired["sha256"], before)
        self.assertEqual(load_source_profile(ROOT, "live-us-equity")["profile_id"], retired["profile_id"])
        self.assertEqual(file_hash(ROOT / "product/profiles/live-us-equity.json"), before)

    def test_current_product_docs_describe_split_and_evidence_based_status(self) -> None:
        product_doc = (ROOT / "docs/product/multi-dimensional-holding-research.md").read_text(
            encoding="utf-8"
        )
        browser_doc = (ROOT / "docs/product/local-research-browser.md").read_text(
            encoding="utf-8"
        )
        capability_doc = (ROOT / "docs/data/free-source-capability-matrix.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("ResearchDimensionReport/2.0.0", product_doc)
        self.assertIn("HoldingResearchBundle/2.0.0", product_doc)
        self.assertIn("MACRO_CONTEXT", product_doc)
        self.assertIn("MARKET_STATE", product_doc)
        self.assertIn("RETIRED/COMPATIBILITY_ONLY", product_doc)
        self.assertNotIn("延期至 `capture-futu-client-research-data`", product_doc)
        self.assertIn("LEGACY_COMBINED_COVERAGE", browser_doc)
        self.assertIn("research-dimension-report/2.0.0", browser_doc)
        self.assertIn("loopback OpenD quote-only", capability_doc)
        self.assertIn("不得回退客户端 Cookie", capability_doc)

    def test_dataset_inventory_freezes_core_scope_before_new_collectors(self) -> None:
        inventory = (
            ROOT / "reviews/development/align-macro-market-company-dataset-inventory.md"
        ).read_text(encoding="utf-8")
        for domain in ("## Macro", "## Market", "## Company"):
            self.assertIn(domain, inventory)
        for required in (
            "经济活动",
            "央行政策原文",
            "已公布发布日历",
            "大盘与相关板块基准",
            "跨资产代表序列",
            "信用指标或明确代理",
            "过去 24 小时市场新闻",
            "公司公告/IR 正文自动发现",
            "公司/行业独立研究自动发现",
            "独立研究正文",
        ):
            self.assertIn(required, inventory)
        self.assertIn("字段与时间语义", inventory)
        self.assertIn("主/备来源与预算", inventory)
        self.assertIn("正式消费位置", inventory)
        self.assertIn("不得回退 Cookie", inventory)
        self.assertIn("| 独立研究正文 | ENHANCEMENT |", inventory)

    def test_third_party_skill_audit_does_not_claim_unverified_coverage(self) -> None:
        audit = (
            ROOT / "reviews/development/workbuddyskills-finance-portability-audit.md"
        ).read_text(encoding="utf-8")
        self.assertIn("78170571d08e7d38c6baf0a13ef805487bfa6dc2", audit)
        self.assertIn("wb-finance-skill", audit)
        self.assertIn("westock-data-clawhub@1.0.4", audit)
        self.assertIn("neodata-financial-search/1.0.1", audit)
        self.assertIn("`NOT_VERIFIED`", audit)
        self.assertIn("`REJECTED`", audit)
        self.assertIn("执行 `npx`", audit)
        self.assertIn("不新增第三方 Skill 到 Agent allowlist", audit)

    def test_provider_coverage_isolates_moomoo_failure_from_base_sources(self) -> None:
        checked_at = "2026-09-11T12:05:00Z"
        capabilities = [
            build_capability(
                source="sec", region="US", security_id="US:COMMON_STOCK:AAPL",
                dataset="identity_profile", status="AVAILABLE", fields=["issuer_name"],
                endpoint_version="sec-submissions/1", checked_at=checked_at,
                as_of="2026-09-11T12:00:00Z", attempt_count=1, limitations=[],
                evidence_ids=["ev-sec-identity"], raw_content_hashes=["a" * 64],
            ),
            build_capability(
                source="yahoo", region="US", security_id="US:COMMON_STOCK:AAPL",
                dataset="identity_profile", status="AVAILABLE", fields=["sector"],
                endpoint_version="yahoo-profile/1", checked_at=checked_at,
                as_of="2026-09-11T12:00:00Z", attempt_count=1,
                limitations=["免费非官方补充源。"],
                evidence_ids=["ev-yahoo-profile"], raw_content_hashes=["b" * 64],
            ),
            build_capability(
                source="moomoo_sg", region="SG", security_id="US:COMMON_STOCK:AAPL",
                dataset="identity_profile", status="SOURCE_LIMITED", fields=[],
                endpoint_version="opend/quote-only", checked_at=checked_at,
                as_of="2026-09-11T12:00:00Z", attempt_count=1,
                limitations=["OpenD 当前不可达，仅隔离该补充层。"],
                failure_code="MOOMOO_OPEND_UNREACHABLE",
            ),
        ]
        batch = build_capture_batch(
            batch_id="batch-provider-degradation",
            security_id="US:COMMON_STOCK:AAPL",
            decision_cutoff="2026-09-11T12:00:00Z",
            created_at=checked_at,
            capabilities=capabilities,
            source_selections=[{
                "dataset": "identity_profile",
                "primary": "sec",
                "fallback": None,
                "selected_source": "sec",
                "fallback_reason": None,
                "supplemental_sources_used": ["yahoo"],
                "attempts": [
                    {"source": "sec", "status": "AVAILABLE", "failure_code": None},
                    {"source": "yahoo", "status": "AVAILABLE", "failure_code": None},
                    {
                        "source": "moomoo_sg", "status": "SOURCE_LIMITED",
                        "failure_code": "MOOMOO_OPEND_UNREACHABLE",
                    },
                ],
            }],
        )
        coverage = build_research_provider_coverage(
            ROOT, evidence=[], capture_batches=[batch],
            decision_cutoff="2026-09-11T12:10:00Z",
        )
        observed = {item["provider"]: item for item in coverage["providers"]}
        self.assertEqual(observed["sec"]["observed_status"], "AVAILABLE")
        self.assertEqual(observed["yahoo"]["observed_status"], "AVAILABLE")
        self.assertEqual(observed["moomoo_sg"]["observed_status"], "SOURCE_LIMITED")
        self.assertEqual(
            observed["moomoo_sg"]["failure_codes"], ["MOOMOO_OPEND_UNREACHABLE"]
        )
        self.assertTrue(coverage["fallback_policy"]["supplement_failure_isolated"])
        self.assertEqual(coverage["fallback_policy"]["base_sources_continue"], ["sec", "yahoo"])
        self.assertIn("CLIENT_COOKIE", coverage["fallback_policy"]["forbidden_fallbacks"])

    def test_base_evidence_keeps_provider_partial_when_supplement_is_limited(self) -> None:
        capability = build_capability(
            source="yahoo", region="US", security_id="US:COMMON_STOCK:AAPL",
            dataset="identity_profile", status="SOURCE_LIMITED", fields=[],
            endpoint_version="yahoo-profile/1", checked_at="2026-09-11T12:05:00Z",
            as_of="2026-09-11T12:00:00Z", attempt_count=1,
            limitations=["profile supplement unavailable"],
            failure_code="YAHOO_PROFILE_UNAVAILABLE",
        )
        batch = build_capture_batch(
            batch_id="batch-yahoo-partial", security_id="US:COMMON_STOCK:AAPL",
            decision_cutoff="2026-09-11T12:00:00Z", created_at="2026-09-11T12:05:00Z",
            capabilities=[capability],
            source_selections=[{
                "dataset": "identity_profile", "primary": "sec", "fallback": None,
                "selected_source": None, "fallback_reason": None,
                "supplemental_sources_used": [],
                "attempts": [{
                    "source": "yahoo", "status": "SOURCE_LIMITED",
                    "failure_code": "YAHOO_PROFILE_UNAVAILABLE",
                }],
            }],
        )
        coverage = build_research_provider_coverage(
            ROOT,
            evidence=[{"source_type": "yahoo", "source_id": "yahoo-chart:AAPL"}],
            capture_batches=[batch], decision_cutoff="2026-09-11T12:10:00Z",
        )
        yahoo = [item for item in coverage["providers"] if item["provider"] == "yahoo"]
        self.assertTrue(yahoo)
        self.assertTrue(all(item["observed_status"] == "PARTIAL" for item in yahoo))

    def test_provider_batch_may_precede_merged_gate_cutoff_but_must_be_in_gate(self) -> None:
        capability = build_capability(
            source="sec", region="US", security_id="US:COMMON_STOCK:AAPL",
            dataset="identity_profile", status="AVAILABLE", fields=["issuer_name"],
            endpoint_version="sec-submissions/1", checked_at="2026-09-11T12:05:00Z",
            as_of="2026-09-11T12:00:00Z", attempt_count=1, limitations=[],
            evidence_ids=["ev-sec-identity"], raw_content_hashes=["a" * 64],
        )
        batch = build_capture_batch(
            batch_id="batch-before-shared-market-merge",
            security_id="US:COMMON_STOCK:AAPL",
            decision_cutoff="2026-09-11T12:00:00Z",
            created_at="2026-09-11T12:05:00Z",
            capabilities=[capability],
            source_selections=[{
                "dataset": "identity_profile", "primary": "sec", "fallback": None,
                "selected_source": "sec", "fallback_reason": None,
                "supplemental_sources_used": [],
                "attempts": [{"source": "sec", "status": "AVAILABLE", "failure_code": None}],
            }],
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            batch_path = root / "supplement/research-capture-batch.json"
            batch_path.parent.mkdir()
            batch_path.write_text(json.dumps(batch), encoding="utf-8")
            preparation = {
                "common_cutoff": "2026-09-11T12:10:00Z",
                "research_supplements": [{
                    "security_id": "US:COMMON_STOCK:AAPL",
                    "batch_id": batch["batch_id"],
                    "batch_ref": "supplement/research-capture-batch.json",
                }],
            }
            (root / "data-preparation.json").write_text(json.dumps(preparation), encoding="utf-8")
            gate = {
                "decision_cutoff": "2026-09-11T12:10:00Z",
                "allowed_evidence_ids": ["ev-sec-identity"],
            }
            loaded = _load_research_capture_batches(
                gate_path=root / "gate.json", gate=gate,
                security_ids=["US:COMMON_STOCK:AAPL"],
            )
            self.assertEqual([batch["batch_id"]], [item["batch_id"] for item in loaded])
            gate["allowed_evidence_ids"] = []
            with self.assertRaisesRegex(
                MultidimensionalStageError, "MULTIDIMENSIONAL_PROVIDER_BATCH_EVIDENCE_INVALID",
            ):
                _load_research_capture_batches(
                    gate_path=root / "gate.json", gate=gate,
                    security_ids=["US:COMMON_STOCK:AAPL"],
                )


if __name__ == "__main__":
    unittest.main()
