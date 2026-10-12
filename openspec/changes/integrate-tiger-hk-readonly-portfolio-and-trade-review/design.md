## Context

动机与范围见 [proposal.md](proposal.md)。当前仓库已经具备 `PortfolioDraft/PortfolioHandoff v3`、仓库外私人产物保护、内容 hash、SQLite 追加式 Research Memory 和只监听 `127.0.0.1` 的只读浏览器，但没有券商适配器、私人账户账本或交易历史分析契约。`PortfolioHandoff v3` 仍只支持 `market=US`、`currency=USD` 的普通股、ETF 和上市期权；现有浏览器默认排除全部账户上下文。

Tiger Python SDK 的账户查询和交易写操作共存在 `TradeClient` 上；TBHK 还需要本地 Token 文件。因此不能把 SDK Client 作为通用 MCP、Agent Tool 或网页依赖暴露。老虎历史接口又具有时间窗、分页、费用按单查询、记录后续修订和实际保留范围不确定等特点，“请求成功”不足以证明账户完整生命周期。

## Goals / Non-Goals

**Goals:**

- 以最小、可审计的本地适配层读取 TBHK 个人账户，并在代码层对全部券商写操作 fail closed。
- 复用现有 Intake 确认边界，将受支持的当前美股资产转成 Draft；混合市场账户以明确声明的 US/USD `USER_DEFINED_PORTFOLIO` 进入 Handoff，而不是建立第二套 Portfolio 或假称覆盖整个券商账户。
- 在仓库外保存可以增量更新、版本化和证明覆盖范围的私人交易账本。
- 将数值核算与图形展示分层，确保页面中的每个指标都能追溯到冻结账本与确定性公式。
- 复用现有 Python 标准库本地浏览器与服务器端 SVG，不增加 Web 前端栈。

**Non-Goals:**

- 不提供或测试下单、预览下单、改单、撤单、换汇、转账、交易解锁、行情抢占或账户写入。
- 不把 Tiger 作为公司、宏观、市场或期权研究行情源；现有 SEC、Yahoo、Moomoo 数据组合保持不变。
- 不在第一版聚合港股、窝轮、牛熊证、期货、基金或非 USD 绩效，也不扩展现有 Handoff 到多市场多币种。
- 不生成税务报表、不重建法定税务批次、不把真实交易史称为策略回测，也不执行 CIO、Risk 或候选晋升。
- 不在第一版实现 LLM Historical Trade Reviewer；确定性分析与 `/trades` 不依赖模型可用性，后续只有在真实账本与页面稳定后才另行评估文字复盘 Agent。
- 不增加常驻服务、自动计划任务、浏览器同步按钮、第二套编排器、前端框架或远程账户门户。

## Decisions

### 1. 用独立同步进程隔离 Tiger SDK 与产品 Runtime

新增一个显式本地 CLI 作为唯一券商网络入口，职责分为 `preflight`、`snapshot`、`sync`、`analyze`。只有前三个需要时才惰性加载官方 SDK；分析只读取账本。CLI 接收仓库外配置目录引用和仓库外 ledger root，不接受私钥、Token 或完整账户号参数。

同步层包装一个固定方法集合：账户发现、`get_prime_assets`、`get_positions`、`get_analytics_asset`、`get_orders`、`get_transactions`、`get_order(show_charges=True)`、`get_fund_details` 和 `get_funding_history`。包装器不提供底层 Client getter、通用 `call` 或字符串反射入口。SDK 新增方法不会自动获得权限；交易、转账、换汇、权限抢占和 Push 方法在适配层无入口，并用带调用记录的 fake client 验证拒绝发生在网络前。

不将 Tiger 包装成 MCP。这样 Runtime Agent、网页和 Council 不可能通过工具发现 SDK 的写方法，依赖也不会进入正常研究启动路径。

备选方案是直接提供 Tiger MCP 的 read-only 模式；拒绝该方案，因为官方 MCP/SDK 的功能面仍包含交易语义，且 Agent 不需要直接查询账户。另一个方案是抓 App Cookie；拒绝，因为它不属于稳定官方契约并扩大凭据暴露。

### 2. 凭据只存在于仓库外配置目录

同步器读取官方导出的 `tiger_openapi_config.properties` 与 TBHK 的 `tiger_openapi_token.properties`。目录必须不在仓库内、非符号链接逃逸且仅当前用户可访问；私钥和 Token 文件要求严格文件权限。诊断只报告缺失字段名、牌照、Token 状态类别和随机生成的本地 `account_ref`，不回显文件内容、绝对路径或完整账户号。

