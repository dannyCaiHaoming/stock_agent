from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import shutil
import tempfile
import unittest

from product.council.research_visuals import (
    CORE_CHARTS,
    ResearchVisualError,
    build_visual_bundle,
    persist_visual_report,
    validate_persisted_visual_report,
    validate_visual_bundle,
)
from product.deterministic.equity_valuation import build_trailing_pe_history
from product.runtime.hashing import canonical_hash


CUTOFF = "2026-09-17T12:00:00Z"
SECURITY = "US:COMMON_STOCK:TEST"


def price_rows(count=25):
    rows = []
    for index in range(count):
        day = index + 1
        close = 100 + index
        rows.append({
            "date": f"2026-08-{day:02d}", "open": str(close - 1),
            "high": str(close + 2), "low": str(close - 2), "close": str(close),
            "adjusted_close": str(close), "volume": str(1000 + index),
            "evidence_refs": [f"ev-price-{index}"],
        })
    return rows


def history():
    prices = []
    eps = []
    for month in range(1, 4):
        prices.append({
            "date": f"2026-0{month}-28", "close": "100",
            "source_id": "yahoo-daily", "retrieved_at": CUTOFF,
            "evidence_refs": [f"ev-month-{month}"],
            "price_basis": "CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
            "dividend_adjusted": False, "currency": "USD",
            "security_id": SECURITY, "segment_id": "continuing-entity",
        })
        eps.append({
            "published_at": f"2026-0{month}-01T00:00:00Z",
            "retrieved_at": CUTOFF, "financial_period": "2025-12-31",
            "value": "5", "evidence_refs": [f"ev-eps-{month}"],
            "source_id": "sec-companyfacts",
            "share_basis": "SPLIT_ADJUSTED", "currency": "USD",
            "security_id": SECURITY, "segment_id": "continuing-entity",
        })
    return build_trailing_pe_history(
        history_id="history", security_id=SECURITY, decision_cutoff=CUTOFF,
        requested_start="2026-01-01", requested_end="2026-03-31",
        price_rows=prices, eps_versions=eps, current_value="20",
        minimum_points=2,
    )


def bundle(*, prices=None):
    prices = prices if prices is not None else price_rows()
    benchmark = [dict(row, evidence_refs=[f"ev-benchmark-{index}"]) for index, row in enumerate(prices) if row.get("adjusted_close") is not None]
    return build_visual_bundle(
        bundle_id="visuals", report_id="report-1", run_id="run-1",
        security_id=SECURITY, decision_cutoff=CUTOFF,
        daily_prices=prices, benchmark_prices=benchmark,
        financial_periods=[
            {"period": "2026Q1", "period_kind": "quarter", "revenue": "100", "gross_margin_pct": "20", "operating_margin_pct": "-5", "operating_cash_flow": "10", "capex": "-20", "fcf": "-10", "diluted_shares": "50", "evidence_refs": ["ev-q1"]},
            {"period": "2026Q2", "period_kind": "quarter", "revenue": "120", "gross_margin_pct": "22", "operating_margin_pct": "3", "operating_cash_flow": "30", "capex": "-15", "fcf": "15", "diluted_shares": "52", "discontinuity": True, "evidence_refs": ["ev-q2"]},
        ],
        valuation_history=history(),
    )


class ResearchVisualBundleTests(unittest.TestCase):
    def test_core_charts_hashes_negative_values_and_short_sma(self):
        value = bundle()
        validate_visual_bundle(value)
        charts = {item["chart_id"]: item for item in value["charts"]}
        self.assertTrue(set(CORE_CHARTS) <= set(charts))
        self.assertIn("SMA60_INSUFFICIENT_HISTORY", charts["price_volume_sma"]["limitations"])
        self.assertEqual("-10", charts["financial_trends"]["data"][0]["fcf"])
        self.assertIn("ACCOUNTING_OR_ENTITY_DISCONTINUITY_NOT_CONNECTED", charts["financial_trends"]["limitations"])
        self.assertEqual("LIMITED", charts["peer_comparison_table"]["status"])

    def test_gap_and_tamper_are_explicit(self):
        prices = price_rows()
        prices[10] = {"date": prices[10]["date"], "open": None, "high": None, "low": None, "close": None, "adjusted_close": None, "volume": None, "evidence_refs": ["ev-gap"]}
        value = bundle(prices=prices)
        chart = next(item for item in value["charts"] if item["chart_id"] == "price_volume_sma")
        self.assertIn("EXPLICIT_PRICE_GAPS_NOT_CONNECTED", chart["limitations"])
        broken = deepcopy(value)
        broken["charts"][0]["data"][0]["close"] = "999"
        broken["bundle_hash"] = canonical_hash({key: item for key, item in broken.items() if key != "bundle_hash"})
        with self.assertRaisesRegex(ResearchVisualError, "DATA_HASH"):
            validate_visual_bundle(broken)

    def test_cross_security_history_rejected(self):
        broken = history()
        broken["security_id"] = "US:COMMON_STOCK:OTHER"
        broken["artifact_hash"] = canonical_hash({key: item for key, item in broken.items() if key != "artifact_hash"})
        with self.assertRaisesRegex(ResearchVisualError, "BINDING_MISMATCH"):
            build_visual_bundle(
                bundle_id="bad", report_id="report-1", run_id="run-1",
                security_id=SECURITY, decision_cutoff=CUTOFF,
                daily_prices=price_rows(), benchmark_prices=price_rows(),
                financial_periods=[], valuation_history=broken,
            )


