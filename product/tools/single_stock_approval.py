"""Claude Code原生逐次用户审批的本地适配；不接收模型批准或启动Agent。"""
from __future__ import annotations

import copy
from datetime import timedelta
from pathlib import Path
import re
import secrets

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.single_stock_input import normalize_single_stock_intent
from product.tools.research import ResearchAccessError, _read_json, _utc_now
from product.tools.research_connection import ResearchConnection, _check_previous_connection, _connection_file_path
from product.tools.single_stock_preparation import (
    PREFIX, _private_path, authorize_single_stock_preparation, prepare_single_stock_from_file,
)
from product.mcp.live.collection import validate_live_collection_configuration

CONFIG_KEY = "STOCK_AGENT_COMPANY_APPROVAL_CONFIG"


def native_approval_tool_manifest():
    return {
        "name": "research_authorize_single_stock",
        "description": "批准本次单股的一次公开资料准备、冻结/Company换绑，以及一次Company原生研究"
            "（原作者至多一次有限修订），按当前宿主模型且不超过expires_at；不含Market、Skeptic、CIO、Risk或交易。"
            "必须由支持anthropic/requiresUserInteraction的Claude Code向真人逐次展示完整审批；"
            "服务端仅消费本次准备工具给出的精确参数，不接受approved、连接凭据或私有路径。"
            "用户拒绝即停止；批准后自动继续原资料准备，返回next_tool接原Company任务，不要求用户执行CLI。",
        "_meta": {"anthropic/requiresUserInteraction": True},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
        "inputSchema": {
            "type": "object", "additionalProperties": False,
            "required": ["approval_ref", "symbol", "question", "expires_at", "source_budgets"],
            "properties": {
                "approval_ref": {"type": "string", "pattern": r"^a\.[0-9a-f]{32}$"},
                "symbol": {"type": "string", "minLength": 1, "maxLength": 15},
                "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                "expires_at": {"type": "string", "minLength": 1},
                "source_budgets": {"type": "string", "minLength": 1},
            },
        },
    }


def _configuration(service):
    if service.prefix != PREFIX:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_MAIN_THREAD_TOOL_REQUIRED")
    values = _read_json(_connection_file_path(service.path))
    config = values.get(CONFIG_KEY)
    fields = {"source_access_path", "output_root", "memory_root", "cache_root", "sec_user_agent", "authorization_seconds"}
    if not isinstance(config, dict) or set(config) != fields:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_CONFIGURATION_REQUIRED")
    if type(config["authorization_seconds"]) is not int or not 1 <= config["authorization_seconds"] <= 3600:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_CONFIGURATION_INVALID")
    for name in ("output_root", "memory_root", "cache_root"):
        _private_path(config[name])
    policies = validate_live_collection_configuration(_private_path(config["source_access_path"], file=True), at=_utc_now())
    contact = config["sec_user_agent"]
    if not isinstance(contact, str) or "@" not in contact or any(ord(c) < 32 for c in contact):
        raise ResearchAccessError("SEC_CONTACT_REQUIRED")
    expected = None
    if {PREFIX + "_CONNECTION", PREFIX + "_TOKEN"}.intersection(values):
        root, token = values.get(PREFIX + "_CONNECTION"), values.get(PREFIX + "_TOKEN")
        if not isinstance(root, str):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
        expected = ResearchConnection(Path(root), connection_token=token).context()["connection_hash"]
    _check_previous_connection(values, prefix=PREFIX, expected_connection_hash=expected)
    return copy.deepcopy(config), canonical_hash(values), canonical_hash(policies), expected, policies


