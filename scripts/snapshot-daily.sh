#!/usr/bin/env bash
# 每日快照入口（供定时任务调用）：在仓库根目录用 .venv 运行 snapshot-daily.py，日志追加到 .local/data/history/snapshot-run.log。
# 退出码：0 全部成功；1 有代码失败（详情见日志与 snapshot-log.jsonl）。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
mkdir -p .local/data/history
log=".local/data/history/snapshot-run.log"
echo "== $(date -u +%FT%TZ) start" >> "$log"
out="$(.venv/bin/python -I scripts/snapshot-daily.py "$@" 2>&1)" || { echo "$out" >> "$log"; echo "$out"; exit 1; }
echo "$out" >> "$log"
echo "$out"
printf '%s' "$out" | .venv/bin/python -c 'import json,sys; d=json.loads(sys.stdin.read()); sys.exit(1 if any(v["failed"] for v in d.values()) else 0)'
