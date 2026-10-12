"""主线程单股准备的薄接线；复用原采集/冻结，不授予模型操作方权限。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import secrets

from product.mcp.live.collection import validate_live_collection_configuration
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.single_stock_input import normalize_single_stock_intent, validate_single_stock_request
from product.tools.research import ResearchAccessError, _private_root, _read_json, _utc_now, _write_json, validate_gate
from product.tools.research_connection import (
    ResearchConnection, ResearchConnectionFile, ROLE_PREFIXES, prepare_connection,
    _bind_connection_values, _check_previous_connection, _connection_expiry,
    _connection_file_path, _locked_connection_file, _replace_connection_file,
)

KEY = "STOCK_AGENT_COMPANY_PREPARATION"
PREFIX = "STOCK_AGENT_COMPANY"


def _private_path(value, *, file=False):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_PRIVATE_PATH_INVALID")
    path = Path(value)
    root = _private_root(path.parent if file else path)
    if file and (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077):
        raise ResearchAccessError("NATIVE_RESEARCH_FILE_PERMISSIONS_INVALID")
    return root / path.name if file else root


def _validate_preparation(grant, *, ticker, intent=None, values=None):
    if (not isinstance(grant, dict) or grant.get("ticker") != ticker
            or not isinstance(grant.get("authorization_id"), str)
            or re.fullmatch(r"p\.[0-9a-f]{24}", grant["authorization_id"]) is None
            or type(grant.get("used")) is not bool
            or grant.get("authorization_hash") != canonical_hash({k: v for k, v in grant.items()
                if k not in {"authorization_hash", "used"}})):
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_AUTHORIZATION_INVALID")
    if grant["used"]:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_PREPARATION_ALREADY_ATTEMPTED")
    if values is not None and "approval_config_hash" in grant:
        if canonical_hash(values.get("STOCK_AGENT_COMPANY_APPROVAL_CONFIG")) != grant["approval_config_hash"]:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_CHANGED")
    if intent is not None and "research_scope" in grant:
        scope = {key: intent[key] for key in ("ticker", "research_question", "cutoff_mode", "requested_cutoff")}
        if grant["research_scope"] != scope:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_MISMATCH")
    if _connection_expiry(grant["expires_at"]) <= parse_timestamp(_utc_now()):
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_AUTHORIZATION_EXPIRED")
    for name in ("output_root", "memory_root", "cache_root"):
        _private_path(grant[name])
    access_path = _private_path(grant["source_access_path"], file=True)
    access = validate_live_collection_configuration(access_path, at=_utc_now())
    if canonical_hash(access) != grant["source_access_hash"]:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_SOURCE_AUTHORIZATION_CHANGED")
    contact = grant["sec_user_agent"]
    if not isinstance(contact, str) or "@" not in contact or any(ord(c) < 32 for c in contact):
        raise ResearchAccessError("SEC_CONTACT_REQUIRED")


def authorize_single_stock_preparation(path: Path, *, symbol: str, source_access_path: Path,
        output_root: Path, memory_root: Path, cache_root: Path, sec_user_agent: str,
        expires_at: str, expected_connection_hash: str | None = None,
        research_scope=None, expected_environment_hash: str | None = None,
        expected_source_access_hash: str | None = None, approval_config_hash: str | None = None):
    """操作方CLI批准一次限定证券准备及Company换绑；不取数、不返回秘密。"""
    path = _connection_file_path(path)
    intent = normalize_single_stock_intent(symbol, at=_utc_now())
    stamp = _utc_now()
    grant = {
        "source_id": "native-single-stock-preparation:" + intent["ticker"],
        "as_of": stamp, "retrieved_at": stamp,
        "authorization_id": "p." + secrets.token_hex(12), "ticker": intent["ticker"],
        "source_access_path": str(source_access_path),
        "source_access_hash": canonical_hash(validate_live_collection_configuration(
            _private_path(str(source_access_path), file=True), at=stamp)),
        "output_root": str(output_root), "memory_root": str(memory_root), "cache_root": str(cache_root),
        "sec_user_agent": sec_user_agent, "expires_at": expires_at,
        "expected_connection_hash": expected_connection_hash, "used": False,
    }
    if approval_config_hash is not None:
        grant["approval_config_hash"] = approval_config_hash
    if expected_source_access_hash is not None and grant["source_access_hash"] != expected_source_access_hash:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_SOURCE_AUTHORIZATION_CHANGED")
    if research_scope is not None:
        checked = normalize_single_stock_intent(symbol, question=research_scope["research_question"], at=stamp)
        if research_scope != {key: checked[key] for key in ("ticker", "research_question", "cutoff_mode", "requested_cutoff")}:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_MISMATCH")
        grant["research_scope"] = copy.deepcopy(research_scope)
        intent = checked
    grant["authorization_hash"] = canonical_hash({k: v for k, v in grant.items() if k != "used"})
    _validate_preparation(grant, ticker=intent["ticker"], intent=intent)
    with _locked_connection_file(path) as values:
        if expected_environment_hash is not None and canonical_hash(values) != expected_environment_hash:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_APPROVAL_SCOPE_CHANGED")
        binding_keys = {p + suffix for p in ROLE_PREFIXES.values() for suffix in ("_CONNECTION", "_TOKEN")}
        if values and not (binding_keys | {KEY, "STOCK_AGENT_COMPANY_APPROVAL_CONFIG"}).intersection(values):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
        _check_previous_connection(values, prefix=PREFIX, expected_connection_hash=expected_connection_hash)
        values[KEY] = grant
        _replace_connection_file(path, values)
    return {"source_id": grant["source_id"], "as_of": stamp, "retrieved_at": stamp,
            "status": "AUTHORIZED_NOT_COLLECTED", "ticker": intent["ticker"],
            "expires_at": expires_at, "max_preparation_attempts": 1, "model_calls": 0}


def _authorization_required(intent, code):
    stamp = _utc_now()
    return {
        "source_id": "native-single-stock-preparation:" + intent["ticker"],
        "as_of": stamp, "retrieved_at": stamp, "status": "AUTHORIZATION_REQUIRED",
        "ticker": intent["ticker"], "reason": code, "model_calls": 0,
        "authorization_action": {
            "user_message": "本请求需要Claude Code原生逐次用户审批；请使用已接好本地审批配置的受支持宿主。"
                "若宿主无法提供真人审批则停止，不以聊天确认代替，不要求你执行CLI或提供私有配置/凭据。",
            "required_host": "Claude Code >= 2.1.214，须兑现anthropic/requiresUserInteraction完整审批契约；自定义SDK自动批准不受支持。",
            "resume": "由主线程使用research_prepare_single_stock取得精确原生审批操作；通过后自动继续。",
        },
    }


def prepare_single_stock_from_file(service: ResearchConnectionFile, *, symbol, question=None, cutoff="latest"):
    """主线程仅给证券与问题；本地操作方授权不进入MCP参数或结果。"""
    if service.prefix != PREFIX:
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_MAIN_THREAD_TOOL_REQUIRED")
    intent = normalize_single_stock_intent(symbol, question=question, cutoff=cutoff, at=_utc_now())
    if intent["cutoff_mode"] != "LATEST":
        raise ResearchAccessError("SINGLE_STOCK_HISTORICAL_FROZEN_INPUT_REQUIRED")
    with _locked_connection_file(service.path) as values:
        grant = values.get(KEY)
        if grant is None:
            return _authorization_required(intent, "NATIVE_SINGLE_STOCK_AUTHORIZATION_REQUIRED")
        try:
            _validate_preparation(grant, ticker=intent["ticker"], intent=intent, values=values)
            _check_previous_connection(values, prefix=PREFIX,
                                       expected_connection_hash=grant["expected_connection_hash"])
        except (ValueError, TypeError, KeyError, OSError) as exc:
            code = str(exc).split(":", 1)[0]
            if not code or not all(c.isupper() or c.isdigit() or c == "_" for c in code):
                code = "NATIVE_SINGLE_STOCK_AUTHORIZATION_INVALID"
            return _authorization_required(intent, code)
        grant = copy.deepcopy(grant)
        grant["used"] = True
        values[KEY] = grant
        _replace_connection_file(service.path, values)
    # 先原子占用一次尝试；失败保留原采集证据，不重试、不回收额度。
    root = _private_root(Path(grant["output_root"]) / grant["authorization_id"], create=True)
    from product.runtime.common_stock_data import collect_single_stock_research_data, validate_common_stock_source_bundle
    result = collect_single_stock_research_data(intent["ticker"], question=intent["research_question"],
        cutoff="latest", access_path=Path(grant["source_access_path"]), output_dir=root / "data",
        sec_user_agent=grant["sec_user_agent"], run_id=grant["authorization_id"],
        repository_root=Path(__file__).resolve().parents[2], memory_root=Path(grant["memory_root"]),
        cache_root=Path(grant["cache_root"]), benchmark_id=None, benchmark_ticker=None)
    if result.get("status") != "FROZEN":
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_DATA_NOT_FROZEN")
    # 只读本次确定性生成的固定产物；不接受模型路径或旧资料兜底。
    def read(name):
        path = root / "data" / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
        return json.loads(path.read_text(encoding="utf-8"))
    request, gate, preparation = read("single-stock-request.json"), read("gate.json"), read("data-preparation.json")
    validate_single_stock_request(request)
    validate_gate(gate)
    validate_common_stock_source_bundle(request, gate=gate, preparation=preparation,
                                        source_bundle_path=root / "data/source-bundle.json")
    if (request["security"]["ticker"] != intent["ticker"]
            or request["research_question"] != intent["research_question"]
            or request["resolved_cutoff"] != gate["decision_cutoff"]):
        raise ResearchAccessError("NATIVE_SINGLE_STOCK_FROZEN_REQUEST_MISMATCH")
    with _locked_connection_file(service.path) as values:
        if values.get(KEY) != grant:
            raise ResearchAccessError("NATIVE_SINGLE_STOCK_AUTHORIZATION_CHANGED")
        checked = {**grant, "used": False}
        _validate_preparation(checked, ticker=intent["ticker"], intent=intent, values=values)
        _check_previous_connection(values, prefix=PREFIX,
                                   expected_connection_hash=grant["expected_connection_hash"])
        prepared = prepare_connection(root / "company", research_input=request, gate=gate,
                                      role="runtime_company_analyst")
        _write_json(root / "company/operator-grant.json", prepared)
        connection = ResearchConnection(root / "company", connection_token=prepared["connection_token"])
        binding = _bind_connection_values(service.path, values, connection, expires_at=grant["expires_at"],
                                          expected_connection_hash=grant["expected_connection_hash"])
        _replace_connection_file(service.path, values)
    return {
        "source_id": "native-single-stock-preparation:" + intent["ticker"],
        "as_of": request["resolved_cutoff"], "retrieved_at": _utc_now(),
        "status": "FROZEN_COMPANY_BOUND", "model_calls": 0,
        "security": request["security"], "research_question": request["research_question"],
        "request_hash": canonical_hash(request), "gate_hash": gate["bundle_hash"],
        "decision_cutoff": gate["decision_cutoff"], "connection_hash": binding["connection_hash"],
        "next_tool": {"name": "research_prepare_task", "arguments": {
            "security_id": request["security"]["security_id"], "capability": "COMPANY_RESEARCH",
            "expected_request_hash": canonical_hash(request), "expected_gate_hash": gate["bundle_hash"],
        }},
        "research_started": False, "caller_authentication": "UNVERIFIED",
    }
