"""合成运行产物验证 Eval 接缝；注入评分不是实际 LLM 研究验收。"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from importlib.metadata import PackageNotFoundError

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import normalize_sec_fact
from product.mcp.provenance import content_hash
from product.runtime.discovery import discover_product_resources
from product.runtime.live_input import freeze_snapshot
from product.runtime.native_eval import evaluate_run, persist_eval_result
from product.runtime.release_gate import check_run
from product.runtime.run_package import prepare_live_run, prepare_cio, finalize_cio
from product.runtime.runtime_eval import prepare_eval_job, finalize_eval_job, verify_runtime_eval_job
from tests import test_live_contracts_gate as samples
from tests.test_native_run_package import specialist_outputs, cio_output, read_json, write_json
from tests.test_runtime_eval_job import semantic_result

ROOT = Path(__file__).resolve().parents[1]
REFS = ["price", "revenue-current", "revenue-prior", "disclosure"]


def synthetic_run(directory, *, action="NO_TRADE", generic=False, dangling=False, stop_before_cio=False):
    """使用实际 prepare/Gate/Risk/finalize；只有输入和角色输出为显式测试数据。"""
    from product.mcp.live.market import ExchangeCalendar
    sample = samples.LiveContractGateTests()
    sample.setUp()
    sample.portfolio["cash"] = 200  # 合成完整组合：200 市值 + 200 现金。
    calendar = ExchangeCalendar(start="2026-09-01", end="2026-09-11")
    cache = SnapshotCache(directory / "cache")
    mapping = json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                          "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}).encode()
    records = [cache.store({"provider": "sec", "url": "synthetic-map"}, mapping,
                           retrieved_at="2026-09-10T00:00:00Z")]
    price = deepcopy(sample.fact)
    price["metadata"].update(calendar_version=calendar.version, calendar_hash=calendar.content_hash)
    records.append(cache.store({"provider": "yahoo", "ticker": "TEST"}, b"synthetic-price-20",
                               retrieved_at="2026-09-10T00:00:00Z"))
    price["raw_content_hash"] = records[-1]["raw_content_hash"]
    facts = [price]
    for year, value, usage in ((2026, "120", "current"), (2025, "100", "comparison")):
        records.append(cache.store({"provider": "sec", "year": year}, value.encode(),
                                   retrieved_at="2026-09-10T00:00:00Z"))
        facts.append(normalize_sec_fact({
            "evidence_id": "revenue-current" if year == 2026 else "revenue-prior",
            "taxonomy": "us-gaap", "tag": "Revenues", "value": value, "unit": "USD",
            "source_id": "synthetic-sec", "source_locator": f"synthetic/{year}",
            "adapter_version": "synthetic/1", "as_of": f"{year}-06-30T00:00:00Z",
            "published_at": f"{year}-08-01T00:00:00Z", "retrieved_at": "2026-09-10T00:00:00Z",
            "raw_content_hash": records[-1]["raw_content_hash"], "cik": "0000000001",
            "form": "10-Q", "context_type": "duration", "period_start": f"{year}-01-01",
            "period_end": f"{year}-06-30"}, security_id="TEST", usage=usage))
    disclosure = "合成披露：TEST 收入主要来自单一客户，续约谈判尚未完成。"
    records.append(cache.store({"provider": "sec", "section": "risk"}, disclosure.encode(),
                               retrieved_at="2026-09-10T00:00:00Z"))
    facts.append(dict(price, evidence_id="disclosure", semantic_field="risk_factors", kind="disclosure",
                      value=disclosure, unit=None, currency=None, source_id="synthetic-sec", source_type="sec",
                      source_locator="synthetic/10-Q#risk", raw_content_hash=records[-1]["raw_content_hash"],
                      as_of="2026-08-01T00:00:00Z", published_at="2026-08-01T00:00:00Z",
                      published_at_policy="synthetic-acceptance", metadata={"untrusted_text": True, "form": "10-Q"}))
    snapshot = freeze_snapshot(snapshot_id="synthetic-eval", portfolio=sample.portfolio,
        request_started_at="2026-09-10T00:00:00Z", decision_cutoff="2026-09-10T01:00:00Z",
        facts=facts, source_access=[sample.access, dict(sample.access, provider="sec")],
        raw_records=records, collection_events=[], gaps=[], identity=sample.identity())
    write_json(directory / "portfolio.json", sample.portfolio)
    write_json(directory / "snapshot.json", snapshot)
    run = directory / "run"
    model = discover_product_resources(ROOT).version_manifest["model"]
    prepared = prepare_live_run(ROOT, portfolio_path=directory / "portfolio.json",
        snapshot_path=directory / "snapshot.json", cache_root=cache.root, calendar=calendar,
        run_dir=run, run_id=f"synthetic-{directory.name}", model=model, authenticity_required=False)
    assert prepared["next_state"] == "DISPATCH_REQUIRED", prepared
    gate = read_json(run / "evidence/gate.json")
    assert set(gate["allowed_evidence_ids"]) == set(REFS), gate
    specialist_outputs(run)
    analyst = read_json(run / "agents/runtime_company_analyst.json")
    analyst.update(scope="TEST 合成研究", counter_evidence_refs=["disclosure"],
                   invalidation_conditions=["下一次披露显示客户未续约"])
    analyst["claims"][0].update(statement="TEST 两期同口径收入分别为 120 和 100 USD。",
                                evidence_refs=["missing"] if dangling else ["revenue-current", "revenue-prior"])
    analyst["claims"].append({"claim_id": "price-claim", "statement": "TEST 合成收盘价为 20 USD。",
                              "kind": "FACT", "evidence_refs": ["price"], "assumption_ids": []})
    write_json(run / "agents/runtime_company_analyst.json", analyst)
    skeptic = read_json(run / "agents/runtime_skeptic.json")
    skeptic.update(scope="TEST 合成独立反证", evidence_refs=["disclosure"], counter_evidence_refs=["revenue-current"])
    skeptic["challenges"][0].update(statement="收入增长不能证明单一客户必将续约。", evidence_refs=["disclosure"],
                                   resolution_evidence_needed=["下一次客户续约披露"])
    write_json(run / "agents/runtime_skeptic.json", skeptic)
    if stop_before_cio:
        return run
    prepared = prepare_cio(ROOT, run_dir=run, model=model)
    if dangling:
        assert read_json(run / "decision_trace.json")["terminal_state"] == "FAILED_VALIDATION", prepared
        return run
    assert prepared["next_state"] == "CIO_SYNTHESIS_REQUIRED", prepared
    draft = cio_output(run)
    draft.update(action=action, security_id="TEST", current_weight=0.5, evidence_refs=REFS,
        thesis="风险较大，建议观望。" if generic else "TEST 收入改善支持经营韧性，但依赖客户续约这一假设。",
        counter_thesis="单一客户尚未续约，收入改善不消除客户集中风险。",
        time_horizon="6 months", consensus=["两期收入与客户集中披露均保留。"],
        unresolved_questions=["客户是否续约"], invalidation_conditions=["下一次披露确认客户流失"],
        confidence_rationale="两期收入可比，但续约结论未知。")
    if action == "NO_TRADE":
        draft.update(target_weight_range=None, maximum_notional=None, no_trade_reason="INSUFFICIENT_EVIDENCE",
            no_trade_explanation="谨慎观望。" if generic else "TEST 占组合 50%，六个月内客户续约不确定，待披露再判断。",
            reevaluation_conditions=["取得下一次客户续约披露"])
    elif action == "TRIM":
        draft.update(target_weight_range=[0.4, 0.4], maximum_notional=40)
    write_json(run / "cio/runtime_cio.json", draft)
    finished = finalize_cio(ROOT, run_dir=run)
    # 不为测试动作绕过真实 Risk；如要求修订，保留原草案测试第二次确定性否决。
    assert "next_state" in finished, finished
    if finished["next_state"] == "ONE_CIO_REVISION_REQUIRED":
        write_json(run / "cio/runtime_cio_revision.json", draft)
        finished = finalize_cio(ROOT, run_dir=run, revision=True)
    assert finished["next_state"] in {"COMPLETED", "SAFE_NO_TRADE"}, finished
    return run


@unittest.skipUnless(importlib.util.find_spec("exchange_calendars"), "requires optional live calendar")
class LiveEvalContractTests(unittest.TestCase):
    def test_cio_context_failure_is_persisted_before_risk_without_advice(self):
        from product.runtime.trace_validation import validate_decision_trace
        for failure, code in ((PackageNotFoundError("exchange-calendars"), "RUNTIME_DEPENDENCY_MISSING"),
                              (ValueError("LIVE_SNAPSHOT_HASH_MISMATCH"), "LIVE_CIO_CONTEXT_INVALID")):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                run = synthetic_run(Path(temporary), stop_before_cio=True)
                model = read_json(run / "run_manifest.json")["model"]
                with patch("product.runtime.live_context.load_live_run_context", side_effect=failure):
                    result = prepare_cio(ROOT, run_dir=run, model=model)
                self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
                self.assertEqual(result["code"], code)
                self.assertEqual(result["failed_stage"], "CIO_SYNTHESIS")
                trace = read_json(run / "decision_trace.json")
                self.assertEqual(trace["risk_lineage"], [])
                validate_decision_trace(trace, run_dir=run)
                self.assertFalse((run / "decision.json").exists())
                self.assertFalse((run / "report.md").exists())

    def test_representative_reports_bind_actual_artifacts_and_propagate_grader_verdict(self):
        for action, generic in (("NO_TRADE", False), ("NO_TRADE", True), ("HOLD", False), ("TRIM", False)):
            with self.subTest(action=action, generic=generic), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                run = synthetic_run(directory, action=action, generic=generic)
                native = evaluate_run(ROOT, run_dir=run, allow_test_artifacts=True)
                persist_eval_result(native, run_dir=run)
                status, code = check_run(ROOT, run_dir=run)
                self.assertEqual(code, 0, status)
                self.assertEqual(status["category"], "RUNTIME_SAFE_RESEARCH_UNASSESSED")
                job = directory / "eval-job"
                prepared = prepare_eval_job(ROOT, run_dir=run, eval_dir=job, eval_id="synthetic-eval")
                self.assertEqual(prepared["next_state"], "SEMANTIC_GRADING_REQUIRED")
                actual = read_json(job / "grader-input.json")
                self.assertEqual(actual["artifacts"]["cio/runtime_cio.json"], read_json(run / "cio/runtime_cio.json"))
                self.assertEqual(actual["artifacts"]["cio/runtime_cio.json"]["action"], action)
                self.assertEqual(actual["artifacts"]["evidence/gate.json"], read_json(run / "evidence/gate.json"))
                self.assertEqual(read_json(job / "input-manifest.json")["source_hashes"]["semantic_input"], content_hash(actual))
                with self.assertRaisesRegex(ValueError, "SEMANTIC_RESULT_REQUIRED"):
                    finalize_eval_job(ROOT, eval_dir=job)
                # 测试替身只验证评分结果传播，不声称这些文本已被真实 LLM 判为合格。
                grade = semantic_result(job, status="FAIL" if generic else "PASS", grade=0 if generic else 2)
                for item in grade["dimensions"].values():
                    item.update(evidence_refs=REFS, rationale="合成评分替身：核对已绑定 TEST 报告与证据；不是实际 dev_eval。")
                if action != "NO_TRADE":
                    grade["dimensions"]["no_trade_reasoning"].update(status="NOT_APPLICABLE", grade=None)
                grade["output_hash"] = content_hash({k: v for k, v in grade.items() if k != "output_hash"})
                write_json(directory / "grade.json", grade)
                result = finalize_eval_job(ROOT, eval_dir=job, semantic_result_path=directory / "grade.json")
                self.assertEqual(result["status"], "FAIL" if generic else "PASS")
                verify_runtime_eval_job(ROOT, eval_result_path=job / "eval/result.json")
                self.assertTrue((job / "eval/report.md").is_file())

    def test_dangling_specialist_reference_is_contained_not_published(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            run = synthetic_run(directory, dangling=True)
            self.assertFalse((run / "decision.json").exists())
            job = directory / "eval-job"
            result = prepare_eval_job(ROOT, run_dir=run, eval_dir=job, eval_id="synthetic-invalid")
            self.assertEqual(result["hard_gate_status"], "FAIL")
            result = finalize_eval_job(ROOT, eval_dir=job)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("HARD_GATE_FAILED:evidence_closure", result["reason_codes"])

    def test_missing_risk_artifact_cannot_enter_semantic_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            run = synthetic_run(directory)
            risk = run / "risk/check-1.json"
            self.assertTrue(risk.is_file())
            risk.unlink()  # 仅删除临时合成运行文件，真实注入底层缺失，不伪造 PASS 摘要。
            with self.assertRaises(ValueError):
                prepare_eval_job(ROOT, run_dir=run, eval_dir=directory / "eval-job", eval_id="synthetic-risk-missing")
            self.assertFalse((directory / "eval-job/grader-input.json").exists())

    def test_grading_input_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            run = synthetic_run(directory)
            job = directory / "eval-job"
            prepare_eval_job(ROOT, run_dir=run, eval_dir=job, eval_id="synthetic-drift")
            grade = semantic_result(job)
            grade["grader"]["input_hash"] = "0" * 64
            grade["output_hash"] = content_hash({k: v for k, v in grade.items() if k != "output_hash"})
            write_json(directory / "grade.json", grade)
            with self.assertRaisesRegex(ValueError, "GRADER_LINEAGE"):
                finalize_eval_job(ROOT, eval_dir=job, semantic_result_path=directory / "grade.json")


if __name__ == "__main__":
    unittest.main()
