"""Content-addressed, self-contained replay capsule support."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .hashing import canonical_hash, file_hash
from .schema_validation import validate_schema_instance


CAPSULE_VERSION = "replay-capsule/1.0.0"
MAX_OBJECT_BYTES = 2 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bghp_[A-Za-z0-9]{30,}\b"),
)
REQUIRED_PRODUCT_PATHS = {
    "product/AGENTS.md",
    "product/version-manifest.json",
    "product/runtime-profile.json",
    "product/model-routing.json",
    "product/.mcp.json",
    "product/.codex/config.toml",
    "product/.codex-plugin/plugin.json",
    "product/contracts/council-decision-contract.json",
    "product/skills/portfolio-council/SKILL.md",
    "product/.codex/agents/runtime_company_analyst.toml",
    "product/.codex/agents/runtime_skeptic.toml",
    "product/.codex/agents/runtime_cio.toml",
}
FROZEN_FIXTURE = "frozen/audit/fixture_snapshot.json"
FROZEN_GATE = "frozen/evidence/gate.json"


class ReplayCapsuleError(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayCapsuleError(f"CAPSULE_ARTIFACT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise ReplayCapsuleError(f"CAPSULE_ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _safe_logical_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or path.parts[0] not in {"product", "frozen"}
        or "\\" in value
    ):
        raise ReplayCapsuleError(f"CAPSULE_PATH_FORBIDDEN:{value}")
    return path


def _scan_payload(payload: bytes, *, logical_path: str) -> None:
    if any(pattern.search(payload) for pattern in SENSITIVE_PATTERNS):
        raise ReplayCapsuleError(f"CAPSULE_SENSITIVE_CONTENT:{logical_path}")


def _protected_repository_files(repository_root: Path) -> list[tuple[str, Path]]:
    root = repository_root.resolve()
    product = root / "product"
    roots = (
        product / ".codex-plugin",
        product / ".codex" / "agents",
        product / "skills",
        product / "schemas",
        product / "contracts",
        product / "deterministic",
        product / "runtime",
        product / "mcp",
        product / "evidence_store",
    )
    paths = [
        path
        for source_root in roots
        if source_root.is_dir()
        for path in source_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    paths.extend(
        product / relative
        for relative in (
            "AGENTS.md",
            "version-manifest.json",
            "runtime-profile.json",
            "model-routing.json",
            ".mcp.json",
            ".codex/config.toml",
        )
    )
    records: list[tuple[str, Path]] = []
    for path in sorted(set(paths)):
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
            raise ReplayCapsuleError(f"CAPSULE_PATH_FORBIDDEN:{path}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ReplayCapsuleError(f"CAPSULE_PATH_FORBIDDEN:{path}")
        records.append((resolved.relative_to(root).as_posix(), resolved))
    return records


def _role(logical_path: str) -> str:
    if logical_path == FROZEN_FIXTURE:
        return "portfolio-and-evidence-input"
    if logical_path == FROZEN_GATE:
        return "pit-gate"
    if "/skills/" in logical_path:
        return "skill"
    if "/agents/" in logical_path:
        return "agent"
    if "/schemas/" in logical_path or "/contracts/" in logical_path:
        return "schema-or-contract"
    if "/runtime/" in logical_path or "/deterministic/" in logical_path:
        return "deterministic-runtime"
    if "/mcp/" in logical_path or logical_path.endswith(".mcp.json"):
        return "mcp-adapter"
    return "runtime-config"


def _capsule_sources(repository_root: Path, run_dir: Path) -> Iterable[tuple[str, Path]]:
    yield from _protected_repository_files(repository_root)
    yield FROZEN_FIXTURE, run_dir / "audit" / "fixture_snapshot.json"
    yield FROZEN_GATE, run_dir / "evidence" / "gate.json"


def build_replay_capsule(
    repository_root: Path,
    *,
    run_dir: Path,
    run_id: str,
    locked_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a sealed capsule. Existing capsule paths are never overwritten."""

    capsule_dir = run_dir.resolve() / "replay_capsule"
    if capsule_dir.exists():
        raise ReplayCapsuleError("CAPSULE_ALREADY_EXISTS")
    objects_dir = capsule_dir / "objects"
    objects_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for logical_path, source in _capsule_sources(repository_root, run_dir.resolve()):
        _safe_logical_path(logical_path)
        if logical_path in seen_paths:
            raise ReplayCapsuleError(f"CAPSULE_PATH_DUPLICATE:{logical_path}")
        seen_paths.add(logical_path)
        if source.is_symlink() or not source.is_file():
            raise ReplayCapsuleError(f"CAPSULE_OBJECT_MISSING:{logical_path}")
        payload = source.read_bytes()
        if len(payload) > MAX_OBJECT_BYTES:
            raise ReplayCapsuleError(f"CAPSULE_OBJECT_TOO_LARGE:{logical_path}")
        _scan_payload(payload, logical_path=logical_path)
        digest = hashlib.sha256(payload).hexdigest()
        object_path = objects_dir / digest
        if not object_path.exists():
            object_path.write_bytes(payload)
            os.chmod(object_path, 0o444)
        records.append(
            {
                "logical_path": logical_path,
                "sha256": digest,
                "bytes": len(payload),
                "media_type": mimetypes.guess_type(logical_path)[0] or "application/octet-stream",
                "role": _role(logical_path),
                "executable": False,
            }
        )
    records.sort(key=lambda item: item["logical_path"])
    paths = {item["logical_path"] for item in records}
    missing = sorted((REQUIRED_PRODUCT_PATHS | {FROZEN_FIXTURE, FROZEN_GATE}) - paths)
    if missing:
        raise ReplayCapsuleError(f"CAPSULE_REQUIRED_OBJECT_MISSING:{','.join(missing)}")
    root_hash = canonical_hash(
        [{"logical_path": item["logical_path"], "sha256": item["sha256"]} for item in records]
    )
    body: dict[str, Any] = {
        "schema_version": CAPSULE_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "locked_context": dict(locked_context),
        "objects": records,
        "root_hash": root_hash,
    }
    body["manifest_hash"] = canonical_hash(body)
    manifest_path = capsule_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o444)
    validate_replay_capsule(capsule_dir, expected_run_id=run_id)
    return body


