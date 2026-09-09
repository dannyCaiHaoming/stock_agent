# runtime-replay-and-eval-hardening：Nested Codex 定点根因诊断与关闭证明

- 日期：2026-09-09（Asia/Shanghai）
- Change：`runtime-replay-and-eval-hardening`
- 范围：仅诊断并关闭“真实 `codex exec` 退出码为 0，但只完成 prepare、没有 Specialist/CIO/Risk/合法终态”的阻断
- 模型：`gpt-5.6-terra`
- 候选版本锁：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`
- 结论：`FINAL_RELEASE_GATE_READY`
- 限制：本轮没有执行完整 Release Gate，没有标记 Task 11.10，没有归档、提交或推送

## 1. 根因结论

### FIRST_DIVERGENCE

最早可观测差异发生在 Codex 进程入口，而不是投资推理内容：失败的独立 Reviewer 命令使用了 `--ignore-user-config`，并且没有把工作目录固定到 `product/`。这使已安装的产品 Agent Package、`portfolio-council` Skill、runtime Agent 定义和 fixture MCP 没有进入真实运行上下文。

失败命令的关键部分：

```text
codex exec --ephemeral --ignore-user-config --strict-config --json \
  -s workspace-write --add-dir <run-dir> -m gpt-5.6-terra -
```

对应运行 `rrh-final-independent-v2-source-normal-20260908` 的 shell exit 为 0，但 `decision_trace.terminal_state=null`、Trace 只有 3 个事件，且没有 Specialist、CIO、Risk 与终态产物。

### ROOT_CAUSE

根因是两层运行契约缺陷叠加：

1. Reviewer 的临时命令绕过产品运行配置，却把 `codex exec` 的进程退出码当作 Council 成功信号；因此“Codex 正常结束”被错误等同于“产品工作流完成”。
2. 恢复产品配置后，原 PreToolUse matcher 使用文档别名 `spawn_agent` / `Agent`，但本机 Codex CLI 0.153.4 在 Hook payload 中实际发送的工具名是 `collaborationspawn_agent`。因此调度 Hook 未命中，无法形成可验证的独立 Specialist 调度和重复调度拒绝证据。

另有一个独立环境问题：默认 `~/.codex/state_5.sqlite` 在受限 Reviewer 环境中不可写。它不是上述“退出码 0 但非终态”的唯一原因，但会让同一命令在更严格环境中提前失败，因此一并通过 run-scoped runtime 目录消除。

## 2. 失败运行与修复后运行对照

| 项目 | 失败运行 | 修复后运行 |
|---|---|---|
| run_id | `rrh-final-independent-v2-source-normal-20260908` | `rrh-final-lock-normal-smoke-01-20260909` |
| 工作目录 | 仓库级临时 Reviewer 上下文 | 固定为 `product/` |
| 用户/插件配置 | `--ignore-user-config` | 保留 `CODEX_HOME` 并加载产品插件 |
| Skill / Agent / MCP | 未暴露 | 全部按版本锁加载 |
| 输入 Prompt | stdin 临时输入 | `invocation/prompt.txt` 冻结并计算 hash |
| Codex 状态目录 | 默认用户目录，出现只读问题 | `<run-dir>/.codex-runtime/` 隔离 |
| 子 Agent 工具 Hook | 无有效调度证明 | 精确匹配 `^collaborationspawn_agent$` |
| Codex exit | 0 | 0 |
| 产品终态判定 | 非终态，实际 FAIL | 所有 completion checks 通过 |
| terminal_state | `null` | `SAFE_NO_TRADE` |
| Specialist/CIO/Risk | 缺失 | Company Analyst、Skeptic、CIO、Risk 均完成 |
| 终态产物 | 缺失 | `decision.json`、`report.md`、`decision_trace.json`、`eval/result.json` 完整 |

## 3. 修复映射

| 问题 | 修复 | 确定性边界 |
|---|---|---|
| Prompt 与原始执行证据易丢失 | `nested-codex-smoke` 在执行前冻结 Prompt，并保存 environment、invocation、event stream、stderr、final message 和 process result | 所有关键文件存在才可判成功 |
| 默认 Codex 状态目录不可写 | 每个 run 使用 `.codex-runtime/sqlite`、`.codex-runtime/logs`、`.codex-runtime/tmp`；保留原 `CODEX_HOME`，不复制认证文件 | 任一写入探针失败即暴露在 environment manifest |
| 产品 Package 未加载 | `-C <repo>/product`，不再使用 `--ignore-user-config`，保留 `--strict-config` | Skill、Agent、MCP 和 Schema hash 均记录 |
| 子 Agent 调度 Hook 未命中 | PreToolUse 精确匹配 CLI 实际工具名 `collaborationspawn_agent` | 只允许一个 Analyst 和一个 Skeptic；重复或未授权类型在调用前拒绝 |
| 并行 Specialist 可能串行完成 | SubagentStop barrier 在两个 Specialist 都已启动前阻止首个 Specialist 结束 | 不向任一 Specialist暴露另一方结论，保持独立首轮上下文 |
| exit code 0 掩盖非终态 | launcher 重新读取 Trace、生命周期、调度、Risk 和终态产物 | 缺少任一阶段返回非零及明确 `failure_code` |
| 运行证据污染业务 Artifact Closure | `invocation/` 和 `.codex-runtime/` 作为审计元数据，不进入业务 artifact closure | Evidence Closure 仍严格、无静默纠正 |

主要实现位置：

- `product/runtime/nested_codex.py`
- `product/runtime/codex_hook_recorder.py`
- `tests/test_nested_codex_launcher.py`
- 受影响的执行证明与原生 Eval 测试

## 4. 当前精确运行命令

外层稳定入口：

```text
python3 -m product.runtime.cli nested-codex-smoke \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir <run-dir> \
  --codex-binary codex \
  --timeout-seconds 1800
