## Why

当前 `portfolio-intake` 已能识别普通股、ETF 和期权，但 `PortfolioHandoff v2` 同时承载账户状态、研究问题和下游能力状态，使用户只改变研究问题也可能影响持仓确认；账户与持仓字段又缺少精确单位、字段级来源、汇总行勾稽和证券身份状态，容易让后续 Agent 或 Risk 错读期权价格、现金、购买力和保证金。现在需要把 Intake 收敛为一个统一、纯粹且足以被多 Agent 复用的账户状态输入。

## What Changes

- 将 `portfolio-intake` 明确为唯一持仓输入入口；股票、ETF、期权、账户资金和保证金均由同一 Skill 识别与规范化，不为不同资产创建输入 Agent。
- **BREAKING**：新增 `PortfolioDraft v3` 与 `PortfolioHandoff v3`。Handoff 只描述经用户确认的账户和持仓状态，移除 `required_capability`、`capability_gaps`、`council_readiness`、`research_plan`、`holding_horizon`、`research_question`、`benchmark_id`、`mandate_artifact_id` 和 `research_scope`；历史 v2 保持原语义，不自动改写。
- 新增独立 `CouncilRequest`：通过 `handoff_id`、`handoff_hash` 和 `portfolio_hash` 引用已确认 Handoff，并承载本次研究问题、持有期限、全部持仓研究范围、benchmark、Mandate 和用户约束。改变研究问题不使原持仓确认失效。
- 新增规范化 `account_snapshot`，分别表达账户类型、基础币种、净清算价值、证券市值、现金余额、可用资金、购买力、保证金占用、初始/维持保证金要求、超额流动性和保证金使用率；来源未显示的字段保持未知，不得写成零。
- 精确定义 Position 的数量与价格语义：区分 `SHARE`/`CONTRACT`、每股/每份合约报价、合约乘数、平均成本价、带符号市值，以及未实现盈亏金额和比例；ETF 和期权仍只是资产事实，不在 Intake 中进行专业分析。
- 为规范化账户与持仓字段保存字段级 lineage；每个事实都能解析到 `source_id`、`as_of`、`retrieved_at` 和内容 hash，派生值额外保存公式版本和父字段。
- 将截图行区分为账户总计、资产类别小计、真实持仓和现金余额；汇总行不得重复生成 Position，并输出确定性勾稽状态、差额、容差和参与计算的组成项。
- 增加证券身份状态、原始显示代码/名称、市场与候选身份；歧义证券或不完整期权不得通过确认。来源契约预留只读券商 API 和券商对账单类型，但本 Change 不接 Tiger 或其他真实 API。
- 继续使用一次集中澄清和一次明确确认。成本、可用数量、账户展示价格、市值、盈亏、购买力或保证金缺失不单独阻断 Handoff，但必须保留缺口；明确现金、证券身份、数量、期权必需字段和来源闭合仍是最小确认条件。
- Research Capability 映射、能力可用性、分批计划和 Agent 派发留给 `portfolio-council`。本 Change 只提供 `CouncilRequest` 与最小确定性规划输出，不启动 Agent、不获取研究 Evidence、不生成投资结论。
- 真实截图、账户信息和私人产物继续存放在仓库外；仓库内只保留 Schema、通用实现、合成样例和脱敏测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `portfolio-intake`：将现有多资产输入升级为单一 Intake 角色、中立 Handoff v3、账户/保证金快照、精确单位、字段级 lineage、行分类与勾稽契约。
- `portfolio-council-orchestration`：新增与 Handoff 分离的 `CouncilRequest`，并明确能力映射与研究计划由 Council 在消费请求后产生，不由 Intake 预计算。

## Impact

- 主要影响 `product/skills/portfolio-intake/`、`product/intake/`、`product/schemas/intake/`、Council 输入接缝、合成样例、Intake CLI 与聚焦测试。
- `PortfolioDraft/Handoff v2` 作为历史契约保留；新调用默认生成 v3。任何需要兼容 v2 的读取路径必须显式区分版本，禁止静默混用、重算 hash 或伪造迁移。
- Council 侧只增加 `CouncilRequest` 和消费中立 Handoff 的最小确定性规划接缝；不启动 Agent，也不在本 Change 中实现 ETF Research、Options Research、真实数据采集、专业 Agent 或多资产 Risk。
- 当前暂停的 `us-equity-live-advisory-slice` 不在本 Change 范围内；不修改其行情、SEC、模型运行、Risk、Replay、Eval 或版本锁实现。
