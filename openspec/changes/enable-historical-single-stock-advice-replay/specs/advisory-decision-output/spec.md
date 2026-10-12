## ADDED Requirements

### Requirement: 历史单股建议必须有独立的条件化输出契约
历史单股 CIO SHALL 输出版本化、仅供研究的建议，至少包含证券身份、决策截止点、假设持仓状态、建议动作、评价期限、具体 Thesis、主要反证及处置、依据的报告和 Evidence 引用、触发条件、失效条件、数据限制与重评条件。`FLAT` 只可产生 `BUY` 或 `NO_TRADE`；`HELD` 可产生 `HOLD`、`ADD`、`TRIM`、`EXIT` 或 `NO_TRADE`。这些动作是给定假设状态下的条件化意见，MUST 标记 `advisory_only=true`、`real_account_fit=NOT_EVALUATED`、`risk_status=NOT_RUN`，不得包含目标权重、金额、股数、现金安排或可执行订单。建议与评价结果 MUST 分开保存并同源渲染；不得复用账户级 `decision.json` 或声称已通过完整组合 Risk。

#### Scenario: 假设已持有且研究偏保守
- **WHEN** CIO 在 `HELD` 假设下提出 `TRIM`
- **THEN** 说明减仓触发、关键证据、反证取舍及推翻条件，但不给减仓比例或金额，也不称作真实用户的持仓建议

#### Scenario: 请求真实账户目标金额
- **WHEN** 调用方要求将历史单股建议扩展为真实账户的目标仓位、名义金额或交易数量，而没有已确认账户快照与适用硬风控
- **THEN** 本阶段明确拒绝该输出，不从行情推测账户约束或生成未校验的金额

### Requirement: 建议不足与系统失败必须区分
合格研究仍可能因证据冲突、时效或低置信度选择有具体理由的 `NO_TRADE`；但身份、历史版本证明、引用闭包、Schema、执行证明或必需报告失败 MUST 形成 `FAILED_VALIDATION` 或明确不可建议终态，不能转换成投资性的 `NO_TRADE`。报告 SHALL 分别展示建议形成时间、历史决策截止点和评价时间，不能把事后表现写回原始建议理由。

#### Scenario: Skeptic 报告悬空引用
- **WHEN** 独立反证的关键引用无法在历史 Gate 中验证
- **THEN** 建议不发布，Trace 指出校验断点；不得输出看似保守的 `NO_TRADE` 掩盖系统故障

#### Scenario: 研究合法但资料不足以行动
- **WHEN** 正反报告都合法而 CIO 判断重要不确定性无法解决
- **THEN** 可输出有依据的 `NO_TRADE`、受影响判断及重评条件，评价步骤仍把它作为真实历史建议保存