def validate_replay_capsule(
    capsule_dir: Path,
    *,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    capsule_dir = capsule_dir.resolve()
    manifest = _json(capsule_dir / "manifest.json")
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "runtime" / "replay-capsule.schema.json"
    schema = _json(schema_path)
    validate_schema_instance(manifest, schema)
    if expected_run_id is not None and manifest["run_id"] != expected_run_id:
        raise ReplayCapsuleError("CAPSULE_RUN_ID_MISMATCH")
    body = dict(manifest)
    claimed_manifest_hash = body.pop("manifest_hash")
    if claimed_manifest_hash != canonical_hash(body):
        raise ReplayCapsuleError("CAPSULE_HASH_MISMATCH:manifest")
    paths: set[str] = set()
    root_records = []
    referenced_hashes: set[str] = set()
    for record in manifest["objects"]:
        logical_path = str(record["logical_path"])
        _safe_logical_path(logical_path)
        if logical_path in paths:
            raise ReplayCapsuleError(f"CAPSULE_PATH_DUPLICATE:{logical_path}")
        paths.add(logical_path)
        digest = str(record["sha256"])
        if not SHA256_PATTERN.fullmatch(digest):
            raise ReplayCapsuleError(f"CAPSULE_HASH_MISMATCH:{logical_path}")
        object_path = capsule_dir / "objects" / digest
        if object_path.is_symlink() or not object_path.is_file():
            raise ReplayCapsuleError(f"CAPSULE_OBJECT_MISSING:{logical_path}")
        payload = object_path.read_bytes()
        if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != digest:
            raise ReplayCapsuleError(f"CAPSULE_HASH_MISMATCH:{logical_path}")
        if len(payload) > MAX_OBJECT_BYTES:
            raise ReplayCapsuleError(f"CAPSULE_OBJECT_TOO_LARGE:{logical_path}")
        _scan_payload(payload, logical_path=logical_path)
        root_records.append({"logical_path": logical_path, "sha256": digest})
        referenced_hashes.add(digest)
    frozen = {str(item["logical_path"]): str(item["sha256"]) for item in manifest["objects"]}
    context = manifest["locked_context"]
    if (
        frozen.get(FROZEN_FIXTURE) != context["fixture_hash"]
        or frozen.get(FROZEN_GATE) != context["gate_hash"]
    ):
        raise ReplayCapsuleError("CAPSULE_LOCKED_CONTEXT_HASH_MISMATCH")
    version_object = frozen.get("product/version-manifest.json")
    if version_object is None:
        raise ReplayCapsuleError("CAPSULE_REQUIRED_OBJECT_MISSING:product/version-manifest.json")
    version_manifest = _json(capsule_dir / "objects" / version_object)
    if canonical_hash(version_manifest) != context["version_manifest_hash"]:
        raise ReplayCapsuleError("CAPSULE_LOCKED_CONTEXT_HASH_MISMATCH")
    if any(
        context.get(context_field) != version_manifest.get(version_field)
        for context_field, version_field in (
            ("candidate_version", "candidate_version"),
            ("model", "model"),
            ("codex_runtime", "codex_runtime"),
            ("runtime_profile", "runtime_profile"),
        )
    ):
        raise ReplayCapsuleError("CAPSULE_LOCKED_CONTEXT_VERSION_MISMATCH")
    fixture = _json(capsule_dir / "objects" / frozen[FROZEN_FIXTURE])
    gate = _json(capsule_dir / "objects" / frozen[FROZEN_GATE])
    if (
        fixture.get("decision_cutoff") != context.get("decision_cutoff")
        or gate.get("decision_cutoff") != context.get("decision_cutoff")
        or gate.get("run_id") != manifest.get("run_id")
    ):
        raise ReplayCapsuleError("CAPSULE_LOCKED_CONTEXT_PIT_MISMATCH")
    integrity_paths = {
        logical_path: digest
        for logical_path, digest in frozen.items()
        if logical_path in {"product/AGENTS.md", "product/version-manifest.json"}
        or logical_path.startswith(
            (
                "product/.codex-plugin/",
                "product/.codex/agents/",
                "product/skills/",
                "product/schemas/",
                "product/contracts/",
                "product/deterministic/",
                "product/runtime/",
            )
        )
    }
    if canonical_hash(integrity_paths) != context.get("product_integrity_hash"):
        raise ReplayCapsuleError("CAPSULE_LOCKED_CONTEXT_INTEGRITY_MISMATCH")
    missing = sorted((REQUIRED_PRODUCT_PATHS | {FROZEN_FIXTURE, FROZEN_GATE}) - paths)
    if missing:
        raise ReplayCapsuleError(f"CAPSULE_REQUIRED_OBJECT_MISSING:{','.join(missing)}")
    actual_objects = {path.name for path in (capsule_dir / "objects").iterdir() if path.is_file()}
    if actual_objects != referenced_hashes:
        raise ReplayCapsuleError("CAPSULE_UNREFERENCED_OR_MISSING_OBJECT")
    if canonical_hash(sorted(root_records, key=lambda item: item["logical_path"])) != manifest["root_hash"]:
        raise ReplayCapsuleError("CAPSULE_HASH_MISMATCH:root")
    return manifest


def materialize_replay_capsule(capsule_dir: Path, *, target_root: Path) -> dict[str, Any]:
    """Materialize only allowlisted logical paths into a new isolated root."""

    if target_root.exists():
        raise ReplayCapsuleError("CAPSULE_TARGET_ALREADY_EXISTS")
    manifest = validate_replay_capsule(capsule_dir)
    target_root.mkdir(parents=True)
    for record in manifest["objects"]:
        logical = _safe_logical_path(str(record["logical_path"]))
        destination = target_root.joinpath(*logical.parts)
        resolved_parent = destination.parent.resolve()
        if not resolved_parent.is_relative_to(target_root.resolve()):
            raise ReplayCapsuleError(f"CAPSULE_PATH_FORBIDDEN:{logical}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = capsule_dir.resolve() / "objects" / str(record["sha256"])
        destination.write_bytes(source.read_bytes())
        os.chmod(destination, 0o444)
    return manifest


def capsule_reference(manifest: Mapping[str, Any], *, capsule_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": manifest["schema_version"],
        "path": str(capsule_dir.resolve()),
        "manifest_hash": manifest["manifest_hash"],
        "root_hash": manifest["root_hash"],
        "object_count": len(manifest["objects"]),
    }
