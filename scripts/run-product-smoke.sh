#!/bin/bash
# 宿主 Terminal 薄入口：代理适配后仍由现有 launcher 执行 Council。
set -eu
if [ "${1:-}" = "--help" ]; then
  echo '用法：bash run-product-smoke.sh [新的外置产物目录]'
  echo '或：bash run-product-smoke.sh --prepared-run <已准备的运行目录> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --resume-multidimensional-run <已准备的多维运行目录> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --resume-multidimensional-task <已准备的多维运行目录> <task_name> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --stage common-stock-research --handoff <已确认Handoff> [--gate <冻结Gate> --data-preparation <准备清单> --source-bundle <来源包>] [--model <研究模型>] [--focus-security-id <证券ID>] <新的外置产物目录>'
  echo '或：bash run-product-smoke.sh --stage multidimensional-holding-research --handoff <已确认Handoff> [--gate <冻结Gate>] [--peer-candidates <冻结候选池>] [--model <研究模型>] [--company-research-run <已完成普通股研究运行>] <新的外置产物目录>'
  echo 'live 需 LIVE_SOURCE_ACCESS_FILE（外置已准入来源 JSON）与 SEC_USER_AGENT；可选 LIVE_CACHE_ROOT。'
  echo '在 macOS Terminal 中执行；默认 normal fixture，模型读取现有路由策略。'
  echo '仅限宿主产品执行；不创建项目沙箱。--review 已停用并明确拒绝。'
  exit 0
fi
for argument in "$@"; do
  case "$argument" in --review|--review=*) echo 'REVIEW_MODE_RETIRED：独立复核读取已有证据，不通过产品入口创建沙箱。' >&2; exit 2;; esac
done
if [ "${1:-}" = "--profile" ]; then
  echo 'LIVE_COUNCIL_ENTRY_RETIRED：请使用 --stage common-stock-research --handoff <已确认Handoff> 进入数据准备与持仓研究链路。' >&2
  exit 2
fi
prepared_run=
resume_multidimensional_run=
resume_multidimensional_task=
stage=full-council
stock_handoff=
stock_gate=
stock_data_preparation=
stock_source_bundle=
stock_model=
stock_focus_security_id=
company_research_run=
stock_peer_candidates=
if [ "${1:-}" = "--resume-multidimensional-run" ]; then
  if [ "$#" -ne 3 ]; then echo '--resume-multidimensional-run 需要已准备运行目录及新的调用产物目录。' >&2; exit 2; fi
  resume_multidimensional_run=$(cd "$2" && pwd -P)
  shift 2
fi
if [ "${1:-}" = "--resume-multidimensional-task" ]; then
  if [ "$#" -ne 4 ]; then echo '--resume-multidimensional-task 需要已准备运行目录、task_name 及新的调用产物目录。' >&2; exit 2; fi
  resume_multidimensional_run=$(cd "$2" && pwd -P)
  resume_multidimensional_task=$3
  shift 3
fi
if [ "${1:-}" = "--stage" ]; then
  if [ "$#" -lt 5 ] || { [ "$2" != "common-stock-research" ] && [ "$2" != "multidimensional-holding-research" ]; }; then
    echo 'RESEARCH_STAGE_ARGUMENTS_INVALID：使用 --help 查看研究阶段参数。' >&2; exit 2
  fi
  stage=$2
  shift 2
  while [ "$#" -gt 1 ]; do
    case "$1" in
      --handoff) stock_handoff=${2:-}; shift 2 ;;
      --gate) stock_gate=${2:-}; shift 2 ;;
      --data-preparation) stock_data_preparation=${2:-}; shift 2 ;;
      --source-bundle) stock_source_bundle=${2:-}; shift 2 ;;
      --model) stock_model=${2:-}; shift 2 ;;
      --focus-security-id) stock_focus_security_id=${2:-}; shift 2 ;;
      --company-research-run) company_research_run=${2:-}; shift 2 ;;
      --peer-candidates) stock_peer_candidates=${2:-}; shift 2 ;;
      *) echo 'RESEARCH_STAGE_ARGUMENTS_INVALID：使用 --help 查看研究阶段参数。' >&2; exit 2 ;;
    esac
  done
  if [ -z "$stock_handoff" ]; then
    echo 'COMMON_STOCK_HANDOFF_REQUIRED：缺少已确认 Handoff。' >&2; exit 2
  fi
  if [ "$stage" = "common-stock-research" ] && [ -n "$stock_gate" ] && { [ -z "$stock_data_preparation" ] || [ -z "$stock_source_bundle" ]; }; then
    echo 'COMMON_STOCK_DATA_PACKAGE_REQUIRED：外部 Gate 必须同时提供 data-preparation 与 source-bundle。' >&2; exit 2
  fi
