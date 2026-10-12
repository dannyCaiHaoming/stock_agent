#!/bin/bash
# 正常研究使用当前原生宿主；仅保留显式冻结Replay与Tiger只读宿主入口。
set -eu
if [ "${1:-}" = "--help" ]; then
  echo '正常研究/Smoke：在当前Codex、Claude Code或OpenCode原生产品会话使用portfolio-council；另获样本、模型、预算和安装授权。'
  echo '旧维护：bash run-product-smoke.sh --prepared-run <已准备EXECUTION_REPLAY目录> <新的外置调用产物目录>'
  echo 'Tiger：bash run-product-smoke.sh --tiger-readonly <preflight|snapshot|sync|analyze> <对应参数>（严格只读，私人数据仅写外置ledger）'
  echo '旧normal、stage、resume及父进程串联已退役；不换宿主或恢复旧launcher。'
  exit 0
fi
for argument in "$@"; do
  case "$argument" in --review|--review=*) echo 'REVIEW_MODE_RETIRED：独立复核只读已有证据。' >&2; exit 2;; esac
  case "$argument" in --preflight-report|--preflight-report=*) echo 'LEGACY_SANDBOX_MODE_RETIRED' >&2; exit 2;; esac
done
if [ "${1:-}" = "--tiger-readonly" ]; then
  shift
  case "${1:-}" in
    preflight|snapshot|sync|analyze) ;;
    *) echo 'TIGER_READONLY_COMMAND_INVALID：只允许 preflight、snapshot、sync 或 analyze。' >&2; exit 2 ;;
  esac
  repo_root=$(cd "$(dirname "$0")/.." && pwd -P)
  export PYTHONDONTWRITEBYTECODE=1
  export STOCK_AGENT_TIGER_HOST_LAUNCH=1
  cd "$repo_root"
  exec python3 -m product.broker.tiger.cli "$@"
fi
if [ "${1:-}" != "--prepared-run" ]; then
  echo 'NATIVE_HOST_EXECUTION_REQUIRED：使用当前宿主portfolio-council原生会话；本脚本不创建正常研究模型进程。' >&2
  exit 2
fi
if [ "$#" -ne 3 ]; then echo 'FROZEN_EXECUTION_REPLAY_ARGUMENTS_REQUIRED' >&2; exit 2; fi
repo_root=$(cd "$(dirname "$0")/.." && pwd -P)
export PYTHONDONTWRITEBYTECODE=1
# 先验证原来源、封闭快照及冻结workspace，失败不探测代理或执行代码。
python3 "$repo_root/scripts/council-dev.py" check-frozen-replay --run-dir "$2"
prepared_run=$(cd "$2" && pwd -P)
bundle=$(python3 - "$3" "$repo_root" <<'PY'
from pathlib import Path
import sys
raw = Path(sys.argv[1]).expanduser().absolute()
if any(p.is_symlink() for p in (raw, *raw.parents)) or raw.resolve().is_relative_to(Path(sys.argv[2]).resolve()):
    sys.exit('REPLAY_OUTPUT_MUST_BE_EXTERNAL_AND_SAFE')
print(raw.resolve())
PY
)
mkdir -p "$bundle"
if [ -e "$bundle/host-proxy" ]; then echo '拒绝覆盖已有调用产物。' >&2; exit 2; fi
bash "$repo_root/scripts/detect-host-proxy.sh" "$bundle/host-proxy" > "$bundle/proxy.env"
mode=UNKNOWN
while IFS='=' read -r key value; do
  case "$key" in
    PROXY_MODE) mode=$value ;;
    HTTP_PROXY_URL) export HTTP_PROXY="$value" http_proxy="$value" ;;
    HTTPS_PROXY_URL) export HTTPS_PROXY="$value" https_proxy="$value" ;;
    ALL_PROXY_URL) export ALL_PROXY="$value" all_proxy="$value" ;;
  esac
done < "$bundle/proxy.env"
case "$mode" in
  UNKNOWN) echo 'PROXY_MODE=UNKNOWN；未执行冻结Replay。' >&2; exit 2 ;;
  SYSTEM_SOCKS_PROXY)
    codex doctor --json > "$bundle/socks-transport.json" 2> "$bundle/socks-transport.stderr" || exit 3
    python3 - "$bundle/socks-transport.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
checks = report.get('checks', {})
transport = checks.get('network.websocket_reachability', {}) if isinstance(checks, dict) else {}
if transport.get('status') != 'ok':
    sys.exit('SOCKS_TRANSPORT_NOT_VERIFIED：未执行冻结Replay。')
PY
    ;;
esac
launch_status=0
python3 "$repo_root/scripts/council-dev.py" execute-frozen-replay --run-dir "$prepared_run" || launch_status=$?
check_status=0
python3 "$repo_root/scripts/council-dev.py" check-run --run-dir "$prepared_run" || check_status=$?
if [ "$launch_status" -ne 0 ]; then exit "$launch_status"; fi
exit "$check_status"
