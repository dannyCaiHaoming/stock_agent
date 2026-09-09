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

### Requirement: 可执行重放必须依赖完整且内容寻址的 Replay Capsule
每次声明支持 Execution Replay 的 Runtime 运行 MUST 保存或引用不可变的 Replay Capsule，至少包含冻结的 Portfolio 输入、研究问题、`decision_cutoff`、PIT Gate 允许与排除的 Evidence 及其 `source_id`、`as_of`、`retrieved_at`、Agent 定义、Skill、仓库可控 Prompt/Instructions、JSON Schema、Model 标识、Codex runtime、MCP Adapter、Risk Policy、数据版本和全部内容哈希。Replay Capsule MUST 具有版本化 Schema、总哈希和逐文件清单；任何必需对象缺失、哈希不符、模型不可用或版本无法解析时，Execution Replay MUST 在调用 LLM 前 fail closed。

#### Scenario: 历史运行具有完整 Replay Capsule
- **WHEN** 操作者请求对一个支持 Execution Replay 的历史 `run_id` 重新执行
- **THEN** 系统先验证 Capsule Schema、逐项哈希、PIT Evidence 和所有运行依赖，再允许创建重放运行

#### Scenario: Skill 内容与冻结哈希不一致
- **WHEN** Capsule 中的 Skill 版本仍同名但内容哈希与可解析对象不一致
- **THEN** Execution Replay 在任何 Agent 调用前失败，并明确报告缺失或漂移的依赖

#### Scenario: 旧运行没有 Replay Capsule
- **WHEN** 一个历史运行只满足旧版 Artifact Replay 契约而没有完整 Replay Capsule
- **THEN** 系统 MAY 继续执行只读 Artifact Replay，但 MUST 拒绝声称它支持 Execution Replay，且不得从当前工作区猜测或补齐历史资源

### Requirement: Artifact Replay 与 Execution Replay 必须是两个独立模式
Artifact Replay MUST 只读验证原历史运行包的 Schema、哈希、Evidence/PIT、Risk、Trace 和报告一致性，不调用 LLM、不改写历史目录。Execution Replay MUST 从已验证 Replay Capsule 创建全新 `run_id` 和全新输出目录，通过 Codex-native Investment Council 重新执行 Agent、CIO、Risk 和 Eval，并在新 Trace 中记录 `source_run_id`、Capsule hash 和原运行/重放运行的配置等价性；LLM 自然语言和动作不要求逐字节相同，但输入、允许 Evidence、仓库可控指令、版本和安全边界 MUST 一致。

#### Scenario: 执行 Artifact Replay
- **WHEN** 操作者选择 `artifact` 模式重放一个终态运行
- **THEN** 系统只返回历史包自洽性与确定性复验结果，LLM 调用数为零，源目录 hash 保持不变

#### Scenario: 执行 Execution Replay
- **WHEN** 操作者选择 `execution` 模式并提供唯一的新 `run_id` 和空输出目录
- **THEN** 系统通过相同 Codex-native 入口重新执行冻结上下文，保存新运行的完整产物、实际 Eval 和与源运行的差异报告

#### Scenario: 重放输出与原始建议不同
- **WHEN** Execution Replay 在相同冻结上下文上产生不同措辞、Confidence 或合法动作
- **THEN** 系统将差异作为非确定性观察交给 Eval，不因非逐字一致自动失败；Schema、Evidence、PIT、Risk 或 Trace 不变量不一致时仍必须失败

#### Scenario: 重放工作区或配置发生漂移
- **WHEN** 已物化的 Replay Capsule 中任一文件或目录仍可写，或 Agent、Skill、Prompt、Schema、Model、Evidence、Risk Policy 等任一实际内容哈希与源运行不一致
- **THEN** Finalizer 必须重新计算逐类配置哈希并 fail closed，不得继承或写死 `configuration_equivalent=true`

