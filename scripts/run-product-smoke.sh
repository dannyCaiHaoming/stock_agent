#!/bin/bash
# 宿主 Terminal 薄入口：代理适配后仍由现有 launcher 执行 Council。
set -eu
if [ "${1:-}" = "--help" ]; then
  echo '用法：bash run-product-smoke.sh [新的外置产物目录]'
  echo '或：bash run-product-smoke.sh --prepared-run <已准备的运行目录> <新的外置调用产物目录>'
  echo '在 macOS Terminal 中执行；默认 normal fixture，模型读取现有路由策略。'
  echo '仅限宿主产品执行；不创建项目沙箱。--review 已停用并明确拒绝。'
  exit 0
fi
for argument in "$@"; do
  case "$argument" in --review|--review=*) echo 'REVIEW_MODE_RETIRED：独立复核读取已有证据，不通过产品入口创建沙箱。' >&2; exit 2;; esac
done
prepared_run=
if [ "${1:-}" = "--prepared-run" ]; then
  if [ "$#" -ne 3 ]; then echo '--prepared-run 需要运行目录及新的调用产物目录。' >&2; exit 2; fi
  prepared_run=$(cd "$2" && pwd -P)
  shift 2
fi
if [ "$#" -gt 1 ]; then echo '参数过多；使用 --help 查看用法。' >&2; exit 2; fi
repo_root=$(cd "$(dirname "$0")/.." && pwd -P)
bundle=${1:-$(mktemp -d "${TMPDIR:-/tmp}/stock-agent-product-smoke.XXXXXX")}
mkdir -p "$bundle"
bundle=$(cd "$bundle" && pwd -P)
case "$bundle/" in "$repo_root/"*) echo '产物目录必须位于源码之外。' >&2; exit 2;; esac
if [ -e "$bundle/run" ] || [ -e "$bundle/host-proxy" ]; then
  echo '拒绝覆盖已有运行，请使用新目录。' >&2; exit 2
fi
bash "$repo_root/scripts/detect-host-proxy.sh" "$bundle/host-proxy" > "$bundle/proxy.env"
# 不 source/eval 检测输出，只接受明确字段。
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
  UNKNOWN) echo 'PROXY_MODE=UNKNOWN；缺少有效系统代理或已连接 VPN 证据，未启动模型。' >&2; exit 2 ;;
  SYSTEM_SOCKS_PROXY)
    # SOCKS 必须先通过现有 Codex transport 诊断，不猜测 HTTP 端口。
    codex doctor --json > "$bundle/socks-transport.json" 2> "$bundle/socks-transport.stderr" || exit 3
    python3 - "$bundle/socks-transport.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
checks = report.get('checks', {})
transport = checks.get('network.websocket_reachability', {}) if isinstance(checks, dict) else {}
if transport.get('status') != 'ok':
    sys.exit('SOCKS_TRANSPORT_NOT_VERIFIED：未启动 Council，不转换代理协议。')
PY
    ;;
esac
export PYTHONDONTWRITEBYTECODE=1
if [ -z "$prepared_run" ]; then
model=$(python3 - "$repo_root" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import select_model
print(select_model(pathlib.Path(sys.argv[1]) / 'product', route='runtime_repeated'))
PY
)
run_id="host-normal-$(uuidgen | tr '[:upper:]' '[:lower:]')"
python3 "$repo_root/scripts/council-dev.py" prepare --repo "$repo_root" \
  --fixture "$repo_root/evals/fixtures/codex-native/normal-research.json" \
  --run-dir "$bundle/run" --run-id "$run_id" --model "$model" \
  --question '基于 fixture 的 PIT Evidence 完成只读组合研究，遵守现有 Council 与 Risk 契约。'
product_run="$bundle/run"
else
  product_run=$prepared_run
fi
launch_status=0
echo "进入宿主产品模式（全进程隔离 UNVERIFIED）；进度：$product_run/invocation/codex-events.jsonl" >&2
# 不强制传当前 repo；既有转发器从 Execution Replay manifest 选择冻结根。
python3 "$repo_root/scripts/council-dev.py" nested-codex-smoke \
  --run-dir "$product_run" || launch_status=$?
check_status=0
python3 "$repo_root/scripts/council-dev.py" check-run --run-dir "$product_run" || check_status=$?
if [ "$launch_status" -ne 0 ]; then exit "$launch_status"; fi
exit "$check_status"
