---
name: macro-market-analysis
description: 使用同一截止点的官方宏观资料和大盘行情解释利率、通胀、经济活动与市场状态，并连接不同持仓的敏感性和反向情景。
metadata:
  version: "2.1.0"
---

# 宏观与市场环境研究

共享采集同一 cutoff 下的官方宏观事实和广泛市场行情，明确观察期、发布日期、修订时间和获取时间。无法取得历史 vintage 时，不得把当前修订值写成当时已知事实。

每次只执行 invocation 指定的一项能力：

- `MACRO_CONTEXT` 只解释利率、通胀、经济活动、政策原文和已公布日历，必须区分观察期、发布时间、获取时间与修订边界；不能用价格走势替代宏观事实。
- `MARKET_STATE` 只解释大盘、相关板块、跨资产、波动、信用/流动性和限定窗口市场新闻；必须标出代理序列，不能把股票波动冒充信用，也不能把 ETF 代理冒充现货、指数原值或资金流。

Moomoo Macro History、Economic Calendar 和 Dot Plot 只能作为 `SECONDARY_VENDOR` 补充；BLS、Treasury 与 Federal Reserve 保持官方主源。actual、consensus、previous、观察期、供应商更新时间和当前检索 vintage 必须分开。FedWatch 是市场隐含预期，只能进入 `MARKET_STATE`，不得描述为 Federal Reserve 承诺；涨跌分布和全市场期权统计也不得归因于单一持仓。

两项能力都必须回答对本批持仓的传导机制和显式假设，解释至少两家公司为何敏感性不同，并说明什么反向情景会推翻解释。禁止复制通用宏观叙述或将阈值改成择时规则。任一能力资料不足只限制该报告，不得把另一项能力的完成状态复制过来。

资料准备阶段对 `MACRO_RESEARCH_DISCOVERY` 和 `MARKET_RESEARCH_DISCOVERY` 分别搜索，标题与摘要只是线索，只有已取得并冻结的 `BODY_VERIFIED` 正文可进入正式 invocation。正式报告必须原样引用当前能力允许的 document 元数据，并用 `research_relationships` 将作者观点、预测和策略假设与 Gate Evidence 事实分开。公司材料、宏观材料与市场策略材料不得跨 invocation 互换；正文受限时保留实际尝试、原因和影响。

输出一个可共享的 `ResearchDimensionReport/2.0.0`，`capability` 必须逐字等于 invocation 的 `MACRO_CONTEXT` 或 `MARKET_STATE`，`scope=SHARED_MARKET`，security_ids 列出实际关联持仓。事实可以共享，报告、状态、缺口与逐股传导必须分别形成。历史 `MACRO_MARKET` 只读产物不得复制或改写为两个新报告。
