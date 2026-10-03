"""Materialize an installed baseline with only this Change's explicit overlay."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .common import canonical_hash, utc_now
from .privacy import PrivacyError, _copy_guard_hash, _no_links, repository_root, tree_hash, write_private


OVERLAY_ROOTS = ("skills/tiger-trade-journal", "skills/trading-reflection", "trading_journal")


def _check_retained_baseline(root: Path, baseline: Path, expected_hash: str) -> None:
    expected_path = root / ".codex-local" / ("product-plugin-baseline-" + expected_hash[:16])
    if baseline != expected_path:
        raise PrivacyError("JOURNAL_BASELINE_RETENTION_PATH_INVALID")
    _no_links(baseline, root)
    if tree_hash(baseline) != expected_hash:
        raise PrivacyError("JOURNAL_BASELINE_RETENTION_HASH_MISMATCH")


def _retain_reviewed_baseline(root: Path, original: Path, expected_hash: str) -> Path:
    """Keep approved bytes independently of installer-managed cache lifetime."""
    retained = root / ".codex-local" / ("product-plugin-baseline-" + expected_hash[:16])
    _no_links(retained, root)
    if not retained.exists():
        # Match tree_hash exclusions exactly. A standalone .pyc is included in
        # that identity, whereas __pycache__ and the named cache dirs are not.
        shutil.copytree(original, retained,
                        ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", ".pytest_cache"))
        retained.chmod(0o700)
    _check_retained_baseline(root, retained, expected_hash)
    return retained


def _registered_install(root: Path, cache: Path, proof: dict) -> dict:
    """Ask the local installer for current registration, never infer from a copy."""
    try:
        name = json.loads((root / ".agents/plugins/marketplace.json").read_text())["name"]
        result = subprocess.run(["codex", "plugin", "list", "--marketplace", name, "--json"], cwd=root,
                                capture_output=True, text=True, timeout=45, check=True)
        state = json.loads(result.stdout)
        version = json.loads((root / ".codex-local/product-plugin/.codex-plugin/plugin.json").read_text())["version"]
        entry = next(item for item in state["installed"] if item.get("pluginId") == f"product@{name}")
        source = Path(entry["source"]["path"]).resolve()
        registered_root = Path(entry["marketplaceSource"]["source"]).resolve()
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
        raise PrivacyError("JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED") from None
    cache_base = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "plugins/cache" / name / "product"
    if (entry.get("installed") is not True or entry.get("enabled") is not True or entry.get("version") != version
            or registered_root != root or source != root / ".codex-local/product-plugin"
            or cache not in {cache_base.joinpath(version).resolve(), cache_base.joinpath("local").resolve()}):
        raise PrivacyError("JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED")
    return {"plugin_id": entry["pluginId"], "version": version,
            "source_path": str(source), "cache_path": str(cache)}


def prepare_clean_source(repository: Path | str, installed_baseline: Path | str,
                         *, expected_baseline_hash: str, expected_overlay_hashes: dict[str, str],
                         activate: bool = False) -> dict:
    root = repository_root(repository)
    supplied_baseline = Path(installed_baseline)
    if supplied_baseline.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    baseline = supplied_baseline.resolve(strict=True)
    if baseline.is_relative_to(root) or tree_hash(baseline) != expected_baseline_hash:
        raise PrivacyError("JOURNAL_APPROVED_BASELINE_HASH_MISMATCH")
    manifest = json.loads((baseline / ".codex-plugin/plugin.json").read_text())
    if manifest.get("name") != "product":
        raise PrivacyError("JOURNAL_BASELINE_NOT_PRODUCT_PLUGIN")
    if (set(expected_overlay_hashes) != set(OVERLAY_ROOTS) or any(
            tree_hash(root / "product" / relative) != expected_overlay_hashes[relative] for relative in OVERLAY_ROOTS)):
        raise PrivacyError("JOURNAL_REVIEWED_OVERLAY_HASH_MISMATCH")
    try:
        declared = json.loads((root / "product/version-manifest.json").read_text())["skills"]
        scoped_versions = {name: declared[name] for name in ("tiger-trade-journal", "trading-reflection")}
        if any(not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value) for value in scoped_versions.values()):
            raise ValueError("invalid version")
    except (OSError, ValueError, KeyError, TypeError):
        raise PrivacyError("JOURNAL_SKILL_VERSIONS_INVALID") from None
    local = root / ".codex-local"
    if local.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    local.mkdir(mode=0o700, exist_ok=True)
    original_baseline = baseline
    baseline = _retain_reviewed_baseline(root, original_baseline, expected_baseline_hash)
    target = local / "product-plugin"
    if target.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    staging = local / "product-plugin.pending"
    if staging.exists():
        raise PrivacyError("JOURNAL_PLUGIN_STAGING_EXISTS")
    shutil.copytree(baseline, staging,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".private"))
    overlays = {}
    for relative in OVERLAY_ROOTS:
        source = root / "product" / relative
        identity = tree_hash(source)
        destination = staging / relative
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".private"))
        overlays[relative] = identity
    # Keep every existing product Skill and runtime byte unchanged. Only add the
    # two new version entries to the baseline's own manifest.
    versions_path = staging / "version-manifest.json"
    versions = json.loads(versions_path.read_text())
    for name in ("tiger-trade-journal", "trading-reflection"):
        versions.setdefault("skills", {})[name] = scoped_versions[name]
    plugin_path = staging / ".codex-plugin/plugin.json"
    # Give the scoped install a distinct cache identity while preserving the
    # previous installed baseline for recovery and its Council candidate pointer.
    manifest["version"] = str(manifest.get("version", "0.3.0")).split("+")[0] + "+trading-journal." + canonical_hash(overlays)[:12]
    plugin_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if "resource_hashes" in versions:
        versions["resource_hashes"]["plugin"] = hashlib.sha256(plugin_path.read_bytes()).hexdigest()
    versions_path.write_text(json.dumps(versions, ensure_ascii=False, indent=2) + "\n")
    unchanged = []
    for path in baseline.rglob("*"):
        if path.is_file() and not any(part in {"__pycache__", ".DS_Store"} for part in path.parts):
            relative = path.relative_to(baseline)
            if relative.as_posix() in {"version-manifest.json", ".codex-plugin/plugin.json"}:
                continue
            if any(relative.is_relative_to(Path(item)) for item in OVERLAY_ROOTS):
                continue
            if (staging / relative).read_bytes() != path.read_bytes():
                raise PrivacyError("JOURNAL_UNRELATED_BASELINE_CHANGED")
            unchanged.append(relative.as_posix())
    source_hash = tree_hash(staging)
    timestamp = utc_now()
    proof = {"status": "PREPARED", "source_id": "plugin-isolation:" + source_hash,
             "as_of": timestamp, "retrieved_at": timestamp, "repository_root": str(root),
             "installed_baseline": str(baseline), "original_installed_baseline": str(original_baseline),
             "baseline_hash": expected_baseline_hash,
             "source_hash": source_hash, "overlays": overlays,
             "unchanged_baseline_file_count": len(unchanged),
             "copy_guard_hash": _copy_guard_hash(root)}
    if target.exists():
        backup = local / ("product-plugin.previous-" + tree_hash(target)[:12])
        if backup.exists():
            raise PrivacyError("JOURNAL_PLUGIN_BACKUP_EXISTS")
        target.rename(backup)
    staging.rename(target)
    if activate:
        path = root / ".agents/plugins/marketplace.json"
        original = path.read_bytes()
        registry = json.loads(original)
        entry = next(item for item in registry["plugins"] if item["name"] == "product")
        original_source = entry["source"]
        entry["source"] = {"source": "local", "path": "./.codex-local/product-plugin"}
        backup = local / ("marketplace.before-" + hashlib.sha256(original).hexdigest()[:12] + ".json")
        if not backup.exists():
            write_private(backup, original)
        path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
        proof.update(status="SOURCE_VERIFIED", original_source=original_source,
                     marketplace_hash=hashlib.sha256(path.read_bytes()).hexdigest())
        proof["proof_hash"] = canonical_hash(proof)
        write_private(local / "trading-journal-isolation.json",
                      json.dumps(proof, ensure_ascii=False, indent=2) + "\n", replace=True)
    return proof


def verify_installed_source(repository: Path | str, installed_copy: Path | str) -> dict:
    """Only a byte-equivalent actual install and private sentinel permit writes."""
    root = repository_root(repository)
    receipt = root / ".codex-local/trading-journal-isolation.json"
    _no_links(receipt, root)
    if receipt.stat().st_mode & 0o777 != 0o600 or receipt.parent.stat().st_mode & 0o777 != 0o700:
        raise PrivacyError("JOURNAL_ISOLATION_RECEIPT_PERMISSION_INVALID")
    proof = json.loads(receipt.read_text())
    if (proof.get("status") != "SOURCE_VERIFIED" or proof.get("repository_root") != str(root)
            or proof.get("proof_hash") != canonical_hash({key: value for key, value in proof.items() if key != "proof_hash"})):
        raise PrivacyError("JOURNAL_SOURCE_VERIFICATION_REQUIRED")
    # Failure here must preserve SOURCE_VERIFIED. Publishing VERIFIED first
    # would leave a misleading receipt when the recovery baseline is missing.
    _check_retained_baseline(root, Path(proof["installed_baseline"]), proof["baseline_hash"])
    cache = Path(installed_copy).resolve(strict=True)
    if cache.is_relative_to(root) or tree_hash(cache) != proof["source_hash"]:
        raise PrivacyError("JOURNAL_ACTUAL_INSTALL_MISMATCH")
    sentinel = root / "product/.private/trading-journal/synthetic-private-isolation-sentinel.txt"
    _no_links(sentinel, root)
    if not sentinel.is_file() or sentinel.read_bytes() != b"SYNTHETIC_PRIVATE_ISOLATION_SENTINEL\n":
        raise PrivacyError("JOURNAL_PRIVATE_SENTINEL_REQUIRED")
    # A same-version cache cannot replace the immutable baseline used for recovery.
    if cache == Path(proof["installed_baseline"]).resolve():
        raise PrivacyError("JOURNAL_BASELINE_MUST_REMAIN_RECOVERABLE")
    registration = _registered_install(root, cache, proof)
    proof.update(status="VERIFIED", installed_copy=str(cache), installed_hash=tree_hash(cache),
                 registration=registration,
                 synthetic_sentinel_sha256=hashlib.sha256(sentinel.read_bytes()).hexdigest())
    proof.pop("proof_hash", None)
    proof["proof_hash"] = canonical_hash(proof)
    write_private(receipt, json.dumps(proof, ensure_ascii=False, indent=2) + "\n", replace=True)
    from .privacy import assert_real_write_ready
    assert_real_write_ready(root)
    return proof
