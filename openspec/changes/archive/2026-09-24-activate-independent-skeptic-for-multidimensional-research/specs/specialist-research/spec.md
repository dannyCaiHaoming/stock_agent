## ADDED Requirements

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
