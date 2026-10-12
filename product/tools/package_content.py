"""从精确审阅清单导出原生内容；不安装插件、启动宿主或生成执行器。"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import tomllib
from typing import Mapping

HOSTS = {"codex", "claude-code", "opencode"}
ROLES = ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic")
FORBIDDEN_PARTS = {".private", ".codex-local", ".codex-runtime", "__pycache__", ".claude"}
LEGACY_CONTROLLERS = {"nested_codex.py", "codex_hook_recorder.py"}
PUBLIC_PREPARATION_RESOURCES = frozenset({
    "product/mcp/live/eastmoney-identity-policy.json",
    "product/mcp/live/research-source-policy.json",
    "product/mcp/live/research-supplement-source-plan.json",
    "product/mcp/live/personal-research-approval.json",
    "product/mcp/live/moomoo-opend-quote-manifest.json",
})


def _safe_relative(name: str) -> Path:
    path = Path(name)
    fixture_source = (str(path.parent) == "evals/fixtures/codex-native" and path.name in {
        "normal-research.json", "insufficient-evidence.json", "evidence-conflict.json", "future-or-stale.json", "risk-veto.json", "invalid-portfolio.json"})
    if (path.is_absolute() or ".." in path.parts or FORBIDDEN_PARTS & set(path.parts)
            or not path.parts or (path.parts[0] != "product" and not fixture_source) or path.name in LEGACY_CONTROLLERS):
        raise ValueError("NATIVE_PACKAGE_SOURCE_PATH_FORBIDDEN")
    return path


def _source(root: Path, name: str, digest: str) -> bytes:
    relative = _safe_relative(name)
    path = root/relative
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("NATIVE_PACKAGE_SOURCE_UNSAFE")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("NATIVE_PACKAGE_REVIEWED_SOURCE_DRIFT")
    if re.search(rb"sk-ant-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", raw):
        raise ValueError("NATIVE_PACKAGE_POTENTIAL_SECRET")
    return raw


def _validate_import_closure(sources: Mapping[str, bytes]) -> None:
    def require_module(module: str) -> None:
        file = module.replace(".", "/") + ".py"
        package = module.replace(".", "/") + "/__init__.py"
        if file not in sources and package not in sources:
            raise ValueError("NATIVE_PACKAGE_PYTHON_DEPENDENCY_MISSING:" + module)
        parts = module.split(".")
        for index in range(1, len(parts)):
            if "/".join(parts[:index]) + "/__init__.py" not in sources:
                raise ValueError("NATIVE_PACKAGE_PYTHON_PACKAGE_MISSING")
    for name, raw in sources.items():
        if not name.endswith(".py") or name.startswith("product/skills/"):
            continue
        current = name.removesuffix(".py").replace("/", ".")
        package = current.removesuffix(".__init__") if current.endswith(".__init__") else current.rsplit(".", 1)[0]
        for node in ast.walk(ast.parse(raw, filename=name)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "product" or alias.name.startswith("product."):
                        require_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = package.split(".")[:len(package.split(".")) - node.level + 1]
                    module = ".".join([*prefix, *([node.module] if node.module else [])])
                else:
                    module = node.module or ""
                if module == "product" or module.startswith("product."):
                    require_module(module)


def _render(raw: bytes, *, python_interpreter: str, module_root: Path, body: bytes | None = None) -> bytes:
    text = raw.decode("utf-8")
    if body is not None:
        if text.count("{{ROLE_BODY}}") != 1:
            raise ValueError("NATIVE_PACKAGE_ROLE_TEMPLATE_INVALID")
        text = text.replace("{{ROLE_BODY}}", body.decode("utf-8"))
    text = text.replace("{{PYTHON}}", json.dumps(python_interpreter, ensure_ascii=False)[1:-1])
    text = text.replace("{{REPOSITORY_ROOT}}", json.dumps(str(module_root), ensure_ascii=False)[1:-1])
    if re.search(r"\{\{[A-Z_]+\}\}", text):
        raise ValueError("NATIVE_PACKAGE_TEMPLATE_UNRESOLVED")
    return text.encode("utf-8")


def _connection_files(repository: Path, target: Path, files: Mapping[str, str]) -> None:
    if not isinstance(files, Mapping) or not files or not set(files) <= {"company", "market", "skeptic", "cio"}:
        raise ValueError("NATIVE_PACKAGE_CLAUDE_CONNECTION_FILES_INVALID")
    for value in files.values():
        if (not isinstance(value, str) or not Path(value).is_absolute()
                or Path(value).resolve().is_relative_to(repository.resolve())
                or Path(value).resolve().is_relative_to(target.resolve())):
            raise ValueError("NATIVE_PACKAGE_CONNECTION_FILE_MUST_BE_EXTERNAL")


def _claude_discovery(sources: Mapping[str, bytes], *, python_interpreter: str,
                      module_root: Path, connection_files: Mapping[str, str] | None,
                      in_place: bool = False) -> dict[str, bytes]:
    def render(raw, **kwargs):
        return _render(raw, python_interpreter=python_interpreter, module_root=module_root, **kwargs)
    main_thread = "product/hosts/claude-code/main-thread.md"
    if main_thread not in sources:
        raise ValueError("NATIVE_PACKAGE_MAIN_THREAD_INSTRUCTIONS_MISSING")
    native_skills = {name: f"product/hosts/claude-code/skills/{name}-native/SKILL.md"
                     for name in ("company", "market", "skeptic")}
    for name, source in native_skills.items():
        if source not in sources:
            raise ValueError(f"NATIVE_PACKAGE_{name.upper()}_NATIVE_SKILL_MISSING")
        if any(path.startswith(f"product/skills/{name}-native/") for path in sources):
            raise ValueError(f"NATIVE_PACKAGE_{name.upper()}_NATIVE_SKILL_CONFLICT")
    template = "product/hosts/claude-code/mcp.json"
    if template not in sources:
        raise ValueError("NATIVE_PACKAGE_TEMPLATE_MISSING")
    config = json.loads(render(sources[template]))
    if connection_files is not None:
        selected = {}
        for name, filename in connection_files.items():
            server = config["mcpServers"][name]
            prefix = server["args"][server["args"].index("--connection-env-prefix") + 1]
            server["args"].extend(["--connection-env-file", filename])
            for key in (prefix + "_CONNECTION", prefix + "_TOKEN"):
                server["env"].pop(key, None)
            selected[name] = server
        config["mcpServers"] = selected
    output = {".mcp.json": (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    for role in ROLES:
        template = f"product/hosts/claude-code/agents/{role}.md"
        if template not in sources:
            raise ValueError("NATIVE_PACKAGE_TEMPLATE_MISSING")
        skills = re.search(r"^skills:\n((?:  - [^\n]+\n)+)", sources[template].decode("utf-8"), re.M)
        for skill in re.findall(r"^  - ([a-z][a-z0-9-]*)$", skills[1] if skills else "", re.M):
            if f"product/skills/{skill}/SKILL.md" not in sources:
                raise ValueError("NATIVE_PACKAGE_REVIEWED_SKILL_MISSING")
        output[f".claude/agents/{role}.md"] = render(sources[template], body=sources[f"product/agents/{role}.md"])
    output["CLAUDE.md"] = (sources["product/AGENTS.md"] + b"\n" + sources[main_thread]
                           + b"\n" + sources["product/agents/runtime_cio.md"])
    for name, raw in sources.items():
        if name.startswith("product/skills/") and (not in_place or (name.count("/") == 3 and name.endswith("/SKILL.md"))):
            relative = name.removeprefix("product/skills/")
            prefix = "../../../" if in_place else "../../../product/"
            text = raw.decode("utf-8").replace("`../../agents/`", f"`{prefix}agents/`")
            text = text.replace("`../../hosts/README.md`", f"`{prefix}hosts/README.md`")
            output[f".claude/skills/{relative}"] = text.encode("utf-8")
    for name, source in native_skills.items():
        output[f".claude/skills/{name}-native/SKILL.md"] = sources[source]
    return output


def export_package(
    repository: Path, target: Path, *, host: str,
    reviewed_file_hashes: Mapping[str, str], python_interpreter: str,
    claude_connection_files: Mapping[str, str] | None = None,
) -> dict:
    """清单由审阅方显式传入；不按dirty目录自动选择、不覆盖现有安装。"""
    if host not in HOSTS:
        raise ValueError("NATIVE_PACKAGE_HOST_UNSUPPORTED")
    repository, target = Path(repository).absolute(), Path(target).absolute()
    if (any(p.is_symlink() for p in (repository, *repository.parents, target, *target.parents))
            or target.exists() or target.resolve().is_relative_to(repository.resolve())):
        raise ValueError("NATIVE_PACKAGE_TARGET_UNSAFE_OR_EXISTS")
    if not Path(python_interpreter).is_absolute():
        raise ValueError("NATIVE_PACKAGE_INTERPRETER_MUST_BE_EXPLICIT")
    if claude_connection_files is not None:
        if host != "claude-code":
            raise ValueError("NATIVE_PACKAGE_CLAUDE_CONNECTION_FILES_INVALID")
        _connection_files(repository, target, claude_connection_files)
    sources = {name: _source(repository, name, digest) for name, digest in reviewed_file_hashes.items()}
    required = {"product/AGENTS.md", "product/agents/runtime_cio.md", *PUBLIC_PREPARATION_RESOURCES,
                "product/tools/prepare.py", "product/tools/material_preparation.py",
                "product/contracts/council-decision-contract.json",
                "product/deterministic/risk.py", "product/deterministic/policy.py",
                *{"product/agents/"+name+".md" for name in ROLES},
                "product/skills/portfolio-council/SKILL.md",
                "product/skills/tiger-trade-journal/SKILL.md", "product/skills/trading-reflection/SKILL.md"}
    if not required <= sources.keys():
        raise ValueError("NATIVE_PACKAGE_REVIEWED_CONTENT_INCOMPLETE")
    # Tool modules must be included explicitly if this export carries its backend.
    if "product/mcp/research.py" not in sources:
        raise ValueError("NATIVE_PACKAGE_REVIEWED_TOOL_SOURCE_REQUIRED")
    _validate_import_closure(sources)
    output = dict(sources)
    def render(raw: bytes, *, body: bytes | None = None) -> bytes:
        return _render(raw, python_interpreter=python_interpreter, module_root=target, body=body)
    if host == "codex":
        name = "product/hosts/codex/config.toml"
        if name not in sources:
            raise ValueError("NATIVE_PACKAGE_TEMPLATE_MISSING")
        output[".codex/config.toml"] = render(sources[name])
        for role in ROLES:
            name = f"product/hosts/codex/agents/{role}.toml"
            if name not in sources:
                raise ValueError("NATIVE_PACKAGE_TEMPLATE_MISSING")
            output[f".codex/agents/{role}.toml"] = render(sources[name], body=sources[f"product/agents/{role}.md"])
        output["AGENTS.md"] = sources["product/AGENTS.md"] + b"\n" + sources["product/agents/runtime_cio.md"]
    elif host == "claude-code":
        output.update(_claude_discovery(sources, python_interpreter=python_interpreter,
                                       module_root=target, connection_files=claude_connection_files))
    else:
        name = "product/hosts/opencode/opencode.json"
        if name not in sources:
            raise ValueError("NATIVE_PACKAGE_TEMPLATE_MISSING")
        output["opencode.json"] = render(sources[name])
    skill_root = ".claude/skills" if host == "claude-code" else ".agents/skills"
    for name, raw in sources.items():
        if name.startswith("product/skills/") and host != "claude-code":
            relative = name.removeprefix("product/skills/")
            text = raw.decode("utf-8")
            # Only relocate the two explicit package references; method prose stays.
            text = text.replace("`../../agents/`", "`../../../product/agents/`")
            text = text.replace("`../../hosts/README.md`", "`../../../product/hosts/README.md`")
            output[f"{skill_root}/{relative}"] = text.encode("utf-8")
    for name, raw in output.items():
        if name.startswith(".codex/") and name.endswith(".toml"):
            tomllib.loads(raw.decode("utf-8"))
        elif name in {".mcp.json", "opencode.json"}:
            json.loads(raw)
    # All validation/rendering precedes target creation; callers retain their old install.
    target.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, raw in output.items():
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "status": "EXPORTED_NOT_INSTALLED", "host": host,
        "source_files": dict(reviewed_file_hashes),
        "exported_files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(output.items())},
        "source_id": "native-package-export:"+host,
        "as_of": timestamp, "retrieved_at": timestamp,
        "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED",
    }
    (target/"native-package-export.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    return result


def prepare_claude_workspace(
    repository: Path, *, reviewed_file_hashes: Mapping[str, str], python_interpreter: str,
    claude_connection_files: Mapping[str, str] | None = None,
    migrate_mcp_sha256: str | None = None,
) -> dict:
    """显式刷新product薄发现；所有来源和已有目标先验，不复制业务源码或读取连接秘密。"""
    repository = Path(repository).absolute()
    target = repository/"product"
    registry = target/".claude/native-product.json"
    if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_dir()
            or repository != repository.resolve()):
        raise ValueError("NATIVE_WORKSPACE_ROOT_UNSAFE")
    if not Path(python_interpreter).is_absolute() or not Path(python_interpreter).is_file():
        raise ValueError("NATIVE_PACKAGE_INTERPRETER_MUST_BE_EXPLICIT")
    if claude_connection_files is not None:
        _connection_files(repository, target, claude_connection_files)
    sources = {}
    for name, digest in reviewed_file_hashes.items():
        path = _safe_relative(name)
        discovery = (name in {"product/AGENTS.md", "product/agents/runtime_cio.md"}
                     or name in {f"product/agents/{role}.md" for role in ROLES}
                     or name in {"product/hosts/claude-code/main-thread.md", "product/hosts/claude-code/mcp.json"}
                     or name in {f"product/hosts/claude-code/agents/{role}.md" for role in ROLES}
                     or name in {f"product/hosts/claude-code/skills/{role}-native/SKILL.md"
                                 for role in ("company", "market", "skeptic")}
                     or (len(path.parts) >= 4 and path.parts[:2] == ("product", "skills")
                         and re.fullmatch(r"[a-z][a-z0-9-]*", path.parts[2])))
        if str(path) != name or not discovery or any(part.startswith(".") for part in path.parts):
            raise ValueError("NATIVE_WORKSPACE_SOURCE_NOT_DISCOVERY")
        sources[name] = _source(repository, name, digest)
    required = {"product/AGENTS.md", "product/agents/runtime_cio.md",
                *{f"product/agents/{role}.md" for role in ROLES},
                *{str(path.relative_to(repository)) for path in (target/"skills").rglob("*")
                  if (path.is_file() or path.is_symlink()) and "__pycache__" not in path.parts
                  and path.suffix != ".pyc"}}
    if not required <= sources.keys():
        raise ValueError("NATIVE_PACKAGE_REVIEWED_CONTENT_INCOMPLETE")
    output = _claude_discovery(sources, python_interpreter=python_interpreter, module_root=repository,
                              connection_files=claude_connection_files or {}, in_place=True)
    links = {".claude/skills/"+name.removeprefix("product/skills/"): name
             for name in sources if name.startswith("product/skills/")
             and not (name.count("/") == 3 and name.endswith("/SKILL.md"))}
    owned = {name: {"sha256": hashlib.sha256(raw).hexdigest()} for name, raw in output.items()}
    owned.update({name: {"source": source} for name, source in links.items()})

    def check_path(path: Path) -> None:
        if (any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in path.parents)
                or (path.exists() and path.is_dir() and not path.is_symlink())):
            raise ValueError("NATIVE_WORKSPACE_TARGET_UNSAFE")
    check_path(registry)
    if registry.is_symlink():
        raise ValueError("NATIVE_WORKSPACE_TARGET_UNSAFE")
    previous = {}
    if registry.exists():
        record = json.loads(registry.read_bytes())
        if (record.get("schema_version") != "claude-product-workspace/1.0.0"
                or record.get("repository_root") != str(repository)
                or not isinstance(record.get("files"), dict)):
            raise ValueError("NATIVE_WORKSPACE_REGISTRY_INVALID")
        previous = record["files"]
        if not previous.keys() <= owned.keys():
            raise ValueError("NATIVE_WORKSPACE_FILE_SET_CHANGED")
        if migrate_mcp_sha256 is not None:
            raise ValueError("NATIVE_WORKSPACE_MCP_ALREADY_MANAGED")
    elif migrate_mcp_sha256 is not None and not (target/".mcp.json").is_file():
        raise ValueError("NATIVE_WORKSPACE_MCP_MIGRATION_MISMATCH")
    for name in owned:
        path = target/name
        check_path(path)
        if name in previous:
            old = previous[name]
            if not isinstance(old, dict):
                raise ValueError("NATIVE_WORKSPACE_REGISTRY_INVALID")
            if set(old) == {"source"}:
                source = links.get(name)
                if (source != old["source"] or not path.is_symlink()
                        or os.readlink(path) != os.path.relpath(repository/source, path.parent)):
                    raise ValueError("NATIVE_WORKSPACE_TARGET_DRIFT")
            elif (set(old) != {"sha256"} or path.is_symlink() or not path.is_file()
                  or hashlib.sha256(path.read_bytes()).hexdigest() != old["sha256"]):
                raise ValueError("NATIVE_WORKSPACE_TARGET_DRIFT")
        elif path.exists() or path.is_symlink():
            if (name != ".mcp.json" or registry.exists() or path.is_symlink()
                    or migrate_mcp_sha256 is None
                    or hashlib.sha256(path.read_bytes()).hexdigest() != migrate_mcp_sha256):
                raise ValueError("NATIVE_WORKSPACE_TARGET_CONFLICT")
    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "schema_version": "claude-product-workspace/1.0.0", "status": "PREPARED_NOT_LOAD_VERIFIED",
        "host": "claude-code", "repository_root": str(repository),
        "source_files": dict(reviewed_file_hashes), "files": owned,
        "source_id": "claude-product-workspace", "as_of": timestamp, "retrieved_at": timestamp,
        "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED",
    }
    # Only our validated discovery files are written; unrelated user files remain untouched.
    for name, raw in {**output, ".claude/native-product.json":
                      (json.dumps(result, ensure_ascii=False, indent=2)+"\n").encode("utf-8")}.items():
        path = target/name
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if path.is_file() and path.read_bytes() == raw:
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        path.chmod(0o600)
    for name, source in links.items():
        path = target/name
        if not path.is_symlink():
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            path.symlink_to(os.path.relpath(repository/source, path.parent))
    return result


def verify_export(target: Path, result: Mapping) -> None:
    root = Path(target)
    if root.is_symlink():
        raise ValueError("NATIVE_PACKAGE_EXPORT_UNSAFE")
    expected = set(result["exported_files"]) | {"native-package-export.json"}
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != expected:
        raise ValueError("NATIVE_PACKAGE_EXPORT_FILE_SET_DRIFT")
    for name, digest in result["exported_files"].items():
        path = root/name
        if (path.is_symlink() or any(p.is_symlink() for p in path.parents)
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("NATIVE_PACKAGE_EXPORT_CONTENT_DRIFT")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="准备product就地Claude发现或显式导出；不启动模型或读取连接秘密。")
    parser.add_argument("--source", type=Path, required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--target", type=Path)
    destination.add_argument("--in-place", action="store_true", help="仅写当前仓库product的薄Claude发现配置。")
    parser.add_argument("--host", choices=sorted(HOSTS), required=True)
    parser.add_argument("--reviewed-files", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--claude-connection-files", type=Path, help="服务名到仓库外私有连接文件路径的映射；不读取文件中的凭据。")
    parser.add_argument("--migrate-mcp-sha256", help="首次就地迁移已有product/.mcp.json所需的已审阅原hash。")
    args = parser.parse_args()
    if (args.in_place and args.host != "claude-code") or (args.migrate_mcp_sha256 and not args.in_place):
        parser.error("就地准备及MCP迁移仅适用于--host claude-code --in-place。")
    hashes = json.loads(args.reviewed_files.read_text(encoding="utf-8"))
    files = json.loads(args.claude_connection_files.read_text(encoding="utf-8")) if args.claude_connection_files else None
    if args.in_place:
        result = prepare_claude_workspace(args.source, reviewed_file_hashes=hashes,
                                          python_interpreter=args.python, claude_connection_files=files,
                                          migrate_mcp_sha256=args.migrate_mcp_sha256)
    else:
        result = export_package(args.source, args.target, host=args.host,
                                reviewed_file_hashes=hashes, python_interpreter=args.python,
                                claude_connection_files=files)
        verify_export(args.target, result)
    print(json.dumps({key: result[key] for key in ("status", "host", "host_execution", "content_verdict")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
