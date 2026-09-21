## ADDED Requirements

### Requirement: Moomoo Evidence 选择必须按 dataset 和 semantic field 闭合
多维研究准备 MUST 为每项批准的 Moomoo 数据集维护显式的 capability 消费映射，并在 dispatch 前验证本次启用能力按规则应接收的合格 Evidence 实际进入目标任务的 `allowed_evidence_ids`。映射 MUST 覆盖分章节 Morningstar 与评级、机构/内部人/空头、Macro 补充、全市场期权统计、个股期权快照与供应商资金数据；不得仅依赖与实际 semantic field 不匹配的通用前缀。过期、去重、主源覆盖、专项未启用和预算裁剪 MUST 保留排除原因；只有缺少合法排除原因的应交付资料未交付才构成路由缺口。

#### Scenario: Moomoo 资料已冻结但未进入任务
- **WHEN** 数据准备包包含本次启用 capability 按规则应接收的合格 Moomoo Evidence，无合法排除原因，而其允许列表中没有相关 ID
- **THEN** 准备阶段报告 capability 路由不闭合并拒绝把该数据集记为已消费

#### Scenario: Moomoo 资料进入错误任务
- **WHEN** 某证券的期权、资金、评级或所有权 Evidence 被选入错误证券或错误 capability
- **THEN** 身份和数据集校验 fail closed，不由 Agent 自行忽略或重新解释

#### Scenario: 资料被合理排除
- **WHEN** 已采集资料因过期、重复、主源覆盖、专项未启用或预算被排除
- **THEN** 记录数量、原因与影响，不触发路由故障，也不宣称该资料已被使用

#### Scenario: 资料交付但没有研究引用
- **WHEN** Evidence 已进入允许列表但有效报告没有引用或解释它
- **THEN** 状态只证明交付，不证明实际使用；验收检查代表资料的正确引用，不强迫每条 Evidence 都被引用

### Requirement: OPTIONS_FLOW 必须消费有界动态结构而非静态目录
`OPTIONS_FLOW` MUST 优先消费同一 cutoff、同一标的和明确交易时段的有界动态期权快照，至少说明实际可得的期限、行权价、bid/ask、volume、OI、IV 与字段时间。只有静态链或部分字段时 SHALL 输出 `SOURCE_LIMITED` 或 `PARTIAL` 及具体影响；不得用全市场 Put/Call、个股 capital flow、short interest 或静态合约数量替代合约级动态结构，也不得由单次快照推断主动买卖方向或 OI 变化。

#### Scenario: 动态快照字段足够
- **WHEN** 选定合约的价差、成交量、OI、IV 和时间语义通过 Gate
- **THEN** `OPTIONS_FLOW` 可解释期限、流动性和波动结构，同时保留单次快照不能证明方向或变化的限制

#### Scenario: 只有全市场 Put/Call 统计
- **WHEN** 合约级快照失败但美国市场级 option volume/OI ratio 可得
- **THEN** 统计只能作为共享市场背景，个股 `OPTIONS_FLOW` 仍保留合约级资料缺口，不把市场比率归因于该公司

#### Scenario: 供应商资本流可得
- **WHEN** 个股 capital flow 或 distribution 通过 Gate
- **THEN** `OPTIONS_FLOW` 或对应 Market 专项将其作为独立 `VENDOR_CALCULATED_FLOW` 观察，不与期权成交量、Short Interest、13F 或真实买卖方身份合并

### Requirement: Company、Macro、Market 和所有权研究必须保留供应商层级
专业研究 MUST 将 Moomoo Morningstar/评级视为外部观点，将机构/内部人/空头数据视为二级披露补充，将 Macro History 视为二级供应商序列，将 FedWatch 视为市场预期。Agent MUST 对每项主张引用目标 capability 允许的冻结 Evidence，并说明与 SEC、BLS、Treasury、Federal Reserve 或 Yahoo 主源的关系、冲突及限制；不得把供应商覆盖或当前值升级为官方事实、独立研报共识或历史 vintage。

#### Scenario: Morningstar 只有一份可读材料
- **WHEN** `RESEARCH_REPORT` 只取得一份 Morningstar 正文或部分 section
- **THEN** 报告可以分析该材料对当前主张的支持、挑战或限制，但不得声称完成多机构独立研报比较

#### Scenario: Moomoo ownership 与 SEC 冲突
- **WHEN** Moomoo 机构汇总或内部人标签与 SEC 原始申报不一致
- **THEN** `OWNERSHIP_DISCLOSURE` 以 SEC 原文为事实锚点并保留供应商冲突，不静默覆盖或生成确定性可信度分数

#### Scenario: Macro 补充只有供应商值
- **WHEN** Moomoo 提供某项宏观实际或 consensus 而官方主源未覆盖
- **THEN** `MACRO_CONTEXT` 明确说明二级来源、观察期、发布时间和 revision/vintage 限制，并将 consensus 与 actual 分开引用

### Requirement: Moomoo 扩展验收必须证明专项实际消费
本 Change 的完成 MUST 至少对一只当前确认持仓普通股证明动态 options snapshot 的 `Capture → Normalize → PIT → Gate/MCP → OPTIONS_FLOW` 闭环，并对 Company、Macro、共享 Market 三域分别证明至少一项资料完成正式交付与报告中的正确引用/解释，来源允许为合格 SEC、Yahoo、官方宏观或 Moomoo，不要求每域 Moomoo 成功。三域覆盖及剩余缺口清单和候选取舍 MUST 完整；最低验收样本不代表全部信息已覆盖。Adapter 测试、AAPL 直接 Spike、配置 hash、静态链和 provider `AVAILABLE` 状态均不能单独替代该验收。受权限或免费覆盖限制的增强项可以保留 `SOURCE_LIMITED_ACCEPTED`，已有来源足够或复杂扩展的候选保留明确取舍；动态期权核心、三域使用证据或消费路由回归未完成时不得归档。

#### Scenario: AAPL Spike 成功但持仓未消费
- **WHEN** AAPL 的直接 SDK Spike 成功，而确认持仓证券没有动态期权和目标任务引用证据
- **THEN** 只保留能力可行性证明，Change 完成条件仍未满足

#### Scenario: 当前持仓没有可交易期权
- **WHEN** 确认持仓普通股均确实没有合格期权合约或当前权限无法取得动态快照
- **THEN** 系统保存逐证券真实尝试和影响；该核心条件只有在用户明确接受范围调整后才能改为受限收尾，不得用市场级统计或非持仓样本自动替代

#### Scenario: Macro 资料未进入研究而 Market 已成功
- **WHEN** Company 和 Market 已有有效使用证据，但 Macro 没有任何合格来源完成正式交付与使用
- **THEN** 三域验收未完成，不用 Market 成功替代 Macro

#### Scenario: Moomoo 受限但官方宏观满足研究
- **WHEN** Moomoo Macro 不可用，而合格官方宏观资料完成交付与正确引用
- **THEN** Macro 域可通过验收，同时保留 Moomoo 数据集限制
