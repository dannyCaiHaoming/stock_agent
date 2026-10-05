#!/bin/bash
# 宿主 Terminal 薄入口：代理适配后仍由现有 launcher 执行 Council。
set -eu
if [ "${1:-}" = "--help" ]; then
  echo '用法：bash run-product-smoke.sh [新的外置产物目录]'
  echo '或：bash run-product-smoke.sh --prepared-run <已准备的运行目录> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --resume-multidimensional-run <已准备的多维运行目录> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --resume-multidimensional-task <已准备的多维运行目录> <task_name> <新的外置调用产物目录>（自动包含最小依赖闭包）'
  echo '或：bash run-product-smoke.sh --start-multidimensional-task <全新准备的多维运行目录> <task_name> <新的外置调用产物目录>（首次定点执行）'
  echo '或：bash run-product-smoke.sh --launch-independent-skeptic-run <已完成正向多维运行目录> <新的外置调用产物目录>'
  echo '或：bash run-product-smoke.sh --resume-independent-skeptic-run <已运行的独立反证目录> [--prepared-index <包内dispatch-index>] <新的外置调用产物目录>（只重试未完成股票；显式消费已准备尝试时不再prepare）'
  echo '或：bash run-product-smoke.sh --stage common-stock-research --handoff <已确认Handoff> [--prepare-only] [--gate <冻结Gate> --data-preparation <准备清单> --source-bundle <来源包>] [--model <研究模型>] [--question <研究问题>] [--focus-security-id <证券ID>] <新的外置产物目录>'
  echo '或：bash run-product-smoke.sh --stage single-stock-research --single-stock ALB [--question <研究问题>] [--cutoff latest] [--prepare-only] [--through forward|skeptic|cio] [--model <研究模型>] <新的外置产物目录>（无持仓的非动作研究）'
  echo '或：bash run-product-smoke.sh --stage multidimensional-holding-research --handoff <已确认Handoff> [--gate <冻结Gate>] [--peer-candidates <冻结候选池>] [--require-materials] [--model <研究模型>] [--company-research-run <已完成普通股研究运行>] <新的外置产物目录>'
  echo '或：bash run-product-smoke.sh --stage independent-counter-thesis-research --handoff <已确认Handoff> [--gate <冻结Gate>] [--model <研究模型>] <新的外置产物目录>（同次正向研究后逐股独立反证；不启动 CIO/Risk）'
  echo '或：bash run-product-smoke.sh --stage predecision-cio-synthesis --source-run <已完成正反研究目录> --target-security-id <已研究普通股ID> [--requested-level RESEARCH_SYNTHESIS] [--model <CIO模型>] <新的外置产物目录>（仅原截止点非动作研究）'
  echo 'live 需 LIVE_SOURCE_ACCESS_FILE（外置已准入来源 JSON）与 SEC_USER_AGENT；可选 LIVE_CACHE_ROOT。'
  echo '多维新包可显式加 --structured-report-submission，仅启用研报结构化提交试验，默认关闭。'
  echo '反证上游补验可显式加 --core-forward-only，仅运行现有六项核心准入，使用新执行身份复用冻结资料；不表示完整八维。'
  echo '在 macOS Terminal 中执行；新 normal fixture、普通股/多维/反证/CIO 与新评分默认 gpt-6-luna；prepared-run 保留冻结模型。'
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
initial_multidimensional_task=0
launch_independent_skeptic_run=
resume_independent_skeptic_run=
skeptic_prepared_index=
stage=full-council
stock_handoff=
single_stock_symbol=
single_stock_cutoff=latest
single_stock_through=forward
stock_gate=
base_stock_gate=
stock_data_preparation=
stock_source_bundle=
stock_model=
stock_question='分析已确认的普通股持仓。'
stock_question_explicit=0
stock_focus_security_id=
company_research_run=
stock_peer_candidates=
require_materials=0
structured_report_submission=0
core_forward_only=0
cio_source_run=
cio_target_security_id=
cio_requested_level=RESEARCH_SYNTHESIS
cio_time_mode=SOURCE_CUTOFF
cio_max_research_age_days=
cio_mandate=
predecision_cio_stage=0
prepare_only=0
multidimensional_stage=0
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
if [ "${1:-}" = "--start-multidimensional-task" ]; then
  if [ "$#" -ne 4 ]; then echo '--start-multidimensional-task 需要全新准备运行目录、task_name 及新的调用产物目录。' >&2; exit 2; fi
  resume_multidimensional_run=$(cd "$2" && pwd -P)
  resume_multidimensional_task=$3
  initial_multidimensional_task=1
  shift 3
