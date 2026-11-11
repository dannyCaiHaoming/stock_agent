#!/usr/bin/env bash
# 前瞻组内方向预测（轻量）：对 evals/replay/universe.txt 的每个组跑一次 direction-forecast，
# 结果追加到 evals/forward/group-ledger.jsonl（只追加；失败也记录）。建议每周一次，周五收盘后运行。
# 用法：scripts/forward-groups.sh [--model M] [--only "组名片段"]
# 每组失败后重试一次。日志：.local/data/history/forward-groups.log。退出码：0 全部成功，1 有组失败。
# 评分：scripts/score-group-forecasts.py（读运行目录）；账本用于冻结“当时的预测”，以 git 提交时间为证。
set -uo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"; cd "$repo"
model="${STOCK_AGENT_CODEX_MODEL:-gpt-6-luna}"; only=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) model="$2"; shift 2 ;;
    --only) only="$2"; shift 2 ;;
    *) sed -n '2,6p' "$0"; exit 2 ;;
  esac
done
mkdir -p .local/data/history
log=".local/data/history/forward-groups.log"; ledger="evals/forward/group-ledger.jsonl"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$log"; }
failed=0; n=0
# 组名取注释行的第一个词（G01、G02… 作前缀，保证唯一且可作目录名）。
while IFS=$'\t' read -r label tickers; do
  [ -z "$only" ] || [[ "$label" == *"$only"* ]] || continue
  ok=0
  for attempt in 1 2; do
    say "group $label attempt $attempt start"
    scripts/dev-research.sh codex "$label" --group "$tickers" --model "$model" --tag "fwdgroup$attempt" >/dev/null 2>>"$log"; rc=$?
    run_dir="$(ls -1dt .local/runs/*-codex-"$label"-fwdgroup"$attempt" 2>/dev/null | head -1)"
    .venv/bin/python -I - "$run_dir" "$label" "$tickers" "$rc" "$ledger" <<'PY' >>"$log" 2>&1 && ok=1
import json, os, sys
from datetime import datetime, timezone
run_dir, label, tickers, rc, ledger = sys.argv[1:]
want = sorted(tickers.split())
line = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "group": label, "tickers": want,
        "run_id": os.path.basename(run_dir) if run_dir else None, "exit_code": int(rc)}
record = None
try:
    record = [json.loads(x) for x in open(f"{run_dir}/group_forecasts.jsonl") if x.strip()][-1]
except (FileNotFoundError, IndexError):
    pass
if record and sorted(x["ticker"] for x in record["forecasts"]) == want:
    line.update(kind="group_forecast", status="ok", **{k: record[k] for k in (
        "forecast_id", "data_as_of", "decided_at", "horizon_days", "target", "forecasts", "model", "code_version")})
else:
    line.update(kind="failure", status="tickers_mismatch" if record else "no_forecast_saved")
fd = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
os.write(fd, (json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n").encode()); os.close(fd)
print(line["kind"], line["status"], label)
sys.exit(0 if line["kind"] == "group_forecast" else 1)
PY
    [ "$ok" = 1 ] && break
  done
  n=$((n + 1))
  [ "$ok" = 1 ] || { failed=1; say "FORWARD_ERROR group $label failed twice"; }
done < <(awk '/^#/ {next} NF {i++; printf "G%02d\t%s\n", i, $0}' evals/replay/universe.txt)
say "== done groups=$n failed=$failed"
exit "$failed"
