from __future__ import annotations

import json
import copy
import subprocess
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from product.runtime.codex_hook_recorder import (
    handle_hook_event, _multidimensional_repair_packet, _terminal_research_tasks,
    _multidimensional_draft_diagnostics, _validate_multidimensional_tool_calculations,
    _validate_multidimensional_calculation_structure,
    _industry_source_identity_copy_paths, _bind_source_literal_selections,
)
from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.council.multidimensional_research import envelope_research_dimension_draft
from product.council.multidimensional_research import MultiDimensionalResearchError
from product.runtime.multidimensional_stage import (
    DISPATCH_VERSION,
    STAGE_VERSION,
    _bounded_latest_facts,
    _latest_annual_eps_focus,
    _same_period_profit_cash_focus,
    _latest_insider_trade_focus,
    _sec_revenue_table_unit_focus,
    _load_research_capture_batches,
    _facts_for_capability,
    _capability_routing_coverage,
    _task_provider_coverage_view,
    _dynamic_draft_schema,
    _adopt_multidimensional_retry,
    _parent_output_schema,
    build_multidimensional_dispatch_packet,
    build_multidimensional_stage_prompt,
    build_multidimensional_task_prompt,
    assemble_canonical_holding_research_package,
    check_multidimensional_bundle_consumable,
    finalize_multidimensional_task_evidence,
    finalize_multidimensional_stage_run,
    serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context,
    launch_multidimensional_stage,
    prepare_multidimensional_stage_run,
    MultidimensionalStageError,
)
from product.runtime.multidimensional_stage import _frozen_peer_candidates, _issuer_document_title
from product.runtime.common_stock_stage import prepare_common_stock_stage_run
from product.council.research_output import persist_equity_research_report
from product.council.multidimensional_output import persist_dimension_report
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.multidimensional_references import translate_references
from product.deterministic.market_analysis import verify_technical_calculation
from product.runtime.validation import ArtifactValidationError, validate_evidence_closure
from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.mcp.provenance import content_hash
from tests.test_common_stock_research_contracts import gate_for, stock_handoff, valid_report
from product.intake import build_handoff, build_manual_draft


ROOT = Path(__file__).resolve().parents[1]


