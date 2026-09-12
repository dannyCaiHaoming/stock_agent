# 持仓草稿（尚未确认）

- 范围：BROKER_ACCOUNT
- 组合是否完整：是
- 截止时间：2026-09-11T20:00:00+08:00
- 基础币种：USD
- 现金：待补充
- 已结构化持仓数量：5（股票、ETF、期权均完整保留）
- 未识别资产数量：0（保留并阻止错误 Handoff）
- 输入项目总数：5

| 类型 | 标的/代码 | 市场 | 数量 | 成本（可选） | 状态 |
|---|---|---|---:|---:|---|
| COMMON_STOCK | AAPL | US | 12 | 181.25 | 已识别 |
| COMMON_STOCK | MSFT | US | 8 | 392.1 | 已识别 |
| COMMON_STOCK | NVDA | US | 20 | 118.4 | 已识别 |
| COMMON_STOCK | AMZN | US | 6 | 176.8 | 已识别 |
| COMMON_STOCK | GOOGL | US | 10 | 164.3 | 已识别 |

## 需要一次补充或确认的项目

- cash

确认仅生成 PortfolioHandoff，不会自动启动股票研究或交易。
