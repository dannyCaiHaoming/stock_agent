## ADDED Requirements

### Requirement: Intake 必须统一表达账户资金与保证金快照
`PortfolioDraft v3` 与 `PortfolioHandoff v3` SHALL 使用一个 `account_snapshot` 表达账户层事实，至少支持账户类型、基础币种、证券市值、净清算价值、现金余额、可用资金、购买力、保证金占用、初始保证金要求、维持保证金要求、超额流动性和保证金使用率。现金余额、可用资金、购买力和保证金字段 MUST 相互独立，不得合并为同一个 `cash` 值。

截图或手工输入未提供的账户字段 MUST 在 Draft 中标记为 `MISSING`，在 Handoff 中表示为 `null` 并列入未知字段；未知值不得写成零。未显示购买力或保证金本身 MUST NOT 阻断 Handoff，只要组合范围、持仓、基础币种和明确现金余额已经满足最小确认条件。券商自定义“保证金水平”只有在定义或组成项明确时才能映射为规范字段，否则 MUST 保留原始标签、原始值和来源，不得猜测公式。

#### Scenario: 截图只有现金而没有保证金信息
- **WHEN** 截图明确显示现金余额，但没有显示购买力、保证金占用或维持保证金
- **THEN** Intake 保留明确现金，将其他字段标记为未知，并允许用户确认 Handoff，不推测保证金状态

#### Scenario: 截图同时显示现金与购买力
- **WHEN** 同一来源分别显示现金余额和购买力
- **THEN** Intake 将两者保存为不同字段并分别关联来源，不用购买力覆盖现金

#### Scenario: 券商显示未定义的保证金水平
- **WHEN** 截图存在“保证金水平”等标签但未说明定义或计算组成
- **THEN** Intake 保存该券商原始字段并标记规范含义未确认，不自行计算或映射为保证金使用率

### Requirement: Intake 必须保留截图可见的持仓账户事实
统一 Position SHALL 支持普通股、ETF 与期权共同拥有的带符号数量、可用数量、平均成本价、可见报价、带符号市值、未实现盈亏金额、未实现盈亏比例和币种。数量 MUST 同时声明 `quantity_unit: SHARE | CONTRACT`；报价与平均成本 MUST 声明每股或每标的单位口径，期权 MUST 结合显式 `contract_multiplier` 表达账户市值，禁止把一份合约的 `0.66` 报价误解为 `0.66 USD` 总市值。除证券身份和非零数量等最小 Handoff 字段外，截图未显示的账户展示字段 MAY 为未知。

上述报价、市值和盈亏仅是用户账户快照事实，MUST 保留来源与时间，但 MUST NOT 被 Intake 宣称为研究 Evidence 或用于生成投资结论。`unrealized_pnl_amount` 与 `unrealized_pnl_percent` MUST 分离；`average_cost_price` 不得使用含义不明的单一 `cost_basis` 代替。

#### Scenario: 截图显示市值但盈亏被截断
- **WHEN** 持仓行的市值清晰可见而盈亏百分比被截断
- **THEN** Intake 保存市值并将无法完整读取的盈亏字段标记为歧义或缺失，不根据其他数字反推

#### Scenario: ETF 与股票使用相同账户字段
- **WHEN** 截图同时包含普通股和 ETF 的数量、成本及市值
- **THEN** 两类 Position 使用同一组账户事实字段，但仍保留不同 `asset_type`

#### Scenario: 空头期权报价与市值口径不同
- **WHEN** 截图显示一份空头 Put、每标的单位报价 `0.66`、合约乘数 `100` 和账户市值 `-66.00 USD`
- **THEN** Intake 分别保存 `quantity=-1`、`quantity_unit=CONTRACT`、报价口径、乘数和带符号市值，不把报价直接当作总市值

#### Scenario: 盈亏金额和比例同时出现
- **WHEN** 持仓行同时显示未实现盈亏金额与百分比
- **THEN** Intake 将两者保存为不同字段并分别保留来源，不把百分比塞入金额字段