fi
if [ "${1:-}" = "--resume-independent-skeptic-run" ]; then
  if [ "$#" -ne 3 ] && { [ "$#" -ne 5 ] || [ "$3" != "--prepared-index" ] || [ -z "$4" ]; }; then
    echo '--resume-independent-skeptic-run 需要已运行目录、可选 --prepared-index <包内dispatch-index> 及新的外置调用产物目录。' >&2; exit 2
  fi
  resume_independent_skeptic_run=$(cd "$2" && pwd -P)
  shift 2
  if [ "${1:-}" = "--prepared-index" ]; then skeptic_prepared_index=$2; shift 2; fi
fi
if [ "${1:-}" = "--launch-independent-skeptic-run" ]; then
  if [ "$#" -ne 3 ]; then echo '--launch-independent-skeptic-run 需要已完成正向多维运行目录及新的外置调用产物目录。' >&2; exit 2; fi
  launch_independent_skeptic_run=$(cd "$2" && pwd -P)
  shift 2
fi
if [ "${1:-}" = "--stage" ]; then
  if [ "$#" -lt 5 ] || { [ "$2" != "single-stock-research" ] && [ "$2" != "common-stock-research" ] && [ "$2" != "multidimensional-holding-research" ] && [ "$2" != "independent-counter-thesis-research" ] && [ "$2" != "predecision-cio-synthesis" ]; }; then
    echo 'RESEARCH_STAGE_ARGUMENTS_INVALID：使用 --help 查看研究阶段参数。' >&2; exit 2
  fi
  stage=$2
  if [ "$stage" = "predecision-cio-synthesis" ]; then predecision_cio_stage=1; fi
  shift 2
  while [ "$#" -gt 1 ]; do
    case "$1" in
      --handoff) stock_handoff=${2:-}; shift 2 ;;
      --single-stock) single_stock_symbol=${2:-}; shift 2 ;;
      --cutoff) single_stock_cutoff=${2:-}; shift 2 ;;
      --through) single_stock_through=${2:-}; shift 2 ;;
      --gate) stock_gate=${2:-}; shift 2 ;;
      --data-preparation) stock_data_preparation=${2:-}; shift 2 ;;
      --source-bundle) stock_source_bundle=${2:-}; shift 2 ;;
      --model) stock_model=${2:-}; shift 2 ;;
      --question) stock_question=${2:-}; stock_question_explicit=1; shift 2 ;;
      --focus-security-id) stock_focus_security_id=${2:-}; shift 2 ;;
      --company-research-run) company_research_run=${2:-}; shift 2 ;;
      --peer-candidates) stock_peer_candidates=${2:-}; shift 2 ;;
      --require-materials) require_materials=1; shift ;;
      --structured-report-submission) structured_report_submission=1; shift ;;
      --core-forward-only) core_forward_only=1; shift ;;
      --source-run) cio_source_run=${2:-}; shift 2 ;;
      --target-security-id) cio_target_security_id=${2:-}; shift 2 ;;
      --requested-level) cio_requested_level=${2:-}; shift 2 ;;
      --time-mode) cio_time_mode=${2:-}; shift 2 ;;
      --max-research-age-days) cio_max_research_age_days=${2:-}; shift 2 ;;
      --mandate) cio_mandate=${2:-}; shift 2 ;;
      --prepare-only) prepare_only=1; shift ;;
      *) echo 'RESEARCH_STAGE_ARGUMENTS_INVALID：使用 --help 查看研究阶段参数。' >&2; exit 2 ;;
    esac
  done
  if [ "$core_forward_only" = "1" ] && { [ -n "$stock_peer_candidates" ] || [ "$require_materials" = "1" ]; }; then
    echo 'COUNTER_CORE_MATERIALS_FORBIDDEN：核心补验不启动资料批次；请勿组合 --peer-candidates 或 --require-materials。' >&2; exit 2
  fi
  if [ "$predecision_cio_stage" = "1" ] && { [ -z "$cio_source_run" ] || [ -z "$cio_target_security_id" ]; }; then
    echo 'CIO_SOURCE_AND_TARGET_REQUIRED：必须指定已完成正反研究目录与已有普通股 ID。' >&2; exit 2
  fi
  if [ "$structured_report_submission" = "1" ] && [ "$stage" != "multidimensional-holding-research" ]; then
    echo 'STRUCTURED_REPORT_STAGE_UNSUPPORTED：结构化研报提交仅用于显式多维研究新包。' >&2; exit 2
  fi
  if [ "$core_forward_only" = "1" ] && [ "$stage" != "independent-counter-thesis-research" ]; then
    echo 'COUNTER_CORE_SCOPE_STAGE_INVALID：核心范围仅用于显式反证上游补验。' >&2; exit 2
  fi
  if [ "$predecision_cio_stage" = "1" ] && [ "$cio_requested_level" != "RESEARCH_SYNTHESIS" ]; then
    echo 'CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE：本阶段仅交付非动作研究综合。' >&2; exit 2
  fi
  if [ "$predecision_cio_stage" = "1" ] && [ -n "$cio_mandate" ]; then
    echo 'CIO_MANDATE_NOT_APPLICABLE_TO_RESEARCH：本阶段不读取当前账户约束。' >&2; exit 2
  fi
  if [ "$predecision_cio_stage" = "1" ] && { [ "$cio_time_mode" != "SOURCE_CUTOFF" ] || [ -n "$cio_max_research_age_days" ]; }; then
    echo 'CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE：当前研究需重新准备上游包。' >&2; exit 2
  fi
  if [ "$predecision_cio_stage" = "0" ] && [ "$stage" != "single-stock-research" ] && [ -z "$stock_handoff" ]; then
    echo 'COMMON_STOCK_HANDOFF_REQUIRED：缺少已确认 Handoff。' >&2; exit 2
  fi
  if [ "$stock_question_explicit" = "1" ] && { { [ "$stage" != "common-stock-research" ] && [ "$stage" != "single-stock-research" ]; } || [ -z "$stock_question" ]; }; then
    echo 'COMMON_STOCK_QUESTION_INVALID：--question 仅适用于非空的普通股研究问题。' >&2; exit 2
  fi
  if [ "$stage" = "common-stock-research" ] && [ -n "$stock_gate" ] && { [ -z "$stock_data_preparation" ] || [ -z "$stock_source_bundle" ]; }; then
    echo 'COMMON_STOCK_DATA_PACKAGE_REQUIRED：外部 Gate 必须同时提供 data-preparation 与 source-bundle。' >&2; exit 2
  fi
  if [ "$prepare_only" = "1" ] && [ "$stage" != "common-stock-research" ] && [ "$stage" != "single-stock-research" ]; then
    echo 'PREPARE_ONLY_STAGE_UNSUPPORTED：当前仅支持普通股公司研究阶段。' >&2; exit 2
  fi
  if [ "$stage" = "single-stock-research" ]; then
    if [ "$cio_time_mode" != "SOURCE_CUTOFF" ] || [ -n "$cio_max_research_age_days" ]; then
      echo 'SINGLE_STOCK_TIME_MODE_UNSUPPORTED：本入口冻结来源截止点，不接受隐式历史重放或时效改写。' >&2; exit 2
    fi
    if [ -z "$single_stock_symbol" ] || [ -n "$stock_handoff" ] || [ -n "$stock_gate" ] || [ -n "$stock_data_preparation" ] || [ -n "$stock_source_bundle" ] || [ -n "$stock_focus_security_id" ] || [ -n "$stock_peer_candidates" ] || [ -n "$company_research_run" ] || [ -n "$cio_source_run" ] || [ -n "$cio_target_security_id" ] || [ -n "$cio_mandate" ] || [ "$core_forward_only" = "1" ] || [ "$cio_requested_level" != "RESEARCH_SYNTHESIS" ]; then
      echo 'SINGLE_STOCK_INPUT_ARGUMENTS_INVALID：只接受单股研究输入，不接受账户、跨批报告或交易建议。' >&2; exit 2
    fi
    case "$single_stock_through" in forward|skeptic|cio) ;; *) echo 'SINGLE_STOCK_STOP_INVALID' >&2; exit 2;; esac
  elif [ -n "$single_stock_symbol" ] || [ "$single_stock_cutoff" != "latest" ] || [ "$single_stock_through" != "forward" ]; then
    echo 'SINGLE_STOCK_STAGE_REQUIRED' >&2; exit 2
  fi
  if [ "$stage" = "multidimensional-holding-research" ] || [ "$stage" = "independent-counter-thesis-research" ]; then
    multidimensional_stage=1
  fi
  if [ "$stage" = "independent-counter-thesis-research" ] && [ -n "$company_research_run" ]; then
    echo 'COUNTER_HISTORICAL_COMPANY_RUN_FORBIDDEN：新阶段必须在本次运行创建公司研究。' >&2; exit 2
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
if [ "$prepare_only" = "0" ]; then
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
fi
export PYTHONDONTWRITEBYTECODE=1
if [ -n "$resume_multidimensional_run" ]; then
  case "$resume_multidimensional_run/" in "$repo_root/"*) echo '已准备的产品运行目录必须位于源码之外。' >&2; exit 2;; esac
  echo "恢复宿主多维研究阶段；进度：$resume_multidimensional_run/invocation/codex-events.jsonl" >&2
  if [ -n "$resume_multidimensional_task" ]; then
    if [ "$initial_multidimensional_task" = "1" ]; then
      python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
        --repo "$repo_root" --run-dir "$resume_multidimensional_run" \
        --task-name "$resume_multidimensional_task" --initial-task
    else
      python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
        --repo "$repo_root" --run-dir "$resume_multidimensional_run" \
        --task-name "$resume_multidimensional_task"
    fi
  else
    python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
      --repo "$repo_root" --run-dir "$resume_multidimensional_run"
  fi
  exit $?
