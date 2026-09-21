from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.moomoo_opend import (
    MoomooOpenDError,
    MoomooOpenDQuoteClient,
    build_quote_manifest,
    load_quote_manifest,
    scan_committable_payload,
    serialize_quote_result,
)
from product.mcp.live.research_supplement import build_capability


NOW = datetime(2026, 9, 16, 13, 15, tzinfo=timezone.utc)


class FakeFrame:
    def __init__(self, rows, *, attrs=None):
        self._rows = rows
        self.columns = list(rows[0]) if rows else []
        self.dtypes = {column: "object" for column in self.columns}
        self.attrs = attrs or {}

    def __len__(self):
        return len(self._rows)

    def to_dict(self, *, orient):
        if orient != "records":
            raise AssertionError(orient)
        return deepcopy(self._rows)


class FakeContext:
    def __init__(self, *, state=None, responses=None):
        self.state = state or {
            "server_ver": "1010",
            "qot_logined": True,
            "program_status_type": "READY",
            "program_status_desc": "",
            "market_us": "OPEN",
        }
        self.responses = responses or {}
        self.closed = False
        self.calls = []

    def close(self):
        self.closed = True

    def get_global_state(self):
        self.calls.append(("get_global_state", {}))
        return 0, deepcopy(self.state)

    def get_company_profile(self, code):
        self.calls.append(("get_company_profile", {"code": code}))
        return self.responses.get("get_company_profile", (0, FakeFrame([
            {"name": "公司代码", "value": code.split(".", 1)[1], "field_type": 0},
            {"name": "公司名称", "value": "苹果", "field_type": 0},
            {"name": "公司简介", "value": "Devices and services", "field_type": 2},
        ])))

    def get_capital_flow(self, code, period_type="INTRADAY", start=None, end=None):
        self.calls.append(("get_capital_flow", {
            "code": code, "period_type": period_type, "start": start, "end": end,
        }))
        return self.responses.get("get_capital_flow", (0, FakeFrame([{
            "last_valid_time": "2026-09-16 09:14:44",
            "in_flow": 1.0,
            "super_in_flow": 2.0,
            "big_in_flow": 3.0,
            "mid_in_flow": 4.0,
            "sml_in_flow": 5.0,
            "main_in_flow": "N/A",
            "capital_flow_item_time": "2026-09-15 16:00:00",
        }])))

    def get_research_analyst_consensus(self, code):
        self.calls.append(("get_research_analyst_consensus", {"code": code}))
        return self.responses.get("get_research_analyst_consensus", (0, {
            "highest": 400.0, "average": 348.19, "lowest": 245.0,
            "rating": "BUY", "total": 25, "update_time": 1789515001,
            "update_time_str": "2026-09-15", "buy": 60.0, "hold": 24.0, "sell": 16.0,
        }))

    def get_research_morningstar_report(self, code):
        self.calls.append(("get_research_morningstar_report", {"code": code}))
        return self.responses.get("get_research_morningstar_report", (0, {
            "rating_type": "QUALITATIVE", "star_rating": 2,
            "star_update_time": 1789507200, "star_update_time_str": "2026-09-15",
            "fair_value": 290.0, "fair_value_content": "Fair value text",
            "economic_moat_label": "NARROW", "economic_moat_content": "Moat text",
            "uncertainty_label": "MEDIUM", "uncertainty_content": "Uncertainty text",
            "financial_health_content": "Financial health text",
            "capital_allocation_label": "STANDARD",
            "capital_allocation_content": "Capital allocation text",
            "investment_thesis_content": "Thesis text", "bull_say": "Bull text",
            "bear_say": "Bear text", "analyst_note_title": "Note",
            "analyst_note_content": "Note text", "analyst_report_by_line": "Analyst",
            "analyst_report_update_time": 1788985740,
            "analyst_report_update_time_str": "2026-09-09",
        }))

    def get_shareholders_institutional(self, code, next_key=None, num=None):
        self.calls.append(("get_shareholders_institutional", {
            "code": code, "next_key": next_key, "num": num,
        }))
        return 0, FakeFrame([{
            "period_text": "2026/Q2", "institution_quantity": 10,
            "institution_quantity_change": 1, "holder_quantity": 1000,
            "holder_quantity_change": 100, "holder_pct": 70,
            "holder_pct_change": 1, "next_key": "-1",
            "update_time": 1789565699, "update_time_str": "2026-09-16 09:34:59",
        }])

    def get_insider_holder_list(self, code, next_key=None, num=None):
        self.calls.append(("get_insider_holder_list", {
            "code": code, "next_key": next_key, "num": num,
        }))
        return 0, FakeFrame([{
            "holder_id": 1, "holder_quantity": 100, "holder_pct": 0.1,
            "name": "Public Person", "title": "Officer", "all_count": 1,
            "next_key": "-1", "insider_total_count": 1,
            "insider_bought_count": 0, "insider_sold_count": 1,
        }])

    def get_insider_trade_list(self, code, holder_id=None, num=None, next_key=None):
        self.calls.append(("get_insider_trade_list", {
            "code": code, "holder_id": holder_id, "num": num, "next_key": next_key,
        }))
        return 0, FakeFrame([{
            "trade_shares": 10, "min_trade_date": 1788796800,
            "min_trade_date_str": "2026-09-07", "max_trade_date": 1788796800,
            "max_trade_date_str": "2026-09-07", "min_price": 200,
            "max_price": 200, "security_holder_quantity": 90,
            "is_proposed_sale_of_securities": False, "holder_id": 1,
            "name": "Public Person", "title": "Officer",
            "security_description": "Common Stock", "transaction_type": "卖出",
            "source_group_name": "Form 4",
        }], attrs={"all_count": 1, "next_key": "-1"})

    def get_option_expiration_date(self, code):
        self.calls.append(("get_option_expiration_date", {"code": code}))
        return 0, FakeFrame([{
            "strike_time": "2026-09-18", "option_expiry_date_distance": 2,
            "expiration_cycle": "WEEK",
        }])

    def get_option_chain(self, code, start=None, end=None):
        self.calls.append(("get_option_chain", {"code": code, "start": start, "end": end}))
        return 0, FakeFrame([{
            "code": "US.AAPL260918C00250000", "name": "AAPL Call",
            "lot_size": 100, "stock_type": "OPTION", "option_type": "CALL",
            "stock_owner": "US.AAPL", "strike_time": "2026-09-18",
            "strike_price": 250, "suspension": False, "stock_id": 1,
            "index_option_type": "N/A", "expiration_cycle": "WEEK",
            "option_standard_type": "STANDARD", "option_settlement_mode": "N/A",
        }])

    def get_research_rating_summary(
        self, code, rating_dimension_type=None, num=None, next_key=None,
    ):
        self.calls.append(("get_research_rating_summary", {
            "code": code, "rating_dimension_type": rating_dimension_type,
            "num": num, "next_key": next_key,
        }))
        if rating_dimension_type == 2:
            return 0, {"analyst_rating_summary_list": [{
                "analyst_info": {"analyst_uid": 2, "analyst_name": "Public Analyst"},
                "rating_item_list": [{
                    "recommendation_date": 1789448400,
                    "recommendation_date_str": "2026-09-15", "rating": "BUY",
                    "target_price": 365, "update_time": 1789482701110206,
                }],
            }], "next_key": "-1"}
        return 0, {"inst_rating_summary_list": [{
            "institution_info": {"institution_uid": 1, "institution_name": "Research Co"},
            "rating_item_list": [{
                "recommendation_date": 1789448400, "recommendation_date_str": "2026-09-15",
                "rating": "BUY", "target_price": 365, "update_time": 1789482701110206,
            }],
        }], "next_key": "-1"}

    def get_short_interest(self, code, next_key=None, num=None):
        self.calls.append(("get_short_interest", {
            "code": code, "next_key": next_key, "num": num,
        }))
        return 0, FakeFrame([{
            "timestamp": 1788148800, "timestamp_str": "2026-08-31",
            "shares_short": 100, "short_percent": 1.5,
            "avg_daily_share_volume": 50, "days_to_cover": 2,
            "close_price": 200, "last_close_price": 199,
        }], attrs={"next_key": "-1"}), FakeFrame([])

    def get_fed_watch_dot_plot(self):
        self.calls.append(("get_fed_watch_dot_plot", {}))
        return 0, FakeFrame([{
            "year": 2026, "rate": 4.0, "vote_count": 5,
            "is_median": True, "median_rate": 4.0, "current_rate": 4.25,
        }])


