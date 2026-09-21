## ADDED Requirements

### Requirement: 高价值接口必须有明确取舍与来源复用依据
本 Change MUST 为营收分部、管理层、财报日历、新闻线索、市场涨跌分布、期权标的总览与历史统计/波动率完成有界候选评估，并核对财务、估值、公司行动和行业关系的既有来源覆盖。每项 MUST 记录研究问题、实际资料缺口、来源证据以及接入、已有来源足够、权限受限或暂缓的结论。系统 MUST 优先复用已获取资料和既有采集能力，不以全部接口接入或调用成功数量作为验收标准。可复用现有链路且确有增量的候选 SHALL 接入；需要新增服务或超出当前研究职责的候选 SHALL 保留后续建议。

#### Scenario: 已有来源能回答同一问题
- **WHEN** SEC、Yahoo 或官方宏观已取得合格字段而补充接口只重复相同内容
- **THEN** 记录已有来源足够并验证其正式消费，不新增重复请求，也不将未调用接口列为系统缺陷

#### Scenario: 候选方法存在但账号不可用
- **WHEN** 文档与 SDK 有该方法而有界验证返回权限不足或缺少关键字段
- **THEN** 保留真实限制与替代来源；评估任务可以完成，但不能把该接口记为已接入

### Requirement: 补充采集必须受共享预算与复用约束
系统 MUST 同时限制方法级、证券级和全批请求/时长预算，重试与分页计入预算；同批共享 Macro/Market 资料 MUST 只按批准参数采集一次并复用。增强项不能挤占核心采集预算。Yahoo 动态期权 MUST 优先复用既有能力接入正式采集，不能仅以配置声明证明可用。

#### Scenario: 多只持仓需要同一宏观资料
- **WHEN** 同批多个任务需要相同指标或市场统计
- **THEN** 它们引用同一冻结资料，共享请求次数不随持仓数重复增加

#### Scenario: 增强项预算不足
- **WHEN** 核心采集后剩余预算不足以获取额外历史或合约波动率
- **THEN** 增强项记录预算排除与影响，不无限重试或扩大请求

### Requirement: Moomoo 能力必须按文档、运行版本和纵向闭环分别晋级
系统 MUST 为每项 Moomoo Quote 能力分别记录官方文档版本、实际 SDK 版本、OpenD server version、方法签名、实际响应字段、权限与最后验证时间。官方 v10.11 文档列出接口或字段只证明 `DOCUMENTED`；只有当前锁定 SDK/OpenD 的真实只读响应成功后才可标记 `SPIKED`，完成版本化 allowlist、Normalize、PIT、正式 Collector、Gate/MCP 和专业 Skill 消费后才可标记 `RESEARCH_VALIDATED`。系统 MUST NOT 因网页标题、方法存在、fixture 或直接 SDK Spike 而跳过中间状态。

#### Scenario: 文档字段未出现在当前 SDK 响应
- **WHEN** v10.11 文档声明 Morningstar 的 `fundamentals_content`、`valuation_content` 或 `pdf_url`，但当前锁定运行版本没有返回该字段
- **THEN** 能力矩阵保留文档字段与实际字段差异，Normalize 输出具体 gap，不将字段加入可用覆盖或宣称 v10.11 runtime 已完成

#### Scenario: 直接 SDK Spike 成功但正式 Collector 未接线
- **WHEN** `get_market_snapshot` 对期权合约返回动态字段，但版本化 adapter、Collector 或 Skill 尚未消费
- **THEN** 能力最多标记为 `SPIKED` 或等价状态，不标记为正式接入或研究验证通过

#### Scenario: 运行版本升级
- **WHEN** 安装的 Moomoo SDK 或 OpenD server version 与批准 manifest 不同
- **THEN** 受影响能力 fail closed，并在方法签名、响应字段、PIT 和聚焦测试重新验证后生成新的 manifest/version/hash，不以版本范围静默放行

