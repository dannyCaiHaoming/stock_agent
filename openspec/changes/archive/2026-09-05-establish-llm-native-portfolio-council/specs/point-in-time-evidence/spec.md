## Purpose

为所有研究事实和主张建立可追溯、可回放且不会泄漏未来信息的证据基础，并统一处理来源、时效、冲突和缺失数据。

## ADDED Requirements

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
系统 SHALL 根据版本化时效政策标记证据的 freshness，并识别同一语义字段的实质冲突；确定性层负责检测，LLM 负责解释冲突影响。

#### Scenario: 关键事实过期
- **WHEN** 决策依赖的关键事实超过其适用的 freshness 阈值
- **THEN** 系统将其标为过期，并要求 CIO 补充数据或输出 `NO_TRADE`

#### Scenario: 多来源事实冲突
- **WHEN** 两个有效来源对同一关键事实给出不兼容值
- **THEN** 系统保留两个来源并标记冲突，不得静默选择其中一个

### Requirement: Claim 必须形成证据闭包
每项投资 Claim SHALL 引用一个或多个 Fact 或明确标记为假设，并且系统 MUST 能从最终决策追溯至 Claim、Fact 和原始 `source_id`。

#### Scenario: 研究报告包含无依据主张
- **WHEN** Agent 输出无法引用事实且未标记为假设的实质性 Claim
- **THEN** Schema 或 Evidence 校验失败，该报告不得进入 CIO 综合阶段

