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

### Requirement: Company、Macro 与 Market 必须映射到现有专业职责
当前持仓研究 SHALL 通过版本化拓扑把 Company 域的公司基本面、公司事件与公开研报能力绑定至 Company Analyst，把 `MACRO_CONTEXT` 与 `MARKET_STATE` 绑定至 Market Catalyst。两项 Market Catalyst 能力 MUST 使用独立 invocation、capability-specific 输入和结构化输出，即使它们复用同一 Agent 定义或 Skill 包；Company Analyst MUST NOT 以公司报告替代宏观或市场状态研究，Market Catalyst MUST NOT 把共享环境解释冒充公司 Thesis。provider 只负责资料语义与可用性，不成为新的研究 Agent。

#### Scenario: 同一 Market Catalyst 执行两项能力
- **WHEN** 一个运行同时派发 `MACRO_CONTEXT` 与 `MARKET_STATE`
- **THEN** 两次 invocation 分别锁定 capability、输入、输出和执行证据，任一失败不伪造另一项完成

#### Scenario: 公司资料包含宏观评论
- **WHEN** Company Analyst 的来源包含管理层对利率或行业环境的评论
- **THEN** 报告可将其保留为公司视角及相关 Evidence，但不能据此声称共享 `MACRO_CONTEXT` 或 `MARKET_STATE` 已完成

#### Scenario: 页面新增一个研究栏目
- **WHEN** 产品展示新增或重命名一个研究栏目但没有新的独立判断职责和可测增益证据
- **THEN** 系统通过已有 capability/Agent 映射展示，不新增默认 runtime Agent

### Requirement: 研究材料必须按研究对象分派
研报与新闻 SHALL 作为材料类型而不是固定 Agent 归属。公司研报归 Company Analyst；宏观与市场策略材料分别进入 Market Catalyst 的 `MACRO_CONTEXT` 与 `MARKET_STATE` 输入。系统 MUST 对相关材料执行相同的来源核实、正文解析、PIT 和引用闭合；仅标题摘要不得视为已读正文，IR 公司宣传不得冒充独立研究，机构预测不得冒充已发生事实。

#### Scenario: 同批取得公司研报与宏观策略
- **WHEN** 资料准备取得两类有可验证正文与发布时间的材料
- **THEN** 分别按研究对象进入对应 invocation，报告引用原始材料并保留观点属性，不把全部研报固定交给 Company Analyst

### Requirement: 研究交付必须通过可信身份与精确引用绑定
正向与反证交付 SHALL 保留原始草案，并在唯一且验证通过的 run、parent/child session、task、Invocation、Agent/model 派发启动绑定下，允许确定性封装缺失的技术身份。显式身份冲突、映射缺失或多义 MUST 拒绝，不根据正文或证券名称猜测。封装不得修改研究正文、状态或证据。

Evidence 引用 SHALL 优先使用工具返回的完整标识；如采用短引用，MUST 使用本 Invocation 内预先冻结的一对一映射，还原后继续校验 Evidence/PIT。未知、截断、错拼、跨 Invocation 或歧义引用 MUST 拒绝，不模糊纠错或删主张。允许集合闭合与真实查询分别核验，`EVIDENCE_CLOSURE_FAILED` 不得单独作为未查询证据的证明。本要求不授权额外补查询再提交，沿用一次纯格式修复及原有显式有界恢复边界。

#### Scenario: 草案漏技术身份但会话绑定唯一
- **WHEN** 草案遗漏技术身份且可信派发启动记录可唯一确定任务和执行主体
- **THEN** 系统从可信记录封装身份，保留原始草案及绑定来源，再执行完整报告校验

#### Scenario: 草案冒用其他 Invocation
- **WHEN** 草案显式身份与可信绑定冲突，或同一子会话存在多义任务映射
- **THEN** 系统拒绝交付，不静默覆盖身份，也不凭正文猜测归属

#### Scenario: 引用是完整 ID 的相似或截断字符串
- **WHEN** 报告引用不在允许集合且不是合法冻结短引用，即使与某完整 ID 高度相似
- **THEN** 系统保留引用失败，不能自动替换成相近 ID 或据此声称未发生查询