fi
if [ -n "$resume_independent_skeptic_run" ]; then
  case "$resume_independent_skeptic_run/" in "$repo_root/"*) echo '反证运行目录必须位于源码之外。' >&2; exit 2;; esac
  echo "恢复宿主独立反证阶段；运行目录：$resume_independent_skeptic_run" >&2
  set -- --repo "$repo_root" --run-dir "$resume_independent_skeptic_run"
  if [ -n "$skeptic_prepared_index" ]; then set -- "$@" --prepared-index "$skeptic_prepared_index"; fi
  python3 "$repo_root/scripts/council-dev.py" resume-independent-skeptic "$@"
  exit $?
fi
if [ -n "$launch_independent_skeptic_run" ]; then
  case "$launch_independent_skeptic_run/" in "$repo_root/"*) echo '反证运行目录必须位于源码之外。' >&2; exit 2;; esac
  echo "继续宿主独立反证阶段；运行目录：$launch_independent_skeptic_run" >&2
  python3 "$repo_root/scripts/council-dev.py" prepare-independent-skeptic \
    --repo "$repo_root" --run-dir "$launch_independent_skeptic_run"
  python3 "$repo_root/scripts/council-dev.py" launch-independent-skeptic \
    --repo "$repo_root" --run-dir "$launch_independent_skeptic_run"
  exit $?
