## Context

参见 [proposal.md](proposal.md)。当前 `portfolio-intake` 已通过一个 Skill 和确定性服务生成多资产 Draft/Handoff，但 v2 把三类职责混在一起：用户账户实际有什么、本次用户想研究什么、当前 Council 能调用哪些 Research Agent。具体表现为 Handoff 同时保存研究问题/期限/Mandate 和 `required_capability`、`capability_gaps`、`council_readiness`、`research_plan`。此外，账户层只有一个 `cash` 数值，Position 的成本、报价和盈亏缺少单位语义与字段级来源，截图汇总行也没有正式分类和勾稽契约。

本 Change 是数据边界调整，不是新的研究能力。当前暂停的 `us-equity-live-advisory-slice` 有大量未提交修改，本设计只触碰统一 Intake 所属文件及必要的规格/文档接缝，不修改其行情、SEC、Agent、Risk、Replay、Eval 或版本锁实现。

## Goals / Non-Goals

**Goals:**

- 保持一个 `portfolio-intake` Skill，统一处理截图和手工输入中的账户、普通股、ETF 与期权。
- 生成只描述用户账户与持仓事实的中立 `PortfolioHandoff v3`。
- 以独立 `CouncilRequest` 表达研究问题、期限、全部持仓范围、benchmark 和 Mandate，使研究请求变化不影响账户确认。
- 清楚区分现金余额、可用资金、购买力和保证金相关字段，并区分未知与明确零值。
- 保留任意数量持仓、带符号数量、精确数量/价格单位、字段级 lineage、一次集中确认和仓库外私人产物。
- 分类账户总计、小计、Position 与现金行，并输出可审计勾稽状态。
- 显式保存证券身份状态，避免 ticker 或截断期权标识被误当作永久 canonical identity。
- 将能力映射和研究计划移交给 Council 侧最小确定性接缝，并保持 Agent 派发仍属于后续研究 Change。

**Non-Goals:**

- 不新增股票、ETF、期权或保证金输入 Agent；不把一个 Skill 拆成多个必须独立运行的子系统。
- 不分析 ETF 杠杆、期权 Greeks、保证金安全性或投资价值。
- 不通过预留来源类型实际连接 Tiger 或其他券商 API。
- 不实现 ETF Research、Options Research、多资产 Risk 或 Council 的真实 Agent 派发。
- 不启动 LLM 产品研究、真实行情采集、Replay、Regression 或完整 Release Gate。
- 不修改或恢复暂停中的 live Change，也不把真实持仓写入仓库。

## Decisions

### 1. 一个 Skill 负责全部输入，不创建 Intake Subagent

`portfolio-intake` 继续由当前 Codex 主线程按 Skill 执行图片理解、字段语义判断、集中澄清和确认交互。Python 仅接受结构化观察，负责 Schema、数字/日期、证券身份格式、来源闭合、hash 和持久化。

选择该方案是因为股票、ETF、期权和保证金在此阶段都是同一张账户快照中的输入事实，不需要独立观点或隔离上下文。按资产创建输入 Agent 会增加数据拼接与冲突处理，却不会增加研究信息。

备选方案是新增 `runtime_portfolio_intake` 或每资产一个 Agent；本 Change 拒绝该方案。只有未来出现需要独立网络权限、异步券商连接或隔离凭证的输入来源，才重新评估专用 runtime Agent。

### 2. 将账户状态、研究请求和 Council 计划拆成三个对象

新边界为：

```text
截图 / 手工输入
        ↓
portfolio-intake Skill
        ↓
PortfolioDraft v3
        ↓
一次集中澄清与确认
        ↓
PortfolioHandoff v3
        ↓
CouncilRequest
  - Handoff 引用
  - research_question
  - holding_horizon
  - research_scope=ALL_INPUT_POSITIONS
  - benchmark / mandate / constraints
        ↓
portfolio-council 确定性规划接缝
        ↓
ResearchPlan / CapabilityGap（只输出，不派发 Agent）
```

Handoff v3 不包含 `required_capability`、`capability_gaps`、`council_readiness`、`research_plan`、`research_question`、`holding_horizon`、`research_scope`、`benchmark_id` 或 `mandate_artifact_id`。它的 hash 只绑定已确认账户与持仓状态。

`CouncilRequest` 以 Handoff/Portfolio hash 引用确认状态，承载一次研究的目标与约束。当前产品固定 `research_scope: ALL_INPUT_POSITIONS`，研究集合必须等于 Handoff 全部 Position。用户更改问题或期限只生成新的 CouncilRequest，不重新确认未变化的持仓。

Council 侧使用最小确定性接缝同时消费 Handoff 和 CouncilRequest，再根据自身版本和 Profile 生成能力映射与研究计划；本 Change 到该输出为止，不启动专业 Agent。这样研究问题或 ETF/Options Agent 的变化都不会改变 Intake Handoff。

