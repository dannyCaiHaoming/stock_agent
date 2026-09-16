# specialist-research Specification

## Purpose

定义由专业 Skill 和少量 runtime Agent 执行的可组合投研能力，使 LLM 研究保持开放推理，同时让输入、证据、输出和评价可结构化验证。

## Requirements

### Requirement: 每项研究能力必须具有完整 Capability Contract
公司研究、估值、市场与催化剂、反证等能力 MUST 定义 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval，缺少任一部分的能力不得进入产品运行面。

#### Scenario: 注册新研究能力
- **WHEN** 开发控制面准备注册一项新研究能力
- **THEN** 能力清单中存在可验证的五段式契约和至少一组 Eval 样本

### Requirement: LLM 与确定性计算职责必须分离
真实 Codex LLM SHALL 负责 Company Research、Counter Thesis、证据是否足以支持投资判断、规范化冲突是否具有实质性、冲突影响和 CIO 决策综合；确定性程序 SHALL 仅负责 fixture 数据读取与标准化、point-in-time 过滤、声明式 freshness 检查、可机械判定的规范化字段冲突、数学计算、持仓核算、硬风控、契约验证和存储。系统 MUST NOT 使用 Python callback、固定字符串或条件分支生成 Thesis、Action 或 Confidence，也不得使用同一个 callback 模拟多个专业 Agent。

#### Scenario: 专业 Agent 对 fixture 开展研究
- **WHEN** Company Analyst 或 Independent Skeptic 接收已通过 Evidence Gate 的输入
- **THEN** Agent 使用自己的 Codex Agent 定义和专业 Skills 生成结构化研究结果，Python 只提供确定性数据与校验结果

#### Scenario: 估值能力执行
- **WHEN** Agent 评估标的估值
- **THEN** 确定性层计算给定假设下的数值，Agent 解释假设、情景、适用性和不确定性

#### Scenario: 实现尝试恢复硬编码投资结论
- **WHEN** 验收发现 Thesis、Action 或 Confidence 来自预写 callback、fixture 预期输出或大型条件规则
- **THEN** 运行真实性门禁失败，候选版本不得通过 Change 验收

#### Scenario: 主观判断被编码为规则
- **WHEN** 实现将“优质公司”“好估值”或“应买入”等主观投资判断写入大型 if/else 规则
- **THEN** 架构评审判定其违反职责边界并阻止晋升

### Requirement: 专业研究输出必须结构化
每份真实 Agent Research Report MUST 通过对应 Schema 校验，并包含研究范围、Agent 身份、Claims、实际存在的 Evidence References、反证、不确定性、数据缺口、失效条件、置信度及其理由；报告 MUST NOT 直接决定完整组合的最终动作，校验失败的报告不得进入 CIO 综合。

#### Scenario: Company Analyst 完成真实 LLM 研究
- **WHEN** Company Analyst 返回分析结果
- **THEN** CIO 只接收通过 Schema 和 Evidence Closure 校验的结构化报告，并能区分事实、假设和解释

#### Scenario: Company Analyst 完成研究
- **WHEN** Company Analyst 完成一个标的的质量和估值研究
- **THEN** CIO 收到符合统一 Schema 的报告，并能区分事实、假设和解释

### Requirement: 反证能力必须保持独立性
系统 SHALL 通过独立的 Skeptic Agent 定义和独立 LLM 上下文执行 `INDEPENDENT_FIRST_PASS`；第一轮 Skeptic 输入不得包含 CIO 草案、Company Analyst 输出或其摘要，且 Trace MUST 保存可验证的输入哈希。只有第一轮报告完成后，系统才可在未来 Change 中引入明确授权的定向压力测试。

#### Scenario: 独立反证研究
- **WHEN** CIO 为同一标的并行委派 Company Analyst 和 Independent Skeptic
- **THEN** Skeptic 的第一轮输入哈希对应的结构化输入只包含证券、研究范围、截止时点和 Evidence Bundle，不包含其他 Agent 结论