fi
if [ "$stage" = "single-stock-research" ]; then
  if [ -z "${LIVE_SOURCE_ACCESS_FILE:-}" ] || [ -z "${SEC_USER_AGENT:-}" ] || [ -z "${RESEARCH_MEMORY_ROOT:-}" ]; then
    echo 'SINGLE_STOCK_SOURCE_CONFIGURATION_REQUIRED：需要外置来源配置、SEC 联系身份与稳定 Research Memory。' >&2; exit 2
  fi
  model=$(python3 - "$repo_root" "$stock_model" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import agent_development_test_model, select_product_runtime_model
print(select_product_runtime_model(Path(sys.argv[1]) / 'product', requested_model=sys.argv[2] or agent_development_test_model()))
PY
)
  run_id="host-single-stock-$(uuidgen | tr '[:upper:]' '[:lower:]')"
  collect_args=(--repo "$repo_root" --single-stock "$single_stock_symbol" --cutoff "$single_stock_cutoff"
    --source-access "$LIVE_SOURCE_ACCESS_FILE" --output-dir "$bundle/data" --run-id "$run_id"
    --memory-root "$RESEARCH_MEMORY_ROOT" --cache-root "${LIVE_CACHE_ROOT:-$RESEARCH_MEMORY_ROOT/raw-cache}")
  if [ "$stock_question_explicit" = "1" ]; then collect_args+=(--question "$stock_question"); fi
  python3 "$repo_root/scripts/council-dev.py" collect-single-stock-data "${collect_args[@]}"
  input_file="$bundle/data/single-stock-request.json"
  python3 "$repo_root/scripts/council-dev.py" prepare-research-materials --repo "$repo_root" \
    --research-input "$input_file" --gate "$bundle/data/gate.json" --peer-candidates "$bundle/data/peer-candidate-pool.json" \
    --run-dir "$bundle/materials-run" --run-id "$run_id" --model "$model" --max-concurrency 3
  python3 - "$bundle" "$single_stock_through" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
request = json.loads((root / 'data/single-stock-request.json').read_text())
materials = json.loads((root / 'materials-run/run_manifest.json').read_text())
index = json.loads((root / 'materials-run/research/dispatch-index.json').read_text())
if len(index['tasks']) != 4 or materials['model'] != materials['parent_model']:
    raise SystemExit('SINGLE_STOCK_PREPARATION_PLAN_INVALID')
