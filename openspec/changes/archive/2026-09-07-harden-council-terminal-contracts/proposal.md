## Why

`activate-codex-native-fixture-council` 的 Release Gate 证明真实 Codex 链路已经可运行，但也暴露出 CIO JSON Schema、Prompt 与 Python Validator 对 `NO_TRADE` 执行字段的条件约束不一致：LLM 可以生成 Schema 合法但运行时非法的 `maximum_notional: 0`。同时，Risk 前校验失败会被 Trace 校验器误判为缺少 Risk lineage，且外层 `codex exec` 的成功退出不能可靠代表 Council 运行成功，因此现有终态不能稳定地被诊断和自动验收。

## What Changes

- 建立版本化的 canonical Council decision contract，集中声明动作相关字段约束、合法/非法示例和可供 Prompt、Schema、运行时 Validator 消费的规则；以一致性测试阻止三者漂移。
- 在 JSON Schema 中表达 `NO_TRADE` 的条件约束：`target_weight_range` 与 `maximum_notional` 必须为 JSON `null`，数值 `0` 不得被视为 `null`；CIO 指令展示由同一契约派生的合法与非法示例。
- 为失败运行记录规范化 `failed_stage`，按 `terminal_state`、失败阶段和实际到达的阶段验证 Trace lineage；Risk 前失败允许空 `risk_lineage`，到达 Risk 阶段后则必须保留完整 Risk lineage。
- 使当前 artifact replay 能对 `FAILED_VALIDATION` 运行执行阶段感知的诊断校验，不要求不存在的后续产物，也不把 Risk 前失败误报为 `TRACE_RISK_LINEAGE_MISSING`。
- 提供确定性的 `check-run`（或等价 Release Gate）命令，读取终态、错误和终态产物矩阵，并以非零退出码报告 `FAILED_VALIDATION` 或不完整运行，不再仅依赖 `codex exec` 的退出码。
- 修复 `fixture_math.calculate` 的 `calculation_id` 参数契约，使 MCP 暴露的 Schema、实际 callable、审计事件和测试保持一致，避免依靠 LLM 工具重试恢复。
- 将 Specialist 的实际输出 Schema 按本次 Gate 的 `allowed_evidence_ids` 编译为 run-scoped enum 约束，并在 Specialist Prompt 中禁止把 source 或时间拼接进 `evidence_refs`；严格 Evidence Closure Validator 保持不变，非法引用继续 fail closed，且不得静默截断修复。
- 扩充确定性测试、四 fixture 真实 Codex Smoke 与实际 Eval 验收；证据冲突 fixture 连续运行至少三次，三次均须形成完整合法终态且经过 Risk Engine。
- **BREAKING**：内部 Council Trace、Run Error 与相关验收产物将升级契约版本并引入 `failed_stage`/阶段感知规则；旧版本产物不得在未显式识别其版本的情况下被当作新版本通过。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `advisory-decision-output`：增加 canonical decision contract、动作条件 Schema 约束及 Prompt/Validator 一致性要求。
- `decision-trace-evaluation`：增加失败阶段血缘、失败运行诊断 replay、终态自动判定和 Release Gate 状态码要求。
- `portfolio-council-orchestration`：加强 Smoke 终态检查与四 fixture、三次证据冲突真实运行验收。
- `specialist-research`：统一只读计算工具的参数 Schema、实际调用签名和审计血缘契约，并以 Gate 允许 ID 约束 Specialist Evidence 引用。

## Impact

- 受影响的产品运行面包括 canonical contract、CIO Schema、Prompt 构建、结构化输出 Validator、Trace/Run Error Schema、运行包生命周期、artifact matrix、artifact replay、Eval 和 CLI 命令面。
- `fixture_math.calculate` 的只读 MCP 输入/输出与工具事件契约将增加 `calculation_id`；不增加真实 Provider、外部网络、券商或写入能力。
- 测试与验收将覆盖契约派生一致性、失败阶段矩阵、Release Gate 退出码、MCP 工具参数以及真实 Codex 四 fixture 稳定性。
- 不新增 Agent、Skill、Python LLM 编排后端、真实行情接入、通用 Replay Executor 扩展或自动交易能力。
