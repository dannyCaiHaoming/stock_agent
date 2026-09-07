# `harden-council-terminal-contracts` Release Gate

评审日期：2026-09-07

## 结论

**PASS，等待人工批准。**

本次只读 Release Gate 严格依据本 Change 的 proposal、四份 delta spec、design 与 tasks 执行。实现、确定性测试、真实 Codex Smoke、实际 Eval 和独立 `check-run` 均满足约定范围；未发现阻断问题，也未发现“任务已勾选但实际未实现”的情况。

本结论不等于已经批准归档。任务 9.2 的人工批准点仍未完成；批准前不得归档、提交或推送。

## PASS / FAIL 矩阵

| 验收面 | 结果 | 可核验证据 |
| --- | --- | --- |
| Canonical decision contract | PASS | `product/contracts/council-decision-contract.json` 是动作条件唯一规范来源；版本与 hash 已进入 discovery、Invocation Manifest、版本锁和完整性快照。 |
| `NO_TRADE` null/null 契约 | PASS | Schema 与 Validator 均接受 null/null，并确定性拒绝 `maximum_notional: 0` 与非空 `target_weight_range`。 |
| CIO Prompt 一致性 | PASS | 实际 CIO 动态 Prompt 由 canonical contract renderer 生成，包含合法/非法示例及“0 不等于 JSON null”。 |
| 普通动作契约 | PASS | `BUY/ADD/HOLD/TRIM/EXIT` 保留动作字段、理由、Evidence 与失效条件约束；未新增投资判断规则。 |
| 九阶段失败契约 | PASS | `PREFLIGHT` 至 `PUBLICATION_VALIDATION` 已版本化；Trace、Run Error、失败事件和 artifact matrix 交叉校验。 |
| Risk 前失败 | PASS | `CIO_VALIDATION` 反例允许空 `risk_lineage`，可通过 Trace 校验和诊断 Replay，不再误报 `TRACE_RISK_LINEAGE_MISSING`。 |
| Risk 中/后失败 | PASS | 进入 Risk 后先保存输入 hash 与 policy 关联；异常保存 `FAILED` lineage，发布阶段失败保留完成的 Risk lineage。 |
| FAILED_VALIDATION Replay | PASS | Replay 按失败阶段验证既有产物、错误和 hash，不调用 LLM、不改写源目录、不生成建议产物。 |
| Release Gate 状态码 | PASS | 已验证发布成功为 0、合法 `FAILED_VALIDATION` 为 2、损坏/非终态为 3、Eval 缺失或失败为 4。 |
| 计算工具参数契约 | PASS | `calculation_id` 在 MCP Schema、callable、无状态代理、结果和审计事件中端到端一致；非法参数在计算前拒绝。 |
| Codex-native 与独立 Agent | PASS | 真实运行保存父 session、两个不同子 session、并行派发证明、Agent 定义 hash、Skill hash、模型和工具调用。 |
| Specialist canonical Evidence ID | PASS | 修复后三次冲突运行的所有 `evidence_refs` / `counter_evidence_refs` 均逐字属于 Gate 的四个允许 ID；未出现来源、时间或说明文字拼接，也未增加静默截断。 |
| Evidence Closure | PASS | 原六次及修复后三次运行的所有引用均闭合；Gate 内事实包含 `source_id`、`as_of`、`retrieved_at`。 |
| Risk Engine | PASS | 所有形成 CIO 草案的最终运行均经过 Risk；Risk veto 场景以确定性规则返回 `REJECTED`。 |
| 实际 Eval | PASS | 原六次及修复后三次冲突运行均存在 `eval/result.json` 且为 `PASSED`；不是仅有目录骨架。 |
| 架构边界 | PASS | 未新增 Python LLM 编排后端、多角色 callback、硬编码 Thesis/Action/Confidence、外部 Provider 或交易写入能力。 |
| OpenSpec 一致性 | PASS | `openspec validate harden-council-terminal-contracts --strict` 通过。 |

## 实际执行命令与结果

### 确定性门禁

```bash
python3 -m unittest discover -s tests -v
# Ran 184 tests；OK

python3 -m unittest tests.test_native_architecture -v
# Ran 5 tests；OK

openspec validate harden-council-terminal-contracts --strict
# Change 'harden-council-terminal-contracts' is valid

git diff --check
# 退出码 0，无输出
```

完整测试输出末尾出现的 `NATIVE_EXECUTION_PROOF_FAILED` JSON 是反例测试主动触发并捕获的预期诊断，不是测试失败；测试进程退出码为 0。

### 真实 Codex Smoke

六次运行均使用以下调用形式，实际 fixture、`run_id` 和目录分别替换：

```bash
python3 -m product.runtime.cli prepare \
  --repo /Users/caihaoming/Documents/stock_agent \
  --fixture /Users/caihaoming/Documents/stock_agent/evals/fixtures/codex-native/<fixture>.json \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
  --run-id <run_id> \
  --model gpt-5.6-terra \
  --question 基于截至决策截止日的证据，对现有持仓给出仅供研究参考的组合建议；证据不足或冲突无法消解时必须NO_TRADE。

python3 -m product.runtime.cli smoke-prompt \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
| codex exec -C product \
  --add-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
  --strict-config --json -m gpt-5.6-terra -
```

每次 Codex 运行后，本轮 Release Review 又独立重跑：

```bash
python3 -m product.runtime.cli check-run \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id>
```

