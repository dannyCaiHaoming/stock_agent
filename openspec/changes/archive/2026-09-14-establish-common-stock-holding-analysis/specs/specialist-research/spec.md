## ADDED Requirements

### Requirement: Company Analyst 必须执行普通股专属研究协议
当研究对象为已持有普通股时，Company Analyst MUST 在同一独立上下文中加载并应用版本化 `evidence-grounding`、`company-research`、`valuation` 和公司级 `catalyst-analysis`，输出符合 `EquityResearchReport` 的公司专属研究。Skill 的实际绑定、输入和产物关联 MUST 可验证；仅在报告中自报 Skill 名称不得视为执行。

#### Scenario: 审计普通股 Analyst 调用
- **WHEN** 评审者检查一次真实普通股研究 Invocation
- **THEN** Agent 定义、四项 Skill、允许 Evidence、确定性计算结果、模型和最终 `EquityResearchReport` 具有同一运行绑定和可验证执行记录

#### Scenario: Catalyst Evidence 不足
- **WHEN** Agent 已加载 `catalyst-analysis` 但当前 Evidence 不包含可靠公司事件
- **THEN** 报告保留公司催化剂数据缺口，不得把 Skill 已加载伪装为已有催化剂结论

### Requirement: 普通股专属报告必须兼容既有 Specialist 边界
`EquityResearchReport` SHALL 保留既有 Specialist 对状态、事实/解释/假设、Evidence References、反证、不确定性、数据缺口、失效条件、置信度、Skill 执行和 Artifact References 的语义，并以普通股专属区块扩充，而不是绕过既有 Evidence Closure、PIT、Agent 隔离或下游验证。历史 `AgentResearchReport` 版本及历史运行包 MUST 保持可验证。

Company Analyst 报告只交给允许消费它的下游 CIO，第一轮 Skeptic MUST NOT 读取报告、摘要或派生结论。本 Change SHALL 只验证这些下游接缝兼容，不要求启动真实 Skeptic/CIO 或升级其研究能力。技术元数据 SHALL 根据实际执行封装，不要求模型复制 hash。

普通使用 MUST NOT 为报告交接隐式启动评分模型；实际语义评分由显式验收或用户请求触发，未评分显示未评估，不等于质量通过。结构化 JSON 的有效性与 Markdown 同源一致性 SHALL 分别检查：非法 JSON 不得消费，仅渲染错误不得触发自动重新研究；错误 Markdown 不得作为有效报告，修正版从原 JSON 生成并保留原始差异。

#### Scenario: 第一轮 Skeptic 输入隔离
- **WHEN** 下游构造第一轮 Skeptic 输入
- **THEN** 输入不含 EquityResearchReport 或其派生结论，只使用自身许可 Evidence 和研究上下文

#### Scenario: CIO 消费新版报告
- **WHEN** 新版 Company Analyst 报告通过普通股专属 Schema 与既有 Specialist 安全校验
- **THEN** CIO 获得完整研究报告，并可从摘要追溯正文、假设、反证、计算和失效条件；无需依赖自然语言转抄或旧报告字段猜测，置信度仅解释为资料对研究判断的支持程度

#### Scenario: 历史报告被重验
- **WHEN** Artifact Replay 验证本 Change 之前的 `AgentResearchReport` 运行包
- **THEN** 系统继续按该历史包锁定的 Schema 和 Skill 版本验证，不要求补写新版普通股字段

### Requirement: 公司专业输出不得替代其他方向的研究
Company Analyst SHALL 深入公司基本面、财务、估值与公司事件，不承担整套技术图形、板块轮动、宏观、期权或资金流研究。相关专业方向 SHALL 先以 Capability 描述，MUST NOT 每个指标或方向预建一个 Agent。报告 SHALL 保留其公司判断的显式假设、反证机制及具体观察条件，标明本阶段未研究的方向；后续 CIO 消费完整报告及可解析的证据和计算引用。第一轮 Skeptic 的隔离要求不变，本轮不增加真实下游调用。

#### Scenario: 公司研究完成但交易时点未分析
- **WHEN** Analyst 已形成公司特定的基本面判断
- **THEN** 报告可作为后续综合材料，但不得据此输出最佳买卖时点或声称完成资金、图形与期权研究

#### Scenario: 首版公司研究与机构深度报告的区别
- **WHEN** 当前资料支持公司关键问题但不足以进行产业调研或完整估值建模
- **THEN** Company Analyst 仍解释判断、依据、因果链、反面因素和改变判断的条件，额外深度需求进入带资料依赖的 TODO，不把公司基础分析推迟给 CIO 或新增同职责 Agent

#### Scenario: 继续深化现有公司研究能力
- **WHEN** 用户要求改善报告准确性、经营驱动、反证、条件情景与中文可读性
- **THEN** 在现有 Company Analyst、四项 Skills 与同源报告内实施，区分事实准确性和研究深度；潜在风险不冒充现实反证，完整模型及额外资料研究仍按 TODO 管理，不新增 Agent 或默认调用下游
