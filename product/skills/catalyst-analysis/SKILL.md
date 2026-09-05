---
name: catalyst-analysis
description: 分析 point-in-time 公司事件、市场环境、数据时效和流动性，并区分事件事实与不确定的投资影响。
---

# 催化剂分析

对事件、价格、成交量和流动性事实应用 `evidence-grounding`。

## 必要输入

- 证券身份、决策截止时点、分析周期、事件事实、市场数据事实和流动性事实。
- 版本化 freshness 结果，以及确定性市场或流动性计算结果。

## 方法

- 构建带日期的事件地图，包含已公告事件、预期时间窗口、依赖关系，以及各事件在截止时点是否已知。
- 解释合理的传导路径和替代解释；不得机械地把事件标签视为利好或利空。
- 使用确定性工具计算收益率、波动率、成交量、价差、流动性和日期。
- 标记过期价格、不确定事件时点、来源冲突和流动性证据不足。

## 结构化输出

返回一个 `CatalystMap` JSON 对象，包含 `status`、`scope`、`events`、`market_context`、`liquidity_context`、`evidence_refs`、`alternative_interpretations`、`uncertainties`、`data_gaps`、`invalidation_conditions` 和 `confidence`。不得输出完整组合动作或可执行订单。

如果无法完成可合理辩护的事件地图，应返回 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`FAILED` 或 `TIMEOUT`，并明确列出缺口。