### Requirement: Runtime Trace Integrity Validator 必须统一且终态感知
所有 Artifact Replay、Execution Replay、Runtime Eval、Regression 和 Promotion Gate MUST 调用同一版本化 Runtime Trace Integrity Validator。Validator MUST 校验 `run_id`、Portfolio Snapshot、Evidence Closure、PIT lineage、Agent 名称与版本、Skill version/hash、Prompt/Instructions hash、Model、Schema version/hash、Risk Policy、Agent 输入输出 hash、终态产物 hash、`terminal_state`、`failed_stage` 和 Risk lineage，并按终态和实际到达阶段应用不同规则。Risk 前失败 MAY 没有 Risk lineage；已进入 Risk 或发布阶段的运行缺少相应 lineage MUST fail closed。

#### Scenario: Risk 前 Specialist 输出非法
- **WHEN** 运行在 Specialist Validation 阶段以 `FAILED_VALIDATION` 终止且尚未调用 Risk Engine
- **THEN** Validator 接受空 Risk lineage，但要求对应 Agent 输入、调用、输出或错误、`failed_stage` 和已有产物完整一致

#### Scenario: 发布运行绕过 Risk Engine
- **WHEN** `COMPLETED` 或 `SAFE_NO_TRADE` 运行形成 CIO 草案但没有完整 Risk lineage
- **THEN** Validator 拒绝该 Trace，并阻止 Eval、Regression 和 Promotion 通过

#### Scenario: Trace 中的输入输出 hash 被篡改
- **WHEN** 任一 Agent、Evidence、Risk 或终态产物的实际内容与 Trace hash 不一致
- **THEN** 所有消费该 Trace 的后续流程均 fail closed，并报告可定位的 lineage 错误

### Requirement: Runtime Eval 必须直接评估真实运行产物
Runtime Eval Runner MUST 直接读取实际 Runtime 运行包、统一 Trace 验证结果和 Replay 结果，自动输出机器可读 `eval/result.json` 与同源的人类可读 `eval/report.md`。Eval MUST 覆盖 Schema 合法性、Evidence 引用正确率、PIT 泄漏、NO_TRADE 合理性、Risk 绕过、Analyst Thesis 的 Evidence 支持、Skeptic 有效反证、CIO 冲突处理和 Confidence 与证据充分程度的基本一致性；不得用人工填写的静态 candidate 文件、目录存在性或预设具体股票动作替代真实运行评分。

#### Scenario: 评估完整发布运行
- **WHEN** Eval Runner 收到真实 `COMPLETED` 或 `SAFE_NO_TRADE` 运行目录
- **THEN** 它验证并引用实际决策、报告、Trace、Evidence、Agent 报告、Risk 和执行证明，输出每个维度的状态、证据路径、评分理由、grader 版本/hash 和总结果

#### Scenario: 评估预期的 fail-closed 案例
- **WHEN** Regression 案例预期悬空 Evidence 或 Specialist 非法输出导致 `FAILED_VALIDATION`
- **THEN** Eval 在独立评估目录记录正确失败阶段、禁止产物缺失和安全终止结果，不要求该失败运行伪造 `decision.json`、`report.md` 或 Risk lineage

#### Scenario: 人工 candidate 报告声称全部通过
- **WHEN** Promotion 输入只有手工编辑的 candidate JSON 而没有可解析的真实 run IDs、Trace、Eval 和 Regression 产物
- **THEN** Eval 与 Promotion Gate 拒绝该输入，不将声明值视为执行证据

### Requirement: Eval 必须分离确定性硬门禁与语义 Rubric
Schema、Evidence Closure、PIT Leakage、Risk Bypass、Trace 完整性和产物哈希 MUST 由确定性检查判定，任一失败不得被平均分抵消。NO_TRADE 解释、Thesis 支持质量、Skeptic 反证质量、CIO 冲突处理和 Confidence 校准 SHALL 由版本化结构化 Rubric 评估，Rubric 输出 MUST 包含适用性、分项结果、引用的 Claim/Evidence、grader 模型、Prompt/Schema hash 和理由；Rubric 不得把市场涨跌、固定动作或固定 Confidence 数值当作唯一正确答案。

#### Scenario: 语义分数高但存在 Future Evidence
- **WHEN** 语义 Rubric 给出高分而确定性 PIT 检查发现未来信息泄漏
- **THEN** Eval 总结果为失败，并保留语义结果作为诊断信息但不得覆盖硬门禁

