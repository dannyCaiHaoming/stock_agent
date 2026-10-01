"""限定版本主张引用：实际装配/读取接缝，不启动模型。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_references import (
    VERSION, LEGACY_VERSION, build_reference_map, known_claim_references,
    parse_scoped_claim_reference, scoped_claim_reference, translate_references,
    validate_reference_map,
)
from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet
from product.runtime.multidimensional_stage import serialize_multidimensional_initial_context, serialize_multidimensional_model_context
from product.council.multidimensional_research import (
    derive_unresolved_research_questions, envelope_research_dimension_draft, validate_research_dimension_report,
)
from product.council.multidimensional_output import render_dimension_report_markdown
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.research_submission import _assemble_v4_draft, _v4_reference_binding, _verify_v4_saved_statements
from product.runtime.research_submission import _selected_documents
from tests import test_multidimensional_stage as fixtures


class ScopedResearchClaimTests(unittest.TestCase):
    def test_unresolved_questions_qualify_same_named_claims_by_report_and_version(self):
        reports = [{"report_id": f"equity:{symbol}", "security": {"security_id": symbol},
            "claims": [{"claim_id": "same", "statement": f"{symbol} 的原观点"}],
            "invalidation_conditions": [{"condition_id": "condition", "description": "观察条件",
                                         "claim_refs": ["same"]}]}
            for symbol in ("AAPL", "MSFT")]
        originals = copy.deepcopy(reports)
        questions = derive_unresolved_research_questions(dimension_reports=[], equity_reports=reports)
        self.assertEqual(len(questions), 2)
        self.assertNotEqual(questions[0]["claim_refs"], questions[1]["claim_refs"])
        for question in questions:
            target = parse_scoped_claim_reference(question["claim_refs"][0])
            report = next(item for item in reports if item["report_id"] == target["report_id"])
            self.assertEqual(target["claim_id"], "same")
            self.assertEqual(target["report_hash"], canonical_hash(report))
            self.assertEqual(question["report_refs"], [report["report_id"]])
        self.assertEqual(reports, originals)

    def packet(self):
        return {
            "reference_transport_version": VERSION,
            "identity": {"run_id": "run", "invocation_id": "task", "agent": "researcher"},
            "allowed_evidence_ids": ["ev-first", "ev-second"],
            "dependency_reports": [
                {"report_id": name, "report_hash": canonical_hash({"report": name}),
                 "claims": [{"claim_id": "same_name", "statement": f"{name} 的原观点"}]}
                for name in ("report:first", "report:second")
            ],
        }

    def test_same_name_keeps_two_report_versions_and_local_name(self):
        packet = self.packet()
        mapping = build_reference_map(packet, "gate", "/run")
        short = list(mapping["claims"])
        value = {"claims": [{"claim_id": "same_name", "statement": "正文不替换 c.fake 或同名主张",
                             "research_claim_refs": ["same_name", *short]}]}
        original = copy.deepcopy(value)
        resolved = translate_references(value, mapping, local_claims={"same_name"})
        refs = resolved["claims"][0]["research_claim_refs"]
        self.assertEqual(refs[0], "same_name")
        self.assertEqual(len(set(refs)), 3)
        self.assertEqual([parse_scoped_claim_reference(ref) for ref in refs[1:]], [
            {"report_id": item["report_id"], "report_hash": item["report_hash"], "claim_id": "same_name"}
            for item in mapping["claims"].values()
        ])
        self.assertEqual(translate_references(resolved, mapping, to_model=True, local_claims={"same_name"}), original)
        self.assertEqual(value, original)
        self.assertNotIn("same_name", known_claim_references(packet["dependency_reports"]))

    def test_scoped_ids_roundtrip_utf8_and_reject_noncanonical_or_hash_guess(self):
        report = {"report_id": "报告:一", "report_hash": "a" * 64}
        ref = scoped_claim_reference(report, "增长率")
        self.assertEqual(parse_scoped_claim_reference(ref), {**report, "claim_id": "增长率"})
        for invalid in (ref.upper(), ref + "|source", "rc1.0.not-hash.00", "rc1.ff." + "a" * 64 + ".11"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_scoped_claim_reference(invalid)

    def test_old_map_is_readable_but_ambiguous_bare_claims_fail(self):
        packet = self.packet()
        packet["reference_transport_version"] = LEGACY_VERSION
        with self.assertRaisesRegex(ValueError, "CLAIM_AMBIGUOUS"):
            build_reference_map(packet, "gate", "/run")
        packet["dependency_reports"] = packet["dependency_reports"][:1]
        mapping = build_reference_map(packet, "gate", "/run")
        self.assertEqual(mapping["binding"]["version"], LEGACY_VERSION)
        validate_reference_map(mapping)
        resolved = translate_references({"research_claim_refs": list(mapping["claims"])}, mapping)
        self.assertEqual(resolved["research_claim_refs"], ["same_name"])
        self.assertNotIn("canonical_ref", next(iter(mapping["claims"].values())))

    def test_local_claim_cannot_mask_transport_namespace(self):
        mapping = build_reference_map(self.packet(), "gate", "/run")
        for ref in (next(iter(mapping["evidence"])), next(iter(mapping["claims"])), "d.fake", "k.fake", "rc1.fake"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "LOCAL_NAMESPACE_COLLISION"):
                translate_references({"research_claim_refs": [ref]}, mapping, local_claims={ref})

    def test_task_run_gate_and_report_version_isolation_in_parallel(self):
        packet = self.packet()
        source = build_reference_map(packet, "gate", "/run")
        changes = []
        for field, value in (("run_id", "another-run"), ("invocation_id", "another-task")):
            other = copy.deepcopy(packet)
            other["identity"][field] = value
            changes.append((other, "gate", "/run"))
        other = copy.deepcopy(packet)
        other["dependency_reports"][0]["report_hash"] = "b" * 64
        changes.extend([(other, "gate", "/run"), (packet, "new-gate", "/run"), (packet, "gate", "/moved")])
        with ThreadPoolExecutor(max_workers=5) as pool:
            maps = list(pool.map(lambda args: build_reference_map(*args), changes))
        old_short = next(iter(source["claims"]))
        for mapping in maps:
            self.assertNotEqual(source["map_hash"], mapping["map_hash"])
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                translate_references({"research_claim_refs": [old_short]}, mapping)
        with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
            translate_references({"evidence_refs": [old_short]}, source)

    def test_map_json_order_and_corruption_without_history_rewrite(self):
        packet = self.packet()
        packet["dependency_reports"][0]["claims"] = [
            {"claim_id": f"claim{i}", "statement": str(i)} for i in range(15)
        ]
        mapping = build_reference_map(packet, "gate", "/run")
        original = json.dumps(mapping, ensure_ascii=False, sort_keys=True).encode()
        validate_reference_map(json.loads(original))
        altered = copy.deepcopy(mapping)
        first = next(iter(altered["claims"]))
        altered["claims"][first]["report_hash"] = "f" * 64
        altered["map_hash"] = canonical_hash({k: v for k, v in altered.items() if k != "map_hash"})
        with self.assertRaisesRegex(ValueError, "MAP_INVALID"):
            validate_reference_map(altered)
        self.assertEqual(json.dumps(mapping, ensure_ascii=False, sort_keys=True).encode(), original)

    def test_document_reference_locks_exact_content_and_type(self):
        packet = self.packet()
        document = {"document_id": "doc-company-report", "title": "原报告", "value": "原文不截断",
                    "source_id": "source", "as_of": "2026-09-01", "retrieved_at": "2026-09-02"}
        packet["task"] = {"allowed_documents": [document]}
        mapping = build_reference_map(packet, "gate", "/run")
        packet["reference_map"] = mapping
        short = next(iter(mapping["documents"]))
        self.assertEqual(_selected_documents({}, packet, [short]), [document])
        self.assertEqual(_selected_documents({}, packet, [document["document_id"]]), [document])
        with self.assertRaisesRegex(ValueError, "SELECTION_AMBIGUOUS"):
            _selected_documents({}, packet, [short, document["document_id"]])
        self.assertEqual(translate_references({"document_id": short, "document_refs": [short]}, mapping),
                         {"document_id": document["document_id"], "document_refs": [document["document_id"]]})
        for field in ("evidence_refs", "research_claim_refs"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                translate_references({field: [short]}, mapping)
        packet["task"]["allowed_documents"][0]["title"] = "更新后的报告"
        with self.assertRaisesRegex(ValueError, "DOCUMENT_BINDING_MISMATCH"):
            _selected_documents({}, packet, [short])
        updated = build_reference_map(packet, "gate", "/run")
        with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
            translate_references({"document_refs": [short]}, updated)

    def test_relation_clauses_use_scoped_identity_not_bare_names(self):
        packet = self.packet()
        packet["task"] = {"submission_version": "research-object-submission/4.0.0"}
        packet["reference_map"] = build_reference_map(packet, "gate", "/run")
        short = list(packet["reference_map"]["claims"])
        draft = {"claims": [{"claim_id": "same_name", "core_statement": "本地研究观点。",
                             "research_claim_refs": ["same_name", *short],
                             "research_relation_clauses": [
                                 {"research_claim_ref": ref, "relation_statement": f"对第{i}份报告的明确关系。"}
                                 for i, ref in enumerate(short)
                             ]}]}
        assembled, _ = _assemble_v4_draft(draft, packet)
        formal = translate_references(assembled, packet["reference_map"], local_claims={"same_name"})
        _verify_v4_saved_statements(draft, formal, _v4_reference_binding(packet))
        bad = copy.deepcopy(draft)
        bad["claims"][0]["claim_id"] = "other"
        with self.assertRaisesRegex(ValueError, "RELATION_REFERENCE_INVALID"):
            _assemble_v4_draft(bad, packet)

    def test_real_hook_producer_scoped_reference_reaches_formal_consumer(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            f.save_fundamental_dependency(run, index)
            task = next(t for t in index["tasks"] if t["capability"] == "RESEARCH_REPORT")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            self.assertEqual(packet["reference_map"]["binding"]["version"], VERSION)
            for serializer in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                context = json.loads(serializer(packet))
                self.assertNotIn("canonical_ref", json.dumps(context))
                self.assertNotIn("rc1.", json.dumps(context))
                for item in context.get("upstream_short_references", {}).values():
                    self.assertEqual(set(item), {"report_id", "claim_id"})
            env = f.targeted_environment(run, task)
            handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
            handle_hook_event(f.start_payload(task, parent="dependency-parent", child="claim-child"), environ=env)
            draft = f.dimension_draft(task)
            short = next(iter(packet["reference_map"]["claims"]))
            draft["claims"] = [{"claim_id": "mrvl_core_drivers", "question": "上游研究意味着什么？",
                                "statement": "原研究事实只是基线，不能证明未来增速。", "kind": "INTERPRETATION",
                                "evidence_refs": [], "research_claim_refs": [short], "document_refs": [],
                                "assumption_ids": []}]
            stopped, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="claim-child"), environ=env)
            self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
            path = run / stopped["output_capture"]["path"]
            before = path.read_bytes()
            report = json.loads(before)
            allowed = known_claim_references(packet["dependency_reports"], allow_legacy=False)
            validate_research_dimension_report(
                report, expected_bindings=report["bindings"], allowed_security_ids=task["security_ids"],
                allowed_evidence_ids=task["allowed_evidence_ids"], known_research_claim_ids=allowed,
            )
            ref = report["claims"][0]["research_claim_refs"][0]
            self.assertEqual(parse_scoped_claim_reference(ref)["report_hash"], packet["dependency_reports"][0]["report_hash"])
            drifted = copy.deepcopy(packet["dependency_reports"])
            drifted[0]["report_hash"] = "c" * 64
            with self.assertRaisesRegex(ValueError, "RESEARCH_CLAIM_DANGLING"):
                validate_research_dimension_report(
                    report, expected_bindings=report["bindings"], allowed_security_ids=task["security_ids"],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    known_research_claim_ids=known_claim_references(drifted, allow_legacy=False),
                )
            self.assertEqual(path.read_bytes(), before)
            rendered = render_dimension_report_markdown(report, evidence=[])
            self.assertIn(packet["dependency_reports"][0]["report_hash"], rendered)
            self.assertIn(packet["dependency_reports"][0]["report_id"], rendered)
            self.assertIn("主张 `mrvl_core_drivers`", rendered)
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])

    def test_actual_formal_producers_with_duplicate_claim_reach_consumer(self):
        """Two deterministic source reports and one dependent report; no model proof."""
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=2)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            bindings = {"handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
                        "portfolio_hash": handoff["portfolio_hash"], "council_request_id": request["request_id"],
                        "council_request_hash": request["request_hash"], "decision_cutoff": gate["decision_cutoff"]}
            security_ids = [p["security_id"] for p in handoff["portfolio"]["positions"]]
            dependencies = []
            for task in [t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT"]:
                draft = f.formal_dimension_draft(task)
                draft["claims"] = [{"claim_id": "same_name", "question": "经营事实？",
                                    "statement": f"{task['security_ids'][0]} 的原始研究。", "kind": "FACT",
                                    "evidence_refs": [task["allowed_evidence_ids"][0]], "research_claim_refs": [],
                                    "document_refs": [], "assumption_ids": [], "calculation_refs": []}]
                dependencies.append(envelope_research_dimension_draft(
                    draft, task=task, invocation=json.loads((run / task["invocation_path"]).read_text()),
                    expected_bindings=bindings, allowed_security_ids=security_ids,
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                ))
            target = next(t for t in index["tasks"] if t["capability"] == "RESEARCH_REPORT")
            packet = {"reference_transport_version": VERSION, "identity": {"run_id": target["run_id"],
                      "invocation_id": target["invocation_id"]}, "allowed_evidence_ids": target["allowed_evidence_ids"],
                      "dependency_reports": dependencies}
            mapping = build_reference_map(packet, gate["bundle_hash"], str(run))
            draft = f.formal_dimension_draft(target)
            draft["claims"] = [{"claim_id": "local", "question": "两份研究何种关系？",
                                "statement": "两份报告分别提供不同公司经营基线。", "kind": "COMPARISON",
                                "evidence_refs": [], "research_claim_refs": list(mapping["claims"]), "document_refs": [],
                                "assumption_ids": [], "calculation_refs": []}]
            allowed = known_claim_references(dependencies, allow_legacy=False)
            report = envelope_research_dimension_draft(
                translate_references(draft, mapping), task=target,
                invocation=json.loads((run / target["invocation_path"]).read_text()), expected_bindings=bindings,
                allowed_security_ids=security_ids, allowed_evidence_ids=target["allowed_evidence_ids"],
                known_research_claim_ids=allowed,
            )
            validate_research_dimension_report(
                report, expected_bindings=bindings, allowed_security_ids=security_ids,
                allowed_evidence_ids=target["allowed_evidence_ids"], known_research_claim_ids=allowed,
            )
            self.assertEqual(len(set(report["claims"][0]["research_claim_refs"])), 2)
            for refs in (["same_name"], [scoped_claim_reference(dependencies[0], "invented")]):
                invalid = copy.deepcopy(report)
                invalid["claims"][0]["research_claim_refs"] = refs
                invalid["report_hash"] = canonical_hash({k: v for k, v in invalid.items() if k != "report_hash"})
                with self.assertRaisesRegex(ValueError, "RESEARCH_CLAIM_DANGLING"):
                    validate_research_dimension_report(
                        invalid, expected_bindings=bindings, allowed_security_ids=security_ids,
                        allowed_evidence_ids=target["allowed_evidence_ids"],
                        known_research_claim_ids=known_claim_references(dependencies),
                    )
