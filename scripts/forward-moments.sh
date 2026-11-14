#!/usr/bin/env bash
# 前瞻消息面概率：最近 N 个交易日内出现关键时刻、且个股明显偏离板块的股票，逐个跑 moment-review（Codex，联网检索），
# 结果追加到 evals/forward/moment-ledger.jsonl（只追加；失败也记录；已有记录的时刻跳过）。建议每周五收盘后运行。
# 用法：scripts/forward-moments.sh [--days 5] [--model M]
# 每个时刻失败后重试一次。日志：.local/data/history/forward-moments.log。退出码：0 全部成功，1 有失败。
# 评分与判定见 evals/forward/README.md。
set -uo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"; cd "$repo"
model="${STOCK_AGENT_CODEX_MODEL:-gpt-6.1-terra}"; days=5
while [ $# -gt 0 ]; do
  case "$1" in
    --model) model="$2"; shift 2 ;;
    --days) days="$2"; shift 2 ;;
    *) sed -n '2,6p' "$0"; exit 2 ;;
  esac
done
mkdir -p .local/data/history
log=".local/data/history/forward-moments.log"; ledger="evals/forward/moment-ledger.jsonl"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$log"; }
failed=0; n=0
while IFS=$'\t' read -r ticker moment day z; do
  [ -n "$ticker" ] || continue
  ok=0
  for attempt in 1 2; do
    say "moment $ticker $moment $day attempt $attempt start"
    scripts/dev-research.sh codex "$ticker" --as-of "$day" --moment "$moment" --model "$model" --tag "fwdmoment$attempt" >/dev/null 2>>"$log"; rc=$?
    run_dir="$(ls -1dt .local/runs/*-codex-"$ticker"-asof"$day"-fwdmoment"$attempt" 2>/dev/null | head -1)"
    .venv/bin/python -I - "$run_dir" "$ticker" "$moment" "$day" "$z" "$rc" "$ledger" <<'PY' >>"$log" 2>&1 && ok=1
import json, os, sys
from datetime import datetime, timezone
run_dir, ticker, moment, day, z, rc, ledger = sys.argv[1:]
line = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ticker": ticker, "moment": moment,
        "moment_date": day, "deviation_vs_sector": float(z), "run_id": os.path.basename(run_dir) if run_dir else None,
        "exit_code": int(rc)}
record = None
try:
    record = [json.loads(x) for x in open(f"{run_dir}/moment_reviews.jsonl") if x.strip()][-1]
    line["observed_model"] = json.load(open(f"{run_dir}/run.json")).get("observed_model")
except (FileNotFoundError, IndexError, ValueError):
    pass
if record and (record["ticker"], record["moment"], record["moment_date"]) == (ticker, moment, day):
    line.update(kind="moment_review", status="ok", **{k: record.get(k) for k in (
        "review_id", "primary_cause", "other_causes", "cause_public_by_close", "confidence", "holder_action",
        "p_outperform_60d", "summary", "lesson", "items", "decided_at", "model", "code_version")})
else:
    line.update(kind="failure", status="moment_mismatch" if record else "no_review_saved")
fd = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
os.write(fd, (json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n").encode()); os.close(fd)
print(line["kind"], line["status"], ticker, moment, day)
sys.exit(0 if line["kind"] == "moment_review" else 1)
PY
    [ "$ok" = 1 ] && break
  done
  n=$((n + 1))
  [ "$ok" = 1 ] || { failed=1; say "FORWARD_ERROR moment $ticker $moment $day failed twice"; }
done < <(.venv/bin/python -I scripts/sample-idiosyncratic-moments.py --recent "$days" 2>>"$log" | .venv/bin/python -I -c '
import json, os, sys
done = set()
if os.path.exists(sys.argv[1]):
    for line in open(sys.argv[1]):
        r = json.loads(line)
        if r.get("kind") == "moment_review":
            done.add((r["ticker"], r["moment_date"]))
for x in json.load(sys.stdin):  # 同一只股票同一天触发多个时刻时只复盘第一个
    if (x["ticker"], x["date"]) not in done:
        done.add((x["ticker"], x["date"]))
        print(x["ticker"], x["moment"], x["date"], x["deviation_vs_sector"], sep="\t")
' "$ledger")
say "== done moments=$n failed=$failed"
exit "$failed"
