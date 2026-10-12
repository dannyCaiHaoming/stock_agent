"""将明确选择的原生准备回执交给既有同行数据物化器；不编造执行事件。"""
from pathlib import Path

from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.research import _private_root, _read_json, _write_json
from product.tools.report_submission import read_submission
from product.tools.material_inputs import freeze_material_inputs, validate_material_inputs






def materialize_peer_selection(tools, *, draft_ref, output_dir, source_access_path,
                               cache_root, sec_user_agent, memory_root=None,
                               collector=None, peer_supplement_collector=None, now=None):
    task, gate = tools._authorize()
    if task["capability"] != "PEER_SELECTION":
        raise ValueError("NATIVE_MATERIAL_PEER_SELECTION_REQUIRED")
    report = read_submission(tools, draft_ref=draft_ref)
    if report["research"]["status"] not in {"READY", "SOURCE_LIMITED"}:
        raise ValueError("NATIVE_MATERIAL_PEER_SELECTION_NOT_READY")
    # This is a new data-only input, not a fabricated old LLM preparation run.
    root = _private_root(Path(output_dir), create=True)
    (root/"inputs/research").mkdir(parents=True, mode=0o700)
    (root/"inputs/evidence").mkdir(mode=0o700)
    manifest = {
        "schema_version": "native-peer-materialization-input/1.0.0",
        "run_id": task["task_id"], "source_report_id": report["report_id"],
        "source_report_hash": report["report_hash"], "caller_authentication": "UNVERIFIED",
        "outputs": [{"preparation_kind": "PEER_SELECTION", "security_id": task["security"]["security_id"],
                     "selections": report["research"]["selections"]}],
    }
    manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
    _write_json(root/"inputs/research/material-preparation-manifest.json", manifest)
    _write_json(root/"inputs/research/peer-candidate-pool.json", task["peer_candidate_pool"])
    _write_json(root/"inputs/evidence/gate.json", gate)
    from product.tools.peer_materialization import materialize_selected_peers
    options = {} if now is None else {"now": now}
    result = materialize_selected_peers(root/"inputs", source_access_path=source_access_path,
        cache_root=cache_root, sec_user_agent=sec_user_agent, output_dir=root/"data",
        collector=collector, peer_supplement_collector=peer_supplement_collector,
        memory_root=memory_root, **options)
    return {"source_report_hash": report["report_hash"], "materialization": result,
            "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED"}
