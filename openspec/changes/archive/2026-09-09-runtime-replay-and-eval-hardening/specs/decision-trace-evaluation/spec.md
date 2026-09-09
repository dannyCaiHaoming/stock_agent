## ADDED Requirements

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