### Requirement: 真实多维持仓研究必须支持逐证券独立反证
显式 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 阶段 SHALL 复用现有 `runtime_skeptic`、`evidence-grounding`、`counter-thesis` 与 `CounterThesisReport`，为多维研究包中的每只普通股建立独立 `INDEPENDENT_FIRST_PASS` Invocation。系统 MUST NOT 为该阶段新增另一种“反向 Agent”、用 Company Analyst 或 Market Catalyst 模拟 Skeptic，或用确定性文本生成反证结论。

#### Scenario: 单只普通股进入反证阶段
- **WHEN** 一只普通股所在运行满足独立反证前置条件
- **THEN** 系统以该证券的独立 Invocation 启动真实 `runtime_skeptic`，并保存其 Agent、Skill、模型、Prompt、输入输出和工具事件绑定

#### Scenario: 多只普通股进入反证阶段
- **WHEN** 合格研究包包含多只普通股
- **THEN** 系统在现有并发上限内逐证券有界派发 Skeptic，保存已完成、合法领域状态、系统失败和待处理覆盖，不以并发上限缩小研究范围

### Requirement: Skeptic 第一轮必须与全部正向结论隔离
每个 Skeptic 第一轮输入 SHALL 只包含本证券身份、研究范围、research question、可选 holding horizon、decision cutoff、来源模式、Gate-scoped Evidence IDs 和读取这些 Evidence 所需的技术身份。输入 MUST NOT 包含 `EquityResearchReport`、`ResearchDimensionReport`、`HoldingResearchBundle`、正向摘要、`unresolved_cross_dimension_questions`、报告或 bundle hash、Artifact References、Company Analyst/Market Catalyst/CIO 结论，或由这些结论派生的提示。

Skeptic MAY 读取同一 Gate 中与本证券有关的 Company Evidence 以及共享 Macro/Market Evidence，但 MUST 通过自己的只读 Evidence 查询选择与核验事实；系统不得根据正向报告使用了哪些证据来缩小、排序或强调 Skeptic 的 Evidence 集合。输入隔离校验 MUST 在 Agent 启动前 fail closed，并在执行证明中保存输入 hash 与禁止上下文检查结果。

#### Scenario: 正向研究完成后构造 Skeptic 输入
- **WHEN** 确定性层已经验证 `HoldingResearchBundle` 并准备 Skeptic Invocation
- **THEN** 只使用原始 Gate 和非结论性请求上下文构造输入，不读取或转抄研究包内容

#### Scenario: 输入包含未解决问题或报告 hash
- **WHEN** Skeptic 输入的任意层级出现正向报告派生问题、摘要、报告 hash、bundle hash 或其他 Agent 结论
- **THEN** 系统在派发前返回 `CONTEXT_ISOLATION_VIOLATION`，不启动该 Agent，也不把错误降级为证据不足

#### Scenario: 共享宏观市场 Evidence 与个股 Evidence 同时可用
- **WHEN** 同一 Gate 中存在与目标普通股相关的公司事实和共享 Macro/Market 事实
- **THEN** Skeptic 可按许可 Evidence IDs 独立检索两类事实并形成跨维度挑战，但不能读取 Market Catalyst 对这些事实的解释

### Requirement: 独立反证报告必须保留真实领域状态与严格引用闭合
每份反证结果 MUST 通过 `CounterThesisReport` Schema、Invocation 身份、Skill 绑定、PIT 和 Evidence Closure 校验，并包含实质性挑战或明确说明证据不足、替代解释、解决挑战所需证据、不确定性、数据缺口、失效条件及置信度理由。Skeptic MUST NOT 输出组合动作、目标权重、推荐数量或订单，也不得为了形式对称编造不利事实。

`COMPLETE`、`LOW_CONFIDENCE`、`INSUFFICIENT_EVIDENCE` 和 `TIMEOUT` SHALL 保持领域状态；非法 JSON、Schema、身份、上下文隔离、悬空引用或越过 Gate 的访问属于系统失败。纯格式错误 MAY 沿用现有一次原 Agent 修复边界，但修复不得新增事实、Evidence 或改变研究内容。

