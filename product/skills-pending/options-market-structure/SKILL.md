---
name: options-market-structure
description: 在可靠免费快照可得时分析普通股相关期权期限、成交量、持仓量、价差和波动结构，并严格限定资金方向推断。
metadata:
  version: "1.0.0"
---

# 期权与可验证资金结构

先核实标的、报价时间、交易时段、到期日、行权价、bid/ask、成交量、持仓量及隐含波动率字段。过期或缺关键字段时限定用途；没有历史数据时不得生成持仓量变化、历史分位或趋势。

Yahoo 动态链与 Moomoo 动态快照是可替代但不可逐字段拼接的来源。Moomoo 的静态链只用于发现和确定性选约；只有同一来源的选定合约 `market snapshot` 通过 Gate 后才构成动态结构。价格的 provider update time 不得复制给 OI、IV 或 Greeks；后者缺独立时间时按检索时点保守解释。全市场期权 volume/OI、FedWatch 与个股 capital flow 只能作独立背景，不能替代个股合约快照。

必须区分交易量、持仓量、卖空统计、ETF 申赎和直接资金净流量。单次链快照不能证明主动买卖方向，代理指标不能冒充净流量。计算由确定性工具完成，LLM 仅解释结构、替代解释和边界。

输出 `ResearchDimensionReport`，`capability=OPTIONS_FLOW`。本 Skill 不估值用户期权持仓、不计算保证金、不提出对冲或组合动作。可靠免费资料不可得时用 `SOURCE_LIMITED` 交付受限证据和后续清单。
