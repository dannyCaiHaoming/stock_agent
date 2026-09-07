# decision-trace-evaluation Specification

## Purpose

建立覆盖数据、推理、编排、风控和结果的可审计评估体系，使任何运行都能在原始时点重放并比较不同版本和 Agent 架构。

## Requirements

### Requirement: 每次运行必须生成完整 Decision Trace
系统 MUST 为真实 Codex Council 运行记录输入快照、Evidence Gate、研究计划、Agent 委派与结构化输入、只读 MCP 工具调用、证据版本、Agent 输出、CIO 草案、可选修订、Risk Report、终态和相应输出。每个相关事件 MUST 包含 `run_id`、实际 Agent 名称与版本、Invocation Manifest ID、仓库可控 Agent/Skill/task prompt/instruction bundle 哈希、显式模型标识、Codex runtime 版本、Evidence IDs、输入输出哈希和上游 Artifact IDs；Risk Engine 事件还 MUST 保留状态变化、可行边界、违规和最终否决记录。验收包 MUST 保存经过最小化和敏感信息检查的 Codex 机器可读执行事件，并由 Trace 引用。

#### Scenario: 审计真实 Codex fixture 决策
- **WHEN** 评审者打开任一真实 Smoke `run_id`
- **THEN** 可以重建从 portfolio fixture 到终态输出的完整产物链，并以 Invocation Manifest、Codex 事件和工具事件确认每个 LLM 与确定性产物的实际生产者、版本和输入输出哈希

#### Scenario: 审计历史决策
- **WHEN** 评审者打开任一历史 run_id
- **THEN** 可以重建从用户输入到最终输出的产物链和每个产物的生产者版本

### Requirement: 运行必须锁定关键版本
Decision Trace SHALL 锁定显式指定的模型标识、Codex runtime、实际解析的 Skill 与 Agent 内容哈希、仓库可控 task prompt 与 instruction bundle 哈希、Schema、fixture MCP adapter、Risk Policy 和数据快照版本；声明但未进入 Invocation Manifest 的配置不得被记录为已使用版本。系统不得把这些哈希描述为 OpenAI 内部系统指令、完整有效上下文或隐藏 Chain-of-Thought 的哈希。

#### Scenario: 配置声明与实际运行不一致
- **WHEN** Agent 配置声明某 Skill 版本但运行证据无法证明其已加载，或实际内容哈希不匹配
- **THEN** Trace 完整性校验失败，候选运行不得作为验收证据；Agent 自报或静态配置声明不能弥补 Invocation Manifest 与 Codex 事件缺失

#### Scenario: 比较两个运行版本
- **WHEN** Replay 比较候选版本与生产版本
- **THEN** 评估报告明确列出所有版本差异，不把未知漂移归因于投资推理

### Requirement: Replay 必须遵守 point-in-time 边界
历史 Replay MUST 使用已保存的 portfolio fixture、Evidence Gate 允许集合、Prompt/Instructions 哈希和固定版本依赖重建原始运行输入，不得访问 `decision_cutoff` 之后的事实。Replay SHALL 支持精确重建已保存 Artifact 和确定性计算；重新调用 LLM 时只要求输入与版本可验证一致，不要求生成逐字节相同的自然语言输出。

#### Scenario: 重放同一次 fixture 运行
- **WHEN** 评审者使用已保存 Trace 对某个 `run_id` 执行 Replay
- **THEN** 系统重建相同的已过滤 Evidence IDs、Agent 输入、Risk 输入和原始产物，并可选择以新 `run_id` 对固定 LLM 配置执行可比较的再运行

#### Scenario: 回放历史财报期
- **WHEN** 后续存在修订财务数据
- **THEN** Replay 使用当时 `retrieved_at` 不晚于决策截止时点的版本

### Requirement: Eval 必须覆盖五类质量
系统 SHALL 实际执行确定性正确性、数据与证据质量、LLM 推理质量、决策及组合结果、多 Agent 架构贡献评估，并为每项能力维护可重复接受标准。针对本 Change，Eval MUST 消费至少一次真实 Codex LLM Smoke 运行产生的 Trace 和终态产物，并按 fixture 的结构化不变量判定，不得预设具体 Thesis、Action 或 Confidence。本 Change 的多 Agent Eval 只要求证明 Skeptic 报告被独立生成、携带非重复反证或缺口并被 CIO 显式消费；市场收益、Alpha 或统计显著的预测增益不属于本 Change 的验收结论。仅测试 Eval 类、检查 fixture 目录或提交静态 JSON 报告不得视为真实运行验收。

