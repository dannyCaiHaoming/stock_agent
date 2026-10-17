#!/usr/bin/env bash
# 历史回放对照实验：同一批样本用不同宿主或流程变体跑回放研究（不做事后复盘），
# 结果索引写入 evals/replay/ablation/<起始日>-<宿主>-<变体>.json（样本 → run_id）。
#
# 用法：scripts/replay-ablation.sh <起始日> <claude|codex> <full|solo> [--parallel N] [--model M]
#   full：完整流程（advocate、skeptic、论证审查）
#   solo：单人对照（不启动子 Agent、不做论证审查，其余步骤与决策规则不变）
set -euo pipefail

SOLO_PROMPT="我目前未持有。本次是单人对照实验：不要启动 advocate、skeptic 子 Agent，也不做第 6 步论证审查；第 1 步的正向与反向研究由你自己完成（论点表来源写“自检”），其余步骤、历史教训对照与决策规则不变。报告“论证审查”一节写“单人对照实验，未做”。"

main() {

repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

if [ "${1:-}" = "_one" ]; then
  shift
  local start="$1" host="$2" variant="$3" model="$4" ticker="$5"
  local args=(--as-of "$start" --tag "$variant")
  [ "$model" = "-" ] || args+=(--model "$model")
  [ "$variant" = solo ] && args+=(--prompt "$SOLO_PROMPT")
  local log
  log="$(scripts/dev-research.sh "$host" "$ticker" "${args[@]}" 2>&1 || true)"
  printf '%s' "$log" | .venv/bin/python -c 'import json,sys; t=sys.stdin.read(); r=json.loads(t[t.index("{"):]); print(r["ticker"], r["run_id"])' 2>/dev/null \
    || echo "$ticker FAIL"
  return
fi

[ $# -ge 3 ] || { sed -n '2,8p' "$0"; exit 2; }
start="$1"; host="$2"; variant="$3"; shift 3
parallel=3; model="-"
while [ $# -gt 0 ]; do
  case "$1" in
    --parallel) parallel="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    *) sed -n '2,8p' "$0"; exit 2 ;;
  esac
done
case "$variant" in full|solo) ;; *) sed -n '2,8p' "$0"; exit 2 ;; esac
cases="evals/replay/cases/$start.json"
out="evals/replay/ablation/$start-$host-$variant.json"
mkdir -p "$(dirname "$out")"

.venv/bin/python -c 'import json,sys; d=json.load(open(sys.argv[1])); [print(i["ticker"]) for g in d["groups"].values() for i in g]' "$cases" \
  | xargs -P "$parallel" -I{} bash "$0" _one "$start" "$host" "$variant" "$model" {} \
  | .venv/bin/python -c 'import json,sys; print(json.dumps(dict(l.split() for l in sys.stdin if l.strip()), indent=2))' > "$out"
cat "$out"
}

main "$@"
