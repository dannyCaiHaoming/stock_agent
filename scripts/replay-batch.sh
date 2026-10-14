#!/usr/bin/env bash
# 历史回放批量运行：对 evals/replay/cases/<起始日>.json 的每个样本，先做回放研究（不告诉模型组别），
# 再做事后复盘（case-review Skill），复盘结果写入 evals/replay/reviews/<起始日>/<TICKER>.md。
#
# 用法：scripts/replay-batch.sh <起始日> [--parallel N] [--only TICKER,...]
# 只用 Codex（模型同 dev-research.sh 默认：$STOCK_AGENT_CODEX_MODEL 或 gpt-6-luna）。
set -euo pipefail

main() {

repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

if [ "${1:-}" = "_one" ]; then
  one "$2" "$3" "$4" "$5"
  return
fi

[ $# -ge 1 ] || { sed -n '2,7p' "$0"; exit 2; }
start="$1"; shift
parallel=3; only=""
while [ $# -gt 0 ]; do
  case "$1" in
    --parallel) parallel="$2"; shift 2 ;;
    --only) only="$2"; shift 2 ;;
    *) sed -n '2,7p' "$0"; exit 2 ;;
  esac
done
cases="evals/replay/cases/$start.json"
[ -f "$cases" ] || { echo "missing $cases (run scripts/select-replay-cases.py $start)"; exit 2; }
mkdir -p "evals/replay/reviews/$start"

.venv/bin/python - "$cases" "$only" <<'PY' | xargs -P "$parallel" -L 1 bash "$0" _one
import json, sys
data = json.load(open(sys.argv[1]))
only = {t for t in sys.argv[2].split(",") if t}
for group, items in data["groups"].items():
    for item in items:
        if not only or item["ticker"] in only:
            print(data["start"], item["ticker"], group, item["excess_pct"])
PY
}

one() {
  local start="$1" ticker="$2" group="$3" excess="$4"
  local review="evals/replay/reviews/$start/$ticker.md"
  [ -s "$review" ] && { echo "skip $ticker (already reviewed)"; return; }
  local log
  log="$(scripts/dev-research.sh codex "$ticker" --as-of "$start" 2>&1 || true)"
  local run_dir report
  run_dir="$(printf '%s' "$log" | .venv/bin/python -c 'import json,sys; t=sys.stdin.read(); print(json.loads(t[t.index("{"):])["run_id"])' 2>/dev/null || true)"
  [ -n "$run_dir" ] || { echo "FAIL research $ticker"; return; }
  run_dir=".local/runs/$run_dir"
  report="$(ls -t "$run_dir"/reports/*/*.md 2>/dev/null | head -1 || true)"
  [ -n "$report" ] || { echo "FAIL no report $ticker ($run_dir)"; return; }
  local model="${STOCK_AGENT_CODEX_MODEL:-gpt-6-luna}"
  codex exec --skip-git-repo-check -s workspace-write -m "$model" \
    -c memories.use_memories=false -c memories.generate_memories=false \
    -c "mcp_servers.stock_data.env.STOCK_AGENT_DATA_DIR=\"$repo/$run_dir\"" \
    -o "$repo/$review" \
    "按 case-review Skill 复盘这次历史回放：报告 $report，回放日期 $start，代码 $ticker，组别 $group，之后 252 个交易日相对 SPY 超额收益 ${excess}%。只输出复盘 Markdown。" \
    < /dev/null > "$run_dir/review.log" 2>&1 || echo "FAIL review $ticker"
  echo "done $ticker -> $review"
}

main "$@"
