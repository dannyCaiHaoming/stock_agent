"""建立众议院议员交易申报（PTR）索引，供 get_congress_trades 使用。

用法：.venv/bin/python -I scripts/build-house-ptr-index.py 2023 2024 2025 2026
索引写入共享缓存目录 .local/cache/derived/house-ptr/<年>.json；已解析的申报不会重复下载。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):  # same contact as the MCP server config
    import json
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import congress_tools  # noqa: E402

for year in [int(y) for y in sys.argv[1:]]:
    print(congress_tools.update_index(year))