### Requirement: 每个专业 Agent 必须实际加载声明的 Skills
每个专业 Agent 运行 MUST 绑定其版本化 Agent 定义和专业 Skills。系统 MUST 在调用前生成不可变 Invocation Manifest，记录解析后的 Agent 定义、纳入仓库可控指令包的 Skill 名称/版本/内容哈希、task prompt 哈希和完整 instruction bundle 哈希，并以 Codex 机器可读执行事件证明对应 Agent 调用真实发生。专业报告还 MUST 满足所绑定 Skill 的专属输出协议并关联其实际工具结果。仅验证文件存在、配置声明或 Agent 自报 Skill 名称均不构成实际参与；系统不得声称能够证明模型内部注意力或保存隐藏推理。

#### Scenario: 审计 Company Analyst 运行
- **WHEN** 评审者检查一次真实 Company Analyst Trace
- **THEN** Invocation Manifest 和 Codex 执行事件证明 `evidence-grounding`、`company-research` 和 `valuation` 的固定内容被纳入该 Agent 的仓库可控指令包且调用真实发生，报告通过三个 Skill 的专属协议与工具结果校验

#### Scenario: Agent 只在输出中自报 Skill 名称
- **WHEN** 专业报告声明使用了某 Skill，但 Invocation Manifest、内容哈希或 Skill 专属输出证据缺失
- **THEN** Skill 参与真实性校验失败，该运行不得作为真实 Council 验收证据

### Requirement: Agent 数量必须由可测增益决定
新增 runtime Agent MUST 在证据质量、反证覆盖、冲突识别、决策校准或效率方面通过相对于现有系统的消融评估。

#### Scenario: 新 Agent 未产生增益
- **WHEN** 消融评估显示新增 Agent 未达到预先声明的接受阈值
- **THEN** 该 Agent 不进入默认 runtime 配置，其能力保留为现有 Skill 或按需流程

### Requirement: 只读计算工具的参数契约必须端到端一致
`fixture_math.calculate` MUST 在其 MCP `inputSchema`、实际 callable、无状态代理、确定性计算结果和审计事件中使用同一版本化参数契约。该契约 SHALL 接受一个调用方提供的非空 `calculation_id` 作为计算关联标识，并要求其在结果及工具事件中原样保留；未声明参数、缺失必需参数或错误类型 MUST 在调用 LLM 恢复前由确定性契约校验拒绝。工具仍只能计算 Gate 允许的 fixture 数值事实，且不得增加开放网络、写入或投资判断能力。

#### Scenario: 使用受支持的 calculation_id 计算
- **WHEN** Company Analyst 按 MCP 暴露的 Schema 调用 `fixture_math.calculate`，并提供合法 `calculation_id`、身份、操作和两个允许的 Evidence IDs
- **THEN** 实际 callable 一次接受该请求，结果和只读审计事件均携带相同 `calculation_id`，无需依靠 LLM 修改参数后重试

#### Scenario: 工具清单与 callable 漂移
- **WHEN** MCP `inputSchema` 声明的必需或允许参数与实际 callable、无状态代理或事件映射不一致
- **THEN** 工具参数契约测试失败，候选版本不得进入真实 Codex Smoke

#### Scenario: 调用包含未声明参数
- **WHEN** 工具调用包含 canonical 参数契约未声明的额外字段
- **THEN** MCP 层在执行计算前确定性拒绝请求，并保存不泄露 Evidence 内容的错误诊断

### Requirement: Specialist Evidence 引用必须受当前 Gate 集合约束
系统 MUST 将当前运行的 `allowed_evidence_ids` 作为独立 Agent 输入，并为 Company Analyst 与 Independent Skeptic 生成 run-scoped 输出 Schema，使所有 `evidence_refs` 与 `counter_evidence_refs` 只能从该集合逐字选择 canonical Evidence ID。Specialist Prompt MUST 明确禁止把 `source_id`、`as_of`、`retrieved_at`、分隔符或说明文字拼接到引用字段；来源描述必须放入其他说明字段。严格 Evidence Closure Validator MUST 保持 fail closed，不得增加自动截断 `|` 后内容、猜测映射或其他静默修复。