through = sys.argv[2]
plan = {'status': 'PREPARED_NOT_RESEARCHED', 'input_kind': request['input_kind'],
    'input_request_hash': request['request_hash'], 'target_security_id': request['security']['security_id'],
    'research_question': request['research_question'], 'provisional_cutoff': request['resolved_cutoff'],
    'final_cutoff_status': 'PENDING_MATERIALIZATION', 'model': materials['model'], 'through': through,
    'specialist_call_limits': {'materials': 4, 'company': 1, 'dimensions': 8,
        'skeptic': 0 if through == 'forward' else 1},
    'host_parent_limit': {'forward': 3, 'skeptic': 4, 'cio': 5}[through],
    'cio_parent_limit': int(through == 'cio'), 'automatic_retry': False,
    'failure_counts_toward_limit': True, 'stop_on_dependency_failure': True,
    'actual_preparation_manifest_hash': materials['manifest_hash']}
(root / 'single-stock-run-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
PY
  research_stage=MULTI_DIMENSIONAL_HOLDING_RESEARCH
  if [ "$single_stock_through" != "forward" ]; then research_stage=INDEPENDENT_COUNTER_THESIS_RESEARCH; fi
  forward_tool_args=(--structured-report-submission)
  if [ "$research_stage" = "MULTI_DIMENSIONAL_HOLDING_RESEARCH" ]; then forward_tool_args+=(--task-bound-tools); fi
  if [ "$prepare_only" = "1" ]; then
    # These actual packets are preparation checks, not formal research outputs.
    python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --research-input "$input_file" --gate "$bundle/data/gate.json" --data-preparation "$bundle/data/data-preparation.json" \
      --source-bundle "$bundle/data/source-bundle.json" --run-dir "$bundle/company-plan" --run-id "$run_id" --model "$model"
    python3 "$repo_root/scripts/council-dev.py" validate-common-stock-research --repo "$repo_root" --run-dir "$bundle/company-plan"
    python3 "$repo_root/scripts/council-dev.py" prepare-multidimensional-research --repo "$repo_root" \
      --research-input "$input_file" --gate "$bundle/data/gate.json" --peer-candidates "$bundle/data/peer-candidate-pool.json" \
      --run-dir "$bundle/eight-plan" --run-id "$run_id" --model "$model" \
      --stage "$research_stage" "${forward_tool_args[@]}"
    echo 'PREPARED_NOT_RESEARCHED：未启动模型；正式截止点待资料取证后冻结。'
    exit 0
  fi
  python3 "$repo_root/scripts/council-dev.py" launch-research-materials --repo "$repo_root" --run-dir "$bundle/materials-run"
  python3 "$repo_root/scripts/council-dev.py" materialize-selected-peers --materials-run "$bundle/materials-run" \
    --source-access "$LIVE_SOURCE_ACCESS_FILE" --cache-root "${LIVE_CACHE_ROOT:-$RESEARCH_MEMORY_ROOT/raw-cache}" \
    --memory-root "$RESEARCH_MEMORY_ROOT" --output-dir "$bundle/materials-run/research/peer-materialization"
  python3 "$repo_root/scripts/council-dev.py" freeze-single-stock-data --data-dir "$bundle/data" \
    --materials-run "$bundle/materials-run" --output-dir "$bundle/final-data"
  input_file="$bundle/final-data/single-stock-request.json"
  python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
    --research-input "$input_file" --gate "$bundle/final-data/gate.json" --data-preparation "$bundle/final-data/data-preparation.json" \
    --source-bundle "$bundle/final-data/source-bundle.json" --run-dir "$bundle/company-run" --run-id "$run_id" \
    --model "$model" --memory-root "$RESEARCH_MEMORY_ROOT"
  python3 "$repo_root/scripts/council-dev.py" launch-common-stock-research --repo "$repo_root" --run-dir "$bundle/company-run"
  python3 "$repo_root/scripts/council-dev.py" prepare-multidimensional-research --repo "$repo_root" \
    --research-input "$input_file" --gate "$bundle/final-data/gate.json" --base-gate "$bundle/final-data/base-source/gate.json" \
    --peer-candidates "$bundle/data/peer-candidate-pool.json" --run-dir "$bundle/run" --run-id "$run_id" --model "$model" \
    --company-research-run "$bundle/company-run" --research-materials-run "$bundle/materials-run" \
    --stage "$research_stage" "${forward_tool_args[@]}"
  python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research --repo "$repo_root" --run-dir "$bundle/run"
  python3 "$repo_root/scripts/council-dev.py" check-multidimensional-consumption --repo "$repo_root" --run-dir "$bundle/run"
  if [ "$single_stock_through" != "forward" ]; then
    python3 "$repo_root/scripts/council-dev.py" prepare-independent-skeptic --repo "$repo_root" --run-dir "$bundle/run"
    python3 "$repo_root/scripts/council-dev.py" launch-independent-skeptic --repo "$repo_root" --run-dir "$bundle/run"
  fi
  if [ "$single_stock_through" = "cio" ]; then
    export STOCK_AGENT_PRODUCT_HOST_LAUNCH=1
    target_id=$(python3 - "$input_file" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['security']['security_id'])
PY
)
    python3 "$repo_root/scripts/council-dev.py" prepare-predecision-cio --repo "$repo_root" \
      --source-run "$bundle/run" --run-dir "$bundle/cio-run" --run-id "cio-$run_id" --target-security-id "$target_id" --model "$model"
    python3 "$repo_root/scripts/council-dev.py" launch-predecision-cio --repo "$repo_root" --run-dir "$bundle/cio-run"
    python3 "$repo_root/scripts/council-dev.py" check-predecision-cio --repo "$repo_root" --run-dir "$bundle/cio-run"
  fi
  exit 0
