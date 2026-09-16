## ADDED Requirements

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
