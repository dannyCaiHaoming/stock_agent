---
name: technical-structure
description: 使用冻结的日线 OHLCV、公司行动、基准和确定性计算，解释持仓股票的趋势、相对强弱、波动、回撤、量价关系及推翻条件；不生成交易动作。
metadata:
  version: "1.1.1"
---

# 技术结构研究

只消费 PIT Gate 允许的资料和确定性计算产物。先确认证券、基准、窗口、交易日、时区、复权口径及未完成交易日处理，再解释结果。运行层已从完整日线序列生成并锁定 `technical-calculation.json` 时，Agent 直接使用输入中的精简统计和 artifact 引用；完整原始 Evidence lineage 由该产物保存，不要求把数千条日线 Evidence 重复注入模型上下文，也不得对空 `evidence_ids` 发起查询。若 `prepared_analysis.calculation=null`，则不得形成没有计算依据的技术 Claim；输出 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`claims=[]`，并在 `data_gaps` 说明缺少的证券或基准序列及影响。

有有效 calculation 时必须回答：当前窗口的趋势结构是什么；相对广泛市场基准表现如何；波动、回撤与成交量是否支持该解释；什么后续可观察信号会推翻它。没有 calculation 时逐项说明因何无法研究，不用无引用的否定性 Claim 填满问题。20、60、约 252 个交易日按资料可用性使用，不能在历史不足时制造长期结论。

收益、相对收益、波动、回撤、均量和成交量比等数字必须引用确定性计算。拆股、分红、重组、停牌、缺失交易日或来源口径变化必须先限定连续性。不得由均线、突破或阈值直接生成 BUY/HOLD/REDUCE。

输出 `ResearchDimensionReport`，`capability=TECHNICAL_STRUCTURE`，逐条保留适用的 Evidence、计算、假设、限制和 observation conditions。仅当 `prepared_analysis.chart` 存在时引用同源量价/相对表现图；若 calculation 有效但 chart 失败，保留有真实 `calculation_refs` 的 Claims，仅记录图表缺口，不把缺图当作缺少全部技术资料。由预计算产物支撑的主张通过 `calculation_refs` 连接 `artifact_id`；对应 calculation 的 `artifact_ref` 必须指向获准产物，不能杜撰原始行情或工具失败。
