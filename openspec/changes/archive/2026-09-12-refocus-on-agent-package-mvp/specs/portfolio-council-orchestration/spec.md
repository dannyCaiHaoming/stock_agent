## ADDED Requirements

### Requirement: Agent Package Demo 与真实 Portfolio Council 必须分离
系统 SHALL 将 `DEMO_SCAFFOLD` 作为开发控制面的装配验证 Profile，而不是现有真实 `portfolio-council` 产品 Profile。Demo MAY 使用确定性 Adapter 产生示例角色输出，并静态验证实际 `portfolio-council` Skill 与 Agent Package 绑定；它 MUST NOT 声称入口 Skill 已执行推理、Codex 主线程已担任 CIO 或真实 Subagent 已启动。真实 fixture 或 live 产品 Profile 仍 MUST 使用其声明的真实 Codex Agent、Skill 和 LLM 约束，不得自动降级到 Demo Adapter。

#### Scenario: 运行 Demo Profile
- **WHEN** 开发者显式选择 `DEMO_SCAFFOLD`
- **THEN** 系统执行固定多 Agent 数据流且不启动真实 LLM，验证实际 Package 静态绑定，并在全部产物中保留 Demo 身份和未执行真实 Skill/CIO/Subagent 的边界

#### Scenario: 真实产品 Agent 调用失败
- **WHEN** 真实 `portfolio-council` Profile 无法调用声明的 LLM Agent
- **THEN** 真实运行按原契约失败或安全终止，不切换到 Demo Adapter 伪造产品报告

### Requirement: Demo 拓扑必须传递经过验证的上游对象
Demo 编排 SHALL 逻辑 fan-out 两份独立输入给 Company Analyst 和 Independent Skeptic，并在 fan-in 后将两份结构化响应作为 CIO 的显式输入，再将 CIO 草案作为 deterministic Risk Engine 的显式输入。任何阶段 MUST 在传递前校验发送者、接收者、`run_id`、`invocation_id` 和 Evidence References，并由编排层保存 Dispatch Record；禁止让 Agent 自行选择下一节点，也禁止使用同一个回调冒充多个 Agent 身份。

#### Scenario: Agent 输出传给下一个节点
- **WHEN** 一个 Demo Agent 返回合法响应
- **THEN** 编排器将该原始结构化对象作为下一节点输入的一部分并保留发送者与接收者，不通过重新生成文本替代传递

#### Scenario: 响应来自错误运行
- **WHEN** CIO 输入包含其他 `run_id` 的 Specialist 响应
- **THEN** 编排器在 CIO 响应前拒绝该输入并报告跨运行传递错误

### Requirement: Demo Adapter 必须保留到真实 Agent 的替换接缝
Demo AgentPort 和只读 ToolPort SHALL 与未来 Codex Agent/MCP Adapter 使用相同的请求、响应和角色输出边界。将任一 Demo Specialist 替换成真实 Codex Subagent，或将 CIO Demo Adapter 替换成当前主线程 CIO 时，MUST NOT 要求下游重写 Portfolio、Evidence、专业报告、CIO Draft 或 Risk 契约。

#### Scenario: 后续替换 Company Analyst
- **WHEN** 后续 Change 为 Company Analyst 接入真实 Codex Subagent 和专业 Skills
- **THEN** 该 Agent 仍消费同一类 Gate-scoped 请求并产生同一角色报告，CIO 和 Risk 接口无需因生产者变化而修改