class MultidimensionalStageTests(unittest.TestCase):
    def test_agent_and_skill_versions_use_current_approved_manifest(self) -> None:
        from product.runtime.multidimensional_stage import _agent_binding, _skill_binding

        manifest = json.loads((ROOT / "product/version-manifest.json").read_text(encoding="utf-8"))
        product = ROOT / "product"
        market = _agent_binding(product, "runtime_market_catalyst")
        self.assertEqual(market["version"], manifest["agents"]["runtime-market-catalyst"])
        skill = _skill_binding(product, "options-market-structure")
        self.assertEqual(skill["version"], manifest["skills"]["options-market-structure"])

        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp)
            shutil.copy2(product / "version-manifest.json", copied / "version-manifest.json")
            target = copied / "skills/options-market-structure/SKILL.md"
            target.parent.mkdir(parents=True)
            source = product / "skills/options-market-structure/SKILL.md"
            target.write_text(
                source.read_text(encoding="utf-8").replace(
                    f'version: "{skill["version"]}"', 'version: "0.0.0"', 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MultidimensionalStageError, "MULTIDIMENSIONAL_SKILL_VERSION_DRIFT"):
                _skill_binding(copied, "options-market-structure")

    def test_calculation_shape_precedes_receipt_lineage_without_rewriting_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            invocation = json.loads((run / task["invocation_path"]).read_text())
            packet = json.loads((run / task["packet_path"]).read_text())
            ids = ["ev-aapl-revenue", "ev-aapl-cash"]
            tool = StatelessFixtureTools(default_run_dir=run)
            tool.query(run_id=task["run_id"], agent=task["agent"],
                       invocation_id=task["invocation_id"], evidence_ids=ids)
            result = tool.calculate(run_id=task["run_id"], agent=task["agent"],
                                    invocation_id=task["invocation_id"],
                                    calculation_id="shape-before-lineage", operation="ratio",
                                    evidence_ids=ids)
            _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
            draft = self.dimension_draft(task)
            draft["calculations"] = [{
                "calculation_id": result["calculation_id"], "method": "ratio",
                "result": result["value"], "unit": "ratio",
                "evidence_refs": ids, "artifact_ref": result["artifact_ref"],
            }]
            draft["artifact_refs"] = [result["artifact_ref"]]
            original = copy.deepcopy(draft)
            environment = self.targeted_environment(run, task)
            parent, child = "parent-malformed-calculation", "child-malformed-calculation"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            blocked, _ = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(blocked["hook_event_name"], "SubagentStopBlocked")
            code = blocked["output_capture"]["failure_code"]
            self.assertIn("SCHEMA_EXTRA_PROPERTY", code)
            # 当前作者不能抄写完整计算。历史正式对象仍先检查结构再验血缘。
            with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING.*calculations"):
                _validate_multidimensional_calculation_structure(draft, packet=packet)
            self.assertEqual(draft, original)
            self.assertTrue((run / result["artifact_ref"]).is_file())
            corrected = copy.deepcopy(draft)
            corrected["calculations"][0]["value"] = corrected["calculations"][0].pop("result")
            corrected["calculations"][0]["input_evidence_refs"] = corrected["calculations"][0].pop("evidence_refs")
            _validate_multidimensional_calculation_structure(corrected, packet=packet)
            _validate_multidimensional_tool_calculations(
                corrected, task=task, invocation=invocation, run_dir=run,
            )

    def test_option_quote_literal_reaches_real_hook_and_final_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            quote = {
                "evidence_id": "ev-aapl-option-quote", "security_id": "US:COMMON_STOCK:AAPL",
                "semantic_field": "moomoo_option_quote:contract", "dataset": "options_snapshot",
                "source_type": "SECONDARY_VENDOR", "source_id": "moomoo-opend",
                "as_of": "2026-09-10T19:58:46Z", "retrieved_at": "2026-09-11T09:00:00Z",
                "value": {"bid": "5.35", "ask": "5.55", "contract_symbol": "US.AAPL261002C270000"},
            }
            gate["allowed_evidence"].append(quote)
            gate["input_evidence_ids"].append(quote["evidence_id"])
            gate["allowed_evidence_ids"].append(quote["evidence_id"])
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff))
            gate_path.write_text(json.dumps(gate))
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="option-literal-hook", model="gpt-5.6-terra",
            )
            task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                        if t["capability"] == "OPTIONS_FLOW")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            short = next(k for k, v in packet["reference_map"]["evidence"].items()
                         if v == quote["evidence_id"])
            environment = self.targeted_environment(run, task)
            parent, child = "option-literal-parent", "option-literal-child"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            started, context = handle_hook_event(self.start_payload(task, parent=parent, child=child),
                                                 environ=environment)
            self.assertEqual(started["context_binding"]["status"], "DELIVERED")
            self.assertIn("source_literal_selections", context["hookSpecificOutput"]["additionalContext"])
            event = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query",
                     "access_mode": "read", "run_id": task["run_id"], "invocation_id": task["invocation_id"],
                     "agent": task["agent"], "evidence_ids": [quote["evidence_id"]]}
            event["event_hash"] = canonical_hash(event)
            (run / "events/mcp").mkdir(parents=True, exist_ok=True)
            (run / "events/mcp/events.jsonl").write_text(json.dumps(event) + "\n")
            draft = self.dimension_draft(task)
            for key in ("run_id", "invocation_id", "agent"):
                draft.pop(key, None)
            draft["claims"] = [{
                "claim_id": "quote", "question": "报价时间？", "statement": "盘口{{sf.quote_time}}。",
                "kind": "FACT", "evidence_refs": [short], "research_claim_refs": [],
                "document_refs": [], "assumption_ids": [],
            }]
            draft["source_literal_selections"] = [{
                "claim_id": "quote", "placeholder": "{{sf.quote_time}}",
                "evidence_ref": short, "field": "as_of",
            }]
            stopped, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")
            self.assertEqual(response, {})
            report = json.loads((run / stopped["output_capture"]["path"]).read_text())
            self.assertEqual(report["claims"][0]["statement"], "盘口as_of=2026-09-10T19:58:46Z。")
            self.assertNotIn("source_literal_selections", report)

    def test_source_literal_real_hook_without_authored_identity_repairs_and_saves(self):
        for second_still_wrong in (False, True):
            with self.subTest(second_still_wrong=second_still_wrong), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                handoff = stock_handoff(1)
                gate = gate_for(handoff)
                fact = next(f for f in gate["allowed_evidence"] if f["evidence_id"] == "ev-aapl-revenue")
                fact.update(source_type="sec", unit="USD", value="100")
                gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                handoff_path, gate_path = root / "handoff.json", root / "gate.json"
                handoff_path.write_text(json.dumps(handoff))
                gate_path.write_text(json.dumps(gate))
                run = root / "run"
                prepare_multidimensional_stage_run(
                    ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                    run_id="source-literal-hook", model="gpt-5.6-terra",
                )
                task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                            if t["capability"] == "FUNDAMENTAL_EVENT")
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                short = next(k for k, v in packet["reference_map"]["evidence"].items()
                             if v == fact["evidence_id"])
                environment = self.targeted_environment(run, task)
                parent, child = "literal-parent", "literal-child"
                handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
                started, context = handle_hook_event(self.start_payload(task, parent=parent, child=child),
                                                     environ=environment)
                self.assertEqual(started["context_binding"]["status"], "DELIVERED")
                self.assertIn("source_literal_selections", context["hookSpecificOutput"]["additionalContext"])
                event = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query",
                         "access_mode": "read", "run_id": task["run_id"],
                         "invocation_id": task["invocation_id"], "agent": task["agent"],
                         "evidence_ids": [fact["evidence_id"]]}
                event["event_hash"] = canonical_hash(event)
                (run / "events/mcp").mkdir(parents=True, exist_ok=True)
                (run / "events/mcp/events.jsonl").write_text(json.dumps(event) + "\n")
                draft = self.dimension_draft(task)
                for key in ("run_id", "invocation_id", "agent"):
                    draft.pop(key, None)
                draft["claims"] = [{
                    "claim_id": "revenue", "question": "收入原值？",
                    "statement": "SEC收入{{sf.revenue}}。", "kind": "FACT",
                    "evidence_refs": [short], "research_claim_refs": [], "document_refs": [],
                    "assumption_ids": [],
                }]
                draft["source_literal_selections"] = [{
                    "claim_id": "revenue", "placeholder": "{{sf.revenue}}",
                    "evidence_ref": short, "field": "retrieved_at",
                }]
                first, response = handle_hook_event(self.stop_payload(task, draft, parent=parent, child=child),
                                                    environ=environment)
                self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
                self.assertEqual(first["output_capture"]["failure_code"],
                                 "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
                self.assertEqual(json.loads(response["reason"])["maximum_submissions"], 2)
                if not second_still_wrong:
                    draft["source_literal_selections"][0]["field"] = "sec_usd_value"
                second, response = handle_hook_event(self.stop_payload(task, draft, parent=parent, child=child),
                                                     environ=environment)
                if second_still_wrong:
                    self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
                    self.assertEqual(second["output_capture"]["status"], "FAILED")
                else:
                    self.assertEqual(second["output_capture"]["status"], "SAVED")
                    report = json.loads((run / second["output_capture"]["path"]).read_text())
                    self.assertEqual(report["claims"][0]["statement"], "SEC收入100 USD。")
                    self.assertNotIn("source_literal_selections", report)
                    self.assertEqual(report["report_hash"], canonical_hash({
                        k: v for k, v in report.items() if k != "report_hash"
                    }))
                    downstream = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                                      if t["capability"] == "RESEARCH_REPORT")
                    dependency_packet = build_multidimensional_dispatch_packet(ROOT, run, downstream["task_name"])
                    self.assertEqual(dependency_packet["dependency_reports"][0]["claims"][0]["statement"],
                                     "SEC收入100 USD。")
                    raw = (run / second["output_capture"]["raw_path"]).read_text()
                    self.assertIn("source_literal_selections", raw)
                    self.assertNotIn('"invocation_id"', raw)
                self.assertEqual(response, {})

    def test_source_literal_failure_gets_only_one_bounded_repair(self):
        packet = {"task": {"task_id": "fundamental_event:mrvl", "invocation_id": "inv",
                           "source_literal_selection": "source-literal-selection/1.0.0"},
                  "output_schema_hash": "schema-hash"}
        payload = {"last_assistant_message": json.dumps({"claims": []})}
        record = {"identity_binding": {"status": "BOUND"},
                  "trusted_task_binding": {"invocation_id": "inv"},
                  "output_binding": {"run_id": "run", "invocation_id": "inv",
                                     "agent": "runtime_company_analyst"}}
        with patch("product.runtime.multidimensional_references.load_reference_packet", return_value=packet):
            first = _multidimensional_repair_packet(
                payload, {"STOCK_AGENT_RUN_DIR": "/tmp/source-literal-test"},
                failure_code="DIMENSION_SOURCE_LITERAL_SELECTION_INVALID", attempt=1,
                trusted_record=record,
            )
            self.assertEqual(first["maximum_submissions"], 2)
            self.assertNotIn("original_draft", first)
            self.assertIsNone(_multidimensional_repair_packet(
                payload, {"STOCK_AGENT_RUN_DIR": "/tmp/source-literal-test"},
                failure_code="DIMENSION_SOURCE_LITERAL_SELECTION_INVALID", attempt=2,
                trusted_record=record,
            ))

    def test_source_literal_contract_reaches_only_two_formal_packets(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                packet = build_multidimensional_dispatch_packet(
                    ROOT, run, task["task_name"], include_dependency_reports=False,
                )
                schema_has_field = "source_literal_selections" in packet["output_schema"]["properties"]
                wanted = task["capability"] in {"FUNDAMENTAL_EVENT", "OPTIONS_FLOW"}
                self.assertEqual(schema_has_field, wanted, task["task_name"])
                self.assertEqual("source_literal_selection" in packet["task"], wanted)
                self.assertEqual("source_literal_selections" in packet["instruction"], wanted)
                delivered = serialize_multidimensional_model_context(packet)
                self.assertEqual("source_literal_selections" in delivered, wanted)

    def test_source_literal_binding_is_task_scoped_and_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "evidence").mkdir()
            (run / "events/mcp").mkdir(parents=True)
            sid = "US:COMMON_STOCK:MRVL"
            sec = {"evidence_id": "ev-sec", "source_type": "sec", "security_id": sid,
                   "semantic_field": "us-gaap.RevenueFromContractWithCustomerExcludingAssessedTax",
                   "as_of": "2026-08-01T00:00:00Z", "retrieved_at": "2026-09-28T12:09:52Z",
                   "unit": "USD", "value": "2739300000"}
            quote = {"evidence_id": "ev-quote", "source_type": "SECONDARY_VENDOR", "security_id": sid,
                     "dataset": "options_snapshot", "semantic_field": "moomoo_option_quote:one",
                     "as_of": "2026-09-25T19:58:46Z", "retrieved_at": "2026-09-28T12:09:35.913898Z",
                     "value": {"bid": "5.35", "ask": "5.55"}}
            gate = {"decision_cutoff": "2026-09-28T12:35:32Z", "allowed_evidence": [sec, quote]}
            gate["bundle_hash"] = canonical_hash(gate)
            (run / "evidence/gate.json").write_text(json.dumps(gate))
            def event(invocation, agent, ids):
                row = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query",
                       "access_mode": "read", "run_id": "run", "invocation_id": invocation,
                       "agent": agent, "evidence_ids": ids}
                row["event_hash"] = canonical_hash(row)
                return row
            events = [event("inv-f", "runtime_company_analyst", ["ev-sec"]),
                      event("inv-o", "runtime_market_catalyst", ["ev-quote"])]
            event_file = run / "events/mcp/events.jsonl"
            event_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            def task(capability, invocation, agent, ids):
                return {"source_literal_selection": "source-literal-selection/1.0.0",
                        "capability": capability, "run_id": "run", "invocation_id": invocation,
                        "agent": agent, "security_ids": [sid], "allowed_evidence_ids": ids}
            fundamental = task("FUNDAMENTAL_EVENT", "inv-f", "runtime_company_analyst", ["ev-sec"])
            options = task("OPTIONS_FLOW", "inv-o", "runtime_market_catalyst", ["ev-quote"])
            def draft(marker, ref, field, statement):
                return {"claims": [{"claim_id": "c", "statement": statement,
                                    "evidence_refs": [ref]}],
                        "source_literal_selections": [{"claim_id": "c", "placeholder": marker,
                                                       "evidence_ref": ref, "field": field}]}
            revenue = draft("{{sf.revenue}}", "e.sec", "sec_usd_value",
                            "收入{{sf.revenue}}；阈值2739000000 USD只是反例。")
            mapping = {"evidence": {"e.sec": "ev-sec", "e.quote": "ev-quote"}}
            bound = _bind_source_literal_selections(revenue, task=fundamental, run_dir=run, reference_map=mapping)
            self.assertIn("2739300000 USD", bound["claims"][0]["statement"])
            self.assertIn("阈值2739000000 USD只是反例", bound["claims"][0]["statement"])
            self.assertNotIn("source_literal_selections", bound)
            self.assertIn("{{sf.revenue}}", revenue["claims"][0]["statement"])
            mixed_ref = copy.deepcopy(revenue)
            mixed_ref["source_literal_selections"][0]["evidence_ref"] = "ev-sec"
            self.assertIn("2739300000 USD", _bind_source_literal_selections(
                mixed_ref, task=fundamental, run_dir=run, reference_map=mapping,
            )["claims"][0]["statement"])
            quoted = draft("{{sf.quote_time}}", "ev-quote", "as_of", "报价{{sf.quote_time}}。")
            self.assertEqual(_bind_source_literal_selections(
                quoted, task=options, run_dir=run, reference_map=mapping,
            )["claims"][0]["statement"], "报价as_of=2026-09-25T19:58:46Z。")
            fetched = copy.deepcopy(quoted)
            fetched["source_literal_selections"][0]["field"] = "retrieved_at"
            self.assertIn("retrieved_at=2026-09-28T12:09:35.913898Z",
                          _bind_source_literal_selections(fetched, task=options, run_dir=run,
                                                          reference_map=mapping)["claims"][0]["statement"])
            variants = []
            for key, value in (("evidence_ref", "ev-other"), ("field", "retrieved_at"),
                               ("placeholder", "{{sf.missing}}")):
                bad = copy.deepcopy(revenue)
                bad["source_literal_selections"][0][key] = value
                variants.append((bad, fundamental))
            bad = copy.deepcopy(revenue)
            bad["source_literal_selections"] *= 2
            variants.append((bad, fundamental))
            bad = copy.deepcopy(revenue)
            bad["claims"][0]["statement"] += "{{sf.unknown}}"
            variants.append((bad, fundamental))
            bad = copy.deepcopy(revenue)
            bad["claims"][0]["statement"] = "收入{{sf.revenue}} USD。"
            variants.append((bad, fundamental))
            bad = copy.deepcopy(quoted)
            bad["claims"][0]["evidence_refs"] = []
            variants.append((bad, options))
            bad = copy.deepcopy(quoted)
            bad["source_literal_selections"][0]["field"] = "sec_usd_value"
            variants.append((bad, options))
            for bad, scoped_task in variants:
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                        _bind_source_literal_selections(bad, task=scoped_task, run_dir=run,
                                                        reference_map=mapping)
            old = {**fundamental, "source_literal_selection": None}
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(revenue, task=old, run_dir=run, reference_map=mapping)
            self.assertEqual(_bind_source_literal_selections(
                {"claims": [{"claim_id": "c", "statement": "收入假设阈值2739000000 USD，不是原值。",
                             "evidence_refs": []}]}, task=old, run_dir=run, reference_map=mapping,
            )["claims"][0]["statement"], "收入假设阈值2739000000 USD，不是原值。")
            tampered = copy.deepcopy(events)
            tampered[0]["evidence_ids"] = ["ev-other"]
            event_file.write_text("\n".join(json.dumps(e) for e in tampered) + "\n")
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(revenue, task=fundamental, run_dir=run,
                                                reference_map=mapping)
            event_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            wrong_invocation = copy.deepcopy(events[0])
            wrong_invocation["invocation_id"] = "elsewhere"
            wrong_invocation["event_hash"] = canonical_hash({k: v for k, v in wrong_invocation.items() if k != "event_hash"})
            event_file.write_text(json.dumps(wrong_invocation) + "\n")
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(revenue, task=fundamental, run_dir=run,
                                                reference_map=mapping)
            event_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            gate["allowed_evidence"][0]["value"] = "2739000000"
            (run / "evidence/gate.json").write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(revenue, task=fundamental, run_dir=run,
                                                reference_map=mapping)
            gate["allowed_evidence"][0]["value"] = "2739.3"
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            (run / "evidence/gate.json").write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(revenue, task=fundamental, run_dir=run,
                                                reference_map=mapping)
            gate["allowed_evidence"][0]["value"] = "2739300000"
            gate["allowed_evidence"][1]["as_of"] = "bad-time"
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            (run / "evidence/gate.json").write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                _bind_source_literal_selections(quoted, task=options, run_dir=run,
                                                reference_map=mapping)

    def test_insider_focus_is_bounded_pit_scoped_and_non_monetary(self):
        sid = "US:COMMON_STOCK:MRVL"
        cutoff = "2026-09-28T12:35:32Z"
        def row(identity, day, kind, *, end=None, security=sid, published="2026-09-28T12:09:36Z"):
            end = end or day
            return {
                "evidence_id": identity, "security_id": security,
                "semantic_field": f"moomoo_insider_trade:{identity}",
                "as_of": f"{end}T16:00:00Z", "published_at": published,
                "retrieved_at": published,
                "value": {"trade_date_start": day, "trade_date_end": end, "transaction_type": kind,
                          "trade_shares": "-7500", "max_price": "298.76"},
            }
        rows = [
            row("older", "2026-07-01", "卖出"),
            row("sale", "2026-09-14", "卖出"),
            row("exercise-sale", "2026-09-14", "行权卖出"),
            row("exercise-grant", "2026-09-14", "行权获得"),
            row("peer", "2026-09-14", "卖出", security="US:COMMON_STOCK:ADI"),
            row("future-observed", "2026-09-14", "卖出", published="2026-09-29T12:00:00Z"),
            row("future-trade", "2026-09-29", "卖出"),
            row("missing-type", "2026-09-14", ""),
        ]
        before = copy.deepcopy(rows)
        expected = ["sale", "exercise-sale", "exercise-grant"]
        for facts in (rows, list(reversed(rows))):
            focus = _latest_insider_trade_focus(facts, security_id=sid, cutoff=cutoff)
            self.assertEqual([item["evidence_id"] for item in focus], expected)
            self.assertTrue(all("trade_shares" not in item and "max_price" not in item for item in focus))
            self.assertTrue(all("observed_at" in item for item in focus))
        self.assertEqual(_latest_insider_trade_focus([], security_id=sid, cutoff=cutoff), [])
        interval = row("interval", "2026-09-01", "卖出", end="2026-09-20")
        interval_focus = _latest_insider_trade_focus([*rows, interval], security_id=sid, cutoff=cutoff)
        self.assertEqual(interval_focus[0]["evidence_id"], "interval")
        self.assertEqual((interval_focus[0]["trade_date_start"], interval_focus[0]["trade_date_end"]),
                         ("2026-09-01", "2026-09-20"))
        self.assertEqual(_latest_insider_trade_focus(
            [row("bad-interval", "2026-09-20", "卖出", end="2026-09-01")],
            security_id=sid, cutoff=cutoff,
        ), [])
        self.assertEqual(rows, before)

    def test_frozen_mrvl_insider_focus_has_three_distinct_latest_types(self):
        gate_path = Path(
            "/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/"
            "eight-dimension-rebuild-20260928/citation-review-ready/evidence/gate.json"
        )
        if not gate_path.exists():
            self.skipTest("host frozen acceptance gate unavailable")
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        focus = _latest_insider_trade_focus(
            gate["allowed_evidence"], security_id="US:COMMON_STOCK:MRVL",
            cutoff=gate["decision_cutoff"],
        )
        self.assertEqual(len(focus), 3)
        self.assertEqual({item["trade_date_start"] for item in focus}, {"2026-09-14"})
        self.assertEqual({item["transaction_type"] for item in focus}, {"卖出", "行权卖出", "行权获得"})

    def test_ownership_focus_reaches_formal_hook_with_institutional_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            sid = handoff["portfolio"]["positions"][0]["security_id"]
            gate = gate_for(handoff)
            cutoff = gate["decision_cutoff"]
            for label, end in (("2026/Q1", "2026-03-31"), ("2026/Q2", "2026-06-30")):
                gate["allowed_evidence"].append({
                    "evidence_id": f"ev-inst-{end}", "security_id": sid,
                    "semantic_field": f"moomoo_institutional_aggregate:{end}",
                    "dataset": "institutional_ownership", "source_id": "moomoo-test",
                    "as_of": f"{end}T00:00:00Z", "published_at": cutoff, "retrieved_at": cutoff,
                    "value": {"period_provisional": False, "period_end": end,
                              "period_label": label},
                })
            for identity, kind in (("sale", "卖出"), ("exercise-sale", "行权卖出"),
                                   ("exercise-grant", "行权获得")):
                gate["allowed_evidence"].append({
                    "evidence_id": f"ev-insider-{identity}", "security_id": sid,
                    "semantic_field": f"moomoo_insider_trade:{identity}",
                    "dataset": "insider_transactions", "source_id": "moomoo-test",
                    "as_of": "2026-09-10T16:00:00Z",
                    "published_at": cutoff, "retrieved_at": cutoff,
                    "value": {"trade_date_start": "2026-09-10",
                              "trade_date_end": "2026-09-10", "transaction_type": kind,
                              "trade_shares": "-100"},
                })
            gate["input_evidence_ids"] = sorted(item["evidence_id"] for item in gate["allowed_evidence"])
            gate["allowed_evidence_ids"] = list(gate["input_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="ownership-focus-test", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "OWNERSHIP_DISCLOSURE")
            focus = task["source_focus"]
            self.assertEqual(len(focus), 5)
            self.assertEqual([item["period_label"] for item in focus[:2]], ["2026/Q1", "2026/Q2"])
            self.assertEqual({item["transaction_type"] for item in focus[2:]}, {"卖出", "行权卖出", "行权获得"})
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            context = json.loads(serialize_multidimensional_model_context(packet))
            self.assertEqual(translate_references(context["task"]["source_focus"], packet["reference_map"]), focus)
            self.assertTrue(all(item["evidence_id"].startswith("e.") for item in context["task"]["source_focus"]))
            self.assertTrue(all("trade_shares" not in item for item in context["task"]["source_focus"]))
            self.assertIn("min/max可能是聚合区间", context["instruction"])
            environment = self.targeted_environment(run, task)
            handle_hook_event(self.dispatch_payload(task, parent="ownership-parent"), environ=environment)
            started, response = handle_hook_event(
                self.start_payload(task, parent="ownership-parent", child="ownership-child"),
                environ=environment,
            )
            self.assertEqual(started["context_binding"]["status"], "DELIVERED")
            delivered = json.loads(response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(delivered["task"]["source_focus"], context["task"]["source_focus"])

    def test_issuer_title_distinguishes_sec_form_and_section(self):
        self.assertIn("10-Q Management's Discussion", _issuer_document_title({
            "semantic_field": "management_discussion", "metadata": {"form": "10-Q"},
        }))
        self.assertIn("8-K earnings release", _issuer_document_title({
            "semantic_field": "earnings_release", "metadata": {"form": "8-K"},
        }))
        self.assertIn("form unknown", _issuer_document_title({
            "semantic_field": "management_discussion", "metadata": {},
        }))
        self.assertIn("form unknown", _issuer_document_title({
            "semantic_field": "earnings_release", "metadata": {"form": "UNVERIFIED"},
        }))

    def save_fundamental_dependency(self, run, index):
        task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
        environment = self.targeted_environment(run, task)
        handle_hook_event(self.dispatch_payload(task, parent="dependency-parent"), environ=environment)
        handle_hook_event(self.start_payload(task, parent="dependency-parent", child="dependency-child"), environ=environment)
        draft = self.dimension_draft(task)
        draft["claims"] = [{
            "claim_id": "mrvl_core_drivers", "question": "经营驱动？", "statement": "冻结事实支持研究基线。",
            "kind": "FACT", "evidence_refs": [task["allowed_evidence_ids"][0]],
            "research_claim_refs": [], "document_refs": [], "assumption_ids": [],
        }]
        record, _ = handle_hook_event(self.stop_payload(task, draft, parent="dependency-parent", child="dependency-child"), environ=environment)
        self.assertEqual(record["output_capture"]["status"], "SAVED")

    def test_full_batch_early_subagent_stop_is_not_blocked_by_unfilled_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            technical = next(
                item for item in index["tasks"]
                if item["capability"] == "TECHNICAL_STRUCTURE"
            )
            environment = self.targeted_environment(run, technical)
            environment.pop("STOCK_AGENT_RESEARCH_TASK_NAME")
            environment["STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS"] = (
                "runtime_company_analyst,runtime_market_catalyst"
            )
            parent, child = "parent-early-stop", "child-early-stop"
            dispatched, _ = handle_hook_event(
                self.dispatch_payload(technical, parent=parent), environ=environment,
            )
            self.assertEqual(dispatched["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(technical, parent=parent, child=child),
                environ=environment,
            )
            stopped, response = handle_hook_event(
                self.stop_payload(
                    technical, self.dimension_draft(technical),
                    parent=parent, child=child,
                ),
                environ=environment,
            )
            self.assertEqual(stopped["hook_event_name"], "SubagentStop")
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")
            self.assertEqual(response, {})
            independent = [
                item for item in index["tasks"]
                if item["task_id"] != technical["task_id"] and not item["depends_on"]
            ]
            self.assertGreaterEqual(len(independent), 4)
            for task in independent[:3]:
                decision, _ = handle_hook_event(
                    self.dispatch_payload(task, parent=parent), environ=environment,
                )
                self.assertEqual(decision["decision"], "ALLOW")
            capped, _ = handle_hook_event(
                self.dispatch_payload(independent[3], parent=parent),
                environ=environment,
            )
            self.assertEqual(capped["decision"], "DENY_CONCURRENCY_LIMIT")

    def test_full_batch_reference_repair_is_bounded_and_keeps_hard_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            technical = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            fundamental = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            tech_env = self.targeted_environment(run, technical)
            parent, child = "parent-full-repair", "child-full-repair"
            draft = self.formal_dimension_draft(technical)  # 历史完整稿只读诊断。
            draft["claims"] = [{
                "claim_id": "unsupported", "question": "技术结构是什么？",
                "statement": "没有依据的观察。", "kind": "INTERPRETATION",
                "evidence_refs": [], "research_claim_refs": [], "document_refs": [],
                "assumption_ids": [],
            }]
            first = self.stop_payload(technical, draft, parent=parent, child=child)
            repair = _multidimensional_repair_packet(
                first, tech_env, failure_code="DIMENSION_REPORT_CLAIM_UNGROUNDED", attempt=1,
            )
            self.assertEqual(repair["validation_details"]["findings"][0]["path"], "claims[0]")
            self.assertNotIn("original_draft", repair)
            self.assertLess(len(json.dumps(repair).encode()), 16 * 1024)
            self.assertIsNone(_multidimensional_repair_packet(
                first, tech_env, failure_code="DIMENSION_REPORT_CLAIM_UNGROUNDED", attempt=2,
            ))
            fundamental_env = self.targeted_environment(run, fundamental)
            wrong_id = self.formal_dimension_draft(fundamental)
            wrong_id["claims"] = [{
                "claim_id": "wrong-id", "question": "经营资料是什么？",
                "statement": "测试数值。", "kind": "FACT",
                "evidence_refs": ["ev-sec-text-invalid"], "research_claim_refs": [],
                "document_refs": [], "assumption_ids": [],
            }]
            wrong_payload = self.stop_payload(fundamental, wrong_id, parent=parent, child=child)
            evidence_repair = _multidimensional_repair_packet(
                wrong_payload, fundamental_env,
                failure_code="EVIDENCE_CLOSURE_FAILED:ev-sec-text-invalid", attempt=1,
            )
            self.assertEqual(evidence_repair["validation_details"]["findings"][0]["identifier"],
                             "ev-sec-text-invalid")
            self.assertNotIn("original_draft", evidence_repair)
            self.assertIsNone(_multidimensional_repair_packet(
                wrong_payload, fundamental_env,
                failure_code="EVIDENCE_CLOSURE_FAILED:ev-other", attempt=1,
            ))
            wrong_artifact = self.formal_dimension_draft(fundamental)
            wrong_artifact["artifact_refs"] = ["made-up-calculation-id"]
            artifact_repair = _multidimensional_repair_packet(
                self.stop_payload(fundamental, wrong_artifact, parent=parent, child=child),
                fundamental_env, failure_code="MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID",
                attempt=1,
            )
            self.assertEqual(artifact_repair["validation_details"]["allowed_artifact_refs"],
                             [fundamental["calculation_ledger_ref"]])
            self.assertEqual(artifact_repair["validation_details"]["findings"][0]["path"],
                             "artifact_refs[0]")
            self.assertIn("不能仅因 ID 合法就保留无关引用", artifact_repair["instruction"])
            self.assertNotIn("保持其他已合法引用不变", artifact_repair["instruction"])
            first_fundamental = self.dimension_draft(fundamental)
            first_fundamental["claims"] = copy.deepcopy(draft["claims"])
            handle_hook_event(self.dispatch_payload(fundamental, parent=parent),
                              environ=fundamental_env)
            handle_hook_event(self.start_payload(fundamental, parent=parent, child=child),
                              environ=fundamental_env)
            stopped, response = handle_hook_event(
                self.stop_payload(fundamental, first_fundamental, parent=parent, child=child),
                environ=fundamental_env,
            )
            self.assertEqual(stopped["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(response["decision"], "block")
            corrected = self.dimension_draft(fundamental)
            saved, _ = handle_hook_event(
                self.stop_payload(fundamental, corrected, parent=parent, child=child),
                environ=fundamental_env,
            )
            self.assertEqual(saved["output_capture"]["status"], "SAVED")
            self.assertEqual(saved["output_capture"]["repair_state"], "REPAIRED")

    def test_runtime_calculation_receipt_is_citable_and_tamper_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            invocation = json.loads((run / task["invocation_path"]).read_text())
            ledger_ref = task["calculation_ledger_ref"]
            self.assertEqual(invocation["calculation_ledger_ref"], ledger_ref)
            packet = json.loads((run / task["packet_path"]).read_text())
            self.assertEqual(packet["output_schema"]["properties"]["artifact_refs"]["items"]["enum"],
                             [ledger_ref])
            ids = ["ev-aapl-revenue", "ev-aapl-cash"]
            tool = StatelessFixtureTools(default_run_dir=run)
            tool.query(run_id=task["run_id"], agent=task["agent"],
                       invocation_id=task["invocation_id"], evidence_ids=ids)
            result = tool.calculate(run_id=task["run_id"], agent=task["agent"],
                                    invocation_id=task["invocation_id"],
                                    calculation_id="test-revenue-cash-ratio", operation="ratio",
                                    evidence_ids=ids)
            self.assertEqual(result["artifact_ref"], ledger_ref)
            receipt = json.loads((run / ledger_ref).read_text(encoding="utf-8"))
            self.assertEqual(
                result["receipt_hash"],
                legacy_envelope_hash(receipt, hash_field="receipt_hash"),
            )
            self.assertEqual(
                result["receipt_hash"],
                content_hash({key: value for key, value in receipt.items() if key != "receipt_hash"}),
            )
            self.assertEqual(
                tool.events[-1]["event_hash"],
                legacy_envelope_hash(tool.events[-1], hash_field="event_hash"),
            )
            _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
            draft = self.dimension_draft(task)
            draft["status"] = "LOW_CONFIDENCE"
            draft["sufficiency"] = "PARTIAL"
            draft["claims"] = [{
                "claim_id": "cash-to-revenue", "question": "经营资料是什么？",
                "statement": "测试证据中的两个同期间数字可由受限工具计算比值。",
                "kind": "FACT", "evidence_refs": ids, "research_claim_refs": [],
                "document_refs": [], "assumption_ids": [],
            }]
            draft["calculation_selections"] = [{"calculation_ref": result["calculation_ref"],
                                                 "claim_ids": ["cash-to-revenue"]}]
            environment = self.targeted_environment(run, task)
            parent, child = "parent-calculation-receipt", "child-calculation-receipt"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            wrong = copy.deepcopy(draft)
            wrong["calculation_selections"][0]["calculation_ref"] = "invented-calculation-id"
            blocked, feedback = handle_hook_event(
                self.stop_payload(task, wrong, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(blocked["hook_event_name"], "SubagentStopBlocked")
            self.assertIn("SCHEMA_PATTERN", blocked["output_capture"]["failure_code"])
            located = json.loads(feedback["reason"])["validation_details"]
            self.assertTrue(any(item["path"] == "/calculation_selections/0/calculation_ref"
                                for item in located["findings"]))
            saved, _ = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(saved["output_capture"]["status"], "SAVED")
            self.assertEqual(saved["output_capture"]["repair_state"], "REPAIRED")
            report_path = run / saved["output_capture"]["path"]
            self.assertTrue(report_path.is_file())
            self.assertTrue(report_path.with_suffix(".md").is_file())
            # 正式报告由可信收据装配，篡改负例继续走原严格血缘校验。
            formal = json.loads(report_path.read_text())
            bad = copy.deepcopy(formal)
            bad["calculations"][0]["input_evidence_refs"] = list(reversed(ids))
            with self.assertRaisesRegex(ValueError, "CALCULATION_INPUT_MISMATCH"):
                _validate_multidimensional_tool_calculations(
                    bad, task=task, invocation=invocation, run_dir=run,
                )
            unknown = copy.deepcopy(formal)
            unknown["calculations"][0]["calculation_id"] = "unknown-calculation"
            with self.assertRaisesRegex(ValueError, "CALCULATION_RECORD_UNKNOWN"):
                _validate_multidimensional_tool_calculations(
                    unknown, task=task, invocation=invocation, run_dir=run,
                )
            ledger = run / ledger_ref
            original = ledger.read_text(encoding="utf-8")
            tampered = json.loads(original)
            tampered["output"]["value"] = "999"
            ledger.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CALCULATION_LEDGER_INVALID"):
                _validate_multidimensional_tool_calculations(
                    formal, task=task, invocation=invocation, run_dir=run,
                )
            ledger.write_text(original, encoding="utf-8")
            event_path = run / "events/mcp/events.jsonl"
            event_path.write_text(
                json.dumps({**tool.events[-1], "context_note": "tampered"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "CALCULATION_EVENT_INVALID"):
                _validate_multidimensional_tool_calculations(
                    formal, task=task, invocation=invocation, run_dir=run,
                )
            event_path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CALCULATION_EVENT_INVALID"):
                _validate_multidimensional_tool_calculations(
                    formal, task=task, invocation=invocation, run_dir=run,
                )

    def test_calculation_permission_is_scoped_to_fundamental_and_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                invocation = json.loads((run / task["invocation_path"]).read_text())
                packet = json.loads((run / task["packet_path"]).read_text())
                expected = ["fixture_evidence.query"]
                if task["capability"] in {"OWNERSHIP_DISCLOSURE", "FUNDAMENTAL_EVENT"}:
                    expected.append("fixture_math.calculate")
                if task["capability"] == "OWNERSHIP_DISCLOSURE":
                    self.assertIn("institutional_period_change", packet["instruction"])
                if task["capability"] == "FUNDAMENTAL_EVENT":
                    self.assertIn("monetary_scale", packet["instruction"])
                    self.assertIn("历史收盘价，不称实时价", packet["instruction"])
                self.assertEqual(invocation["tool_permissions"], expected)
                self.assertEqual(packet["tool_context"]["logical_permissions"], expected)

    def test_fundamental_routes_only_latest_target_close_without_mutation(self):
        facts = [
            {"evidence_id": identity, "security_id": sid,
             "semantic_field": "historical_close_price", "source_id": "yahoo",
             "as_of": date, "retrieved_at": "2026-09-11T10:00:00Z",
             "value": "100", "unit": "USD"}
            for identity, sid, date in (
                ("older", "US:COMMON_STOCK:MRVL", "2026-09-09T20:00:00Z"),
                ("latest", "US:COMMON_STOCK:MRVL", "2026-09-10T20:00:00Z"),
                ("other", "US:COMMON_STOCK:ADI", "2026-09-10T20:00:00Z"),
            )
        ]
        before = copy.deepcopy(facts)
        args = {"security_ids": ["US:COMMON_STOCK:MRVL"], "benchmark_id": None}
        for values in (facts, list(reversed(facts))):
            selected = _facts_for_capability(values, capability="FUNDAMENTAL_EVENT", **args)
            self.assertEqual([f["evidence_id"] for f in selected], ["latest"])
            self.assertEqual(selected[0], facts[1])
        self.assertEqual(_facts_for_capability([], capability="FUNDAMENTAL_EVENT", **args), [])
        technical = _facts_for_capability(facts, capability="TECHNICAL_STRUCTURE", **args)
        self.assertEqual({f["evidence_id"] for f in technical}, {"older", "latest"})
        self.assertEqual(facts, before)

    def test_fundamental_eps_focus_keeps_latest_allowed_period_candidates(self):
        def eps(identity, sid, start, end, *, period="FY", source="sec"):
            return {
                "evidence_id": identity, "security_id": sid,
                "semantic_field": "us-gaap.EarningsPerShareDiluted",
                "source_type": source, "unit": "USD/shares", "value": "3.07",
                "metadata": {"fiscal_period": period, "context_type": "duration",
                             "period_start": start, "period_end": end},
            }

        facts = [
            eps("older", "US:COMMON_STOCK:MRVL", "2024-02-04", "2025-02-01"),
            eps("fy-a", "US:COMMON_STOCK:MRVL", "2025-02-02", "2026-01-31"),
            eps("fy-b", "US:COMMON_STOCK:MRVL", "2025-02-02", "2026-01-31"),
            eps("q2", "US:COMMON_STOCK:MRVL", "2026-05-03", "2026-08-01", period="Q2"),
            eps("peer", "US:COMMON_STOCK:ADI", "2025-02-02", "2026-01-31"),
            eps("other-source", "US:COMMON_STOCK:MRVL", "2025-02-02", "2026-01-31", source="yahoo"),
            eps("bad-period", "US:COMMON_STOCK:MRVL", "2026-01-31", "2025-02-02"),
        ]
        legacy = eps("legacy-sec", "US:COMMON_STOCK:MRVL", "2025-02-02", "2026-01-31")
        legacy.pop("source_type")
        legacy["source_id"] = "sec-companyfacts-test"
        facts.append(legacy)
        before = copy.deepcopy(facts)
        for values in (facts, list(reversed(facts))):
            focus = _latest_annual_eps_focus(values, security_id="US:COMMON_STOCK:MRVL")
            self.assertEqual([item["evidence_id"] for item in focus], ["fy-a", "fy-b", "legacy-sec"])
            self.assertTrue(all(item["period_start"] == "2025-02-02" for item in focus))
            self.assertTrue(all("value" not in item for item in focus))
        self.assertEqual(_latest_annual_eps_focus([], security_id="US:COMMON_STOCK:MRVL"), [])
        self.assertEqual(facts, before)

    def test_sec_revenue_table_unit_focus_uses_header_not_derived_amounts(self):
        def business(identity, sid, source, value):
            return {
                "evidence_id": identity, "security_id": sid,
                "semantic_field": "business", "source_type": source,
                "value": value,
            }

        table = (
            "The following table summarizes net revenue disaggregated by end market "
            "(in millions, except percentages): Data center $ 6,100.3 74 % "
            "Communications and other 2,094.3 26 % Total $ 8,194.6"
        )
        facts = [
            business("sec-table", "US:COMMON_STOCK:MRVL", "sec", table),
            business("peer-table", "US:COMMON_STOCK:ADI", "sec", table),
            business("provider-table", "US:COMMON_STOCK:MRVL", "yahoo", table),
            business("no-table", "US:COMMON_STOCK:MRVL", "sec", "Revenue was 8,194.6 million USD."),
        ]
        before = copy.deepcopy(facts)
        self.assertEqual(
            _sec_revenue_table_unit_focus(facts, security_id="US:COMMON_STOCK:MRVL"),
            [{"evidence_id": "sec-table", "semantic_field": "business",
              "table_unit": "millions", "table_label": "revenue_disaggregation"}],
        )
        self.assertEqual(_sec_revenue_table_unit_focus([], security_id="US:COMMON_STOCK:MRVL"), [])
        self.assertEqual(facts, before)

    def test_same_period_profit_cash_focus_is_bounded_and_requires_exact_period(self):
        sid = "US:COMMON_STOCK:MRVL"
        def financial(identity, field, start, end, *, security=sid, source="sec", unit="USD"):
            return {
                "evidence_id": identity, "security_id": security,
                "semantic_field": f"us-gaap.{field}", "source_type": source,
                "unit": unit, "value": "123", "published_at": "2026-08-28T20:04:02Z",
                "metadata": {"context_type": "duration", "period_start": start, "period_end": end},
            }
        facts = [
            financial("old-net", "NetIncomeLoss", "2025-02-02", "2025-08-02"),
            financial("old-cash", "NetCashProvidedByUsedInOperatingActivities", "2025-02-02", "2025-08-02"),
            financial("h1-net", "NetIncomeLoss", "2026-02-01", "2026-08-01"),
            financial("h1-net-duplicate", "NetIncomeLoss", "2026-02-01", "2026-08-01"),
            financial("h1-net-third", "NetIncomeLoss", "2026-02-01", "2026-08-01"),
            financial("h1-cash", "NetCashProvidedByUsedInOperatingActivities", "2026-02-01", "2026-08-01"),
            financial("quarter-net", "NetIncomeLoss", "2026-05-03", "2026-08-01"),
            financial("peer-cash", "NetCashProvidedByUsedInOperatingActivities", "2026-02-01", "2026-08-01", security="US:COMMON_STOCK:ADI"),
            financial("provider-cash", "NetCashProvidedByUsedInOperatingActivities", "2026-02-01", "2026-08-01", source="yahoo"),
            financial("wrong-unit", "NetIncomeLoss", "2026-02-01", "2026-08-01", unit="USD/shares"),
        ]
        before = copy.deepcopy(facts)
        expected = ["h1-net-third", "h1-net-duplicate", "h1-cash"]
        for values in (facts, list(reversed(facts))):
            focus = _same_period_profit_cash_focus(values, security_id=sid)
            self.assertEqual([item["evidence_id"] for item in focus], expected)
            self.assertTrue(all(item["period_start"] == "2026-02-01" and item["period_end"] == "2026-08-01" for item in focus))
            self.assertTrue(all("value" not in item for item in focus))
        self.assertEqual(_same_period_profit_cash_focus([facts[2], facts[6]], security_id=sid), [])
        self.assertEqual(_same_period_profit_cash_focus([], security_id=sid), [])
        self.assertEqual(facts, before)

    def test_fundamental_eps_focus_reaches_formal_model_context_without_value(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            security_id = next(item["security_id"] for item in handoff["portfolio"]["positions"])
            gate = gate_for(handoff)
            eps = {
                "evidence_id": "ev-frozen-fy-eps", "security_id": security_id,
                "semantic_field": "us-gaap.EarningsPerShareDiluted",
                "source_type": "sec", "source_id": "sec-companyfacts-test",
                "as_of": "2026-01-31T00:00:00Z", "retrieved_at": "2026-09-11T10:00:00Z",
                "value": "3.07", "unit": "USD/shares",
                "metadata": {"fiscal_period": "FY", "context_type": "duration",
                             "period_start": "2025-02-02", "period_end": "2026-01-31"},
            }
            gate["allowed_evidence"].append(eps)
            gate["input_evidence_ids"].append(eps["evidence_id"])
            gate["allowed_evidence_ids"].append(eps["evidence_id"])
            table = {
                "evidence_id": "ev-frozen-sec-table", "security_id": security_id,
                "semantic_field": "business", "source_type": "sec",
                "source_id": "sec-filing-test", "as_of": "2026-03-11T20:04:20Z",
                "retrieved_at": "2026-09-11T10:00:00Z", "unit": "text",
                "value": "The following table summarizes net revenue disaggregated by end market "
                         "(in millions, except percentages): Total $ 8,194.6",
            }
            gate["allowed_evidence"].append(table)
            gate["input_evidence_ids"].append(table["evidence_id"])
            gate["allowed_evidence_ids"].append(table["evidence_id"])
            for identity, field, amount in (
                ("ev-frozen-h1-net", "us-gaap.NetIncomeLoss", "342500000"),
                ("ev-frozen-h1-cash", "us-gaap.NetCashProvidedByUsedInOperatingActivities", "1244300000"),
            ):
                item = {
                    "evidence_id": identity, "security_id": security_id,
                    "semantic_field": field, "source_type": "sec", "source_id": "sec-companyfacts-test",
                    "as_of": "2026-08-01T00:00:00Z", "retrieved_at": "2026-09-11T10:00:00Z",
                    "value": amount, "unit": "USD",
                    "metadata": {"context_type": "duration", "period_start": "2026-02-01", "period_end": "2026-08-01"},
                }
                gate["allowed_evidence"].append(item)
                gate["input_evidence_ids"].append(identity)
                gate["allowed_evidence_ids"].append(identity)
            gate["input_evidence_ids"].sort()
            gate["allowed_evidence_ids"].sort()
            gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="eps-focus-test", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            self.assertEqual(
                [item["evidence_id"] for item in task["source_focus"]],
                [eps["evidence_id"], table["evidence_id"], "ev-frozen-h1-net", "ev-frozen-h1-cash"],
            )
            self.assertEqual(task["source_focus"][1]["table_unit"], "millions")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            context = json.loads(serialize_multidimensional_model_context(packet))
            focus = translate_references(context["task"]["source_focus"], packet["reference_map"])
            self.assertEqual(focus, task["source_focus"])
            self.assertNotIn("value", context["task"]["source_focus"][0])
            initial = json.loads(serialize_multidimensional_initial_context(packet))
            self.assertEqual(initial["task"]["source_focus"], context["task"]["source_focus"])
            self.assertIn("单季EPS比值工具失败不等于同Gate没有年度EPS", context["instruction"])
            self.assertIn("不得自行将million改为billion", context["instruction"])
            self.assertIn("SEC原单位为USD的整数金额也不能自行缩写为million/billion", context["instruction"])
            self.assertIn("不得把业绩稿约数写成带结构化事实期间的精确整数USD", context["instruction"])
            self.assertIn("表头继承的数字", context["instruction"])
            self.assertIn("最近完整财年收入分解表", context["minimum_questions"][0])
            self.assertIn("不得只引用该表却只解释较近季度增速", context["instruction"])
            self.assertIn("同起止日不自动证明现金转化率", context["instruction"])
            environment = self.targeted_environment(run, task)
            environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
            dispatched, _ = handle_hook_event(
                self.dispatch_payload(task, parent="eps-focus-parent"), environ=environment,
            )
            self.assertEqual(dispatched["decision"], "ALLOW")
            started, response = handle_hook_event(
                self.start_payload(task, parent="eps-focus-parent", child="eps-focus-child"),
                environ=environment,
            )
            self.assertEqual(started["context_binding"]["status"], "DELIVERED")
            hook_context = json.loads(response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(hook_context["task"]["source_focus"], initial["task"]["source_focus"])
            self.assertEqual(hook_context["packet_hash"], initial["packet_hash"])
            self.assertIsInstance(hook_context["evidence_catalog"], list)
            self.assertTrue(hook_context["task"]["source_focus"][0]["evidence_id"].startswith("e."))
            self.assertTrue(hook_context["task"]["source_focus"][1]["evidence_id"].startswith("e."))
            self.assertEqual(hook_context["task"]["source_focus"][1]["table_unit"], "millions")
            self.assertEqual(len(hook_context["task"]["source_focus"]), 4)
            self.assertEqual(hook_context["task"]["source_focus"][2]["period_start"], "2026-02-01")
            self.assertNotIn("value", hook_context["task"]["source_focus"][2])
            self.assertEqual(hook_context["minimum_questions"], context["minimum_questions"])
            self.assertIn("不得只引用该表却只解释较近季度增速", hook_context["instruction"])
            self.assertIn("SEC原单位为USD的整数金额也不能自行缩写为million/billion", hook_context["instruction"])
            self.assertIn("不得把业绩稿约数写成带结构化事实期间的精确整数USD", hook_context["instruction"])
            self.assertEqual(
                translate_references(hook_context["task"]["source_focus"], packet["reference_map"]),
                task["source_focus"],
            )
            tool = StatelessFixtureTools(default_run_dir=run)
            queried = tool.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"], evidence_ids=[eps["evidence_id"]],
            )
            self.assertEqual("fixture-gate-scoped/2.5.0", queried["adapter_version"])
            self.assertEqual(queried["evidence"][0]["value"], "3.07")
            paired = tool.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"],
                evidence_ids=["ev-frozen-h1-net", "ev-frozen-h1-cash"],
            )
            self.assertEqual(
                [item["value"] for item in paired["evidence"]],
                ["342500000", "1244300000"],
            )
            report_task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            self.assertEqual(report_task["source_focus"], [])
            table_result = tool.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"], evidence_ids=[table["evidence_id"]],
            )
            self.assertIn("(in millions, except percentages)", table_result["evidence"][0]["value"])

    def test_market_and_options_source_boundaries_reach_formal_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
            expected = {
                "MARKET_STATE": ("两日涨跌百分比", "单位未核实"),
                "OPTIONS_FLOW": ("单位未核实", "两日涨跌百分比"),
            }
            for capability, (present, absent) in expected.items():
                task = next(item for item in tasks if item["capability"] == capability)
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                context = json.loads(serialize_multidimensional_model_context(packet))
                self.assertIn(present, context["instruction"])
                self.assertNotIn(absent, context["instruction"])
                if capability == "OPTIONS_FLOW":
                    self.assertIn("逐项给出该合约可得的 delta、gamma、theta、vega、rho 原值", context["minimum_questions"][1])
                    self.assertIn("标的波动单位未知只限制跨口径比较", context["minimum_questions"][1])
                    environment = self.targeted_environment(run, task)
                    dispatched, _ = handle_hook_event(
                        self.dispatch_payload(task, parent="options-question-parent"),
                        environ=environment,
                    )
                    self.assertEqual(dispatched["decision"], "ALLOW")
                    started, response = handle_hook_event(
                        self.start_payload(task, parent="options-question-parent", child="options-question-child"),
                        environ=environment,
                    )
                    self.assertEqual(started["context_binding"]["status"], "DELIVERED", started["context_binding"])
                    hook_context = json.loads(response["hookSpecificOutput"]["additionalContext"])
                    self.assertEqual(hook_context["minimum_questions"], context["minimum_questions"])
                self.assertLessEqual(len(json.dumps(context, ensure_ascii=False).encode("utf-8")), 256 * 1024)
            legacy = next(item for item in tasks if item["capability"] == "TECHNICAL_STRUCTURE")
            legacy_packet = build_multidimensional_dispatch_packet(ROOT, run, legacy["task_name"])
            self.assertNotIn("两日涨跌百分比", legacy_packet["instruction"])
            self.assertNotIn("单位未核实", legacy_packet["instruction"])

    def test_formal_model_context_keeps_exact_catalog_and_source_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, task["task_name"], include_dependency_reports=False,
            )
            packet["provider_coverage"]["providers"].append({
                "plane": "RESEARCH_SUPPLEMENT", "provider": "test-provider",
                "limitations": ["license-limited"],
                "dataset_observations": [
                    {"dataset": "research_discovery", "status": "AVAILABLE"},
                    {"dataset": "research_discovery", "status": "SOURCE_LIMITED",
                     "failure_code": "LICENSE_REQUIRED", "limitations": ["body unavailable"]},
                ],
            })
            full = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            context = json.loads(serialize_multidimensional_model_context(packet))
            columns = context["evidence_catalog"]["columns"]
            rebuilt = [dict(zip(columns, row)) for row in context["evidence_catalog"]["rows"]]
            rebuilt = translate_references(rebuilt, packet["reference_map"])
            self.assertEqual(rebuilt, packet["evidence_catalog"])
            self.assertEqual(
                {row["evidence_id"] for row in rebuilt}, set(packet["allowed_evidence_ids"]),
            )
            self.assertNotIn("allowed_evidence_ids", context)
            self.assertNotIn("allowed_evidence_ids", context["task"])
            self.assertIn("output_format_guide", context["instruction"])
            removed = {"run_id", "invocation_id", "agent", "calculations", "documents", "artifact_refs"}
            choices = {"calculation_selections", "document_selections"}
            self.assertEqual(set(context["output_format_guide"]["required"]),
                             (set(packet["output_schema"]["required"]) - removed) | choices)
            self.assertEqual(set(context["output_format_guide"]["properties"]),
                             (set(packet["output_schema"]["properties"]) - removed) | choices)
            self.assertNotIn("enum", context["output_format_guide"]["$defs"]["evidence_id"])
            self.assertEqual(context["authoritative_output_schema_hash"], packet["output_schema_hash"])
            self.assertEqual(
                packet["output_schema"]["$defs"]["evidence_id"]["enum"],
                packet["allowed_evidence_ids"],
            )
            limited = next(item for item in context["provider_coverage"]["providers"]
                           if item["provider"] == "test-provider")
            self.assertEqual(limited["limitations"], ["license-limited"])
            self.assertEqual(limited["dataset_status_counts"]["research_discovery"],
                             {"AVAILABLE": 1, "SOURCE_LIMITED": 1})
            self.assertEqual(limited["dataset_observations"][0]["failure_code"],
                             "LICENSE_REQUIRED")
            self.assertLess(len(serialize_multidimensional_model_context(packet).encode()),
                            len(full.encode()))
            broken = copy.deepcopy(packet)
            broken["evidence_catalog"] = []
            with self.assertRaisesRegex(MultidimensionalStageError, "CATALOG_BINDING_INVALID"):
                serialize_multidimensional_model_context(broken)

    def test_formal_hook_delivers_measured_compact_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            environment = self.targeted_environment(run, task)
            parent, child = "parent-compact-input", "child-compact-input"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(task, parent=parent), environ=environment,
            )
            self.assertEqual(allowed["decision"], "ALLOW")
            event, response = handle_hook_event(
                self.start_payload(task, parent=parent, child=child), environ=environment,
            )
            context = response["hookSpecificOutput"]["additionalContext"]
            delivered = json.loads(context)
            self.assertEqual(delivered["frozen_packet_hash"], canonical_hash(packet))
            self.assertEqual(delivered["model_context_version"],
                             "multidimensional-model-context/2.0.0")
            diagnostics = event["context_binding"]["delivery_diagnostics"]
            self.assertEqual(diagnostics["model_context_bytes"], len(context.encode()))
            self.assertEqual(diagnostics["evidence_catalog_rows"],
                             len(packet["evidence_catalog"]))
            self.assertEqual(diagnostics["token_count_status"], "NOT_OBSERVED")


    def test_merged_live_gate_reads_original_preparation_without_rewriting_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            final = root / "final"
            source.mkdir()
            final.mkdir()
            handoff = stock_handoff(1)
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            base = gate_for(handoff, run_id="merged-live-test")
            base["source_mode"] = "live-read-only"
            base["source_bundle_hash"] = "b" * 64
            base["bundle_hash"] = canonical_hash({
                key: value for key, value in base.items() if key != "bundle_hash"
            })
            base_path = source / "gate.json"
            base_path.write_text(json.dumps(base))
            preparation = {
                "common_cutoff": base["decision_cutoff"],
                "items": [{"security_id": security_id, "status": "READY"}],
                "research_supplements": [],
            }
            preparation["preparation_hash"] = canonical_hash(preparation)
            (source / "data-preparation.json").write_text(json.dumps(preparation))
            merged = dict(base)
            merged["decision_cutoff"] = "2026-09-11T13:00:00Z"
            merged["base_gate_content_hash"] = canonical_hash({
                key: value for key, value in base.items()
                if key not in {"run_id", "bundle_hash"}
            })
            merged["bundle_hash"] = canonical_hash({
                key: value for key, value in merged.items() if key != "bundle_hash"
            })
            final_path = final / "gate.json"
            final_path.write_text(json.dumps(merged))
            self.assertEqual(_load_research_capture_batches(
                gate_path=final_path, gate=merged, security_ids=[security_id],
                base_gate_path=base_path,
            ), [])
            self.assertEqual(json.loads((source / "data-preparation.json").read_text()), preparation)
            # 新执行身份只能在显式冻结资料复用模式下与原采集身份不同。
            rebound = dict(merged, run_id="new-execution")
            rebound["bundle_hash"] = canonical_hash({
                key: value for key, value in rebound.items() if key != "bundle_hash"
            })
            with self.assertRaisesRegex(MultidimensionalStageError, "BASE_GATE_BINDING_INVALID"):
                _load_research_capture_batches(gate_path=final_path, gate=rebound,
                    security_ids=[security_id], base_gate_path=base_path)
            self.assertEqual(_load_research_capture_batches(gate_path=final_path, gate=rebound,
                security_ids=[security_id], base_gate_path=base_path,
                allow_source_run_rebinding=True), [])
            with self.assertRaisesRegex(MultidimensionalStageError, "BASE_GATE_REQUIRED"):
                _load_research_capture_batches(
                    gate_path=final_path, gate=merged, security_ids=[security_id],
                )
            wrong = dict(merged, base_gate_content_hash="0" * 64)
            with self.assertRaisesRegex(MultidimensionalStageError, "BASE_GATE_BINDING_INVALID"):
                _load_research_capture_batches(
                    gate_path=final_path, gate=wrong, security_ids=[security_id],
                    base_gate_path=base_path,
                )

    def test_industry_route_admits_selected_moomoo_peer_but_not_unrelated_security(self) -> None:
        facts = [
            {"evidence_id": f"ev-{index}", "security_id": security_id,
             "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
             "dataset": dataset, "semantic_field": field}
            for index, (security_id, dataset, field) in enumerate((
                ("US:COMMON_STOCK:MRVL", "business_segments", "moomoo_revenue_breakdown"),
                ("US:COMMON_STOCK:ALAB", "research_discovery", "moomoo_morningstar_section:bull_case"),
                ("US:COMMON_STOCK:NVDA", "business_segments", "moomoo_revenue_breakdown"),
                ("US:COMMON_STOCK:ALAB", "options_snapshot", "moomoo_option_quote"),
            ))
        ]
        selected = _facts_for_capability(
            facts, capability="INDUSTRY_COMPARISON",
            security_ids=["US:COMMON_STOCK:MRVL", "US:COMMON_STOCK:ALAB"],
            benchmark_id=None,
        )
        self.assertEqual([fact["evidence_id"] for fact in selected], ["ev-0", "ev-1"])
        for family in ("sec", "yahoo"):
            with self.subTest(family=family):
                supplement = [
                    {"evidence_id": f"business-{i}", "security_id": security,
                     "source_family": family, "source_type": "REGULATORY_FILING",
                     "dataset": dataset, "semantic_field": "sec_business_and_segment_candidate_text"}
                    for i, (security, dataset) in enumerate((
                        ("US:COMMON_STOCK:ALAB", "business_segments"),
                        ("US:COMMON_STOCK:NVDA", "business_segments"),
                        ("US:COMMON_STOCK:ALAB", "insider_transactions"),
                    ))
                ]
                selected = _facts_for_capability(
                    supplement, capability="INDUSTRY_COMPARISON",
                    security_ids=["US:COMMON_STOCK:MRVL", "US:COMMON_STOCK:ALAB"],
                    benchmark_id=None,
                )
                self.assertEqual([f["evidence_id"] for f in selected], ["business-0"])

    @staticmethod
    def mrvl_daily_inputs(*, include_spy: bool) -> tuple[dict, dict]:
        fixture = ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["draft_id"] = "draft-technical-mrvl"
        payload["positions"] = [{"ticker": "MRVL", "quantity": 1, "cost_basis": 100}]
        handoff = build_handoff(
            build_manual_draft(payload), confirmed=True,
            confirmed_at="2026-09-11T20:05:00+08:00",
        )
        gate = gate_for(handoff)
        days = []
        for index in range(32):
            day = date(2026, 8, 10) + timedelta(days=index)
            if day.weekday() < 5:
                days.append(day.isoformat())
        series = [("US:COMMON_STOCK:MRVL", 2)]
        if include_spy:
            series.append(("US:SPY", 1))
        for security_id, scale in series:
            for day_index, day in enumerate(days):
                for field, value, unit in (
                    ("historical_close_price", 100 + day_index * scale, "USD"),
                    ("adjusted_close_price", 100 + day_index * scale, "USD"),
                    ("share_volume", 1000 + day_index * 10, "shares"),
                ):
                    gate["allowed_evidence"].append({
                        "evidence_id": f"ev-{security_id.split(':')[-1].lower()}-{day}-{field}",
                        "security_id": security_id, "semantic_field": field,
                        "value": str(value), "unit": unit,
                        "source_id": "synthetic-yahoo-daily", "source_type": "yahoo",
                        "as_of": day + "T20:00:00Z",
                        "published_at": day + "T20:00:00Z",
                        "retrieved_at": "2026-09-11T11:00:00Z",
                        "metadata": {"trading_date": day},
                    })
        gate["allowed_evidence_ids"] = sorted(
            item["evidence_id"] for item in gate["allowed_evidence"]
        )
        gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        return handoff, gate

    @classmethod
    def prepare_mrvl_daily_run(cls, root: Path, *, include_spy: bool) -> Path:
        handoff, gate = cls.mrvl_daily_inputs(include_spy=include_spy)
        handoff_path, gate_path = root / "handoff.json", root / "gate.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        run = root / "run"
        prepare_multidimensional_stage_run(
            ROOT, handoff_path=handoff_path, gate_path=gate_path,
            run_dir=run, run_id="technical-mrvl-test", model="gpt-5.6-terra",
        )
        return run

    @staticmethod
    def research_bindings(run: Path) -> dict:
        handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
        request = json.loads((run / "council-request.json").read_text())
        gate = json.loads((run / "evidence/gate.json").read_text())
        return {
            "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
            "portfolio_hash": handoff["portfolio_hash"],
            "council_request_id": request["request_id"],
            "council_request_hash": request["request_hash"],
            "decision_cutoff": gate["decision_cutoff"],
        }

    def test_forward_host_command_ignores_desktop_config_and_keeps_strict_product_config(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            with patch(
                "product.runtime.multidimensional_stage.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "test stop"),
            ) as launched:
                result, code = launch_multidimensional_stage(ROOT, run_dir=run)
            command = launched.call_args.args[0]
            self.assertEqual(command[command.index("exec") + 1], "--ignore-user-config")
            self.assertIn("--strict-config", command)
            self.assertEqual(command[command.index("-C") + 1], str(ROOT / "product"))
            self.assertTrue(any("mcp_servers.fixture_runtime=" in value for value in command))
            for agent_name in ("runtime_company_analyst", "runtime_market_catalyst"):
                self.assertTrue(any(
                    value.startswith(f"agents.{agent_name}=")
                    and str(ROOT / "product/.codex/agents" / f"{agent_name}.toml") in value
                    for value in command
                ))
            self.assertIn("agents.max_threads=3", command)
            self.assertEqual(
                command,
                json.loads((run / "invocation/environment-manifest.json").read_text())["command"],
            )
            self.assertEqual(result["failure_code"], "MULTIDIMENSIONAL_CODEX_PROCESS_FAILED")
            self.assertEqual(code, 7)

    def test_forward_macro_market_view_is_bound_and_other_packets_keep_legacy_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for capability in ("MACRO_CONTEXT", "MARKET_STATE"):
                task = next(item for item in index["tasks"] if item["capability"] == capability)
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                view = packet["provider_coverage"]
                self.assertEqual("TASK_SCOPED_PROVIDER_COVERAGE", view["view_kind"])
                self.assertEqual(capability, view["capability"])
                self.assertIn("global_coverage", view["providers"][0])
                self.assertNotIn("evidence_ids", str(view["providers"]))
                self.assertIn("global_coverage", packet["instruction"])
                if capability == "MACRO_CONTEXT":
                    self.assertIn("最新可用观察", packet["instruction"])
                    self.assertIn("不得自行缩写为million/billion或改写为亿美元", packet["instruction"])
                else:
                    self.assertNotIn("最新可用观察", packet["instruction"])
                    self.assertNotIn("不得自行缩写为million/billion或改写为亿美元", packet["instruction"])
            other = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            other_packet = build_multidimensional_dispatch_packet(ROOT, run, other["task_name"])
            self.assertNotIn("view_kind", other_packet["provider_coverage"])
            self.assertNotIn("global_coverage", other_packet["instruction"])

            audit_path = run / "audit/provider-coverage.json"
            audit = json.loads(audit_path.read_text())
            audit["providers"][0]["limitations"].append("tampered")
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            macro = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            with self.assertRaisesRegex(MultidimensionalStageError, "COVERAGE_AUDIT_HASH_MISMATCH"):
                build_multidimensional_dispatch_packet(ROOT, run, macro["task_name"])
            audit["coverage_hash"] = canonical_hash({
                key: value for key, value in audit.items() if key != "coverage_hash"
            })
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            with self.assertRaisesRegex(MultidimensionalStageError, "COVERAGE_VIEW_BINDING_MISMATCH"):
                build_multidimensional_dispatch_packet(ROOT, run, macro["task_name"])
            self.assertEqual(
                other_packet, build_multidimensional_dispatch_packet(ROOT, run, other["task_name"])
            )

    def test_provider_view_preserves_empty_official_and_failed_multisecurity_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            coverage = json.loads((run / "audit/provider-coverage.json").read_text())
            index = json.loads((run / "research/dispatch-index.json").read_text())
            market = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            macro = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            for provider in coverage["providers"]:
                if provider["provider"] == "bls":
                    provider["observed_status"] = "AVAILABLE"
                    provider["evidence_count"] = 2
                if provider["provider"] == "moomoo_sg":
                    def observation(security_id, dataset, status, failure_code):
                        return {
                            "security_id": security_id, "dataset": dataset,
                            "status": status, "failure_code": failure_code,
                            "checked_at": coverage["decision_cutoff"],
                            "as_of": None, "evidence_ids": [],
                            "limitations": ["limited"] if failure_code else [],
                        }
                    provider["dataset_observations"] = [
                        observation("US:COMMON_STOCK:AAPL", "market_breadth", "SOURCE_LIMITED", "QUOTE_FAILED"),
                        observation("US:COMMON_STOCK:MSFT", "market_breadth", "SOURCE_LIMITED", "QUOTE_FAILED"),
                        observation("US:COMMON_STOCK:AAPL", "analyst_expectations", "AVAILABLE", None),
                        observation("US:COMMON_STOCK:AAPL", "future_unknown_dataset", "PARTIAL", None),
                    ]
            coverage["coverage_hash"] = canonical_hash({
                key: value for key, value in coverage.items() if key != "coverage_hash"
            })
            market_view = _task_provider_coverage_view(
                coverage, task=market, evidence=[], stage="MULTI_DIMENSIONAL_HOLDING_RESEARCH",
            )
            moomoo = next(item for item in market_view["providers"] if item["provider"] == "moomoo_sg")
            self.assertEqual(3, len(moomoo["dataset_observations"]))
            self.assertEqual(
                {"US:COMMON_STOCK:AAPL", "US:COMMON_STOCK:MSFT"},
                {item["security_id"] for item in moomoo["dataset_observations"]},
            )
            self.assertEqual("SOURCE_LIMITED", moomoo["dataset_observations"][0]["status"])
            yahoo = [item for item in market_view["providers"] if item["provider"] == "yahoo"]
            self.assertEqual(2, len(yahoo))
            self.assertEqual(2, len({item["plane"] for item in yahoo}))
            macro_view = _task_provider_coverage_view(
                coverage, task=macro, evidence=[], stage="MULTI_DIMENSIONAL_HOLDING_RESEARCH",
            )
            bls = next(item for item in macro_view["providers"] if item["provider"] == "bls")
            self.assertEqual("NO_DATASET_DETAIL", bls["dataset_observation_scope"])
            self.assertEqual(2, bls["global_coverage"]["evidence_count"])
            self.assertEqual("AVAILABLE", bls["global_coverage"]["observed_status"])

            invalid = copy.deepcopy(coverage)
            next(item for item in invalid["providers"] if item["provider"] == "moomoo_sg")["dataset_observations"][0]["checked_at"] = "2030-01-01T00:00:00Z"
            invalid["coverage_hash"] = canonical_hash({
                key: value for key, value in invalid.items() if key != "coverage_hash"
            })
            with self.assertRaisesRegex(MultidimensionalStageError, "COVERAGE_VIEW_AFTER_CUTOFF"):
                _task_provider_coverage_view(
                    invalid, task=market, evidence=[], stage="MULTI_DIMENSIONAL_HOLDING_RESEARCH",
                )

    def test_selected_but_unmaterialized_peers_still_forbid_comparison_claims(self) -> None:
        task = {
            "selected_peer_candidates": [{
                "candidate_id": "candidate-amd",
                "materialization_status": "NOT_MATERIALIZED",
                "materialized_security_id": None,
            }],
        }
        self.assertEqual([], _frozen_peer_candidates(task))
        task["selected_peer_candidates"].append({
            "candidate_id": "candidate-intc",
            "materialization_status": "FROZEN",
            "materialized_security_id": "US:COMMON_STOCK:INTC",
        })
        self.assertEqual(
            ["US:COMMON_STOCK:INTC"],
            [item["materialized_security_id"] for item in _frozen_peer_candidates(task)],
        )

    def test_evidence_closure_requires_exact_full_identifier(self) -> None:
        full_id = "ev-official-macro-f4c54045b82c4676c50556b5c53d6e024bb95adaa770be97e8b5c01b68902216"
        value = {"claims": [{"evidence_refs": [full_id]}]}
        self.assertEqual(
            {full_id}, validate_evidence_closure(value, allowed_evidence_ids=[full_id])
        )
        for invalid in (full_id[:-12], full_id.replace("c53d6e", "c01b68"), "ev-unknown"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ArtifactValidationError, "EVIDENCE_CLOSURE_FAILED"
            ):
                validate_evidence_closure(
                    {"claims": [{"evidence_refs": [invalid]}]},
                    allowed_evidence_ids=[full_id],
                )

    def test_prepare_independent_stage_reuses_forward_plan_without_skeptic_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="counter-stage-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            manifest = json.loads((run / "run_manifest.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual("INDEPENDENT_COUNTER_THESIS_RESEARCH", manifest["stage"])
            self.assertEqual(manifest["stage"], request["stage"])
            self.assertFalse(manifest["complete_portfolio_decision"])
            self.assertNotIn("runtime_skeptic", {task["agent"] for task in index["tasks"]})
            macro = next(task for task in index["tasks"] if task["capability"] == "MACRO_CONTEXT")
            packet = json.loads((run / macro["packet_path"]).read_text())
            self.assertNotIn("view_kind", packet["provider_coverage"])
            self.assertNotIn("global_coverage", packet["instruction"])
            self.assertNotIn("最新可用观察", packet["instruction"])
            self.assertIn("先通过非空 fixture_runtime.query 实际读取", packet["instruction"])
            self.assertIn("当前只有一只普通股持仓", packet["instruction"])
            self.assertIn("不得因缺少第二只持仓", packet["instruction"])
            self.assertEqual(
                packet["citation_contract"]["required_form"],
                "FULL_EVIDENCE_ID_FROM_TOOL_RESULT",
            )
            self.assertEqual(packet["citation_contract"]["aliases"], {})
            old_run = root / "old-run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=old_run, run_id="old-stage-run", model="gpt-5.6-terra",
            )
            old_index = json.loads((old_run / "research/dispatch-index.json").read_text())
            old_macro = next(task for task in old_index["tasks"] if task["capability"] == "MACRO_CONTEXT")
            old_packet = json.loads((old_run / old_macro["packet_path"]).read_text())
            self.assertNotIn("先通过非空 fixture_runtime.query 实际读取", old_packet["instruction"])

    def test_moomoo_datasets_route_to_existing_capabilities_without_new_domain(self):
        def fact(evidence_id, security_id, dataset, field):
            return {
                "evidence_id": evidence_id, "security_id": security_id,
                "dataset": dataset, "semantic_field": field,
                "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
            }
        evidence = [
            fact("rating", "US:COMMON_STOCK:AAPL", "research_discovery", "moomoo_rating_item:x"),
            fact("owner", "US:COMMON_STOCK:AAPL", "institutional_ownership", "moomoo_institutional_aggregate:x"),
            fact("option", "US:COMMON_STOCK:AAPL", "options_snapshot", "moomoo_option_quote:x"),
            fact("macro", "US:MARKET", "macro_history", "moomoo_us_cpi_yoy:x"),
            fact("market", "US:MARKET", "fedwatch_expectations", "moomoo_fedwatch:x"),
        ]
        expected = {
            "RESEARCH_REPORT": {"rating"}, "OWNERSHIP_DISCLOSURE": {"owner"},
            "OPTIONS_FLOW": {"option"}, "MACRO_CONTEXT": {"macro"},
            "MARKET_STATE": {"market"},
        }
        for capability, ids in expected.items():
            selected = _facts_for_capability(
                evidence, capability=capability,
                security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
            )
            self.assertEqual(ids, {item["evidence_id"] for item in selected})

    def test_provider_neutral_routing_coverage_separates_delivery_from_actual_use(self):
        evidence = [{
            "evidence_id": "ev-option", "security_id": "US:COMMON_STOCK:AAPL",
            "dataset": "options_snapshot", "semantic_field": "moomoo_option_quote:x",
            "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
        }]
        coverage = _capability_routing_coverage(
            evidence, capture_batches=[{"capabilities": [{
                "source": "moomoo_sg", "dataset": "options_snapshot",
                "evidence_ids": ["ev-option"],
            }]}], security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        option = next(
            item for item in coverage["dataset_observations"]
            if item["dataset"] == "options_snapshot"
        )
        self.assertEqual("CLOSED", coverage["status"])
        self.assertEqual(1, option["capture_evidence_count"])
        self.assertEqual(1, option["gate_eligible_evidence_count"])
        self.assertEqual(1, option["delivered_evidence_count"])
        self.assertEqual("NOT_EVALUATED_AT_PREPARATION", option["actual_research_use_status"])

        wrong_scope = [dict(evidence[0], security_id="US:COMMON_STOCK:MSFT")]
        failed = _capability_routing_coverage(
            wrong_scope, capture_batches=[],
            security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        self.assertEqual("FAILED", failed["status"])
        self.assertTrue(failed["failure_codes"][0].startswith(
            "CAPABILITY_EVIDENCE_NOT_ROUTED:OPTIONS_FLOW:"
        ))

    def test_provider_neutral_routing_counts_yahoo_primary_options(self):
        evidence = [{
            "evidence_id": "ev-yahoo-option", "security_id": "US:COMMON_STOCK:AAPL",
            "dataset": "options_snapshot", "semantic_field": "option_chain_contract:AAPL",
            "source_family": "yahoo", "source_type": "options",
        }]
        coverage = _capability_routing_coverage(
            evidence, capture_batches=[{"capabilities": [{
                "source": "yahoo", "dataset": "options_snapshot",
                "evidence_ids": ["ev-yahoo-option"],
            }]}], security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        option = next(
            item for item in coverage["dataset_observations"]
            if item["dataset"] == "options_snapshot"
        )
        self.assertEqual("CLOSED", coverage["status"])
        self.assertEqual("DELIVERED", option["delivery_status"])
        self.assertEqual(1, option["capture_evidence_count"])
        self.assertEqual(1, option["gate_eligible_evidence_count"])
        self.assertEqual(1, option["delivered_evidence_count"])

    @staticmethod
    def dimension_draft(task: dict, *, include_impact: bool = True) -> dict:
        """测试作者的当前语义草稿；不在 Stop 工具中改写传入原稿。"""
        draft = MultidimensionalStageTests.formal_dimension_draft(task, include_impact=include_impact)
        for key in ("run_id", "invocation_id", "agent", "calculations", "documents", "artifact_refs"):
            draft.pop(key, None)
        draft.update(calculation_selections=[], document_selections=[])
        return draft

    @staticmethod
    def formal_dimension_draft(task: dict, *, include_impact: bool = True) -> dict:
        """显式完整报告测试输入：仅用于旧报告/正式契约读取和负例。"""
        gap = {
            "gap_id": f"gap:{task['task_id']}",
            "reason_code": "UNKNOWN",
            "description": "测试资料不足。",
        }
        if include_impact:
            gap["impact"] = "不形成研究主张。"
        return {
            "run_id": task["run_id"],
            "invocation_id": task["invocation_id"],
            "agent": task["agent"],
            "status": "INSUFFICIENT_EVIDENCE",
            "sufficiency": "INSUFFICIENT",
            "evaluation_status": "NOT_EVALUATED",
            "summary": "测试报告明确保留资料缺口。",
            "claims": [],
            "assumptions": [],
            "calculations": [],
            "documents": [],
            "research_relationships": [],
            "limitations": ["测试资料不足。"],
            "observation_conditions": [],
            "data_gaps": [gap],
            "artifact_refs": [],
        }

    @staticmethod
    def targeted_environment(run: Path, task: dict) -> dict[str, str]:
        invocation_dir = run / "invocation"
        invocation_dir.mkdir(exist_ok=True)
        return {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                invocation_dir / "subagent-events.jsonl"
            ),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                invocation_dir / "subagent-dispatches.jsonl"
            ),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": task["agent"],
            "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            "STOCK_AGENT_RESEARCH_TASK_NAME": task["task_name"],
        }

    @staticmethod
    def dispatch_payload(task: dict, *, parent: str) -> dict:
        return {
            "hook_event_name": "PreToolUse",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "tool_name": "spawn_agent",
            "tool_use_id": f"tool:{parent}",
            "cwd": str(ROOT / "product"),
            "model": "gpt-5.6-terra",
            "permission_mode": "workspace-write",
            "tool_input": {
                "agent_type": task["agent"],
                "task_name": task["task_name"],
                "fork_turns": "none",
                "message": "启动冻结多维研究任务。",
            },
        }

    @staticmethod
    def stop_payload(task: dict, draft: dict, *, parent: str, child: str) -> dict:
        return {
            "hook_event_name": "SubagentStop",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "agent_id": child,
            "agent_type": task["agent"],
            "model": "gpt-5.6-terra",
            "cwd": str(ROOT / "product"),
            "permission_mode": "read-only",
            "stop_hook_active": False,
            "last_assistant_message": json.dumps(draft),
        }

    @staticmethod
    def start_payload(task: dict, *, parent: str, child: str) -> dict:
        return {
            "hook_event_name": "SubagentStart",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "agent_id": child,
            "agent_type": task["agent"],
            "model": "gpt-5.6-terra",
            "cwd": str(ROOT / "product"),
            "permission_mode": "read-only",
        }

    def complete_with_explicit_gaps(self, run: Path) -> None:
        from product.runtime.research_input import load_research_input, research_input_binding, research_subjects
        invocation_dir = run / "invocation"
        invocation_dir.mkdir()
        index = json.loads((run / "research/dispatch-index.json").read_text())
        handoff = load_research_input(run)
        request = json.loads((run / "council-request.json").read_text())
        gate = json.loads((run / "evidence/gate.json").read_text())
        bindings = {
            **research_input_binding(handoff),
            "council_request_id": request["request_id"],
            "council_request_hash": request["request_hash"],
            "decision_cutoff": gate["decision_cutoff"],
        }
        events = []
        stage = json.loads((run / "run_manifest.json").read_text())["stage"]
        for task in index["tasks"]:
            if task["capability"] in {"MACRO_CONTEXT", "MARKET_STATE"}:
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                if stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH":
                    self.assertEqual("TASK_SCOPED_PROVIDER_COVERAGE", packet["provider_coverage"]["view_kind"])
                else:
                    self.assertNotIn("view_kind", packet["provider_coverage"])
            invocation = json.loads((run / task["invocation_path"]).read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": task["run_id"],
                    "invocation_id": task["invocation_id"],
                    "agent": task["agent"],
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "测试报告明确保留资料缺口。",
                    "claims": [], "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": ["测试不形成投资判断。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": f"gap:{task['task_id']}",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "仅验证交接结构。",
                    }],
                    "artifact_refs": [],
                },
                task=task,
                invocation=invocation,
                expected_bindings=bindings,
                allowed_security_ids=[
                    item["security_id"] for item in research_subjects(handoff)
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_documents=task.get("allowed_documents", []),
            )
            output = persist_dimension_report(
                run / "research/reports" / task["task_id"],
                report=report,
                evidence=[],
            )
            events.append({
                "hook_event_name": "SubagentStop",
                "output_capture": {
                    "status": "SAVED", "task_id": task["task_id"],
                    "path": str(Path(output["json"]).relative_to(run)),
                },
            })
        (invocation_dir / "subagent-dispatches.jsonl").write_text(
            "\n".join(json.dumps({
                "task_name": task["task_name"], "decision": "ALLOW"
            }) for task in index["tasks"]) + "\n",
            encoding="utf-8",
        )
        (invocation_dir / "subagent-events.jsonl").write_text(
            "\n".join(json.dumps(item) for item in events) + "\n",
            encoding="utf-8",
        )
        finalize_multidimensional_stage_run(ROOT, run)

    def test_parent_and_dimension_structured_output_properties_have_types(self) -> None:
        def walk(value, path="$"):
            if isinstance(value, dict):
                for name, child in value.get("properties", {}).items():
                    self.assertTrue(
                        "type" in child or any(key in child for key in ("$ref", "anyOf", "oneOf", "allOf")),
                        f"{path}.properties.{name} 缺少显式类型",
                    )
                for name, child in value.items():
                    walk(child, f"{path}.{name}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
        walk(_parent_output_schema("run", 19))
        self.assertEqual(
            ["stage", "run_id", "dispatched", "completed"],
            _parent_output_schema("run", 19)["required"],
        )
        walk(_dynamic_draft_schema(
            ROOT, run_id="run", invocation_id="inv",
            agent="runtime_market_catalyst", allowed_evidence_ids=["ev-1"],
            allowed_artifact_refs=["artifact.json"], allowed_documents=[],
        ))

    def prepare(self, root: Path, count: int = 2, **options):
        handoff = stock_handoff(count)
        gate = gate_for(handoff)
        handoff_path, gate_path = root / "handoff.json", root / "gate.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        run = root / "run"
        result = prepare_multidimensional_stage_run(
            ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
            run_id="multi-stage-run", model="gpt-5.6-terra",
            **options,
        )
        return run, result

    def test_prepare_creates_explicit_all_holding_dimension_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, result = self.prepare(Path(temp))
            self.assertEqual(result["status"], "PREPARED")
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], STAGE_VERSION)
            self.assertEqual(manifest["stage"], "MULTI_DIMENSIONAL_HOLDING_RESEARCH")
            self.assertFalse(manifest["complete_portfolio_decision"])
            self.assertEqual(manifest["downstream_stages_started"], [])
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual(index["schema_version"], DISPATCH_VERSION)
            self.assertEqual(len(index["tasks"]), 14)  # 六个逐股维度 + Macro/Market 两项共享研究
            self.assertEqual(
                {item["agent"] for item in index["tasks"]},
                {"runtime_company_analyst", "runtime_market_catalyst"},
            )
            macro = [item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"]
            market = [item for item in index["tasks"] if item["capability"] == "MARKET_STATE"]
            self.assertEqual(len(macro), 1)
            self.assertEqual(len(market), 1)
            self.assertEqual(
                macro[0]["security_ids"],
                ["US:COMMON_STOCK:AAPL", "US:COMMON_STOCK:MSFT"],
            )
            self.assertEqual(macro[0]["depends_on"], [])
            self.assertEqual(market[0]["depends_on"], [])
            self.assertEqual(
                manifest["research_input_topology"]["domains"]["MACRO"],
                ["MACRO_CONTEXT"],
            )
            self.assertEqual(macro[0]["agent"], market[0]["agent"])
            macro_packet = json.loads((run / macro[0]["packet_path"]).read_text())
            market_packet = json.loads((run / market[0]["packet_path"]).read_text())
            self.assertIn("当前有多只普通股持仓", macro_packet["instruction"])
            self.assertIn("当前有多只普通股持仓", market_packet["instruction"])
            self.assertNotIn("当前只有一只普通股持仓", macro_packet["instruction"])
            task = index["tasks"][0]
            packet = json.loads((run / task["packet_path"]).read_text())
            invocation = json.loads((run / task["invocation_path"]).read_text())
            self.assertEqual(packet["output_schema"]["$id"], "research-dimension-draft/2.0.0")
            self.assertEqual(packet["output_schema_hash"], canonical_hash(packet["output_schema"]))
            self.assertEqual(
                invocation["output_contract"]["draft_schema_hash"],
                packet["output_schema_hash"],
            )
            self.assertEqual(
                invocation["output_contract"]["sha256"],
                manifest["research_input_topology"]["default_output_contract"]["sha256"],
            )

    def test_company_report_routes_issuer_body_guidance_and_expectations_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            issuer = {
                "evidence_id": "ev-issuer-body", "security_id": security_id,
                "semantic_field": "earnings_release", "value": (
                    "Issuer earnings release discussion provides a verified operating update. " * 30
                ),
                "source_id": "sec-filing:test", "source_type": "sec",
                "source_locator": "https://www.sec.gov/Archives/example.htm",
                "as_of": "2026-09-10T20:00:00Z", "published_at": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z", "raw_content_hash": "a" * 64,
                "section": "earnings_release", "metadata": {"description": "Issuer earnings release"},
            }
            issuer_toc = {
                **issuer, "evidence_id": "ev-issuer-toc",
                "value": "Item 2. Management Discussion and Analysis 28",
                "semantic_field": "management_discussion",
            }
            guidance = {
                **issuer, "evidence_id": "ev-guidance", "semantic_field": "sec_issuer_guidance_candidate_text",
                "source_id": "sec-guidance:test", "source_family": "sec",
            }
            expectation = {
                **issuer, "evidence_id": "ev-expectation", "semantic_field": "yahoo_earnings_trend",
                "source_id": "yahoo-quote-summary:AAPL", "source_type": "yahoo",
                "source_family": "yahoo",
            }
            gate["allowed_evidence"].extend([issuer, issuer_toc, guidance, expectation])
            gate["allowed_evidence_ids"] = sorted(
                item["evidence_id"] for item in gate["allowed_evidence"]
            )
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="issuer-material-routing", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, task["task_name"], include_dependency_reports=False
            )
            self.assertEqual(packet["company_material_coverage"]["issuer_body_count"], 1)
            self.assertEqual(packet["company_material_coverage"]["public_lead_evidence_ids"], [])
            self.assertNotIn("至少用本任务只读 query 查询其中一条", packet["instruction"])
            self.assertEqual(packet["company_material_coverage"]["guidance_evidence_ids"], ["ev-guidance"])
            self.assertEqual(packet["company_material_coverage"]["expectation_evidence_ids"], ["ev-expectation"])
            self.assertEqual(packet["task"]["allowed_documents"][0]["material_type"], "ISSUER_MATERIAL")
            self.assertNotEqual(
                packet["task"]["allowed_documents"][0]["body_hash"],
                issuer["raw_content_hash"],
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["body_hash"],
                packet["verified_documents"][0]["content"]["body_hash"],
            )
            self.assertEqual(
                packet["verified_documents"][0]["content"]["evidence_id"],
                "ev-issuer-body",
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["retrieved_at"],
                issuer["retrieved_at"],
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["interest_disclosure"]["status"],
                "DECLARED",
            )
            self.assertIn("不得省略问题字段", packet["instruction"])
            self.assertIn("limitations 必须是纯字符串数组", packet["instruction"])
            self.assertIn("gap_id、reason_code、description、impact", packet["instruction"])
            self.assertEqual(packet["verified_documents"][0]["content"]["classification"], "SEC_EARNINGS_RELEASE_EXCERPT")
            self.assertEqual(packet["task"]["allowed_documents"][0]["title"],
                             "SEC filing form unknown, earnings_release excerpt")
            self.assertIn("ev-guidance", packet["allowed_evidence_ids"])
            self.assertIn("ev-expectation", packet["allowed_evidence_ids"])
            macro = [item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"]
            market = [item for item in index["tasks"] if item["capability"] == "MARKET_STATE"]
            self.assertEqual(macro[0]["skill_name"], market[0]["skill_name"])
            self.assertNotEqual(macro[0]["invocation_id"], market[0]["invocation_id"])
            macro_packet = json.loads((run / macro[0]["packet_path"]).read_text())
            market_packet = json.loads((run / market[0]["packet_path"]).read_text())
            self.assertNotEqual(
                macro_packet["minimum_questions"], market_packet["minimum_questions"]
            )
            self.assertEqual(
                macro_packet["research_input_topology"],
                market_packet["research_input_topology"],
            )
            macro_invocation = json.loads((run / macro[0]["invocation_path"]).read_text())
            self.assertEqual(
                macro_invocation["research_input_topology"],
                macro_packet["research_input_topology"],
            )
            industry = [
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            ]
            self.assertTrue(all(item["depends_on"] == [] for item in industry))
            self.assertTrue(all(item["model"] == "gpt-5.6-terra" for item in [
                json.loads((run / task["invocation_path"]).read_text()) for task in index["tasks"]
            ]))

    def test_dispatch_packet_has_dynamic_evidence_ids_and_no_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            fundamental = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(ROOT, run, fundamental["task_name"])
            self.assertTrue(packet["allowed_evidence_ids"])
            self.assertEqual(
                packet["output_schema"]["$defs"]["evidence_id"]["enum"],
                packet["allowed_evidence_ids"],
            )
            self.assertNotIn("action", packet["output_schema"]["properties"])
            prompt = build_multidimensional_stage_prompt(ROOT, run)
            self.assertIn("runtime_company_analyst", prompt)
            self.assertIn("runtime_market_catalyst", prompt)
            self.assertIn("不得启动 runtime_skeptic", prompt)

    def test_targeted_prompt_dispatches_only_one_independent_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            macro = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            prompt = build_multidimensional_task_prompt(ROOT, run, macro["task_name"])
            self.assertIn(f"task_name={macro['task_name']}", prompt)
            self.assertIn("只派发一次", prompt)
            other_names = {
                item["task_name"] for item in index["tasks"] if item is not macro
            }
            self.assertTrue(all(name not in prompt for name in other_names))
            dependent = next(item for item in index["tasks"] if item["depends_on"])
            dependency = next(
                item for item in index["tasks"]
                if item["task_id"] == dependent["depends_on"][0]
            )
            chain_prompt = build_multidimensional_task_prompt(
                ROOT, run, dependent["task_name"]
            )
            self.assertIn(dependent["task_name"], chain_prompt)
            self.assertIn(dependency["task_name"], chain_prompt)
            self.assertIn("最小依赖闭包", chain_prompt)
            self.assertNotIn("跨批次复制或注入报告", prompt)
            self.assertIn("不得跨批次复制或注入报告", chain_prompt)

    def test_targeted_hook_scopes_dispatch_and_stop_barrier_to_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(
                item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"
            )
            other = next(item for item in index["tasks"] if item is not target)
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                    invocation_dir / "subagent-events.jsonl"
                ),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                    invocation_dir / "subagent-dispatches.jsonl"
                ),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": target["agent"],
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
                "STOCK_AGENT_RESEARCH_TASK_NAME": target["task_name"],
            }

            def pre(task, tool_id):
                return {
                    "hook_event_name": "PreToolUse",
                    "session_id": "parent-targeted",
                    "turn_id": "turn-targeted",
                    "tool_name": "spawn_agent",
                    "tool_use_id": tool_id,
                    "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra",
                    "permission_mode": "workspace-write",
                    "tool_input": {
                        "agent_type": task["agent"],
                        "task_name": task["task_name"],
                        "fork_turns": "none",
                        "message": "启动冻结多维研究任务。",
                    },
                }

            denied, _ = handle_hook_event(pre(other, "wrong-task"), environ=environment)
            self.assertEqual(denied["decision"], "DENY_DISPATCH_CONTRACT")
            allowed, _ = handle_hook_event(pre(target, "target-task"), environ=environment)
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    target, parent="parent-targeted", child="child-targeted"
                ),
                environ=environment,
            )

            stop = {
                "hook_event_name": "SubagentStop",
                "session_id": "parent-targeted",
                "turn_id": "turn-targeted",
                "agent_id": "child-targeted",
                "agent_type": target["agent"],
                "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"),
                "permission_mode": "read-only",
                "stop_hook_active": False,
                "last_assistant_message": json.dumps({
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "定点 Hook 屏障测试。",
                    "claims": [],
                    "assumptions": [],
                    "calculation_selections": [],
                    "document_selections": [],
                    "research_relationships": [],
                    "limitations": ["测试资料不足。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": "gap-targeted-hook",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "不形成宏观主张。",
                    }],
                }),
            }
            stopped, response = handle_hook_event(stop, environ=environment)
            self.assertEqual(stopped["hook_event_name"], "SubagentStop")
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")
            self.assertEqual(stopped["output_capture"]["task_id"], target["task_id"])
            self.assertEqual(response, {})

    def test_industry_source_identity_copy_gets_one_located_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "INDUSTRY_COMPARISON")
            environment = self.targeted_environment(run, task)
            parent, child = "industry-source-parent", "industry-source-child"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            draft = self.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "wrong-peer-source", "question": "同行证据是什么？",
                "statement": "错误主体。 source_id=sec-filing-wrong as_of=2026-08-19T11:04:23Z",
                "kind": "INTERPRETATION", "evidence_refs": [],
                "research_claim_refs": [], "document_refs": [], "assumption_ids": [],
            }]
            self.assertEqual(_industry_source_identity_copy_paths(task, draft), ["claims[0].statement"])
            legacy_task = {key: value for key, value in task.items() if key != "industry_source_boundary"}
            self.assertEqual(_industry_source_identity_copy_paths(legacy_task, draft), [])
            self.assertEqual(_industry_source_identity_copy_paths(task, {"claims": []}), [])
            first, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
            # 零同行资料的冻结 Schema 先拒绝任何行业主张，不能为诊断放宽它。
            self.assertEqual(first["output_capture"]["failure_code"], "SCHEMA_MAX_ITEMS:$.claims")
            repair = json.loads(response["reason"])
            self.assertEqual(repair["maximum_submissions"], 2)
            self.assertTrue(any(item["path"] == "/claims"
                                for item in repair["validation_details"]["findings"]))
            self.assertIn("evidence_refs", repair["instruction"])
            corrected = copy.deepcopy(draft)
            corrected["claims"] = []  # 此零同行 fixture 正确保留原资料缺口。
            second, _ = handle_hook_event(
                self.stop_payload(task, corrected, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(second["output_capture"]["attempt"], 2)
            self.assertEqual(second["output_capture"]["status"], "SAVED")

    def test_industry_source_identity_copy_second_draft_stays_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            task = next(item for item in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                        if item["capability"] == "INDUSTRY_COMPARISON")
            environment = self.targeted_environment(run, task)
            parent, child = "industry-source-fail-parent", "industry-source-fail-child"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            draft = self.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "wrong-source", "question": "来源身份？",
                "statement": "错误抄录 source_id=wrong", "kind": "INTERPRETATION",
                "evidence_refs": [], "research_claim_refs": [], "document_refs": [],
                "assumption_ids": [],
            }]
            first, _ = handle_hook_event(self.stop_payload(task, draft, parent=parent, child=child), environ=environment)
            self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED")
            second, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(second["output_capture"]["status"], "FAILED")
            self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual(second["output_capture"]["failure_code"], "SCHEMA_MAX_ITEMS:$.claims")
            self.assertEqual(response, {})

    def test_market_internal_calculation_reference_gets_one_located_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            task = next(item for item in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                        if item["capability"] == "MARKET_STATE")
            environment = self.targeted_environment(run, task)
            parent, child = "market-internal-parent", "market-internal-child"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            draft = self.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "market_claim", "question": "市场宽度？",
                "statement": "此计算引用不存在。", "kind": "INTERPRETATION",
                "evidence_refs": [], "research_claim_refs": [], "document_refs": [],
                "assumption_ids": [], "calculation_refs": ["invented_calculation"],
            }]
            first, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(first["output_capture"]["failure_code"],
                             "SCHEMA_EXTRA_PROPERTY:$.claims[0]:calculation_refs")
            repair = json.loads(response["reason"])
            self.assertIn({"code": "SCHEMA_EXTRA_PROPERTY",
                           "path": "/claims/0/calculation_refs"},
                          repair["validation_details"]["findings"])
            second, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual(response, {})

    def test_structural_failure_blocks_once_then_original_agent_repair_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-repair", "child-repair"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(task, parent=parent), environ=environment
            )
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )

            first, response = handle_hook_event(
                self.stop_payload(
                    task,
                    self.dimension_draft(task, include_impact=False),
                    parent=parent,
                    child=child,
                ),
                environ=environment,
            )
            self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED")
            self.assertEqual(response["decision"], "block")
            repair = json.loads(response["reason"])
            self.assertIn("$.data_gaps[0]:impact", repair["validation_error"])
            self.assertEqual(repair["repair_contract"], "research-local-revision/1.0.0")
            self.assertEqual(repair["allowed_paths"], ["/data_gaps/0/impact"])
            self.assertNotIn("output_schema_hash", repair)
            self.assertNotIn("original_draft", repair)
            self.assertTrue((run / first["output_capture"]["raw_path"]).is_file())
            self.assertNotIn(
                task["task_name"],
                _terminal_research_tasks(
                    Path(environment["STOCK_AGENT_SUBAGENT_EVENT_LOG"]),
                    parent_session_id=parent,
                    environment=environment,
                ),
            )
            redispatch = self.dispatch_payload(task, parent=parent)
            redispatch["tool_use_id"] = "tool:repair-redispatch"
            redispatch_record, _ = handle_hook_event(
                redispatch, environ=environment
            )
            self.assertEqual(
                redispatch_record["decision"], "DENY_DUPLICATE_AGENT"
            )

            second, response = handle_hook_event(
                self.stop_payload(
                    task,
                    self.dimension_draft(task, include_impact=True),
                    parent=parent,
                    child=child,
                ),
                environ=environment,
            )
            self.assertEqual(second["hook_event_name"], "SubagentStop")
            self.assertEqual(second["output_capture"]["status"], "SAVED")
            self.assertEqual(second["output_capture"]["attempt"], 2)
            self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED")
            self.assertEqual(response, {})
            self.assertIn(
                task["task_name"],
                _terminal_research_tasks(
                    Path(environment["STOCK_AGENT_SUBAGENT_EVENT_LOG"]),
                    parent_session_id=parent,
                    environment=environment,
                ),
            )
            self.assertTrue((run / second["output_capture"]["raw_path"]).is_file())
            self.assertNotEqual(
                first["output_capture"]["raw_path"],
                second["output_capture"]["raw_path"],
            )

    def test_research_report_condition_repair_is_narrow_and_locatable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            environment = self.targeted_environment(run, task)
            draft = self.formal_dimension_draft(task)
            draft["claims"] = [{"claim_id": "claim-valid"}]
            draft["observation_conditions"] = [{
                "condition_id": "condition-1", "claim_refs": ["claim-missing"],
            }]
            payload = self.stop_payload(task, draft, parent="parent-condition", child="child-condition")
            repair = _multidimensional_repair_packet(
                payload, environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=1,
            )
            self.assertEqual(
                repair["validation_details"],
                {"dangling_references": [{
                    "path": "observation_conditions[0].claim_refs[0]",
                    "claim_id": "claim-missing",
                }], "valid_claim_ids": ["claim-valid"]},
            )
            self.assertEqual(repair["maximum_submissions"], 2)
            self.assertIsNone(_multidimensional_repair_packet(
                payload, environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=2,
            ))
            for code in ("EVIDENCE_REFERENCE_INVALID", "PIT_SOURCE_FUTURE", "PERMISSION_DENIED"):
                self.assertIsNone(_multidimensional_repair_packet(
                    payload, environment, failure_code=code, attempt=1,
                ))
            other = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            other_payload = self.stop_payload(
                other, {**draft, "invocation_id": other["invocation_id"]},
                parent="parent-other", child="child-other",
            )
            self.assertIsNone(_multidimensional_repair_packet(
                other_payload, environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=1,
            ))
            initial_environment = dict(environment)
            initial_environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
            initial_repair = _multidimensional_repair_packet(
                other_payload, initial_environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=1,
            )
            self.assertEqual(
                initial_repair["validation_details"]["dangling_references"],
                [{"path": "observation_conditions[0].claim_refs[0]", "claim_id": "claim-missing"}],
            )
            self.assertIsNone(_multidimensional_repair_packet(
                other_payload, initial_environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=2,
            ))
            draft["observation_conditions"][0]["claim_refs"] = ["claim-valid"]
            self.assertIsNone(_multidimensional_repair_packet(
                self.stop_payload(task, draft, parent="parent-condition", child="child-condition"),
                environment,
                failure_code="DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING", attempt=1,
            ))

    def test_draft_diagnostics_locate_coexisting_errors_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            draft = self.formal_dimension_draft(task)
            draft["claims"] = [{"claim_id": "valuation-gap", "statement": "private report text"}]
            draft["claims"].append({
                "claim_id": "valid-assumption-claim", "evidence_refs": [],
                "assumption_ids": ["assumption-valid"],
            })
            draft["assumptions"] = [{"assumption_id": "assumption-valid"}]
            draft["observation_conditions"] = [{
                "claim_refs": ["missing-claim"], "evidence_refs": ["ev-truncated"],
            }]
            payload = self.stop_payload(task, draft, parent="p", child="c")
            original = copy.deepcopy(payload)
            diagnostic = _multidimensional_draft_diagnostics(
                payload, environment, failure_code="EVIDENCE_CLOSURE_FAILED:ev-truncated",
            )
            self.assertEqual(payload, original)
            self.assertEqual(diagnostic["finding_count"], 3)
            self.assertEqual(diagnostic["first_failure_code"], "EVIDENCE_CLOSURE_FAILED")
            self.assertEqual({item["path"] for item in diagnostic["findings"]}, {
                "claims[0]", "observation_conditions[0].claim_refs[0]",
                "observation_conditions[0].evidence_refs[0]",
            })
            self.assertNotIn("private report text", json.dumps(diagnostic))
            self.assertEqual(diagnostic["task_id"], task["task_id"])
            self.assertFalse(diagnostic["truncated"])
            valid = self.formal_dimension_draft(task)
            valid["claims"] = [draft["claims"][1]]
            valid["assumptions"] = draft["assumptions"]
            no_findings = _multidimensional_draft_diagnostics(
                self.stop_payload(task, valid, parent="p", child="c"), environment,
                failure_code="OTHER_VALIDATION_FAILURE",
            )
            self.assertEqual(no_findings["status"], "NO_KNOWN_ISSUES")
            self.assertEqual(no_findings["finding_count"], 0)

    def test_draft_diagnostics_are_bounded_and_preserve_original_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            draft = self.formal_dimension_draft(task)
            draft["observation_conditions"] = [{"evidence_refs": ["private text " * 50] * 40}]
            payload = self.stop_payload(task, draft, parent="p", child="c")
            diagnostic = _multidimensional_draft_diagnostics(payload, environment, failure_code="ORIGINAL_FAILURE")
            self.assertEqual(diagnostic["finding_count"], 40)
            self.assertEqual(len(diagnostic["findings"]), 32)
            self.assertTrue(diagnostic["truncated"])
            self.assertNotIn("private text", json.dumps(diagnostic))
            for message in ("not JSON", "[]"):
                unavailable = _multidimensional_draft_diagnostics(
                    {"last_assistant_message": message}, environment, failure_code="ORIGINAL_FAILURE",
                )
                self.assertEqual(unavailable["status"], "UNAVAILABLE")
                self.assertEqual(unavailable["first_failure_code"], "ORIGINAL_FAILURE")
            with patch("product.runtime.codex_hook_recorder._research_index", side_effect=OSError("private path")):
                unavailable = _multidimensional_draft_diagnostics(payload, environment, failure_code="ORIGINAL_FAILURE")
            self.assertEqual(unavailable["status"], "UNAVAILABLE")
            self.assertNotIn("private path", json.dumps(unavailable))

    def test_initial_fundamental_condition_repair_stays_in_same_child(self) -> None:
        for repair_succeeds in (True, False):
            with self.subTest(repair_succeeds=repair_succeeds):
                with tempfile.TemporaryDirectory() as temp:
                    run, _ = self.prepare(Path(temp), count=1)
                    index = json.loads((run / "research/dispatch-index.json").read_text())
                    task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
                    environment = self.targeted_environment(run, task)
                    environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
                    parent, child = "parent-condition-repair", "child-condition-repair"
                    allowed, _ = handle_hook_event(
                        self.dispatch_payload(task, parent=parent), environ=environment,
                    )
                    self.assertEqual(allowed["decision"], "ALLOW")
                    handle_hook_event(
                        self.start_payload(task, parent=parent, child=child),
                        environ=environment,
                    )
                    draft = self.dimension_draft(task)
                    draft["observation_conditions"] = [{
                        "condition_id": "condition-dangling",
                        "description": "后续披露再核查。",
                        "claim_refs": ["claim-not-present"],
                        "evidence_refs": [],
                    }]
                    first, response = handle_hook_event(
                        self.stop_payload(task, draft, parent=parent, child=child),
                        environ=environment,
                    )
                    self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
                    self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED")
                    self.assertEqual(response["decision"], "block")
                    repair = json.loads(response["reason"])
                    self.assertEqual(repair["maximum_submissions"], 2)
                    self.assertEqual(repair["validation_details"]["dangling_references"], [{
                        "path": "observation_conditions[0].claim_refs[0]",
                        "claim_id": "claim-not-present",
                    }])
                    self.assertLess(len(response["reason"].encode("utf-8")), 256 * 1024)
                    corrected = copy.deepcopy(draft)
                    if repair_succeeds:
                        corrected["observation_conditions"] = []
                    second, second_response = handle_hook_event(
                        self.stop_payload(task, corrected, parent=parent, child=child),
                        environ=environment,
                    )
                    self.assertEqual(second["output_capture"]["attempt"], 2)
                    self.assertEqual(second_response, {})
                    self.assertEqual(
                        second["output_capture"]["status"],
                        "SAVED" if repair_succeeds else "FAILED",
                    )
                    if not repair_succeeds:
                        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")

    def test_initial_fundamental_ungrounded_claim_repair_is_narrow(self) -> None:
        for repair_succeeds in (True, False):
            with self.subTest(repair_succeeds=repair_succeeds):
                with tempfile.TemporaryDirectory() as temp:
                    run, _ = self.prepare(Path(temp), count=1)
                    index = json.loads((run / "research/dispatch-index.json").read_text())
                    task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
                    environment = self.targeted_environment(run, task)
                    environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
                    parent, child = "parent-ungrounded", "child-ungrounded"
                    draft = self.dimension_draft(task)
                    draft["claims"] = [{
                        "claim_id": "claim-unsupported-valuation",
                        "question": "估值是否可判断？",
                        "statement": "缺少可靠价格与计算条件，当前不能形成估值结论。",
                        "kind": "INTERPRETATION",
                        "evidence_refs": [], "research_claim_refs": [],
                        "document_refs": [], "assumption_ids": [],
                    }]
                    payload = self.stop_payload(task, draft, parent=parent, child=child)
                    old_environment = dict(environment)
                    old_environment.pop("STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT")
                    ordinary_repair = _multidimensional_repair_packet(
                        payload, old_environment,
                        failure_code="DIMENSION_REPORT_CLAIM_UNGROUNDED", attempt=1,
                        trusted_record={"identity_binding": {"status": "BOUND"},
                                        "trusted_task_binding": {"invocation_id": task["invocation_id"]}},
                    )
                    self.assertEqual(ordinary_repair["maximum_submissions"], 2)
                    self.assertNotIn("original_draft", ordinary_repair)
                    self.assertNotIn("output_schema", ordinary_repair)
                    other = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
                    other_payload = self.stop_payload(
                        other, {**draft, "invocation_id": other["invocation_id"]},
                        parent=parent, child=child,
                    )
                    self.assertIsNotNone(_multidimensional_repair_packet(
                        other_payload, environment,
                        failure_code="DIMENSION_REPORT_CLAIM_UNGROUNDED", attempt=1,
                    ))
                    self.assertIsNone(_multidimensional_repair_packet(
                        payload, environment,
                        failure_code="DIMENSION_REPORT_CLAIM_UNGROUNDED", attempt=2,
                    ))
                    allowed, _ = handle_hook_event(
                        self.dispatch_payload(task, parent=parent), environ=environment,
                    )
                    self.assertEqual(allowed["decision"], "ALLOW")
                    handle_hook_event(
                        self.start_payload(task, parent=parent, child=child),
                        environ=environment,
                    )
                    first, response = handle_hook_event(payload, environ=environment)
                    self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
                    self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED")
                    self.assertEqual(response["decision"], "block")
                    repair = json.loads(response["reason"])
                    self.assertEqual(repair["validation_details"]["ungrounded_claims"], [
                        {"path": "claims[0]", "claim_id": "claim-unsupported-valuation"},
                    ])
                    self.assertEqual(repair["validation_details"]["findings"], [{
                        "code": "DIMENSION_REPORT_CLAIM_UNGROUNDED",
                        "path": "claims[0]", "identifier": "claim-unsupported-valuation",
                    }])
                    self.assertEqual(repair["allowed_paths"], ["/claims/0"])
                    self.assertLess(len(response["reason"].encode("utf-8")), 256 * 1024)
                    corrected = copy.deepcopy(draft)
                    if repair_succeeds:
                        corrected["claims"] = []
                    second, second_response = handle_hook_event(
                        self.stop_payload(task, corrected, parent=parent, child=child),
                        environ=environment,
                    )
                    self.assertEqual(second["output_capture"]["attempt"], 2)
                    self.assertEqual(second_response, {})
                    self.assertEqual(
                        second["output_capture"]["status"],
                        "SAVED" if repair_succeeds else "FAILED",
                    )
                    if not repair_succeeds:
                        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")

    def test_initial_fundamental_repairs_all_located_reference_issues_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
            valid_id = task["allowed_evidence_ids"][0]
            draft = self.dimension_draft(task)
            draft["claims"] = [
                {"claim_id": "claim-supported", "question": "已知事实是什么？",
                 "statement": "存在已准入事实。", "kind": "FACT", "evidence_refs": [valid_id],
                 "research_claim_refs": [], "document_refs": [], "assumption_ids": [],
                 },
                {"claim_id": "claim-unsupported", "question": "估值情况？",
                 "statement": "估值资料不足。", "kind": "INTERPRETATION", "evidence_refs": [],
                 "research_claim_refs": [], "document_refs": [], "assumption_ids": [],
                 },
            ]
            draft["observation_conditions"] = [{
                "condition_id": "condition-1", "description": "后续再核查。",
                "claim_refs": ["claim-supported", "claim-missing"],
                "evidence_refs": ["ev-short"],
            }]
            parent, child = "parent-combined", "child-combined"
            allowed, _ = handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            first, response = handle_hook_event(
                self.stop_payload(task, draft, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(response["decision"], "block")
            repair = json.loads(response["reason"])
            self.assertEqual({item["path"] for item in repair["validation_details"]["findings"]}, {
                "claims[1]", "observation_conditions[0].evidence_refs[0]",
                "observation_conditions[0].claim_refs[1]",
            })
            self.assertEqual(repair["allowed_paths"], ["/claims/1", "/observation_conditions/0"])
            corrected = copy.deepcopy(draft)
            corrected["claims"] = corrected["claims"][:1]
            corrected["observation_conditions"][0]["claim_refs"] = ["claim-supported"]
            corrected["observation_conditions"][0]["evidence_refs"] = [valid_id]
            second, response = handle_hook_event(
                self.stop_payload(task, corrected, parent=parent, child=child), environ=environment,
            )
            self.assertEqual(response, {})
            self.assertEqual(second["output_capture"]["status"], "SAVED")
            self.assertEqual(second["output_capture"]["attempt"], 2)

    def test_initial_evidence_repair_requires_complete_bounded_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            environment["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
            draft = self.formal_dimension_draft(task)
            draft["observation_conditions"] = [{"evidence_refs": ["ev-short"]}]
            payload = self.stop_payload(task, draft, parent="p", child="c")
            repair = _multidimensional_repair_packet(
                payload, environment, failure_code="EVIDENCE_CLOSURE_FAILED:ev-short", attempt=1,
            )
            self.assertEqual(repair["validation_details"]["findings"][0]["path"],
                             "observation_conditions[0].evidence_refs[0]")
            self.assertIsNone(_multidimensional_repair_packet(
                payload, environment, failure_code="EVIDENCE_CLOSURE_FAILED:ev-other", attempt=1,
            ))
            self.assertIsNone(_multidimensional_repair_packet(
                payload, environment, failure_code="EVIDENCE_CLOSURE_FAILED:ev-short", attempt=2,
            ))
            old_environment = dict(environment)
            old_environment.pop("STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT")
            compact = _multidimensional_repair_packet(
                payload, old_environment, failure_code="EVIDENCE_CLOSURE_FAILED:ev-short", attempt=1,
            )
            self.assertEqual(compact["validation_details"]["findings"][0]["identifier"], "ev-short")
            self.assertNotIn("original_draft", compact)
            draft["observation_conditions"][0]["evidence_refs"] = ["ev-short"] * 33
            self.assertIsNone(_multidimensional_repair_packet(
                self.stop_payload(task, draft, parent="p", child="c"), environment,
                failure_code="EVIDENCE_CLOSURE_FAILED:ev-short", attempt=1,
            ))

    def test_trusted_start_envelopes_missing_identity_without_changing_raw_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-missing-identity", "child-missing-identity"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(task, parent=parent), environ=environment
            )
            self.assertEqual("ALLOW", allowed["decision"])
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )
            raw = self.dimension_draft(task)
            for key in ("run_id", "invocation_id", "agent"):
                raw.pop(key, None)
            stopped, response = handle_hook_event(
                self.stop_payload(task, raw, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual("SAVED", stopped["output_capture"]["status"])
            self.assertEqual(
                ["agent", "invocation_id", "run_id"],
                sorted(stopped["identity_binding"]["filled_fields"]),
            )
            self.assertEqual(task["invocation_id"], stopped["output_binding"]["invocation_id"])
            self.assertEqual({}, response)
            persisted_raw = json.loads(
                (run / stopped["output_capture"]["raw_path"]).read_text()
            )
            self.assertNotIn("run_id", persisted_raw)
            self.assertNotIn("invocation_id", persisted_raw)
            self.assertNotIn("agent", persisted_raw)

    def test_targeted_company_dependency_chain_is_scoped_and_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
            )
            dependency = next(
                item for item in index["tasks"]
                if item["task_id"] == target["depends_on"][0]
            )
            outside = next(
                item for item in index["tasks"]
                if item["task_id"] not in {dependency["task_id"], target["task_id"]}
            )
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                    invocation_dir / "subagent-events.jsonl"
                ),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                    invocation_dir / "subagent-dispatches.jsonl"
                ),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": target["agent"],
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
                "STOCK_AGENT_RESEARCH_TASK_NAMES": json.dumps(
                    [dependency["task_name"], target["task_name"]]
                ),
            }
            parent = "parent-company-chain"

            outside_record, _ = handle_hook_event(
                self.dispatch_payload(outside, parent=parent), environ=environment
            )
            self.assertEqual(outside_record["decision"], "DENY_UNAPPROVED_AGENT")
            early_record, _ = handle_hook_event(
                self.dispatch_payload(target, parent=parent), environ=environment
            )
            self.assertEqual(early_record["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                early_record["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )

            dependency_record, _ = handle_hook_event(
                self.dispatch_payload(dependency, parent=parent), environ=environment
            )
            self.assertEqual(dependency_record["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    dependency, parent=parent, child="child-company-foundation"
                ),
                environ=environment,
            )
            stopped, _ = handle_hook_event(
                self.stop_payload(
                    dependency, self.dimension_draft(dependency),
                    parent=parent, child="child-company-foundation",
                ),
                environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")

            target_record, _ = handle_hook_event(
                self.dispatch_payload(target, parent=parent), environ=environment
            )
            self.assertEqual(target_record["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    target, parent=parent, child="child-company-report"
                ),
                environ=environment,
            )
            stopped, _ = handle_hook_event(
                self.stop_payload(
                    target, self.dimension_draft(target),
                    parent=parent, child="child-company-report",
                ),
                environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")

            proof = finalize_multidimensional_task_evidence(
                ROOT, run, target["task_name"]
            )
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["scope"], "DEPENDENCY_CHAIN_EVIDENCE")
            self.assertEqual(
                proof["task_names"],
                [dependency["task_name"], target["task_name"]],
            )
            self.assertEqual(len(proof["report_inventory"]), 2)
            self.assertTrue(proof["dependency_chain_complete"])

    def test_initial_targeted_host_execution_finishes_without_retry_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            dependency = next(item for item in index["tasks"] if item["task_id"] == target["depends_on"][0])
            launched = []

            def simulated_codex(command, *, input, cwd, env, **kwargs):
                del command, input, cwd, kwargs
                parent = "parent-initial-chain"
                for number, task in enumerate((dependency, target), start=1):
                    dispatched, _ = handle_hook_event(
                        self.dispatch_payload(task, parent=parent), environ=env,
                    )
                    self.assertEqual(dispatched["decision"], "ALLOW")
                    launched.append(task["task_name"])
                    started, start_response = handle_hook_event(
                        self.start_payload(task, parent=parent, child=f"child-{number}"),
                        environ=env,
                    )
                    self.assertEqual(started["context_binding"]["status"], "DELIVERED")
                    delivered = start_response["hookSpecificOutput"]["additionalContext"]
                    self.assertLessEqual(len(delivered.encode("utf-8")), 256 * 1024)
                    self.assertEqual(
                        json.loads(delivered)["identity"]["task_name"], task["task_name"],
                    )
                    stopped, _ = handle_hook_event(
                        self.stop_payload(
                            task, self.dimension_draft(task), parent=parent,
                            child=f"child-{number}",
                        ), environ=env,
                    )
                    self.assertEqual(stopped["output_capture"]["status"], "SAVED")
                (Path(env["TMPDIR"]) / "final-message.json").write_text(json.dumps({
                    "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
                    "run_id": index["run_id"], "dispatched": 2, "completed": 2,
                }), encoding="utf-8")
                return subprocess.CompletedProcess([], 0, "", "")

            with patch("product.runtime.multidimensional_stage.subprocess.run", side_effect=simulated_codex):
                result, code = launch_multidimensional_stage(
                    ROOT, run_dir=run, task_name=target["task_name"], initial_task=True,
                )
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "PASSED")
            self.assertEqual(launched, [dependency["task_name"], target["task_name"]])
            self.assertFalse(result["complete_holding_research_bundle"])
            proof = json.loads((run / "research/task-execution-proof.json").read_text())
            self.assertEqual(proof["scope"], "DEPENDENCY_CHAIN_EVIDENCE")
            self.assertEqual(len(proof["report_inventory"]), 2)
            self.assertFalse((run / "research/holding-research-bundle.json").exists())
            self.assertFalse((run / "research/retry-adoptions.jsonl").exists())
            self.assertEqual(json.loads((run / "invocation/process-result.json").read_text())["stage_status"], "PASSED")
            with self.assertRaisesRegex(MultidimensionalStageError, "INITIAL_TASK_SCOPE_OR_STATE_INVALID"):
                launch_multidimensional_stage(
                    ROOT, run_dir=run, task_name=target["task_name"], initial_task=True,
                )

    def test_initial_targeted_host_rejects_tampering_and_unknown_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            with self.assertRaisesRegex(MultidimensionalStageError, "TARGET_TASK_UNKNOWN"):
                launch_multidimensional_stage(
                    ROOT, run_dir=run, task_name="not-a-declared-task", initial_task=True,
                )
            self.assertFalse((run / "invocation").exists())

            gate_path = run / "evidence/gate.json"
            gate = json.loads(gate_path.read_text())
            gate["decision_cutoff"] = "2025-01-01T00:00:00Z"
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            target = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            with self.assertRaisesRegex(MultidimensionalStageError, "INITIAL_INPUT_NOT_READY"):
                launch_multidimensional_stage(
                    ROOT, run_dir=run, task_name=target["task_name"], initial_task=True,
                )
            self.assertFalse((run / "invocation").exists())

    def test_initial_targeted_host_blocks_downstream_after_invalid_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            dependency = next(item for item in index["tasks"] if item["task_id"] == target["depends_on"][0])

            def simulated_codex(command, *, input, cwd, env, **kwargs):
                del command, input, cwd, kwargs
                parent = "parent-invalid-upstream"
                allowed, _ = handle_hook_event(
                    self.dispatch_payload(dependency, parent=parent), environ=env,
                )
                self.assertEqual(allowed["decision"], "ALLOW")
                handle_hook_event(
                    self.start_payload(dependency, parent=parent, child="child-invalid"),
                    environ=env,
                )
                invalid_draft = self.dimension_draft(dependency)
                invalid_draft["run_id"] = "wrong-run"
                stopped, _ = handle_hook_event(
                    self.stop_payload(
                        dependency, invalid_draft,
                        parent=parent, child="child-invalid",
                    ), environ=env,
                )
                self.assertNotEqual(stopped["output_capture"]["status"], "SAVED")
                blocked, _ = handle_hook_event(
                    self.dispatch_payload(target, parent=parent), environ=env,
                )
                self.assertEqual(
                    blocked.get("dispatch_binding", {}).get("failure_code"),
                    "RESEARCH_DEPENDENCY_NOT_READY", blocked,
                )
                (Path(env["TMPDIR"]) / "final-message.json").write_text(json.dumps({
                    "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
                    "run_id": index["run_id"], "dispatched": 2, "completed": 2,
                }), encoding="utf-8")
                return subprocess.CompletedProcess([], 0, "", "")

            with patch("product.runtime.multidimensional_stage.subprocess.run", side_effect=simulated_codex):
                result, code = launch_multidimensional_stage(
                    ROOT, run_dir=run, task_name=target["task_name"], initial_task=True,
                )
            self.assertEqual(code, 7)
            self.assertEqual(result["status"], "FAILED")
            process = json.loads((run / "invocation/process-result.json").read_text())
            self.assertEqual(process["stage_status"], "FAILED")
            self.assertEqual(process["task_outcomes"][1]["status"], "DEPENDENCY_BLOCKED")
            failed = process["task_outcomes"][0]
            self.assertEqual(failed["diagnostics"]["stage"], "REPORT_VALIDATION")
            self.assertEqual(failed["diagnostics"]["first_failure_code"], failed["failure_code"].split(":", 1)[0])
            self.assertFalse((run / "research/task-execution-proof.json").exists())
            self.assertFalse((run / "research/holding-research-bundle.json").exists())

    def test_live_preparation_failed_item_never_creates_research_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            gate["source_mode"] = "live-read-only"
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            preparation = {
                "common_cutoff": gate["decision_cutoff"],
                "items": [{
                    "security_id": handoff["portfolio"]["positions"][0]["security_id"],
                    "status": "FAILED",
                    "failure_code": "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE",
                }],
            }
            preparation["preparation_hash"] = canonical_hash(preparation)
            (root / "data-preparation.json").write_text(
                json.dumps(preparation), encoding="utf-8",
            )
            with self.assertRaisesRegex(MultidimensionalStageError, "DATA_PREPARATION_NOT_READY"):
                prepare_multidimensional_stage_run(
                    ROOT, handoff_path=handoff_path, gate_path=gate_path,
                    run_dir=root / "run", run_id="failed-preparation",
                    model="gpt-5.6-terra",
                )
            self.assertFalse((root / "run").exists())

    def test_public_research_lead_is_queryable_and_citable_as_source_limited(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            lead_id = "ev-moomoo-public-rating-lead"
            gate["allowed_evidence"].append({
                "evidence_id": lead_id,
                "security_id": "US:COMMON_STOCK:AAPL",
                "dataset": "research_discovery",
                "semantic_field": "moomoo_public_lead:3:post:123",
                "value": {"title": "公开评级新闻标题", "content_tier": "LEAD_ONLY", "body_verified": False},
                "source_id": "moomoo-public-news:post:123",
                "source_family": "moomoo_public_news",
                "source_type": "SECONDARY_VENDOR",
                "as_of": "2026-07-01T00:00:00Z",
                "retrieved_at": "2026-07-02T00:00:00Z",
                "usage": "LEAD_ONLY",
            })
            gate["allowed_evidence_ids"] = sorted(
                item["evidence_id"] for item in gate["allowed_evidence"]
            )
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="public-lead-test", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            self.assertIn(lead_id, task["allowed_evidence_ids"])
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, task["task_name"], include_dependency_reports=False,
            )
            self.assertIn(lead_id, packet["allowed_evidence_ids"])
            self.assertEqual(packet["company_material_coverage"]["public_lead_evidence_ids"], [lead_id])
            self.assertIn("至少用本任务只读 query 查询其中一条", packet["instruction"])
            self.assertIn("不得据标题推断评级依据", packet["instruction"])
            self.assertIn("事实主张只引用实际承载该金额的 Evidence", packet["instruction"])
            self.assertIn("没有本主张有效的换算收据时保留来源原币种和单位表示", packet["instruction"])
            initial = json.loads(serialize_multidimensional_initial_context(packet))
            self.assertIn("事实主张只引用实际承载该金额的 Evidence", initial["instruction"])
            fundamental = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            fundamental_packet = build_multidimensional_dispatch_packet(
                ROOT, run, fundamental["task_name"], include_dependency_reports=False,
            )
            self.assertNotIn("事实主张只引用实际承载该金额的 Evidence", fundamental_packet["instruction"])
            self.assertLessEqual(
                len(serialize_multidimensional_initial_context(packet).encode("utf-8")),
                256 * 1024,
            )
            tools = StatelessFixtureTools(default_run_dir=run)
            self.save_fundamental_dependency(run, index)
            result = tools.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"], evidence_ids=[lead_id],
            )
            actual_packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            self.assertEqual(translate_references(result, actual_packet["reference_map"])["evidence"][0]["evidence_id"], lead_id)
            draft = self.formal_dimension_draft(task)
            draft.update(status="SOURCE_LIMITED", evaluation_status="SOURCE_LIMITED")
            draft["claims"] = [{
                "claim_id": "claim-public-lead",
                "question": packet["minimum_questions"][0],
                "statement": "存在公开评级新闻标题，原文论据未核验。",
                "kind": "FACT", "evidence_refs": [lead_id],
                "research_claim_refs": [], "assumption_ids": [],
                "document_refs": [], "calculation_refs": [],
            }]
            invocation = json.loads((run / task["invocation_path"]).read_text())
            report = envelope_research_dimension_draft(
                draft, task=task, invocation=invocation,
                expected_bindings=self.research_bindings(run),
                allowed_security_ids=task["security_ids"],
                allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_documents=task.get("allowed_documents", []),
            )
            self.assertEqual(report["status"], "SOURCE_LIMITED")
            self.assertEqual(report["claims"][0]["evidence_refs"], [lead_id])
            invalid = copy.deepcopy(draft)
            invalid["claims"][0]["evidence_refs"] = ["ev-not-in-gate"]
            with self.assertRaisesRegex(MultiDimensionalResearchError, "EVIDENCE"):
                envelope_research_dimension_draft(
                    invalid, task=task, invocation=invocation,
                    expected_bindings=self.research_bindings(run),
                    allowed_security_ids=task["security_ids"],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    allowed_documents=task.get("allowed_documents", []),
                )

            # Exercise the real task builder with imported material states. The
            # importer is stubbed; no network/model runs or frozen files change.
            from tests.test_research_materials_stage import FakeOpenAlexClient
            from product.runtime.multidimensional_stage import _report_document_from_verified
            client = FakeOpenAlexClient(None, None)
            candidate = client.search(
                query="AAPL research", security_id="US:COMMON_STOCK:AAPL",
                decision_cutoff=gate["decision_cutoff"],
            )["candidates"][0]
            body = client.fetch(candidate)
            document = {"report_document": _report_document_from_verified(body), "content": body}
            for preparation_status in ("SOURCE_LIMITED", "READY", "BLOCKED_CONFIGURATION", "FAILED"):
                with self.subTest(preparation_status=preparation_status):
                    documents = [document] if preparation_status == "READY" else []
                    imported = {
                        "documents_by_security": {"US:COMMON_STOCK:AAPL": documents},
                        "documents_by_capability": {}, "peers_by_security": {},
                        "shared_preparation_by_capability": {
                            capability: {"status": "SOURCE_LIMITED", "gaps": [], "artifact_refs": []}
                            for capability in ("MACRO_CONTEXT", "MARKET_STATE")
                        },
                        "peer_preparation_by_security": {"US:COMMON_STOCK:AAPL": {
                            "status": "SOURCE_LIMITED", "gaps": [], "artifact_refs": [],
                        }},
                        "report_preparation_by_security": {"US:COMMON_STOCK:AAPL": {
                            "status": preparation_status, "gaps": [], "artifact_refs": [],
                        }},
                        "import_hash": "a" * 64,
                    }
                    case_run = root / preparation_status
                    with patch("product.runtime.multidimensional_stage._import_research_materials", return_value=imported):
                        prepare_multidimensional_stage_run(
                            ROOT, handoff_path=handoff_path, gate_path=gate_path,
                            run_dir=case_run, run_id="public-lead-test", model="gpt-5.6-terra",
                            research_materials_run_path=root / "synthetic-materials",
                        )
                    case_index = json.loads((case_run / "research/dispatch-index.json").read_text())
                    case_task = next(t for t in case_index["tasks"] if t["capability"] == "RESEARCH_REPORT")
                    case_packet = build_multidimensional_dispatch_packet(
                        ROOT, case_run, case_task["task_name"], include_dependency_reports=False,
                    )
                    self.assertEqual(case_packet["material_preparation"]["status"], preparation_status)
                    self.assertEqual(case_packet["verified_documents"], documents)
                    self.assertEqual(case_packet["company_material_coverage"]["public_lead_evidence_ids"], [lead_id])
                    self.assertEqual(case_packet["company_material_coverage"]["independent_body_count"], len(documents))
                    self.assertEqual(case_packet["tool_context"], packet["tool_context"])
                    self.assertEqual(case_packet["output_schema"]["properties"]["status"], packet["output_schema"]["properties"]["status"])
                    instruction = case_packet["instruction"]
                    self.assertNotIn("并保留独立研报正文缺口与 SOURCE_LIMITED", instruction)
                    if preparation_status in {"BLOCKED_CONFIGURATION", "FAILED"}:
                        self.assertNotIn("至少用本任务只读 query 查询其中一条", instruction)
                        self.assertIn("FAILED / evaluation_status=FAIL", instruction)
                        if preparation_status == "BLOCKED_CONFIGURATION":
                            incomplete = self.formal_dimension_draft(case_task)
                            incomplete.update(status="LOW_CONFIDENCE", sufficiency="PARTIAL")
                            case_invocation = json.loads((case_run / case_task["invocation_path"]).read_text())
                            with self.assertRaisesRegex(
                                MultiDimensionalResearchError,
                                "DIMENSION_DRAFT_CONFIGURATION_BLOCK_STATE_INVALID",
                            ):
                                envelope_research_dimension_draft(
                                    incomplete, task=case_task, invocation=case_invocation,
                                    expected_bindings=self.research_bindings(case_run),
                                    allowed_security_ids=case_task["security_ids"],
                                    allowed_evidence_ids=case_task["allowed_evidence_ids"],
                                    allowed_documents=case_task.get("allowed_documents", []),
                                )
                    else:
                        self.assertIn("至少用本任务只读 query 查询其中一条", instruction)
                        self.assertIn("不因存在标题自动降级", instruction)
                        self.assertIn("不为引用数量拼凑主张", instruction)
                        self.assertIn("说明具体核验用途", instruction)
                    self.assertLessEqual(len(serialize_multidimensional_initial_context(case_packet).encode()), 256 * 1024)

            section = {
                "evidence_id": "ev-licensed-bear", "security_id": "US:COMMON_STOCK:AAPL",
                "dataset": "research_discovery", "semantic_field": "moomoo_morningstar_section:bear_case:0",
                "value": {"content_tier": "LICENSED_API_CONTENT", "section": "bear_case",
                          "content": "供应商观点：增长假设可能无法实现。"},
                "source_id": "moomoo-sg-opend-morningstar:AAPL", "source_type": "SECONDARY_VENDOR",
                "raw_content_hash": "b" * 64, "as_of": "2026-07-01T00:00:00Z",
                "retrieved_at": "2026-07-02T00:00:00Z", "usage": "RESEARCH_ONLY",
            }
            gate["allowed_evidence"].append(section)
            gate["allowed_evidence_ids"].append(section["evidence_id"])
            gate["input_evidence_ids"].append(section["evidence_id"])
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            for state in ("BLOCKED_CONFIGURATION", "READY"):
                imported["report_preparation_by_security"]["US:COMMON_STOCK:AAPL"]["status"] = state
                imported["documents_by_security"]["US:COMMON_STOCK:AAPL"] = [document] if state == "READY" else []
                case_run = root / f"licensed-{state}"
                with patch("product.runtime.multidimensional_stage._import_research_materials", return_value=imported):
                    prepare_multidimensional_stage_run(
                        ROOT, handoff_path=handoff_path, gate_path=gate_path,
                        run_dir=case_run, run_id="licensed-test", model="gpt-5.6-terra",
                        research_materials_run_path=root / "synthetic-materials",
                    )
                case_index = json.loads((case_run / "research/dispatch-index.json").read_text())
                task = next(t for t in case_index["tasks"] if t["capability"] == "RESEARCH_REPORT")
                packet = build_multidimensional_dispatch_packet(
                    ROOT, case_run, task["task_name"], include_dependency_reports=False,
                )
                frozen_task = json.loads((
                    case_run / "research/tasks" / f"{canonical_hash({'task_id': task['task_id']})}.json"
                ).read_text())
                self.assertEqual(
                    frozen_task["company_material_coverage"],
                    packet["company_material_coverage"],
                )
                self.assertEqual(packet["material_preparation"]["status"], state)
                self.assertEqual(packet["company_material_coverage"]["licensed_sections"], [{
                    "evidence_id": section["evidence_id"], "section": "bear_case",
                    "raw_content_hash": "b" * 64, "content_tier": "LICENSED_API_CONTENT",
                }])
                self.assertNotIn("正式报告必须输出 FAILED", packet["instruction"])
                self.assertIn("仍须查询与研究问题相关的正反章节", packet["instruction"])
                self.assertIn("不能改称作者预测", packet["instruction"])
                self.assertIn("新增供应商估值观点也不自动修订该核验缺口", packet["instruction"])
                first_context = json.loads(serialize_multidimensional_initial_context(packet))
                self.assertIn("不能改称作者预测", first_context["instruction"])
                self.assertIn("新增供应商估值观点也不自动修订该核验缺口",
                              first_context["instruction"])
                self.assertEqual(len(packet["verified_documents"]), 1 if state == "READY" else 0)
                self.save_fundamental_dependency(case_run, json.loads((case_run / "research/dispatch-index.json").read_text()))
                full_packet = build_multidimensional_dispatch_packet(ROOT, case_run, task["task_name"])
                full_context = json.loads(serialize_multidimensional_model_context(full_packet))
                self.assertIn("不能改称作者预测", full_context["instruction"])
                self.assertIn("新增供应商估值观点也不自动修订该核验缺口",
                              full_context["instruction"])
                result = StatelessFixtureTools(default_run_dir=case_run).query(
                    run_id=task["run_id"], agent=task["agent"], invocation_id=task["invocation_id"],
                    evidence_ids=[section["evidence_id"]],
                )
                self.assertEqual(result["evidence"][0]["value"], section["value"])
                if state == "BLOCKED_CONFIGURATION":
                    draft = self.formal_dimension_draft(task)
                    draft.update(status="LOW_CONFIDENCE", sufficiency="PARTIAL")
                    draft["claims"] = [{
                        "claim_id": "licensed-bear-case", "question": packet["minimum_questions"][0],
                        "statement": "许可章节指出增长假设可能无法实现；独立正文仍缺失。",
                        "kind": "INTERPRETATION", "evidence_refs": [section["evidence_id"]],
                        "research_claim_refs": [], "assumption_ids": [],
                        "document_refs": [], "calculation_refs": [],
                    }]
                    invocation = json.loads((case_run / task["invocation_path"]).read_text())
                    report = envelope_research_dimension_draft(
                        draft, task=frozen_task, invocation=invocation,
                        expected_bindings=self.research_bindings(case_run),
                        allowed_security_ids=task["security_ids"],
                        allowed_evidence_ids=task["allowed_evidence_ids"],
                        allowed_documents=task.get("allowed_documents", []),
                    )
                    self.assertEqual(report["status"], "LOW_CONFIDENCE")
                    self.assertEqual(report["claims"][0]["evidence_refs"], [section["evidence_id"]])

    def test_initial_hook_context_is_bounded_and_keeps_exact_query_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, task["task_name"], include_dependency_reports=False,
            )
            text = serialize_multidimensional_initial_context(packet)
            context = json.loads(text)
            context = translate_references(context, packet["reference_map"])
            self.assertLessEqual(len(text.encode("utf-8")), 256 * 1024)
            self.assertEqual(context["packet_hash"], canonical_hash(packet))
            self.assertEqual(
                {item["evidence_id"] for group in context["evidence_catalog"]
                 for item in group["items"]},
                set(task["allowed_evidence_ids"]),
            )
            self.assertEqual(context["tool_context"], packet["tool_context"])
            self.assertEqual(context["output_schema_hash"], packet["output_schema_hash"])
            self.assertNotIn("allowed_evidence_ids", context)
            self.assertNotIn("capability_routing", context["provider_coverage"])
            oversize = copy.deepcopy(packet)
            oversize["evidence_catalog"] *= 2000
            with self.assertRaisesRegex(MultidimensionalStageError, "INITIAL_CONTEXT_TOO_LARGE"):
                serialize_multidimensional_initial_context(oversize)

    def test_repair_budget_exhausts_and_identity_failure_is_not_repairable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-exhausted", "child-exhausted"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )
            invalid = self.dimension_draft(task, include_impact=False)
            first, first_response = handle_hook_event(
                self.stop_payload(task, invalid, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(first_response["decision"], "block")
            second, second_response = handle_hook_event(
                self.stop_payload(task, invalid, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(second["hook_event_name"], "SubagentStop")
            self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual(second["output_capture"]["attempt"], 2)
            self.assertEqual(second_response, {})

        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent = "parent-binding"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(
                self.start_payload(
                    task, parent=parent, child="child-binding"
                ),
                environ=environment,
            )
            wrong_identity = self.dimension_draft(task)
            wrong_identity["agent"] = "runtime_market_catalyst"
            stopped, response = handle_hook_event(
                self.stop_payload(
                    task, wrong_identity, parent=parent, child="child-binding"
                ),
                environ=environment,
            )
            self.assertEqual(stopped["hook_event_name"], "SubagentStop")
            self.assertEqual(stopped["output_capture"]["repair_state"], "NOT_ALLOWED")
            self.assertIn(
                "RESEARCH_OUTPUT_IDENTITY_CONFLICT",
                stopped["output_capture"]["failure_code"],
            )
            self.assertEqual(response, {})

    def test_targeted_finalizer_proves_only_requested_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            invocation = json.loads((run / task["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": task["run_id"],
                    "invocation_id": task["invocation_id"],
                    "agent": task["agent"],
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "定点执行证明测试。",
                    "claims": [], "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": ["测试资料不足。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": "gap-targeted",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "不形成宏观主张。",
                    }],
                    "artifact_refs": [],
                },
                task=task,
                invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
            )
            output = persist_dimension_report(
                run / "research/reports/targeted", report=report, evidence=[]
            )
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"task_name": task["task_name"], "decision": "ALLOW"}) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED",
                        "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                }) + "\n",
                encoding="utf-8",
            )
            proof = finalize_multidimensional_task_evidence(
                ROOT, run, task["task_name"]
            )
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["scope"], "SINGLE_TASK_EVIDENCE")
            self.assertFalse(proof["complete_holding_research_bundle"])
            self.assertTrue((run / "research/task-execution-proof.json").is_file())

    def test_successful_targeted_retry_archives_bundle_and_records_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            self.complete_with_explicit_gaps(run)
            old_bundle_hash = file_hash(run / "research/holding-research-bundle.json")
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            )
            invocation = json.loads((run / task["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                self.formal_dimension_draft(task), task=task, invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_documents=task.get("allowed_documents", []),
            )
            retry_output = persist_dimension_report(
                run / "research/reports/retry-industry", report=report, evidence=[],
            )
            retry_dir = run / "invocation/retries/retry-industry/attempt-1"
            retry_dir.mkdir(parents=True)
            (retry_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"task_name": task["task_name"], "decision": "ALLOW"}) + "\n",
                encoding="utf-8",
            )
            (retry_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(retry_output["json"]).relative_to(run)),
                    },
                }) + "\n",
                encoding="utf-8",
            )
            finalize_multidimensional_task_evidence(
                ROOT, run, task["task_name"], invocation_dir=retry_dir,
            )
            result = _adopt_multidimensional_retry(
                ROOT, run, invocation_dir=retry_dir,
            )
            self.assertEqual("PASSED", result["status"])
            self.assertEqual(
                old_bundle_hash,
                file_hash(run / "research/revisions/1/holding-research-bundle.json"),
            )
            adoption = json.loads(
                (run / "research/retry-adoptions.jsonl").read_text().strip()
            )
            self.assertEqual(task["task_name"], adoption["task_name"])
            self.assertEqual(
                str(retry_dir.relative_to(run)), adoption["invocation_ref"]
            )

    def test_macro_packet_includes_scoped_company_context_without_report_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for security_id in ("US:COMMON_STOCK:AAPL", "US:COMMON_STOCK:MSFT"):
                evidence_id = f"ev-business-{security_id.rsplit(':', 1)[-1].lower()}"
                gate["allowed_evidence"].append({
                    "evidence_id": evidence_id,
                    "security_id": security_id,
                    "semantic_field": "business",
                    "value": "可核对的公司业务暴露。",
                    "unit": "text",
                    "source_id": "sec-companyfacts",
                    "source_type": "sec",
                    "as_of": "2026-09-10T00:00:00Z",
                    "published_at": "2026-09-10T00:00:00Z",
                    "retrieved_at": "2026-09-11T00:00:00Z",
                })
                gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="macro-company-context", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            macro = next(
                item for item in index["tasks"]
                if item["capability"] == "MACRO_CONTEXT"
            )
            self.assertEqual(macro["depends_on"], [])
            self.assertTrue(
                {"ev-business-aapl", "ev-business-msft"}
                <= set(macro["allowed_evidence_ids"])
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, macro["task_name"]
            )
            self.assertIn("必须读取至少两只持仓", packet["instruction"])

    def test_macro_packet_includes_deterministic_benchmark_market_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for index in range(21):
                day = f"2026-08-{index + 1:02d}"
                for field, value in (
                    ("historical_close_price", 500 + index),
                    ("adjusted_close_price", 500 + index),
                    ("share_volume", 1_000_000 + index * 1_000),
                ):
                    evidence_id = f"ev-spy-{field}-{index}"
                    gate["allowed_evidence"].append({
                        "evidence_id": evidence_id,
                        "security_id": "US:SPY",
                        "semantic_field": field,
                        "value": value,
                        "unit": "USD" if field != "share_volume" else "shares",
                        "source_id": "yahoo-daily",
                        "source_type": "yahoo",
                        "as_of": f"{day}T20:00:00Z",
                        "published_at": f"{day}T20:00:00Z",
                        "retrieved_at": "2026-09-11T00:00:00Z",
                        "metadata": {"trading_date": day},
                    })
                    gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="macro-market-state", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            market = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, market["task_name"])
            prepared = packet["prepared_analysis"]
            self.assertEqual(
                prepared["calculation"]["schema_version"],
                "market-state-calculation/1.0.0",
            )
            self.assertEqual(
                prepared["calculation"]["windows"][0]["status"], "COMPLETE"
            )
            self.assertEqual(
                packet["allowed_artifact_refs"], [prepared["calculation_ref"]]
            )
            self.assertIn("共享市场状态报告", packet["instruction"])
            self.assertIn("不得把股票波动称为信用", packet["instruction"])
            self.assertIn("至少读取并解释各一项实际观测", packet["instruction"])
            self.assertIn("单日观察不等于趋势或资金流", packet["instruction"])

    def test_peer_candidate_pool_is_bound_but_not_promoted_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            holdings = [
                {"security_id": item["security_id"], "ticker": item["display_symbol"]}
                for item in handoff["portfolio"]["positions"]
                if item["asset_type"] == "COMMON_STOCK"
            ]
            observed = "2026-09-11T11:00:00Z"
            rows = []
            for symbol, name, cap in (
                (holdings[0]["ticker"], "Holding One", "100"),
                (holdings[1]["ticker"], "Holding Two", "200"),
                ("PEER1", "Peer One", "120"),
            ):
                rows.append({
                    "symbol": symbol, "name": name, "market_cap": cap,
                    "country": "United States", "ipo_year": 2000,
                    "sector": "Technology", "industry": "Synthetic Industry",
                    "source_id": "nasdaq-screener", "as_of": observed,
                    "retrieved_at": observed, "raw_content_hash": "a" * 64,
                })
            universe = {
                "schema_version": "live-universe/1.0.0", "provider": "nasdaq",
                "source_id": "nasdaq-screener",
                "source_locator": "https://api.nasdaq.com/api/screener/stocks",
                "request_started_at": "2026-09-11T10:59:00Z",
                "as_of": observed, "retrieved_at": observed,
                "completeness": "COMPLETE", "rows": rows,
                "snapshot_hash": content_hash({"rows": rows, "as_of": observed}),
            }
            pool = build_peer_candidate_pool(holdings, universe=universe)
            handoff_path, gate_path, pool_path = root / "handoff.json", root / "gate.json", root / "peers.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            pool_path.write_text(json.dumps(pool), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="peer-pool-stage-run", model="gpt-5.6-terra",
                peer_candidate_pool_path=pool_path,
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            industry = next(item for item in index["tasks"] if item["capability"] == "INDUSTRY_COMPARISON")
            packet = build_multidimensional_dispatch_packet(ROOT, run, industry["task_name"], include_dependency_reports=False)
            self.assertEqual(packet["peer_candidate_group"]["security_id"], industry["security_ids"][0])
            self.assertTrue(packet["peer_candidate_group"]["candidates"])
            self.assertFalse(
                set(item["candidate_id"] for item in packet["peer_candidate_group"]["candidates"])
                & set(packet["allowed_evidence_ids"])
            )
            self.assertIn("未核实候选池", packet["instruction"])
            self.assertIn("claims 必须为空", packet["instruction"])
            self.assertEqual(packet["output_schema"]["properties"]["claims"]["maxItems"], 0)

    def test_prepare_revalidates_and_freezes_existing_company_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff, "company-source-run")
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            source = root / "company-run"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=source, run_id="company-source-run", model="gpt-5.6-terra",
            )
            source_gate = json.loads((source / "evidence/gate.json").read_text())
            index = json.loads((source / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                request = json.loads((source / task["request_path"]).read_text())
                report = valid_report(request)
                report["report_id"] = f"equity:{task['security_id']}"
                evidence_by_id = {
                    item["evidence_id"]: item for item in source_gate["allowed_evidence"]
                }
                persist_equity_research_report(
                    source / "research/reports", report=report, request=request,
                    evidence=[evidence_by_id[item] for item in request["allowed_evidence_ids"]],
                )
            proof = {
                "schema_version": "common-stock-research-execution-proof/1.0.0",
                "run_id": "company-source-run",
                "expected_tasks": sorted(item["task_name"] for item in index["tasks"]),
                "completed_security_ids": sorted(item["security_id"] for item in index["tasks"]),
                "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
                "agent": {}, "skills": [], "gate_hash": source_gate["bundle_hash"],
                "complete_portfolio_decision": False,
            }
            proof["proof_hash"] = canonical_hash(proof)
            (source / "research/execution-proof.json").write_text(
                json.dumps(proof), encoding="utf-8"
            )
            target = root / "multidimensional-run"
            gate_path.write_text(
                json.dumps(gate_for(handoff, "multidimensional-import-run")),
                encoding="utf-8",
            )
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=target, run_id="multidimensional-import-run",
                model="gpt-5.6-terra", company_research_run_path=source,
            )
            imported = json.loads(
                (target / "research/imported-company-research/import-manifest.json").read_text()
            )
            self.assertEqual(len(imported["reports"]), 2)
            self.assertEqual(
                {item["security_id"] for item in imported["reports"]},
                {item["security_id"] for item in index["tasks"]},
            )
            self.assertTrue(all((target / item["artifact_ref"]).is_file() for item in imported["reports"]))
            manifest = json.loads((target / "run_manifest.json").read_text())
            self.assertEqual(manifest["company_research_import_hash"], imported["import_hash"])

    def test_canonical_assembly_imports_company_reports_and_excludes_drifted_supplement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff, "company-source-run")
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")

            company = root / "company-run"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=company, run_id="company-source-run", model="gpt-5.6-terra",
            )
            company_gate = json.loads((company / "evidence/gate.json").read_text())
            company_index = json.loads((company / "research/dispatch-index.json").read_text())
            for task in company_index["tasks"]:
                request = json.loads((company / task["request_path"]).read_text())
                report = valid_report(request)
                report["report_id"] = f"equity:{task['security_id']}"
                evidence_by_id = {
                    item["evidence_id"]: item for item in company_gate["allowed_evidence"]
                }
                persist_equity_research_report(
                    company / "research/reports", report=report, request=request,
                    evidence=[evidence_by_id[item] for item in request["allowed_evidence_ids"]],
                )
            company_proof = {
                "schema_version": "common-stock-research-execution-proof/1.0.0",
                "run_id": "company-source-run",
                "expected_tasks": sorted(item["task_name"] for item in company_index["tasks"]),
                "completed_security_ids": sorted(item["security_id"] for item in company_index["tasks"]),
                "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
                "agent": {}, "skills": [], "gate_hash": company_gate["bundle_hash"],
                "complete_portfolio_decision": False,
            }
            company_proof["proof_hash"] = canonical_hash(company_proof)
            (company / "research/execution-proof.json").write_text(json.dumps(company_proof))

            base = root / "base-run"
            gate_path.write_text(
                json.dumps(gate_for(handoff, "canonical-base-run")),
                encoding="utf-8",
            )
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=base, run_id="canonical-base-run", model="gpt-5.6-terra",
            )
            self.complete_with_explicit_gaps(base)
            supplement = root / "supplement-run"
            (supplement / "research").mkdir(parents=True)
            shutil.copy2(base / "evidence/gate.json", supplement / "gate.json")
            supplement_report = next((base / "research/reports").glob("*/dimension-report.json"))
            shutil.copy2(supplement_report, supplement / "research/dimension-report.json")
            report = json.loads(supplement_report.read_text())
            (supplement / "run_manifest.json").write_text(json.dumps({
                "run_id": "different-run",
            }))
            shutil.move(str(supplement / "gate.json"), str(supplement / "evidence-gate.json"))
            (supplement / "evidence").mkdir()
            shutil.move(str(supplement / "evidence-gate.json"), str(supplement / "evidence/gate.json"))
            (supplement / "research/task-execution-proof.json").write_text(json.dumps({
                "report_ref": "research/dimension-report.json",
            }))

            target = root / "canonical"
            result = assemble_canonical_holding_research_package(
                ROOT,
                base_run_dir=base,
                company_research_run_dir=company,
                output_dir=target,
                supplement_run_dirs=[supplement],
            )
            self.assertEqual(result["consumability"], "STRUCTURALLY_CONSUMABLE")
            bundle = json.loads((target / "research/holding-research-bundle.json").read_text())
            self.assertTrue(all(
                item["report_id"]
                for item in bundle["coverage"]
                if item["capability"] == "COMPANY_RESEARCH"
            ))
            self.assertEqual(
                bundle["package_provenance"]["excluded_supplements"][0]["reason_codes"],
                ["RUN_ID_MISMATCH"],
            )
            package_proof = json.loads(
                (target / "research/canonical-package-proof.json").read_text()
            )
            self.assertEqual(len(package_proof["source_inputs"]["supplements"]), 1)
            self.assertEqual(
                set(package_proof["implementation_snapshot"]),
                {
                    "product/council/multidimensional_research.py",
                    "product/council/multidimensional_output.py",
                    "product/runtime/multidimensional_stage.py",
                    "product/runtime/cli.py",
                    "product/schemas/runtime/holding-research-bundle-v1.1.schema.json",
                    "product/skills/portfolio-council/SKILL.md",
                    "product/version-manifest.json",
                },
            )
            proof = check_multidimensional_bundle_consumable(ROOT, target)
            self.assertEqual(proof["downstream_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(proof["status_projection"]["research_review_status"], "NOT_REVIEWED")
            self.assertEqual(proof["downstream_models_started"], [])
            gate_path = target / "evidence/gate.json"
            original_gate = json.loads(gate_path.read_text())
            drifted_gate = {**original_gate, "decision_cutoff": "2026-09-12T12:00:00Z"}
            gate_path.write_text(json.dumps(drifted_gate))
            with self.assertRaisesRegex(MultidimensionalStageError, "MULTIDIMENSIONAL_CONSUMER_GATE_INVALID"):
                check_multidimensional_bundle_consumable(ROOT, target, persist=False)
            drifted_gate["bundle_hash"] = canonical_hash({
                key: value for key, value in drifted_gate.items() if key != "bundle_hash"
            })
            gate_path.write_text(json.dumps(drifted_gate))
            with self.assertRaisesRegex(MultidimensionalStageError, "MULTIDIMENSIONAL_CONSUMER_GATE_INVALID"):
                check_multidimensional_bundle_consumable(ROOT, target, persist=False)

    def test_multidimensional_invocation_can_query_its_frozen_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            tools = StatelessFixtureTools(default_run_dir=run)
            result = tools.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"],
                evidence_ids=[task["allowed_evidence_ids"][0]],
            )
            mapping = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])["reference_map"]
            self.assertEqual(translate_references(result, mapping)["evidence"][0]["evidence_id"], task["allowed_evidence_ids"][0])
            self.assertEqual(tools.events[-1]["invocation_id"], task["invocation_id"])

    def test_hook_loads_correct_agent_packet_and_rejects_unready_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            invocation = run / "invocation"
            invocation.mkdir()
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            }
            index = json.loads((run / "research/dispatch-index.json").read_text())
            first = index["tasks"][0]
            pre = {
                "hook_event_name": "PreToolUse", "session_id": "parent", "turn_id": "turn",
                "tool_name": "spawn_agent", "tool_use_id": "tool-1", "cwd": str(ROOT / "product"),
                "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": first["agent"], "task_name": first["task_name"],
                    "fork_turns": "none", "message": "启动冻结多维研究任务。",
                },
            }
            record, response = handle_hook_event(pre, environ=environment)
            self.assertEqual(record["decision"], "ALLOW")
            self.assertEqual(response, {})
            start = {
                "hook_event_name": "SubagentStart", "session_id": "parent", "turn_id": "turn",
                "agent_id": "child", "agent_type": first["agent"], "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"), "permission_mode": "read-only",
            }
            start_record, start_response = handle_hook_event(start, environ=environment)
            context = json.loads(start_response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(context["identity"]["task_id"], first["task_id"])
            self.assertEqual(start_record["context_binding"]["packet_hash"], canonical_hash(
                build_multidimensional_dispatch_packet(ROOT, run, first["task_name"])
            ))

            dependent = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            denied = dict(pre, tool_use_id="tool-2", tool_input={
                "agent_type": dependent["agent"], "task_name": dependent["task_name"],
                "fork_turns": "none", "message": "依赖尚未完成。",
            })
            denied_record, denied_response = handle_hook_event(denied, environ=environment)
            self.assertEqual(denied_record["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                denied_record["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )
            self.assertEqual(
                denied_response["hookSpecificOutput"]["permissionDecision"], "deny"
            )

    def test_failed_report_releases_slot_but_does_not_satisfy_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            index["target_concurrency"] = 1
            index["index_hash"] = canonical_hash({
                key: value for key, value in index.items() if key != "index_hash"
            })
            index_path.write_text(json.dumps(index), encoding="utf-8")
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation_dir / "subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation_dir / "subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            }
            fundamental = next(
                item for item in index["tasks"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
            )
            dependent = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
                and item["security_ids"] == fundamental["security_ids"]
            )
            independent = next(
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
                and item["security_ids"] == fundamental["security_ids"]
            )

            def pre(task, tool_id):
                return {
                    "hook_event_name": "PreToolUse", "session_id": "parent",
                    "turn_id": "turn", "tool_name": "spawn_agent",
                    "tool_use_id": tool_id, "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                    "tool_input": {
                        "agent_type": task["agent"], "task_name": task["task_name"],
                        "fork_turns": "none", "message": "启动冻结多维研究任务。",
                    },
                }

            allowed, _ = handle_hook_event(
                pre(fundamental, "fundamental"), environ=environment
            )
            self.assertEqual(allowed["decision"], "ALLOW")
            (invocation_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "parent_session_id": "parent",
                    "output_binding": {"invocation_id": fundamental["invocation_id"]},
                    "output_capture": {
                        "status": "FAILED", "failure_code": "EVIDENCE_CLOSURE_FAILED"
                    },
                }) + "\n",
                encoding="utf-8",
            )
            blocked, _ = handle_hook_event(
                pre(dependent, "dependent"), environ=environment
            )
            self.assertEqual(blocked["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                blocked["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )
            released, _ = handle_hook_event(
                pre(independent, "independent"), environ=environment
            )
            self.assertEqual(released["decision"], "ALLOW")

    def test_prepare_binds_same_source_technical_calculation_and_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for security_id, scale in (
                ("US:COMMON_STOCK:AAPL", 2), ("US:SPY", 1)
            ):
                for day_index, day in enumerate(("2026-09-08", "2026-09-09", "2026-09-10")):
                    for field, value, unit in (
                        ("historical_close_price", 100 + day_index * scale, "USD"),
                        ("adjusted_close_price", 100 + day_index * scale, "USD"),
                        ("share_volume", 1000 + day_index * 10, "shares"),
                    ):
                        evidence_id = f"ev-{security_id.split(':')[-1].lower()}-{day}-{field}"
                        gate["allowed_evidence"].append({
                            "evidence_id": evidence_id,
                            "security_id": security_id,
                            "semantic_field": field,
                            "value": str(value),
                            "unit": unit,
                            "source_id": "yahoo-daily",
                            "source_type": "yahoo",
                            "as_of": day + "T20:00:00Z",
                            "published_at": day + "T20:00:00Z",
                            "retrieved_at": "2026-09-11T11:00:00Z",
                            "metadata": {"trading_date": day},
                        })
                        gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="technical-stage-run", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            technical = next(
                item for item in index["tasks"]
                if item["capability"] == "TECHNICAL_STRUCTURE"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, technical["task_name"]
            )
            prepared = packet["prepared_analysis"]
            self.assertIsNotNone(prepared["calculation"])
            self.assertNotIn("evidence_fact_ids", prepared["calculation"])
            calculation_artifact = json.loads(
                (run / prepared["calculation_ref"]).read_text()
            )
            self.assertEqual(
                prepared["calculation"]["evidence_fact_count"],
                len(calculation_artifact["evidence_fact_ids"]),
            )
            self.assertEqual(
                len(prepared["calculation"]["evidence_fact_ids_hash"]), 64
            )
            self.assertEqual(technical["allowed_evidence_ids"], [])
            self.assertIsNotNone(prepared["chart"])
            self.assertEqual(len(prepared["allowed_artifact_refs"]), 2)
            for relative in prepared["allowed_artifact_refs"]:
                self.assertTrue((run / relative).is_file())
            self.assertEqual(
                packet["output_schema"]["properties"]["artifact_refs"]["items"]["enum"],
                prepared["allowed_artifact_refs"],
            )

    def test_live_spy_etf_daily_prices_resolve_default_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff, gate = self.mrvl_daily_inputs(include_spy=True)
            for fact in gate["allowed_evidence"]:
                if fact.get("security_id") == "US:SPY":
                    fact["security_id"] = "US:ETF:SPY"
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="technical-spy-etf-test", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            technical = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, technical["task_name"])
            self.assertGreater(packet["prepared_analysis"]["benchmark_row_count"], 20)
            self.assertIsNotNone(packet["prepared_analysis"]["calculation"])
            self.assertEqual(technical["time_context"]["benchmark_id"], "US:ETF:SPY")

    def test_mrvl_daily_without_spy_saves_insufficient_technical_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.prepare_mrvl_daily_run(root, include_spy=False)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            prepared = packet["prepared_analysis"]
            self.assertGreater(prepared["security_row_count"], 20)
            self.assertEqual(prepared["benchmark_row_count"], 0)
            self.assertIsNone(prepared["calculation"])
            self.assertIsNone(prepared["chart"])
            self.assertEqual(packet["output_schema"]["properties"]["claims"]["maxItems"], 0)
            self.assertEqual(packet["output_schema"]["properties"]["status"]["const"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(packet["output_schema"]["properties"]["sufficiency"]["const"], "INSUFFICIENT")
            self.assertEqual(packet["output_schema"]["properties"]["data_gaps"]["minItems"], 1)
            self.assertIn("基准 US:SPY", packet["instruction"])
            self.assertNotIn("证券 US:COMMON_STOCK:MRVL日线序列", packet["instruction"])

            draft = self.formal_dimension_draft(task)
            draft["data_gaps"][0].update(
                description="MRVL 有冻结日线，但 US:SPY 基准日线缺失。",
                impact="不能计算相对收益、波动、回撤及同源量价图。",
            )
            invalid = {**draft, "status": "COMPLETE", "sufficiency": "SUFFICIENT"}
            invocation = json.loads((run / task["invocation_path"]).read_text())
            with self.assertRaisesRegex(MultiDimensionalResearchError, "TECHNICAL_NO_CALCULATION_STATE_INVALID"):
                envelope_research_dimension_draft(
                    invalid, task=task, invocation=invocation,
                    expected_bindings={}, allowed_security_ids=task["security_ids"],
                    allowed_evidence_ids=[],
                )
            invalid_claim = copy.deepcopy(draft)
            invalid_claim["claims"] = [{
                "claim_id": "claim-unavailable", "question": packet["minimum_questions"][0],
                "statement": "无法判断技术结构。", "kind": "INTERPRETATION",
                "evidence_refs": [], "research_claim_refs": [], "document_refs": [],
                "assumption_ids": [], "calculation_refs": [],
            }]
            with self.assertRaisesRegex(MultiDimensionalResearchError, "TECHNICAL_NO_CALCULATION_CONTENT_INVALID"):
                envelope_research_dimension_draft(
                    invalid_claim, task=task, invocation=invocation,
                    expected_bindings={}, allowed_security_ids=task["security_ids"],
                    allowed_evidence_ids=[],
                )

            environment = self.targeted_environment(run, task)
            parent, child = "parent-technical-missing", "child-technical-missing"
            allowed, _ = handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(self.start_payload(task, parent=parent, child=child), environ=environment)
            native = self.dimension_draft(task)
            native["data_gaps"] = copy.deepcopy(draft["data_gaps"])
            stopped, _ = handle_hook_event(
                self.stop_payload(task, native, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")
            report = json.loads((run / stopped["output_capture"]["path"]).read_text())
            self.assertEqual(report["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(report["sufficiency"], "INSUFFICIENT")
            self.assertEqual(report["claims"], [])
            self.assertIn("US:SPY", report["data_gaps"][0]["description"])

            bundle_run_root = root / "bundle-case"
            bundle_run_root.mkdir()
            bundle_run = self.prepare_mrvl_daily_run(bundle_run_root, include_spy=False)
            self.complete_with_explicit_gaps(bundle_run)
            bundle = json.loads((bundle_run / "research/holding-research-bundle.json").read_text())
            technical_coverage = next(
                item for item in bundle["coverage"]
                if item["capability"] == "TECHNICAL_STRUCTURE"
            )
            self.assertEqual(technical_coverage["status"], "INSUFFICIENT_EVIDENCE")
            self.assertNotEqual(technical_coverage["status"], "COMPLETE")

    def test_mrvl_with_spy_keeps_grounded_calculation_and_chart_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare_mrvl_daily_run(Path(temp), include_spy=True)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            prepared = packet["prepared_analysis"]
            self.assertGreater(prepared["security_row_count"], 20)
            self.assertEqual(prepared["security_row_count"], prepared["benchmark_row_count"])
            self.assertIsNotNone(prepared["calculation"])
            self.assertIsNotNone(prepared["chart"])
            refs = prepared["allowed_artifact_refs"]
            self.assertEqual(refs, [prepared["calculation_ref"], prepared["chart"]["artifact_ref"]])
            self.assertTrue(all((run / ref).is_file() for ref in refs))
            self.assertNotIn("maxItems", packet["output_schema"]["properties"]["claims"])
            metric = prepared["calculation"]["windows"][0]["metrics"]["security_total_return"]
            draft = self.formal_dimension_draft(task)
            draft.update(
                status="LOW_CONFIDENCE", sufficiency="PARTIAL",
                summary="20 日窗口已有冻结计算和同源图表，较长窗口仍缺历史。",
                calculations=[{
                    "calculation_id": "calc-technical-return", "method": "security_total_return",
                    "value": metric, "unit": "ratio", "input_evidence_refs": [],
                    "artifact_ref": refs[0],
                }],
                claims=[{
                    "claim_id": "claim-technical-return",
                    "question": packet["minimum_questions"][0],
                    "statement": "20 日窗口收益由同源冻结计算给出。",
                    "kind": "INTERPRETATION", "evidence_refs": [],
                    "research_claim_refs": [], "document_refs": [],
                    "assumption_ids": [], "calculation_refs": ["calc-technical-return"],
                }],
                artifact_refs=refs,
            )
            invocation = json.loads((run / task["invocation_path"]).read_text())
            report = envelope_research_dimension_draft(
                draft, task=task, invocation=invocation,
                expected_bindings=self.research_bindings(run),
                allowed_security_ids=task["security_ids"],
                allowed_evidence_ids=[], allowed_documents=[],
            )
            output = persist_dimension_report(
                run / "research/reports" / task["task_id"], report=report, evidence=[],
            )
            saved = json.loads(Path(output["json"]).read_text())
            self.assertEqual(saved["claims"][0]["calculation_refs"], ["calc-technical-return"])
            self.assertEqual(saved["artifact_refs"], refs)
            self.assertEqual(saved["calculations"][0]["artifact_ref"], refs[0])

    def test_chart_failure_keeps_calculation_and_grounded_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch(
                "product.council.technical_chart.render_relative_performance_svg",
                side_effect=ValueError("TECHNICAL_CHART_VALUE_INVALID"),
            ):
                run = self.prepare_mrvl_daily_run(root, include_spy=True)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            prepared = packet["prepared_analysis"]
            calculation_ref = prepared["calculation_ref"]
            self.assertIsNotNone(prepared["calculation"])
            self.assertIsNone(prepared["chart"])
            self.assertEqual(prepared["allowed_artifact_refs"], [calculation_ref])
            self.assertEqual([gap["reason_code"] for gap in prepared["gaps"]], ["TECHNICAL_CHART_VALUE_INVALID"])
            self.assertIn("图表不可用数值", prepared["gaps"][0]["description"])
            self.assertNotIn("交易日不足", prepared["gaps"][0]["description"])
            calculation_artifact = json.loads((run / calculation_ref).read_text())
            verify_technical_calculation(calculation_artifact)
            self.assertEqual(calculation_artifact["artifact_hash"], prepared["calculation"]["artifact_hash"])
            self.assertNotIn("maxItems", packet["output_schema"]["properties"]["claims"])
            self.assertIn("若 chart=null", packet["instruction"])
            metric = prepared["calculation"]["windows"][0]["metrics"]["security_total_return"]
            draft = self.formal_dimension_draft(task)
            draft.update(
                status="LOW_CONFIDENCE", sufficiency="PARTIAL",
                summary="已有同源计算，图表生成失败不影响计算主张。",
                calculations=[{
                    "calculation_id": "calc-technical-return", "method": "security_total_return",
                    "value": metric, "unit": "ratio", "input_evidence_refs": [],
                    "artifact_ref": calculation_ref,
                }],
                claims=[{
                    "claim_id": "claim-technical-return",
                    "question": packet["minimum_questions"][0],
                    "statement": "20 日窗口的证券收益已由冻结计算给出。",
                    "kind": "INTERPRETATION", "evidence_refs": [],
                    "research_claim_refs": [], "document_refs": [],
                    "assumption_ids": [], "calculation_refs": ["calc-technical-return"],
                }],
                artifact_refs=[calculation_ref],
                data_gaps=[{
                    "gap_id": "gap-chart-render", "reason_code": "UNKNOWN",
                    "description": "相对表现图渲染失败。",
                    "impact": "缺少图形展示，但冻结计算及其主张仍可阅读。",
                }],
            )
            invocation = json.loads((run / task["invocation_path"]).read_text())
            report = envelope_research_dimension_draft(
                draft, task=task, invocation=invocation,
                expected_bindings=self.research_bindings(run), allowed_security_ids=task["security_ids"],
                allowed_evidence_ids=[], allowed_documents=[],
            )
            self.assertEqual(report["claims"][0]["calculation_refs"], ["calc-technical-return"])
            self.assertEqual(report["sufficiency"], "PARTIAL")
            self.assertEqual(report["status"], "LOW_CONFIDENCE")
            self.assertEqual(report["artifact_refs"], [calculation_ref])

    def test_unknown_chart_error_is_not_reclassified_as_data_gap(self) -> None:
        for error in (ValueError("UNEXPECTED_RENDER_ERROR"), PermissionError("CHART_OUTPUT_DENIED")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temp:
                with patch(
                    "product.council.technical_chart.render_relative_performance_svg",
                    side_effect=error,
                ), self.assertRaisesRegex(type(error), str(error)):
                    self.prepare_mrvl_daily_run(Path(temp), include_spy=True)

    def test_chart_history_gap_names_alignment_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "product.council.technical_chart.render_relative_performance_svg",
                side_effect=ValueError("TECHNICAL_CHART_HISTORY_INSUFFICIENT"),
            ):
                run = self.prepare_mrvl_daily_run(Path(temp), include_spy=True)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            prepared = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])["prepared_analysis"]
            self.assertIsNotNone(prepared["calculation"])
            self.assertIsNone(prepared["chart"])
            self.assertEqual(prepared["gaps"][0]["reason_code"], "TECHNICAL_CHART_HISTORY_INSUFFICIENT")
            self.assertIn("可对齐的交易日不足", prepared["gaps"][0]["description"])

    def test_bounded_latest_facts_keeps_recent_values_per_reporting_series(self) -> None:
        facts = []
        for index, as_of in enumerate(("2024-12-31", "2025-12-31", "2026-06-30")):
            facts.append({
                "evidence_id": f"ev-revenue-{index}",
                "security_id": "US:COMMON_STOCK:TEST",
                "semantic_field": "us-gaap.Revenues",
                "unit": "USD",
                "as_of": f"{as_of}T00:00:00Z",
                "published_at": f"{as_of}T20:00:00Z",
                "retrieved_at": "2026-09-15T00:00:00Z",
                "metadata": {"form": "10-K", "period_start": "2024-01-01"},
            })
        selected = _bounded_latest_facts(facts)
        self.assertEqual(
            [item["evidence_id"] for item in selected],
            ["ev-revenue-1", "ev-revenue-2"],
        )

    def test_dependency_report_is_delivered_as_structured_agent_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            fundamental = next(
                item for item in index["tasks"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            invocation = json.loads((run / fundamental["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": fundamental["run_id"],
                    "invocation_id": fundamental["invocation_id"],
                    "agent": fundamental["agent"],
                    "status": "COMPLETE",
                    "sufficiency": "SUFFICIENT",
                    "evaluation_status": "PASS",
                    "summary": "公司资料支持一项有依据的核心判断。",
                    "claims": [{
                        "claim_id": "fundamental-claim-1",
                        "question": "核心经营驱动是什么？",
                        "statement": "收入事实为后续研报对比提供公司基线。",
                        "kind": "FACT",
                        "evidence_refs": [fundamental["allowed_evidence_ids"][0]],
                        "research_claim_refs": [], "assumption_ids": [],
                        "document_refs": [],
                        "calculation_refs": [],
                    }],
                    "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": [], "observation_conditions": [],
                    "data_gaps": [], "artifact_refs": [],
                },
                task=fundamental,
                invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=fundamental["allowed_evidence_ids"],
            )
            output = run / "research/reports/dependency"
            output.mkdir(parents=True)
            (output / "dimension-report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            dependent = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, dependent["task_name"]
            )
            from product.runtime.multidimensional_references import scoped_claim_reference
            self.assertEqual(packet["allowed_research_claim_ids"],
                             [scoped_claim_reference(report, "fundamental-claim-1")])
            self.assertEqual(
                packet["dependency_reports"][0]["report_hash"], report["report_hash"]
            )

    def test_finalizer_keeps_valid_reports_and_records_dependency_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            bindings = {
                "handoff_id": handoff["handoff_id"],
                "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
                "decision_cutoff": gate["decision_cutoff"],
            }
            failed_task = next(
                task for task in index["tasks"]
                if task["capability"] == "FUNDAMENTAL_EVENT"
            )
            blocked_task = next(
                task for task in index["tasks"]
                if task["capability"] == "RESEARCH_REPORT"
            )
            events = []
            for task in index["tasks"]:
                if task is failed_task:
                    events.append({
                        "hook_event_name": "SubagentStop",
                        "final_structured_output_hash": "f" * 64,
                        "output_binding": {"invocation_id": task["invocation_id"]},
                        "output_capture": {
                            "status": "FAILED",
                            "failure_code": "DIMENSION_REPORT_CLAIM_UNGROUNDED",
                        },
                    })
                    continue
                if task is blocked_task:
                    continue
                invocation = json.loads((run / task["invocation_path"]).read_text())
                report = envelope_research_dimension_draft(
                    {
                        "run_id": task["run_id"],
                        "invocation_id": task["invocation_id"],
                        "agent": task["agent"],
                        "status": "INSUFFICIENT_EVIDENCE",
                        "sufficiency": "INSUFFICIENT",
                        "evaluation_status": "NOT_EVALUATED",
                        "summary": "本测试仅验证失败隔离与覆盖交接。",
                        "claims": [], "assumptions": [], "calculations": [],
                        "documents": [], "research_relationships": [],
                        "limitations": ["资料不足。"],
                        "observation_conditions": [],
                        "data_gaps": [{
                            "gap_id": f"gap:{task['task_id']}",
                            "reason_code": "UNKNOWN",
                            "description": "测试资料不足。",
                            "impact": "不形成研究主张。",
                        }],
                        "artifact_refs": [],
                    },
                    task=task,
                    invocation=invocation,
                    expected_bindings=bindings,
                    allowed_security_ids=[
                        item["security_id"] for item in handoff["portfolio"]["positions"]
                    ],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    allowed_documents=task.get("allowed_documents", []),
                )
                output = persist_dimension_report(
                    run / "research/reports" / task["task_id"],
                    report=report,
                    evidence=[],
                )
                events.append({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                })
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps(
                    {
                        "task_name": task["task_name"],
                        "decision": "DENY_DISPATCH_CONTRACT",
                        "dispatch_binding": {
                            "failure_code": "RESEARCH_DEPENDENCY_NOT_READY"
                        },
                    }
                    if task is blocked_task else {
                        "task_name": task["task_name"], "decision": "ALLOW"
                    }
                ) for task in index["tasks"]) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8",
            )
            result = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["contract_status"], "FAILED")
            self.assertEqual(result["completed"], 6)
            self.assertEqual(result["expected"], 8)
            self.assertEqual(result["research_review_status"], "NOT_REVIEWED")
            self.assertEqual(result["promotion_status"], "NOT_EVALUATED")
            bundle = json.loads(
                (run / "research/holding-research-bundle.json").read_text()
            )
            failed = next(
                item for item in bundle["coverage"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
            )
            self.assertEqual(failed["status"], "FAILED")
            self.assertIsNone(failed["report_id"])
            self.assertIn("DIMENSION_REPORT_CLAIM_UNGROUNDED", failed["gap_reason"])
            blocked = next(
                item for item in bundle["coverage"]
                if item["capability"] == "RESEARCH_REPORT"
            )
            self.assertEqual(blocked["status"], "FAILED")
            self.assertIn(
                "MULTIDIMENSIONAL_UPSTREAM_DEPENDENCY_FAILED",
                blocked["gap_reason"],
            )
            proof = json.loads((run / "research/execution-proof.json").read_text())
            self.assertFalse(proof["all_reports_valid"])
            self.assertTrue(proof["coverage_complete"])
            self.assertEqual(
                {item["task_id"] for item in proof["failed_tasks"]},
                {failed_task["task_id"], blocked_task["task_id"]},
            )
            markdown = (run / "research/holding-research-bundle.md").read_text()
            self.assertIn("## 已验证报告摘要", markdown)
            self.assertIn("本测试仅验证失败隔离与覆盖交接。", markdown)
            self.assertIn("## 未形成有效报告的维度", markdown)
            self.assertIn("未执行额外语义综合", markdown)

    def test_finalizer_records_started_task_without_stop_as_explicit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            missing_task = next(
                task for task in index["tasks"]
                if task["capability"] == "INDUSTRY_COMPARISON"
            )
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            bindings = {
                "handoff_id": handoff["handoff_id"],
                "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
                "decision_cutoff": gate["decision_cutoff"],
            }
            events = []
            for task in index["tasks"]:
                if task is missing_task:
                    events.append({
                        "hook_event_name": "SubagentStart",
                        "context_binding": {
                            "status": "DELIVERED",
                            "invocation_id": task["invocation_id"],
                        },
                    })
                    events.append({
                        "hook_event_name": "SubagentStopBlocked",
                        "child_session_id": "child-repair-unavailable",
                        "output_binding": {"invocation_id": task["invocation_id"]},
                        "repair_request": {
                            "task_id": task["task_id"],
                            "invocation_id": task["invocation_id"],
                            "validation_error": "DIMENSION_REPORT_SCHEMA_INVALID",
                            "output_schema_hash": "a" * 64,
                        },
                        "output_capture": {
                            "status": "FAILED",
                            "attempt": 1,
                            "repair_state": "REPAIR_REQUESTED",
                            "raw_output_hash": "b" * 64,
                            "raw_path": "research/raw-drafts/unavailable.json",
                        },
                    })
                    continue
                invocation = json.loads((run / task["invocation_path"]).read_text())
                report = envelope_research_dimension_draft(
                    {
                        "run_id": task["run_id"],
                        "invocation_id": task["invocation_id"],
                        "agent": task["agent"],
                        "status": "INSUFFICIENT_EVIDENCE",
                        "sufficiency": "INSUFFICIENT",
                        "evaluation_status": "NOT_EVALUATED",
                        "summary": "本测试验证缺失终态事件的失败隔离。",
                        "claims": [], "assumptions": [], "calculations": [],
                        "documents": [], "research_relationships": [],
                        "limitations": ["资料不足。"],
                        "observation_conditions": [],
                        "data_gaps": [{
                            "gap_id": f"gap:{task['task_id']}",
                            "reason_code": "UNKNOWN",
                            "description": "测试资料不足。",
                            "impact": "不形成研究主张。",
                        }],
                        "artifact_refs": [],
                    },
                    task=task, invocation=invocation,
                    expected_bindings=bindings,
                    allowed_security_ids=[
                        item["security_id"] for item in handoff["portfolio"]["positions"]
                    ],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    allowed_documents=task.get("allowed_documents", []),
                )
                output = persist_dimension_report(
                    run / "research/reports" / task["task_id"],
                    report=report, evidence=[],
                )
                events.append({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                })
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps({
                    "task_name": task["task_name"], "decision": "ALLOW"
                }) for task in index["tasks"]) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8",
            )
            result = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["contract_status"], "FAILED")
            bundle = json.loads(
                (run / "research/holding-research-bundle.json").read_text()
            )
            failed = next(
                item for item in bundle["coverage"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            )
            self.assertEqual(failed["status"], "FAILED")
            self.assertIn("TERMINAL_EVENT_MISSING", failed["gap_reason"])
            proof = json.loads((run / "research/execution-proof.json").read_text())
            self.assertEqual(
                proof["failed_tasks"][0]["failure_source"],
                "START_WITHOUT_STOP_AFTER_PARENT_EXIT",
            )
            self.assertIsNone(proof["failed_tasks"][0]["rejected_output_hash"])
            self.assertEqual(len(proof["repair_attempts"]), 1)
            self.assertEqual(
                proof["repair_attempts"][0]["task_id"], missing_task["task_id"]
            )
            self.assertIsNone(
                proof["repair_attempts"][0]["terminal_status"]
            )


if __name__ == "__main__":
    unittest.main()