```

由 launcher 生成并记录在每个 `environment-manifest.json` 的内层命令包含：

```text
codex --ask-for-approval never --dangerously-bypass-hook-trust exec \
  --ephemeral --json --sandbox workspace-write \
  --add-dir <run-dir> -C /Users/caihaoming/Documents/stock_agent/product \
  --strict-config \
  -c sqlite_home="<run-dir>/.codex-runtime/sqlite" \
  -c log_dir="<run-dir>/.codex-runtime/logs" \
  -c history.persistence="none" \
  -c hooks.PreToolUse=[matcher="^collaborationspawn_agent$"] \
  -c hooks.SubagentStart=[matcher="^(runtime_company_analyst|runtime_skeptic)$"] \
  -c hooks.SubagentStop=[matcher="^(runtime_company_analyst|runtime_skeptic)$"] \
  --output-last-message <run-dir>/.codex-runtime/tmp/final-message.txt \
  --model gpt-5.6-terra -
```

实际命令数组、完整 Hook command 和所有绝对路径以各运行的 `invocation/environment-manifest.json` 为准。

## 5. 完整原始执行证据

每个成功 Council run 均保存：

- `invocation/prompt.txt`
- `invocation/invocation-manifest.json`
- `invocation/codex-events.jsonl`
- `invocation/codex-stderr.log`
- `invocation/final-message.json`
- `invocation/process-result.json`
- `invocation/environment-manifest.json`
- `invocation/subagent-dispatches.jsonl`
- `invocation/subagent-events.jsonl`

`environment-manifest.json` 包含 run_id、cwd、repo/product/run 目录、模型、完整 argv、sandbox、approval policy、`CODEX_HOME`、隔离的 sqlite/log/tmp 路径、可写探针，以及 Skill、Agent、Prompt、Schema、MCP 和运行配置 hash。

证据根目录：

```text
/Users/caihaoming/Documents/stock_agent/evals/results/
runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock
```

## 6. 聚焦测试

实际命令：

```text
python3 -m unittest \
  tests.test_nested_codex_launcher \
  tests.test_native_execution_proof \
  tests.test_portfolio_council_skill \
  tests.test_native_eval
```

结果：`38 tests`，全部 PASS，耗时 1.747 秒。

覆盖包括：

- 内层命令固定 Prompt、隔离状态目录和 Hook 配置；
- 正确 Specialist 类型允许；
- 重复 Specialist 调度拒绝；
- 未授权 Agent 类型拒绝；
- Hook 记录不保留原始 Prompt 或推理正文；
- Codex exit 0 但缺少阶段或产物时 launcher 非零失败；
- 完整生命周期、Risk、Trace 与原生 Eval 成功路径。

## 7. 三次当前版本锁 Normal Smoke

| run_id | Skill | Analyst + Skeptic | CIO | Risk | 终态产物 | Runtime Eval | 结果 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rrh-final-lock-normal-smoke-01-20260909` | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `rrh-final-lock-normal-smoke-02-20260909` | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `rrh-final-lock-normal-smoke-03-20260909` | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

三个 run_id 全局唯一；每次都只有一个实际 Analyst 和一个实际 Skeptic `SubagentStart`，并生成合法 `SAFE_NO_TRADE` 终态。三个运行的 `source_integrity_unchanged=true`。

## 8. 六个真实 LLM Regression 案例

