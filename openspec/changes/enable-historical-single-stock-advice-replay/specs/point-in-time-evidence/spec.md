## MODIFIED Requirements

### Requirement: 系统必须识别过期、缺失和冲突证据
系统 SHALL 在任何 Agent 获得研究上下文前，根据版本化时效政策识别并处理未来、过期、缺失和冲突证据；确定性层负责时间与元数据过滤、声明式 freshness 标记，以及具有同一规范化 conflict key 的不兼容值检测。LLM 只能研究已通过 Gate 的证据，并负责判断证据充分性、冲突实质性及其投资影响。普通研究 Gate 中 `retrieved_at` 或 `as_of` 晚于 `decision_cutoff` 的事实内容和引用 MUST NOT 进入 Agent 上下文。

仅显式历史重建模式可对事后获取的旧资料作例外：`retrieved_at` MUST 保留实际获取时间，事实的 `as_of` 不得晚于 `decision_cutoff`，且必须有可验证的原始历史版本、该版本的公开时间及来源定位/hash，证明同一内容在截止点已可知；Gate SHALL 在新版本的重建证明中记录该条件及可用时间。事后取得的当前修订值、无历史 vintage 的供应商快照或发布时间不确定的资料 MUST 被排除。该例外不得改变普通 Gate 或既有运行的解释。

#### Scenario: 事实获取时间晚于决策截止时点
- **WHEN** 普通 fixture Fact 的 `retrieved_at` 晚于 `decision_cutoff`
- **THEN** Evidence Gate 排除该事实、记录原因和 Fact ID，并且任何 Agent 输入均不包含该 Fact

#### Scenario: 事实有效时间晚于决策截止时点
- **WHEN** 任何模式的 Fact 的 `as_of` 晚于 `decision_cutoff`
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

#### Scenario: 事后取得但可核验的原始 SEC 披露
- **WHEN** 历史重建模式读取截止点之后才检索到的原始 filing，其 accession、原文版本和公开时间证明该内容在截止点已可得
- **THEN** 保留真实 `retrieved_at` 与历史公开证明；仅该原版本可通过历史 Gate，不能用后来修订后的 companyfacts 代替它

#### Scenario: 当前供应商快照试图回填过去
- **WHEN** Yahoo/Moomoo 当前估值、预期或宏观修订值只有旧观察期而没有可核验的旧版本
- **THEN** 历史 Gate 排除该值并记录 dataset gap，不因旧 `as_of` 或旧 release time 推定当前值当时已知
