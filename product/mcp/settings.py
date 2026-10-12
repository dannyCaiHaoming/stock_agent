"""Runtime settings for the stock-data MCP server (environment variables only)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from product.mcp.live.cache import SnapshotCache


class SettingsError(ValueError):
    pass


def data_dir() -> Path:
    """Private data root outside the repository (cache, reports, decision log)."""
    root = Path(os.environ.get("STOCK_AGENT_DATA_DIR", "~/StockAgentData")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


@lru_cache(maxsize=1)
def cache() -> SnapshotCache:
    return SnapshotCache(data_dir() / "cache")


def sec_user_agent() -> str:
    """SEC requires a declared contact, e.g. 'stock-agent your-name@example.com'."""
    value = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in value:
        raise SettingsError("SEC_USER_AGENT_REQUIRED: set SEC_USER_AGENT to 'app-name contact@email'")
    return value