#### Scenario: Evidence 不足时降低置信度或 NO_TRADE
- **WHEN** 运行存在已记录的重大证据缺口、过期或未解决冲突
- **THEN** Rubric 检查 Confidence 和动作是否与这些限制方向一致，但不要求 Confidence 等于预设常数

### Requirement: Regression Set 必须以 expected_invariants 描述至少十二类案例
固定、版本化 Regression Set MUST 包含正常研究、Evidence 不足、Evidence 全部过期、Future information leakage、Analyst/Skeptic 强冲突、悬空 Evidence、Risk veto、高集中度持仓、LLM 过度自信、必须 `NO_TRADE`、合法非 `NO_TRADE` 动作结构以及 Specialist 非法输出十二类案例。每个案例 MUST 声明 `case_id`、输入与 Evidence 版本、是否需要真实 LLM、适用拓扑、`expected_invariants` 和硬/软判定类型；不得硬编码某只股票必须 BUY 或 Confidence 必须等于固定数值。合法减仓类动作 MUST 使用现有 canonical `TRIM`/`EXIT`，不得引入 `REDUCE` 枚举。

#### Scenario: 运行固定 Regression Set
- **WHEN** Regression Runner 执行一个候选版本
- **THEN** 每个案例生成全局唯一 run ID，Runner 亲自执行 Trace Validator、Artifact Replay 和 Runtime Eval 验证，并保存实际命令、产物路径、哈希与执行证明；套件报告列出通过、失败、跳过及其原因

#### Scenario: 两个案例复用同一运行身份
- **WHEN** Regression 输入索引或缓存让两个不同案例指向同一个 `run_id`
- **THEN** Runner 在汇总前确定性拒绝该套件，不得把重复运行伪装成独立案例覆盖

#### Scenario: Regression 仅提供上游状态摘要
- **WHEN** 案例只提供 `status=PASS`、Eval 摘要或缓存结论，而底层 Trace、Artifact Replay 或 Runtime Eval 无法重新验证
- **THEN** Runner fail closed，并将该案例标记为缺少真实执行证据

#### Scenario: 必须 NO_TRADE 的安全案例
- **WHEN** 案例的确定性前提为全部 Evidence 过期、PIT 泄漏不可排除或 Risk veto
- **THEN** `expected_invariants` 可以要求合法 `NO_TRADE` 或 fail-closed，但不得规定自然语言 Thesis 或固定 Confidence

#### Scenario: 无输入或版本变化的重复运行
- **WHEN** case、候选 hash、模型、Evidence、拓扑和 Rubric 版本均未变化且已有完整可信结果
- **THEN** Regression Runner复用已验证结果并记录 cache provenance；只有显式强制或相关 hash 变化才重新调用 LLM

### Requirement: Ablation 必须基于可比的真实运行而非人工分数
Ablation Runner MUST 对同一组冻结 Portfolio、PIT Evidence、Model、Schema/Rubric 版本和 Risk Policy 运行 A（CIO only）、B（Company Analyst + CIO）和 C（Company Analyst + Independent Skeptic + CIO）三种隔离拓扑，并从真实运行产物计算 Evidence grounding、反证质量、NO_TRADE 质量、冲突处理、Risk violation、Schema failure、总 token 和端到端延迟。报告 MUST 同时展示逐案例结果、聚合结果、缺失维度的 `NOT_APPLICABLE` 和成本差异，不得预设 C 必然优于 A 或 B。

#### Scenario: 多 Agent 没有可测增益
- **WHEN** C 相对 A/B 未达到预先声明的质量阈值或只增加 token 与延迟
- **THEN** Ablation 报告明确输出 `NO_MEASURABLE_GAIN` 或负增益及置信限制，不得改写为成功叙事

#### Scenario: Variant 使用不同 Evidence
- **WHEN** 任意两个 Variant 的 Portfolio hash、Gate Evidence IDs/hash、Model 或 Risk Policy 不一致
- **THEN** 该组比较被判为不可比并失败，不得计算或发布质量增益

#### Scenario: Ablation 使用静态 VariantRun 分数
- **WHEN** 只有人工构造的聚合分数而没有每个 Variant 的真实 run ID、Trace、Eval、token 和延迟来源
- **THEN** Ablation 不能作为 Promotion Gate 的有效输入
