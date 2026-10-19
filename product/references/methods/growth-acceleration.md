---
id: growth-acceleration
version: 1
kind: fundamental
signals: [revenue_growth_acceleration, revenue_growth_deceleration, operating_margin_expansion, operating_margin_contraction]
---
# 成长加速与利润率方向

## 回答什么问题
营收增速在加快还是放慢？利润率相对去年同期在扩张还是收缩？

## 适用情境 / 不适用情境
- 适用：有稳定季度营收与营业利润报告的公司。
- 不适用或需调整：银行（用净利息收入、拨备等专门指标）；有大型并购或剥离的季度（区分有机与并表）；低基数（亏损转盈、营收很小）时百分比失真。

## 数据要求
- `get_financial_statements(period="quarterly", limit≥9)`：revenue、operating_income；注意 `derived_cells`（Q4 由全年减前三季推导）。
- 同比口径：本季对去年同季；不用环比判断趋势（季节性）。

## 分析步骤
1. 计算最近 6 个季度每季营收同比增速与 GAAP 营业利润率（用 `percent_change`、`ratio`）。
2. 加速度：最新季度同比增速 − 上一季度同比增速（>+1pp 加速，<−1pp 放缓）。
3. 利润率方向：最新季度营业利润率 − 去年同季（>+0.5pp 扩张，<−0.5pp 收缩）。
4. 区分来源：价格、销量、并购、汇率、一次性项目（读 10-Q MD&A）。

## 输出口径
“营收同比：Qx a% → Qy b%（加速／放缓 c pp）；营业利润率：d% vs 去年同季 e%（扩张／收缩 f pp）；主要来源：…”。

## 对应统计
`get_signal_stats("revenue_growth_acceleration" | "revenue_growth_deceleration" | "operating_margin_expansion" | "operating_margin_contraction", 60, as_of)`：以 10-Q/10-K 公布后第一个交易日为起点，对照 `baseline_filings`。

## 常见误用
- 用一个季度外推全年；忽略并表带来的“加速”。
- 低基数时把大百分比当作强信号。
- 把已发生的加速当作未来必然延续（要看指引与订单）。

## 与其他方法的关系
与 `guidance-revision` 互证；与 `quality` 一起判断增长能否转化为现金；与 `implied-expectations` 判断加速是否已被定价。
