## Purpose

定义老虎证券香港个人账户的严格只读数据接入、私人账本、历史覆盖证明与隐私边界，使当前持仓和历史活动能够被现有 Intake 与复盘能力安全消费，同时从产品工具面彻底排除交易和账户写入。

## ADDED Requirements

### Requirement: Tiger 接入必须使用官方 TBHK 本地配置且不接收凭据正文
系统 SHALL 仅从用户显式指定、位于仓库外且权限受限的本地目录加载官方 Tiger OpenAPI 配置。TBHK 个人账户至少需要可解析的 `tiger_id`、账户、`license=TBHK`、RSA 私钥以及 `tiger_openapi_token.properties`；私钥、Token、密码、完整账户号和可重放认证材料 MUST NOT 进入命令参数、日志、Git、模型上下文、普通运行产物或网页响应。系统 SHALL 接受配置目录引用而不是要求用户在聊天、表单或配置样例中粘贴凭据。

#### Scenario: 用户提供仓库外配置目录
- **WHEN** 显式同步命令读取权限合格且内容完整的 TBHK 配置目录
- **THEN** 连接器可以建立只读会话，并且诊断只返回脱敏账户引用、牌照类型和连接状态，不回显任何认证内容

#### Scenario: Token 缺失或过期
- **WHEN** TBHK Token 文件缺失、不可读或服务端拒绝过期 Token
- **THEN** 本次同步以稳定认证错误停止，不删除既有账本、不退回 Cookie 抓取、不要求用户发送 Token 正文，并提示用户在官方管理台重新生成或续期

### Requirement: 券商接口必须由硬白名单限制为读取
Tiger 适配器 SHALL 只暴露账户发现、账户资产、持仓、历史资产、订单查询、逐笔成交查询、单笔订单费用查询、资金明细和出入金历史等读取操作。产品包 MUST NOT 暴露或透传下单、预览下单、改单、撤单、换汇、转账、交易解锁、行情抢占、账户修改、任意 SDK 方法调用或 Push 写入能力；未知方法和新增 SDK 方法默认拒绝。Runtime Agent、网页和研究 Tool MUST NOT 获得 Tiger Client、配置对象或任意券商网络工具。

#### Scenario: 调用允许的账户读取操作
- **WHEN** 同步器请求白名单内的账户资产、持仓或历史记录
- **THEN** 适配器执行对应只读查询并记录方法、参数范围、结果数量和时间，不记录凭据或完整账户号

#### Scenario: 请求交易或未知 SDK 方法
- **WHEN** 调用方请求下单、撤单、改单、转账、换汇、交易解锁或白名单外方法
- **THEN** 适配器在发出网络请求前拒绝调用并记录稳定拒绝码

### Requirement: 当前账户快照必须完整保留范围与未支持资产
系统 SHALL 在一个一致的采集批次内获取账户资产与全部可见持仓，并形成版本化账户快照。第一版只有 `market=US`、`currency=USD` 且资产类型为普通股、ETF 或上市期权的持仓可以进入 `PortfolioDraft v3`；其他市场、币种或资产类型 MUST 保留原始身份、数量、币种、来源和 `UNSUPPORTED_FOR_PORTFOLIO_INTAKE` 原因，并在账户覆盖清单中标记“已采集但投研接入待定”，不得静默丢弃、换汇、合并或冒充美股。混合市场账户的快照覆盖状态与 US/USD 子组合的 Intake 完整性 MUST 分开表达；券商快照只产生 Draft，MUST NOT 自动确认 Handoff 或启动研究。

#### Scenario: TBHK 账户同时持有美股和港股
- **WHEN** 同一快照返回 USD 美股与 HKD 港股
- **THEN** 全账户快照和私人账本保留两类资产；全部受支持美股进入 `USER_DEFINED_PORTFOLIO` Intake 候选，港股作为投研接入待定项出现在覆盖清单且不阻断美股确认，系统不把港股或全账户汇总金额换算或冒充为 USD 子组合值

#### Scenario: 账户没有受支持的美股资产
- **WHEN** 快照只有港股、现金或其他未支持资产
- **THEN** 系统保存只读快照和未支持清单，但不构造伪造或空的 `PortfolioHandoff v3`

