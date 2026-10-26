#!/usr/bin/env bash
# 前瞻纸面预测每日入口（供 Codex 定时任务调用，不安装任何 launchd/cron）：
# 选股并写入账本 → 对尚未记录的代码依次跑 dev-research.sh codex → forward-record → 日志。
# 用法：scripts/forward-run.sh [--date YYYY-MM-DD]（默认纽约今天；只用于补跑当天，不要用于回填历史）
# 每只股票失败后自动重试一次（两次尝试都记入账本，失败可见）。
# 错误即时报告：以 FORWARD_ERROR 开头写到 stderr、forward-run.log 与 forward-errors.log，并尝试发送 macOS 通知；结束时汇总。
# 退出码：0 全部成功；1 有股票两次都失败或选股失败。日志：.local/data/history/forward-run.log。
set -uo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
mkdir -p .local/data/history
log=".local/data/history/forward-run.log"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$log"; }
errors=()
err() {
  local msg="FORWARD_ERROR $*"
  echo "$(date -u +%FT%TZ) $msg" | tee -a "$log" .local/data/history/forward-errors.log >&2
  errors+=("$msg")
  osascript -e "display notification \"$(printf '%s' "$*" | tr -d '"\\' | cut -c1-200)\" with title \"stock_agent 前瞻记录出错\"" >/dev/null 2>&1 || true
}
date_args=("$@")

sel="$(.venv/bin/python -I scripts/forward-select.py --write ${date_args[@]+"${date_args[@]}"} 2>>"$log")" || { err "select failed (see $log)"; exit 1; }
sel_date="$(printf '%s' "$sel" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["date"])')"
todo="$(printf '%s' "$sel" | .venv/bin/python -c 'import json,sys; print(" ".join(json.load(sys.stdin)["todo"]))')"
say "== $sel_date todo: ${todo:-none}"

failed=0
attempt() {  # $1 ticker, $2 attempt number; sets last_kind (runs in this shell so errors[] is kept)
  local t="$1" n="$2" out rc run_id rec kind
  last_kind=none
  say "research $t attempt $n start"
  out="$(scripts/dev-research.sh codex "$t" --tag "forward$n" 2>>"$log")"; rc=$?
  run_id="$(printf '%s' "$out" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' 2>/dev/null)"
  [ -n "$run_id" ] || run_id="$(ls -1t .local/runs | grep -- "-codex-$t-forward$n\$" | head -1)"
  if [ -z "$run_id" ]; then err "$sel_date $t attempt $n: no run dir (rc=$rc)"; return; fi
  rec="$(.venv/bin/python -I scripts/forward-record.py ".local/runs/$run_id" --date "$sel_date" 2>>"$log")"
  kind="$(printf '%s' "$rec" | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("kind","?"), d.get("status",""))' 2>/dev/null)"
  say "$t attempt $n rc=$rc record: $rec"
  [ "${kind%% *}" = prediction ] || err "$sel_date $t attempt $n: ${kind:-record failed} (run $run_id, rc=$rc)"
  last_kind="${kind%% *}"
}
for t in $todo; do
  attempt "$t" 1; [ "$last_kind" = prediction ] && continue
  say "$t retrying once"
  attempt "$t" 2; [ "$last_kind" = prediction ] && continue
  err "$sel_date $t failed twice, no prediction recorded today"
  failed=1
done
if [ ${#errors[@]} -gt 0 ]; then
  say "== errors (${#errors[@]}):"; for e in "${errors[@]}"; do say "   $e"; done
fi
say "== done failed=$failed"
exit "$failed"