#### Scenario: Evidence 支持实质性失败路径
- **WHEN** Skeptic 找到可引用的替代解释、治理风险、竞争威胁或 Thesis 失败条件
- **THEN** 报告把挑战、Evidence、待补证据和可观察失效条件结构化保存，不决定最终动作

#### Scenario: 免费资料不足以形成可靠反证
- **WHEN** Gate 内资料不足、受限或相互冲突但报告结构和引用合法
- **THEN** Skeptic 返回相应低置信度或证据不足状态，交接层如实保留而不补写悲观观点

#### Scenario: 报告引用其他运行的 Evidence
- **WHEN** 反证报告包含不属于当前 Invocation 允许集合的 Evidence ID
- **THEN** Evidence Closure 校验失败，该证券不能进入下游就绪交接包

### Requirement: 独立首轮必须提供有依据且可检验的风险研究
正向研究 SHALL 保持客观，Skeptic SHALL 独立研究公司特定失败路径和替代解释，不固定唱空、不要求逐条反驳未见过的正向 claim，不以挑战数量或观点不同作为成功标准。报告 SHALL 区分观察事实与假设，说明风险如何传导、待补证据以及会推翻挑战的可观察条件。非空工具查询只证明执行行为；真实验收 SHALL 由独立人工复核对照原始 Evidence 检查上述内容，不新增自动评分器或 Runtime Eval。

#### Scenario: 未找到有力反证
- **WHEN** Skeptic 已实际核验许可资料但没有发现有力不利证据
- **THEN** 报告可以如实说明未发现强反证及核验范围、限制，不编造挑战；资料不足则使用对应不足状态

### Requirement: 反证假设引用必须在报告内闭合
新阶段 SHALL 使用 `CounterThesisReport/2.1.0`，在既有报告上最小增加 `assumptions` 数组，每项包含唯一非空 `assumption_id` 与非空 `statement`。每个 challenge 的 `assumption_ids` MUST 指向本报告定义，不能引用不可见的 Analyst 假设或虚构 ID。假设不得冒充事实 Evidence；事实性断言仍须 Evidence 支持，纯情景须明确说明假设性质。旧 2.0.0 报告 SHALL 保留按锁定版本读取的兼容路径。

#### Scenario: 空造假设 ID 绕过依据要求
- **WHEN** challenge 只提供未在本报告定义的 assumption_id
- **THEN** 验证失败，不因该数组非空而认可挑战已获得依据

### Requirement: 资料读取必须在逐 Invocation 工具边界授权
系统 SHALL 从同一冻结 Gate 和资料准备关系提供目标公司、共享 Macro/Market、相关同行公开事实及来源闭合的确定性计算；材料选择受既有资料准备限制时必须保留限制说明，不宣称资料全集无偏。同行是否同时属于持仓不影响公开事实准入，私人组合字段仍禁止进入输入。确定性计算只暴露校验后的数值、方法和输入来源，不暴露正向研究解释或任意文件。

工具 SHALL 按可信任务映射绑定 run、task、invocation、security 和允许资料集合，并在服务端拒绝超出本次 Invocation 的访问。独立首轮 SHALL 使用不继承父会话的上下文；权限隔离覆盖启动输入及后续工具访问。首版缺资料只记录缺口，不增加 Gate 外网络查询或动态扩充 Gate。

#### Scenario: 同一 Skeptic 角色处理两只证券
- **WHEN** A 证券的 Invocation 请求仅授权给 B 的公司资料或冒用 B 的 Invocation
- **THEN** 工具拒绝访问，即使该资料属于同一全局 Gate；明确共享或允许的同行事实仍可读取

#### Scenario: 同行与计算资料有效
- **WHEN** 目标证券需要已冻结同行事实或由已准入输入产生的确定性计算
- **THEN** 工具按本次允许集合返回可追溯资料，不附带其他 Agent 的报告解释