#### Scenario: Specialist 使用 canonical Evidence ID
- **WHEN** Specialist 的引用字段包含一个或多个当前 Gate 允许的原始 `evidence_id`
- **THEN** run-scoped Schema 接受这些 ID，后续 Evidence Closure 校验通过

#### Scenario: Specialist 拼接来源或时间
- **WHEN** Specialist 在原始 `evidence_id` 后拼接 source、`as_of`、`retrieved_at` 或说明文字
- **THEN** 该值不属于 run-scoped enum，结构化输出或 Evidence Closure 确定性拒绝，系统不得截断后继续运行

#### Scenario: Specialist 引用不存在的 ID
- **WHEN** Specialist 输出不在当前 Gate 允许集合中的 Evidence ID
- **THEN** Schema 或严格 Evidence Closure Validator fail closed，不得进入 CIO 综合

### Requirement: Demo Adapter 只能验证角色契约而不能声明研究能力
在显式 `DEMO_SCAFFOLD` Profile 中，专业 Agent MAY 由确定性 Demo Adapter 生成固定但输入相关的示例响应，以验证角色边界、只读 Tool Port、结构化输出和上下游传递。响应 MUST 标记 `producer_type: deterministic_demo`、`llm_used: false` 与 `skill_reasoning_executed: false`，不得声明 Skill 已参与推理、不得作为 Thesis 质量、真实 Agent 独立上下文或投资结论的验收证据。

#### Scenario: Demo Specialist 返回示例研究
- **WHEN** 合法 Demo 输入调用 Company Analyst 或 Independent Skeptic Adapter
- **THEN** 返回符合 Demo 契约的角色响应并引用输入中的合法 Evidence，同时明确其内容只用于链路演示

#### Scenario: Demo 响应声称真实 Skill 推理
- **WHEN** Demo 响应将自身标记为真实 LLM 或声称已执行专业 Skill 推理
- **THEN** Demo 校验失败，不把该响应传给 CIO

### Requirement: Agent 独立调用与链路调用必须使用同一输入输出契约
同一 Demo Agent 在独立调用和完整链路调用中 MUST 使用相同的请求、只读 Tool Port 与响应 Schema。完整链路不得依赖仅在编排器内部可见、单独调用时无法提供的隐藏业务字段。

#### Scenario: 独立调用结果进入下游
- **WHEN** 开发者单独调用 Specialist 并将其合法响应交给 CIO Demo 入口
- **THEN** CIO 能按同一契约消费该响应，无需人工改写字段

### Requirement: Demo Specialist 必须保留真实角色的语义边界
Company Analyst Demo 输出 MUST 包含示例 Claims、Assumptions、Counter Evidence、Uncertainties、Data Gaps、Invalidation Conditions 和 Confidence Rationale，且 MUST NOT 输出组合动作。Independent Skeptic Demo 输出 MUST 包含 Challenges、Alternative Explanations 或 Failure Paths、Evidence References、Uncertainties、Data Gaps、Invalidation Conditions 和 Confidence Rationale，且 MUST NOT 读取 Analyst 输出或选择最终组合动作。示例内容 MUST 来自明确的 synthetic fixture，而不是 Python 投资判断分支。

#### Scenario: Analyst 与 Skeptic 各自响应
- **WHEN** 两个 Demo Specialist 分别接收同一 Gate 合格 Evidence 集合
- **THEN** 两者返回不同角色语义的结构化报告，且 Analyst 不能代替 CIO、Skeptic 不能仅复制 Analyst 或制造无依据反对意见

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