| 案例 | 接受的 run_id | Council | 外部 Runtime Eval | 结果 |
|---|---|---:|---:|---:|
| normal-research | `rrh-final-lock-regression-normal-research-20260909` | PASS | PASS | PASS |
| insufficient-evidence | `rrh-final-lock-regression-insufficient-evidence-20260909` | PASS | PASS | PASS |
| analyst-skeptic-strong-conflict | `rrh-final-lock-regression-analyst-skeptic-strong-conflict-20260909` | PASS | PASS | PASS |
| risk-veto | `rrh-final-lock-regression-risk-veto-retry-01-20260909` | PASS | PASS | PASS |
| high-concentration-portfolio | `rrh-final-lock-regression-high-concentration-portfolio-20260909` | PASS | PASS | PASS |
| llm-overconfidence | `rrh-final-lock-regression-llm-overconfidence-20260909` | PASS | PASS | PASS |

六个 Runtime Eval 均使用真实 `dev_eval`、模型 `gpt-5.6-terra`，并保存 parent/child session_id、Prompt/Input/Output hash、proof hash、语义结果及 `eval/result.json`、`eval/report.md`。

`llm-overconfidence` 运行中 CIO 曾尝试再次调度 Skeptic；PreToolUse 留下 `DENY_DUPLICATE_AGENT`，实际生命周期仍只有一个 Skeptic。这证明 Guard 不是依赖 Prompt 自律。

保留了一次未计入通过结果的 risk-veto 失败运行：

```text
final-lock/regression-runs/risk-veto
run_id = rrh-final-lock-regression-risk-veto-20260909
```

该运行因 Analyst 的 `skill_execution.invocation_hash` 非法而得到 `SKILL_EXECUTION_PROOF_MISMATCH`；Codex exit 为 0，但 launcher exit 为 7 并进入 `FAILED_VALIDATION`。系统没有截断、修补或掩盖错误，随后使用新 run_id 重跑并通过。

## 9. 十二案例 Regression Runner

实际命令：

```text
python3 -m product.runtime.cli regression \
  --repo /Users/caihaoming/Documents/stock_agent \
  --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/regression/suite-final \
  --suite-id rrh-final-lock-regression-suite-20260909 \
  --candidate-hash 618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198 \
  --run-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/regression/run-index.json
```

结果：12/12 PASS，suite hash：

```text
179b70a83526db786357354a5bdcddcae55c06cabe05e513e81b8db3e55c7b39
```

Regression set hash：

```text
6004fb79ed7ec5de2ea9dcdd3156b3d25c15544802950f9a86e95cf4ad1edb4
```

Runner 对六个 LLM 案例消费上述真实运行及 Eval 证据；对六个确定性负例执行注入、Trace Integrity、Artifact Replay 和 Runtime Eval verify。`future-information-leakage` 的两个未来 Evidence 在 PIT Gate 前真实注入，Gate 排除后由 Trace/Eval 重算通过，不是事后补写摘要。

## 10. 最终矩阵

| 验证项 | 结果 | 证据 |
|---|---:|---|
| 失败运行原始证据保留 | PASS | `final-independent-v2-20260908/` |
| Prompt 固定文件与 hash | PASS | 每个 run 的 `invocation/prompt.txt`、environment manifest |
| run-scoped sqlite/log/tmp | PASS | 每个 run 的 `.codex-runtime/` 与写入探针 |
| Skill/Agent/MCP/Schema 版本锁 | PASS | `resource_hashes` |
| Specialist 独立真实上下文 | PASS | dispatch 与 lifecycle Hook 事件 |
| 重复 Specialist fail-closed | PASS | `DENY_DUPLICATE_AGENT` 真实事件与聚焦测试 |
| CIO 与 Risk 完成 | PASS | Trace、CIO、Risk 与 process completion checks |
| exit 0 非充分条件 | PASS | 保留的失败 run 返回 launcher 非零 |
| 三次 Normal Smoke | PASS | 3/3，唯一 run_id，完整终态 |
| 六个真实 LLM Regression | PASS | 6/6 Council + 外部 Runtime Eval |
| 十二案例 Regression | PASS | 12/12，suite result/report |
| 产品源码运行前后 hash | PASS | `24fe59edbc75db2c5d667df7e58b069f63e136aad59a0ff22782cb27e0fa74fb` |
| Task 11.10 | 保持未完成 | `openspec/changes/runtime-replay-and-eval-hardening/tasks.md` |
| 完整 Release Gate | 未执行 | 遵守本轮禁止事项 |

## 11. 最终状态

当前唯一阻断已经关闭，满足进入一次最终独立只读 Release Gate 的前置条件：

```text
FINAL_RELEASE_GATE_READY
```

本结论只表示“可以开始最终 Gate”，不等同于 Change 已获最终批准，也不授权归档、提交或推送。