#### Scenario: Codex-native 候选申请验收
- **WHEN** 候选版本完成四类 fixture Smoke 和至少一次真实 Codex LLM 运行
- **THEN** Eval Runner 从实际产物计算并保存 Schema、point-in-time、Evidence Closure、独立反证、仓库可控 Prompt/Skill/Agent 血缘、MCP 只读性、Risk 经过或 veto 和报告一致性结果，且不以固定投资结论作为通过条件

#### Scenario: 候选版本申请晋升
- **WHEN** 候选 Skill 或 Agent 配置进入回归评估
- **THEN** 评估同时报告 Schema/数学测试、引用正确性、反证与冲突处理、风险和组合指标以及消融结果

### Requirement: Change 验收必须包含真实 Codex LLM 运行证据
单元测试和 fake adapter MAY 验证确定性边界，但本 Change MUST 至少成功执行一次真实 Codex-native 正常 fixture 运行；该运行 MUST 显式指定模型，且验收记录必须包含可核验命令、退出状态、`run_id`、Codex runtime 版本、Invocation Manifests、机器可读 Agent 与工具调用事件、产物路径和实际 Eval 报告。

#### Scenario: 只有 fake callback 测试通过
- **WHEN** 所有单元测试通过但没有真实 Codex LLM 运行产物
- **THEN** Change 验收状态保持失败，不得宣称 fixture Council 已激活

### Requirement: Risk veto 验收必须独立于 LLM 动作随机性
每个可形成 CIO draft 的真实 Codex-native Council 运行 MUST 调用 deterministic Risk Engine 并记录实际结果。系统还 MUST 提供确定性的 Risk boundary fixture，以固定、明确标记为测试输入的 Council draft 稳定验证 `REVISE_REQUIRED`、修改记录或 `REJECTED`/`RISK_VETO`；该固定 draft MUST NOT 被记录为 LLM 输出，也不得用来满足真实 LLM 运行门禁。

#### Scenario: 真实 CIO 自主选择 HOLD 或 NO_TRADE
- **WHEN** Risk veto 场景中的真实 LLM 没有生成会违反政策的交易动作
- **THEN** Trace 仍证明真实 draft 经过 Risk Engine，但确定性 Risk boundary fixture 单独提供可重复的否决证据，验收器不要求硬编码 LLM 动作

#### Scenario: 固定 Risk draft 被否决
- **WHEN** 确定性 Risk boundary fixture 将违反明确硬约束的测试 draft 提交给同一 Risk Engine 和 policy version
- **THEN** 每次运行产生相同的修改或否决结果及原因，并明确标记 producer 为 fixture 而非 CIO LLM

### Requirement: 市场结果不得作为唯一正确性标签
系统 MUST 将市场收益视为多期限、带噪声的 Outcome Observation，并结合 Thesis 事件实现、风险暴露、基准和交易成本分析决策质量。

#### Scenario: 正确推理后价格短期下跌
- **WHEN** Thesis 证据仍有效但短期相对收益为负
- **THEN** Eval 不自动把该决策标为推理错误，而是保留分解后的结果指标供评审

### Requirement: 新 Agent 必须通过消融评估
系统 SHALL 比较 CIO 单体、现有 Council 和新增 Agent 候选，在预先定义的留出集上验证增益和成本。

#### Scenario: 新 Agent 只增加一致性文本
- **WHEN** 新 Agent 提高 token 和延迟但未改善预定质量指标
- **THEN** 晋升门禁拒绝把该 Agent 加入默认 Council

### Requirement: 失败 Trace 必须按失败阶段验证血缘
以 `FAILED_VALIDATION` 终止的运行 MUST 在 `decision_trace.json` 与 `run_error.json` 中保存一致、受枚举约束的 `failed_stage`，并按 `terminal_state`、`failed_stage` 与已经实际到达的阶段验证产物和 lineage。Risk Engine 前失败 MAY 具有空 `risk_lineage`；已经进入 Risk 阶段或更晚阶段的运行 MUST 保存完整 Risk 尝试及结果血缘，缺少时 Trace 校验 MUST 失败。该规则不得允许发布状态绕过 Risk Engine，也不得把系统校验失败改写为投资性 `NO_TRADE`。

