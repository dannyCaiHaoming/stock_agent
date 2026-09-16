---
name: industry-comparison
description: 基于公司核心问题选择并核实同行或行业基准，比较经营、估值和相对表现，解释行业传导与可比性限制；不机械排名。
metadata:
  version: "1.3.0"
---

# 行业与同行比较

准备模式从 Gate 合格公司资料和显式 `peer_candidate_group` 提出最多三个有理由的同行/基准候选，并输出 `ResearchMaterialPreparation`；候选池只是为限制请求预算而排序的 NASDAQ 目录观察，`candidate_status=UNVERIFIED`，不是事实、同行结论或自动赢家。由确定性只读采集接缝核实证券身份并有限获取公开资料，冻结并通过 PIT Gate 后才进入正式模式。正式模式输出 `ResearchDimensionReport`；`selected_peer_candidates` 中标为 `materialization_status=FROZEN` 且带 `materialized_security_id` 的项目已经通过该接缝，必须从当前 allowed_evidence_ids 中读取持仓与同行的合格事实。准备阶段的未核实 gap 只描述历史选择时点，不能覆盖后续 FROZEN 状态。未标为 FROZEN 或没有对应 Evidence 的候选仍输出具体缺口，不把目录名称、行业标签或市值写成已核实比较主张。

必须回答：公司相对同行的位置；关键差异来自行业周期还是公司自身；哪些需求、价格或产业周期变量会传导到公司；币种、期间、会计基础、业务组合和盈利状态怎样限制比较。

计算只使用可比原值和确定性工具。正式查询从 allowed_evidence_ids 原样选择与最低必答问题直接相关的非空子集，不发送空数组，也不把没有尝试调用误写为工具不可用。指标不可比时保留可用部分及具体缺口，不用行业标签、单一倍数或规则评分选择赢家。输出 `ResearchDimensionReport`，`capability=INDUSTRY_COMPARISON`，可按同行组覆盖多只持仓。
