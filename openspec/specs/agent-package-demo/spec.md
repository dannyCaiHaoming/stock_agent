# agent-package-demo Specification

## Purpose

定义一个不依赖真实 LLM、网络或真实市场数据的 Agent Package 演示闭环，用最小可观察契约证明多个角色能够接收输入、独立响应、传递结构化结果、经过确定性风险检查并生成最终报告。

## Requirements

### Requirement: Demo Profile 必须使用显式且独立的运行身份
系统 SHALL 提供显式 `DEMO_SCAFFOLD` Profile。它 MUST 接受任意符合 Demo Schema 的 Portfolio、Evidence、研究问题和 `decision_cutoff`，并将全部产物标记为 `synthetic: true`、`advisory_only: true` 和 `llm_used: false`。该 Profile MUST NOT 被默认产品入口、真实研究验收或候选晋升读取为真实 Council 运行。

#### Scenario: 启动 Agent Package Demo
- **WHEN** 开发者使用 Demo 入口提交合法示例输入
- **THEN** 系统建立独立 Demo 运行并明确展示 synthetic、非 LLM、非投资建议状态，不访问网络、真实 Provider 或券商

#### Scenario: Demo 产物被用于真实研究验收
- **WHEN** 真实产品验收或 Promotion Gate 收到 `DEMO_SCAFFOLD` 产物
- **THEN** 系统拒绝把该产物认定为真实 LLM、真实 Evidence 或产品研究质量证明

### Requirement: Demo 必须绑定实际 Agent Package 拓扑
Demo MUST 解析并验证仓库实际 Plugin manifest、`portfolio-council` Skill、CIO Role Policy、Company Analyst 与 Independent Skeptic Agent definitions、各角色声明的 Skills、只读 Tool/MCP 契约、角色输出 Schema、deterministic Risk Engine 和最终输出契约。拓扑 MUST 按角色列出 Input、Tool/Data、Skill/Reasoning、Structured Output 和 MVP Check；静态绑定通过只表示 `binding_verified=true`，Demo MUST 同时记录 `reasoning_executed=false`。未纳入 Demo 的已有 Agent MUST 被列为 excluded 及原因，不得实例化为空角色。

#### Scenario: 实际 Package 绑定完整
- **WHEN** Demo 启动前解析当前仓库 Agent Package
- **THEN** 拓扑能从入口 Skill 定位 CIO、两个 Specialist、各自 Skills/Tools/Schema 和 Risk/Output 节点，并明确 Skill 未实际执行推理

#### Scenario: Agent definition 与拓扑声明不一致
- **WHEN** 拓扑引用不存在的 Agent、Skill、Tool 或输出 Schema，或角色声明与实际 Package 不一致
- **THEN** Demo 在任何角色响应前进入 `DEMO_FAILED_VALIDATION`，不得只用同名 Demo 组件继续

### Requirement: Demo 必须定义完整且可观察的 Agent 数据流
Demo SHALL 按以下固定拓扑执行：Input → Evidence Store/Bundle → PIT Evidence Gate → Company Analyst Demo Adapter 与 Independent Skeptic Demo Adapter → CIO Demo Adapter → deterministic Risk Engine → Final Report。两个 Specialist 构成逻辑 fan-out/fan-in；本阶段不要求真实并行线程。每个节点 MUST 接收结构化输入并产生结构化输出；下游输入 MUST 来自已完成且校验通过的上游 Artifact，不得通过隐式全局状态或报告文本反向推断。

#### Scenario: 完成端到端 Demo
- **WHEN** 示例 Portfolio 和 Evidence 通过输入及 PIT 校验
- **THEN** 两个 Specialist 分别响应，CIO 接收两份有效输出，Risk Engine 接收 CIO 草案，最终生成结构化决策与可读报告

#### Scenario: 上游输出无效
- **WHEN** 任一 Agent 输出缺少必填字段、身份不匹配或包含非法 Evidence 引用
- **THEN** 链路在进入下一节点前失败并指出失败角色，不使用占位输出继续伪造完整成功

### Requirement: 每个 Demo Agent 必须能够独立响应
Company Analyst、Independent Skeptic 和 CIO SHALL 各自暴露同一类 Agent Response Envelope，至少包含 `schema_version`、`run_id`、`invocation_id`、`agent_name`、`status`、`input_refs`、`output`、`producer_type` 和 `llm_used`。开发者 MUST 能在不运行完整链路的情况下，用合法的上游输入单独调用每个角色并取得可校验响应。下一接收方 MUST 由编排层的 Dispatch Record 指定，不得由专业 Agent 的领域响应决定。

#### Scenario: 单独调用 Company Analyst
- **WHEN** Company Analyst Demo Adapter 收到合法 Gate 输出
- **THEN** 它返回自己的结构化研究响应，且不生成 CIO 动作或最终报告

#### Scenario: 单独调用 CIO
- **WHEN** CIO Demo Adapter 收到两份已验证 Specialist 响应和组合摘要
- **THEN** 它返回结构化决策草案，编排层另外记录该草案被发送给 Risk Engine