fi
if [ "$predecision_cio_stage" = "1" ]; then
  case "$cio_source_run/" in "$repo_root/"*) echo '来源研究目录必须位于源码之外。' >&2; exit 2;; esac
  export STOCK_AGENT_PRODUCT_HOST_LAUNCH=1
  cio_run_id="predecision-cio-$(uuidgen | tr '[:upper:]' '[:lower:]')"
  set -- --repo "$repo_root" --source-run "$cio_source_run" --run-dir "$bundle/run" \
    --run-id "$cio_run_id" --target-security-id "$cio_target_security_id" \
    --requested-level "$cio_requested_level" --time-mode "$cio_time_mode"
  if [ -n "$cio_max_research_age_days" ]; then set -- "$@" --max-research-age-days "$cio_max_research_age_days"; fi
  if [ -n "$cio_mandate" ]; then set -- "$@" --mandate "$cio_mandate"; fi
  if [ -n "$stock_model" ]; then set -- "$@" --model "$stock_model"; fi
  python3 "$repo_root/scripts/council-dev.py" prepare-predecision-cio "$@"
  python3 "$repo_root/scripts/council-dev.py" launch-predecision-cio --repo "$repo_root" --run-dir "$bundle/run"
  python3 "$repo_root/scripts/council-dev.py" check-predecision-cio --repo "$repo_root" --run-dir "$bundle/run"
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
if [ "$stage" = "common-stock-research" ] || [ "$multidimensional_stage" = "1" ]; then
  if [ -z "$stock_model" ]; then
    model=$(python3 - "$repo_root" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import agent_development_test_model
print(agent_development_test_model())
PY
)
  fi
  if [ -n "$stock_model" ]; then
    model=$(python3 - "$repo_root" "$stock_model" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from product.runtime.model_routing import select_product_runtime_model
print(select_product_runtime_model(pathlib.Path(sys.argv[1]) / 'product', requested_model=sys.argv[2]))
PY
)
  fi
  if [ "$stage" = "multidimensional-holding-research" ] || [ "$core_forward_only" = "1" ]; then
    # 冻结资料的来源 run_id 不等于新的研究执行身份；每次新准备均生成 UUID。
    run_id="host-multidimensional-$(uuidgen | tr '[:upper:]' '[:lower:]')"
  elif [ -n "$stock_gate" ]; then
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
    if [ -z "${LIVE_SOURCE_ACCESS_FILE:-}" ] || [ -z "${SEC_USER_AGENT:-}" ] || [ -z "${RESEARCH_MEMORY_ROOT:-}" ]; then
      echo 'COMMON_STOCK_SOURCE_CONFIGURATION_REQUIRED：自动准备公司资料需要外置来源配置、SEC 联系身份和稳定 RESEARCH_MEMORY_ROOT。' >&2; exit 2
    fi
    if [ "$multidimensional_stage" = "1" ]; then
      python3 "$repo_root/scripts/council-dev.py" collect-common-stock-data --repo "$repo_root" \
        --handoff "$stock_handoff" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
        --output-dir "$bundle/data" --cache-root "${LIVE_CACHE_ROOT:-$RESEARCH_MEMORY_ROOT/raw-cache}" \
        --memory-root "$RESEARCH_MEMORY_ROOT" \
        --run-id "$run_id" --benchmark-id US:SPY --benchmark-ticker SPY
    else
      python3 "$repo_root/scripts/council-dev.py" collect-common-stock-data --repo "$repo_root" \
        --handoff "$stock_handoff" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
        --output-dir "$bundle/data" --cache-root "${LIVE_CACHE_ROOT:-$RESEARCH_MEMORY_ROOT/raw-cache}" \
        --memory-root "$RESEARCH_MEMORY_ROOT" \
        --run-id "$run_id"
    fi
    stock_gate="$bundle/data/gate.json"
    stock_data_preparation="$bundle/data/data-preparation.json"
    stock_source_bundle="$bundle/data/source-bundle.json"
    if [ "$core_forward_only" != "1" ] && [ -f "$bundle/data/peer-candidate-pool.json" ]; then
      stock_peer_candidates="$bundle/data/peer-candidate-pool.json"
    fi
  fi
  if [ "$stage" = "independent-counter-thesis-research" ]; then
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --run-dir "$bundle/company-run" \
      --run-id "$run_id" --model "$model" --question '研究当前确认的普通股持仓。' --force-rerun
    if [ "$core_forward_only" = "1" ] && [ -n "$stock_gate" ]; then
      set -- "$@" --reuse-frozen-gate
    fi
    if [ -n "$stock_data_preparation" ]; then
      set -- "$@" --data-preparation "$stock_data_preparation" --source-bundle "$stock_source_bundle"
    fi
    "$@"
    python3 "$repo_root/scripts/council-dev.py" launch-common-stock-research \
      --repo "$repo_root" --run-dir "$bundle/company-run"
    company_research_run="$bundle/company-run"
    if [ "$core_forward_only" = "1" ]; then
      stock_gate="$company_research_run/evidence/gate.json"
    fi
  fi
  if [ "$multidimensional_stage" = "1" ]; then
    research_materials_run=
    if [ "$core_forward_only" != "1" ] && [ -n "$stock_peer_candidates" ]; then
      python3 "$repo_root/scripts/council-dev.py" prepare-research-materials --repo "$repo_root" \
        --handoff "$stock_handoff" --gate "$stock_gate" --peer-candidates "$stock_peer_candidates" \
        --run-dir "$bundle/materials-run" --run-id "$run_id" --model "$model" \
        --max-concurrency 2 --reuse-frozen-gate
      if python3 "$repo_root/scripts/council-dev.py" launch-research-materials \
        --repo "$repo_root" --run-dir "$bundle/materials-run"; then
        research_materials_run="$bundle/materials-run"
        if [ "$require_materials" = "1" ]; then
          python3 - "$repo_root" "$research_materials_run" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from product.runtime.research_materials_stage import require_complete_research_materials_stage
