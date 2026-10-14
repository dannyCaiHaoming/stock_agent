#!/usr/bin/env bash
# 开发调试：在指定宿主上无交互地跑一次个股研究，产物全部写入 .local/runs/<run-id>/。
#
# 用法：scripts/dev-research.sh <claude|codex> <TICKER> [--model MODEL] [--prompt "补充说明"] [--as-of YYYY-MM-DD]
# --as-of：历史回放。工具固定在该日期，只有当前数据的工具与 moomoo 被禁用。
# 默认模型（可用 --model 或环境变量覆盖）：
#   claude → $STOCK_AGENT_CLAUDE_MODEL，默认 claude-haiku-5-5
#   codex  → $STOCK_AGENT_CODEX_MODEL，默认 gpt-6-luna
# run.json 中 observed_model 是宿主实际报告的模型，用于核对映射。
# 运行目录内容：run.json（参数与结果）、transcript.*（宿主输出）、reports/、decisions.jsonl。
# 原始响应缓存共用 .local/cache/。
set -euo pipefail

# 整个流程放在函数里：bash 先读完整个文件再执行，运行中修改脚本不会破坏正在进行的运行。
main() {

repo="$(cd "$(dirname "$0")/.." && pwd)"
usage() { sed -n '2,11p' "$0"; exit 2; }
[ $# -ge 2 ] || usage
host="$1"; ticker="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"; shift 2
model=""; extra="我目前未持有。"; as_of=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) model="$2"; shift 2 ;;
    --prompt) extra="$2"; shift 2 ;;
    --as-of) as_of="$2"; shift 2 ;;
    *) usage ;;
  esac
done
case "$host" in
  claude) model="${model:-${STOCK_AGENT_CLAUDE_MODEL:-claude-haiku-5-5}}" ;;
  codex) model="${model:-${STOCK_AGENT_CODEX_MODEL:-gpt-6-luna}}" ;;
  *) usage ;;
esac

run_id="$(date -u +%Y%m%dT%H%M%SZ)-${host}-${ticker}${as_of:+-asof$as_of}"
run_dir="$repo/.local/runs/$run_id"
mkdir -p "$run_dir"
prompt="研究 ${ticker}，按 stock-research Skill 的流程完成并给出建议。${extra}"
if [ -n "$as_of" ]; then
  [[ "$as_of" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || usage
  prompt="研究 ${ticker}，历史回放模式：数据截至 ${as_of}，把 ${as_of} 当作今天，按 stock-research Skill 的回放规则完成并给出建议。${extra}"
fi
started="$(date -u +%FT%TZ)"
cd "$repo"

status=0
if [ "$host" = claude ]; then
  .venv/bin/python - "$run_dir" "$as_of" <<'PY'
import json, sys
run_dir = sys.argv[1]
config = json.load(open(".mcp.json"))
env = config["mcpServers"]["stock-data"].setdefault("env", {})
env["STOCK_AGENT_DATA_DIR"] = run_dir
if sys.argv[2]:
    env["STOCK_AGENT_REPLAY_AS_OF"] = sys.argv[2]
json.dump(config, open(f"{run_dir}/mcp.json", "w"), indent=2)
PY
  # dontAsk: anything not listed below is denied instead of falling back to the user's default mode.
  # curl is limited to the moomoo Skill form and may only print to stdout. Replay runs get no Bash at all
  # (moomoo only returns current data).
  bash_tools=("Bash(curl -sG 'https://ai-news-search.moomoo.com/*)" "Bash(.venv/bin/python -I product/skills/moomoo-*)")
  [ -z "$as_of" ] || bash_tools=()
  claude -p "$prompt" --model "$model" --permission-mode dontAsk \
    --mcp-config "$run_dir/mcp.json" --strict-mcp-config \
    --allowedTools "Skill" "Read" "Glob" "Grep" "ToolSearch" "mcp__stock-data__*" "Agent" "Task" ${bash_tools[@]+"${bash_tools[@]}"} \
    --disallowedTools "Bash(curl * -o *)" "Bash(curl * --output *)" \
    --output-format stream-json --verbose \
    > "$run_dir/transcript.jsonl" 2> "$run_dir/stderr.log" || status=$?
else
  # workspace-write + [sandbox_workspace_write] network_access=true：允许 moomoo 公开 HTTP 与本机 OpenD 连接。
  # 调试运行不读取、也不生成 Codex 全局记忆（~/.codex/memories 含旧项目规则）。
  # 回放：MCP 固定在 as_of，并关闭沙箱网络（moomoo 只有当前数据）。
  replay_args=()
  [ -z "$as_of" ] || replay_args=(-c "mcp_servers.stock_data.env.STOCK_AGENT_REPLAY_AS_OF=\"$as_of\"" -c sandbox_workspace_write.network_access=false)
  codex exec --skip-git-repo-check -s workspace-write -m "$model" \
    -c memories.use_memories=false -c memories.generate_memories=false \
    -c "mcp_servers.stock_data.env.STOCK_AGENT_DATA_DIR=\"$run_dir\"" ${replay_args[@]+"${replay_args[@]}"} \
    "$prompt" < /dev/null > "$run_dir/transcript.log" 2>&1 || status=$?
fi

.venv/bin/python - "$run_dir" "$run_id" "$host" "$model" "$ticker" "$started" "$status" "$as_of" <<'PY'
import json, sys
from datetime import datetime, timezone
run_dir, run_id, host, model, ticker, started, status, as_of = sys.argv[1:]
observed = None
try:
    if host == "claude":
        for line in open(f"{run_dir}/transcript.jsonl"):
            event = json.loads(line)
            if event.get("type") == "system" and event.get("subtype") == "init":
                observed = event.get("model")
                break
    else:
        for line in open(f"{run_dir}/transcript.log"):
            if line.startswith("model:"):
                observed = line.split(":", 1)[1].strip()
                break
except (FileNotFoundError, json.JSONDecodeError):
    pass
decisions = []
try:
    decisions = [json.loads(line) for line in open(f"{run_dir}/decisions.jsonl")]
except FileNotFoundError:
    pass
record = {"run_id": run_id, "host": host, "model": model, "observed_model": observed, "ticker": ticker,
          "replay_as_of": as_of or None, "started_at": started,
          "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "exit_code": int(status),
          "decisions": [{k: d.get(k) for k in ("decision_id", "action", "confidence", "report_path")} for d in decisions]}
json.dump(record, open(f"{run_dir}/run.json", "w"), ensure_ascii=False, indent=2)
print(json.dumps(record, ensure_ascii=False, indent=2))
PY
exit "$status"
}

main "$@"
