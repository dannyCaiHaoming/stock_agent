"""Bind private state to an explicit project and verify real write isolation."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

from .common import canonical_hash


class PrivacyError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def repository_root(value: Path | str) -> Path:
    supplied = Path(value)
    if not supplied.is_absolute():
        raise PrivacyError("JOURNAL_EXPLICIT_ABSOLUTE_REPOSITORY_REQUIRED")
    root = supplied.resolve(strict=True)
    if not (root / "product").is_dir():
        raise PrivacyError("JOURNAL_PROJECT_INVALID")
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                            capture_output=True, text=True, check=False)
    if result.returncode or Path(result.stdout.strip()).resolve() != root:
        raise PrivacyError("JOURNAL_REPOSITORY_BINDING_INVALID")
    return root


def _no_links(path: Path, root: Path) -> None:
    if not path.is_relative_to(root):
        raise PrivacyError("JOURNAL_PATH_ESCAPE")
    current = path
    while current != root:
        if current.is_symlink():
            raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
        current = current.parent


def _git_private_guard(root: Path) -> None:
    tracked = subprocess.run(["git", "ls-files", "--", "product/.private"],
                             cwd=root, capture_output=True, text=True, check=True)
    if tracked.stdout.strip():
        raise PrivacyError("JOURNAL_PRIVATE_FILE_TRACKED")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--no-index",
                              "product/.private/trading-journal/.isolation-probe"],
                             cwd=root, capture_output=True, check=False)
    if ignored.returncode:
        raise PrivacyError("JOURNAL_GIT_IGNORE_MISSING")


def private_root(value: Path | str, *, create: bool = False, real: bool = False) -> Path:
    root = repository_root(value)
    target = root / "product/.private/trading-journal"
    _no_links(target, root)
    _git_private_guard(root)
    if real:
        assert_real_write_ready(root)
    if create:
        for directory in (target.parent, target, target / "sources", target / "market",
                          target / "artifacts"):
            _no_links(directory, root)
            if not directory.exists():
                directory.mkdir(mode=0o700)
            if not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
                raise PrivacyError("JOURNAL_PRIVATE_DIRECTORY_PERMISSION_INVALID")
    elif not target.is_dir():
        raise PrivacyError("JOURNAL_NOT_INITIALIZED")
    if target.exists() and stat.S_IMODE(target.stat().st_mode) != 0o700:
        raise PrivacyError("JOURNAL_PRIVATE_DIRECTORY_PERMISSION_INVALID")
    return target


def write_private(path: Path, content: str | bytes, *, replace: bool = False) -> None:
    """No symlink following; exclusive writes by default, private temp for replace."""
    if path.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    current = path.parent
    while current != current.parent:
        if current.is_symlink():
            raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
        current = current.parent
    payload = content.encode("utf-8") if isinstance(content, str) else content
    if replace:
        temporary = path.with_name(path.name + ".new-" + os.urandom(6).hex())
        write_private(temporary, payload)
        os.replace(temporary, path)
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    os.chmod(path, 0o600)


def tree_hash(path: Path) -> str:
    """Code-only immutable tree identity; refuses private directories and links."""
    records = []
    if not path.is_dir() or path.is_symlink():
        raise PrivacyError("JOURNAL_CODE_SOURCE_INVALID")
    for node in sorted(path.rglob("*")):
        relative = node.relative_to(path)
        if ".private" in relative.parts or node.is_symlink():
            raise PrivacyError("JOURNAL_CODE_COPY_CONTAINS_PRIVATE_OR_LINK")
        if any(part in {"__pycache__", ".DS_Store", ".pytest_cache"} for part in relative.parts):
            continue
        if node.is_file():
            records.append([relative.as_posix(), hashlib.sha256(node.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()


def _copy_guard_hash(root: Path) -> str:
    paths = [root / "product/runtime/common_stock_stage.py"]
    data = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        copies = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr == "copytree"
                  and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "product_root"]
        if not copies:
            raise PrivacyError("JOURNAL_RUNTIME_COPY_GUARD_MISSING")
        for copy in copies:
            ignore = next((item.value for item in copy.keywords if item.arg == "ignore"), None)
            if (not isinstance(ignore, ast.Call) or not isinstance(ignore.func, ast.Attribute)
                    or ignore.func.attr != "ignore_patterns" or not any(
                        isinstance(item, ast.Constant) and item.value == ".private" for item in ignore.args)):
                raise PrivacyError("JOURNAL_RUNTIME_COPY_GUARD_MISSING")
        data.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def assert_real_write_ready(value: Path | str) -> Path:
    root = repository_root(value)
    _git_private_guard(root)
    receipt = root / ".codex-local/trading-journal-isolation.json"
    _no_links(receipt, root)
    if (receipt.parent.exists() and stat.S_IMODE(receipt.parent.stat().st_mode) != 0o700
            or receipt.exists() and stat.S_IMODE(receipt.stat().st_mode) != 0o600):
        raise PrivacyError("JOURNAL_ISOLATION_RECEIPT_PERMISSION_INVALID")
    try:
        proof = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PrivacyError("JOURNAL_REAL_WRITE_ISOLATION_UNVERIFIED") from None
    if proof.get("repository_root") != str(root) or proof.get("status") != "VERIFIED":
        raise PrivacyError("JOURNAL_REAL_WRITE_ISOLATION_UNVERIFIED")
    if proof.get("proof_hash") != canonical_hash({key: value for key, value in proof.items() if key != "proof_hash"}):
        raise PrivacyError("JOURNAL_ISOLATION_RECEIPT_HASH_MISMATCH")
    marketplace = root / ".agents/plugins/marketplace.json"
    if hashlib.sha256(marketplace.read_bytes()).hexdigest() != proof.get("marketplace_hash"):
        raise PrivacyError("JOURNAL_PLUGIN_SOURCE_CHANGED")
    registry = json.loads(marketplace.read_text())
    product = next((entry for entry in registry.get("plugins", []) if entry.get("name") == "product"), {})
    source = (root / product.get("source", {}).get("path", "")).resolve()
    expected = root / ".codex-local/product-plugin"
    if source != expected or tree_hash(source) != proof.get("source_hash"):
        raise PrivacyError("JOURNAL_PLUGIN_SOURCE_CHANGED")
    from .packaging import OVERLAY_ROOTS, _registered_install
    if set(proof.get("overlays", {})) != set(OVERLAY_ROOTS):
        raise PrivacyError("JOURNAL_OVERLAY_PROOF_INVALID")
    for relative, digest in proof["overlays"].items():
        if tree_hash(root / "product" / relative) != digest or tree_hash(source / relative) != digest:
            raise PrivacyError("JOURNAL_REVIEWED_OVERLAY_CHANGED")
    baseline = Path(proof.get("installed_baseline", ""))
    if tree_hash(baseline) != proof.get("baseline_hash"):
        raise PrivacyError("JOURNAL_INSTALLED_BASELINE_CHANGED")
    installed = Path(proof.get("installed_copy", ""))
    if (not installed.is_absolute() or installed.resolve().is_relative_to(root)
            or tree_hash(installed) != proof.get("installed_hash") or proof.get("installed_hash") != proof.get("source_hash")):
        raise PrivacyError("JOURNAL_ACTUAL_INSTALL_CHANGED")
    if _registered_install(root, installed.resolve(), proof) != proof.get("registration"):
        raise PrivacyError("JOURNAL_ACTUAL_INSTALL_REGISTRATION_CHANGED")
    if _copy_guard_hash(root) != proof.get("copy_guard_hash"):
        raise PrivacyError("JOURNAL_RUNTIME_COPY_GUARD_CHANGED")
    return root / "product/.private/trading-journal"