require_complete_research_materials_stage(Path(sys.argv[2]))
PY
        fi
        if [ -n "${LIVE_SOURCE_ACCESS_FILE:-}" ] && [ -n "${SEC_USER_AGENT:-}" ]; then
          peer_cache_root="${LIVE_CACHE_ROOT:-${RESEARCH_MEMORY_ROOT:-$bundle}/raw-cache}"
          peer_memory_arg=()
          if [ -n "${RESEARCH_MEMORY_ROOT:-}" ]; then
            peer_memory_arg=(--memory-root "$RESEARCH_MEMORY_ROOT")
          fi
          if python3 "$repo_root/scripts/council-dev.py" materialize-selected-peers \
            --materials-run "$research_materials_run" --source-access "$LIVE_SOURCE_ACCESS_FILE" \
            --cache-root "$peer_cache_root" \
            "${peer_memory_arg[@]}" \
            --output-dir "$research_materials_run/research/peer-materialization"; then
            if [ -f "$research_materials_run/research/peer-materialization/gate.json" ]; then
              if [ "$require_materials" = "1" ]; then
                python3 - "$research_materials_run/research/peer-materialization/peer-materialization-manifest.json" <<'PY'
import json, sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result.get("status") != "FROZEN" or not result.get("selected") or not result.get("evidence_ids"):
    raise SystemExit("REQUIRED_PEER_EVIDENCE_MISSING：未启动八维模型。")