### Requirement: Demo Agent 必须通过只读 Tool Port 获取 Evidence
Company Analyst 与 Independent Skeptic Demo Adapter MUST 使用与现有 Evidence Query MCP 契约兼容的只读 Tool Port，根据本次 Gate 的 `allowed_evidence_ids` 查询事实；Company Analyst MAY 使用与现有确定性计算工具兼容的 Math Port。CIO 核验引用时 MUST 使用同一 Evidence Query Port。任何 Demo Agent MUST NOT 直接读取原始 fixture、Evidence 文件、被排除事实或隐式全局数据。

#### Scenario: Specialist 查询允许 Evidence
- **WHEN** Demo Specialist 需要取得事实内容
- **THEN** 它通过 Tool Port 提交本次 run、invocation、agent 和允许 Evidence IDs，并只收到 Gate 合格事实

#### Scenario: Specialist 绕过 Tool Port
- **WHEN** Demo Adapter 尝试直接读取原始输入文件或查询被 Gate 排除的 Evidence ID
- **THEN** 访问被拒绝且运行进入 `DEMO_FAILED_VALIDATION`，不得把直接读取结果传给 CIO

### Requirement: Specialist Demo 首轮必须保持输入隔离
Company Analyst 与 Independent Skeptic SHALL 读取同一份 Gate 合格 Evidence，但 Skeptic 的首轮输入 MUST NOT 包含 Analyst 输出，Analyst 输入也 MUST NOT 包含 Skeptic 输出。两者完成后才可由 CIO 同时读取。

#### Scenario: 检查两个 Specialist 输入
- **WHEN** Demo 完成双 Specialist 调用
- **THEN** 两份输入均只包含 Portfolio 摘要、研究问题、截止时点和允许 Evidence，且不包含对方输出

### Requirement: Demo Evidence 与 Risk 安全边界必须保留
每项 Demo 事实 MUST 包含 `evidence_id`、`source_id`、`as_of` 和 `retrieved_at`，且 `as_of` 和 `retrieved_at` 不得晚于 `decision_cutoff`。所有 CIO 草案 MUST 经过现有 deterministic Risk Engine；Risk 否决不得被 Demo Adapter 覆盖。

#### Scenario: 示例 Evidence 来自未来
- **WHEN** 示例事实的 `as_of` 或 `retrieved_at` 晚于 `decision_cutoff`
- **THEN** PIT Gate 在任何 Specialist 响应前排除该事实，并且下游不得引用它

#### Scenario: Demo 草案违反硬风险约束
- **WHEN** CIO Demo Adapter 产生违反现行硬约束的草案
- **THEN** Risk Engine 确定性修改或否决该草案，最终报告展示风险结果而不是原草案动作

### Requirement: Demo 必须区分领域状态与运行终态
Agent Response 的合法领域状态 SHALL 包含 `COMPLETE`、`INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE` 和 `TIMEOUT`。后三种状态 MUST 作为结构化响应传给 CIO，由 CIO 形成保守草案或 `NO_TRADE`；非法 Schema、身份、跨 run、引用或传递 MUST NOT 转换成领域状态。Demo 运行终态 MUST 仅为 `DEMO_COMPLETED`、`DEMO_SAFE_NO_TRADE` 或 `DEMO_FAILED_VALIDATION`。

#### Scenario: Specialist 合法报告证据不足
- **WHEN** 一个或两个 Specialist 返回结构合法的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE` 或 `TIMEOUT`
- **THEN** CIO 仍消费这些状态并形成合法 Demo 决策，不能由编排器伪造 Specialist 的研究内容

#### Scenario: Gate 后没有可用 Evidence
- **WHEN** PIT Gate 排除全部 Evidence
- **THEN** Demo 在 Agent 前形成 `DEMO_SAFE_NO_TRADE`，不伪造三个 Agent 响应

#### Scenario: Agent 输出引用不存在的 Evidence
- **WHEN** 任一 Agent Response 包含悬空、被排除或跨 run Evidence Reference
- **THEN** Demo 形成 `DEMO_FAILED_VALIDATION`，不把该错误包装成 `NO_TRADE`

### Requirement: Demo 完成必须产生最小可审阅产物
一次成功且到达 CIO 的 Demo MUST 保存原始输入、Agent Package 拓扑、Gate 结果、三个 Agent Response Envelope、编排 Dispatch Records、Risk 结果、`decision.json` 和中文 `report.md`。Agent 前安全终止 MUST 保存输入、拓扑、Gate、终态决策和报告，但不得伪造 Agent 或 Risk 产物。全部产物 SHALL 足以沿固定拓扑查看每一步的实际输入来源和输出去向，但 MUST NOT 要求 Replay Capsule、语义 Eval、Regression、Calibration、Ablation、Promotion 结果或真实 LLM 事件。

#### Scenario: 审阅 Demo 产物
- **WHEN** Demo 命令成功结束
- **THEN** 操作者可以依次打开输入、Gate、Analyst、Skeptic、CIO、Risk、Decision 和 Report 产物确认链路完整
