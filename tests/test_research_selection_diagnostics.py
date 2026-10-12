"""计算选择的真实装配、结构诊断与模型视图；不模拟宿主执行或研究质量。"""
import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from product.runtime.calculation_handoff import (
    assemble_calculation_selections, build_calculation_catalog, model_calculation_catalog,
    semantic_selection_draft_schema,
)
from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_stage import (
    MINIMUM_QUESTIONS,
    prepare_multidimensional_stage_run, build_multidimensional_dispatch_packet,
    serialize_multidimensional_initial_context, serialize_multidimensional_model_context,
)
from product.runtime.schema_validation import schema_issue_locations, validate_schema_instance
from product.tools.revision import _apply, located_paths
from tests import test_multidimensional_stage as fixtures
from tests import test_calculation_handoff as calculations
from tests.test_common_stock_research_contracts import gate_for, stock_handoff


class ResearchSelectionDiagnosticsTests(unittest.TestCase):
    helper = fixtures.MultidimensionalStageTests()

    def test_readable_prepared_aliases_are_exact_bound_rows_and_old_profile_stays_hashed(self):
        from product.runtime.calculation_handoff import (
            _put, require_current_selection_transport, validate_semantic_selection_draft,
        )
        for capability in ("TECHNICAL_STRUCTURE", "MARKET_STATE"):
            with self.subTest(capability=capability), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory), capability=capability, long_history=True)
                original = copy.deepcopy(packet)
                catalog = build_calculation_catalog(run, packet)
                old = copy.deepcopy(packet)
                old["task"].pop("prepared_result_reference_version")
                legacy = build_calculation_catalog(run, old)
                self.assertTrue(all(ref.startswith("p.") for ref in catalog))
                self.assertTrue(all(ref.startswith("k.") for ref in legacy))
                self.assertEqual(list(catalog.values()), list(legacy.values()))
                vol = next(ref for ref, row in catalog.items()
                           if row["calculation"]["method"] == "annualized_volatility:20_sessions")
                self.assertEqual(vol, "p.annualized_volatility.20_sessions")
                self.assertNotEqual(catalog[vol], catalog["p.latest_volume_ratio.20_sessions"])
                draft = calculations.CalculationHandoffTests().draft(task, vol)
                validate_semantic_selection_draft(draft, packet)
                assembled = assemble_calculation_selections(run, packet, draft)
                self.assertEqual(assembled["calculations"], [catalog[vol]["calculation"]])
                with self.assertRaises(ValueError):
                    validate_semantic_selection_draft(draft, old)
                unknown = copy.deepcopy(draft)
                unknown["calculation_selections"][0]["calculation_ref"] = "p.nonexistent_metric.20_sessions"
                with self.assertRaisesRegex(ValueError, "SELECTION_UNKNOWN"):
                    assemble_calculation_selections(run, packet, unknown)
                index_task = copy.deepcopy(task)
                index_task.pop("prepared_result_reference_version")
                invocation = json.loads((run / task["invocation_path"]).read_text())
                with self.assertRaisesRegex(ValueError, "PREPARED_REFERENCE_BINDING_INVALID"):
                    require_current_selection_transport(packet, invocation, indexed_task=index_task)
                with self.assertRaisesRegex(ValueError, "REFERENCE_COLLISION"):
                    _put(dict(catalog), packet, catalog[vol], "0" * 64)
                illegal = copy.deepcopy(catalog[vol])
                illegal["calculation"]["method"] = "annualized.volatility:20_sessions"
                with self.assertRaisesRegex(ValueError, "REFERENCE_METHOD_INVALID"):
                    _put({}, packet, illegal, "0" * 64)
                for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                    view = json.loads(serialize(packet))
                    rows = view["calculation_selection_contract"]["prepared_results"]
                    self.assertEqual(next(x for x in rows if x["calculation_ref"] == vol)["value"],
                                     catalog[vol]["calculation"]["value"])
                saved, _, _ = self.helper.read_dimension_draft(run, task, draft)
                self.assertEqual(saved["calculations"], assembled["calculations"])
                self.assertEqual(packet, original)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_structural_correction_does_not_ground_an_empty_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            ref = next(iter(build_calculation_catalog(run, packet)))
            draft = calculations.CalculationHandoffTests().draft(task, ref)
            draft["claims"].append({**copy.deepcopy(draft["claims"][0]), "claim_id": "zero_relation"})
            draft["calculation_selections"][0]["calculation_ref"] = "k.scope.scope.invalid"
            original = copy.deepcopy(draft)
            with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                self.helper.read_dimension_draft(run, task, draft)
            corrected = copy.deepcopy(draft)
            corrected["calculation_selections"][0]["calculation_ref"] = ref
            with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CLAIM_UNGROUNDED"):
                self.helper.read_dimension_draft(run, task, corrected)
            corrected["claims"][1]["research_claim_refs"] = ["comparison"]
            report, _, _ = self.helper.read_dimension_draft(run, task, corrected)
            self.assertEqual(report["claims"][1]["research_claim_refs"], ["comparison"])
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
            self.assertEqual(draft, original)
            self.assertFalse((run / "research/reports").exists())

    def test_malformed_claim_id_has_bounded_schema_locations_without_mutation(self):
        for bad_id in ([], {}):
            with self.subTest(bad_id=bad_id), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory))
                ref = next(iter(build_calculation_catalog(run, packet)))
                draft = calculations.CalculationHandoffTests().draft(task, ref)
                draft["claims"][0]["claim_id"] = bad_id
                draft["calculation_selections"][0]["calculation_ref"] = "k.scope.scope.invalid"
                original = copy.deepcopy(draft)
                schema = semantic_selection_draft_schema(packet)
                findings = schema_issue_locations(draft, schema)
                self.assertIn("/claims/0/claim_id", [f["path"] for f in findings])
                self.assertEqual(located_paths(findings), ["/calculation_selections/0", "/claims/0"])
                with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                    validate_schema_instance(draft, schema)
                corrected = copy.deepcopy(draft)
                corrected["claims"][0]["claim_id"] = "comparison"
                corrected["calculation_selections"][0]["calculation_ref"] = ref
                self.helper.read_dimension_draft(run, task, corrected)
                self.assertEqual(draft, original)

    def test_new_questions_and_market_summary_check_reach_views_and_hash_only_new_profile(self):
        from tests.test_research_submission import ResearchSubmissionTests
        from product.runtime.research_submission import BOUNDED_REVISION_VERSION
        baseline = copy.deepcopy(MINIMUM_QUESTIONS)
        for enabled in (False, True):
            for capability in ("FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "MARKET_STATE"):
                with self.subTest(enabled=enabled, capability=capability), tempfile.TemporaryDirectory() as directory:
                    if capability == "RESEARCH_REPORT":
                        _, run, task = ResearchSubmissionTests().prepare(
                            Path(directory), version=BOUNDED_REVISION_VERSION, task_bound_tools=enabled)
                        packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                    else:
                        run, task, packet = self.prepared(Path(directory), enabled=enabled, capability=capability)
                    original = copy.deepcopy(packet)
                    for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                        view = json.loads(serialize(packet))
                        self.assertEqual(view["minimum_questions"], packet["minimum_questions"])
                        if capability == "FUNDAMENTAL_EVENT":
                            self.assertEqual("累计期间的净利润" in view["minimum_questions"][1], enabled)
                            self.assertEqual("一次性处置" in view["minimum_questions"][2], enabled)
                        elif capability == "RESEARCH_REPORT":
                            self.assertEqual("core_statement及每条" in view["minimum_questions"][0], enabled)
                        else:
                            self.assertEqual("定稿summary前回读" in view["instruction"], enabled)
                        if not enabled:
                            self.assertEqual(view["minimum_questions"], baseline[capability])
                    invocation = json.loads((run / task["invocation_path"]).read_text())
                    self.assertEqual(invocation["prompt_hash"], canonical_hash({
                        "instruction": packet["instruction"], "questions": packet["minimum_questions"]}))
                    self.assertEqual(packet, original)
                    self.assertEqual(MINIMUM_QUESTIONS, baseline)

    def test_explicit_selection_patch_preserves_scope_and_revalidates_duplicate_and_null(self):
        # 纯补丁算法向量；显式作用域不代表宿主/服务端已经授予修订权限。
        for scenario in ("save", "duplicate", "null", "outside"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory))
                refs = list(build_calculation_catalog(run, packet))[:3]
                draft = calculations.CalculationHandoffTests().draft(task, refs[0])
                draft["claims"].append({**copy.deepcopy(draft["claims"][0]), "claim_id": "untouched"})
                draft["calculation_selections"] = [
                    {"calculation_ref": "k." + "0" * 12 + ".short", "claim_ids": ["comparison"]},
                    {"calculation_ref": refs[1] + "00", "claim_ids": ["comparison"]},
                    {"calculation_ref": refs[0], "claim_ids": ["comparison"]},
                    {"calculation_ref": refs[2], "claim_ids": ["untouched"]},
                ]
                original = copy.deepcopy(draft)
                allowed = ["/calculation_selections/0", "/calculation_selections/1"]
                changes = [{"op": "remove", "path": "/calculation_selections/0"},
                           {"op": "replace", "path": "/calculation_selections/1/calculation_ref", "value": refs[1]}]
                if scenario == "duplicate":
                    changes[0] = {"op": "replace", "path": "/calculation_selections/0",
                                  "value": {"calculation_ref": refs[0], "claim_ids": ["untouched"]}}
                elif scenario == "null":
                    changes[0] = {"op": "replace", "path": "/calculation_selections/0", "value": None}
                elif scenario == "outside":
                    changes.append({"op": "replace", "path": "/calculation_selections/2/calculation_ref", "value": refs[1]})
                if scenario == "outside":
                    with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE"):
                        _apply(draft, changes, allowed)
                else:
                    corrected = _apply(draft, changes, allowed)
                    if scenario == "save":
                        report, _, _ = self.helper.read_dimension_draft(run, task, corrected)
                        self.assertEqual(len(report["calculations"]), 3)
                        self.assertEqual(report["claims"][1]["statement"], original["claims"][1]["statement"])
                        self.assertEqual(len(report["claims"][0]["calculation_refs"]), 2)
                    else:
                        failure = "SELECTION_DUPLICATE" if scenario == "duplicate" else "SCHEMA_TYPE_INVALID"
                        with self.assertRaisesRegex(ValueError, failure):
                            self.helper.read_dimension_draft(run, task, corrected)
                self.assertEqual(draft, original)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def prepared(self, root, *, enabled=True, capability="TECHNICAL_STRUCTURE", long_history=False):
        handoff, gate = self.helper.mrvl_daily_inputs(include_spy=True)
        if long_history:
            templates = {(f["security_id"], f["semantic_field"]): f for f in gate["allowed_evidence"]
                         if f.get("source_id") == "synthetic-yahoo-daily"}
            gate["allowed_evidence"] = [f for f in gate["allowed_evidence"]
                                        if f.get("source_id") != "synthetic-yahoo-daily"]
            day, days = date(2026, 9, 10), []
            while len(days) < 253:
                if day.weekday() < 5:
                    days.append(day.isoformat())
                day -= timedelta(days=1)
            for i, day in enumerate(reversed(days)):
                for (security, field), template in templates.items():
                    value = 1000 + i * 10 if field == "share_volume" else 100 + i * (2 if security.endswith("MRVL") else 1)
                    gate["allowed_evidence"].append({**template,
                        "evidence_id": f"synthetic-{security}-{day}-{field}", "value": str(value),
                        "as_of": day + "T20:00:00Z", "published_at": day + "T20:00:00Z",
                        "metadata": {"trading_date": day}})
            gate["allowed_evidence_ids"] = sorted(f["evidence_id"] for f in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
        for name, value in (("handoff", handoff), ("gate", gate)):
            (root / (name + ".json")).write_text(json.dumps(value))
        run = root / "run"
        prepare_multidimensional_stage_run(
            fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
            run_dir=run, run_id="selection-diagnostics", model="gpt-6-luna", task_bound_tools=enabled,
        )
        index = json.loads((run / "research/dispatch-index.json").read_text())
        task = next(t for t in index["tasks"] if t["capability"] == capability)
        return run, task, build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_unselected_claim_requires_explicit_grounding_and_keeps_artifact_unchanged(self):
        for fix in (True, False):
            with self.subTest(fix=fix), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory))
                refs = list(build_calculation_catalog(run, packet))[:3]
                draft = calculations.CalculationHandoffTests().draft(task, refs[0])
                template = draft["claims"][0]
                draft["claims"] = [{**copy.deepcopy(template), "claim_id": f"claim_{i}"} for i in range(4)]
                draft["calculation_selections"] = [
                    {"calculation_ref": ref, "claim_ids": [f"claim_{i}"]} for i, ref in enumerate(refs)
                ]
                snapshot = canonical_hash(draft)
                artifact = run / packet["prepared_analysis"]["calculation_ref"]
                frozen = artifact.read_bytes()
                with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CLAIM_UNGROUNDED"):
                    self.helper.read_dimension_draft(run, task, draft)
                corrected = copy.deepcopy(draft)
                if fix:
                    corrected["claims"][3]["research_claim_refs"] = ["claim_0"]
                    report, _, _ = self.helper.read_dimension_draft(run, task, corrected)
                    self.assertEqual(report["claims"][3]["research_claim_refs"], ["claim_0"])
                    for i in range(3):
                        self.assertEqual(len(report["claims"][i]["calculation_refs"]), 1)
                        self.assertEqual(report["claims"][i]["statement"], draft["claims"][i]["statement"])
                else:
                    corrected["claims"][3]["statement"] = "只改正文仍无依据。"
                    with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CLAIM_UNGROUNDED"):
                        self.helper.read_dimension_draft(run, task, corrected)
                self.assertEqual(canonical_hash(draft), snapshot)
                self.assertEqual(artifact.read_bytes(), frozen)

    def test_unknown_calculation_is_not_treated_as_grounding(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            draft = calculations.CalculationHandoffTests().draft(task, "k." + "0" * 12 + "." + "0" * 24)
            with self.assertRaisesRegex(ValueError, "SELECTION_UNKNOWN"):
                self.helper.read_dimension_draft(run, task, draft)
            self.assertFalse((run / "research/reports").exists())

    def test_author_selected_return_windows_assemble_exactly_without_inferred_support(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory), long_history=True)
            catalog = model_calculation_catalog(run, packet)
            methods = {f"{metric}:{window}_sessions" for metric in (
                "security_total_return", "benchmark_total_return", "relative_return")
                for window in (20, 60, 252)}
            chosen = [x for x in catalog if x["method"] in methods]
            self.assertEqual({x["method"] for x in chosen}, methods)
            draft = calculations.CalculationHandoffTests().draft(task, chosen[0]["calculation_ref"])
            claim = draft["claims"][0]
            claim["statement"] = "；".join(f"{x['method']}原比例={x['value']}" for x in chosen)
            draft["calculation_selections"] = [{"calculation_ref": x["calculation_ref"],
                                                 "claim_ids": [claim["claim_id"]]} for x in chosen]
            before = copy.deepcopy(draft)
            result = assemble_calculation_selections(run, packet, draft)
            self.assertEqual({x["method"] for x in result["calculations"]}, methods)
            self.assertEqual(len(result["claims"][0]["calculation_refs"]), len(methods))
            self.assertEqual(result["claims"][0]["statement"], claim["statement"])
            self.assertEqual(draft, before)
            # 不扫描正文补选择；未选结果不自动加入。
            draft["calculation_selections"] = draft["calculation_selections"][:-3]
            partial = assemble_calculation_selections(run, packet, draft)
            self.assertEqual(len(partial["calculations"]), 6)
            self.assertEqual(partial["claims"][0]["statement"], claim["statement"])
            self.assertEqual(len(partial["claims"][0]["calculation_refs"]), 6)

    def test_options_existing_time_selection_guidance_reaches_both_views_only_new_profile(self):
        baseline = copy.deepcopy(MINIMUM_QUESTIONS)
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory), enabled=enabled, capability="OPTIONS_FLOW")
                original = copy.deepcopy(packet)
                for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                    view = json.loads(serialize(packet))
                    self.assertEqual("报价身份问题须呈现" in view["instruction"], enabled)
                    self.assertEqual("同一合约两供应商" in view["instruction"], enabled)
                    self.assertEqual("查询同身份OpenD合约报价及风险补源" in view["instruction"], enabled)
                    questions = view["minimum_questions"]
                    self.assertEqual("contract_multiplier/contract_size" in questions[1], enabled)
                    self.assertEqual("单位未知须说明" in questions[1], enabled)
                    self.assertEqual(questions, packet["minimum_questions"])
                    if not enabled:
                        self.assertEqual(questions, baseline["OPTIONS_FLOW"])
                    self.assertEqual(packet, original)
                invocation = json.loads((run / task["invocation_path"]).read_text())
                self.assertEqual(invocation["prompt_hash"], canonical_hash({
                    "instruction": packet["instruction"], "questions": packet["minimum_questions"]}))
                self.assertEqual(MINIMUM_QUESTIONS, baseline)

    def test_selected_contract_supplement_is_queryable_and_time_binding_does_not_erase_risk(self):
        # 合成事实经真实查询和业务装配，不生成Hook或宿主作者证明。
        for query_quote in (True, False):
            with self.subTest(query_quote=query_quote), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                handoff = stock_handoff(1)
                gate = gate_for(handoff)
                common = {"security_id": "US:COMMON_STOCK:AAPL", "dataset": "options_snapshot",
                          "source_type": "SECONDARY_VENDOR", "source_id": "moomoo-opend",
                          "as_of": "2026-09-10T19:30:00Z", "retrieved_at": "2026-09-11T09:00:00Z"}
                quote = {**common, "evidence_id": "synthetic-opend-quote", "semantic_field": "moomoo_option_quote:contract",
                         "value": {"contract_symbol": "US.AAPL261218P150000", "bid": "4.0", "ask": "4.5"}}
                yahoo = {**common, "source_id": "yahoo-options", "evidence_id": "synthetic-yahoo-quote",
                         "semantic_field": "yahoo_option_quote:contract",
                         "as_of": "2026-09-10T19:40:00Z",
                         "value": {"contract_symbol": "AAPL261218P00150000", "bid": "4.1", "ask": "4.6"}}
                risk = {**common, "evidence_id": "synthetic-opend-risk", "semantic_field": "moomoo_option_risk:contract",
                        "value": {"contract_symbol": "US.AAPL261218P150000", "delta": -0.4, "gamma": 0.01,
                                  "theta": -0.2, "vega": 0.3, "rho": -0.1, "iv": 0.6, "oi": 100,
                                  "multiplier": 100, "vintage_status": "UNKNOWN"}}
                gate["allowed_evidence"].extend([quote, risk, yahoo])
                for key in ("input_evidence_ids", "allowed_evidence_ids"):
                    gate[key] = sorted([*gate[key], quote["evidence_id"], risk["evidence_id"], yahoo["evidence_id"]])
                gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                for name, value in (("handoff", handoff), ("gate", gate)):
                    (root / (name + ".json")).write_text(json.dumps(value))
                run = root / "run"
                prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                                                  run_dir=run, run_id="options-supplement", model="gpt-6-luna", task_bound_tools=True)
                task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                            if t["capability"] == "OPTIONS_FLOW")
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                refs = {v: k for k, v in packet["reference_map"]["evidence"].items()}
                quote_ref, risk_ref, yahoo_ref = refs[quote["evidence_id"]], refs[risk["evidence_id"]], refs[yahoo["evidence_id"]]
                tool = StatelessFixtureTools(default_run_dir=run)
                result = tool.query(**tool.bind_task_tool_arguments("query", {"task_name": task["task_name"],
                                    "evidence_ids": [yahoo_ref, quote_ref, risk_ref] if query_quote else [yahoo_ref, risk_ref]}))
                _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
                returned_risk = next(f for f in result["evidence"] if f["evidence_id"] == risk_ref)
                self.assertEqual(returned_risk["value"], risk["value"])
                self.assertEqual(next(f for f in result["evidence"] if f["evidence_id"] == yahoo_ref)["value"], yahoo["value"])
                if query_quote:
                    returned_quote = next(f for f in result["evidence"] if f["evidence_id"] == quote_ref)
                    self.assertEqual(returned_quote["value"], quote["value"])
                    self.assertEqual(returned_quote["as_of"], quote["as_of"])
                draft = self.helper.dimension_draft(task)
                draft["claims"] = [{"claim_id": "contract", "question": "同合约报价与风险？", "kind": "FACT",
                    "statement": "所选P150合约OpenD报价4.0/4.5，{{sf.quote}}；Yahoo4.1/4.6为另一时点快照，不合并为同步同源；risk原delta=-0.4，gamma=0.01，theta=-0.2，vega=0.3，rho=-0.1，IV=0.6，OI=100，乘数100；风险vintage未知，不是字段不存在。",
                    "evidence_refs": [yahoo_ref, quote_ref, risk_ref], "research_claim_refs": [], "document_refs": [], "assumption_ids": []}]
                draft["source_literal_selections"] = [{"claim_id": "contract", "placeholder": "{{sf.quote}}",
                                                       "evidence_ref": quote_ref, "field": "as_of"}]
                before = copy.deepcopy(draft)
                if query_quote:
                    report, _, _ = self.helper.read_dimension_draft(run, task, draft)
                    self.assertIn("as_of=2026-09-10T19:30:00Z", report["claims"][0]["statement"])
                    self.assertIn("风险vintage未知，不是字段不存在", report["claims"][0]["statement"])
                    self.assertEqual(report["claims"][0]["evidence_refs"], [yahoo["evidence_id"], quote["evidence_id"], risk["evidence_id"]])
                else:
                    with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                        self.helper.read_dimension_draft(run, task, draft)
                self.assertEqual(draft, before)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_dynamic_calculation_direct_fact_inputs_keep_original_joint_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = calculations.CalculationHandoffTests()
            run, task, packet = helper.prepared(Path(directory))
            result = helper.successful_ratio(run, task, packet)
            draft = helper.draft(task, result["calculation_ref"])
            draft["claims"].append({**copy.deepcopy(draft["claims"][0]), "claim_id": "missing"})
            self.assertFalse(task["allowed_calculation_evidence_ids"])
            original = copy.deepcopy(draft)
            with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CLAIM_UNGROUNDED"):
                self.helper.read_dimension_draft(run, task, draft)
            draft["claims"][1]["research_claim_refs"] = ["comparison"]
            report, _, _ = self.helper.read_dimension_draft(run, task, draft)
            self.assertEqual(report["claims"][0]["calculation_refs"], [result["calculation_id"]])
            self.assertEqual(original["claims"][1]["research_claim_refs"], [])
            self.assertFalse((run / "research/reports").exists())

    def test_both_model_views_pair_results_without_mutating_artifacts_or_old_profile(self):
        for enabled in (True, False):
            for capability in ("TECHNICAL_STRUCTURE", "MARKET_STATE"):
                with self.subTest(enabled=enabled, capability=capability), tempfile.TemporaryDirectory() as directory:
                    run, task, packet = self.prepared(Path(directory), enabled=enabled, capability=capability)
                    original = copy.deepcopy(packet)
                    raw = (run / packet["prepared_analysis"]["calculation_ref"]).read_bytes()
                    expected = model_calculation_catalog(run, packet)
                    for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                        view = json.loads(serialize(packet))
                        calc = view["prepared_analysis"]["calculation"]
                        results = view["calculation_selection_contract"]["prepared_results"]
                        self.assertEqual({x["calculation_ref"]: x for x in results},
                                         {x["calculation_ref"]: x for x in expected})
                        for actual, source in zip(calc["windows"], packet["prepared_analysis"]["calculation"]["windows"]):
                            if enabled:
                                self.assertNotIn("metrics", actual)
                                self.assertEqual(actual, {k: v for k, v in source.items() if k != "metrics"})
                            else:
                                self.assertEqual(actual, source)
                        if enabled:
                            self.assertEqual(calc["metrics_view"], "calculation_selection_contract.prepared_results")
                            self.assertEqual(results, sorted(expected, key=lambda x: (
                                x["method"].partition(":")[0], x.get("window_sessions", 0), x["calculation_ref"],
                            )))
                        else:
                            self.assertNotIn("metrics_view", calc)
                            self.assertEqual(results, expected)
                        guide = view["calculation_selection_contract"]["instruction"]
                        self.assertEqual("分别核对security_total_return" in guide,
                                         enabled and capability == "TECHNICAL_STRUCTURE")
                        self.assertEqual("收益、年化波动率和回撤" in guide,
                                         enabled and capability == "MARKET_STATE")
                        self.assertEqual(packet, original)
                        self.assertEqual((run / packet["prepared_analysis"]["calculation_ref"]).read_bytes(), raw)