### Requirement: 动态期权补充必须形成有界同源快照
系统 MUST 使用批准的只读 Quote 方法取得标的当前快照、到期日、静态合约和选定合约动态行情，并由确定性策略限制到期日、行权价与合约总数。动态快照 MUST 保留实际可得的 bid、ask、last、volume、OI、IV、Greeks、合约属性、币种、交易时段及字段时间语义；静态链、筛选结果或缺失字段 MUST NOT 冒充动态期权面。来源选择声明 Yahoo 主源、Moomoo 回退时，两源都 MUST 有真实采集路线或准确标记为未实现。

#### Scenario: Moomoo 动态期权回退成功
- **WHEN** Yahoo `options_snapshot` 失败，Moomoo 静态链与所选合约动态 snapshot 在预算内成功且通过 PIT/Gate
- **THEN** 系统记录 Yahoo 失败、Moomoo 回退、确定性选择策略和实际字段覆盖，并把同源 Moomoo 快照交给 `OPTIONS_FLOW`

#### Scenario: 只有静态链成功
- **WHEN** 到期日和合约属性可得，但动态 snapshot 权限不足、字段缺失或超时
- **THEN** 数据集保持 `PARTIAL/STATIC_CHAIN_ONLY`，明确缺失 bid/ask/volume/OI/IV/Greeks，不生成完整 options snapshot

#### Scenario: 全链规模超过预算
- **WHEN** 标的返回的静态合约数量超过批准上限
- **THEN** 确定性层按版本化策略选取有限到期日和现价附近合约，保存总覆盖与排除数量，禁止把全链传给 Agent 或循环扩大请求

### Requirement: 高价值 Market、Macro 和研究补充接口必须保持来源语义
系统 MUST 对 Moomoo 的资本分布、全市场期权统计、期权波动率、Macro Indicator History、FedWatch、Dot Plot、Economic Calendar、评级汇总和 Morningstar 分别定义数据集、来源类型、参数预算、分页上限和允许用途。Moomoo 宏观实际值、前值、供应商共识、FedWatch 概率、FOMC Dot Plot、评级和 Morningstar 观点 MUST 保持不同语义，不得互换或覆盖 BLS、Treasury、Federal Reserve、SEC 或 Yahoo 的职责。

#### Scenario: Moomoo 宏观值与 BLS 官方值同时可得
- **WHEN** 同一通胀或就业指标同时存在合格 BLS Evidence 和 Moomoo Macro History
- **THEN** BLS 保持官方主源，Moomoo 作为带覆盖与版本限制的二级补充，冲突并列保留而不选择静默 winner

#### Scenario: FedWatch 概率可得
- **WHEN** Moomoo 返回未来会议目标利率概率
- **THEN** 系统将其标记为市场隐含/供应商市场预期，只允许 Market Context 使用，不描述为 Federal Reserve 的政策承诺或官方预测

#### Scenario: 评级分页仍有后续页
- **WHEN** 机构或分析师评级响应返回非终止 `next_key`
- **THEN** 系统在批准页数内停止，保留未覆盖分页和外部观点限制，不把当前页面描述为全部机构或分析师覆盖

### Requirement: 新能力必须保持 OpenD Quote-only 和内容许可边界
扩展 Moomoo 能力 MUST 继续通过 loopback `OpenQuoteContext` 和逐方法 allowlist；不得开放通用 SDK 调用、Trade Context、账户、用户持仓、订单、资金、交易解锁、远程 OpenD 或客户端私有会话。Morningstar、评级 URL 和供应商分析文本 MUST 标记许可与内容层级；系统不得因取得下载地址而自动下载、再分发或把供应商判断转为确定性事实。

#### Scenario: 新接口返回账户或认证材料
- **WHEN** Quote 响应或错误意外包含账号、Token、Cookie、设备秘密或交易字段
- **THEN** 内容扫描拒绝其进入缓存、Evidence 和模型上下文，并以脱敏错误隔离该能力

#### Scenario: Morningstar 正文可读
- **WHEN** 用户有权通过 OpenD 读取 Morningstar section 正文
- **THEN** 系统仅按内部研究的授权内容层级保存必要正文、section 时间和来源限制，不声明再分发许可，也不自动抓取 `pdf_url`
