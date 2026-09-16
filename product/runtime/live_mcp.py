"""Live Gate 查询/计算适配：复用既有确定性工具，不暴露采集器。"""
from copy import deepcopy
from pathlib import Path

# 安装后的插件根目录没有外层 product/ 文件夹；只为当前产品包建立同一包名。
# 不改 sys.path，不加载仓库外同名模块；普通仓库 import 不经过此分支。
try:
    import product
except ModuleNotFoundError as exc:
    if exc.name != "product":
        raise
    import importlib.util
    import sys
    product_root = Path(__file__).resolve().parents[1]
    specification = importlib.util.spec_from_file_location("product", product_root / "__init__.py",
                                                          submodule_search_locations=[str(product_root)])
    if specification is None or specification.loader is None:
        raise RuntimeError("LIVE_PRODUCT_PACKAGE_MISSING")
    module = importlib.util.module_from_spec(specification)
    sys.modules["product"] = module
    specification.loader.exec_module(module)

from product.runtime.evidence_gate import run_live_evidence_gate
from product.runtime.fixture_mcp import GateScopedFixtureTools, StatelessFixtureTools, ToolAccessError, _load_object, _tool_manifest

LIVE_MCP_VERSION = "live-gate-scoped/1.0.0"
PERMISSIONS = {"live_evidence.query": "fixture_evidence.query", "live_math.calculate": "fixture_math.calculate"}


class GateScopedLiveTools(GateScopedFixtureTools):
    """服务绑定层传入冻结快照与 invocation；Agent 只见 query/calculate。"""
    adapter_version = LIVE_MCP_VERSION

    def __init__(self, snapshot, gate_artifact, *, run_id, agent, invocation_id,
                 allowed_tools=("live_evidence.query",), calendar=None):
        if not set(allowed_tools) <= set(PERMISSIONS):
            raise ToolAccessError("UNSUPPORTED_LIVE_TOOL_PERMISSION")
        checked = run_live_evidence_gate(snapshot, run_id=run_id, calendar=calendar).artifact
        if checked != gate_artifact:
            raise ToolAccessError("LIVE_GATE_REVALIDATION_FAILED")
        super().__init__(deepcopy(checked), run_id=run_id, agent=agent, invocation_id=invocation_id,
                         allowed_tools=[PERMISSIONS[p] for p in allowed_tools])

    @staticmethod
    def tool_manifest():
        import json
        return tuple(json.loads(json.dumps(tool).replace("fixture", "live")) for tool in GateScopedFixtureTools.tool_manifest())

    def _record(self, tool, inputs, output):
        # 基类执行授权、计算与事件 hash；对外名称在写事件之前转换。
        super()._record(tool.replace("fixture_", "live_"), inputs, output)

    def _authorize_evidence(self, run_id, evidence_ids):
        return deepcopy(super()._authorize_evidence(run_id, evidence_ids))


class StatelessLiveTools(StatelessFixtureTools):
    adapter_version = LIVE_MCP_VERSION

    @staticmethod
    def tool_manifest():
        import json
        return tuple(json.loads(json.dumps(tool).replace("fixture", "live")) for tool in _tool_manifest(stateless=True))

    def _bound_tools(self, *, run_dir: str, run_id: str, agent: str, invocation_id: str):
        from product.runtime.live_context import load_live_run_context
        from product.runtime.invocation import verify_invocation_manifest
        from product.mcp.live.contracts import external_path
        from product.runtime.hashing import canonical_hash, file_hash
        if agent not in ("runtime_company_analyst", "runtime_skeptic", "runtime_cio"):
            raise ToolAccessError("LIVE_AGENT_UNKNOWN")
        root = external_path(Path(run_dir))
        run = _load_object(root / "run_manifest.json")
        expected_adapter = run.get("integrity_before", {}).get("files", {}).get("product/runtime/live_mcp.py")
        if expected_adapter != file_hash(Path(__file__).resolve()):
            raise ToolAccessError("LIVE_LOADED_ADAPTER_HASH_MISMATCH")
        invocation = _load_object(root / f"invocations/{agent}.json")
        agent_input = _load_object(root / f"inputs/{agent}.json")
        if (run.get("run_id") != run_id or invocation.get("run_id") != run_id
                or invocation.get("invocation_id") != invocation_id or invocation.get("agent", {}).get("name") != agent):
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")
        portfolio, snapshot, gate, calendar = load_live_run_context(root, run)
        if agent_input.get("security_id") != run["focus_security_id"]:
            raise ToolAccessError("LIVE_INVOCATION_FOCUS_MISMATCH")
        if (agent_input.get("portfolio_hash") != canonical_hash(portfolio)
                or agent_input.get("snapshot_hash") != snapshot["snapshot_hash"]
                or agent_input.get("gate_hash") != gate["bundle_hash"]):
            raise ToolAccessError("LIVE_INVOCATION_INPUT_SOURCE_MISMATCH")
        verify_invocation_manifest(Path(run["discovery"]["product_root"]).parent, invocation, agent_input=agent_input)
        if agent != "runtime_cio" and run.get("authenticity_required", True):
            from product.runtime.invocation import verify_specialist_start_binding
            verify_specialist_start_binding(Path(run["discovery"]["product_root"]).parent, root, agent)
        self.dynamic_event_log = root / "events/mcp/events.jsonl"
        return GateScopedLiveTools(snapshot, gate, run_id=run_id, agent=agent, invocation_id=invocation_id,
                                   allowed_tools=invocation["tool_permissions"], calendar=calendar)


def main():
    from product.runtime.fixture_mcp import serve_stdio
    return serve_stdio(tools_override=StatelessLiveTools())


if __name__ == "__main__":
    raise SystemExit(main())
