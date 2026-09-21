# point-in-time-evidence Specification

## Purpose

为所有研究事实和主张建立可追溯、可回放且不会泄漏未来信息的证据基础，并统一处理来源、时效、冲突和缺失数据。

## Requirements

### Requirement: 每项事实必须携带来源和有效时点
系统 MUST 为每项事实记录稳定的 `source_id`、`as_of` 和 `retrieved_at`，并记录可定位原始内容的来源信息、版本或内容哈希。

#### Scenario: 数据适配器返回事实
- **WHEN** MCP 数据适配器返回财务、行情、公告或事件事实
- **THEN** 每项事实均包含 `source_id`、`as_of`、`retrieved_at` 和来源定位信息，否则该事实不得进入可用 Evidence Bundle

### Requirement: 外部数据访问必须只读
runtime Agent 可使用的外部 MCP Tools SHALL 仅提供查询和只读计算能力，产品包 MUST NOT 暴露券商写入、订单发送、账户修改或其他真实交易工具。

#### Scenario: Runtime Agent 请求交易工具
- **WHEN** runtime Agent 尝试查找或调用下单、撤单或账户写入工具
- **THEN** 系统不提供该能力，并记录被拒绝的工具请求

### Requirement: Evidence Store 必须保留双时间语义
Evidence Store SHALL 区分事实对现实世界有效的 `as_of` 与系统获取事实的 `retrieved_at`，并以追加式版本保存证据和血缘。

#### Scenario: 历史公告被后续修订
- **WHEN** 数据源发布修订后的公告或财务数据
- **THEN** 系统保存新版本及其时间信息，不覆盖历史运行当时可见的版本

### Requirement: 系统必须识别过期、缺失和冲突证据
系统 SHALL 在任何 Agent 获得研究上下文前，根据版本化时效政策识别并处理未来、过期、缺失和冲突证据；确定性层负责时间与元数据过滤、声明式 freshness 标记，以及具有同一规范化 conflict key 的不兼容值检测。LLM 只能研究已通过 Gate 的证据，并负责判断证据充分性、冲突实质性及其投资影响。`retrieved_at` 或 `as_of` 晚于 `decision_cutoff` 的事实内容和引用 MUST NOT 进入 Agent 上下文。

#### Scenario: 事实获取时间晚于决策截止时点
- **WHEN** fixture Fact 的 `retrieved_at` 晚于 `decision_cutoff`
- **THEN** Evidence Gate 排除该事实、记录原因和 Fact ID，并且任何 Agent 输入均不包含该 Fact

#### Scenario: 事实有效时间晚于决策截止时点
- **WHEN** fixture Fact 的 `as_of` 晚于 `decision_cutoff`
- **THEN** Evidence Gate 排除该事实并记录未来信息违规，不允许 LLM 使用其内容或引用

#### Scenario: 关键证据过期或缺失
- **WHEN** 过滤后关键事实超过 freshness 阈值或不再完整
- **THEN** 确定性层输出结构化数据缺口；若没有任何可用事实则在 Agent 前安全终止，否则由专业 Agent 与 CIO 判断其影响并可返回 `INSUFFICIENT_EVIDENCE`、`STALE_DATA` 或 `NO_TRADE`

#### Scenario: 关键事实过期
- **WHEN** 决策依赖的关键事实超过其适用的 freshness 阈值
- **THEN** 系统将其标为过期且不向 Agent 返回事实内容，并在仍有可用证据时要求 CIO 解释数据缺口或输出 `NO_TRADE`

#### Scenario: 多来源事实冲突
- **WHEN** 两个通过时间门禁的有效来源对同一关键事实给出不兼容值
- **THEN** 系统保留两个来源和规范化 conflict key 并标记不兼容值，不得静默选择其中一个；冲突是否实质及其决策影响由 LLM 判断

### Requirement: Claim 必须形成证据闭包
每项 Agent Claim、CIO Thesis、Counter Thesis 和最终决策 Evidence Reference SHALL 引用本次运行 Evidence Bundle 中实际存在且通过 point-in-time Gate 的 Fact，或明确标记为假设。系统 MUST 在 Agent 报告进入 CIO 前和最终输出保存前分别执行 Evidence Closure；未知、被过滤或悬空引用 MUST 导致 `FAILED_VALIDATION` 并阻止最终建议发布，不得转换成投资性 `NO_TRADE`。

#### Scenario: Agent 报告包含悬空引用
- **WHEN** 专业报告引用 Evidence Bundle 中不存在或已被 Gate 排除的 `evidence_id`
- **THEN** 报告校验失败且不得进入 CIO 综合，Trace 记录失败原因和引用 ID

#### Scenario: 最终计划包含悬空引用
- **WHEN** CIO 草案或最终决策引用不存在的 `evidence_id`
- **THEN** 运行进入 `FAILED_VALIDATION` 并返回结构化系统错误，不得写出 `decision.json` 或 `report.md`

#### Scenario: 研究报告包含无依据主张
- **WHEN** Agent 输出无法引用事实且未标记为假设的实质性 Claim
- **THEN** Schema 或 Evidence 校验失败，该报告不得进入 CIO 综合阶段

