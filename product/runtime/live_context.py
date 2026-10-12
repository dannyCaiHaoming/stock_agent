"""运行包内 live 输入绑定与底层重验；不访问 Provider、不执行模型。"""
import hashlib
import json
from pathlib import Path

from product.mcp.live.contracts import external_path, validate_contract
from product.mcp.live.identity import verify_frozen_identity
from product.mcp.provenance import content_hash
from product.runtime.hashing import file_hash
from product.tools.raw_records import validate_raw_records

LIVE_AUDIT_FILES = ("audit/live/portfolio.json", "audit/live/snapshot.json", "audit/live/calendar.json", "evidence/gate.json")




def live_artifact_hashes(run_dir: Path) -> dict:
    return {name: file_hash(run_dir / name) for name in LIVE_AUDIT_FILES}


def live_resource_hashes(repository_root: Path) -> dict:
    """live 增量资源单独锁定，不改变历史 fixture Capsule 的完整性算法。"""
    roots = [repository_root / "product/mcp/live", repository_root / "product/profiles"]
    paths = [p for root in roots for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths.extend([repository_root / "requirements-live-macos-py313.lock", repository_root / "pyproject.toml"])
    paths.append(repository_root / "evals/grading/live-us-equity-rubric-v1.json")
    paths.append(repository_root / "docs/data/personal-research-approval.json")
    paths.extend((repository_root / "product/schemas/runtime").glob("live-*.schema.json"))
    if any(p.is_symlink() or not p.resolve().is_relative_to(repository_root.resolve()) for p in paths):
        raise ValueError("LIVE_RESOURCE_PATH_ESCAPE")
    return {p.relative_to(repository_root).as_posix(): file_hash(p) for p in sorted(paths)}


def source_topology_lock(snapshot: dict) -> dict:
    """从冻结内容重算来源锁，不相信摘要 PASS 或手填所选来源。"""
    validate_contract("snapshot", snapshot)
    if snapshot["schema_version"] not in ("live-snapshot/3.0.0", "live-snapshot/4.0.0"):
        return {"schema_version": snapshot["schema_version"], "scope": "LEGACY_OFFLINE_ONLY"}
    from product.mcp.live.source_routing import policy_lock
    if snapshot.get("identity"):
        identity = snapshot["identity"]
        by_hash = {content_hash(m): m for m in identity["security_metadata"]}
        by_security = {b["security_id"]: by_hash[b["security_metadata_hash"]]
                       for b in identity["binding"]["bindings"]}
        for selection in snapshot["source_selections"]:
            expected_source = {"yahoo": "yahoo-chart-identity", "eastmoney": "eastmoney-kline-identity"}.get(selection["selected_provider"])
            if (selection["security_id"] not in by_security or
                    by_security[selection["security_id"]].get("quote_identity", {}).get("source_id") != expected_source):
                raise ValueError("LIVE_SELECTED_IDENTITY_SOURCE_MISMATCH")
    recorded_policies = {json.dumps(selection["routing_policy"], sort_keys=True)
                         for selection in snapshot["source_selections"]}
    if len(recorded_policies) > 1:
        raise ValueError("LIVE_ROUTING_POLICY_MIXED")
    recorded_policy = (json.loads(next(iter(recorded_policies)))
                       if recorded_policies else policy_lock())
    value = {"schema_version": snapshot["schema_version"], "routing_policy": recorded_policy,
             "universe_hash": snapshot["universe"]["snapshot_hash"],
             "source_access_hash": content_hash(snapshot["source_access"]),
             "selections": {s["security_id"]: {"selection_hash": s["selection_hash"],
                 "selected_provider": s["selected_provider"], "attempts": s["attempts"],
                 "raw_hashes": s["raw_hashes"], "evidence_ids": s["evidence_ids"]}
                 for s in snapshot["source_selections"]}}
    return dict(value, lock_hash=content_hash(value))


def load_live_run_context(run_dir: Path, manifest: dict) -> tuple:
    """按固定路径读取并重算 Gate；不能通过改一个 PASSED 字段放行。"""
    from product.mcp.live.market import load_locked_calendar
    from product.runtime.evidence_gate import run_live_evidence_gate
    from product.runtime.runtime_profiles import LIVE_PROFILE_ID
    root = external_path(run_dir)
    if (manifest.get("source_mode") != "live" or manifest.get("runtime_profile") != LIVE_PROFILE_ID
            or "fixture" in manifest or "fixture_id" in manifest
            or Path(manifest["output_dir"]).resolve() != root):
        raise ValueError("LIVE_RUN_SOURCE_INVALID")
    hashes = live_artifact_hashes(root)
    context = manifest.get("source_context", {})
    product_root = Path(manifest.get("discovery", {}).get("product_root", "")).resolve()
    if product_root.name != "product":
        raise ValueError("LIVE_DISCOVERY_ROOT_INVALID")
    if context.get("resource_hashes") != live_resource_hashes(product_root.parent):
        raise ValueError("LIVE_RUN_RESOURCE_LOCK_DRIFT")
    if hashes != context.get("artifact_hashes"):
        raise ValueError("LIVE_RUN_SOURCE_HASH_MISMATCH")
    for name in LIVE_AUDIT_FILES:
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError("LIVE_RUN_SOURCE_PATH_ESCAPE")
    portfolio, snapshot, calendar_record, gate = [json.loads((root / name).read_text(encoding="utf-8")) for name in LIVE_AUDIT_FILES]
    validate_contract("portfolio", portfolio)
    validate_contract("snapshot", snapshot)
    if manifest.get("authenticity_required") and snapshot["schema_version"] != "live-snapshot/4.0.0":
        raise ValueError("LIVE_CURRENT_SNAPSHOT_REQUIRED")
    if context.get("topology_lock") != source_topology_lock(snapshot):
        raise ValueError("LIVE_RUN_TOPOLOGY_LOCK_MISMATCH")
    from product.runtime.discovery import discover_product_resources
    expected = discover_product_resources(product_root.parent, source_profile="live-us-equity")
    if manifest.get("discovery") != expected.to_dict():
        raise ValueError("LIVE_RUN_DISCOVERY_LOCK_DRIFT")
    if any(manifest.get(key) != expected.version_manifest[key]
           for key in ("model", "runtime_profile", "codex_runtime", "candidate_version")):
        raise ValueError("LIVE_RUN_VERSION_LOCK_MISMATCH")
    if snapshot["schema_version"] in ("live-snapshot/3.0.0", "live-snapshot/4.0.0") and (
            {s["security_id"] for s in snapshot["source_selections"]} != {p["security_id"] for p in portfolio["positions"]}):
        raise ValueError("LIVE_ROUTING_PORTFOLIO_COVERAGE_MISMATCH")
    if snapshot["portfolio_hash"] != content_hash(portfolio) or context.get("snapshot_hash") != snapshot["snapshot_hash"]:
        raise ValueError("LIVE_RUN_PORTFOLIO_BINDING_MISMATCH")
    if manifest["decision_cutoff"] != snapshot["decision_cutoff"]:
        raise ValueError("LIVE_RUN_CUTOFF_MISMATCH")
    if manifest.get("focus_security_id") not in {p["security_id"] for p in portfolio["positions"]}:
        raise ValueError("LIVE_RUN_FOCUS_INVALID")
    if snapshot.get("identity") is not None:
        verify_frozen_identity(portfolio, snapshot["identity"], cutoff=snapshot["decision_cutoff"])
        if manifest.get("authenticity_required"):
            from product.mcp.live.security_metadata import METADATA_VERSION, EASTMONEY_METADATA_VERSION
            versions = (METADATA_VERSION, EASTMONEY_METADATA_VERSION) if snapshot["schema_version"] in ("live-snapshot/3.0.0", "live-snapshot/4.0.0") else (METADATA_VERSION,)
            if any(item.get("metadata_version") not in versions for item in snapshot["identity"]["security_metadata"]):
                raise ValueError("LIVE_REAL_IDENTITY_PROOF_REQUIRED")
    def read_object(digest):
        path = root / "audit/live/objects" / digest
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("LIVE_RAW_OBJECT_PATH_ESCAPE")
        return path.read_bytes()
    validate_raw_records(snapshot, read_object)
    calendar = load_locked_calendar(calendar_record)
    if gate != run_live_evidence_gate(snapshot, run_id=manifest["run_id"], calendar=calendar).artifact:
        raise ValueError("LIVE_RUN_GATE_MISMATCH")
    return portfolio, snapshot, gate, calendar