### Requirement: 规范化字段必须具有字段级 lineage
Draft 与 Handoff 中每个账户、持仓和期权规范字段 MUST 通过字段路径关联其直接 `source_id`；每个 `source_id` MUST 闭合解析到 `source_type`、`as_of`、`retrieved_at` 和内容 hash。Position 级统一 `source_refs` MAY 作为摘要，但不得代替字段级 lineage。确定性派生值还 MUST 保存公式标识、公式版本、父字段路径和父来源；任何悬空、跨 Draft 或来源时间无效的 lineage MUST fail closed。

#### Scenario: 用户只修正期权乘数
- **WHEN** 数量和执行价来自截图，而合约乘数由用户明确修正为 `100`
- **THEN** Handoff 的字段级 lineage 分别指向截图来源和用户修订来源，不把整条 Position 错记为单一来源

#### Scenario: 派生保证金比例
- **WHEN** 所需组成项均已确认且系统按版本化公式计算保证金使用率
- **THEN** 派生字段保存公式版本、输入字段路径和父来源，任一组成项缺失时不生成该比率

### Requirement: Intake 必须区分汇总行、持仓行和现金行并执行勾稽
截图结构化观察 SHALL 将可见行分类为 `ACCOUNT_TOTAL`、`ASSET_CLASS_SUBTOTAL`、`POSITION` 或 `CASH_BALANCE`。只有 `POSITION` 生成持仓；账户总计和资产类别小计只用于账户快照与确定性勾稽，MUST NOT 作为额外 Position 重复计入。

当净清算价值、现金、持仓市值或分类小计的组成项足够时，系统 SHALL 输出版本化勾稽记录，至少包含报告值、计算值、差额、容差、组成字段和 `RECONCILED | UNRECONCILED | NOT_EVALUATED`。超过容差的差异必须进入集中澄清或以明确未勾稽状态保留，不得静默调整任一持仓；组成项不足时必须为 `NOT_EVALUATED`，不得伪造通过。

#### Scenario: 汇总行与四个真实持仓同时出现
- **WHEN** 截图包含“做多股票总计”“做空期权总计”和四条具体持仓行
- **THEN** Intake 只创建四个 Position，并使用两条小计进行勾稽，不把汇总行作为第五星、第六项持仓

#### Scenario: 账户总值可以勾稽
- **WHEN** 持仓带符号市值之和加现金在允许容差内等于报告的净清算价值
- **THEN** 勾稽状态为 `RECONCILED` 并保存公式、组成字段和差额

#### Scenario: 组成项不足
- **WHEN** 截图未显示部分持仓市值或账户总值
- **THEN** 勾稽状态为 `NOT_EVALUATED`，系统保留缺口且不反推缺失数值

### Requirement: Intake 必须显式表达证券身份状态
每个 Position SHALL NOT assume ticker alone is a permanent canonical identity. Draft 与 Handoff SHALL 保存原始显示代码、原始名称、市场、资产类型、身份状态、可选 canonical security ID 和歧义候选。身份状态至少支持 `OBSERVED`、`USER_CONFIRMED`、`RESOLVED` 和 `AMBIGUOUS`；生成 Handoff 前不得保留 `AMBIGUOUS`，也不得根据相似名称静默选择候选。期权除结构字段外还 SHALL 保存可选原始合约标识和调整状态；无法排除调整合约歧义时必须澄清。

来源类型 SHALL 支持当前 `SCREENSHOT`、`MANUAL`、`USER_CORRECTION`，并为未来输入适配预留 `BROKER_READ_ONLY_API` 与 `BROKER_STATEMENT`；预留类型不代表本 Change 已连接任何券商。

#### Scenario: 同一代码存在身份歧义
- **WHEN** 原始代码无法在市场与资产类型上下文中唯一对应证券
- **THEN** Draft 保存候选并标记 `AMBIGUOUS`，用户确认或后续只读身份解析前不得生成 Handoff

#### Scenario: 只读券商来源尚未实现
- **WHEN** Schema 出现 `BROKER_READ_ONLY_API` 来源类型但当前没有 Tiger 或其他券商适配器
- **THEN** 系统只把它视为可表达的来源类型，不宣称已完成 API 连接或账户同步

