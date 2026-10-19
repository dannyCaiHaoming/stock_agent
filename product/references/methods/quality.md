---
id: quality
version: 1
kind: fundamental
signals: []
---
# 质量：利润能否转化为现金与回报

## 回答什么问题
公司的盈利是否真实、稳定、能转化为现金？增长是否需要大量资本或稀释来换？

## 适用情境 / 不适用情境
- 适用：所有非金融公司；尤其是高增长、高估值或刚扭亏的公司。
- 不适用：银行与保险（改看资本充足率、信用成本、赔付率）。

## 数据要求
- `get_financial_statements`（年度与季度）：operating_cash_flow、capex、free_cash_flow、net_income、stockholders_equity、total_debt、diluted_shares_weighted、SBC（如有）。
- `financial_ratios`：ROE、ROA、FCF/净利润、利息覆盖、流动性。

## 分析步骤
1. 现金转化：TTM 经营现金流 / 净利润，FCF / 净利润；连续多年低于 1 要找原因。
2. 稳定性：近 5 年营业利润率的波动区间。
3. 资本强度：capex / 营收；增长是否依赖持续高 capex。
4. 稀释：稀释股数变化、SBC 占营收；回购是否只是抵消 SBC。
5. 资产负债表：净债务、利息覆盖、即将到期的债务。

## 输出口径
“现金转化 x、利润率区间 a%–b%、capex/营收 c%、稀释股数年变化 d%、净债务/EBITDA e”。只描述质量，不单独推出买卖。

## 对应统计
无（质量不是单一触发条件）：需要验证。

## 常见误用
- 用单年现金流下结论（营运资本时点会扭曲）。
- 把回购当作股东回报而忽略 SBC 稀释。
- 质量好就认为“值得买”——质量与价格是两件事，后者看 `implied-expectations`。

## 与其他方法的关系
为 `growth-acceleration` 的结论加权（增长是否可持续）；为 `implied-expectations` 选择合理的利润率与倍数区间。