备选方案是在 Handoff 中保留任务和能力字段但标成可选；该方案仍使账户确认依赖某次研究和运行环境，因此不采用。期限尚未提供时，CouncilRequest 使用明确未知状态或停止补充，不把哨兵文本塞入 Handoff。

### 3. 版本升级而不是原地修改 v2

新增 Draft/Handoff v3 Schema，新入口默认输出 v3。v2 文件与校验语义保留，用于读取历史外置产物和审计旧运行；不提供自动 v2→v3 改写器，因为删除能力字段后重新计算 hash 会产生一个新的确认对象，不能冒充原用户确认。

实现读取时按 `schema_version` 显式分派。未知版本、v2/v3 字段混用或版本声明与 Schema 不一致均失败。若用户希望把历史组合用于新流程，应从原始可确认数据生成新的 v3 Draft 并再次确认，而不是静默迁移。

### 4. AccountSnapshot 区分规范字段、未知值与券商原始字段

Draft 的账户字段沿用带状态的观察结构：`value`、`status`、`source_refs`、`candidates`、`note`。Handoff 使用规范化 `account_snapshot`：

```text
account_type: CASH | MARGIN | UNKNOWN
account_ref: optional pseudonymous reference
base_currency
as_of
net_liquidation_value
securities_value
cash_balance
available_funds
buying_power
margin_used
initial_margin_requirement
maintenance_margin_requirement
excess_liquidity
margin_utilization_ratio
unknown_fields[]
broker_reported_fields[]
source_refs[]
```

`cash_balance` 是最小确认字段并允许明确为零；考虑到保证金账户可能出现借方现金，数值不强制非负。其他金额和比率允许 `null`，`null` 必须对应 `unknown_fields`，不能与零混淆。

`broker_reported_fields` 用于保留券商自定义标签及原值。只有截图明确给出定义，或组成项和版本化公式都已满足时，确定性层才可产生规范化派生值，并保存公式与父字段来源；否则不把“保证金水平”等文本猜成统一比率。

### 5. Position 使用明确的数量、报价、成本和盈亏口径

所有资产共享以下结构：

```text
quantity
quantity_unit: SHARE | CONTRACT
available_quantity
average_cost_price
quote_price
quote_unit: PER_SHARE | PER_UNDERLYING_UNIT
market_value
unrealized_pnl_amount
unrealized_pnl_percent
currency
```

股票和 ETF 使用 `SHARE` 与 `PER_SHARE`。期权使用 `CONTRACT`，报价和平均成本按每标的单位表达，并通过显式 `contract_multiplier` 与数量得到带符号账户市值；不能把期权报价直接当成整份合约价值。负数量继续表示现有空头持仓。

期权额外保留标的、CALL/PUT、到期日、执行价、乘数、可选原始合约标识和调整状态。ETF 不增加杠杆倍数、指数、基金持仓等研究字段；这些属于未来 ETF Research。

截图中的现价、市值和盈亏随账户快照保存 `source_id/as_of/retrieved_at`，只服务于用户确认和输入勾稽。它们不会自动进入 Council Evidence Gate，也不能代替未来准入的行情数据。

### 6. 字段级 lineage 是 Handoff 的事实闭包

Draft 的每个观察字段继续携带状态和 `source_refs`；Handoff 额外保存规范化字段路径到直接来源的映射。例如数量来自截图，而期权乘数来自用户修订时，两者必须指向不同来源。Position 级 `source_refs` 只作为摘要，不能替代字段级 lineage。

每个来源包含 `source_id`、`source_type`、`as_of`、`retrieved_at` 和内容 hash。派生字段使用独立记录保存公式 ID/版本、父字段路径和父来源；任何悬空、跨 Draft 或时间无效的 lineage 均阻断 Handoff。

### 7. 截图行先分类，再生成 Position 和勾稽结果

LLM 结构化观察将截图行分为：

```text
ACCOUNT_TOTAL
ASSET_CLASS_SUBTOTAL
POSITION
CASH_BALANCE
```

只有 `POSITION` 进入 Handoff 持仓数组。总计和小计保存在账户观察及 `reported_totals`，用于确定性勾稽，避免把“做多股票总计”等行重复当作证券。

勾稽记录包含报告值、计算值、差额、容差、组成字段、公式版本和 `RECONCILED | UNRECONCILED | NOT_EVALUATED`。组成项不足时保持 `NOT_EVALUATED`；超过容差时不静默调数，由集中澄清处理或以明确未勾稽状态保存。

### 8. 证券身份表达观察、确认、解析和歧义状态

Position 不把 ticker 单独视为永久 canonical identity，而是保存：

