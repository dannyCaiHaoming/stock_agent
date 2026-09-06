## MODIFIED Requirements

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

## ADDED Requirements

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
