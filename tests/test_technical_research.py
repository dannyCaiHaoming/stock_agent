from __future__ import annotations

import unittest
from decimal import Decimal
import hashlib
import json

from product.council.technical_chart import render_relative_performance_svg
from product.deterministic.market_analysis import (
    calculate_market_state_statistics,
    calculate_technical_statistics,
    verify_market_state_calculation,
    verify_technical_calculation,
)
from product.mcp.live.market import normalize_cached_research_series, normalize_research_daily_rows
from product.runtime.common_stock_data import merge_benchmark_research_evidence


class SyntheticCalendar:
    version = "synthetic/1"
    content_hash = "c" * 64

    def session_close(self, day):
        return {
            "2026-09-10": "2026-09-10T20:00:00Z",
            "2026-09-11": "2026-09-11T20:00:00Z",
            "2026-09-12": None,
            "2026-09-14": "2026-09-14T20:00:00Z",
        }.get(day)

    def completed_sessions(self, cutoff):
        return [
            close for close in (
                "2026-09-10T20:00:00Z", "2026-09-11T20:00:00Z",
                "2026-09-14T20:00:00Z",
            )
            if close <= cutoff.isoformat().replace("+00:00", "Z")
        ]


class ResearchSeriesTests(unittest.TestCase):
    def test_cached_research_series_revalidates_raw_byte_hash(self) -> None:
        raw = json.dumps([{
            "date": "2026-09-10", "open": 10, "high": 12, "low": 9,
            "close": 11, "adjusted_close": 11, "volume": 1000,
            "dividends": 0, "stock_splits": 0,
        }]).encode()
        record = {
            "key": {
                "provider": "yahoo", "ticker": "TEST", "security_id": "US:TEST",
                "currency": "USD", "interval": "1d",
                "adapter_version": "yahoo-eod-adapter/0.2.0",
            },
            "raw_content_hash": hashlib.sha256(raw).hexdigest(),
            "retrieved_at": "2026-09-11T21:00:00Z",
        }
        result = normalize_cached_research_series(
            record, raw, security_id="US:TEST", ticker="TEST", currency="USD",
            calendar=SyntheticCalendar(),
        )
        self.assertTrue(result["evidence"])
        with self.assertRaisesRegex(ValueError, "YAHOO_RESEARCH_RAW_HASH_MISMATCH"):
            normalize_cached_research_series(
                record, raw + b" ", security_id="US:TEST", ticker="TEST", currency="USD",
                calendar=SyntheticCalendar(),
            )

    def test_cached_series_detects_missing_completed_middle_session(self) -> None:
        rows = [
            {
                "date": day, "open": 10, "high": 12, "low": 9,
                "close": 11, "adjusted_close": 11, "volume": 1000,
                "dividends": 0, "stock_splits": 0,
            }
            for day in ("2026-09-10", "2026-09-14")
        ]
        raw = json.dumps(rows).encode()
        record = {
            "key": {
                "provider": "yahoo", "ticker": "TEST", "security_id": "US:TEST",
                "currency": "USD", "interval": "1d",
                "start": "2026-09-10", "end": "2026-09-15",
                "adapter_version": "yahoo-eod-adapter/0.2.0",
            },
            "raw_content_hash": hashlib.sha256(raw).hexdigest(),
            "retrieved_at": "2026-09-14T21:00:00Z",
        }
        result = normalize_cached_research_series(
            record, raw, security_id="US:TEST", ticker="TEST", currency="USD",
            calendar=SyntheticCalendar(),
        )
        self.assertEqual(
            [{"date": "2026-09-11", "reason": "YAHOO_COMPLETED_SESSION_MISSING"}],
            [
                gap for gap in result["gaps"]
                if gap["reason"] == "YAHOO_COMPLETED_SESSION_MISSING"
            ],
        )

    def test_ohlcv_adjustment_and_actions_are_preserved(self) -> None:
        result = normalize_research_daily_rows(
            [{
                "date": "2026-09-10", "open": 10, "high": 12, "low": 9,
                "close": 11, "adjusted_close": 5.5, "volume": 1000,
                "dividends": 0.25, "stock_splits": 2,
            }],
            security_id="US:TEST", ticker="TEST",
            retrieved_at="2026-09-11T21:00:00Z", calendar=SyntheticCalendar(),
            raw_content_hash="a" * 64, currency="USD",
        )
        fields = {item["semantic_field"]: item for item in result["evidence"]}
        self.assertEqual(
            set(fields),
            {"open_price", "high_price", "low_price", "historical_close_price",
             "adjusted_close_price", "share_volume", "cash_dividend", "stock_split_ratio"},
        )
        self.assertTrue(fields["adjusted_close_price"]["metadata"]["historical_return_eligible"])
        self.assertEqual(fields["stock_split_ratio"]["source_id"], "yahoo-daily")
        for fact in fields.values():
            self.assertEqual(fact["as_of"], "2026-09-10T20:00:00Z")
            self.assertEqual(fact["retrieved_at"], "2026-09-11T21:00:00Z")

    def test_missing_fields_and_incomplete_session_are_explicit(self) -> None:
        result = normalize_research_daily_rows(
            [
                {"date": "2026-09-10", "close": 11},
                {"date": "2026-09-12", "close": 12},
            ],
            security_id="US:TEST", ticker="TEST",
            retrieved_at="2026-09-11T21:00:00Z", calendar=SyntheticCalendar(),
            raw_content_hash="a" * 64, currency="USD",
        )
        reasons = {item["reason"] for item in result["gaps"]}
        self.assertIn("YAHOO_RESEARCH_FIELD_MISSING", reasons)
        self.assertIn("NOT_COMPLETED_REGULAR_SESSION", reasons)

    def test_inconsistent_ohlc_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "OHLC_INCONSISTENT"):
            normalize_research_daily_rows(
                [{"date": "2026-09-10", "open": 10, "high": 9, "low": 8,
                  "close": 11, "adjusted_close": 11, "volume": 10}],
                security_id="US:TEST", ticker="TEST",
                retrieved_at="2026-09-11T21:00:00Z", calendar=SyntheticCalendar(),
                raw_content_hash="a" * 64, currency="USD",
            )

    def test_benchmark_merge_extends_gate_without_reclassifying_holdings(self) -> None:
        prepared = {
            "gate": {
                "decision_cutoff": "2026-09-10T20:00:00Z",
                "input_evidence_ids": ["ev-stock"],
                "allowed_evidence_ids": ["ev-stock"],
                "excluded_evidence_ids": [],
                "allowed_evidence": [{
                    "evidence_id": "ev-stock", "security_id": "US:TEST",
                    "source_id": "yahoo-daily", "as_of": "2026-09-10T20:00:00Z",
                    "retrieved_at": "2026-09-10T20:00:00Z",
                }],
                "excluded": [],
            },
            "preparation": {"preparation_hash": "old"},
        }
        benchmark = {
            "benchmark_id": "US:SPY", "status": "FROZEN",
            "snapshot_hash": "s" * 64, "gaps": [],
            "evidence": [{
                "evidence_id": "ev-spy", "security_id": "US:SPY",
                "semantic_field": "adjusted_close_price", "value": "500",
                "source_id": "yahoo-daily", "as_of": "2026-09-10T20:00:00Z",
                "published_at": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T01:00:00Z",
            }],
        }
        merged = merge_benchmark_research_evidence(prepared, benchmark=benchmark)
        self.assertEqual(
            set(merged["gate"]["allowed_evidence_ids"]), {"ev-stock", "ev-spy"}
        )
        self.assertEqual(merged["preparation"]["benchmark"]["benchmark_id"], "US:SPY")
        self.assertEqual(merged["gate"]["decision_cutoff"], "2026-09-11T01:00:00Z")


