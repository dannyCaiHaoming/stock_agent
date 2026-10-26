#!/usr/bin/env bash
# 前瞻纸面预测每日入口（供 Codex 定时任务调用，不安装任何 launchd/cron）：
# 选股并写入账本 → 对尚未记录的代码依次跑 dev-research.sh codex → forward-record → 日志。
# 用法：scripts/forward-run.sh [--date YYYY-MM-DD]（默认纽约今天；只用于补跑当天，不要用于回填历史）
# 退出码：0 全部成功；1 有失败（失败也已记入账本）。日志：.local/data/history/forward-run.log。
set -uo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
mkdir -p .local/data/history
log=".local/data/history/forward-run.log"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$log"; }
date_args=("$@")

sel="$(.venv/bin/python -I scripts/forward-select.py --write ${date_args[@]+"${date_args[@]}"} 2>>"$log")" || { say "select failed"; exit 1; }
sel_date="$(printf '%s' "$sel" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["date"])')"
todo="$(printf '%s' "$sel" | .venv/bin/python -c 'import json,sys; print(" ".join(json.load(sys.stdin)["todo"]))')"
say "== $sel_date todo: ${todo:-none}"

failed=0
for t in $todo; do
  say "research $t start"
  out="$(scripts/dev-research.sh codex "$t" --tag forward 2>>"$log")"; rc=$?
  run_id="$(printf '%s' "$out" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' 2>/dev/null)"
  [ -n "$run_id" ] || run_id="$(ls -1t .local/runs | grep -- "-codex-$t-forward\$" | head -1)"
  if [ -z "$run_id" ]; then say "$t no run dir (rc=$rc)"; failed=1; continue; fi
  rec="$(.venv/bin/python -I scripts/forward-record.py ".local/runs/$run_id" --date "$sel_date" 2>>"$log")" || failed=1
  say "$t rc=$rc record: $rec"
done
say "== done failed=$failed"
exit "$failed"
