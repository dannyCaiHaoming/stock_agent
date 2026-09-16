---
name: macro-market-analysis
description: 使用同一截止点的官方宏观资料和大盘行情解释利率、通胀、经济活动与市场状态，并连接不同持仓的敏感性和反向情景。
metadata:
  version: "1.0.0"
---

# 宏观与市场环境研究

共享采集同一 cutoff 下的官方宏观事实和广泛市场行情，明确观察期、发布日期、修订时间和获取时间。无法取得历史 vintage 时，不得把当前修订值写成当时已知事实。

必须回答：哪些利率、通胀/经济活动和市场风险变量与本批持仓有关；传导机制和显式假设是什么；至少两家公司为何敏感性不同；什么反向情景会推翻解释。禁止复制通用宏观叙述或将宏观阈值改成择时规则。

输出一个可共享的 `ResearchDimensionReport`，`capability=MACRO_MARKET`，`scope=SHARED_MARKET`，security_ids 列出实际关联持仓。事实共享，逐股传导分别表述。
