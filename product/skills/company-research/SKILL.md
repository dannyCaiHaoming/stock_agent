---
name: company-research
description: 使用 point-in-time 证据分析公司的商业质量、经济特征、竞争地位和 Thesis，但不作出组合层决策。
---

# 公司研究

整个分析过程必须应用 `evidence-grounding`。

## 必要输入

- 证券身份、研究问题、决策截止时点和 Evidence Bundle。
- 相关财报期间，以及界定研究范围所需的用户 Mandate 上下文。

## 方法

- 解释商业模式、收入驱动因素、单位经济性、资本密集度、公司治理、竞争地位和重要依赖关系。
- 区分已报告事实、假设和解释。
- 使用确定性工具计算比率、趋势、勾稽关系或情景值。不得进行隐藏计算，也不得把“质量”编码为规则分数。
- 主动寻找反证，并描述哪些事实会使每项主要 Thesis 失效。
- 保留尚未解决的来源冲突，并说明其对置信度的影响。

## 结构化输出

返回一个 `AgentResearchReport` JSON 对象，包含 `status`、`scope`、`claims`、`assumptions`、`counter_evidence_refs`、`uncertainties`、`data_gaps`、`invalidation_conditions` 和 `confidence`。任何 `ValuationAssessment` 都应通过 artifact 引用纳入。不得输出 `BUY`、`ADD`、`HOLD`、`TRIM`、`EXIT`、目标仓位或完整组合决策。

如果关键证据不可用、过期、存在冲突或工具失败，必须返回相应的结构化状态和缺口，不得依靠记忆补全 Thesis。