class MoomooOpenDTests(unittest.TestCase):
    def manifest(self):
        return load_quote_manifest()

    def client(self, contexts, **kwargs):
        def factory(host, port):
            self.assertEqual((host, port), ("127.0.0.1", 11111))
            context = contexts.pop(0)
            return context
        client = MoomooOpenDQuoteClient(
            manifest=self.manifest(), context_factory=factory,
            sdk_version_loader=lambda: "10.10.7008", now=lambda: NOW, **kwargs,
        )
        client.server_version = "1010"
        client._readiness_approved = True
        return client

    def test_manifest_is_quote_only_and_remote_hosts_are_rejected(self):
        manifest = self.manifest()
        self.assertTrue(all(item["method"].startswith("get_") for item in manifest["capabilities"]))
        methods = {item["method"] for item in manifest["capabilities"]}
        self.assertTrue({"place_order", "unlock_trade", "get_acc_list"}.isdisjoint(methods))
        with self.assertRaisesRegex(ValueError, "REMOTE_HOST_REJECTED"):
            MoomooOpenDQuoteClient(manifest=manifest, host="192.0.2.10")
        broken = deepcopy(manifest)
        broken["capabilities"][0]["method"] = "place_order"
        with self.assertRaisesRegex(ValueError, "METHOD_NOT_ALLOWED"):
            build_quote_manifest(
                manifest_id="bad", sdk_version="10.10.7008",
                minimum_opend_server_version="1010", approved_at="2026-09-16T00:00:00Z",
                capabilities=broken["capabilities"],
            )

    def test_readiness_requires_ready_quote_login_and_version(self):
        ready_context = FakeContext()
        result = self.client([ready_context]).readiness()
        self.assertEqual(result["status"], "OPEND_QUOTE_FEASIBLE")
        self.assertEqual(result["server_version"], "1010")
        self.assertTrue(ready_context.closed)

        logged_out = FakeContext(state={
            "server_ver": "1010", "qot_logined": False,
            "program_status_type": "READY", "program_status_desc": "", "market_us": "OPEN",
        })
        with self.assertRaisesRegex(MoomooOpenDError, "QUOTE_NOT_LOGGED_IN"):
            self.client([logged_out]).readiness()

        old = FakeContext(state={
            "server_ver": "1009", "qot_logined": True,
            "program_status_type": "READY", "program_status_desc": "", "market_us": "OPEN",
        })
        with self.assertRaisesRegex(MoomooOpenDError, "VERSION_UNSUPPORTED"):
            self.client([old]).readiness()

        unready = MoomooOpenDQuoteClient(
            manifest=self.manifest(), context_factory=lambda host, port: FakeContext(),
            sdk_version_loader=lambda: "10.10.7008", now=lambda: NOW,
        )
        with self.assertRaisesRegex(MoomooOpenDError, "READINESS_REQUIRED"):
            unready.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})

    def test_failed_readiness_never_authorizes_same_client(self):
        states = ({
            "server_ver": "1010", "qot_logined": False,
            "program_status_type": "READY", "program_status_desc": "", "market_us": "OPEN",
        }, {
            "server_ver": "1010", "qot_logined": True,
            "program_status_type": "STARTING", "program_status_desc": "", "market_us": "OPEN",
        })
        for state, failure in zip(states, ("QUOTE_NOT_LOGGED_IN", "OPEND_NOT_READY")):
            with self.subTest(failure=failure):
                contexts = [FakeContext(state=state), FakeContext()]
                client = MoomooOpenDQuoteClient(
                    manifest=self.manifest(),
                    context_factory=lambda host, port: contexts.pop(0),
                    sdk_version_loader=lambda: "10.10.7008", now=lambda: NOW,
                )
                with self.assertRaisesRegex(MoomooOpenDError, failure):
                    client.readiness()
                self.assertIsNone(client.server_version)
                self.assertFalse(client._readiness_approved)
                with self.assertRaisesRegex(MoomooOpenDError, "READINESS_REQUIRED"):
                    client.read(
                        capability_id="company-profile-v1", params={"code": "US.AAPL"},
                    )
                self.assertEqual(len(contexts), 1)

        contexts = [FakeContext(), FakeContext()]
        approved = MoomooOpenDQuoteClient(
            manifest=self.manifest(),
            context_factory=lambda host, port: contexts.pop(0),
            sdk_version_loader=lambda: "10.10.7008", now=lambda: NOW,
        )
        approved.readiness()
        result = approved.read(
            capability_id="company-profile-v1", params={"code": "US.AAPL"},
        )
        self.assertEqual(result["server_version"], "1010")

    def test_sdk_version_parameters_security_and_unknown_capability_fail_closed(self):
        with self.assertRaisesRegex(MoomooOpenDError, "SDK_VERSION_UNSUPPORTED"):
            MoomooOpenDQuoteClient(
                manifest=self.manifest(), context_factory=lambda host, port: FakeContext(),
                sdk_version_loader=lambda: "10.9.6908", now=lambda: NOW,
            ).read(capability_id="company-profile-v1", params={"code": "US.AAPL"})
        client = self.client([])
        with self.assertRaisesRegex(ValueError, "SECURITY_INVALID"):
            client.read(capability_id="company-profile-v1", params={"code": "HK.00700"})
        with self.assertRaisesRegex(ValueError, "PARAMETERS_INVALID"):
            client.read(capability_id="company-profile-v1", params={"code": "US.AAPL", "account_id": "1"})
        with self.assertRaisesRegex(ValueError, "CAPABILITY_UNKNOWN"):
            client.read(capability_id="trade-order", params={})
        with self.assertRaisesRegex(ValueError, "CODE_LIST_INVALID"):
            client.read(capability_id="market-snapshot-v1", params={
                "code_list": [f"US.X{index}" for index in range(49)],
            })
        with self.assertRaisesRegex(ValueError, "MACRO_INDICATOR_INVALID"):
            client.read(capability_id="macro-indicator-history-v1", params={
                "indicator_id": 999, "max_count": 24,
            })
        with self.assertRaisesRegex(ValueError, "RATING_PAGE_SIZE_INVALID"):
            client.read(capability_id="institution-rating-summary-v1", params={
                "code": "US.AAPL", "rating_dimension_type": 1, "num": 21,
            })
        with self.assertRaisesRegex(ValueError, "DATE_WINDOW_EXCEEDED"):
            client.read(capability_id="option-underlying-history-v1", params={
                "code": "US.AAPL", "start": "2026-07-01", "end": "2026-09-20",
            })

    def test_profile_capture_is_deterministic_cached_and_request_bound(self):
        context = FakeContext()
        with tempfile.TemporaryDirectory() as temp:
            result = self.client(
                [context], cache=SnapshotCache(Path(temp) / "cache"),
            ).read(capability_id="company-profile-v1", params={"code": "US.AAPL"})
        self.assertEqual(result["security_code"], "US.AAPL")
        self.assertEqual(result["payload"]["kind"], "DATAFRAME")
        self.assertEqual(result["record"]["raw_content_hash"], result["raw_content_hash"])
        self.assertTrue(context.closed)

    def test_extended_quote_methods_are_allowlisted_parameter_bound_and_keep_pagination(self):
        cases = [
            ("institutional-aggregate-v1", {"code": "US.AAPL", "num": 20}),
            ("insider-holder-list-v1", {"code": "US.AAPL", "num": 20}),
            ("insider-trade-list-v1", {"code": "US.AAPL", "holder_id": 1, "num": 20}),
            ("option-expirations-v1", {"code": "US.AAPL"}),
            ("option-chain-static-v1", {
                "code": "US.AAPL", "start": "2026-09-18", "end": "2026-09-18",
            }),
            ("institution-rating-summary-v1", {
                "code": "US.AAPL", "rating_dimension_type": 1, "num": 20,
            }),
            ("analyst-rating-summary-v1", {
                "code": "US.AAPL", "rating_dimension_type": 2, "num": 20,
            }),
            ("short-interest-v1", {"code": "US.AAPL", "num": 20}),
        ]
        contexts = [FakeContext() for _ in cases]
        client = self.client(contexts)
        results = [client.read(capability_id=capability, params=params) for capability, params in cases]
        self.assertEqual(results[2]["payload"]["attrs"]["next_key"], "-1")
        self.assertEqual(results[-1]["payload"]["attrs"]["next_key"], "-1")
        self.assertEqual(results[4]["payload"]["rows"][0]["stock_owner"], "US.AAPL")

        with self.assertRaisesRegex(ValueError, "PAGE_SIZE_INVALID"):
            self.client([]).read(
                capability_id="institutional-aggregate-v1",
                params={"code": "US.AAPL", "num": 51},
            )
        with self.assertRaisesRegex(ValueError, "DATE_RANGE_INVALID"):
            self.client([]).read(capability_id="option-chain-static-v1", params={
                "code": "US.AAPL", "start": "2026-09-19", "end": "2026-09-18",
            })

    def test_dot_plot_uses_official_method_name_and_missing_sdk_method_is_sanitized(self):
        context = FakeContext()
        result = self.client([context]).read(
            capability_id="fedwatch-dot-plot-v1", params={},
        )
        self.assertEqual(result["method"], "get_fed_watch_dot_plot")
        self.assertIn(("get_fed_watch_dot_plot", {}), context.calls)

        class MissingDotPlot(FakeContext):
            def __getattribute__(self, name):
                if name == "get_fed_watch_dot_plot":
                    raise AttributeError(name)
                return super().__getattribute__(name)

        with self.assertRaisesRegex(MoomooOpenDError, "METHOD_UNAVAILABLE"):
            self.client([MissingDotPlot()]).read(
                capability_id="fedwatch-dot-plot-v1", params={},
            )

    def test_option_contract_codes_do_not_fail_underlying_security_binding(self):
        result = self.client([FakeContext()]).read(
            capability_id="option-chain-static-v1",
            params={"code": "US.AAPL", "start": "2026-09-18", "end": "2026-09-18"},
        )
        self.assertEqual(result["security_code"], "US.AAPL")

        bad = FakeContext()
        original = bad.get_option_chain
        def wrong_owner(code, start=None, end=None):
            ret, frame = original(code, start=start, end=end)
            frame._rows[0]["stock_owner"] = "US.MSFT"
            return ret, frame
        bad.get_option_chain = wrong_owner
        with self.assertRaisesRegex(MoomooOpenDError, "SECURITY_MISMATCH"):
            self.client([bad]).read(capability_id="option-chain-static-v1", params={
                "code": "US.AAPL", "start": "2026-09-18", "end": "2026-09-18",
            })

    def test_schema_drift_and_entitlement_open_only_affected_circuit(self):
        drift = FakeContext(responses={"get_company_profile": (0, FakeFrame([{"unexpected": 1}]))})
        client = self.client([drift])
        with self.assertRaisesRegex(MoomooOpenDError, "SCHEMA_DRIFT"):
            client.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})
        with self.assertRaisesRegex(MoomooOpenDError, "CIRCUIT_OPEN"):
            client.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})

        denied = FakeContext(responses={"get_company_profile": (-1, "No quote right")})
        with self.assertRaisesRegex(MoomooOpenDError, "ENTITLEMENT_REQUIRED"):
            self.client([denied]).read(
                capability_id="company-profile-v1", params={"code": "US.AAPL"},
            )

        limited = FakeContext(responses={"get_company_profile": (-1, "frequency limit exceeded")})
        with self.assertRaisesRegex(MoomooOpenDError, "RATE_LIMITED"):
            self.client([limited]).read(
                capability_id="company-profile-v1", params={"code": "US.AAPL"},
            )

    def test_time_and_request_budgets_fail_closed(self):
        moments = iter((NOW, datetime(2026, 9, 16, 13, 15, 16, tzinfo=timezone.utc)))
        context = FakeContext()
        client = MoomooOpenDQuoteClient(
            manifest=self.manifest(), context_factory=lambda host, port: context,
            sdk_version_loader=lambda: "10.10.7008", now=lambda: next(moments),
        )
        client.server_version = "1010"
        client._readiness_approved = True
        with self.assertRaisesRegex(MoomooOpenDError, "TIME_BUDGET_EXCEEDED"):
            client.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})

        one = self.client([FakeContext()])
        one.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})
        with self.assertRaisesRegex(MoomooOpenDError, "BUDGET_EXHAUSTED"):
            one.read(capability_id="company-profile-v1", params={"code": "US.AAPL"})

    def test_secret_scanner_rejects_credentials_but_keeps_public_research(self):
        scan_committable_payload({
            "reporting_owner_name": "Jane Public",
            "accounting_standards": "US GAAP",
            "analyst_note_content": "Public research text",
        })
        for value in ({"Cookie": "sid=private"}, {"access_token": "private"}, {"account_id": "123"}):
            with self.assertRaisesRegex(ValueError, "SECRET_MATERIAL_REJECTED"):
                scan_committable_payload(value)

    def test_serializer_rejects_wrong_kind(self):
        payload, raw = serialize_quote_result({"server_ver": "1010"}, response_kind="DICT")
        self.assertEqual(payload["value"]["server_ver"], "1010")
        self.assertTrue(raw)
        with self.assertRaisesRegex(ValueError, "KIND_MISMATCH"):
            serialize_quote_result({}, response_kind="DATAFRAME")

    def test_capability_contract_records_opend_specific_failure_and_versions(self):
        capability = build_capability(
            source="moomoo_sg", region="SG", security_id="US:COMMON_STOCK:AAPL",
            dataset="vendor_money_flow", status="OPEND_UNREACHABLE", fields=[],
            endpoint_version="opend/1010;sdk/10.10.7008;method/get_capital_flow",
            checked_at="2026-09-16T13:15:00Z", as_of="2026-09-16T13:15:00Z",
            attempt_count=1, limitations=["本机 OpenD 不可达"],
            failure_code="MOOMOO_OPEND_UNREACHABLE",
        )
        self.assertEqual(capability["schema_version"], "research-source-capability/1.2.0")
        self.assertEqual(capability["status"], "OPEND_UNREACHABLE")


if __name__ == "__main__":
    unittest.main()
