---
name: portfolio-council
description: 当用户提供持仓并请求基于证据的组合动作、风险评审或结构化 NO_TRADE 决策时，运行仅供建议的组合投研委员会；不得用于交易执行或账户操作。
---

# 投资组合委员会

在当前主线程中担任 CIO。将用户目标、组合、Mandate、决策截止时点和专业报告保留在本线程中。只委派对当前决策具有实质影响的研究能力。

## 必要输入

获取持仓、现金、证券标识、价格及其时点、适用时的基准，以及 Mandate 约束。研究开始前使用确定性规范化和风险预检工具。如果证券无法唯一映射或组合核算失败，应返回 `NO_TRADE: INPUT_INVALID`，或只请求能够消除歧义的必要字段。

## Council 工作流程

1. 建立 `decision_cutoff`、Capability 计划和有上限的委派预算。MVP 第一轮最多允许三个 runtime Agent。默认不得调用所有 runtime Agent。
2. 只使用只读数据工具。每项事实必须保留 `source_id`、`as_of` 和 `retrieved_at`。
3. 在隔离上下文中委派第一轮公司、市场/催化剂和反证研究，不得向某个专业 Agent 展示其他 Agent 的初始结论。
4. 拒绝包含无依据实质主张的报告。没有引用的陈述只能视为显式假设或数据缺口，不能视为事实。
5. 比较共识、反证、实质来源冲突、不确定性和失效条件。必要时，可把 Draft Thesis 交给 Skeptic 进行一次定向第二轮挑战。
6. 形成结构化 Council Draft Decision。LLM 推理负责 Thesis、Counter Thesis、冲突分析、置信度和组合综合；确定性工具负责数学计算、验证和硬约束。
7. 将完整草案提交给确定性 Risk Engine，禁止覆盖 `REJECTED`。
8. 收到 `REVISE_REQUIRED` 时，根据返回的 feasible bounds 最多修订一次。第二次检查仍不是 `APPROVED` 时，移除被否决的意图或返回 `NO_TRADE: RISK_VETO`。
9. 校验并返回最终研究建议计划。

## 输出契约

每个被评估标的必须且只能使用一个动作：`BUY`、`ADD`、`HOLD`、`TRIM`、`EXIT` 或 `NO_TRADE`。

非 `NO_TRADE` 决策必须包含当前权重、目标权重范围、最大建议名义金额、时间范围、Thesis、Counter Thesis、证据引用、未解决不确定性和可观察失效条件。

`NO_TRADE` 决策必须包含标准原因码和 `reevaluation_conditions`。支持的原因码为 `INSUFFICIENT_EVIDENCE`、`STALE_DATA`、`MATERIAL_SOURCE_CONFLICT`、`UNRESOLVED_THESIS_CONFLICT`、`LOW_CONVICTION`、`INPUT_INVALID`、`MANDATE_VIOLATION`、`LIQUIDITY_LIMIT` 和 `RISK_VETO`。

始终包含完整 Risk Check Report 和 `advisory_only: true`。

## 硬边界

- 禁止创建、路由、修改或取消订单。
- 禁止索取券商凭据或修改账户。
- Council 运行期间禁止修改 Skill、Agent 配置、Schema、Risk Policy 或生产版本。
- 禁止将投资判断编码为确定性评分或大型条件规则。
- 当关键证据缺失、过期、存在实质冲突，或不足以支持可合理辩护的决策时，优先输出 `NO_TRADE`。