def _rows(count: int, *, scale: int = 1, split_at: int | None = None, missing_adjusted=False):
    values = []
    for index in range(count):
        close = 100 + index * scale
        values.append({
            "date": f"2026-08-{index + 1:02d}",
            "close": close,
            "adjusted_close": None if missing_adjusted else close,
            "volume": 1000 + index * 10,
            "stock_split": 2 if split_at == index else 0,
            "evidence_ids": [f"ev-{scale}-{index}"],
        })
    return values


class TechnicalCalculationTests(unittest.TestCase):
    def test_market_state_statistics_are_deterministic_and_keep_lineage(self) -> None:
        artifact = calculate_market_state_statistics(
            _rows(6), market_id="US:SPY",
            as_of="2026-08-06T20:00:00Z", windows=(2, 5),
        )
        verify_market_state_calculation(artifact)
        self.assertEqual(artifact["windows"][0]["status"], "COMPLETE")
        self.assertEqual(
            Decimal(artifact["windows"][0]["metrics"]["market_total_return"]),
            Decimal(105) / Decimal(103) - Decimal(1),
        )
        self.assertTrue(artifact["evidence_fact_ids"])

    def test_hand_checkable_return_relative_strength_drawdown_and_volume(self) -> None:
        security = _rows(6, scale=2)
        benchmark = _rows(6, scale=1)
        artifact = calculate_technical_statistics(
            security, benchmark, security_id="US:TEST", benchmark_id="US:SPY",
            as_of="2026-08-06T20:00:00Z", windows=(2, 5),
        )
        verify_technical_calculation(artifact)
        two = artifact["windows"][0]
        self.assertEqual(two["status"], "COMPLETE")
        self.assertEqual(
            Decimal(two["metrics"]["security_total_return"]),
            Decimal(110) / Decimal(106) - Decimal(1),
        )
        self.assertLess(float(two["metrics"]["maximum_drawdown"]), 0.000001)
        self.assertGreater(float(two["metrics"]["latest_volume_ratio"]), 1)
        self.assertTrue(artifact["evidence_fact_ids"])

    def test_history_shortage_and_split_without_adjusted_close_do_not_invent_signal(self) -> None:
        short = calculate_technical_statistics(
            _rows(3), _rows(3, scale=2), security_id="US:TEST", benchmark_id="US:SPY",
            as_of="2026-08-03T20:00:00Z", windows=(5,),
        )
        self.assertEqual(short["windows"][0]["status"], "INSUFFICIENT_HISTORY")
        discontinuity = calculate_technical_statistics(
            _rows(4, split_at=2, missing_adjusted=True), _rows(4, scale=2),
            security_id="US:TEST", benchmark_id="US:SPY",
            as_of="2026-08-04T20:00:00Z", windows=(2,),
        )
        self.assertEqual(discontinuity["windows"][0]["status"], "PRICE_DISCONTINUITY")

    def test_chart_uses_same_adjusted_series_and_volume(self) -> None:
        svg = render_relative_performance_svg(
            _rows(4), _rows(4, scale=2), security_label="TEST", benchmark_label="SPY"
        )
        self.assertIn("复权表现（起点=100）", svg)
        self.assertEqual(svg.count("<polyline"), 2)
        self.assertEqual(svg.count("<rect"), 5)  # 背景 + 四个成交量柱
        self.assertIn("2026-08-01", svg)
        self.assertIn("2026-08-04", svg)


if __name__ == "__main__":
    unittest.main()