### Requirement: 历史同步必须覆盖全部 API 可见活动并可安全续跑
首次同步 SHALL 针对用户声明的 `history_start` 到同步截止时间执行，并保存 `history_start_accuracy=EXACT|APPROXIMATE`；估算起点不得被解释为开户日期。同步按接口限制拆分有界时间窗并遍历全部分页，采集所有状态订单；对每个存在实际成交数量的订单补取逐笔成交和订单费用，并分别采集资金明细、出入金及历史资产点。后续同步 SHALL 使用保存的水位和有界重叠窗口重新检查可修订记录；任一页或时间窗失败只留下显式 gap，不得推进覆盖水位越过失败区间。同步 MUST 遵守 Provider 频率限制并支持安全重试，不得以无限循环或无界请求追求“全量”。

#### Scenario: 首次同步跨越多年历史
- **WHEN** 声明窗口超过单次接口允许跨度或单页容量
- **THEN** 同步器分窗、分页直至每个窗口出现确定完成条件，并保存每个窗口的请求范围、页数、记录数和状态

#### Scenario: 中间时间窗限流或失败
- **WHEN** 某个窗口返回限流、认证以外的暂时错误或分页不完整
- **THEN** 同步保留已经提交的完整窗口，将失败窗口记为 gap，不把后续成功伪装成连续完整历史，并允许下一次从缺口安全续跑

### Requirement: 私人交易账本必须追加式、可去重且可审计
系统 SHALL 将真实账户活动保存到仓库外的单一 SQLite 私人账本，与 Research Memory、冻结研究运行和 Git 分离。第一版账本 SHALL 只使用活动修订、资产点、同步窗口和分析包四组核心逻辑表；订单、成交、费用和资金活动通过严格 `activity_type` 与类型专属字段保持语义，不为每种类型扩建独立主表/修订表或内容寻址对象目录。每条记录 MUST 包含稳定本地身份、脱敏账户引用、记录类别、Provider 稳定 ID 或确定性替代键、`source_id`、`as_of`、`retrieved_at`、原始内容 hash、规范化版本和同步批次；上游同一 ID 内容改变时 SHALL 新增 revision 并保留旧版。订单不能等同于成交，汇总订单不能覆盖逐笔成交。

#### Scenario: 重复同步同一逐笔成交
- **WHEN** 两次同步返回相同成交 ID 和相同内容 hash
- **THEN** 账本只保留一个规范记录并记录再次观察，不重复计算数量、费用或盈亏

#### Scenario: 上游修订订单费用
- **WHEN** 已有订单 ID 后续返回不同费用或状态内容
- **THEN** 账本追加新 revision、保留两个获取时点，并使当前分析选择不晚于分析截止点的最新可知版本

### Requirement: 历史覆盖状态必须区分 API 完整与生命周期完整
每次同步 SHALL 输出覆盖清单，至少包含声明起点、起点准确度、截止点、实际最早/最晚记录、分窗与分页结果、重复数、修订数、失败区间、各记录类别计数和完整性状态。`API_COMPLETE_WITHIN_DECLARED_WINDOW` 只表示声明窗口内的全部请求与分页完成，不代表 Provider 返回了账户生命周期的每条记录。`FULL_HISTORY_RECONCILED` 仅为未来结单勾稽保留；第一版同步器 MUST NOT 产生该状态，也不把结单解析作为完成条件。其余结果必须为 `PARTIAL` 或 `API_COMPLETE_WITHIN_DECLARED_WINDOW`。

#### Scenario: API 分页完成但早期记录未知
- **WHEN** 所有请求都成功但用户未确认账户历史起点或接口未证明历史保留范围
- **THEN** 覆盖最多标记 `API_COMPLETE_WITHIN_DECLARED_WINDOW`，页面明确显示不能证明完整生命周期

#### Scenario: 第一版请求生命周期完整状态
- **WHEN** 第一版同步已经完成声明窗口内全部 API 请求，但尚未实现独立结单勾稽
- **THEN** 覆盖最多标记 `API_COMPLETE_WITHIN_DECLARED_WINDOW`，不会产生 `FULL_HISTORY_RECONCILED`

### Requirement: 连接、同步和读取职责必须分离
只有用户显式启动的本地同步入口 MAY 加载 Tiger 配置、联网并写入私人账本。`portfolio-intake`、确定性分析和本机浏览器 SHALL 只读取已经提交且通过校验的快照、账本或分析包；页面打开、刷新、筛选和分析阅读 MUST NOT 连接 Tiger、刷新 Token、调用模型或写入任何账户数据。

#### Scenario: 用户在网页点击重新读取
- **WHEN** 浏览器已经配置私人账本且用户刷新 `/trades`
- **THEN** 浏览器只重新读取本地已提交版本，Tiger 请求数和账本内容均不改变