| 场景 | `run_id` | Codex 退出 | 本轮 `check-run` 退出 | 终态 | Eval | 关键结果 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 正常研究 | `harden-normal-02` | 0 | 0 | `SAFE_NO_TRADE` | PASS，9 项 | 3 个 Agent lineage；Risk `APPROVED`；合法 null/null。 |
| 未来/过期 | `harden-stale-01` | 0 | 0 | `SAFE_NO_TRADE` | PASS，6 项 | 3 条证据在 Agent 前排除；0 Agent、0 Risk，符合 pre-Agent 安全终止契约。 |
| Risk veto | `harden-risk-01` | 0 | 0 | `SAFE_NO_TRADE` | PASS，10 项 | Risk `REJECTED`，包含 `POSITION_LIMIT`、`LIQUIDITY_LIMIT`、`SECTOR_LIMIT`。 |
| 证据冲突 1 | `harden-conflict-01` | 0 | 0 | `SAFE_NO_TRADE` | PASS，9 项 | 独立双 Agent、CIO 消费冲突、Risk `APPROVED`、合法 null/null。 |
| 证据冲突 2 | `harden-conflict-02` | 0 | 0 | `SAFE_NO_TRADE` | PASS，9 项 | 同上；唯一目录与 `run_id`。 |
| 证据冲突 3 | `harden-conflict-03` | 0 | 0 | `SAFE_NO_TRADE` | PASS，9 项 | 同上；候选产品完整性未漂移。 |

六个 `check-run` 均输出 `status=PASSED`、`category=RELEASE_READY`，并分别验证 artifact matrix、Trace、deterministic replay 和 Eval hash。

### Specialist Evidence ID 修复后的三次稳定性运行

在 Gate-scoped Specialist Schema 与动态 Prompt 修复后，又以三个全新目录和 `run_id` 连续执行冲突 fixture。三次运行的产品完整性快照与运行结束后的当前快照均为 `a82bc4f12dfca43d15a4916ceb76b30dc514b4eb41c1574859261eaf2773f831`。

| `run_id` | Codex 退出 | 独立 `check-run` | 终态 | Eval | canonical Evidence ID | 四项终态产物 |
| --- | ---: | ---: | --- | --- | --- | --- |
| `rg3-conflict-1-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | PASS | 齐全 |
| `rg3-conflict-2-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | PASS | 齐全 |
| `rg3-conflict-3-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | PASS | 齐全 |

三次运行均生成 `decision.json`、`report.md`、`decision_trace.json`、`eval/result.json`，均经过实际双 Specialist、CIO 与 Risk Engine；抽取 Specialist 的全部引用字段后，仅出现 `ev-conflict-margin`、`ev-conflict-price`、`ev-conflict-revenue-a`、`ev-conflict-revenue-b`。

## 规格与任务交叉核对

| 规划范围 | 实现与验证结论 |
| --- | --- |
| Proposal / Design 决策 1–2 | Canonical contract、Schema 条件分支、Prompt renderer、Validator interpreter 与漂移检查均已实现；对应任务 1.1–2.5 有正反测试。 |
| Design 决策 3 | 九阶段矩阵、`failed_stage`、Trace/Run Error 2.1 和 Risk lineage 已实现；对应任务 3.1–3.6 有阶段与旧版拒绝测试。 |
| Design 决策 4 | 失败包诊断 Replay 已实现，并验证只读性、错误复现和越界产物拒绝；对应任务 4.1–4.3 完成。 |
| Design 决策 5 | `check-run` 已实现且状态码 0/2/3/4 均有执行测试；Skill 与 Smoke 提示要求独立运行 Gate；对应任务 5.1–5.3 完成。 |
| Design 决策 6 | `calculation_id` 已统一到工具公开接口、实现和事件；首调成功及非法参数测试通过；Gate-scoped Specialist Schema、动态允许 ID 与严格 Closure 规则均已实现；对应任务 6.1–6.5 完成。 |
| Design 决策 7 | 184 项完整测试、严格 OpenSpec 校验、原六次真实 Codex Smoke，以及 Evidence ID 修复后的三次冲突稳定性运行与验收记录齐全；对应任务 7.1–8.6 完成。 |
| Release Review | 本文完成只读交叉核对，任务 9.1 可判定完成；任务 9.2 保留为人工批准。 |

## 产物路径

- 实际命令与六次运行汇总：`reviews/runtime/harden-council-terminal-contracts-acceptance.md`
- 本 Release Gate：`reviews/runtime/harden-council-terminal-contracts-release-gate.md`
- 原六次运行根目录：`evals/runs/harden-council-terminal-contracts/`
- 修复后三次冲突运行根目录：`evals/runs/harden-council-terminal-contracts/release-gate-fix-20260907/`
- 每个运行目录均含：`decision.json`、`report.md`、`decision_trace.json`、`eval/result.json`
- 有专业 Agent 的运行另含：`events/codex/specialist-execution-proof.json`、`events/mcp/events.jsonl`、`risk/check-1.json`

## 阻断问题

无。

## 非阻断问题

- Codex 运行时会提示插件图标相对路径警告；未影响 Skill、Agent、MCP 或运行产物加载。
- 个别运行出现远端插件目录刷新、遥测发送或 WebSocket 预热警告；模型调用、Subagent、MCP、Eval 和 Release Gate 均已完成。
- 插件辅助校验脚本在本机缺少 PyYAML；仓库内插件 manifest、Skill frontmatter、权限和运行时配置测试均已通过，因此不构成本 Change 的阻断项。后续可将该辅助依赖纳入开发环境锁定。

## 人工批准点

请人工查看本报告与真实验收记录后，明确批准或拒绝任务 9.2。只有明确批准后，才可继续同步规格、归档 Change、提交并推送 Git。
