---
name: evidence-grounding
description: 使用 point-in-time 证据约束投资研究，在综合报告前区分事实、假设、冲突和数据缺口。
---

# 证据约束

当研究主张依赖行情、公告、新闻或基本面数据时，必须使用本 Skill。

## 必要输入

- 研究范围和 `decision_cutoff`。
- Evidence Bundle；其中的事实必须包含 `fact_id`、`source_id`、`as_of`、`retrieved_at`、`freshness_status`，以及来源定位或哈希。

## 方法

1. 排除在 `decision_cutoff` 之后获取的事实，禁止用后续修订替代当时版本。
2. 将每项实质性陈述分类为 `FACT`、`ASSUMPTION` 或 `INTERPRETATION`。
3. 为事实和基于证据的解释附加 `evidence_refs`。缺乏支持但仍有分析价值的前提只能作为显式假设保留。
4. 保留存在实质冲突的来源，解释冲突对决策的影响，不得静默选择一方。
5. 将过期或缺失的关键证据记录为结构化缺口，不得自行推断数值。

## 停止条件

当缺失、过期或冲突事实可能实质改变结论，且无法在本次运行中解决时，返回 `INSUFFICIENT_EVIDENCE` 或 `LOW_CONFIDENCE`。输入无效时返回 `FAILED`，工具预算耗尽时返回 `TIMEOUT`。禁止编造来源或结论来填补缺口。

## 输出内容

提供可直接写入 JSON 的 `claims`、`assumptions`、`counter_evidence_refs`、`uncertainties`、`data_gaps`、`invalidation_conditions` 和 `confidence`。每项主张必须引用证据，或者明确分类为假设。不得生成组合动作。
