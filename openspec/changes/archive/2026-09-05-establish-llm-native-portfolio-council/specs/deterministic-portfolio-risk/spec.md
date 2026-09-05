## Purpose

提供独立、可重复和不可绕过的组合核算与硬风控能力，在不替代投资判断的前提下约束所有建议动作的可行性。

## ADDED Requirements

### Requirement: 持仓输入必须先规范化和核算
系统 MUST 在研究开始前解析证券标识、数量、现金、价格时点、基准和 Mandate，并验证重复持仓、未知标的、金额守恒和必要字段。

#### Scenario: 持仓包含无法映射的证券
- **WHEN** Security Master 无法唯一映射用户提交的标识
- **THEN** 系统不猜测标的，并返回输入无效或要求补充信息

### Requirement: Risk Engine 必须执行前置和后置两阶段检查
同一版本化 Risk Policy SHALL 支持研究前的风险预检和 CIO 草案后的最终校验；前置结果提供当前风险状态与可行边界，后置结果拥有最终否决权。

#### Scenario: CIO 形成草案前
- **WHEN** Portfolio Snapshot 通过输入验证
- **THEN** Risk Engine 返回当前现金、仓位、集中度、敞口、流动性和其他适用风险指标

#### Scenario: CIO 提交草案
- **WHEN** 草案包含一个或多个目标仓位范围
- **THEN** Risk Engine 计算建议前后指标并返回 `APPROVED`、`REVISE_REQUIRED` 或 `REJECTED`

### Requirement: 硬约束必须确定性且可解释
Risk Engine SHALL 仅执行可表述为会计恒等式、数学定义、数据质量要求或明确 Mandate 的硬约束，并为每项违规输出政策条款、输入、计算和原因码。

#### Scenario: 计划超过单一标的上限
- **WHEN** 计划后的目标仓位超过版本化 Mandate 上限
- **THEN** Risk Engine 返回具体违规、计算值和允许的最大可行边界

### Requirement: Risk Engine 不得进行主观投资判断
Risk Engine MUST NOT 根据商业质量、估值吸引力、新闻含义、市场情绪或模型生成的信心分数选择证券或创造投资 Thesis。

#### Scenario: 风险校验收到低置信度 Thesis
- **WHEN** CIO 草案的置信度较低但所有硬约束均满足
- **THEN** Risk Engine 不以主观置信度替代 CIO 决策，只校验明确政策；CIO 可自行选择 `NO_TRADE`

### Requirement: 风险否决不可被 Agent 覆盖
任何 Agent、Skill 或 CIO 输出均不得把 `REJECTED` 风险结果改写为通过；最终输出 MUST 保留原始 Risk Check Report 和 policy version。

#### Scenario: CIO 坚持被否决的交易
- **WHEN** CIO 文本结论与 Risk Engine 的 `REJECTED` 状态冲突
- **THEN** 最终结构化状态以风险否决为准，并记录该冲突

