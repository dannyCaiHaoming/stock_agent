## ADDED Requirements

### Requirement: 只读券商账户事实必须保留私人来源与双时间语义
通过受支持只读券商适配器取得的账户快照、订单、成交、费用、资金活动和资产点 MUST 分别包含稳定 `source_id`、事实有效或业务时间 `as_of`、系统获取时间 `retrieved_at`、内容 hash 和脱敏账户引用。时间字段 SHALL 保留 Provider 原始值及时区、规范化 UTC，以及仅用于美国市场日/月分组的 `America/New_York` 市场日期；只有业务日期而无精确时刻时必须保留日期精度限制，不能伪造成成交时刻。订单创建、状态更新时间、成交时间、资金业务日期和 API 获取时间不得合并为一个时间。上游修订 SHALL 追加新版本而不是覆盖旧事实。

每条证券相关活动 SHALL 优先保存 Tiger 稳定合约标识，并同时保存显示代码、市场、币种、资产类型和期权原始结构字段；ticker 不得单独作为跨历史版本的永久身份。无法建立稳定证券身份的活动可以显示，但 MUST 从 FIFO episode 和按证券聚合中排除并说明原因。

#### Scenario: 订单成交后费用延迟更新
- **WHEN** 同一订单先取得成交状态，之后取得不同内容 hash 的费用明细
- **THEN** 系统保存两个获取版本及各自时间，历史分析只能选择在其截止点已经可知的版本

### Requirement: 私人账户证据不得自动进入证券研究 Evidence
券商账户事实与个人交易复盘数据 SHALL 保存在私人账本和分析包中，MUST NOT 自动进入 Company、Macro、Market、Independent Skeptic 或 CIO 的公开资料 Evidence Gate。若未来 Capability 需要使用持仓或个人历史，必须通过显式版本化输入契约、最小字段投影和用户授权引用；本 Change 只允许当前持仓通过已确认 `PortfolioHandoff v3` 进入既有研究边界。

#### Scenario: Company Agent 查询用户成交历史
- **WHEN** Company 研究 Agent 请求私人账本、交易时间或成本信息
- **THEN** 当前工具面拒绝请求，Agent 只能看到其既有允许 Evidence；已确认 Handoff 的持仓字段仍按原契约处理

### Requirement: 券商认证与网络客户端必须与 Agent 上下文隔离
RSA 私钥、TBHK Token、完整账户号、配置文件正文、官方 SDK Client 和任意券商网络调用能力 MUST 只存在于显式同步进程的受限本地边界。Runtime Agent、确定性分析、浏览器、研究 MCP、Evidence Bundle、Prompt、Trace 和普通产物不得包含或引用这些对象。脱敏账户引用、同步状态和错误类别可以进入确定性产物，但认证错误正文必须经过清理。

#### Scenario: 生成确定性分析和交易页面
- **WHEN** 系统基于已验证账本生成分析包并由 `/trades` 读取
- **THEN** 分析与页面只获得脱敏活动、指标和稳定引用，不获得配置目录、账户号、Token、私钥或 Tiger Client