### Requirement: Handoff v3 与历史 v2 必须显式区分
新调用 SHALL 默认生成 `PortfolioDraft v3` 和 `PortfolioHandoff v3`。历史 v2 Schema 与既有外置产物 MAY 继续按原版本验证，但系统 MUST NOT 自动补写、删除、移动研究上下文字段或重算其 hash 以伪装成 v3；接收方遇到未知版本或把 v2/v3 字段混用时 MUST fail closed。

#### Scenario: 读取历史 v2 Handoff
- **WHEN** 调用方显式请求校验一个未修改的历史 `PortfolioHandoff v2`
- **THEN** 系统按 v2 契约验证并保持原 hash，不将其静默迁移为 v3

#### Scenario: v3 包含旧能力字段
- **WHEN** 一个声称为 v3 的 Handoff 仍包含能力状态、研究计划、研究问题或持有期限
- **THEN** v3 Schema 校验失败，不能把混合契约交给下游

## MODIFIED Requirements

### Requirement: portfolio-intake 必须是独立产品 Skill
系统 SHALL 提供单一 `portfolio-intake` Skill，接受一张或多张持仓截图、手工描述或两者组合，统一识别账户快照、普通股、ETF 和上市期权，并输出 `PortfolioDraft`、集中澄清问题或已确认 `PortfolioHandoff`。系统 MUST NOT 为股票、ETF、期权、现金或保证金分别创建输入 Agent；该 Skill MUST NOT 研究证券、生成买卖动作、充当 CIO、判断下游 Agent 可用性、调用研究 Agent 或自动启动 `portfolio-council`。

#### Scenario: 用户上传持仓截图
- **WHEN** 用户调用 `portfolio-intake` 并提供包含股票、ETF、期权和账户余额的可读取截图
- **THEN** 同一个 Skill 提取全部可见输入事实并生成统一 Draft，而不是启动多个专业研究 Agent 或输出投资建议

#### Scenario: 用户手工输入组合
- **WHEN** 用户仅用文字提供持仓、现金、购买力或保证金字段
- **THEN** 同一个 Skill 使用相同 Draft 与确认流程，不要求图片或伪造图片来源

### Requirement: PortfolioDraft 必须保留不确定性和来源
`PortfolioDraft` MUST 允许缺失、歧义和冲突。每项持仓及账户事实 MUST 通过字段级 lineage 可追溯到 `source_id`、`as_of`、`retrieved_at` 和来源内容 hash；截图不可见、被裁切、券商语义未知或无法确定的字段 MUST 标记为 `MISSING`、`AMBIGUOUS` 或 `CONFLICTING`，不得猜测。用户修订 SHALL 作为新来源保存，并产生新的 Draft hash。

#### Scenario: 截图未显示可用资金
- **WHEN** 截图没有可用资金，但明确显示现金余额
- **THEN** Draft 保留现金并将可用资金标记为缺失，不能复制现金或写成零

#### Scenario: 截图未显示现金
- **WHEN** 截图没有现金余额
- **THEN** Draft 将现金标记为缺失并集中请求补充，不能自动写成零或用购买力代替

#### Scenario: 用户修正数量
- **WHEN** 用户纠正模型提取的持仓数量
- **THEN** Draft 保留原提取与用户修订来源，更新 hash，并使旧确认失效

### Requirement: Intake 必须区分普通股、ETF 与期权
Draft 与 Handoff MUST 使用可辨别资产结构支持 `COMMON_STOCK`、`ETF` 与 `OPTION`，但资产类型只描述用户持有的证券事实，不声明下游 Research Capability。ETF MUST 保留其自身证券身份，不得伪装为普通股；期权 MUST 保留标的证券、`CALL/PUT`、到期日、执行价、合约乘数、可选原始合约标识及带符号数量。数量为零 MUST 被拒绝；负数 MUST 表示已有空头仓位而不是输入错误或新增交易授权。

#### Scenario: 组合包含杠杆 ETF
- **WHEN** 截图明确显示 SOXL 等 ETF 持仓
- **THEN** Draft 与 Handoff 将其记录为 `ETF` 并完整保留，不生成 `etf-research` 状态或分析杠杆结构

#### Scenario: 组合包含空头 Put
- **WHEN** 截图显示数量为负的 Put 期权
- **THEN** Intake 保留负数量及期权身份，不生成 `options-research` 状态，且输入接受不代表允许新增空头交易