```text
display_symbol
display_name
market
asset_type
identity_status: OBSERVED | USER_CONFIRMED | RESOLVED | AMBIGUOUS
canonical_security_id
candidates[]
```

Handoff 不允许 `AMBIGUOUS`。当前截图可由用户确认证券身份；未来 Security Master 或只读券商适配可以将其提升为 `RESOLVED`，但不得改写原始显示值。期权无法排除调整合约歧义时继续澄清。

来源类型保留 `SCREENSHOT`、`MANUAL`、`USER_CORRECTION`，并预留 `BROKER_READ_ONLY_API`、`BROKER_STATEMENT`。预留只是输入协议兼容，不连接 Tiger、不请求凭据，也不表示券商接入已完成。

### 9. 最小确认条件与可选账户字段分离

生成 Handoff 需要：

- 用户声明的 Portfolio 范围完整；
- 基础币种和明确现金余额；
- 每个 Position 的可辨别证券类型、非歧义身份、非零数量和数量单位；
- 期权身份必需字段完整；
- 字段级来源闭合、Draft hash 与明确确认有效。

平均成本价、可用数量、报价、市值、盈亏、可用资金、购买力和保证金字段缺失不会单独阻断 Handoff，但必须保留未知状态。账户勾稽在组成项不足时可为 `NOT_EVALUATED`，不得伪造成功。该边界避免因常见截图不展示保证金详情而无法完成输入，同时保证“未知”不会被当成“没有风险”。

### 10. 只做聚焦确定性验收

本 Change 通过合成输入和现有真实截图的仓库外重放验证：

- 一个 Skill 同时处理股票、ETF、期权和账户摘要；
- Handoff 与 CouncilRequest hash/生命周期彼此独立；
- SHARE/CONTRACT、报价口径、乘数、带符号市值和盈亏字段不会混淆；
- 字段级 lineage、证券身份状态、汇总行分类和账户勾稽闭合；
- 零值、未知、冲突和用户修订语义；
- v3 不含研究问题、期限、Mandate、Research Capability 或计划字段；
- v2 原包仍按 v2 验证且 hash 不变；
- 私人持仓不进入 Git。

不运行专业 Agent、产品 LLM、Council Smoke、Replay、Regression、Calibration、Ablation 或 Promotion Gate。OpenSpec strict validate 与 Intake 聚焦测试足以覆盖本次边界变化。

## Risks / Trade-offs

- [Handoff v3 是破坏性契约升级] → 保留 v2 校验和历史文件，不静默迁移；新流程显式使用 v3。
- [研究任务与持仓生命周期分离后对象增加] → 用 Handoff/Portfolio hash 建立简单确定性绑定；不创建工作流平台。
- [期权报价和合约市值容易被误算] → 强制数量单位、报价单位和乘数；同时保留券商报告的带符号市值用于勾稽。
- [汇总行可能重复计入持仓] → 在图片观察阶段分类行类型，确定性层只接受 `POSITION` 生成证券持仓。
- [ticker 或调整期权身份不唯一] → 保存身份状态和候选，歧义在确认前解决。
- [账户字段在不同券商含义不同] → 规范字段与 `broker_reported_fields` 分离，无法证明语义时保持未知。
- [可选保证金字段可能使下游无法完成风险分析] → Handoff 如实传递缺口；未来 Council/Risk 决定是否需要补充，Intake 不伪造完整性。
- [Council 规划接缝可能被误认为真实研究] → 产物明确标记只完成规划、未启动 Agent；能力缺失仍如实输出，不能冒充 Council 完成。
- [当前工作区存在暂停 live Change 修改] → 只编辑可明确归属的 Intake 与本 Change 文件；重叠无法安全分离时停止并报告。

## Migration Plan

1. 新增 Draft/Handoff v3、CouncilRequest 和规划输出 Schema，保持 v2 文件及历史校验路径不变。
2. 将 Draft 创建、修订、确认、摘要和 CLI 默认输出切换到 v3；补齐单位、字段级 lineage、行分类、勾稽和身份状态。
3. 删除 v3 Intake 构建路径中的研究问题、期限、Mandate、Research Capability、计划与 readiness，改由独立 CouncilRequest 和 Council 确定性接缝承载；该接缝不派发 Agent。
4. 更新 `portfolio-intake` Skill、契约说明、合成样例和聚焦测试。
5. 使用用户现有多资产截图在仓库外重新生成 v3 Draft/Handoff，创建独立 CouncilRequest，并验证规划接缝保留五项持仓、账户字段和私人数据边界后请求一次人工完成批准。

回滚时将默认输出恢复为 v2 并保留未使用的 v3 文件；不得改写已经生成的 v3 私人 Handoff 或将其降级成 v2。
