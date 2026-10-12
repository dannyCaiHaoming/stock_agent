"""stock-data MCP server: read-only market data and deterministic calculations.

Run with: python -m product.mcp.server  (stdio transport)
"""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

server = MCPServer(
    name="stock-data",
    instructions=(
        "Read-only US equity research data and deterministic financial calculations. "
        "Every fact carries source_id, as_of and retrieved_at. No trading capability."
    ),
)


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


@server.tool(annotations=READ_ONLY)
def ping() -> dict[str, str]:
    """Health check: confirms the stock-data server is reachable."""
    return {"status": "ok", "server": "stock-data", "time": datetime.now(UTC).isoformat()}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
