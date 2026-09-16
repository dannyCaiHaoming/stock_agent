## ADDED Requirements

### Requirement: Demo 最终报告必须与真实投资建议明显区分
`DEMO_SCAFFOLD` 的 `decision.json` 和 `report.md` MUST 显示“合成示例、未使用真实 LLM、未使用真实市场数据、不得作为投资建议或交易依据”。到达 CIO 的 Demo 报告 MUST 展示 Portfolio 摘要、参与角色及其状态、示例 Thesis、Counter Thesis、共识、冲突、Evidence References、数据缺口、失效条件、Action、Confidence Rationale 和完整 Risk Result；Agent 前安全终止报告 MUST 展示 Gate 原因且不得伪造角色内容。全部研究内容 MUST 来自 Demo Agent 响应及 Risk 结果，不得由报告模板新增。

#### Scenario: 用户查看 Demo 报告
- **WHEN** 完整 Demo 链路生成最终报告
- **THEN** 报告用中文展示 Agent 数据流结果、风险处理和 Demo 限制，且不会被误认为真实股票研究

#### Scenario: Gate 后没有 Evidence
- **WHEN** Demo 在任何 Agent 调用前形成 `DEMO_SAFE_NO_TRADE`
- **THEN** 报告展示 Portfolio、Gate 排除原因和 NO_TRADE，不生成虚假的 Analyst、Skeptic、CIO 或 Risk 内容

### Requirement: Demo 输出必须保留最终安全字段
Demo 的 `decision.json` SHALL 使用独立 `DemoDecisionEnvelope`，由外层明确记录 `synthetic: true`、`llm_used: false`、`advisory_only: true` 和 Demo 终态，内层 `decision` 继续满足现有动作字段、Evidence Closure、NO_TRADE 条件和 canonical decision contract。确定性 Adapter 不得绕过 Risk Engine，真实产品验收 MUST NOT 接受该 Demo Envelope 代替产品 Decision Schema。

#### Scenario: Demo 形成 NO_TRADE
- **WHEN** Demo 最终动作是 `NO_TRADE`
- **THEN** Envelope 内层 Decision 的 `target_weight_range` 与 `maximum_notional` 均为 null，并保留风险原因和合法 Evidence References
