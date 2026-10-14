"""Runtime settings for the stock-data MCP server (environment variables only)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from product.mcp.live.cache import SnapshotCache


class SettingsError(ValueError):
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / ".local" / "data"


def data_dir() -> Path:
    """Private data root: reports and decision log. Default <repo>/.local/data (git-ignored).

    Dev test runs override it with STOCK_AGENT_DATA_DIR=<repo>/.local/runs/<run-id>.
    """
    configured = os.environ.get("STOCK_AGENT_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_DATA_DIR
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


@lru_cache(maxsize=1)
def cache() -> SnapshotCache:
    """Shared raw-response cache. Default <repo>/.local/cache, shared by normal use and dev runs."""
    configured = os.environ.get("STOCK_AGENT_CACHE_DIR")
    return SnapshotCache(Path(configured).expanduser().resolve() if configured else REPO_ROOT / ".local" / "cache")


def sec_user_agent() -> str:
    """SEC requires a declared contact, e.g. 'stock-agent your-name@example.com'."""
    value = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in value:
        raise SettingsError("SEC_USER_AGENT_REQUIRED: set SEC_USER_AGENT to 'app-name contact@email'")
    return value


def replay_as_of() -> str | None:
    """Historical replay date (YYYY-MM-DD) from STOCK_AGENT_REPLAY_AS_OF, or None for normal use.

    In replay mode every point-in-time tool is pinned to this date and current-only tools are refused,
    so a replayed study cannot see prices, estimates or news published afterwards.
    """
    value = os.environ.get("STOCK_AGENT_REPLAY_AS_OF", "").strip()
    if not value:
        return None
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SettingsError("STOCK_AGENT_REPLAY_AS_OF must be YYYY-MM-DD")
    return value