SDK Token 自动刷新若启用，只允许原子更新同一配置目录中的 Token 文件；首版默认不由网页或分析触发。认证失败不会回退到 Cookie、Keychain、客户端数据库或手工粘贴。日志在 SDK 层关闭 debug payload，并在产品层再次清理 `account`、`token`、`private_key`、`authorization`、`secret` 等字段。

账户引用采用首次初始化时写入私人 ledger metadata 的随机 ID；账本和下游产物不保存从账户号可直接推导的 hash。完整账户号仍只存在于官方配置和请求内存中。

### 3. 当前快照复用 PortfolioDraft v3，历史活动使用独立契约

数据流为：

```text
Tiger snapshot --> private source snapshot --> PortfolioDraft v3 --> user confirmation --> PortfolioHandoff v3

Tiger history  --> PrivateBrokerLedger --> TradeHistoryAnalysis --> /trades
```

当前快照先保存脱敏、字段允许列表化的全账户源对象和内容 hash，再转换为 Intake 观察。只有 US/USD 的普通股、ETF 和上市期权进入 Positions；其余资产进入与 Draft 关联但不参与 Handoff 完整性判定的账户覆盖清单，并显示为“已采集但投研接入待定”。混合市场账户的 Draft 使用 `portfolio_scope=USER_DEFINED_PORTFOLIO`，其 `portfolio_complete` 只表示声明的 US/USD 子组合已经完整纳入，不能解释为整个 Tiger 账户完整；只有账户全部资产都属于当前支持范围时才可使用 `BROKER_ACCOUNT`。

账户覆盖清单不得通过现有 `unsupported_assets` 路径把港股等排除项转换成阻断 Handoff 的 `unresolved_fields`。确认界面仍必须同时展示子组合边界、排除资产数量、市场、币种和原因。全账户净资产、现金、购买力、保证金和总盈亏不得复制为美股子组合数值；只有 Tiger 明确提供与声明子组合相同范围的 US/USD 分段数据时才可进入 Draft，否则对应字段保持未知并披露原因。券商成本、报价、市值和盈亏仍只是账户事实，不成为证券研究 Evidence。API 来源不会绕过 Draft 摘要和一次明确确认；新快照产生新 Draft，永不覆盖旧 Handoff。

历史订单、成交和资金活动不写进 Handoff，因为它们的基数、修订频率和生命周期与当前组合不同。它们也不进入 Research Memory，以避免私人账户数据与公开公司事实共享索引或权限面。

### 4. 使用一个独立 SQLite 私人账本

`PrivateBrokerLedger` 位于显式仓库外 root，使用一个带 schema version 的 SQLite 数据库和四组核心逻辑表：

- `activity_revisions`：以 `activity_type` 区分账户快照、持仓、订单、逐笔成交、费用、分红税费、公司行动和出入金，并保存规范化字段、允许字段 JSON、revision 与 hash；
- `asset_points`：保存每日资产、NAV、外部现金流引用和数据覆盖；
- `sync_windows`：保存随机 `account_ref`、历史起点及准确度、每类同步窗口、水位、分页 receipt、gap 和覆盖状态；
- `analysis_packages`：保存冻结输入 hash、公式版本、确定性指标和内嵌图形数据。

数据库内部行结构不逐一升级成公共 JSON Schema；第一版只维护 `TigerAccountSnapshot`、`BrokerSyncManifest` 和 `TradeHistoryAnalysis` 三个边界契约。图形数据内嵌在 `TradeHistoryAnalysis`，不增加单独 Chart Schema、内容寻址对象目录或按活动类别拆分的主表/修订表。

上游 ID 与 `account_ref` 组成稳定逻辑键；无稳定 ID 时使用记录类别、稳定证券身份、业务时间、方向、数量、价格/金额等允许字段产生确定性替代键，并标记其可靠性。相同键和相同内容 hash 只更新再次观察时间，不复制经济活动；相同逻辑键内容改变则在 `activity_revisions` 追加 revision。禁止 pickle、SDK 对象序列化或保存请求头。

选择 SQLite 是因为单机、单用户、增量去重和只读网页需要事务一致性；复用 Research Memory 会打破私人数据隔离。浏览器以 `mode=ro`、`query_only` 和短 busy timeout 打开账本；同步器用短事务提交完整窗口。

