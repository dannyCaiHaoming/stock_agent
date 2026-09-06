## MODIFIED Requirements

### Requirement: 输出必须通过 Schema 和证据校验
系统 MUST 在保存或展示结果前验证公共信封、动作枚举、Evidence References、Risk Report、版本信息和必要字段；每个 Evidence Reference MUST 存在于本次运行通过 point-in-time Gate 的 Evidence Bundle 中。数据不足、过期、投资冲突、低置信度和 Risk veto MAY 形成契约有效的 `SAFE_NO_TRADE`；Schema、Evidence Closure、运行血缘或必要 Risk Report 校验失败 MUST 形成 `FAILED_VALIDATION`，不得输出伪完整获批计划或将系统错误改写为投资性 `NO_TRADE`。

#### Scenario: 最终计划缺失风险报告
- **WHEN** CIO 生成的计划没有可验证的 Risk Check Report
- **THEN** 运行进入 `FAILED_VALIDATION` 并返回结构化系统错误，不得生成 `decision.json` 或 `report.md`

#### Scenario: 最终计划引用未知 Evidence
- **WHEN** 任一决策引用本次允许 Evidence IDs 中不存在的 ID
- **THEN** 运行进入 `FAILED_VALIDATION`，且不得保存任何 `decision.json` 或 `report.md`

## ADDED Requirements

### Requirement: 每次完成的 Council 运行必须输出三个一致产物
每次以 `COMPLETED` 或 `SAFE_NO_TRADE` 终止的 fixture Council 运行 MUST 在指定输出目录保存 `decision.json`、`report.md` 和 `decision_trace.json`。`decision.json` SHALL 是机器可验证的最终建议，`report.md` SHALL 是对同一建议、证据、冲突、失效条件和 Risk 结果的人类可读呈现，`decision_trace.json` SHALL 提供完整运行血缘。以 `FAILED_VALIDATION` 终止的运行 MUST 保存 `decision_trace.json` 和 `run_error.json`，且 MUST NOT 保存 `decision.json` 或 `report.md`。

#### Scenario: 正常研究运行完成
- **WHEN** Evidence、专业报告、CIO 草案和 Risk Result 均通过验证
- **THEN** 三个文件共享同一 `run_id`，动作、Evidence IDs、Risk 状态和 `advisory_only` 标志相互一致

#### Scenario: 数据不足形成安全 NO_TRADE
- **WHEN** 有效输入因 Gate 后无可用事实或 CIO 的证据判断形成合法 `SAFE_NO_TRADE`
- **THEN** 三个最终文件共享同一 `run_id` 和标准 NO_TRADE 原因，且 Trace 表明它不是 Schema 或引用校验失败的替代结果

#### Scenario: 运行因悬空引用失败
- **WHEN** 最终引用闭包校验失败
- **THEN** 输出目录只保存可审计的 `decision_trace.json` 和 `run_error.json`，不存在 `decision.json` 或 `report.md`

### Requirement: 报告渲染不得引入新的投资事实或结论
`report.md` MUST 仅渲染已验证的 `decision.json` 和其引用产物，不得通过模板、后处理或硬编码添加新的 Thesis、Action、Confidence、Evidence ID 或 Risk 结论。对于 `SAFE_NO_TRADE`，报告只需映射适用的证据缺口、冲突、原因码、Risk 状态和重新评估条件，不得要求虚构交易 Thesis。

#### Scenario: 比较机器决策和人类报告
- **WHEN** 验收器比较 `decision.json` 与 `report.md`
- **THEN** 报告中的动作、核心 Thesis、Evidence IDs、失效条件和 Risk 状态均可映射回机器决策且不存在新增事实
