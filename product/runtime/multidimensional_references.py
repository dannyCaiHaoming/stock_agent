"""历史任务包加载；纯引用规则由共享业务工具维护。"""
from __future__ import annotations
from typing import Any
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.references import (
    LEGACY_VERSION, VERSION, READ_VERSIONS, CLAIM_REFERENCE_PREFIX,
    EVIDENCE_FIELDS, CLAIM_FIELDS, DOCUMENT_FIELDS, REPORT_FIELDS,
    reference_output_schema, model_claim_targets, scoped_claim_reference,
    parse_scoped_claim_reference, known_claim_references, build_reference_map,
    validate_reference_map, translate_references,
)

def load_reference_packet(run_dir, invocation_id: str, *, include_dependencies: bool = True,
                          index_ref: str | None = None, for_execution: bool = True):
    """Use the same verified packet builder as actual Hook delivery; no side cache."""
    import json
    from pathlib import Path
    from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet

    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH" and (
        index_ref is not None or (run_dir / "research/skeptic/dispatch-index.json").is_file()
    ):
        from product.runtime.independent_skeptic_stage import read_dispatch_index, build_skeptic_dispatch_packet
        index = read_dispatch_index(run_dir, index_ref)
        matches = [t for t in index["tasks"] if t["invocation_id"] == invocation_id]
        if len(matches) > 1:
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_TASK_INVALID")
        if matches:
            return build_skeptic_dispatch_packet(
                Path(__file__).resolve().parents[2], run_dir, matches[0]["task_name"], index_ref=index_ref)
        # 反证前置门禁仍会重验冻结的正向计算；按精确 Invocation 归属读取，
        # 不能因父运行已进入反证阶段而把上游对象误路由到 Skeptic。
    index = json.loads((run_dir / "research/dispatch-index.json").read_text())
    matches = [t for t in index["tasks"] if t["invocation_id"] == invocation_id]
    if len(matches) != 1:
        raise ValueError("MULTIDIMENSIONAL_REFERENCE_TASK_INVALID")
    if manifest.get("stage") == "COMMON_STOCK_RESEARCH":
        from product.runtime.common_stock_stage import build_common_stock_dispatch_packet
        return build_common_stock_dispatch_packet(
            Path(__file__).resolve().parents[2], run_dir, matches[0]["task_name"],
        )
    return build_multidimensional_dispatch_packet(
        Path(__file__).resolve().parents[2], run_dir, matches[0]["task_name"],
        include_dependency_reports=include_dependencies,
        for_execution=for_execution,
    )