#### Scenario: Risk 前 CIO 契约校验失败
- **WHEN** 两个专业 Agent 已完成，但 CIO 草案在进入 Risk Engine 前因动作条件或 Evidence Closure 失败
- **THEN** Trace 以 `FAILED_VALIDATION` 和对应的 Risk 前 `failed_stage` 终止，`risk_lineage` 可以为空，且 Trace 校验不得返回 `TRACE_RISK_LINEAGE_MISSING`

#### Scenario: Risk 阶段失败保留完整血缘
- **WHEN** 系统已经向 Risk Engine 提交草案后发生校验或持久化失败
- **THEN** Trace 包含 Risk policy、输入哈希、尝试状态、结果或结构化错误以及修改/否决信息；缺少该 lineage 时校验失败

#### Scenario: 失败阶段与错误产物不一致
- **WHEN** `decision_trace.json` 和 `run_error.json` 的 `failed_stage`、`run_id` 或终态不一致
- **THEN** Trace 与 artifact matrix 校验均 fail closed，并返回明确的契约错误

### Requirement: FAILED_VALIDATION 运行必须支持诊断性 Artifact Replay
当前 deterministic artifact replay MUST 识别 `FAILED_VALIDATION` 终态，验证该阶段已经存在的输入、产物、哈希、错误和 lineage，并跳过失败阶段之后按契约不应存在的产物。诊断性 Replay SHALL 证明失败包自洽以及可确定性复验的校验仍得到相同错误类别；它不得生成投资建议、补跑 LLM、伪造 Risk lineage，或被描述为通用 Replay Executor 扩展。

#### Scenario: 重放 Risk 前 FAILED_VALIDATION
- **WHEN** 评审者重放一个 CIO 条件契约校验失败且 Risk 尚未运行的产物包
- **THEN** Replay 验证专业报告、CIO 输入/草案、错误、Trace 和阶段矩阵，确认不存在发布产物，并以诊断通过结束而不要求 Risk 产物

#### Scenario: 失败包缺少阶段必需产物
- **WHEN** `FAILED_VALIDATION` 产物包缺少其 `failed_stage` 之前必须存在的产物或包含阶段之后禁止出现的发布产物
- **THEN** Replay 失败并指出缺失或越界产物，不把原始失败视为合法诊断包

### Requirement: Release Gate 必须根据运行产物返回状态码
系统 MUST 提供确定性的 `check-run`、`release-gate` 或等价命令，直接读取 `terminal_state`、`run_error.json`、Decision Trace、终态 artifact matrix 和实际 Eval 结果后给出机器可读判定。`FAILED_VALIDATION`、未知或非终态、产物不完整、Trace 无效、Evidence 悬空、Risk 被绕过或 Eval 缺失/失败 MUST 返回非零状态；只有完整的 `COMPLETED` 或 `SAFE_NO_TRADE` 运行通过全部门禁时才可返回零。外层 `codex exec` 的 shell exit code MUST NOT 单独决定 Release Gate 结果。

#### Scenario: Codex 进程成功但内部校验失败
- **WHEN** `codex exec` 返回零，但 run 目录中的 `terminal_state` 为 `FAILED_VALIDATION`
- **THEN** Release Gate 输出失败终态、`failed_stage` 和 `run_error` 原因，并返回非零状态

#### Scenario: 完整发布运行通过门禁
- **WHEN** run 目录为 `COMPLETED` 或 `SAFE_NO_TRADE`，终态产物、Trace、Evidence Closure、Risk 要求和实际 Eval 全部有效
- **THEN** Release Gate 返回零并输出可机器读取的 `PASSED` 结果

#### Scenario: 运行目录尚未形成终态
- **WHEN** run 目录缺少可验证终态、错误产物或必要终态产物
- **THEN** Release Gate 返回非零状态并区分不完整运行与已确认的 `FAILED_VALIDATION`
