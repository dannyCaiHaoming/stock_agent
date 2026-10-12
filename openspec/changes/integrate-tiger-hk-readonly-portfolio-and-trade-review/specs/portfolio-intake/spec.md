## MODIFIED Requirements

### Requirement: Intake 必须显式表达证券身份状态
每个 Position SHALL NOT assume ticker alone is a permanent canonical identity. Draft 与 Handoff SHALL 保存原始显示代码、原始名称、市场、资产类型、身份状态、可选 canonical security ID 和歧义候选。身份状态至少支持 `OBSERVED`、`USER_CONFIRMED`、`RESOLVED` 和 `AMBIGUOUS`；生成 Handoff 前不得保留 `AMBIGUOUS`，也不得根据相似名称静默选择候选。期权除结构字段外还 SHALL 保存可选原始合约标识和调整状态；无法排除调整合约歧义时必须澄清。

来源类型 SHALL 支持 `SCREENSHOT`、`MANUAL`、`USER_CORRECTION`、`BROKER_READ_ONLY_API` 与 `BROKER_STATEMENT`。`BROKER_READ_ONLY_API` 可以承载通过 `tiger-readonly-broker-data` 契约取得的 Tiger 当前账户快照；它不代表任意券商、任意 Tiger SDK 方法或历史交易账本可以直接成为 Handoff。`BROKER_STATEMENT` 继续只表示受支持的显式结单输入，不因来源类型存在而宣称已经完成任意格式解析。

#### Scenario: 同一代码存在身份歧义
- **WHEN** 原始代码无法在市场与资产类型上下文中唯一对应证券
- **THEN** Draft 保存候选并标记 `AMBIGUOUS`，用户确认或后续只读身份解析前不得生成 Handoff

#### Scenario: Tiger 只读账户快照进入 Intake
- **WHEN** 有效 Tiger 快照包含身份已解析的 USD 美股、ETF 或美股期权
- **THEN** Intake 以 `BROKER_READ_ONLY_API` 保存字段级来源并生成仍需用户确认的 Draft，不因 API 来源自动生成 Handoff

#### Scenario: 只读券商来源尚未实现
- **WHEN** 调用方声明 `BROKER_READ_ONLY_API` 或 `BROKER_STATEMENT` 但没有对应受支持适配器和有效来源产物
- **THEN** 系统 fail closed，不把来源枚举本身当作已完成连接或解析证明

## ADDED Requirements

### Requirement: Tiger Draft 必须保持现有美股美元边界并分离子组合完整性与账户覆盖
从 Tiger 快照生成的 `PortfolioDraft v3` SHALL 只包含现有 Schema 支持的美国市场、USD 普通股、ETF 和上市期权，并引用同一次全账户快照及账户覆盖清单。所有被排除的市场、币种和资产类型 MUST 出现在与 Draft 关联的等价账户覆盖清单中，包含原始标签、原因和来源，并标记为“已采集但投研接入待定”；这些排除项不得通过现有 `unsupported_assets`/`unresolved_fields` 语义阻断受支持子组合的确认。系统不得用汇率或符号猜测把港股、窝轮、牛熊证、期货或基金转换为受支持持仓。

当账户同时包含受支持与未支持资产时，Draft MUST 使用 `portfolio_scope=USER_DEFINED_PORTFOLIO`，并把声明范围明确为同一快照中全部可验证的 US/USD 受支持资产；此时 `portfolio_complete=true` 只表示该声明子组合完整，不代表整个券商账户完整。只有同一快照中的全部资产均属于当前支持范围时，Draft MAY 使用 `BROKER_ACCOUNT`。全账户净资产、现金、购买力、保证金和总盈亏 MUST NOT 作为子组合账户值写入 Draft；只有 Provider 明确提供相同范围的 US/USD 分段数据时才可使用，否则相关字段必须保持未知并披露范围不匹配。

#### Scenario: 快照有受支持和不受支持资产
- **WHEN** Tiger 账户同时包含 USD 美股和 HKD 港股
- **THEN** Draft 以 `USER_DEFINED_PORTFOLIO` 只规范化同一快照中全部受支持美股，`portfolio_complete` 相对该子组合成立；港股保留在独立账户覆盖清单中并标记投研接入待定，用户确认界面明确展示排除范围且港股不阻断美股 Handoff

#### Scenario: 快照只包含当前受支持资产
- **WHEN** Tiger 账户全部可见持仓均为身份已解析的 US/USD 普通股、ETF 或上市期权，且账户范围字段可以完成勾稽
- **THEN** Draft 可以使用 `BROKER_ACCOUNT`，并继续经过一次明确用户确认后才生成 Handoff

#### Scenario: 混合账户只有全账户汇总金额
- **WHEN** Tiger 返回 US/USD 美股与 HKD 港股，但只提供覆盖整个账户的净资产或现金汇总
- **THEN** Draft 不把该汇总金额写成美股子组合净资产或现金，相关子组合字段保持未知并显示范围不匹配限制

### Requirement: 券商刷新必须产生新 Draft 并使旧确认保持历史不变
每个账户快照 SHALL 具有独立 `source_id`、`as_of`、`retrieved_at` 与内容 hash。新同步发现数量、成本、现金、账户值或持仓集合发生变化时，系统 SHALL 生成新的 Draft；既有 Handoff 保持原确认时点和 hash，不得被后台覆盖、自动更新或自动再次确认。只有用户明确确认新 Draft 后，才生成新的 Handoff。

#### Scenario: 已确认后账户持仓变化
- **WHEN** 新快照比已确认 Handoff 多出一项美股持仓
- **THEN** 旧 Handoff 保持有效历史对象，新 Draft 显示差异并等待确认，下游研究不会静默改用新组合
