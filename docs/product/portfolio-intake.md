# 持仓输入使用说明

`portfolio-intake` 是多 Agent 投研系统的统一输入能力。股票、ETF、上市期权以及账户现金、可用资金、购买力和保证金信息均由同一个 Skill 处理；系统不为不同资产创建 Intake Agent。

## 输入流程

1. 用户声明截图或手工输入代表完整券商账户，或一个完整自定义组合。
2. Codex 读取可见事实，并把账户总计、资产小计、真实持仓和现金行分开。
3. Skill 生成 `PortfolioDraft v3`，展示账户摘要、全部持仓、勾稽状态和集中澄清项。
4. 用户明确确认当前 `draft_hash` 后，生成中立 `PortfolioHandoff v3`。
5. Intake 到此停止，不自动研究证券或启动 Portfolio Council。

组合没有持仓数量上限。总计和小计不会作为 Position 重复入仓。平均成本、报价、盈亏、可用资金、购买力和保证金可以未知；基础币种、现金余额、非零数量与单位、证券身份、期权必需字段和来源闭合是确认底线。

## 单位与勾稽

股票和 ETF 数量使用 `SHARE`，期权数量使用 `CONTRACT`。期权报价按每标的单位保存，并与 `contract_multiplier` 分开；一份空头 Put 的 `0.66` 报价、`100` 乘数和 `-1` 数量对应 `-66 USD` 带符号市值，而不是 `-0.66 USD`。

系统在组成项充分时用现金加带符号持仓市值勾稽账户总值。差异超出容差时输出 `UNRECONCILED`，不会为了对平而修改持仓；组成不足时输出 `NOT_EVALUATED`。

## 来源与身份

每个规范化字段都保留直接来源；来源包含 `source_id`、`as_of`、`retrieved_at` 和内容 hash。用户修订只改变对应字段，并使旧确认失效。券商自定义字段在无法证明含义时保留原标签，不猜测成统一保证金指标。

证券身份可以是观察到、用户确认、已解析或歧义。歧义证券和无法排除调整合约歧义的期权不能生成 Handoff。

协议预留 `BROKER_READ_ONLY_API` 和 `BROKER_STATEMENT` 来源类型，但这不表示已经接入 Tiger 或其他券商，也不会请求账户凭据。

## 与 Portfolio Council 的关系

`PortfolioHandoff v3` 只保存确认后的账户和持仓状态，不包含研究问题、期限、benchmark、Mandate、下游能力或计划。

用户准备研究时，再针对同一 Handoff 创建独立 `CouncilRequest`。研究问题改变只会产生新的 Request，不会改变 Handoff 或要求重新确认持仓。当前请求范围固定为 `ALL_INPUT_POSITIONS`。

Council 的最小确定性规划接缝负责把普通股、ETF 和期权映射到对应 Research Capability，并明确报告能力缺口。Handoff 完成不代表 ETF Research、Options Research 或多资产 Risk 已经可用；规划输出也不代表真实研究已经执行。

## 隐私

真实截图、完整账户号和真实 Draft/Handoff 必须保存在仓库外。仓库仅保存合成样例。账户引用必须脱敏，真实持仓、凭据和私人账户资料不得提交 Git。