### Requirement: Evidence Gate 必须生成可审计的确定性产物
每次运行 MUST 在研究委派前保存 Evidence Gate 结果，至少包含 `decision_cutoff`、输入 Evidence IDs、允许 Evidence IDs、排除 Evidence IDs、排除原因、freshness policy version、conflict policy version 和 Evidence Bundle hash。后续 Agent 输入只能包含允许 Evidence IDs；Gate 审计信息可以保留排除 ID 和原因，但不得把被排除事实内容复制到 Agent Invocation Manifest 或 Prompt。

#### Scenario: 未来事实被过滤
- **WHEN** Gate 从 fixture 中排除一个未来事实
- **THEN** Decision Trace 引用该 Gate 产物，且后续两个 Agent 的输入 Evidence IDs 都是允许集合的子集

### Requirement: 复合供应商响应必须具有字段级时间语义
当同一响应中的字段具有不同观察、有效、推荐、更新或公开时间时，系统 MUST 按字段族或 section 生成独立时间语义，至少保存 `as_of`、`published_at`、`retrieved_at`、时间来源及无法确认的限制。响应级 `update_time` MUST NOT 自动覆盖全部字段；缺少字段有效时间时 MUST 使用明确的保守策略或拒绝历史用途，不得伪造精确时点。

#### Scenario: 期权价格和 Greeks 共用一个响应
- **WHEN** Market Snapshot 的 `update_time` 只被官方定义为最新价格时间，而 OI、IV 或 Greeks 没有独立有效时间
- **THEN** 价格 Evidence 使用该报价时间，其他字段使用检索时点的保守 snapshot 语义并记录供应商有效时间未知，不把它们描述为与最新价同时更新

#### Scenario: Morningstar section 更新时间不同
- **WHEN** fair value、economic moat、financial health、bull/bear、analyst note 或 investment thesis 具有各自更新时间或正文缺失
- **THEN** 系统按 section 保存 Evidence 和时间，缺正文的 section 只形成字段 gap，不用 analyst report 总时间覆盖整份材料

#### Scenario: 评级推荐日早于供应商更新时间
- **WHEN** rating item 的 `recommendation_date` 与 `update_time` 不同
- **THEN** `as_of` 保存推荐日，`published_at` 使用供应商更新时间或更保守的获取时间，历史 cutoff 早于可知时间时排除该评级

### Requirement: 期间、公开版本与当前供应商修订必须分离
Macro、机构汇总、评级和期权统计 Evidence MUST 区分经济观察期或报告期、供应商公开/更新时间、当前检索时间与历史 vintage 可用性。供应商响应只提供当前 `previous_value`、consensus 或修订值时，系统 MUST 标记当前快照，不得将其回填为过去 cutoff 已知版本。

#### Scenario: Macro History 包含 data time 和 release time
- **WHEN** Moomoo Macro 数据点同时返回 `data_time`、`release_time`、actual、predict 和 previous
- **THEN** 系统分别保存观察期、可知时间和数值角色；发布时间时区未核实时 fail closed 或以 retrieved_at 保守处理，不能按本地默认时区猜测

#### Scenario: 机构持仓 period_text 和 update_time 不同
- **WHEN** Moomoo 机构汇总返回报告期间和供应商更新时间
- **THEN** `as_of` 对应已解析并核实的报告期，`published_at` 对应供应商更新时间；无法解析报告期时记录 gap 而不把更新时间冒充持仓期末

#### Scenario: 当前 consensus 被用于历史研究
- **WHEN** 当前响应的预测值或评级共识没有历史版本标识，而目标 decision cutoff 早于本次获取
- **THEN** Evidence 不进入历史研究包，只能形成新的当前 cutoff 快照

#### Scenario: 历史 actual 已被供应商修订
- **WHEN** 当前获取的历史 actual 带有旧 release time，但没有证明当前值在旧 cutoff 已知的原始版本
- **THEN** 系统将其作为当前获取版本，不以旧 release time 自动放行历史用途

#### Scenario: 当前已知的未来日程
- **WHEN** 日历或 FedWatch 指向未来事件，而该日程或预期在当前 cutoff 已公开
- **THEN** 分别保存事件目标时间与资料可知时间，允许引用当前已知日程/预期，但不得表述为事件已经发生或结果已确定

### Requirement: 供应商字段单位和时区必须显式标准化
系统 MUST 对 Moomoo 字段保存官方声明的市场、时区、百分比缩放、货币和单位，并以实际响应验证转换。无法从文档与响应共同确定比例或时区时 MUST 保留原值、原标签和 gap，不得基于示例或字段名称自动乘除、转换日期或混合不同市场时区。

#### Scenario: 百分比响应使用小数值
- **WHEN** Macro History 返回 `unit_type=PERCENT` 且实际数值为小数形式
- **THEN** Normalize 通过批准的字段定义保存原值与标准化值及转换版本，不因 UI 表示习惯重复除以或乘以 100

#### Scenario: 美国行情包含盘前盘后和夜盘字段
- **WHEN** Snapshot 同时返回 regular、pre-market、after-hours 或 overnight 字段
- **THEN** 各交易时段分别标记并保持原时点，不合并为单一 close/last，也不与 Yahoo 不同时段的字段静默拼接

#### Scenario: 同名宏观指标的口径不同
- **WHEN** 官方 CPI 指数水平或非农总人数与供应商同比、环比或新增人数同时出现
- **THEN** 系统显式保留统计口径与单位，未经有据可查的换算不得直接比较为冲突或相互替代