PY
              fi
              base_stock_gate=$stock_gate
              stock_gate="$research_materials_run/research/peer-materialization/gate.json"
            elif [ "$require_materials" = "1" ]; then
              echo 'REQUIRED_PEER_GATE_MISSING：未启动八维模型。' >&2; exit 7
            fi
          else
            echo 'PEER_MATERIALIZATION_FAILED：保留失败产物，其他独立维度继续。' >&2
            if [ "$require_materials" = "1" ]; then exit 7; fi
          fi
        else
          echo 'PEER_MATERIALIZATION_SOURCE_CONFIGURATION_MISSING：同行资料未核实，其他独立维度继续。' >&2
          if [ "$require_materials" = "1" ]; then exit 7; fi
        fi
      else
        echo 'RESEARCH_MATERIALS_STAGE_FAILED：资料准备未形成合法清单，其他独立维度继续。' >&2
        if [ "$require_materials" = "1" ]; then exit 7; fi
      fi
    else
      echo 'PEER_CANDIDATE_POOL_MISSING：未启动资料准备批次，正式阶段保留研报/同行缺口。' >&2
      if [ "$require_materials" = "1" ]; then exit 7; fi
    fi
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-multidimensional-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --run-dir "$bundle/run" \
      --run-id "$run_id" --model "$model" --question '补全已确认普通股持仓的免费多维研究资料。'
    if [ "$stage" = "multidimensional-holding-research" ]; then
      set -- "$@" --reuse-frozen-gate
    fi
    if [ "$stage" = "independent-counter-thesis-research" ]; then
      set -- "$@" --stage INDEPENDENT_COUNTER_THESIS_RESEARCH
      if [ "$core_forward_only" = "1" ]; then set -- "$@" --core-forward-only; fi
    fi
    if [ -n "$stock_peer_candidates" ]; then
      set -- "$@" --peer-candidates "$stock_peer_candidates"
    fi
    if [ -n "$company_research_run" ]; then
      set -- "$@" --company-research-run "$company_research_run"
    fi
    if [ -n "$research_materials_run" ]; then
      set -- "$@" --research-materials-run "$research_materials_run"
    fi
    if [ -n "$base_stock_gate" ]; then
      set -- "$@" --base-gate "$base_stock_gate"
    fi
    if [ "$structured_report_submission" = "1" ]; then
      set -- "$@" --structured-report-submission
    fi
  elif [ -n "$stock_data_preparation" ]; then
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --data-preparation "$stock_data_preparation" \
      --source-bundle "$stock_source_bundle" \
      --run-dir "$bundle/run" --run-id "$run_id" --model "$model" \
      --question "$stock_question"
  else
    set -- python3 "$repo_root/scripts/council-dev.py" prepare-common-stock-research --repo "$repo_root" \
      --handoff "$stock_handoff" --gate "$stock_gate" --run-dir "$bundle/run" \
      --run-id "$run_id" --model "$model" --question "$stock_question"
  fi
  if [ "$multidimensional_stage" != "1" ] && [ -n "${RESEARCH_MEMORY_ROOT:-}" ]; then
    set -- "$@" --memory-root "$RESEARCH_MEMORY_ROOT"
  fi
  if [ "$multidimensional_stage" != "1" ] && [ "${FORCE_COMPANY_RESEARCH_RERUN:-0}" = "1" ]; then
    set -- "$@" --force-rerun
  fi
  if [ -n "$stock_focus_security_id" ]; then
    if [ "$multidimensional_stage" = "1" ]; then
      echo 'MULTIDIMENSIONAL_FOCUS_NOT_SUPPORTED：多维阶段必须保留当前全部普通股覆盖。' >&2; exit 2
    fi
    set -- "$@" --focus-security-id "$stock_focus_security_id"
  fi
  if [ -n "${EQUITY_RESEARCH_PACKAGE_FILE:-}" ]; then
    if [ "$multidimensional_stage" = "1" ]; then
      echo 'EQUITY_RESEARCH_PACKAGE_STAGE_UNSUPPORTED：冻结估值附件只接入普通股公司研究阶段。' >&2; exit 2
    fi
    set -- "$@" --equity-research-package "$EQUITY_RESEARCH_PACKAGE_FILE"
  fi
  "$@"
  product_run="$bundle/run"
  if [ "$prepare_only" = "1" ]; then
    python3 "$repo_root/scripts/council-dev.py" validate-common-stock-research \
      --repo "$repo_root" --run-dir "$product_run" > "$bundle/prepare-only-result.json"
    cat "$bundle/prepare-only-result.json"
    exit 0
  fi
  echo "进入宿主研究阶段；进度：$product_run/invocation/codex-events.jsonl" >&2
  if [ "$multidimensional_stage" = "1" ]; then
    python3 "$repo_root/scripts/council-dev.py" launch-multidimensional-research \
      --repo "$repo_root" --run-dir "$product_run"
    if [ "$stage" = "independent-counter-thesis-research" ]; then
      python3 "$repo_root/scripts/council-dev.py" prepare-independent-skeptic \
        --repo "$repo_root" --run-dir "$product_run"
      python3 "$repo_root/scripts/council-dev.py" launch-independent-skeptic \
        --repo "$repo_root" --run-dir "$product_run"
    fi
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
if [ -n "$prepared_run" ]; then
  prepared_stage=$(python3 - "$prepared_run/run_manifest.json" <<'PY'
import json, sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("stage", ""))
PY
)
  if [ "$prepared_stage" = "COMMON_STOCK_RESEARCH" ]; then
    echo "进入宿主普通股研究阶段；进度：$product_run/invocation/codex-events.jsonl" >&2
    python3 "$repo_root/scripts/council-dev.py" launch-common-stock-research \
      --repo "$repo_root" --run-dir "$product_run"
    exit $?
  fi
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
