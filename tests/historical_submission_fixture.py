"""仅在测试临时目录构造 v3–v5 历史包；不经过产品提交入口。

保留退役协议的存档格式与当时的预检查向量，用于验证当前读取器。
这些合成回执/事件不是当前 MCP 写入、真实 Agent 或历史执行证明。
产品代码不得导入此模块。当前写入由 test_bounded_research_submission 验证。
"""
from __future__ import annotations

import json
import os
import secrets

from product.runtime import research_submission as submission
from product.runtime.calculation_handoff import validate_semantic_selection_draft
from product.runtime.hashing import canonical_hash, legacy_envelope_hash


def store_historical_submission_fixture(tools, task, draft):
    root = tools.default_run_dir
    packet = submission._packet(root, task["invocation_id"])
    version = packet["task"]["submission_version"]
    if version not in {submission.VERSION, submission.FORMAL_VERSION, submission.SHORT_RECEIPT_VERSION}:
        raise AssertionError("此构造器只用于明确标记的历史 v3–v5 合成包")
    token = packet["submission_access"]["token"]
    if not isinstance(draft, dict) or submission.IDENTITY_FIELDS & draft.keys():
        raise ValueError("RESEARCH_SUBMISSION_DRAFT_IDENTITY_FORBIDDEN")
    body = json.dumps(draft, ensure_ascii=False, allow_nan=False)
    if token in body:
        raise ValueError("RESEARCH_SUBMISSION_CREDENTIAL_IN_DRAFT")
    if len(body.encode("utf-8")) > submission.MAX_BYTES:
        raise ValueError("RESEARCH_SUBMISSION_TOO_LARGE")
    if "calculation_selections" in draft:
        validate_semantic_selection_draft(draft, packet)
    if "document_selections" in draft:
        submission._selected_documents(draft, packet, draft["document_selections"])
    try:
        assembled, selected = submission._assemble_draft(draft, packet, root=root)
    except (KeyError, TypeError, ValueError):
        assembled, selected = None, []
    reviewed = draft if assembled is None else assembled
    citation = submission._citation_review(reviewed, packet, token)
    source = submission._source_evidence_review(root, reviewed, packet, token)
    monetary = submission._monetary_review(root, assembled, packet, selected)
    directory = submission._directory(root, task["invocation_id"])
    for number in (1, 2):
        path = directory / f"{number}.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            continue
        value = {"binding": {"version": version, "identity": packet["identity"],
                             "packet_hash": canonical_hash(packet)}, "draft": draft}
        if version == submission.SHORT_RECEIPT_VERSION:
            value["submission_ref"] = f"r{number}.{secrets.token_urlsafe(18)}"
        value["content_hash"] = legacy_envelope_hash(value, hash_field="content_hash")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        result = {"status": "DRAFT_STORED_NOT_VALIDATED", "submission": number,
                  "content_hash": value["content_hash"],
                  "final_message": value.get("submission_ref") or json.dumps({
                      "submission": number, "content_hash": value["content_hash"]}),
                  "citation_review": citation, "source_evidence_review": source,
                  "monetary_review": monetary}
        # 只保留供历史辅助检查断言读取的合成事件，不写真实 MCP 事件流。
        event = {"tool": "research_report.submit", "invocation_id": task["invocation_id"],
                 "submission": number, "output_hash": value["content_hash"],
                 "review_hash": canonical_hash({"citation_review": citation,
                     "monetary_review": monetary, "source_evidence_review": source}),
                 "citation_pair_count": citation["pair_count"],
                 "monetary_finding_count": monetary.get("finding_count", 0),
                 "source_review_pair_count": source["pair_count"]}
        tools.events.append({**event, "event_hash": canonical_hash(event)})
        return result
    raise ValueError("RESEARCH_SUBMISSION_LIMIT_EXHAUSTED")


def read_historical_report_fixture(run, task, receipt, *, attempt=1):
    """历史回执及正式业务对象的只读检查，不生成 Hook/执行证明。"""
    from product.runtime.codex_hook_recorder import _read_multidimensional_report_artifact
    packet = submission._packet(run, task["invocation_id"])
    if packet["task"]["submission_version"] not in {
        submission.VERSION, submission.FORMAL_VERSION, submission.SHORT_RECEIPT_VERSION,
    }:
        raise AssertionError("历史向量读取不支持当前执行协议")
    record = {"identity_binding": {"status": "BOUND"}, "trusted_task_binding": packet["identity"]}
    resolved = submission.resolve(run, {"last_assistant_message": receipt}, record, attempt)
    invocation = json.loads((run / task["invocation_path"]).read_text())
    report, evidence, selected = _read_multidimensional_report_artifact(
        json.loads(resolved["last_assistant_message"]), record, task=task,
        invocation=invocation, reference_packet=packet, run_dir=run,
    )
    return report, evidence, selected, record


def store_historical_report_fixture(run, task, receipt):
    """仅构造临时历史报告/接受记录供旧读取器测试；不是当前 writer。"""
    from product.council.multidimensional_output import persist_dimension_report
    report, evidence, selected, record = read_historical_report_fixture(run, task, receipt)
    binding = record["submission_binding"]
    packet = submission._packet(run, task["invocation_id"])
    directory = submission._directory(run, task["invocation_id"], create=False)
    stored = json.loads((directory / f"{binding['submission']}.json").read_text())
    marker = {"version": binding["version"], "invocation_id": task["invocation_id"],
              "report_id": report["report_id"], "report_hash": report["report_hash"],
              "source_gate_hash": json.loads((run / "evidence/gate.json").read_text())["bundle_hash"],
              "submission": binding["submission"], "submission_content_hash": binding["content_hash"],
              "upstream_calculation_selections": record.get("upstream_calculation_selections", [])}
    if binding["version"] == submission.SHORT_RECEIPT_VERSION:
        marker["submission_ref"] = stored["submission_ref"]
    if binding["version"] in submission.FORMAL_VERSIONS:
        marker["relation_reference_binding"] = submission._v4_reference_binding(packet)
        submission._verify_v4_saved_statements(stored["draft"], report, marker["relation_reference_binding"])
    marker["marker_hash"] = canonical_hash(marker)
    path = directory / "accepted.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(marker, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    output_dir = run / "research/reports" / canonical_hash({"task_id": task["task_id"]})[:16]
    output = persist_dimension_report(output_dir, report=report, evidence=evidence,
                                      selected_upstream_calculations=selected)
    return report, output, path