class NativeSingleStockApproval:
    """仅服务端stdio会话持有待批准快照；ref是关联号，不是用户批准凭据。"""

    def __init__(self):
        self.initialized = False
        self.supported = False
        self.pending = {}

    def initialize(self, params):
        if self.initialized:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SESSION_ALREADY_INITIALIZED")
        self.initialized = True
        info = params.get("clientInfo", {})
        if not isinstance(info, dict):
            return
        version = info.get("version", "")
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version) if isinstance(version, str) else None
        # 官方门禁从2.1.214起支持；未知/旧/自定义SDK客户端不假定能显示真人审批。
        self.supported = (info.get("name") == "claude-code" and match is not None
                          and tuple(map(int, match.groups())) >= (2, 1, 214))

    def offer(self, service, *, symbol, question=None, cutoff="latest"):
        intent = normalize_single_stock_intent(symbol, question=question, cutoff=cutoff, at=_utc_now())
        if intent["cutoff_mode"] != "LATEST":
            raise ResearchAccessError("SINGLE_STOCK_HISTORICAL_FROZEN_INPUT_REQUIRED")
        if not self.supported:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED")
        config, environment_hash, source_hash, expected, policies = _configuration(service)
        expires_at = iso_utc(parse_timestamp(_utc_now()) + timedelta(seconds=config["authorization_seconds"]))
        arguments = {
            "approval_ref": "a." + secrets.token_hex(16), "symbol": intent["ticker"],
            "question": intent["research_question"], "expires_at": expires_at,
            "source_budgets": "; ".join(f"{p['provider']}={p['request_budget']}" for p in sorted(policies, key=lambda p: p["provider"])),
        }
        # 一个活动授权提示；新提示使旧ref失效，不能跨请求或重放续期。
        self.pending = {arguments["approval_ref"]: {
            "arguments": copy.deepcopy(arguments), "service_path": service.path,
            "config": config, "environment_hash": environment_hash, "source_hash": source_hash,
            "expected_connection_hash": expected,
        }}
        stamp = _utc_now()
        return {
            "source_id": "native-single-stock-approval:" + intent["ticker"],
            "as_of": stamp, "retrieved_at": stamp, "status": "AUTHORIZATION_REQUIRED", "model_calls": 0,
            "ticker": intent["ticker"],
            "authorization_action": {
                "user_message": "请在Claude Code完整审批界面确认本次单股资料准备及Company研究；拒绝即停止，无需执行CLI。",
                "tool": {"name": "research_authorize_single_stock", "arguments": arguments},
            },
        }

    def approve_and_prepare(self, service, **arguments):
        if not self.supported or service.prefix != PREFIX:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED")
        pending = self.pending.pop(arguments.get("approval_ref"), None)
        if pending is None or pending["service_path"] != service.path or arguments != pending["arguments"]:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_MISMATCH")
        if parse_timestamp(arguments["expires_at"]) <= parse_timestamp(_utc_now()):
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_AUTHORIZATION_EXPIRED")
        config, environment_hash, source_hash, expected, _ = _configuration(service)
        if (config != pending["config"] or environment_hash != pending["environment_hash"]
                or source_hash != pending["source_hash"] or expected != pending["expected_connection_hash"]):
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_CHANGED")
        scope = {"ticker": arguments["symbol"], "research_question": arguments["question"],
                 "cutoff_mode": "LATEST", "requested_cutoff": None}
        # 调用现有authorize-single-stock逻辑；操作方配置和连接凭据始终留在本地。
        authorize_single_stock_preparation(service.path, symbol=arguments["symbol"],
            source_access_path=config["source_access_path"], output_root=config["output_root"],
            memory_root=config["memory_root"], cache_root=config["cache_root"], sec_user_agent=config["sec_user_agent"],
            expires_at=arguments["expires_at"], expected_connection_hash=expected,
            research_scope=scope, expected_environment_hash=environment_hash,
            expected_source_access_hash=source_hash, approval_config_hash=canonical_hash(config))
        result = prepare_single_stock_from_file(service, symbol=arguments["symbol"], question=arguments["question"])
        if result["status"] != "FROZEN_COMPANY_BOUND":
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_CONTINUATION_REJECTED")
        result["company_authorization"] = {
            "source_id": "native-company-authorization:" + arguments["approval_ref"],
            "as_of": _utc_now(), "retrieved_at": _utc_now(),
            "security_id": result["security"]["security_id"], "capability": "COMPANY_RESEARCH",
            "expires_at": arguments["expires_at"], "max_native_invocations": 1,
            "model": "inherit", "approval_channel": "claude-code-requires-user-interaction",
        }
        return result
