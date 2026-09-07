## ADDED Requirements

### Requirement: 失败 Trace 必须按失败阶段验证血缘
以 `FAILED_VALIDATION` 终止的运行 MUST 在 `decision_trace.json` 与 `run_error.json` 中保存一致、受枚举约束的 `failed_stage`，并按 `terminal_state`、`failed_stage` 与已经实际到达的阶段验证产物和 lineage。Risk Engine 前失败 MAY 具有空 `risk_lineage`；已经进入 Risk 阶段或更晚阶段的运行 MUST 保存完整 Risk 尝试及结果血缘，缺少时 Trace 校验 MUST 失败。该规则不得允许发布状态绕过 Risk Engine，也不得把系统校验失败改写为投资性 `NO_TRADE`。

#### Scenario: Risk 前 CIO 契约校验失败
- **WHEN** 两个专业 Agent 已完成，但 CIO 草案在进入 Risk Engine 前因动作条件或 Evidence Closure 失败
- **THEN** Trace 以 `FAILED_VALIDATION` 和对应的 Risk 前 `failed_stage` 终止，`risk_lineage` 可以为空，且 Trace 校验不得返回 `TRACE_RISK_LINEAGE_MISSING`

#### Scenario: Risk 阶段失败保留完整血缘
- **WHEN** 系统已经向 Risk Engine 提交草案后发生校验或持久化失败
- **THEN** Trace 包含 Risk policy、输入哈希、尝试状态、结果或结构化错误以及修改/否决信息；缺少该 lineage 时校验失败

#### Scenario: 失败阶段与错误产物不一致
- **WHEN** `decision_trace.json` 和 `run_error.json` 的 `failed_stage`、`run_id` 或终态不一致
- **THEN** Trace 与 artifact matrix 校验均 fail closed，并返回明确的契约错误

### Requirement: FAILED_VALIDATION 运行必须支持诊断性 Artifact Replay
当前 deterministic artifact replay MUST 识别 `FAILED_VALIDATION` 终态，验证该阶段已经存在的输入、产物、哈希、错误和 lineage，并跳过失败阶段之后按契约不应存在的产物。诊断性 Replay SHALL 证明失败包自洽以及可确定性复验的校验仍得到相同错误类别；它不得生成投资建议、补跑 LLM、伪造 Risk lineage，或被描述为通用 Replay Executor 扩展。

#### Scenario: 重放 Risk 前 FAILED_VALIDATION
- **WHEN** 评审者重放一个 CIO 条件契约校验失败且 Risk 尚未运行的产物包
- **THEN** Replay 验证专业报告、CIO 输入/草案、错误、Trace 和阶段矩阵，确认不存在发布产物，并以诊断通过结束而不要求 Risk 产物

#### Scenario: 失败包缺少阶段必需产物
- **WHEN** `FAILED_VALIDATION` 产物包缺少其 `failed_stage` 之前必须存在的产物或包含阶段之后禁止出现的发布产物
- **THEN** Replay 失败并指出缺失或越界产物，不把原始失败视为合法诊断包

### Requirement: Release Gate 必须根据运行产物返回状态码
系统 MUST 提供确定性的 `check-run`、`release-gate` 或等价命令，直接读取 `terminal_state`、`run_error.json`、Decision Trace、终态 artifact matrix 和实际 Eval 结果后给出机器可读判定。`FAILED_VALIDATION`、未知或非终态、产物不完整、Trace 无效、Evidence 悬空、Risk 被绕过或 Eval 缺失/失败 MUST 返回非零状态；只有完整的 `COMPLETED` 或 `SAFE_NO_TRADE` 运行通过全部门禁时才可返回零。外层 `codex exec` 的 shell exit code MUST NOT 单独决定 Release Gate 结果。

#### Scenario: Codex 进程成功但内部校验失败
- **WHEN** `codex exec` 返回零，但 run 目录中的 `terminal_state` 为 `FAILED_VALIDATION`
- **THEN** Release Gate 输出失败终态、`failed_stage` 和 `run_error` 原因，并返回非零状态

#### Scenario: 完整发布运行通过门禁
- **WHEN** run 目录为 `COMPLETED` 或 `SAFE_NO_TRADE`，终态产物、Trace、Evidence Closure、Risk 要求和实际 Eval 全部有效
- **THEN** Release Gate 返回零并输出可机器读取的 `PASSED` 结果

#### Scenario: 运行目录尚未形成终态
- **WHEN** run 目录缺少可验证终态、错误产物或必要终态产物
- **THEN** Release Gate 返回非零状态并区分不完整运行与已确认的 `FAILED_VALIDATION`
