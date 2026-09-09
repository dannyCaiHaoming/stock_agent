## ADDED Requirements

### Requirement: Execution Replay 必须通过受控的 Codex-native Council 入口运行
Execution Replay MUST 使用经过验证的 Replay Capsule，通过现有 Codex-native `portfolio-council` 入口重新执行研究链路，而不是由 Python callback 重建 LLM 结论。重放运行 MUST 使用新的 `run_id` 和空输出目录，明确关联 `source_run_id`，保留相同 Portfolio、PIT Evidence、研究问题、Model、Agent、Skill、Prompt、Schema、MCP Adapter 和 Risk Policy 版本，并重新生成独立 Agent、CIO、Risk、Trace 和 Eval 产物。原运行目录 MUST 保持只读。

#### Scenario: 重放完整双 Agent Council
- **WHEN** 来源运行在 Evidence Gate 后执行了 Company Analyst、Independent Skeptic 和 CIO
- **THEN** Execution Replay 在相同冻结能力计划下重新调用三个独立上下文，并重新经过 deterministic Risk Engine 和终态校验

#### Scenario: 重放 Agent 前安全终止运行
- **WHEN** 来源运行因全部 Evidence 被 PIT Gate 排除而在 Agent 前合法终止
- **THEN** Execution Replay 重建相同 Gate 输入与允许集合，不调用 Agent，并生成关联来源运行的新安全终态与 Eval

#### Scenario: 试图覆盖历史运行目录
- **WHEN** 新输出目录已存在或与来源目录相同
- **THEN** 系统在任何写入或 LLM 调用前拒绝重放

### Requirement: Ablation Profile 必须与默认产品 Council 隔离
CIO-only、Company Analyst + CIO 和完整双 Specialist Council MUST 作为显式 `EVAL_ABLATION` Profile 运行，使用各自版本化的拓扑输入与输出契约，但不得修改或放宽默认产品 Profile 对 Company Analyst、Independent Skeptic、CIO、Evidence Closure 和 Risk Engine 的要求。Ablation 产物 MUST 标记为实验性、仅供评估且不可作为正常产品建议发布。

#### Scenario: 运行 CIO-only Ablation
- **WHEN** Ablation Runner 选择 Variant A
- **THEN** 现有 CIO 在独立实验上下文中直接消费同一 Gate-scoped Evidence，输出符合 Variant 契约的草案并经过 Risk Engine，且不会伪造 Specialist 报告

#### Scenario: 运行 Company Analyst + CIO Ablation
- **WHEN** Ablation Runner 选择 Variant B
- **THEN** 系统只调用现有 Company Analyst 和 CIO，Trace 明确记录 Skeptic 未参与的实验拓扑，不把它伪装成默认 Council 完整运行

#### Scenario: Ablation 配置被用于产品发布
- **WHEN** 普通 `portfolio-council` 运行或产品 Release Gate 收到 `EVAL_ABLATION` Profile 产物
- **THEN** 系统拒绝将其作为产品建议或生产候选运行通过

### Requirement: 重复 LLM 执行必须遵循模型路由和消耗策略
普通实现与确定性开发验证 SHALL 使用 GPT-5.6 Sol；Runtime Regression、Execution Replay 验收和重复 Ablation LLM 运行 MUST 使用显式 GPT-5.6 Terra。只有架构或 Eval 方法存在书面记录的重大争议且获得人工批准时，才 MAY 使用 GPT-6 Astra。每次真实执行 MUST 记录模型标识、token、延迟、cache provenance 和触发原因，并禁止在输入与所有版本 hash 未变化时无理由重复调用 LLM。

#### Scenario: Regression 使用默认重复运行模型
- **WHEN** 一个需要真实 LLM 的 Regression 或 Ablation 案例没有模型覆盖
- **THEN** Runner 使用 GPT-5.6 Terra，并将模型纳入运行锁和缓存键

#### Scenario: 请求升级 GPT-6 Astra
- **WHEN** 操作者拟因架构或 Eval 方法争议升级模型
- **THEN** 运行必须引用争议记录和人工批准；缺少任一项时 fail closed，不得静默升级

#### Scenario: 确定性反例无需 LLM
- **WHEN** Regression 案例只验证悬空 Evidence、Schema、PIT 或 Risk 的确定性 fail-closed 行为
- **THEN** Runner 不调用 LLM，并在报告中记录零 token 与确定性执行原因
