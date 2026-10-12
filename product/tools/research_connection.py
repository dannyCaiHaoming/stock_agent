"""请求/角色限定的业务任务路由；不派发Agent或管理宿主任务状态。"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping

from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.tools.research import (
    ROLES, ResearchAccessError, ResearchTools, _private_root, _read_json,
    _write_json, _utc_now, prepare_task, validate_gate,
)
from product.tools.research_input import is_single_stock, is_fixture, research_input_binding, validate_research_input


def _validate_request(original, request):
    if is_single_stock(original) or is_fixture(original):
        validate_research_input(request)
        if request != original:
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_REQUEST_MISMATCH")
    else:
        from product.council.intake_planning import validate_council_request
        validate_council_request(request, handoff=original)


VERSION = "native-research-connection/1.0.0"
TASK_REF = re.compile(r"t\.[0-9a-f]{24}")
ROLE_PREFIXES = {"runtime_company_analyst": "STOCK_AGENT_COMPANY",
                 "runtime_market_catalyst": "STOCK_AGENT_MARKET",
                 "runtime_skeptic": "STOCK_AGENT_SKEPTIC", "runtime_cio": "STOCK_AGENT_CIO"}


def _connection_file_path(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_PATH_INVALID")
    return _private_root(path.parent) / path.name


def _connection_expiry(value: str):
    try:
        if not isinstance(value, str):
            raise ValueError
        return parse_timestamp(value)
    except (ValueError, TypeError, AttributeError):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPIRY_INVALID") from None


class ResearchConnectionFile:
    """稳定角色接入点；每次RPC取得一个完整私有绑定快照，不缓存旧请求。"""

    def __init__(self, path: Path, *, prefix: str):
        if prefix not in ROLE_PREFIXES.values():
            raise ResearchAccessError("NATIVE_RESEARCH_ROLE_BINDING_INVALID")
        self.path = _connection_file_path(path)
        self.prefix = prefix

    def discovery_context(self) -> dict[str, Any]:
        """Company 可在仅有私有准备授权、尚无冻结连接时发现主线程入口。"""
        values = _read_json(_connection_file_path(self.path))
        if (self.prefix == "STOCK_AGENT_COMPANY"
                and not {self.prefix + "_CONNECTION", self.prefix + "_TOKEN"}.intersection(values)):
            if values and not {"STOCK_AGENT_COMPANY_PREPARATION", "STOCK_AGENT_COMPANY_APPROVAL_CONFIG"}.intersection(values):
                raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
            return {"role": "runtime_company_analyst"}
        return self.connection().context()

    def connection(self) -> ResearchConnection:
        path = _connection_file_path(self.path)
        values = _read_json(path)
        expiry_key = self.prefix + "_EXPIRES_AT"
        if expiry_key in values:
            if _connection_expiry(values[expiry_key]) <= parse_timestamp(_utc_now()):
                raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPIRED")
        root, token = values.get(self.prefix + "_CONNECTION"), values.get(self.prefix + "_TOKEN")
        if (not isinstance(root, str) or not Path(root).is_absolute()
                or not isinstance(token, str) or len(token) < 32):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
        connection = ResearchConnection(Path(root), connection_token=token)
        context = connection.context()
        if ROLE_PREFIXES.get(context["role"]) != self.prefix:
            raise ResearchAccessError("NATIVE_RESEARCH_ROLE_BINDING_INVALID")
        return connection


def _connection_values(path: Path) -> dict[str, Any]:
    _connection_file_path(path)
    return _read_json(path) if path.exists() or path.is_symlink() else {}


@contextmanager
def _locked_connection_file(path: Path):
    path = _connection_file_path(path)
    _connection_values(path)
    fd = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise ResearchAccessError("NATIVE_RESEARCH_FILE_PERMISSIONS_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_BUSY") from None
        yield _connection_values(path)
    finally:
        os.close(fd)


def _replace_connection_file(path: Path, values: dict[str, Any]) -> None:
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(12))
    try:
        _write_json(temporary, values)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _check_previous_connection(values, *, prefix, expected_connection_hash):
    if expected_connection_hash is not None and (not isinstance(expected_connection_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_connection_hash) is None):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
    root_key, token_key = prefix + "_CONNECTION", prefix + "_TOKEN"
    if root_key in values or token_key in values:
        root, token = values.get(root_key), values.get(token_key)
        if (not isinstance(root, str) or not Path(root).is_absolute() or not isinstance(token, str)):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
        previous = ResearchConnection(Path(root), connection_token=token).context()
        if (ROLE_PREFIXES.get(previous["role"]) != prefix
                or previous["connection_hash"] != expected_connection_hash):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
    elif expected_connection_hash is not None:
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")


def _bind_connection_values(path, values, connection, *, expires_at, expected_connection_hash):
    if path.is_relative_to(connection.root):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_MUST_BE_OUTSIDE_BINDING")
    context = connection.context()
    prefix = ROLE_PREFIXES[context["role"]]
    stamp = _utc_now()
    if _connection_expiry(expires_at) <= parse_timestamp(stamp):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPIRED")
    binding_keys = {p + suffix for p in ROLE_PREFIXES.values() for suffix in ("_CONNECTION", "_TOKEN")}
    if values and not (binding_keys | {"STOCK_AGENT_COMPANY_PREPARATION", "STOCK_AGENT_COMPANY_APPROVAL_CONFIG"}).intersection(values):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_INVALID")
    _check_previous_connection(values, prefix=prefix, expected_connection_hash=expected_connection_hash)
    values.update({prefix + "_CONNECTION": str(connection.root), prefix + "_TOKEN": connection.connection_token,
                   prefix + "_EXPIRES_AT": expires_at})
    return {"source_id": "native-research-connection-binding:" + context["role"],
            "as_of": stamp, "retrieved_at": stamp, "role": context["role"],
            "connection_hash": context["connection_hash"], "expires_at": expires_at,
            "status": "BOUND_NOT_RESEARCHED", "model_calls": 0}


def bind_connection_file(path: Path, connection: ResearchConnection, *, expires_at: str,
                         expected_connection_hash: str | None = None) -> dict[str, Any]:
    """操作方显式换绑；原连接/任务不改，原子更新必要角色，不写MCP配置。"""
    path = _connection_file_path(path)
    if path.is_relative_to(connection.root):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_FILE_MUST_BE_OUTSIDE_BINDING")
    connection.context()
    if _connection_expiry(expires_at) <= parse_timestamp(_utc_now()):
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPIRED")
    with _locked_connection_file(path) as values:
        result = _bind_connection_values(path, values, connection, expires_at=expires_at,
                                         expected_connection_hash=expected_connection_hash)
        _replace_connection_file(path, values)
    return result


def prepare_connection(root: Path, *, research_input: Mapping[str, Any],
                       gate: Mapping[str, Any], role: str,
                       research_request: Mapping[str, Any] | None = None,
                       dependency_connections: Mapping[str, str] | None = None,
                       public_research_authorized: bool = False,
                       peer_candidate_pool: Mapping[str, Any] | None = None,
                       peer_materialization: Mapping[str, Any] | None = None,
                       material_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validate_research_input(research_input)
    request = research_request if research_request is not None else research_input if is_single_stock(research_input) or is_fixture(research_input) else None
    if request is None:
        raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_REQUEST_REQUIRED")
    _validate_request(research_input, request)
    validate_gate(gate)
    if role not in set(ROLES.values()):
        raise ResearchAccessError("NATIVE_RESEARCH_ROLE_UNSUPPORTED")
    if research_input.get("resolved_cutoff", gate["decision_cutoff"]) != gate["decision_cutoff"]:
        raise ResearchAccessError("NATIVE_RESEARCH_CUTOFF_MISMATCH")
    sources = dict(dependency_connections or {})
    if role == "runtime_skeptic" and sources:
        raise ResearchAccessError("CONTEXT_ISOLATION_VIOLATION")
    for source_role, source_root in sources.items():
        if source_role not in set(ROLES.values()):
            raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_ROLE_INVALID")
        source_root = _private_root(Path(source_root))
        source = _read_json(source_root / "connection.json")
        if (source["role"] != source_role or source["input_hash"] != canonical_hash(research_input)
                or source["gate_hash"] != gate["bundle_hash"] or source["request_hash"] != canonical_hash(request)):
            raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_CONNECTION_INVALID")
        sources[source_role] = str(source_root)
    if type(public_research_authorized) is not bool:
        raise ResearchAccessError("NATIVE_MATERIAL_SOURCE_AUTHORIZATION_INVALID")
    if role == "runtime_skeptic" and (public_research_authorized or peer_candidate_pool is not None):
        raise ResearchAccessError("CONTEXT_ISOLATION_VIOLATION")
    if material_inputs is not None:
        if role == "runtime_skeptic":
            raise ResearchAccessError("CONTEXT_ISOLATION_VIOLATION")
        from product.tools.material_inputs import validate_material_inputs
        validate_material_inputs(material_inputs, research_input=research_input, gate=gate)
    if peer_candidate_pool is not None:
        from product.mcp.live.peer_candidates import validate_peer_candidate_pool
        validate_peer_candidate_pool(peer_candidate_pool)
    stamp = _utc_now()
    connection = {
        "schema_version": VERSION, "role": role,
        "input_binding": research_input_binding(research_input),
        "input_hash": canonical_hash(research_input), "gate_hash": gate["bundle_hash"],
        "request_hash": canonical_hash(request), "research_question": request["research_question"],
        "decision_cutoff": gate["decision_cutoff"], "dependency_connections": sources,
        "preparation_inputs": {"public_research_authorized": public_research_authorized,
                               "peer_candidate_pool": copy.deepcopy(peer_candidate_pool),
                               "peer_materialization": copy.deepcopy(peer_materialization),
                               "material_inputs": copy.deepcopy(material_inputs)},
        "caller_authentication": "UNVERIFIED",
        "source_id": "native-research-connection:"+role, "as_of": gate["decision_cutoff"], "retrieved_at": stamp,
    }
    connection["connection_hash"] = canonical_hash(connection)
    token = secrets.token_urlsafe(32)
    path = _private_root(root, create=True)
    _write_json(path/"connection.json", connection)
    _write_json(path/"access.json", {"connection_hash": connection["connection_hash"], "token": token})
    _write_json(path/"input.json", research_input)
    _write_json(path/"request.json", request)
    _write_json(path/"gate.json", gate)
    return {"connection": connection, "connection_token": token}


class ResearchConnection:
    def __init__(self, root: Path, *, connection_token: str | None = None):
        self.root = _private_root(root)
        self.connection_token = connection_token

    def _authorize(self):
        access = _read_json(self.root/"access.json")
        expected = access.get("token")
        if (not isinstance(expected, str) or len(expected) < 32
                or not isinstance(self.connection_token, str)
                or not secrets.compare_digest(expected.encode(), self.connection_token.encode())):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_ACCESS_INVALID")
        connection = _read_json(self.root/"connection.json")
        digest = canonical_hash({k: v for k, v in connection.items() if k != "connection_hash"})
        if (connection.get("schema_version") != VERSION or digest != connection.get("connection_hash")
                or digest != access.get("connection_hash")):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_BINDING_INVALID")
        original, gate = _read_json(self.root/"input.json"), _read_json(self.root/"gate.json")
        validate_research_input(original)
        request = _read_json(self.root/"request.json")
        _validate_request(original, request)
        validate_gate(gate)
        if (canonical_hash(request) != connection["request_hash"]
                or request["research_question"] != connection["research_question"]
                or canonical_hash(original) != connection["input_hash"]
                or research_input_binding(original) != connection["input_binding"]
                or gate["bundle_hash"] != connection["gate_hash"]
                or gate["decision_cutoff"] != connection["decision_cutoff"]):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_SOURCE_INVALID")
        return connection, original, gate

    def context(self):
        connection, _original, _gate = self._authorize()
        result = copy.deepcopy(connection)
        result.pop("dependency_connections", None)
        result.pop("preparation_inputs", None)
        return result

    def binding_context(self, *, expected_connection_hash: str) -> dict[str, Any]:
        _private_root(self.root)
        connection = self.context()
        if (not isinstance(expected_connection_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_connection_hash) is None
                or expected_connection_hash != connection["connection_hash"]):
            raise ResearchAccessError("NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
        result = {name: connection[name] for name in (
            "role", "connection_hash", "request_hash", "input_hash", "gate_hash", "decision_cutoff",
        )}
        stamp = _utc_now()
        return {**result, "source_id": "native-research-connection-observation:"+connection["role"],
                "as_of": stamp, "retrieved_at": stamp, "caller_authentication": "UNVERIFIED"}

    def task_tools(self, *, task_ref: str, task_token: str) -> ResearchTools:
        connection, _original, _gate = self._authorize()
        if not isinstance(task_ref, str) or TASK_REF.fullmatch(task_ref) is None:
            raise ResearchAccessError("NATIVE_RESEARCH_TASK_REF_INVALID")
        directory = self.root/"tasks"/task_ref
        if any(path.is_symlink() for path in (self.root/"tasks", directory)):
            raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
        tools = ResearchTools(directory, access_token=task_token)
        task, _gate = tools._authorize()
        if (task.get("connection_binding") != {"connection_hash": connection["connection_hash"], "request_hash": connection["request_hash"]}
                or task["role"] != connection["role"] or task["input_hash"] != connection["input_hash"]
                or task["input_binding"] != connection["input_binding"]
                or task["gate_hash"] != connection["gate_hash"]
                or task["research_question"] != connection["research_question"]
                or task["decision_cutoff"] != connection["decision_cutoff"]):
            raise ResearchAccessError("NATIVE_RESEARCH_TASK_CONNECTION_MISMATCH")
        return tools

    def prepare_authorized_task(self, *, dependency_grants=(), **arguments):
        connection, _, _ = self._authorize()
        reports = []
        for grant in dependency_grants:
            source_root = str(self.root) if grant["role"] == connection["role"] else connection.get("dependency_connections", {}).get(grant["role"])
            if source_root is None:
                raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_CONNECTION_NOT_ALLOWED")
            source_path = _private_root(Path(source_root))
            access = _read_json(source_path / "access.json")
            source = ResearchConnection(source_path, connection_token=access["token"])
            bound = source.context()
            if (bound["request_hash"] != connection["request_hash"] or bound["gate_hash"] != connection["gate_hash"]
                    or bound["input_hash"] != connection["input_hash"] or bound["role"] != grant["role"]):
                raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_CONNECTION_INVALID")
            tools = source.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
            reports.append(tools.read_submission(draft_ref=grant["draft_ref"]))
        from product.tools.material_contracts import MATERIAL_ROLES, DISCOVERY_KINDS
        from product.tools.documents import preparation_documents
        preparation = connection.get("preparation_inputs", {})
        if arguments["capability"] in DISCOVERY_KINDS:
            arguments["public_research_authorized"] = preparation.get("public_research_authorized", False)
        if arguments["capability"] == "PEER_SELECTION":
            arguments["peer_candidate_pool"] = preparation.get("peer_candidate_pool")
        if arguments["capability"] in {"INDUSTRY_COMPARISON", "INDEPENDENT_FIRST_PASS", "RESEARCH_SYNTHESIS"}:
            arguments["peer_materialization"] = preparation.get("peer_materialization")
        material_reports = [r for r in reports if r["capability"] in MATERIAL_ROLES]
        documents = preparation_documents(material_reports, capability=arguments["capability"],
            input_binding=connection["input_binding"], gate_hash=connection["gate_hash"],
            security_id=arguments["security_id"], cutoff=connection["decision_cutoff"])
        from product.tools.documents import DOCUMENT_CAPABILITIES
        materials = preparation.get("material_inputs")
        if materials is not None:
            for report in materials["reports"]:
                if (DOCUMENT_CAPABILITIES.get(report["capability"]) == arguments["capability"]
                        and report["security"]["security_id"] == arguments["security_id"]):
                    if report["research"]["status"] == "BLOCKED_CONFIGURATION":
                        raise ResearchAccessError("NATIVE_MATERIAL_DEPENDENCY_BLOCKED_CONFIGURATION")
                    documents.extend(copy.deepcopy((report.get("material_support") or {}).get("documents", [])))
        return self.prepare_task(dependency_reports=[r for r in reports if r["capability"] not in MATERIAL_ROLES],
                                 allowed_documents=documents, **arguments)

    def prepare_task(self, *, security_id: str, capability: str,
                     benchmark_id: str | None = None, research_question: str | None = None,
                     allowed_documents=(), dependency_reports=(),
                     public_research_authorized=False, peer_candidate_pool=None,
                     peer_materialization=None) -> dict[str, Any]:
        """仅操作方确定性准备调用；不在专业Agent工具面开放任务创建。"""
        connection, original, gate = self._authorize()
        if ROLES.get(capability) != connection["role"]:
            raise ResearchAccessError("NATIVE_RESEARCH_CAPABILITY_ROLE_MISMATCH")
        if research_question is not None and research_question != connection["research_question"]:
            raise ResearchAccessError("NATIVE_RESEARCH_TASK_QUESTION_OUTSIDE_REQUEST")
        tasks = self.root/"tasks"
        if tasks.is_symlink():
            raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
        tasks.mkdir(mode=0o700, exist_ok=True)
        task_ref = "t." + secrets.token_hex(12)
        prepared = prepare_task(tasks/task_ref, research_input=original, gate=gate,
            security_id=security_id, capability=capability, benchmark_id=benchmark_id,
            research_question=connection["research_question"], allowed_documents=allowed_documents,
            dependency_reports=dependency_reports, public_research_authorized=public_research_authorized,
            peer_candidate_pool=peer_candidate_pool, peer_materialization=peer_materialization,
            connection_binding={"connection_hash": connection["connection_hash"], "request_hash": connection["request_hash"]})
        return {"task_ref": task_ref, "task_token": prepared["access_token"], "task": prepared["task"]}
