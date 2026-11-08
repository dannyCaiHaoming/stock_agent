#!/usr/bin/env bash
# 每日数据采集合并入口（纯 Python，不调用 LLM）：预期与社区快照 → 新闻存档。
# 供定时任务一次触发，只输出一行汇总，减少触发方需要读取的内容。
# 用法：scripts/collect-daily.sh   退出码：0 全部成功；1 有失败（详情见日志）。
# 日志：.local/data/history/snapshot-run.log、.local/data/history/news-run.log
set -uo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
scripts/snapshot-daily.sh >/dev/null 2>&1; snap=$?
scripts/snapshot-news.sh >/dev/null 2>&1; news=$?
status=$(( snap != 0 || news != 0 ))
echo "$(date -u +%FT%TZ) collect-daily snapshot=$([ $snap = 0 ] && echo ok || echo FAILED) news=$([ $news = 0 ] && echo ok || echo FAILED)"
exit "$status"