#### Scenario: 期权标识被截断
- **WHEN** 截图只显示部分合约标识或无法确定执行价
- **THEN** Draft 将对应字段标记为缺失或歧义并集中请求用户确认，不得猜测后生成 Handoff

### Requirement: Handoff 前必须进行最小确定性校验
系统 MUST 校验非零带符号数量及单位、明确现金余额、基础币种、资产辨别与身份状态、期权身份和乘数、重复证券、组合范围、字段级来源闭合和确认 hash。现金未知不等于零；平均成本、可用数量、可见报价、市值、盈亏、可用资金、购买力及保证金字段 MAY 缺失且不得单独阻断输入确认。歧义证券、无法完整识别的期权合约或悬空 lineage MUST 明确列出并阻断 Handoff，不得静默删除。

#### Scenario: 明确零现金
- **WHEN** 用户或来源明确确认现金余额为零
- **THEN** 零值合法并保留来源，不与未知现金混淆

#### Scenario: 保证金字段全部缺失
- **WHEN** 完整组合与现金已确认，但截图没有任何保证金字段
- **THEN** Handoff 以未知保证金状态通过输入校验，并明确其信息缺口

#### Scenario: 期权字段完整
- **WHEN** 用户确认期权标的、类型、到期日、执行价、合约乘数和数量
- **THEN** Handoff 保留完整期权结构，不附加研究能力或交易授权字段

### Requirement: 输入接受不得扩大研究或交易权限
Intake SHALL 如实表示用户已有普通股、ETF、期权与空头仓位，但 MUST NOT 因此授权建立新仓、卖空、衍生品交易、真实下单或任何研究结论。Intake MUST NOT 读取当前 Agent Package 的 Research Skill/Agent 清单，也不得输出能力缺口、Council 就绪状态、研究问题、持有期限、benchmark、Mandate、研究范围、研究批次或派发结果；这些任务上下文和判断只能由独立 `CouncilRequest` 与后续 `portfolio-council` 承担。

#### Scenario: Intake 接受期权但 Council 尚无 Options Skill
- **WHEN** 有效 Handoff 包含期权而当前候选版本没有对应研究能力
- **THEN** Intake 仍生成中立且完整的 Handoff；是否能够研究该期权由后续 Council 判断，Intake 不删除持仓也不伪造能力状态

### Requirement: 所有输入持仓都必须是研究对象
Portfolio 与 Handoff Schema MUST NOT 设置持仓数量业务上限。Handoff MUST 完整保存用户确认范围内的全部 Position；不得截断、抽样、只取前三只或要求用户另选重点标的。是否将这些 Position 全部纳入某次研究由独立 `CouncilRequest` 声明，改变研究请求不得改变 Handoff 或要求重新确认账户状态。

#### Scenario: 输入十只股票
- **WHEN** 用户确认包含十只证券的组合
- **THEN** Handoff 完整保留十只且不包含下游研究选择；引用该 Handoff 的 `CouncilRequest` 可声明十只全部为研究对象

#### Scenario: 实现存在固定数量上限
- **WHEN** Schema、Skill 或交接器试图因持仓数量超过固定值而删除或拒绝合法持仓
- **THEN** 验收失败；资源控制只能由后续 Council 透明分批，不能改变已确认 Handoff

### Requirement: PortfolioHandoff 必须兼容 Council 输入边界
`PortfolioHandoff v3` SHALL 只包含确认后的完整多资产 Portfolio、规范化 `account_snapshot`、Portfolio 声明范围、字段级来源 lineage、Draft hash、确认记录和完整性/勾稽状态。它 MUST 能在不读取 Research Agent 配置、不启动 Council 的情况下单独验证，并不得包含 Research Capability、Council readiness、研究计划、研究问题、持有期限、研究范围、benchmark、Mandate、截图推导的市场 Evidence、Thesis、动作或订单指令。

#### Scenario: 独立验证 Handoff
- **WHEN** 确认后的 v3 Handoff 提交给交接校验器
- **THEN** 校验器确认 Portfolio 与全部输入证券一致、数量和价格单位明确、账户字段零值和未知值可区分、字段级来源闭合且确认有效，不读取研究请求、Research Agent 或调用研究 LLM
