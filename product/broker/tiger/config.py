"""Credential-reference validation for Tiger OpenAPI.

This module deliberately does not import ``tigeropen`` and never returns
credential values.  Network-capable SDK construction lives in the adapter and
is only reached by explicit snapshot/sync commands.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import stat
from typing import Mapping


CONFIG_FILE = "tiger_openapi_config.properties"
TOKEN_FILE = "tiger_openapi_token.properties"
REQUIRED_CONFIG_FIELDS = frozenset({"tiger_id", "account", "license"})
PRIVATE_KEY_FIELDS = ("private_key", "private_key_pk8", "private_key_pk1")
SENSITIVE_FIELDS = frozenset({
    "tiger_id", "account", "private_key", "private_key_pk8", "private_key_pk1",
    "token", "secret_key", "authorization", "password",
})


class TigerConfigError(ValueError):
    """Stable fail-closed configuration error without credential content."""


@dataclass(frozen=True)
class TigerConfigPreflight:
    status: str
    code: str
    license: str | None
    config_file_status: str
    token_file_status: str
    missing_fields: tuple[str, ...]
    sdk_required: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _outside_repository(path: Path, repository_root: Path) -> bool:
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        return True
    return False


def _private_mode(path: Path) -> bool:
    if os.name == "nt":
        return True
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def _parse_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TigerConfigError("TIGER_CONFIG_UNREADABLE") from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        separator = "=" if "=" in line else (":" if ":" in line else None)
        if separator is None:
            continue
        key, value = line.split(separator, 1)
        result[key.strip()] = value.strip()
    return result


def preflight_config(config_dir: Path, *, repository_root: Path) -> TigerConfigPreflight:
    """Validate a repository-external TBHK config reference without networking."""

    supplied = Path(config_dir).expanduser()
    repository_root = Path(repository_root).resolve()
    if not supplied.is_absolute():
        raise TigerConfigError("TIGER_CONFIG_ABSOLUTE_PATH_REQUIRED")
    if supplied.is_symlink():
        raise TigerConfigError("TIGER_CONFIG_SYMLINK_REJECTED")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise TigerConfigError("TIGER_CONFIG_DIRECTORY_MISSING") from exc
    if not resolved.is_dir():
        raise TigerConfigError("TIGER_CONFIG_DIRECTORY_REQUIRED")
    if not _outside_repository(resolved, repository_root):
        raise TigerConfigError("TIGER_CONFIG_INSIDE_REPOSITORY")
    if not _private_mode(resolved):
        raise TigerConfigError("TIGER_CONFIG_DIRECTORY_PERMISSIONS_TOO_OPEN")

    config_file = resolved / CONFIG_FILE
    token_file = resolved / TOKEN_FILE
    for path, missing_code in (
        (config_file, "TIGER_CONFIG_FILE_MISSING"),
        (token_file, "TIGER_TOKEN_FILE_MISSING"),
    ):
        if path.is_symlink():
            raise TigerConfigError("TIGER_CONFIG_FILE_SYMLINK_REJECTED")
        if not path.is_file():
            raise TigerConfigError(missing_code)
        if not _private_mode(path):
            raise TigerConfigError("TIGER_CONFIG_FILE_PERMISSIONS_TOO_OPEN")

    properties = _parse_properties(config_file)
    missing_values = [field for field in REQUIRED_CONFIG_FIELDS if not properties.get(field)]
    if not any(properties.get(field) for field in PRIVATE_KEY_FIELDS):
        missing_values.append("private_key")
    missing = tuple(sorted(missing_values))
    if missing:
        return TigerConfigPreflight(
            status="BLOCKED",
            code="TIGER_CONFIG_FIELDS_MISSING",
            license=None,
            config_file_status="PRESENT_PRIVATE",
            token_file_status="PRESENT_UNVERIFIED",
            missing_fields=missing,
            sdk_required="tigeropen==3.8.0",
        )
    license_value = properties.get("license", "").upper()
    if license_value != "TBHK":
        return TigerConfigPreflight(
            status="BLOCKED",
            code="TIGER_LICENSE_NOT_TBHK",
            license=license_value or None,
            config_file_status="PRESENT_PRIVATE",
            token_file_status="PRESENT_UNVERIFIED",
            missing_fields=(),
            sdk_required="tigeropen==3.8.0",
        )
    token_properties = _parse_properties(token_file)
    if not token_properties.get("token"):
        return TigerConfigPreflight(
            status="BLOCKED",
            code="TIGER_TOKEN_MISSING",
            license="TBHK",
            config_file_status="PRESENT_PRIVATE",
            token_file_status="MISSING_VALUE",
            missing_fields=("token",),
            sdk_required="tigeropen==3.8.0",
        )
    return TigerConfigPreflight(
        status="READY",
        code="TIGER_CONFIG_READY",
        license="TBHK",
        config_file_status="PRESENT_PRIVATE",
        token_file_status="PRESENT_UNVERIFIED",
        missing_fields=(),
        sdk_required="tigeropen==3.8.0",
    )


def sanitized_error(exc: BaseException) -> str:
    """Map SDK/config failures to stable non-secret categories."""

    if isinstance(exc, TigerConfigError):
        return str(exc)
    text = str(exc).casefold()
    if any(word in text for word in ("token", "unauthorized", "authentication", "signature")):
        return "TIGER_AUTHENTICATION_FAILED"
    if any(word in text for word in ("rate limit", "too many request")):
        return "TIGER_RATE_LIMITED"
    if any(word in text for word in ("timeout", "timed out")):
        return "TIGER_NETWORK_TIMEOUT"
    return "TIGER_PROVIDER_ERROR"


def redacted_mapping(value: Mapping[str, object]) -> dict[str, object]:
    """Drop sensitive keys before structured diagnostics are persisted."""

    return {
        str(key): item
        for key, item in value.items()
        if str(key).casefold() not in SENSITIVE_FIELDS
    }
