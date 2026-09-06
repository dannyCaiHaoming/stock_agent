---
name: valuation
description: 构建估值假设与情景，将全部数值计算交给确定性工具，并解释不确定性，但不输出交易动作。
metadata:
  version: "2.0.0"
---

# 估值分析

## 必要输入

- 证券身份、估值日期、决策截止时点、point-in-time 财务事实、市场价格事实和显式情景假设。
- 确定性估值或财务计算工具。

## 方法

1. 选择适合该业务的估值方法，并解释适用原因。
2. 将每个预测值或折现率输入标记为假设，并附上来源或理由。
3. 将假设和事实输入提交给确定性计算器。禁止编造计算结果，也不得在文字中静默重新计算。
4. 解释基准、乐观、悲观和敏感性输出，识别主导不确定性的假设。
5. 将过期输入、来源冲突、计算错误和缺乏支持的假设保留为结构化缺口。

## 结构化输出

返回一个 `ValuationAssessment` JSON 对象，包含 `status`、`valuation_date`、`methods`、`assumptions`、`calculation_artifact_refs`、`scenarios`、`sensitivities`、`evidence_refs`、`uncertainties`、`data_gaps` 和 `confidence`。情景数值必须引用确定性计算产物。不得直接把估值结果转换为买卖动作或目标组合权重。

如果相应条件使估值无法得到合理辩护，应停止并返回 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`FAILED` 或 `TIMEOUT`。