### 5. 全量同步以声明窗口、分类水位和 gap 证明完整性

首次同步使用用户在本地配置中声明的 `history_start`，并要求 `history_start_accuracy=EXACT|APPROXIMATE`。无论准确或估算，覆盖都只相对声明窗口成立；`APPROXIMATE` 不得用于证明账户生命周期完整。订单按官方限制使用有界日期片和 `page_token`/时间游标遍历全部状态；对每个存在实际成交数量的订单补取逐笔成交，并通过订单详情补取费用。资金明细、出入金和资产历史分别按各自分页/日期窗口取得，不把它们重复解释为成交。实现以固定预算、接口频率限制和指数退避约束请求，不递归无界探测“更早历史”。

每个窗口只有在页结束条件、去重计数与响应结构均成立后才提交 `COMPLETE`。失败窗口保存错误类别和重试状态，水位不能跨越它。后续同步从各数据类别水位开始，并回看一个版本化重叠期以接收订单状态和费用修订。

覆盖状态：

- `PARTIAL`：存在失败窗口、未知类别或不可解释差异；
- `API_COMPLETE_WITHIN_DECLARED_WINDOW`：声明窗口的全部请求与分页完成，但不证明 Provider 历史保留或账户起点；
- `FULL_HISTORY_RECONCILED`：为未来结单勾稽保留；第一版同步器不得产生该状态，也不把结单解析作为完成条件。

第一版必须完成声明窗口内的 API 遍历、覆盖证明和 gap 呈现，完成状态最多为 `API_COMPLETE_WITHIN_DECLARED_WINDOW`。券商结单解析与 `FULL_HISTORY_RECONCILED` 留给后续独立 Change，不能为满足名称虚构生命周期完整。

### 6. 数值计算、交易 episode 与图形数据分层

确定性分析从一个冻结 ledger revision set 生成 `TradeHistoryAnalysis`。金额按原币种保存；第一版聚合只接受 US/USD 记录，其他活动保留在活动表并标记排除。券商 reported realized P&L 与系统计算值分别保存。成交匹配只用于复盘 episode，`formula_version=v1` 使用按稳定证券身份、方向和成交时间排序的 FIFO；开放仓位、无法闭合的期权到期/指派、公司行动和身份不确定记录不强行配对，也不能称为税务 lot。

`formula_version=v1` 的最小确定性口径为：每日现金流调整收益在资产点和净外部现金流完整时按 `(期末资产 - 当日净外部现金流) / 期初资产 - 1` 计算，累计收益采用逐日连乘；drawdown 从同一累计收益序列的历史高点计算。胜率为净盈利的已闭合 FIFO episode 数除以全部净结果已知的已闭合 episode 数；盈亏比为平均盈利除以平均亏损绝对值；Profit Factor 为盈利总额除以亏损总额绝对值；单笔期望为已闭合 episode 的平均净盈亏。零分母、费用不完整、资产点缺失或现金流时间无法归属时对应净指标为 `unavailable`，不得补零。月度热力图使用月度现金流调整收益率，月度净盈亏另行展示。第一版不把换手率作为完成条件。

分析包包含：

- 现金流调整的收益序列、资产曲线和 drawdown；
- realized/unrealized、费用、分红与税费分层；
- 交易数、胜率、盈亏比、Profit Factor、期望和持有期；
- 订单状态、取消/拒绝/部分成交和交易时段统计；
- 按证券与月份的明细；
- 六组结构化图形数据及限制；
- 输入、公式、覆盖、排除、gap 与输出 hash。

### 7. `/trades` 复用现有服务器端页面和 SVG

浏览器增加可选 `--trade-ledger` 配置和独立只读 reader。未配置时 `/trades` 显示未配置，不扫描默认路径。页面导航、路由、模型和渲染遵循现有 Python 标准库模式；折线、回撤、热力图、柱形/分层、散点和时间线均从分析包的结构化数据生成 inline SVG，不引入 JavaScript 或外部图表库。

活动表由服务器端 query 参数分页筛选，订单、成交、费用和资金活动不合并语义。页面不提供原始账本下载，不显示完整账户号、源对象、配置路径或绝对路径。刷新只重新读取数据库；同步仍在独立 CLI。交易 reader 失败只影响 `/trades` 和 health 中对应诊断，不影响现有三域。

