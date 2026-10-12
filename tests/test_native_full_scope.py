"""完整输入/停止点、共享市场与原同行数据复用的业务检查。"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.research import prepare_task, ResearchTools
from product.tools.report_contracts import semantic_schema
from product.tools.research_scope_plan import build_stage_scope, summarize_reports
from product.tools.material_preparation import materialize_peer_selection
from tests.test_common_stock_research_contracts import confirmed_handoff, stock_handoff, gate_for
from tests.test_single_stock_input import alb_request
from tests.test_native_research_tools import SECURITY, AT, frozen_gate
from tests.test_multidimensional_research_contracts import _report


class NativeFullScopeTests(unittest.TestCase):
    def test_all_input_assets_and_stage_stop_points_are_preserved(self):
        handoff=confirmed_handoff();gate=gate_for(handoff,run_id="scope-test")
        original=copy.deepcopy(handoff)
        for stage,has_skeptic,has_cio in [("COMMON_STOCK_RESEARCH",False,False),("MULTI_DIMENSIONAL_HOLDING_RESEARCH",False,False),
                                         ("INDEPENDENT_COUNTER_THESIS_RESEARCH",True,False),("PREDECISION_CIO_SYNTHESIS",True,True)]:
            scope=build_stage_scope(handoff,gate,stage=stage)
            self.assertEqual({i["security_id"] for i in scope["items"]},{i["security_id"] for i in handoff["portfolio"]["positions"]})
            for item in scope["items"]:
                if item["asset_type"]=="COMMON_STOCK":
                    self.assertEqual("INDEPENDENT_FIRST_PASS" in item["required_capabilities"],has_skeptic)
                    self.assertEqual("RESEARCH_SYNTHESIS" in item["required_capabilities"],has_cio)
                else:
                    self.assertEqual(item["coverage"],"CAPABILITY_GAP")
            status=summarize_reports(scope,[])
            self.assertFalse(status["all_required_reports_saved"])
            self.assertEqual(status["risk_status"],"NOT_RUN")
        self.assertEqual(handoff,original)

    def test_one_shared_macro_report_covers_two_stocks_without_private_position_fields(self):
        handoff=stock_handoff(2);gate=gate_for(handoff,run_id="shared-market")
        gate["allowed_evidence"].append({"evidence_id":"macro-rate","security_id":"US:MARKET","semantic_field":"us_treasury_10y_yield",
            "value":"4","unit":"percent","source_type":"fred","source_id":"synthetic-fred",
            "as_of":"2026-09-10T00:00:00Z","retrieved_at":"2026-09-10T00:00:00Z"})
        gate["allowed_evidence_ids"].append("macro-rate");gate["input_evidence_ids"].append("macro-rate")
        gate["bundle_hash"]=legacy_envelope_hash(gate,hash_field="bundle_hash")
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root=Path(temp)/"macro"
            task=prepare_task(root,research_input=handoff,gate=gate,security_id=handoff["portfolio"]["positions"][0]["security_id"],
                              capability="MACRO_CONTEXT",research_question="研究宏观传导。")
            tools=ResearchTools(root,access_token=task["access_token"])
            context=tools.context()
            self.assertEqual(context["research_scope"],"SHARED_MARKET")
            self.assertEqual(len(context["security_ids"]),2)
            for item in context["securities"]:
                self.assertNotIn("quantity",item);self.assertNotIn("cost",item)
            tools.query(evidence_ids=["macro-rate"])
            original=_report(capability="MACRO_CONTEXT")
            draft={k:copy.deepcopy(v) for k,v in original.items() if k in semantic_schema("MACRO_CONTEXT")["properties"]}
            draft.update(calculation_selections=[],document_selections=[])
            draft["claims"][0].pop("calculation_refs");draft["claims"][0]["evidence_refs"]=["macro-rate"]
            draft["observation_conditions"][0]["evidence_refs"]=["macro-rate"]
            result=tools.submit(draft=draft);self.assertTrue(result["accepted"],result)
            report=tools.read_submission(draft_ref=result["draft_ref"])
            scope=build_stage_scope(handoff,gate,stage="MULTI_DIMENSIONAL_HOLDING_RESEARCH")
            coverage=summarize_reports(scope,[report])
            ids={entry["report_id"] for item in coverage["coverage"] for entry in item["capabilities"] if entry["capability"]=="MACRO_CONTEXT"}
            self.assertEqual(ids,{report["report_id"]})
            self.assertFalse(coverage["all_required_reports_saved"])

    def test_complete_eight_dimension_reports_and_auxiliary_failure_preserve_core(self):
        from product.tools.research_scope import RESEARCH_CAPABILITIES
        from product.tools.report_reading import CORE_FORWARD, validate_dependencies
        from product.tools.research_input import research_input_binding
        from tests.test_native_research_reading import complete_gate
        from tests.test_native_research_submission import company_draft
        source, gate = alb_request(), complete_gate()
        reports = []
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            for capability in ("COMPANY_RESEARCH", *RESEARCH_CAPABILITIES):
                dependencies = [r for r in reports if r["capability"] == "FUNDAMENTAL_EVENT"] if capability == "RESEARCH_REPORT" else []
                task = prepare_task(root/capability, research_input=source, gate=gate, security_id=SECURITY,
                                    capability=capability, benchmark_id="US:SPY", dependency_reports=dependencies)
                tools = ResearchTools(root/capability, access_token=task["access_token"])
                if capability == "COMPANY_RESEARCH":
                    tools.query(evidence_ids=["ev-revenue"])
                    draft = company_draft()
                else:
                    old = _report(capability=capability, status="SOURCE_LIMITED", evaluation_status="SOURCE_LIMITED")
                    draft = {k: copy.deepcopy(v) for k, v in old.items() if k in semantic_schema(capability)["properties"]}
                    draft.update(claims=[], observation_conditions=[], calculation_selections=[], document_selections=[],
                                 data_gaps=[{"gap_id": "synthetic-gap", "reason_code": "SOURCE_LIMITED", "description": "合成夹具不证明研究充分性", "impact": "保持来源限制"}])
                result = tools.submit(draft=draft)
                self.assertTrue(result["accepted"], (capability, result))
                reports.append(tools.read_submission(draft_ref=result["draft_ref"]))
            scope = build_stage_scope(source, gate, stage="MULTI_DIMENSIONAL_HOLDING_RESEARCH")
            self.assertTrue(summarize_reports(scope, reports)["all_required_reports_saved"])
            partial = [r for r in reports if r["capability"] != "OPTIONS_FLOW"]
            result = summarize_reports(scope, partial)
            self.assertFalse(result["all_required_reports_saved"])
            self.assertEqual(len([c for c in result["coverage"][0]["capabilities"] if c["report_id"]]), 8)
            core = [r for r in partial if r["capability"] in CORE_FORWARD]
            self.assertEqual(len(core), 6)
            # Auxiliary failure does not alter a valid core or grant CIO without independent counter evidence.
            with self.assertRaisesRegex(ValueError, "DEPENDENCY_MISSING"):
                validate_dependencies(core, capability="RESEARCH_SYNTHESIS", input_binding=research_input_binding(source),
                                      gate_hash=gate["bundle_hash"], security_id=SECURITY, cutoff=AT)
            with self.assertRaisesRegex(ValueError, "REPORT_OUTSIDE_STAGE"):
                summarize_reports(build_stage_scope(source, gate, stage="COMMON_STOCK_RESEARCH"), reports)

    def test_peer_candidate_is_not_fact_until_selected_and_original_materializer_freezes_it(self):
        source=alb_request();gate=frozen_gate()
        rows=[]
        for symbol in ("ALB","PEER1"):
            rows.append({"symbol":symbol,"name":symbol,"market_cap":"100","country":"United States","ipo_year":2000,
                         "sector":"Synthetic Sector","industry":"Synthetic Industry","source_id":"nasdaq-screener",
                         "as_of":AT,"retrieved_at":AT,"raw_content_hash":"a"*64})
        universe={"schema_version":"live-universe/1.0.0","provider":"nasdaq","source_id":"nasdaq-screener",
                  "source_locator":"https://api.nasdaq.com/api/screener/stocks","request_started_at":AT,"as_of":AT,
                  "retrieved_at":AT,"completeness":"COMPLETE","rows":rows,"snapshot_hash":canonical_hash({"rows":rows,"as_of":AT})}
        pool=build_peer_candidate_pool([{"security_id":SECURITY,"ticker":"ALB"}],universe=universe)
        peer={"evidence_id":"peer-revenue","security_id":"US:COMMON_STOCK:PEER1","semantic_field":"revenue","value":"80","unit":"USD",
              "source_id":"synthetic-sec","source_type":"sec","as_of":AT,"retrieved_at":AT}
        gate["allowed_evidence"].append(peer);gate["allowed_evidence_ids"].append(peer["evidence_id"])
        gate["bundle_hash"]=legacy_envelope_hash(gate,hash_field="bundle_hash")
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root=Path(temp)
            task=prepare_task(root/"peer-selection",research_input=source,gate=gate,security_id=SECURITY,
                              capability="PEER_SELECTION",peer_candidate_pool=pool)
            tools=ResearchTools(root/"peer-selection",access_token=task["access_token"])
            candidate=tools.context()["peer_candidates"][0]
            self.assertEqual(candidate["candidate_status"],"UNVERIFIED")
            draft={"status":"READY","summary":"选择合成同业候选，不作事实升级。","query_intents":[],
                   "selections":[{"candidate_id":candidate["candidate_id"],"document_id":None,"rationale":"合成可比性选择，仅验证数据接缝。"}],"gaps":[]}
            saved=tools.submit(draft=draft);self.assertTrue(saved["accepted"],saved)
            access=root/"access.json";access.write_text(json.dumps([{"operator_approval":{"record":{"scope":{"max_positions":3}}}}]))
            collector=Mock(side_effect=AssertionError("Already frozen peer must not be recollected"))
            material=materialize_peer_selection(tools,draft_ref=saved["draft_ref"],output_dir=root/"materialized",
                source_access_path=access,cache_root=root/"cache",sec_user_agent="synthetic",collector=collector)
            self.assertEqual(material["materialization"]["status"],"FROZEN")
            collector.assert_not_called()
            final=json.loads((root/"materialized/data/gate.json").read_text())
            task2=prepare_task(root/"industry",research_input=source,gate=final,security_id=SECURITY,capability="INDUSTRY_COMPARISON",
                               peer_materialization=material["materialization"])
            industry=ResearchTools(root/"industry",access_token=task2["access_token"])
            self.assertIn("peer-revenue",industry.context()["allowed_evidence_ids"])
            self.assertEqual(industry.query(evidence_ids=["peer-revenue"])["evidence"][0],peer)