fi
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
if [ -n "$resume_multidimensional_run" ]; then
  case "$resume_multidimensional_run/" in "$repo_root/"*) echo '已准备的产品运行目录必须位于源码之外。' >&2; exit 2;; esac
  echo "恢复宿主多维研究阶段；进度：$resume_multidimensional_run/invocation/codex-events.jsonl" >&2
  if [ -n "$resume_multidimensional_task" ]; then
    python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
      --repo "$repo_root" --run-dir "$resume_multidimensional_run" \
      --task-name "$resume_multidimensional_task"
  else
    python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
      --repo "$repo_root" --run-dir "$resume_multidimensional_run"
  fi
  exit $?
fi
if [ -z "$prepared_run" ]; then
model=$(python3 - "$repo_root" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import select_model
print(select_model(pathlib.Path(sys.argv[1]) / 'product', route='runtime_repeated'))
PY
)
if [ "$stage" = "common-stock-research" ] || [ "$stage" = "multidimensional-holding-research" ]; then
  if [ -n "$stock_model" ]; then
    model=$(python3 - "$repo_root" "$stock_model" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import select_product_runtime_model
print(select_product_runtime_model(pathlib.Path(sys.argv[1]) / 'product', requested_model=sys.argv[2]))
PY
)
  fi
  if [ -n "$stock_gate" ]; then
    run_id=$(python3 - "$stock_gate" <<'PY'
import json, re, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
run_id = value.get("run_id")
if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", run_id):
    raise SystemExit("RESEARCH_GATE_RUN_ID_INVALID")
print(run_id)
PY
)
  else
    run_id="host-common-stock-$(uuidgen | tr '[:upper:]' '[:lower:]')"
  fi
  if [ -z "$stock_gate" ]; then
    if [ -z "${LIVE_SOURCE_ACCESS_FILE:-}" ] || [ -z "${SEC_USER_AGENT:-}" ]; then
      echo 'COMMON_STOCK_SOURCE_CONFIGURATION_REQUIRED：自动准备公司资料需要外置来源配置和 SEC 联系身份。' >&2; exit 2
    fi
    if [ "$stage" = "multidimensional-holding-research" ]; then
      python3 "$repo_root/scripts/council-dev.py" collect-common-stock-data --repo "$repo_root" \
        --handoff "$stock_handoff" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
        --output-dir "$bundle/data" --cache-root "${LIVE_CACHE_ROOT:-$bundle/cache}" \
        --run-id "$run_id" --benchmark-id US:SPY --benchmark-ticker SPY
    else
      python3 "$repo_root/scripts/council-dev.py" collect-common-stock-data --repo "$repo_root" \
        --handoff "$stock_handoff" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
        --output-dir "$bundle/data" --cache-root "${LIVE_CACHE_ROOT:-$bundle/cache}" \
        --run-id "$run_id"
    fi
    stock_gate="$bundle/data/gate.json"
    stock_data_preparation="$bundle/data/data-preparation.json"
    stock_source_bundle="$bundle/data/source-bundle.json"
    if [ -f "$bundle/data/peer-candidate-pool.json" ]; then
      stock_peer_candidates="$bundle/data/peer-candidate-pool.json"
    fi
  fi
  if [ "$stage" = "multidimensional-holding-research" ]; then
    research_materials_run=
    if [ -n "$stock_peer_candidates" ]; then
      python3 "$repo_root/scripts/council-dev.py" prepare-research-materials --repo "$repo_root" \
        --handoff "$stock_handoff" --gate "$stock_gate" --peer-candidates "$stock_peer_candidates" \
        --run-dir "$bundle/materials-run" --run-id "$run_id" --model "$model"
      if python3 "$repo_root/scripts/council-dev.py" launch-research-materials \
        --repo "$repo_root" --run-dir "$bundle/materials-run"; then
        research_materials_run="$bundle/materials-run"
        if [ -n "${LIVE_SOURCE_ACCESS_FILE:-}" ] && [ -n "${SEC_USER_AGENT:-}" ]; then
          if python3 "$repo_root/scripts/council-dev.py" materialize-selected-peers \
            --materials-run "$research_materials_run" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
            --cache-root "${LIVE_CACHE_ROOT:-$bundle/cache}" \
            --output-dir "$research_materials_run/research/peer-materialization"; then
            if [ -f "$research_materials_run/research/peer-materialization/gate.json" ]; then
              stock_gate="$research_materials_run/research/peer-materialization/gate.json"
            fi
          else
            echo 'PEER_MATERIALIZATION_FAILED：保留失败产物，其他独立维度继续。' >&2
          fi
        else
          echo 'PEER_MATERIALIZATION_SOURCE_CONFIGURATION_MISSING：同行资料未核实，其他独立维度继续。' >&2
        fi
      else
        echo 'RESEARCH_MATERIALS_STAGE_FAILED：资料准备未形成合法清单，其他独立维度继续。' >&2
      fi
    else
      echo 'PEER_CANDIDATE_POOL_MISSING：未启动资料准备批次，正式阶段保留研报/同行缺口。' >&2
    fi
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-multidimensional-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --run-dir "$bundle/run" \
      --run-id "$run_id" --model "$model" --question '补全已确认普通股持仓的免费多维研究资料。'
    if [ -n "$stock_peer_candidates" ]; then
      set -- "$@" --peer-candidates "$stock_peer_candidates"
    fi
    if [ -n "$company_research_run" ]; then
      set -- "$@" --company-research-run "$company_research_run"
    fi
    if [ -n "$research_materials_run" ]; then
      set -- "$@" --research-materials-run "$research_materials_run"
    fi
  elif [ -n "$stock_data_preparation" ]; then
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --data-preparation "$stock_data_preparation" \
      --source-bundle "$stock_source_bundle" \
      --run-dir "$bundle/run" --run-id "$run_id" --model "$model" \
      --question '分析已确认的普通股持仓。'
  else
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --run-dir "$bundle/run" \
      --run-id "$run_id" --model "$model" --question '分析已确认的普通股持仓。'
  fi
  if [ -n "$stock_focus_security_id" ]; then
    if [ "$stage" = "multidimensional-holding-research" ]; then
      echo 'MULTIDIMENSIONAL_FOCUS_NOT_SUPPORTED：多维阶段必须保留当前全部普通股覆盖。' >&2; exit 2
    fi
    set -- "$@" --focus-security-id "$stock_focus_security_id"
  fi
  if [ -n "${EQUITY_RESEARCH_PACKAGE_FILE:-}" ]; then
    if [ "$stage" = "multidimensional-holding-research" ]; then
      echo 'EQUITY_RESEARCH_PACKAGE_STAGE_UNSUPPORTED：冻结估值附件只接入普通股公司研究阶段。' >&2; exit 2
    fi
    set -- "$@" --equity-research-package "$EQUITY_RESEARCH_PACKAGE_FILE"
  fi
  "$@"
  product_run="$bundle/run"
  echo "进入宿主研究阶段；进度：$product_run/invocation/codex-events.jsonl" >&2
  if [ "$stage" = "multidimensional-holding-research" ]; then
    python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
      --repo "$repo_root" --run-dir "$product_run"
  else
    python3 "$repo_root/scripts/council-dev.py" launch-common-stock-research \
      --repo "$repo_root" --run-dir "$product_run"
  fi
  exit $?
fi
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
