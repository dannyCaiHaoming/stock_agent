"""显式业务任务准备入口；不启动宿主、模型或Agent。"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

from product.tools.research import _private_root, _read_json, _utc_now, _write_json
from product.tools.research_connection import prepare_connection, ResearchConnection, bind_connection_file


def agent_grant(grant):
    """只机械提取当前任务能力；业务正文仍由受限工具交付。"""
    task = grant["task"]
    return {"source_id": "native-agent-grant:" + grant["task_ref"],
            "as_of": task["decision_cutoff"], "retrieved_at": _utc_now(),
            "task_ref": grant["task_ref"], "task_token": grant["task_token"],
            "role": task["role"], "capability": task["capability"],
            "security_id": task["security"]["security_id"],
            "decision_cutoff": task["decision_cutoff"], "task_hash": task["task_hash"]}


def _validate_grant_outputs(paths):
    seen = set()
    for path in paths:
        if not path.is_absolute():
            raise ValueError("NATIVE_AGENT_GRANT_PATH_MUST_BE_ABSOLUTE")
        parent = _private_root(path.parent)
        target = parent / path.name
        if target in seen or target.exists() or target.is_symlink():
            raise ValueError("NATIVE_AGENT_GRANT_OUTPUT_EXISTS_OR_DUPLICATED")
        seen.add(target)


def main():
    parser=argparse.ArgumentParser(description="准备已授权业务连接/任务；输出私有授权文件，不执行研究。")
    commands=parser.add_subparsers(dest="command",required=True)
    fixture = commands.add_parser("fixture")
    fixture.add_argument("--source", type=Path, required=True)
    fixture.add_argument("--question", required=True)
    fixture.add_argument("--output-dir", type=Path, required=True)
    connection=commands.add_parser("connection")
    connection.add_argument("--input",type=Path,required=True)
    connection.add_argument("--gate",type=Path,required=True)
    connection.add_argument("--request",type=Path)
    connection.add_argument("--role",choices=["runtime_company_analyst","runtime_market_catalyst","runtime_skeptic","runtime_cio"],required=True)
    connection.add_argument("--root",type=Path,required=True)
    connection.add_argument("--public-research-authorized", action="store_true")
    connection.add_argument("--peer-candidate-pool", type=Path)
    connection.add_argument("--peer-materialization", type=Path)
    connection.add_argument("--dependency-connections", type=Path)
    connection.add_argument("--material-inputs", type=Path)
    authorization = commands.add_parser("authorize-single-stock", help="操作方批准一次单股资料准备及Company换绑；不取数或启动模型")
    authorization.add_argument("--symbol", required=True)
    authorization.add_argument("--connection-env-file", type=Path, required=True)
    authorization.add_argument("--source-access", type=Path, required=True)
    authorization.add_argument("--output-root", type=Path, required=True)
    authorization.add_argument("--memory-root", type=Path, required=True)
    authorization.add_argument("--cache-root", type=Path, required=True)
    authorization.add_argument("--expires-at", required=True)
    authorization.add_argument("--expected-connection-hash", help="已有Company绑定时必须提供原精确connection_hash")
    binding=commands.add_parser("bind", help="操作方将已准备连接绑定到稳定私有接入文件；不改MCP配置或启动服务")
    binding.add_argument("--connection-root",type=Path,required=True)
    binding.add_argument("--connection-access",type=Path,required=True)
    binding.add_argument("--connection-env-file",type=Path,required=True)
    binding.add_argument("--expires-at",required=True,help="本次角色任务授权的带时区截止时间；不是资料cutoff")
    binding.add_argument("--expected-connection-hash",help="替换已绑定角色时必须提供原精确connection_hash")
    task=commands.add_parser("task")
    task.add_argument("--connection-root",type=Path,required=True)
    task.add_argument("--connection-access",type=Path,required=True)
    task.add_argument("--security-id",required=True)
    task.add_argument("--capability",required=True)
    task.add_argument("--benchmark-id")
    task.add_argument("--dependency-grants", type=Path)
    task.add_argument("--grant-output",type=Path,required=True)
    task.add_argument("--agent-grant-output",type=Path,help="另写小型私有任务授权；不含完整task或连接凭据。")
    archive=commands.add_parser("archive", help="操作方按精确任务授权和有效提交回执归档；零模型，不覆盖旧导出")
    archive.add_argument("--connection-root",type=Path,required=True)
    archive.add_argument("--connection-access",type=Path,required=True)
    archive.add_argument("--task-grant",type=Path,required=True)
    archive.add_argument("--draft-ref",required=True)
    archive.add_argument("--memory-root",type=Path,required=True)
    archive.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    if args.command == "authorize-single-stock":
        from product.tools.single_stock_preparation import authorize_single_stock_preparation
        try:
            result = authorize_single_stock_preparation(args.connection_env_file, symbol=args.symbol,
                source_access_path=args.source_access, output_root=args.output_root, memory_root=args.memory_root,
                cache_root=args.cache_root, sec_user_agent=os.environ.get("SEC_USER_AGENT", ""),
                expires_at=args.expires_at, expected_connection_hash=args.expected_connection_hash)
        except (ValueError, TypeError, KeyError, OSError):
            sys.stderr.write("NATIVE_SINGLE_STOCK_AUTHORIZATION_REJECTED\n")
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "bind":
        try:
            access = _read_json(args.connection_access)
            connection = ResearchConnection(args.connection_root, connection_token=access["connection_token"])
            result = bind_connection_file(args.connection_env_file, connection, expires_at=args.expires_at,
                                          expected_connection_hash=args.expected_connection_hash)
        except (ValueError, TypeError, KeyError, OSError):
            sys.stderr.write("NATIVE_RESEARCH_CONNECTION_BINDING_REJECTED\n")
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "archive":
        from product.tools.report_history import export_report
        access = _read_json(args.connection_access)
        grant = _read_json(args.task_grant)
        connection = ResearchConnection(args.connection_root, connection_token=access["connection_token"])
        tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        result = export_report(tools, draft_ref=args.draft_ref, memory_root=args.memory_root,
                               output_dir=args.output_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "fixture":
        from product.tools.fixture_input import prepare_fixture_request
        from product.tools.research import _private_root
        result = prepare_fixture_request(args.source, research_question=args.question)
        root = _private_root(args.output_dir, create=True)
        _write_json(root/"preparation.json", result)
        if "input" in result:
            _write_json(root/"input.json", result["input"])
            _write_json(root/"gate.json", result["gate"])
        print(json.dumps({"status": result["status"], "input_kind": "FIXTURE_COUNCIL", "model_calls": 0}, ensure_ascii=False))
        return 0
    if args.command=="connection":
        original=json.loads(args.input.read_text(encoding="utf-8"))
        gate=json.loads(args.gate.read_text(encoding="utf-8"))
        request=json.loads(args.request.read_text(encoding="utf-8")) if args.request else None
        options = {name: json.loads(getattr(args, name).read_text(encoding="utf-8")) if getattr(args, name) else None
                   for name in ("peer_candidate_pool", "peer_materialization", "dependency_connections", "material_inputs")}
        result=prepare_connection(args.root,research_input=original,gate=gate,role=args.role,research_request=request,
                                  public_research_authorized=args.public_research_authorized, **options)
        _write_json(args.root/"operator-grant.json",result)
        print(json.dumps({"status":"PREPARED_NOT_RESEARCHED","role":args.role,"model_calls":0},ensure_ascii=False))
    else:
        if args.agent_grant_output is not None:
            _validate_grant_outputs((args.grant_output, args.agent_grant_output))
        access=_read_json(args.connection_access)
        connection=ResearchConnection(args.connection_root,connection_token=access["connection_token"])
        from product.mcp.research import preparation_tool_manifest
        from product.runtime.schema_validation import validate_schema_instance
        dependencies = _read_json(args.dependency_grants)["dependency_grants"] if args.dependency_grants else []
        arguments = {"security_id": args.security_id,
                     "capability": args.capability, "benchmark_id": args.benchmark_id,
                     "dependency_grants": dependencies}
        validate_schema_instance(arguments, preparation_tool_manifest()["inputSchema"])
        result=connection.prepare_authorized_task(**arguments)
        _write_json(args.grant_output,result)
        if args.agent_grant_output is not None:
            _write_json(args.agent_grant_output, agent_grant(result))
        print(json.dumps({"status":"TASK_PREPARED_NOT_RESEARCHED","task_ref":result["task_ref"],"model_calls":0},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