class StaticReportTests(unittest.TestCase):
    def report(self):
        return {
            "report_id": "report-1", "run_id": "run-1", "security_id": SECURITY,
            "decision_cutoff": CUTOFF, "title": "<script>alert(1)</script> 测试公司",
            "summary": {"current_trailing_pe": "20", "history_coverage_ratio": "0.92"},
            "limitations": ["历史区间有限"], "interpretations": ["仅复述冻结研究解释"],
        }

    def test_offline_report_is_escaped_hash_bound_and_movable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = persist_visual_report(root, directory_name="handoff/report", report=self.report(), bundle=bundle())
            directory = Path(result["directory"])
            html = (directory / "report.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script", html.lower())
            self.assertNotIn("https://", html.lower())
            self.assertIn("估值摘要与覆盖说明", html)
            self.assertIn("历史区间有限", html)
            self.assertIn("仅复述冻结研究解释", html)
            self.assertTrue((directory / "report.md").is_file())
            self.assertTrue((directory / "research.json").is_file())
            financial_svg = (directory / "charts/financial_trends.svg").read_text(encoding="utf-8")
            self.assertGreaterEqual(financial_svg.count("<circle"), 8)
            moved = root / "moved"
            shutil.move(str(directory), moved)
            validate_persisted_visual_report(moved)

    def test_escape_path_and_old_report_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ResearchVisualError, "PATH_INVALID"):
                persist_visual_report(Path(temporary), directory_name="../outside", report=self.report(), bundle=bundle())
        fallback = persist_visual_report(Path("."), directory_name="ignored", report=self.report(), bundle=None, legacy_markdown="old")
        self.assertEqual({"mode": "LEGACY_UNCHANGED", "legacy_markdown": "old"}, fallback)

    def test_html_table_formats_provider_float_noise_for_readability(self):
        prices = price_rows()
        prices[0].update(
            open="100.123456789", high="102.123456789",
            low="99.123456789", close="101.123456789",
            adjusted_close="101.123456789",
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(persist_visual_report(
                Path(temporary), directory_name="report", report=self.report(),
                bundle=bundle(prices=prices),
            )["directory"])
            html = (directory / "report.html").read_text(encoding="utf-8")
            self.assertIn("101.1235", html)
            self.assertNotIn("101.123456789", html)

    def test_supplement_text_value_stays_in_table_without_breaking_svg(self):
        value = bundle()
        governance = next(
            chart for chart in value["charts"]
            if chart["chart_id"] == "supplement_governance"
        )
        governance["data"] = [{
            "item_id": "policy", "value": "AUDIT_COMMITTEE_PREAPPROVAL",
        }]
        governance["window"]["points"] = 1
        governance["data_hash"] = canonical_hash(governance["data"])
        value["bundle_hash"] = canonical_hash({
            key: item for key, item in value.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(persist_visual_report(
                Path(temporary), directory_name="report", report=self.report(), bundle=value,
            )["directory"])
            html = (directory / "report.html").read_text(encoding="utf-8")
            self.assertIn("AUDIT_COMMITTEE_PREAPPROVAL", html)
            self.assertIn(".table-wrap table{min-width:900px}", html)
            self.assertIn(".limit{color:#9a3412;overflow-wrap:anywhere}", html)
            self.assertIn("section h2{break-after:avoid-page}", html)
            self.assertIn("@page{size:A4 landscape;margin:8mm}", html)
            mixed_svg = (directory / "charts/supplement_governance.svg").read_text(encoding="utf-8")
            self.assertIn("混合量纲数据不绘制跨字段折线", mixed_svg)
            self.assertNotIn("<polyline", mixed_svg)

    def test_persisted_data_file_tamper_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(persist_visual_report(Path(temporary), directory_name="report", report=self.report(), bundle=bundle())["directory"])
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            path = directory / manifest["entries"][0]["data_ref"]
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ResearchVisualError, "PATH_OR_HASH"):
                validate_persisted_visual_report(directory)


if __name__ == "__main__":
    unittest.main()
