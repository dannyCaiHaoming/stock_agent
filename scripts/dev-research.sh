#!/usr/bin/env bash
# 开发调试：在指定宿主上无交互地跑一次个股研究，产物全部写入 .local/runs/<run-id>/。
#
# 用法：scripts/dev-research.sh <claude|codex> <TICKER> [--model MODEL] [--prompt "补充说明"]
# 默认模型（可用 --model 或环境变量覆盖）：
#   claude → $STOCK_AGENT_CLAUDE_MODEL，默认 claude-haiku-5-5
#   codex  → $STOCK_AGENT_CODEX_MODEL，默认 gpt-6-luna
# run.json 中 observed_model 是宿主实际报告的模型，用于核对映射。
# 运行目录内容：run.json（参数与结果）、transcript.*（宿主输出）、reports/、decisions.jsonl。
# 原始响应缓存共用 .local/cache/。
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
usage() { sed -n '2,10p' "$0"; exit 2; }
[ $# -ge 2 ] || usage
host="$1"; ticker="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"; shift 2
model=""; extra="我目前未持有。"
while [ $# -gt 0 ]; do
  case "$1" in
    --model) model="$2"; shift 2 ;;
    --prompt) extra="$2"; shift 2 ;;
    *) usage ;;
  esac
done
case "$host" in
  claude) model="${model:-${STOCK_AGENT_CLAUDE_MODEL:-claude-haiku-5-5}}" ;;
  codex) model="${model:-${STOCK_AGENT_CODEX_MODEL:-gpt-6-luna}}" ;;
  *) usage ;;
esac

run_id="$(date -u +%Y%m%dT%H%M%SZ)-${host}-${ticker}"
run_dir="$repo/.local/runs/$run_id"
mkdir -p "$run_dir"
prompt="研究 ${ticker}，按 stock-research Skill 的流程完成并给出建议。${extra}"
started="$(date -u +%FT%TZ)"
cd "$repo"

status=0
if [ "$host" = claude ]; then
  .venv/bin/python - "$run_dir" <<'PY'
import json, sys
run_dir = sys.argv[1]
config = json.load(open(".mcp.json"))
config["mcpServers"]["stock-data"].setdefault("env", {})["STOCK_AGENT_DATA_DIR"] = run_dir
json.dump(config, open(f"{run_dir}/mcp.json", "w"), indent=2)
PY
  claude -p "$prompt" --model "$model" \
    --mcp-config "$run_dir/mcp.json" --strict-mcp-config \
    --allowedTools "Skill" "Read" "Glob" "Grep" "mcp__stock-data__*" "Agent" "Task" \
      "Bash(curl:*)" "Bash(.venv/bin/python -I product/skills/moomoo-:*)" \
    --output-format stream-json --verbose \
    > "$run_dir/transcript.jsonl" 2> "$run_dir/stderr.log" || status=$?
else
  # workspace-write + [sandbox_workspace_write] network_access=true：允许 moomoo 公开 HTTP 与本机 OpenD 连接。
  codex exec --skip-git-repo-check -s workspace-write -m "$model" \
    -c "mcp_servers.stock_data.env.STOCK_AGENT_DATA_DIR=\"$run_dir\"" \
    "$prompt" < /dev/null > "$run_dir/transcript.log" 2>&1 || status=$?
fi

.venv/bin/python - "$run_dir" "$run_id" "$host" "$model" "$ticker" "$started" "$status" <<'PY'
import json, sys
from datetime import datetime, timezone
run_dir, run_id, host, model, ticker, started, status = sys.argv[1:]
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
record = {"run_id": run_id, "host": host, "model": model, "observed_model": observed, "ticker": ticker, "started_at": started,
          "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "exit_code": int(status),
          "decisions": [{k: d.get(k) for k in ("decision_id", "action", "confidence", "report_path")} for d in decisions]}
json.dump(record, open(f"{run_dir}/run.json", "w"), ensure_ascii=False, indent=2)
print(json.dumps(record, ensure_ascii=False, indent=2))
PY
exit "$status"
