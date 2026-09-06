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
