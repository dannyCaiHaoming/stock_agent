"""Deterministic Codex-native prompt for a prepared fixture Council run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return dict(value)


def build_smoke_prompt(run_dir: Path, *, repository_root: Path) -> str:
    """Return instructions only; Codex remains the LLM orchestrator and CIO."""

    run_dir = run_dir.resolve()
    repository_root = repository_root.resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    if Path(str(manifest.get("output_dir", ""))).resolve() != run_dir:
        raise ValueError("run directory does not match run manifest")
    run_id = str(manifest["run_id"])
    model = str(manifest["model"])
    return f"""$product:portfolio-council

你是本次 fixture Council 的 Codex 主线程 CIO。继续一个已通过确定性预检的运行；禁止读取 `{run_dir / 'audit' / 'fixture_snapshot.json'}` 或任何 `evals/fixtures` 原始文件，禁止 Web、App、外部 Provider、券商、账户与订单工具，禁止修改产品代码。

固定参数：
- repository_root: `{repository_root}`
- run_dir: `{run_dir}`
- run_id: `{run_id}`
- explicit_model: `{model}`

严格按以下顺序执行：

1. 只读取 run_dir 内的 `run_manifest.json`、`evidence/gate.json`、`inputs/runtime_company_analyst.json`、`inputs/runtime_skeptic.json`、对应 `invocations/*.json`、`prompts/*.txt`，以及仓库内三个输出 Schema。不得读取 audit/fixture_snapshot.json。
2. 在等待任何一个结果前，连续调用两次 collaboration `spawn_agent`。第一条调用必须包含 `task_name=company_research`、`agent_type=runtime_company_analyst`、`fork_turns=none`；第二条必须包含 `task_name=independent_skeptic`、`agent_type=runtime_skeptic`、`fork_turns=none`。`agent_type` 是必填验收字段，禁止用同名 task_name 代替。两条子任务消息必须逐字包含各自 `prompts/<agent>.txt` 的 task prompt、run_id、invocation_id、run_dir、完整 Agent input、完整 `skill_execution` 数组和输出 Schema 契约。
3. 两个子 Agent 必须独立调用插件工具 `mcp__fixture_runtime__query`，参数必须包含本次 run_dir/run_id、自己的 agent/invocation_id 和所需 Evidence IDs；Company Analyst 可额外调用 `mcp__fixture_runtime__calculate`。不得使用 Shell 或直接文件读取获取 Evidence。要求它们只返回一个 JSON 对象，不加 Markdown。
4. 两个委派都发出后才可等待。收到结果后，将原样 JSON 分别保存为 `agents/runtime_company_analyst.json` 与 `agents/runtime_skeptic.json`；此时不得自行判断或改写格式错误。
5. 运行 `cd {repository_root} && python3 -m product.runtime.cli prepare-cio --repo {repository_root} --run-dir {run_dir} --model {model}`。若返回 `ONE_SPECIALIST_FORMAT_REPAIR_REQUIRED`，读取返回的 repair request，只向其中指定的原 Agent/原会话请求一次纯格式修复，并将结果保存到返回的 `repaired_output` 路径；随后只可再运行一次同一 `prepare-cio` 命令。修复不得新增事实、Evidence ID、Agent 身份或 Invocation；第二次仍非法必须停止。只有返回 `CIO_SYNTHESIS_REQUIRED` 才继续。
6. 读取 `inputs/runtime_cio.json`、`invocations/runtime_cio.json`、`prompts/runtime_cio.txt` 和 CIO Schema。你自己担任 CIO，不再启动 CIO 子 Agent。只基于两份已验证报告、Evidence References、机械冲突与组合确定性数据综合；需要核验时调用同一个 fixture MCP，并使用 runtime_cio 的 invocation_id。`consumed_reports` 的 `output_hash` 必须逐字复制 `inputs/runtime_cio.json` 中对应的 `validated_report_hashes`，禁止运行 `shasum` 或自行计算文件字节哈希。输出必须显式记录 consensus、conflicts、unresolved_questions、invalidation_conditions、confidence_rationale，允许 NO_TRADE，禁止固定结论。
7. 将单个 CIODecisionDraft JSON 保存为 `cio/runtime_cio.json`。随后运行 `cd {repository_root} && python3 -m product.runtime.cli execution-proof --repo {repository_root} --run-dir {run_dir} --sessions-root /Users/caihaoming/.codex/sessions`。只有返回 `EXECUTION_PROOF_VERIFIED` 才可进入下一步；任何 Agent 身份、Skill、MCP、并行顺序或原始 fixture 访问证据失败都必须停止，且不得发布建议。
8. 运行 `cd {repository_root} && python3 -m product.runtime.cli finalize-cio --repo {repository_root} --run-dir {run_dir}`。若返回一次 `ONE_CIO_REVISION_REQUIRED`，只依据 `risk/revision-request.json` 修订一次并保存 `cio/runtime_cio_revision.json`，再使用 `--revision` 调用；不得覆盖 Risk Engine 否决。
9. 仅在获得 `COMPLETED` 或 `SAFE_NO_TRADE` 后运行 `cd {repository_root} && python3 -m product.runtime.cli eval --repo {repository_root} --run-dir {run_dir}`。Eval 必须消费本次真实运行产物并返回 `PASSED`；禁止用静态报告或 test-only bypass 代替。
10. 最终只报告 run_id、next_state 和生成的文件名。不得输出或执行真实订单。

任何非法 JSON、Schema、Evidence Closure、身份、执行元数据或持久化错误都是 FAILED_VALIDATION，不得改写成投资性 NO_TRADE。
"""
