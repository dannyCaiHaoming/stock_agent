"""原生资料准备与正式任务隔离；仅替代外部HTTP transport，不启动模型。"""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.public_research import OpenAlexResearchClient
from product.mcp.live.sec_client import Response
from product.tools.research import prepare_task, ResearchTools
from tests.test_native_research_tools import SECURITY, frozen_gate, AT
from tests.test_single_stock_input import alb_request

ROOT=Path(__file__).resolve().parents[1]


class NativeResearchMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root=Path(self.tmp.name)
        self.calls=[]
        policy=json.loads((ROOT/"product/mcp/live/research-source-policy.json").read_text())["sources"]["openalex"]
        def transport(request, *, max_bytes):
            self.calls.append(request.full_url)
            if request.full_url.startswith("https://api.openalex.org/"):
                raw=json.dumps({"results":[{"id":"https://openalex.org/W123","title":"Synthetic research",
                    "publication_date":"2026-02-01","authorships":[],"primary_location":{},
                    "content_urls":{"grobid_xml":"https://content.openalex.org/works/W123.grobid-xml"}}]}).encode()
            else:
                raw=b'<TEI><text><body><div><head>Business</head><p>Synthetic source text only.</p></div></body></text></TEI>'
            return Response(status=200,body=raw)
        self.client=OpenAlexResearchClient(policy,SnapshotCache(self.root/"cache"),api_key="SYNTHETIC_TEST_KEY",transport=transport,now=lambda: __import__('datetime').datetime.fromisoformat(AT.replace('Z','+00:00')))

    def tearDown(self):
        self.tmp.cleanup()

    def tools(self,kind,authorized=True):
        root=self.root/kind.lower()
        prepared=prepare_task(root,research_input=alb_request(),gate=frozen_gate(),security_id=SECURITY,
                              capability=kind,public_research_authorized=authorized)
        tools=ResearchTools(root,access_token=prepared["access_token"])
        tools.material_client=self.client
        return tools

    def test_actual_search_fetch_normalize_and_select_without_transcribing_metadata(self):
        tools=self.tools("RESEARCH_REPORT_DISCOVERY")
        search=tools.search(query="synthetic business")
        self.assertEqual(search["status"],"COMPLETED")
        candidate=search["result"]["candidates"][0]
        self.assertEqual(candidate["verification_status"],"LEAD_ONLY")
        fetched=tools.fetch(candidate_id=candidate["candidate_id"])
        document=fetched["result"]
        self.assertEqual(document["verification_status"],"BODY_VERIFIED")
        draft={"status":"READY","summary":"已取得合成正文，仅验证业务接缝。",
               "query_intents":[{"query":"synthetic business","purpose":"核对正文"}],
               "selections":[{"candidate_id":candidate["candidate_id"],"document_id":document["document_id"],"rationale":"选择实际取得正文"}],"gaps":[]}
        result=tools.submit(draft=draft)
        self.assertTrue(result["accepted"],result)
        report=tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["material_support"]["documents"],[document])
        self.assertEqual(len(report["material_support"]["attempts"]),2)
        self.assertEqual(report["host_execution"],"UNVERIFIED")
        self.assertNotIn("SYNTHETIC_TEST_KEY",json.dumps(report))

    def selected_document(self, kind="RESEARCH_REPORT_DISCOVERY"):
        tools = self.tools(kind)
        searched = tools.search(query="synthetic business")
        candidate = searched["result"]["candidates"][0]
        document = tools.fetch(candidate_id=candidate["candidate_id"])["result"]
        saved = tools.submit(draft={"status": "READY", "summary": "合成正文。",
            "query_intents": [{"query": "synthetic business", "purpose": "正文核对"}],
            "selections": [{"candidate_id": candidate["candidate_id"], "document_id": document["document_id"], "rationale": "实际正文"}], "gaps": []})
        self.assertTrue(saved["accepted"], saved)
        return tools.read_submission(draft_ref=saved["draft_ref"])

    def test_selected_preparation_body_can_be_frozen_read_and_consumed_by_formal_task(self):
        from product.tools.documents import preparation_documents
        from product.tools.research_input import research_input_binding
        from product.tools.report_contracts import semantic_schema
        from product.tools.report_submission import _expand_choices
        from tests.test_multidimensional_research_contracts import _report
        report = self.selected_document()
        source, gate = alb_request(), frozen_gate()
        documents = preparation_documents([report], capability="RESEARCH_REPORT",
            input_binding=research_input_binding(source), gate_hash=gate["bundle_hash"], security_id=SECURITY, cutoff=AT)
        prepared = prepare_task(self.root/"formal-macro", research_input=source, gate=gate,
            security_id=SECURITY, capability="MACRO_CONTEXT", allowed_documents=documents)
        formal = ResearchTools(self.root/"formal-macro", access_token=prepared["access_token"])
        context = formal.context()
        self.assertNotIn("document_bodies", context)
        self.assertNotIn("sections", context["allowed_documents"][0])
        old = _report(capability="MACRO_CONTEXT")
        draft = {k: v for k, v in old.items() if k in semantic_schema("MACRO_CONTEXT")["properties"]}
        draft.update(calculation_selections=[], document_selections=[documents[0]["document_id"]])
        draft["claims"][0].pop("calculation_refs", None)
        with self.assertRaisesRegex(ValueError, "DOCUMENT_NOT_READ"):
            _expand_choices(formal, draft)
        read = formal.read_documents(document_ids=draft["document_selections"])
        self.assertEqual(read["documents"][0]["sections"], documents[0]["sections"])
        expanded, _ = _expand_choices(formal, draft)
        self.assertEqual(expanded["documents"], context["allowed_documents"])
        draft["claims"][0]["evidence_refs"] = []
        draft["claims"][0]["document_refs"] = draft["document_selections"]
        draft["observation_conditions"][0]["evidence_refs"] = []
        submitted = formal.submit(draft=draft)
        self.assertTrue(submitted["accepted"], submitted)
        self.assertEqual(formal.read_submission(draft_ref=submitted["draft_ref"])["research"]["documents"], context["allowed_documents"])
        self.assertNotIn("search", context["permissions"])
        with self.assertRaisesRegex(ValueError, "DOCUMENT_NOT_ALLOWED"):
            formal.read_documents(document_ids=["other-body"])

    def test_latest_material_receipt_refreezes_common_input_and_routes_body_without_metadata_copy(self):
        from product.tools.material_preparation import freeze_material_inputs
        from product.tools.research_connection import prepare_connection, ResearchConnection
        from product.runtime.hashing import legacy_envelope_hash
        from product.mcp.research import dispatch
        self.selected_document("MACRO_RESEARCH_DISCOVERY")
        root = self.root/"macro_research_discovery"
        access = json.loads((root/"access.json").read_text())
        record = json.loads((root/"submissions/1.json").read_text())
        tools = ResearchTools(root, access_token=access["token"])
        gate = frozen_gate()
        from datetime import datetime, timedelta
        gate["decision_cutoff"] = (datetime.fromisoformat(AT.replace("Z", "+00:00")) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        bundle = freeze_material_inputs([(tools, record["draft_ref"])], final_gate=gate)
        self.assertEqual(bundle["input"]["preparation_request_hash"], alb_request()["request_hash"])
        connection = prepare_connection(self.root/"formal", research_input=bundle["input"], gate=gate,
                                        role="runtime_market_catalyst", material_inputs=bundle)
        routed = ResearchConnection(self.root/"formal", connection_token=connection["connection_token"])
        response = dispatch(routed, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_prepare_task", "arguments": {"security_id": SECURITY, "capability": "MACRO_CONTEXT"}}})
        self.assertFalse(response["result"]["isError"], response)
        grant = json.loads(response["result"]["content"][0]["text"])
        formal = routed.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        self.assertEqual(formal.context()["decision_cutoff"], gate["decision_cutoff"])
        self.assertEqual(formal.read_documents(document_ids=[grant["task"]["allowed_documents"][0]["document_id"]])["documents"][0]["sections"],
                         record["report"]["material_support"]["documents"][0]["sections"])
        with self.assertRaisesRegex(ValueError, "CONTEXT_ISOLATION_VIOLATION"):
            prepare_connection(self.root/"skeptic", research_input=bundle["input"], gate=gate,
                               role="runtime_skeptic", material_inputs=bundle)

    def test_material_configuration_failure_cannot_become_formal_body_source(self):
        from product.tools.documents import preparation_documents
        from product.tools.research_input import research_input_binding
        tools = self.tools("MACRO_RESEARCH_DISCOVERY")
        tools.material_client.api_key = None
        result = tools.search(query="macro test")
        tools.fetch(candidate_id=result["result"]["candidates"][0]["candidate_id"])
        saved = tools.submit(draft={"status": "BLOCKED_CONFIGURATION", "summary": "缺正文凭证。",
            "query_intents": [{"query": "macro test", "purpose": "正文"}], "selections": [],
            "gaps": [{"reason_code": "PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED", "description": "缺凭证", "impact": "不能取正文"}]})
        report = tools.read_submission(draft_ref=saved["draft_ref"])
        with self.assertRaisesRegex(ValueError, "DEPENDENCY_BLOCKED_CONFIGURATION"):
            preparation_documents([report], capability="MACRO_CONTEXT", input_binding=research_input_binding(alb_request()),
                gate_hash=frozen_gate()["bundle_hash"], security_id=SECURITY, cutoff=AT)

    def test_bodyless_or_future_document_is_rejected_before_task_creation(self):
        import copy
        document = self.selected_document()["material_support"]["documents"][0]
        for mutation, code in (({"sections": []}, "BODY_REQUIRED"), ({"retrieved_at": "2027-01-01T00:00:00Z"}, "AFTER_CUTOFF"),
                               ({"security_id": "US:COMMON_STOCK:OTHER"}, "TARGET_INVALID")):
            root = self.root/code
            changed = {**copy.deepcopy(document), **mutation}
            with self.assertRaisesRegex(ValueError, code):
                prepare_task(root, research_input=alb_request(), gate=frozen_gate(), security_id=SECURITY,
                             capability="MACRO_CONTEXT", allowed_documents=[changed])
            self.assertFalse(root.exists())

    def test_large_body_response_is_rejected_without_truncation_or_read_proof(self):
        import copy
        document = copy.deepcopy(self.selected_document()["material_support"]["documents"][0])
        document["sections"][0]["text"] = "资料" * 40000
        prepared = prepare_task(self.root/"large-body", research_input=alb_request(), gate=frozen_gate(),
                                security_id=SECURITY, capability="MACRO_CONTEXT", allowed_documents=[document])
        formal = ResearchTools(self.root/"large-body", access_token=prepared["access_token"])
        with self.assertRaisesRegex(ValueError, "DOCUMENT_RESPONSE_TOO_LARGE"):
            formal.read_documents(document_ids=[document["document_id"]])
        self.assertFalse((formal.root/"tools").exists())
        stored = json.loads((formal.root/"task.json").read_text())
        self.assertEqual(stored["document_bodies"][document["document_id"]][0]["text"], document["sections"][0]["text"])

    def test_formal_company_and_unapproved_preparation_cannot_search(self):
        for kind,authorized in [("COMPANY_RESEARCH",True),("MACRO_RESEARCH_DISCOVERY",False)]:
            tools=self.tools(kind,authorized)
            with self.assertRaisesRegex(ValueError,"SOURCE_ACCESS_FORBIDDEN"):
                tools.search(query="synthetic")
            self.assertFalse((tools.root/"materials").exists())
        self.assertEqual(self.calls,[])

    def test_unknown_candidate_does_not_trigger_http(self):
        tools=self.tools("MARKET_RESEARCH_DISCOVERY")
        with self.assertRaisesRegex(ValueError,"CANDIDATE_NOT_OBSERVED"):
            tools.fetch(candidate_id="another-task-candidate")
        self.assertEqual(self.calls,[])

    def test_missing_content_key_retains_configuration_failure_not_source_absence(self):
        tools=self.tools("MACRO_RESEARCH_DISCOVERY")
        tools.material_client.api_key=None
        result=tools.search(query="macro test")
        fetched=tools.fetch(candidate_id=result["result"]["candidates"][0]["candidate_id"])
        self.assertEqual(fetched["status"],"BLOCKED_CONFIGURATION")
        draft={"status":"BLOCKED_CONFIGURATION","summary":"缺正文凭证。",
               "query_intents":[{"query":"macro test","purpose":"核对宏观材料"}],"selections":[],
               "gaps":[{"reason_code":"PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED","description":"已尝试但缺正文凭证。","impact":"不能取得正文。"}]}
        saved=tools.submit(draft=draft)
        self.assertTrue(saved["accepted"],saved)
        self.assertEqual(len(tools.read_submission(draft_ref=saved["draft_ref"])["material_support"]["attempts"]),2)
        self.assertEqual(len(self.calls),1)

    def test_persisted_search_limit_prevents_reset_by_new_client(self):
        tools=self.tools("RESEARCH_REPORT_DISCOVERY")
        for index in range(3):
            self.assertEqual(tools.search(query=f"synthetic {index}")["status"],"COMPLETED")
        self.client.search_count=0
        with self.assertRaisesRegex(ValueError,"REQUEST_BUDGET_EXHAUSTED"):
            tools.search(query="fourth")
        self.assertEqual(len(self.calls),3)

    def test_title_cannot_be_selected_as_body(self):
        tools=self.tools("MARKET_RESEARCH_DISCOVERY")
        search=tools.search(query="market test")
        candidate=search["result"]["candidates"][0]
        draft={"status":"READY","summary":"错误地只选标题。","query_intents":[{"query":"market test","purpose":"测试"}],
               "selections":[{"candidate_id":candidate["candidate_id"],"document_id":"fake-body","rationale":"测试错误"}],"gaps":[]}
        result=tools.submit(draft=draft)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["validation_error"],"RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID")
