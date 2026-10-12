"""资料准备回执到正式冻结输入的纯业务绑定；不包含采集或宿主控制。"""
from product.runtime.hashing import canonical_hash
from product.tools.research import _read_json
from product.tools.report_submission import read_submission

def freeze_material_inputs(prepared_submissions, *, final_gate):
    """读取实际准备回执，把已选择正文接入正式共同截止点；不运行模型或来源。"""
    from product.tools.material_contracts import MATERIAL_ROLES
    from product.tools.research import validate_gate
    from product.tools.research_input import is_single_stock, research_input_binding
    from product.runtime.single_stock_input import freeze_latest_research_request
    validate_gate(final_gate)
    reports, original, source_gate = [], None, None
    for tools, draft_ref in prepared_submissions:
        task, gate = tools._authorize()
        if task["capability"] not in MATERIAL_ROLES:
            raise ValueError("NATIVE_MATERIAL_PREPARATION_REQUIRED")
        source = _read_json(tools.root/"input.json")
        if original is not None and (original != source or source_gate != gate):
            raise ValueError("NATIVE_MATERIAL_PREPARATION_SOURCE_MISMATCH")
        original, source_gate = source, gate
        reports.append(read_submission(tools, draft_ref=draft_ref))
    if not reports:
        raise ValueError("NATIVE_MATERIAL_PREPARATION_REQUIRED")
    final_input = freeze_latest_research_request(original, resolved_cutoff=final_gate["decision_cutoff"]) if is_single_stock(original) else original
    bundle = {"source_input": original, "source_gate": source_gate, "reports": reports,
              "input": final_input, "input_binding": research_input_binding(final_input), "gate_hash": final_gate["bundle_hash"]}
    bundle["bundle_hash"] = canonical_hash(bundle)
    validate_material_inputs(bundle, research_input=final_input, gate=final_gate)
    return bundle


def validate_material_inputs(bundle, *, research_input, gate):
    from product.mcp.provenance import parse_timestamp
    from product.tools.research import validate_gate
    from product.tools.research_input import is_single_stock, research_input_binding
    from product.tools.report_reading import validate_report
    from product.tools.material_contracts import MATERIAL_ROLES
    from product.tools.documents import freeze_documents
    from product.runtime.single_stock_input import freeze_latest_research_request
    if bundle.get("bundle_hash") != canonical_hash({k: v for k, v in bundle.items() if k != "bundle_hash"}):
        raise ValueError("NATIVE_MATERIAL_INPUT_HASH_INVALID")
    original, old_gate = bundle["source_input"], bundle["source_gate"]
    validate_gate(old_gate)
    validate_gate(gate)
    expected = freeze_latest_research_request(original, resolved_cutoff=gate["decision_cutoff"]) if is_single_stock(original) else original
    if (bundle["input"] != expected or dict(research_input) != expected
            or bundle["input_binding"] != research_input_binding(expected) or bundle["gate_hash"] != gate["bundle_hash"]
            or parse_timestamp(gate["decision_cutoff"]) < parse_timestamp(old_gate["decision_cutoff"])):
        raise ValueError("NATIVE_MATERIAL_INPUT_BINDING_INVALID")
    facts = {f["evidence_id"]: f for f in gate["allowed_evidence"]}
    if any(facts.get(f["evidence_id"]) != f for f in old_gate["allowed_evidence"]):
        raise ValueError("NATIVE_MATERIAL_INPUT_EVIDENCE_DRIFT")
    identities = set()
    for report in bundle["reports"]:
        validate_report(report, input_binding=research_input_binding(original), gate_hash=old_gate["bundle_hash"],
                        security_id=report["security"]["security_id"], cutoff=old_gate["decision_cutoff"])
        key = (report["security"]["security_id"], report["capability"])
        if report["capability"] not in MATERIAL_ROLES or key in identities:
            raise ValueError("NATIVE_MATERIAL_INPUT_REPORT_AMBIGUOUS")
        identities.add(key)
        freeze_documents((report.get("material_support") or {}).get("documents", []),
                         security_id=report["security"]["security_id"], cutoff=gate["decision_cutoff"])
