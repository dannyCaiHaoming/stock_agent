"""原生宿主使用的受限研究 MCP；处理业务与最小绑定观察，不启动模型。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from product.runtime.schema_validation import validate_schema_instance
from product.tools.research import ResearchTools
from product.tools.research_connection import ResearchConnection, ResearchConnectionFile, ROLE_PREFIXES


def routed_tool_manifest():
    result = tool_manifest()
    for item in result:
        schema = item["inputSchema"]
        schema["properties"].update({
            "task_ref": {"type": "string", "pattern": r"^t\.[0-9a-f]{24}$"},
            "task_token": {"type": "string", "minLength": 32},
        })
        schema["required"] = ["task_ref", "task_token", *schema["required"]]
        item["description"] += " 请求/角色连接内必须使用本任务精确task_ref和任务能力凭据；它们不证明宿主作者身份。"
    return result


def tool_manifest() -> tuple[dict[str, Any], ...]:
    def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {
            "name": name, "description": description,
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
            "inputSchema": {"type": "object", "additionalProperties": False,
                            "properties": properties, "required": required},
        }
    ids = {"type": "array", "minItems": 1, "maxItems": 64,
           "uniqueItems": True, "items": {"type": "string", "minLength": 1}}
    return (
        tool("research_context", "读取任务权限与完整输出契约；事实ID只返回有界页及总数/next_evidence_offset，需继续时显式翻页或用catalog；目录不是事实查询，不证明宿主作者身份。", {
            "evidence_offset": {"type": "integer", "minimum": 0},
            "evidence_limit": {"type": "integer", "minimum": 1, "maximum": 64},
        }, []),
        tool("research_catalog", "分页发现本任务允许资料的来源/字段/期间；目录不是事实查询，不含其他任务。", {
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 64},
        }, []),
        tool("research_query", "按精确ID读取任务允许的冻结事实，最多64项、响应65536 UTF-8字节；大响应或显式offset/limit按选中顺序返回完整事实页及total/offset/next_offset，需继续时以同一ID列表和next_offset显式翻页，末页为null。仅返回事实计作已查询；单事实超限拒绝，不截断、跳过事实或自动翻页；每页先验全部选中ID。禁止传run、agent、task身份或任意路径。", {
            "evidence_ids": ids,
            "offset": {"type": "integer", "minimum": 0, "maximum": 63},
            "limit": {"type": "integer", "minimum": 1, "maximum": 64},
        }, ["evidence_ids"]),
        tool("research_calculate", "只对当前允许事实执行既有受限运算；SEC结构化amount仅支持同证券/accession/taxonomy/单位/期间的ratio及USD monetary_scale，结构化percent_change未实现；不接受任意对象、表达式或自填操作数，成功结果再经research_calculations取得短引用。", {
            "operation": {"enum": ["ratio", "percent_change", "institutional_period_change", "monetary_scale"]},
            "evidence_ids": {**ids, "maxItems": 2},
            "target_scale": {"enum": ["one", "thousand", "million", "billion", "万", "亿"]},
        }, ["operation", "evidence_ids"]),
        tool("research_calculations", "读取本任务真实成功计算的精确k引用/数值/单位/方法，不执行新运算；大型目录按offset/limit及next_offset显式翻页，每页65536 UTF-8字节。长血缘只返回数量/hash；用calculation_ref及evidence_offset/evidence_limit按next_evidence_offset读取完整输入ID页，ID目录不是原始事实query。目录页参数与精确引用模式不可混用；五个可选参数的null等同省略，另一模式的参数可用null，不自动选择或翻页。", {
            "offset": {"type": ["integer", "null"], "minimum": 0},
            "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 64},
            "calculation_ref": {"type": ["string", "null"], "pattern": r"^k\.[0-9a-f]{12}\.[0-9a-f]{24}$"},
            "evidence_offset": {"type": ["integer", "null"], "minimum": 0},
            "evidence_limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 64},
        }, []),
        {**tool("research_submit", "提交本任务语义草稿并得到精确回执；最多首稿加一次原作者精确补丁，不填身份/hash。保存有效不代表宿主或内容通过。", {
            "draft": {"type": "object"},
        }, ["draft"]), "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
        tool("research_read_submission", "按精确有效回执读取本任务报告；小报告原格式，大型或显式offset/limit返回有界canonical JSON片段，每页65536 UTF-8字节。offset/total按Unicode字符计，limit默认及最大8192；用同一draft_ref按next_offset显式继续并拼接report_json_fragment，payload_hash绑定完整序列化，原report_hash不改。片段不是完整报告，未读末页不得声明完整回读，不自动翻页，不读别任务。", {
            "draft_ref": {"type": "string", "pattern": r"^r[12]\.[A-Za-z0-9_-]{24}$"},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 8192},
        }, ["draft_ref"]),
        tool("research_read_documents", "读取本任务冻结且已验证正文；目录不等于已读，超出响应上限明确拒绝，不截断正文。", {
            "document_ids": {**ids, "maxItems": 5},
        }, ["document_ids"]),
        tool("research_read_reports", "当前任务按已批准目录读取完整依赖报告并记录实际读取；目录不等于已消费。独立Skeptic首轮禁止。", {
            "report_ids": {"type": "array", "minItems": 1, "uniqueItems": True,
                           "items": {"type": "string", "minLength": 1}},
        }, ["report_ids"]),
        {**tool("research_search", "只用于明确授权的资料准备任务；按既有来源政策与有限预算搜索，结果仅LEAD_ONLY，正式研究禁止。", {
            "query": {"type": "string", "minLength": 1, "maxLength": 240},
        }, ["query"]), "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}},
        {**tool("research_fetch", "只取得本任务实际搜索观察到的候选正文；缺凭证/来源失败保留，不接受URL或其他任务候选。", {
            "candidate_id": {"type": "string", "minLength": 1},
        }, ["candidate_id"]), "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}},
    )


METHODS = {
    "research_context": "context", "research_catalog": "catalog",
    "research_query": "query", "research_calculate": "calculate",
    "research_calculations": "calculations", "research_submit": "submit",
    "research_read_submission": "read_submission_page", "research_read_reports": "read_reports",
    "research_read_documents": "read_documents",
    "research_search": "search", "research_fetch": "fetch",
}


def connection_context_tool_manifest():
    return {"name": "research_connection_context",
            "description": "仅获准主线程核对当前连接绑定；expected_connection_hash来自本次确定性准备，不是凭据。只返回绑定hash/角色与观察时点，不含研究资料或秘密，无写入；不认证caller、模型、作者或隔离，不替代业务任务授权。错绑定停止，不换hash重试。",
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
            "inputSchema": {"type": "object", "additionalProperties": False,
                "required": ["expected_connection_hash"],
                "properties": {"expected_connection_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"}}}}


def preparation_tool_manifest(*, single_stock_entry=False):
    grant = {"type": "object", "additionalProperties": False,
             "required": ["role", "task_ref", "task_token", "draft_ref"],
             "properties": {"role": {"type": "string"}, "task_ref": {"type": "string", "pattern": r"^t\.[0-9a-f]{24}$"},
                            "task_token": {"type": "string", "minLength": 32}, "draft_ref": {"type": "string", "pattern": r"^r[12]\.[A-Za-z0-9_-]{24}$"}}}
    result = {"name": "research_prepare_task",
            "description": "仅主线程/操作方使用当前私有角色连接准备业务任务；连接授权由服务端校验，不向模型暴露连接凭据；专业Agent不得使用，不派发模型。依赖只传已授予精确回执，不抄报告元数据。",
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            "inputSchema": {"type": "object", "additionalProperties": False,
                "required": ["security_id", "capability"],
                "properties": {"security_id": {"type": "string", "minLength": 1},
                    "capability": {"type": "string", "minLength": 1},
                    "benchmark_id": {"type": ["string", "null"]},
                    "dependency_grants": {"type": "array", "items": grant}}}}
    if single_stock_entry:
        result["inputSchema"]["properties"].update({
            "expected_request_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
            "expected_gate_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        })
    return result


def single_stock_preparation_tool_manifest():
    return {"name": "research_prepare_single_stock",
            "description": "仅Company服务的主线程单股入口；用户只给代码时主动尝试。需要业务授权时返回精确research_authorize_single_stock原生用户审批操作，不让用户执行CLI，不接受模型批准。批准后自动接回既有身份解析、采集、冻结及Company连接，成功后按next_tool调用research_prepare_task；专业Agent禁止使用。私有路径、来源配置和凭据只由服务端读取，缺少可信宿主/本地配置则明确停止。",
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
            "inputSchema": {"type": "object", "additionalProperties": False,
                "required": ["symbol"], "properties": {
                    "symbol": {"type": "string", "minLength": 1, "maxLength": 15},
                    "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "cutoff": {"type": "string", "minLength": 1},
                }}}


def company_entry_tool_manifest():
    # Company角色业务清单不变；工具发现不等于资料/任务授权。
    from product.tools.single_stock_approval import native_approval_tool_manifest
    return [*routed_tool_manifest(), connection_context_tool_manifest(), preparation_tool_manifest(single_stock_entry=True),
            single_stock_preparation_tool_manifest(), native_approval_tool_manifest()]


def _rejected_result(exc):
    # No payload, private path, credential or financial content in errors.
    code = str(exc).split(":", 1)[0]
    if not code or not all(c.isupper() or c.isdigit() or c == "_" for c in code):
        code = "NATIVE_RESEARCH_REQUEST_REJECTED"
    return {"content": [{"type": "text", "text": code}], "isError": True}


def dispatch(tools: ResearchTools | ResearchConnection | ResearchConnectionFile,
             message: dict[str, Any], *, approval=None) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ValueError("NATIVE_RESEARCH_RPC_INVALID")
    identifier, method = message.get("id"), message.get("method")
    if not isinstance(message.get("params", {}), dict):
        raise ValueError("NATIVE_RESEARCH_RPC_INVALID")
    if identifier is None:
        return None
    company_entry = isinstance(tools, ResearchConnectionFile) and tools.prefix == "STOCK_AGENT_COMPANY"
    if company_entry and method == "tools/list":
        tools.discovery_context()
        return {"jsonrpc": "2.0", "id": identifier, "result": {"tools": company_entry_tool_manifest()}}
    if (company_entry and method == "tools/call"
            and message.get("params", {}).get("name") in {"research_prepare_single_stock", "research_authorize_single_stock"}):
        try:
            from product.tools.single_stock_approval import CONFIG_KEY, native_approval_tool_manifest
            from product.tools.single_stock_preparation import KEY, prepare_single_stock_from_file
            from product.tools.research import _read_json
            name = message["params"]["name"]
            arguments = message["params"].get("arguments", {})
            manifest = native_approval_tool_manifest() if name == "research_authorize_single_stock" else single_stock_preparation_tool_manifest()
            validate_schema_instance(arguments, manifest["inputSchema"])
            if name == "research_authorize_single_stock":
                if approval is None:
                    raise ValueError("NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED")
                value = approval.approve_and_prepare(tools, **arguments)
            elif approval is not None and (CONFIG_KEY in (values := _read_json(tools.path)) or KEY not in values):
                value = approval.offer(tools, **arguments)
            else:
                value = prepare_single_stock_from_file(tools, **arguments)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}],
                      "isError": False}
        except (ValueError, TypeError, KeyError, OSError, ImportError) as exc:
            result = _rejected_result(exc)
        return {"jsonrpc": "2.0", "id": identifier, "result": result}
    if isinstance(tools, ResearchConnectionFile) and method in {"tools/list", "tools/call"}:
        try:
            tools = tools.connection()
        except (ValueError, TypeError, KeyError, OSError) as exc:
            if method != "tools/call":
                raise
            return {"jsonrpc": "2.0", "id": identifier, "result": _rejected_result(exc)}
    if method == "initialize":
        if approval is not None:
            approval.initialize(message.get("params", {}))
        result = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "stock-agent-research", "version": "1.0.0"}}
    elif method == "tools/list":
        context = tools.context()
        if isinstance(tools, ResearchConnection):
            role = context["role"]
            permissions = {"calculate", "read_reports", "read_documents", "search", "fetch"} if role in {"runtime_company_analyst", "runtime_market_catalyst"} else {"read_reports"} if role == "runtime_cio" else set()
            manifest = routed_tool_manifest()
        else:
            permissions = set(context["permissions"])
            manifest = tool_manifest()
        result = {"tools": [item for item in manifest
                            if (item["name"] != "research_calculate" or "calculate" in permissions)
                            and (item["name"] != "research_calculations" or {"calculate", "calculation_catalog"} & permissions)
                            and (item["name"] != "research_read_reports" or "read_reports" in permissions)
                            and (item["name"] != "research_read_documents" or "read_documents" in permissions)
                            and (item["name"] != "research_search" or "search" in permissions)
                            and (item["name"] != "research_fetch" or "fetch" in permissions)]}
        if isinstance(tools, ResearchConnection):
            result["tools"].append(connection_context_tool_manifest())
            result["tools"].append(preparation_tool_manifest())
    elif method == "tools/call":
        params = message.get("params", {})
        name, arguments = params.get("name"), params.get("arguments", {})
        if name == "research_prepare_task" and isinstance(tools, ResearchConnection):
            schema = preparation_tool_manifest(single_stock_entry=company_entry)["inputSchema"]
            try:
                validate_schema_instance(arguments, schema)
                arguments = dict(arguments)
                expected_request = arguments.pop("expected_request_hash", None)
                expected_gate = arguments.pop("expected_gate_hash", None)
                if expected_request is not None or expected_gate is not None:
                    context = tools.context()
                    if expected_request != context["request_hash"] or expected_gate != context["gate_hash"]:
                        raise ValueError("NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
                value = tools.prepare_authorized_task(**arguments)
                value["task"] = tools.task_tools(task_ref=value["task_ref"], task_token=value["task_token"]).context()
                return {"jsonrpc": "2.0", "id": identifier, "result": {
                    "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}], "isError": False}}
            except (ValueError, KeyError, TypeError, OSError):
                return {"jsonrpc": "2.0", "id": identifier, "result": {
                    "content": [{"type": "text", "text": "NATIVE_RESEARCH_PREPARATION_REJECTED"}], "isError": True}}
        manifest = routed_tool_manifest() if isinstance(tools, ResearchConnection) else tool_manifest()
        observing = name == "research_connection_context" and isinstance(tools, ResearchConnection)
        schema = (connection_context_tool_manifest()["inputSchema"] if observing else
                  next((item["inputSchema"] for item in manifest if item["name"] == name), None))
        try:
            if schema is None:
                raise ValueError("NATIVE_RESEARCH_TOOL_UNSUPPORTED")
            validate_schema_instance(arguments, schema)
            if observing:
                value = tools.binding_context(**arguments)
            else:
                selected = tools
                if isinstance(tools, ResearchConnection):
                    arguments = dict(arguments)
                    selected = tools.task_tools(task_ref=arguments.pop("task_ref"), task_token=arguments.pop("task_token"))
                if name == "research_calculations":
                    arguments = {key: value for key, value in arguments.items() if value is not None}
                value = getattr(selected, METHODS[name])(**arguments)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}],
                      "isError": False}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            result = _rejected_result(exc)
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="受限研究MCP；不调用模型或管理宿主会话。")
    binding = parser.add_mutually_exclusive_group(required=True)
    binding.add_argument("--task-root")
    binding.add_argument("--connection-root")
    prefixes = tuple(ROLE_PREFIXES.values())
    binding.add_argument("--task-env-prefix", choices=prefixes)
    binding.add_argument("--connection-env-prefix", choices=prefixes)
    parser.add_argument("--connection-env-file", help="稳定仓库外私有JSON；每次调用重读所选角色绑定，不注入全局环境。")
    args = parser.parse_args()
    if args.connection_env_file is not None and not args.connection_env_prefix:
        parser.error("--connection-env-file requires --connection-env-prefix")
    from pathlib import Path
    routed = bool(args.connection_root or args.connection_env_prefix)
    prefix = args.connection_env_prefix or args.task_env_prefix or "STOCK_AGENT_RESEARCH"
    root = args.connection_root or args.task_root or os.environ.get(prefix + ("_CONNECTION" if routed else "_TASK"))
    token = os.environ.get(prefix + "_TOKEN")
    try:
        if args.connection_env_file is not None:
            tools = ResearchConnectionFile(Path(args.connection_env_file), prefix=prefix)
            context = tools.discovery_context()
        else:
            if not root:
                sys.stderr.write("NATIVE_RESEARCH_TASK_ENV_REQUIRED\n")
                return 2
            tools = (ResearchConnection(Path(root), connection_token=token) if routed
                     else ResearchTools(Path(root), access_token=token))
            context = tools.context()
        if (args.task_env_prefix or args.connection_env_prefix) and ROLE_PREFIXES.get(context["role"]) != prefix:
            raise ValueError("NATIVE_RESEARCH_ROLE_BINDING_INVALID")
    except (ValueError, OSError, KeyError, TypeError):
        sys.stderr.write("NATIVE_RESEARCH_CONNECTION_REJECTED\n")
        return 2
    from product.tools.single_stock_approval import NativeSingleStockApproval
    approval = NativeSingleStockApproval()
    for line in sys.stdin:
        message = None
        try:
            if len(line.encode("utf-8")) > 1024 * 1024:
                raise ValueError("NATIVE_RESEARCH_RPC_TOO_LARGE")
            message = json.loads(line)
            response = dispatch(tools, message, approval=approval)
        except (ValueError, TypeError, KeyError, OSError):
            response = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                        "error": {"code": -32600, "message": "Research request rejected"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
