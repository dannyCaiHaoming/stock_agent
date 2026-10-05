#!/bin/sh
# 由宿主 launcher 绑定解释器；避免 Codex 子 Agent 依赖受限 PATH。
set -eu

case "${STOCK_AGENT_FIXTURE_MCP_PYTHON:-}" in
  /*) ;;
  *) echo 'FIXTURE_MCP_PYTHON_NOT_BOUND' >&2; exit 126 ;;
esac
case "${STOCK_AGENT_FIXTURE_MCP_PYTHONPATH:-}" in
  /*) ;;
  *) echo 'FIXTURE_MCP_PYTHONPATH_NOT_BOUND' >&2; exit 126 ;;
esac

[ -x "$STOCK_AGENT_FIXTURE_MCP_PYTHON" ] || {
  echo 'FIXTURE_MCP_PYTHON_NOT_EXECUTABLE' >&2
  exit 126
}
export PYTHONPATH="$STOCK_AGENT_FIXTURE_MCP_PYTHONPATH"
"$STOCK_AGENT_FIXTURE_MCP_PYTHON" -c 'import jsonschema' >/dev/null 2>&1 || {
  echo 'FIXTURE_MCP_DEPENDENCY_UNAVAILABLE:jsonschema' >&2
  exit 126
}
exec "$STOCK_AGENT_FIXTURE_MCP_PYTHON" -m runtime.fixture_mcp "$@"
