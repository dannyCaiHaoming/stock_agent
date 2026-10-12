"""现有研究边界的两种明确输入；不转换或伪造 PortfolioHandoff。"""
import json
from pathlib import Path

from product.runtime.single_stock_input import INPUT_KIND
from product.tools.research_input import (
    is_single_stock, validate_research_input, research_subjects, research_input_ref,
    research_input_binding, artifact_input_binding,
)




















def single_stock_contract_locks(product_root):
    """显式新输入分支的批准版本及实际文件；不迁移旧 Schema。"""
    from product.runtime.hashing import file_hash
    from product.runtime.versioning import CURRENT_SCHEMA_FILES, load_version_manifest, validate_current_component_versions
    product = Path(product_root)
    manifest = load_version_manifest(product / "version-manifest.json")
    names = tuple(name for name in CURRENT_SCHEMA_FILES if name.startswith("single-stock."))
    validate_current_component_versions(product, manifest, skill_names=(), schema_names=names,
        adapter_scopes=(), check_risk=False)
    return {name: {"version": manifest["schemas"][name], "path": CURRENT_SCHEMA_FILES[name],
        "content_hash": file_hash(product / CURRENT_SCHEMA_FILES[name])} for name in names}


def load_research_input(run_dir, *, manifest=None):
    """按记录中的模式读原件，不能因文件缺失静默回退成另一种输入。"""
    root = Path(run_dir)
    if manifest is None:
        manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    single = manifest.get("input_kind") == INPUT_KIND
    if manifest.get("input_kind") not in (None, "PORTFOLIO_HANDOFF", INPUT_KIND):
        raise ValueError("RESEARCH_INPUT_KIND_UNKNOWN")
    path = root / ("audit/single-stock-request.json" if single else "audit/portfolio-handoff.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_research_input(value)
    if is_single_stock(value) != single:
        raise ValueError("RESEARCH_INPUT_KIND_MISMATCH")
    expected = research_input_binding(value)
    if any(manifest.get(key) != item for key, item in expected.items() if key != "handoff_id"):
        raise ValueError("RESEARCH_INPUT_MANIFEST_BINDING_MISMATCH")
    if single and any(key in manifest for key in ("handoff_id", "handoff_hash", "portfolio_hash")):
        raise ValueError("RESEARCH_INPUT_PORTFOLIO_IMPERSONATION")
    return value
