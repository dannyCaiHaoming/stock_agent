#!/usr/bin/env bash
# 每日新闻存档入口（供定时任务调用）：在仓库根目录用 .venv 运行 snapshot-news.py，日志追加到 .local/data/history/news-run.log。
# 退出码：0 全部成功；1 有失败（详情见日志）。同日已完成的代码会跳过，可直接重跑补缺。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
mkdir -p .local/data/history
log=".local/data/history/news-run.log"
echo "== $(date -u +%FT%TZ) start" >> "$log"
rc=0
out="$(.venv/bin/python -I scripts/snapshot-news.py "$@" 2>&1)" || rc=$?
echo "$out" >> "$log"
echo "$out"
exit "$rc"