### 8. 产品边界和验证必须先改再接真实账户

实施开始先将根 `AGENTS.md` 的绝对券商禁令改为允许“已批准、严格只读、无 Agent 网络暴露”的账户数据接入，并同步 `PRODUCT.md`/`product/AGENTS.md`；下单和索取凭据禁令保持。代码与合成测试先完成，官方 SDK 使用固定版本及锁定来源。

真实验收只从现有 `scripts/run-product-smoke.sh` 宿主 launcher 的显式 Tiger 只读模式执行，由它调用同步 CLI：先做不返回金融数据的配置 preflight，再做最小账户/持仓读取，然后按用户本地 ledger root 执行一次有界初始同步、一次相同窗口重复同步和一次带重叠窗口的增量同步，最后生成确定性分析。验收必须证明重复同步不产生重复经济活动，重叠增量可以追加修订且水位不跨 gap。不得绕过宿主 launcher 直接用底层模块或临时脚本发起真实账户请求。验收记录只能保存脱敏状态、计数、时间窗和 hash；真实数据、配置、日志和私人分析留在仓库外。没有本地配置时，Change 可以完成确定性实现与合成验收，但不得宣称真实 TBHK 接入已跑通或完成归档批准。

## Risks / Trade-offs

- [SDK 同时包含交易方法] → SDK 只在独立同步模块惰性加载，固定包装器不暴露 Client，未知方法默认拒绝，并用 fake client 验证交易调用为零。
- [TBHK Token 30 天失效] → preflight 提供稳定过期状态；续期/刷新只发生在仓库外配置目录，失败不破坏账本或回退到非官方认证。
- [“全部历史”被误解为生命周期完整] → 保存历史起点的准确/估算状态、逐窗 receipt 和 gap；第一版最多输出 `API_COMPLETE_WITHIN_DECLARED_WINDOW`，不实现结单勾稽或产生 `FULL_HISTORY_RECONCILED`。
- [逐订单费用查询放大请求量] → 首次同步按预算分批，优先已成交且费用缺失订单，保存费用水位并复用成功记录；限流留下 gap 而非无限重试。
- [订单、成交、资金流水重复计入] → 在 `activity_revisions` 中以严格类型和 stable ID 保存不同语义，指标只消费明确允许的记录类别，并勾稽成交数量、费用和现金活动。
- [港股或多币种被错误聚合或阻断美股 Intake] → 全账户活动保留在私人账本与覆盖清单；混合账户只以显式 `USER_DEFINED_PORTFOLIO` 进入美股 Intake，港股标记为投研接入待定且不进入 Handoff 完整性判断。第一版计算严格使用 US/USD allowlist，页面显示排除计数且不隐式换汇。
- [私人账本泄漏] → 仓库外路径、严格权限、随机账户引用、字段允许列表、无下载、网页 no-store；凭据永不进入账本。首版不引入自制加密，依赖本机磁盘加密与目录权限，避免不可恢复的密钥管理复杂度。
- [网页读取时同步写入] → SQLite 短事务、只读连接、busy timeout；只显示完整提交版本，繁忙时提示重试。

## Migration Plan

1. 先同步开发/产品边界文档并加入新 Schema、合成 fixtures 和固定版本依赖；此时既有 Intake、Council 与浏览器行为不变。
2. 实现只读适配器、凭据 preflight 和合成 fake-client 测试；未通过写方法拒绝测试前不得连接真实账户。
3. 实现私人账本、全量/增量同步和 coverage receipt，再接当前快照到 Draft；旧截图/手工 Intake 与历史 Handoff 保持兼容。
4. 实现确定性分析与内嵌图形数据；再增加浏览器 reader、`/trades` 与窄屏展示。
5. 使用仓库外合成 ledger 完成聚焦测试和浏览只读 hash 检查；之后仅在用户本机配置就绪时执行最小真实只读验收。
6. 回滚时停止使用新同步 CLI 和 `--trade-ledger` 参数即可；不迁移或删除既有 Research Memory、Handoff 或私人账本。新 ledger schema 不受支持时只读拒绝，不自动降级重写。

## Open Questions

- 官方 SDK 的最终锁定版本、真实 TBHK 响应中各资产/订单字段完整度和账户可追溯最早日期由实施 Spike 记录；这些结果只决定字段 gap、批次预算和是否需要结单补齐，不改变只读边界、三态覆盖或第一版 US/USD 分析范围。
