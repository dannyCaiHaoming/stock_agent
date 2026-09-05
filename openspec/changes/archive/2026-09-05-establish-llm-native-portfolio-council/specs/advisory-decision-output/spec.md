## Purpose

定义可供用户审阅但不可直接执行的组合建议格式，使动作、仓位范围、证据、反证、失效条件和风险状态完整且机器可验证。

## ADDED Requirements

### Requirement: 最终计划必须使用结构化动作集合
每个被评估标的的最终动作 SHALL 为 `BUY`、`ADD`、`HOLD`、`TRIM`、`EXIT` 或 `NO_TRADE`，并包含适用的目标仓位范围、时间范围和建议理由。

#### Scenario: 输出增加持仓建议
- **WHEN** 最终动作是 `ADD`
- **THEN** 输出包含当前仓位、目标仓位范围、最大建议名义金额、时间范围和最终 Risk 状态

### Requirement: 最终计划必须展示证据和失效条件
非 `NO_TRADE` 的建议 MUST 包含主要 Thesis、Counter Thesis、关键证据引用、未解决不确定性和可观察的失效条件。

#### Scenario: 用户审阅买入建议
- **WHEN** 用户查看 `BUY` 建议
- **THEN** 用户可以沿 Evidence References 追溯至带 `source_id` 和 `as_of` 的事实，并看见何种事件会使 Thesis 失效

### Requirement: NO_TRADE 必须是一等结果
系统 SHALL 使用标准原因码和人类可读解释表达 `NO_TRADE`，并区分数据不足、证据冲突、低置信度、输入无效、Mandate 违规、流动性限制和风险否决。

#### Scenario: 数据过期导致不交易
- **WHEN** 关键证据过期且不能在本次运行中更新
- **THEN** 输出 `NO_TRADE`、`STALE_DATA` 原因码、受影响事实和重新评估条件

### Requirement: 输出必须明确禁止真实执行
所有 Final Decision Plan MUST 标记为 `advisory_only`，不得包含可由券商直接执行的授权、账户凭据、订单标识或已发送状态。

#### Scenario: 生成最终交易计划
- **WHEN** Risk Engine 批准一个或多个建议动作
- **THEN** 系统仅返回研究性计划，不调用任何外部写工具或交易接口

### Requirement: 输出必须通过 Schema 和证据校验
系统 MUST 在展示结果前验证公共信封、动作枚举、Evidence References、Risk Report、版本信息和必要字段；校验失败时不得输出伪完整计划。

#### Scenario: 最终计划缺失风险报告
- **WHEN** CIO 生成的计划没有可验证的 Risk Check Report
- **THEN** 输出阶段失败并返回结构化系统错误或 `NO_TRADE`，不得宣称计划已获批准

